"""Campiona un workload esplicito senza attribuire capacità non misurate."""
import argparse
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _missing(reason: str) -> tuple[None, str]:
    return None, reason


def parse_proc_status(text: str) -> dict:
    """Estrae KiB da /proc/*/status; assenze restano None con il motivo."""
    fields = {"VmRSS": "rss_bytes", "RssAnon": "rss_anon_bytes"}
    values = {name: None for name in fields.values()}
    reasons = {name: "campo assente in /proc/1/status" for name in fields.values()}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key not in fields:
            continue
        try:
            values[fields[key]] = int(value.split()[0]) * 1024
            reasons[fields[key]] = None
        except (IndexError, ValueError):
            reasons[fields[key]] = "valore non interpretabile in /proc/1/status"
    return {**values, **{f"{key}_reason": value for key, value in reasons.items()}}


def parse_smaps_rollup(text: str) -> dict:
    """Private_Clean + Private_Dirty, distinti da RSS/USS."""
    values = {}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key in ("Private_Clean", "Private_Dirty"):
            try:
                values[key] = int(value.split()[0]) * 1024
            except (IndexError, ValueError):
                pass
    if len(values) != 2:
        return {"private_bytes": None, "private_bytes_reason": "campi privati assenti in smaps_rollup"}
    return {"private_bytes": values["Private_Clean"] + values["Private_Dirty"], "private_bytes_reason": None}


def _read_cgroup() -> dict:
    current = Path("/sys/fs/cgroup/memory.current")
    maximum = Path("/sys/fs/cgroup/memory.max")
    if not current.is_file() or not maximum.is_file():
        return {"usage_bytes": None, "limit_bytes": None,
                "reason": "cgroup v2 memory files non disponibili"}
    try:
        limit = maximum.read_text().strip()
        return {"usage_bytes": int(current.read_text().strip()),
                "limit_bytes": None if limit == "max" else int(limit), "reason": None}
    except (OSError, ValueError) as exc:
        return {"usage_bytes": None, "limit_bytes": None, "reason": str(exc)}


def _process_sample(pid: int) -> dict:
    row = {"pid": pid, "ppid": None, "rss_bytes": None, "private_bytes": None,
           "uss_bytes": None, "io_read_bytes": None, "io_write_bytes": None,
           "cpu_user_seconds": None, "cpu_system_seconds": None, "reason": None}
    try:
        process = psutil.Process(pid)
        with process.oneshot():
            memory = process.memory_info()
            row.update(ppid=process.ppid(), rss_bytes=memory.rss)
            if hasattr(memory, "private"):
                row["private_bytes"] = memory.private
            else:
                row["private_bytes_reason"] = "private Windows non supportata"
            try:
                row["uss_bytes"] = process.memory_full_info().uss
            except (psutil.AccessDenied, AttributeError) as exc:
                row["uss_bytes_reason"] = str(exc)
            try:
                io = process.io_counters()
                row.update(io_read_bytes=io.read_bytes, io_write_bytes=io.write_bytes)
            except (psutil.AccessDenied, AttributeError) as exc:
                row["io_reason"] = str(exc)
            cpu = process.cpu_times()
            row.update(cpu_user_seconds=cpu.user, cpu_system_seconds=cpu.system)
    except (psutil.AccessDenied, psutil.NoSuchProcess) as exc:
        row["reason"] = str(exc)
    return row


def _system_sample() -> dict:
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {"virtual_memory_total_bytes": memory.total, "virtual_memory_available_bytes": memory.available,
            "swap_total_bytes": swap.total, "swap_used_bytes": swap.used, "cgroup": _read_cgroup()}


def _docker_qdrant(name: str) -> dict:
    if not shutil.which("docker"):
        return {"rss_bytes": None, "private_bytes": None, "reason": "docker non disponibile"}
    try:
        script = ("for p in /proc/[0-9]*; do [ \"$(cat $p/comm 2>/dev/null)\" = qdrant ] && "
                  "pid=${p##*/} && break; done; [ -n \"$pid\" ] || exit 1; "
                  "printf '__PID__=%s\\n__STATUS__\\n' \"$pid\"; cat /proc/$pid/status; "
                  "printf '__SMAPS__\\n'; cat /proc/$pid/smaps_rollup; printf '__CURRENT__\\n'; "
                  "cat /sys/fs/cgroup/memory.current; printf '__MAX__\\n'; cat /sys/fs/cgroup/memory.max; "
                  "printf '__STAT__\\n'; cat /sys/fs/cgroup/memory.stat")
        completed = subprocess.run(["docker", "exec", name, "sh", "-c", script], text=True,
                                   capture_output=True, timeout=10, check=True)
        pid = completed.stdout.split("__PID__=", 1)[1].splitlines()[0]
        status = parse_proc_status(completed.stdout.split("__STATUS__\n", 1)[1].split("__SMAPS__\n", 1)[0])
        private = parse_smaps_rollup(completed.stdout.split("__SMAPS__\n", 1)[1].split("__CURRENT__\n", 1)[0])
        cgroup = _parse_container_cgroup(completed.stdout.split("__CURRENT__\n", 1)[1])
        return {"pid": int(pid), **status, **private, "cgroup": cgroup, "reason": None}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"rss_bytes": None, "private_bytes": None, "reason": str(exc)}


def _parse_container_cgroup(text: str) -> dict:
    try:
        current, remainder = text.split("__MAX__\n", 1)
        maximum, stat = remainder.split("__STAT__\n", 1)
        current, maximum = current.strip(), maximum.strip()
        cache = next((line.split()[1] for line in stat.splitlines() if line.startswith("file ")), None)
        return {"usage_bytes": int(current), "limit_bytes": None if maximum == "max" else int(maximum),
                "cache_bytes": int(cache) if cache is not None else None,
                "reason": None if cache is not None else "cache non presente in memory.stat"}
    except (OSError, ValueError, StopIteration, subprocess.SubprocessError) as exc:
        return {"usage_bytes": None, "limit_bytes": None, "cache_bytes": None, "reason": str(exc)}


def _sample(root: psutil.Process, qdrant: dict | None) -> tuple[dict, dict[int, float]]:
    try:
        processes = [root, *root.children(recursive=True)]
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        processes = [root]
    identities = {}
    for process in processes:
        try:
            identities[process.pid] = process.create_time()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    return {"utc": _utc(), "monotonic_seconds": time.monotonic(),
            "processes": [_process_sample(process.pid) for process in processes],
            "system": _system_sample(), "device": {"kind": "cpu/default", "memory_bytes": None,
            "reason": "GPU non misurata: NVIDIA API non implementata"},
            "qdrant": qdrant}, identities


def _request_graceful_stop(process: subprocess.Popen) -> dict:
    """Solo una richiesta graceful: nessun timeout né kill automatico."""
    if process.poll() is not None:
        return {"requested": False, "reason": "workload già terminato"}
    if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
            return {"requested": True, "signal": "CTRL_BREAK_EVENT", "scope": "process group"}
        except OSError as exc:
            return {"requested": False, "reason": f"CTRL_BREAK_EVENT non inviabile: {exc}"}
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGTERM)
            return {"requested": True, "signal": "SIGTERM", "scope": "process group"}
        except OSError as exc:
            return {"requested": False, "reason": f"SIGTERM gruppo non inviabile: {exc}"}
    return {"requested": False, "reason": "gruppo graceful non garantibile su questa piattaforma"}


def _same_process_alive(pid: int, created: float) -> bool:
    try:
        candidate = psutil.Process(pid)
        return candidate.create_time() == created and candidate.status() != psutil.STATUS_ZOMBIE
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return False


def _wait_for_workload(process: subprocess.Popen, known_pids: dict[int, float]) -> None:
    """Non forza PID: aspetta root e figli già osservati, anche dopo un errore sampler."""
    while process.poll() is None or any(
        _same_process_alive(pid, created) for pid, created in known_pids.items() if pid != process.pid
    ):
        time.sleep(0.05)


def _write_report(output: Path, payload: dict) -> None:
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)


def run_sampler(command: list[str], output: Path, interval: float = 0.2,
                qdrant_container: str | None = None) -> int:
    if interval <= 0:
        raise ValueError("--interval deve essere positivo")
    output.parent.mkdir(parents=True, exist_ok=True)
    stdout_path = output.with_suffix(".stdout.log")
    stderr_path = output.with_suffix(".stderr.log")
    raw_path = output.with_suffix(".jsonl")
    started_monotonic, started_utc = time.monotonic(), _utc()
    error = None
    process = None
    known_pids: dict[int, float] = {}
    shutdown = {"requested": False, "reason": "nessuna richiesta stop"}
    qdrant_state = {"sample": None, "thread": None, "deadline_monotonic": started_monotonic}

    def start_qdrant(now: float) -> None:
        deadline = qdrant_state["deadline_monotonic"]
        if not qdrant_container or now < deadline or qdrant_state["thread"] and qdrant_state["thread"].is_alive():
            return
        while qdrant_state["deadline_monotonic"] <= now:
            qdrant_state["deadline_monotonic"] += 1.0
        def collect() -> None:
            begun = time.monotonic()
            qdrant_state["sample"] = {**_docker_qdrant(qdrant_container), "deadline_monotonic": deadline,
                                       "finished_monotonic": time.monotonic(),
                                       "duration_seconds": round(time.monotonic() - begun, 3)}
        qdrant_state["thread"] = threading.Thread(target=collect, daemon=True)
        qdrant_state["thread"].start()

    def _report_payload(completion: str) -> dict:
        return {"schema_version": 1, "started_utc": started_utc, "finished_utc": _utc(),
                "runtime_seconds": round(time.monotonic() - started_monotonic, 3), "command": command,
                "interval_seconds": interval, "qdrant_container": qdrant_container,
                "exit_code": process.returncode if process is not None else None,
                "raw_samples": str(raw_path), "stdout": str(stdout_path), "stderr": str(stderr_path),
                "python": sys.version, "platform": platform.platform(), "sampler_error": error,
                "completion": completion, "shutdown": shutdown,
                "shutdown_note": "Nessun kill automatico: su errore si attende il termine naturale; Ctrl-C richiede solo stop graceful di gruppo quando supportato."}

    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        try:
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, text=True,
                                       creationflags=flags, start_new_session=os.name != "nt")
            root = psutil.Process(process.pid)
            with raw_path.open("w", encoding="utf-8") as raw:
                while process.poll() is None:
                    now = time.monotonic()
                    start_qdrant(now)
                    row, discovered = _sample(root, qdrant_state["sample"])
                    known_pids.update(discovered)
                    raw.write(json.dumps(row, ensure_ascii=False) + "\n")
                    raw.flush()
                    time.sleep(interval)
        except BaseException as exc:
            error = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, KeyboardInterrupt) and process is not None:
                shutdown = _request_graceful_stop(process)
            checkpoint = _report_payload("waiting_for_natural_exit")
            _write_report(output, checkpoint)
        finally:
            if process is not None:
                _wait_for_workload(process, known_pids)
            elif not raw_path.exists():
                raw_path.write_text("", encoding="utf-8")
    qdrant_thread = qdrant_state["thread"]
    if qdrant_thread is not None:
        qdrant_thread.join(timeout=10)
        final_qdrant = qdrant_state["sample"] if not qdrant_thread.is_alive() else {
            "reason": "lettura Qdrant non completata entro 10 s", "deadline_monotonic": qdrant_state["deadline_monotonic"]}
        with raw_path.open("a", encoding="utf-8") as raw:
            raw.write(json.dumps({"event": "qdrant_final", "utc": _utc(), "qdrant": final_qdrant}, ensure_ascii=False) + "\n")
    payload = _report_payload("completed")
    _write_report(output, payload)
    return 1 if error else (process.returncode or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--qdrant-container")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="workload dopo --")
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("specificare COMMAND ARG... dopo --")
    try:
        return run_sampler(command, args.output, args.interval, args.qdrant_container)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())

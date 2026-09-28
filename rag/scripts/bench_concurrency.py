"""Harness P0 read-only per il carico di POST /ask."""
import asyncio
import codecs
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx


BASELINE_COMMIT = "ea0cf91"
ROOT = Path(__file__).resolve().parents[2]
SUCCESS_STATUSES = frozenset(("success", "abstained", "graph_answer", "no_results", "no_graph_nodes"))


def _percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def load_metadata(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("--metadata deve contenere un oggetto JSON")
    return payload


def run_metadata(args, queries):
    return {
        "command": ["scripts/bench.py", "--concurrency-bench", "--url", args.url,
                    "--concurrency", *map(str, args.concurrency), "--requests", str(args.requests),
                    "--warmup", str(args.warmup), "--response-mode", args.response_mode,
                    "--queries", args.queries, "--out", args.out, "--timeout", str(args.timeout),
                    "--cache-cohort", args.cache_cohort],
        "queries_sha256": hashlib.sha256(json.dumps(queries, ensure_ascii=False).encode()).hexdigest(),
        "timeout_seconds": args.timeout, "ask_top_k": 5,
    }


def _command(args):
    try:
        completed = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=3, check=True)
        return completed.stdout.strip(), None
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)


def _sha(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest(), None
    except OSError as exc:
        return None, str(exc)


async def consume_ndjson(chunks, *, started, clock=time.perf_counter):
    """Legge NDJSON incrementale: solo delta testuale determina TTFT."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    pending = ""
    meta = {}
    text_bytes = 0
    ttft_ms = None
    first_text_monotonic = None
    terminal = None
    error = None
    result = None

    def handle(line):
        nonlocal meta, text_bytes, ttft_ms, first_text_monotonic, terminal, error, result
        if terminal is not None:
            error = "protocollo NDJSON non valido: evento dopo terminale"
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            error = f"NDJSON non valido: {exc.msg}"
            return
        if not isinstance(event, dict):
            error = "evento NDJSON non valido: oggetto richiesto"
            return
        kind = event.get("type")
        now = clock()
        if kind == "meta":
            meta = event
        elif kind == "delta":
            text = event.get("text")
            if not isinstance(text, str):
                error = "protocollo NDJSON non valido: delta.text stringa richiesta"
            elif text:
                text_bytes += len(text.encode("utf-8"))
                if ttft_ms is None:
                    first_text_monotonic = now
                    ttft_ms = round((now - started) * 1000, 3)
        elif kind == "result":
            if not isinstance(event.get("value"), dict):
                error = "evento NDJSON non valido: result.value oggetto richiesto"
            else:
                terminal = kind
                result = event["value"]
        elif kind == "error":
            terminal = kind
            error = str(event.get("detail") or event.get("error") or "errore stream")
        else:
            error = "evento NDJSON non valido: type sconosciuto"

    async for chunk in chunks:
        pending += decoder.decode(chunk)
        while "\n" in pending:
            line, pending = pending.split("\n", 1)
            if line.strip():
                handle(line)
    pending += decoder.decode(b"", final=True)
    if pending.strip():
        handle(pending)
    if terminal is None and error is None:
        error = "EOF senza evento terminale"
    return {"ttft_ms": ttft_ms, "first_text_monotonic": first_text_monotonic,
            "terminal": terminal, "error": error, "meta": meta, "result": result, "text_bytes": text_bytes}


async def _one(client, url, question, response_mode, timeout, clock):
    started = clock()
    row = {"question": question, "dispatch_monotonic": started, "first_text_monotonic": None,
           "finish_monotonic": None, "response_mode": response_mode, "status_code": None,
           "application_status": None, "terminal_event": None, "ttft_ms": None, "total_ms": None,
           "cached": None, "index_version": None, "request_id": None, "retrieval_strategy": None,
           "qdrant_collection": None, "text_bytes": None, "outcome": "error", "error": None}
    try:
        payload = {"question": question, "stream": response_mode == "stream"}
        async with asyncio.timeout(timeout):
            if response_mode == "stream":
                async with client.stream("POST", f"{url}/ask", json=payload, timeout=timeout) as response:
                    row["status_code"] = response.status_code
                    if response.is_error:
                        row["error"] = f"HTTP {response.status_code}"
                    else:
                        parsed = await consume_ndjson(response.aiter_bytes(), started=started, clock=clock)
                        row.update(ttft_ms=parsed["ttft_ms"], first_text_monotonic=parsed["first_text_monotonic"],
                                   text_bytes=parsed["text_bytes"], error=parsed["error"], terminal_event=parsed["terminal"])
                        meta = parsed["meta"]
                        row.update(cached=meta.get("cached"), index_version=meta.get("index_version"),
                                   request_id=meta.get("request_id"), retrieval_strategy=meta.get("retrieval_strategy"),
                                   qdrant_collection=meta.get("qdrant_collection"))
                        if parsed["terminal"] == "result" and not parsed["error"]:
                            _set_application_status(row, parsed["result"])
            else:
                response = await client.post(f"{url}/ask", json=payload, timeout=timeout)
                row["status_code"] = response.status_code
                if response.is_error:
                    row["error"] = f"HTTP {response.status_code}"
                else:
                    body = response.json()
                    if not isinstance(body, dict):
                        row["error"] = "risposta JSON non oggetto"
                    else:
                        row.update(cached=body.get("cached"), index_version=body.get("index_version"),
                                   request_id=body.get("request_id"), retrieval_strategy=body.get("retrieval_strategy"),
                                   qdrant_collection=body.get("qdrant_collection"))
                        _set_application_status(row, body)
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        row["error"] = f"timeout totale {timeout}s"
    except (httpx.HTTPError, ValueError) as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        row["finish_monotonic"] = clock()
        row["total_ms"] = round((row["finish_monotonic"] - started) * 1000, 3)
    return row


def _summary(rows, started, finished):
    successes = [row for row in rows if row["outcome"] == "success"]
    total = max(finished - started, 0.000001)
    return {
        "n": len(rows), "successes": len(successes),
        "errors": sum(row["outcome"] == "error" for row in rows),
        "cancelled": sum(row["outcome"] == "cancelled" for row in rows),
        "ttft_p50_ms": _percentile([row["ttft_ms"] for row in successes if row["ttft_ms"] is not None], .5),
        "ttft_p95_ms": _percentile([row["ttft_ms"] for row in successes if row["ttft_ms"] is not None], .95),
        "total_p50_ms": _percentile([row["total_ms"] for row in successes], .5),
        "total_p95_ms": _percentile([row["total_ms"] for row in successes], .95),
        "wall_seconds": round(total, 6), "throughput_successes_per_second": round(len(successes) / total, 6),
        "ttft_samples": sum(row["ttft_ms"] is not None for row in successes),
        "cancellation_probes_not_run": True,
    }


def _set_application_status(row, payload):
    row["application_status"] = payload.get("status")
    if row["application_status"] not in SUCCESS_STATUSES:
        row["error"] = f"status applicativo non valido: {row['application_status']!r}"
    else:
        row["outcome"] = "success"


async def run_cell(client, url, queries, *, concurrency, requests, warmup, response_mode, timeout,
                   clock=time.perf_counter, api_pid=None, engine_pid=None):
    """Closed-loop bounded: warm-up escluso, esattamente `requests` righe misurate."""
    if concurrency < 1 or requests < 1 or not queries:
        raise ValueError("concurrency, requests e queries devono essere non vuoti/positivi")
    for index in range(warmup):
        await _one(client, url, queries[index % len(queries)], response_mode, timeout, clock)
    started = clock()
    stop_sampling = asyncio.Event()
    sampler = asyncio.create_task(sample_memory_peaks(api_pid, engine_pid, stop_sampling))
    semaphore = asyncio.Semaphore(concurrency)

    async def measured(index):
        async with semaphore:
            return await _one(client, url, queries[index % len(queries)], response_mode, timeout, clock)

    try:
        rows = await asyncio.gather(*(measured(index) for index in range(requests)))
    finally:
        stop_sampling.set()
        memory_peaks = await sampler
    finished = clock()
    return {"rows": rows, "summary": _summary(rows, started, finished), "memory_peaks": memory_peaks}


async def sample_memory_peaks(api_pid, engine_pid, stop, interval=0.2):
    """Campiona RSS dei PID indicati; i null restano espliciti per host senza psutil/PID."""
    try:
        import psutil
    except ImportError:
        return {"interval_seconds": interval, "samples": 0,
                "api": {"peak_rss_bytes": None, "reason": "psutil non disponibile"},
                "engine": {"peak_rss_bytes": None, "reason": "psutil non disponibile"}}
    pids = {"api": api_pid, "engine": engine_pid}
    peaks = {name: {"peak_rss_bytes": None, "aggregation": "pid_and_recursive_children",
                    "reason": "PID non fornito" if pid is None else None}
             for name, pid in pids.items()}
    samples = 0
    while True:
        for name, pid in pids.items():
            if pid is None:
                continue
            try:
                process = psutil.Process(pid)
                rss = sum(candidate.memory_info().rss for candidate in [process, *process.children(recursive=True)])
                peaks[name]["peak_rss_bytes"] = max(peaks[name]["peak_rss_bytes"] or 0, rss)
            except psutil.Error as exc:
                peaks[name]["reason"] = str(exc)
        samples += 1
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            break
        except TimeoutError:
            pass
    return {"interval_seconds": interval, "samples": samples, **peaks}


def runtime_metadata(api_pid=None, engine_pid=None):
    memory = {"total_bytes": None, "reason": "psutil non disponibile"}
    processes = {}
    try:
        import psutil
        memory = {"total_bytes": psutil.virtual_memory().total, "reason": None}
        for name, pid in (("api", api_pid), ("engine", engine_pid)):
            if pid is None:
                processes[name] = {"rss_bytes": None, "reason": "PID non fornito"}
            else:
                try:
                    processes[name] = {"pid": pid, "rss_bytes": psutil.Process(pid).memory_info().rss, "reason": None}
                except (psutil.Error, ValueError) as exc:
                    processes[name] = {"pid": pid, "rss_bytes": None, "reason": str(exc)}
    except ImportError:
        processes = {"api": {"rss_bytes": None, "reason": "psutil non disponibile"},
                     "engine": {"rss_bytes": None, "reason": "psutil non disponibile"}}
    commit, commit_reason = _command(["git", "rev-parse", "HEAD"])
    dirty, dirty_reason = _command(["git", "status", "--porcelain"])
    diff, diff_reason = _command(["git", "diff", "--binary"])
    gpu_text, gpu_reason = _command(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"])
    lock_hash, lock_reason = _sha(ROOT / "rag" / "uv.lock")
    return {"baseline_commit": BASELINE_COMMIT, "client_source_commit": commit,
            "client_source_commit_reason": commit_reason, "client_dirty": None if dirty is None else bool(dirty),
            "client_dirty_reason": dirty_reason, "client_diff_sha256": None if diff is None else hashlib.sha256(diff.encode()).hexdigest(),
            "client_diff_reason": diff_reason, "python": sys.version, "httpx_version": httpx.__version__,
            "platform": platform.platform(), "uv_lock_sha256": lock_hash, "uv_lock_reason": lock_reason,
            "cpu_count": os.cpu_count(), "memory": memory, "processes": processes,
            "gpu": {"value": gpu_text, "reason": gpu_reason, "nvidia_smi": shutil.which("nvidia-smi")},
            "ollama": {"url": os.environ.get("VIBECRAFT_OLLAMA_URL"),
                       "model": os.environ.get("VIBECRAFT_OLLAMA_MODEL") or os.environ.get("OLLAMA_MODEL"),
                       "num_ctx": os.environ.get("VIBECRAFT_OLLAMA_NUM_CTX") or os.environ.get("OLLAMA_NUM_CTX"),
                       "num_parallel": os.environ.get("OLLAMA_NUM_PARALLEL"),
                       "reason": "parametri non esportati nell'ambiente"}, "cache_cohort": "declared-by-cli"}


def _save(out, cell, metadata):
    out.mkdir(parents=True, exist_ok=True)
    raw = out / f"raw-k{cell['concurrency']}.jsonl"
    raw.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in cell["rows"]), encoding="utf-8")
    summary = {"metadata": metadata, "memory_peaks": cell["memory_peaks"],
               "gpu_peak": {"peak_memory_bytes": None, "reason": "P0 non campiona un picco GPU; metadata.gpu è istantanea"},
               "config": {key: cell[key] for key in ("concurrency", "requests", "warmup", "response_mode", "cache_cohort")}, **cell["summary"], "raw": raw.name}
    (out / f"summary-k{cell['concurrency']}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def main_from_args(args):
    queries = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    if not isinstance(queries, list) or not all(isinstance(query, str) and query for query in queries):
        raise ValueError("--queries deve contenere una lista JSON di stringhe non vuote")
    headers = {"X-API-Key": os.environ["VIBECRAFT_API_KEY"]} if os.environ.get("VIBECRAFT_API_KEY") else {}

    async def run_all():
        metadata = runtime_metadata(args.api_pid, args.engine_pid)
        metadata.update(run_metadata(args, queries))
        if args.metadata:
            metadata["server"] = load_metadata(args.metadata)
        metadata["cache_cohort"] = args.cache_cohort
        async with httpx.AsyncClient(headers=headers, trust_env=False) as client:
            for concurrency in args.concurrency:
                result = await run_cell(client, args.url.rstrip("/"), queries, concurrency=concurrency,
                                        requests=args.requests, warmup=args.warmup,
                                        response_mode=args.response_mode, timeout=args.timeout,
                                        api_pid=args.api_pid, engine_pid=args.engine_pid)
                _save(Path(args.out), {**result, "concurrency": concurrency, "requests": args.requests,
                                        "warmup": args.warmup, "response_mode": args.response_mode,
                                        "cache_cohort": args.cache_cohort}, metadata)
    asyncio.run(run_all())
    return 0

"""F6 sandbox-only retention run: five consecutive real k=1 deltas, no restore."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue

HERE = Path(__file__).resolve(); RESULTS = HERE.parents[2]; SCRIPTS = HERE.parents[4] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import bench_delta as delta
from disk_inventory import inventory


def fail(message): raise ValueError(message)
def _sha(data): return delta._sha(data)
def save(path, data):
    temp = path.with_suffix(".tmp"); temp.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8"); temp.replace(path)
def event(data, name, **extra): data["events"].append({"event": name, "utc": datetime.now(timezone.utc).isoformat(), **extra})


def tree_hash(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink(): fail(f"frozen copy contains symlink: {path}")
        if path.is_file(): digest.update(path.relative_to(root).as_posix().encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def source_hash(checkout):
    """Hash only frozen RAG source: database and bytecode are run state, not code."""
    root, digest = Path(checkout) / "rag", hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts[0] == "database" or "__pycache__" in relative.parts:
            continue
        if path.is_symlink(): fail(f"source copy contains symlink: {path}")
        if path.is_file(): digest.update(relative.as_posix().encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def paths(checkout_arg, output_arg, frozen_arg):
    result = delta.validate_paths(checkout_arg, output_arg)
    run, raw_frozen = result["run"], Path(frozen_arg).absolute()
    frozen = delta._safe(raw_frozen, RESULTS)
    if not delta._within(frozen, run / "sandbox") or frozen == result["checkout"] or not frozen.is_dir(): fail("frozen copy must be a distinct directory under run/sandbox")
    if not result["collection"].startswith("sidecar_0628_retention_"): fail("collection must use sidecar_0628_retention_ prefix")
    if (frozen / "rag" / "rag_config.yaml").read_bytes() != (result["rag"] / "rag_config.yaml").read_bytes(): fail("frozen and experiment dedicated configs differ")
    if source_hash(frozen) != source_hash(result["checkout"]): fail("frozen and experiment RAG source differ")
    result["frozen"] = frozen; return result


def snapshot(paths, qdrant, version):
    from core.artifacts import artifact_hashes, list_versions, manifest_path
    manifest = json.loads(manifest_path(version).read_text(encoding="utf-8")) if version else None
    journal_path = paths["database"] / "reindex_jobs.jsonl"
    journal = journal_path.read_text(encoding="utf-8") if journal_path.exists() else ""
    return {"current": version, "versions": list_versions(), "manifest": manifest,
            "artifact_hashes": artifact_hashes(version), "qdrant_points": delta._point_digest(qdrant, paths["collection"]),
            "journal": {"path": str(journal_path), "sha256": _sha(journal.encode()),
                        "entries": [json.loads(line) for line in journal.splitlines() if line]},
            "disk": inventory(paths["database"])}


def pinned_reader(frozen_rag, database, version):
    """Child entrypoint: frozen loader plus an F5 lease-backed ColBERT reader."""
    sys.path.insert(0, str(Path(frozen_rag).resolve(strict=True)))
    from core import artifacts
    artifacts.DATABASE_DIR = Path(database).resolve(strict=True)
    arts = artifacts.load_artifacts(required=("colbert",), version=version)
    from core.colbert_store import ColbertStore
    store = ColbertStore.open_version(database, version)
    try:
        key = next(iter(store))
        vector = store[key]
        fingerprint = {"chunk": key, "sha256": _sha(vector.tobytes()),
                       "shape": list(vector.shape), "dtype": str(vector.dtype),
                       "loaded_colbert_chunks": len(arts.colbert_store)}
        print(json.dumps({"status": "READY", "version": version, "fingerprint": fingerprint}), flush=True)
        for line in sys.stdin:
            if line.strip() == "CHECK":
                current = store[key]
                check = {**fingerprint, "sha256": _sha(current.tobytes()),
                         "shape": list(current.shape), "dtype": str(current.dtype)}
                print(json.dumps({"status": "CHECK", "version": version, "fingerprint": check}), flush=True)
            if line.strip() == "CLOSE":
                break
    finally:
        store.close()
    print(json.dumps({"status": "CLOSED", "version": version}), flush=True)


def start_pinned_reader(paths, version):
    command = [sys.executable, "-B", str(HERE), "--pinned-reader", "--frozen-rag",
               str(paths["frozen"] / "rag"), "--database", str(paths["database"]), "--version", version]
    child = subprocess.Popen(command, cwd=paths["frozen"] / "rag", stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env=dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1"))
    ready = read_child_line(child, "readiness")
    try:
        row = json.loads(ready)
    except json.JSONDecodeError:
        child.terminate(); _, stderr = child.communicate(timeout=10)
        fail(f"pinned reader did not become ready: {ready!r}; {stderr}")
    if row.get("status") != "READY" or row.get("version") != version:
        child.terminate(); _, stderr = child.communicate(timeout=10)
        if stderr: row["stderr"] = stderr
        fail(f"pinned reader rejected baseline: {row}")
    return child, row


def read_child_line(child, label):
    lines = Queue()
    threading.Thread(target=lambda: lines.put(child.stdout.readline()), daemon=True).start()
    try:
        line = lines.get(timeout=30).strip()
    except Empty:
        child.terminate(); child.wait(timeout=10)
        fail(f"pinned reader {label} timeout")
    if not line:
        _, stderr = child.communicate(timeout=10)
        fail(f"pinned reader {label} ended early: {stderr}")
    return line


def check_pinned_reader(child, expected):
    child.stdin.write("CHECK\n"); child.stdin.flush()
    row = json.loads(read_child_line(child, "check"))
    if row.get("status") != "CHECK" or row.get("fingerprint") != expected:
        fail(f"pinned reader fingerprint changed: {row}")
    return row


def close_pinned_reader(child):
    child.stdin.write("CLOSE\n"); child.stdin.flush()
    row = json.loads(read_child_line(child, "close"))
    code = child.wait(timeout=20); stderr = child.stderr.read()
    if row.get("status") != "CLOSED" or code != 0 or stderr:
        fail(f"pinned reader close failed: {row}; {stderr}")
    return row


def run(paths):
    payload = {"status": "running", "parameters": {"n": 10, "mode": "docs", "k": 1, "deltas": 5,
               "keep_versions": 3, "collection": paths["collection"], "server_url": delta.URL, "qdrant_url": delta.QDRANT_URL,
               "restore_between_jobs": False, "old_reader_cross_process": "F5 lease-backed pinned reader"}, "events": [], "steps": [],
               "resources": {"materialized": None, "required_wrapper": "bench_process.py must wrap this process; this driver does not fabricate RSS or I/O"}}
    server = thread = qdrant = reader = pinned = None; stop = threading.Event(); old_env = {}
    frozen_before, source_before, experiment_source_before = tree_hash(paths["frozen"]), source_hash(paths["frozen"]), source_hash(paths["checkout"])
    payload["source_hashes"] = {"frozen_before": source_before, "experiment_before": experiment_source_before}
    try:
        delta._qdrant_preflight(paths["collection"]); paths["output"].mkdir(); save(paths["output"] / "result.json", payload)
        files = delta._make_corpus(paths, 10, "docs"); payload["corpus"] = delta._fingerprint(files)
        env = {"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "CUDA_VISIBLE_DEVICES": "-1", "HF_HUB_OFFLINE": "1", "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4", "VIBECRAFT_INDEX_KEEP": "3", "QDRANT_URL": delta.QDRANT_URL, "VIBECRAFT_HOST": delta.HOST, "VIBECRAFT_PORT": "18000"}
        old_env = {key: os.environ.get(key) for key in env}; os.environ.update(env); event(payload, "bootstrap_start")
        child = subprocess.run([sys.executable, "-B", str(SCRIPTS / "bench_delta.py"), "--bootstrap", "--checkout", str(paths["checkout"]), "--output-dir", str(paths["output"]), "--n", "10", "--mode", "docs", "--k", "0,1,10", "--repeats", "5"], cwd=paths["rag"], capture_output=True, text=True)
        payload["bootstrap"] = {"returncode": child.returncode, "stdout": child.stdout, "stderr": child.stderr}; event(payload, "bootstrap_end")
        if child.returncode: fail("bootstrap failed")
        sys.path.insert(0, str(paths["rag"])); import uvicorn; import server as server_module
        from api.deps import reload_index_state; from core.indexing import check_index_integrity; from qdrant_client import QdrantClient
        qdrant = QdrantClient(url=delta.QDRANT_URL, timeout=300); server = uvicorn.Server(uvicorn.Config(server_module.app, host=delta.HOST, port=18000, log_level="warning")); thread = threading.Thread(target=server.run, daemon=False); thread.start()
        deadline = time.monotonic() + 180
        while not server.started and time.monotonic() < deadline: time.sleep(delta.POLL)
        if not server.started: fail("server startup timeout")
        baseline = delta._request_job(); delta.validate_job(baseline, "docs", [], 0); payload["baseline_job"] = baseline
        delta._join_writer(); payload["baseline"] = snapshot(paths, qdrant, baseline["published_token"])
        pinned, payload["pinned_reader"] = start_pinned_reader(paths, baseline["published_token"])
        event(payload, "pinned_reader_ready", version=baseline["published_token"])
        reader_rows = []; reader = threading.Thread(target=delta._query_reader, args=(reader_rows, stop, "docs"), daemon=False); reader.start()
        for index, file in enumerate(files[:5]):
            before, after = file.read_bytes(), delta.changed_bytes(file.read_bytes()); file.write_bytes(after); started = time.monotonic(); event(payload, "delta_start", step=index + 1)
            job = delta._request_job(); ended = time.monotonic(); delta.validate_job(job, "docs", [file], 1); delta._join_writer()
            status, versions = delta._http("GET", "/api/index/versions")
            if status != 200 or versions.get("current") != job["published_token"] or not check_index_integrity(emit=lambda *_: None)["ok"]: fail("current token or integrity invalid")
            step = {"step": index + 1, "mutation": {"path": file.relative_to(paths["checkout"]).as_posix(), "before_sha256": delta._sha(before), "after_sha256": delta._sha(after), "bytes": len(after)}, "job": job, "elapsed_seconds": ended - started, "state": snapshot(paths, qdrant, job["published_token"])}
            step["pinned_reader"] = check_pinned_reader(pinned, payload["pinned_reader"]["fingerprint"])
            payload["steps"].append(step); event(payload, "delta_ready", step=index + 1); save(paths["output"] / "result.json", payload)
        if baseline["published_token"] not in payload["steps"][-1]["state"]["versions"]:
            fail("baseline version was pruned while its reader lease remained open")
        payload["pinned_reader_closed"] = close_pinned_reader(pinned); pinned = None
        from core.artifacts import list_versions, prune_versions
        removed = prune_versions(keep=3)
        payload["retention_after_reader_close"] = {"removed": removed, "versions": list_versions()}
        if baseline["published_token"] not in removed or baseline["published_token"] in payload["retention_after_reader_close"]["versions"]:
            fail("baseline was not pruned after reader close")
        stop.set(); reader.join(); reader = None; payload["reader_queries"] = reader_rows
        if any(x.get("error") or x.get("status") != 200 for x in reader_rows): fail("concurrent reader failed")
        if tree_hash(paths["frozen"]) != frozen_before or source_hash(paths["frozen"]) != source_before:
            fail("frozen copy changed during run")
        if source_hash(paths["checkout"]) != experiment_source_before:
            fail("experiment source changed during run")
        payload["status"] = "completed"; return 0
    except Exception as exc:
        payload["status"] = "failed"; payload["error"] = f"{type(exc).__name__}: {exc}"; return 1
    finally:
        if reader is not None: stop.set(); reader.join()
        if pinned is not None:
            try: payload["pinned_reader_closed"] = close_pinned_reader(pinned)
            except Exception as exc: payload["pinned_reader_close_error"] = str(exc)
        if server is not None: delta._join_writer(); server.should_exit = True; thread.join()
        if qdrant is not None: qdrant.close()
        payload["frozen_copy_unchanged"] = tree_hash(paths["frozen"]) == frozen_before
        payload["frozen_source_unchanged"] = source_hash(paths["frozen"]) == source_before
        payload["experiment_source_unchanged"] = source_hash(paths["checkout"]) == experiment_source_before
        for key, value in old_env.items(): os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)
        if paths["output"].exists(): save(paths["output"] / "result.json", payload)


def selfcheck():
    assert delta.changed_bytes(b"VarianteA") == b"VarianteB"
    try: delta.changed_bytes(b"VarianteB")
    except ValueError: print("pure guard selfcheck passed")
    else: raise AssertionError("invalid mutation accepted")


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--checkout"); parser.add_argument("--output-dir"); parser.add_argument("--frozen-copy"); parser.add_argument("--selfcheck", action="store_true")
    parser.add_argument("--pinned-reader", action="store_true"); parser.add_argument("--frozen-rag"); parser.add_argument("--database"); parser.add_argument("--version"); args = parser.parse_args()
    if args.pinned_reader:
        if not all((args.frozen_rag, args.database, args.version)): fail("pinned reader needs frozen rag, database, and version")
        pinned_reader(args.frozen_rag, args.database, args.version); return
    if args.selfcheck:
        if args.checkout or args.output_dir or args.frozen_copy: fail("--selfcheck takes no paths")
        selfcheck(); return
    if not all((args.checkout, args.output_dir, args.frozen_copy)): fail("--checkout, --output-dir, and --frozen-copy are required")
    raise SystemExit(run(paths(args.checkout, args.output_dir, args.frozen_copy)))


if __name__ == "__main__": main()

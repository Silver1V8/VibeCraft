"""Isolated real incremental benchmark. Run only from bench.py --real-delta."""
import argparse
import csv
import hashlib
import json
import os
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Porte di default storiche (F2/F3/F6). Override via env per lab throwaway paralleli
# (es. VIBECRAFT_BENCH_QDRANT_URL=http://127.0.0.1:16334) senza toccare il Qdrant
# operativo né un altro worker su 16333.
HOST = os.environ.get("VIBECRAFT_BENCH_HOST", "127.0.0.1")
SERVER_PORT = os.environ.get("VIBECRAFT_BENCH_PORT", "18000")
URL = f"http://{HOST}:{SERVER_PORT}"
QDRANT_URL = os.environ.get("VIBECRAFT_BENCH_QDRANT_URL", "http://127.0.0.1:16333")
COLLECTION_PREFIX = "sidecar_0628_"
RESULTS = Path(__file__).resolve().parents[1] / "eval" / "results"
POLL = 0.5
JOB_TIMEOUT = 600
QUERIES = ("prenotazione evento posti", "pagamenti accettati", "notifiche prenotazione")
_stop = threading.Event()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _safe(path: Path, root: Path) -> Path:
    """Reject links at every existing component before any write or removal."""
    if not path.is_absolute() or not root.is_absolute():
        raise ValueError("absolute paths required")
    root = root.resolve(strict=True)
    current = path
    while _within(current, root) and current != root:
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError(f"link/reparse forbidden: {current}")
        current = current.parent
    resolved = path.resolve(strict=False)
    if not _within(resolved, root):
        raise ValueError(f"path escapes dedicated root: {path}")
    return resolved


def validate_paths(checkout_arg: str, output_arg: str, *, bootstrap: bool = False) -> dict:
    checkout = Path(checkout_arg)
    output = Path(output_arg)
    if not checkout.is_absolute() or not output.is_absolute():
        raise ValueError("checkout/output must be absolute")
    results = RESULTS.resolve(strict=True)
    run = checkout.parent.parent
    _safe(run, results)
    if run.parent != results or checkout != run / "sandbox" / "experiment":
        raise ValueError("checkout must be <results>/<run>/sandbox/experiment")
    _safe(checkout, results)
    if not checkout.is_dir() or checkout.resolve() == Path(__file__).resolve().parents[2]:
        raise ValueError("dedicated checkout missing")
    rag = _safe(checkout / "rag", results)
    config_file = _safe(rag / "rag_config.yaml", results)
    if not config_file.is_file():
        raise ValueError("checkout config missing")
    import yaml
    config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    collection = (config.get("vector_database") or {}).get("collection_name")
    if not isinstance(collection, str) or not collection.startswith(COLLECTION_PREFIX) or not collection.replace("_", "").isalnum():
        raise ValueError("collection must use dedicated sidecar_0628_ prefix")
    docs_setting = Path(str(config["paths"]["docs_dir"]))
    code_setting = Path(str(config["paths"]["codebase_dir"]))
    if (docs_setting.is_absolute() or code_setting.is_absolute() or
            ".." in docs_setting.parts or ".." in code_setting.parts):
        raise ValueError("config path may not escape checkout")
    docs = _safe(checkout / str(docs_setting).lstrip("./"), results)
    code = _safe(checkout / "code", results)
    configured_code = _safe(checkout / str(code_setting).lstrip("./"), results)
    database = _safe(rag / "database", results)
    if (not _within(docs, checkout) or configured_code != code or
            not all(p.is_dir() for p in (rag, docs, code, database))):
        raise ValueError("effective core paths differ from dedicated checkout")
    if not bootstrap and any(database.iterdir()):
        raise ValueError("dedicated database must be empty before bootstrap")
    output = _safe(output, results)
    if output.parent != run or (output.exists() and not bootstrap) or _within(output, checkout):
        raise ValueError("output must be a new sibling under dedicated run")
    if bootstrap and (not output.is_dir() or (output / "bootstrap.json").exists()):
        raise ValueError("bootstrap requires parent-created output without previous result")
    # Validate every existing descendant, including Windows junctions via resolve().
    for root in (docs, code, database):
        for path in root.rglob("*"):
            _safe(path, results)
    return dict(run=run, checkout=checkout, rag=rag, docs=docs, code=code,
                database=database, output=output, collection=collection)


def validate_cell(n: int, mode: str, ks: list[int], repeats: int) -> None:
    if n not in (10, 30, 100) or mode not in ("docs", "code", "mixed") or repeats < 1:
        raise ValueError("N must be 10/30/100, mode docs/code/mixed, repeats >=1")
    if any(k < 0 or k > n for k in ks):
        raise ValueError("k > N or negative k")
    if len(set(ks)) != len(ks) or 0 not in ks:
        raise ValueError("k list must be unique and include 0")


def changed_bytes(before: bytes) -> bytes:
    if before.count(b"VarianteA") != 1 or b"VarianteB" in before:
        raise ValueError("expected exactly one VarianteA and no VarianteB")
    after = before.replace(b"VarianteA", b"VarianteB")
    if len(after) != len(before):
        raise ValueError("mutation changed byte length")
    return after


def select_changes(docs: Path, code: Path, mode: str, k: int) -> list[Path]:
    d = sorted(docs.glob("*.md"))
    c = sorted(code.glob("*.py"))
    if mode == "docs":
        chosen = d[:k]
    elif mode == "code":
        chosen = c[:k]
    else:
        chosen = d[:(k + 1) // 2] + c[:k // 2]
    if len(chosen) != k or len(set(chosen)) != k:
        raise ValueError("k > available eligible files")
    return chosen


def validate_job(job: dict, mode: str, changed: list[Path], k: int) -> None:
    if job.get("_poll_timed_out") or job.get("status") != "completed":
        raise ValueError("job incomplete")
    if job.get("coalesced"):
        raise ValueError("coalesced job")
    if job.get("reload_status") != "completed" or job.get("published_token") is None:
        raise ValueError("reload incomplete")
    for field in ("queue_duration_seconds", "writer_lock_wait_seconds", "build_duration_seconds",
                  "reload_duration_seconds", "snapshot_ready_duration_seconds"):
        if not isinstance(job.get(field), (int, float)) or job[field] < 0:
            raise ValueError(f"journal timing incomplete: {field}")
    result = job.get("result") or {}
    if (k == 0 and result.get("noop") is not True) or (k > 0 and result.get("noop") is True):
        raise ValueError("false noop/delta")
    if k == 0:
        return
    if job["published_token"] != result.get("version"):
        raise ValueError("stale published token")
    docs = [p.name for p in changed if p.suffix == ".md"]
    code = [p for p in changed if p.suffix == ".py"]
    counts = result.get("counts") or {}
    planned = result.get("planned") or {}
    if sorted(planned.get("modified") or []) != sorted(docs) or result.get("reindexed_docs") != len(docs):
        raise ValueError("document modification count mismatch")
    if counts.get("code_modified") != len(code):
        raise ValueError("code modification count mismatch")
    if docs and (counts.get("chunks_processed", 0) < len(docs) or counts.get("colbert_tokens_processed", 0) < len(docs)):
        raise ValueError("missing document chunks/tokens")


def _save(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _event(payload: dict, name: str, **fields) -> None:
    payload["events"].append(dict(event=name, utc=datetime.now(timezone.utc).isoformat(),
                                  monotonic=time.monotonic(), **fields))


def _http(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = Request(URL + path, data=data, method=method,
                  headers={"Content-Type": "application/json"} if data else {})
    with urlopen(req, timeout=30) as response:
        return response.status, json.loads(response.read())


def _wait_job(job_id: str) -> dict:
    deadline = time.monotonic() + JOB_TIMEOUT
    last = {}
    while time.monotonic() < deadline:
        status, last = _http("GET", f"/api/reindex/{job_id}")
        if status != 200:
            raise RuntimeError(f"journal HTTP {status}")
        if last.get("status") in ("completed", "failed", "interrupted", "completed_not_promoted") and last.get("reload_status") != "pending":
            return last
        time.sleep(POLL)
    return {**last, "_poll_timed_out": True}


def _request_job() -> dict:
    status, queued = _http("POST", "/api/reindex")
    if status != 202 or not queued.get("job_id"):
        raise RuntimeError(f"reindex not queued: {status} {queued}")
    return _wait_job(queued["job_id"])


def _fingerprint(paths: list[Path]) -> dict:
    return {p.as_posix(): {"sha256": _sha(p.read_bytes()), "bytes": p.stat().st_size} for p in paths}


def _make_corpus(paths: dict, n: int, mode: str) -> list[Path]:
    if any(paths["docs"].rglob("*")) or any(paths["code"].rglob("*")):
        raise ValueError("dedicated docs/code must be empty before corpus generation")
    docs_n = n if mode == "docs" else 0 if mode == "code" else n // 2
    files = []
    for i in range(n):
        is_doc = i < docs_n
        path = (paths["docs"] / f"d{i:03}.md") if is_doc else (paths["code"] / f"c{i:03}.py")
        _safe(path, RESULTS)
        if path.exists():
            raise ValueError(f"corpus target already exists: {path}")
        pad = "tema " * (1 + i % 3)
        data = (f"# Scheda {i:03}\nPrenotazione pagamento notifiche VarianteA {pad}\n" if is_doc else
                f'def caso_{i:03}():\n    """Prenotazione pagamento notifiche VarianteA {pad}"""\n    return "caso_{i:03}"\n')
        path.write_bytes(data.encode("utf-8"))
        files.append(path)
    return files


def _qdrant_preflight(collection: str) -> list[str]:
    from qdrant_client import QdrantClient
    client = QdrantClient(url=QDRANT_URL, timeout=300)
    try:
        physical = [item.name for item in client.get_collections().collections]
        aliases = [item.alias_name for item in client.get_aliases().aliases]
    finally:
        client.close()
    if (collection in physical or collection in aliases or
            any(not name.startswith(COLLECTION_PREFIX) for name in physical + aliases)):
        raise ValueError(f"Qdrant port contains non-dedicated or reused collection/alias: {physical}, {aliases}")
    return physical


def _point_digest(qdrant, collection: str) -> dict:
    entries = []
    offset = None
    while True:
        page, offset = qdrant.scroll(collection_name=collection, limit=128, offset=offset,
                                     with_payload=True, with_vectors=True)
        entries.extend(p.model_dump(mode="json") for p in page)
        if offset is None:
            break
    entries.sort(key=lambda p: str(p["id"]))
    return {"count": len(entries), "sha256": _sha(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode())}


def _backup_database(paths: dict) -> dict:
    backup = paths["output"] / "baseline-database"
    _safe(backup, RESULTS)
    shutil.copytree(paths["database"], backup, ignore=shutil.ignore_patterns(".writer.lock", ".reader-locks", "reindex_jobs.jsonl", "alerts.jsonl"))
    return _fingerprint([p for p in backup.rglob("*") if p.is_file()])


def _database_fingerprint(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): {"sha256": _sha(p.read_bytes()), "bytes": p.stat().st_size}
            for p in root.rglob("*") if p.is_file() and ".reader-locks" not in p.relative_to(root).parts and p.name not in
            (".writer.lock", "reindex_jobs.jsonl", "alerts.jsonl")}


def _restore_files(paths: dict, original: dict[Path, bytes], qdrant, snapshot) -> None:
    from core.writer_lock import try_version_lease, writer_lock
    db = paths["database"]
    backup = paths["output"] / "baseline-database"
    with writer_lock(timeout_seconds=60), ExitStack() as leases:
        versions = db / "versions"
        if versions.is_dir():
            for folder in versions.iterdir():
                if folder.is_dir():
                    lease = try_version_lease(db, folder.name, exclusive=True)
                    if lease is None:
                        raise BlockingIOError(f"database restore blocked by reader of {folder.name}")
                    leases.enter_context(lease)
        for path, data in original.items():
            _safe(path, RESULTS)
            path.write_bytes(data)
        for path in sorted(db.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            _safe(path, RESULTS)
            if ".reader-locks" in path.relative_to(db).parts:
                continue
            if path.is_file() and path.name not in (".writer.lock", "reindex_jobs.jsonl", "alerts.jsonl"):
                path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        for source in backup.rglob("*"):
            target = _safe(db / source.relative_to(backup), RESULTS)
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        recovered = qdrant.recover_snapshot(collection_name=paths["collection"],
                          location=f"file:///qdrant/snapshots/{paths['collection']}/{snapshot.name}",
                          priority="snapshot", wait=True)
        if recovered is False:
            raise RuntimeError("Qdrant snapshot recovery rejected")


def _query_spec(mode: str, index: int) -> tuple[str, str]:
    query = QUERIES[index % len(QUERIES)]
    code = mode == "code" or (mode == "mixed" and index % 2 == 1)
    endpoint = "/api/code/search" if code else "/api/retrieve"
    params = {"q": query, "k": 3}
    if code:
        params["min_score"] = 0
    return endpoint, endpoint + "?" + urlencode(params)


def _query_reader(samples: list[dict], stop: threading.Event, mode: str) -> None:
    i = 0
    while not stop.is_set():
        start = time.monotonic()
        endpoint, path = _query_spec(mode, i)
        try:
            status, body = _http("GET", path)
            samples.append({"start_monotonic": start, "end_monotonic": time.monotonic(),
                            "endpoint": endpoint, "status": status,
                            "index_version": body.get("index_version"),
                            "results": len(body.get("results") or [])})
        except Exception as exc:
            samples.append({"start_monotonic": start, "end_monotonic": time.monotonic(),
                            "endpoint": endpoint, "error": str(exc)})
        i += 1
        stop.wait(0.15)


def _join_writer():
    from api import routes_reindex
    from api.deps import project_registry
    project = project_registry().get("legacy")
    manager = routes_reindex.project_manager(project)
    while not manager.join_all(timeout=5):
        pass


def _bootstrap(paths: dict) -> int:
    sys.path.insert(0, str(paths["rag"]))
    from core.indexing import incremental_index
    from core.writer_lock import writer_lock
    with writer_lock(timeout_seconds=60):
        result = incremental_index()
    _save(paths["output"] / "bootstrap.json", {"pid": os.getpid(), "result": result})
    return 2 if _stop.is_set() else 0


def _summarize(payload: dict, output: Path) -> None:
    rows = []
    for k in payload["parameters"]["k"]:
        valid = [s for s in payload["samples"] if s["k"] == k and s["valid"]]
        times = [s["job"]["snapshot_ready_duration_seconds"] for s in valid]
        http_times = [s["elapsed_seconds"] for s in valid]
        rows.append({"n": payload["parameters"]["n"], "mode": payload["parameters"]["mode"],
                     "k": k, "valid": len(valid), "median_ready_s": statistics.median(times) if times else None,
                     "min_ready_s": min(times) if times else None, "max_ready_s": max(times) if times else None,
                     "median_http_s": statistics.median(http_times) if http_times else None})
    zeros = {s["repeat"]: s["job"]["snapshot_ready_duration_seconds"] for s in payload["samples"] if s["k"] == 0 and s["valid"]}
    for row in rows:
        pairs = [s["job"]["snapshot_ready_duration_seconds"] - zeros[s["repeat"]] for s in payload["samples"]
                 if s["k"] == row["k"] and s["valid"] and s["repeat"] in zeros]
        row["paired_median_ready_difference_s"] = statistics.median(pairs) if pairs else None
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(paths: dict, n: int, mode: str, ks: list[int], repeats: int) -> int:
    payload = {"status": "running", "pid": os.getpid(), "parameters": {"n": n, "mode": mode, "k": ks,
               "repeats": repeats, "query_pause_seconds": 0.15, "qdrant_url": QDRANT_URL,
               "server_url": URL, "collection": paths["collection"],
               "restore_io_outside_measurement": True}, "events": [], "samples": []}
    server = server_thread = qdrant = None
    active_query = None
    files = []
    original = {}
    baseline = None
    snapshot = None
    old_env = {}
    try:
        existing = _qdrant_preflight(paths["collection"])
        paths["output"].mkdir()
        _save(paths["output"] / "result.json", payload)
        payload["qdrant_collections_before"] = existing
        files = _make_corpus(paths, n, mode)
        original = {p: p.read_bytes() for p in files}
        payload["corpus"] = _fingerprint(files)
        env = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "CUDA_VISIBLE_DEVICES": "-1",
               "HF_HUB_OFFLINE": "1", "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4",
               "QDRANT_URL": QDRANT_URL, "VIBECRAFT_HOST": HOST, "VIBECRAFT_PORT": SERVER_PORT}
        old_env = {key: os.environ.get(key) for key in env}
        os.environ.update(env)
        _event(payload, "bootstrap_start")
        child = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "--bootstrap",
                                  "--checkout", str(paths["checkout"]), "--output-dir", str(paths["output"]),
                                  "--n", str(n), "--mode", mode, "--k", ",".join(map(str, ks)),
                                  "--repeats", str(repeats)], cwd=paths["rag"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = child.communicate()
        payload["bootstrap"] = {"pid": child.pid, "returncode": child.returncode,
                                "stdout": stdout, "stderr": stderr}
        payload["bootstrap_result_file"] = str(paths["output"] / "bootstrap.json")
        _event(payload, "bootstrap_end")
        if _stop.is_set():
            raise InterruptedError("stop requested after bootstrap")
        if child.returncode:
            raise RuntimeError("bootstrap failed")
        sys.path.insert(0, str(paths["rag"]))
        import uvicorn
        import server as server_module
        from api.deps import reload_index_state, state as server_state
        from core.indexing import check_index_integrity
        from qdrant_client import QdrantClient
        qdrant = QdrantClient(url=QDRANT_URL, timeout=300)
        server = uvicorn.Server(uvicorn.Config(server_module.app, host=HOST, port=18000, log_level="warning"))
        server_thread = threading.Thread(target=server.run, daemon=False)
        server_thread.start()
        deadline = time.monotonic() + 180
        while not server.started and time.monotonic() < deadline:
            time.sleep(POLL)
        if not server.started:
            raise RuntimeError("server startup timeout")
        verification = _request_job()
        validate_job(verification, mode, [], 0)
        payload["baseline_verification_job"] = verification
        _join_writer()
        payload["baseline_integrity"] = check_index_integrity(emit=lambda *_: None)
        if not payload["baseline_integrity"]["ok"]:
            raise RuntimeError("baseline integrity failed")
        _join_writer()
        _backup_database(paths)
        baseline = _database_fingerprint(paths["database"])
        payload["baseline_database"] = baseline
        payload["baseline_points"] = _point_digest(qdrant, paths["collection"])
        payload["baseline_current"] = (paths["database"] / "CURRENT").read_bytes().hex()
        snapshot = qdrant.create_snapshot(collection_name=paths["collection"], wait=True)
        if snapshot is None or not snapshot.name or Path(snapshot.name).name != snapshot.name:
            raise RuntimeError("Qdrant snapshot unavailable")
        payload["qdrant_snapshot"] = snapshot.name
        _event(payload, "baseline_frozen")
        payload["baseline_queries"] = []
        for i, query in enumerate(QUERIES):
            started = time.monotonic()
            endpoint, path = _query_spec(mode, i)
            status, body = _http("GET", path)
            entry = {"query": query, "endpoint": endpoint,
                     "start_monotonic": started, "end_monotonic": time.monotonic(),
                     "status": status, "results": len(body.get("results") or [])}
            payload["baseline_queries"].append(entry)
            if status != 200 or not entry["results"]:
                raise RuntimeError(f"baseline query failed: {entry}")
        _save(paths["output"] / "result.json", payload)
        for repeat in range(repeats):
            for k in ks:
                if _stop.is_set():
                    raise InterruptedError("stop requested")
                sample = {"repeat": repeat, "k": k, "valid": False, "queries": []}
                payload["samples"].append(sample)
                try:
                    _join_writer()
                    if _fingerprint(files) != payload["corpus"] or _database_fingerprint(paths["database"]) != baseline:
                        raise RuntimeError("pre-sample baseline differs")
                    chosen = select_changes(paths["docs"], paths["code"], mode, k)
                    if k:
                        sample["mutations"] = []
                        for path in chosen:
                            before = path.read_bytes()
                            after = changed_bytes(before)
                            path.write_bytes(after)
                            sample["mutations"].append({"path": path.relative_to(paths["checkout"]).as_posix(),
                                 "before_sha256": _sha(before), "after_sha256": _sha(after), "bytes": len(after),
                                 "code_symbol": path.stem.replace("c", "caso_", 1) if path.suffix == ".py" else None})
                    query_stop = threading.Event()
                    active_query = threading.Thread(target=_query_reader, args=(sample["queries"], query_stop, mode), daemon=False)
                    _event(payload, "sample_start", repeat=repeat, k=k)
                    started = time.monotonic()
                    active_query.start()
                    job = _request_job()
                    ended = time.monotonic()
                    query_stop.set()
                    active_query.join()
                    active_query = None
                    sample.update(job=job, elapsed_seconds=ended-started,
                                  started_monotonic=started, ended_monotonic=ended)
                    validate_job(job, mode, chosen, k)
                    _join_writer()
                    status, versions = _http("GET", "/api/index/versions")
                    sample["current_version"] = versions.get("current")
                    if status != 200 or sample["current_version"] != job["published_token"]:
                        raise ValueError("stale current version")
                    sample["empty_results_count"] = sum(q.get("results") == 0 for q in sample["queries"])
                    sample["empty_results_rate"] = sample["empty_results_count"] / len(sample["queries"]) if sample["queries"] else None
                    if not sample["queries"] or any(q.get("error") or q.get("status") != 200 for q in sample["queries"]):
                        raise ValueError("concurrent query failed")
                    sample["integrity"] = check_index_integrity(emit=lambda *_: None)
                    if not sample["integrity"]["ok"]:
                        raise ValueError("sample index integrity failed")
                    sample["valid"] = True
                    _event(payload, "sample_ready", repeat=repeat, k=k)
                except Exception as exc:
                    sample["error"] = f"{type(exc).__name__}: {exc}"
                    raise
                finally:
                    if active_query is not None:
                        query_stop.set()
                        active_query.join()
                        active_query = None
                    _join_writer()
                    # Restore is deliberately outside measured interval.
                    try:
                        # No HTTP readers or writer remain. Drop the server's active
                        # Mapping before removing version directories; its OS lease
                        # must never be invalidated by deleting the lock file.
                        server_state["snapshot"] = None
                        _restore_files(paths, original, qdrant, snapshot)
                        reload_index_state()
                        restored = (_fingerprint(files) == payload["corpus"] and
                                    _database_fingerprint(paths["database"]) == baseline and
                                    (paths["database"] / "CURRENT").read_bytes().hex() == payload["baseline_current"] and
                                    _point_digest(qdrant, paths["collection"]) == payload["baseline_points"] and
                                    check_index_integrity(emit=lambda *_: None)["ok"])
                        sample["restore_verified"] = restored
                    except Exception as exc:
                        sample["valid"] = False
                        sample["restore_error"] = f"{type(exc).__name__}: {exc}"
                        raise
                    if not restored:
                        sample["valid"] = False
                        raise RuntimeError("baseline restore verification failed")
                    _event(payload, "sample_restored", repeat=repeat, k=k)
                    _save(paths["output"] / "result.json", payload)
        if _stop.is_set():
            raise InterruptedError("stop requested after final sample")
        payload["status"] = "completed"
        _summarize(payload, paths["output"])
        return 0
    except Exception as exc:
        payload["status"] = "failed"
        payload["error"] = f"{type(exc).__name__}: {exc}"
        return 1
    finally:
        if active_query is not None:
            query_stop.set()
            active_query.join()
        if server is not None:
            _join_writer()
            server.should_exit = True
            server_thread.join()
        if qdrant is not None:
            qdrant.close()
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if paths["output"].exists():
            _save(paths["output"] / "result.json", payload)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--k", required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--bootstrap", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    ks = [int(x) for x in args.k.split(",")]
    validate_cell(args.n, args.mode, ks, args.repeats)
    paths = validate_paths(args.checkout, args.output_dir, bootstrap=args.bootstrap)
    for sig in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGBREAK", None)):
        if sig is not None:
            signal.signal(sig, lambda *_: _stop.set())
    if args.bootstrap:
        return _bootstrap(paths)
    return run(paths, args.n, args.mode, ks, args.repeats)


if __name__ == "__main__":
    raise SystemExit(main())

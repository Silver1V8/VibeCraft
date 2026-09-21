"""Safety and sample-contract checks; the real workload is run separately."""
import hashlib
import json
import sys
import time
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

from scripts import bench_delta as delta

TIMINGS = {name: 0.1 for name in ("queue_duration_seconds", "writer_lock_wait_seconds",
           "build_duration_seconds", "reload_duration_seconds", "snapshot_ready_duration_seconds")}


def test_select_changes_distinct_and_same_size(tmp_path):
    docs = tmp_path / "docs"
    code = tmp_path / "code"
    docs.mkdir()
    code.mkdir()
    for i in range(10):
        (docs / f"d{i:03}.md").write_bytes(b"# Topic\nVarianteA\n")
        (code / f"c{i:03}.py").write_bytes(b'def f():\n    """VarianteA"""\n    return 1\n')
    for mode, expected_docs in (("docs", 10), ("code", 0), ("mixed", 5)):
        selected = delta.select_changes(docs, code, mode, 10)
        assert len(selected) == len(set(selected)) == 10
        assert sum(p.suffix == ".md" for p in selected) == expected_docs
        for path in selected:
            before = path.read_bytes()
            after = delta.changed_bytes(before)
            assert len(after) == len(before)
            assert hashlib.sha256(after).digest() != hashlib.sha256(before).digest()


def test_k_larger_than_corpus_fails(tmp_path):
    with pytest.raises(ValueError, match="k > N"):
        delta.validate_cell(10, "docs", [0, 11], 5)


def test_real_delta_rejects_noop_and_incomplete_journal():
    job = {**TIMINGS, "status": "completed", "reload_status": "completed", "published_token": "v2",
           "result": {"noop": True, "version": "v2", "planned": {"modified": ["d.md"]},
                      "reindexed_docs": 1, "counts": {"chunks_processed": 1,
                                                       "colbert_tokens_processed": 1}}}
    with pytest.raises(ValueError, match="noop"):
        delta.validate_job(job, "docs", [Path("d.md")], 1)
    job["result"]["noop"] = False
    job["reload_status"] = "pending"
    with pytest.raises(ValueError, match="reload"):
        delta.validate_job(job, "docs", [Path("d.md")], 1)
    job["reload_status"] = "completed"
    job["coalesced"] = True
    with pytest.raises(ValueError, match="coalesced"):
        delta.validate_job(job, "docs", [Path("d.md")], 1)
    job.pop("coalesced")
    job["result"].pop("noop")
    job["result"]["counts"]["code_modified"] = 0
    delta.validate_job(job, "docs", [Path("d.md")], 1)
    job.pop("snapshot_ready_duration_seconds")
    with pytest.raises(ValueError, match="journal timing"):
        delta.validate_job(job, "docs", [Path("d.md")], 1)


def test_code_and_mixed_counts_must_match():
    job = {**TIMINGS, "status": "completed", "reload_status": "completed", "published_token": "v2",
           "result": {"noop": False, "version": "v2", "planned": {"modified": ["d.md"]},
                      "reindexed_docs": 1, "counts": {"code_modified": 1,
                      "chunks_processed": 2, "colbert_tokens_processed": 10}}}
    delta.validate_job(job, "mixed", [Path("d.md"), Path("c.py")], 2)
    job["result"]["counts"]["code_modified"] = 0
    with pytest.raises(ValueError, match="code"):
        delta.validate_job(job, "mixed", [Path("d.md"), Path("c.py")], 2)


def test_guard_rejects_operational_collection_before_writes(tmp_path, monkeypatch):
    results = tmp_path / "results"
    checkout = results / "run" / "sandbox" / "experiment"
    rag = checkout / "rag"
    for path in (rag / "database", checkout / "docs", checkout / "code"):
        path.mkdir(parents=True)
    (rag / "rag_config.yaml").write_text(
        'paths:\n  docs_dir: "./docs"\n  codebase_dir: "./code"\n'
        'vector_database:\n  collection_name: "vibecraft_events"\n', encoding="utf-8")
    monkeypatch.setattr(delta, "RESULTS", results)
    output = results / "run" / "out"
    with pytest.raises(ValueError, match="collection"):
        delta.validate_paths(str(checkout), str(output))
    assert not output.exists()
    (rag / "rag_config.yaml").write_text(
        'paths:\n  docs_dir: "../outside"\n  codebase_dir: "./code"\n'
        'vector_database:\n  collection_name: "sidecar_0628_test"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="config path"):
        delta.validate_paths(str(checkout), str(output))
    (rag / "rag_config.yaml").write_text(
        'paths:\n  docs_dir: "./docs"\n  codebase_dir: "./code"\n'
        'vector_database:\n  collection_name: "sidecar_0628_test"\n', encoding="utf-8")
    assert delta.validate_paths(str(checkout), str(output))["collection"] == "sidecar_0628_test"
    (rag / "database" / "CURRENT").write_bytes(b"old")
    with pytest.raises(ValueError, match="database must be empty"):
        delta.validate_paths(str(checkout), str(output))
    with pytest.raises(ValueError, match="checkout"):
        delta.validate_paths(str(results / "run" / "other"), str(output))
    assert not output.exists()


def test_qdrant_alias_reuse_rejected_before_output(tmp_path, monkeypatch):
    class Qdrant:
        def __init__(self, **_kwargs):
            pass
        def get_collections(self):
            return types.SimpleNamespace(collections=[])
        def get_aliases(self):
            return types.SimpleNamespace(aliases=[types.SimpleNamespace(alias_name="sidecar_0628_test")])
        def close(self):
            pass
    import qdrant_client
    monkeypatch.setattr(qdrant_client, "QdrantClient", Qdrant)
    with pytest.raises(ValueError, match="reused"):
        delta._qdrant_preflight("sidecar_0628_test")


def test_restore_reinstates_source_and_database_bytes_after_exception(tmp_path, monkeypatch):
    results = tmp_path / "results"
    results.mkdir()
    checkout = results / "run" / "sandbox" / "experiment"
    db = checkout / "rag" / "database"
    docs = checkout / "docs"
    output = results / "run" / "out"
    db.mkdir(parents=True)
    docs.mkdir()
    output.mkdir()
    source = docs / "d.md"
    artifact = db / "CURRENT"
    source.write_bytes(b"VarianteA\r\n")
    artifact.write_bytes(b"v1")
    paths = {"database": db, "output": output, "collection": "sidecar_0628_test"}
    monkeypatch.setattr(delta, "RESULTS", results)
    delta._backup_database(paths)
    source.write_bytes(b"VarianteB\r\n")
    artifact.write_bytes(b"v2")
    (db / "new-artifact").write_bytes(b"extra")

    @contextmanager
    def lock(**_kwargs):
        yield

    import core.writer_lock
    monkeypatch.setattr(core.writer_lock, "writer_lock", lock)

    class Qdrant:
        def recover_snapshot(self, **kwargs):
            assert source.read_bytes() == b"VarianteA\r\n"
            assert artifact.read_bytes() == b"v1"
            return True

    delta._restore_files(paths, {source: b"VarianteA\r\n"}, Qdrant(),
                         type("Snapshot", (), {"name": "baseline.snapshot"})())
    assert source.read_bytes() == b"VarianteA\r\n"
    assert artifact.read_bytes() == b"v1"
    assert not (db / "new-artifact").exists()


def test_run_restores_real_files_when_sample_job_raises(tmp_path, monkeypatch):
    results = tmp_path / "results"
    checkout = results / "run" / "sandbox" / "experiment"
    rag = checkout / "rag"
    db = rag / "database"
    for path in (db, checkout / "docs", checkout / "code"):
        path.mkdir(parents=True)
    output = results / "run" / "workload"
    paths = {"checkout": checkout, "rag": rag, "docs": checkout / "docs",
             "code": checkout / "code", "database": db, "output": output,
             "collection": "sidecar_0628_test"}
    monkeypatch.setattr(delta, "RESULTS", results)
    monkeypatch.setattr(delta, "_join_writer", lambda: None)
    monkeypatch.setattr(delta, "_point_digest", lambda *_: {"count": 1, "sha256": "same"})
    monkeypatch.setattr(delta, "_http", lambda *_: (200, {"results": [{"id": 1}]}))

    class Qdrant:
        def __init__(self, **_kwargs):
            pass
        def get_collections(self):
            return types.SimpleNamespace(collections=[])
        def get_aliases(self):
            return types.SimpleNamespace(aliases=[])
        def create_snapshot(self, **_kwargs):
            return types.SimpleNamespace(name="baseline.snapshot")
        def recover_snapshot(self, **_kwargs):
            return True
        def close(self):
            pass

    import qdrant_client
    monkeypatch.setattr(qdrant_client, "QdrantClient", Qdrant)

    class Child:
        pid = 123
        returncode = 0
        def communicate(self):
            (db / "CURRENT").write_bytes(b"v1")
            return "", ""
    real_popen = delta.subprocess.Popen
    def bootstrap_only(args, *other, **kwargs):
        if isinstance(args, (list, tuple)) and "--bootstrap" in args and Path(args[2]).name == "bench_delta.py":
            return Child()
        return real_popen(args, *other, **kwargs)
    monkeypatch.setattr(delta.subprocess, "Popen", bootstrap_only)

    class Server:
        started = False
        should_exit = False
        def __init__(self, *_args):
            pass
        def run(self):
            self.started = True
            while not self.should_exit:
                time.sleep(0.01)
    import uvicorn
    monkeypatch.setattr(uvicorn, "Server", Server)
    monkeypatch.setattr(uvicorn, "Config", lambda *_a, **_k: object())
    monkeypatch.setitem(sys.modules, "server", types.SimpleNamespace(app=object()))
    import api.deps
    import core.indexing
    import core.writer_lock
    monkeypatch.setattr(api.deps, "reload_index_state", lambda: "v1")
    monkeypatch.setattr(core.indexing, "check_index_integrity", lambda **_k: {"ok": True})

    @contextmanager
    def lock(**_kwargs):
        yield
    monkeypatch.setattr(core.writer_lock, "writer_lock", lock)
    calls = 0
    def job():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected job failure")
        return {**TIMINGS, "status": "completed", "reload_status": "completed",
                "published_token": "v1", "result": {"noop": True}}
    monkeypatch.setattr(delta, "_request_job", job)
    assert delta.run(paths, 10, "docs", [1, 0], 1) == 1
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["samples"][0]["restore_verified"] is True
    assert (checkout / "docs" / "d000.md").read_bytes().count(b"VarianteA") == 1
    assert (db / "CURRENT").read_bytes() == b"v1"

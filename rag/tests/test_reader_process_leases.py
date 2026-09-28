"""Local-process lease proof for immutable NPZ snapshots; no cross-host claim."""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from types import SimpleNamespace

import networkx as nx

from core import artifacts
from core import indexing as index
from core.writer_lock import writer_lock


RAG_DIR = Path(__file__).resolve().parents[1]
_READER = (
    "import sys; "
    "from core.artifacts import load_artifacts; "
    "snapshot=load_artifacts(version=sys.argv[1], required=('graph','colbert'), "
    "retain_lease=True); "
    "print(f'READY {snapshot.version}', flush=True); "
    "sys.stdin.readline(); "
    "snapshot.version_lease.close()"
)


class _FakeQdrant:
    def __init__(self, collections, alias, target):
        self.collections = set(collections)
        self.alias = alias
        self.target = target

    def get_collections(self):
        return SimpleNamespace(
            collections=[SimpleNamespace(name=name) for name in sorted(self.collections)])

    def get_aliases(self):
        return SimpleNamespace(
            aliases=[SimpleNamespace(alias_name=self.alias, collection_name=self.target)])

    def delete_collection(self, name):
        self.collections.remove(name)


def _save_npz_version(database: Path, version: str) -> str:
    graph = nx.DiGraph()
    graph.add_node(version)
    directory = database / "versions" / version
    directory.mkdir(parents=True)
    artifacts._atomic_write_json(directory / "graph.json", artifacts._graph_to_json(graph))
    artifacts._save_vectors(directory / "colbert.npz", {})
    artifacts._atomic_write_json(directory / "chunks.json", {})
    collection = index.qdrant_collection_name(version)
    artifacts._atomic_write_json(
        directory / artifacts.MANIFEST_FILENAME,
        {"immutable": True, "qdrant_collection": collection,
         "artifact_hashes": artifacts.artifact_hashes(version)},
    )
    return collection


def _start_reader(database: Path, version: str) -> subprocess.Popen:
    env = dict(
        os.environ,
        VIBECRAFT_DATABASE_DIR=str(database),
        VIBECRAFT_ROLE="reader",
        VIBECRAFT_INDEX_MODE="immutable",
        QDRANT_URL="http://127.0.0.1:16333",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1",
    )
    env.pop("VIBECRAFT_TEST_QDRANT_URL", None)
    return subprocess.Popen(
        [sys.executable, "-B", "-c", _READER, version],
        cwd=RAG_DIR,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def _ready(child: subprocess.Popen) -> str:
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(child.stdout.readline)
    try:
        line = future.result(timeout=10).strip()
    except FutureTimeoutError:
        child.kill()
        child.communicate(timeout=10)
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    if not line.startswith("READY "):
        raise AssertionError(f"reader failed before READY: {line!r}; stderr={child.stderr.read()!r}")
    return line


def _stop(child: subprocess.Popen, *, crash: bool) -> int:
    if child.poll() is not None:
        return child.returncode
    if crash:
        child.kill()
        child.communicate(timeout=10)
    else:
        child.communicate("close\n", timeout=10)
    return child.returncode


def test_two_npz_reader_processes_pin_version_until_orderly_exit_and_crash(tmp_path, monkeypatch):
    database = tmp_path / "database"
    monkeypatch.setattr(artifacts, "DATABASE_DIR", database)
    monkeypatch.setattr(artifacts, "INDEX_MODE", "legacy")
    monkeypatch.setenv("VIBECRAFT_INDEX_KEEP", "2")
    artifacts._atomic_write_text(
        database / artifacts.IMMUTABLE_MARKER_FILENAME, "immutable\n")

    v1, v2, v3 = "v1", "v2", "v3"
    c1 = _save_npz_version(database, v1)
    artifacts.promote_version(v1)
    children = [_start_reader(database, v1), _start_reader(database, v1)]
    lock_path = database / ".writer.lock"

    try:
        assert [_ready(child) for child in children] == ["READY v1", "READY v1"]

        with writer_lock(lock_path=lock_path):
            c2 = _save_npz_version(database, v2)
            artifacts.promote_version(v2)
            c3 = _save_npz_version(database, v3)
            artifacts.promote_version(v3)
            artifacts.rollback_version(v2)
            qdrant = _FakeQdrant(
                {c1, c2, c3, index.qdrant_collection_name("orphan")},
                index.COLLECTION_NAME,
                c2,
            )
            assert v1 not in artifacts.prune_versions(keep=2)
            assert index.gc_orphaned_qdrant_collections(qdrant) == [
                index.qdrant_collection_name("orphan")]
            assert artifacts.manifest_path(v1).is_file() and c1 in qdrant.collections

        assert _stop(children[0], crash=False) == 0
        with writer_lock(lock_path=lock_path):
            assert v1 not in artifacts.prune_versions(keep=2)
            assert artifacts.manifest_path(v1).is_file() and c1 in qdrant.collections

        assert _stop(children[1], crash=True) != 0
        with writer_lock(lock_path=lock_path):
            assert v1 in artifacts.prune_versions(keep=2)
            assert c1 in index.gc_orphaned_qdrant_collections(qdrant)
            assert not artifacts.version_dir(v1).exists() and c1 not in qdrant.collections
    finally:
        for child in children:
            _stop(child, crash=True)

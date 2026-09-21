"""F5A: per-document immutable NPY reader/writer and cross-process leases."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from core.colbert_store import ColbertStore, ColbertWriter
from core.writer_lock import try_version_lease


def _vectors(start=0):
    return {"doc#one": np.arange(start, start + 12, dtype=np.float16).reshape(3, 4),
            "doc#two": np.arange(start + 12, start + 20, dtype=np.float16).reshape(2, 4)}


def _store(tmp_path):
    root = tmp_path / "colbert"
    writer = ColbertWriter(root, 4)
    writer.add_document("doc.md", _vectors())
    writer.finish()
    return root


def test_roundtrip_mapping_fp16_and_missing_none(tmp_path):
    root = _store(tmp_path)
    store = ColbertStore(root)
    expected = _vectors()
    assert set(store) == set(expected)
    assert store.get("missing") is None
    assert store.token_count == 5
    for key, value in expected.items():
        actual = store[key]
        assert actual.dtype == np.float16
        assert np.array_equal(actual, value)
        actual[0, 0] = -10
        assert np.array_equal(store[key], value)


@pytest.mark.parametrize("damage", ["path", "offset", "dtype", "dim", "header", "file_size", "duplicate", "mixed_doc"])
def test_corrupt_index_or_header_rejected(tmp_path, damage):
    root = _store(tmp_path)
    path = root / "index.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    file_name = next(iter(data["files"]))
    chunk = next(iter(data["chunks"].values()))
    if damage == "path":
        chunk["file"] = "../escape.npy"
    elif damage == "offset":
        chunk["stop"] = 999
    elif damage == "dtype":
        data["dtype"] = "float32"
    elif damage == "dim":
        data["dim"] = 5
    elif damage == "header":
        np.save(root / file_name, np.ones((5, 4), dtype=np.float32), allow_pickle=False)
        data["files"][file_name]["bytes"] = (root / file_name).stat().st_size
    elif damage == "file_size":
        data["files"][file_name]["bytes"] += 1
    elif damage == "duplicate":
        path.write_text('{"format":1,"format":1}', encoding="utf-8")
    elif damage == "mixed_doc":
        list(data["chunks"].values())[1]["doc_id"] = "other.md"
    if damage != "duplicate":
        path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises((ValueError, KeyError)):
        ColbertStore(root)


def test_incremental_writer_links_unchanged_and_excludes_removed(tmp_path):
    old_root = tmp_path / "old"
    old = ColbertWriter(old_root, 4)
    old.add_document("changed.md", {"changed#1": np.ones((2, 4), dtype=np.float16)})
    old.add_document("kept.md", {"kept#1": np.ones((3, 4), dtype=np.float16)})
    old.add_document("removed.md", {"removed#1": np.ones((1, 4), dtype=np.float16)})
    old.finish()
    parent = ColbertStore(old_root)
    new_root = tmp_path / "new"
    new = ColbertWriter(new_root, 4, parent=parent,
                        verified_parent_hashes=parent.verify_full_hashes(),
                        removed_docs={"removed.md"})
    new.add_document("changed.md", {"changed#1": np.full((2, 4), 7, dtype=np.float16)})
    stats = new.finish()
    child = ColbertStore(new_root)
    assert set(child) == {"changed#1", "kept#1"}
    assert np.all(child["changed#1"] == 7)
    assert np.all(parent["changed#1"] == 1)
    kept_file = parent.index["chunks"]["kept#1"]["file"]
    assert os.path.samefile(old_root / kept_file, new_root / kept_file)
    assert stats["hardlinked_bytes"] > 0 and stats["copied_bytes"] == 0
    assert stats["inherited_hashes_not_reverified"] == 1


def test_copy_fallback_is_explicit(tmp_path, monkeypatch):
    old_root = tmp_path / "old"
    old = ColbertWriter(old_root, 4)
    old.add_document("kept.md", {"kept#1": np.ones((3, 4), dtype=np.float16)})
    old.finish()
    parent = ColbertStore(old_root)
    def fail_link(*_args): raise OSError("different filesystem")
    monkeypatch.setattr(os, "link", fail_link)
    new_root = tmp_path / "new"
    stats = ColbertWriter(new_root, 4, parent=parent,
                          verified_parent_hashes=parent.verify_full_hashes()).finish()
    name = parent.index["chunks"]["kept#1"]["file"]
    assert not os.path.samefile(old_root / name, new_root / name)
    assert stats["copied_bytes"] == (old_root / name).stat().st_size
    assert stats["hardlinked_bytes"] == 0


def test_deep_hash_check_detects_same_size_data_corruption(tmp_path):
    root = _store(tmp_path)
    store = ColbertStore(root)
    assert store.verify_full_hashes()
    name = next(iter(store.index["files"]))
    with (root / name).open("r+b") as stream:
        stream.seek(-1, os.SEEK_END)
        value = stream.read(1)
        stream.seek(-1, os.SEEK_END)
        stream.write(bytes([value[0] ^ 1]))
    # Header and offsets still look valid; the explicit full-byte pass catches it.
    assert len(ColbertStore(root)) == 2
    with pytest.raises(ValueError, match="hash mismatch"):
        ColbertStore(root).verify_full_hashes()


def test_now_empty_document_drops_parent_chunks(tmp_path):
    old_root = tmp_path / "old"
    old = ColbertWriter(old_root, 4)
    old.add_document("empty-now.md", {"old#1": np.ones((2, 4), dtype=np.float16)})
    old.finish()
    parent = ColbertStore(old_root)
    new = ColbertWriter(tmp_path / "new", 4, parent=parent,
                        verified_parent_hashes=parent.verify_full_hashes())
    new.remove_document("empty-now.md")
    new.finish()
    assert len(ColbertStore(tmp_path / "new")) == 0


def test_two_process_readers_block_exclusive_until_last_closes(tmp_path):
    database = tmp_path / "database"
    database.mkdir()
    version = "v20260921T000000"
    code = ("import sys; from core.writer_lock import try_version_lease; "
            "lease=try_version_lease(sys.argv[1],sys.argv[2]); "
            "print('READY' if lease else 'BUSY',flush=True); "
            "sys.stdin.readline(); lease.close() if lease else None")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    children = []
    try:
        for _ in range(2):
            child = subprocess.Popen([sys.executable, "-B", "-c", code, str(database), version],
                                     cwd=Path(__file__).resolve().parents[1], env=env,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
            children.append(child)
            status = child.stdout.readline().strip()
            assert status == "READY", status
        assert try_version_lease(database, version, exclusive=True) is None
        children[0].stdin.write("done\n")
        children[0].stdin.flush()
        assert children[0].wait(timeout=10) == 0
        assert try_version_lease(database, version, exclusive=True) is None
        children[1].stdin.write("done\n")
        children[1].stdin.flush()
        assert children[1].wait(timeout=10) == 0
        exclusive = try_version_lease(database, version, exclusive=True)
        assert exclusive is not None
        exclusive.close()
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)


def test_reader_owns_lease_until_close(tmp_path):
    database = tmp_path / "database"
    version = "v20260921T000000"
    root = database / "versions" / version / "colbert"
    writer = ColbertWriter(root, 4)
    writer.add_document("doc.md", _vectors())
    writer.finish()
    store = ColbertStore.open_version(database, version)
    assert try_version_lease(database, version, exclusive=True) is None
    assert store.get("missing") is None
    store.close()
    with pytest.raises(RuntimeError, match="closed"):
        store["doc#one"]
    exclusive = try_version_lease(database, version, exclusive=True)
    assert exclusive is not None
    exclusive.close()


def test_failed_open_releases_version_lease(tmp_path, monkeypatch):
    database = tmp_path / "database"
    version = "v20260921T000002"
    root = database / "versions" / version / "colbert"
    root.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        ColbertStore.open_version(database, version)
    exclusive = try_version_lease(database, version, exclusive=True)
    assert exclusive is not None
    exclusive.close()


def test_linked_version_component_rejected_before_open(tmp_path, monkeypatch):
    database = tmp_path / "database"
    version = "v20260921T000003"
    root = database / "versions" / version / "colbert"
    root.mkdir(parents=True)
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == root.parent or real_is_symlink(path))
    with pytest.raises(ValueError, match="linked version"):
        ColbertStore.open_version(database, version)


def test_parent_hash_attestation_required(tmp_path):
    root = _store(tmp_path)
    parent = ColbertStore(root)
    with pytest.raises(ValueError, match="attested"):
        ColbertWriter(tmp_path / "new", 4, parent=parent)
    with pytest.raises(ValueError, match="attested"):
        ColbertWriter(tmp_path / "new", 4, parent=parent,
                      verified_parent_hashes={"wrong": "hash"})


def test_lease_released_by_process_exit(tmp_path):
    database = tmp_path / "database"
    database.mkdir()
    version = "v20260921T000001"
    code = ("import sys; from core.writer_lock import try_version_lease; "
            "lease=try_version_lease(sys.argv[1],sys.argv[2]); "
            "print('READY' if lease else 'BUSY',flush=True); sys.stdin.readline()")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    child = subprocess.Popen([sys.executable, "-B", "-c", code, str(database), version],
                             cwd=Path(__file__).resolve().parents[1], env=env,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "READY"
        assert try_version_lease(database, version, exclusive=True) is None
        child.kill()
        child.wait(timeout=10)
        deadline = time.monotonic() + 5
        exclusive = None
        while exclusive is None and time.monotonic() < deadline:
            exclusive = try_version_lease(database, version, exclusive=True)
            if exclusive is None:
                time.sleep(0.05)
        assert exclusive is not None
        exclusive.close()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)

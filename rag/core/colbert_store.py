"""Immutable per-document ColBERT NPY sidecar (F5A, not yet wired to production)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import weakref
from collections.abc import Iterator, Mapping
from pathlib import Path

import numpy as np

from core.config import DENSE_DIM
from core.writer_lock import VersionLease, try_version_lease

FORMAT = 1
_FILENAME = re.compile(r"d-[0-9a-f]{64}\.npy\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _file(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not _FILENAME.fullmatch(name):
        raise ValueError(f"invalid NPY filename: {name!r}")
    path = root / name
    if (path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())
            or not path.is_file() or path.resolve().parent != root.resolve()):
        raise ValueError(f"missing, linked, or escaping NPY file: {name}")
    return path


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class ColbertStore(Mapping[str, np.ndarray]):
    """Index in RAM; each get opens/copies one chunk and closes its read-only map."""

    def __init__(self, root: str | Path, lease: VersionLease | None = None):
        self.root = Path(root)
        index_path = self.root / "index.json"
        try:
            if (self.root.is_symlink() or index_path.is_symlink()
                    or (hasattr(self.root, "is_junction") and self.root.is_junction())
                    or (hasattr(index_path, "is_junction") and index_path.is_junction())):
                raise ValueError("linked colbert root/index forbidden")
            index = json.loads(index_path.read_text(encoding="utf-8"), object_pairs_hook=_object)
            self._validate(index)
        except BaseException:
            if lease is not None:
                lease.close()
            raise
        self.index = index
        self._lease = lease
        self._finalizer = weakref.finalize(self, lease.close) if lease is not None else None
        self._closed = False

    @classmethod
    def open_version(cls, database_dir: str | Path, version: str) -> ColbertStore:
        base = Path(database_dir)
        root = base / "versions" / version / "colbert"
        for path in (base, base / "versions", base / "versions" / version, root):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError(f"linked version path forbidden: {path}")
        lease = try_version_lease(database_dir, version)
        if lease is None:
            raise BlockingIOError(f"version {version} is being removed")
        try:
            for path in (base, base / "versions", base / "versions" / version, root):
                if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                    raise ValueError(f"linked version path forbidden: {path}")
            if not root.is_dir() or base.resolve() not in root.resolve().parents:
                raise FileNotFoundError(f"version vanished before reader open: {version}")
            return cls(root, lease)
        except BaseException:
            lease.close()
            raise

    def _validate(self, index: dict) -> None:
        if not isinstance(index, dict) or set(index) != {"format", "dtype", "dim", "chunks", "files"}:
            raise ValueError("invalid colbert index fields")
        if index["format"] != FORMAT or index["dtype"] != "float16":
            raise ValueError("unsupported colbert format/dtype")
        if type(index["dim"]) is not int or index["dim"] <= 0:
            raise ValueError("invalid vector dimension")
        chunks, files = index["chunks"], index["files"]
        if not isinstance(chunks, dict) or not isinstance(files, dict):
            raise ValueError("invalid chunk/file tables")
        spans: dict[str, list[tuple[int, int]]] = {name: [] for name in files}
        file_docs: dict[str, str] = {}
        for name, meta in files.items():
            if not isinstance(meta, dict) or set(meta) != {"sha256", "bytes", "rows"}:
                raise ValueError(f"invalid file metadata: {name}")
            path = _file(self.root, name)
            if not isinstance(meta["sha256"], str) or not _HASH.fullmatch(meta["sha256"]):
                raise ValueError(f"invalid hash: {name}")
            if type(meta["bytes"]) is not int or meta["bytes"] != path.stat().st_size:
                raise ValueError(f"file size mismatch: {name}")
            if type(meta["rows"]) is not int or meta["rows"] <= 0:
                raise ValueError(f"invalid row count: {name}")
            array = np.load(path, mmap_mode="r", allow_pickle=False)
            try:
                if array.dtype != np.dtype("float16") or array.shape != (meta["rows"], index["dim"]):
                    raise ValueError(f"NPY header mismatch: {name}")
            finally:
                if isinstance(array, np.memmap):
                    array._mmap.close()
                del array
        for key, entry in chunks.items():
            if not isinstance(key, str) or not key or not isinstance(entry, dict) or set(entry) != {"doc_id", "file", "start", "stop"}:
                raise ValueError(f"invalid chunk entry: {key!r}")
            name, start, stop = entry["file"], entry["start"], entry["stop"]
            if name not in files or not isinstance(entry["doc_id"], str) or not entry["doc_id"]:
                raise ValueError(f"invalid chunk document/file: {key}")
            if type(start) is not int or type(stop) is not int or not 0 <= start < stop <= files[name]["rows"]:
                raise ValueError(f"invalid chunk offsets: {key}")
            if name in file_docs and file_docs[name] != entry["doc_id"]:
                raise ValueError(f"multiple documents in one NPY file: {name}")
            file_docs[name] = entry["doc_id"]
            spans[name].append((start, stop))
        for name, positions in spans.items():
            if not positions:
                raise ValueError(f"unreferenced NPY file: {name}")
            cursor = 0
            for start, stop in sorted(positions):
                if start != cursor:
                    raise ValueError(f"overlap/gap in NPY file: {name}")
                cursor = stop
            if cursor != files[name]["rows"]:
                raise ValueError(f"unindexed NPY rows: {name}")

    def __getitem__(self, key: str) -> np.ndarray:
        if self._closed:
            raise RuntimeError("ColbertStore closed")
        entry = self.index["chunks"][key]
        array = np.load(_file(self.root, entry["file"]), mmap_mode="r", allow_pickle=False)
        try:
            return np.array(array[entry["start"]:entry["stop"]], copy=True)
        finally:
            array._mmap.close()
            del array

    def __iter__(self) -> Iterator[str]:
        return iter(self.index["chunks"])

    def __len__(self) -> int:
        return len(self.index["chunks"])

    @property
    def token_count(self) -> int:
        """Count from validated offsets; never open/decompress all chunk arrays."""
        return sum(entry["stop"] - entry["start"] for entry in self.index["chunks"].values())

    def close(self) -> None:
        self._closed = True
        if self._finalizer is not None:
            self._finalizer()

    def verify_full_hashes(self) -> dict[str, str]:
        """Explicit deep integrity pass; ordinary open checks metadata/header only."""
        checked = {}
        for name, meta in self.index["files"].items():
            digest = _sha(_file(self.root, name))
            if digest != meta["sha256"]:
                raise ValueError(f"NPY hash mismatch: {name}")
            checked[name] = digest
        return checked


class ColbertWriter:
    """Write each changed document immediately, then link/copy unchanged parent files."""

    def __init__(self, root: str | Path, dim: int | None, *, parent: ColbertStore | None = None,
                 verified_parent_hashes: Mapping[str, str] | None = None,
                 removed_docs: set[str] | frozenset[str] = frozenset()):
        if ((dim is not None and (type(dim) is not int or dim <= 0))
                or (parent is not None and dim is not None and parent.index["dim"] != dim)):
            raise ValueError("invalid/incompatible dimension")
        if parent is not None:
            expected = {name: meta["sha256"] for name, meta in parent.index["files"].items()}
            if verified_parent_hashes is None or dict(verified_parent_hashes) != expected:
                raise ValueError("parent file hashes must be explicitly attested before reuse")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.dim = dim if dim is not None else (parent.index["dim"] if parent is not None and parent.index["chunks"] else None)
        self.parent = parent
        self.removed_docs = set(removed_docs)
        self.changed_docs: set[str] = set()
        self.chunks: dict = {}
        self.files: dict = {}
        self.new_files: set[str] = set()
        self.stats = {"written_bytes": 0, "hardlinked_bytes": 0, "copied_bytes": 0,
                      "inherited_hashes_not_reverified": 0}
        self.finished = False

    def add_document(self, doc_id: str, vectors: Mapping[str, np.ndarray]) -> None:
        if self.finished or not isinstance(doc_id, str) or not doc_id or doc_id in self.changed_docs:
            raise ValueError("invalid/duplicate/removed document")
        if not vectors:
            raise ValueError("empty document vectors")
        arrays = []
        spans = []
        cursor = 0
        for chunk_id, value in vectors.items():
            array = np.asarray(value)
            if self.dim is None and array.ndim == 2:
                self.dim = int(array.shape[1])
            if not isinstance(chunk_id, str) or not chunk_id or chunk_id in self.chunks or array.dtype != np.float16 or array.ndim != 2 or array.shape[1] != self.dim or array.shape[0] == 0:
                raise ValueError(f"invalid vector chunk: {chunk_id!r}")
            arrays.append(array)
            spans.append((chunk_id, cursor, cursor + len(array)))
            cursor += len(array)
        fd, temp_name = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                np.save(stream, np.concatenate(arrays, axis=0), allow_pickle=False)
                stream.flush()
                os.fsync(stream.fileno())
            temp = Path(temp_name)
            digest = _sha(temp)
            opaque = hashlib.sha256(doc_id.encode("utf-8") + bytes.fromhex(digest)).hexdigest()
            name = f"d-{opaque}.npy"
            if (self.root / name).exists():
                raise FileExistsError(name)
            os.replace(temp, self.root / name)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        size = (self.root / name).stat().st_size
        self.files[name] = {"sha256": digest, "bytes": size, "rows": cursor}
        self.new_files.add(name)
        for chunk_id, start, stop in spans:
            self.chunks[chunk_id] = {"doc_id": doc_id, "file": name, "start": start, "stop": stop}
        self.changed_docs.add(doc_id)
        self.removed_docs.discard(doc_id)
        self.stats["written_bytes"] += size

    def remove_document(self, doc_id: str) -> None:
        """Drop a deleted or now-empty changed document without writing an empty NPY."""
        if self.finished or not isinstance(doc_id, str) or not doc_id or doc_id in self.changed_docs:
            raise ValueError("invalid/finished document removal")
        self.removed_docs.add(doc_id)

    def finish(self) -> dict:
        if self.finished:
            raise RuntimeError("writer already finished")
        if self.parent is not None:
            for key, entry in self.parent.index["chunks"].items():
                if entry["doc_id"] in self.changed_docs or entry["doc_id"] in self.removed_docs:
                    continue
                if key in self.chunks:
                    raise ValueError(f"duplicate inherited chunk: {key}")
                name = entry["file"]
                if name not in self.files:
                    source = _file(self.parent.root, name)
                    target = self.root / name
                    try:
                        os.link(source, target)
                        self.stats["hardlinked_bytes"] += source.stat().st_size
                    except OSError:
                        shutil.copy2(source, target)
                        self.stats["copied_bytes"] += source.stat().st_size
                    self.files[name] = dict(self.parent.index["files"][name])
                    self.stats["inherited_hashes_not_reverified"] += 1
                self.chunks[key] = dict(entry)
        index = {"format": FORMAT, "dtype": "float16", "dim": self.dim or DENSE_DIM,
                 "chunks": self.chunks, "files": self.files}
        temp = self.root / "index.json.tmp"
        with temp.open("w", encoding="utf-8") as stream:
            json.dump(index, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self.root / "index.json")
        check = ColbertStore(self.root)
        if len(check) != len(self.chunks):
            raise AssertionError("index validation failed")
        self.finished = True
        return dict(self.stats)

    @property
    def token_count(self) -> int:
        own = sum(item["stop"] - item["start"] for item in self.chunks.values())
        if self.parent is None:
            return own
        return own + sum(item["stop"] - item["start"]
                         for item in self.parent.index["chunks"].values()
                         if item["doc_id"] not in self.changed_docs | self.removed_docs)

"""F4 disposable reader experiment. Run only from this checkout; never writes sources."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import threading
import time
import platform
from collections.abc import Mapping, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RUN = HERE.parent
RAG = HERE.parents[3]
sys.path.insert(0, str(RAG))
from core.artifacts import _load_vectors  # production loader, imported before worker baselines
HIST = RAG / "eval/results/sidecar_20260915/sandbox/historical-artifacts/v20260911T155042"
PROVENANCE = RAG / "eval/results/sidecar_20260915/evidence/historical-artifacts-provenance.json"
F3 = RAG / "eval/results/sidecar_delta_post_20260921_mixed_n100/sandbox/experiment/rag/database"
F3_RESULT = RAG / "eval/results/sidecar_delta_post_20260921_mixed_n100/evidence/result.json"
PREFLIGHT = HERE / "pm-preflight.json"
COLLECTION = "sidecar_0628_mixed_n100_post"
QUERIES = ("prenotazione evento posti", "pagamenti accettati", "notifiche prenotazione")


def _under(path: Path, root: Path) -> Path:
    path, root = path.resolve(), root.resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"path escapes experiment: {path}")
    return path


def _write_json(path: Path, value: object) -> None:
    _under(path, RUN)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def verify_history() -> dict:
    records = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    checked = {}
    for record in records:
        path = HIST / Path(record["copy"]).name
        _under(path, HIST)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest.casefold() != record["sha256"].casefold() or path.stat().st_size != record["bytes"]:
            raise ValueError(f"historical copy changed: {path.name}")
        checked[path.name] = {"sha256": digest, "bytes": path.stat().st_size}
    return checked


class Eager(Mapping):
    def __init__(self, path: Path):
        self.values = _load_vectors(path)

    def __getitem__(self, key): return self.values[key]
    def __iter__(self) -> Iterator[str]: return iter(self.values)
    def __len__(self): return len(self.values)


class LazyNPZ(Mapping):
    """One ZipFile per reader; lock protects shared seek/read state."""
    def __init__(self, path: Path):
        self.data = np.load(path, allow_pickle=False)
        self.keys = tuple(str(k) for k in self.data["keys"])
        self.positions = {key: i for i, key in enumerate(self.keys)}
        self.lock = threading.RLock()

    def __getitem__(self, key):
        with self.lock:
            return self.data[f"v{self.positions[key]}"]

    def __iter__(self) -> Iterator[str]: return iter(self.keys)
    def __len__(self): return len(self.keys)
    def close(self): self.data.close()


class PerDocNPY(Mapping):
    """Read-only map held only until the requested chunk has been copied."""
    def __init__(self, root: Path):
        self.root = root
        self.index = json.loads((root / "index.json").read_text(encoding="utf-8"))

    def __getitem__(self, key):
        filename, start, end = self.index[key]
        path = _under(self.root / filename, self.root)
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        try:
            return np.array(array[start:end], copy=True)
        finally:
            array._mmap.close()
            del array

    def __iter__(self) -> Iterator[str]: return iter(self.index)
    def __len__(self): return len(self.index)


def convert(source: Path, chunks: Path, target: Path) -> dict:
    """Streaming by document: only one document's arrays reside in memory."""
    _under(target, RUN)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(target)
    doc_by_chunk = {key: value["doc_id"] for key, value in json.loads(chunks.read_text(encoding="utf-8")).items()}
    with np.load(source, allow_pickle=False) as data:
        keys = [str(k) for k in data["keys"]]
        groups: dict[str, list[tuple[str, int]]] = {}
        for i, key in enumerate(keys):
            groups.setdefault(doc_by_chunk[key], []).append((key, i))
        target.mkdir(parents=True)
        index = {}
        for j, (_, members) in enumerate(groups.items()):
            filename = f"d{j:04d}.npy"
            arrays = [data[f"v{i}"] for _, i in members]
            offsets = np.cumsum([0] + [len(a) for a in arrays])
            packed = np.concatenate(arrays, axis=0)
            np.save(target / filename, packed, allow_pickle=False)
            for (key, _), start, end in zip(members, offsets[:-1], offsets[1:]):
                index[key] = (filename, int(start), int(end))
            del packed, arrays
    _write_json(target / "index.json", index)
    return {"documents": len(groups), "chunks": len(index), "bytes": sum(p.stat().st_size for p in target.iterdir())}


def reader(kind: str, npz: Path, npy: Path) -> Mapping:
    if kind == "eager": return Eager(npz)
    if kind == "lazy": return LazyNPZ(npz)
    if kind == "npy": return PerDocNPY(npy)
    raise ValueError(kind)


def _close(value):
    close = getattr(value, "close", None)
    if close is not None: close()


def parity(npz: Path, npy: Path) -> dict:
    from core.retrieval import colbert_maxsim, rank_sections_by_relevance
    stores = [reader(kind, npz, npy) for kind in ("eager", "lazy", "npy")]
    try:
        keys = list(stores[0])
        if any(set(s) != set(keys) for s in stores[1:]):
            raise AssertionError("key set differs")
        for key in keys:
            a = stores[0][key]
            if a.dtype != np.float16 or any(not np.array_equal(a, s[key]) for s in stores[1:]):
                raise AssertionError(f"array mismatch: {key}")
        query = np.asarray(stores[0][keys[0]][:2], dtype=np.float32)
        ranked = [rank_sections_by_relevance(keys[:12] + ["missing"], colbert_store=s,
                                             colbert_query=query, min_score=-1e9) for s in stores]
        if ranked[0] != ranked[1] or ranked[0] != ranked[2] or ranked[0][-1] != ("missing", None):
            raise AssertionError("graph score/rank/missing parity")
        sequential = [colbert_maxsim(query, stores[0].get(k)) for k in keys[:16] * 3]
        for store in stores:
            with ThreadPoolExecutor(max_workers=4) as pool:
                concurrent = list(pool.map(lambda k: colbert_maxsim(query, store.get(k)), keys[:16] * 3))
            if concurrent != sequential:
                raise AssertionError(f"concurrent score mismatch: {type(store).__name__}")
        return {"chunks": len(keys), "ranked": ranked[0], "concurrent_reads_per_reader": len(sequential)}
    finally:
        for store in stores: _close(store)


def snapshot_publication_check(npz: Path, npy: Path, scratch: Path) -> dict:
    """Old reader stays usable while a new immutable version is built and selected."""
    _under(scratch, RUN)
    old = PerDocNPY(npy)
    key = next(iter(old))
    before = old[key]
    # An independent generation has its own files. Only a pointer changes atomically.
    import shutil
    scratch.mkdir(parents=True, exist_ok=False)
    new = scratch / "new"
    with ThreadPoolExecutor(max_workers=2) as pool:
        old_reads = pool.submit(lambda: [old[key] for _ in range(8)])
        shutil.copytree(npy, new)
        if any(not np.array_equal(before, value) for value in old_reads.result()):
            raise AssertionError("old snapshot changed during new copy")
    candidate = PerDocNPY(new)
    filename, start, _ = candidate.index[key]
    changed = np.load(new / filename, mmap_mode="r+", allow_pickle=False)
    changed[start, 0] += np.float16(1)
    changed.flush()
    changed._mmap.close()
    del changed
    pointer = scratch / "CURRENT"
    temp = scratch / "CURRENT.tmp"
    temp.write_text("new\n", encoding="utf-8")
    os.replace(temp, pointer)
    fresh = PerDocNPY(scratch / pointer.read_text(encoding="utf-8").strip())
    if not np.array_equal(before, old[key]) or np.array_equal(before, fresh[key]):
        raise AssertionError("old snapshot changed or new generation did not change")
    return {"old_reader_preserved": True, "new_reader_updated_only": True}


def _metrics() -> dict:
    import psutil
    p = psutil.Process()
    mem = p.memory_full_info()
    io = p.io_counters() if hasattr(p, "io_counters") else None
    try: files = len(p.open_files())
    except (OSError, psutil.Error): files = None
    try: maps = len(p.memory_maps(grouped=False))
    except (OSError, psutil.Error): maps = None
    return {"rss_bytes": mem.rss, "uss_bytes": getattr(mem, "uss", None),
            "private_bytes": getattr(mem, "private", None),
            "read_bytes": getattr(io, "read_bytes", None), "write_bytes": getattr(io, "write_bytes", None),
            "open_files": files, "maps": maps}


def io_worker(kind: str, npz: Path, npy: Path, candidates: Path, output: Path) -> None:
    seed = _hash_seed()
    from core.retrieval import rank_sections_by_relevance
    payload = json.loads(candidates.read_text(encoding="utf-8"))
    ids = payload["ids"]
    query = np.asarray(payload["query"], dtype=np.float32)
    baseline = _metrics()
    t = time.perf_counter()
    store = reader(kind, npz, npy)
    load_s = time.perf_counter() - t
    loaded = _metrics()
    timings = []
    checks = []
    try:
        for _ in range(6):
            start = time.perf_counter()
            rank = rank_sections_by_relevance(ids, colbert_store=store, colbert_query=query, min_score=-1e9)
            timings.append(time.perf_counter() - start)
            checks.append(rank)
        if any(check != checks[0] for check in checks[1:]): raise AssertionError("warm rank drift")
        after = _metrics()
    finally: _close(store)
    _write_json(output, {"kind": kind, "baseline_after_import": baseline, "after_load": loaded,
                         "after_reads": after, "load_s": load_s, "first_s": timings[0],
                         "warm_s": timings[1:], "rank": checks[0], "pid": os.getpid(), "python_hash_seed": seed,
                         "label": "historical I/O candidate replay; not full retrieval"})


def _source_guard():
    if not HIST.is_dir() or not F3.is_dir(): raise FileNotFoundError("historical/F3 baseline missing")
    return verify_history()


def _hash_seed() -> str:
    seed = os.environ.get("PYTHONHASHSEED")
    if seed != "0": raise EnvironmentError("set PYTHONHASHSEED=0 before measured workers")
    return seed


def validate_f3_disk() -> dict:
    """Pin CURRENT and every frozen artifact to the accepted F3 evidence."""
    record = json.loads(F3_RESULT.read_text(encoding="utf-8"))
    if record["status"] != "completed" or record["parameters"]["collection"] != COLLECTION:
        raise ValueError("F3 evidence is not the accepted mixed N100 collection")
    current = (F3 / "CURRENT").read_bytes()
    if current.hex() != record["baseline_current"]:
        raise ValueError("F3 CURRENT differs from accepted baseline")
    checked = {}
    for name, expected in record["baseline_database"].items():
        path = _under(F3 / name, F3)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != expected["sha256"] or path.stat().st_size != expected["bytes"]:
            raise ValueError(f"F3 baseline artifact differs: {name}")
        checked[name] = digest
    source, _, _ = _f3_paths()
    folder = source.parent
    manifest = json.loads((folder / "index_manifest.json").read_text(encoding="utf-8"))
    if manifest["qdrant_collection"] != COLLECTION:
        raise ValueError("F3 manifest collection mismatch")
    for name, digest in manifest["artifact_hashes"].items():
        if checked.get(f"versions/{folder.name}/{name}") != digest:
            raise ValueError(f"F3 manifest hash mismatch: {name}")
    return {"current_hex": current.hex(), "artifact_hashes": checked,
            "expected_points": record["baseline_points"]}


def validate_f3_qdrant(qdrant) -> dict:
    from scripts.bench_delta import _point_digest
    disk = validate_f3_disk()
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if preflight["full_qdrant_points"] != disk["expected_points"] or not preflight["full_corpus_verified"]:
        raise ValueError("PM preflight and F3 evidence disagree")
    if COLLECTION not in {c.name for c in qdrant.get_collections().collections}:
        raise ValueError("dedicated F3 collection absent")
    actual = _point_digest(qdrant, COLLECTION)
    if actual != disk["expected_points"]:
        raise ValueError("F3 Qdrant points differ from accepted baseline")
    return {"current_hex": disk["current_hex"], "points": actual,
            "artifact_hashes": disk["artifact_hashes"]}


def compare_outputs() -> dict:
    """Strict scored/ranked parity for each repeat, across all reader variants."""
    summary = {}
    for label in ("io", "full"):
        rows = {}
        for kind in ("eager", "lazy", "npy"):
            rows[kind] = [json.loads((HERE / f"{label}-{kind}-{i}.json").read_text(encoding="utf-8")) for i in range(5)]
        def scored(row):
            if label == "io": return row["rank"]
            return [(entry["question"], entry["results"], entry["graph_branch"]) for entry in row["queries"]]
        baseline = scored(rows["eager"][0])
        if any(scored(row) != baseline for values in rows.values() for row in values):
            raise AssertionError(f"{label} ranking/score parity failed")
        summary[label] = {kind: {
            "load_s": {"median": statistics.median(row["load_s"] for row in values),
                       "min": min(row["load_s"] for row in values),
                       "max": max(row["load_s"] for row in values)},
            "rss_after_load_bytes": [row["after_load"]["rss_bytes"] for row in values],
            "uss_after_load_bytes": [row["after_load"]["uss_bytes"] for row in values],
            **({"retrieval_s_by_query": [{"median": statistics.median(row["queries"][q]["retrieval_s"] for row in values),
                                          "min": min(row["queries"][q]["retrieval_s"] for row in values),
                                          "max": max(row["queries"][q]["retrieval_s"] for row in values)}
                                         for q in range(len(QUERIES))]} if label == "full" else {}),
            **({"first_s": {"median": statistics.median(row["first_s"] for row in values),
                              "min": min(row["first_s"] for row in values),
                              "max": max(row["first_s"] for row in values)},
                "warm_s_median_each": [statistics.median(row["warm_s"]) for row in values]} if label == "io" else {})
        } for kind, values in rows.items()}
    _write_json(HERE / "comparison.json", summary)
    return summary


def _f3_paths() -> tuple[Path, Path, Path]:
    version = (F3 / "CURRENT").read_text(encoding="utf-8").strip()
    if not version.startswith("v") or "/" in version or "\\" in version:
        raise ValueError("invalid F3 CURRENT")
    folder = _under(F3 / "versions" / version, F3)
    return folder / "colbert.npz", folder / "chunks.json", folder / "graph.json"


def _model():
    # The caller sets HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE and CPU threads.
    if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("TRANSFORMERS_OFFLINE") != "1":
        raise EnvironmentError("model runs require HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1")
    from FlagEmbedding import BGEM3FlagModel
    from core.config import EMBEDDING_MODEL
    return BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False, devices="cpu")


def prepare_candidates() -> dict:
    """Real once-only encode; fixed historical IDs give each reader identical I/O."""
    _hash_seed()
    from core.retrieval import encode_query
    import torch
    torch.set_num_threads(4)
    model = _model()
    chunks = json.loads((HIST / "chunks.json").read_text(encoding="utf-8"))
    ids = list(chunks)[:32] + ["missing"]
    encoding = encode_query(model, QUERIES[0])
    result = {"ids": ids, "query": np.asarray(encoding["colbert"], dtype=np.float32).tolist(),
              "question": QUERIES[0], "label": "historical candidate replay, fixed IDs; not Qdrant retrieval"}
    _write_json(HERE / "historical-candidates.json", result)
    return {"ids": len(ids), "query_tokens": len(result["query"])}


def full_worker(kind: str, repeat: int) -> None:
    """Real encode + Qdrant + canonical hybrid_search, separate from reader load timing."""
    seed = _hash_seed()
    from core.retrieval import encode_query, hybrid_search, rank_sections_by_relevance
    from core.artifacts import _graph_from_json
    from qdrant_client import QdrantClient
    import torch
    torch.set_num_threads(4)
    source, _, graph_path = _f3_paths()
    target = RUN / "sandbox/f3-npy"
    qdrant = QdrantClient(url="http://127.0.0.1:16333", timeout=30)
    validated = validate_f3_qdrant(qdrant)
    model = _model()
    graph = _graph_from_json(json.loads(graph_path.read_text(encoding="utf-8")))
    baseline = _metrics()
    start = time.perf_counter()
    store = reader(kind, source, target)
    load_s = time.perf_counter() - start
    loaded = _metrics()
    rows = []
    try:
        for question in QUERIES:
            t = time.perf_counter()
            encoding = encode_query(model, question)
            encode_s = time.perf_counter() - t
            t = time.perf_counter()
            result = hybrid_search(question, 3, qdrant=qdrant, embed_model=model,
                                   colbert_store=store, collection_name=COLLECTION,
                                   query_encoding=encoding, graph=graph)
            retrieval_s = time.perf_counter() - t
            ids = [item["chunk_id"] for item in result] + ["missing"]
            ranked = rank_sections_by_relevance(ids, colbert_store=store,
                                                colbert_query=np.asarray(encoding["colbert"], dtype=np.float32),
                                                min_score=-1e9)
            rows.append({"question": question, "encode_s": encode_s,
                         "retrieval_s": retrieval_s, "results": result, "graph_branch": ranked})
        after = _metrics()
    finally:
        _close(store)
        qdrant.close()
    _write_json(HERE / f"full-{kind}-{repeat}.json",
                {"kind": kind, "repeat": repeat, "pid": os.getpid(), "python": sys.version,
                 "platform": platform.platform(), "collection": COLLECTION, "model_loaded_before_baseline": True,
                 "python_hash_seed": seed, "validated_baseline": validated,
                 "baseline_after_model_import": baseline, "after_load": loaded, "after_retrieval": after,
                 "load_s": load_s, "queries": rows, "label": "complete retrieval: real encode + Qdrant + canonical hybrid_search"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "convert", "convert-f3", "parity-history", "selfcheck", "prepare-candidates", "io-worker", "io-batch", "full-worker", "full-batch", "compare"))
    parser.add_argument("--kind", choices=("eager", "lazy", "npy"))
    parser.add_argument("--repeat", type=int)
    args = parser.parse_args()
    npz = HIST / "colbert.npz"
    npy = RUN / "sandbox/historical-npy"
    if args.command == "verify":
        _write_json(HERE / "historical-hashes.json", _source_guard()); return
    if args.command == "convert":
        _source_guard()
        _write_json(HERE / "conversion.json", convert(npz, HIST / "chunks.json", npy)); return
    if args.command == "convert-f3":
        validate_f3_disk()
        source, chunks, _ = _f3_paths()
        _write_json(HERE / "conversion-f3.json", convert(source, chunks, RUN / "sandbox/f3-npy")); return
    if args.command == "parity-history":
        _source_guard()
        _write_json(HERE / "historical-parity.json", parity(npz, npy)); return
    if args.command == "prepare-candidates":
        _source_guard()
        _write_json(HERE / "candidate-preparation.json", prepare_candidates()); return
    if args.command == "selfcheck":
        # Tiny synthetic fixture: no model, Qdrant, or historical performance claim.
        fixture = RUN / "sandbox/selfcheck"
        fixture.mkdir(parents=True, exist_ok=True)
        a = np.arange(12, dtype=np.float16).reshape(3, 4)
        b = np.arange(8, dtype=np.float16).reshape(2, 4)
        np.savez_compressed(fixture / "source.npz", keys=np.array(["doc/a#1", "doc/b#2"]), v0=a, v1=b)
        _write_json(fixture / "chunks.json", {"doc/a#1": {"doc_id": "doc/a"}, "doc/b#2": {"doc_id": "doc/b"}})
        target = fixture / "npy"
        if not target.exists(): convert(fixture / "source.npz", fixture / "chunks.json", target)
        result = parity(fixture / "source.npz", target)
        import uuid
        publication = fixture / f"publication-{uuid.uuid4().hex}"
        result.update(snapshot_publication_check(fixture / "source.npz", target, publication))
        _write_json(HERE / "synthetic-selfcheck.json", result); return
    if args.command in ("io-worker", "io-batch"):
        candidates = HERE / "historical-candidates.json"
        if not candidates.is_file(): raise FileNotFoundError("prepare historical-candidates.json")
        if not npy.is_dir(): raise FileNotFoundError("convert first")
        if args.command == "io-worker":
            if args.kind is None or args.repeat is None or not 0 <= args.repeat < 5: raise ValueError("kind and repeat 0..4 required")
            io_worker(args.kind, npz, npy, candidates, HERE / f"io-{args.kind}-{args.repeat}.json")
        else:
            for kind in ("eager", "lazy", "npy"):
                for repeat in range(5):
                    subprocess.run([sys.executable, "-B", str(__file__), "io-worker", "--kind", kind, "--repeat", str(repeat)], check=True, cwd=RAG)
        return
    if args.command == "full-worker":
        if args.kind is None or args.repeat is None or not 0 <= args.repeat < 5: raise ValueError("kind and repeat 0..4 required")
        full_worker(args.kind, args.repeat); return
    if args.command == "full-batch":
        for kind in ("eager", "lazy", "npy"):
            for repeat in range(5):
                subprocess.run([sys.executable, "-B", str(__file__), "full-worker", "--kind", kind, "--repeat", str(repeat)], check=True, cwd=RAG)
        return
    if args.command == "compare":
        compare_outputs(); return


if __name__ == "__main__":
    main()

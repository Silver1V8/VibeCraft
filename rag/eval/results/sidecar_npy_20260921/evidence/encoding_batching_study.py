"""Read-only F6 encoding-only study on the frozen F3 docs N100 corpus.

--selfcheck checks source SHA-256, canonical parsing and grouping without a model.
--run requires one offline CPU model and writes batching-study.json in this evidence
directory. It never writes the source corpus or calls Qdrant.
"""

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np

RAG = Path(__file__).resolve().parents[4]
RESULTS = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(RAG))

from core.chunking import chunk_markdown, read_document
from core.retrieval import rank_sections_by_relevance

SOURCE = RESULTS / "sidecar_delta_post_20260921_docs_n100"
RESULT = SOURCE / "evidence" / "result.json"
DOCS = SOURCE / "sandbox" / "experiment" / "docs"
QUERY = RESULTS / "sidecar_readers_20260921" / "evidence" / "historical-candidates.json"
OUTPUT = HERE / "batching-study.json"
BATCH = 12  # same as core.indexing._encode_chunks_to_points
VARIANTS = ("global", "per_document", "groups_12")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_chunks():
    record = read_json(RESULT)
    params = record.get("parameters") or {}
    if record.get("status") != "completed" or params.get("mode") != "docs" or params.get("n") != 100 or params.get("repeats") != 5:
        raise ValueError("source is not completed F3 docs N100")
    if DOCS.is_symlink() or not DOCS.is_dir():
        raise ValueError("frozen docs directory is missing or linked")
    files = sorted(DOCS.glob("*.md"))
    listed = {Path(name).resolve(): item for name, item in record["corpus"].items()
              if Path(name).resolve().parent == DOCS.resolve()}
    if len(files) != 100 or len(listed) != 100 or {file.resolve() for file in files} != set(listed):
        raise ValueError("frozen F3 corpus is not exactly 100 Markdown documents")
    chunks = []
    for file in files:
        if file.is_symlink() or file.stat().st_size != listed[file.resolve()]["bytes"] or sha256(file) != listed[file.resolve()]["sha256"]:
            raise ValueError(f"frozen corpus changed: {file.name}")
        metadata, body = read_document(file)
        if not body.strip():
            raise ValueError(f"empty frozen document: {file.name}")
        parsed = chunk_markdown(file.relative_to(DOCS).as_posix(), metadata, body)
        if len(parsed) != 1:
            raise ValueError(f"expected one canonical chunk per frozen document: {file.name}")
        chunks.extend(parsed)
    if len(chunks) != 100 or len({chunk["chunk_id"] for chunk in chunks}) != 100:
        raise ValueError("expected exactly 100 unique canonical chunks")
    query_data = read_json(QUERY)
    query = np.asarray(query_data["query"], dtype=np.float32)
    if query.ndim != 2 or query.shape[1] != 1024 or not np.isfinite(query).all():
        raise ValueError("cached ColBERT query invalid")
    return chunks, query, {"result": str(RESULT), "docs": str(DOCS),
                           "query": str(QUERY), "chunk_count": len(chunks),
                           "docs_sha256": {file.name: listed[file.resolve()]["sha256"] for file in files},
                           "query_sha256": sha256(QUERY)}


def groups(chunks, variant):
    if variant == "global":
        return [chunks]
    if variant == "per_document":
        return [[chunk] for chunk in chunks]
    if variant == "groups_12":
        return [chunks[i:i + BATCH] for i in range(0, len(chunks), BATCH)]
    raise ValueError(variant)


def encode_variant(model, chunks, variant, *, retain):
    output = {}
    group_sizes = []
    encode_seconds = 0.0
    for batch in groups(chunks, variant):
        group_sizes.append(len(batch))
        start = time.perf_counter()
        encoded = model.encode([chunk["text"] for chunk in batch], batch_size=BATCH,
                               max_length=8192, return_dense=True, return_sparse=True,
                               return_colbert_vecs=True)
        encode_seconds += time.perf_counter() - start
        if retain:
            for chunk, dense, sparse, colbert in zip(batch, encoded["dense_vecs"],
                                                      encoded["lexical_weights"], encoded["colbert_vecs"], strict=True):
                output[chunk["chunk_id"]] = {"dense": np.asarray(dense),
                                             "sparse": {int(key): float(value) for key, value in sparse.items()},
                                             "colbert": np.asarray(colbert).astype(np.float16)}
    if len(group_sizes) != (1 if variant == "global" else 100 if variant == "per_document" else 9):
        raise AssertionError("unexpected encode call count")
    if retain and len(output) != len(chunks):
        raise AssertionError("encoder returned incomplete chunk output")
    return encode_seconds, group_sizes, output


def delta(left, right):
    if left.shape != right.shape:
        return {"shape_equal": False, "shape_left": list(left.shape), "shape_right": list(right.shape)}
    a, b = left.astype(np.float64), right.astype(np.float64)
    difference = np.abs(a - b)
    return {"shape_equal": True, "different_values": int(np.count_nonzero(a != b)),
            "max_abs_difference": float(difference.max()) if difference.size else 0.0}


def compare(left, right, ids):
    different = {"dense": 0, "sparse": 0, "colbert": 0}
    values = {"dense": 0, "sparse": 0, "colbert": 0}
    maxima = {"dense": 0.0, "sparse": 0.0, "colbert": 0.0}
    sparse_key_different = []
    shape_different = []
    for key in ids:
        a, b = left[key], right[key]
        for kind in ("dense", "colbert"):
            d = delta(a[kind], b[kind])
            if not d["shape_equal"]:
                shape_different.append({"chunk_id": key, "kind": kind, **d})
                continue
            if d["different_values"]:
                different[kind] += 1
                values[kind] += d["different_values"]
                maxima[kind] = max(maxima[kind], d["max_abs_difference"])
        ak, bk = set(a["sparse"]), set(b["sparse"])
        if ak != bk:
            sparse_key_different.append(key)
        common = sorted(ak & bk)
        d = delta(np.asarray([a["sparse"][i] for i in common]),
                  np.asarray([b["sparse"][i] for i in common]))
        if d["different_values"] or ak != bk:
            different["sparse"] += 1
            values["sparse"] += d["different_values"]
            maxima["sparse"] = max(maxima["sparse"], d["max_abs_difference"])
    return {"different_chunks": different, "different_values": values,
            "max_abs_difference": maxima, "sparse_key_different_ids": sparse_key_different,
            "shape_different": shape_different}


def rank(output, ids, query):
    return rank_sections_by_relevance(ids + ["missing.synthetic#00"],
                                      colbert_store={key: output[key]["colbert"] for key in ids},
                                      colbert_query=query)


def selfcheck():
    chunks, query, source = source_chunks()
    sizes = {variant: [len(group) for group in groups(chunks, variant)] for variant in VARIANTS}
    if sizes["global"] != [100] or sizes["per_document"] != [1] * 100 or sizes["groups_12"] != [12] * 8 + [4]:
        raise AssertionError("incorrect grouping")
    if OUTPUT.parent != HERE or not OUTPUT.resolve().is_relative_to(HERE.resolve()):
        raise ValueError("output escapes evidence")
    print(json.dumps({"selfcheck": "passed", "source": source["result"],
                      "chunks": len(chunks), "query_shape": list(query.shape),
                      "calls_per_variant": {key: len(value) for key, value in sizes.items()},
                      "model_loaded": False}))
    return chunks, query, source


def run():
    for name, expected in (("HF_HUB_OFFLINE", "1"), ("TRANSFORMERS_OFFLINE", "1"),
                           ("CUDA_VISIBLE_DEVICES", "-1"), ("PYTHONHASHSEED", "0")):
        if os.environ.get(name) != expected:
            raise EnvironmentError(f"{name}={expected} required")
    chunks, query, source = selfcheck()
    import torch
    torch.set_num_threads(4)
    from FlagEmbedding import BGEM3FlagModel
    from core.config import EMBEDDING_MODEL
    model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False, devices="cpu")
    # Each variant gets one full warmup; measured rounds rotate first position.
    warmup = {}
    for variant in VARIANTS:
        elapsed, sizes, _ = encode_variant(model, chunks, variant, retain=False)
        warmup[variant] = {"seconds": elapsed, "calls": len(sizes), "group_sizes": sizes}
    trials = {variant: [] for variant in VARIANTS}
    vectors = {}
    order = []
    for repeat in range(3):
        sequence = VARIANTS[repeat:] + VARIANTS[:repeat]
        order.append(list(sequence))
        for variant in sequence:
            elapsed, sizes, output = encode_variant(model, chunks, variant, retain=variant not in vectors)
            trials[variant].append({"repeat": repeat, "encode_seconds": elapsed,
                                    "calls": len(sizes), "group_sizes": sizes})
            if output:
                vectors[variant] = output
    ids = [chunk["chunk_id"] for chunk in chunks]
    comparisons = {}
    for first, second in (("global", "per_document"), ("global", "groups_12"),
                          ("groups_12", "per_document")):
        comparisons[f"{first}_vs_{second}"] = compare(vectors[first], vectors[second], ids)
    rankings = {variant: rank(vectors[variant], ids, query) for variant in VARIANTS}
    metadata = {variant: {key: {"dense_shape": list(item["dense"].shape),
                                "dense_dtype": str(item["dense"].dtype),
                                "sparse_terms": len(item["sparse"]),
                                "colbert_shape": list(item["colbert"].shape),
                                "colbert_dtype": str(item["colbert"].dtype)}
                          for key, item in vectors[variant].items()} for variant in VARIANTS}
    payload = {"label": "encoding-only synthetic corpus study; no Qdrant/full retrieval",
               "source": source, "model": EMBEDDING_MODEL, "model_cpu_threads": 4,
               "batch_size": BATCH, "warmup": warmup, "measured_order": order,
               "trials": trials,
               "medians_encode_seconds": {variant: statistics.median(t["encode_seconds"] for t in trials[variant])
                                          for variant in VARIANTS},
               "vector_metadata": metadata, "vector_comparisons": comparisons,
               "colbert_replay": {"cached_query": str(QUERY), "scope": "same 100 IDs plus missing; cached query, not full retrieval",
                                  "rankings": rankings,
                                  "pair_exact": {f"{first}_vs_{second}": rankings[first] == rankings[second]
                                                 for first, second in (("global", "per_document"),
                                                                       ("global", "groups_12"),
                                                                       ("groups_12", "per_document"))}}}
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "medians_encode_seconds": payload["medians_encode_seconds"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selfcheck", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()
    selfcheck() if args.selfcheck else run()

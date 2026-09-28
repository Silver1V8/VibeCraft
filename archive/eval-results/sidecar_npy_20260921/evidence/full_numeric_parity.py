"""Read-only numeric comparison of the two frozen F5 full candidates."""
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from core.colbert_store import ColbertStore
from core.retrieval import rank_sections_by_relevance

RESULTS = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent
PRE = RESULTS / "sidecar_fullmemory_pre_20260921"
POST = RESULTS / "sidecar_fullmemory_post_20260921"
HIST = RESULTS / "sidecar_readers_20260921" / "evidence" / "historical-candidates.json"
OUTPUT = EVIDENCE / "full-numeric-parity.json"


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _points(qdrant, collection):
    order, points, offset = [], {}, None
    while True:
        page, offset = qdrant.scroll(collection_name=collection, offset=offset, limit=128,
                                     with_payload=True, with_vectors=True)
        for point in page:
            key = str(point.id)
            if key in points:
                raise ValueError(f"duplicate Qdrant point ID: {key}")
            order.append(key)
            points[key] = point
        if offset is None:
            return order, points


def _number_delta(left, right):
    a, b = np.asarray(left, dtype=np.float64), np.asarray(right, dtype=np.float64)
    if a.shape != b.shape:
        return {"shape_pre": list(a.shape), "shape_post": list(b.shape), "same_shape": False}
    diff = np.abs(a - b)
    changed = int(np.count_nonzero(a != b))
    return {"same_shape": True, "elements": int(a.size), "different_elements": changed,
            "max_abs_difference": float(diff.max()) if diff.size else 0.0,
            "mean_abs_difference": float(diff.mean()) if diff.size else 0.0}


class LegacyNPZ(Mapping):
    def __init__(self, archive):
        self.archive = archive
        keys = [str(key) for key in archive["keys"]]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate legacy NPZ chunk keys")
        self.members = {key: f"v{i}" for i, key in enumerate(keys)}

    def __iter__(self):
        return iter(self.members)

    def __len__(self):
        return len(self.members)

    def __getitem__(self, key):
        return self.archive[self.members[key]]


def main():
    pre_record, post_record = _json(PRE / "evidence" / "result.json"), _json(POST / "evidence" / "result.json")
    pre_version, post_version = pre_record["version"], post_record["version"]
    pre_dir = PRE / "sandbox" / "experiment" / "rag" / "database" / "versions" / pre_version
    post_dir = POST / "sandbox" / "experiment" / "rag" / "database" / "versions" / post_version
    pre_collection = pre_record["candidate"]["manifest"]["qdrant_collection"]
    post_collection = post_record["candidate"]["manifest"]["qdrant_collection"]
    if not pre_dir.is_dir() or not post_dir.is_dir():
        raise FileNotFoundError("frozen candidate version directory missing")
    if pre_record["status"] != "completed" or post_record["status"] != "completed":
        raise ValueError("candidate run incomplete")
    result = {"source": {"pre_result": str(PRE / "evidence" / "result.json"),
                         "post_result": str(POST / "evidence" / "result.json"),
                         "pre_version": pre_version, "post_version": post_version,
                         "pre_collection": pre_collection, "post_collection": post_collection,
                         "query_file": str(HIST)},
              "method": "Read-only Qdrant scroll and frozen artifact comparison; no model or new retrieval; exact equality reported separately from numeric differences."}

    qdrant = QdrantClient(url="http://127.0.0.1:16333", timeout=120)
    try:
        pre_order, pre_points = _points(qdrant, pre_collection)
        post_order, post_points = _points(qdrant, post_collection)
    finally:
        qdrant.close()
    common = sorted(pre_points.keys() & post_points.keys())
    result["qdrant"] = {"pre_count": len(pre_points), "post_count": len(post_points),
                        "same_scroll_order": pre_order == post_order,
                        "missing_in_post": sorted(pre_points.keys() - post_points.keys()),
                        "new_in_post": sorted(post_points.keys() - pre_points.keys()),
                        "payload_different_ids": [], "payload_key_order_different_ids": [],
                        "dense_different_points": 0, "dense_different_elements": 0,
                        "dense_max_abs_difference": 0.0,
                        "sparse_index_order_different_ids": [], "sparse_index_set_different_ids": [],
                        "sparse_value_different_points": 0, "sparse_value_different_elements": 0,
                        "sparse_max_abs_difference": 0.0, "examples": []}
    q = result["qdrant"]
    for pid in common:
        left, right = pre_points[pid], post_points[pid]
        if left.payload != right.payload:
            q["payload_different_ids"].append(pid)
        if list(left.payload) != list(right.payload):
            q["payload_key_order_different_ids"].append(pid)
        dense = _number_delta(left.vector["dense"], right.vector["dense"])
        li, ri = list(left.vector["sparse"].indices), list(right.vector["sparse"].indices)
        if li != ri:
            q["sparse_index_order_different_ids"].append(pid)
        if set(li) != set(ri):
            q["sparse_index_set_different_ids"].append(pid)
        lv = dict(zip(li, left.vector["sparse"].values))
        rv = dict(zip(ri, right.vector["sparse"].values))
        all_indices = sorted(set(lv) | set(rv))
        sparse = _number_delta([lv.get(i, 0.0) for i in all_indices],
                               [rv.get(i, 0.0) for i in all_indices])
        if dense.get("different_elements", 0):
            q["dense_different_points"] += 1
            q["dense_different_elements"] += dense["different_elements"]
            q["dense_max_abs_difference"] = max(q["dense_max_abs_difference"], dense["max_abs_difference"])
        if sparse.get("different_elements", 0):
            q["sparse_value_different_points"] += 1
            q["sparse_value_different_elements"] += sparse["different_elements"]
            q["sparse_max_abs_difference"] = max(q["sparse_max_abs_difference"], sparse["max_abs_difference"])
        if dense.get("different_elements", 0) or sparse.get("different_elements", 0) or left.payload != right.payload:
            q["examples"].append({"id": pid, "chunk_id": left.payload.get("chunk_id"),
                                  "dense": dense, "sparse": sparse})
    q["examples"] = sorted(q["examples"],
                           key=lambda item: max(item["dense"].get("max_abs_difference", 0),
                                                item["sparse"].get("max_abs_difference", 0)),
                           reverse=True)[:10]

    result["artifacts"] = {}
    for filename in ("graph.json", "chunks.json", "code.json", "dense.npz", "code.npz"):
        left, right = pre_dir / filename, post_dir / filename
        result["artifacts"][filename] = {"sha256_pre": _sha(left), "sha256_post": _sha(right),
                                          "byte_identical": _sha(left) == _sha(right)}
    with np.load(pre_dir / "dense.npz", allow_pickle=False) as pre_dense, np.load(post_dir / "dense.npz", allow_pickle=False) as post_dense:
        left, right = LegacyNPZ(pre_dense), LegacyNPZ(post_dense)
        keys = sorted(left.keys() & right.keys())
        different, elements, maximum = [], 0, 0.0
        for key in keys:
            delta = _number_delta(left[key], right[key])
            if delta.get("different_elements", 0):
                different.append(key)
                elements += delta["different_elements"]
                maximum = max(maximum, delta["max_abs_difference"])
        result["dense_sidecar"] = {"pre_chunks": len(left), "post_chunks": len(right),
                                   "missing_in_post": sorted(left.keys() - right.keys()),
                                   "new_in_post": sorted(right.keys() - left.keys()),
                                   "different_chunk_count": len(different),
                                   "different_element_count": elements, "max_abs_difference": maximum,
                                   "different_chunk_ids": different}

    post_colbert = ColbertStore(post_dir / "colbert")
    with np.load(pre_dir / "colbert.npz", allow_pickle=False) as archive:
        old = LegacyNPZ(archive)
        keys = sorted(old.keys() & post_colbert.keys())
        different, elements, maximum = [], 0, 0.0
        for key in keys:
            before, after = old[key], post_colbert[key]
            delta = _number_delta(before, after)
            if delta.get("different_elements", 0):
                different.append({"chunk_id": key, **delta})
                elements += delta["different_elements"]
                maximum = max(maximum, delta["max_abs_difference"])
        result["colbert_sidecar"] = {"pre_chunks": len(old), "post_chunks": len(post_colbert),
                                     "missing_in_post": sorted(old.keys() - post_colbert.keys()),
                                     "new_in_post": sorted(post_colbert.keys() - old.keys()),
                                     "different_chunk_count": len(different),
                                     "different_element_count": elements, "max_abs_difference": maximum,
                                     "different_chunks": different}
        query = np.asarray(_json(HIST)["query"], dtype=np.float32)
        ranked_ids = sorted(old.keys()) + ["missing.synthetic#00"]
        old_rank = rank_sections_by_relevance(ranked_ids, colbert_store=old, colbert_query=query)
        post_rank = rank_sections_by_relevance(ranked_ids, colbert_store=post_colbert, colbert_query=query)
        old_map, post_map = dict(old_rank), dict(post_rank)
        score_different = [key for key in ranked_ids if old_map[key] != post_map[key]]
        result["fixed_query_replay"] = {"question": _json(HIST)["question"],
                                         "candidate_count": len(ranked_ids), "missing_score": old_map["missing.synthetic#00"],
                                         "score_different_count": len(score_different),
                                         "score_different_ids": score_different,
                                         "ranking_identical": old_rank == post_rank,
                                         "ordered_ids_identical": [key for key, _ in old_rank] == [key for key, _ in post_rank],
                                         "top10_pre": old_rank[:10], "top10_post": post_rank[:10],
                                         "scope": "Fixed query and all 64 known chunk IDs plus one missing ID; no Qdrant search, encode, graph expansion, or full retrieval."}
    post_colbert.close()
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "qdrant_dense_different_points": q["dense_different_points"],
                      "qdrant_sparse_different_points": q["sparse_value_different_points"],
                      "colbert_different_chunks": result["colbert_sidecar"]["different_chunk_count"],
                      "replay_ranking_identical": result["fixed_query_replay"]["ranking_identical"]}))


if __name__ == "__main__":
    main()

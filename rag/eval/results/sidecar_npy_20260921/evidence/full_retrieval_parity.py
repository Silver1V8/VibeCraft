"""Paired, read-only full retrieval for the two frozen F5 full candidates.

From rag/, first run ``python -B .../full_retrieval_parity.py --selfcheck``.
For the real run set PYTHONHASHSEED=0, PYTHONUTF8=1,
PYTHONDONTWRITEBYTECODE=1, HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1,
CUDA_VISIBLE_DEVICES=-1, then use --run. One offline CPU model encodes each of
three queries once; canonical hybrid_search reads both physical collections.
The driver writes full-retrieval-parity.json beside this file only after every
query passes. It never reads CURRENT, promotes an index, or mutates Qdrant.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RESULTS = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.artifacts import _graph_from_json, _load_vectors
from core.colbert_store import ColbertStore
from core.retrieval import encode_query, hybrid_search
from scripts.bench_delta import _point_digest

QUERIES = ("prenotazione evento posti", "pagamenti accettati", "notifiche prenotazione")
QDRANT_URL = "http://127.0.0.1:16333"
OUTPUT = HERE / "full-retrieval-parity.json"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def candidate(label):
    run = RESULTS / f"sidecar_fullmemory_{label}_20260921"
    record = read_json(run / "evidence" / "result.json")
    if record["status"] != "completed" or not record["candidate"]["ok"]:
        raise ValueError(f"{label} candidate was not completed/validated")
    version = record["version"]
    if not isinstance(version, str) or not version.startswith("v") or Path(version).name != version:
        raise ValueError(f"invalid {label} version")
    database = run / "sandbox" / "experiment" / "rag" / "database"
    folder = database / "versions" / version
    if not folder.is_dir() or folder.is_symlink() or folder.resolve().parent != (database / "versions").resolve():
        raise ValueError(f"{label} explicit version directory absent/linked")
    manifest = read_json(folder / "index_manifest.json")
    if manifest != record["candidate"]["manifest"]:
        raise ValueError(f"{label} manifest changed")
    collection = manifest["qdrant_collection"]
    if collection != f"sidecar_0628_fullmemory_{label}__{version}":
        raise ValueError(f"{label} collection is not the frozen physical candidate")
    expected = record["candidate"]["artifact_hashes"]
    if expected != manifest["artifact_hashes"]:
        raise ValueError(f"{label} artifact hash table changed")
    for name, digest in expected.items():
        path = folder / name
        if path.is_symlink() or folder.resolve() not in path.resolve().parents or sha256(path) != digest:
            raise ValueError(f"{label} artifact changed: {name}")
    layout = record["candidate"]["colbert_layout"]
    if layout != ("npz" if label == "pre" else "npy"):
        raise ValueError(f"{label} ColBERT layout changed")
    return {"label": label, "run": run, "version": version, "folder": folder,
            "collection": collection, "manifest": manifest,
            "qdrant_points": record["candidate"]["qdrant_points"], "layout": layout}


class ReadOnlyQueries:
    """Only expose the Qdrant read used by hybrid_search, recording raw hits."""

    def __init__(self, client, collection):
        self.client = client
        self.collection = collection
        self.calls = []

    def query_points(self, **kwargs):
        if kwargs.get("collection_name") != self.collection or kwargs.get("using") not in ("dense", "sparse"):
            raise ValueError("retrieval escaped the frozen physical collection")
        response = self.client.query_points(**kwargs)
        self.calls.append({"using": kwargs["using"], "limit": kwargs["limit"],
                           "hits": [{"point_id": str(hit.id), "score": hit.score,
                                     "payload": hit.payload or {}} for hit in response.points]})
        return response


def load_reader(item):
    folder = item["folder"]
    graph = _graph_from_json(read_json(folder / "graph.json"))
    if item["layout"] == "npz":
        store = _load_vectors(folder / "colbert.npz")
    else:
        # Direct immutable candidate path: open_version would create a lease file
        # inside the frozen source database and violate this experiment's read-only scope.
        store = ColbertStore(folder / "colbert")
    return graph, store


def selfcheck():
    pre, post = candidate("pre"), candidate("post")
    if pre["manifest"]["embedding_model"] != post["manifest"]["embedding_model"]:
        raise ValueError("candidate embedding models differ")
    for name in ("graph.json", "chunks.json"):
        if sha256(pre["folder"] / name) != sha256(post["folder"] / name):
            raise ValueError(f"candidate {name} differs")
    if OUTPUT.parent != HERE or not OUTPUT.resolve().is_relative_to(HERE.resolve()):
        raise ValueError("output escapes evidence")
    class FakeClient:
        def query_points(self, **kwargs):
            return type("Response", (), {"points": []})()
    probe = ReadOnlyQueries(FakeClient(), pre["collection"])
    probe.query_points(collection_name=pre["collection"], using="dense", limit=10)
    if probe.calls != [{"using": "dense", "limit": 10, "hits": []}]:
        raise AssertionError("query recorder selfcheck failed")
    print(json.dumps({"selfcheck": "passed", "versions": [pre["version"], post["version"]],
                      "collections": [pre["collection"], post["collection"]],
                      "queries": list(QUERIES), "model_loaded": False}))
    return pre, post


def run():
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise EnvironmentError("launch with PYTHONHASHSEED=0 for reproducible fusion ties")
    if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("TRANSFORMERS_OFFLINE") != "1":
        raise EnvironmentError("offline model flags must both be 1")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
        raise EnvironmentError("CUDA_VISIBLE_DEVICES=-1 required")
    pre, post = selfcheck()
    from qdrant_client import QdrantClient
    qdrant = QdrantClient(url=QDRANT_URL, timeout=120)
    try:
        for item in (pre, post):
            observed = _point_digest(qdrant, item["collection"])
            if observed != item["qdrant_points"]:
                raise ValueError(f"{item['label']} Qdrant points changed: {observed}")
        import torch
        torch.set_num_threads(4)
        from FlagEmbedding import BGEM3FlagModel
        from core.config import EMBEDDING_MODEL
        if EMBEDDING_MODEL != pre["manifest"]["embedding_model"]:
            raise ValueError("local model path/config differs from candidate manifest")
        model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False, devices="cpu")
        loaded = {}
        try:
            for item in (pre, post):
                loaded[item["label"]] = load_reader(item)
            rows = []
            for question in QUERIES:
                encoding = encode_query(model, question)  # shared by the pair
                pair = {}
                for item in (pre, post):
                    graph, store = loaded[item["label"]]
                    recorder = ReadOnlyQueries(qdrant, item["collection"])
                    results = hybrid_search(question, 3, qdrant=recorder, embed_model=model,
                                            colbert_store=store, collection_name=item["collection"],
                                            query_encoding=encoding, graph=graph)
                    if [call["using"] for call in recorder.calls] != ["dense", "sparse"]:
                        raise ValueError("canonical hybrid search did not run both Qdrant branches")
                    pair[item["label"]] = {"candidates": recorder.calls, "ranking": results}
                before, after = pair["pre"], pair["post"]
                pair["comparison"] = {
                    "dense_candidate_ids_identical": [h["point_id"] for h in before["candidates"][0]["hits"]] == [h["point_id"] for h in after["candidates"][0]["hits"]],
                    "sparse_candidate_ids_identical": [h["point_id"] for h in before["candidates"][1]["hits"]] == [h["point_id"] for h in after["candidates"][1]["hits"]],
                    "dense_candidate_hits_exact": before["candidates"][0]["hits"] == after["candidates"][0]["hits"],
                    "sparse_candidate_hits_exact": before["candidates"][1]["hits"] == after["candidates"][1]["hits"],
                    "final_ids_identical": [r["chunk_id"] for r in before["ranking"]] == [r["chunk_id"] for r in after["ranking"]],
                    "final_ranking_exact": before["ranking"] == after["ranking"],
                }
                rows.append({"question": question, **pair})
            output = {"label": "paired complete retrieval; one shared real query encoding per question",
                      "python_hash_seed": "0", "model": EMBEDDING_MODEL, "top_k": 3,
                      "qdrant_url": QDRANT_URL,
                      "candidates": {item["label"]: {"version": item["version"],
                                                        "collection": item["collection"],
                                                        "point_digest": item["qdrant_points"]} for item in (pre, post)},
                      "queries": rows}
            OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"output": str(OUTPUT), "queries": len(rows),
                              "final_ids_identical": [r["comparison"]["final_ids_identical"] for r in rows]}))
        finally:
            for graph, store in loaded.values():
                if isinstance(store, ColbertStore):
                    store.close()
    finally:
        qdrant.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selfcheck", action="store_true", help="hash/contract guards without model or Qdrant")
    mode.add_argument("--run", action="store_true", help="real paired retrieval, offline CPU model")
    args = parser.parse_args()
    selfcheck() if args.selfcheck else run()

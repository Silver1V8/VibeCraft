"""Isolated F5 full-candidate measurement; never promotes or runs an eval gate."""
import argparse
import inspect
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
SCRIPTS = HERE.parents[4] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import bench_delta as delta


def fail(message):
    raise ValueError(message)


def valid_collection(value):
    return isinstance(value, str) and value.startswith("sidecar_0628_fullmemory_") and value.replace("_", "").isalnum()


def save(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    temp.replace(path)


def paths(checkout_arg, output_arg):
    result = delta.validate_paths(checkout_arg, output_arg)
    if not valid_collection(result["collection"]):
        fail("collection must use sidecar_0628_fullmemory_ prefix")
    if any(result["database"].iterdir()):
        fail("candidate database must be empty")
    return result


def candidate_integrity(paths, qdrant, version):
    from core.artifacts import artifact_dir, artifact_hashes, manifest_path
    manifest = json.loads(manifest_path(version).read_text(encoding="utf-8"))
    candidate_dir = artifact_dir(version)
    npy = (candidate_dir / "colbert" / "index.json").is_file()
    npz = (candidate_dir / "colbert.npz").is_file()
    if npy == npz:
        fail("candidate must contain exactly one ColBERT layout")
    supports_deep = "deep" in inspect.signature(artifact_hashes).parameters
    if npy and not supports_deep:
        fail("NPY candidate requires deep artifact hash support")
    hashes = artifact_hashes(version, deep=True) if supports_deep else artifact_hashes(version)
    points = delta._point_digest(qdrant, manifest["qdrant_collection"])
    expected = manifest.get("artifact_hashes")
    report = {"manifest": manifest, "artifact_hashes": hashes, "qdrant_points": points,
              "colbert_layout": "npy" if npy else "npz",
              "ok": expected == hashes and points["count"] == manifest.get("documents")}
    if not report["ok"]:
        fail("candidate manifest, artifacts, or Qdrant points disagree")
    return report


def run(paths):
    payload = {"status": "running", "parameters": {"promote": False, "eval_gate": False,
               "collection": paths["collection"], "qdrant_url": delta.QDRANT_URL,
               "measurement": "full candidate build only; no publish/readiness/crossover"},
               "resources": {"materialized": None,
               "required_wrapper": "bench_process.py must wrap this process for peak RSS and I/O"}}
    payload["pid"] = os.getpid()
    qdrant = None
    old_env = {}
    try:
        delta._qdrant_preflight(paths["collection"])
        payload["pre_build_publication"] = {"current_absent": not (paths["database"] / "CURRENT").exists()}
        if not payload["pre_build_publication"]["current_absent"]:
            fail("candidate database already has CURRENT")
        paths["output"].mkdir()
        save(paths["output"] / "result.json", payload)
        payload["corpus"] = {"docs": delta._fingerprint(sorted(p for p in paths["docs"].rglob("*") if p.is_file())),
                             "code": delta._fingerprint(sorted(p for p in paths["code"].rglob("*") if p.is_file()))}
        config = paths["rag"] / "rag_config.yaml"
        payload["config"] = {"path": str(config), "sha256": delta._sha(config.read_bytes())}
        env = {"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "CUDA_VISIBLE_DEVICES": "-1",
               "HF_HUB_OFFLINE": "1", "QDRANT_URL": delta.QDRANT_URL}
        old_env = {key: os.environ.get(key) for key in env}; os.environ.update(env)
        sys.path.insert(0, str(paths["rag"]))
        from core import indexing
        from core.writer_lock import writer_lock
        from qdrant_client import QdrantClient
        if not Path(indexing.__file__).resolve().is_relative_to(paths["rag"].resolve()):
            fail("core.indexing did not load from dedicated checkout")
        qdrant = QdrantClient(url=delta.QDRANT_URL, timeout=300)
        collector, events = {}, []
        payload["build_started_monotonic"] = time.monotonic()
        started = time.perf_counter()
        with writer_lock(timeout_seconds=60):
            version = indexing.build_graph_and_index(qdrant=qdrant, promote=False,
                                                     collector=collector, emit=events.append)
        elapsed = time.perf_counter() - started
        payload["build_ended_monotonic"] = time.monotonic()
        if not version:
            fail("candidate build returned no version")
        aliases = [item.alias_name for item in qdrant.get_aliases().aliases]
        payload["post_build_publication"] = {"current_absent": not (paths["database"] / "CURRENT").exists(),
                                               "base_alias_absent": paths["collection"] not in aliases}
        if not all(payload["post_build_publication"].values()):
            fail("candidate build published CURRENT or base alias")
        phases = collector.get("phase_timings_seconds") or {}
        if phases.get("eval_gate", 0) != 0 or phases.get("promote", 0) != 0:
            fail("candidate unexpectedly ran eval gate or promotion")
        payload.update(version=version, elapsed_seconds=elapsed, collector=collector,
                       writer_emissions=events, candidate=candidate_integrity(paths, qdrant, version),
                       source={"indexing_file": str(Path(indexing.__file__).resolve())},
                       gate_promotion_seconds={"eval_gate": phases.get("eval_gate", 0), "promote": phases.get("promote", 0)})
        payload["status"] = "completed"
        return 0
    except Exception as exc:
        payload.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        return 1
    finally:
        if qdrant is not None:
            qdrant.close()
        for key, value in old_env.items():
            os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)
        if paths["output"].exists():
            save(paths["output"] / "result.json", payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout"); parser.add_argument("--output-dir")
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    if args.selfcheck:
        if args.checkout or args.output_dir:
            fail("--selfcheck takes no paths")
        assert valid_collection("sidecar_0628_fullmemory_pre")
        assert not valid_collection("sidecar_0628_docs_n100_pre")
        assert not valid_collection("sidecar_0628_fullmemory_bad-name")
        print("pure guard selfcheck passed")
        return
    if not args.checkout or not args.output_dir:
        fail("--checkout and --output-dir are required")
    raise SystemExit(run(paths(args.checkout, args.output_dir)))


if __name__ == "__main__":
    main()

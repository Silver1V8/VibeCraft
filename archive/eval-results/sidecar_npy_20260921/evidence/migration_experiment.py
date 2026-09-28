"""F5-06 local historical NPZ→NPY migration; run only on a PM-prepared sandbox."""
import argparse, hashlib, json, os, shutil, sys
from pathlib import Path

HERE=Path(__file__).resolve(); RESULTS=HERE.parents[2]; SCRIPTS=HERE.parents[4]/"scripts"
sys.path.insert(0,str(SCRIPTS)); import bench_delta as delta
HIST=RESULTS/"sidecar_20260915/sandbox/historical-artifacts/v20260911T155042"
CANDIDATES=RESULTS/"sidecar_readers_20260921/evidence/historical-candidates.json"
FILES=frozenset(("chunks.json","code.json","code.npz","colbert.npz","dense.npz","graph.json","index_manifest.json"))
EXPECTED_CHUNKS=257; EXPECTED_TOKENS=112429

def fail(x): raise ValueError(x)
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(p,x): p.write_text(json.dumps(x,indent=2)+"\n",encoding="utf-8")
def valid_collection(value): return isinstance(value,str) and value.startswith("sidecar_0628_migration_history")
def validate_names(names):
    if set(names)!=FILES: fail("historical artifact set is not exactly seven files")
def paths(checkout,output):
    x=delta.validate_paths(checkout,output)
    if not valid_collection(x["collection"]): fail("migration collection prefix required")
    return x
def source_files():
    delta._safe(HIST, RESULTS)
    validate_names(p.name for p in HIST.iterdir())
    rows={}
    for path in HIST.iterdir():
        if path.is_symlink() or not path.is_file(): fail("historical artifact is linked or not regular")
        rows[path.name]={"sha256":sha(path),"bytes":path.stat().st_size}
    return rows
def replay(store,payload,retrieval):
    ids=payload["ids"]; query=__import__("numpy").asarray(payload["query"],dtype="float32")
    return retrieval.rank_sections_by_relevance(ids,colbert_store=store,colbert_query=query,min_score=-1e9)
def run(x):
    out={"status":"running","scope":"local artifacts only; historical manifest collection is not contacted"}
    try:
        if not HIST.is_dir() or not CANDIDATES.is_file(): fail("historical inputs missing")
        if any(x["database"].iterdir()): fail("dedicated database must be empty")
        x["output"].mkdir(); save(x["output"]/'result.json',out)
        sys.path.insert(0,str(x["rag"])); from core import artifacts,retrieval
        from core.writer_lock import writer_lock
        if not Path(artifacts.__file__).resolve().is_relative_to(x["rag"].resolve()): fail("artifacts not loaded from checkout")
        source_before=source_files(); manifest=json.loads((HIST/'index_manifest.json').read_text()); version=HIST.name
        target=x["database"]/'versions'/version; target.parent.mkdir(parents=True)
        if target.exists(): fail("historical target already exists")
        target.mkdir()
        for name in FILES: shutil.copy2(HIST/name,target/name)
        source_after=source_files(); copied={name:{"sha256":sha(target/name),"bytes":(target/name).stat().st_size} for name in FILES}
        if source_before!=source_after or copied!=source_before: fail("source/copy hashes changed")
        (x["database"]/'CURRENT').write_text(version+'\n',encoding='utf-8')
        if artifacts.artifact_hashes(version,deep=True)!=manifest.get("artifact_hashes"): fail("source manifest hashes differ")
        before=artifacts.load_artifacts(required=("colbert",)); payload=json.loads(CANDIDATES.read_text())
        out["replay_provenance"]={"path":str(CANDIDATES),"sha256":sha(CANDIDATES)}
        out["npz_rank"]=replay(before.colbert_store,payload,retrieval)
        if out["npz_rank"][-1] != ("missing",None): fail("NPZ missing replay differs")
        with writer_lock(timeout_seconds=60): candidate=artifacts.migrate_colbert_npy()
        candidate=candidate or artifacts.current_version()
        if candidate==version or artifacts.current_version()!=candidate: fail("migration did not publish candidate CURRENT")
        cdir=artifacts.version_dir(candidate); candidate_manifest=json.loads(artifacts.manifest_path(candidate).read_text())
        if (cdir/'colbert.npz').exists() or not (cdir/'colbert'/'index.json').is_file() or artifacts.artifact_hashes(candidate,deep=True)!=candidate_manifest.get("artifact_hashes"): fail("candidate NPY layout/hash invalid")
        after=artifacts.load_artifacts(required=("colbert",)); out["npy_rank"]=replay(after.colbert_store,payload,retrieval)
        if out["npy_rank"]!=out["npz_rank"]: fail("rank replay differs")
        if out["npy_rank"][-1] != ("missing",None): fail("NPY missing replay differs")
        import numpy as np
        checked=tokens=0
        with np.load(target/'colbert.npz',allow_pickle=False) as data:
            keys=[str(k) for k in data['keys']]
            for i,key in enumerate(keys):
                array=data[f'v{i}']
                if not np.array_equal(array,after.colbert_store[key]): fail(f"array differs: {key}")
                checked+=1; tokens+=int(array.shape[0])
        if checked!=EXPECTED_CHUNKS or checked!=manifest.get("documents") or tokens!=EXPECTED_TOKENS: fail("historical chunk/token count differs")
        out["candidate_verification"]={"current":artifacts.current_version(),"layout":"npy","arrays_exact":checked,"colbert_token_rows":tokens,"artifact_hashes":artifacts.artifact_hashes(candidate,deep=True)}
        close=getattr(after.colbert_store,"close",None)
        if close: close()
        with writer_lock(timeout_seconds=60): rolled=artifacts.rollback_version(version)
        restored=artifacts.load_artifacts(required=("colbert",)); out["rollback_rank"]=replay(restored.colbert_store,payload,retrieval)
        if rolled!=version or artifacts.current_version()!=version or out["rollback_rank"]!=out["npz_rank"] or out["rollback_rank"][-1] != ("missing",None): fail("rollback replay differs")
        source_after=source_files()
        if source_before!=source_after: fail("historical source changed during validation")
        out.update(status="completed",source_files={"before":source_before,"after":source_after,"copied":copied},baseline=version,candidate=candidate,current=artifacts.current_version())
        return 0
    except Exception as e: out.update(status="failed",error=f"{type(e).__name__}: {e}"); return 1
    finally:
        if x["output"].exists(): save(x["output"]/'result.json',out)
def main():
 p=argparse.ArgumentParser();p.add_argument('--checkout');p.add_argument('--output-dir');p.add_argument('--selfcheck',action='store_true');a=p.parse_args()
 if a.selfcheck:
  if a.checkout or a.output_dir: fail("selfcheck takes no paths")
  assert valid_collection("sidecar_0628_migration_history") and not valid_collection("sidecar_0628_docs")
  validate_names(FILES)
  try: validate_names((*FILES,"extra"))
  except ValueError: pass
  else: raise AssertionError("extra historical file accepted")
  print("pure guard selfcheck passed");return
 if not a.checkout or not a.output_dir: fail("checkout and output required")
 raise SystemExit(run(paths(a.checkout,a.output_dir)))
if __name__=='__main__':main()

# F6 retention experiment driver — prepared

`retention_experiment.py` is an evidence-only driver. It requires a new `rag/eval/results/<run>/sandbox/experiment`, a distinct frozen copy under the same sandbox, a new sibling output directory, and a dedicated `sidecar_0628_retention_*` collection. It verifies the copied dedicated configuration and exact RAG source hashes before the run. A frozen tree or source mismatch, or an experiment source change, invalidates the run; all values are recorded in `result.json`.

The driver bootstraps a small docs N=10 baseline, sets `VIBECRAFT_INDEX_KEEP=3`, then performs five genuine k=1 mutations on distinct files without restoring source, database, or Qdrant between jobs. Every step validates completed/reloaded/current job token, counts, integrity, current version, manifest, artifact hashes, Qdrant digest, versions, and `disk_inventory` logical/physical values. The existing HTTP reader runs throughout; job journal and raw reader events are retained in `result.json`. External `bench_process.py` sampling must wrap the run for process RSS/I/O raw evidence.

The driver starts a child from the frozen `rag/` copy after the baseline. It loads that baseline through `load_artifacts`, holds an F5 `ColbertStore` lease, reports `READY` with a fingerprint of its first vector, and checks that fingerprint after every mutation. The driver requires the baseline to remain on disk after it falls outside `keep=3`; after explicit `CLOSE`, it calls retention and requires that version to be removed. This is a lifecycle check of snapshot storage, not a full retrieval benchmark. The ordinary HTTP reader separately records request contention.

The driver does not test rollback of an in-place shared Qdrant collection; that is a separate limit. It preserves the sandbox after completion for inventory and independent review.

Before any real run, execute only the pure guard check:

```powershell
$env:PYTHONUTF8 = '1'
python -B rag/eval/results/sidecar_retention_20260921/evidence/retention_experiment.py --selfcheck
```

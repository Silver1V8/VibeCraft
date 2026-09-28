# F5-04 full-candidate experiment — prepared

`full_candidate_experiment.py` measures one isolated full `build_graph_and_index(promote=False)` from a PM-prepared copy. It requires an empty dedicated database and a fresh `sidecar_0628_fullmemory_*` collection on Qdrant port 16333. The driver refuses reused collections, loads `core.indexing` only from the dedicated checkout, holds the writer lock, and never calls the eval gate, promotion, readiness, or a simulated noop.

The output records the supplied corpus fingerprints, dedicated config hash, candidate version, elapsed duration, collector timing/counts, writer emissions, manifest, artifact hashes, candidate ColBERT layout, and the candidate collection point digest. It supports the historical NPZ implementation and F5 NPY implementation; when `artifact_hashes(deep=...)` exists, it re-reads NPY bytes. Counts are recorded as returned; the driver does not assume a fixed document, chunk, or token total. It is not a crossover or capacity measurement. Run it under `bench_process.py` to collect process peak memory and I/O; the driver records those fields as unavailable rather than inventing a value.

Preparation only checks the command shape:

```powershell
$env:PYTHONUTF8 = '1'
python -B rag/eval/results/sidecar_npy_20260921/evidence/full_candidate_experiment.py --selfcheck
```

For a reviewed real run, wrap the command in `rag/scripts/bench_process.py`, pass absolute paths for the PM-created `sandbox/experiment` checkout and new sibling output directory, and retain `result.json` plus the external sampler evidence.

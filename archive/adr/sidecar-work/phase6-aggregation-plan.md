# F6 aggregation plan (offline)

When all nine NPY families are completed, reuse `compare_delta.py` with the nine F3 `result.json` files as `--pre` and the nine NPY files as `--post`. Its existing validation must remain intact: exact 3×3 cells, five repeats, completed/reloaded jobs, restored baselines, identical corpus bytes, baseline Qdrant point digest, counts, and run parameters except the dedicated collection.

The current Markdown heading says “F3 pre/post delta comparison”. Make that heading generic before the F3-versus-NPY run, without changing any acceptance check or synthetic selfcheck. The comparison table already supplies median/min/max `T=job.snapshot_ready_duration_seconds` and paired `T(k)-T(0)` values. It must continue to describe paired delta as more than embedding time and avoid p95, capacity, budget, and crossover claims.

For resource rows, reuse `summarize_resources.summarize(result_path)`: it requires a completed sampler and aligns raw process samples to each job’s recorded interval. `colbert_io_bytes` should be read only when the completed raw job result exposes a finite value; preserve `null` and its reason when absent. Do not substitute process I/O counters: those are sampled process counters, not ColBERT I/O. Keep sampled memory maxima as lower bounds and Qdrant separate.

Retention is a separate local lifecycle table from `retention_experiment.py`: per step report current version, surviving versions, manifest/hash evidence, and `disk_inventory` logical bytes plus deduplicated physical allocation. Its physical field stays null when allocation is unavailable; it is not summed with RSS and has no capacity interpretation.

No curve, aggregate CSV, or measured conclusion is produced until all 18 accepted inputs exist.

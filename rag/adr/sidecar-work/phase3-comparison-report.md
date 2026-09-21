# F3 pre/post comparison — prepared

`compare_delta.py` accepts exactly nine explicit pre inputs and nine explicit post inputs. It rejects smoke, synthetic, incomplete, failed, invalid, un-restored, coalesced, non-standard, or non-five-repeat families.

For each matched N/mode/k it proves identical baseline corpus relative paths, SHA-256 and bytes, plus the complete Qdrant baseline point count/digest; identical N/mode/k and document/code/chunk/token count results; valid no-op/reload/current token. Missing collection parameters or any `result.parameters` difference beyond the dedicated collection name fails the comparison. This is not a YAML configuration-file comparison; the PM records normalized YAML-file evidence separately.

Exports are stdlib `comparison.csv`, `comparison.json`, and `comparison.md`. They contain T medians/min/max and change, separately paired T-minus-noop, timing-breakdown medians, sampled memory/I/O medians with sampler limits, and contention query metrics by endpoint. Five repeats do not support p95; no capacity budget or crossover is inferred. Missing resource samples remain null, never zero.

Resource summaries are recalculated from the existing raw sampler through `summarize_resources.summarize`, which rejects nonzero process exit or sampler errors. The comparator also checks raw source, parameters, server PID, and exact `(k, repeat)` alignment; absent raw sampler input remains null, while failed or partial sampler evidence is rejected.

`T(k)-T(0)` is a paired delta, not “embedding only.” A fast F3 no-op can avoid model load, so a larger paired delta alone does not establish a worse absolute delta duration. Query data describes the HTTP observation window: the reader starts around the request and can end after the recorded HTTP end, so individual query entries do not prove writer overlap. Resource maxima are sampled lower bounds.

Run only after all nine post-F3 families complete:

```powershell
$env:PYTHONUTF8 = '1'
python -B rag/eval/results/sidecar_20260915/evidence/compare_delta.py --pre <nine pre result.json paths> --post <nine post result.json paths> --output <new directory>
```

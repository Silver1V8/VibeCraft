# F2 summary aggregator — prepared

`rag/eval/results/sidecar_20260915/evidence/summarize_delta.py` accepts exactly nine completed `result.json` inputs: N=10/30/100 for `docs`, `code`, and `mixed`. It refuses smoke runs, failed runs, invalid samples, missing verified restore, non-standard k sets, and any cardinality other than five paired repeats per k.

It exports `summary.csv`, `summary.md`, and a static `summary.svg`. T is `job.snapshot_ready_duration_seconds`; `elapsed_seconds` is retained separately as HTTP elapsed. The table reports median/min/max T and paired `T(N,k)-T(N,0)` median/min/max for matching repeats. The SVG reports T with min/max error bars: one panel per mode, N=10/30/100 curves, and explicit k=0/1/10/100 labels.

The nine real F2 families have now completed (150 valid restored samples); outputs are in `evidence/phase2-summary`. PM rendered the same ReportLab drawing to PDF and inspected its PNG rasterization. The exclusive `sandbox/summary-selfcheck` fixture is marked `synthetic_fixture`; the ordinary command rejects it, while `--selfcheck` validates the importer and export format. Synthetic corpus and uncontrolled OS cache are declared in the outputs. It makes no p95, capacity threshold, or crossover claim.

Run after the nine real families finish:

```powershell
$env:PYTHONUTF8 = '1'
& 'C:/Users/Silve/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -B rag/eval/results/sidecar_20260915/evidence/summarize_delta.py --inputs <nine result.json paths> --output <new output directory>
```

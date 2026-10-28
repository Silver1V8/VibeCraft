# Evidence pesanti rimosse — `sidecar_npy_20260921`

I file sotto sono stati tolti dal tip di `main` il 2026-10-28 (R6) per
alleggerire checkout e clone sparse. Restano nella history git: recuperali con

```bash
git checkout 66954f9 -- archive/eval-results/<path>
# oppure, per un solo blob:
git show 66954f9:archive/eval-results/<path> > <path>
```

`66954f9` e' il tip di `main` prima di R6 (merge del PR quick-wins #25). Per un
clone senza scaricare queste evidenze resta valida la ricetta `sparse-checkout`
in [README.md](../../../README.md).

| Path relativo a `archive/eval-results/` | KiB |
|---|---:|
| `sidecar_npy_20260921/evidence/batching-study.json` | 120.0 |
| `sidecar_npy_20260921/evidence/phase6-comparison/comparison.json` | 100.2 |
| `sidecar_npy_20260921/evidence/npy-delta-summary.json` | 94.9 |
| `sidecar_npy_20260921/evidence/full-retrieval-parity.json` | 72.4 |
| `sidecar_npy_20260921/evidence/full-numeric-parity.json` | 26.6 |
| `sidecar_npy_20260921/evidence/batching-study.stderr.log` | 16.0 |
| `sidecar_npy_20260921/evidence/qdrant-native-f6-container.json` | 8.3 |
| `sidecar_npy_20260921/evidence/encoding_batch_parity.json` | 6.4 |
| `sidecar_npy_20260921/evidence/phase6-prepared-environment.json` | 6.3 |
| `sidecar_npy_20260921/evidence/phase6-input-verification.json` | 2.8 |
| `sidecar_npy_20260921/evidence/full-comparison.json` | 1.5 |
| `sidecar_npy_20260921/evidence/full-retrieval.stderr.log` | 1.1 |
| `sidecar_npy_20260921/evidence/progress.json` | 0.7 |
| `sidecar_npy_20260921/evidence/batching-study.stdout.log` | 0.6 |
| `sidecar_npy_20260921/evidence/full-retrieval.stdout.log` | 0.5 |
| `sidecar_npy_20260921/evidence/qdrant-native-f6-final-state.json` | 0.2 |
| `sidecar_npy_20260921/evidence/batching-study-input-after.json` | 0.2 |
| `sidecar_npy_20260921/evidence/encoding_batch_parity.stderr.log` | 0.1 |
| `sidecar_npy_20260921/evidence/encoding_batch_parity.stdout.log` | 0.1 |

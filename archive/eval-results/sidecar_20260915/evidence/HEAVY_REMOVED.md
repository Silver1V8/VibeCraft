# Evidence pesanti rimosse — `sidecar_20260915`

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
| `sidecar_20260915/evidence/calibration-20260921-process.jsonl` | 430.5 |
| `sidecar_20260915/evidence/calibration-20260921-r2-process.jsonl` | 422.2 |
| `sidecar_20260915/evidence/phase3-comparison/comparison.json` | 100.1 |
| `sidecar_20260915/evidence/calibration-corpus-config.zip` | 20.7 |
| `sidecar_20260915/evidence/calibration-20260921-r2/phase1d-result.json` | 15.1 |
| `sidecar_20260915/evidence/calibration-20260921/phase1d-result.json` | 14.3 |
| `sidecar_20260915/evidence/calibration-20260921-r2-process.stderr.log` | 6.8 |
| `sidecar_20260915/evidence/phase3-config-comparison.json` | 6.3 |
| `sidecar_20260915/evidence/calibration-20260921-process.stderr.log` | 5.9 |
| `sidecar_20260915/evidence/phase3-prepared-environment.json` | 5.2 |
| `sidecar_20260915/evidence/phase2-prepared-environment.json` | 5.1 |
| `sidecar_20260915/evidence/calibration-20260921-partial-summary.json` | 5.1 |
| `sidecar_20260915/evidence/calibration-20260921-r2-summary.json` | 4.9 |
| `sidecar_20260915/evidence/phase3-code-vector-parity.json` | 4.2 |
| `sidecar_20260915/evidence/qdrant-bind-snapshot-failure.log` | 3.2 |
| `sidecar_20260915/evidence/historical-artifacts-provenance.json` | 2.7 |
| `sidecar_20260915/evidence/environment-20260921.json` | 2.1 |
| `sidecar_20260915/evidence/calibration-20260921-r2-process.json` | 1.6 |
| `sidecar_20260915/evidence/calibration-20260921-process.json` | 1.6 |
| `sidecar_20260915/evidence/qdrant-native-f3-snapshot-probe.json` | 1.4 |
| `sidecar_20260915/evidence/series-post-progress.json` | 1.4 |
| `sidecar_20260915/evidence/series-progress.json` | 1.4 |
| `sidecar_20260915/evidence/qdrant-native-snapshot-probe.json` | 1.3 |
| `sidecar_20260915/evidence/calibration-20260921/phase1d-bootstrap.json` | 1.3 |
| `sidecar_20260915/evidence/calibration-20260921-r2/phase1d-bootstrap.json` | 1.3 |
| `sidecar_20260915/evidence/environment.json` | 1.1 |
| `sidecar_20260915/evidence/qdrant-preflight-20260921.json` | 0.5 |
| `sidecar_20260915/evidence/calibration-20260921-process.stdout.log` | 0.0 |
| `sidecar_20260915/evidence/calibration-20260921-r2-process.stdout.log` | 0.0 |

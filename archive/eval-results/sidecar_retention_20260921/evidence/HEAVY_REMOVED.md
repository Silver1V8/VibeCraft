# Evidence pesanti rimosse — `sidecar_retention_20260921`

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
| `sidecar_retention_20260921/evidence/process.jsonl` | 674.4 |
| `sidecar_retention_20260921/evidence/result.json` | 384.2 |
| `sidecar_retention_20260921/evidence/process.stderr.log` | 28.8 |
| `sidecar_retention_20260921/evidence/retention-summary.json` | 10.8 |
| `sidecar_retention_20260921/evidence/process.json` | 1.7 |
| `sidecar_retention_20260921/evidence/bootstrap.json` | 1.6 |
| `sidecar_retention_20260921/evidence/windows-selfcheck-inventory.json` | 1.0 |
| `sidecar_retention_20260921/evidence/linux-selfcheck.json` | 0.8 |
| `sidecar_retention_20260921/evidence/prepared-environment.json` | 0.6 |
| `sidecar_retention_20260921/evidence/process.stdout.log` | 0.0 |

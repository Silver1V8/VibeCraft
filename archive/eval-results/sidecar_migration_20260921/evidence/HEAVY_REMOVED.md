# Evidence pesanti rimosse — `sidecar_migration_20260921`

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
| `sidecar_migration_20260921/evidence/prepared-environment.json` | 30.4 |
| `sidecar_migration_20260921/evidence/result.json` | 20.7 |
| `sidecar_migration_20260921/evidence/post-run-input-verification.json` | 0.1 |
| `sidecar_migration_20260921/evidence/migration.stderr.log` | 0.0 |
| `sidecar_migration_20260921/evidence/migration.stdout.log` | 0.0 |

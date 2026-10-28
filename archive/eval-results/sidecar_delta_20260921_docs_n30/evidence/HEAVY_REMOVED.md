# Evidence pesanti rimosse — `sidecar_delta_20260921_docs_n30`

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
| `sidecar_delta_20260921_docs_n30/evidence/process.jsonl` | 942.3 |
| `sidecar_delta_20260921_docs_n30/evidence/result.json` | 125.0 |
| `sidecar_delta_20260921_docs_n30/evidence/process.stderr.log` | 92.8 |
| `sidecar_delta_20260921_docs_n30/evidence/resources.json` | 13.3 |
| `sidecar_delta_20260921_docs_n30/evidence/bootstrap.json` | 1.8 |
| `sidecar_delta_20260921_docs_n30/evidence/process.json` | 1.6 |
| `sidecar_delta_20260921_docs_n30/evidence/process.stdout.log` | 0.0 |

# Evidence pesanti rimosse — `implementazione_migliorie_20260910`

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
| `implementazione_migliorie_20260910/evidence/out/verifica_s2.json` | 620.0 |
| `implementazione_migliorie_20260910/evidence/EVIDENCE_MANIFEST.json` | 11.7 |
| `implementazione_migliorie_20260910/evidence/out/esperimento/report.json` | 8.9 |
| `implementazione_migliorie_20260910/evidence/out/e2e_api.json` | 6.7 |

# Evidence pesanti rimosse — `libreoffice_20260910`

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
| `libreoffice_20260910/evidence/out_lo_2/risultati.json` | 42.7 |
| `libreoffice_20260910/evidence/out_lo_1/risultati.json` | 42.6 |
| `libreoffice_20260910/evidence/EVIDENCE_MANIFEST.json` | 33.2 |
| `libreoffice_20260910/evidence/out_base/risultati.json` | 18.7 |

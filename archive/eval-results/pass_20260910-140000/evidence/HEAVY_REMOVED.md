# Evidence pesanti rimosse — `pass_20260910-140000`

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
| `pass_20260910-140000/evidence/out/prova_v_k10.json` | 44.8 |
| `pass_20260910-140000/evidence/out/prova_cf_diag3.json` | 15.3 |
| `pass_20260910-140000/evidence/out/prova_k5_diag3.json` | 14.2 |
| `pass_20260910-140000/evidence/out/prova_u_diag3.json` | 13.8 |
| `pass_20260910-140000/evidence/out/prova_v_k5.json` | 11.1 |
| `pass_20260910-140000/evidence/out/soffitto.json` | 4.5 |
| `pass_20260910-140000/evidence/inventario_sha256.json` | 4.2 |
| `pass_20260910-140000/evidence/EVIDENCE_MANIFEST.json` | 3.8 |
| `pass_20260910-140000/evidence/calibrazione/riepilogo_varianti.json` | 2.8 |

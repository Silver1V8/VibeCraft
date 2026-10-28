# Evidence pesanti rimosse — `fix_attribuzione_20260909-183000`

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
| `fix_attribuzione_20260909-183000/evidence/out/eval_B_p3.json` | 453.1 |
| `fix_attribuzione_20260909-183000/evidence/out/eval_B_p2.json` | 451.1 |
| `fix_attribuzione_20260909-183000/evidence/out/eval_D_p2.json` | 450.8 |
| `fix_attribuzione_20260909-183000/evidence/out/eval_D_p1.json` | 450.7 |
| `fix_attribuzione_20260909-183000/evidence/out/eval_B_p1.json` | 449.9 |
| `fix_attribuzione_20260909-183000/evidence/out/eval_D_p3.json` | 449.9 |
| `fix_attribuzione_20260909-183000/evidence/out/eval_C_p3.json` | 436.0 |
| `fix_attribuzione_20260909-183000/evidence/out/eval_C_p2.json` | 434.6 |
| `fix_attribuzione_20260909-183000/evidence/out/eval_A_p3.json` | 433.7 |
| `fix_attribuzione_20260909-183000/evidence/out/eval_C_p1.json` | 433.4 |
| `fix_attribuzione_20260909-183000/evidence/out/eval_A_p2.json` | 431.8 |
| `fix_attribuzione_20260909-183000/evidence/out/eval_A_p1.json` | 431.8 |
| `fix_attribuzione_20260909-183000/evidence/out/confronto_finale.json` | 245.3 |
| `fix_attribuzione_20260909-183000/evidence/manifest/congelamento.json` | 25.9 |
| `fix_attribuzione_20260909-183000/evidence/EVIDENCE_MANIFEST.json` | 16.0 |
| `fix_attribuzione_20260909-183000/evidence/out/diagnostici_variante.json` | 13.6 |
| `fix_attribuzione_20260909-183000/evidence/out/diagnostici_variante_p3.json` | 13.6 |
| `fix_attribuzione_20260909-183000/evidence/out/diagnostici_variante_p2.json` | 13.4 |
| `fix_attribuzione_20260909-183000/evidence/out/diagnostici_originale_p3.json` | 12.6 |
| `fix_attribuzione_20260909-183000/evidence/out/diagnostici_originale_p2.json` | 12.3 |
| `fix_attribuzione_20260909-183000/evidence/inventario_sha256.json` | 12.3 |
| `fix_attribuzione_20260909-183000/evidence/out/diagnostici_originale.json` | 12.2 |
| `fix_attribuzione_20260909-183000/evidence/out/diagnostici_originale_v1_strumento_difettoso.json` | 11.1 |
| `fix_attribuzione_20260909-183000/evidence/out/prompt_D.json` | 3.8 |
| `fix_attribuzione_20260909-183000/evidence/out/prompt_C.json` | 3.8 |
| `fix_attribuzione_20260909-183000/evidence/out/prompt_B.json` | 3.7 |
| `fix_attribuzione_20260909-183000/evidence/out/prompt_A.json` | 3.7 |

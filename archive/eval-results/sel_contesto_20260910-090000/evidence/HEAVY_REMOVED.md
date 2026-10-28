# Evidence pesanti rimosse — `sel_contesto_20260910-090000`

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
| `sel_contesto_20260910-090000/evidence/out/sweep_golden_0.0.json` | 2236.6 |
| `sel_contesto_20260910-090000/evidence/out/comp_A_golden.json` | 2236.5 |
| `sel_contesto_20260910-090000/evidence/out/sweep_golden_0.30.json` | 2196.1 |
| `sel_contesto_20260910-090000/evidence/out/sweep_golden_0.35.json` | 2101.7 |
| `sel_contesto_20260910-090000/evidence/out/sweep_golden_0.40.json` | 1972.8 |
| `sel_contesto_20260910-090000/evidence/out/sweep_golden_0.45.json` | 1875.8 |
| `sel_contesto_20260910-090000/evidence/out/comp_A_golden_solosem.json` | 1815.9 |
| `sel_contesto_20260910-090000/evidence/out/sweep_multihop_0.0.json` | 339.4 |
| `sel_contesto_20260910-090000/evidence/out/comp_A_multihop.json` | 339.3 |
| `sel_contesto_20260910-090000/evidence/out/sweep_multihop_0.30.json` | 338.4 |
| `sel_contesto_20260910-090000/evidence/out/sweep_multihop_0.35.json` | 332.3 |
| `sel_contesto_20260910-090000/evidence/out/sweep_multihop_0.40.json` | 325.9 |
| `sel_contesto_20260910-090000/evidence/out/sweep_multihop_0.45.json` | 307.8 |
| `sel_contesto_20260910-090000/evidence/out/comp_A_multihop_solosem.json` | 295.2 |
| `sel_contesto_20260910-090000/evidence/holdout/comp_S2.json` | 291.4 |
| `sel_contesto_20260910-090000/evidence/holdout/comp_S0.json` | 291.3 |
| `sel_contesto_20260910-090000/evidence/out/sweep_pdf_0.0.json` | 282.8 |
| `sel_contesto_20260910-090000/evidence/out/comp_S3a_pdf.json` | 282.8 |
| `sel_contesto_20260910-090000/evidence/out/comp_S3b_pdf.json` | 282.8 |
| `sel_contesto_20260910-090000/evidence/out/comp_S2_off.json` | 282.7 |
| `sel_contesto_20260910-090000/evidence/out/composizione_A_attuale.json` | 282.7 |
| `sel_contesto_20260910-090000/evidence/out/comp_A_solografo.json` | 280.9 |
| `sel_contesto_20260910-090000/evidence/out/sweep_pdf_0.30.json` | 248.2 |
| `sel_contesto_20260910-090000/evidence/out/comp_S1_pdf.json` | 233.6 |
| `sel_contesto_20260910-090000/evidence/out/comp_S4_pdf.json` | 233.4 |
| `sel_contesto_20260910-090000/evidence/out/comp_S2_finale_pdf.json` | 233.4 |
| `sel_contesto_20260910-090000/evidence/out/sweep_pdf_0.35.json` | 233.4 |
| `sel_contesto_20260910-090000/evidence/out/sweep_pdf_0.40.json` | 227.4 |
| `sel_contesto_20260910-090000/evidence/out/sweep_pdf_0.45.json` | 220.0 |
| `sel_contesto_20260910-090000/evidence/out/comp_A_solosem.json` | 215.2 |
| `sel_contesto_20260910-090000/evidence/out/comp_k5_S0_pdf.json` | 212.5 |
| `sel_contesto_20260910-090000/evidence/out/comp_k5_S2_pdf.json` | 162.6 |
| `sel_contesto_20260910-090000/evidence/diagnosi/comp_aggressivo_pdf.json` | 86.7 |
| `sel_contesto_20260910-090000/evidence/holdout/gen_S0.json` | 29.4 |
| `sel_contesto_20260910-090000/evidence/out/gen_k5_S0_pdf.json` | 28.7 |
| `sel_contesto_20260910-090000/evidence/holdout/gen_S2.json` | 27.6 |
| `sel_contesto_20260910-090000/evidence/out/gen_S0_pdf.json` | 27.5 |
| `sel_contesto_20260910-090000/evidence/out/gen_k5_S2_pdf.json` | 26.9 |
| `sel_contesto_20260910-090000/evidence/manifest/congelamento.json` | 25.9 |
| `sel_contesto_20260910-090000/evidence/out/gen_S2_pdf.json` | 25.3 |
| `sel_contesto_20260910-090000/evidence/EVIDENCE_MANIFEST.json` | 23.1 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_S2_golden.json` | 21.1 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_S2fin_golden.json` | 21.1 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_S0_golden.json` | 21.1 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_S3a_golden.json` | 21.1 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_S3b_golden.json` | 21.1 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_S1_golden.json` | 21.1 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_k5_S0_golden.json` | 21.0 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_k5_S2_golden.json` | 21.0 |
| `sel_contesto_20260910-090000/evidence/inventario_sha256.json` | 14.7 |
| `sel_contesto_20260910-090000/evidence/diagnosi/ablazione_scala.json` | 5.5 |
| `sel_contesto_20260910-090000/evidence/diagnosi/gen_aggressivo.json` | 3.8 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_S2_multihop.json` | 3.8 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_S2fin_multihop.json` | 3.8 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_S0_multihop.json` | 3.8 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_S3a_multihop.json` | 3.8 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_S3b_multihop.json` | 3.8 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_S1_multihop.json` | 3.8 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_k5_S2_multihop.json` | 3.8 |
| `sel_contesto_20260910-090000/evidence/calibrazione/cop_k5_S0_multihop.json` | 3.8 |

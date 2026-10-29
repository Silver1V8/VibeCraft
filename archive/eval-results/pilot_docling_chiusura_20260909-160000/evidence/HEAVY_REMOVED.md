# Evidence pesanti rimosse — `pilot_docling_chiusura_20260909-160000`

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
| `pilot_docling_chiusura_20260909-160000/evidence/out/eval_candidate-variante_p2.json` | 450.1 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/eval_candidate_p3.json` | 449.7 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/eval_candidate_p2.json` | 449.5 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/eval_candidate-variante_p3.json` | 449.5 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/eval_candidate_p1.json` | 449.2 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/eval_candidate-variante_p1.json` | 449.2 |
| `pilot_docling_chiusura_20260909-160000/evidence/audit/indice_precedente_candidate/chunks.json` | 434.3 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/eval_baseline_p2.json` | 433.0 |
| `pilot_docling_chiusura_20260909-160000/evidence/audit/indice_precedente_baseline/chunks.json` | 433.0 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/eval_baseline-variante_p3.json` | 432.6 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/eval_baseline-variante_p1.json` | 432.5 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/eval_baseline_p1.json` | 432.2 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/eval_baseline_p3.json` | 431.1 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/eval_baseline-variante_p2.json` | 430.7 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/attribuzione_baseline.json` | 297.7 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/attribuzione_candidate-variante.json` | 297.6 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/attribuzione_candidate.json` | 297.1 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/attribuzione_baseline-variante.json` | 294.0 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/confronto_finale.json` | 252.8 |
| `pilot_docling_chiusura_20260909-160000/evidence/audit/indice_precedente_candidate/index_manifest.json` | 34.3 |
| `pilot_docling_chiusura_20260909-160000/evidence/audit/indice_precedente_baseline/index_manifest.json` | 34.3 |
| `pilot_docling_chiusura_20260909-160000/evidence/audit/audit_finale_20260909-110000.json` | 28.0 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/attribuzione_candidate-r2.json` | 24.8 |
| `pilot_docling_chiusura_20260909-160000/evidence/EVIDENCE_MANIFEST.json` | 22.6 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/attribuzione_candidate-r3.json` | 19.9 |
| `pilot_docling_chiusura_20260909-160000/evidence/inventario_sha256.json` | 13.3 |
| `pilot_docling_chiusura_20260909-160000/evidence/truth/verita_riferimento.json` | 8.3 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/sonda_baseline.json` | 3.6 |
| `pilot_docling_chiusura_20260909-160000/evidence/manifest/manifest.json` | 3.4 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/sonda_candidate.json` | 3.3 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/verifica_riuso.json` | 2.1 |
| `pilot_docling_chiusura_20260909-160000/evidence/diff/indice_candidate.json` | 1.0 |
| `pilot_docling_chiusura_20260909-160000/evidence/diff/indice_baseline.json` | 0.8 |
| `pilot_docling_chiusura_20260909-160000/evidence/out/suite.json` | 0.5 |

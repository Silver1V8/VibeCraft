# Evidence pesanti rimosse — `pilot_docling_finale_20260909-110000`

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
| `pilot_docling_finale_20260909-110000/evidence/out/run1/candidate_mockup.json` | 94.1 |
| `pilot_docling_finale_20260909-110000/evidence/out/run2/candidate_mockup.json` | 94.1 |
| `pilot_docling_finale_20260909-110000/evidence/out/run1/candidate_diagrammi.json` | 49.4 |
| `pilot_docling_finale_20260909-110000/evidence/out/run2/candidate_diagrammi.json` | 49.4 |
| `pilot_docling_finale_20260909-110000/evidence/out/eval_candidate.json` | 46.0 |
| `pilot_docling_finale_20260909-110000/evidence/out/eval_baseline.json` | 44.8 |
| `pilot_docling_finale_20260909-110000/evidence/EVIDENCE_MANIFEST.json` | 14.6 |
| `pilot_docling_finale_20260909-110000/evidence/inventario_sha256.json` | 8.6 |
| `pilot_docling_finale_20260909-110000/evidence/truth/verita_riferimento.json` | 8.3 |
| `pilot_docling_finale_20260909-110000/evidence/out/run1/run_report.json` | 7.0 |
| `pilot_docling_finale_20260909-110000/evidence/out/run2/run_report.json` | 7.0 |
| `pilot_docling_finale_20260909-110000/evidence/out/confronto_testo.json` | 5.8 |
| `pilot_docling_finale_20260909-110000/evidence/out/confronto_risposte.json` | 4.6 |
| `pilot_docling_finale_20260909-110000/evidence/manifest/manifest_input_e_catena.json` | 4.3 |
| `pilot_docling_finale_20260909-110000/evidence/out/confronto_celle.json` | 3.6 |
| `pilot_docling_finale_20260909-110000/evidence/out/confronto_domande.json` | 3.5 |
| `pilot_docling_finale_20260909-110000/evidence/out/verification.json` | 1.4 |

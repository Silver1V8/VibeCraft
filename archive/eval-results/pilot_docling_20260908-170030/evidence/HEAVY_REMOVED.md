# Evidence pesanti rimosse — `pilot_docling_20260908-170030`

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
| `pilot_docling_20260908-170030/evidence/EVIDENCE_MANIFEST.json` | 14.0 |
| `pilot_docling_20260908-170030/evidence/summary.json` | 11.9 |
| `pilot_docling_20260908-170030/evidence/out/multihop_20260908_171352.json` | 10.9 |
| `pilot_docling_20260908-170030/evidence/out/retrieval_pdf.json` | 8.3 |
| `pilot_docling_20260908-170030/evidence/truth/verita_riferimento.json` | 8.3 |
| `pilot_docling_20260908-170030/evidence/out/confronto_testo.json` | 6.5 |
| `pilot_docling_20260908-170030/evidence/out/granite_report.json` | 6.4 |
| `pilot_docling_20260908-170030/evidence/out/confronto_celle.json` | 3.6 |
| `pilot_docling_20260908-170030/evidence/out/confronto_celle_run2.json` | 3.6 |
| `pilot_docling_20260908-170030/evidence/out/confronto_domande.json` | 3.6 |
| `pilot_docling_20260908-170030/evidence/out/confronto_testo_disaggregato.json` | 2.2 |
| `pilot_docling_20260908-170030/evidence/out/granite_refine_report.json` | 2.0 |
| `pilot_docling_20260908-170030/evidence/out/baseline_report.json` | 1.9 |
| `pilot_docling_20260908-170030/evidence/out/novlm-run2/granite_report_run2.json` | 1.4 |

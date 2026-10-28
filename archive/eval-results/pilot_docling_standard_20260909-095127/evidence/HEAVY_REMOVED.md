# Evidence pesanti rimosse — `pilot_docling_standard_20260909-095127`

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
| `pilot_docling_standard_20260909-095127/evidence/run1/standard_mockup.json` | 95.0 |
| `pilot_docling_standard_20260909-095127/evidence/run2/standard_mockup.json` | 95.0 |
| `pilot_docling_standard_20260909-095127/evidence/run1/standard_diagrammi.json` | 52.5 |
| `pilot_docling_standard_20260909-095127/evidence/run2/standard_diagrammi.json` | 52.5 |
| `pilot_docling_standard_20260909-095127/evidence/EVIDENCE_MANIFEST.json` | 16.3 |
| `pilot_docling_standard_20260909-095127/evidence/artifact_inventory.json` | 14.8 |
| `pilot_docling_standard_20260909-095127/evidence/truth/verita_riferimento.json` | 8.3 |
| `pilot_docling_standard_20260909-095127/evidence/confronto_testo.json` | 5.9 |
| `pilot_docling_standard_20260909-095127/evidence/run2/run_report.json` | 5.2 |
| `pilot_docling_standard_20260909-095127/evidence/run1/run_report.json` | 5.0 |
| `pilot_docling_standard_20260909-095127/evidence/confronto_domande.json` | 3.6 |
| `pilot_docling_standard_20260909-095127/evidence/confronto_celle.json` | 3.6 |

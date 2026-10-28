# Evidence pesanti rimosse — `excel_diretto_20260911`

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
| `excel_diretto_20260911/evidence/oracolo_excel/SOLVSAMP.XLS.lo.xlsx.88bdfd19.excel.json` | 270.5 |
| `excel_diretto_20260911/evidence/oracolo_excel/SOLVSAMP.XLS.b7fefe55.excel.json` | 270.4 |
| `excel_diretto_20260911/evidence/classificazione_SOLVSAMP.json` | 105.1 |
| `excel_diretto_20260911/evidence/EVIDENCE_MANIFEST.json` | 30.8 |
| `excel_diretto_20260911/evidence/oracolo_excel/casi_excel.xlsx.7fa2a847.excel.json` | 20.4 |
| `excel_diretto_20260911/evidence/oracolo_excel/casi_excel.xls.8fc9f60b.excel.json` | 20.4 |
| `excel_diretto_20260911/evidence/oracolo_excel/registro_excel.xlsx.1fc40f0d.excel.json` | 9.7 |
| `excel_diretto_20260911/evidence/oracolo_excel/registro.xls.34afb1ad.excel.json` | 9.7 |
| `excel_diretto_20260911/evidence/oracolo_excel/registro.xlsx.588a3d14.excel.json` | 9.7 |
| `excel_diretto_20260911/evidence/oracolo_excel/legacy.xls.34afb1ad.excel.json` | 9.7 |
| `excel_diretto_20260911/evidence/host_a_banco_da_correggere/results.json` | 9.1 |
| `excel_diretto_20260911/evidence/host_a/results.json` | 8.6 |
| `excel_diretto_20260911/evidence/host_b/results.json` | 8.6 |
| `excel_diretto_20260911/evidence/container_2/results.json` | 8.0 |
| `excel_diretto_20260911/evidence/container_1/results.json` | 8.0 |
| `excel_diretto_20260911/evidence/protected.after.json` | 6.6 |
| `excel_diretto_20260911/evidence/protected.before.json` | 6.6 |
| `excel_diretto_20260911/evidence/oracolo_excel/registro.xlsx.e457f838.excel.json` | 6.1 |
| `excel_diretto_20260911/evidence/oracolo_excel/budget.xlsx.3d23d5d6.excel.json` | 4.7 |
| `excel_diretto_20260911/evidence/oracolo_excel/budget.xls.9bae8d49.excel.json` | 3.9 |
| `excel_diretto_20260911/evidence/oracolo_excel/rete.xlsx.56d2d1b3.excel.json` | 2.0 |
| `excel_diretto_20260911/evidence/oracolo_excel/PROTTPLN.XLS.c59c01b6.excel.json` | 1.5 |
| `excel_diretto_20260911/evidence/prestazioni.jsonl` | 1.5 |
| `excel_diretto_20260911/evidence/strict-gate-diretto.json` | 1.0 |

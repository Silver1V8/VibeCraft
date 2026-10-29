# Evidence pesanti rimosse — `excel_fidelity_20260910`

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
| `excel_fidelity_20260910/evidence/baseline1/results.json` | 47.7 |
| `excel_fidelity_20260910/evidence/baseline2/results.json` | 47.7 |
| `excel_fidelity_20260910/evidence/candidate2/results.json` | 38.7 |
| `excel_fidelity_20260910/evidence/candidate1/results.json` | 38.7 |
| `excel_fidelity_20260910/evidence/gap1/results.json` | 35.7 |
| `excel_fidelity_20260910/evidence/EVIDENCE_MANIFEST.json` | 21.3 |
| `excel_fidelity_20260910/evidence/protected.before.json` | 6.7 |
| `excel_fidelity_20260910/evidence/verification.json` | 3.8 |
| `excel_fidelity_20260910/evidence/candidate-code-sha256.json` | 1.0 |
| `excel_fidelity_20260910/evidence/strict-candidate.json` | 0.4 |
| `excel_fidelity_20260910/evidence/remote-ci.json` | 0.4 |
| `excel_fidelity_20260910/evidence/strict-baseline.json` | 0.2 |

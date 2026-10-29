# Evidence pesanti rimosse — `propose_ablation_20260914`

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
| `propose_ablation_20260914/evidence/responses/P10_provider.json` | 223.6 |
| `propose_ablation_20260914/evidence/responses/P01_provider.json` | 219.8 |
| `propose_ablation_20260914/evidence/responses/P07_provider.json` | 215.6 |
| `propose_ablation_20260914/evidence/responses/P05_provider.json` | 215.1 |
| `propose_ablation_20260914/evidence/responses/P09_provider.json` | 213.7 |
| `propose_ablation_20260914/evidence/responses/P02_provider.json` | 209.9 |
| `propose_ablation_20260914/evidence/responses/P12_provider.json` | 129.8 |
| `propose_ablation_20260914/evidence/responses/P06_provider.json` | 129.4 |
| `propose_ablation_20260914/evidence/responses/P08_provider.json` | 126.5 |
| `propose_ablation_20260914/evidence/responses/P11_provider.json` | 125.9 |
| `propose_ablation_20260914/evidence/responses/P04_provider.json` | 120.1 |
| `propose_ablation_20260914/evidence/responses/P03_provider.json` | 119.4 |
| `propose_ablation_20260914/evidence/AFTER_REVIEW/MEASUREMENTS.json` | 12.4 |
| `propose_ablation_20260914/evidence/manifest.json` | 4.6 |
| `propose_ablation_20260914/evidence/run_status.json` | 2.3 |
| `propose_ablation_20260914/evidence/AFTER_REVIEW/KEY.json` | 1.5 |
| `propose_ablation_20260914/evidence/runtime_observation.json` | 0.1 |

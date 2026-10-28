# Evidence pesanti rimosse — `propose_count_ablation_20260914`

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
| `propose_count_ablation_20260914/evidence/responses/la2_V3_r2_provider.json` | 233.6 |
| `propose_count_ablation_20260914/evidence/responses/la2_V3_r1_provider.json` | 233.3 |
| `propose_count_ablation_20260914/evidence/responses/la2_V3_r3_provider.json` | 231.2 |
| `propose_count_ablation_20260914/evidence/responses/la2_V2_r1_provider.json` | 229.8 |
| `propose_count_ablation_20260914/evidence/responses/la2_V1_r3_provider.json` | 226.2 |
| `propose_count_ablation_20260914/evidence/responses/la2_V1_r1_provider.json` | 224.3 |
| `propose_count_ablation_20260914/evidence/responses/la2_B0_r1_provider.json` | 223.3 |
| `propose_count_ablation_20260914/evidence/responses/la2_V2_r2_provider.json` | 220.3 |
| `propose_count_ablation_20260914/evidence/responses/la2_B0_r2_provider.json` | 217.7 |
| `propose_count_ablation_20260914/evidence/responses/la2_V1_r2_provider.json` | 217.5 |
| `propose_count_ablation_20260914/evidence/responses/la2_V2_r3_provider.json` | 217.2 |
| `propose_count_ablation_20260914/evidence/responses/la2_B0_r3_provider.json` | 215.9 |
| `propose_count_ablation_20260914/evidence/STRUCTURAL.json` | 154.7 |
| `propose_count_ablation_20260914/evidence/responses/fe3_V3_r3_provider.json` | 135.9 |
| `propose_count_ablation_20260914/evidence/responses/fe3_V3_r1_provider.json` | 135.6 |
| `propose_count_ablation_20260914/evidence/responses/fe3_V2_r2_provider.json` | 133.3 |
| `propose_count_ablation_20260914/evidence/responses/fe3_V3_r2_provider.json` | 131.6 |
| `propose_count_ablation_20260914/evidence/responses/fe3_B0_r3_provider.json` | 130.8 |
| `propose_count_ablation_20260914/evidence/responses/fe3_V2_r1_provider.json` | 130.4 |
| `propose_count_ablation_20260914/evidence/responses/fe3_V1_r2_provider.json` | 130.4 |
| `propose_count_ablation_20260914/evidence/responses/fe3_V1_r3_provider.json` | 130.3 |
| `propose_count_ablation_20260914/evidence/responses/fe3_V2_r3_provider.json` | 127.9 |
| `propose_count_ablation_20260914/evidence/responses/fe3_B0_r2_provider.json` | 123.8 |
| `propose_count_ablation_20260914/evidence/responses/fe3_B0_r1_provider.json` | 120.7 |
| `propose_count_ablation_20260914/evidence/responses/fe3_V1_r1_provider.json` | 120.6 |
| `propose_count_ablation_20260914/evidence/MAPPING.json` | 45.8 |
| `propose_count_ablation_20260914/evidence/manifest.json` | 6.2 |
| `propose_count_ablation_20260914/evidence/run_status.json` | 4.4 |
| `propose_count_ablation_20260914/evidence/VERIFICATION.json` | 0.6 |

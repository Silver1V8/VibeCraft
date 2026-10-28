# Evidence pesanti rimosse — `propose_inventory_ablation_20260914`

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
| `propose_inventory_ablation_20260914/evidence/responses/la2_V4_r2_provider.json` | 248.4 |
| `propose_inventory_ablation_20260914/evidence/responses/la2_V4_r3_provider.json` | 244.8 |
| `propose_inventory_ablation_20260914/evidence/responses/la2_V4_r1_provider.json` | 243.2 |
| `propose_inventory_ablation_20260914/evidence/STRUCTURAL.json` | 184.0 |
| `propose_inventory_ablation_20260914/evidence/responses/fe3_V4_r1_provider.json` | 156.7 |
| `propose_inventory_ablation_20260914/evidence/responses/fe3_V4_r2_provider.json` | 142.6 |
| `propose_inventory_ablation_20260914/evidence/responses/fe3_V4_r3_provider.json` | 141.1 |
| `propose_inventory_ablation_20260914/evidence/ANNOTATIONS.json` | 54.0 |
| `propose_inventory_ablation_20260914/evidence/manifest.json` | 4.5 |
| `propose_inventory_ablation_20260914/evidence/run_status.json` | 1.3 |
| `propose_inventory_ablation_20260914/evidence/VERIFICATION.json` | 0.6 |

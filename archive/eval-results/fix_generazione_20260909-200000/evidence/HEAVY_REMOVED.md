# Evidence pesanti rimosse — `fix_generazione_20260909-200000`

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
| `fix_generazione_20260909-200000/evidence/diagnosi/rep_w1_A_p2.json` | 36.2 |
| `fix_generazione_20260909-200000/evidence/manifest/congelamento.json` | 25.9 |
| `fix_generazione_20260909-200000/evidence/EVIDENCE_MANIFEST.json` | 17.5 |
| `fix_generazione_20260909-200000/evidence/diagnosi/ablazione3_B.json` | 13.9 |
| `fix_generazione_20260909-200000/evidence/diagnosi/rep_orig_A_p3.json` | 13.6 |
| `fix_generazione_20260909-200000/evidence/diagnosi/ablazione_B.json` | 13.3 |
| `fix_generazione_20260909-200000/evidence/diagnosi/ablazione_graduata_B.json` | 13.3 |
| `fix_generazione_20260909-200000/evidence/out/diagnostici_w1_p2.json` | 12.9 |
| `fix_generazione_20260909-200000/evidence/diagnosi/rep_orig_A_p1.json` | 12.8 |
| `fix_generazione_20260909-200000/evidence/diagnosi/rep_orig_A_p2.json` | 12.6 |
| `fix_generazione_20260909-200000/evidence/out/diagnostici_w1_p3.json` | 12.3 |
| `fix_generazione_20260909-200000/evidence/out/diagnostici_w1_p1.json` | 12.1 |
| `fix_generazione_20260909-200000/evidence/diagnosi/rep_w1_A_p1.json` | 11.7 |
| `fix_generazione_20260909-200000/evidence/inventario_sha256.json` | 11.5 |
| `fix_generazione_20260909-200000/evidence/diagnosi/rep_w1_A_p3.json` | 11.2 |
| `fix_generazione_20260909-200000/evidence/diagnosi/prova_w2_A.json` | 8.6 |
| `fix_generazione_20260909-200000/evidence/diagnosi/varianti_B.json` | 8.3 |
| `fix_generazione_20260909-200000/evidence/diagnosi/prova_ordine_B.json` | 7.8 |
| `fix_generazione_20260909-200000/evidence/diagnosi/prova_x4_B.json` | 7.0 |
| `fix_generazione_20260909-200000/evidence/out/riscoring_archivio.json` | 4.1 |
| `fix_generazione_20260909-200000/evidence/diagnosi/prova_w2_B.json` | 3.5 |
| `fix_generazione_20260909-200000/evidence/diagnosi/replay_w1_B_r3.json` | 2.8 |
| `fix_generazione_20260909-200000/evidence/diagnosi/ablazione2_B.json` | 2.6 |
| `fix_generazione_20260909-200000/evidence/diagnosi/replay_v0_B.json` | 2.5 |
| `fix_generazione_20260909-200000/evidence/diagnosi/replay_w1_A_r3.json` | 2.3 |
| `fix_generazione_20260909-200000/evidence/diagnosi/replay_w1_A_r2.json` | 1.9 |
| `fix_generazione_20260909-200000/evidence/diagnosi/replay_w1_A_r1.json` | 1.8 |
| `fix_generazione_20260909-200000/evidence/diagnosi/replay_w1_B_r1.json` | 1.8 |
| `fix_generazione_20260909-200000/evidence/diagnosi/replay_w1_B_r2.json` | 1.5 |

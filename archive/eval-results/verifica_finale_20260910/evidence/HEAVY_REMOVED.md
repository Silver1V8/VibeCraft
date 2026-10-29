# Evidence pesanti rimosse — `verifica_finale_20260910`

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
| `verifica_finale_20260910/evidence/s2/s2_risposte.json` | 1206.2 |
| `verifica_finale_20260910/evidence/EVIDENCE_MANIFEST.json` | 22.8 |
| `verifica_finale_20260910/evidence/formati/confronto.json` | 15.8 |
| `verifica_finale_20260910/evidence/e2e/e2e_api_v2.json` | 6.8 |
| `verifica_finale_20260910/evidence/formati2/confronto_2.json` | 3.9 |
| `verifica_finale_20260910/evidence/linux/struttura_windows.json` | 3.8 |
| `verifica_finale_20260910/evidence/linux/struttura_linux_fonts.json` | 3.6 |
| `verifica_finale_20260910/evidence/linux/struttura_linux.json` | 3.6 |
| `verifica_finale_20260910/evidence/indice/scenario_sandbox_dopo_fix.json` | 2.8 |
| `verifica_finale_20260910/evidence/indice/scenario_sandbox.json` | 2.7 |
| `verifica_finale_20260910/evidence/indice/staging_cataloghi.json` | 1.5 |
| `verifica_finale_20260910/evidence/docker/avvio/preview.json` | 1.2 |
| `verifica_finale_20260910/evidence/docker/avvio/approve.json` | 1.1 |
| `verifica_finale_20260910/evidence/docker/avvio/upload.json` | 0.5 |
| `verifica_finale_20260910/evidence/formati/timeout_reale.json` | 0.5 |
| `verifica_finale_20260910/evidence/gate_log_excerpt.json` | 0.5 |
| `verifica_finale_20260910/evidence/docker/avvio/health.json` | 0.5 |

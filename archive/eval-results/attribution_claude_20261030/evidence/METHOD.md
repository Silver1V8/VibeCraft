# R29: giudice di attribuzione remoto, `claude-opus-5-5`, passa S6

Data: 2026-10-30, branch `feat/settings-menu` (menu Impostazioni). Giudice selezionato dal
menu, scopo `judge` → provider `claude_code`: Claude Opus 5.5 attraverso la CLI di Claude
Code (Agent SDK, un turno, nessuno strumento) con il login dell'abbonamento, non con API
key. Temperatura non impostabile da quella via (default del modello). Archivio
`rag/eval/golden_attribution.yaml` (indice storico `v20260907T094225`), prompt del giudice
invariato da S14 (v4): nessuna taratura sul nuovo modello. 72 giudizi in circa 8 minuti.

Il JSON della corsa (`rag/eval/results/attribution_20261030_110401.json`) non è versionato:
dopo R6 l'archivio tiene solo `.md`.

| | qwen3.5:9b (S14) | qwen3.8:27b (29/10) | **claude-opus-5-5** |
|---|---|---|---|
| Accordo col verdetto umano | 20/24 | 21/24 | **24/24** |
| Positivi / negativi | 15/17 · 5/7 | 16/17 · 5/7 | **17/17 · 7/7** |
| Unanimi su 3 giudizi | 24/24 | 24/24 | **24/24** |
| Binario corretta/sbagliata | 22/24 | 22/24 | **24/24** |
| Negativi mancati | 0/7 | 1/7 | **0/7** |
| Falsi allarmi | 2/17 | 1/17 | **0/17** |

Esito: passa il criterio di S6 («se non coincide col verdetto umano, il giudice non è
pronto») e la condizione di R29 (sopra 20/24, negativi 7/7, unanimi). Il 07·2, sbagliato da
tutti e tre i giudizi della famiglia Qwen (9b, nimble, 27b) sul distrattore
`graph_rag_ingestion_strategy`, qui è giusto: R29 aveva ragione a chiedere un'altra famiglia.

Limiti: i 24 record sono gli stessi su cui il prompt fu tarato (per qwen, non per Claude);
24 è un campione piccolo; i passi virgolettati non sono verificabili su nessun record
(45 «in nessuno», 27 senza passo), come con i giudici precedenti.

## Riproduzione

Da `rag/`, con Claude Code autenticato sull'abbonamento (`claude` → `/login`) e nel menu
Impostazioni → Modelli LLM → Per attività: Giudice = Claude (abbonamento), `claude-opus-5-5`.

```bash
uv run python -m eval.attribution --repeats 3
```

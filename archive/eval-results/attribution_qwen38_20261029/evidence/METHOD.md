# R29: secondo giudice di attribuzione, `qwen3.8:27b`

Data: 2026-10-29, codice `24222ba` (main). Ollama 0.40.13, `qwen3.8:27b` (id `aaee06c39dcf`,
17 GB, 71%/29% CPU/GPU su RTX 3070 Ti 8 GB), num_ctx 16384, think false, temperatura 0.
Archivio `rag/eval/golden_attribution.yaml` (indice storico `v20260907T094225`), prompt del
giudice invariato rispetto a S14 (v4): nessuna taratura sul nuovo modello.

Risultati: il JSON della corsa (`rag/eval/results/attribution_20261029_182423.json`, non
versionato: dopo R6 l'archivio tiene solo `.md`) è riassunto qui sotto. 72 giudizi in circa
27 minuti (il 9b: 1 min 42).

| | qwen3.5:9b (S14) | qwen3.8:27b |
|---|---|---|
| Accordo col verdetto umano | 20/24 | **21/24** |
| Positivi / negativi | 15/17 · 5/7 | 16/17 · 5/7 |
| Unanimi su 3 giudizi | 24/24 | 24/24 |
| Binario corretta/sbagliata | 22/24 | 22/24 |
| Negativi mancati | **0/7** | **1/7** (05·2) |
| Falsi allarmi | 2/17 | 1/17 (04·3) |

Esito: non passa il criterio di S6. Sul numero che conta per uno schermo (negativi mancati)
fa peggio del 9b. 07·2 sceglie `graph_rag_ingestion_strategy`, lo stesso distrattore di
qwen3.5:9b e di nimble: dentro la famiglia Qwen il difetto resta.

I tre disaccordi, tutti unanimi sui tre giudizi:

| Record | Umano | Giudice |
|---|---|---|
| 04·3 | `ui_ux_brand_directives` | `safeguards_security` (falso allarme) |
| 05·2 | `inferenza_locale_o_remota` (negativo) | `safeguards_security` (negativo mancato) |
| 07·2 | `spec_graph_rag_ingestion` (negativo) | `graph_rag_ingestion_strategy` (fonte diversa, ma segnalato come sbagliato) |

## Riproduzione

Da `rag/`, con il modello scaricato (`ollama pull qwen3.8:27b`) e `llm_settings.purposes`
impostato a `judge: {model: "qwen3.8:27b"}` in `rag_config.yaml`:

```bash
uv run python -m eval.attribution --repeats 3
```

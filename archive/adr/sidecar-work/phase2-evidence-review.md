# Review indipendente — evidenze F2 complete

**Verdetto: APPROVATO per F2/U-02.** Le nove famiglie `N=10,30,100 × docs,code,mixed` sono complete. La review legge risultati, campioni di processo e aggregato; non ha avviato benchmark, modello o container.

| Modo | N=10 | N=30 | N=100 | Risposte HTTP 200 vuote durante contesa |
|---|---:|---:|---:|---:|
| docs | 15/15 | 15/15 | 20/20 | 29/55 a N10; 132/217 a N100 |
| code | 15/15 | 15/15 | 20/20 | 0 in tutte le famiglie |
| mixed | 15/15 | 15/15 | 20/20 | 10/63 a N10; 37/266 a N100 |

Sono **150 campioni validi su 150**, distribuiti in **30 celle con cinque ripetizioni per cella**: k=0,1,10 per N10/N30 e k=0,1,10,100 per N100. Tutte le famiglie hanno `status=completed`, sampler exit 0 senza errore, baseline integra, query baseline riuscite e restore verificato dopo ciascun campione. Ogni job ha build e reload completati, token pubblicato uguale al `current_version`, nessun coalescing e durate journal finite. Ogni mutazione riguarda k file distinti, con hash cambiato e stessa lunghezza byte; `planned.modified`, `reindexed_docs` e `counts.code_modified` coincidono con i file scelti. Le prove k=0 sono veri no-op. I docs riportano chunk/token ColBERT elaborati; per il codice i token restano `null` con motivo dichiarato, mentre hash/simbolo e conteggi dimostrano la modifica indicizzabile.

I nove `resources.json` coincidono con il ricalcolo di `summarize_resources.py` dai rispettivi `process.jsonl`; ogni campione ha osservazioni del server. L'aggregato `phase2-summary/summary.csv` contiene 30 righe: mediane, min/max e differenze abbinate `T(N,k)-T(N,0)` coincidono numericamente con i job grezzi per tutte le celle. `summary.md` e `summary.svg` sono presenti; il grafico è esportabile. HTTP elapsed resta distinto dal tempo fino allo snapshot pronto. Non viene dichiarato p95 stabile, soglia di capacità o crossover con full rebuild.

Le risposte vuote HTTP 200 durante il delta sono conservate come **degrado osservato**, senza invalidazione silenziosa; il conteggio nell'output coincide con le query grezze. La causa non è identificata da questo esperimento. I picchi di memoria sono limiti inferiori campionati; i contatori I/O sono cumulativi per processo, la cache OS non è controllata e il Qdrant dedicato conserva collection sperimentali precedenti. Nel modo code-only la collection vettoriale baseline ha zero punti perché il codice è negli artefatti sidecar, con integrità comunque riuscita. Il corpus è sintetico: le curve misurano queste condizioni locali, non una capacità universale.

**Finding che richiedono correzioni alle evidenze: nessuno.** La verifica visiva del grafico è separata e in carico al PM; i valori numerici e la presenza dell'SVG sono stati verificati qui.

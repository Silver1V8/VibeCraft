Italiano | [English](README.en.md)

# ADR — Architecture Decision Records

Decisioni architetturali significative del progetto, con contesto,
motivazioni, conseguenze e trigger espliciti per riaprirle. Non sotto
`docs/` di proposito: `docs/` è il corpus indicizzato dal RAG, e un ADR lì
dentro inquinerebbe il retrieval.

| # | Titolo | Stato |
|---|--------|-------|
| [0001](0001-multi-agent-scartato.md) | Multi-agent supervisor scartato | Scartato (con trigger di riapertura) |
| [0002](0002-autorita-dichiarata-e-fiducia-sul-cammino.md) | Autorità dichiarata e fiducia sul cammino del grafo | Accettato e attuato. La tabella nel documento è la fotografia del 18 agosto 2026, non il codice di oggi. I [prompt](../../archive/adr/0002-prompts/) sono il piano con cui è stato fatto, non lavoro aperto |

## Le altre tracce

Non ogni decisione entra in un ADR numerato: le tracce sotto raccolgono registri e piani —
misure, riscontri e lavoro futuro — non singole decisioni chiuse.
Vivono qui per la stessa ragione degli ADR sopra: sono cronaca di sviluppo, non corpus da
indicizzare.

| File | Cosa contiene |
|---|---|
| [`AUDIT.md`](../../archive/adr/AUDIT.md) | cronaca dell'audit, in archive dal 25 ottobre 2026. I numeri di riga citati altrove restano quelli del file spostato |
| [`RESIDUI.md`](../../archive/adr/RESIDUI.md) | backlog derivato dall'audit, chiuso; stessa cartella |
| [`DISTRIBUTION.md`](DISTRIBUTION.md) | il piano di distribuzione: numeri, forcelle e decisioni sul packaging |
| [`EVOLUZIONE.md`](../../archive/adr/EVOLUZIONE.md) | piano di evoluzione del settembre 2026, in archive |
| [`DOCLING_PIPELINE_ALTERNATIVA.md`](DOCLING_PIPELINE_ALTERNATIVA.md) | la proposta di pipeline Docling alternativa al pilot Granite, con configurazione e criteri di valutazione |
| [`NOTA_IMPLEMENTAZIONE_MIGLIORIE.md`](NOTA_IMPLEMENTAZIONE_MIGLIORIE.md) | migliorie e bugfix emersi dal pilot Docling e indipendenti da esso: causa, diff, verifiche, rischio e rollback |
| [`PIPELINE_GATE.md`](PIPELINE_GATE.md) | gate operativo, ciclo end-to-end verificato il 15 settembre 2026, misure, registro degli attriti e problemi aperti |

## Scalabilità sidecar — esecuzione del 21 settembre 2026

- [Piano originale](SCALABILITA_SIDECAR_DELTA.md), conservato come fonte dei requisiti.
- [Matrice finale e decisioni](SCALABILITA_SIDECAR_DELTA_MATRICE.md), con i limiti delle prove e i rami condizionali non attivati.
- [Risultati finali, curve e compromessi](../../archive/eval-results/sidecar_npy_20260921/evidence/PHASE6.md), con migrazione, retention e studio del batching.

Integrata su `main` in `3eda61a`: NPY per documento e letture a richiesta,
migrazione NPZ esplicita e benchmark del delta reale. La review finale ha corretto
l'attribuzione dei tempi di scrittura e il recupero dei reload interrotti.
Verifica d'integrazione: 1.767 test passati su Windows (5 saltati per pesi Docling
assenti), 438 su Linux (9 saltati per Git assente, coperti su Windows).
Il risparmio di memoria è misurato; i delta numerosi di piccoli documenti possono
rallentare. Batching limitato studiato, sharding e ColBERT su Qdrant non attivati.
Per aggiornare un indice esistente seguire la [procedura operativa](../README.md#artefatti-dellindice-formati-sicuri-ispezionabili-e-versionati-bluegreen).

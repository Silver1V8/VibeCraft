# Fase 3 — preparazione PM, non ancora delegata

Avviare soltanto dopo tutte le baseline F2 verificate. Fonte ADR F3-01..05, invarianti G-03/G-04, matrice/checkpoint. Codice core baseline914a170, driver17ce3ca; stessa distribuzione sintetica N10/30/100, modalità docs/code/mixed, stessi k e cinque ripetizioni, CPU4thread/offline, Qdrant1.19 volume Docker nativo/1GiB/2CPU. Non confrontare direttamente tempi F1 sul bind Windows con F2/F3.

## Unità di implementazione prevista

Sol ownership route/reindex/deps/artifacts e test pertinenti; core/indexing solo hash source/caller strettamente necessario. Nessun formato nuovo o cambi scoring. Nessun modello/benchmark/container durante implementazione; PM prepara run post dopo review e suite Windows/Linux.

1. Route incrementale lascia il core decidere se istanziare il modello; già `incremental_index(embed_model=None)` crea un'istanza solo per contenuto docs/code aggiunto/modificato. Il helper `_reindex_embed_model` resta necessario per full. Conservare timing init_model misurato, zero per noop/solo-delete, istanza dedicata (non modello query) per embedding. Regression no-op, solo-delete e contenuto con modello necessario.
2. Noop non ricarica artefatti né invoca callback reload se lo snapshot corrente è già corretto. Token registrato deve essere quello realmente servito, non dedotto soltanto da CURRENT/manifest o inventato dai campi del risultato. Se una CLI ha cambiato CURRENT e lo snapshot server è vecchio, non dichiarare readiness falsa: mantenere riparazione/reload per quel caso o soluzione equivalente documentata. Preservare queue/coalescing, callback errors, journal storico, terminale != pronto. Il bench deve accettare esplicitamente lo stato osservabile noop e verificare token/durate corrette, senza accettare journal incompleti. Minimo contratto necessario, niente framework di callback.
3. Rilasciare locali di lifespan che trattenevano arts/graph/colbert/chunks/code/rules oltre yield dopo creazione snapshot. Regression con weakref: dopo reload, senza lettori pendenti, vecchi oggetti liberabili; lettori attivi mantengono proprio snapshot coerente.
4. SHA256 streaming con `hashlib.file_digest`, identici bytes/hash, in artifact_hashes e caller effettivi integrità/writer. Tracciare anche _docs_hashes/_code_hashes e altri read_bytes usati solo per hash; non modificare read_bytes con diversa semantica. Nessuna validazione hash saltata: stessa integrità completa. Un test file significativo dimostra digest uguale e niente lettura integrale.
5. PM ripete F2 dopo verifica e misura costi residui. Aggiornare driver F2 soltanto per nuovo contratto noop se necessario (stesso timing/corpus/query/restore); rendere compatibile anche baseline pre, non riscrivere raw storici.

## Verifica e report

Focalizzare suite reindex/retrieve_reload/lifespan/atomic_storage/index_timings/bench/bench_delta e hash source se toccato. Red/green essenziale, test con finti encoder non prove prestazionali. Report sidecar-work/phase3-report.md con callers, invarianti e risultati. NPY e ottimizzazioni di scanning mirato restano fuori da questa unità; nessuna soglia universale o migrazione inferita da budget assenti.

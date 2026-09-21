# ColBERT su disco: fonti e vincoli di progetto

Ricerca del 2026-09-15. Stato: valutazione tecnica, nessuna migrazione eseguita. Fonti primarie cercate con Firecrawl Developer Index e verificate nelle pagine ufficiali. Le proposte sotto sono deduzioni progettuali, non risultati di benchmark.

## Riscontro

La direzione è valida: `.npy` permette accesso a porzioni dei vettori senza caricare l'intero archivio. Non dimostra però che ColBERT sia l'unico limite di RAM, né che il limite residuo diventi esclusivamente lo spazio su disco. Occorrono misure del processo applicativo, dell'indicizzatore, del servizio Qdrant e della cache del sistema operativo. Nessun rapporto di costo RAM/disco o tetto di corpus è stato misurato in questa ricerca.

## NumPy: modifica piccola, beneficio da misurare

- `np.load(path, mmap_mode="r", allow_pickle=False)` apre un `.npy` in sola lettura con accesso parziale. Il manuale precisa: “without reading the entire file into memory”. [`numpy.load`](https://numpy.org/doc/stable/reference/generated/numpy.load.html).
- Aggiungere `mmap_mode` a un `.npz` non lo rende memmappato: il ramo ZIP restituisce `NpzFile`; `open_memmap` viene chiamato solo per `.npy`. Verificato nel [sorgente ufficiale NumPy 2.5.0](https://github.com/numpy/numpy/blob/v2.5.0/numpy/lib/_npyio_impl.py) e nel sorgente installato locale `rag/.venv/Lib/site-packages/numpy/lib/_npyio_impl.py:467`. Il progetto dichiara `numpy==2.5.2` in `rag/pyproject.toml`.
- `numpy.lib.format.open_memmap` crea o apre `.npy`; creandolo richiede una forma nota. Non è un archivio con chiavi e aggiornamenti transazionali già pronti. [`open_memmap`](https://numpy.org/doc/stable/reference/generated/numpy.lib.format.open_memmap.html).
- `memmap.flush()` scrive le modifiche, ma NumPy non espone una API pubblica per chiudere la mappa sottostante, che può essere condivisa da viste. Dunque non equiparare `flush` a chiusura o commit atomico. [`numpy.memmap`](https://numpy.org/doc/stable/reference/generated/numpy.memmap.html).

**Implicazione progettuale:** preferire letture lazy dei soli candidati, mantenendo il calcolo corrente. `.npy` immutabili per chunk, con nomi legati alla versione dei contenuti e manifest pubblicato alla fine, evitano la riscrittura dei vettori invariati. Se il delta opera già per documento, un `.npy` per documento con offset per chunk è un raggruppamento naturale: riscrive il documento modificato e contiene il numero di file. Non preaprire e trattenere una mappa per ogni elemento del corpus. Non usare subito un unico `.npy` riscritto per ogni delta: elimina il caricamento completo ma lascia il costo di scrittura proporzionale al corpus. Segmenti generici append-only e compattazione si giustificano solo se le misure rendono insufficienti questi due layout.

Come confronto economico iniziale, `NpzFile` permette già l'accesso selettivo ai singoli array senza materializzare un dizionario di tutti i valori. È una lettura lazy, non mmap: serve misurare decompressione e accessi ripetuti e non risolve la riscrittura globale dell'archivio. Il ramo `NpzFile.__getitem__` nel [sorgente NumPy](https://github.com/numpy/numpy/blob/v2.5.0/numpy/lib/_npyio_impl.py) legge l'array richiesto dallo ZIP.

Va provata esplicitamente la sostituzione/ritiro di generazioni con lettori attivi, soprattutto su Windows. La prima migrazione dovrebbe conservare dtype e formula: quantizzazione e cambio storage insieme impedirebbero di attribuire le differenze.

## Qdrant: candidato plausibile, non cambio di formato equivalente

Qdrant supporta multivettori per punto dal v1.10.0, con numero di token variabile e dimensione del singolo vettore fissa. `MAX_SIM` aggrega con la **somma** dei massimi delle similarità. [Documentazione multivettori](https://qdrant.tech/documentation/manage-data/vectors/#multivectors).

Per usarli nel reranking, la guida ufficiale disabilita HNSW sul solo campo ColBERT con `m=0`, conservando il retrieval iniziale dense. Questo evita costruire un grafo su ogni token e permette retrieval seguito da reranking nella stessa query. [Guida multivettori e late interaction](https://qdrant.tech/documentation/tutorials-search-engineering/using-multivector-representations/).

Dal v1.19 la configurazione corrente è `memory="cold"`; il precedente `on_disk=True` resta funzionante ma deprecato. `cold` e `cached` usano entrambi file memmappati: cambia il preriscaldamento della cache, non l'esistenza di pagine residenti. Il sistema operativo può rimuoverle sotto pressione e i successivi accessi possono richiedere I/O. [Memory tiers, configurazione e migrazione](https://qdrant.tech/documentation/ops-configuration/memory-tiers/). Perciò esternalizzare sposta lavoro e memoria al servizio, senza eliminarli: misurare anche il server. [Storage Qdrant](https://qdrant.tech/documentation/manage-data/storage/).

Il progetto pinna `qdrant-client==1.19.0` e la CI usa `qdrant/qdrant:v1.19.0`. Il modello `VectorParams` installato espone `memory`, `multivector_config` e `hnsw_config`. La fattibilità del parametro è riscontrata; configurazione e versione del server di produzione vanno comunque rilevate prima del pilot.

**Differenza semantica concreta:** `rag/core/retrieval.py:833` restituisce `round(mean(max(dot(query, chunk))), 4)`, mentre Qdrant documenta una somma. Per preservare i punteggi bisogna dividere lo score Qdrant per il numero dei vettori query e riprodurre l'arrotondamento, oltre a scegliere una metrica coerente con il dot product corrente. Non assumere equivalenza tra Dot e Cosine senza verificare la normalizzazione. Il solo ordine su una query non basta: controllare soglie, autorità, ramo grafo e significato di `None` per vettori mancanti.

## Decisione suggerita e prove minime

1. Misurare RAM residente e privata, picco durante caricamento/salvataggio, avvio, query, delta vero e server Qdrant. Separare dati originali, oggetti Python, copie numeriche e cache. `nbytes` e dimensioni del `.npz` non sono una misura di tutto questo.
2. Automatizzare delta riproducibili con k = 0, 1, 10, 100; conservare la durata journal e il tempo esterno totale. Ripetere su baseline ripristinate, registrando chunk e token realmente modificati. Variare anche la dimensione totale N: una curva nel solo k a N fisso non identifica il limite di scala né dimostra la necessità di sharding.
3. Se la misura conferma il sidecar come contributo dominante, pilot `.npy` lazy immutabili. Verificare uguaglianza punteggi, assenza di riferimenti a vettori vecchi dopo delta/delete, recupero dopo interruzione, comportamento con lettori attivi e I/O a cache calda/fredda.
4. Pilot Qdrant solo se il lato operativo o le misure rendono utile centralizzare i vettori. Stessi candidati e stessi embedding per confrontare qualità e costo, `m=0`, `memory="cold"`, normalizzazione dello score esplicita e misura congiunta client/server.

Lo sharding per progetto va riaperto quando il costo che cresce con N continua a superare l'obiettivo operativo dopo le ottimizzazioni locali; non come deduzione automatica da un delta di 100 file. Il criterio deve usare una latenza/memoria accettabile dichiarata e misure, non un numero universale di documenti.

# Scalabilità dei sidecar e delta reale — analisi e piano di implementazione

**Data:** 2026-09-15. **Stato:** proposta, sviluppo non avviato.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** misurare memoria e costo del delta, eliminare costi evitabili e rendere ColBERT caricabile a richiesta senza cambiare il retrieval.

**Architecture:** mantenere inizialmente Qdrant dense/sparse, MaxSim locale e versioni degli artefatti. Confrontare lettura NPZ a richiesta e NPY memmappati; per la migrazione proposta, raggruppare i vettori per documento e riusare i file immutati fra versioni.

**Tech Stack:** Python >=3.14, NumPy 2.5.2, qdrant-client 1.19.0, FastAPI, pytest già presenti. psutil 7.2.2 disponibile nell'ambiente misurato ma non dichiarato direttamente: se usato dal benchmark persistente, dichiararlo nel gruppo dev.

**Spec:** requisiti e decisioni nelle sezioni 1–5 di questo documento; fasi eseguibili nella sezione 6. Fonti esterne nella [nota di ricerca](2026-09-15-colbert-storage-sources.md).

## Vincoli globali

- Memoria e prestazioni prima/dopo devono essere misurate e conservate in `rag/eval/results/<run>/evidence/`.
- Nessuna modifica del corpus o delle collection operative per il benchmark. Usare checkout, database, porta e collection dedicati; i percorsi attuali sono in parte derivati dalla posizione del package.
- Conservare fp16 persistito, conversione fp32 per MaxSim, media dei massimi, arrotondamento a quattro decimali e `None` per un chunk non giudicabile.
- Conservare pubblicazione tramite CURRENT, writer lock, lettura coerente dello snapshot, controllo integrità e rollback esistenti.
- Testare Windows e Linux: file memmappati aperti e retention hanno comportamenti differenti.
- Non introdurre sharding per progetto né un secondo backend permanente senza un risultato sperimentale che lo giustifichi.
- I piani vivono in `rag/adr/`: `docs/` è corpus RAG, come documentato nell'[indice ADR](README.md).

## 1. Giudizio

La miglioria è conveniente **come percorso di misura e rimozione dei colli di bottiglia**. La RAM obbligatoria dei vettori ColBERT è un limite reale, confermato sul loader. Non è dimostrato che sia l'unico limite di capacità del sistema, né che spostare i vettori su disco basti a risolvere l'incrementale.

Tre correzioni alla proposta iniziale:

1. Memmap sposta il requisito da «tutti i vettori materializzati» a «pagine e candidati usati». Restano RAM del modello, grafo, metadati, cache del sistema operativo e temporanei fp32.
2. Misurare `k=1,10,100` su un solo corpus produce una curva del carico modificato, non una soglia di volume. Serve `T(N,k)`, dove N descrive anche chunk/token complessivi, e un budget operativo esplicito.
3. Il rapporto di costo disco/RAM «due ordini di grandezza» non è verificato per questa installazione; non viene usato per giustificare la scelta. Servono anche velocità del disco, spazio per versioni, backup e concorrenza.

## 2. Prima misura reale, già eseguita

Codice: `18c4dc928d88b98c7731b3bfad429ced41135919`. Indice: `v20260911T155042`.
Windows 11 Pro 10.0.26200, AMD Ryzen 7 5800X, circa 32 GiB RAM visibile.

Tre processi Python nuovi hanno eseguito `_load_vectors` di produzione, senza modello e senza server, con baseline dopo gli import. Poi ciascun processo ha caricato tutti gli artefatti mantenendo il primo ColBERT vivo, per osservare due insiemi sovrapposti. Cache del filesystem non controllata.

| Misura | Risultato |
|---|---:|
| Documenti rappresentati in chunks.json | 42 |
| Chunk ColBERT | 257 |
| Token ColBERT effettivi | 112.429 |
| Dimensione effettiva | 1.024, fp16 |
| Token per chunk, min–max | 21–5.927 |
| NPZ su disco | 186,67 MiB |
| Buffer degli array caricati, somma nbytes | 219,59 MiB |
| Incremento RSS caricando ColBERT, mediana | **221,57 MiB** |
| Intervallo RSS dei tre caricamenti | 221,48–221,70 MiB |
| Incremento USS caricando ColBERT | circa 222 MiB |
| Tempo del solo caricamento ColBERT | 0,79–0,85 s |
| Secondo caricamento completo, incremento RSS mediano | 225,29 MiB |

RSS misura memoria residente del processo; USS quella residente privata. `nbytes` descrive i buffer e non include contenitori/allocator. ColBERT occupa il 98,43% dei byte dei file nella versione osservata. Questo dimostra predominanza **oggi**, non un tasso di crescita nel tempo.

Il payload non compresso è solo 1,176 volte il NPZ attuale: su questo corpus la compressione risparmia circa il 15% rispetto ai buffer grezzi. Non è una misura di un formato NPY realizzato; header, offset, metadati e retention aggiungono spazio.

**Limite:** non sono stati misurati il picco del server, il reindex con modello, Qdrant o il delta reale. Non estrapolare da 42 documenti un massimo di corpus. [JSON grezzo](../eval/results/colbert_memory_20260915/evidence/memory.json), [metodo riproducibile](../eval/results/colbert_memory_20260915/evidence/METHOD.md).

## 3. Cosa fa davvero il codice

| Evidenza | Conseguenza |
|---|---|
| [`_load_vectors`](../core/artifacts.py) itera tutti i membri NPZ e costruisce un dict di ndarray | Tutti i multivettori vengono decompressi e materializzati, non soltanto i candidati |
| [`hybrid_search` e `rank_sections_by_relevance`](../core/retrieval.py) leggono `store.get(chunk_id)` | Il confine per leggere a richiesta esiste già; va mantenuto anche nel ramo di espansione del grafo |
| [`incremental_index`](../core/indexing.py) chiama load_artifacts e save_artifacts per ogni delta non vuoto | Embedding incrementale, ma caricamento e persistenza globali |
| [`artifact_hashes`](../core/artifacts.py) usa `path.read_bytes()` | Si alloca temporaneamente l'intero file anche per l'hash; memmap da solo non elimina questo picco |
| [`_encode_chunks_to_points`](../core/indexing.py) riceve tutti i chunk e trattiene tutto l'output di encode | `batch_size=12` limita il batch del modello, non il totale degli output conservati per full o delta grande |
| [`_run_reindex`](../api/routes_reindex.py) costruisce il modello prima di chiamare incremental_index | Anche un no-op paga l'inizializzazione del modello. Nel core la creazione è già condizionata alla presenza di lavoro |
| [`ReindexManager._run`](../api/reindex.py) registra finished_at prima della callback di reload | Il tempo nel journal non include il momento in cui il nuovo snapshot è pronto; created_at include invece l'eventuale coda |
| [`bench_incremental_noop`](../scripts/bench.py) non verifica `result.noop` | L'assenza di modifiche prodotte dal bench non prova che il corpus fosse già allineato; un delta preesistente può falsare l'etichetta |
| [`lifespan`](../api/deps.py) conserva arts/graph/colbert_store/chunks/code_store nelle locali oltre yield | I riferimenti al primo indice restano vivi durante il servizio, anche dopo il rebind dello snapshot. Verificare e rilasciare queste locali al termine del boot |
| [`incremental_index`](../core/indexing.py) calcola _docs_hashes e _code_hashes prima di filtrare changed_paths | Anche il delta ristretto mantiene una scansione/hash del corpus globale |

I 4,81278 s provengono da `bench_20260721T084815Z.json`; il file locale del 4 settembre riporta 4,432094 s. Sono baseline storiche su altri stati, non misure aggiornate. La descrizione «overhead fisso» è incompleta: scansione e hash dipendono da N e dai byte dei sorgenti; la route include il modello, mentre il tempo terminale esclude il reload.

Il no-op attualmente attiva inoltre la callback di reload: non cambia CURRENT, ma ricarica gli artefatti. Separare questa spesa dal delta è necessario per confronti corretti.

## 4. Alternative

| Alternativa | Vantaggio | Limite / impiego |
|---|---|---|
| NPZ letto a richiesta | Migrazione disco non necessaria; si decomprimono solo i membri richiesti | Non è memmap; directory ZIP e indice chiavi restano in RAM, decompressione nelle query, lifecycle/concorrenza da gestire. Persiste la riscrittura globale. Ottimo confronto economico iniziale |
| Un NPY per chunk | Semplice associazione chunk→file e lettura mmap | Molti file, aperture, mappe e operazioni di retention al crescere dei chunk |
| **NPY raggruppati per documento, offset per chunk** | Allinea l'unità di scrittura al delta attuale, che reindicizza documenti interi; meno file, lettura delle sole slice necessarie | Serve un formato indicizzato e un ciclo di vita dei file. Un documento enorme può richiedere segmenti più piccoli |
| NPY unico per versione | Loader mmap semplice | Un solo documento modificato può richiedere riscrivere tutto: risolve principalmente il requisito di lettura in RAM |
| Multivettori Qdrant | Storage e rerank gestiti dal motore già usato | Migrazione collection, score, espansione grafo, consistenza e profiling del server Qdrant. Non basta aggiungere una configurazione |

**Scelta proposta:** confronto NPZ a richiesta vs NPY per documento; adottare il primo solo se soddisfa memoria e latenza al volume target. Preferire NPY quando serve anche ridurre decompressione e byte riscritti. Evitare un framework di backend intercambiabili: al termine dell'esperimento mantenere una strada e il solo lettore necessario alla migrazione.

Qdrant è la seconda strada se i costi di file, lifecycle o reranking locale risultano dominanti. MAX_SIM nativo somma i massimi, mentre qui si fa la media: con la stessa query l'ordine può coincidere, ma soglie e score assoluti no. Servono divisione per numero dei token query, stesso arrotondamento e verifica Dot vs Cosine. La fusione attuale, l'autorità e la valutazione dei chunk aggiunti dal grafo devono restare identiche. Per un uso solo rerank, valutare HNSW `m=0` sul solo campo multivettore. Verificare il contratto della versione server per `on_disk`/`memory`, dtype e query: il pin client non identifica il server in esecuzione.

## 5. Formato proposto, se il confronto giustifica NPY

Dentro ogni versione, `colbert/index.json` descrive formato, dtype, dimensione e mapping `chunk_id -> {file, start, stop}`. Ogni documento ha un file con matrice fp16 `[token_totali_documento, dimensione]`; la slice `[start:stop]` restituisce il chunk. Nomi file opachi derivati da hash, mai path sorgente usati direttamente.

Il reader espone il contratto già consumato: `Mapping[str, ndarray]` con get/len/iterazione chiavi. Apre `np.load(..., mmap_mode='r', allow_pickle=False)` quando serve il documento. Valida confini, dtype, dimensione, file e percorsi prima della pubblicazione. Non costruisce un dict di tutti gli array né una concatenazione dell'intero corpus.

Per scrivere una nuova versione: riusare i file immutati con hard link sullo stesso filesystem; scrivere nuovi NPY soltanto per documenti aggiunti/modificati; escludere i rimossi dall'indice. Gli hard link sono sicuri soltanto mantenendo i file **immutabili**: mai modificare in place un file linkato. Se il filesystem non supporta hard link, usare una copia dichiarata nelle metriche; non sostenere che quella modalità abbia I/O proporzionale al delta.

Tenere ciascuna versione autosufficiente evita un archivio globale condiviso con garbage collector a riferimenti. L'indice JSON, il grafo e gli altri sidecar restano globali inizialmente: non promettere complessità O(k) dell'intero job.

La retention deve rispettare snapshot in uso e mappe aperte. In particolare su Windows, una directory non cancellabile va ritentata e non segnata come rimossa: oggi `rmtree(ignore_errors=True)` nasconde il risultato. Un limite alle mappe deve considerare anche lettori concorrenti, senza chiudere una mappa ancora usata da una slice. Il primo pilot può aprire/chiudere la mappa durante una lettura e restituire una copia del solo chunk: paga una copia limitata, evita mappe persistenti e rende il confronto più semplice. Ottimizzare questo passaggio solo se il benchmark lo richiede.

Full rebuild: emettere e persistire gruppi limitati di output del modello; il solo reader mmap non risolve la memoria trattenuta in scrittura. Hash dei file a streaming, preferendo `hashlib.file_digest`; per file immutabili riusati, conservare gli hash già verificati. Mantenere un controllo integrità completo esplicito che rilegge tutti i byte, distinto dal lavoro ordinario del delta.

## 6. Programma di sviluppo

Le stime sono giorni di lavoro tecnico, non tempi misurati; escludono attese di benchmark e revisione. Sviluppare le fasi nell'ordine indicato, con evidenze separabili e confronto prima/dopo ogni cambiamento.

### Fase 1 — Baseline di processo e journal corretto (1–2 giorni)

**File:** `rag/api/reindex.py`, `rag/core/indexing.py`, `rag/api/deps.py`, `rag/scripts/bench.py`; test esistenti `test_reindex.py`, `test_bench.py`, `test_retrieve_reload.py`.

- [ ] Aggiungere misure monotone per attesa in coda, lock, inizializzazione modello, scan/hash, load, parsing/embedding, Qdrant, relink, save/hash, promote e reload. Conservare created_at/finished_at per compatibilità; non sottrarli per attribuire tempo CPU al delta.
- [ ] Persistire separatamente esito e durata del reload, con token effettivamente pubblicato. Il benchmark aspetta questo esito; `completed` da solo non basta. Un fallimento reload resta distinguibile da una build fallita.
- [ ] Campionare RSS e memoria privata durante boot, query, delta e reload; misurare anche Qdrant, cache/limite del sistema e memoria del dispositivo quando usato. Non sommare RSS condivisi come se fossero byte privati.
- [ ] Conservare versione codice/corpus, modello, numero query concorrenti, cache OS non controllata o esplicitamente controllata, token, chunk e byte letti/scritti.
- [ ] Test: una callback reload bloccata lascia il job terminale ma non pronto; il bench non lo considera pronto. Un journal storico senza i nuovi campi resta leggibile e non acquisisce durate inventate.

**Uscita:** un JSON distingue tutti i costi misurati e il momento di pubblicazione. I vecchi 4,8 s restano etichettati come dato storico.

### Fase 2 — Curva reale T(N,k) automatica (2–3 giorni)

**File:** `rag/scripts/bench.py`, `rag/tests/test_bench.py`; risultati in `rag/eval/results/`; istruzioni in `rag/README.md`.

- [ ] Aggiungere una modalità esplicita per il delta reale, separata dal benchmark ordinario che non modifica sorgenti. Fallire prima di ogni modifica se checkout/database/collection non sono quelli dedicati al test.
- [ ] Costruire una baseline indicizzata e verificata; salvare fingerprint e job_id. Per ogni prova ripristinare la stessa baseline di file **e** indice, evitando la crescita cumulativa del corpus.
- [ ] Eseguire `k=0,1,10,100`, con cambiamenti deterministici al contenuto indicizzabile di k file già presenti. Non usare `touch`, soli timestamp o modifiche che il parser elimina. Verificare hash, `planned.modified`, `reindexed_docs`, chunk e token realmente elaborati.
- [ ] Separare documenti, codice e carico misto; registrare dimensioni dei file e token. Il campione locale ha 42 documenti: per k=100 creare in sandbox un corpus più grande, etichettato sintetico/calibrato, oppure usare un corpus rappresentativo autorizzato.
- [ ] Misurare almeno tre taglie N con la stessa distribuzione di file/token, ad esempio baseline, 3× e 10× se il budget lo permette. Sono punti sperimentali, non soglie di capacità. Riportare solo le combinazioni k≤N effettivamente eseguite.
- [ ] Almeno cinque ripetizioni per cella per una prima mediana/min/max; aumentare le ripetizioni vicino al limite. Non presentare il p95 di cinque campioni come percentile stabile.
- [ ] Salvare durata job dal journal, attesa e tempo fino a snapshot pronto, breakdown, memoria e contesa sulle query. Conservare T(N,0), T(N,k) e differenza abbinata, senza chiamare quest'ultima «solo embedding».
- [ ] Se la coda fonde richieste, il corpus è stale, `result.noop` non è vero per k=0 o i conteggi non coincidono, invalidare il campione. Non convertirlo in un successo né in uno skip generico.
- [ ] Test: falso noop rigettato; k=10 modifica dieci file distinti e identici in lunghezza prevista; k>N è esplicito; restore anche dopo eccezione; journal in coda/reload incompleto non produce un tempo pronto valido.

**Uscita:** tabella e grafico esportabile `T(N,k)` con risultati grezzi. Per conoscere un incrocio incrementale/full, eseguire anche full sulla stessa baseline e dichiarare il costo del suo eval gate. La sola curva incrementale non individua quell'incrocio.

### Fase 3 — Rimuovere costi evitabili senza migrare formato (1–2 giorni)

**File:** `rag/api/routes_reindex.py`, `rag/api/reindex.py`, `rag/api/deps.py`, `rag/core/artifacts.py`; `test_reindex.py`, `test_lifespan.py`, `test_atomic_storage.py`.

- [ ] Riutilizzare la creazione condizionata del modello già presente in incremental_index; preservare un'istanza dedicata per il lavoro che richiede encoding. Test: no-op e sole cancellazioni non istanziano il modello; delta con contenuto sì.
- [ ] Saltare il reload sul risultato noop. Test: callback non chiamata e stesso token snapshot; il benchmark registra che il vecchio snapshot è già quello corretto.
- [ ] Rilasciare le locali del boot che trattengono il primo indice dopo la costruzione dello snapshot. Test di lifecycle: dopo reload, senza richieste pendenti, il vecchio oggetto è liberabile.
- [ ] Sostituire letture integrali usate soltanto per hash con lettura a streaming, mantenendo SHA-256 identico. Includere hash di integrità e percorsi effettivamente chiamati, non solo il writer.
- [ ] Ripetere le stesse celle della baseline. Misurare quanto resta attribuibile ai sidecar prima di migrare.

**Uscita:** riduzione misurata; nessun cambiamento al formato né ai punteggi. Se questa fase copre già volume e budget richiesti, rimandare la migrazione.

### Fase 4 — Confronto economico dei reader (1–2 giorni)

**File sperimentali:** script e risultati nella directory locale della run; usare gli artefatti e le query esistenti, senza modificare produzione.

- [ ] Confrontare eager NPZ attuale, NPZ a richiesta e NPY per documento, prima isolando I/O con candidati identici e poi sul retrieval completo.
- [ ] Verificare array uguali, score e ranking identici, inclusi chunk del ramo grafo, chunk assente e query concorrenti. Misurare memoria privata, RSS, file/mappe aperte, byte e latenza a cache calda e alla prima lettura.
- [ ] Testare vecchio snapshot in lettura durante caricamento/pubblicazione del nuovo. Mai riusare file mutabili fra versioni.
- [ ] Scegliere il reader più semplice che rientra nei budget; scartare gli altri prototipi. Un miglioramento del solo loader non prova il miglioramento del reindex.

**Uscita:** decisione NPZ/NPY supportata da numeri; nessun secondo backend stabile introdotto per prudenza.

### Fase 5 — NPY incrementali e migrazione, condizionale (3–5 giorni)

**File:** `rag/core/artifacts.py` e un solo modulo `rag/core/colbert_store.py` se il reader/writer rende artifacts troppo esteso; `rag/core/indexing.py`, `rag/core/config.py`, `rag/api/deps.py`. Adeguare annotazioni dei consumatori da dict a Mapping dove sono sola lettura. Test: `test_artifacts.py`, `test_incremental_indexing.py`, `test_index_integrity.py`, `test_versioning.py`, `test_retrieve_reload.py`, `test_retrieval.py`.

- [ ] Implementare il formato della sezione 5. Primo reader limitato al chunk richiesto, senza cache applicativa illimitata. Validare indice/file/offset e formato numerico senza pickle.
- [ ] Il writer riceve documenti cambiati/rimossi e la versione padre, senza convertire tutto lo store in dict. Riutilizza file/hash immutati, scrive quelli modificati e mantiene una versione autosufficiente.
- [ ] Aggiornare elenco artefatti, manifest/hash e check di completezza: oggi l'integrità apre direttamente `colbert.npz` e confronta le chiavi. Un indice JSON presente non prova che i file riferiti esistano o siano integri.
- [ ] Segmentare l'encoding del full e dei grandi delta in gruppi limitati, persistendo i risultati progressivamente. Misurare il picco: cambiare solo batch_size non basta.
- [ ] Gestire retention con lettori attivi e cancellazioni fallite; retry tracciato, senza log di rimozione falsa. Test su Windows oltre che Linux, dopo avere chiuso i reader.
- [ ] Convertire la versione NPZ a una nuova candidata NPY, verificare parità e integrità prima di CURRENT. Conservare lettura NPZ per rollback; non scrivere per sempre entrambi i formati.
- [ ] Test di regressione: modifica/cancella un documento, invariati byte/hash degli altri; full e delta equivalenti; crash prima della promozione conserva CURRENT; file/offset corrotti bloccano la nuova pubblicazione; rollback ripristina la stessa risposta.

**Uscita:** limite di memoria ColBERT indipendente dalla materializzazione di tutti i vettori e byte dei vettori riscritti attribuibili ai documenti modificati. Il costo globale residuo di grafo, JSON e scan deve restare visibile.

### Fase 6 — Capacità e decisione Qdrant/sharding (1 giorno + run)

- [ ] Ripetere T(N,k) prima/dopo sulle stesse baseline; includere query durante reindex e retention di più versioni. Riportare disco fisicamente allocato, non soltanto somma delle dimensioni logiche dei file hard-linkati.
- [ ] Applicare budget concordati: memoria disponibile con margine per il picco, massimo ritardo di aggiornamento, degrado tollerato del retrieval e spazio massimo. Finché non esistono questi budget, pubblicare curve e intervalli osservati, non una soglia universale.
- [ ] Se domina scan/hash globale, valutare un vero percorso changed_paths con hash mirati più riconciliazione completa periodica, preservando rilevazione di modifiche non segnalate. Se domina save, intervenire sulla granularità residua; se domina embedding, studiare batching/hardware prima del partizionamento.
- [ ] Aprire un pilot Qdrant solo se file/rerank locale restano il limite. Misurare app e server insieme; preservare candidati, score, dtype, espansione grafo e coerenza delle versioni. Un incrementale Qdrant oggi muta la collection in place: spostare lì ColBERT non crea snapshot storici dei vettori.
- [ ] Valutare sharding per progetto solo se i budget restano violati e query, dipendenze e operazioni richiedono davvero isolamento per progetto. Misurare anche ricerca trasversale e ricalcolo dei link prima di scegliere la partizione.

**Stima complessiva:** 5–9 giorni per misure, curva, correzioni e confronto; altri 3–5 giorni per NPY se necessario, più validazione finale e run. Qdrant e sharding sono decisioni successive, non parte del costo qui stimato.

## 7. Verifiche dello sviluppo

Ogni fase aggiunge i casi comportamentali indicati alle suite esistenti; niente nuovo framework. Da `rag/`, usare il Python del venv e `-m pytest` sui file della fase. Per la migrazione, almeno:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_artifacts.py tests/test_atomic_storage.py tests/test_incremental_indexing.py tests/test_index_integrity.py tests/test_versioning.py tests/test_retrieve_reload.py tests/test_retrieval.py tests/test_reindex.py tests/test_bench.py tests/test_lifespan.py
```

Su Linux usare `.venv/bin/python`. I test dimostrano correttezza, non prestazioni: accettazione della capacità soltanto con run reali e risultati conservati. In questa analisi sono stati eseguiti soltanto i caricamenti read-only descritti, non questi test né il delta k=1/10/100.

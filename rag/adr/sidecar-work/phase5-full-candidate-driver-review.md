# Review pre-run indipendente — full candidate F5-04

**Verdetto dopo fix: APPROVATO per il preflight del driver full-candidate.** Review statica del driver e del report preparatorio; nessun modello, server, container o benchmark avviato. La produzione F5B è ancora in lavorazione, quindi questa review non attribuisce al driver gli errori temporanei del core.

## Riesame dei fix

- **Layout/integrità — chiuso, `full_candidate_experiment.py:39-58`:** esattamente un layout NPZ/NPY; per NPY la firma deve supportare `deep=True` oppure il driver fallisce, quindi rilegge i byte prima di confrontare il set di hash col manifest. NPZ storico conserva la vecchia firma compatibile.
- **Promozione assente — chiuso:** DB iniziale vuoto e Qdrant preflight dedicato; dopo build il driver registra e richiede CURRENT assente e nessun alias base, oltre a timings gate/promote zero. PID e confini monotoni permettono l'allineamento al sampler esterno.
- **Selfcheck — chiuso:** `valid_collection()` è ora usato da `paths()` ed esercitato con input valido e due input respinti. Nel perimetro pre-run è una guardia leggera sufficiente; nessuna fixture di build reale richiesta.

## Contratti già presenti

`delta.validate_paths()` limita checkout a `<run>/sandbox/experiment`, output a sibling nuovo, database inizialmente vuoto e config/paths risolti nel checkout; il driver aggiunge il prefisso collection `sidecar_0628_fullmemory_` e il preflight Qdrant rifiuta riuso o collection non dedicate. `sys.path` antepone il checkout prima dell'import `core.indexing`; il controllo `indexing.__file__` è evidenza diretta dell'implementazione chiamata. Il writer lock circonda il build. Fingerprint del corpus e hash della config precedono la misura; `collector` ed eventi sono dati restituiti dal core, non numeri inventati. `resources.materialized=null` e la richiesta di `bench_process.py` distinguono correttamente il driver dal sampler. La versione non è promossa per scelta intenzionale: gate, readiness, rollback e capacità/crossover non sono provati da questa run.

**Nota di misura:** il report deve mantenere elapsed della build distinto dai tempi del collector e dai picchi campionati del wrapper; nessuna inferenza di budget da una candidata full isolata. Conservare gli hash/config/corpus anche dopo la prova se si vuole attestare immutabilità degli input.

## Nota sulla prova batch separata

`encoding_batch_parity.json` riporta dieci chunk reali: quattro valori fp16 differiscono (massimo assoluto 3,8147e-6), vettori dense e payload dei punti coincidono, e tre query mantengono score a quattro decimali e ranking. È prova circoscritta del raggruppamento dell'encoding, non parità byte fp16 totale, reader NPY o retrieval full; il file stesso dichiara questo limite. Non è stato rieseguito il modello in questa review.

## Review statica aggregatore risorse

`full_candidate_resources.py` usa il PID del workload e i confini monotoni della build per separare i campioni build da quelli dell'intero processo. Lo schema `process.jsonl` osservato nel raw pre contiene le chiavi `monotonic_seconds`, `processes`, `system` e `qdrant`; quest'ultimo fornisce `finished_monotonic` e `cgroup` quando presente. L'aggregatore deduplica le osservazioni Qdrant per timestamp di fine, mantiene RSS/USS/private separati dai dati Qdrant/host, calcola massimi campionati come limiti inferiori e differenze I/O/CPU fra primo e ultimo campione. Metriche mancanti restano `null`. `FULL_MEMORY_METHOD.md` dichiara correttamente che un solo full per variante è esplorativo, che il modello è nel build, e che NPY e grouping encoding cambiano insieme.

**Verdetto aggregatore: APPROVATO dopo fix.** `summarize()` ora rifiuta il caso senza campioni del PID nella finestra build, e il selfcheck negativo usa un raw con PID presente solo fuori intervallo. Restano `null` per singole metriche non osservate. Il raw pre ha lo schema atteso; non ho lanciato il workload né riassunto una run incompleta.

## Validazione evidenza full pre F3

`sidecar_fullmemory_pre_20260921` ha workload `completed`, wrapper `exit_code=0`, `completion=completed`, `sampler_error=null`. La build dura 859,160 s; il PID 29016 ha 4.487 campioni nell'intervallo monotono e 4.563 nell'intero processo. Ho ricalcolato dal raw i picchi campionati di build: RSS 6.910.664.704 B, USS 5.462.532.096 B, private 8.534.343.680 B, uguali a `resources.json`. Le 859 osservazioni Qdrant distinte corrispondono al raw e restano separate dai valori del workload. I contatori I/O/CPU della build sono differenze fra endpoint campionati; quelli dell'intero processo restano `null` perché gli endpoint non li espongono entrambi, correttamente senza sostituire zero.

Il risultato registra 32 documenti, 64 chunk e 28.659 token ColBERT, 64 punti Qdrant, layout NPZ e integrità candidata positiva. Eval gate/promote sono 0; CURRENT assente prima/dopo e alias base assente dopo. `post-run-input-verification.json` conferma corpus/config immutati, 267 file codice congelati verificati e integrità candidata. È una singola misura full pre con picchi campionati inferiori ai massimi reali; non supporta ancora un confronto pre/post o un budget di capacità.

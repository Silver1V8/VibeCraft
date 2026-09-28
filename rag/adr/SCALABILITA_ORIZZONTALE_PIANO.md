# Scalabilità orizzontale — piano di implementazione

> **For agentic workers:** usare `superpowers:subagent-driven-development` per i task delegati o `superpowers:executing-plans` per esecuzione inline. Il metodo è già autorizzato: PM Astra, Sol per codice/concorrenza, Terra per benchmark/docs, Astra per review. Passare alla root prima di iniziare codice prodotto.

**Goal:** streaming `/ask`, concorrenza controllata e misurata, repliche locali opt-in con writer unico e indice immutabile.

**Architecture:** mantenere un processo API per la prima misura; riutilizzare FastAPI, HTTP async, cache, collection versionate e lease esistenti. Dopo il primo gate funzionale, separare reader/writer e verificare due reader locali. Cross-host resta preparazione documentata.

**Tech Stack:** Python 3.14+, FastAPI, httpx2/httpx già presenti, Qdrant server, Ollama, pytest e psutil esistenti. Nessuna nuova dipendenza.

**Spec:** [SCALABILITA_ORIZZONTALE.md](SCALABILITA_ORIZZONTALE.md).

## Vincoli globali

- Solo `C:/Users/Silve/.codex/worktrees/horizontal-scaling/vibecraft`, branch `codex/horizontal-scaling`, base `ea0cf91425a5d01b39ed821c714cd397a6e0d2b0`.
- Non modificare checkout principale, DB/Qdrant operativi, installazioni GPU/modelli; nessun push main.
- Python disponibile: `C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe`; cwd per test: `rag` nel worktree. Usare temp directory/fake servizi; gli import non devono accedere a servizi operativi.
- Prima/dopo ogni fase e fanout: leggere quota. A residuo <=5% in una finestra applicabile o uso vietato/spendControlReached: non iniziare altra fase, salvare checkpoint e avvisare root. Ripresa solo >=15% in tutte le finestre applicabili e uso consentito. Crediti zero da soli non bloccano uso ordinario consentito.
- Niente promessa di throughput o TTFT migliorati prima dei dati reali. Distinguere capacità HTTP concorrente, inferenza fake sovrapposta e inferenza reale.

## Review focus

1. Disconnect durante embedding, attesa slot o primo token: nessuna perdita di slot né cache parziale (P1).
2. Promozione/rollback fra query dense e sparse: entrambe usano collection catturata; richiesta vecchia conserva file e collection (P1/P2).
3. Reader importato con job incompleto nel journal: zero scritture già prima del lifespan (P2).
4. Marker immutabilità presente ma env assente o CLI legacy: nessuna mutazione in place (P2).
5. NDJSON spezzato in byte/chunk, errore dopo delta, risposta senza testo: parser corretto e TTFT non falsato (P0/P1).

## P0 — benchmark riproducibile e baseline (Terra)

**File:** modificare `rag/scripts/bench.py` come ingresso `--concurrency-bench` in sola lettura; helper `rag/scripts/bench_concurrency.py` ammesso, creare `rag/tests/test_bench_concurrency.py`; riusare calcolo percentili/provenienza da `rag/scripts/bench.py` o `bench_process.py` se appropriati. Risultati reali in directory `rag/adr/horizontal-bench/<run>/`, raw JSONL + summary JSON/Markdown. Non alterare vecchi report.

**Interfaccia CLI:** `scripts/bench.py --concurrency-bench --url`, `--concurrency 1 4 8`, `--requests 30`, `--warmup 3`, `--response-mode json|stream`, `--queries FILE`, `--out DIR`, `--timeout SECONDS`; chiave API da env, mai salvata nei report. Il dispatch concorrente deve uscire prima di run_bench storico, che accoda un reindex incrementale: nessun reindex/full nel nuovo percorso. Cache è configurazione server esplicita, non query random per simulare miss. Opzione pid per RSS API/motore e descrizione hardware/parametri nei metadati; valori mancanti null con motivo.

**Contratto:** parser NDJSON incrementale emette eventi; primo `delta.text` non vuoto determina TTFT, result/error determina termine; EOF senza terminale è errore. `result` graph/no_results senza delta => TTFT null. Report conta tutto il denominatore e throughput sui completamenti durante la durata totale, non media dei reciproci delle latenze.

- [ ] Scrivere test con righe frammentate, UTF-8 spezzato, meta iniziale, delta, result; asserire TTFT al delta e non al meta, p95 deterministico, errore a EOF incompleto.
- [ ] Eseguire test in rosso; implementare parser e runner con client async già installato e limite k.
- [ ] Test fake HTTP con contatore attivi: raggiunge k, non supera k, produce esattamente N righe e summary coerente anche con errore/cancel.
- [ ] Salvare baseline JSON sul **servizio isolato** solo quando disponibile; non usare il server operativo. Se indisponibile registrare il blocco, completare harness e non inventare numeri.
- [ ] Verificare e committare P0; aggiornare stato con comandi, raw e limiti delle misure.

Comando test:

```powershell
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -m pytest tests/test_bench_concurrency.py -q
```

Comando benchmark dopo allestimento isolato (porta 18000 dedicata):

```powershell
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' scripts/bench.py --concurrency-bench --url http://127.0.0.1:18000 --concurrency 1 4 8 --requests 30 --warmup 3 --response-mode json --queries adr/horizontal-bench/queries.json --out adr/horizontal-bench/baseline-json --timeout 300
```

## P1 — collection coerente, ammissione e streaming (Sol; review Astra)

**File:** `rag/api/models.py`, `rag/api/routes_retrieval.py`, `rag/api/deps.py`, `rag/core/llm.py`, `rag/templates/dashboard.unified.html`; test esistenti ask/llm + nuovo `rag/tests/test_ask_streaming.py`. Evitare ricopiare 500 righe della pipeline: il JSON e lo stream consumano lo stesso percorso di retrieval/sintesi e finalizzazione.

**Interfacce:** `AskQuery.stream: bool = False`; `core.llm.astream(prompt, *, purpose, timeout, max_attempts)` async iterator di stringhe. Provider Ollama usa HTTP stream nativo; adapter non nativo dichiarato in meta e compatibile coi provider registrati. Contratto NDJSON nella spec. Parametri: `VIBECRAFT_ASK_MAX_ACTIVE=8`, `VIBECRAFT_LLM_CONCURRENCY=2`, `VIBECRAFT_LLM_QUEUE_TIMEOUT_SECONDS=30`; validazione valori positivi al boot. Timeout totale finito coerente con il timeout LLM esistente. Stati ammissione app-local, non semafori globali legati a loop di test precedenti.

- [ ] Test `/ask` cattura collection `c_v1`: finto client cambia alias dopo query dense, query sparse deve ancora ricevere `c_v1`; usare opzione esistente `collection_name` e fallback legacy solo dove già consentito.
- [ ] Scrivere test streaming con provider controllato da eventi: delta iniziale arriva prima che l'evento di conclusione sia liberato; due richieste raggiungono insieme il provider, senza sleep come prova principale.
- [ ] Test limite ammissione: con 8 richieste sospese, la nona riceve 429 prima dell'upstream; dopo cancel/successo lo slot torna disponibile. Test inferenza non supera limite2, attesa scade, health resta responsivo.
- [ ] Implementare astream con chiusura upstream su cancel, errori HTTP/payload/EOF e retry soltanto prima del primo delta. Non usare la coda thread illimitata di `run_streaming` per Ollama.
- [ ] Integrare stream nella pipeline comune e JSON storico; mantenere request_id/versione/cache/status. Aborted/error non entra in cache; cache hit identificabile; marcatore astensione spezzato non altera la finalizzazione.
- [ ] Aggiornare dashboard: invia stream true, decodifica NDJSON incrementale, mostra testo provvisorio, applica result finale; errore/EOF visibile e pulsante riabilitato in finally. Riutilizzare rendering sicuro esistente.
- [ ] Eseguire test mirati e controllare diff per cambi estranei; review Astra e commit P1.

```powershell
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -m pytest tests/test_ask_streaming.py tests/test_ask_unified_llm.py tests/test_ask_cache.py tests/test_ask_abstention.py tests/test_ask_limits.py tests/test_ask_observability.py tests/test_llm.py -q
```

Eseguire matrice `--response-mode stream` e JSON con cache off, poi hit calda separata. Documentare se Ollama effettivamente esegue due richieste; la sola sovrapposizione HTTP non soddisfa la prova reale. Non cambiare configurazione Ollama operativa per produrre il risultato.

## P2 — reader/writer locali e indice immutabile (Sol; review Astra)

**File:** `rag/server.py`, `rag/api/deps.py`, `rag/api/routes_reindex.py`, `rag/api/reindex.py`, `rag/core/config.py`, `rag/core/artifacts.py`, `rag/core/indexing.py`, `rag/core/writer_lock.py`, `rag/core/colbert_store.py`, `rag/index.py` soltanto nei punti necessari. Test `rag/tests/test_reader_role.py`, esistenti versioning/blue_green/writer_lock/lifespan. Documentazione operativa nella specifica e README RAG.

**Interfacce:** `VIBECRAFT_ROLE=standalone|reader|writer`, default standalone. `VIBECRAFT_INDEX_MODE=legacy|immutable`, default legacy; reader/writer richiedono immutable. Marker persistente nel database attiva la stessa protezione anche per CLI senza env. Configurazione percorso database esplicita necessaria ai processi di test e futura separazione host. Snapshot conserva `collection_name` e lease condivisa per tutta la propria vita; riutilizzare `VersionLease`, senza un secondo protocollo.

- [ ] Inventario route/import: reader non deve importare il modulo che istanzia ReindexManager; test API key obbligatoria nel reader anche con peer loopback/proxy e X-Forwarded-For falsificato; test journal con job interrotto e metodi Qdrant mutanti che sollevano se chiamati al boot o durante richieste.
- [ ] Test reader con manifest legacy/incompleto => boot non ready; immutable valido => ready, dati versionati invariati dopo le richieste, solo coordinamento `.reader-locks` RW.
- [ ] Test incremental con marker immutable e senza env => rifiuto chiaro prima di delete/upsert; full esplicito crea nuova collection. Applicare guardia all'entrypoint condiviso dopo aver enumerato tutti i chiamanti CLI/API/webhook/archive.
- [ ] Versionare descrizioni regole e richiedere chunk completi nel reader; niente fallback docs live. Hash/promozione includono il nuovo artefatto; versioni storiche standalone continuano a caricarsi.
- [ ] Tenere lease per snapshot anche nel formato NPZ; richieste/stream mantengono riferimento snapshot. Test processi A/B: A trattiene v1, B promuove v2/v3 e avvia retention+GC sotto lock; manifest e collection v1 restano. Dopo rilascio A, retention/GC può eliminarli.
- [ ] Test rollback mentre due reader servono: ciascuna richiesta usa un'unica versione; nuove richieste dopo reload vedono rollback. Crash reader rilascia lock OS; reload fallito conserva snapshot valido. Zero promessa di lease cross-host.
- [ ] Documentare avvio di un writer e due reader sulla stessa directory locale e porte diverse, limiti aggregati verso Ollama, memoria per processo e prerequisiti futuri cross-host. Nessun load balancer obbligatorio per provare i due reader.
- [ ] Verificare suite mirata, review Astra e commit P2.

```powershell
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -m pytest tests/test_reader_role.py tests/test_versioning.py tests/test_qdrant_blue_green.py tests/test_writer_lock.py tests/test_colbert_store.py tests/test_lifespan.py tests/test_reindex.py -q
```

## P3 — misura finale e consegna (Terra, giudizio Astra)

- [ ] Stessa matrice e corpus baseline/candidato, almeno30 richieste/k fattibili, cache off/on separata; confronto 1 e 2 reader locali con RSS di ogni processo e totale. Evitare inferenze spurie da cache o sole query graph.
- [ ] Test burst e tre sonde di cancellazione per k, fuori dai percentili principali, con conteggi finali degli slot; prova due inferenze Ollama reali sovrapposte su servizio isolato se hardware lo permette. Se mancano le risorse, riportare limite/blocco senza dichiarare completamento end-to-end.
- [ ] Eseguire controlli repository per i file modificati e test di regressione pertinenti; ampliare soltanto se emergono problemi. Comandi/results esatti nel checkpoint.
- [ ] Report tabellare k/scenario/N/TTFT p50-p95/totale p50-p95/throughput/errori/cancel/memoria; link raw+provenienza. Benefici confermati separati da ipotesi. Nessun uso del vecchio 494ms sequenziale come confronto.
- [ ] Review finale Astra contro tutti i gate della spec. Checkpoint con commit, quota e prossimo passo; root integra il ramo secondo autorizzazione senza push main.

## Copertura e ordine

P0 misura e parser → P1 streaming/concorrenza/versione → P2 replica immutabile locale → P3 confronto reale. P0 può essere delegato insieme all'analisi P1 solo dopo gate root e controllo quota; nessun fanout automatico mentre mancano margine o dipendenze. Ogni fase lascia un commit verificato o un checkpoint che dichiara precisamente prove mancanti. Gli host remoti e vLLM restano fuori dall'implementazione corrente finché una prova ne dimostra necessità.

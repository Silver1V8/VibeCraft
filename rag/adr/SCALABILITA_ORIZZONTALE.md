# Scalabilità orizzontale — specifica

Stato: approvata dalla root per implementazione progressiva; ripresa autorizzata 2026-09-28. Audit 2026-09-22, base `ea0cf91425a5d01b39ed821c714cd397a6e0d2b0`, branch `codex/horizontal-scaling`.

## Obiettivo e confini

Servire più utenti sulla macchina attuale e predisporre repliche di lettura su altri host, mantenendo un writer unico e una vista coerente dell'indice per richiesta. Consegnare streaming `/ask`, ammissione limitata e misure a concorrenza k=1,4,8. Nessuna promessa di accelerazione prima delle misure.

Non modificare checkout principale, DB/Qdrant operativi, installazioni GPU o modelli. Test e benchmark di integrazione usano dati e servizi isolati; non avviare il server corrente sui percorsi operativi. Nessun push su main. Specifica, piano e prove restano in `rag/adr/`, fuori dal corpus `docs/`.

## Situazione accertata

| Area | Evidenza nel codice di base | Conseguenza |
|---|---|---|
| HTTP/inferenza | `api/routes_retrieval.py:99,529`; `core/llm.py:311,508` sono già async | «Un utente alla volta» non è un limite applicativo dimostrato. Manca streaming del testo, non async in assoluto. |
| Embedding | `api/deps.py:244` limita l'accesso con semaforo, default 2; `core/retrieval.py:283` chiama encode | Non aumentare worker/concorrenza alla cieca: misurare CPU, memoria e attese. |
| Snapshot | `IndexSnapshot` e `load_artifacts` catturano una versione dei file | Dataclass frozen non garantisce immutabilità globale di vettori o fonti. |
| Qdrant | `/ask` non passa `collection_name` a hybrid_search; `/api/retrieve:638` lo passa | Una promozione può associare file vecchi a collection nuova. |
| Incrementale | `core/indexing.py:2084` riusa la collection del padre | Anche il pin della collection non rende immutabile una versione modificata in place. |
| Boot | `api/deps.py:414` ripara alias e fa GC sotto writer lock | Oggi ogni replica può compiere scritture. |
| Lease | `core/writer_lock.py:72` crea `.reader-locks` con O_RDWR; loader NPZ chiude la lease dopo load | Volume strettamente RO incompatibile con loader attuale; lease file non è protocollo distribuito per collection. |
| Fonti prompt | `api/deps.py:369` legge descrizioni da docs; `/ask:320` ha fallback su docs live | Bundle immutabile deve includere tutto il contesto utilizzato. |
| Writer | ReindexManager è in-process; writer_lock è OS/file locale | Un solo processo writer designato; non distribuire il lock come se fosse un consenso multi-host. |
| Memoria | BGEM3 e snapshot sono caricati per processo | N worker moltiplicano RAM; non moltiplicano la GPU disponibile a Ollama. |

## Decisione

### A. Prima: singolo processo API, streaming e carico limitato

Riutilizzare FastAPI, HTTP client async e cache esistenti. Un solo processo API e un solo servizio Ollama sulla macchina attuale. Conservare il limite embedding configurabile; misurarlo prima di cambiarne il valore. Separare la fase Qdrant/rerank dal semaforo embedding quando l'encoding è già disponibile.

`POST /ask` mantiene la risposta JSON attuale se `stream` è assente/false. `stream: true` restituisce NDJSON (`application/x-ndjson`):

```json
{"type":"meta","request_id":"...","index_version":"...","qdrant_collection":"...","cached":false}
{"type":"delta","text":"testo progressivo"}
{"type":"result","value":{"status":"success","answer":"testo completo"}}
```

`result.value` mantiene il payload JSON attuale completo, inclusi graph_answer, no_results, no_graph_nodes e abstained. Un `error` terminale sostituisce result in caso di errore della pipeline dopo l'apertura dello stream, se il trasporto è ancora disponibile. Un errore di invio o una scadenza durante backpressure chiude la risposta senza garantire un evento finale; il client tratta EOF senza evento terminale come errore. Validazione, autenticazione e saturazione falliscono prima con stato HTTP appropriato. Metadati e heartbeat non sono testo e non contano come TTFT. Cache hit può emettere un delta completo, ma va riconoscibile come cache.

La generazione Ollama usa lo streaming nativo; nessuna divisione artificiale di una risposta già completa. La dashboard mostra testo provvisorio durante lo stream e applica status/fonti/payload definitivo solo sul result; conserva autenticazione, escaping e accessibilità. Il marcatore di astensione, anche diviso fra chunk, non deve comparire come risposta definitiva. I provider senza streaming restano compatibili in JSON; eventuale stream emulato a risposta completa dichiara `streaming_native:false` nei metadati e non dimostra TTFT nativo.

Ammissione di `/ask`: limite per processo validato, default iniziale 8 richieste attive (ipotesi prudente da misurare, non capacità dimostrata); oltre il limite risposta 429 con Retry-After, senza coda illimitata. Limite inferenza separato, default iniziale 2 da misurare, con attesa limitata a 30 s all'interno delle richieste ammesse. Timeout totale configurabile e finito. Gli slot sono rilasciati in finally su successo, errore e disconnect; il client HTTP upstream viene chiuso su cancellazione. Una chiamata CPU già in thread non è cancellabile forzatamente: mantenere il conteggio occupato fino a conclusione effettiva. Retry solo prima del primo testo; dopo un delta nessun riavvio invisibile che duplichi output. Cache solo su completamento valido, mai parziale.

Il limite inferenza applicativo non prova esecuzione parallela nel motore. Verificare separatamente due richieste realmente sovrapposte e parametri Ollama. L'attuale default ufficiale OLLAMA_NUM_PARALLEL è 1; scegliere 2 solo in una prova isolata compatibile con memoria/context, senza alterare il servizio operativo. Repliche con un solo Ollama condividono lo stesso collo di bottiglia; sommare i limiti per replica non crea una quota globale.

### B. Poi: repliche locali opt-in, writer unico e versioni immutabili

Ruoli: `standalone` (default storico), `reader`, `writer`. Reader espone solo pagine necessarie, asset, `/ask`, retrieval, graph e health di lettura. Non importa né registra pipeline, intake, reindex, rollback, webhook, agent runner o altro endpoint mutante: ReindexManager può scrivere il journal già durante import. Un inventario delle route è il controllo di sicurezza. Anche `/ask` conserva le protezioni esistenti. Writer è un processo singolo con l'attuale ReindexManager; il lock OS coordina API e CLI sulla stessa macchina. Multi-writer e failover automatico sono fuori perimetro. Nel reader richiedere API key esplicita anche per peer loopback: un proxy locale non deve trasformare utenti remoti in chiamanti anonimi autorizzati. Non fidarsi ciecamente di X-Forwarded-For; autenticazione per-hop documentata. Lo standalone locale conserva la compatibilità storica.

Il profilo indice `immutable` è obbligatorio per reader/writer replicati:

1. Ogni pubblicazione ha una nuova collection fisica e artefatti completi: grafo, chunk, ColBERT e codice. Le descrizioni regole sono derivate deterministicamente dai chunk versionati, senza leggere docs live né duplicare un artefatto. Il manifest dichiara formato, collection, hash e immutabilità.
2. L'incrementale viene **rifiutato prima del calcolo del delta**, incluso il caso che sarebbe no-op, con messaggio che richiede full rebuild esplicito nel profilo immutable. API/webhook non devono convertire silenziosamente un delta in job GPU completo: indicano operazione non supportata. Qualunque entrypoint che trova il marker persistente immutable deve rispettarlo anche senza env, per impedire ritorni accidentali a mutazioni in place. Il full esplicito esistente costruisce una collection candidata.
3. Build, validazione/eval e manifest precedono promozione atomica di CURRENT. La richiesta cattura un solo snapshot e usa sempre la sua collection fisica; non si affida all'alias. Manifest mancante/invalido causa errore di readiness, senza fallback all'alias nel reader.
4. Descrizioni salvate o derivate esclusivamente dai chunk versionati. Il reader non legge docs live per ricostruire il contesto. Versione incompleta rifiutata prima del serving; reload fallito conserva l'ultima valida e segnala readiness degradata.
5. Prima implementazione: repliche sulla **stessa macchina**, con identico database locale e stesso dominio di lock OS. Una lease condivisa sulla versione dura per l'intera vita dello snapshot, inclusi NPZ, richieste e stream che lo trattengono. Retention acquisisce lease esclusiva prima di cancellare versione e manifest; GC sotto writer lock conserva tutte le collection referenziate dai manifest superstiti. Serve test esplicito della catena lease → manifest → collection. Il pin collection senza tale prova non è sufficiente.
6. Le directory dei dati versionati possono essere RO; `.reader-locks` è coordinamento RW condiviso locale. Non dichiarare l'intero database strettamente RO. Nessun reader modifica artefatti, CURRENT, manifest o Qdrant. Lo stato/log mutabile resta fuori dai dati versionati. Riutilizzare il protocollo lease esistente, estendendone la durata: nessun secondo registro di lease.
7. Host futuri: configurazione endpoint e percorsi esplicita, ma **cross-host non supportato/verificato da questa consegna**. Una copia remota dei file non partecipa alle lease locali. Prerequisiti per abilitarla sono distribuzione atomica delle versioni e retention coordinata di file+collection (oppure conservazione manuale completa fino drain). Documentarli; non implementare export bundle, lease distribuite o orchestratore adesso.

Limite deliberato: full rebuild esplicito costa più dell'attuale delta. Solo costi misurati non sostenibili giustificano snapshot/clone dei vettori. Il profilo standalone legacy conserva semantica storica: nessuna dichiarazione di immutabilità globale per i suoi incrementali. Credenziali Qdrant read-only per reader dove supportate/configurate; nessuna credenziale writer nel reader.

### C. Benchmark e criteri di accettazione

Matrice: k=1,4,8, almeno 30 richieste misurate per k e per scenario, dopo warm-up escluso. Separare cache disabilitata (`VIBECRAFT_ASK_CACHE_SIZE=0`) e hit calda, JSON e streaming, ramo hybrid con LLM e ramo graph. Usare query/versione/modello/context/output comparabili; conservare seed e ordine. Un workload closed-loop mantiene k richieste in volo fino al completamento; un test burst distinto misura i rifiuti.

Per richiesta salvare JSONL raw con timestamp monotoni di dispatch/primo delta testuale/termine, TTFT testo, totale, esito HTTP/evento terminale, cached, strategia, versione/collection, bytes o token se realmente disponibili, cancellazione e timeout. Non stimare token da caratteri senza etichettarlo. Graph/no_results senza testo hanno TTFT null, non zero. p50/p95 su successi con denominatore esplicito; fallimenti/cancel riportati a parte e mai eliminati dal throughput complessivo.

Report: p50/p95 TTFT e totale, completamenti/s su durata wall-clock dell'intera prova, errore/rifiuti/cancel, RSS per API e motore, picco RAM/VRAM e intervallo campionamento. Se dato non rilevabile: null e motivo. Provenienza include commit+dirty diff, OS/CPU/RAM/GPU/driver, runtime/package, modello digest, parametri Ollama/context, processi e limiti, indice/hash, warm-up e comandi. Eseguire baseline prima della modifica e candidato nelle stesse condizioni; 494 ms p50 storico sequenziale non è baseline concorrenza.

Gate funzionali: due generazioni fake sovrapposte; streaming primo delta prima della fine; limite rispettato e slot recuperati; nessuna cache parziale; JSON compatibile; due reader durante promozione/rollback mantengono una singola versione per richiesta; reader non scrive né chiama metodi Qdrant mutanti; marker persistente impedisce incrementali in place; lease mantiene manifest e collection fino al rilascio.

Gate reale: prova Ollama isolata di almeno due inferenze sovrapposte, matrice k=1,4,8 documentata e nessun OOM. Se l'hardware non regge, registrare il limite e mantenere la configurazione sostenibile: test fake non autorizza il claim di concorrenza reale. Nessuno SLA numerico inventato; confrontare distribuzioni, throughput e risorse e riportare eventuale regressione. Se manca dataset/servizio isolato, il benchmark reale resta esplicitamente non eseguito e la consegna non viene chiamata verificata end-to-end.

## Fonti ufficiali verificate dalla root

- [Ollama FAQ](https://docs.ollama.com/faq): parallelismo, code e costo memoria del context moltiplicato per parallelismo.
- [Ollama streaming](https://docs.ollama.com/api/streaming): NDJSON nativo.
- [TGI](https://huggingface.co/docs/text-generation-inference/en/index): maintenance mode; non nuovo backend predefinito.

vLLM resta opzione successiva solo se benchmark dimostra necessità e hardware compatibile. Nessuna installazione o migrazione GPU inclusa in questa fase.

- [vLLM online serving](https://docs.vllm.ai/en/stable/serving/online_serving/): eventuale alternativa API, subordinata a misure e compatibilità.

## Esito audit benchmark

`bench.py:122` esegue 10 richieste sequenziali; non misura concorrenza, TTFT o cancellazioni. `bench_process.py:72` offre già sampling RSS/USS/CPU/I/O, da estendere ai PID API/motore invece del solo client. Il README riporta 24,1s p50 e 32s p95 su 10 campioni storici, non una baseline valida per questo confronto. Host con ollama/docker/nvidia-smi disponibili, ma nessun servizio di test avviato. Aggiungere tre sonde di cancellazione per k fuori dai percentili principali e annotare altri carichi concorrenti sullo stesso host.

## Prova reale del motore — 2026-09-28

La root ha verificato Ollama0.34.4 con l'unico modello locale qwen3.5:9b: il log sched.go:514 dichiara `model architecture does not currently support parallel requests` per architettura qwen35 e avvia runner `-np 1` malgrado `OLLAMA_NUM_PARALLEL=2`. Due richieste HTTP200 concorrenti sono state eseguite in sequenza sullo slot0. Quindi **inferenza realmente parallela non ottenibile con questo abbinamento**, mentre concorrenza HTTP e streaming rimangono implementabili e verificabili.

[Codice ufficiale Ollama scheduler](https://github.com/ollama/ollama/blob/main/server/sched.go) conferma la restrizione qwen35/qwen35moe. Decisione utente 2026-09-28: mantenere per ora Qwen3.5:9b, senza installare modelli/backend alternativi. L'inferenza parallela resta non dimostrata e viene differita come limite accettato della fase attuale. Restano richieste le misure reali di streaming, richieste concorrenti e repliche locali con questo modello; non confondere successo dei test fake con risoluzione del limite.

Correzione provenienza: il processo isolato ereditava `OLLAMA_VULKAN=true`; `CUDA_VISIBLE_DEVICES=-1` non disabilita Vulkan. La prova ha usato GPU Vulkan RTX3070Ti, `size_vram=5435828468`, **non CPU**. La root ha fermato l'istanza dopo la rilevazione. Prove persistenti in `rag/adr/horizontal-bench/preflight-20260928/` (`ollama-overlap.json`, `ollama-evidence.log`, `README.md`); il report finale deve usare la provenienza reale.

L'avvio del server baseline18000 è stato rifiutato dalla revisione automatica (`blocked by policy`, nessun ulteriore dettaglio). Nessun tentativo alternativo: baseline end-to-end resta bloccata, codice/test indipendenti proseguono.

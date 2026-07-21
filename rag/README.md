# rag/ — Console HARO Graph-RAG

Indicizzazione (core/indexing), retrieval ibrido e pipeline Explore → Canvas →
Propose (core/) esposti via FastAPI (api/). Entrypoint: `server.py`, `index.py`.

Le decisioni architetturali significative sono raccolte in
[rag/adr/](adr/README.md) (Architecture Decision Records).

## LLM: un solo layer, provider intercambiabili per step

Tutte le chiamate generative (drift, canvas, propose, validate, explore, canvas
review) passano da [core/llm.py](core/llm.py): `generate(prompt, purpose=...)`
(sincrona) e `agenerate(...)` (async). Provider e modello si risolvono da
[rag_config.yaml](rag_config.yaml): di default `llm_settings.active_provider` +
`llm_settings.models`, con override opzionale **per singolo step** via
`llm_settings.purposes` (esempio commentato nel file). Così si può ad esempio
generare il canvas con Claude e tenere il drift su Ollama locale.

Provider disponibili: `ollama` (endpoint locale `/api/generate`) e `anthropic`
(SDK ufficiale — richiede `uv add anthropic` e la variabile d'ambiente
`ANTHROPIC_API_KEY`; se mancano l'errore è esplicito). Gli errori di rete/timeout
sollevano `LLMError` con messaggio leggibile: i chiamanti restano tolleranti come
prima (il check drift mette il messaggio nel report, l'archive salta la review
con un warning, gli step della pipeline restituiscono il messaggio come testo via
`pipeline.generate_tolerant`). Nei test si inietta un provider fake con
`llm.register_provider` — nessun HTTP (vedi [tests/test_llm.py](tests/test_llm.py)).

Anche `POST /ask` (sintesi della risposta RAG) passa da questo layer, con purpose
`ask`: il prompt (system storico + contesto + domanda, invariati) è costruito
dalla funzione pura `retrieval.build_ask_prompt` e la chiamata è
`llm.agenerate(..., purpose="ask")` — stessi guardrail `think`/`options.num_ctx`
degli altri step, un solo client da mantenere. Su `LLMError` la route risponde
`502` col messaggio dell'errore: mai un testo d'errore dentro `answer` con
`status: "success"`. La base URL di Ollama è unica per tutto il codice
(`VIBECRAFT_OLLAMA_URL`, default `http://127.0.0.1:11434`, core/config.py).

**Router deterministico M2 davanti a `/ask`.** Prima del retrieval, la funzione
pura `core.router.route_question` (regex, zero LLM, zero grafo) classifica la
domanda: le formulazioni **strutturali** inequivocabili (enumerazioni di
documenti/entità, `quali relazioni ha X`, `impatto se modifico Y`, nodi
adiacenti — i casi risolti dal grafo nel report M1) vanno su strategia `graph` e
sono risposte direttamente da `graph_ops.graph_query` (offload in threadpool),
**senza retrieval né chiamata LLM**: la risposta ha `status: "graph_answer"` col
`graph_result` esatto. Tutto il resto (incluse le multihop) resta su strategia
`hybrid`, il percorso retrieval + sintesi LLM descritto sopra. Il router è
**conservativo per costruzione** — in dubbio `hybrid`, vincolo di zero falsi
positivi sul golden-set classico — e la scelta finisce nel campo
`retrieval_strategy` del log strutturato M3.

**Breakdown di latenza in risposta (M3/F3).** Sia il ramo `hybrid` sia il ramo
`graph` restituiscono, oltre a `request_id` e `index_version`, un oggetto
`latency: {retrieval_ms, generation_ms, total_ms}` (nel ramo grafo
`retrieval_ms` è la latenza di `graph_query` e `generation_ms` è 0): gli stessi
valori già presenti nel log strutturato di fine richiesta, esposti anche nel JSON
così i client (e `scripts/bench.py`) misurano il breakdown senza parsare i log.

## Reindex automatico: l'indice non invecchia mai

Due meccanismi tengono l'indice allineato al codebase senza intervento manuale:

**1. Reindex incrementale su webhook (durante il giorno).**
`POST /api/reindex` lancia un reindex incrementale in background e risponde
subito `202` con un `job_id`; `GET /api/reindex/{job_id}` ne riporta lo stato
(`queued`/`running`/`completed`/`failed`) col risultato o l'errore. A fine job
riuscito il server ricarica in memoria grafo/ColBERT/chunk riusando
`reload_index_state` (api/deps.py). `GET /api/reindex` (senza id) elenca gli
ultimi `N` job (`?limit=`, default 20, più recente prima), utile per debug e UI.
Auth: `X-API-Key` come tutti i `/api/*`.

Lo storico dei job è **persistente ai riavvii**: ogni transizione di stato
(`created`/`completed`/`failed`) appende una riga JSON al journal append-only
`database/reindex_jobs.jsonl`. Al boot il `ReindexManager` ricostruisce lo storico
dal journal (l'ultima riga per `job_id` vince); i job rimasti `running` (crash a
metà) vengono marcati `interrupted`. Il file si auto-compatta quando supera ~1MB
(riscritto tenendo solo l'ultimo stato di ogni job) e **non va committato** (è in
`.gitignore`).

Il manager usa una **coda con coalescing** (`ReindexManager`, api/reindex.py):
al massimo un job in esecuzione + al massimo **un pending**. Se arriva una
richiesta mentre un reindex è in corso **non viene più rifiutata con `409`**: è
accodata in un unico slot pending e la risposta è `202` con
`{"job_id": <id del pending>, "queued": true}`. I `changed_paths` delle richieste
accodate vengono **fusi** (unione degli insiemi; una richiesta "completa" con
`changed_paths=None` assorbe tutto → incrementale su tutto). A fine job (successo
o fallimento) il pending parte automaticamente. Così due push GitLab ravvicinati
non si perdono più — il secondo evento si fonde nel pending invece di sparire.

**Un solo scrittore per costruzione.** Ogni scrittura degli artefatti dell'indice
dal server passa dalla coda del manager, che distingue due tipi di job (`kind` nel
`to_dict`/journal): `incremental` (delta) e `full` (`build_graph_and_index`,
ricostruzione completa, senza `changed_paths`). Un corpo `{"full": true}` su
`POST /api/reindex` accoda un full rebuild; anche l'archive (Step 5,
`/api/pipeline/archive[/stream]`) non ricostruisce più inline ma accoda un job
full e riporta il `job_id` al client (nello stream l'evento finale è
`{"type": "reindex_queued", "job_id": ...}`). Coalescing tra tipi: un full
**sussume** qualunque incrementale — se il pending è incremental e arriva un full,
il pending diventa full; se il pending è già full, ogni richiesta successiva vi si
fonde senza cambiarlo. La CLI (`python index.py`) invece scrive gli artefatti
direttamente, fuori dalla coda: con il server acceso preferisci `POST /api/reindex`
(eventualmente `{"full": true}`), che accoda invece di scrivere in place.

**Un solo scrittore anche cross-processo (writer lock).** CLI e server non si
corrompono più a vicenda: ogni ramo che SCRIVE gli artefatti — i comandi CLI di
scrittura (`index.py`: build, `--incremental`, `--archive`, `--rollback`) e i job
del ReindexManager — gira per l'intera durata sotto un lock advisory a livello di
sistema operativo su `database/.writer.lock` ([core/writer_lock.py](core/writer_lock.py):
`msvcrt.locking` su Windows, `fcntl.flock` su POSIX). Il mutex è il lock OS
sull'handle, che il kernel rilascia automaticamente alla morte del processo (crash
inclusi): nessun lock stale da ripulire, il file non viene mai cancellato. Se un
altro writer è attivo la CLI **fallisce subito** con un exit code dedicato
(`WriterLockBusyError`, messaggio con pid/timestamp del detentore) invece di
scrivere a metà — così un `python index.py` lanciato mentre il server reindicizza
non produce artefatti misti.

Configura il webhook GitLab (Settings → Webhooks) su **Push events** e/o
**Merge request events** puntando a `https://<host>/api/reindex`. Per esporre il
webhook in sicurezza imposta **entrambe** le variabili d'ambiente: `VIBECRAFT_API_KEY`
(header `X-API-Key`, richiesta per ogni accesso non locale) e `VIBECRAFT_GITLAB_TOKEN`
(header `X-Gitlab-Token`, il *Secret token* del webhook GitLab). Quando
`VIBECRAFT_GITLAB_TOKEN` è impostata, `POST /api/reindex` esige il token corretto
(confronto a tempo costante con `hmac.compare_digest`) **in aggiunta** a `X-API-Key`;
se non è impostata il comportamento resta invariato (solo `X-API-Key`). Dal payload
push vengono estratti i path modificati
(`commits[].added/modified/removed`) e passati al plan del delta indexing per
limitare il lavoro ai soli file cambiati; un payload merge request (senza elenco
file) fa un incrementale completo su `docs/` + `code/`. È accettato anche un
override esplicito `{"paths": ["docs/x.md", ...]}` per trigger manuali. La
logica di estrazione è in [api/reindex.py](api/reindex.py) (`extract_gitlab_paths`).

**2. Batch notturno ECONOMICO (check di integrità, zero embedding).**
Lo script notturno [scripts/nightly_consistency.ps1](scripts/nightly_consistency.ps1)
(variante POSIX `.sh`) esegue `index.py --check-integrity`
(`check_index_integrity`, core/indexing.py): **niente modello di embedding,
niente costruzione, secondi di esecuzione**. Verifica che il manifest esista e
sia leggibile, confronta `doc_hashes`/`code_hashes` con gli hash correnti su
disco (differenze ⇒ indice **stale**), valida gli `artifact_hashes` contro i
file in `database/` (mancanti o hash diverso ⇒ artefatti **corrotti**/misti) e
confronta il conteggio dei punti Qdrant col numero di chunk nel sidecar. Lo
stesso check è esposto come `GET /api/index/integrity` (auth `X-API-Key`).
In base al report lo script:
- **ok** → esce senza fare nulla;
- **stale** (solo sorgenti cambiate) → `POST /api/reindex` al server locale
  (`VIBECRAFT_SERVER_URL`, default `http://127.0.0.1:8000`, con `X-API-Key` da
  `VIBECRAFT_API_KEY`) così il delta passa dalla coda del ReindexManager; se il
  server è spento, fallback a `index.py --incremental`;
- **artefatti corrotti o Qdrant disallineato** → full rebuild (`index.py`).

**3. Batch settimanale profondo (guardrail anti-deriva).**
Il confronto esaustivo grafo incrementale vs full rebuild (`index.py
--check-graph`, che ri-embedda tutto in memoria) è declassato a settimanale:
[scripts/weekly_consistency.ps1](scripts/weekly_consistency.ps1) (variante
POSIX `.sh`) lo esegue e, **solo se trova drift**, lancia un full rebuild che
riallinea tutto. Dopo il rebuild il server rileva il puntatore `database/CURRENT`
spostato (la promozione della nuova versione blue/green; per i layout legacy senza
CURRENT, l'mtime di `graph.json`) e ricarica gli artefatti alla prima richiesta
(`maybe_reload_graph`).

Scheduling — Windows Task Scheduler:

```powershell
# nightly alle 03:00, weekly la domenica alle 04:00
schtasks /Create /TN "vibecraft-nightly" /SC DAILY  /ST 03:00 `
  /TR "pwsh -File C:\path\to\rag\scripts\nightly_consistency.ps1"
schtasks /Create /TN "vibecraft-weekly"  /SC WEEKLY /D SUN /ST 04:00 `
  /TR "pwsh -File C:\path\to\rag\scripts\weekly_consistency.ps1"
```

cron:

```cron
0 3 * * *  /path/to/rag/scripts/nightly_consistency.sh >> /var/log/vibecraft-nightly.log 2>&1
0 4 * * 0  /path/to/rag/scripts/weekly_consistency.sh  >> /var/log/vibecraft-weekly.log  2>&1
```

## Eval del retrieval: da attrezzo da banco a guardrail

La qualità del retrieval si misura sul golden-set
([eval/golden_set.yaml](eval/golden_set.yaml)) con [eval/run.py](eval/run.py),
che interroga il server reale (`GET /api/retrieve`, così riusa il modello già
caricato) e salva ogni run in `eval/results/`. La modalità guardrail è
`--assert-min`: exit code 1 se il **recall@10 medio** scende sotto la soglia
(il report viene comunque scritto), 0 altrimenti.

**Comando consigliato prima di ogni merge che tocca chunking, ranking o pesi
di autorità** (server su):

```bash
uv run python -m eval.run --assert-min 0.90
```

La soglia 0.90 è fissata poco sotto l'ultimo valore misurato (recall@10 =
0.955 su 22 casi, run del 2026-07-12): se un refactor la fa scattare, il
retrieval è regredito davvero. Rimisura e aggiorna la soglia quando il
golden-set cresce. Questo comando richiede il server acceso (modello caricato):
per questo NON è nella pipeline CI (vedi [sezione CI](#ci)), resta manuale
pre-merge finché non matura la regola di promozione descritta lì.

I test pytest, che non possono caricare bge-m3, coprono la **meccanica** del
guardrail con un retriever fake deterministico
([tests/test_eval_guardrail.py](tests/test_eval_guardrail.py)): parsing del
golden-set, matcher, calcolo del recall, soglia che scatta, estrazione e
promozione dei candidati. Le metriche vere restano il comando qui sopra.

**Il golden-set cresce dalle change (ciclo archive → golden-set):**

1. **Canvas** — alla generazione del canvas il server persiste in
   `changes/<feature>/meta.json` i documenti normativi usati dal retrieval
   governato (`governed_sources`, parsati dagli header del contesto).
2. **Archive → candidato** — `archive_feature` estrae deterministicamente
   (nessun LLM) un caso candidato: query = nome feature + prima riga del
   canvas, expected = quei documenti. Lo accoda a `eval/candidates.yaml`
   (append-only, dedup per query, **mai** nel golden-set diretto).
3. **Revisione umana** — `uv run python -m eval.run --review-candidates`
   mostra i candidati; `--promote 0 2` SPOSTA quelli scelti nel
   `golden_set.yaml` (append testuale: i commenti del file sopravvivono).
4. **Soglia** — con il golden-set aggiornato, rilancia l'eval e rifissa
   `--assert-min` poco sotto il nuovo valore misurato.

## CI

Pipeline minima, senza servizi esterni: [scripts/ci.sh](scripts/ci.sh) (POSIX,
usato anche dalla pipeline) / [scripts/ci.ps1](scripts/ci.ps1) (Windows) fanno
`uv sync --frozen` (installazione riproducibile da `uv.lock`) seguito da `uv run
pytest -q`, con l'exit code di pytest propagato:

```bash
scripts/ci.sh
```

```powershell
pwsh -File scripts/ci.ps1
```

Qdrant e Ollama possono restare spenti: la suite li mocka ovunque (httpx.MockTransport,
attributi di `core.llm` monkeypatchati, `fastapi.testclient.TestClient` in-process). I
soli 3 test che parlano con un Qdrant reale
([tests/test_qdrant_blue_green.py](tests/test_qdrant_blue_green.py), sezione
"OPZIONALE / SKIPPABLE") si auto-saltano con `pytest.skip` quando la connessione
fallisce — non richiedono Docker per il verde.

Il remote effettivo del repo determina la config della pipeline: su GitHub è
[.github/workflows/ci.yml](../.github/workflows/ci.yml) (job `test` che chiama
`scripts/ci.sh`); su GitLab sarebbe `.gitlab-ci.yml` con uno stage `test` equivalente.
Nota: il resto del progetto (webhook `X-Gitlab-Token`, `extract_gitlab_paths`,
l'indicizzatore `.gitlab-ci.yml` in [code_index/ci.py](code_index/ci.py)) presuppone
GitLab come piattaforma — se il remote cambia, la config della pipeline va allineata di
conseguenza.

**Eval NON è nella pipeline (per ora):** `uv run python -m eval.run --assert-min
0.90` (vedi sopra) richiede il server acceso coi modelli caricati — non lo può
lanciare una pipeline che non prevede servizi. Resta un comando manuale
pre-merge per chi tocca chunking, ranking o pesi di autorità.

**Regola di promozione a stadio bloccante:** l'eval diventa uno stadio CI
bloccante SOLO dopo **10 esecuzioni locali consecutive verdi** (nessun flake)
registrate in `eval/results/`. Fino ad allora resta un comando manuale, non
gating. Quando la soglia è raggiunta, aggiungere alla pipeline uno stage
`eval` opzionale/non bloccante prima, poi promuoverlo a bloccante.

**Test intermittente noto:** in run locali senza servizi la suite completa può
occasionalmente andare in errore a cascata (molti `ERROR` di setup/teardown con
`UnicodeDecodeError`) invece che in un singolo test fallito. La causa nota è un
thread daemon di `ReindexManager` che sopravvive al teardown di
`test_archive_stream_route_queues_full_and_emits_final_event`
([tests/test_reindex.py](tests/test_reindex.py)) e logga (`api/deps.py:263`,
caratteri accentati) dopo che la capture di pytest è già smontata — su console
non-UTF-8 questo corrompe il file di capture FD-level e fa fallire in cascata i
test successivi. `scripts/ci.sh`/`ci.ps1` impostano `PYTHONUTF8=1` per evitare la
cascata, ma non eliminano la causa: il fix corretto (sincronizzare il test con la
fine reale del thread via `ReindexManager.join_all`) esiste già altrove nella
storia del repo e va portato su questa linea prima di considerare la suite
completamente stabile in CI.

## Benchmark baseline

[scripts/bench.py](scripts/bench.py) misura le latenze delle vie critiche (server
acceso) e salva uno snapshot in `eval/results/bench_<timestamp UTC>.json`:

```bash
uv run python scripts/bench.py                    # senza full rebuild (default)
uv run python scripts/bench.py --url http://127.0.0.1:8000
uv run python scripts/bench.py --with-rebuild      # accoda anche un full rebuild (lento: minuti)
```

Cosa misura, in ordine: `GET /api/retrieve` su 10 query del golden-set (p50/p95);
`POST /ask` su 3 query fisse (latenze medie — vedi nota sotto); `GET
/api/graph/semantic-map` (latenza end-to-end + `truncated`); un reindex incrementale
NO-OP reale (nessun file toccato: misura solo l'overhead fisso del job, dal journal
`GET /api/reindex`); un full rebuild, **solo con `--with-rebuild`** (di default
`skipped`, è un'operazione lunga e costosa). Se una dipendenza è giù la sezione
corrispondente è `skipped` con motivo: il bench è una **misurazione**, mai un gate —
exit code sempre 0.

**Nota sui campi di latenza di `/ask`:** dal F3 il breakdown è **anche nella
risposta JSON**, non solo nel log strutturato di fine richiesta (osservabilità M3,
vedi [api/routes_retrieval.py](api/routes_retrieval.py)): `/ask` restituisce
`latency: {retrieval_ms, generation_ms, total_ms}` accanto a `request_id` e
`index_version`. Il bench legge questi campi dalla risposta e, per robustezza,
affianca `avg_latency_total_ms_client` misurato lato client.

**Il delta incrementale VERO** (con un file davvero modificato) non è automatizzato:
va misurato a mano modificando un file in `docs/` o `code/` e rilanciando `POST
/api/reindex`, confrontando la durata col job no-op salvato qui.

**Regola:** nessuna ottimizzazione di retrieval, chunking, ranking o indicizzazione
senza prima confrontare un bench "prima" e uno "dopo" — la sensazione che qualcosa
sia più veloce non sostituisce un numero salvato in `eval/results/`.

I test pytest ([tests/test_bench.py](tests/test_bench.py)) coprono solo la
**meccanica** dello script (percentili, aggregazione, polling del journal, struttura
del JSON) con un server finto (`httpx.MockTransport`): le latenze vere restano il
comando qui sopra, da eseguire ed allegare alla PR.

## Artefatti dell'indice: formati sicuri, ispezionabili e versionati (blue/green)

L'indice persiste in `rag/database/` tramite [core/artifacts.py](core/artifacts.py),
**unico punto di I/O**: né `core/indexing.py` né `api/deps.py` toccano i file
direttamente. I formati sono sicuri (nessun `pickle`, che è fragile tra versioni
e un vettore d'attacco se qualcuno scrive in `database/`) e ispezionabili:

| Artefatto | File | Formato |
|-----------|------|---------|
| Grafo NetworkX | `graph.json` | node-link JSON (`nx.node_link_data`), attributi normalizzati JSON-safe |
| Multivettori ColBERT | `colbert.npz` | `np.savez_compressed`, fp16, chiave = `chunk_id` |
| Vettori densi dei chunk | `dense.npz` | idem, chiave = `chunk_id` |
| Vettori densi dei simboli | `code.npz` | idem, chiave = `symbol_id` |
| Sidecar testuale dei chunk | `chunks.json` | `chunk_id → {doc_id, section, text}` |
| Sidecar testuale del codice | `code.json` | `symbol_id → {name, kind, file, dev_type, text, deps, refs, links}` |

Gli attributi dei nodi-documento vengono dal frontmatter YAML e possono contenere
tipi non-JSON (date, `Path`): `_json_safe` li normalizza (una data → la sua ISO
string) così `graph.json` è sempre serializzabile. I vettori restano **fp16
bit-identici** al round-trip. Ogni scrittura è **atomica** (`_atomic_write`): un
crash a metà non lascia file troncati.

### Versionamento blue/green: swap atomico, rollback istantaneo

Ogni build scrive gli artefatti in una **directory di versione nuova**
(`database/versions/v<timestamp UTC>/`, es. `v20260714T153045/`) contenente
grafo, vettori, sidecar **e il manifest di quella build** (`index_manifest.json`:
hash SHA-256 dei sorgenti e dei file artefatto — ogni versione è autodescritta,
così dopo un rollback anche staleness e integrità si misurano contro la versione
attiva). Il file di testo `database/CURRENT` è il **puntatore alla versione
attiva**: la lettura (`load_artifacts`) lo segue sempre, e la sua scrittura è
atomica (`_atomic_write`), quindi lo swap è istantaneo e mai a metà.

Build e promozione sono **due passi espliciti**: `save_artifacts()` restituisce
il nome della nuova versione (senza toccare CURRENT), `promote_version(nome)`
sposta il puntatore. Gli **incrementali** promuovono a fine build riuscita, senza
passare dal gate (finché M6 non decide diversamente). I **full** — sia la CLI
(`python index.py`) sia i job del ReindexManager — prima di promuovere eseguono
l'**eval-gate del golden-set sulla nuova versione** (in process, config
`rag_config.yaml` → `eval_gate.*`: `enabled`, `min_recall` default 0.90, `blocking`):
sotto soglia (e gate bloccante) la versione resta su disco **non promossa**, il job
termina `completed_not_promoted` col report nell'esito e il server continua a
servire la versione precedente. Se il gate è disattivo, il golden-set manca, o
l'eval fallisce, la promozione è diretta (fail-open). Il server rileva ogni
spostamento di CURRENT (`maybe_reload_graph`) e ricarica lo snapshot alla prima
richiesta.

**Rollback istantaneo** — sposta solo il puntatore, nessuna build:

```bash
python index.py --rollback              # torna alla versione precedente
python index.py --rollback v20260713T031500   # o a una versione specifica
```

Equivalente HTTP: `POST /api/index/rollback` (corpo opzionale
`{"version": "v..."}`) ricarica anche lo snapshot in memoria;
`GET /api/index/versions` elenca le versioni disponibili e quella attiva.

**Retention**: dopo ogni promozione restano le ultime N versioni (default 5, env
`VIBECRAFT_INDEX_KEEP`); la versione puntata da CURRENT non viene **mai** eliminata,
anche se più vecchia delle N conservate (caso post-rollback).

### Blue/green Qdrant (collection versionate + alias)

Ogni full rebuild scrive su una collection Qdrant *candidata* e versionata
(`{collection_name}__{version}`), valuta l'eval-gate su quella stessa candidata, e
solo a gate passato promuove CURRENT e sposta un **alias** Qdrant (il nome
configurato in `vector_database.collection_name`, lo stesso che `/ask` e
`/api/retrieve` interrogano sempre) sulla candidata — la collection di produzione
non viene mai toccata durante il build, solo alla promozione. Se il gate blocca la
promozione, la collection candidata resta su Qdrant non referenziata da alcuna
versione attiva: il GC del prossimo job/boot riuscito la rimuove (nessuna
collezione orfana si accumula).

**Migrazione one-shot legacy→alias.** Se la collection di produzione esiste ancora
come collection *fisica* (un'installazione mai passata da questo meccanismo —
Qdrant non ammette un alias con lo stesso nome di una collection esistente), alla
prima promozione viene **cancellata e ricreata come alias** verso la candidata. È
l'**unica operazione irreversibile** del meccanismo: una finestra di
indisponibilità breve ma reale (millisecondi) fra il delete e la create, loggata
esplicitamente. Da quel momento il nome di produzione non è più una collection
fisica: è sempre un alias verso l'ultima versione promossa. Un crash esattamente
in quella finestra lascia l'alias mancante: il reconciler lo ripara al boot
successivo (o al prossimo job full) se la collection candidata esiste ancora,
senza bisogno di un nuovo rebuild.

**Rollback**: `python index.py --rollback [VERSIONE]` (o `POST /api/index/rollback`)
sposta CURRENT **e** riallinea l'alias Qdrant alla collection dichiarata nel
manifest della versione target — cross-lineage esegue lo swap, intra-lineage (alias
già corretto) è un no-op. Se la collection della versione target non esiste più su
Qdrant (es. rimossa dal GC perché la lineage era già stata ruotata), l'alias
**non** viene corretto automaticamente: la risposta riporta
`"qdrant_alias": {"state": "missing_target_collection"}` e serve un full rebuild o
un intervento manuale — nessuna collection viene mai "inventata".

**Riconciliazione e GC.** Al boot del server, prima di servire richieste, un
reconciler confronta lo stato REALE dell'alias con quello atteso dal manifest della
versione attiva e ripara automaticamente i casi "missing"/"diverging" — ma solo se
la collection attesa esiste davvero (nessuna correzione distruttiva); lo stesso
punto esegue il GC delle collection versionate orfane (build crashati o non
promossi, lineage già ruotate dalla retention locale). Riconciliazione e GC girano
**sotto il writer lock** (F2): se una build CLI è in corso al boot il lock è
occupato e questo avvio **salta** entrambe (nessun GC che cancelli la collection
candidata di un rebuild a metà) — non è un errore, il prossimo boot o job full le
riesegue. `GET /api/index/integrity` espone la classificazione READ-ONLY sotto il
campo `qdrant_alias`: `legacy`/`aligned`/`missing`/`diverging`/`unknown`.

### Retrocompatibilità e formati legacy

`save_artifacts()` scrive **solo** i formati correnti, sempre in una directory di
versione nuova (mai riscritta). In lettura, se `CURRENT` non esiste ma in
`database/` ci sono i file flat storici, `load_artifacts()` li carica come
versione `legacy` (con fallback ai vecchi pickle `*.pkl` e un warning che invita
a re-indicizzare con `python index.py`); la prima build successiva crea la
struttura versionata e la promozione fa vincere CURRENT sul layout flat.

## Embedding (bge-m3): CPU per le query, GPU per il reindex

`BGEM3FlagModel` viene istanziato in due punti con device diversi, di proposito:

- **`api/deps.py`** (`state["embed_model"]`, usato da `/ask` e
  `/api/graph/query`): `devices="cpu"`. Una singola query costa ms anche su
  CPU, e lasciare la VRAM libera evita che Ollama carichi `qwen3.5:9b` in
  split GPU/CPU (molto più lento — vedi sezione LLM sopra).
- **`api/routes_reindex.py`** (`_reindex_embed_model()`): nessun `devices`
  esplicito → autodetect GPU. I job di reindex processano migliaia di
  chunk/simboli in batch; su CPU un `full` rebuild passa da minuti a **decine
  di ore** (misurato: ~10s/embedding CPU contro ~6-10 it/s GPU). Richiede la
  build CUDA di torch (vedi `[tool.uv.sources]` in [pyproject.toml](pyproject.toml)
  — su Windows PyPI serve solo la wheel CPU-only, quella CUDA vive
  sull'indice ufficiale `download.pytorch.org`).

Un'istanza fresca per job costa solo qualche secondo di caricamento,
trascurabile rispetto al lavoro di embedding che segue — non vale la pena
condividere l'istanza fra i due usi.

## Esclusioni dalla scansione del codice generato

`CODE_EXCLUDED_DIRS` (core/config.py) è la lista condivisa di cartelle mai
scansionate sotto `code/`: dipendenze installate e output di build
(`node_modules`, `.next`, `dist`, `build`, `coverage`, `.venv`, `venv`,
`__pycache__`, `.turbo`, `.cache`, `bin`, `obj`, `.vs`, `TestResults`,
`packages`). Usata da tre punti che altrimenti farebbero ciascuno il proprio
`rglob("*")` senza filtro:

1. `core.indexing._code_hashes` — base del delta incrementale;
2. `code_index.collect_code_symbols` — estrazione simboli per il grafo (full
   rebuild E incrementale: l'incrementale filtra a valle sui file "toccati",
   ma la scansione grezza sotto è la stessa);
3. il check drift (`core.indexing`, scansione per il confronto codice↔canvas).

Senza questo filtro un `npm install`/`dotnet build` già eseguito nel repo fa
esplodere sia il prompt di drift (Ollama risponde 500) sia il grafo di codice:
misurato +16708 nodi/+131780 archi da un solo `node_modules`, che rendeva
`/api/graph/all` irrenderizzabile in browser. Aggiungere un linguaggio con una
propria cartella di build (es. `target/` per Maven) va aggiunto qui.

## Code index: aggiungere un nuovo linguaggio

L'estrazione dei simboli dal codice generato (`code/`) vive in
[code_index/](code_index/__init__.py); i parser tree-sitter in
[code_index/ts.py](code_index/ts.py) (TS/TSX/JS/JSX/Svelte),
[code_index/java.py](code_index/java.py) (Java + pom.xml/build.gradle +
Kogito .bpmn/.dmn), [code_index/csharp.py](code_index/csharp.py)
(C#/.NET + .csproj/packages.config) [code_index/razor.py](code_index/razor.py)
(famiglia Razor: view MVC, Razor Pages, componenti Blazor) e
[code_index/sql.py](code_index/sql.py) (SQL: T-SQL, PL/SQL, generico —
archi semantici READS/WRITES/EXECUTES e ponte codice→stored procedure
dai parser C#/Java) [code_index/config.py](code_index/config.py)
(file di configurazione riconosciuti per nome: web/app.config,
appsettings*.json, package.json, WSDL/XSD — secret sempre mascherati,
nodi collegati al progetto di appartenenza) e
[code_index/shell.py](code_index/shell.py) (script operazionali Bash e
PowerShell via tree-sitter — archi EXECUTES script→script e riferimenti
incrociati verso i progetti/file invocati) e
[code_index/ci.py](code_index/ci.py) (pipeline GitLab CI / Azure DevOps
riconosciute per nome — nodi pipeline/job, archi verso template, progetti
buildati e repo esterni dai trigger),
[code_index/frontend.py](code_index/frontend.py) (semantica React/Angular
sopra il parser TS: componenti, hook, DI, route, template — framework
rilevato dal package.json del progetto, non dall'estensione) e
[code_index/docker.py](code_index/docker.py) (artefatti di containerizzazione
riconosciuti per nome — Docker Compose via pyyaml e Dockerfile via scanner
riga-per-riga: nodi service/image, archi service→service da `depends_on` e
service→Dockerfile dal build context; environment/ARG sensibili sempre
mascherati). L'interfaccia di un parser è una funzione
`(text: str, stem: str, suffix: str) -> list[tuple]` con tuple
`(kind, name, snippet)` o `(kind, name, snippet, meta)`: `kind` è ad es.
`function`/`class`/`endpoint`/`component`, `name` è univoco nel file,
`snippet` è il contesto testuale usato per l'embedding (max ~1500 char) e
`meta` (opzionale) porta `deps` (nomi di altri simboli del progetto, risolti
best-effort in archi DEPENDS_ON da `link_symbols`) e `package`.

Per aggiungere un linguaggio:

1. **Grammatica** — aggiungi il wheel della grammatica con `uv add
   tree-sitter-<lang>` (o usa `tree-sitter-language-pack`, già in dipendenza,
   se il wheel singolo non esiste: `get_parser("<lang>")`). Niente
   compilazione manuale: solo wheel precompilati.
2. **Parser** — implementa in `code_index/ts.py` una funzione con
   l'interfaccia sopra. Per linguaggi C-like spesso basta estendere
   `_DECL_KINDS`/`_walk_symbols`; per formati contenitore (vedi
   `svelte_symbols`) localizza i blocchi di codice con la grammatica del
   formato e ri-parsa il contenuto con la grammatica del linguaggio interno.
3. **Dispatch** — in `code_index/` registra l'estensione in `CODE_EXTS`,
   mappa suffisso → linguaggio in `_PARSER_LANG`, imposta il default in
   `_PARSER_DEFAULTS` e aggiungi il ramo in `_extract`. Il flag
   `code_parsers.<lang>` in [rag_config.yaml](rag_config.yaml) permette di
   tornare a un'eventuale implementazione alternativa senza deploy.
4. **Test di equivalenza** — estendi
   [tests/test_ts_parser_equivalence.py](tests/test_ts_parser_equivalence.py)
   con un corpus del linguaggio: se sostituisci un parser esistente, il nuovo
   deve estrarre almeno tutti i simboli del vecchio (zero `persi`).

**Secondo esempio del pattern — Java** (`code_index/java.py`): grammatica
`java` dal language-pack; estrazione framework-aware via annotation (JAX-RS
`@Path`+`@GET/...` → `endpoint`, CDI `@Inject` → nodo `field` + dep verso il
bean, messaging `@ConsumeEvent/@Incoming/@Outgoing` → `listener`), stesso
pattern dei decoratori FastAPI nel parser Python. Gli artefatti di progetto
non hanno bisogno di tree-sitter: pom.xml/.bpmn/.dmn sono XML (ElementTree),
build.gradle è regex best-effort. Niente test di equivalenza: non esisteva un
parser Java precedente (i test sono su un mini-progetto fittizio in
[tests/test_java_index.py](tests/test_java_index.py)).

**Esempio completo del pattern — C#/.NET** (`code_index/csharp.py`): mostra
tutti i pezzi in un modulo solo. Grammatica `csharp` dal language-pack (punto
1 della guida); simboli con namespace nel meta `package` e using come `deps`;
estrazione framework-aware via attributi, runtime-agnostica: [HttpGet]/
[HttpPost]/[Route] (ASP.NET Core) e [OperationContract] su [ServiceContract]
(WCF, .NET Framework legacy) → kind `endpoint`; file di progetto senza
tree-sitter: `.csproj` (PackageReference/ProjectReference → DEPENDS_ON tra
progetti, base dell'impact analysis multi-repo) e `packages.config` legacy;
dispatch + flag `code_parsers.csharp` (punto 3); corpus fittizio in
[tests/test_csharp_index.py](tests/test_csharp_index.py) (punto 4, senza
equivalenza: parser nuovo). Fuori scope, TODO nel dispatch: Razor/.cshtml
(grammatica immatura; servirà un parser dedicato stile `svelte_symbols`) e
VB.NET.

**Variante senza grammatica — Razor** (`code_index/razor.py`): quando la
grammatica tree-sitter non esiste o è immatura, il parser può essere uno
scanner ibrido: regex per direttive/markup, delega al parser tree-sitter di
un altro linguaggio per i frammenti incassati (i blocchi `@code` vanno al
parser C#, come gli `<script>` Svelte vanno alla grammatica TS). I link che
richiedono la vista d'insieme dei file (code-behind per convenzione di nome,
`View()` → `Views/{Controller}/{Azione}.cshtml`, tag componente Blazor) si
esprimono come **dep tipizzate** (`view:...`, `page:...`, `component:...`)
risolte da `resolve_links` dopo la scansione di tutto `code/`: le dep
risolte diventano archi DEPENDS_ON, quelle non risolte finiscono nel report
di governance (`code_index.razor_report()`: link rotti e view orfane), mai
in nodi fantasma. `refs` nel meta crea archi REFERENCES codice→codice
(es. view → `@model`).

I parser regex storici (`_js_symbols`) restano come fallback d'emergenza
dietro flag; TODO datato in `code_index/` per la loro rimozione.

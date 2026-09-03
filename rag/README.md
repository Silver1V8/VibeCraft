# rag/ — Console Graph-RAG

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

**L'astensione è leggibile a macchina** (`status: "abstained"`). Il modello si
astiene già correttamente in prosa libera quando il contesto recuperato non
contiene la risposta — verificato dal vivo — ma prima il payload restava
`status: "success"` con le fonti elencate in `qdrant_scores`, identico nella
forma a una risposta vera: un client non aveva modo di distinguere "ha
risposto" da "si è astenuto" senza fare NLP sulla prosa. `[REGOLA-ASTENSIONE]`
nel prompt (`retrieval.build_ask_prompt`) impone al modello di anteporre il
token `retrieval.ASK_ABSTENTION_MARKER` (`[ASTENSIONE]`) quando e solo quando
il contesto non basta; `ask_rag` lo legge, lo rimuove — l'utente umano non lo
vede mai — e imposta `status: "abstained"`. Distinto da `no_results` /
`no_graph_nodes`: lì il retrieval non trova nulla, qui trova qualcosa ed è la
sintesi a dire che non risponde.

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

**Il codice è una fonte di `/ask`, non solo i documenti.** La ricerca semantica
interroga Qdrant, dove stanno **solo i documenti**: il codice vive nel grafo (nodi
simbolo) e i suoi vettori densi nel sidecar `code.npz`. `/ask` lo porta nel contesto
per **due strade complementari**, e ciò che inietta è esposto nel campo
`implementing_code` della risposta (con `source` per ramo di provenienza):

1. **Ricerca semantica diretta** (`retrieval.search_code_symbols`): coseno fra il
   vettore denso della **domanda** e quelli dei simboli, calcolato in memoria (~25 ms
   su 4.000 simboli, nessun punto in più in Qdrant, nessun costo di indicizzazione).
   È l'unica strada che trova il codice che **nessuna spec descrive** — un DTO con
   l'elenco dei campi obbligatori, un helper, una query. Un tetto per **file**
   (`code_search_max_per_file`) impedisce a un singolo file autogenerato (il proxy
   WCF `Reference.cs`) di occupare tutte le posizioni con varianti della stessa riga.
2. **Ponte `IMPLEMENTS`** (`retrieval.collect_implementing_code`): dagli archi
   entranti ai nodi recuperati risale l'**implementazione di ciò che si è
   recuperato**, così l'LLM confronta la spec con il codice reale ("cosa manca nel
   form?").

I due risultati sono deduplicati per simbolo con priorità al ramo semantico e cappati
complessivamente (`code_context_total_snippets`). La regola `[FONTE-CODICE]` del
system prompt dichiara il blocco «CODICE ESISTENTE» **fonte legittima**: senza,
`[REGOLA-DIZIONARIO-RIGIDO]` portava il modello a trattare come invenzione qualunque
nome di campo assente dai documenti e a rispondere "Non specificato" con la classe che
quei campi li dichiara sotto gli occhi. Se il retrieval documentale non trova nulla ma
il codice sì, la domanda **riceve comunque una risposta** (prima: "Nessun documento
rilevante"). Tutte le soglie stanno in `rag_config.yaml → retrieval.*`;
`code_search_max_snippets: 0` disattiva il ramo diretto.

**Budget guard giornaliero su Claude, fallback automatico su Ollama.**
`core/llm.py` tiene un contatore di spesa Anthropic per giorno UTC, alimentato dallo
stesso costo stimato già loggato per l'osservabilità (`llm_settings.pricing`): senza
un prezzo configurato per il modello nulla viene contato e il guard resta inerte. Se
`llm_settings.budget.daily_usd` è superato, `resolve(purpose)` devia silenziosamente
(provider, model) su `budget.fallback_provider` (default `ollama`) — a patto che quel
provider abbia un modello in `llm_settings.models`, altrimenti resta su anthropic per
non trasformare un problema di costo in un fallimento di generazione. Il contatore
persiste opzionalmente su file (`budget.spend_file`, altrimenti solo in-memory,
azzerato al riavvio) e non fa mai fallire una chiamata: qualunque errore interno del
guard (config malformata, file illeggibile) viene loggato e si resta sul provider
risolto. `spend_today_usd()` espone la spesa corrente per diagnostica.

**Breakdown di latenza in risposta (M3/F3).** Sia il ramo `hybrid` sia il ramo
`graph` restituiscono, oltre a `request_id` e `index_version`, un oggetto
`latency: {retrieval_ms, generation_ms, total_ms}` (nel ramo grafo
`retrieval_ms` è la latenza di `graph_query` e `generation_ms` è 0): gli stessi
valori già presenti nel log strutturato di fine richiesta, esposti anche nel JSON
così i client (e `scripts/bench.py`) misurano il breakdown senza parsare i log.

**Cache semantica su `/ask`, invalidata per `index_version`.**
[core/ask_cache.py](core/ask_cache.py) è una LRU thread-safe in-process che azzera il
costo (embedding + generazione LLM) delle domande ripetute — la maggioranza su una
console di governance. La chiave (`make_key`) è `(index_version, retrieval_strategy,
top_k, bfs_depth, sha256(domanda normalizzata))`: la domanda è normalizzata (trim,
lowercase, spazi collassati) prima dell'hash, così due formulazioni identiche a meno
di spaziatura condividono la voce. **L'invalidazione non esiste come operazione**:
`index_version` fa parte della chiave, quindi dopo una re-indicizzazione o un
rollback (`database/CURRENT` cambia in entrambi i casi) le voci della versione
precedente non vengono più consultate e la LRU le espelle. Lo stato vive su
`app.state.ask_cache` (non in una global di modulo, quindi i test restano isolati
senza fixture globali), creato lazy con tetto da env `VIBECRAFT_ASK_CACHE_SIZE`
(default 256 voci, `0` disattiva la cache). I payload cachati sono trattati come
immutabili: la route costruisce la risposta con una copia (`{**cached, ...}`), mai
mutando l'oggetto in cache.

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

**Divergenza `docs/` ↔ git (campo `docs_git`).** I file di `docs/` sono marcati
`skip-worktree`, quindi le differenze fra la copia di lavoro e il committato sono
**invisibili a `git status` e `git diff`** — voluto, per non vedere il materiale di
dominio come "modifiche", ma significa che il corpus indicizzato può discostarsi dal
repository senza che nessuno se ne accorga. `observe_docs_git_divergence` confronta
l'hash del blob di `ls-tree HEAD` con `hash-object` sul file di lavoro (bypassa
l'indice git, che per gli skip-worktree è fermo al committato; `hash-object` applica
gli stessi filtri eol, quindi niente falsi positivi su checkout CRLF). È
**osservazione pura**, come `qdrant_alias`: non contribuisce mai a `ok`/`problems`,
perché una divergenza git **non si ripara re-indicizzando** — il reindex rileggerebbe
gli stessi file — e trattarla come problema farebbe scattare un full rebuild inutile a
ogni esecuzione. Quale corpus sia autoritativo è una decisione umana; il check la rende
solo visibile. Gli script notturni la stampano **sempre**, anche a integrità OK (è il
caso in cui resterebbe nascosta) e scrivono un alert.

**Istanziazione dichiarata ≠ difetto.** La baseline è fatta per essere istanziata sul
posto — `docs/README.md` prescrive di compilare la Sezione 0 e risolvere i
`<<PARAMETRO>>`, e `skip-worktree` esiste proprio perché quell'istanza non risulti come
"modifica". Un check che segnalasse anche quella non verrebbe più letto: il rumore
atteso seppellisce il segnale raro. Un documento che dichiara `instantiated_from:` nel
frontmatter è quindi classificato a parte — resta elencato e contato, ma non è un
problema, e non fa scattare l'alert notturno. Il marcatore è una dichiarazione umana con
lo stesso modello di fiducia di `authority:`: chi lo scrive per mascherare una divergenza
accidentale sta mentendo al proprio strumento, non aggirando un controllo. Un file
**sparito** dal disco non può dichiarare nulla e resta sempre una divergenza; un
frontmatter malformato non vale come dichiarazione (il caso ambiguo si risolve verso
`diverging`, che è il più prudente).

Stati: `aligned`, `instantiated` (solo differenze dichiarate), `diverging` (almeno una
non dichiarata — e ne basta una perché lo stato torni tale), `unavailable` (git assente,
non un repository, HEAD assente — mai un'eccezione).
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

## Intake & Import: ingresso controllato della conoscenza

La pagina **`/intake`** ([templates/intake.unified.html](templates/intake.unified.html),
route in [api/routes_pages.py](api/routes_pages.py)) è l'unico ingresso di nuova
conoscenza — documenti e progetti — nel sistema. Il principio non negoziabile è lo
**staging con review**: nulla entra in `docs/` o nell'indice senza un'approvazione
esplicita dalla pagina. Il ciclo vive in [core/intake.py](core/intake.py) e nelle
route [api/routes_intake.py](api/routes_intake.py) (`/api/intake/*`, auth `X-API-Key`
come il resto), e usa lo stesso reindex delta + writer lock dell'indicizzazione
incrementale.

**Cinque flussi, un solo staging** (`database/staging/`, con journal append-only
`intake.jsonl`):

- **Genera con Ollama** (`POST /api/intake/generate`, [core/doc_generation.py](core/doc_generation.py)):
  fino a `intake.generation_max_files` documenti markdown grounded nel Graph RAG
  (hybrid_search) e nelle lezioni delle canvas review; ogni file è validato
  (parse + chunking) prima di entrare in staging.
- **Importa documenti** (`POST /api/intake/docs`, [core/intake_convert.py](core/intake_convert.py)):
  upload multipart convertito in Markdown con microsoft/markitdown — un solo motore per
  tutti i formati non-md (PDF, DOCX, PPTX, XLSX/XLS, HTML, CSV, JSON, XML, EPUB, MSG, ...);
  i `.md` entrano nativi (solo decodifica). La whitelist resta la nostra
  (`intake.allowed_formats`, markitdown è permissivo e ripiega su plaintext per estensioni
  ignote). Estensione e dimensione (`intake.max_upload_mb`) validate PRIMA di leggere
  l'intero body in memoria. L'uscita del convertitore passa **sempre** per
  [core/intake_clean.py](core/intake_clean.py), che toglie l'arredo di impaginazione del
  sorgente — testate e piè di pagina ripetuti a ogni pagina, numeri di pagina, indici coi
  puntini di guida, immagini base64, sillabazione e a-capo di giustificazione. È pulizia
  **deterministica e idempotente**: nessuna parola di contenuto viene persa (su un PDF
  istituzionale toglie comunque il 20-60% del dump). Senza, tutto quel rumore finisce
  identico nei chunk del RAG.
- **Raffina con LLM** (`POST /api/intake/staged/{id}/refine`,
  [core/intake_refine.py](core/intake_refine.py)): passo **opt-in** del ciclo di review che
  trasforma il dump del convertitore in una spec strutturata — sezioni `##` (l'unità di
  chunking), tabelle per gli elenchi di campi, blocchi di codice per XML/XSD — più un
  frontmatter **semantico** dedotto dal documento (`title`, `document_type`, `domain`,
  `tags`), che `approve` fonde in coda ai campi normativi senza mai sovrascriverli. Job
  async (pattern S3) perché su un documento lungo sono decine di chiamate al modello
  (~2 min per finestra su GPU locale). Due guardrail contro il rischio vero di questo
  passo, che è tradire il documento: si raffina a **finestre**
  (`intake.refine.window_chars`, ben sotto `num_ctx` — oltre, Ollama tronca in silenzio) e
  una finestra la cui riscrittura esce dalla **forbice di lunghezza** viene **scartata** a
  favore del testo pulito. Troppo corta significa che il modello ha riassunto (e un
  riassunto perde requisiti); troppo lunga che ha commentato o ipotizzato invece di
  riformattare — su una fonte frammentaria tende a riempire i buchi con congetture
  ("inferito", "potrebbe riferirsi") che in un documento normativo sono peggio del testo
  grezzo. Il tetto **dipende dalla forma della fonte**: la prosa sta sotto
  `max_output_ratio`, mentre le fonti dense (alberi di classi, elenchi di campi — righe
  mediamente più corte di `dense_line_chars`) hanno diritto a `max_output_ratio_dense`,
  perché diventando tabelle con una colonna di descrizione crescono di 3-4× senza che una
  parola sia stata inventata. Il markdown grezzo resta in staging accanto al raffinato:
  rieseguire il refine riparte sempre da quello, mai dalla riscrittura.
- **Review staging** (`GET /api/intake/staged`, `.../preview`, `POST .../approve`,
  `POST .../reject`): preview del markdown, poi **approve** (scrive
  `docs/<categoria>/<nome_file>` con frontmatter conforme + reindex delta della sola
  path aggiunta, sotto writer lock) o **reject** (motivo nel journal, file spostati
  in `staging/rejected/`, mai cancellati). `approve` **non sovrascrive MAI** un file
  esistente in `docs/`, e il documento composto deve passare parse/chunking PRIMA di
  qualunque scrittura.
- **Importa progetto da path** (`POST /api/intake/project/plan` + `.../apply`,
  [core/project_import.py](core/project_import.py)): import di un progetto locale in
  `code/<target>` (`backend`, `frontend`, `logicAgent`) col pattern **plan/apply**.
  Il plan è un **dry-run puro** (zero scritture) che classifica i file in
  nuovi/identici/conflitti/esclusi (esclusioni riusate da `CODE_EXCLUDED_DIRS`).
  Semantica **additiva e non distruttiva, vincolante**: cartella vuota → bootstrap
  (copia tutto il copiabile); cartella popolata → additivo (copia SOLO i file nuovi;
  i file esistenti con contenuto diverso sono **conflitti**, riportati nel piano e
  **mai applicati**). `apply` fa un backup zip della cartella target, copia solo i
  nuovi, rifiuta un piano **stale** (fingerprint del target cambiato dopo l'anteprima)
  e reindicizza il codice in delta (avviso esplicito se serve un full rebuild per i
  code-link). **Mai una sovrascrittura, mai una cancellazione** di un file esistente
  in `code/`.

**Project brief** (`POST /api/intake/project/brief`, [core/project_brief.py](core/project_brief.py)):
dopo un import riuscito, genera via Ollama una sintesi architetturale del progetto
(componenti, entrypoint, dipendenze, mappa simboli→spec dagli archi `IMPLEMENTS` del
grafo, aree candidate a refactoring), **grounded sui dati reali del grafo** — mai
inventati. Precondizione: un import `applied` per quel target/progetto nel journal
(altrimenti 409); grafo senza simboli → esito con avviso, mai un crash. Il brief
entra in staging come ogni altro documento (`source "brief"`) e passa dalla stessa
review S2: **nessun percorso diretto verso `docs/`**.

L'unità del brief è il **progetto**, non il target. `target` è un bucket
(`backend`/`frontend`/`logicAgent`) e l'import è additivo, quindi `code/backend/` può
ospitare più progetti affiancati (`GD102_WSGDAProtocolloManager` **e**
`GD172_WSProtocollo`): un grounding filtrato per solo `dev_type` prende i simboli di
tutti, e il tetto `_MAX_SIMBOLI_NEL_PROMPT` riempie il prompt col primo in ordine di
`id` — il brief chiesto per un progetto descrive l'altro. Il campo `progetto` della
richiesta seleziona la cartella sotto `code/<target>/`; **omesso vale l'ultimo progetto
importato** in quel target, mai "tutto il bucket". `GET /api/intake/project/imports`
elenca i progetti importati (dal journal) per popolare la scelta nella pagina.

Nel prompt i simboli sono un **campione scelto, non un troncamento**. Un progetto reale
ne ha migliaia (`GD172_WSProtocollo`: 4100 simboli in 309 file) e nel contesto di
qwen3.5:9b ne stanno decine: `simboli[:80]` su una lista ordinata per path mostrava solo
le cartelle iniziali in ordine alfabetico e, dei 337 endpoint, solo quelli che iniziano
per A. `seleziona_simboli` fa invece **un giro per file** (una `Reference.cs` generata da
1650 simboli vale come ogni altro file) e dentro ciascuno prende prima ciò che ha valore
architetturale (`_RANGO_KIND`: tipi ed entrypoint prima delle property, a parità di
natura vince il grado nel sottografo), campionando **a passo costante** le fasce
omogenee troppo lunghe — così le 337 operazioni SOAP si attraversano tutte invece di
fermarsi alla A. Accanto al campione il prompt porta i **conteggi per modulo, completi**:
sono l'unico grounding che copre il 100% del progetto, e il prompt dice esplicitamente al
modello che l'elenco dei simboli è parziale. I tetti del prompt sono **in caratteri**
(`_BUDGET_CHAR_*`), non solo in voci: la lunghezza di una riga dipende dai path del
progetto, e con soli tetti a voci il prompt usciva a ~48.000 caratteri (~13.700 token) —
dentro `num_ctx 16384` a stento, con Ollama che taglia l'eccedenza **dall'inizio**, cioè
proprio le istruzioni. Ora resta sotto i ~6.500 token, il resto della finestra è per la
risposta.

Le **regole di formato** del prompt sono istruzioni per il modello, non garanzie: prima
della validazione l'output passa da `normalize_generated_markdown`
([core/doc_generation.py](core/doc_generation.py)), che ripara i tre modi ricorrenti in
cui il contorno del documento esce sbagliato — documento avvolto in un fence
```` ```markdown ````, frontmatter aperto e **mai chiuso**, frontmatter non caricabile
come YAML — senza toccare il corpo. Il frontmatter generato è materiale di passaggio
(quello conforme lo ricalcola l'`approve`), quindi un contorno rotto non costa più
l'intero documento; resta scartato solo ciò che non ha un corpo utilizzabile, col motivo
nel journal. In parallelo il parser di indicizzazione riconosce il frontmatter **solo**
come blocco ben formato `---`…`---` in cima al file (`core.chunking.split_frontmatter`,
confronto per riga): un blocco non chiuso vale come assente, non inghiotte più il corpo
del documento nel YAML.

## Eval del retrieval: da attrezzo da banco a guardrail

La qualità del retrieval si misura sul golden-set
([eval/golden_set.yaml](eval/golden_set.yaml)) con [eval/run.py](eval/run.py),
che interroga il server reale (`GET /api/retrieve`, così riusa il modello già
caricato) e salva ogni run in `eval/results/`. La modalità guardrail dà exit code 1 se il
recall **alla `k` dell'eval-gate** scende sotto la soglia dell'eval-gate — oggi
`recall@2 < 0.75` — con il report scritto comunque; `--assert-min` sostituisce quella
soglia per una corsa singola.

**Comando consigliato prima di ogni merge che tocca chunking, ranking o pesi
di autorità** (server su):

```bash
uv run python -m eval.run
```

Ultima misura (2026-08-25, 59 casi, corpus 26 documenti / 181 chunk, baseline
ripristinato, `safeguards_security.md` istanziato sul dominio v2.2.0 e scheda
`BUDGET_ANNUO` aggiunta al glossario):
`recall@1 0.576 · @2 0.797 · @5 0.983 · @10 1.000`.

**Il guardrail asserisce sulla `k` dell'eval-gate, e con la sua soglia** — entrambe lette
da `eval_gate` in [rag_config.yaml](rag_config.yaml), oggi `recall@2 ≥ 0.75`. `--k`
sceglie quali colonne *leggere*, mai su cosa si fallisce, e la `k` del gate viene misurata
comunque anche se non la chiedi. `--assert-min` resta per abbassare o alzare la soglia in
una corsa singola.

**Prima asseriva sul k più alto passato** (A2b), e i due script notturni non passano `--k`:
il loro confronto cadeva su `recall@10`, **satura a 1.000**, contro un `--assert-min 0.90`
scritto a mano. Un `--assert-min` su una metrica satura non è severo, è cieco — lo supera
qualunque regressione che non faccia uscire una fonte dai primi dieci — e quello era un
check notturno che, per costruzione, non poteva fallire.

`recall@5` era saturata a 1.000 dopo l'istanziazione ed è tornata a 0.983 quando il
corpus si è arricchito ancora: **il gate resta comunque a k=2**. Un gate che cambia
`k` a ogni modifica del corpus non è un gate — la stabilità della soglia vale più di
qualche punto di sensibilità.

Il criterio *«/ask inietta 8 sezioni, quindi conta se la fonte entra nella
finestra, non a che rango»* resterebbe valido — ma un gate deve prima di tutto
**distinguere una regressione**, e a @5 non distingue più nulla. Se anche
`recall@2` saturasse non resterebbe un k più basso utile: vorrà dire che il
golden-set ha smesso di essere una misura e va **esteso** con casi che il sistema
sbaglia, non abbassata un'altra soglia.

Questo comando richiede il server acceso (modello caricato): per questo NON è
nella pipeline CI (vedi [sezione CI](#ci)), resta manuale pre-merge finché non
matura la regola di promozione descritta lì.

**Tre letture, non una media sola** (S5, [ADR 0002](adr/0002-autorita-dichiarata-e-fiducia-sul-cammino.md)).
La corsa standard riporta il recall a **k ∈ {1, 2, 5, 10}**, e non per completezza:

- **la saturazione è segnalata come difetto, non come 100%.** Una recall che vale
  1.000 su *tutti* i casi non è un buon risultato: è una misura che ha smesso di
  discriminare. Il report la marca `⚠️ SATURA` sulla riga della metrica. È un
  errore già commesso: la ricalibrazione dei pesi di autorità del 2026-07-22 girò
  a k=10 e k=5 su una griglia interamente satura e concluse — correttamente ma
  inutilmente — che nessuna combinazione era distinguibile.
- **il sottoinsieme avversariale ha una voce a sé.** I casi marcati
  `adversarial: true` nel golden-set (oggi 4 su 55) contrappongono una fonte a
  bassa autorità che matcha lessicalmente *meglio* della normativa che risponde:
  sono l'unico posto dove il boost di autorità può essere falsificato, e nella
  media coi casi facili il loro movimento sarebbe invisibile.
- **i pesi di autorità si calibrano con [eval/calibrate_authority.py](eval/calibrate_authority.py)**,
  che gira in-process (niente server) e **non applica nulla**: scrive una proposta
  in `eval/results/authority_calibrated.yaml` da rivedere a mano. Calibrare
  **sempre** con split di validazione, **sempre** a un k non saturo e **sempre**
  su più seed — il default è 5-fold su 5 seed con deviazione standard riportata,
  perché su un solo split un guadagno sopra soglia si è già rivelato rumore di
  partizione. Lo script segnala anche gli **assi morti**, cioè i parametri che sul
  corpus corrente non muovono la metrica di un millesimo.
- **e ciò che il recall NON misura: a chi la risposta attribuisce il vincolo.** Il
  recall dice se la fonte giusta è stata *recuperata*; `/ask` ne inietta fino a 8 e
  l'LLM le legge tutte, quindi il recall può essere ottimo mentre la risposta cita
  come fonte del vincolo il documento che lo *illustra*. È successo davvero — 2 casi
  avversariali su 4, indagine A3 in [AUDIT.md](AUDIT.md) — e la correzione
  (`[CLASSE-FONTI]`: la classe dichiarata nell'intestazione di ogni blocco del
  contesto, più la graduatoria delle classi presenti) **non ha mosso il recall di un
  decimale**, perché il ranking era già corretto. Chi tocca il prompt di `/ask` non
  ha una metrica che lo protegga: legga le risposte.

```bash
uv run python -m eval.calibrate_authority --k 5   # proposta, mai applicazione automatica
```

### La seconda suite: strutturale e multihop

[eval/golden_multihop.yaml](eval/golden_multihop.yaml) + [eval/run_multihop.py](eval/run_multihop.py)
misurano le domande che il golden-set classico non copre: **enumerare** («quali documenti
esistono nel corpus?»), **navigare** («cosa impatta la modifica di X?») e **combinare due o
tre documenti collegati**. Su ogni domanda misura due strade — **A** il retrieval puro
(`/api/retrieve`, k=10) e **B** la query deterministica sul grafo (`/api/graph/query`) — così
il divario fra le due è un numero, non un'impressione.

```bash
uv run python -m eval.run_multihop        # server su; exit 1 sotto soglia
```

**Quattro casi su 14 non possono passare A, ed è la misura, non un difetto.**
L'enumerazione chiede 11 fonti a un top-10, e le tre catene che spandono tre documenti si
fermano a due: è esattamente il gap che ha motivato il router deterministico. Per questo la
soglia — `eval_multihop` in [rag_config.yaml](rag_config.yaml) — sta sulla **recall media di
A** (0.85, con 0.896 misurato) e sull'**esattezza piena delle attese strutturali di B**, mai
sul numero di casi «riusciti»: sarebbe un numero che il sistema non può far salire.

A differenza di `recall@10` sul golden-set classico, **questa metrica non è mai stata satura**.

Fino al 2026-09-03 la suite girava solo a mano (A4): ora ogni corsa lascia una riga in
`history.jsonl` (`source="multihop"`, chiavi prefissate per non mescolarsi con l'altra
suite) e, sotto soglia, un alert critico — ed è nel check notturno insieme all'eval classico.

**Il caso che non passava, e perché la sua storia resta qui** (chiuso il
2026-08-25). *«posso usare un sinonimo per nominare una variabile o devo seguire
il glossario»* è stato per settimane l'unico dei 59 a non comparire in top-10.
L'attesa puntava a `coding_standards § Tracciabilità della Governance`, e sembrava
un caso scritto male.

Non lo era. Quando il golden-set fu redatto (commit `3a95322`, 2026-07-22)
`coding_standards.md` era alla **v2.0.0 cross-progetto** e possedeva
`[REGOLA-CLEAN-07] Allineamento terminologico rigido`, che risponde esattamente a
quella domanda. La copia di lavoro era però tornata alla **v1.0.0
dominio-specifica**, ferma a `CLEAN-04`: la regola esisteva solo nel committato, e
il RAG indicizza il disco. Tre file divergevano, e la divergenza era **invisibile a
`git status`** perché i file di `docs/` sono `skip-worktree`. Il difetto non era né
nell'indice né nel ranking: era nel corpus, e nulla lo guardava.

Ripristinato il baseline committato, il caso **passa** (atteso a rango 3) e
l'intero golden-set rientra in top-10. Due effetti collaterali che valgono più
della singola riga verde:

- **due casi avversariali erano stati scartati per il motivo sbagliato.** «Estrazione
  dei magic numbers» e «isolamento delle regole di business» erano stati giudicati
  *disonesti* perché `coding_standards.md` non trattava quegli argomenti: sono
  `[REGOLA-CLEAN-05]` e `[CLEAN-06]`, presenti nel baseline e assenti dalla copia di
  lavoro. Il giudizio era una conseguenza della divergenza, non del caso.
- **un caso avversariale ha smesso di esserlo.** «Tracciabilità bidirezionale nei
  commenti» lo era perché `vibe_coding_workflow.md` v1.0.0 ridefiniva
  `[REGOLA-CLEAN-*]` con una numerazione collidente. La v2.0.0 rimanda a
  `coding_standards.md` invece di duplicarlo: sparita la collisione, l'atteso va a
  rango 1 e il marcatore `adversarial` è stato tolto — un caso che il sistema supera
  gonfierebbe la recall del sottoinsieme. Gli avversariali sono passati da 10 a 9.

Da qui il check [`docs_git`](#reindex-automatico-lindice-non-invecchia-mai): la
divergenza è tornata visibile, e a ogni check notturno resta tale.
I test pytest, che non possono caricare bge-m3, coprono la **meccanica** del
guardrail con un retriever fake deterministico
([tests/test_eval_guardrail.py](tests/test_eval_guardrail.py)): parsing del
golden-set, matcher, calcolo del recall, soglia che scatta, estrazione e
promozione dei candidati. Saturazione, sottoinsieme avversariale e integrità dei
matcher avversariali (devono puntare a documenti e sezioni realmente esistenti nel
corpus) sono in [tests/test_retrieval_eval.py](tests/test_retrieval_eval.py). Le
metriche vere restano i comandi qui sopra.

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
   `eval_gate.min_recall` poco sotto il nuovo valore misurato. È lì che vive la
   soglia, e da lì la leggono gate, guardrail, check notturno e dashboard.

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

Qdrant e Ollama possono restare spenti: la suite li mocka ovunque (httpx2.MockTransport,
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

**Eval NON è nella pipeline (per ora):** `uv run python -m eval.run` (vedi sopra)
richiede il server acceso coi modelli caricati — non lo può lanciare una pipeline
che non prevede servizi. Resta un comando manuale
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
del JSON) con un server finto (`httpx2.MockTransport`): le latenze vere restano il
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
l'eval fallisce, la promozione è diretta (fail-open).

Il gate misura anche la **saturazione** della propria metrica e, se `recall@k`
vale 1.000 su tutti i casi, scrive un alert `warning`: a quel k non è un gate
severo, è un gate cieco — lo supera qualunque candidata, anche una peggiorata.
Non blocca (non è una regressione), ma va letto come "abbassare `eval_gate.k` a un
k che discrimina". Non è teorico: sul golden-set di 49 casi, misurato a luglio
sul corpus di allora (11 documenti), il recall@10 era saturo a 1.000 su tutta la
griglia di calibrazione. Oggi è 0.983 e discrimina, per due ragioni che vale la
pena tenere distinte: il corpus è cresciuto a 26 documenti (e un caso classico non
arriva più in top-10, vedi sotto) e i casi avversariali abbassano il recall@1. Il server rileva ogni
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
`packages`), più `.git`. Usata da tre punti che altrimenti farebbero ciascuno il proprio
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

## Estrazione entità: solo riferimenti veri nel grafo

`core.chunking.extract_entities` cerca nel corpo dei documenti i riferimenti fra
parentesi quadre nella forma `[UTENTE]` (entità di dominio) o `[REGOLA-VAL-07]`
(identificatore di regola) e li trasforma in nodi `entity` + archi `MENTIONS`.
L'estrattore originale (`re.findall(r"\[(.*?)]", text)`) catturava **qualunque**
cosa fra quadre: sul corpus reale produceva 22 nodi entità privi di semantica
su 109 token estratti — checkbox Markdown `- [ ]`, etichette dei link
`[testo](url)`, destrutturazioni JS `[k, v]`, literal `'[REDACTED]'`, classi
regex `[A-Z_]` e segnaposto dei template (`[REGOLA-XXX-NN]`,
`[SAFEGUARD-YYY-NN]`) citati a scopo esplicativo nella prosa.

Il filtro ora è a due stadi:

1. **Rimozione delle regioni non-riferimento** prima dell'estrazione: blocchi
   di codice ``` ``` (dove le quadre sono sintassi) e link Markdown (dove sono
   navigazione). Il codice inline fra backtick singoli **non** viene scartato:
   la convenzione dei documenti cita le regole proprio così
   (`` `[REGOLA-HITL-01]` ``) nei titoli e nelle tabelle, e in alcuni documenti
   è l'unica forma in cui certe famiglie di regole compaiono.
2. **Vaglio di forma** sul token candidato: `_RULE_ID_RE`
   (`[A-Z][A-Z0-9]*(-[A-Z0-9]+)*-\d+`, ultimo segmento numerico — il
   discriminante fra una regola vera e un segnaposto di formato) oppure
   `_ENTITY_ID_RE` (`[A-Z][A-Z0-9_]{2,}`, sole maiuscole/cifre/underscore, MAI
   il trattino, così le wildcard `[REGOLA-*]` restano fuori).

Effetto misurato sul grafo (full rebuild `v20260722T105547`): nodi 226→204
(entity 124→102, section/document invariati), archi 332→302 (`MENTIONS`
183→153, nessun'altra relazione toccata) — zero token legittimi persi.
Test in [tests/test_chunking.py](tests/test_chunking.py).

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

## L'indice come acceleratore per l'agente che scrive il codice

`GET /api/code/search?q=...&k=...` espone a un agente esterno (Claude Code,
Cursor) la stessa ricerca semantica sui simboli che alimenta `/ask`: coseno fra
la domanda e i vettori densi dei simboli, già calcolati all'indicizzazione e
persistiti in `code.npz`. Nessun LLM, nessuna query a Qdrant — una forward pass
di bge-m3 e un prodotto matriciale in memoria.

Serve a un problema misurato: un agente che deve integrare codice in `code/` non
sa dove sta ciò che gli serve e ripiega su Glob+Read a tappeto, cioè legge (e
paga) l'intero ambito per trovare i due file che gli servono. Su questo repo,
una ricerca `k=5` in `code/frontend` restituisce ~2,2 KB che puntano a 3 file per
21 KB complessivi, contro i ~101 KB dell'intero `src/`.

Quel guadagno però si ribalta facilmente nel suo contrario — se la risposta è
grossa, l'agente paga i token dell'indice **e poi** quelli dei file. Perciò la
risposta è **navigazionale**, non documentale:

- **niente testo dei simboli per default**: solo `symbol_id`, `file`, `kind`,
  `dev_type` e `score`, più l'aggregato `files` — l'elenco dei file da aprire, che
  è la sola cosa che l'agente deve davvero ricavarne;
- `&snippet=true` aggiunge il testo, **troncato** a `code_search_api_snippet_chars`
  (400): sullo stesso esempio raddoppia la risposta, ed è per questo un'eccezione
  dichiarata nel prompt, non il default;
- `&k=` è limitato da `code_search_api_max_k` (25) e `max_per_file` impedisce a un
  file autogenerato di occupare tutte le posizioni;
- `&dev_type=` restringe all'ambito della feature. Il filtro agisce **prima** dei
  top-k (`search_code_symbols(subset_idx=...)`, indici per ambito precalcolati una
  volta per snapshot in `api/deps._prep_dev_type_index`): applicato a valle, un
  ambito poco rappresentato sparirebbe ogni volta che i top-k globali appartengono
  a un altro ambito.

Il prompt finale della pipeline istruisce l'agente a usarlo, ma **solo quando il
destinatario può**: `build_final_prompt(..., consumer=...)` aggiunge il blocco di
orientamento per `external` (Claude Code/Cursor, che hanno una shell) e lo omette
per `agent` — l'esecuzione in-app via Agent SDK non ha Bash (vedi
[agent_bridge.py](agent_bridge.py)) e non può fare alcuna chiamata HTTP; darle
quelle istruzioni significherebbe descriverle uno strumento che non ha. Il blocco
è additivo: la variante `agent` è, byte per byte, il prompt storico. La dashboard
mostra la variante `external` da copiare e chiede `GET
/api/pipeline/final-prompt?consumer=agent` quando lancia l'esecuzione in-app —
endpoint che esiste anche per togliere di mezzo la copia JavaScript del template,
che era già rimasta indietro di una frase rispetto a `core/pipeline.py`.

Il blocco dice tre cose che ne delimitano l'uso, e sono la parte che conta:
l'indice serve **solo** a scegliere cosa leggere, è uno snapshot dell'ultima
indicizzazione e può essere disallineato (i code-link restano stale fino al
rebuild), quindi ogni file va letto per intero prima di modificarlo e nessuna riga
va dedotta dai frammenti dell'indice; e se l'indice non risponde, l'agente procede
con Read/Grep — è una scorciatoia, non una dipendenza.

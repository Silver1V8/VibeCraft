# rag/ — Console HARO Graph-RAG

Indicizzazione (core/indexing), retrieval ibrido e pipeline Explore → Canvas →
Propose (core/) esposti via FastAPI (api/). Entrypoint: `server.py`, `index.py`.

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

**Eccezione:** `POST /ask` (sintesi della risposta RAG) NON passa da
[core/llm.py](core/llm.py) — usa `retrieval.call_llm` (core/retrieval.py), un
secondo layer Ollama/Anthropic/OpenAI più vecchio, mai unificato col primo. Per
il ramo `ollama` replica manualmente `think`/`options.num_ctx` da
`rag_config.yaml` (`llm_settings.ollama_think`/`ollama_num_ctx`): senza,
`qwen3.5` genera in modalità "thinking" completa su un contesto di 32768 token
(default del modello) invece dei 16384 configurati — misurato: 335s a risposta
invece di 47s, e la cache KV più grande spinge il caricamento del modello fuori
dagli 8GB di VRAM in split GPU/CPU. Se si tocca `_ollama_payload` in
`core/llm.py` va aggiornato anche il branch `ollama` di `retrieval.call_llm`.

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
direttamente, fuori dalla coda: **non usare la CLI per (re)indicizzare mentre il
server è attivo** — con il server acceso usa `POST /api/reindex` (eventualmente
`{"full": true}`).

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
golden-set cresce. Non esiste (ancora) una pipeline CI in questo repo: quando
verrà aggiunta, questo comando è lo step da inserire dopo l'avvio del server.

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
sposta il puntatore. La CLI e gli incrementali promuovono a fine build riuscita;
i job **full** del ReindexManager, se `VIBECRAFT_EVAL_GATE=1`, prima di promuovere
eseguono l'**eval del golden-set sulla nuova versione** (in process, soglia
`VIBECRAFT_EVAL_MIN`, default 0.7 — stessa semantica di `eval.run --assert-min`):
sotto soglia la versione resta su disco **non promossa**, il job termina
`completed_not_promoted` col report nell'esito e il server continua a servire la
versione precedente. Se l'eval non è disponibile (golden-set assente, errore), la
promozione è diretta. Il server rileva ogni spostamento di CURRENT
(`maybe_reload_graph`) e ricarica lo snapshot alla prima richiesta.

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

**Limite documentato — Qdrant non è versionato.** I punti della collection hanno
id deterministici e l'incrementale la muta in place: il blue/green copre grafo e
sidecar (ColBERT/chunk/codice), **non** la collection Qdrant. Un rollback
ripristina grafo e sidecar; Qdrant resta all'ultima build e verrà riallineato dal
reindex successivo. È accettabile perché il retrieval filtra/riordina sui chunk
presenti nei sidecar della versione attiva; nel frattempo il check notturno di
integrità può segnalare un mismatch Qdrant↔sidecar **atteso**.

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
buildati e repo esterni dai trigger) e
[code_index/frontend.py](code_index/frontend.py) (semantica React/Angular
sopra il parser TS: componenti, hook, DI, route, template — framework
rilevato dal package.json del progetto, non dall'estensione). L'interfaccia di un parser è una funzione
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

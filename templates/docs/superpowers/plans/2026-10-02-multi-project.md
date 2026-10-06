# VibeCraft multi-progetto — Implementation Plan

> **For agentic workers:** usare `superpowers:subagent-driven-development` per implementare e revisionare i task. Il PM coordina, mantiene il registro e integra; gli implementatori non avviano altri agenti.

**Goal:** creare, aprire e selezionare più progetti nella stessa console, ciascuno con codice, documenti, indice, pipeline e storico separati.

**Architecture:** una sola applicazione FastAPI e un contesto immutabile per ogni progetto. Qdrant e modelli sono condivisi; cartelle, collection, snapshot e operazioni appartengono al progetto identificato esplicitamente dalla richiesta. L'installazione di VibeCraft è distinta dai progetti gestiti.

**Tech Stack:** Python >=3.14, FastAPI, Pydantic, pathlib/dataclasses/json, PyYAML, Qdrant, NetworkX, frontend HTML/CSS/JavaScript esistente, pytest e check Node già disponibili. Nessuna nuova dipendenza prevista.

**Spec:** questo stesso documento, sezioni «Specifica vincolante» e «Criteri di accettazione»; il piano e la specifica sono intenzionalmente raccolti nell'unico Markdown richiesto.

**Autorizzazione:** il 2 ottobre 2026 l'utente ha chiesto questo documento e l'avvio di un PM con GPT 6.1 Sol che coordini gli agenti per eseguire tutti i task. Procedere con sviluppo, test e correzioni senza un ulteriore passaggio di approvazione del piano. Non pubblicare, effettuare push o merge su branch condivisi, cancellare dati o reindicizzare il corpus reale per verificare una modifica.

## Global Constraints

- Preservare codice/documenti/indice attuali e le modifiche preesistenti; lavorare nel worktree isolato assegnato.
- Usare `codex/multi-project` come branch, se il worktree è detached e quel nome è disponibile; non modificare il branch di un altro lavoro.
- Mantenere Python >=3.14 e le dipendenze già dichiarate; riusare helper di atomicità, writer lock, snapshot e version lease.
- Nessuna modifica globale a environment, cwd, costanti importate o configurazione durante una richiesta; nessun monkeypatch di moduli per selezionare il progetto.
- Un identificativo progetto validato identifica storage e collection; il nome visualizzato non costruisce percorsi.
- Auth, CSP, Host guard, controlli cross-site, gate agentic e confinement delle scritture conservano le garanzie attuali.
- Massimo quattro agenti attivi in tutto l'albero: root + PM + due agenti operativi; un reviewer occupa uno di questi due slot.
- Test su cartelle temporanee e collection di prova; ogni eventuale pulizia riguarda esclusivamente dati creati dal test.
- Ponytail full: il minimo cambiamento completo, niente nuove piattaforme, framework UI, scheduler persistenti o filtri multi-tenant sull'indice.

## Review Focus

1. Progetti A/B con stessi nomi file, feature, query e token versione: nessuna risposta o validazione condivisa per collisione.
2. Cambio selezione durante streaming, job o retry auth: il lavoro rimane nel progetto originario e non aggiorna l'interfaccia di B con risultati di A.
3. Registry o manifest corrotti, root mancante e Qdrant indisponibile: errore esplicito, mai fallback a un altro progetto o sovrascrittura del registry.
4. Root con spazi, percorsi Windows/Unix, symlink/junction e traversal: confinement corretto, senza accesso alle cartelle di un altro progetto.
5. Installazione vuota e progetto senza indice: console e gestione progetti disponibili; retrieval indisponibile dichiarato, health del processo distinto dalla disponibilità del progetto.

---

## Specifica vincolante

### 1. Flusso utente e perimetro

- La console mostra sempre progetto selezionato, stato dell'indice, azioni «Nuovo progetto» e «Apri progetto esistente».
- Nuovo progetto: nome non vuoto, cartella creata sotto la directory gestita usando l'ID, `code/`, `docs/`, `changes/`, `database/` pronti. Nessuna indicizzazione automatica di una cartella vuota.
- Apertura: registrare una root VibeCraft esistente con `project.yaml` valido. La scelta di un percorso host è disponibile soltanto con bind locale, riusando il dialogo dell'intake; in Docker si possono registrare solo directory montate nel container. Non clonare o copiare silenziosamente repository esterni: usare l'importazione già presente per popolare `code/`.
- Le schede browser possono selezionare progetti differenti. Selezione conservata per scheda in `sessionStorage`, con `?project=<id>` nei link per refresh, cronologia e collegamenti diretti. Le preferenze visuali e la chiave API rimangono condivise.
- Console, intake, pipeline, grafo, valutazioni, prompt esportati e agenti usano il progetto selezionato.
- La prima versione non include eliminazione progetti, rinomina/spostamento dei dati, ricerca fra progetti, collaborazione multiutente o configurazioni di embedding diverse per progetto.

### 2. Layout, registry e configurazione

```text
<VIBECRAFT_PROJECTS_DIR>/
  projects.json
  <id>/
    project.yaml
    code/
    docs/
    changes/
    database/
      CURRENT
      versions/
      staging/
      pipeline/
      eval/
      reindex_jobs.jsonl
```

- `VIBECRAFT_PROJECTS_DIR` accetta un percorso assoluto; default `<PROJECT_ROOT>/projects`. È storage utente escluso da Git/build context. In Compose usare un volume persistente scrivibile separato.
- ID nuovo: `uuid.uuid4().hex`, 32 caratteri esadecimali minuscoli. Riservare `legacy` per il progetto corrente.
- `project.yaml`: `schema_version: 1`, `id`, `name`; opzionali `settings` per authority/retrieval/eval e verification commands, mantenendo validazione esistente. Vietare override di root, database_dir, collection, segreti, endpoint di rete, binding, ruolo e embedding model dal manifest del progetto.
- `projects.json`: `schema_version: 1`, `projects: [{id, name, root, legacy}]`. Percorsi root canonici assoluti; niente chiavi API. Scrittura atomica e lock cross-processo. Rilevare duplicati di ID/root; errore 409 senza cambiare file. Schema/versione sconosciuti e JSON corrotto sono guasti, non un elenco vuoto.
- Root ordinaria: tutte le cartelle si derivano dalla root; `changes/` e dati del database non sono condivisi. I pesi embedding, Docling e Ollama restano nell'installazione/volumi condivisi e non vengono duplicati nei database dei progetti.
- La configurazione dell'installazione è il default; gli override ammessi del progetto sono applicati a una copia, mai al dict globale. I comandi verification sono configurazione fidata locale: niente endpoint remoto che installi comandi shell, nessuna esecuzione all'apertura del progetto.

### 3. Contratto del contesto e identificazione HTTP

Interfacce proposte, da mantenere stabili tra agenti; una modifica motivata deve essere registrata dal PM prima dei task dipendenti:

```python
@dataclass(frozen=True)
class ProjectContext:
    id: str
    name: str
    root: Path
    code_dir: Path
    docs_dir: Path
    changes_dir: Path
    database_dir: Path
    staging_dir: Path
    collection_name: str
    settings: dict
    legacy: bool = False

class ProjectRegistry:
    def list(self) -> list[ProjectContext]: ...
    def get(self, project_id: str) -> ProjectContext: ...
    def create(self, name: str) -> ProjectContext: ...
    def register(self, root: Path) -> ProjectContext: ...

def get_project(request: Request) -> ProjectContext: ...
def current_snapshot(project: ProjectContext | None = None) -> IndexSnapshot | None: ...
def reload_index_state(project: ProjectContext | None = None) -> str | float | None: ...
```

- Riusare i percorsi HTTP già esistenti e il wrapper fetch di `static/shared.js`: ogni chiamata di progetto invia `X-VibeCraft-Project: <id>`. Questo è il contratto scelto per evitare duplicazioni dei router; il prefisso URL nella discussione iniziale era un esempio.
- Gestione globale: `GET /api/projects`, `POST /api/projects` con `{name}`, `POST /api/projects/register` con `{root}`; registrazione di path host arbitrari protetta da `require_local_bind`; con bind non locale accettare soltanto root canoniche senza link sotto `VIBECRAFT_PROJECTS_DIR`, rifiutando root esterne prima di leggere il manifest.
- `GET /api/projects/{id}` restituisce metadati pubblici e stato indice; non restituisce segreti o percorsi filesystem a client non locali. Stati: `not_indexed`, `ready`, `indexing`, `error`, più booleano `stale` quando calcolabile. Lo stato è derivato, non una seconda verità persistita nel registry.
- Header progetto assente: endpoint storici usano esclusivamente il progetto `legacy`, se registrato, per compatibilità. Non usare il primo progetto disponibile o l'ultimo scelto. Con zero progetti: 409 `project_required`; ID malformato: 422; ID sconosciuto: 404.
- Le pagine HTML usano `?project=<id>`; il server può iniettare un meta project ID usando escaping. Shell e registry funzionano senza indice. Le API che richiedono snapshot restituiscono 409 `project_not_indexed` o 503 per storage/reload guasto.
- I job catturano il ProjectContext al submit; i thread ricevono esplicitamente il contesto. Eventuale ContextVar è un ponte privato per compatibilità, non può sostituire la cattura esplicita in thread, callback, generatori SSE e CLI. Non introdurre proxy Path o default argument dipendenti da un progetto globale.
- Registrazione di progetti non equivale ad ACL multiutente: conservare l'autenticazione attuale, senza promettere autorizzazioni per progetto.

### 4. Runtime, indicizzazione e Qdrant

- Separare risorse condivise (client Qdrant, embedding, limiti di concorrenza) da runtime per ID (snapshot, mtime/reload_error, manager/job e store pipeline).
- Caricare gli indici a richiesta; le richieste catturano uno snapshot coerente e ne mantengono le lease. Limitare la cache di snapshot residenti, inizialmente a 2, con eviction che rimuove riferimenti della cache e non chiude snapshot ancora usati da richieste/job. Riutilizzare le lease attuali; non costruire un nuovo sistema di conteggio se non serve.
- Nuovi alias: `vibecraft_<id>`; collection fisiche: `vibecraft_<id>__<version>`. Manifest, CURRENT, staging ColBERT, rollback, retention, reconciliation e GC sono riferiti al ProjectContext. Il prefisso di GC deve coincidere con l'alias del progetto, mai con `vibecraft_` generico.
- Un job per progetto conserva journal e stato nel suo database. Indicizzazioni serializzate a livello di processo mediante primitiva condivisa per limitare RAM/VRAM, oltre ai writer lock per progetto tra processi; le query restano possibili. Annotare il limite con commento `ponytail:`. Nessun job cambia target perché si seleziona un altro progetto.
- Cache ask: includere project ID oltre a versione e parametri. Cache della collection/versione, analisi del grafo, metadati e altri memo devono essere per progetto o avere ID nella chiave.
- Storicizzare valutazioni, alert e gate nel progetto. Il golden set deve appartenere al progetto: usare `<root>/eval/golden.yaml` se presente, altrimenti lo stato «non valutato» secondo la policy fail-open già esistente. Le baseline legacy continuano a usare i file attuali; mai valutare B con il golden set di A.
- Con ruolo reader: registro leggibile e API di sola lettura, validazione marker immutable per database selezionato, gestione progetti e writer disabilitati come gli endpoint mutanti attuali.

### 5. Pipeline, agenti e interfaccia

- Store validazioni, decisioni, lock feature, eventi, staging, import plans e job di generazione/raffinazione separati per progetto. Stesso feature slug in A/B è valido.
- `dev_type` elenca le sottocartelle di `code/` del progetto; verifica eseguita lì con argv senza shell. Prompt e riferimenti alle fonti riportano il progetto originario.
- `agent_bridge.py` distingue INSTALL_ROOT (script/runtime di VibeCraft) e project root (cartella leggibile/operativa). Hook di scrittura confina in `project.code_dir`; letture non attraversano altri progetti, segreti o `.git`.
- Ogni MCP avviato da un agente riceve `VIBECRAFT_PROJECT_ID`; il server MCP invia l'header progetto fisso per tutta la sessione. Conservare loopback-only, limiti e strumenti in sola lettura.
- Il wrapper fetch cattura l'ID una volta all'avvio della richiesta, incluso il retry dopo 401; supportare string, URL e Request senza perdere body/header/AbortSignal. Non allegare ID/credenziali a URL esterni.
- `workspace.js` conserva le pagine con chiave `(project_id, pathname)`; gli iframe ricevono l'ID originario, senza leggerlo da una selezione globale mutable al momento del fetch. Impostare un limite di 2 progetti con pagine conservate per scheda; non eliminare frame con run/stream attivo, segnalare il limite se necessario.
- A cambio progetto, risultati tardivi e stream aggiornano solo le pagine del progetto originario. Tornando ad A si ritrova lo stato conservato finché residente; nessuna promessa di ripristino di chat non persistite dopo chiusura browser.
- Controlli accessibili con label, tastiera e focus; nomi progetto resi con textContent/escaping, niente innerHTML da manifest.

### 6. Compatibilità e migrazione

- Registrare il progetto attuale come `legacy` senza spostare dati, rinominare collection, riscrivere manifest o reindicizzare. Usa i percorsi attuali di config, incluso DATABASE_DIR da env, staging storico, changes e nome collection attuale.
- Il bootstrap legacy è idempotente: eseguirlo quando esistono artefatti o sorgenti legacy significative; in un'installazione totalmente vuota non inventare un progetto. Dopo la prima inizializzazione del registry non rigenerarlo perché qualcuno lo ha svuotato intenzionalmente.
- CLI `index.py --project <id>`: selezione prima delle operazioni, stesso contesto per rebuild/delta/status/integrity/rollback/migrazione ColBERT. Senza flag mantiene la semantica legacy.
- MCP esterno: `VIBECRAFT_PROJECT_ID` seleziona il progetto; senza env resta legacy, nessuna dipendenza dal browser.
- Docker: nuovi progetti persistono fra restart/rebuild; il volume legacy e i mount `docs/`/`code/` rimangono utilizzabili. Modificare healthcheck per disponibilità del processo anche a zero progetti, mantenendo stato corpus nei dettagli di health/API.

## Mappa dei file e responsabilità

| Area | File principali da leggere/modificare |
|---|---|
| Progetti | nuovo `rag/core/projects.py`, nuovo `rag/api/routes_projects.py`, `rag/api/models.py` |
| Config/runtime | `rag/core/config.py`, `rag/api/deps.py`, `rag/server.py`, `rag/core/ask_cache.py` |
| Storage/indice | `rag/core/artifacts.py`, `colbert_store.py`, `writer_lock.py`, `qdrant_versions.py`, `indexing.py`, `rag/api/reindex.py`, `routes_reindex.py` |
| Retrieval/grafo/health | `rag/api/routes_retrieval.py`, `routes_graph.py`, `routes_health.py`, `rag/core/retrieval.py`, `graph_ops.py` |
| Pipeline/intake | `rag/api/routes_pipeline.py`, `routes_intake.py`, `rag/core/pipeline*.py`, `intake*.py`, `project_import.py`, `project_brief.py`, `doc_generation.py`, `feature_archive.py`, `drift*.py`, `verification.py`, `eval*.py` |
| Agent/CLI/MCP | `rag/agent_bridge.py`, `rag/agent_runners.py`, `rag/mcp_server.py`, `rag/index.py`, script operativi che leggono directory/collection |
| UI | `rag/static/shared.js`, `shared.css`, `pages/workspace.js`, altri page script, `rag/templates/workspace*.html` e template effettivamente serviti, `rag/api/routes_pages.py` |
| Distribuzione | `docker-compose.yml`, `Dockerfile`, `.gitignore`, `.dockerignore`, `rag/.env.example`, README principali, `.github/workflows/ci.yml` |

Questa mappa non sostituisce la ricerca dei chiamanti. Prima di cambiare un percorso/default, cercare tutti gli import di PROJECT_ROOT/CODE_DIR/DOCS_DIR/CHANGES_DIR/DATABASE_DIR/COLLECTION_NAME, i default arguments e le cache. In particolare staging ed eval oggi non dipendono sempre da DATABASE_DIR.

## Task esecutivi

Ogni task: aggiungere il test che fallisce, verificarne il fallimento pertinente, implementare, eseguire test mirati e lint, consegnare report al PM, ottenere review e correggere prima dei task dipendenti. Non modificare test storici solo per nascondere regressioni. Il PM è l'unico a effettuare commit quando due agenti condividono il worktree; stage soltanto i file del task verificato.

### Task 1: Registry, contesto e bootstrap legacy

**Dipendenze:** nessuna. **Modello:** gpt-6.1-sol/high.
**File:** `core/projects.py`, `core/config.py`, `tests/test_projects.py` (nuovo), `.gitignore`, `.dockerignore`.
**Produce:** ProjectContext/ProjectRegistry e un resolver legacy; schema sopra, writer lock/atomic write esistenti.

- [x] Test `test_create_project_layout_and_unique_ids`: A/B hanno ID, root, database e collection diversi; stesso nome visualizzato consentito.
- [x] Test registro concorrente, duplicato, corrotto/versione sconosciuta, manifest non valido, symlink/junction e nomi con HTML; nessuna perdita di record.
- [x] Test `test_legacy_registration_preserves_paths_and_collection`: checksum degli artefatti e nome collection invariati dopo bootstrap ripetuto.
- [x] Implementare interfacce; separare INSTALL_ROOT dai percorsi del progetto; override limitati; nessun nuovo database per registry.
- [x] Eseguire da `rag/`: `uv run --frozen pytest tests/test_projects.py -rs`; review dello schema e delle garanzie filesystem.

### Task 2: Artefatti, collection e indicizzazione per progetto

**Dipendenze:** 1. **Modello:** gpt-6-astra/high.
**File:** `core/artifacts.py`, `colbert_store.py`, `writer_lock.py`, `qdrant_versions.py`, `indexing.py`, `tests/test_project_indexing.py` (nuovo), test indice/blue-green esistenti.
**Consume:** ProjectContext. **Produce:** funzioni storage/index che accettano `project: ProjectContext | None = None`, con None esclusivamente legacy; namespace e lock coerenti end-to-end.

- [x] Test build/delta/promote/rollback A/B con stessi token versione e nomi documento; CURRENT/manifest/vettori restano separati.
- [x] Test `test_gc_never_deletes_other_project_collections`, includendo candidato A non ancora manifestato e collection legacy.
- [x] Test lease: un reader di A mantiene snapshot precedente mentre A promuove; operazioni B non invalidano lease A.
- [x] Propagare contesto in tutti i chiamanti; rimuovere dipendenze dai path globali nei percorsi non legacy, inclusi temporanei ColBERT e manifest fingerprint.
- [x] Eseguire suite mirata storage/indice/versioni e regressioni legacy; integrare prova con Qdrant reale su sole collection temporanee.

### Task 3: Runtime HTTP, retrieval, cache e health

**Dipendenze:** 1, 2. **Modello:** gpt-6-astra/high.
**File:** `api/deps.py`, `server.py`, `routes_projects.py`, `routes_retrieval.py`, `routes_graph.py`, `routes_health.py`, `core/ask_cache.py`, `tests/test_project_api.py` (nuovo), `tests/test_project_runtime.py` (nuovo).
**Produce:** get_project/current_snapshot/reload_index_state, runtime per ID, API registry e contratto header; readiness separata.

- [x] Test zero progetti e senza indice: shell e registry 200, retrieval 409; progetto guasto non blocca elenco/altro progetto.
- [x] Test header mancante/malformato/sconosciuto e auth/cross-site/local-bind; nessun fallback a B.
- [x] Test cache A/B con stessa query/versione e contenuti diversi; stato grafo/reload/version-cache isolato.
- [x] Test richieste concorrenti e eviction con snapshot in uso; modello/client pesanti condivisi, non ricaricati per ogni progetto.
- [x] Collegare tutti gli endpoint dati al contesto catturato una volta; metadata ID/versione coerenti anche in streaming.
- [x] Eseguire nuovi test e suite retrieval/graph/health/cache/security interessate; review su isolamento e ciclo vita.

### Task 4: Job, intake, pipeline e valutazioni

**Dipendenze:** 3. **Modello:** gpt-6.1-sol/high; escalation astra per bug di concorrenza persistenti.
**File:** `api/reindex.py`, `routes_reindex.py`, `routes_pipeline.py`, `routes_intake.py`, moduli core associati nella mappa, `tests/test_project_workflows.py` (nuovo).
**Consume:** ProjectContext e runtime. **Produce:** store/manager per progetto, callback con contesto esplicito, coda di indicizzazione limitata.

- [x] Test due feature omonime con validazioni/decisioni/gate diversi; gate valido A non autorizza B.
- [x] Test upload/approve/archive/generation/refine A: scritture soltanto nelle directory A; import plan A inutilizzabile da B.
- [x] Test job A avviato, scelta B, completamento A: snapshot/journal/alert aggiornano A soltanto; job ID A non consultabile sotto B.
- [x] Test serializzazione indicizzazioni e rilascio dopo errore; nessun deadlock con writer lock o perdita di job.
- [x] Test golden set/storico per progetto e comportamento assenza golden; conservare policy legacy.
- [x] Eseguire nuovi test e suite pipeline/intake/reindex/verification/eval pertinenti; review della propagazione nei thread/generatori.

### Task 5: Agenti, CLI e MCP

**Dipendenze:** 3; integrazione finale con 4. **Modello:** gpt-6.1-sol/high.
**File:** `agent_bridge.py`, `agent_runners.py`, `mcp_server.py`, `index.py`, script operativi effettivamente interessati, `tests/test_project_tools.py` (nuovo).
**Consume:** contesto; niente accesso diretto a selezione UI. **Produce:** --project e VIBECRAFT_PROJECT_ID, runner e hook confinati.

- [x] Test CLI status/integrity/delta/full/rollback dispatchano il progetto scelto; flag assente continua legacy.
- [x] Test runner cwd/code_root A, hook blocca B e traversal/symlink; script MCP trovato in INSTALL_ROOT anche con progetto esterno.
- [x] Test MCP emette header fisso A e conserva auth/loopback/read-only; nessuna chiave o path sensibile nei prompt/log.
- [x] Test impostazioni e retry di agenti simultanei A/B non mutano dict AGENT_MODES/config condivisi.
- [x] Eseguire nuovi test e suite MCP/agent/CLI esistenti con provider simulati nei gate finali; incidenti di avvio precedenti documentati nel report, senza claim di zero contatti di rete.

Ruling PM verificato: Codex/Cursor integrati non avviano processi finché l'isolamento delle letture non è verificato; prompt esportati e MCP esterno con ID esplicito restano disponibili. SDK/local applicano i guard; le scansioni SDK di un subtree con .git/segreti/link sono negate, mentre Read e scansioni di directory sicure restano utilizzabili. Compatibilità e limiti provati nel report Task5.

### Task 6: Selettore e workspace nel browser

**Dipendenze:** 3; può procedere in parallelo a 4 o 5 con proprietà esclusiva dei file UI.
**Modello:** gpt-6.1-sol/high.
**File:** `static/shared.js`, `shared.css`, `pages/workspace.js`, template/pagine serviti, `api/routes_pages.py`, `tests/navigation_workspace.cjs`, nuovo `tests/projects_workspace.cjs`.
**Produce:** selezione per scheda, nuovo/apri progetto, stato indice, fetch e iframe con identità stabile.

- [x] Test browser due schede A/B, refresh/back/forward e link diretto: selezioni indipendenti.
- [x] Test nuova creazione e apertura, errori leggibili e accessibilità tastiera; nomi HTML restano testo.
- [x] Test fetch string/URL/Request, header esplicito, retry 401 e AbortSignal: il progetto resta quello iniziale; nessun header verso origin esterna.
- [x] Test stream/job A continua mentre si visualizza B; iframe A non consuma B; limite delle pagine conservate non interrompe un agente attivo.
- [x] Riutilizzare stile e navigazione esistenti; niente framework o ridisegno non richiesto.
- [x] Eseguire check Node e smoke browser usando runtime Playwright disponibile, senza aggiungere dipendenza product; review dei risultati tardivi.

### Task 7: Distribuzione, istruzioni e CI

**Dipendenze:** 1, 3, 5, 6; completamento dopo 4.
**Modello:** gpt-6.1-sol/medium; gpt-6-luna/medium soltanto per edit documentali meccanici.
**File:** Compose/Dockerfile/env example/README/CI/test distribuzione interessati.

- [x] Volume progetti persistente, permessi non-root, pesi condivisi, legacy mounts conservati; `.dockerignore` esclude i dati dei nuovi progetti.
- [x] Healthcheck passa con console funzionante a zero progetti; API espone readiness del corpus distinta.
- [x] Documentare nuovo/apri/seleziona, --project, MCP env, storage/backup, percorso Docker, registrazione legacy e limiti della prima versione.
- [x] Collegare nuovi check ai gate esistenti; nessun download di pesi o build pesante duplicato se il test non lo richiede.
- [x] Verificare test statici distribuzione e smoke container se Docker disponibile; altrimenti registrare il limite senza dichiarare prova riuscita.

### Task 8: Integrazione completa e review finale

**Dipendenze:** tutti. **Modello implementazione:** gpt-6.1-sol/high; **review finale indipendente:** gpt-6-astra/high.
**File:** soltanto correzioni necessarie, test integrazione progetto, report finale del PM.

- [x] Fixture A/B temporanee con stessi path/feature/versioni e testi distintivi: creare, indicizzare, chiedere, importare, validare, avviare runner simulato, selezionare B e tornare A.
- [x] Eseguire un vero smoke Qdrant su collection di prova isolate: build A/B, retrieval diverso, rebuild/rollback/GC A, B ancora leggibile e integro.
- [x] Eseguire `uv run --frozen ruff check .` e `uv run --frozen pytest -rs` da rag; equivalenti del gate scripts/ci.sh con PYTHONUTF8=1 su Windows.
- [x] Eseguire check Node già in CI più navigation_workspace/projects_workspace; smoke UI reale con servizi/provider simulati.
- [x] Reviewer confronta diff complessivo e criteri sotto; difetti di isolamento/sicurezza/dati sono bloccanti, correggerli e rieseguire i test pertinenti.
- [x] Compilare report con commit/branch, file, test eseguiti e skip motivati, limiti reali; marcare complete solo le caselle provate. Nessun push/publish/merge automatico.

## Criteri di accettazione

- [x] AC1: dalla console si creano e si aprono almeno due progetti; ciascuno ha code/docs/changes/database distinti.
- [x] AC2: file e query omonimi producono risultati riferiti esclusivamente al progetto richiesto; cache/graph/reload non contaminano altri progetti.
- [x] AC3: full/delta/rollback/retention/GC A non modificano artifact, CURRENT, alias o collection B.
- [x] AC4: intake/pipeline/gate/validazioni/storico/lock e job separati; stessa feature consentita in A/B.
- [x] AC5: cambio selezione, streaming, retry e due schede non cambiano il target di operazioni già partite.
- [x] AC6: agenti leggono il progetto corretto e scrivono solo nel suo code; MCP e CLI selezionano lo stesso progetto esplicito.
- [x] AC7: console utilizzabile senza indice; stato non indicizzato/guasto dichiarato, senza fallback silenzioso.
- [x] AC8: progetto attuale registrato in-place, senza perdita dati, nuova build o rename della collection.
- [x] AC9: Docker mantiene progetti dopo restart; auth/CSP/Host guard/local-bind e modalità reader conservano le garanzie.
- [x] AC10: suite pertinente, lint, smoke Qdrant isolato e smoke browser verificati; eventuali prove impedite dall'ambiente restano esplicitamente non verificate.

Accettazione finale 5 ottobre 2026: review indipendente Astra PASS, nessun finding bloccante aperto; suite completa2348pass/20filelinkskipWindows, lint e smoke reali Qdrant/browser/Docker verificati. AC6 vale con il ruling native-launch sopra (SDK/local, export e MCP esterno disponibili); AC9/10 non equivalgono a fresh Docker build o esecuzione GitHub Actions. Dettagli/prove/limiti nel report finale e nella review Task8.

## Istruzioni operative per il PM

1. Modello PM obbligatorio `gpt-6.1-sol`, reasoning high. Leggere questo documento, il codice e le skill pertinenti; l'utente ha già scelto l'esecuzione a subagenti.
2. Usare il worktree `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft`. Non lavorare nel checkout originale e non cambiare i suoi file preesistenti sporchi.
3. All'avvio creare `docs/superpowers/plans/2026-10-02-multi-project-progress.md` nel worktree: identità piano, baseline, tabella task/stato/agente/file/modello, decisioni, prove, blocchi reali. Mantenerlo dopo la fine: è il resoconto richiesto per seguire l'esecuzione.
4. Baseline repository: HEAD `34b46dfeabcff05820240a1241baae1a215d3e1b`; nel checkout originale erano già modificati `.claude/launch.json`, `rag/eval/candidates.yaml`, `rag/uv.lock`; non tracciati `rag/database/.reader-locks/`, `rag/scripts/install_mcp.ps1`. Non includerli nei commit. Il worktree non include corpus/indice privati ignorati: usare fixture e non interpretarli come dati cancellati.
5. Preparare environment senza installazioni superflue: uv è disponibile; valutare interpreter/venv esistenti. `uv sync --frozen` solo se necessario, senza toccare il lockfile dell'utente. PYTHONUTF8=1 per i test Windows. Registrare fallimenti baseline e continuare sulle parti indipendenti quando la causa è chiaramente preesistente/ambientale.
6. Prima del primo dispatch verificare le dipendenze/file condivisi e fissare le interfacce. Ordine 1→2→3; poi UI 6 in parallelo a un solo task backend 4/5; 7 e 8 dopo integrazione. Due agenti non modificano lo stesso file in parallelo.
7. Usare `collaboration.spawn_agent` con `fork_turns: none`, `model` e `reasoning_effort` espliciti; assegnare brief, file posseduti, interfacce e test. Worker senza subagenti e senza commit quando altro worker scrive; il PM integra e committa serialmente.
8. Conservare report task in file, non incollare l'intero piano in ogni dispatch. Review indipendente dopo task sostanziali; UI e backend possono essere revisionati quando l'altro slot è libero. Scegliere gpt-6.1-sol per integrazione, astra per isolamento/concorrenza/review finale, luna soltanto per compiti meccanici davvero delimitati.
9. Non fermarsi fra task per chiedere di proseguire. Risolvere scelte reversibili con decisione motivata nel registro; interrompere soltanto per operazioni distruttive/irreversibili o informazione indispensabile mancante senza alternativa utile.
10. Aggiornare root con avvio, milestone, blocchi e conclusione mediante collaboration; root mantiene la comunicazione con l'utente. Nessuna nuova chat sidebar, messaggio esterno o automazione richiesta.
11. Dopo compaction riprendere dal registro e da git log; non rifare i task completati. Alla fine riportare ciò che è effettivamente implementato, verificato e ancora impedito.

## Comandi di riferimento

Da `rag/`, ambiente UTF-8; non usare un Qdrant di produzione per test con cleanup:

```powershell
$env:PYTHONUTF8 = '1'
uv run --frozen ruff check .
uv run --frozen pytest -rs
node tests/intake_excel_preview.cjs
node tests/pipeline_dryrun_escape.cjs
node tests/dashboard_graph_escape.cjs
```

I test browser workspace richiedono un server di prova e Playwright disponibile come descritto negli script; il PM registra comando, fixture/servizi e risultati. Per Qdrant reale usare servizio o istanza dedicata ai test e prefissi univoci; non l'indice legacy dell'utente.

# rag/ — Console HARO Graph-RAG

Indicizzazione (core/indexing), retrieval ibrido e pipeline Explore → Canvas →
Propose (core/) esposti via FastAPI (api/). Entrypoint: `server.py`, `index.py`.

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

**2. Batch notturno di fallback (guardrail anti-deriva).**
L'incrementale può accumulare deriva sui code-link; lo script notturno
[scripts/nightly_consistency.ps1](scripts/nightly_consistency.ps1) (variante
POSIX `.sh`) esegue `index.py --check-graph` (grafo incrementale vs full
rebuild) e, **solo se trova drift**, lancia un full rebuild che riallinea tutto.
Schedulalo di notte con Windows Task Scheduler (`pwsh -File
scripts/nightly_consistency.ps1`) o cron. Dopo il rebuild il server rileva
`graph.json` cambiato su disco e ricarica gli artefatti alla prima richiesta
(`maybe_reload_graph`).

## Artefatti dell'indice: formati sicuri e ispezionabili

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

`save_artifacts()` scrive **solo** questi formati. In lettura `load_artifacts()`
ricade sui vecchi pickle (`*.pkl`) se i nuovi file non esistono ancora, loggando
un warning che invita a re-indicizzare (`python index.py`) per migrare — il
prossimo full/incremental rebuild emette i nuovi formati. Il manifest
(`index_manifest.json`) elenca gli hash SHA-256 di ogni file artefatto
(`artifact_hashes`), così il check di coerenza può validarne anche l'integrità.

## Code index: aggiungere un nuovo linguaggio

L'estrazione dei simboli dal codice generato (`code/`) vive in
[code_index.py](code_index.py); i parser tree-sitter in
[code_index_ts.py](code_index_ts.py) (TS/TSX/JS/JSX/Svelte),
[code_index_java.py](code_index_java.py) (Java + pom.xml/build.gradle +
Kogito .bpmn/.dmn), [code_index_csharp.py](code_index_csharp.py)
(C#/.NET + .csproj/packages.config) [code_index_razor.py](code_index_razor.py)
(famiglia Razor: view MVC, Razor Pages, componenti Blazor) e
[code_index_sql.py](code_index_sql.py) (SQL: T-SQL, PL/SQL, generico —
archi semantici READS/WRITES/EXECUTES e ponte codice→stored procedure
dai parser C#/Java) [code_index_config.py](code_index_config.py)
(file di configurazione riconosciuti per nome: web/app.config,
appsettings*.json, package.json, WSDL/XSD — secret sempre mascherati,
nodi collegati al progetto di appartenenza) e
[code_index_shell.py](code_index_shell.py) (script operazionali Bash e
PowerShell via tree-sitter — archi EXECUTES script→script e riferimenti
incrociati verso i progetti/file invocati) e
[code_index_ci.py](code_index_ci.py) (pipeline GitLab CI / Azure DevOps
riconosciute per nome — nodi pipeline/job, archi verso template, progetti
buildati e repo esterni dai trigger) e
[code_index_frontend.py](code_index_frontend.py) (semantica React/Angular
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
2. **Parser** — implementa in `code_index_ts.py` una funzione con
   l'interfaccia sopra. Per linguaggi C-like spesso basta estendere
   `_DECL_KINDS`/`_walk_symbols`; per formati contenitore (vedi
   `svelte_symbols`) localizza i blocchi di codice con la grammatica del
   formato e ri-parsa il contenuto con la grammatica del linguaggio interno.
3. **Dispatch** — in `code_index.py` registra l'estensione in `CODE_EXTS`,
   mappa suffisso → linguaggio in `_PARSER_LANG`, imposta il default in
   `_PARSER_DEFAULTS` e aggiungi il ramo in `_extract`. Il flag
   `code_parsers.<lang>` in [rag_config.yaml](rag_config.yaml) permette di
   tornare a un'eventuale implementazione alternativa senza deploy.
4. **Test di equivalenza** — estendi
   [tests/test_ts_parser_equivalence.py](tests/test_ts_parser_equivalence.py)
   con un corpus del linguaggio: se sostituisci un parser esistente, il nuovo
   deve estrarre almeno tutti i simboli del vecchio (zero `persi`).

**Secondo esempio del pattern — Java** (`code_index_java.py`): grammatica
`java` dal language-pack; estrazione framework-aware via annotation (JAX-RS
`@Path`+`@GET/...` → `endpoint`, CDI `@Inject` → nodo `field` + dep verso il
bean, messaging `@ConsumeEvent/@Incoming/@Outgoing` → `listener`), stesso
pattern dei decoratori FastAPI nel parser Python. Gli artefatti di progetto
non hanno bisogno di tree-sitter: pom.xml/.bpmn/.dmn sono XML (ElementTree),
build.gradle è regex best-effort. Niente test di equivalenza: non esisteva un
parser Java precedente (i test sono su un mini-progetto fittizio in
[tests/test_java_index.py](tests/test_java_index.py)).

**Esempio completo del pattern — C#/.NET** (`code_index_csharp.py`): mostra
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

**Variante senza grammatica — Razor** (`code_index_razor.py`): quando la
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
dietro flag; TODO datato in `code_index.py` per la loro rimozione.

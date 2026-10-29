Italiano | [English](../README.en.md)

> Documentazione operativa sotto `rag/docs/`: **non** è corpus RAG (il corpus è `docs/` del progetto). Stesso schema degli ADR. Italiano canonico; l'inglese resta un indice breve in `rag/README.en.md`.

[← Indice operativo](../README.md)

# Grafo, drift e code index

## Check drift (Step 4): rilievi verificati, verdetto calcolato

`core.drift_check.check_drift` orchestra, `core/drift.py` contiene la logica pura. Il check
storico passava all'LLM il solo Canvas e 40.000 caratteri di codice troncati alla cieca, e
ne mostrava il testo libero: su BE1 segnalava come drift requisiti imposti dalla Spec,
librerie "mancanti" che stavano nei file tagliati, verdetti NO che si davano torto da soli.

1. **Contratto = Canvas + Spec**, con precedenza dichiarata alla Spec: uno scenario vince
   sul Canvas, un punto aperto non è un difetto.
2. **Lotti, non troncamento**: i file (prima quelli citati dal Canvas) sono distribuiti in
   lotti entro `ollama_num_ctx`; un file grande è diviso in parti. Ogni prompt elenca i file
   che il modello *non* vede. Test e migrazioni generate restano fuori dai lotti.
3. **Pre-check deterministico**: le tecnologie in grassetto nel Canvas sono cercate tra le
   dipendenze dei manifest (csproj, pom, gradle, package.json, dal code index) e date al
   modello come fatti; un'alternativa tecnica già soddisfatta ("MinIO o Azure") non può
   diventare una mancanza.
4. **Rilievi JSON verificati in Python**: la citazione del codice deve esistere nei file
   visti; ogni "mancanza" porta dei termini che non devono comparire nel codice (commenti e
   test esclusi); il JSON malformato del modello locale si recupera rilievo per rilievo.
5. **Controllo di copertura** sull'indice dei simboli di tutto il progetto.
6. **Riesame mirato** di ogni drift sopravvissuto: scenario intero, codice citato, indice
   dei simboli e righe che citano gli identificativi del requisito; esito `violato`,
   `rispettato` (scartato) o `punto_aperto` (declassato ma visibile).
7. **Verdetto calcolato**: `✅ NESSUN DRIFT`, `⚠️ DRIFT RILEVATO`, `⚠️ PUNTI APERTI DA
   DECIDERE` (requisito assente ma aperto nella Spec) o `⚠️ VERIFICA INCOMPLETA` (risposta
   non interpretabile). La UI colora lo Step 4 da questa prima riga; gli scartati restano
   nel report con il motivo.

Costo: un lotto ogni ~17.500 caratteri di codice, più copertura e riesami. Su BE1 servono
40–85 s con qwen3.5:9b sulla RTX 3070 Ti, contro i 12–20 s del check storico.

Misurato il 2026-09-16 su BE1 (5 run per caso, temperatura 0.1):

| Caso | Check storico | Check attuale |
|---|---|---|
| Codice conforme | NO in 2/2 run, 6–9 rilievi falsi (file "mancanti" solo perché troncati) | ✅ in 4/5 run; 1 run con 1 falso positivo |
| Copia senza export Excel (vero drift) | Excel non citato; report "NO" chiuso da "✅ NESSUN DRIFT" | segnalato in 5/5 run (4 DRIFT, 1 PUNTI APERTI) |

Limite noto: il falso positivo residuo è sempre una "mancanza" con un nome inventato di cui
il riesame non riconosce l'implementazione altrove. Il modello locale resta un giudice
debole: il report mostra sempre gli scartati e il loro motivo, così l'esito si verifica a mano.


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
3. il check drift (`core.drift_check`, scansione per il confronto codice↔canvas).

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
`[testo](../url)`, destrutturazioni JS `[k, v]`, literal `'[REDACTED]'`, classi
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
Test in [tests/test_chunking.py](../tests/test_chunking.py).


## Code index: aggiungere un nuovo linguaggio

L'estrazione dei simboli dal codice generato (`code/`) vive in
[code_index/](../code_index/__init__.py); i parser tree-sitter in
[code_index/ts.py](../code_index/ts.py) (TS/TSX/JS/JSX/Svelte),
[code_index/java.py](../code_index/java.py) (Java + pom.xml/build.gradle +
Kogito .bpmn/.dmn), [code_index/csharp.py](../code_index/csharp.py)
(C#/.NET + .csproj/packages.config) [code_index/razor.py](../code_index/razor.py)
(famiglia Razor: view MVC, Razor Pages, componenti Blazor) e
[code_index/sql.py](../code_index/sql.py) (SQL: T-SQL, PL/SQL, generico —
archi semantici READS/WRITES/EXECUTES e ponte codice→stored procedure
dai parser C#/Java) [code_index/config.py](../code_index/config.py)
(file di configurazione riconosciuti per nome: web/app.config,
appsettings*.json, package.json, WSDL/XSD — secret sempre mascherati,
nodi collegati al progetto di appartenenza) e
[code_index/shell.py](../code_index/shell.py) (script operazionali Bash e
PowerShell via tree-sitter — archi EXECUTES script→script e riferimenti
incrociati verso i progetti/file invocati) e
[code_index/ci.py](../code_index/ci.py) (pipeline GitLab CI / Azure DevOps
riconosciute per nome — nodi pipeline/job, archi verso template, progetti
buildati e repo esterni dai trigger),
[code_index/frontend.py](../code_index/frontend.py) (semantica React/Angular
sopra il parser TS: componenti, hook, DI, route, template — framework
rilevato dal package.json del progetto, non dall'estensione) e
[code_index/docker.py](../code_index/docker.py) (artefatti di containerizzazione
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
3. **Dispatch** — in `code_index/` registra l'estensione in `CODE_EXTS` e
   aggiungi un ramo `if suffix == "...":` in `_extract` che chiama il parser
   direttamente: è il pattern che java/csharp/razor/sql/shell già usano, non
   un flag di configurazione — un dispatch pluggable per-linguaggio (`_PARSER_LANG`
   / `_PARSER_DEFAULTS`) esisteva solo per TS/JS/Svelte durante la migrazione da
   regex a tree-sitter, ed è stato rimosso con quella (A12, 2026-09-03: nessun
   linguaggio ha più due implementazioni fra cui scegliere). Se un giorno un
   linguaggio ne avesse davvero due, `code_parsers.<lang>` in
   [rag_config.yaml](../rag_config.yaml) resta il posto dove dichiarare quale.
4. **Test diretti** — un corpus rappresentativo del linguaggio con le coppie
   (kind, name) attese per file, come [tests/test_ts_parser.py](../tests/test_ts_parser.py):
   se sostituisci un parser esistente, verifica sul corpus che il nuovo trovi
   almeno tutto ciò che trovava il vecchio, poi sostituisci le attese.

**Secondo esempio del pattern — Java** (`code_index/java.py`): grammatica
`java` dal language-pack; estrazione framework-aware via annotation (JAX-RS
`@Path`+`@GET/...` → `endpoint`, CDI `@Inject` → nodo `field` + dep verso il
bean, messaging `@ConsumeEvent/@Incoming/@Outgoing` → `listener`), stesso
pattern dei decoratori FastAPI nel parser Python. Gli artefatti di progetto
non hanno bisogno di tree-sitter: pom.xml/.bpmn/.dmn sono XML (ElementTree),
build.gradle è regex best-effort. Niente test di equivalenza: non esisteva un
parser Java precedente (i test sono su un mini-progetto fittizio in
[tests/test_java_index.py](../tests/test_java_index.py)).

**Esempio completo del pattern — C#/.NET** (`code_index/csharp.py`): mostra
tutti i pezzi in un modulo solo. Grammatica `csharp` dal language-pack (punto
1 della guida); simboli con namespace nel meta `package` e using come `deps`;
estrazione framework-aware via attributi, runtime-agnostica: [HttpGet]/
[HttpPost]/[Route] (ASP.NET Core) e [OperationContract] su [ServiceContract]
(WCF, .NET Framework legacy) → kind `endpoint`; file di progetto senza
tree-sitter: `.csproj` (PackageReference/ProjectReference → DEPENDS_ON tra
progetti, base dell'impact analysis multi-repo) e `packages.config` legacy;
dispatch + flag `code_parsers.csharp` (punto 3); corpus fittizio in
[tests/test_csharp_index.py](../tests/test_csharp_index.py) (punto 4, senza
equivalenza: parser nuovo). Fuori scope per questo modulo: Razor/.cshtml, che
ha il proprio scanner ibrido dedicato (`code_index/razor.py`, vedi sotto) —
la grammatica tree-sitter Razor è immatura, da qui la scelta di uno scanner
invece che una nuova grammatica. VB.NET resta fuori scope per entrambi.

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

Il parser regex storico per TS/JS/Svelte (`_js_symbols`) è stato **rimosso**
(A12, 2026-09-03): 53 giorni senza incidenti dalla migrazione a tree-sitter
del 2026-07-12 erano il segnale che il debito poteva chiudersi per davvero,
non solo ridatarsi. `code_index.ts` (tree-sitter) è oggi l'unica
implementazione per quei tre linguaggi.


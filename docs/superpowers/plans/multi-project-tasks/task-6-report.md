# Task 6 — Selettore e workspace multiprogetto

Implementazione client stabile, gate Node/browser con API simulate verdi. **Smoke FastAPI/API reale pending: handoff Task 8**, dopo review Task 3 e integrazione backend. Nessun modello, agente o corpus reale usato; nessuna modifica a deps/server/runtime/backend condiviso, nessun commit/stage.

## Comportamento

- Progetto per scheda: `sessionStorage` e `?project=<id>`; link, refresh e back/forward conservano l'identità. Soltanto `legacy` è un default di compatibilità; nessun fallback al primo progetto disponibile o da ID sconosciuto.
- Selettore, nuovo/apri, stato indice aggiornato per il progetto visualizzato; dialog nativo con label, Invio, Escape e ripristino focus. Errori `{detail:{code,message}}` leggibili. Nomi progetto resi esclusivamente con `textContent`.
- `read_only` disabilita nuovo/apri; nessuna indicizzazione automatica. Apertura usa root esistente e riusa `POST /api/intake/project/browse-path`; il pulsante nativo è visibile soltanto con metadato server `local-bind=true`. Il backend deve mantenere browse globale anche a zero progetti: segnalato al PM per Task 4.
- Wrapper fetch string/URL/Request: progetto e header iniziali catturati una volta, clone Request per retry 401, body/header/AbortSignal conservati. Management e liveness globali; nessuna aggiunta di ID/API key verso URL esterna.
- Frame con ID fissato prima dell'esecuzione script; cache `(project_id,pathname)`, massimo due progetti residenti. Stream, azioni async, scorciatoie tastiera e polling reindex mantengono il frame residente. Errori polling temporanei non dichiarano finito un job; completed/404 rilasciano il vincolo. Se entrambi i progetti lavorano, il terzo è rifiutato con messaggio accessibile.
- Stile, vendor e CSP esistenti conservati; nessuna nuova dipendenza o framework.

## File esatti

1. `rag/api/routes_pages.py` — metadati project escaped/local-bind nella shell/pagine.
2. `rag/static/shared.js` — identità, fetch/retry, link, contatore operazioni.
3. `rag/static/shared.css` — barra/dialog e regola hidden per browse.
4. `rag/static/pages/workspace.js` — gestione progetti e cache frame.
5. `rag/static/pages/dashboard.js` — retention per Ctrl+Invio.
6. `rag/static/pages/pipeline.js` — retention Ctrl+Invio e polling reindex.
7. `rag/templates/workspace.html` — controlli accessibili.
8. `rag/tests/projects_workspace.cjs` — Node + Edge con server HTTP fixture.
9. `rag/tests/navigation_workspace.cjs` — fixture risposta frozen e href con project; tutte le asserzioni pregresse conservate.
10. `rag/tests/intake_excel_preview.cjs` — sola normalizzazione CRLF per lettura shared.
11. `rag/tests/pipeline_dryrun_escape.cjs` — idem.
12. `rag/tests/dashboard_graph_escape.cjs` — idem.
13. `rag/tests/pipeline_agent.cjs` — adapter baseline autorizzato PM: expected `max_attempts:1` e nodo fixture `agent-attempts-select`.
14. `rag/static/pages/graph_analysis.js` — fix round 1 autorizzato PM: messaggi progetto leggibili per impatto/query deterministica.
15. Questo report.

## Red/green e comandi effettivi

Tutti i comandi eseguiti con cwd esplicito `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft`. Runtime browser:

```powershell
$env:NODE_PATH='C:/Users/Silve/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
node rag/tests/projects_workspace.cjs --fetch-only
node rag/tests/projects_workspace.cjs --navigation
node rag/tests/pipeline_agent.cjs
node rag/tests/pipeline_validation.cjs
node rag/tests/intake_excel_preview.cjs
node rag/tests/pipeline_dryrun_escape.cjs
node rag/tests/dashboard_graph_escape.cjs
node --check rag/static/shared.js
node --check rag/static/pages/workspace.js
node --check rag/static/pages/pipeline.js
node --check rag/static/pages/dashboard.js
```

- RED iniziale nuovo fetch test: `null !== 'legacy'` (header progetto assente). GREEN dopo wrapper.
- RED browser iniziale: timeout `#project-select` (selettore assente). GREEN dopo workspace e dialog.
- Nav RED intermedio: href senza query nei srcdoc, perché `location.origin` vale `null`; corretto confronto con origine `document.baseURI`. Nav GREEN, con stream/agent fuori pagina, Intake, history, tema, key e CSP invariati.
- Test reindex RED: timer ancora presente dopo 404. GREEN con rilascio terminale e retry solo degli errori temporanei.
- Remote browse RED: visibile nonostante hidden, `.btn` sovrascrive display nativo. GREEN con regola CSS mirata; fixture `Cache-Control:no-store` uguale al server.
- Ultimo `projects_workspace.cjs --navigation`: exit 0; Node fetch/reindex, Edge multiprogetto e nav baseline verdi. Lo streaming è **HTTP chunked reale nel server fixture**, con headers e primo evento delta già ricevuti e `workspaceIsBusy=true` prima del cambio A→B; finale consegnato successivamente. Le API dati restano simulate, nessun provider.
- Cinque baseline Node finali: tutti exit 0; sette file Node totali verificati includendo multiprogetto e navigazione. Quattro controlli sintassi JS exit 0.
- Sintassi `routes_pages.py` verificata tramite `compile(Path(...).read_text(...),..., 'exec')` con Python esistente `C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe`: exit 0. Nessun import runtime/backend anticipato.
- `git diff --check -- <file di ownership>` exit 0; soltanto avvisi Git LF→CRLF, nessun errore whitespace.

## Baseline preesistenti corretti

Tre extractor XSS già rossi prima delle modifiche: non trovavano chiusura funzione in shared CRLF. La sola lettura `shared.js` normalizza CRLF; asserzioni XSS/markup originali intatte.

`pipeline_agent.cjs` falliva `deepEqual` per `max_attempts:1` già nel sorgente HEAD. Prova senza checkout condiviso:

```powershell
@'
const fs = require('node:fs');
const cp = require('node:child_process');
const original = fs.readFileSync;
const head = cp.execFileSync('git', ['show', 'HEAD:rag/static/pages/pipeline.js'], {encoding:'utf8'});
fs.readFileSync = function(file, ...args) {
  if (String(file).replaceAll('\\', '/').endsWith('/static/pages/pipeline.js')) return head;
  return original.call(this, file, ...args);
};
require('./rag/tests/pipeline_agent.cjs');
'@ | node -
```

Prova effettuata prima dell'adapter: stesso errore `max_attempts:1` inatteso. `api/models.py` già accetta `AgentRunRequest.max_attempts` (default 1, range 1..10). Con expected aggiornato emergeva anche il nodo fixture mancante letto dal codice agentic; aggiunto il nodo corrispondente al markup reale. Tutte le altre asserzioni restano intatte. Scope esteso esplicitamente dal PM il 2 ottobre.

## Self-review e limiti

Verificati tutti i chiamanti fetch nei page script: nessun EventSource/WebSocket/XMLHttpRequest che bypassi il wrapper. Job Intake ereditano ID fisso del frame anche durante polling lontano dalla pagina; metadata tardivi aggiornano la barra soltanto se ancora selezionati. Header espliciti catturati prima del retry anche se l'oggetto Headers originale viene mutato. Operazioni tastiera e reindex fra timer trattenute; nessuna lettura del progetto mutable del parent dai frame.

Test browser include due schede indipendenti, link diretto/refresh/session senza query/back/forward, ID sconosciuto e selezione assente senza fallback, nomi HTML inerti, nuovi/apertura/errori, zero progetti, reader, Escape/focus, browse bind remoto nascosto, late stream A/B, job A mentre B, eviction idle e rifiuto max2 busy.

Rimane da verificare con server FastAPI integrato il metadato local-bind, le API create/register reali, l'esenzione browse globale di Task 4 e i comportamenti progetto non indicizzato/storage guasto: ownership Task 8/PM dopo backend review. Non è stata lanciata suite pytest complessiva durante gli edit concorrenti Task 3; il gate backend integrato rimane esplicitamente aperto. Refresh/chiusura non ripristinano conversazioni non persistite; il limite è annotato `ponytail:` nel sorgente.

## Fix round 1 dopo review indipendente

Corrette le due segnalazioni in `task-6-review.md`, scope esteso a graph_analysis.js dal PM. File modificati nel round: **rag/static/shared.js, rag/static/pages/dashboard.js, rag/static/pages/graph_analysis.js, rag/tests/projects_workspace.cjs**, più questo report. Nessun backend, stage o commit. La review indipendente Task3 è documentata separatamente in `task-3-review.md`.

- P1: l'input URL viene convertito nella stringa href catturata prima del primo tentativo, come già avviene per la cattura del progetto/header; Request conserva il clone/body/signal. Test modifica lo stesso oggetto URL nel prompt dopo 401, da same-origin a external.example: entrambi i tentativi devono restare sull'URL iniziale e sul progetto A, con chiave presente. Test URL esterna iniziale e tutti i test Request/body/header/AbortSignal precedenti conservati.
- P2: `apiErrorMessage` condivisa interpreta detail string o detail.message con fallback HTTP. Dashboard /ask e errori streaming, impatto e query deterministica del grafo mostrano la causa leggibile. Nessun redesign o dipendenza. Test esegue i veri submitQuery/loadImpact/runGraphQuery con risposte 409 non indicizzato, 503 storage, string legacy e detail assente; verifica testo visibile e rilascio loader. Edge verifica inoltre i veri controlli dashboard e grafo sui 409/503 usando API simulate, senza provider.

Red/green effettivo:

```powershell
node rag/tests/projects_workspace.cjs --fetch-only
node rag/tests/projects_workspace.cjs --query-only
$env:NODE_PATH='C:/Users/Silve/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
node rag/tests/projects_workspace.cjs --navigation
node rag/tests/pipeline_agent.cjs
node rag/tests/pipeline_validation.cjs
node rag/tests/intake_excel_preview.cjs
node rag/tests/pipeline_dryrun_escape.cjs
node rag/tests/dashboard_graph_escape.cjs
node --check rag/static/shared.js
node --check rag/static/pages/dashboard.js
node --check rag/static/pages/graph_analysis.js
node --check rag/tests/projects_workspace.cjs
git diff --check -- rag/static/shared.js rag/static/pages/dashboard.js rag/static/pages/graph_analysis.js rag/tests/projects_workspace.cjs
```

RED prima degli edit: fetch-only exit1 «URL mutated during 401 must keep the captured target»; query-only exit1 `❌ Errore: [object Object]` invece del messaggio progetto. Dopo il solo fix P1 fetch assertions GREEN, ma il comando resta exit1 per il P2 ancora aperto. Dopo normalizzazione dashboard/impatto, il nuovo test query deterministica ha dato RED `❌ HTTP 409` invece della causa; adeguato anche il consumer. Intermedio corretto l'extractor della nuova prova per caricare il helper dalla sua posizione in shared.js; nessuna asserzione indebolita.

Ultimo fetch-only exit0: fetch, tre consumer query × quattro forme errore, reindex. Ultimo navigation exit0: Edge multiprogetto, nuovi messaggi dashboard/grafo, navigazione baseline/CSP. Cinque baseline aggiuntive tutte exit0; **sette file Node** coperti dalla verifica finale includendo multiprogetto e navigazione. Quattro controlli sintassi exit0 e diff-check exit0 (soli avvisi conversione LF→CRLF). Self-review del round: nessun oggetto URL mutable trattenuto nel ramo protetto; messaggi assegnati con textContent, compatibilità detail string conservata. Re-review indipendente e gate integrato Task8 rimangono al PM.

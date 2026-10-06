# Task 6 — review indipendente UI

Esito: **Spec FAIL; qualità/correttezza FAIL**, due finding bloccanti da correggere e riverificare prima del commit UI. Review readonly del package `task-6-review-package.md`, base verificata `436b90872500244a9279ff278badcc1b139fbfc2`; letti tutti i 13 file UI/test del diff staged, brief e report Task 6. Nessuna modifica a implementazione/test, staging o commit. Worker diverso dall'autore UI; il reviewer ha implementato il backend Task 3 e ne ha confrontato il contratto congelato.

La review usa i due assi della skill code-review, svolti nello stesso worker per l'esplicito vincolo PM di non creare subagent. Standard disponibili: brief/progetto (CSP, no framework, stile esistente, testo escaped); il design contract menzionato nel docstring `routes_pages.py` non esiste nel worktree e non è stato inventato.

## Finding di correttezza e specifica

### 1. [P1] Congelare anche il target URL prima del retry autenticato

File `rag/static/shared.js`, righe **152, 165–170**. `url` usato per same-origin è una stringa catturata, ma `original` mantiene l'oggetto URL originale. Mutare quell'oggetto dopo la prima chiamata e prima del retry 401 fa inviare il retry alla nuova origin con `X-API-Key` e `X-VibeCraft-Project`. La protezione same-origin viene verificata solo all'ingresso, sul vecchio target. Non serve una richiesta inizialmente esterna: nasce same-origin e cambia mentre la prima risposta è pendente.

Riproduzione Node con codice reale shared estratto (chiavi di esempio, nessuna rete):

```javascript
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const shared=fs.readFileSync('rag/static/shared.js','utf8');
const src=shared.slice(shared.indexOf('const API_KEY_STORAGE'),shared.indexOf('const prefersReducedMotion'));
const input=new URL('http://localhost/api/health'),calls=[];
const context=vm.createContext({URL,Request,Headers,Promise,
  location:{href:'http://localhost/?project=legacy'},
  localStorage:{getItem(){return 'secret';},setItem(){}},
  sessionStorage:{getItem(){return 'legacy';}},
  document:{baseURI:'http://localhost/',querySelector(){return null;}},
  window:{frameElement:null,
    prompt(){input.href='https://external.example/api/health';return 'retry-secret';},
    fetch:async(url,init)=>{calls.push({url:String(url),
      key:init.headers.get('X-API-Key'),project:init.headers.get('X-VibeCraft-Project')});
      return {status:calls.length===1?401:200};}}});
vm.runInContext(src,context);
context.window.fetch(input).then(()=>console.log(calls));
```

Output effettivo: primo target `http://localhost/api/health`, key `secret`, project `legacy`; secondo target **`https://external.example/api/health`, key `retry-secret`, project `legacy`**. Exit 0 della prova che asseriva la presenza del bug. Il test di regressione deve invertire l'aspettativa: entrambi i tentativi restano sul target iniziale.

Correzione minima suggerita: convertire l'input URL nella stringa href catturata prima del primo tentativo, mantenendo il clone dedicato per Request. Aggiungere test mutation fra primo tentativo e retry, preservando quelli su body/header/signal e URL esterna iniziale. Priorità P1 confermata dal PM per possibile perdita credenziali.

Spec violata: «supportare string, URL e Request … Non allegare ID/credenziali a URL esterni».

### 2. [P2] Rendere leggibile il nuovo errore progetto nella query della console

File `rag/static/pages/dashboard.js`, righe **984–986**. La UI management interpreta `detail.message`, ma `submitQuery` continua a costruire `Error(err.detail)`. Il backend congelato restituisce `{detail:{code,message}}` per progetto senza indice, ID non valido e storage guasto. Una domanda nel progetto appena creato produce **`❌ Errore: [object Object]`**, perdendo il motivo e l'indicazione di indisponibilità. La barra «Non indicizzato» non sostituisce il messaggio della richiesta fallita. Pattern analogo in `graph_analysis.js:183–185`; verificare i consumer dati toccati dal nuovo contratto, mantenendo compatibilità con detail string.

Riproduzione Node sul vero `submitQuery`, senza server/provider:

```javascript
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('rag/static/pages/dashboard.js','utf8');
const fn=src.slice(src.indexOf('    async function submitQuery()'),
                  src.indexOf('    /* Submit on Ctrl+Enter.'));
const nodes={};
const node=id=>nodes[id]??={value:id==='question-input'?'question':'5',
  textContent:'',classList:{add(){},remove(){}}};
const ctx=vm.createContext({document:{getElementById:node},
  fetch:async()=>({ok:false,status:409,json:async()=>({detail:{
    code:'project_not_indexed',message:'Project has no index.'}})}),
  showLoader(){},setStatus(){},console});
vm.runInContext(fn,ctx);
ctx.submitQuery().then(()=>{
  assert.equal(node('answer-text').textContent,'❌ Errore: [object Object]');
  console.log(node('answer-text').textContent);
});
```

Exit 0 con messaggio errato riprodotto. Correzione suggerita: normalizzazione condivisa di error detail string/oggetto, oppure adattamento mirato dei consumer interessati; aggiungere test 409 non indicizzato e 503 storage con messaggio visibile. Questi test non richiedono provider né un corpus indicizzato.

Spec violata: disponibilità dichiarata senza indice e compatibilità con contratto backend congelato `{detail:{code,message}}`. È un'incompatibilità statica già riproducibile, non soltanto uno smoke integrato Task 8 ancora pendente.

## Standard e qualità

Nessuna violazione di stile/manutenibilità aggiuntiva da segnalare. Implementazione piccola, nessun framework o dipendenza, escaping e textContent corretti per nomi e metadata. I due difetti sopra impediscono il pass di correttezza; non richiedono un ridisegno. La logica di retention usa l'azione async completa oltre al fetch, proteggendo lo stream dopo l'arrivo degli header; reindex mantiene il frame fra timer ed errori transitori. I frame leggono un ID fissato prima degli script e non la selezione mutable del parent.

## Verifiche effettive del reviewer

Cwd sempre esplicito nel worktree assegnato. Eseguito personalmente:

```powershell
$env:NODE_PATH='C:/Users/Silve/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
node rag/tests/projects_workspace.cjs --navigation
node rag/tests/pipeline_agent.cjs
node rag/tests/pipeline_validation.cjs
node rag/tests/intake_excel_preview.cjs
node rag/tests/pipeline_dryrun_escape.cjs
node rag/tests/dashboard_graph_escape.cjs
```

Tutti **exit 0**. Primo comando include VM fetch/reindex e browser Edge headless: HTTP stream fixture con primo chunk già ricevuto; selezioni A/B, late A, job A mentre B, limite max2 busy, eviction idle, session/direct/refresh/history, nuovo/apri/errori/reader/zero-project, Escape/focus, XSS/CSP e navigazione storica. Le cinque baseline aggiuntive mantengono le asserzioni preesistenti. Eseguite inoltre le due riproduzioni VM sopra, entrambe confermano i difetti attuali.

La suite esistente passa perché non muta l'oggetto URL di input durante 401 e le API query simulate non restituiscono errori strutturati di progetto. I test management del messaggio strutturato non coprono dashboard.

## Gate integrato e handoff

Shape metadata/list/create/register/read_only corrisponde al Task 3. Selezione header e gestione iframe coerenti; browse-path resta endpoint globale (conversione Task 4). Reader, auth/CSP e local-bind non risultano indeboliti dal diff esaminato. Smoke FastAPI reale è separato e affidato al PM/Task 8; non sostituisce i due fix richiesti. Nessun gate backend ripetuto durante questa review readonly.

Riepilogo assi: Spec 2 finding (P1 retry target, P2 messaggi progetto); Standard/manutenibilità 0 finding aggiuntivi; qualità/correttezza FAIL fino a fix e re-review.

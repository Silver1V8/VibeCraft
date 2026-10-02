# Task 6 — re-review fix round 1

**Esito: PASS nello scope del fix.** Entrambi i finding della review iniziale sono **ADDRESSED**; nessuna regressione aggiuntiva rilevata nei quattro file modificati. Review indipendente readonly del delta `task-6-fix-1-review-package.md`, confrontato con `git diff` dei file reali: shared.js, dashboard.js, graph_analysis.js, projects_workspace.cjs. Nessun edit UI/backend, stage o commit durante questa re-review.

## P1 — URL mutable e credenziali: ADDRESSED

`original` ora converte un input URL nella stringa `url` catturata prima della prima richiesta. Il retry usa quindi esattamente il target già validato same-origin; Request continua a usare il clone, senza alterazioni a body/header/signal. Il test aggiunto muta il medesimo oggetto URL verso external.example durante il prompt401 e verifica entrambi i target iniziali, l'ID originario e gli header. Conservato anche il test input inizialmente esterno senza credenziali/ID.

Evidenza RED precedente: nella review iniziale la VM inviava il secondo tentativo a external.example con API key e project. Evidenza GREEN di questa re-review: nuovo test di regressione nel comando sotto passato; lettura del diff conferma che nessun URL object mutable sopravvive nel ramo protetto.

## P2 — Errori progetto leggibili: ADDRESSED

`apiErrorMessage` supporta detail string e detail.message, con fallback HTTP; chiamato da submitQuery (anche evento errore streaming), loadImpact e runGraphQuery. I testi restano assegnati con textContent. Il contratto runtime `{detail:{code,message}}` è rispettato senza eliminare compatibilità con gli errori storici stringa.

Evidenza RED precedente: submitQuery mostrava `❌ Errore: [object Object]` su409. Evidenza GREEN di questa re-review: VM esegue i tre consumer reali con409/503/stringa/fallback e controlla i testi più rilascio loader; Edge verifica i controlli effettivi dashboard/grafo e i messaggi noindex/storage.

## Test effettivamente eseguiti dal reviewer

Cwd esplicito `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft`:

```powershell
$env:NODE_PATH='C:/Users/Silve/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
node rag/tests/projects_workspace.cjs --navigation
node --check rag/static/shared.js
node --check rag/static/pages/dashboard.js
node --check rag/static/pages/graph_analysis.js
node --check rag/tests/projects_workspace.cjs
git diff --check -- rag/static/shared.js rag/static/pages/dashboard.js rag/static/pages/graph_analysis.js rag/tests/projects_workspace.cjs
```

Tutti verdi, exit0. Il primo comando comprende fetch/retry, query errors, polling reindex, Edge multiprogetto e navigazione baseline: streaming HTTP con primo chunk già ricevuto, A/B, limite2 busy, late result, reader, zero progetti, history e nessuna violazione CSP. Nessuna full suite eseguita. Gli altri cinque baseline Node già verificati nella review iniziale non sono stati ripetuti per questo fix limitato.

**Spec PASS; standard/qualità PASS per il delta riesaminato.** Resta separato il gate integrato FastAPI PM/Task8 già pianificato, inclusa l'integrazione dei writer Task4/5. Questo report supera i due FAIL della review iniziale `task-6-review.md`; non sostituisce quel verbale né attribuisce al reviewer gli smoke FastAPI eseguiti dal PM.

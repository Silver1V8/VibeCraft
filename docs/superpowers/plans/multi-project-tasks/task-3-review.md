# Task 3 — review indipendente runtime HTTP

Esito: **Spec FAIL, correttezza FAIL** fino alla correzione dei due finding P2 sotto. **Standard/manutenibilità PASS**, nessun finding aggiuntivo. Review readonly del package completo `task-3-review-package.md`, base `436b90872500244a9279ff278badcc1b139fbfc2`, tutti i 26 file runtime/test del package, brief e report Task 3. Esclusi i file UI dell'autore di questa review. Nessuna modifica backend/test, staging o commit. I due assi della skill code-review sono svolti nello stesso worker per il vincolo PM di non creare subagent.

## Spec e correttezza

### [P2] Il metadata non restituisce lo stale calcolabile di un indice reale

`rag/api/routes_projects.py:46–47` confronta `index_status()['version']` con il token CURRENT. I valori hanno semantiche diverse: `core/indexing.py:742` scrive nel campo manifest `version` un timestamp ISO, mentre CURRENT contiene il nome della directory, ad esempio `v1`. Il confronto è sempre falso sugli indici prodotti dall'indicizzatore. Dopo la modifica di un documento, `index_status(project)['stale']` è true ma `project_metadata(... )['stale']` resta null; anche lo stato aggiornato false non viene esposto. Viola «booleano stale quando calcolabile». La fixture `test_project_runtime.indexed` assegna invece il token al campo manifest e maschera l'incompatibilità.

Riproduzione effettiva con ProjectRegistry temporaneo e artefatti reali: creare A, scrivere docs/same.md, usare `indexed(A, 'See [RULE-X-01]')`, poi `indexing.write_index_manifest(1, version='v1', qdrant_collection=A.collection_name+'__v1', immutable=True, project=A)`; modificare docs/same.md e confrontare `indexing.index_status(project=A)` con `routes_projects.project_metadata(A, Request({'type':'http','headers':[],'client':('127.0.0.1',1)}))`.

Output: `actual_index_status: true`, `manifest_version: 2026-10-02T14:28:25.516232+00:00`, `api_index_version: v1`, **`api_stale: null`**. Correzione deve conservare la protezione contro una promozione concorrente usando la stessa identità CURRENT/artifact version, senza cambiare il significato storico del campo manifest. Test con `write_index_manifest` reale e stale false→true.

### [P2] Il cambio del peso restatement lascia il ranking dipendente dalla cache residente

`rag/core/retrieval.py:246–247` elimina la classificazione delle sezioni se il peso attuale è 1.0; `rag/api/deps.py:679` conserva tale set nello snapshot. Il registry rilegge gli override a ogni richiesta, ma `require_snapshot` riusa lo snapshot se CURRENT non cambia. Dopo un cambio ammesso in project.yaml da 1.0 a 0.5, `rank_by_authority` legge il nuovo peso ma riceve il vecchio set vuoto: non applica la penalità. Una successiva eviction/reload cambia i risultati con gli stessi artefatti e la stessa configurazione. La classificazione dipende dal testo immutabile e dovrebbe restare completa, mentre il peso viene applicato al ranking.

Riproduzione effettiva: artefatto chunk `same.md#1` con testo `See [RULE-X-01]`; YAML settings.authority.section_restatement_weight=1.0; `first=require_snapshot(registry.get(id))`; modificare YAML a 0.5; `changed=registry.get(id)` e `reused=require_snapshot(changed)`. Con candidati `{chunk_id:'same.md#1', authority:1.0, colbert_score:1.0}` e `{chunk_id:'declared#1', authority:1.0, colbert_score:0.8}`, ordinare con `rank_by_authority(..., restatements=reused.restatements, project=changed)` e con il set ricalcolato dai medesimi chunks.

Output: `same_snapshot: true`, `new_weight: 0.5`, `cached_restatements: []`, **actual_winner: same.md#1**, expected_winner: declared#1. Testare la modifica della configurazione senza reindicizzazione e la stabilità prima/dopo eviction. La fixture statica attuale verifica A/B con pesi diversi, ma non il passaggio di peso sullo stesso indice residente.

## Standard e qualità

Nessuna violazione aggiuntiva dello stile/CSP/auth o smell che richieda una modifica. Contesti espliciti, snapshot catturati una volta, cache ask con ID, collection fisiche per ID/versione, errori progetto sanitizzati e bootstrap lazy sono coerenti con il brief. LRU a due snapshot rimuove riferimenti senza chiudere lease ancora usate; cattura concorrente serializzata, stream conserva contesto/snapshot originari. Header assente resta esclusivamente legacy, con zero progetti 409; ID errato non ricade su B. Metadata remoto non espone root, reader conserva controlli immutable e rifiuta mutazioni. I fixture adapter legacy mantengono le asserzioni di sicurezza e di contenuto, spostando correttamente il caricamento dal lifespan alla prima lettura. Il rischio pending reindex rilevato durante pianificazione è già corretto tramite `is_running or pending_id is not None` e relativo test.

## Verifiche effettive

Cwd esplicito `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft`; Python dell'ambiente esistente originale, import da worktree, nessun sync/install. Eseguito personalmente:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH='C:/Users/Silve/.codex/worktrees/multi-project/vibecraft/rag'
$env:VIBECRAFT_TEST_QDRANT_URL='http://127.0.0.1:49634'
$env:VIBECRAFT_REQUIRE_QDRANT='1'
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -m pytest rag/tests/test_project_runtime.py rag/tests/test_project_api.py rag/tests/test_lifespan.py -ra --tb=short
```

**24 passed, 1 skipped, 19.84s, exit 0**, inclusa integrazione HTTP A/B con Qdrant reale dedicato. Skip unico: Windows WinError1314 sulla creazione del file symlink. Eseguite inoltre le due riproduzioni sopra con here-string Python stdin, PYTHONPATH comprensivo di rag/tests per il solo helper `indexed`, assert sui risultati e chiusura delle lease create dalla prova: entrambe confermate, secondo run pulito exit 0. Il primo run aveva riprodotto entrambi ma cleanup WinError32 perché la prova conservava le lease; corretto soltanto lo script di riproduzione. Nessuna full suite ripetuta. Il gate worker 558 pass/1 skip è evidenza nel report Task3, non un'esecuzione di questo reviewer.

## Handoff

Workflow, intake, tool writers e agenti sono responsabilità esplicita Task4/5; non sono finding di questo scope. Il gate UI/API integrato Task8 resta separato. Non rilevata contaminazione A→B nello scope esaminato; i due difetti sono metadata e ranking/configurazione e richiedono fix e re-review mirata prima di dichiarare Task3 completo.

Riepilogo assi: Spec 2 finding P2; Standard/manutenibilità 0; correttezza FAIL fino ai fix.

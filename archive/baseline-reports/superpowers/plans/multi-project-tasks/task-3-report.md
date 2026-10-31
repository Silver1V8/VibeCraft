# Task 3 — runtime HTTP, retrieval, cache e health multiprogetto

Stato: implementazione pronta per review, 2026-10-02. Nessun commit o staging eseguito dal worker. Base assegnata `436b908`; lavoro esclusivamente nel worktree `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft`.

## Risultato e contratti di integrazione

- `get_project(request)` cattura il contesto immutabile una volta nella richiesta. Header `X-VibeCraft-Project`; assenza ammessa soltanto se esiste legacy; altrimenti 409 `project_required`. ID malformato 422, sconosciuto 404, registry corrotto 503. Errori pubblici sanitizzati `{detail: {code, message}}`, senza percorsi o configurazione.
- `GET /api/projects` restituisce `{projects: [...], read_only: bool}`. GET singolo e POST create/register restituiscono metadata singoli (POST 201): `{id, name, legacy, index_status, stale, index_version, error?, root?}`. Stati `not_indexed|ready|indexing|error`; stale `bool|null`. Root solo per richiesta loopback con bind locale. Un manifest corrotto compare come errore nella propria voce senza nascondere B; registry corrotto fallisce chiuso.
- `GET /api/health/live` restituisce `{status: "ok", role, read_only}` senza registry, snapshot, modelli, Qdrant o Ollama; mantiene il normale helper auth. Console/lista disponibili senza indice e con servizi assenti.
- `project_runtime(project)` restituisce metadata persistenti per progetto. La chiave `lock` è un `RLock` da usare in Task 4 per creare manager/store una sola volta. La chiave `reindex_manager` alimenta health e metadata; `is_running` oppure `pending_id != None` indica indexing. Il runtime non viene espulso dalla LRU.
- `require_snapshot(project)` carica/cattura atomicamente sotto lock, 409 senza indice e 503 su errore; `current_snapshot(project)` è solo peek; `reload_index_state(project)` e `maybe_reload_graph(project)` aggiornano il solo progetto. Il default `None` resta esclusivamente legacy. LRU massimo due riferimenti agli snapshot; eviction/shutdown rimuovono riferimenti senza chiudere store posseduti da richieste in corso.
- `ensure_shared_resources(embedding=True)` inizializza risorse condivise lazy e una sola volta dopo successo, con lock; `embedding=False` permette l'accesso Qdrant senza caricare il modello. Nessuna selezione progetto modifica cwd, environment, costanti o configurazione globale.
- Retrieval/ask/stream/code/graph propagano il progetto e lo snapshot catturato, compresa collection fisica immutabile e metadati `project_id`/`index_version`. La cache ask include l'ID. Le impostazioni authority/retrieval/restatement, i helper governed e `eval_gate.evaluate_recall` propagano esplicitamente project. Stream A conserva A/v1 anche dopo caricamento B/C, eviction A e promozione A/v2.
- Health, cronologia eval, alert, graph cache e descrizioni appartengono al progetto. I lettori sidecar usano il guard condiviso anche sul file finale. Ordinary non usa fallback legacy; legacy conserva graph flat e sidecar opzionali storici.

## Lifecycle e sicurezza

Ruling PM recepito: boot HTTP lazy senza riparazione alias o GC impliciti. Manutenzione nei percorsi espliciti writer/indexing/CLI, mai nelle GET lazy. Shutdown chiude soltanto il client condiviso inizializzato e libera i riferimenti. `SECURITY_SURFACE.md` documenta questa policy e le nuove route (65 totali, 27 POST, 24 anti-cross-site, 8 router). Auth, Host guard, CSP, cross-site, reader e local-bind register verificati dal gate.

I diagnostici SQL/Razor globali non hanno consumer HTTP attuali: nessuna nuova esposizione introdotta. Nessuna modifica a pipeline/intake/reindex/tools/UI in questo task; conversione affidata ai task successivi.

## Verifica effettiva

Python usato: `C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe`; `PYTHONPATH` sul `rag` del worktree, `PYTHONUTF8=1`. Qdrant test dedicato `http://127.0.0.1:49634`, `VIBECRAFT_REQUIRE_QDRANT=1`. Il test reale crea namespace UUID temporanei A/B e rimuove solo le proprie collection; nessun accesso test alla porta 6333.

RED osservati prima dei rispettivi fix:

- Prime fixture A/B: runtime/cache mancanti e startup HTTP eager che invocava il modello; primo slice GREEN 9 passed.
- `test_lifespan_closes_only_initialized_shared_client_even_on_error`: mancata cleanup su eccezione del context manager, poi corretto con finally.
- `test_project_code_search_defaults_are_local`: default code/search ancora globali, poi propagazione impostazioni locali.
- `test_legacy_flat_graph_remains_available_without_optional_sidecars`: primo load lazy richiedeva sidecar opzionali, poi ripristinata compatibilità legacy.
- `test_indexing_status_is_local_to_running_project`: manager running con pending_id=None risultava not_indexed, poi corretto.
- I gate intermedi hanno anche identificato adattatori strict-signature storici e inventario sicurezza da aggiornare; preservate le assertion esistenti.

Comando finale, con le variabili sopra impostate:

```powershell
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -m pytest rag/tests/test_project_runtime.py rag/tests/test_project_api.py rag/tests/test_lifespan.py rag/tests/test_retrieve_reload.py rag/tests/test_retrieval.py rag/tests/test_retrieval_eval.py rag/tests/test_ask_cache.py rag/tests/test_ask_router.py rag/tests/test_ask_streaming.py rag/tests/test_graph_ops.py rag/tests/test_health.py rag/tests/test_reader_mode.py rag/tests/test_server_core.py rag/tests/test_code_search_api.py rag/tests/test_ask_observability.py rag/tests/test_ask_unified_llm.py rag/tests/test_ask_authority_prompt.py rag/tests/test_ask_abstention.py rag/tests/test_security_fixes.py rag/tests/test_security_headers.py rag/tests/test_host_header.py rag/tests/test_eval_gate.py -ra --tb=short
```

**558 passed, 1 skipped in 88.20s.** Unico skip: creazione file symlink Windows negata (`WinError 1314`), test `test_manifest_sidecar_link_never_reads_other_project`; nessun risultato simulato. Il test HTTP Qdrant reale è passato. Ruff su tutti i 25 file Python posseduti: **All checks passed**. `git diff --check`: exit 0 (soli avvisi LF/CRLF). Nessuna full-suite ripetuta; gate completo rinviato al Task 8 come richiesto. Ultima modifica successiva al gate: sola concordanza documentale del boot in SECURITY_SURFACE.

Log locali spostati sotto `docs/superpowers/plans/multi-project-tasks/task3-logs/`, ignorati da Git.

## Ownership esatta per staging PM

Produzione/documentazione (11):

- `rag/SECURITY_SURFACE.md`
- `rag/api/deps.py`
- `rag/api/routes_graph.py`
- `rag/api/routes_health.py`
- `rag/api/routes_projects.py` (nuovo)
- `rag/api/routes_retrieval.py`
- `rag/core/ask_cache.py`
- `rag/core/eval_gate.py`
- `rag/core/projects.py` (solo `Registry.records`)
- `rag/core/retrieval.py`
- `rag/server.py`

Test (15):

- `rag/tests/conftest.py` (nuovo)
- `rag/tests/test_project_api.py` (nuovo)
- `rag/tests/test_project_runtime.py` (nuovo)
- `rag/tests/test_ask_abstention.py`
- `rag/tests/test_ask_cache.py`
- `rag/tests/test_ask_observability.py`
- `rag/tests/test_ask_router.py`
- `rag/tests/test_ask_streaming.py`
- `rag/tests/test_ask_unified_llm.py`
- `rag/tests/test_code_search_api.py`
- `rag/tests/test_eval_gate.py`
- `rag/tests/test_lifespan.py`
- `rag/tests/test_reader_mode.py`
- `rag/tests/test_retrieve_reload.py`
- `rag/tests/test_security_fixes.py`

Report aggiuntivo: `docs/superpowers/plans/multi-project-tasks/task-3-report.md`.

Il nuovo conftest introduce solo la fixture **opt-in** `legacy_http_project`, attivata nei nove file HTTP storici adattati: fornisce il contesto legacy esplicito e preserva i seam di configurazione già usati dai vecchi test. Non è autouse, non simula registry o routing nelle nuove prove A/B. Queste usano registry reale, root temporanee e artifact/versioni reali. I test lifespan obsoleti sul boot eager sono sostituiti da quattro prove sul nuovo contratto lazy, cleanup anche in errore e lease in-flight.

## Self-review e limiti

Verificati capture una volta, physical collection da snapshot, chiave cache con ID, impostazioni ranking/eval locali, nessun fallback A→B, isolamento degli errori e nessuna chiusura anticipata alla eviction. Il lock globale serializza il caricamento disco iniziale; i lettori lavorano sui riferimenti catturati. La LRU limita i riferimenti mantenuti dal server, non quelli delle richieste in corso. Il test symlink file resta non eseguibile con i privilegi Windows attuali. UI e writer ancora in task paralleli/successivi; nessuna pretesa di gate integrato finale in questo report. File UI già staged e registro progresso PM non appartengono al Task 3.

## Review round 1 — correzioni e verifica

Recepiti i due P2 della review indipendente e i controlli aggiuntivi PM. Stato: fix pronto per re-review, nessun commit/staging del worker.

1. **Stale del manifest reale**: `index_status(project, *, version=None)` accetta una directory/versione esplicita, conservando il significato ISO storico di `result.version`. Metadata passa il token catturato e confronta il timestamp con quello del manifest già letto. Test usa `write_index_manifest` reale, stale false→true e promozione v1→v2 fra cattura metadata e calcolo: non etichetta v1 con gli hash di v2.
2. **Restatement e impostazioni nuove**: classificazione completa derivata soltanto dai chunk, mai dal peso iniziale. Il ranking applica il peso del contesto della richiesta; nessun reload pesante per cambi config. Test cambia YAML 1.0→0.5 sullo stesso snapshot, verifica il vincitore e l'identico risultato dopo eviction/reload. Corretto il vecchio test che erroneamente richiedeva classificazione vuota con peso 1.0.
3. **Cache/config**: confermato RED della stessa query/progetto/v1 dopo modifica YAML. La chiave ora include SHA-256 della serializzazione canonica dei soli blocchi authority/retrieval catturati nella richiesta. Non mantiene configurazione in chiaro. Test HTTP cambia entrambi i blocchi separatamente: miss e nuovo risultato dopo il cambiamento, hit sulla ripetizione.
4. **Junction dopo context capture**: confermata lettura di B da A nel lettore descrizioni quando docs/root venivano sostituiti da junction. `load_rule_descriptions` riusa `source_files`, il cui controllo ora include gli ancestor della source root, e `_unlinked` sul file prima della lettura. Test reali Windows per docs, root e directory nested; target B conservato. Individuato e chiuso lo stesso difetto nel fallback documentale di `/ask` legacy con `_unlinked` e risposta 503 sanitizzata. Test HTTP con contesto/snapshot già catturati e junction A/docs→B/docs: nessun testo esterno inviato a LLM.

**File ulteriori autorizzati**: `rag/core/indexing.py` (solo parametro opzionale/version pin in index_status) e `rag/code_index/__init__.py` (solo ancestor guard in source_files). Gli altri edit sono nei file Task3 già elencati: deps, routes_projects, routes_retrieval, ask_cache, retrieval, test_project_api/runtime. Ownership finale Task3: 28 file produzione/test + report.

**RED/GREEN effettivi**:

- `pytest rag/tests/test_project_api.py rag/tests/test_project_runtime.py -k 'settings_change or captured_version or junction_after' -ra --tb=short`: RED **6 failed, 21 deselected in 13.74s**; GREEN **6 passed, 21 deselected in 12.90s**.
- `pytest rag/tests/test_project_api.py -k legacy_ask_fallback -ra --tb=short`: RED pulito **1 failed, 14 deselected in 10.74s**, con HTTP200 invece di503 e chiamata LLM raggiunta. Primo tentativo RED usava pytest.fail dal thread HTTP e produceva anche errore teardown del portale; fixture corretta per osservare la risposta normalmente, senza cambiare il difetto verificato.
- Gate mirato finale (stesse env Python/Qdrant dedicate del report):

```powershell
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -m pytest rag/tests/test_project_runtime.py rag/tests/test_project_api.py rag/tests/test_ask_cache.py rag/tests/test_retrieval.py rag/tests/test_retrieval_eval.py rag/tests/test_index_status.py rag/tests/test_code_index.py rag/tests/test_project_indexing.py rag/tests/test_retrieve_reload.py rag/tests/test_reader_mode.py rag/tests/test_eval_gate.py -ra --tb=short
```

**220 passed, 18 skipped in 68.88s**, exit0. Tutte le prove junction eseguite e verdi; gli skip sono 1 file symlink API +17 file symlink storage per WinError1314 già documentati. Inclusa integrazione HTTP A/B Qdrant49634. Ruff su tutti i nove file Python del fix: **All checks passed**; `git diff --check` exit0. Non ripetuta full suite né precedente gate558 senza necessità.

Percorso log corretto e verificato con `git check-ignore`: `docs/superpowers/plans/multi-project-tasks/task3-logs/`. La precedente root `.pytest_cache` conteneva soltanto questi log ed è ora vuota; nessun altro cache o dato spostato. Non introdotta esposizione HTTP di impostazioni/percorsi.

## Review round 2 — compatibilità estensione Markdown

Corretto il solo finding residuo P2 di `task-3-fix-1-review.md`: il filtro del lettore descrizioni usa `suffix.lower() == ".md"`, conservando la compatibilità Windows per `spec.MD` e rendendola esplicita su tutte le piattaforme. Guard source_files e `_unlinked` invariati. File del round: `rag/api/deps.py`, `rag/tests/test_project_runtime.py`, questo report; nessun altro scope.

Nuovo test parametrizzato con file reali `spec.md` e `spec.MD`: RED **1 failed, 1 passed, 13 deselected in 10.49s** (`pytest rag/tests/test_project_runtime.py -k extension_case -ra --tb=short`). Dopo il fix, gate limitato descrizioni/legacy flat/junction: `pytest rag/tests/test_project_runtime.py -k 'descriptions or legacy_flat' -ra --tb=short` → **6 passed, 9 deselected in 11.14s**, nessuno skip. Ruff sui due file: All checks passed; diff-check mirato exit0. Stesso Python/PYTHONPATH del report, nessun modello/provider/Qdrant necessario per questo slice. Log nel folder task3-logs già ignorato. Nessuna full/broad suite ripetuta.

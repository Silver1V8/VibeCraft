# Gestione uniforme dei progetti Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Metodo proposto: esecuzione diretta in questa sessione, da confermare dopo la lettura del piano.

**Goal:** Creare tutti i progetti nel layout ordinario e migrare il progetto iniziale conservando dati e ID `legacy`.

**Architecture:** Il registro risolve ogni progetto tramite manifest; runtime e indice usano il contesto ordinario anche per l'ID `legacy`. Bootstrap e migrazione condividono una copia verificata e riprendibile. La migrazione riusa la build, il gate e i controlli di integrità esistenti.

**Tech Stack:** Python 3.14, pathlib/shutil/hashlib/json della libreria standard, PyYAML e pytest già installati, pipeline Qdrant/embedding esistente, PowerShell e shell per gli script esistenti.

**Spec:** [Specifica approvata](2026-10-05-uniform-project-layout-design.md), approvazione dell'utente nella chat dopo il commit `bfe5ee0`.

## Global Constraints

- Ogni progetto creato da VibeCraft deve avere una cartella dedicata sotto `VIBECRAFT_PROJECTS_DIR`.
- Conservare `legacy` come identificatore stabile del progetto iniziale.
- Il percorso base resta configurabile e in Docker resta `/app/projects`.
- Gli altri nuovi progetti conservano il comportamento attuale di creazione vuota.
- Un registro già esistente e vuoto resta vuoto.
- Il bootstrap non scarica modelli, non chiama Qdrant e non indicizza.
- Un reader non crea cartelle né modifica il registro.
- Nessuna nuova dipendenza, nessun sistema parallelo di progetti e nessuna modifica alla selezione per scheda.
- L'indicizzatore scansiona solo `project.docs_dir` e `project.code_dir`.
- Modelli, client e servizi esterni restano condivisi.
- Modifiche locali preesistenti e dati reali non entrano nei commit o nei test.
- Eseguire i task in ordine con ciclo RED/GREEN e commit dei soli file del task. I comandi Python sotto partono da `rag/`; i comandi Git dalla root del checkout di lavoro.
- Il piano rimane in `rag/adr`, come la specifica: `rag/adr/README.md` esclude esplicitamente questi documenti dal corpus RAG.

## Review Focus

- Registro assente con veri dati storici: chiedere migrazione, senza trattarlo come clone vergine (Task 2).
- Registro vuoto o corrotto dopo inizializzazione: non ripopolare e non sovrascrivere (Task 1).
- Interruzione dopo la build e prima del registro: riprendere la candidata verificata senza duplicare dati (Task 4).
- Namespace `vibecraft_legacy` già occupato: fallire prima di modificare alias o collection altrui (Task 4).
- Script senza selezione con root contenente dati: risolvere il progetto registrato o fallire, senza accesso implicito alla root (Task 3 e Task 5).

## File Structure

| File | Responsabilità |
| --- | --- |
| `rag/core/projects.py` | Registro, manifest, creazione comune del layout e bootstrap |
| `rag/core/project_migration.py` (nuovo) | Copia verificata, checkpoint e migrazione esplicita |
| `rag/scripts/migrate_project_layout.py` (nuovo) | CLI della migrazione con import lazy della pipeline pesante |
| `rag/api/deps.py`, `rag/api/routes_projects.py`, `rag/index.py` | Risoluzione del target e stato per progetto |
| `rag/core/artifacts.py`, `rag/core/indexing.py`, `rag/core/qdrant_versions.py`, `rag/core/eval_gate.py` | Stesso profilo di indice per ogni contesto applicativo |
| `rag/api/routes_reindex.py`, `rag/agent_bridge.py`, `rag/agent_runners.py`, `rag/mcp_server.py` | Propagazione del target ordinario e compatibilità dell'ID |
| Test esistenti e `rag/tests/test_project_migration.py` (nuovo) | Bootstrap, recupero e regressioni di isolamento |
| Configurazione, script, Docker/Compose e README | Distribuzione e istruzioni coerenti con il layout |

Non dividere i moduli esistenti per motivi estranei a questo cambiamento. Il nuovo
modulo di migrazione è il confine fra compatibilità storica e operazioni ordinarie.

### Task 1: Registro uniforme e layout comune

**Files:** Modify `rag/core/projects.py`; Test `rag/tests/test_projects.py`, `rag/tests/test_project_api.py`.

**Interfaces:** Conservare `ProjectRegistry.create(name: str) -> ProjectContext`, `register(root: Path) -> ProjectContext`, `get(project_id: str) -> ProjectContext`, `records() -> list[dict]` e `list() -> list[ProjectContext]`. Aggiungere `_create_project_root(root: Path, project_id: str, name: str, settings: dict | None = None) -> ProjectContext`, riusato da create/bootstrap/migrazione; `historical_project() -> ProjectContext | None` restituisce esclusivamente la sorgente storica verificata per la migrazione. `ProjectContext.legacy` resta temporaneamente per compatibilità, ma vale `False` per ogni contesto applicativo.

- [x] **Step 1: Test RED.** Sostituire il test che impone la root storica con test della lettura diagnostica schema 1 e aggiungere:

  ```python
  def test_legacy_id_uses_an_ordinary_manifest(tmp_path):
      store = registry(tmp_path)
      root = manifest(tmp_path / 'managed' / 'legacy', 'legacy', 'Initial')
      project = store.register(root)
      assert project.id == 'legacy' and project.legacy is False
      assert project.collection_name == 'vibecraft_legacy'
      assert store.get('legacy') == project
      assert json.loads(store.registry_path.read_text())['schema_version'] == 2
  ```

  `registry()` e `manifest()` sono già definiti in `test_projects.py`. Aggiungere `test_v1_legacy_requires_explicit_migration`: `get('legacy')`, create e register su registro storico con legacy restituiscono `ProjectError(code='project_migration_required', status_code=409)` senza modificarne i byte. Aggiungere `test_v1_ordinary_records_remain_openable`, `test_empty_v2_registry_stays_empty` e conservare i casi di corruzione/link già presenti.
- [x] **Step 2: Verificare RED.** `uv run --frozen pytest tests/test_projects.py -k 'legacy_id_uses or v1_legacy or v1_ordinary or empty_v2' -v`. Atteso: fallimenti sul manifest riservato e sullo schema/comportamento ancora storico.
- [x] **Step 3: Implementare.** Lo schema 2 conserva i record `{id, name, root, legacy}`, con `legacy: false` per tutti. Il manifest accetta `legacy` come ID ordinario. Lo schema 1 è validato con le regole originali; le root UUID ordinarie rimangono utilizzabili, mentre la root legacy è disponibile soltanto tramite `historical_project()`. La lettura non aggiorna lo schema; una scrittura writer senza legacy storico converte i record ordinari in schema 2. Estrarre il solo layout oggi dentro `create()`, senza cambiare validazione, ID UUID o registrazione di root esterne. Eliminare la registrazione automatica in-place: con sorgenti storiche e registro assente restituire `project_migration_required`, senza creare un record schema 2 storico. Il Task 2 aggiunge poi il bootstrap dedicato al clone pulito.
- [x] **Step 4: Verificare GREEN.** `uv run --frozen pytest tests/test_projects.py tests/test_project_api.py -v`. I test che richiedevano bootstrap in-place devono ora richiedere l'errore diagnostico o il contesto storico di sola migrazione; tutti i test di questo task devono passare.
- [x] **Step 5: Commit focalizzato.** `git add rag/core/projects.py rag/tests/test_projects.py rag/tests/test_project_api.py`; `git commit -m 'feat: resolve initial project through an ordinary manifest'`.

### Task 2: Bootstrap senza servizi e copia verificata

**Files:** Modify `rag/core/projects.py`; Create `rag/core/project_migration.py`, `rag/tests/test_project_migration.py`; Test `rag/tests/test_projects.py`.

**Interfaces:** Nel modulo di migrazione, `copy_source_tree(source: Path, target: Path) -> dict[str, str]` copia e restituisce `{percorso_relativo: sha256}`; `prepare_project_copy(source: ProjectContext, target: ProjectContext, *, checkpoint_path: Path, include_history: bool) -> dict` prepara e verifica la copia riprendibile. Nel registro, `_bootstrap_initial_project() -> ProjectContext | None` usa queste funzioni e il layout del Task 1. Il checkpoint JSON ha versione 1, radici sorgente/destinazione canoniche, inventari dei file e fase `prepared`, `copied`, `index_verified` o `published`.

- [x] **Step 1: Test RED.** In `test_project_migration.py`, costruire sorgenti e destinazioni in `tmp_path` con `legacy_project_context()` e `dataclasses.replace`, già usati nei test di registro. Aggiungere `test_clean_bootstrap_is_ordinary_and_idempotent`: solo documenti e scheletro del codice; ID `legacy`, root `managed/legacy`, hash identici, originali presenti, nessun `CURRENT`; modificare un documento del target e verificare che il riavvio lo conservi. Aggiungere `test_bootstrap_with_historical_state_requires_migration`, parametrizzato per indice, changes, staging, pipeline e codice reale; `test_copy_rejects_links_and_foreign_destination`; `test_copy_resumes_after_interruption`; `test_reader_never_bootstraps`.
- [x] **Step 2: Verificare RED.** `uv run --frozen pytest tests/test_project_migration.py -v`. Atteso: funzioni mancanti o root ancora globale.
- [x] **Step 3: Implementare.** Usare `Path.walk`, `shutil.copy2`, `hashlib.file_digest` e scritture JSON atomiche esistenti. Controllare link/junction e sovrapposizioni prima della copia. Registrare l'identità della preparazione prima di scrivere nella destinazione; una destinazione estranea fallisce. Verificare inventario/hash dei sorgenti e dei target prima della pubblicazione; dopo interruzione accettare solo file coerenti con il checkpoint e ricopiare quelli incompleti. Nel bootstrap copiare docs e scheletro, verificando anche documenti locali aggiuntivi; indice, history o codice reale impongono migrazione. Ignorare solo segnaposto vuoti e file di lock nel rilevamento dello stato storico. Creare schema 2 e manifest soltanto a copia completa. Un registro già vuoto non viene ripopolato. Tenere fuori dalla catena del bootstrap import di indexing/embedding/Qdrant.
- [x] **Step 4: Verificare GREEN.** `uv run --frozen pytest tests/test_project_migration.py tests/test_projects.py tests/test_project_api.py -v`. Aggiungere al test di bootstrap guardie di import/client che falliscano se viene inizializzata la pipeline pesante. Tutti i test dei Task 1 e 2 devono ora passare.
- [x] **Step 5: Commit focalizzato.** `git add rag/core/projects.py rag/core/project_migration.py rag/tests/test_project_migration.py rag/tests/test_projects.py rag/tests/test_project_api.py`; `git commit -m 'feat: bootstrap initial project with verified local copies'`.

### Task 3: Runtime e indice ordinari anche per legacy

**Files:** Modify `rag/api/deps.py`, `rag/api/routes_projects.py`, `rag/api/routes_reindex.py`, `rag/core/artifacts.py`, `rag/core/indexing.py`, `rag/core/qdrant_versions.py`, `rag/core/eval_gate.py`, `rag/index.py`, `rag/agent_bridge.py`, `rag/agent_runners.py`; inspect `rag/mcp_server.py`, `rag/core/config.py` and production scripts; Test `rag/tests/conftest.py`, `rag/tests/test_project_runtime.py`, `rag/tests/test_project_indexing.py`, `rag/tests/test_project_tools.py`, `rag/tests/test_project_workflows.py`, `rag/tests/test_mcp_server.py` and existing historical suites affected by the changed defaults.

**Interfaces:** Conservare `get_project(request) -> ProjectContext`, `project_runtime(project=None) -> dict`, `current_snapshot(project=None) -> IndexSnapshot | None` e le firme pubbliche di build/delta/rollback. In `core/projects.py`, aggiungere `resolve_registered_project(project_id: str | None = None) -> ProjectContext`: usa un registro readonly e ID `legacy` solo quando l'argomento è assente; assenza di quel default produce `project_required`. I confini applicativi risolvono sempre un contesto prima di chiamare il core. Le funzioni storiche di lettura degli artefatti rimangono disponibili soltanto per diagnostica e migrazione.

- [x] **Step 1: Test RED.** Parametrizzare i test di isolamento esistenti includendo un progetto manifest con ID `legacy`: stesso `same.md`, stessa versione `v1`, dati diversi; assert snapshot/job/cache separati, alias distinti, delta noop e delta con build, rollback e corruzione del CURRENT confinati al target. Aggiornare `test_cli_absent_flag_ignores_mcp_environment`: senza legacy registrato deve fallire prima di chiamare il core, anche se l'ambiente MCP seleziona B. Aggiungere `test_cli_default_resolves_registered_legacy` e `test_root_docs_are_never_an_implicit_corpus`. Aggiungere un caso HTTP schema 1 legacy che mostri `project_migration_required` nella metadata diagnostica.
- [x] **Step 2: Verificare RED.** `uv run --frozen pytest tests/test_project_runtime.py tests/test_project_indexing.py tests/test_project_tools.py tests/test_project_api.py -v`. Atteso: comportamento globale di snapshot/CLI o mancanza di contesto nel default.
- [x] **Step 3: Implementare.** Cercare tutti i caller di ogni funzione cambiata prima dell'edit. I rami `project.legacy` non possono più selezionare profili per contesti applicativi. Centralizzare default API/CLI nel registro; lo stato globale conserva soltanto client e modelli condivisi, snapshot e job sono per ID. La validazione immutabile e delle collection vale anche per ID `legacy`. Il default CLI non usa `VIBECRAFT_PROJECT_ID` e non passa più `project=None`; MCP continua a catturare la selezione per sessione. Conservare i lettori del formato storico `LEGACY_VERSION` per migrazione, senza usarli come fallback operativo. Adattare le fixture storiche a contesti espliciti temporanei e i loro monkeypatch al runtime per ID. Nessun guard duplicato in ogni route quando basta la risoluzione condivisa.
- [x] **Step 4: Verificare GREEN.** `uv run --frozen pytest tests/test_project_runtime.py tests/test_project_indexing.py tests/test_project_tools.py tests/test_project_api.py tests/test_project_workflows.py tests/test_mcp_server.py tests/test_artifacts.py tests/test_eval_gate.py tests/test_qdrant_blue_green.py -v`. Qdrant in memoria e l'encoder `Embed` di `test_project_indexing.py` coprono il flusso; gli skip del server dedicato vanno riportati. Aggiungere al test del gate il percorso `legacy/eval/golden.yaml`, senza fallback al golden globale.
- [x] **Step 5: Commit focalizzato.** Stagiare soltanto i file modificati da questo task; `git commit -m 'refactor: use project scoped runtime and indexes for initial project'`.

### Task 4: Migrazione esplicita con pubblicazione verificata

**Files:** Modify `rag/core/project_migration.py`, `rag/core/projects.py`; Create `rag/scripts/migrate_project_layout.py`; Test `rag/tests/test_project_migration.py`, `rag/tests/test_project_indexing.py`.

**Interfaces:** `migrate_legacy_project(registry: ProjectRegistry, *, qdrant=None, embed_model=None, emit=None) -> ProjectContext` riusa `historical_project()` e `prepare_project_copy()`. CLI da `rag/`: `uv run --frozen python -m scripts.migrate_project_layout`; apre `ProjectRegistry(bootstrap_legacy=False)`, migra soltanto il progetto storico e produce esito/percorso senza contenuti dei file o segreti. Reader: errore e nessuna scrittura.

- [x] **Step 1: Test RED.** `test_migrate_unindexed_legacy_preserves_all_sources`: docs/code/changes, staging e pipeline anche fuori dalla root; confronto hash e registro originale salvato, nuovo contesto ordinario, altri record invariati. `test_migrate_indexed_legacy_publishes_only_verified_build`: Qdrant in memoria ed encoder minimo esistente, vecchia collection intatta, nuova root attiva solo a build/gate/integrità riusciti. Aggiungere casi parametrizzati per copy error, hash mismatch, gate bloccante, Qdrant assente e namespace occupato. In ogni fallimento assert byte del registro e sorgenti intatti. Aggiungere `test_migration_resumes_after_index_verification`, `test_migration_is_noop_after_publication`, `test_migration_preserves_golden_and_requires_contract_revalidation` e test CLI senza import pesanti per il caso non indicizzato.
- [x] **Step 2: Verificare RED.** `uv run --frozen pytest tests/test_project_migration.py -k 'migrate or migration' -v`. Atteso: migrazione assente.
- [x] **Step 3: Implementare.** Server e altri writer devono essere fermi; acquisire lock registro, writer sorgente e writer target nell'ordine fisso. Salvare una copia byte per byte in `projects/projects.v1.backup.json` prima della pubblicazione; se esiste una copia diversa, fallire. Checkpoint in `projects/.legacy-migration.json`; nessuna cancellazione automatica degli originali. Copiare staging/pipeline nelle cartelle ordinarie e il golden storico configurato in `<target>/eval/golden.yaml`, con verifica e validazione del formato. I metadati storici legati a root/versione non diventano approvazioni valide nel nuovo contesto.

  Per l'indice, import lazy e riuso di `build_graph_and_index(..., promote=True, project=target)`: la funzione applica già il gate. Il valore restituito è una candidata anche quando il gate blocca; richiedere quindi `current_version(project=target) == version`, `check_index_integrity(qdrant, project=target)['ok'] is True` e alias sulla collection del manifest prima di pubblicare il registro. Controllare namespace e collisioni prima di qualunque build; non chiamare la migrazione distruttiva della vecchia collection. Sulla ripresa, accettare soltanto la candidata del checkpoint, con stessi hash sorgenti e integrità verificata; uno stato diverso fallisce conservando la preparazione per diagnosi. Dopo successo scrivere checkpoint `published`; una ripetizione confronta il registro e restituisce lo stesso progetto senza build. Se il checkpoint è ancora `index_verified` ma il registro è già aggiornato, completare soltanto il checkpoint.
- [x] **Step 4: Verificare GREEN.** `uv run --frozen pytest tests/test_project_migration.py tests/test_project_indexing.py tests/test_projects.py -v`. Verificare anche un guasto dopo CURRENT e prima dell'alias: registro originale intatto, candidato riparabile esplicitamente senza toccare il vecchio namespace. Controllare che il test di lock non lasci modificare sorgenti a un writer concorrente.
- [x] **Step 5: Commit focalizzato.** `git add rag/core/project_migration.py rag/core/projects.py rag/scripts/migrate_project_layout.py rag/tests/test_project_migration.py rag/tests/test_project_indexing.py`; `git commit -m 'feat: migrate initial project with verified publication and recovery'`.

### Task 5: Distribuzione, script e verifica integrata

**Files:** Modify as required `README.md`, `rag/README.md`, `rag/core/config.py`, `Dockerfile`, `docker-compose.yml`, `rag/scripts/doctor.py`, `rag/scripts/run_server.ps1`, `rag/scripts/run_server.sh`, `rag/scripts/nightly_consistency.ps1`, `rag/scripts/nightly_consistency.sh`, `rag/scripts/weekly_consistency.ps1`, `rag/scripts/weekly_consistency.sh`; Test `rag/tests/test_docker_compose_pinned.py`, `rag/tests/test_docker_index.py`, `rag/tests/test_project_integration.py`, `rag/tests/test_project_tools.py`; inspect `rag/static/pages/workspace.js` and `rag/tests/projects_workspace.cjs`.

**Interfaces:** Baseline distribuita sotto `/app/docs`, progetto iniziale attivo sotto `/app/projects/legacy`; modelli invariati. Gli script conservano il default registrato `legacy`; se ricevono `VIBECRAFT_PROJECT_ID`, inoltrano lo stesso ID con `--project` alla CLI e `X-VibeCraft-Project` alle API. La selezione ordinaria della CLI resta quella del Task 3. La documentazione espone il comando del Task 4, prerequisiti, costo della ricostruzione e recupero dal registro salvato.

- [x] **Step 1: Test RED.** Aggiungere bootstrap in root temporanea con layout del container e un test subprocess della CLI con progetto assente e dati nella root: non deve indicizzarli. Adattare il test Docker per `/app/projects/legacy`; aggiungere script smoke check per coerenza ID CLI/header. Parametrizzare l'integrazione di progetto per legacy e UUID. Mantenere il test browser esistente per apertura/selezione e verificare che ID `legacy` non dipenda dal campo API `legacy: true`.
- [x] **Step 2: Verificare RED.** `uv run --frozen pytest tests/test_docker_compose_pinned.py tests/test_docker_index.py tests/test_project_tools.py tests/test_project_integration.py -v`. Atteso: istruzioni/test o script ancora riferiti al layout storico attivo.
- [x] **Step 3: Implementare.** Separare nei commenti/config i percorsi di sorgente storica dai percorsi attivi; la compatibilità storica viene usata solo dalla migrazione. Conservare il volume `/app/projects` e i permessi UID 10001. I vecchi bind docs/code/database servono solo come sorgenti di migrazione, con istruzioni esplicite. Aggiornare script in modo che HTTP e fallback CLI lavorino sullo stesso target. Documentare il bootstrap una tantum, i progetti nuovi vuoti, i percorsi host/container e la copia recuperabile. Non migrare ancora il workspace reale.
- [x] **Step 4: Verifica finale unica.** Da `rag/`: `uv run --frozen ruff check .`; `uv run --frozen pytest -rs`; `node tests/projects_workspace.cjs`. Usare il servizio Qdrant dedicato e il browser di integrazione se disponibili, rispettando `VIBECRAFT_TEST_QDRANT_URL` e `VIBECRAFT_REQUIRE_QDRANT`; non usare collection di produzione per i test. Riportare separatamente ogni verifica non eseguita. Eseguire `git diff --check` dalla root e confrontare il diff con tutti i criteri della specifica.
- [ ] **Step 5: Commit e handoff.** Commit solo dei file di distribuzione/documentazione e dei test aggiornati: `git commit -m 'docs: align setup and scripts with uniform project layout'`. Review finale dell'intero diff; applicare e verificare soltanto le correzioni necessarie. Consegnare riepilogo, risultati dei controlli e comando di migrazione reale. La migrazione del workspace esistente va eseguita a processi fermi, dopo avere verificato che i servizi necessari siano disponibili; se manca un requisito operativo, lasciare i dati intatti e indicare quello specifico.

## Controllo di copertura del piano

Bootstrap/clone pulito: Task 2 e 5. Layout e compatibilità dell'ID: Task 1.
Runtime, indice e perimetro del corpus: Task 3. Migrazione, golden, recupero e
pubblicazione: Task 4. Docker, script e regressioni: Task 5. Ogni elemento del
Review Focus ha un caso nel task che possiede il relativo codice.

## Metodo di esecuzione proposto

Esecuzione diretta in questa sessione: i task dipendono strettamente dal registro
e dal medesimo contesto, quindi un unico implementatore mantiene più facilmente
coerenti migrazione e runtime. Alternativa: subagenti per task con review fra i
passaggi. Prima dell'implementazione serve la revisione del piano e la scelta
del metodo; poi seguire il workflow della skill scelta e la verifica finale.

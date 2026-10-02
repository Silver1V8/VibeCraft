# Task 2 — Storage e indicizzazione per progetto

Status: implementato, pronto per review PM. Nessun commit/stage eseguito.

Worktree: `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft`.
Base: Task 1, commit `9e48d98`.

## Risultato

Artefatti, CURRENT, manifest, hash sorgenti, staging ColBERT, marker immutable,
lease, retention e writer lock ricevono il ProjectContext esplicito. Qdrant usa
alias e collection del progetto in build, delta, rollback, riconciliazione e GC.
`None` conserva il percorso legacy: nessuna selezione globale, cambio cwd/env o
monkeypatch runtime. I test possono usare gli stessi token versione e nomi file
in A/B senza condividere artefatti o vettori.

Il primo delta di un progetto nuovo riusa il full build, creando subito la
collection fisica versionata e l'alias. I delta successivi conservano la lineage
esistente. Manifest nuovi corrotti, CURRENT vuoto/mancante nella directory
indicata e collection dichiarate fuori namespace producono errori espliciti;
le API di osservazione Qdrant mantengono il contratto storico `state=unknown`
con dettaglio errore.

Il gate legge `<project.root>/eval/golden.yaml`, scrive storico in
`database/eval/history.jsonl` e alert in `database/alerts.jsonl`. Usa le impostazioni
`eval_gate` del contesto; golden assente resta `no_golden_set` fail-open. Legacy
mantiene golden e destinazioni storiche.

Lo scanner condiviso `code_index.source_files` rifiuta symlink, junction e percorsi
che escono dalla root prima della lettura. È riusato da hash, build e scanner
codice. L'adapter Razor usa lo stesso scanner anche per `_Imports.razor` e
`_ViewImports.cshtml`: il precedente glob ausiliario attraversava junction sotto
directory escluse. ColbertWriter rifiuta antenati collegati prima di creare staging.

## File modificati

- `rag/core/artifacts.py`
- `rag/core/colbert_store.py`
- `rag/core/writer_lock.py`
- `rag/core/qdrant_versions.py`
- `rag/core/indexing.py`
- `rag/core/eval_gate.py` — adapter autorizzato per golden/settings/telemetria.
- `rag/code_index/__init__.py` — scanner condiviso autorizzato per confinement.
- `rag/code_index/razor.py` — lettura ausiliaria che aggirava lo scanner principale.
- `rag/conftest.py` — fixture writer lock aggiornata con `project=None`; sandbox
  legacy conservata, path espliciti di progetto rispettati.
- `rag/tests/test_project_indexing.py` — nuovo.
- `rag/tests/test_artifacts.py`, `test_incremental_indexing.py`,
  `test_index_integrity.py`, `test_qdrant_blue_green.py` — sole firme dei doppi
  adattate al keyword `project`, nessuna assertion eliminata.

I documenti generali del piano/progresso modificati dal PM non appartengono a
questo task e non sono stati modificati da questo agente.

## Verifica RED/GREEN

Runtime di tutti i comandi:

```powershell
$env:PYTHONPATH='C:/Users/Silve/.codex/worktrees/multi-project/vibecraft/rag'
$env:PYTHONUTF8='1'
$env:VIBECRAFT_TEST_QDRANT_URL='http://127.0.0.1:49634'
$env:VIBECRAFT_REQUIRE_QDRANT='1'
```

Ogni comando è stato eseguito nel worktree, con l'interprete esistente
`C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe`.

RED iniziale:

```powershell
& C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -m pytest rag/tests/test_project_indexing.py -q --tb=short
```

5 fallimenti per keyword `project` non supportato, 3 skip server senza endpoint
in quella prima esecuzione. Nessuna modifica produttiva precede quel test.

RED successivi, con `-o addopts=''`:

- `-k 'corrupt or foreign or first_delta or traversal'`: 7 failed, 2 skipped,
  8 deselected; riprodotti fallback da CURRENT corrotto, alias verso collection
  estranea, primo delta senza collection versionata e traversal.
- `-k junction`: 8 failed, 17 deselected; junction Windows reali da A a B su
  hash, full, delta e scanner. Un primo tentativo aveva un errore nella fixture
  (`QdrantClient` non è context manager), corretto prima del RED comportamentale.
- `-k staging_junction`: 1 failed, 25 deselected; staging attraversava il junction.
- `-k 'staging_junction or auxiliary_scan'`: 1 passed, 1 failed, 25 deselected;
  lo scanner Razor ausiliario leggeva `PrivateProjectB` dal progetto collegato.

Regressioni intermedie: 13 failed/208 passed (firme dei doppi legacy), poi
2 failed/336 passed (token con underscore nelle fixture legacy). Entrambi i
problemi sono corretti senza indebolire le assertion. Gate precedenti verdi:
346 passed; successivo controllo parser/reader 74 passed.

Gate finale, sul codice e sui test definitivi:

```powershell
& C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -m pytest rag/tests/test_project_indexing.py rag/tests/test_artifacts.py rag/tests/test_colbert_store.py rag/tests/test_writer_lock.py rag/tests/test_qdrant_blue_green.py rag/tests/test_incremental_indexing.py rag/tests/test_eval_gate.py rag/tests/test_indexing_reexports.py rag/tests/test_versioning.py rag/tests/test_index_integrity.py rag/tests/test_eval_history.py rag/tests/test_projects.py rag/tests/test_code_index.py rag/tests/test_frontend_index.py rag/tests/test_razor_index.py rag/tests/test_reader_mode.py rag/tests/test_reader_process_leases.py -q --tb=short -o addopts=''
```

**397 passed in 69.29s**, exit 0, nessuno skip. Il gate comprende cinque prove A/B
parametrizzate su Qdrant in memoria e server reale, oltre alle prove Qdrant
esistenti. Le lease reali mantengono A/v1 leggibile durante promozione A/v2,
promozione/prune B e GC; dopo rilascio, retention e GC A rimuovono la vecchia versione.

```powershell
& C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -m ruff check rag/core/artifacts.py rag/core/indexing.py rag/core/qdrant_versions.py rag/core/writer_lock.py rag/core/colbert_store.py rag/core/eval_gate.py rag/code_index/__init__.py rag/code_index/razor.py rag/conftest.py rag/tests/test_project_indexing.py rag/tests/test_artifacts.py rag/tests/test_incremental_indexing.py rag/tests/test_index_integrity.py rag/tests/test_qdrant_blue_green.py
```

**All checks passed**. `git diff --check` globale segnala soltanto una riga vuota
finale in `docs/superpowers/plans/2026-10-02-multi-project.md:301`, file in lavorazione
dal PM; nessun whitespace error nei file posseduti da Task 2.

Il server reale usato è esclusivamente il container di prova dedicato sulla porta
49634. Namespace UUID temporanei; cleanup limitato agli alias/collection esatti
creati dal test, inclusa una sentinella legacy temporanea. Nessun accesso a 6333,
reindex del corpus reale, copia dati o nuova dipendenza.

## Interfacce per i task dipendenti

Le funzioni storage/index e Qdrant che prima selezionavano implicitamente un path
o namespace accettano ora `project: ProjectContext | None = None`. Passare il
keyword lungo tutto il job/richiesta, inclusi `writer_lock`, `load_artifacts`,
`current_version[_token]`, `artifact_dir`, `manifest_path`, `artifact_hashes`,
`list_versions`, `promote_version`, `resolve_rollback_target`, `rollback_version`,
`prune_versions`, `migrate_colbert_npy`, `docs_hashes`, `index_status`,
`check_index_integrity`, `check_graph_consistency`, `observe_docs_git_divergence`,
`build_graph_and_index`, `incremental_index`, `apply_incremental_indexing` e tutte
le funzioni Qdrant di naming/rollback/reconcile/GC.

ColbertStore e `try_version_lease` conservano la firma con `database_dir` esplicito:
ricevono sempre quello del progetto. Nessun import runtime di ProjectContext nei
moduli storage, quindi nessun ciclo con `core.projects`.

Helper Qdrant di basso livello che già ricevono alias/collection espliciti
(`_swap_alias`, `_read_alias_target`, `_ensure_collection`, `_delete_doc_chunks`)
mantengono il contratto. `gate_promotion(..., project=project)` deriva l'alias se
`collection_name` non è specificato; una candidata deve continuare a essere passata
esplicitamente dal chiamante.

## Self-review e limiti concordati

- Task 3 deve completare `retrieval.hybrid_search` / `restatement_sections` e il
  ranking con impostazioni project-aware, quindi propagare `project` da
  `eval_gate.evaluate_recall`. In Task 2 golden, collection, soglia gate e storico
  sono isolati; i pesi authority/retrieval del ranking restano quelli esistenti.
  Confine concordato col PM, nessuna modifica a retrieval in questo task.
- Task 3/4/5 devono passare il contesto nei caller esterni: `api/deps.py`,
  reindex/routes, pipeline/intake/import, CLI e moduli eval. `None` rimane legacy
  finché ciascun caller non è aggiornato dal suo task.
- Writer lock e lease OS sono riusati. La serializzazione dei job tra progetti
  e la cache snapshot residenti restano responsabilità del runtime/reindex.
- `code_index._LAST_RAZOR_REPORT` e SQL `FALLBACK_LOG` restano diagnostiche globali;
  il PM ha verificato che nessun router/runtime legge `razor_report` attualmente.
  `frontend._framework_cache` include già la root codice nella chiave.
- Il delta conserva il limite preesistente: modifica i vettori della lineage
  corrente in place. Un rollback tra versioni delta della stessa lineage non
  riavvolge i punti; un full rebuild crea una collection distinta.
- Non è stata rieseguita l'intera suite: autorizzato il gate mirato, full gate
  previsto dal piano per Task 8. Nessun fallimento residuo nei test eseguiti.

## Review fix round 1 — golden confinement, CURRENT e snapshot immutabili

Status: implementato e verificato, pronto per nuova review. Questo round
**sostituisce la semantica delta descritta sopra per i progetti ordinari**:
la lineage mutabile resta esclusivamente legacy. Modificati soltanto
`artifacts.py`, `indexing.py`, `eval_gate.py` e `test_project_indexing.py`.

Tre difetti riprodotti e corretti:

1. Un junction `<A.root>/eval -> <B.root>/eval` consentiva al gate A di leggere
   il golden B. Il gate valida ora il file golden e tutta la catena degli antenati
   prima di chiamare il loader tollerante. Un link/junction o escape causa un
   `ValueError` esplicito; non diventa `no_golden_set` e non entra nel fail-open.
   Il controllo usa il contesto catturato, quindi protegge anche link creati dopo
   la registrazione. Il normale file mancante mantiene il fail-open previsto.
2. `CURRENT=legacy` in un progetto ordinario era accettato e attivava il layout
   sintetico flat. Il token è ora rifiutato nel lettore CURRENT e nel resolver
   delle versioni, anche quando `artifact_dir` o `load_artifacts` ricevono la
   versione esplicitamente. I percorsi legacy reali conservano il comportamento.
3. Il delta ordinario modificava la collection v1 mentre una lease conservava
   ColBERT v1: snapshot e rollback diventavano misti. Ora un progetto ordinario
   usa sempre il profilo immutable esistente, scrive il marker e richiede un
   manifest immutable con collection fisica dedicata alla propria versione.
   Un delta non-noop riusa il full rebuild già esistente; la vecchia collection
   non cambia, la nuova viene pubblicata tramite alias e rollback ripristina anche
   i risultati Qdrant. Nessun clone/COW o nuova gestione lease.

Costo esplicito: nei progetti ordinari un delta effettivo rilegge e ri-embeddizza
**tutti** i sorgenti. `changed_paths` decide se avviare il lavoro; una volta deciso,
il full rebuild comprende tutto il corpus. Il controllo no-op è conservato.
Il commento `ponytail:` indica di aggiungere un delta copy-on-write solo se il
costo del rebuild lo giustifica. Questa scelta è stata richiesta e confermata
dal PM durante la review.

RED, con runtime/env e Qdrant dedicato descritti sopra:

```powershell
& C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -m pytest rag/tests/test_project_indexing.py -k 'linked_golden or synthetic_legacy or pinned_vectors' -q --tb=short -o addopts=''
```

**9 failed, 27 deselected in 11.79s**: due junction golden, cinque lettori del
token sintetico, due prove Qdrant (memoria/server). La prova Qdrant misurava
con query densa reale lo score della collection v1: atteso `+1`, ottenuto `-1`
dopo il delta mentre ColBERT v1 era ancora in lease.

GREEN finale del round:

```powershell
& C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -m pytest rag/tests/test_project_indexing.py rag/tests/test_artifacts.py rag/tests/test_colbert_store.py rag/tests/test_writer_lock.py rag/tests/test_qdrant_blue_green.py rag/tests/test_incremental_indexing.py rag/tests/test_eval_gate.py rag/tests/test_indexing_reexports.py rag/tests/test_versioning.py rag/tests/test_index_integrity.py rag/tests/test_eval_history.py rag/tests/test_projects.py rag/tests/test_code_index.py rag/tests/test_frontend_index.py rag/tests/test_razor_index.py rag/tests/test_reader_mode.py rag/tests/test_reader_process_leases.py -q --tb=short -o addopts=''
```

**406 passed in 74.27s**, exit 0, nessuno skip. Dopo il fix la query su v1 resta
`+1`, quella sull'alias v2 diventa `-1`, il rollback A restituisce `+1` e B resta
invariato. Marker e manifest immutable sono verificati; le regressioni legacy
passano insieme alle prove reali di reader/lease.

```powershell
& C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -m ruff check rag/core/artifacts.py rag/core/indexing.py rag/core/eval_gate.py rag/tests/test_project_indexing.py
git diff --check -- rag/core/artifacts.py rag/core/indexing.py rag/core/eval_gate.py rag/tests/test_project_indexing.py
```

Ruff e diff-check del round verdi. Nessun commit/stage da questo agente.

## Review fix round 2 — link nei file degli artefatti

Status: implementato e verificato, codice stabile per review. Modificati
`artifacts.py`, `indexing.py` e `test_project_indexing.py`; nessun commit/stage.

La guardia condivisa `_project_artifact_path(path, project)` verifica che il
percorso appartenga al database selezionato e che né il file né alcun antenato
siano symlink/junction. Il percorso risolto deve restare nel database. `None`
conserva il comportamento storico. La guardia precede gli accessi a CURRENT,
manifest, versioni, marker, graph/chunks/dense/code/ColBERT NPZ e hashing. È
applicata anche a migrazione NPZ, promozione, rollback e percorso di retention.
Le directory vengono validate prima delle lease, evitando accessi ai lock su
una directory già reindirizzata. I controlli ColBERT esistenti sono conservati.

Il controllo d'integrità leggeva chunks e ColBERT NPZ direttamente dopo avere
registrato un errore di hashing. Ora valida quei percorsi prima di leggerli;
una segnalazione di corruzione non consente comunque una lettura attraverso link.
I futuri caller che costruiscono un percorso aggiungendo un filename ad
`artifact_dir` devono usare la stessa guardia o il loader degli artefatti.

RED:

```powershell
& C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -m pytest rag/tests/test_project_indexing.py -k 'artifact_file_link or version_junction' -q --tb=short -o addopts=''
```

**15 failed, 14 skipped, 36 deselected in 20.61s**. I fallimenti attivi sono
junction reali sugli stessi percorsi di file, lettura/scrittura CURRENT,
manifest, sidecar e retention: il codice raggiungeva I/O sul junction o tentava
la rimozione senza il controllo previsto. I veri symlink ai file sono stati
tentati ma Windows restituisce `WinError 1314`: l'utente non dispone del privilegio
CreateSymbolicLink. I test riportano esplicitamente questo motivo e vengono
eseguiti senza skip dove il sistema consente la creazione.

RED aggiuntivo del bypass nel controllo d'integrità:

```powershell
& C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -m pytest rag/tests/test_project_indexing.py -k 'integrity-junction' -q --tb=short -o addopts=''
```

**1 failed, 70 deselected in 11.93s**. La verifica non rifiutava il path collegato
e continuava nel ramo di lettura. Aggiunti inoltre i casi ColBERT NPZ.

GREEN intermedio: 298 passed, 14 skipped in 76.42s.

Gate finale del round, con `PYTHONPATH`, `PYTHONUTF8`, endpoint Qdrant dedicato
49634 e `VIBECRAFT_REQUIRE_QDRANT=1` come nei round precedenti:

```powershell
& C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -m pytest rag/tests/test_project_indexing.py rag/tests/test_artifacts.py rag/tests/test_versioning.py rag/tests/test_colbert_store.py rag/tests/test_qdrant_blue_green.py rag/tests/test_incremental_indexing.py rag/tests/test_index_integrity.py rag/tests/test_reader_mode.py -q --tb=short -o addopts=''
```

**301 passed, 17 skipped in 80.18s**, exit 0. Tutti i 17 skip riguardano
esclusivamente il privilegio Windows per i symlink FILE; tutte le corrispondenti
prove junction e le prove Qdrant reale sono state eseguite e passano. Nessun
fallback simulato o cambio permessi di sistema per aggirare il limite OS.

```powershell
& C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -m ruff check rag/core/artifacts.py rag/core/indexing.py rag/tests/test_project_indexing.py
git diff --check -- rag/core/artifacts.py rag/core/indexing.py rag/tests/test_project_indexing.py
```

Ruff e diff-check verdi; nessuna esecuzione della suite completa.

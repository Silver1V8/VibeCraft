# Task 1 report — registry, contesto e bootstrap legacy

Status: **DONE**. Implementazione e verifiche mirate verdi; suite completa verde prima del delta finale di confinement, verificato poi con 33 test mirati e Ruff.

## File modificati

- `rag/core/projects.py`: `ProjectContext` frozen con il contratto esatto; `ProjectRegistry.list/get/create/register`; `legacy_project_context` e `validate_project_id`; `ProjectError` con `status_code` e `code` per gli adapter HTTP.
- `rag/core/config.py`: `INSTALL_ROOT` distinto dai contesti e `PROJECTS_DIR` da env assoluto, default `<INSTALL_ROOT>/projects`; nessuna modifica ai percorsi storici.
- `rag/tests/test_projects.py`: 33 casi reali su filesystem temporaneo, inclusi sei processi concorrenti e junction Windows reali.
- `.gitignore`, `.dockerignore`: storage default `projects/` escluso.
- Questo report.

## Contratto e implementazione

Constructor aggiuntivo approvato dal PM: `ProjectRegistry(projects_dir=None, *, legacy_context=None, bootstrap_legacy=True)`. Il seam `legacy_context` permette test senza modificare i percorsi globali né accedere al corpus reale. La registrazione legacy conserva root, code/docs/changes/database/staging e collection correnti; nessun manifest legacy, spostamento, indicizzazione o accesso Qdrant. Un registry vuoto esistente non viene rigenerato.

`ProjectError`: 422 input/manifest non validi; 409 ID/root duplicati, overlap e reader mutante; 404 ID valido sconosciuto; 503 registry corrotto o progetto già registrato non apribile. Il resolver HTTP resta di Task 2. Nessun fallback al primo progetto.

Le scritture riusano `_atomic_write_json/_atomic_write_text` di `core.artifacts` e `writer_lock` cross-processo su `.projects.lock`. Nessun database o lock implementato nuovamente. Il registry valida schema/versione, tipi, chiavi duplicate JSON, unicità ID/root e root canoniche. I manifest usano SafeLoader con rifiuto delle chiavi duplicate YAML. ID `legacy` riservato, nomi soltanto metadati: HTML/traversal nel nome non costruisce percorsi.

Settings copiati profondamente dalla configurazione dell'installazione; ammessi soltanto blocchi authority/retrieval/eval_gate/eval_multihop/verification, con chiavi e tipi già disponibili. Comandi verification solo argv non vuoti da manifest locale, nessuna esecuzione all'apertura. Override di percorsi, Qdrant/embedding, segreti, endpoint e ruolo respinti.

Root e cartelle operative, comprese database/versions/pipeline/eval/staging, rifiutano symlink/junction; roots ordinarie sovrapposte e roots che inglobano storage registry respinte. L'overlap legacy comprende staging anche se esterno al database/root storico. Il reader non crea storage/lock quando il registry manca, legge quello esistente e rifiuta le mutazioni.

## Letture e ricerca chiamanti

Letti brief integrale, `core/config.py`, `core/writer_lock.py`, primitive atomic di `core/artifacts.py`, `core/verification.py`, whitelist `validate_dev_type`, configurazione YAML, pyproject/pytest e ignore file. Cercati import/default di PROJECT_ROOT/CODE_DIR/DOCS_DIR/CHANGES_DIR/DATABASE_DIR/COLLECTION_NAME e validatori/atomic helpers con `rg`. Nessun AGENTS.md individuato nel worktree. Skills TDD, writing-good-tests e Ponytail lette; using-superpowers indica esplicitamente skip per subagent.

## Red / green e comandi reali

Tutti i comandi eseguiti con workdir esplicito nel worktree isolato; test da `rag/`, `PYTHONPATH=C:/Users/Silve/.codex/worktrees/multi-project/vibecraft/rag`, `PYTHONUTF8=1`. Interprete esistente Python 3.14.6: `C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe`.

1. Test-first: `python.exe -m pytest tests/test_projects.py -rs` → collection error atteso `ModuleNotFoundError: core.projects`: modulo feature ancora assente. Riportato precisamente, senza presentarlo come assertion failure.
2. Prima implementazione: medesimo comando → 22 passed, 1 failed. Failure del helper test: nome argomento `root` collideva con campo manifest vietato `root`. Corretto helper in `directory`.
3. Secondo red con casi di sicurezza aggiunti: medesimo comando → 26 passed, 2 failed: `test_duplicate_yaml_keys_and_nested_settings_are_rejected` e `test_registering_registry_directory_is_rejected`, entrambi `DID NOT RAISE ProjectError`. Implementati rifiuto delle chiavi YAML duplicate e containment dello storage registry.
4. Green: medesimo comando → **28 passed in 8.38s**, nessuno skip.
5. `python.exe -m ruff check core/projects.py core/config.py tests/test_projects.py` → **All checks passed**.
6. Suite completa: con `VIRTUAL_ENV=C:/Users/Silve/Desktop/vibecraft/rag/.venv`, `uv run --frozen --no-sync --active pytest -rs` → **2123 passed, 10 skipped in 262.34s (4m22s)**. Cinque skip `test_intake_docling.py` (pesi Docling assenti nel worktree), cinque skip `test_qdrant_blue_green.py` (`VIBECRAFT_TEST_QDRANT_URL` assente). Sono gli stessi prerequisiti mancanti della baseline; nessun failure. Nessun sync dipendenze o modifica lockfile.
7. Seconda verifica frozen mirata: `uv run --frozen --no-sync --active pytest tests/test_projects.py -rs` → **28 passed in 10.87s**; `git diff --check` senza errori.
8. Self-review e rilievo reviewer/PM: test-first `uv run --frozen --no-sync --active pytest tests/test_projects.py -k linked_database_subdirectories -rs` → **3 failed, 28 deselected**, `DID NOT RAISE ProjectError` per versions/pipeline/eval con junction esterna. Test-first `... pytest tests/test_projects.py -k external_legacy_staging -rs` → **2 failed, 31 deselected**, `DID NOT RAISE ProjectError` per root parent/nested dello staging legacy esterno. Guardia dei tre dirs e protezione staging aggiunte dopo i red.
9. Green finale dello scope: `uv run --frozen --no-sync --active pytest tests/test_projects.py -rs` → **33 passed in 6.52s**. `uv run --frozen --no-sync --active ruff check core/projects.py core/config.py tests/test_projects.py` → **All checks passed**.

La suite completa del punto 6 ha raccolto 28 test registry prima dell'ultimo delta; il punto 9 verifica anche i cinque casi ulteriori e le guardie finali. La verifica d'integrazione completa del piano resta al PM.

Baseline completa precedente del PM: 2095 passed, 10 skipped, Ruff verde. Successivo scope finale verificato anche indipendentemente dal PM: 33 passed e Ruff verde.

## Self-review e limiti

- Test A/B con stesso nome, collection/database differenti, layout pronto senza CURRENT né duplicazione pesi; get/list roundtrip.
- Sei processi reali creano progetti sullo stesso registry senza perdere record; duplicate ID/root lasciano bytes registry invariati.
- JSON corrotto/versioni sconosciute/tipi errati, manifest malformati e override vietati non provocano fallback o riscrittura del registry.
- Junction reali di root/storage e code, anche introdotte dopo la registrazione, respinte. Test dati soltanto in `tmp_path`; nessuna cancellazione del corpus.
- Artefatto legacy test preservato byte per byte e percorsi custom/staging/collection invariati attraverso bootstrap ripetuto; registry intenzionalmente svuotato resta vuoto.
- Settings di contesti distinti e configurazione globale indipendenti anche dopo mutazione del dict di un contesto. La dataclass frozen rispetta il contratto; `settings: dict` resta strutturalmente mutabile come richiesto, sempre copiato.
- Atomicità copre il file registry; un errore filesystem durante la creazione può lasciare una root nuova non registrata. Non effettuo cancellazioni automatiche di cartelle per non rischiare dati; l'ID UUID nuovo e `mkdir` senza `exist_ok` impediscono sovrascritture.
- I controlli symlink/junction riusano la strategia esistente di validazione dei percorsi, non una nuova piattaforma di filesystem handles. Non promettono resistenza a un processo locale privilegiato che sostituisce path tra controllo e uso.
- Eseguito e verificato su Windows; il lock POSIX usa il ramo `fcntl` già esistente, non eseguito su questo host.
- Dipendenza atomic helpers: Task 2/3 devono evitare import runtime inverso `artifacts -> projects`; usare `TYPE_CHECKING` per annotazioni o seam paths. PM informato.

Nessun commit o staging effettuato. Nessun subagente avviato.

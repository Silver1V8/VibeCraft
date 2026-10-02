# Task 3 — re-review fix round 1

Esito: **due finding originali ADDRESSED; Spec/correttezza FAIL per un nuovo P2 del delta**. Standard/manutenibilità PASS, nessun finding aggiuntivo. Letti package completo `task-3-fix-1-review-package.md`, tutti i nove file del delta e appendice RED/GREEN del report Task3. Scope readonly; nessun backend/test modificato, stage, commit o subagent. UI congelata esclusa dalla review.

## Finding originali

- **P2 stale: ADDRESSED.** Metadata passa la directory versionata già catturata a `index_status(project, version=...)`; il valore ISO storico nel manifest/result.version è conservato. Test usa `write_index_manifest` reale e prova stale false→true, poi promuove v2 fra cattura metadata e calcolo: v1 conserva i propri hash e resta stale. Non si confondono token directory e timestamp.
- **P2 restatement/config: ADDRESSED.** La classificazione dipende solo dal testo dello snapshot, il peso dal contesto della richiesta. Test cambia YAML 1.0→0.5 senza reload e verifica lo stesso vincitore dopo eviction A mediante B/C e ricaricamento. L'asserzione statica aggiornata da set vuoto a completo corregge il presupposto del bug e conserva le asserzioni di ranking A/B.

Controlli ulteriori PM: cache include digest canonico dei soli blocchi authority/retrieval del contesto catturato, senza config in chiaro; prova HTTP miss/hit dopo ogni cambio dei due blocchi. Guard source_files include gli ancestor root; junction docs/root/nested reali falliscono prima della lettura e preservano il target B. Fallback /ask legacy valida docs root e file con `_unlinked`, error503 sanitizzato e nessun prompt raggiunge LLM. Le estensioni a indexing/code_index restano minime e motivabili dalle prove. Non rilevate nuove contaminazioni o cambi del lifecycle snapshot/lease.

## Nuova regressione

### [P2] Preservare i Markdown con estensione maiuscola su Windows

`rag/api/deps.py:700` usa ora `if spec_file.suffix != '.md': continue` dopo `source_files`. Il precedente `docs_dir.rglob('*.md')` era case-insensitive su Windows; `spec.MD` veniva letto. Ora il confronto stringa case-sensitive lo elimina, perdendo le descrizioni delle regole dal progetto legacy senza cambiare sorgenti o indice. Regressione introdotta soltanto da questo fix, non necessaria al confinement.

Riproduzione readonly reale Windows, con Python originale e import worktree:

```python
from tempfile import TemporaryDirectory
from pathlib import Path
from dataclasses import replace
from api.deps import load_rule_descriptions
from core.projects import legacy_project_context
with TemporaryDirectory() as tmp:
    docs = Path(tmp) / 'docs'
    docs.mkdir()
    (docs / 'spec.MD').write_text('`[REGOLA-X]`: Visible legacy rule', encoding='utf-8')
    project = replace(legacy_project_context(), root=Path(tmp), docs_dir=docs)
    print('PREVIOUS_MATCHES', [p.name for p in docs.rglob('*.md')])
    print('CURRENT_DESCRIPTIONS', load_rule_descriptions(project))
```

Output effettivo, exit0: **PREVIOUS_MATCHES ['spec.MD']**, **CURRENT_DESCRIPTIONS {}**. Atteso `{'REGOLA-X': 'Visible legacy rule'}`. Correzione minima: riconoscere l'estensione normalizzata, mantenendo i guard source_files/_unlinked e un test `.MD`/`.md`. Le sette regressioni correnti usano soltanto secret.md e non coprono questa compatibilità. Nessuna modifica applicata dal reviewer.

## Verifiche effettive

Cwd esplicito `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft`; `PYTHONUTF8=1`, `PYTHONPATH=<worktree>/rag`, Python `C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe`; env Qdrant dedicato49634 + REQUIRE_QDRANT=1 sul gate delle nuove regressioni. Nessun install/sync/full suite.

```powershell
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -m pytest rag/tests/test_project_api.py rag/tests/test_project_runtime.py -k 'settings_change or captured_version or junction_after or legacy_ask_fallback' -ra --tb=short
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -m pytest rag/tests/test_index_status.py rag/tests/test_ask_cache.py rag/tests/test_code_index.py -ra --tb=short
git diff --check -- rag/api/deps.py rag/api/routes_projects.py rag/api/routes_retrieval.py rag/code_index/__init__.py rag/core/ask_cache.py rag/core/indexing.py rag/core/retrieval.py rag/tests/test_project_api.py rag/tests/test_project_runtime.py
```

Personale: **7 passed, 21 deselected in 13.24s; 39 passed in 11.63s**, entrambi exit0 e nessuno skip. Le junction Windows sono state eseguite. Riproduzione estensione maiuscola via Python stdin: exit0, difetto confermato. Diff-check exit0. Il gate worker220pass18skip/Qdrant reale è evidenza nel suo report, non ripetuto da questo reviewer; la selezione personale delle sette regressioni non invoca Qdrant.

Handoff: Task4/5 writers e Task8 integrato restano separati. Re-review mirata della correzione estensione necessaria prima del PASS Task3; nessun altro finding del delta.

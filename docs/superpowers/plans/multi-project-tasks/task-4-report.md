# Task 4 — workflow isolation report

Status: implementation candidate; independent review requested five corrections, now implemented and pending re-review. Base HEAD `4223b84`; the PM staged the initial candidate, and the correction delta remains unstaged. The implementer performed no stage, commit, provider call, production reindex, dependency installation or original-checkout edit.

Worktree: `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft`. Interpreter: existing `C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe`; `PYTHONUTF8=1`, worktree `rag` in `PYTHONPATH`.

## Behavior and boundaries

- Project-specific reindex/generation/refine/brief managers and import plans are cached under the captured runtime ID; pipeline store, validations, decisions, events, feature locks, staging and journals use captured project paths. Jobs and callbacks receive the admission context explicitly. Same feature, document path or version in A/B does not select shared storage.
- Shared process indexing lock is acquired before the project writer lock for reindex, intake approval and rollback. Archive releases its feature/mutation locks before acquiring the indexing slot for a rebuild. Existing coalescing and reload semantics remain; failed jobs release the slot and queued work proceeds.
- Guarded file and ancestor paths reject linked storage, including Windows junctions. Database-backed pipeline/journal paths reuse `_project_artifact_path`; code/docs/changes/staging files use `_unlinked` and confinement checks.
- Async pipeline/intake admission offloads `require_snapshot` and shared-resource initialization to the existing threadpool. Synchronous worker functions stay synchronous. Captured snapshots survive delayed generation and captured projects survive delayed reindex/reload.
- Ordinary projects use their golden set, eval history, alerts and candidate archive paths. Legacy retains existing configured paths and fail-open no-golden policy. Archived-spec detection tests the selected project's archive root; frozen gate validation intentionally checks contract text without an archive bypass.
- Workflow storage, job/gate and canvas/propose/explore provider failures preserve status, terminal job/gate state and availability meaning without returning private diagnostic strings. Explore retains its HTTP 200 tolerant interaction and safe history; missing staged Markdown retains 404. Intake/pipeline UI use the existing shared `apiErrorMessage`; error rendering remains text/escaped HTML.
- Archive treats captured code, including an explicit empty string, as authoritative: no Git/tasks fallback can substitute another project's code. Standalone omitted-code review keeps its historical fallback but only uses Git when the supplied root is the repository's exact top-level.
- External prompts include the originating `X-VibeCraft-Project` HTTP header and fixed `VIBECRAFT_PROJECT_ID` MCP startup binding. Gate source acquisition lazily loads healthy persisted snapshots after a cold start or LRU eviction; genuine index errors remain structured `sources_unavailable` responses.
- Browse-path remains an installation-global, authenticated/local-bind capability and works with zero projects. No project resolver was added to this route.
- Health's stale singleton import was removed. Existing runtime managers supply live status; when absent, a temporary `ReindexManager(..., recover_journal=False)` reads persisted legacy/ordinary history without persisting interrupted transitions or compacting. Mutating submission retains the default recovery and one runtime manager under its lock. Reader imports/initializes no writer manager.

## Exact owned files

The following product/test files belong to Task 4 (PM plan/ledger edits excluded):

- `rag/api/reindex.py`
- `rag/api/routes_health.py`
- `rag/api/routes_intake.py`
- `rag/api/routes_pipeline.py`
- `rag/api/routes_reindex.py`
- `rag/core/canvas_review.py`
- `rag/core/doc_generation.py`
- `rag/core/drift_check.py`
- `rag/core/eval_gate.py`
- `rag/core/eval_history.py`
- `rag/core/feature_archive.py`
- `rag/core/indexing_lock.py`
- `rag/core/intake.py`
- `rag/core/intake_refine.py`
- `rag/core/pipeline.py`
- `rag/core/pipeline_activity.py`
- `rag/core/pipeline_store.py`
- `rag/core/pipeline_validation.py`
- `rag/core/project_brief.py`
- `rag/core/project_import.py`
- `rag/core/verification.py`
- `rag/static/pages/intake.js`
- `rag/static/pages/pipeline.js`
- `rag/tests/conftest.py`
- `rag/tests/pipeline_agent.cjs`
- `rag/tests/pipeline_dryrun_escape.cjs`
- `rag/tests/test_canvas_review.py`
- `rag/tests/test_health.py`
- `rag/tests/test_intake_docling.py`
- `rag/tests/test_intake_excel.py`
- `rag/tests/test_intake_generate_routes.py`
- `rag/tests/test_intake_staging.py`
- `rag/tests/test_pipeline.py`
- `rag/tests/test_pipeline_execution.py`
- `rag/tests/test_pipeline_validation.py`
- `rag/tests/test_project_brief.py`
- `rag/tests/test_project_import.py`
- `rag/tests/test_project_workflows.py`
- `rag/tests/test_reindex.py`
- `rag/tests/test_security_fixes.py`
- `rag/tests/test_verification.py`
- `rag/tests/workflow_errors.cjs`

This report is the sole Task 4 documentation artifact. `docs/superpowers/plans/2026-10-02-multi-project.md` and `...-progress.md` remain PM-owned.

## Fresh verification

Final post-correction unified 24-file gate: **824 passed, 0 failed, 0 skipped, 15 Docling deprecation warnings, 135.06s; exit 0**. Includes 45 workflow cases (35 initial plus 10 review regression cases, including parametrization), actual pinned/offline Docling conversions and historical security checks. The earlier pre-correction gate was 814 passed in 128.55s. Command from worktree `rag/`:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH='C:/Users/Silve/.codex/worktrees/multi-project/vibecraft/rag'
$env:VIBECRAFT_REQUIRE_DOCLING='1'
$env:HF_HUB_OFFLINE='1'
$env:HF_HOME='C:/Users/Silve/.codex/worktrees/multi-project/vibecraft/rag/database/models/hf'
$env:VIBECRAFT_TEST_QDRANT_URL='http://127.0.0.1:58123'
$env:VIBECRAFT_REQUIRE_QDRANT='1'
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -m pytest tests/test_project_workflows.py tests/test_pipeline.py tests/test_pipeline_execution.py tests/test_pipeline_validation.py tests/test_intake_staging.py tests/test_intake_generate_routes.py tests/test_project_import.py tests/test_project_brief.py tests/test_reindex.py tests/test_intake.py tests/test_intake_refine.py tests/test_canvas_review.py tests/test_docs_archive.py tests/test_eval_gate.py tests/test_eval_history.py tests/test_verification.py tests/test_intake_convert.py tests/test_intake_docling.py tests/test_intake_excel.py tests/test_intake_clean.py tests/test_intake_page.py tests/test_pipeline_gate.py tests/test_health.py tests/test_security_fixes.py -q -o addopts='' --tb=short
```

Intermediate fresh gates, not summed as unique coverage:

| Gate | Observed result |
| --- | --- |
| Final post-correction unified 24-file gate | 824 passed, 0 failed, 0 skipped, 15 warnings, 135.06s |
| Initial unified 24-file gate, before review corrections | 814 passed, 0 failed, 0 skipped, 15 warnings, 128.55s |
| Review correction batch: 10 new cases | 10 passed, 0 failed, 0 skipped, 14.65s |
| Post-correction workflow/pipeline/canvas/gate/intake-staging | 217 passed, 0 failed, 0 skipped, 4 warnings, 57.55s |
| Nine workflow/pipeline/intake/import/brief/reindex files | 330 passed, 0 skip, 4 Docling deprecation warnings, 58.40s |
| Workflow + health + verification + Excel + canvas review | 114 passed, 0 skip, 39.54s |
| Historical security suite after explicit-context adapters | 223 passed, 0 skip, 48.88s |
| `python -m ruff check rag` / later `ruff check .` from rag | Exit 0, all checks passed |
| Node `workflow_errors.cjs` | Exit 0: generation/prompt/upload/polling errors 409/503/404 and XSS checks |
| Existing Node pipeline_validation, pipeline_agent, pipeline_dryrun_escape, intake_excel_preview | Exit 0; shared-error helper loaded in the two existing extractor harnesses |
| Node syntax checks intake.js/pipeline.js | Exit 0 |

## TDD and corrected regressions

Independent review correction batch 1 closes the five findings in `task-4-review.md` with changes only to `routes_intake.py`, `routes_pipeline.py`, `canvas_review.py`, `pipeline.py` and `test_project_workflows.py`, all inside the 42-file ownership. Ten added cases passed with zero skips in 14.65s after the fixes. The corrected RED run had eight regressions fail and the two nonempty captured-code controls pass; preview's missing-file leak was separately reproduced as one failing test. Initial probe setup errors (missing backend folder, non-loopback TestClient and staging docs subdirectory) were corrected before counting behavioral RED evidence.

- Actual archive on ordinary and temporary legacy contexts inside a real parent Git repository with B tracked, a matching feature commit and B task-file reference: explicit empty A code never calls fallback; nonempty A code is preserved. Standalone nested A review selects A tasks instead of B's parent Git diff. Existing exact-root Git tests retain positive behavior.
- Prompt A/B transport instructions contain their own captured header/environment ID and exclude the other's ID; omitted-context compatibility is preserved.
- Actual immutable A/B/C artifact loads and a passing persisted A gate prove cold acquisition, eviction/reload without changing validation bytes, safe `sources_unavailable` after genuine corrupt CURRENT, and B availability. A held gate loader proves B responds before release and snapshot capture runs off the event-loop thread.
- Explore provider-boundary failure with synthetic private path/token yields safe ai_response and history with HTTP 200; a successful generation returns the original expected answer/history.
- Actual staged Markdown upload and successful preview followed by deletion of only the just-created fixture derivative yields a safe 404; staged journal state remains intact.

- The preflight UI repro exercised actual `startGeneration` and produced `Errore: [object Object]`; `workflow_errors.cjs` now exercises generation, final prompt, multipart upload and polling with structured 409/503/404 errors and malicious strings.
- Fresh initial admission regression, after correcting its `documents` typo to the real `staged` response key: B request stalled 0.552s on A's loader (RED). After offload the final test proves B responds while A's loader is physically held and both loaders run off the event-loop thread. The physical barrier replaced a flaky 0.3s wall-clock threshold; the responsiveness requirement remains stronger than completion-order testing.
- Four typed HTTP error cases leaked an absolute project root plus `private-provider-key` (RED). Conversion/refine/import error messages were sanitized; the final gate retains each expected 422 status and absence of private diagnostics.
- Fresh process `import server` reproduced the removed `routes_reindex.manager` import (RED). Health now uses the captured project manager/read-only view; process-import and legacy/A/B history tests pass. Byte checksum, mtime, sidecar absence, read-only file mode and a forced compaction boundary prove GET does not persist/compact.
- Same-feature storage, independent operator decisions, valid gate A denying B, upload/approval, cross-plan refusal, archive/drift sources, actual refine preserving raw bytes, delayed generation snapshot and delayed reindex reload are covered in `test_project_workflows.py`. New A/B tests never request the historical legacy fixture.
- Historical HTTP tests explicitly opt into `legacy_workflow_project` where they patch legacy paths. Direct handler tests pass `project=None`; fake callable signatures accept captured context. Original auth, 403, publication, gate and terminal-state assertions remain.

## Test artifacts and limits

An early broader gate was invoked from the worktree root, producing 11 fixture-relative missing-file errors; it was rerun from `rag/` without product changes for those errors. Additional historical Excel/Docling HTTP tests lacked their opt-in context fixture and therefore wrote fixture artifacts into the ignored worktree legacy storage. The adapter was corrected before the final gate.

Only these two test-created docs were moved to quarantine, after validating their `intake.sha256` against the corresponding committed Excel fixture:

- `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft/docs/04_knowledge_informative/casi_excel.xlsx.md` → `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft/docs/superpowers/plans/multi-project-tasks/task4-test-quarantine/casi_excel.xlsx.md`.
- `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft/docs/04_knowledge_informative/casi_excel.xls.md` → `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft/docs/superpowers/plans/multi-project-tasks/task4-test-quarantine/casi_excel.xls.md`.

The PM subsequently moved those same two verified files into the ignored development-evidence directory above; SHA256 of the published fixture Markdown: XLSX `A7A15C5D5FF949A5D91E8AE5BBC23D8CFE1E51EDF87CEBA45B7D26721A701017`, XLS `E00FFDBA2FEFE34ECA62E1EB5CF28DD29C9DA3A19CCF523288ACD81AC84D5299`. No original checkout/corpus file was touched. Ignored worktree staging fixture residue is retained; no broad cleanup is attempted. The complete branch gate and actual A/B Qdrant build/query/rollback/GC and real browser integration remain Tasks 8. Current Task 4 tests mock providers and use isolated temporary storage/in-memory Qdrant as applicable; setting the dedicated Qdrant URL does not by itself establish a real-Qdrant Task 4 proof. Windows junction proofs are real; PM's Linux actual symlink proof is independently owned and must be cited separately by the PM.

`rag/scripts/bench_delta.py:336` still references the former singleton in an experimental legacy benchmark. It is outside this task's ownership and has been handed to Task 5. No Task 5/7/8 completion is claimed.

The legacy `generate_tolerant` helper retains its compatibility semantics; the HTTP explore route now calls the provider directly and applies the safe public boundary. No provider implementation or native runner work was added.

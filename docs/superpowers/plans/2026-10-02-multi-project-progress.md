# SDD ledger — plan: docs/superpowers/plans/2026-10-02-multi-project.md

Baseline: 34b46dfeabcff05820240a1241baae1a215d3e1b; branch codex/multi-project; worktree C:/Users/Silve/.codex/worktrees/multi-project/vibecraft. Original checkout untouched.

| Task | State | Model | Agent | Owned files |
|---|---|---|---|---|
| 1 registry | complete | sol/high | task1_registry | projects.py, config.py, test_projects.py, ignore files |
| 2 indexing | complete | astra/high | task2_indexing | artifacts, colbert, writer_lock, qdrant_versions, indexing |
| 3 runtime | queued | astra/high | — | deps/server/projects/retrieval/graph/health/cache |
| 4 workflows | queued | sol/high | — | pipeline/intake/reindex/eval core/routes |
| 5 tools | queued | sol/high | — | agent_bridge/runners/MCP/CLI |
| 6 UI | queued | sol/high | — | static/templates/routes_pages/Node tests |
| 7 distribution | queued | sol/medium | — | Compose/Dockerfile/env/README/CI |
| 8 integration | queued | sol/high; astra review | — | integration tests/report |

## Preflight contract scan

| Tasks | Shared surface | Finding/ruling |
|---|---|---|
| 1→2,3,4,5,6,7,8 | ProjectContext/Registry/config | Fixed dataclass contract from spec; None only legacy. Sequential 1→2→3. |
| 2→3,4,5,8 | snapshot/storage/indexing | project keyword passed explicitly; database/collection derived from context. |
| 3→4,5,6,7,8 | get_project/runtime/header | context captured on request/submit; routes retain existing paths. |
| 4↔5 | workflow agent invocation | Task 5 after 4 avoids concurrent core ownership. |
| 4↔6,5↔6 | page/API identity | UI owns only static/templates/routes_pages; backend owns workflow/tool files. |
| 7↔1,3,5,6 | ignore/config/health/docs | Task 7 follows backend/UI; persistence/readiness confirmed. |
| 8↔all | full branch | final independent review and verified integration. |
| 1 | own tests/implementation | consistent; canonical roots and corrupt registry fail closed. |
| 2 | own tests/implementation | consistent; GC exact project alias, leases retain snapshot. |
| 3 | own tests/implementation | consistent; empty shell doesn't import/load heavyweight resources. |
| 4 | own tests/implementation | consistent; explicit contexts in threads and golden paths. |
| 5 | own tests/implementation | consistent; installation path separate from code root. |
| 6 | own tests/implementation | consistent; per-frame fixed origin ID and retained cache. |
| 7 | own tests/implementation | consistent; health process distinct from corpus. |
| 8 | own tests/implementation | real smoke may depend on local tooling; report actual limits. |

## Decisions

Ruling: keep skill artifacts and ledger under docs/superpowers/plans/multi-project-tasks, not disposable .superpowers scratch — requested persistent report wins — no cost except tracked documentation.
Ruling: create PowerShell briefs/review packages instead of bash helper scripts — Windows environment and same content contract — no functional cost.
Ruling: use existing Python 3.14.6 environment with worktree cwd/PYTHONPATH and no-sync tools until dependency gap demonstrated — avoid reinstalling heavy models or changing lock — frozen lock consistency remains separate verification.
Ruling: permit UI/backend parallelism with exclusive files once Task 3 is reviewed — explicit plan authorization supersedes skill serial default — shared files remain serial.

## Evidence and blockers

- Worktree initially clean; detached HEAD baseline verified; branch created.
- Existing interpreter C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe reports Python 3.14.6.
- No AGENTS.md found by rg --files in worktree.
- Baseline tests/lint pending.
- Task 1 dispatched to /root/pm_multi_project/task1_registry (gpt-6.1-sol/high); no worker commits, exclusive registry/config/ignore/test ownership.
- Baseline ruff check .: passed; full pytest running (session 6122).
- uv sync --frozen --dry-run validates frozen resolution but would install 164 packages in absent worktree .venv; no environment or lock changed. Existing environment deliberately reused.
- Docker 29.8.1 active and qdrant/qdrant:v1.19.0 already local. Dedicated test container possible.
- Bundled Playwright resolves with NODE_PATH=C:/Users/Silve/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules.
Ruling: ProjectError exposes status_code/code and ProjectRegistry accepts dependency-injectable projects_dir/legacy_context/bootstrap_legacy — thin HTTP adapter and temporary fixtures without mutable globals — additive interface, dependent tasks must use it.
- Baseline Node gates all fail pre-existing: intake_excel_preview ReferenceError escapeHtml; pipeline_dryrun_escape/dashboard_graph_escape markers for escapeHtml absent. Helper moved to shared.js by HEAD but tests still extract page source. Task 6 will update test extraction without weakening assertions.
- Dedicated Qdrant test service: container vibecraft-multi-project-test-20261002 (7645a0589b27), http://127.0.0.1:49634, ephemeral no volume, qdrant/qdrant:v1.19.0. Only unique test namespaces used; remove this exact created container on completion.
Ruling: repair baseline Node extraction in Task 6 alongside UI because current gate tests are disconnected from served helper — preserves XSS assertions — minimal additional test files.

- Baseline full pytest -rs: 2095 passed, 10 skipped in 264.46s; 5 Docling skips for missing model weights in worktree, 5 Qdrant skips because first baseline intentionally had no test service env. Exit 0. Ruff baseline exit 0.
- Dedicated Qdrant /readyz returned HTTP 200; subsequent storage/integration tests set VIBECRAFT_TEST_QDRANT_URL=http://127.0.0.1:49634 and VIBECRAFT_REQUIRE_QDRANT=1.
- uv run --frozen --no-sync --active verified resolves existing Python when VIRTUAL_ENV=C:/Users/Silve/Desktop/vibecraft/rag/.venv; this permits frozen CLI without modifying either environment.
- Task 1 targeted implementation reports 28 tests passing and scoped ruff passing; complete regression started with frozen/no-sync active environment.
- Task 1 staged package reviewed by /root/pm_multi_project/task1_review (gpt-6-astra/high), independent read-only gate.
Ruling: projects.py reuses artifacts atomic helpers; Task 2 must TYPE_CHECKING-import ProjectContext in storage modules to prevent artifacts→projects→artifacts cycle — reuse standard helpers without moving abstractions — requires explicit type-only import discipline.
- Task 1 fix round 1: reviewer concrete risk legacy staging_dir omitted from protected-root overlap when outside database_dir; implementer self-review found nested database/versions,pipeline,eval junction checks missing. Authorized test-first guards before dependent tasks. Reviewer assesses original diff then scoped fix delta.
- Reviewer accidentally started plain uv run creating ignored worktree rag/.venv scaffold, immediately aborted. No code/git changes; use explicit original interpreter/no-sync only. PM will clean only verified created scaffold if needed; not a dependency install requirement.

Task 1: complete — ProjectContext/Registry, validated atomic locked metadata, whitelisted copied settings, legacy in-place bootstrap, storage ignores. Independent Astra initial P1 legacy staging overlap fixed; scoped re-review PASS, nested junction guards also verified.
Evidence: PM final targeted pytest 33 passed in 6.54s; scoped Ruff passed; implementer complete regression 2123 passed, 10 skipped in 262.34s collected pre-fix 28 registry tests; added 5 fixes checked in final scope. No corpus/collection touched. Reports task-1-report.md, task-1-review.md, task-1-fix-1-review.md.

- Task 1 commit 9e48d987c00b3925be4b6d16869fb4d939786efc. Task 2 dispatched /root/pm_multi_project/task2_indexing, base9e48d98.
- Task 3 integration risk to resolve: Registry.list currently materializes every context; a broken manifest makes list fail. API listing must expose per-project error metadata without blocking another healthy get(), while corrupt registry itself remains a 503. Add narrow metadata iteration only if needed, do not swallow registry corruption.
- Baseline real browser navigation smoke: existing Python uvicorn server:app --lifespan off --host127.0.0.1 --port9876, bundled NODE_PATH Playwright/Edge, node tests/navigation_workspace.cjs passed (console/agent off-page continuation, Intake/history/theme/API key preserved, zero CSP violations). Only API simulations, no models/provider run.
- Task 2 RED reported: 5 expected failing tests for missing project keyword, 3 skip; contexts now propagated in artifacts/writer_lock/qdrant_versions/indexing. ColBERT already accepts explicit database_dir/lease, reused unchanged where appropriate.
Ruling: authorize narrow core/eval_gate.py adapter during Task2 because index promotion gate must never evaluate a new project against legacy golden — project root/eval/golden.yaml, database/eval/history.jsonl and database/alerts.jsonl, project gate settings — Task4 inherits adapter, no parallel file owner.
Ruling: Task2 golden/store isolation is index boundary, but authority/retrieval scoring configuration belongs Task3 — Task3 adds project to hybrid_search/restatement_sections and internal ranking helpers plus evaluate_recall propagation — pending finding cannot be dropped before final criteria.
Ruling: authorize conftest lambda default_lock_path(project=None), preserving legacy temp fallback while honoring explicit project databases — existing autouse sandbox must not rewrite A/B locks — fixture signature adjustment only, assertions retained.
- Task 2 PM concrete risk: scans rglob/is_file in full/docs_hashes/code_hashes can follow descendant file links or Windows junctions into another project even when top-level registry dirs are validated. Requested test-first confinement in shared scans before hash/read/embed; code_index scanner changes permitted if needed. This is a blocking isolation check, not accepted residual.
- Task2 stable implementation preliminary: worker final scoped gate397 passed69.29s, no skip, real Qdrant; PM targeted27 passed20.86s+ruff passed. Review now in fix round1, not yet task-complete.
- Reviewer concrete golden isolation risk: root/eval junction A→B lets gateA read B cases, while registry validates database/eval only. Fix requires guard golden path/parents before fail-open loader and registry evalroot guard as appropriate.
- Reviewer fail-closed risk: CURRENT=legacy on nonlegacy accepts synthetic flat fallback. Ordinary projects must reject token legacy.
Ruling: ordinary nonlegacy projects use existing immutable indexing path so delta creates distinct physical alias__version, held snapshots retain matching vectors, and rollback restores its vectors — explicit coherent snapshot/physical namespace contract wins over inherited legacy mode — collection-copy cost on delta already supported, legacy behavior preserved untouched. Root informed; Task2 implementer instructed RED/GREEN.
- Pending Task3 memo cleanup: code_index._LAST_RAZOR_REPORT and SQL FALLBACK_LOG are global diagnostics, currently no HTTP consumers. Keep explicit per-project accessor/metadata isolation in Task3 audit, no new pipeline exposure.
- Task2 fixround1 worker fresh gate406 passed74.27s zero skip, real Qdrant; ordinary v1 vectors stable afterdelta-v2 and rollbackrestore, B unchanged. Golden parent/file guard and syntheticlegacy failclosed tests green.
- Task2 fixround2 before scoped re-review: PM found artifact FILE symlinks (CURRENT/manifest/graph/chunks/dense/code) followed by read_text/load/hash despite valid version directories. Worker instructed concrete tempfile-link RED then minimal shared pathguard before every relevant access. Not task-complete until verified. Exact tests may skip file-symlink creation only if OS privilege unavailable, with reported limitation; directoryjunction proofs already real onWindows.

- Task2 fixround2 complete worker gate301 passed17 skipped80.18s, Ruff/diffcheckgreen. All17skip FILEsymlink WindowsWinError1314; actual junction equivalents and realQdrant passed. Guard artifacts._project_artifact_path shared covers file+parent access and is required by future direct-sidecar readers.
- Astra /root/pm_multi_project/task2_review scoped fixround1+2 re-review running; package task-2-fixes-review-package.md. PM fresh final newproject test+full Ruff running session1438. Do not mark taskcomplete until this gate.

Task 2: complete (producer/storage scope) — explicit project paths/namespace/locks/leases, strict metadata and pointer handling, GC exact alias, ordinary immutable delta via existing full rebuild, golden/history/alerts isolated, source and artifact confinement. Consumers routes/jobs/CLI remain handoff Tasks3-5, scoring settings handoff3.
Evidence: final PM newproject pytest54 passed17 skipped46.55s (all skip WindowsFILEsymlink privilege), full Ruff passed. Worker broad storage406passed before finalfilefix, final artifact301passed17skip. Astra original3 findings +PM artifact risk fixed, scoped re-review PASS. RealQdrant dedicated49634 vectorquery+rollback/GC/lease/Bisolation exercised. No actual corpus touched. Reports task-2-report.md, task-2-review.md, task-2-fixes-review.md.

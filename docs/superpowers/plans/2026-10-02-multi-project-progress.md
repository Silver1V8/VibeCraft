# SDD ledger — plan: docs/superpowers/plans/2026-10-02-multi-project.md

Baseline: 34b46dfeabcff05820240a1241baae1a215d3e1b; branch codex/multi-project; worktree C:/Users/Silve/.codex/worktrees/multi-project/vibecraft. Original checkout untouched.

| Task | State | Model | Agent | Owned files |
|---|---|---|---|---|
| 1 registry | complete | sol/high | task1_registry | projects.py, config.py, test_projects.py, ignore files |
| 2 indexing | queued | astra/high | — | artifacts, colbert, writer_lock, qdrant_versions, indexing |
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

# Task 8 — Final integration

Status: Task8 implementation and required gates complete; worker released by PM after accepted complete candidate result. Worker-owned source frozen. PM writer-lock fix passed focused Windows/Linux proofs. PM accepted independent whole-branch Astra PASS in task-8-final-review.md and marked supported AC1–10 complete; this worker changed no acceptance checkboxes.

Base: `06c7626d8183834b30476d3fe92a4fe3945c2f03`, branch `codex/multi-project`; whole-branch baseline `34b46dfeabcff05820240a1241baae1a215d3e1b`.
All commands use only `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft` or its `rag/` as cwd. Original checkout is not edited; only its existing interpreter/venv is reused. Worker stages/commits nothing. PM owns plan and progress ledger.

## Owned changes

- `rag/tests/test_project_integration.py`: actual HTTP FastAPI server on a bound ephemeral loopback socket, actual temporary registry and UUID projects, actual Qdrant client and dedicated service, actual artifact snapshots/cache, plan import/validation/gate, local tool writes, actual reindex manager/journal/callback, rollback and project-scoped GC.
- `rag/tests/project_integration_browser.cjs`: real browser and the same HTTP fixture; no route interception. The UI asks the same query in A then B, selects A again, and preserves the distinct answers and input.
- `.github/workflows/ci.yml`: PM-authorized single invocation of the combined integration/browser test after the existing temporary Playwright/Chromium setup. Its existing environment supplies NODE_PATH and the isolated CI Qdrant service. No new product dependency or weight download.
- Four historical test modules: `rag/tests/test_reload_concurrency.py`, `test_security_headers.py`, `test_security_fixes.py`, `test_health.py`. Narrow PM-authorized admission/signature/spec adapters and logging-test isolation, preserving behavior/security assertions.
- `rag/SECURITY_SURFACE.md`: registration row65 now documents the already implemented local arbitrary-root/remote strict managed-root policy accurately. No product policy changed.
- This report. Raw gate logs and task8-env.ps1 remain in the ignored task directory.

## Real boundaries and acceptance evidence

The fixture creates two managed projects using POST /api/projects and verifies all four directories. Both use `docs/same.md`, `code/backend/same.py`, `same-feature`, the same query and deliberately colliding version `v1`. Source bytes contain ALPHA_SENTINEL or BETA_SENTINEL. Actual build, Qdrant sparse/dense queries and actual stored chunks determine the generated answer; the provider rejects a prompt containing both sentinels. The repeat A ask is cached, while the initial B ask receives B context. Real validator source records contain only their project's sentinel and the actual captured index version.

Actual HTTP plan creation/application copies a temporary external Python file into A, writes the import journal, acquires the writer lock, publishes ordinary delta v2 and reloads A. The same plan ID under B returns404; B receives no imported file. The same feature is saved and validated independently in A/B through the actual structural/semantic pipeline. A's persisted passing validation cannot admit a B agent run. A's admitted local runner executes the real guarded write_file tool and callback/event machinery; only its chat provider is simulated. A/code/runner.txt exists and B/code/runner.txt does not.

A full HTTP reindex captures A, then is held inside the embedding provider only when its source contains HELD_ALPHA_REBUILD. While the actual manager retains its global indexing slot and project writer lock, B metadata, actual Qdrant retrieval and ask respond; B cannot query A's job ID. Releasing the provider publishes A v3, reloads A's snapshot, and appends A's job journal. B remains v1 with no reindex journal. This verifies concurrent queries during a serialized writer, not simultaneous physical index builds.

Actual HTTP rollback restores A v1 and its alias. Actual project-scoped GC removes a known A orphan. B's CURRENT bytes, artifact hashes, alias, complete stored vectors and index integrity remain unchanged. Cleanup enumerates only exact physical names v1/v2/v3/unused in the UUID namespaces created by this test; it does not call generic-prefix deletion or touch production Qdrant. The fixture joins its manager threads, stops its owned uvicorn thread and closes sockets/client/leases before cleanup.

The new browser requires `VIBECRAFT_INTEGRATION_BROWSER=1`; the Python integration still runs its actual HTTP/Qdrant behavior without that flag. After asserting A→B→A state, actual UI clicks create a third project and register a fourth pre-existing temporary manifest/root. The real registry is checked for four distinct roots and complete layouts; the newly created/opened empty projects remain unindexed. A's state is checked before these additional projects, respecting the intentional two-project residency cap. CI installs browser tooling after the normal Python gate and then explicitly enables the flag. The local final gate enables it too. Existing projects_workspace checks cover per-tab history, origin-safe fetch, fixed retry identity and late stream/job behavior. Existing navigation checks use a separate actual uvicorn9876 server and intercept provider APIs, preserving streaming/UI/CSP assertions.

## Environment and commands

Every Python process uses PYTHONUTF8=1, PYTHONPATH=worktree/rag, both QDRANT_URL and VIBECRAFT_TEST_QDRANT_URL=http://127.0.0.1:58123, VIBECRAFT_REQUIRE_QDRANT=1, VIBECRAFT_REQUIRE_DOCLING=1, VIBECRAFT_REQUIRE_LIBREOFFICE=1, HF_HUB_OFFLINE=1, HF_HOME=worktree/rag/database/models/hf. VIRTUAL_ENV points to original/rag/.venv. Node26 and bundled Playwright1.62.1 are available via NODE_PATH=C:/Users/Silve/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules. No sync/install/lock changes occur.

PM verified 163 reused installed package base versions against uv.lock; wheel/source artifact identities and a fresh clean install are not established. PM copied 37 existing Docling asset files into ignored worktree storage and verified five pinned hashes; no original model-directory writes or downloads. Actual LibreOffice conversion belongs to the mandatory full suite, not executable presence alone.

Commands from worktree rag after sourcing `../docs/superpowers/plans/multi-project-tasks/task8-env.ps1`:

```powershell
uv run --frozen --no-sync --active ruff check .
uv run --frozen --no-sync --active pytest -rs
uv run --frozen --no-sync --active pytest tests/test_project_integration.py -q -o addopts= --tb=short
node tests/intake_excel_preview.cjs
node tests/pipeline_dryrun_escape.cjs
node tests/dashboard_graph_escape.cjs
node tests/workflow_errors.cjs
node tests/pipeline_runner_capability.cjs
node tests/pipeline_agent.cjs
node tests/projects_workspace.cjs
```

Provider/native boundary audit inspected the actual bound local chat injection, SDK query fakes, fake LLM registered providers/HTTP transports, native CLI failclosed tests with explicitly bound Popen injection, CLI constructors/dispatch, benchmark bootstrap fake and loopback test services. The historical SDK settings-isolation tests intentionally initialize the installed SDK with credentials removed and API base loopback1, send no query, and exercise temporary hooks. They are not described as mocked SDK initialization. The new fixture invokes no SDK/MCP/native provider process.

## Observed gates so far

- Initial fixture probes failed on two harness assumptions: project import deliberately includes source directory name; a single BDD scenario deliberately fails the existing structural gate. The fixture was corrected to the actual nested path and two explicit positive/negative scenarios. These are not product RED evidence or repaired product regressions.
- Initial combined fixture: 1 passed in17.71s. Strengthened actual full job/source-record/cleanup fixture: **1 passed in17.90s**, with browser flag1 and exact dedicated Qdrant URLs. Logs: task8-integration-third.log and task8-integration-final.log.
- Full frozen Ruff: **all checks passed** after replacing one test-only assigned lambda flagged E731 with a named helper. No product edits.
- All seven Node checks listed above: **exit0 PASS**; per-check task8-node-*.log retained.
- Separate actual uvicorn `server:app --lifespan off --host127.0.0.1 --port9876`, original interpreter with mandatory worktree environment: readiness200; `node tests/navigation_workspace.cjs` **PASS**, including preserved stream/agent/intake/CSP. Owned PID8888 stopped by CtrlC, terminal session closed; no process left at that PID. Log task8-navigation.log.
- `git diff --check`: exit0 (Git line-ending notices only).
- First complete frozen pytest -rs: **5 failed,2339 passed,19 skipped,15 Docling deprecation warnings in362.28s; exit1**. Raw task8-full-pytest-first.log. Actual Docling and LibreOffice required tests ran; none skipped for weights/executable. Five historical adapter/spec failures were:
  - `tests/test_reload_concurrency.py::test_reload_lento_non_blocca_l_event_loop`: missing explicit legacy admission and disk-version fake accepting the captured context; real reload never began. The adapter keeps actual require_snapshot/project runtime/thread offload and existing responsiveness/one-load assertions.
  - `tests/test_security_headers.py::test_streaming_response_on_real_app_has_security_headers`: fake_check_drift lacked project keyword. It now asserts the admitted temporary legacy ID/root and keeps original headers/NDJSON assertions.
  - `tests/test_security_fixes.py::test_local_only_route_declares_local_bind_dependency[router0-POST-/api/projects/register]`.
  - `tests/test_security_fixes.py::test_no_other_route_is_disabled_by_bind`.
  - `tests/test_security_fixes.py::test_http_local_only_route_returns_403_when_bind_is_open[router0-POST-/api/projects/register]`.
  The last three expected blanket local-only registration and a different payload shape, contradicting the Task7 managed-root policy. Only registration was removed from the two-route local-only list; explicit registration auth/cross-site classification and existing actual managed-root/auth/traversal/link/reader tests remain.
- Adapter gate across reload/security headers/security fixes/project API: **256 passed,1 Windows file-link skip in53.81s; exit0** (task8-adapters.log).
- A later ordered six-module probe: **1 failed,271 passed,1 skipped in86.13s** (task8-final-scoped.log). Its new security-headers fixture initially used legacy_workflow_project before the first server import; the historical include_router adapter installed a persistent legacy dependency override on that first shared app. The actual integration detected B's plan apply incorrectly reaching the old fixture context (200 vs404). This was a harness leak, not a production routing change. Headers now build a specific temporary legacy context and override only its exact dependency with monkeypatch; they never activate the include_router adapter. Integration asserts app.dependency_overrides is empty before using real header admission; it does not clear or hide leaked overrides. An intermediate headers/integration probe passed16 in19.77s, followed by the final complete scoped rerun below.
- Two logging-level tests isolate root.handlers before the actual setup_logging(force=True) calls and restore their original level/handlers with monkeypatch. The previous tests retained handlers targeting a disposed pytest capture stream and emitted closed-file logging diagnostics later. Existing DEBUG/WARNING/default INFO/invalid fallback assertions remain; product logging is unchanged.
- A full rerun launched prematurely while that ordered probe was finishing was stopped after verifying its exact owned uv→pytest→Python launcher chain and absence of live worker children. It reached57% plus partial next row; **no completion count or passing gate is claimed**. Session72726 closed with exit-1. The raw task8-full-pytest-final.log remains diagnostic; the actual final candidate gate uses a new log.
- Final complete ordered scoped gate: **272 passed,1 skipped in61.85s; exit0**, with Ruff all checks passed (task8-final-scoped-clean.log). Order: health, reload concurrency, security headers, security fixes, project API, actual HTTP/Qdrant/browser integration. Empty dependency override assertion passed; actual A/B distinct contexts, held A job with responsive B, UI A→B→A state, UI create C and open D passed. The sole skip was project API manifest-sidecar file symlink WinError1314. Worker-owned source is frozen for independent review. The complete frozen candidate gate after the PM-owned writer-lock confinement fix passed, as recorded below.

The first complete suite had19 Windows file-symlink skips; the final candidate has20, including the new writer-lock file-link regression. All share unavailable CreateSymbolicLink privilege (WinError1314), with actual junction alternatives running:

- `tests/test_project_api.py::test_manifest_sidecar_link_never_reads_other_project`.
- `tests/test_project_tools.py::test_file_symlink_is_never_read_listed_or_grepped`.
- Final-candidate additional case: `tests/test_project_lock_confinement.py::test_writer_file_link_before_admission_preserves_foreign_document`. Its actual Windows error was1314; the narrowed guard accepts only that Windows error (PM-authored after the reviewer finding), and actual Linux regression passed without a skip.
- `tests/test_project_indexing.py::test_project_artifact_file_link_is_rejected` for these17 exact parameter IDs: `CURRENT-token-symlink`, `CURRENT-promote-symlink`, `CURRENT-rollback-symlink`, `index_manifest.json-manifest-symlink`, `chunks.json-integrity-symlink`, `graph.json-load-symlink`, `graph.json-hash-symlink`, `chunks.json-load-symlink`, `chunks.json-hash-symlink`, `dense.npz-load-symlink`, `dense.npz-hash-symlink`, `code.json-load-symlink`, `code.json-hash-symlink`, `code.npz-load-symlink`, `code.npz-hash-symlink`, `colbert.npz-load-symlink`, `colbert.npz-hash-symlink`.

## Limits carried forward

Native integrated Codex/Cursor launch remains unavailable before Popen until cross-project read enforcement is verified. Prompt export and external MCP fixed explicit ID remain supported. SDK/local guard proofs are separate Task5 coverage; conservative SDK root-wide unsafe-subtree scans are intentionally denied while safe Read/scoped scans/local pruning work.

Task5's earlier test-boundary incidents are preserved: an ineffective import-bound Popen patch allowed native startup/network prewarm400/Cursor authentication rejection; model execution/billing was not observed, and zero host effects are not asserted. An earlier rollback probe omitted the effective QDRANT_URL override and could attempt default6333 compatibility access before being stopped; the earlier interrupted suite had no completion result. All current Python commands supply both dedicated58123 URLs. No outside-worktree cleanup of unproven state is attempted.

Windows file-symlink privilege remains unavailable. PM's separate Linux CPU-runtime source-overlay proof covers35 artifact/file/directory cases plus20 SDK/local cases with zero skips; that is complementary platform evidence, not a fresh frozen image build. Task7 proved actual Docker UID10001, zero-project authenticated liveness, A/B restart persistence and reader health using a cached CPU-image overlay. GitHub Actions and a full fresh frozen Dockerfile build are not claimed here.

No real corpus reindex/deletion, push, merge, publication, dependency install, security-host change or original checkout edit. Full branch final independent Astra review remains PM-owned.


## Final review finding and candidate gate

The independent whole-branch review reproduced a P1 lock-confinement gap: after capturing a project context, a linked `.writer.lock` or replaced database/project ancestor could open/lock a foreign file and then truncate diagnostic bytes before project artifact guards. The PM exclusively changed `rag/core/writer_lock.py` and added `rag/tests/test_project_lock_confinement.py`. The fix validates the file and every ancestor before filesystem I/O, rechecks after writer-parent mkdir, adds O_NOFOLLOW where available, and applies the same confinement to reader lease paths and holder diagnostics. Tests assert foreign sentinel bytes and directory contents remain unchanged, while ordinary and explicit locks remain usable. Worker-owned integration files were untouched by this fix.

PM-reported focused proof: Windows **13 passed,1 file-link privilege skip in7.17s**, Linux **14 passed,0 skipped in11.24s**, plus full Ruff PASS. These counts are separate from this worker's gate. The reviewer flagged an overly broad OSError skip, and the PM narrowed the test-only file-symlink skip to Windows WinError1314. The reviewer authored no test or product changes. Independent reviewer reruns then passed the actual integrated HTTP/Qdrant/browser fixture (1 passed in19.02s) and focused Windows lock suite (13 passed,1 Windows1314 skip in7.44s); PM Linux proof remains14 passed,0 skipped in11.24s. That final skip-guard edit landed just after this worker started the complete candidate gate; Windows1314 behavior and product source are unchanged. A second complete suite solely for this skip guard is not claimed or required by the PM.

Final candidate command started after source freeze and the clean ordered scoped gate: `uv run --frozen --no-sync --active ruff check .` (PASS), then `uv run --frozen --no-sync --active pytest -rs`, session53857, raw task8-full-pytest-candidate.log. Mandatory dedicated URLs58123, offline pinned Docling, required LibreOffice and integrated browser flag1 are enabled. **Complete result: session53857 closed exit0; 2348 passed,20 skipped,15 Docling deprecation warnings in359.39s (05:59).** The required actual Docling/LibreOffice tests and actual integrated browser ran; none skipped for service, weight, executable or browser availability. Raw skip groups are1 API manifest file link,17 indexing file links,1 writer-lock file link and1 guarded-tools file link. The warnings concern existing deprecated Docling OCR/table-image fields. No product or worker test edits occurred during this gate; only the PM test-only Windows1314 skip tightening during its initial collection and report edits described above. Ruff passed immediately before pytest. Seven Node checks and separate navigation remain the already recorded final candidate proofs, with no subsequent UI product changes. Formal independent whole-branch review report and final acceptance ledger remain PM-owned; the worker was released after the accepted gate.

## Acceptance evidence map

| Criterion | Evidence |
| --- | --- |
| AC1 | Actual API creates A/B; actual console creates C and opens D; all four registered roots/layouts are distinct. |
| AC2 | Real same-query A/B/A HTTP retrieval/provider prompts/cache contain only the selected sentinel; colliding v1 tokens and reload remain isolated. |
| AC3 | Actual A delta/full/rollback/GC; B CURRENT/artifact hashes/alias/all vectors stay identical. Existing indexing suite covers retention edge cases. |
| AC4 | Same feature A/B real validation stores and local gate, actual import journal, held A job/writer lock and B job404; historical workflow/intake tests supplement. |
| AC5 | Actual browser A→B→A retains inputs/answers; projects_workspace covers tabs, fixed retry ID, origin-safe transport and late stream/job targeting. |
| AC6 | Actual admitted local runner uses guarded write_file into A only; Task5 SDK/MCP/CLI fixed-ID and confinement gates supply other runner coverage and explicit native-launch limit. |
| AC7 | Created/opened C/D stay unindexed without automatic indexing; earlier API/UI runtime tests cover declared empty/broken states and failclosed admission. |
| AC8 | Existing registry/legacy migration tests from Tasks1/2/3 supply in-place registration/unchanged collection evidence; this fixture deliberately uses temporary managed roots. |
| AC9 | Task7 actual cached-runtime Docker restart/persistence/reader/liveness proof plus current auth/CSP/Host/local-bind tests; full fresh image/Actions remain unrun. |
| AC10 | Actual Qdrant and browser fixture, seven Node checks and separate navigation PASS; scoped272 PASS; complete frozen candidate2348 PASS/20 Windows file-link skips; formal independent review report/final acceptance ledger remain PM-owned. |

Owned-run cleanup: the completed pytest session53857 exited0, so its fixture server thread and Qdrant clients no longer exist. Fixture teardown explicitly stops and joins uvicorn/managers, closes HTTP/Qdrant clients and snapshot leases, and removes only exact UUID physical collection names. The separate navigation server session was previously stopped/closed. No worker-owned test server or client is active; the dedicated Qdrant service container remains alive under PM ownership and is not stopped by this worker.

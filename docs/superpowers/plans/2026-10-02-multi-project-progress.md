# SDD ledger — plan: docs/superpowers/plans/2026-10-02-multi-project.md

Baseline: 34b46dfeabcff05820240a1241baae1a215d3e1b; branch codex/multi-project; worktree C:/Users/Silve/.codex/worktrees/multi-project/vibecraft. Original checkout untouched.

| Task | State | Model | Agent | Owned files |
|---|---|---|---|---|
| 1 registry | complete | sol/high | task1_registry | projects.py, config.py, test_projects.py, ignore files |
| 2 indexing | complete | astra/high | task2_indexing | artifacts, colbert, writer_lock, qdrant_versions, indexing |
| 3 runtime | complete | astra/high | task3_runtime | deps/server/projects/retrieval/graph/health/cache |
| 4 workflows | queued | sol/high | — | pipeline/intake/reindex/eval core/routes |
| 5 tools | queued | sol/high | — | agent_bridge/runners/MCP/CLI |
| 6 UI | complete | sol/high | task6_ui | static/templates/routes_pages/Node tests |
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

- Task2 commit436b90872500244a9279ff278badcc1b139fbfc2. Task3 /root/pm_multi_project/task3_runtime dispatched, base436b908.
Ruling: frozen Task3 metadata payload `{projects:[{id,name,legacy,index_status,stale,index_version,error?,root?}],read_only}`; singular endpoints return metadata; status enum spec, safe HTTP detail code/message; liveness `/api/health/live` independent — stable Task6 contract — additive fields, no cost if caller follows it.

Ruling: anticipate only Task6 client implementation after Task3 frozen API contract, per root explicit authorization UI after stable contract — exclusive static/templates/routes_pages/Node ownership +API simulated tests, integrated UI gate waits reviewedTask3 — replaces conservative initial wait-for-Task3-complete ruling, cost if wrong limited UI rework on API contract.
- Task6 /root/pm_multi_project/task6_ui active gpt6.1-sol/high alongsideTask3; max two operational slots observed. No other active worker/reviewer until a slot frees.
- Task4 must keep POST /api/intake/project/browse-path global auth/localbind without get_project: console opener needs browse at zero projects. Register route already global; all actual project intake/import writes must still capture context.
- Task3 first new API/runtime RED→GREEN:9tests passed covering zeroresource bootstrap/missing/unknown/legacy selection, corruptmanifest isolated vsregistry503, auth/localbind/cross-site, projectcache keys, real disk snapshotsA/B, eviction/capture concurrency, sharedresourcesonce. Broader retrieval/stream/ranking/health regressions in progress.
- Frozen backend seam forTask4: project_runtime(project) per-ID dict reindex_manager metadata; require_snapshot raises409/503 vscurrent_snapshot peek; reload explicit; resourceslazyshared. Per-runtime lock requested for first manager/store creation; LRU2 may not evict active manager metadata.
Ruling: Task3 startup is lazy and performs no implicit boot alias repair/GC — zero-project/resource-down console plus read-only GET requirements prohibit maintenance side effects — writer indexing/CLI retain explicit repair/GC, legacy startup automaticrepair behavior changes and must be documented.
- Task3 runtime metadata exposes lock:RLock per ID, persistent across snapshoteviction. Task4 use it for single manager/store construction.
- Task6 first new Node+Edge fixture GREEN: A/B tabs/query/history/refresh, late stream/job, busy retention limit2, create/open/errors/reader/zero/XSS/CSP. Three existing NodeXSS extraction gates nowgreen preservingassertions; nav regression inprogress. Backend unchanged except routes_pages querymetaescaped/localbind info.
- Task3 broad regression identified security inventory changes for 4 project routes plus liveness; narrow SECURITY_SURFACE.md/test_security_fixes.py updates approved, preserve auth/reader assertions.
- Task6 baseline pipeline_agent.cjs additionally failed on HEAD: exact expected request lacked existing max_attempts:1. Approved schema fixture adapter retains all assertions; confirmed AgentRunRequest supports it.
- Task6 strengthened real HTTP fixture sends headers + first NDJSON chunk before holding stream; verifies busy protection after streaming begins and polling gaps/errors retain active reindex frames.
- PM fresh node tests/projects_workspace.cjs failed remote-local-bind browser assertion line226 (browse visible true); sent concrete failure to implementer, review pending fix. Fetch and reindex-unit portions passed.
- Task6 PM fresh Node projects_workspace --navigation exit0 after concrete CSS fix [hidden] overridden by .btn display:inline-flex; five baseline Node exit0 and full Ruff green. Review dispatch technically blocked: spawn_agent and followup_task both agent thread limit reached despite Task6 completed status; root notified, reconciliation pending.
Ruling: reuse two existing operational agent identities for later scopes when harness rejects fresh spawn with agent thread limit reached — existing live followup works, new/revived retired thread does not; preserve independent reviewer per changed files and exclusive ownership — costs fresh-context isolation; final whole-branch independent Astra remains required and capacity will be reassessed.
- Task6 Sol worker reactivated readonly Task3 smoke planning; Task3 Astra worker remains final targeted gate, will independently review UI after own report. Cross-review only excludes own implementation. No new agent/extra coordinator spawned.
- Task3 implementation final broad targeted gate:558 passed1skipped88.20s realQdrant49634; PM fresh test_project_api/runtime exit0 (20passed1skip, same Windowsfile-symlinkprivilege). Reviewpending. No fullsuite rerun until Task8.
- Task6 independent Astra cross-review FAIL2 blockingfindings: P1 mutable URL input retained for authenticated401retry can switch externalorigin and leak key/project; P2 dashboard/graph data consumer Error(detailobject) renders [object Object] on new409/503. ConcreteVMrepros in task-6-review.md. Fixround1 assignedoriginalSol afterTask3readonlyreview, noUIcommit untilscopedre-review.
- PM realFastAPI+Edge smoke (uvicornlifespanon127.0.0.1:9876, tempseededemptyregistry in rag/.pytest_cache/pm-api-smoke-20261002, QDRANT_URL invalid127.0.0.1:1) proved shell/live/registryzero200, createA/B201, tab/query/refresh/fixedsrcdocidentity, escapedHTMLname, nonindexed409/project_requirednofallback, nofrontenderror. Initial smoke's assertion wrongly expected iframe.src; actual appuses srcdoc+dataset.projectId. Corrected harness assert provedfixedidentity; noUIcodechange from this smoke. Models/realcorpus neverloaded. Server cleanup pending.
- Task3 independent Sol cross-review FAIL2P2: metadata stale compares manifesttimestamp vsCURRENTdirectorytoken (normal producerrealwrite_index_manifest proof), and runtime cachedrestatementclassification drops setwhenweight1 then changesranking afterprojectsettings edit withoutindexchange. task-3-review.md realrepro andpersonal24pass1skip19.84s. Fixround1 originalAstraassigned, SolnowfixUI6.
- PM Task3 samewave isolationrisk: load_rule_descriptions docsroot resolve/rglob could legitimize root/ancestorjunction swapped aftercontextcapture; require actualjunctionRED and sharedsafescan/ancestor guard. Narrow code_index scanner scope permitted ifneeded.
- PM Task3 samewave coherencerisk: askcache ignores effectiveprojectsettings while registryrereadsYAML; require meaningful REDsamequery/version settingsedit; fingerprintkey onlyifproofconfirms. Bothriskchecks recordedbeforecode, not assumedfixes.
- PM realFastAPI smoke server session11536/pid9528 stoppedCtrlC exit1 intentionally; no testHTTPserver remains. DedicatedQdrant49634 stillrunning forfuturegates.
- Task3 fixround1 sixRED→GREEN reported: stale false/true + concurrentpromotion, restatement weight1→0.5 stablebefore/aftereviction, askcache samequery/version authority/retrievalsettingschange, capturedcontext docs/root/nestedjunctionsafe. Addedminimal core/indexing.py index_status(version=...) preservingmanifesttimestamp and code_index source_files ancestorlinks guard. Same weakguard foundlegacy/ask live-doc fallback; seventhRED/fix inprogress. NoTask3complete yet.
- Task6 fixround1 reported stable twoRED→GREEN; new shared error-message helper adapts dashboard stream +graph_analysis query/impact, URL hrefcaptured for401retry. PM fresh projects_workspace --navigation exit0 allVMerrors/fetch/reindex/browser/nav; scopedAstra re-reviewqueuedafterbackendfixgate. Added graph_analysis.js exactownership authorized, no other scope.
- Task6 fixround1 Astra scopedre-review PASS2ADDR/no newfinding; reporttask-6-fix-1-review.md. Reviewer actual projects_workspace --navigation+4JSsyntaxgreen. PM independentfreshUIgategreen; clientscope gated, formalcompletion/commit alongsideTask3 afterruntimefinalgate.
- Task3 fixround1 PM fresh27passed1skip21.22s realQdrant+fullRuffgreen; Solscopedreview original2P2+PM7regressionsADDR (7newpass13.24s,39compatpass11.63s) but newdeltaP2Windowslegacy spec.MD ignored vs previouscaseinsensitiveglob. Round2minimal lowercasedsuffix+testassignedoriginalAstra, nofullbroadrepeat. Fixround1restagedbase for minimalround2delta.

Task 3: complete — explicit captured HTTP context/snapshot, lazy sharedresources, LRU2 retainleases, project-ID+effective-settings askcache, realstale metadata, projectranking, reader/security/liveness, confined sources/artifactreads. Independent Sol cross-review2P2 +PMcache/junctionrisks fixedround1; newWindows.MD regression fixedround2; both scopedreviews PASS, no openfinding.
Evidence: originalworker558pass1skip88.20s; fixgate220pass18WindowsFILEsymlinkskip68.88s actualQdrant49634; reviewer46fixpass0skip then6micro0skip; PMfinal27pass1FILEskip21.22s plus6micro0skip10.71s andfullRuffgreen. Nofullsuite repeats; Tasks4/5 still owndatawriter/job/tool surfaces. Reports task-3-report.md/task-3-review.md/task-3-fix-1-review.md/task-3-fix-2-review.md.

- Task3 commit edfbbe4 (runtime/storage read consumer scope reviewed). Task4 datawriter/jobs andTask5CLI/MCP/runner stillqueued.
Task 6: complete (client scope) — tab/query projectselector/create/open/indexstatus, fixed frame and fetch identity, retry-target+headercapture, LRU2 busyrefusal, accessiblecontrols/escapednames, structuredqueryerrors, preservedlegacy/CSP. Independent Astra initialP1URLmutable+P2objecterrors fixedround1 and scopedPASS. Baseline3extractor +pipeline_agent fixtureadapter retainassertions.
Evidence: PM+worker+reviewer freshprojects_workspace --navigation exit0 with realHTTPchunk fixture afterfirstchunk, A/Btabs/history/latejobs/streams andqueryerrors; fiveexistingNodeexit0, JSsyntaxgreen, fullRuffgreen; PMrealFastAPI/Edge actualzeroproject/createA/B/tabrefresh/fixedsrcdoc/noindex409 passed. Full indexedworkflow/browser/APIintegration stillTask8. Reports task-6-report.md/task-6-review.md/task-6-fix-1-review.md.

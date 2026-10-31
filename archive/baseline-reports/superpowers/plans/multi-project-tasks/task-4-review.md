# Task 4 — independent review

Date: 2026-10-05. Reviewer: resume_independent_review, no product authorship. Base HEAD: `4223b84d066af61aa4dd9c11150f2b7c0a0b5cca`; reviewed staged Task 4 package and its 42 owned product/test files plus report. Worktree product files matched the staged candidate during review. Plan and progress ledger remain PM-owned.

**Verdict: changes required.** Five concrete findings: one P1 and four P2. No product edits, staging, commits, provider calls or production data operations were performed.

## Spec and correctness

### P1 — Empty project code activates a foreign Git/tasks fallback

`rag/core/canvas_review.py:364`, reached from `rag/core/feature_archive.py:114`.

Archive supplies the captured project's `_review_code(...)`, but `code or collect_change_diff(...)` treats an explicit empty result as permission to run Git/tasks fallback. With ordinary project A inside an installation Git checkout, Git invoked from A discovers the parent repository. A matching feature subject then returns an unrestricted repository diff, including B's code. Legacy root is itself the installation repository, so checking only that Git's top-level equals the supplied root does not exclude a registered foreign project nested elsewhere under that root. The tasks fallback also accepts files throughout the root rather than the captured code scope. This violates the plan's project-local archive/drift context and isolation requirement.

Independent reproduction: created a temporary parent Git repository, nested A/B roots, a baseline commit, and a second commit named `same-feature implementation B` adding B/private.py with `OTHER_PROJECT_SENTINEL`. Calling actual `collect_change_diff('same-feature', A/changes/same-feature, repo_root=A)` returned that sentinel. No model call was made. Code inspection traces this output directly into the review prompt when `_review_code` is empty.

Minimal accepted correction criterion: distinguish omitted `code=None` from explicitly supplied `code=''`; the archive path already always supplies captured code, and an empty project result must remain empty. `rg` confirms the only production call chain is archive -> generate_canvas_review -> collect_change_diff; remaining callers are tests. Prove actual archive ordinary/legacy paths cannot reach Git/tasks fallback on empty captured code, including a B task-file reference, and preserve the nonempty captured-code case. Any retained standalone Git fallback should avoid accidental parent-repository discovery. No new general policy framework is required.

### P2 — External prompt instructions omit project selection

`rag/core/pipeline.py:242` and `:283`.

`build_final_prompt(..., project=A)` adds an ID/root preamble, but its actionable HTTP examples specify only X-API-Key and the MCP examples never instruct starting the bridge with VIBECRAFT_PROJECT_ID=A. Following those instructions consults registered legacy, because an absent project header/MCP environment explicitly means legacy; if legacy is absent, it fails instead of querying A. This violates the requirement that exported prompts and agents use the originating project. Mentioning an ID in prose does not set a transport header.

Independent check on actual generated prompt: neither `X-VibeCraft-Project` nor `VIBECRAFT_PROJECT_ID` appeared. Remedy: include the captured header in every HTTP fallback instruction and the fixed session environment requirement for external MCP; preserve legacy/no-context behavior and external prompt/export availability independently of integrated native runner admission.

### P2 — Snapshot eviction makes a valid persisted gate unavailable

`rag/api/routes_pipeline.py:776-778`.

`_validation_source_state` uses `current_snapshot(project)`, which only peeks. After the two-snapshot LRU evicts A, gate status/admission never reloads A and reports unavailable sources despite healthy persisted artifacts and an unchanged valid validation. The same issue occurs after process restart before any unrelated retrieval happens to load A. This violates the lazy runtime contract and prevents normal resume of a validated workflow.

Independent reproduction used real temporary immutable artifacts A/B/C at v1 and a persisted passing A validation. Actual `pipeline_gate_status` returned allowed=True after loading A. Loading B and C evicted A; the same handler then returned allowed=False with `sources_unavailable`, http_status=503, without any data change. Use snapshot acquisition at this shared boundary, already called from worker/threadpool paths, and translate genuine absence/storage failures into the existing safe gate availability response. Check both eviction and unavailable-storage behavior.

### P2 — Explore copies provider diagnostics into response and history

`rag/api/routes_pipeline.py:472`, through `rag/core/pipeline.py:79-86`.

Explore still uses the tolerant helper that returns raw `str(LLMError)`. The result goes into both ai_response and history, and the latter can be saved as interview content. Real provider wrappers include generic exception/API response diagnostics, so this bypasses the safe public workflow error rule already applied to canvas/propose. This is a remaining boundary in the touched workflow, not a request to redesign provider error handling.

Independent actual-handler reproduction replaced only `llm.agenerate` with an LLMError containing a synthetic private-provider-key and private path: both ai_response and history retained the diagnostic. Preserve the intended tolerant interaction if desired, but return the existing safe public message while keeping diagnostics server-side; test that history is safe too.

### P2 — Missing staged Markdown exposes the host path in preview errors

`rag/api/routes_intake.py:86`, originating in `rag/core/intake.py:343-346`.

A staged record whose Markdown file has become absent/unreadable raises StagedDocumentNotFoundError containing the raw OSError. `_raise_http` sanitizes several domain classes but falls through to `str(exc)` for this one, returning an absolute project root to the HTTP caller. The new public error boundary therefore misses a normal storage failure case.

Independent reproduction staged a Markdown fixture in temporary A, deleted only its test-created Markdown file, and called the real preview handler. It returned HTTP 404 with the absolute temporary project root in detail. Preserve 404 and a useful missing/unreadable staged-document explanation while excluding the nested OS diagnostic. The initial probe compared Windows escaped-path text literally and its assertion failed; normalizing doubled backslashes confirmed the leak, and the corrected probe exited 0.

## Standards and quality

No separate blocking style or speculative abstraction finding. The implementation generally reuses ProjectContext, runtime locks, existing storage guards, the threadpool, and the UI error helper. Historical test adapters retain relevant status/auth/content assertions and are explicitly opt-in; real A/B tests use independent contexts. The findings above concern behavior and privacy, not formatting.

## Fresh independent verification

- Nine focused tests passed, zero skips, 22.53s: fresh writer-process import; health legacy/A/B history without writes; readonly journal recovery/compaction prevention; held-loader B responsiveness; cross-project reindex serialization/error release; delayed generation captured snapshot/project; A validation cannot authorize B; delayed reindex/reload and safe public job error; cross-project import-plan rejection.
- `node rag/tests/workflow_errors.cjs`: exit 0, actual generation/final-prompt/upload/polling error checks for 409/503/404 and XSS rendering.
- Fresh child process imported actual server, entered its FastAPI lifespan, and requested authenticated `/api/health/live`: HTTP 200/status ok, exit 0. Temporary projects/database paths; writer+immutable configuration. First probe omitted the required immutable mode and was correctly rejected by existing config validation, then corrected without product changes.
- Four independent synthetic scripts reproduced the five findings above using temporary files/artifacts/Git repositories or provider-boundary fakes only. Existing interpreter used with explicit worktree cwd/PYTHONPATH and PYTHONUTF8=1. No heavyweight resource initialization, Qdrant connection or provider execution was required by these probes.
- Earlier preflight UI `[object Object]` and event-loop loader findings are addressed by this candidate: the fresh Node check and held-loader test pass. Fresh server import and read-only health history checks also pass.

The implementer's 814-test gate and PM's Linux symlink evidence are separately reported evidence, not reruns claimed by this reviewer. Full branch acceptance remains pending Tasks 5/7/8 and the final baseline review. Scope fixes to these findings and re-review the correction delta before committing Task 4.

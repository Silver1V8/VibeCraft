# Task 5 — CLI, agent tools and native export

Implementation package based on `dde1ef92be99c5c5d15926634bfed9c1288b91fe`. No staging or commit by implementer. The previously committed runner/MCP adapter remains in place. PM owns the progress ledger; it is not part of this author's changes.

## Scope and resulting behavior

- `rag/index.py` captures `--project` once before dispatch and carries it through full/delta/status/integrity/graph/drift/archive/ColBERT maintenance and every rollback stage. Absent flag retains historical legacy behavior and ignores the external MCP environment. Mixed rollback/read flags still take the writer lock. Empty rollback/archive/drift values are rejected before they can fall into a full rebuild.
- `rag/agent_bridge.py` and `rag/agent_runners.py` reuse the same path guard for SDK/local reads and writes. It checks all ancestors/file links and Windows junctions before resolve, containment, traversal, secret paths, `.git`, and registered nested foreign roots. Registry metadata refreshes for each operation; a missing/corrupt foreign manifest cannot grant access. A registered legacy ancestor does not deny an ordinary project's own tools. Reserved names in harmless trusted root ancestors do not deny absolute own-code writes.
- SDK Read/Grep/Glob and write hooks capture the project context. Local threads capture their root/code directory and readonly registry view before dispatch. Shared AGENT_MODES/config/environment/cwd are not mutated.
- `rag/core/projects.py` adds default-compatible `readonly=False`; readonly views neither bootstrap nor lock/write, and reject create/register before filesystem effects. Successful metadata reads remember registry presence, so subsequent deletion fails closed. This is the narrow accessor authorized by PM.
- Native integrated Codex/Cursor execution rejects before Popen for ordinary A/B, legacy and raw None, using machine code `native_read_isolation_unverified`. Metadata distinguishes binary installation, export and execution. Prompt export remains available even without a server-side native binary. HTTP final-prompt export remains outside execution admission. External MCP retains its explicit fixed project ID.
- `rag/api/routes_pipeline.py` and `rag/static/pages/pipeline.js` preserve Task 4 behavior while keeping the native export chooser reachable, showing a human Run reason, fetching the current runner/mode's external prompt when copying, and preventing selector changes or repeated clicks from launching another active stream.
- `rag/mcp_server.py` exposes the existing project-ID/header validation as a lightweight helper, reused by `rag/scripts/bench_mcp.py`; stdio environment and HTTP header now share one captured ID. `rag/scripts/bench_delta.py` uses the admitted legacy project manager instead of the removed singleton.
- PM-approved `rag/api/routes_reindex.py`/`rag/core/indexing.py` repair eager model initialization: optional `embed_model_factory=None` is invoked only after actual no-op planning and only when embedding is needed. The route passes its existing shared-model getter, initializes non-embedding resources first, and reuses one model across actual changes. Legacy delete-only work needs no model. Ordinary candidates include factory time in their existing init-model phase. No duplicate planner, new dependency or index refactor.

## Exact owned files

Product: `rag/agent_bridge.py`, `rag/agent_runners.py`, `rag/mcp_server.py`, `rag/index.py`, `rag/scripts/bench_delta.py`, `rag/scripts/bench_mcp.py`, `rag/api/routes_pipeline.py`, `rag/static/pages/pipeline.js`, and narrowly approved `rag/core/projects.py`, `rag/api/routes_reindex.py`, `rag/core/indexing.py`.

Tests: new `rag/tests/test_project_tools.py`, new `rag/tests/pipeline_runner_capability.cjs`, plus `rag/tests/test_project_runner_seam.py`, `rag/tests/test_agent_runners.py`, `rag/tests/test_agent_bridge_perimeter.py`, `rag/tests/test_agent_settings_isolation.py`, and PM-approved historical adapters `rag/tests/test_project_workflows.py`, `rag/tests/test_atomic_storage.py`, `rag/tests/test_index_timings.py`, `rag/tests/test_csp.py`, `rag/tests/test_llm.py`, `rag/tests/test_mcp_http.py`. Existing authentication, escaping, sandbox-argv and isolation assertions remain; helper translation tests replace impossible public native execution tests. Historical adapters accept captured-project kwargs; CSP still asserts every declared action is registered and now parses inline/shorthand registration keys.

## RED/GREEN evidence and gates

- Initial new tool/CLI/native tests: 21 failed, 1 control passed; failures covered missing project dispatch and incomplete read isolation. Initial GREEN: 22 passed.
- Absolute Glob pattern with a file base: 1 RED plus 6 controls, fixed by checking the pattern before the directory condition.
- Readonly mutators and MCP benchmark captured-ID mismatch: concrete RED, then shared guard/helper fixes.
- Empty operation values: three RED cases showed unintended full-build dispatch, fixed before admission.
- Mixed rollback/read flag: RED showed rollback skipped the writer lock; fixed dispatch precedence.
- Trusted absolute-code roots under `.codex`/`secrets`, then `docs`/`rag`: actual RED followed by scoped reserved-name checks; sensitive descendants remain denied.
- Real incremental plan no-op: RED initialized the model once; lazy callback fix preserves zero initialization on no-op, one shared initialization across two content changes, zero on legacy delete-only. A subsequent test assertion was adjusted to use the existing legacy result contract, which omits `noop` for real work.
- Reviewer default-layout finding: real bootstrap registry with legacy INSTALLROOT and A/B beneath projects reproduced own read denial (1 RED). Shared guard now excludes foreign descendants, not the selected project's legacy ancestor; actual SDK Read/Write/Grep/Glob and local read/write/list/grep positives plus legacy negatives cover both A/B.
- Earlier bounded API/agent/MCP/CLI/project gate: 204 passed. Windows extended tool gate: 34 passed, 1 skipped (actual file symlink privilege only).
- Safe broad diagnosis (`--maxfail=12`): 8 failed, 1169 passed, 4 errors, 15 warnings in 168.31s; it stopped at the requested failure bound and is not a complete-suite pass. Causes were stale test signatures, stale hook equality, CSP inline-action parsing, safe drift-error expectation, MCP fixture adaptation and the eager-model regression. Relevant failures were repaired without dropping their original assertions.
- Last adapter/core gate before the final regression assertion correction: 308 passed, 1 skipped, 1 failed in 49.11s; the failure was the new test's indexing result-contract assumption, not another product change.
- Final scoped package gate (18 relevant files): **582 passed, 18 skipped, 1 failed in 125.56s**. The sole failure was a historical reason-text assertion expecting `rag`; actual forbidden `../rag/rag_config.yaml` input still received SDK deny. PM-approved test adapter retains deny/shape assertions, requires the sandbox/perimeter reason and forbids raw path echo. Source product remained unchanged. Refreshed tools/perimeter result is appended below. Skip count includes existing project-artifact filelink cases plus the new Windows filelink case.
- Refreshed final tools/perimeter gate after reason adapter and portable directory links: **95 passed, 1 skipped in 19.96s**, covering all 50 new tools cases plus historical perimeter assertions. The skip is only the actual Windows file-symlink WinError 1314.
- Node: `pipeline_runner_capability.cjs`, `pipeline_agent.cjs`, `workflow_errors.cjs`, and `node --check static/pages/pipeline.js` passed. The capability harness exercises native export with Run disabled, fresh external prompt requests, and a pending stream with runner changes and no second fetch.
- Ruff on all owned Python files/tests passed; `git diff --check` passed.

Python gates run from this worktree's `rag` with the original Python 3.14.6 executable, UTF8/PYTHONPATH pointing here, BOTH Qdrant URLs set to `http://127.0.0.1:58123`. Final scoped gate additionally requires Qdrant and Docling, offline HF, and own-worktree HF_HOME. No environment installation, production reindex or real corpus deletion. Installed Claude Agent SDK inspected: **0.2.144**; hook input is the installed schema, without invented argument rewrites.

Exact final scoped selection:

```text
python -m pytest -q -o addopts='' tests/test_project_tools.py tests/test_project_runner_seam.py tests/test_agent_bridge_perimeter.py tests/test_agent_runners.py tests/test_agent_settings_isolation.py tests/test_mcp_server.py tests/test_mcp_http.py tests/test_index_cli_rollback.py tests/test_pipeline_execution.py tests/test_bench_delta.py tests/test_projects.py tests/test_project_indexing.py tests/test_project_workflows.py tests/test_atomic_storage.py tests/test_index_timings.py tests/test_csp.py tests/test_llm.py tests/test_incremental_indexing.py --tb=short --maxfail=5
```

Fresh adapter refresh:

```text
python -m pytest -q -o addopts='' tests/test_project_tools.py tests/test_agent_bridge_perimeter.py --tb=short
```

## Boundaries and operational audit

SDK native scans cannot filter unsafe descendants through their documented hook contract. A Grep/Glob scan is conservatively denied if its actual base subtree contains a reserved path, link or foreign root. For a normal Git checkout, a root-wide SDK scan can therefore be denied because `.git` exists; direct safe file Read, safe code subdirectory scans and MCP retrieval remain usable. Local tools prune unsafe descendants before returning content. No claimed native sandbox enforcement, fallback or host security setup.

Operational scripts reviewed: nightly/weekly shell and PowerShell jobs remain explicitly historical legacy workflows; doctor/server/CI and pinned Docling model scripts are installation concerns; synthetic graph/concurrency/semantic experiments do not acquire a project flag they would ignore. Actual broken delta benchmark manager and MCP project consumer were repaired. `migrate_spec_format` already uses its explicit input directory.

Windows actual junction tests cover root, code directory and ancestors, plus read/write/scan. Both directory-link tests use actual junctions on Windows and actual directory symlinks on Unix, with identical assertions and no Linux skip. Refreshed Windows directory-link gate: **4 passed, 46 deselected in 10.49s**. File symlink coverage skips only Windows WinError 1314 (no privilege); it does not silently skip other link failures. PM will supply Linux proof using:

```text
python -m pytest -q -o addopts='' tests/test_project_tools.py -k "file_symlink or junction_file or replaced_roots or own_absolute_write or default_registry_legacy or legacy_foreign_registration or sdk_scan or glob_absolute_pattern or tilde_and_rooted_glob or captured_read_guard" --tb=short
```

Relevant actual-filelink test: `test_file_symlink_is_never_read_listed_or_grepped`; absolute own-code and ancestor regression: `test_own_absolute_write_ignores_harmless_trusted_root_ancestors`; default registry layout: `test_default_registry_legacy_ancestor_keeps_ordinary_tools_usable`. Linux does not replace Windows junction evidence.

PM Linux proof: **20 passed, 30 deselected, zero skipped in 18.55s, exit 0**. It exercised actual file/directory symlinks, root/code/ancestor replacement, harmless absolute-root ancestors, default legacy/ordinary registry layout, foreign-root registration refresh and corrupt/removed manifests, unsafe SDK subtrees, Glob patterns and registry damage. Runtime was the reused CPU image with Python 3.14.7 and SDK 0.2.144, current readonly source overlay and existing pytest scratch, with network disabled. This is current-source/runtime-overlay evidence, **not a fresh Docker build**. No provider calls, dependency installation or host security changes.

Exact PM command (from the PM ledger, worktree root):

```powershell
docker run --rm --network none --mount 'type=bind,src=C:/Users/Silve/.codex/worktrees/multi-project/vibecraft/rag,dst=/candidate/rag,readonly' --mount 'type=bind,src=C:/Users/Silve/.codex/worktrees/multi-project/vibecraft/docs/superpowers/plans/multi-project-tasks/linux-testtools,dst=/testtools,readonly' --workdir /candidate/rag --env PYTHONPATH=/candidate/rag:/testtools --env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 --env PYTHONDONTWRITEBYTECODE=1 --env QDRANT_URL=http://127.0.0.1:58123 --env VIBECRAFT_TEST_QDRANT_URL=http://127.0.0.1:58123 --env HF_HUB_OFFLINE=1 --entrypoint python vibecraft:cpu -m pytest tests/test_project_tools.py -k 'file_symlink or own_absolute_write or default_registry_legacy or legacy_foreign_registration or sdk_scan or glob_absolute_pattern or tilde_and_rooted_glob or captured_read_guard or junction_file_and_ancestor or captured_sdk_guard' -rs -o addopts= -o cache_dir=/tmp/pm-pytest-cache --tb=short
```

Independent formal review: **PASS** (`task-5-review.md`), fresh reviewer tools/seam gate **65 passed, 1 skipped in 24.63s**, plus Node capability PASS. The legacy-ancestor preflight finding is closed. PM then approved one last test-only real-Git fixture: `test_real_git_checkout_keeps_safe_code_tools_and_denies_git_reads`, **1 passed in 10.22s**, Ruff PASS. It uses local `git init` in the owned temporary code root (no identity configuration, commit or network), proves safe Read/src Grep/Glob remain usable, root-wide SDK Grep/Glob are denied, `.git/config` Read is denied, and local root scans safely prune `.git`. Product remained unchanged. Product/test source refrozen after this scoped addition; reviewer receives the test-only closure through PM.

## Sanitized test-boundary incidents

An initial native RED monkeypatch missed `run_cli`'s already-bound default Popen argument. Native launch and startup network traffic occurred: Cursor rejected authentication; Codex received HTTP 400 unsupported-model startup rejection. No evidence of model execution or sandbox setup was observed; this does not establish zero host side effects. Readonly process inventory found no surviving owned agent children. PM/root were informed. Subsequent tests bind fake Popen at the effective call site or spy the runner dispatch before any native call. Owned temporary stderr fixture paths were `C:/Users/Silve/AppData/Local/Temp/tmpb0nmfxyl/stderr.txt` and `C:/Users/Silve/AppData/Local/Temp/tmpdfr6a45g/stderr.txt`; no account identifiers, headers or stderr contents are recorded here, and no unproven host logs/config were removed.

A mixed-flags RED initially lacked a Qdrant constructor fake. A compatibility read against default port 6333 was possible; project-manifest mismatch rejected before vector access/write or CURRENT mutation, with no vector/write evidence. Fake constructor was added and the actual failure reverified. The first broad suite lacked QDRANT_URL despite its dedicated test URL and was interrupted at 61% without a completion result. All later Python gates set both dedicated URLs. These earlier executions are not claimed production-isolation proofs.

Final whole-branch gate remains Task 8 after Task 7; this scoped package does not claim that later gate.

The final scoped raw log was moved, after its owned process completed, to ignored `docs/superpowers/plans/multi-project-tasks/local-task5-logs/task5-final-scoped-gate.log`; it is not part of the commit package. Product and tests frozen after the refreshed gate; only report/proof results may be appended until review.

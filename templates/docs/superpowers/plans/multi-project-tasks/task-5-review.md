# Task 5 independent review

Verdict: **PASS**, with no unresolved findings in the frozen Task 5 product/test package based on `dde1ef92be99c5c5d15926634bfed9c1288b91fe`. This is a scoped spec and quality/security review, not the final whole-branch acceptance gate. The reviewer authored no product code, staged nothing and started no native agent/provider.

## Scope and specification

Reviewed the 23 staged product/test files, the package/report and the binding Task 5 brief, including the previously accepted native compatibility ruling. CLI project capture covers full/delta/status/integrity/graph/drift/archive/migration and all rollback stages; writer-lock selection follows actual dispatch precedence. An absent project flag retains legacy semantics despite MCP environment selection, and empty operation arguments cannot fall through into a rebuild.

SDK/local tools share the captured root/code guard. Readonly registry views refresh validated metadata, retain observed-registry deletion detection, do not bootstrap or take a writer lock, and reject mutators before side effects. Foreign-root checks remain effective after foreign manifests are removed/corrupt and for newly registered roots. Link checks precede resolution, including captured root/code/ancestor replacements. SDK scans conservatively deny unsafe descendant subtrees; local scans prune them. Safe own-project reads, writes and scoped scans remain available.

Native Codex/Cursor integrated launch fails before process creation through HTTP admission, streaming admission and the direct CLI generator. The reason code agrees with metadata/UI. Export remains selectable with binaries absent, and copy requests a fresh external prompt for the selected runner/mode. Active-run state prevents selector changes from enabling a second launch. This implements the approved capability limitation; it does not establish native sandbox enforcement.

MCP captures its project header for the session. The benchmark snapshots environment before constructing both stdio and HTTP consumers, so a later environment change cannot split their identities. The delta benchmark uses the admitted legacy manager. The small model factory extension runs after no-op planning, preserves shared-model reuse and legacy delete-only behavior, and passes the selected context through the ordinary full candidate build.

## Closed preflight finding

**P2 — a registered legacy ancestor denied ordinary own-project tools.** The earlier candidate used `foreign != root and candidate.is_relative_to(foreign)`. An independent temporary real `ProjectRegistry(root / 'projects')`, bootstrapped by `root/code/old.py`, followed by `create('A')`, reproduced `PermissionError: area di un altro progetto` for A/code/app.py. This is the default installation layout, not a synthetic invalid overlap.

The frozen guard additionally requires `foreign.is_relative_to(root)`. Thus a captured ordinary project ignores its legitimate legacy ancestor while a captured legacy project still excludes nested foreign descendants. The fresh regression uses actual bootstrap plus A/B creation and checks SDK Read/Write/Grep/Glob, local read/write/list/grep, and legacy negatives. Finding closed.

## Independent evidence and limits

- Fresh reviewer gate: `tests/test_project_tools.py tests/test_project_runner_seam.py` — **65 passed, 1 skipped in 24.63s**. The only skip is actual Windows file-symlink creation requiring unavailable privilege. Actual Windows directory junction cases ran. Before execution the reviewer inspected the explicitly bound fake `popen` in both direct CLI and streaming paths, the mocked SDK query/local chat, and the loopback synthetic MCP transport. No native agent execution was needed.
- Fresh reviewer Node gate: `tests/pipeline_runner_capability.cjs` — **PASS**, including native export, disabled Run with reason, fresh external prompt, and no duplicate launch during an active request.
- The independent Python gate includes actual no-op planning, lazy shared-model initialization, own-project positives, foreign/link/secret negatives, registry corruption/deletion, native admission, HTTP export/auth and CLI dispatch/lock cases. It also exercises actual stdio MCP sessions against a synthetic loopback HTTP server.
- PM supplied complementary Linux CPU-image evidence on read-only source: **20 passed, 30 deselected, 0 skipped in 18.55s**, including actual file/directory symlinks and root/code/ancestor replacements. This is PM evidence, not a separately repeated reviewer run; it complements Windows junction coverage.
- Execution used the original Python executable with worktree `rag` cwd/PYTHONPATH, UTF8, both Qdrant URLs on the dedicated 58123 endpoint, and offline HF with a worktree cache. No broad baseline suite was repeated. Product/test worktree-versus-index diff was empty when checked during review; later report/proof updates do not change this verdict's product scope.

The implementation report correctly records the earlier worker test-boundary incidents: native startup/network occurred before effective Popen injection was fixed, and an earlier Qdrant isolation boundary was incomplete. This review does **not** recast those earlier runs as provider/network-free or claim zero host effects. The later scoped guards and evidence are assessed separately. Whole-branch compatibility and final acceptance remain the later planned gate.

Post-review test-only closure: inspected `test_real_git_checkout_keeps_safe_code_tools_and_denies_git_reads`, which creates a temporary Git repository and asserts safe SDK Read/scoped scans, root scan and `.git/config` denial, plus local pruning. Accepted; worker reports **1 passed in 10.22s** and Ruff green. Product code is unchanged; scoped PASS remains valid without repeating the broader gate.

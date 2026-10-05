# Independent whole-branch final review

**Verdict: PASS — specification and quality/security. No unresolved blocking findings.**

Reviewed baseline `34b46dfeabcff05820240a1241baae1a215d3e1b` through committed HEAD `06c7626d8183834b30476d3fe92a4fe3945c2f03`, plus the frozen staged Task 8 candidate identified in `task-8-final-review-package.md`. Branch: `codex/multi-project`. The final complete gate has finished successfully. This verdict includes the approved capability limits below; it does not claim native sandbox enforcement, a fresh dependency installation or a fresh full Dockerfile build.

The reviewer authored **zero product/test files**, made no staging/commit changes, spawned no agents and ran no native agent/provider. Reviewer-authored files are review reports only. PM owns implementation decisions, fixes and integration.

## Review scope

Audited the whole branch by subsystem and its acceptance criteria, using the binding plan, current source/diff, the independent Task 1–7 review and fix reports, and the final integration fixture. Traced project admission into runtime/snapshots/cache, artifact paths and collection lifecycle, pipeline/intake callbacks/stores, CLI/MCP/runner entry points, browser request/frame identity and Docker registration/health. Previously reviewed fixes remain present. Historical adapter changes retain their original concurrency, header, auth, cross-site and route-classification assertions; the integration test detects leaked dependency overrides rather than clearing them.

The outstanding Task 2 context-propagation checkbox is supported by the completed Task 4/5 paths: ordinary requests carry the captured project through source/index storage, collection resolution, ranking/settings, workflow validation and generation, import/reindex callbacks, CLI operations and agent tools. No further reachable ordinary-project fallback to global legacy paths was found in that audit. The lock-path defect found below was fixed before this final acceptance.

## Final finding and closure

**P1 — writer lock could truncate a foreign file through a link: CLOSED.** In the pre-fix candidate, `core/writer_lock.py` constructed the selected database's `.writer.lock`, created its parent, opened the path and wrote diagnostic bytes with `ftruncate`, without checking the file and its ancestors for links.

Independent Windows repro used two real temporary registry projects. B/database/.writer.lock contained `B_SENTINEL_UNCHANGED`; after A's context was captured, A/database was replaced with an actual junction to B/database. `with writer_lock(project=a): pass` changed B's sentinel into the PID diagnostic. The observed result was `cross_project_lock_truncated=True`. No provider, model, Qdrant operation or real corpus was involved. The related Linux file-link case places A/database/.writer.lock directly onto B/docs/victim.md before registry admission.

The PM fix adds one small shared guard for the lock file and every ancestor before filesystem creation/open, rechecks after parent creation, guards holder diagnostics and applies the same ancestor validation to version leases. POSIX open adds `O_NOFOLLOW` where supported. Existing OS locking, explicit `lock_path`, ordinary/legacy use and version leases remain intact. Regression tests preserve foreign bytes and prohibit foreign directory creation, alongside positive usability cases. This closes the reproduced static-link/captured-context conditions; no immunity to every adversarial filesystem race is claimed.

Fresh reviewer lock gate: **13 passed, 1 Windows file-link privilege skip in 7.44s**. Complementary PM Linux gate: **14 passed, 0 skipped in 11.24s**, including the actual file-link case. The reviewer flagged an overly broad test skip; the PM narrowed it to Windows WinError 1314 and the reviewer verified the final source. The reviewer did not author that test edit.

## Acceptance assessment

| Criterion | Assessment and concrete evidence |
| --- | --- |
| AC1 | PASS. Actual HTTP creates A/B; the real browser creates C and opens existing D. Real registry checks four distinct roots and complete code/docs/changes/database layouts. |
| AC2 | PASS. Same paths, same query and colliding v1 tokens yield distinct A/B source sentinels through actual builds, Qdrant retrieval, snapshots and answer cache. A repeat hits A's cache; B does not borrow it. |
| AC3 | PASS. Actual A import/delta, held full build, rollback and orphan GC leave B CURRENT bytes, artifact hashes, alias and stored vectors unchanged; B integrity passes. Existing indexing/lease/retention regressions also pass the complete gate. |
| AC4 | PASS. Same feature is independently saved and validated in A/B. Persisted source records carry the correct snapshot version and sentinel; B cannot use A's import plan, validation or job. Actual callbacks, journal and locks remain captured to A. |
| AC5 | PASS. Independent real-browser A→B→A preserves answers/input. Prior reviewed workspace gates cover separate tabs, late stream/job results, busy-frame eviction limits and fixed request/retry identity, including mutable URL handling. |
| AC6 | PASS within the approved capability policy. Actual local provider simulation invokes the real guarded write tool into A only. Task 5 SDK/local, CLI and real stdio MCP proofs verify fixed context and denied foreign/link/secret paths. Codex/Cursor integrated execution is disabled before Popen; export and fixed-ID external MCP remain available. Native cross-project read enforcement is not claimed. |
| AC7 | PASS. API/UI and container proofs support a usable empty shell, explicit project-required/not-indexed/storage states and no silent fallback. Newly created/opened empty projects remain unindexed. |
| AC8 | PASS on temporary legacy fixtures. Registry and indexing tests preserve legacy paths/collection identity and in-place bootstrap without a build or move. The reviewer did not reindex or mutate the user's original corpus to establish this. |
| AC9 | PASS on the supported evidence. Actual Docker source-overlay tests cover UID10001, project restart persistence, empty/Qdrant-down liveness, authenticated reader health and strict remote managed-root registration. Current auth/CSP/Host/cross-site/reader tests pass. Arbitrary host roots/native browse stay local-only; reader create409 remains historical, register403 is enforced. |
| AC10 | PASS with explicit environment limits. Complete lint/pytest, real dedicated Qdrant integration, Node/browser gates and complementary Linux link proofs are available. Fresh full image build and an actual GitHub Actions run remain unverified, as permitted by the criterion's explicit reporting requirement. |

## Verification evidence

**Personally executed by this reviewer during final review:**

- Pre-fix real Windows junction repro demonstrating foreign lock truncation; temporary files only.
- Post-fix `tests/test_project_lock_confinement.py tests/test_writer_lock.py`: **13 passed, 1 skipped in 7.44s**.
- `tests/test_project_integration.py` with `VIBECRAFT_INTEGRATION_BROWSER=1`: **1 passed in 19.02s**. Actual ephemeral FastAPI HTTP server, Qdrant collections, filesystem/artifacts/stores/jobs, import, validation, guarded local write, held A build with responsive B, rollback/GC and real browser were exercised. Embedding/LLM/local chat provider boundaries were simulated. Browser routes were not intercepted.
- Inspected the complete raw `task8-full-pytest-candidate.log` summary and its skip groups. Checked absence of unstaged product/test changes during final review. No second full suite was run by the reviewer.

**Completed candidate gate, executed by worker and corroborated from raw output:**

- `uv run --frozen --no-sync --active ruff check .`: PASS.
- `uv run --frozen --no-sync --active pytest -rs`: **2348 passed, 20 skipped, 15 warnings in 359.39s**, process exit 0 confirmed by PM. Dedicated Qdrant, Docling and LibreOffice were mandatory; none of those integrations skipped. The warnings are reported Docling deprecations.
- All 20 skips are Windows file-symlink privilege limitations: 1 project API, 17 artifact cases, 1 new lock case and 1 agent-tool case. Actual directory junctions ran. Complementary Linux source-overlay proofs cover the corresponding file-link surfaces: prior 35 artifact/API cases, 20 SDK/local cases, and current 14 lock-suite cases, all with zero skips. These are separate test sets, not an assertion of 69 distinct skipped cases.
- Worker/PM report seven Node checks and actual navigation PASS, plus the combined integration/browser gate. Prior Task 5/7 reports distinguish personally rerun reviewer checks from worker/PM evidence.

Every final reviewer Python process used the worktree cwd/PYTHONPATH, original installed interpreter, UTF8, both Qdrant URLs at the dedicated `http://127.0.0.1:58123`, and offline HF with a worktree cache. The integrated fixture deletes only exact physical collection names in its newly created UUID namespaces and shuts down its own server/jobs. No production Qdrant or real-corpus mutation was part of this review.

## Limits retained in acceptance

The reused venv's 163 checked installed package base versions match the worktree lock; this does not prove a fresh clean install or wheel/source artifact identity. Docker evidence uses current source over an existing CPU dependency image and explicit empty fixture mounts, not a fresh frozen product image. GitHub Actions was not executed locally. Windows link privileges were not changed.

Native Codex/Cursor integrated launch remains unavailable until its read boundary is independently verified; there is no silent provider fallback. Exports/external MCP remain usable. SDK Grep/Glob can reject a subtree containing forbidden descendants, including `.git`; safe direct Read, safe scoped scans and MCP remain available, while local scans prune forbidden entries. Ordinary nonempty delta currently rebuilds the full candidate; lazy startup performs no automatic alias repair/GC.

Earlier Task 5 test-boundary incidents remain disclosed: an ineffective Popen injection allowed native startup/network traffic, and an earlier incomplete Qdrant environment override allowed possible default-port compatibility contact. The current passing gates do not rewrite that history as zero network/provider contact or prove zero host effects. No paid model execution/billing or real corpus mutation was evidenced. The interrupted/failed earlier gates are not presented as passing results.

With the reproduced lock defect closed and the completed candidate gate corroborated, no additional product fix is requested by this independent review. PM may mark the supported plan/acceptance items complete and integrate the reviewed candidate without changing product source.

# Task 7 independent review

Verdict: **PASS** for the frozen 12 product/test files plus implementation report staged against `24c7eb078080d69f6256c7a195c6895dc5600d2a`. No unresolved spec or quality/security findings. This is a scoped distribution review; final whole-branch acceptance remains Task 8. No product edits, staging, native provider execution or container rebuild were performed by the reviewer.

## Specification and security

Remote registration reuses the existing registry and `_unlinked` guard. It requires absolute, traversal-free input resolving strictly beneath the configured managed directory; root/ancestor links and the managed directory itself are rejected before `registry.register` reads the requested manifest. Reader registration returns 403 before registry acquisition. Router authentication and the cross-site dependency remain in place. Local arbitrary-root registration remains available, and the historical reader create response remains 409/read_only per the explicit compatibility ruling.

UI help describes the managed-root restriction without injecting the configured private host path. Remote native browse remains hidden, while manual managed-root submission remains available. Local metadata disclosure remains conditional on local bind and local request.

All three Compose profiles use the same separate persistent project volume at `/app/projects` and retain legacy index and shared-model volumes. Dockerfile creates/chowns that directory before switching to UID 10001. The liveness command uses `/api/health/live` and supplies the API key from process environment, including reader mode, without printing it. Project storage and development plans/reports are excluded from the Docker context.

Documentation describes create/open/per-tab selection, CLI versus MCP selection, mounted host/IDE paths, backup scope, in-place legacy registration, reader initialization, lazy startup and explicit writer maintenance. It accurately distinguishes initial missing registry from disappearance after observation, ordinary nonempty delta rebuild cost, native integrated-launch unavailability with exports retained, and conservative SDK scans with safe Read/scoped alternatives.

CI retains existing gates and adds workflow/capability tests plus actual browser navigation. Playwright is pinned as temporary test tooling rather than a product dependency. Existing launchers use Chromium on Linux and Edge only on Windows. Navigation starts a real loopback uvicorn process, bounds readiness waiting and installs cleanup before checking readiness. No claim is made that GitHub Actions or a fresh frozen Dockerfile build ran locally.

## Verification

- Fresh independent focused gate: `test_project_api.py` remote-registration, mutation, remote-metadata and empty-shell cases, plus the executable multi-project distribution contract — **6 passed, 18 deselected in 10.51s**, no skips. Mocks/fixture boundaries were inspected first. This covers actual temporary registry roots and a Windows directory junction, remote missing-key 401, authenticated inside 201, outside/root/traversal 403, local arbitrary-root compatibility, reader registration 403, no denied manifest access, and healthcheck header execution.
- The gate used the original Python executable with explicit worktree `rag` cwd/PYTHONPATH, UTF8, both Qdrant URLs on the dedicated 58123 endpoint, and offline HF/worktree cache. No model/provider/native agent was started by these cases.
- Read the actual owned Docker smoke/reader/persistence scripts and their PASS logs. They support the implementer's reported UID10001, explicit empty-installation mounts, Qdrant-unavailable liveness, creation/layouts, remote registration boundaries with real POSIX symlink, restart persistence and authenticated reader liveness. This is complementary implementer evidence, not a newly repeated reviewer container run.
- The report distinguishes the source overlay based on an existing CPU image from a fresh full frozen build, records the corrected reader immutable-mode setup and preserved create409 expectation, and identifies cleanup of owned containers/volume/tag. Existing image and PM Qdrant are outside that cleanup scope.
- The report records all-profile quiet Compose validation, Windows browser/navigation and Node checks; the reviewer inspected the CI wiring and browser source changes. These do not establish an actual Linux GitHub Actions run.
- No unstaged product/test differences were present when checked during review. No further broad suite or redundant Docker build was needed for this unchanged scoped candidate.

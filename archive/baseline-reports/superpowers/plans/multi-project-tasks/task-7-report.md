# Task 7 — Distribution, instructions and CI

Status: PM accepted after independent spec/quality/security PASS. PM owns staging/commit.
Base: `24c7eb078080d69f6256c7a195c6895dc5600d2a`, branch `codex/multi-project`.
All commands ran only in `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft`
or its `rag/`; original checkout was never edited/mounted.

## Exact ownership

- `docker-compose.yml`
- `Dockerfile`
- `.dockerignore`
- `rag/.env.example`
- `README.md`
- `rag/README.md`
- `.github/workflows/ci.yml`
- `rag/api/routes_projects.py` (narrow authorized remote registration rule)
- `rag/static/pages/workspace.js` (generic managed-root help)
- `rag/tests/test_project_api.py`
- `rag/tests/projects_workspace.cjs`
- `rag/tests/test_docker_compose_pinned.py`
- this `docs/superpowers/plans/multi-project-tasks/task-7-report.md`

The progress ledger is PM-owned; its working change is not mine.
No core registry/contracts, native runners, product dependency/lock, provider,
security host setup, staging or commits changed.

## Implementation

All three Compose profiles use `VIBECRAFT_PROJECTS_DIR=/app/projects` and a
separate named writable volume. Existing index/model mounts and optional legacy
docs/code mounts are retained. Dockerfile creates/chowns projects before UID10001.
Docker context excludes both projects and `docs/superpowers/` working artifacts.
Liveness uses `/api/health/live`; urllib Request reads the key from os.environ,
never prints it, and applies normal authentication including reader mode.

Remote registration removes blanket local-only rejection, then checks absolute,
raw `..`, every link/junction ancestor through existing `_unlinked`, canonical
strict descent beneath the existing registry directory, before registry.register
can inspect the requested manifest. Outside/managed-root-itself/traversal/links
return generic403. Local arbitrary root remains supported. Reader register403;
existing reader create409 read_only remains unchanged (PM ruling).

UI browse remains hidden on remote bind and help explains managed roots with
Docker `/app/projects/<cartella>` without disclosing private host PROJECTS_DIR.
README describes create/open/per-tab selection, CLI flags/MCP fixed ID, external
mounted root→host IDE mapping, storage/backups, in-place legacy and reader setup,
lazy resources/explicit maintenance and ordinary delta full-rebuild cost. Old
boot-GC/native-runner claims were corrected. Main instructions live in root README;
rag README links them and retains specific CLI/reader information.

CI adds workflow_errors/pipeline_runner_capability plus both browser gates.
Playwright1.62.1 and Chromium are temporary CI tooling under /tmp, outside product
package/lock. Navigation uses actual uvicorn9876 readiness, a bounded wait and EXIT
cleanup. Existing checks remain; no additional embedding/model download added.
Compose validation now uses `config --quiet`.

## RED / GREEN and checks

Every local Python command used `task7-env.ps1` in the ignored task directory:
PYTHONUTF8=1; PYTHONPATH=worktree/rag; QDRANT_URL and VIBECRAFT_TEST_QDRANT_URL
http://127.0.0.1:58123; REQUIRE_QDRANT=1; REQUIRE_DOCLING=1; HF_HUB_OFFLINE=1;
HF_HOME=worktree/rag/database/models/hf; VIRTUAL_ENV=original/rag/.venv.
`uv run --frozen --no-sync --active` reused installed frozen-compatible runtime.
No new environment/dependency installation or fresh wheel build is claimed.

- RED `pytest tests/test_project_api.py -k remote_registration -q -o addopts= --tb=short`:
  1 failed/1 passed/15 deselected, 10.86s. Managed valid inside root expected201,
  received403 from previous local-only dependency. `task7-red.log` preserves it.
- GREEN boundary+existing local-bind test: 3 passed/14 deselected,10.77s.
  Actual temp manifest/layouts; inside201, outside/root-itself/rawtraversal403,
  denied root never reaches registry.register, local outside201, reader403.
  Windows actual directory junction rejected403 with no skip; POSIX uses symlink.
- `pytest tests/test_project_api.py tests/test_docker_compose_pinned.py tests/test_dockerignore.py -q -o addopts= --tb=short`:
  49 passed/1 existing Windows file-symlink skip,17.91s. Distribution test executes
  Docker healthcheck code with intercepted urllib and verifies key/endpoint, profiles,
  storage/models and exclusion rules.
- Final auth strengthening on frozen product: remote192.0.2.1 client missing key401,
  supplied key inside201/outside403; local cross-site unkeyed register403. Targeted
  rerun 2 passed/15 deselected,10.41s (`task7-final-api.log`).
- `ruff check api/routes_projects.py tests/test_project_api.py tests/test_docker_compose_pinned.py`: all checks passed.
- `projects_workspace.cjs`: all fetch/query/reindex/browser groups PASS. Remote
  help/browse-hidden/manual-managed-open covered. Existing extraction failed after
  Task5 made copyFinalPrompt async; corrected only the owned extraction boundary,
  preserving all polling/assertions (`task7-browser.log`).
- Actual server: original installed python binary, cwd worktree/rag, `-m uvicorn
  server:app --lifespan off --host 127.0.0.1 --port 9876`; live200 readiness before
  `navigation_workspace.cjs` PASS, including preserved stream/agent/intake/CSP.
  Owned PID11012 shut down with CtrlC; session closed (`task7-navigation.log`).
- Existing Node intake_excel_preview, pipeline_dryrun_escape, dashboard_graph_escape
  plus workflow_errors/pipeline_runner_capability: all PASS using bundled Node26
  and NODE_PATH bundled Playwright.
- `VIBECRAFT_API_KEY=<synthetic> docker compose --profile <cpu|gpu|host-ollama> config --quiet`: all exit0; no env/key dumps.
- `git diff --check`: exit0.

## Actual Docker proof and limitations

Unique candidate `vibecraft:task7-candidate-20261005` built with
`docker build --pull=false --network none -f docs/superpowers/plans/multi-project-tasks/task7-container/Dockerfile -t vibecraft:task7-candidate-20261005 .`.
Candidate FROM existing local `vibecraft:cpu`, copies current rag source using
.dockerignore (no .venv/database/secrets), retains its dependency venv, mkdir/chowns
projects before USER vibecraft, and uses the actual new HEALTHCHECK command.
Only health scheduling was shortened to 5s/10s start for the smoke.
This is a source overlay runtime proof, NOT a full frozen product Dockerfile build.
No heavy model download, product install, native CLI or provider launch occurred.

Exact owned test objects:
- image above
- containers `vibecraft-task7-writer-20261005`, `vibecraft-task7-reader-20261005`
- volume `vibecraft-task7-projects-20261005`, created2026-10-05T08:59:39Z
- exact empty bind directories under task7-container: docs→/app/docs,
  code→/app/code, changes→/app/changes, database→/app/rag/database.
  Source venv is NOT hidden by database mount; no original checkout mount.

Containers ran with `--network none`, HOST0.0.0.0, PROJECTS_DIR/app/projects,
synthetic key, prescribed Python/offline/Qdrant58123 env (HF_HOME shared /models/huggingface).
The dedicated PM Qdrant container and production6333/corpus were never modified.
Smoke scripts use real HTTP urllib requests inside containers; assert uid10001.

Writer: zero projects, live200 despite Qdrant unavailable, retrieve409;
create A/B201 with all four directories; managed existing201; outside/traversal/
actual POSIX symlink403. Docker actual health status healthy.
After `docker restart`, exact A/B+mounted registry/layouts persisted and HTML console200.
Reader: required INDEX_MODE=immutable; live200 with key and401 without key while
Qdrant unavailable; list read_only true; create409/read_only and register403.
Actual reader health status healthy proves the image healthcheck supplies its key.
Raw scripts/build/smoke/persistence/reader logs remain in ignored task7-container/.

Recorded non-product corrections: first reader launch omitted existing mandatory
INDEX_MODE=immutable and exited1; recreated only its owned container with the setting.
First reader assertion incorrectly assumed create403; PM confirmed preserving409.
A combined orchestration command was rejected by execution policy (no stated reason);
smaller individual commands/foreground owned server session completed the same work.

Cleanup verified exact names/health/volume timestamp, then removed only the two owned
containers, owned volume and unique candidate tag. Source scripts/logs remain; base
vibecraft:cpu and all other containers/volumes untouched. Local navigation process exited.
GitHub Actions themselves (Linux Chromium installation and full fresh image build)
were not executed from this machine; workflow wiring/static checks and Windows Edge
browser plus actual local Docker overlay proofs are the evidence available.

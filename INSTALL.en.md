English | [Italiano](INSTALL.md)

# Install and operate

The full guide: requirements, startup, projects, updates, scalability, configuration, MCP,
and security. The overview is in the [README](README.en.md).

## Before cloning

`archive/` is not the product. It is the historical evidence of measurements, cited by the ADRs: see [archive/README.md](archive/README.md) / [archive/README.en.md](archive/README.en.md). Docker and the tests do not read it. From 2026-10-28 (R6) the tip of `archive/eval-results/` keeps reports and pointers (~4 MiB of text); heavy blobs (~108 MiB of json/jsonl/log) remain in **history** — deleting them from the tip alone does not lighten a full clone. For a light clone that does not download them:

```bash
git clone --filter=blob:none --sparse https://github.com/Silver1V8/VibeCraft.git
cd VibeCraft
git sparse-checkout set '/*' '!archive/eval-results'
```

Inventory and recovery: [archive/eval-results/HEAVY_REMOVED.md](archive/eval-results/HEAVY_REMOVED.md).

Operational console docs are no longer a monolith: index in [`rag/README.md`](rag/README.md), pages in [`rag/docs/`](rag/docs/) (outside the corpus, like ADRs). Italian is canonical; [`rag/README.en.md`](rag/README.en.md) is a short index.

**Documented status: `main`, 28 October 2026.**
Multi-project has been in `main` since 5 October; copy-on-write delta and GPU embedding since the 12th. The in-console manuals are from the 25th. Gate numbers remain those of the day they were measured. The same status is in [`rag/README.md`](rag/README.md) / [`rag/README.en.md`](rag/README.en.md).

## Separate projects

Opening `/` shows the home screen with recent projects, search, creation, and opening of existing folders. **Projects** in the bar returns to selection without interrupting active operations. `?project=<id>` links open the project directly; recent history is kept in the browser.

The console also works without projects or an index. **New project** creates a root with `project.yaml`, `code/`, `docs/`, `changes/`, `database/` under `VIBECRAFT_PROJECTS_DIR` (absolute path; default `<install>/projects`). It does not start indexing: import code/documents from Intake and index the project. **Open existing project** registers a VibeCraft root without copying it: with a local bind you can choose a host folder; with a remote bind only a root without symlink/junction strictly under the managed projects directory. In Docker use `/app/projects/<folder>` and mount the existing project there; the native picker is hidden. Example extra Compose mount: `/host/path/project:/app/projects/existing` (root with a valid `project.yaml`). In the console open `/app/projects/existing`; in the IDE open the original host folder. The mount links the paths: VibeCraft does not copy the repository automatically. The project name does not build paths.

Selection is per tab: `sessionStorage` and `?project=<id>` keep the target; jobs already started stay in the original project. Two projects can keep resident pages; active operations block eviction. The pipeline saves interview, inputs, and drafts locally per project and feature. After refresh or close you can choose “Restore local draft” after server files load: restore does not overwrite them. Until you restore or discard the draft, chat and editor stay read-only; the development type remains selectable and restore replaces it only if the draft had one. The last save is visible; drafts stay in the browser and are not synced across devices. From the console you can rename (display name only: id, folder, and Qdrant namespaces stay unchanged), delete (destroy for managed roots under `VIBECRAFT_PROJECTS_DIR`; unregister for external roots, without deleting host files), and filter the project list by name or id (`GET /api/projects?q=`). Cross-project corpus search is not supported (each question stays in one project), nor is per-project ACL.

From `rag/`: `uv run python index.py --project <id> --index-status` selects the project also for full/delta/integrity/rollback; without the flag it uses only `legacy`. The ID is in the console `?project=<id>` parameter or in `GET /api/projects`. Project APIs receive `X-VibeCraft-Project: <id>`; without the header only the registered `legacy` project is used. For external MCP set `VIBECRAFT_PROJECT_ID=<id>` in the process environment, beyond the usual URL/key config: the target stays fixed for the session.

A single Qdrant hosts distinct namespaces: alias `vibecraft_<id>` and collection `vibecraft_<id>__<version>`. Cache, graph, staging, jobs, gate, and history are per project; changing selection does not change the target of work already started.

The initial project also has a dedicated root: `projects/legacy/`, with `code/`, `docs/`, `changes/`, and `database/`. On first writer start VibeCraft copies and verifies the baseline into `projects/legacy/`, without indexing or downloading models: `docs/` and `code/` at the install root if they contain files, otherwise the versioned baseline in `templates/docs/` and `templates/code/` (the clean local clone case; the Docker image already has it in `/app/docs` and `/app/code`). `template_*.md` files in `templates/` are not copied. Other new projects start empty. An already empty registry stays empty. The name `legacy` identifies the initial project: it uses the same runtime and index as the others. The index reads only `docs/` and `code/` in the selected project root. In PyCharm expand `projects/legacy/` or `projects/<id>/`; the active root is also in the project metadata. Folders at the install root are only the source of that initial copy. The reader does not initialize the registry: an initially missing registry returns `[]` and requests without a project return `project_required`; after it has been observed, its deletion/corruption fails closed. Initialize with a writer before reader deploy; configure `VIBECRAFT_ROLE=reader`, `VIBECRAFT_INDEX_MODE=immutable`, and a required API key.

Compose keeps `vibecraft_projects:/app/projects` separate from `vibecraft_index` with UID 10001 permissions; historical docs/code/database mounts serve as migration sources. Weights are shared (`vibecraft_models`, Docling cache in the install, `ollama_models`), not copied per project. Consistent backup: registry, manifest, code/docs/changes/database of every root (including registered external roots), legacy volume, and `qdrant_storage` with matching collections; also save model volumes if you want to avoid downloads. Stop writes during backup.

`/api/health/live` checks only the process, even without projects or with Qdrant unavailable; it requires normal authentication, including the key in reader mode. Readiness and index status are separate in `/api/health` and project metadata. Models/clients/snapshots load on demand: opening the console does not download weights, repair aliases, or run GC. Maintenance is explicit via writer/CLI lifecycle. For ordinary projects a non-empty delta publishes a copy-on-write version: a new collection with unchanged parent points and re-embedding of only changed documents and code files. If the parent is not reusable it falls back to a full rebuild (reason in the job’s `fallback_reason`); a noop delta writes nothing.

Embeddings for reindex jobs use an accelerator only for the duration of the job. Which component takes the weights, and when they are shared instead, is written once in [rag/README.md](rag/README.md#embedding-bge-m3-cpu-per-le-query-acceleratore-per-il-reindex). `/ask` stays on the server CPU.

### Migrating an existing install

With historical data, opening returns `project_migration_required`: migration is explicit. Stop server, reader, and other writers; keep the variables that point at the original database and staging. From `rag/`:

```bash
uv run --frozen python -m scripts.migrate_project_layout
```

Migration keeps ID `legacy`, originals, and old collections; it copies and verifies documents, code, changes, staging, pipeline, and golden set. If an index exists, Qdrant and the embedding model must be available: a full candidate is rebuilt under `projects/legacy/database/`, with gate, integrity, and alias verified before publishing the registry. The cost is a full rebuild of the whole corpus; space is needed for the copy and the new index. Historical validations need a new validation.

The original registry is saved byte-for-byte in `projects/projects.v1.backup.json` when present. The checkpoint is `projects/.legacy-migration.json`: re-run the same command after an interruption; if a promoted candidate remains with an incomplete alias, use `--repair`. Changed hashes or foreign namespaces block resume and require diagnosis. After publication a repeat does not rebuild. To undo offline, restore the saved registry and use the previous code, keeping original paths; do not delete the originals. If the registry did not exist before, restore requires removing only the new one with processes stopped.

In Docker, after stopping the app service, use `docker compose --profile cpu run --rm app-cpu python -m scripts.migrate_project_layout`. Keep historical volumes and any binds until verification; active data then lives in `vibecraft_projects:/app/projects`, including `/app/projects/legacy`.

Integrated Codex/Cursor stay disabled until read isolation is verified; prompt export and external MCP remain available even without an installed binary. SDK: safe Read and safe directory scans are usable; subtree scans with secrets/links and root scans with `.git` are denied. The local runner applies pruning of forbidden paths.

## Pipeline and agents

From [`/pipeline`](http://127.0.0.1:8000/pipeline) you go from interview to Canvas, to Spec with Gherkin scenarios, to validation and archival. The **development type** is a subfolder of the project’s `code/`: the dropdown lists existing ones and **Add** creates a new one (single-component name, letters, digits, `-` and `_`). Canvas dry-run shows the sources that would be used without calling the model. Propose and agent share a list of **open points**: their description is declared by the model, not automatically verified on the merits.

| Runner | Mode | Context access |
|---|---|---|
| Claude Code (`claude`) | suggest, oneshot, agentic | three local MCP tools |
| Ollama (`local`) | suggest, oneshot, agentic | local read and search; writes confined in agentic |
| Codex CLI (`codex`) | export prompt | integrated disabled: read isolation not verified |
| Cursor CLI (`cursor`) | export prompt | integrated disabled: read isolation not verified |

The console distinguishes installed runners, available launch, and prompt export. Claude Code and related provider access must be set up on the server; `local` uses Ollama. Codex/Cursor offer prompt export and external MCP, with integrated execution disabled. Claude and external clients may send context to their own provider.

**Agentic starts only with a passed validation of the current contract**: Canvas, Spec, and decisions are frozen in the record and re-checked by the server before start. Suggest and oneshot remain available even when the gate blocks agentic. Canvas, Propose, and agent context distinguish retrieval failures from empty results: an operational failure returns an error and does not start generation. Accepting an open point keeps it unresolved; the shared API key does not certify the identity of who decides (`origin_verified: false`).

Details and limits: [agent runner](rag/README.md#runner-dellagente-claude-ollama-codex-cursor) and [pipeline gate](rag/adr/PIPELINE_GATE.md).

## Requirements, without sugarcoating

**The default setup downloads about 11 GB for embedding and LLM.** Docling models for PDF import need extra space:

| | |
|---|---|
| `bge-m3` (embedding) | 4.3 GB, loaded on the first operation that needs it |
| `qwen3.5:9b` (local LLM) | 6.6 GB, via Ollama |
| Recommended disk space | ~20 GB |

**An NVIDIA GPU changes a lot.** Measured on an RTX 3070 Ti against the CPU of the same machine:

| | GPU | CPU |
|---|---|---|
| Embedding | 46 chunks/s | **1 chunk/s (45× slower)** |
| Full indexing (sample corpus, 612 items) | ~13 s | **~10 min** |

Without a GPU the system **works**, but reindexing becomes an operation to take calmly. Single questions remain usable: query embedding costs about a second, inside the ~30 s the local LLM already needs to answer.

Prerequisites depend on how you install it:

- **Via Docker** — Docker with Compose. Python and Qdrant are in the stack; Ollama too in the `cpu` and `gpu` profiles.
- **Native** — **Python 3.14**, [uv](https://docs.astral.sh/uv/), **Docker** (for Qdrant only), and **[Ollama](https://ollama.com)**.

## Quick start — Docker (recommended)

One stack: application, Qdrant, and Ollama. The commands below use the `cpu` profile; variants are noted under them. Run them from the repository root.

```bash
git clone https://github.com/Silver1V8/VibeCraft.git
cd VibeCraft

# 0. Generate the API key. In Docker it is required: the browser does not reach the server
#    as 127.0.0.1, so authentication cannot be bypassed — and without a key
#    configured ON THE SERVER no value could satisfy it.
#    compose reads this file on its own; without it, it refuses to start and tells you why.
docker run --rm python:3.14-slim python -c "import secrets; print('VIBECRAFT_API_KEY=' + secrets.token_urlsafe(32))" > .env

# 1. Support services
docker compose --profile cpu up -d qdrant ollama

# 2. The LLM model (6.6 GB, once)
docker compose exec ollama ollama pull qwen3.5:9b

# 3. Start the console: it works even without an index.
docker compose --profile cpu up -d

# 4. Optional: index the baseline included in the legacy project.
# The first indexing downloads bge-m3 (4.3 GB).
docker compose --profile cpu run --rm app-cpu python index.py
```

Then open **http://127.0.0.1:8000**.

Step 0 creates `.env`: if the file already exists, keep its contents and add only `VIBECRAFT_API_KEY`, without overwriting it. The command uses Python in a container, so it does not require Python on the host.

| Profile | Support services | Application service |
|---|---|---|
| `cpu` | `qdrant ollama` | `app-cpu` |
| `gpu` | `qdrant ollama-gpu` | `app-gpu` |
| `host-ollama` | `qdrant` | `app-host-ollama` |

For **GPU**, replace `cpu` with `gpu`, `ollama` with `ollama-gpu` in service names, and `app-cpu` with `app-gpu`. The download becomes `docker compose exec ollama-gpu ollama pull qwen3.5:9b`. NVIDIA Container Toolkit must be configured for Docker.

For **Ollama on the host**, use `--profile host-ollama`, start only `qdrant` at step 1, run `ollama pull qwen3.5:9b` on the host, and index with `app-host-ollama`. Ollama must be reachable from the container via `host.docker.internal:11434`.

**Indexing and startup are independent.** After start you can create a project, import from Intake, and start indexing from the console. `run --rm` runs the CLI in a temporary container with the same volumes; for a new project add `--project <id>`. The console shell does not require an index; retrieval and corpus-based generation do.

**Why three profiles.** Docker on macOS does not expose Metal: a 9B model inside a container runs on CPU. There the sensible path is to keep **native Ollama** on the host and use `--profile host-ollama`, which starts everything else and points at your Ollama.

Model weights **do not live in the image**: they live in volumes, so they download once and survive upgrades.

**The console asks for the key, once.** On first load the console notices requests are rejected, asks for the `VIBECRAFT_API_KEY` — the one generated at step 0 — and keeps it in this browser. It is never written into the page: the page is served without authentication, so putting it there would give it to anyone who reaches it.

With a native install nothing changes: from `127.0.0.1` nothing is asked.

> ⚠️ **Do not point the Docker stack at a Qdrant you already use for a native install.**
> The two installs have distinct local indexes, and each treats the other’s collections as “orphans”. The stack above uses its own Qdrant with its own volume, so the problem does not arise: it arises only if you set `QDRANT_URL` by hand toward a shared instance.

## Quick start — native install

```bash
git clone https://github.com/Silver1V8/VibeCraft.git
cd VibeCraft

# 1. Compose config: on a fresh checkout create .env with a key.
#    If .env exists, add the variable without overwriting the file.
python -c "import secrets; print('VIBECRAFT_API_KEY=' + secrets.token_urlsafe(32))" > .env

# 2. Qdrant (vector store), on 127.0.0.1:6333
docker compose up -d qdrant

# 3. The local LLM model (6.6 GB — the longest download)
ollama pull qwen3.5:9b

# 4. Python dependencies
cd rag
uv sync --frozen

# 5. Start the console; create/select the project and import from Intake.
uv run python server.py       # or: scripts/run_server.sh

# In another terminal, from rag/: optional legacy baseline.
uv run python index.py
# Project created in the console: uv run python index.py --project <id>
```

Then open **http://127.0.0.1:8000**.

The key in the root `.env` is for Compose interpolation, even when starting only Qdrant. The native backend reads `rag/.env.local` instead; from loopback it does not require the key.

If something does not start, **ask preflight instead of guessing**: it checks Python version, Qdrant, Ollama and its model, disk space, GPU, LibreOffice (DOC/PPT), and port — and for each problem prints the remedy.

```bash
# From the rag/ directory
uv run python scripts/doctor.py
```

**On which machines `uv sync` succeeds.** `torch` is the only platform-sensitive dependency: where a CUDA build exists it is taken from the official PyTorch index, elsewhere from PyPI (`[tool.uv.sources]` in [rag/pyproject.toml](rag/pyproject.toml), with a platform marker). Verified with `uv sync --frozen --dry-run --python-platform <p>`:

| Platform | `uv sync` | torch |
|---|---|---|
| Linux x86-64 | ✅ | `2.13.0+cu126` |
| Linux ARM64 | ✅ | `2.13.0+cu126` |
| Windows x86-64 | ✅ | `2.13.0+cu126` |
| macOS Apple Silicon (macOS 14+) | ✅ | `2.13.0` (PyPI) |
| macOS Intel | ❌ | PyTorch no longer publishes x86-64 wheels for macOS |
| Windows ARM64 | ❌ | no upstream `win_arm64` wheel |

The two red rows are **upstream limits, not of this repository**: for those platforms PyTorch publishes no wheel, and no configuration here creates them. The available path there is Docker (`cpu` target, multi-arch).

A machine **without an NVIDIA GPU** on Linux or Windows x86-64 syncs normally: the CUDA build installs and runs on CPU (`torch.cuda.is_available()` → `False`). It costs ~4 GB of download you will not use — if that hurts, the Dockerfile `cpu` target avoids them.

**You do not need to procure documents to try it:** the repository includes in `templates/docs/` a [cross-project governance baseline](templates/docs/README.en.md), ready to index (see above how it enters the initial project).

In a public clone `templates/code/` contains only placeholders: host-project code is not distributed. A local checkout may already contain it. Features that live on code (Semantic Map, Impact Ripple, implementing code inside answers) therefore stay off until you import code into the selected project.

## Ready image

Releases publish an image on GHCR so you do not need to build it:

```bash
docker pull ghcr.io/silver1v8/vibecraft:latest
```

It is the **CPU** target, `linux/amd64`, usable without a GPU. Anyone with an NVIDIA GPU — or running on Apple Silicon — builds locally, where it is fast and native:

```bash
docker build --target gpu -t vibecraft:gpu .   # NVIDIA
docker build --target cpu -t vibecraft:cpu .   # Apple Silicon, native arm64 build
```

## Updating without losing the index

Indexes live in persistent data: `<project-root>/database/` for all, including `projects/legacy/database/`. `rag/database/` is only the historical source. Compose keeps `vibecraft_projects`, `vibecraft_index`, and `qdrant_storage`; updating the code does not move data. Also keep external roots and their mounts.

```bash
# Docker — volumes (index, model weights, Qdrant) survive
git pull && docker compose --profile cpu build && docker compose --profile cpu up -d

# Native
git pull && cd rag && uv sync --frozen
```

After the update, **ask the system whether the index is still valid** instead of reindexing out of habit:

```bash
# From the rag/ directory
uv run python index.py --index-status
uv run python index.py --check-integrity
```

Three cases, in cost order:

| What changed | What is needed |
|---|---|
| Sources of any project | `index.py --project <id> --incremental` — no-op if unchanged; otherwise copy-on-write delta (see below). Without the flag it selects registered `legacy` |
| The **embedding model** (`rag_config.yaml`) | **Full rebuild** required: old vectors are not comparable with new ones. The manifest records the model used, so the difference is detectable and not silent |
| The **artifact format** | JSON, ColBERT in per-document NPY, dense/code in NPZ. A versioned ColBERT NPZ needs the migration below before a non-empty delta; the old flat layout needs a new build to move to NPY. Pickle-only indexes need a rebuild |

For a **versioned** index that still uses `colbert.npz`, from `rag/`:

```bash
uv run python index.py --check-integrity
uv run python index.py --migrate-colbert-npy
uv run python index.py --check-integrity
```

In Docker use the same arguments with `docker compose --profile cpu run --rm app-cpu python index.py` from the root. Conversion verifies vector equality without recomputing embeddings, publishes a new version, and keeps Qdrant. It does not repair pre-existing misalignment: if the check reports extra or missing points, diagnose the difference first. Indexes already on NPY do not need this conversion.

To return to a kept version, from `rag/`:

```bash
uv run python index.py --rollback          # to the previous version
# For a precise version: uv run python index.py --rollback VERSION_NAME
```

Kept versions are 5 by default (`VIBECRAFT_INDEX_KEEP`).

Rollback is refused if the target Qdrant collection is missing. Old historical indexes with mutable deltas shared the origin build’s collection: their rollback did not rewind points modified later. Migration rebuilds the index in the ordinary profile, with a distinct collection per candidate.

In all projects a non-empty delta, copy-on-write or rebuild, goes through the eval gate before promotion. The golden set is `<project-root>/eval/golden.yaml`; if missing, promotion may pass as unevaluated. A metric under threshold blocks promotion if the gate is configured as blocking; an evaluation error follows the gate configuration. This gate is distinct from the one that authorizes agentic start.

## Scalability: results and limits

The following measurements are from **21 September 2026, legacy path**. ColBERT is read on demand and legacy deltas reuse unchanged document files. The delta for new projects is copy-on-write: a dedicated new collection receives unchanged parent points and only changed sources are re-embedded. If the parent is not reusable (embedding model changed, collection or artifacts missing or not attested by the manifest, `VIBECRAFT_DELTA_MODE=rebuild`) it falls back to a full rebuild and the reason stays in `fallback_reason`. These curves, measured on the legacy path, do not describe its cost. Graph, metadata, and dense/code vectors keep global costs: the corpus does not become unbounded and overall delta cost does not depend only on modified files.

- A full CPU trial, 32 documents / 64 chunks, reduced sampled RSS peak from **6.436 to 3.152 GiB**. It is one trial per variant; encoding format and grouping change together, so it is not a guarantee for every corpus.
- Delta curves include **150 trials per version**, with document, code, and mixed corpora. With 100 small documents all modified, median until snapshot ready goes from **15.934 to 58.099 s**: less RAM does not mean more speed in every case. Limited batching was studied but not yet implemented.
- No universal volume or sharding thresholds were fixed. ColBERT remains local; the Qdrant multi-vector backend was not introduced.

Methods, curves, and limits: [scalability evidence](rag/eval/results/README.en.md#sidecar-scalability--21-september-2026) and [benchmark instructions](rag/README.md#delta-reale-isolato).

## Configuration

Main environment variables are documented in [`rag/.env.example`](rag/.env.example). To customize the native backend:

```bash
cp rag/.env.example rag/.env.local
```

`rag/.env.local` is gitignored and loaded automatically at startup.

LLM provider and model are chosen in [`rag/rag_config.yaml`](rag/rag_config.yaml), also **per pipeline step**: for example you can generate the canvas with Claude and keep everything else on local Ollama.

To import PDF with Docling, from `rag/` download and verify the weights:

```bash
uv run python scripts/docling_models.py
uv run python scripts/docling_models.py --verifica
```

DOC/PPT import requires LibreOffice on the host in a native install; it is already included in the Docker image. XLS/XLSX are read directly, without recalculating formulas. To use host documents and code in Docker, adapt a bind of the full root under `/app/projects/<folder>` and register its manifest; or import files into the selected project via Intake.

## Local MCP

With the HTTP backend running and the project index ready, from `rag/` (set `VIBECRAFT_PROJECT_ID=<id>` in the client for a new project):

```bash
uv run --frozen python -B mcp_server.py
```

For Claude Code on Windows, `rag/scripts/install_mcp.ps1` syncs the environment and registers the server as `vibecraft` (`-Scope user|local|project`, `-BackendUrl`): re-running replaces the previous registration. The backend must be started separately.

It is a **stdio** adapter, started through an MCP client: it waits for messages on stdin and does not open a new port. It exposes only `vibecraft_retrieve`, `vibecraft_code_search`, and `vibecraft_graph_query`, with no writes or agent launch. The default backend is `http://127.0.0.1:8000`; `VIBECRAFT_MCP_BACKEND_URL` accepts only loopback addresses. Any `VIBECRAFT_API_KEY` must be inherited from the client environment. Full configuration and container use: [read-only local MCP](rag/README.md#mcp-locale-di-sola-lettura).

## Security

The default is **bind on `127.0.0.1`**: reachable only from this machine, without authentication. It is a deliberate choice for local use.

**If you change `VIBECRAFT_HOST` to expose the server on the network, also set `VIBECRAFT_API_KEY`.** With a non-loopback bind, features that only make sense locally (native folder picker, scanning an arbitrary filesystem path) are disabled automatically — but the rest of the surface must be protected by you.

The server accepts only requests with a recognized `Host` header (DNS-rebinding defense): `127.0.0.1`, `localhost`, `::1`, the `VIBECRAFT_HOST` address if specific, and the host of `VIBECRAFT_BASE_URL`; others get **400**. If you reach the server with another name (LAN hostname, reverse proxy), add it to **`VIBECRAFT_ALLOWED_HOSTS`**, a comma-separated list (e.g. `VIBECRAFT_ALLOWED_HOSTS=vibecraft.lan,192.168.1.20`). No wildcards (entries with `*` are ignored with a warning): list only names whose DNS you control.

Every response forbids framing (`X-Frame-Options: DENY`, `Content-Security-Policy: frame-ancestors 'none'`, clickjacking defense) and carries `X-Content-Type-Options: nosniff` and `Referrer-Policy: same-origin`: the console **cannot** be embedded in an `<iframe>` of another page, not even an internal dashboard.

Responses also carry a full **Content-Security-Policy**: `script-src 'self'` without `unsafe-inline`/`unsafe-eval` (the browser runs only scripts served from `/static/`), no external sources (`default-src 'self'`). That is why templates in `rag/templates/` contain no `<script>` or inline `onclick=`/`onchange=` handlers: each page’s code lives in `rag/static/pages/<page>.js` and controls declare the action with `data-click`/`data-change`/`data-input`, registered with `registerActions()` (`rag/static/shared.js`); `rag/tests/test_csp.py` checks it. Inline styles remain allowed (`style-src 'unsafe-inline'`) because mermaid, vis, and templates write `style` attributes: Tailwind does not run in the browser; it is precompiled into `/static/tailwind*.css` by [`scripts/build_css.sh`](rag/scripts/build_css.sh). Anyone adding a page or button follows the same schema: an inline handler would be blocked silently. Manuals under `rag/static/manuale/` obey the same constraint: the script is [`rag/static/manuale.js`](rag/static/manuale.js).

The attack surface is mapped route by route in [`rag/SECURITY_SURFACE.md`](rag/SECURITY_SURFACE.md).

## Multi-project evolution verification

The final gate of 5 October 2026 recorded **2,348 tests passed and 20 skips** for Windows file-symlink privileges, with complementary Linux proofs. Lint, Node check, HTTP/Qdrant/browser integration, and Docker persistence were verified. Providers are mocked at the boundaries; Docker smoke uses an existing CPU runtime with the current source mounted. Docker builds from scratch and GitHub Actions were not run: the gate does not certify a newly published image.

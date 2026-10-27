English | [Italiano](README.md)

> **Documentation languages.** Italian is canonical in `README.md`; English is `README.en.md`. The console language preference is separate (IT/EN selector in the UI).

# rag/ — Console Graph-RAG

** Documented Status: `main`, October 25, 2026.**
Multi-project is in `main` from 5 October; delta copy-on-write and GPU embedding
from 12. The manuals on the console are 25. The numbers of a gate remain those of the day
where they were measured. The same state is in [`../README.md`](../README.md).

## Separate projects

A single installation manages projects with separate contexts and snapshots.
The console creates/opens/selects the project by card; templates and Qdrant clients
they remain shared, while root, code, documents, pipeline, and index are separate.
The shell and the registry are available without an index. Heavy resources and snapshots
they load on demand; the cache retains at most two resident snapshots,
maintaining the leases of the requests already in progress. Startup and reading do not fix
aliases neither perform GC: writer operations handle maintenance.

```text
<VIBECRAFT_PROJECTS_DIR>/        # default <installazione>/projects
  projects.json                # registry atomico e protetto da lock
  <id>/
    project.yaml               # schema_version, id, name, settings opzionali
    code/
    docs/
    changes/
    database/
      CURRENT
      versions/
      staging/
      pipeline/
      eval/
      reindex_jobs.jsonl
```

The display name does not construct paths; the ID is stable. `project.yaml`
allows overriding validated authority, retrieval, eval, and verification. Root,
collection, secrets, endpoint and embedding model remain under control
of the installation. All projects use the same embedding model.

### Identity in APIs, CLI, and MCP

| Operation | Contract |
|---|---|
| List and status | `GET /api/projects`, `GET /api/projects/<id>` |
| Creation | `POST /api/projects`, JSON `{"name":"Nome progetto"}` |
| Opening | `POST /api/projects/register`, JSON `{"root":"percorso-assoluto"}` |
| Project API | Header `X-VibeCraft-Project: <id>` on `/ask` and on the data APIs |
| Navigation |`?project=<id>`, selection in sessionStorage per tab |
| CLI index | `index.py --project <id>` |
| External MCP | `VIBECRAFT_PROJECT_ID=<id>`, captured at the start of the session |

Requests without headers use **only** the registered project `legacy`;
never the first available or the last chosen in the browser. Malformed header: 422;
Unknown ID: 404; selection absent without legacy: 409 `project_required`;
index missing: 409 `project_not_indexed`; storage or resource failures: 503.
Auth, Host guard, CSP, and cross-site controls remain valid.

Index metadata: `not_indexed`, `ready`, `indexing`, `error`, plus `stale`
when calculable. `/api/health/live` measures the process, `/api/health` the
selected project and the dependencies, `/api/health/deps` only Qdrant/Ollama
(the indicator in the shell bar, every 30 s). Creating a project does not index it.

The pipeline keeps a draft in the browser for each project and feature: interview,
input not sent, editor, scope and current step. After refresh or reopening
first upload the files to the server and it suggests 'Restore local draft' or
"Discard draft and use server file." The restore is explicit, it does not write to the server and does not recover
authorizations, validations or executions of the agent. The interface shows
the last local save and reports browser storage unavailable or corrupted.
Drafts are not synchronized between devices and are lost when site data is deleted.
As long as a draft awaits selection, chat and editor are in read-only mode and the field
the interview says it; the type of development remains selectable and the restoration it
replaces only if the draft had one.

The development type is a real subfolder of `code/` of the project
(`GET /api/pipeline/dev-types`). **Add** it to the creation with `POST /api/pipeline/dev-types`,
JSON `{"name":"..."}`: a single component `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`, names
Windows reserved denied, idempotent case-insensitive. Pipeline and
Intake imports use the same rule (`core/projects.py`).

From `rag/`, with the ID obtained from the console or from `GET /api/projects`:

```bash
uv run python index.py --project <id>
uv run python index.py --project <id> --index-status
uv run python index.py --project <id> --check-integrity
uv run python index.py --project <id> --incremental
uv run python index.py --project <id> --rollback [VERSIONE]
```

`[VERSIONE]` indicates an optional argument, it should not be typed literally.
The new collections use aliases `vibecraft_<id>` and physical names
`vibecraft_<id>__<version>`. The **non-empty delta of a new project is
copy-on-write**: a new dedicated collection receives the unchanged points from the parent and
only the changed sources are re-embedded; if the parent is not reusable, it falls back on
full rebuild (`fallback_reason`). A no-op does not load embedding nor rewrite the index.
Each candidate keeps their own collection and the rollback reactivates it
version. The golden set is `<root>/eval/golden.yaml`, the historian lives in
`database/eval/`; a missing golden can let the gate pass as not evaluated.
The CLIs `eval.run` and `eval.run_multihop` return exit 3 for a missing or empty suite;
The night check reports it as not evaluated.
HTTP jobs are serialized in the process to contain RAM/VRAM, with writer lock
by design even among processes. Requests, callbacks, and streams retain the target
original: selecting B does not move a job from A.

### Legacy, Docker and limits

The initial project uses `<VIBECRAFT_PROJECTS_DIR>/legacy/`, with manifest and layout
ordinary. The first writer launch copies and checks in that root `docs/` and `code/` at
installation root if they contain files, otherwise `templates/docs/` and
`templates/code/` (clean local clone; the Docker image brings them to `/app/docs` and
`/app/code`), without models, Qdrant or build. The other new projects remain empty. The reader does not
Initialize the register. A register that is already empty remains empty.
The index scans only docs/code of the selected project, even for ID `legacy`.

With historical data `project_migration_required` appears: stop server and other writers,
then from `rag/` execute `uv run --frozen python -m scripts.migrate_project_layout`.
The copy preserves the originals; an existing index requires Qdrant and embedding,
and a full rebuild verified before publication. Pipeline and staging are being
copied; historical validations require new validation. Original record:
`projects/projects.v1.backup.json` when present; checkpoint:
`projects/.legacy-migration.json`. Repeat the same command to resume;
`--repair` only repairs the candidate immediately after CURRENT/alias interruption.
Costs and restoration: [migrazione](../README.md#migrare-uninstallazione-esistente).

The examples without `--project` select only the registered `legacy`.
His index is immutable like the others: non-empty delta with complete candidate,
gate, separate alias and rollback. The paragraphs on flat and mutable delta formats
they describe the historical indexes preserved for diagnostics.

With local bind, Apri can register an external VibeCraft root; with remote bind
accept only root without links strictly under `VIBECRAFT_PROJECTS_DIR`, before
read the manifest. Docker mounts `vibecraft_projects:/app/projects`: to open
a host project mounts the root under `/app/projects/<cartella>`. The native dialog
It is available only with local bind. Backup: registry, registered roots and related
Qdrant collection, with write operations paused. Model weights shared in the installation.

The reader requires `VIBECRAFT_ROLE=reader`, `VIBECRAFT_INDEX_MODE=immutable` and key
API also on loopback; registry prepared by the writer and mutant APIs disabled.
To create/import and for Docker details: [istruzioni principali](../README.md#progetti-separati).

In-app launch available for Claude SDK and local Ollama. Codex/Cursor integrated
are disabled with `native_read_isolation_unverified`; export prompt and MCP
external remain available. Supported: deletion (destroy for managed roots;
unregister for external roots), display-name rename only (id and path stay fixed), and
project-list filter by name or id (`?q=`). Still out of scope: id move/migration,
cross-project corpus search, per-project ACL, or different embeddings.

Indexing, retrieval, pipeline, and import are exposed by FastAPI.
Entrypoint: `server.py`, `index.py`, `mcp_server.py`; architectural decisions in
[adr/](adr/README.md). The outdated benchmarks below remain measures of the legacy path.

## LLM: a single layer, interchangeable providers per step

All generative calls (drift, canvas, propose, validate, explore, canvas)
review) they go from [core/llm.py](core/llm.py): `generate(prompt, purpose=...)`
(synchronous) and `agenerate(...)` (async). Provider and model are resolved from
[rag_config.yaml](rag_config.yaml): by default `llm_settings.active_provider` +
`llm_settings.models`, with optional override **for each individual step** via
`llm_settings.purposes` (commented example in the file). This way, for example, one can
generate the canvas with Claude and keep the drift on local Ollama.

Available providers: `ollama` (local endpoint `/api/generate`) and `anthropic`
(Official SDK — requires `uv add anthropic` and the environment variable
`ANTHROPIC_API_KEY`; if they are missing the error is explicit). Network/timeout errors
they raise `LLMError` with a readable message: the callers remain tolerant as
first (the check drift puts the message in the report, the archive skips the review
with a warning, the pipeline steps return the message as text via
`pipeline.generate_tolerant`). In the tests, a fake provider is injected with
`llm.register_provider` — no HTTP (see [tests/test_llm.py](tests/test_llm.py)).

Even `POST /ask` (summary of the RAG response) goes through this layer, with purpose
`ask`: the prompt (historical system + context + question + one closing line
which asks to respond without repeating context and instructions) is built
from the pure function `retrieval.build_ask_prompt` and the call is
`llm.agenerate(..., purpose="ask")` — same guardrails `think`/`options.num_ctx`
of the other steps, only one client to maintain. On `LLMError` the route responds
`502` with the error message: never an error text inside `answer` with
`status: "success"`. The base URL of Ollama is unique for all the code
(`VIBECRAFT_OLLAMA_URL`, default `http://127.0.0.1:11434`, core/config.py).

**The closing line prevents the prompt echo.** Instructions and context travel
in a single user turn: on a long and repetitive context (for example two parts
of the same section in window) qwen3.5:9b was losing the boundary between task and
document and returned as `answer` the prompt itself, copied from the first line
until filling `num_ctx`. On the question «last place» the prompt was copied
in 16 variants out of 21 (each without one of the context blocks); with the line of
closure, at 0 out of 22. It is the same result that is obtained by moving the instructions into
Ollama field `system`, but without touching the provider layer.

**Abstention is machine-readable** (`status: "abstained"`). The model is
already abstains correctly in free prose when the retrieved context does not
contains the answer — verified live — but before the payload remained
`status: "success"` with the sources listed in `qdrant_scores`, identical in
shapes a true answer: a client had no way to distinguish 'has
"answered" from "abstained" without performing NLP on the prose. `[REGOLA-ASTENSIONE]`
in the prompt (`retrieval.build_ask_prompt`) it requires the model to place before the
token `retrieval.ASK_ABSTENTION_MARKER` (`[ASTENSIONE]`) if and only if
the context is not enough; `ask_rag` reads it, removes it — the human user does not
sees ever — and sets `status: "abstained"`. Distinct from `no_results` /
`no_graph_nodes`: there the retrieval finds nothing, here it finds something and it is the
in short, to say that he/she does not answer.

**Deterministic M2 router in front of `/ask`.** Before retrieval, the function
pure `core.router.route_question` (regex, zero LLM, zero graph) classifies the
question: the unequivocal **structural** formulations (enumerations of
documents/entities, `quali relazioni ha X`, `impatto se modifico Y`, nodes
adjacent — the cases solved by the graph in the M1 report) go to strategy `graph` and
they are responses directly from `graph_ops.graph_query` (offload in threadpool),
**without retrieval or LLM call**: the answer has `status: "graph_answer"` with
`graph_result` correct. Everything else (including the multihops) remains on strategy
`hybrid`, the retrieval + LLM synthesis path described above. The router is
**conservative for construction** — in doubt `hybrid`, zero false constraint
positive on the classic golden set — and the choice ends on the court
`retrieval_strategy` of the structured log M3.

**The code is a source of `/ask`, not just the documents.** Semantic search
query Qdrant, where **only the documents** are: the code lives in the graph (nodes
symbol) and its dense vectors in the sidecar `code.npz`. `/ask` brings it into the context
through **two complementary roads**, and what it injects is exposed in the field
`implementing_code` of the answer (with `source` for source branch):

1. **Direct semantic search** (`retrieval.search_code_symbols`): cosine between the
dense vector of the **question** and those of the symbols, calculated in memory (~25 ms
on 4,000 symbols, no additional points in Qdrant, no indexing cost).
It is the only path that the code finds that **no specification describes** — a DTO with
the list of required fields, a helper, a query. A ceiling for **files**
(`code_search_max_per_file`) prevents a single self-generated file (the proxy
WCF `Reference.cs`) to occupy all positions with variants of the same row.
2. **Bridge `IMPLEMENTS`** (`retrieval.collect_implementing_code`): from the arches
incoming to the recovered nodes goes back to the **implementation of what has been
recovered**, so the LLM compares the spec with the actual code ("what is missing in the
form?)

The two results are deduplicated by symbol with priority given to the semantic branch and capped
overall (`code_context_total_snippets`). The rule `[FONTE-CODICE]` of
system prompt declares the block «EXISTING CODE» **legitimate source**: none,
`[REGOLA-DIZIONARIO-RIGIDO]` considered the model to treat any invention as such
field name missing from the documents and replying "Not specified" with the class that
he declares those fields in front of the eyes. If the document retrieval finds nothing but
the code yes, the question **still receives an answer** (before: "No document"
relevant). All thresholds are in `rag_config.yaml → retrieval.*`;
`code_search_max_snippets: 0` disables the direct branch.

**Daily guard budget on Claude, automatic fallback on Ollama.**
`core/llm.py`has an Anthropic spending counter per UTC day, powered by the
same estimated cost already logged for observability (`llm_settings.pricing`): none
a price set for the model nothing is counted and the guard remains inert. If
`llm_settings.budget.daily_usd` is overtaken, `resolve(purpose)` silently swerves
(provider, model) on `budget.fallback_provider` (default `ollama`) — provided that that
provider has a model in `llm_settings.models`, otherwise stay on anthropic for
do not turn a cost problem into a generation failure. The meter
optionally persists to file (`budget.spend_file`, otherwise only in-memory,
reset at reboot) and never fails a call: any internal error of the
guard (malformed config, unreadable file) is logged and you stay on the provider
resolved. `spend_today_usd()` presents the current expenditure for diagnostics.
In the same meter goes the cost of Claude agent runs
(`POST /api/pipeline/agent/run`, runner `claude`): a fine run `agent_bridge` records the
`total_cost_usd` reported by the SDK (also for failed runs; nothing if the stream is
stops before the result), without the need for `pricing`. Not having a provider
site to downgrade, with active budget and threshold reached the new runs `claude` (and the
automatic retries after a failed check) are **rejected** with 429 and
`Retry-After` until midnight UTC; the runners `local`, `codex` and `cursor` are not
touched by the budget. The threshold is **soft**: the cost is known only at the end of the run, so the
Runs already admitted or in progress can pass it and only block the following ones.

**Latency breakdown in response (M3/F3).** Both the branch `hybrid` and the branch
`graph` return, in addition to `request_id` and `index_version`, an object
`latency: {retrieval_ms, generation_ms, total_ms}` (in the graph branch
`retrieval_ms` is the latency of `graph_query` and `generation_ms` is 0): the same
values already present in the structured end-of-request log, also exposed in the JSON
so the clients (and `scripts/bench.py`) measure the breakdown without parsing the logs.

**Response cache on `/ask`, isolated by project and version.**
[core/ask_cache.py](core/ask_cache.py) is a thread-safe in-process LRU that resets the
cost (embedding + LLM generation) of repeated questions — the majority on one
governance console. The key (`make_key`) includes project, version, strategy, top-k, depth
BFS, question hash and fingerprint of authority/retrieval settings: the question is normalized (trim,
lowercase, collapsed spaces) before the hash, so two identical formulations except
of spacing share the item. **Invalidation does not exist as an operation**:
Project ID, `index_version` and settings are part of the key: projects
with the same query/version they do not share answers; after a re-indexing or a
rollback (`database/CURRENT` changes in both cases) the entries of the version
previous ones are no longer consulted and the LRU evicts them. The state resides on
`app.state.ask_cache` (not in a module global, so the tests remain isolated
without global fixtures), created lazy with ceiling from env `VIBECRAFT_ASK_CACHE_SIZE`
(default 256 voices, `0` disables the cache). Cached payloads are treated as
immutable: the route builds the response with a copy (`{**cached, ...}`), never
changing the object in cache.

## Automatic reindexing: the index never ages

Two mechanisms keep the index aligned with the codebase without manual intervention:

**1. Incremental reindexing on webhook (during the day).**
`POST /api/reindex` launches an incremental reindex in the background and responds
immediately `202` with a `job_id`; `GET /api/reindex/{job_id}` reports its status
(`queued`/`running`/`completed`/`failed`) with the result or the error. At the end job
once the server has started, it updates the graph and chunks in memory and opens the ColBERT reader
on request via `reload_index_state` (api/deps.py). `GET /api/reindex` (without id) lists the
latest `N` job (`?limit=`, default 20, most recent first), useful for debug and UI.
Auth: `X-API-Key` like all the `/api/*`.

The job history is **persistent across restarts**: every state transition
(`created`/`completed`/`failed`) appends a JSON line to the append-only journal
`database/reindex_jobs.jsonl`. At boot `ReindexManager` rebuilds the history
from the journal (the last line for `job_id` wins); the remaining jobs `running` (crash at
half) are marked `interrupted`. Even a `reload_status: pending` becomes
`interrupted` on restart: the reload process does not survive the crash, while
The outcome of an already completed build remains saved. The journal distinguishes duration
of the build, reload duration and time until the snapshot is ready; `completed` from
it only does not certify that the server is already serving the new version.
The file self-compresses when it exceeds ~1MB
(rewritten keeping only the last state of each job) and **should not be committed** (it is in
`.gitignore`).

The manager uses a **queue with coalescing** (`ReindexManager`, api/reindex.py):
at most one job running + at most **one pending**. If one arrives a
request while a reindex is in progress **is no longer rejected with `409`**: it is
queued in a single pending slot and the response is `202` with
`{"job_id": <id del pending>, "queued": true}`. The `changed_paths` of requests
queued are **merged** (union of sets; a "complete" request with
`changed_paths=None` absorbs everything → incremental on everything). At the end of the job (success
or failure) the pending automatically starts. Thus two close GitLab pushes
they are no longer lost — the second event merges into pending instead of disappearing.

**Only one writer by design.** Every writing of the index artifacts
from the server it goes through the manager's queue, which distinguishes two types of jobs (`kind` in the
`to_dict`/journal): `incremental` (delta) and `full` (`build_graph_and_index`,
complete reconstruction, without `changed_paths`). A body `{"full": true}` on
`POST /api/reindex` queues a full rebuild; also the archive (Step 5,
`/api/pipeline/archive[/stream]`) no longer reconstructs inline but queues a job
full and returns the `job_id` to the client (in the stream the final event is
`{"type": "reindex_queued", "job_id": ...}`). Coalescing between types: a full
**subsumes** any incremental — if the pending is incremental and a full arrives,
the pending becomes full; if the pending is already full, every subsequent request goes there
merges without changing it. The CLI (`python index.py`), on the other hand, writes the artifacts
directly, out of the queue: with the server on do you prefer `POST /api/reindex`
(if necessary `{"full": true}`), which appends instead of writing in place.

**Only one writer even cross-process (writer lock).** CLI and server do not
corrupt each other more: every branch that WRITES the artifacts — the CLI commands of
writing (`index.py`: build, `--incremental`, `--archive`, `--rollback`,
`--migrate-colbert-npy`) and jobs
of the ReindexManager — runs for the entire duration under an advisory lock at the level of
operating system on `database/.writer.lock` ([core/writer_lock.py](core/writer_lock.py):
`msvcrt.locking` on Windows, `fcntl.flock` on POSIX). The mutex is the OS lock
on the handle, which the kernel automatically releases upon the death of the process (crash
included): no stale lock to clean up, the file is never deleted. If a
another writer is active the CLI **fails immediately** with a dedicated exit code
(`WriterLockBusyError`, message with holder's pid/timestamp) instead of
write halfway — like a `python index.py` thrown while the server reindexes
it does not produce mixed artifacts.

Set up the GitLab webhook (Settings → Webhooks) on **Push events** and/or
**Merge request events** pointing to `https://<host>/api/reindex`. To expose the
secure webhook set **both** environment variables: `VIBECRAFT_API_KEY`
(header`X-API-Key`, request for every non-local access) and`VIBECRAFT_GITLAB_TOKEN`
(header `X-Gitlab-Token`, the *Secret token* of the GitLab webhook). When
`VIBECRAFT_GITLAB_TOKEN` is set, `POST /api/reindex` requires the correct token
(comparison at constant time with `hmac.compare_digest`) **in addition** to `X-API-Key`;
if it is not set the behavior remains unchanged (only `X-API-Key`). The `<host>` of
webhook must also be allowed in the header `Host` (`VIBECRAFT_ALLOWED_HOSTS` or
`VIBECRAFT_BASE_URL`), otherwise the request receives 400. From the payload
push the modified paths are extracted
(`commits[].added/modified/removed`) and moved on to the delta indexing plan for
limit work to only the changed files; a merge request payload (without list
file) makes a full incremental on`docs/`+`code/`. A ... is also accepted
explicit override `{"paths": ["docs/x.md", ...]}` for manual triggers. The
Extraction logic is in [api/reindex.py](api/reindex.py) (`extract_gitlab_paths`).

**2. Night batch ECONOMIC (integrity check, zero embedding).**
The night script [scripts/nightly_consistency.ps1](scripts/nightly_consistency.ps1)
(POSIX variant `.sh`) executes `index.py --check-integrity`
(`check_index_integrity`, core/indexing.py): **no embedding model,
no construction, execution seconds**. Check that the manifest exists and
to be readable, compare `doc_hashes`/`code_hashes` with the current hashes on
disk (differences ⇒ index **stale**), validates the `artifact_hashes` against the
files in `database/` (missing or different hash ⇒ **corrupted**/mixed artifacts),
compare the keys of the ColBERT sidecar with the `chunk_id` of `chunks.json` (a chunk
without a multivector makes`colbert_maxsim`non-assessable and degrades the ranking in
silence — see `AUDIT.md`, A7) and compare the Qdrant score count with the number
of chunk in the sidecar, also checking that the collection declared by the version
active still exists. The same check is exposed as `GET /api/index/integrity`
(auth `X-API-Key`).

**Divergence `docs/` ↔ git (field `docs_git`).** The `docs/` files are marked
`skip-worktree`, so the differences between the working copy and the committed one are
**invisible to `git status` and `git diff`** — intentional, to not see the material of
domain like "modifications", but it means that the indexed corpus may deviate from
repository without anyone noticing. `observe_docs_git_divergence` compares
the hash of the `ls-tree HEAD` blob with `hash-object` on the working file (bypasses
the git index, which for skip-worktree is stuck at the committed; `hash-object` applies
the same EOL filters, so no false positives on CRLF checkout). It is
**pure observation**, like `qdrant_alias`: it never contributes to `ok`/`problems`,
because a git divergence **is not fixed by reindexing** — reindexing would reread
the same files — and treating it as a problem would trigger an unnecessary full rebuild
every execution. Which corpus is authoritative is a human decision; the check makes it so
only visible. The night scripts always print it, even at OK integrity (it's the
case in which it would remain hidden) and they write an alert.

**Declared instantiation ≠ defect.** The baseline is made to be instantiated on the
place — `docs/README.md` prescribes filling out Section 0 and solving the
`<<PARAMETRO>>`, and `skip-worktree` exists precisely so that that instance does not appear as
"edit". A check that would also indicate that one would no longer be read: the noise
waited buries the rare signal. A document that declares `instantiated_from:` in the
Frontmatter is therefore classified separately — it remains listed and counted, but it is not a
problem, and it does not trigger the night alert. The marker is a human statement with
the same trust model of `authority:`: whoever writes it to mask a divergence
Accidental is lying to its own instrument, not bypassing a check. A file
**disappeared** from the disk cannot declare anything and always remains a divergence; a
malformed frontmatter does not count as a declaration (the ambiguous case is resolved towards
`diverging`, which is the most cautious).

States: `aligned`, `instantiated` (only declared differences), `diverging` (at least one
undeclared — and one is enough for the state to return as such), `unavailable` (git missing,
not a repository, HEAD missing — never an exception).
Based on the report, the script:
- **ok** → exits without doing anything;
- **stale** (only changed sources) → `POST /api/reindex` to the local server
(`VIBECRAFT_SERVER_URL`, default `http://127.0.0.1:8000`, with `X-API-Key` from
`VIBECRAFT_API_KEY`) this way the delta passes from the tail of the ReindexManager; if the
server is off, fallback to `index.py --incremental`;
- **corrupted artifacts or misaligned Qdrant** → full rebuild (`index.py`).

**3. Deep weekly batch (anti-drift guardrail).**
The comprehensive comparison incremental graph vs full rebuild (`index.py
`--check-graph`, which re-embeds everything in memory, is downgraded to weekly:
[scripts/weekly_consistency.ps1](scripts/weekly_consistency.ps1) (variant
POSIX `.sh`) executes it and, **only if it finds drift**, triggers a full rebuild that
realigns everything. After the rebuild the server detects the pointer `database/CURRENT`
moved (the promotion of the new blue/green version; for legacy layouts without
CURRENT, the mtime of `graph.json`) and reloads the artifacts on the first request
(`maybe_reload_graph`). The loading runs in a thread of the thread pool (the event loop
continues to serve the other requests) and is serialized by a lock with double-check
of the version: more concurrent requests, or a request and the end-of-job reload,
they produce a single loading.

Scheduling — Windows Task Scheduler:

```powershell
# nightly alle 03:00, weekly la domenica alle 04:00
schtasks /Create /TN "vibecraft-nightly" /SC DAILY  /ST 03:00 `
  /TR "pwsh -File C:\path\to\rag\scripts\nightly_consistency.ps1"
schtasks /Create /TN "vibecraft-weekly"  /SC WEEKLY /D SUN /ST 04:00 `
  /TR "pwsh -File C:\path\to\rag\scripts\weekly_consistency.ps1"
```

cron:

```cron
0 3 * * *  /path/to/rag/scripts/nightly_consistency.sh >> /var/log/vibecraft-nightly.log 2>&1
0 4 * * 0  /path/to/rag/scripts/weekly_consistency.sh  >> /var/log/vibecraft-weekly.log  2>&1
```

## Intake & Import: controlled entry of knowledge

The page **`/intake`** ([templates/intake.unified.html](templates/intake.unified.html),
route in [api/routes_pages.py](api/routes_pages.py)) is the only new entrance
knowledge — documents and projects — in the system. The non-negotiable principle is the
**staging with review**: nothing goes into `docs/` or the index without approval
explicit from the page. The cycle lives in [core/intake.py](core/intake.py) and in the
route [api/routes_intake.py](api/routes_intake.py) (`/api/intake/*`, auth `X-API-Key`
like the rest), and uses the same writer lock as indexing. The approval of
documents save the files; the **Update Index** button starts the indexing after the review.

**Five streams, a single staging** (`database/staging/`, with journal append-only
`intake.jsonl`):

- **Generate with Ollama** (`POST /api/intake/generate`, [core/doc_generation.py](core/doc_generation.py)):
up to `intake.generation_max_files` markdown documents grounded in the Graph RAG
(hybrid_search) and in the Canvas review lessons; each file is validated
(parse + chunking) before entering staging.
- **Import documents** (`POST /api/intake/docs`, [core/intake_convert.py](core/intake_convert.py)):
upload multipart converted to Markdown **locally** and placed in staging next to it
to the original. The engine follows an explicit matrix, measured on the installed version:

| format | engine |
  |---|---|
| `.md` | native (decoding only) |
| `.pdf` | **Docling** 2.126.0 if `intake.docling.enabled`, otherwise MarkItDown |
| `.xlsx`, `.xls` | direct reading of the original: **openpyxl** 3.1.5, **xlrd** 2.0.2 ([core/intake_excel.py](core/intake_excel.py)) |
| DOCX, PPTX, HTML/HTM, TXT, CSV, JSON, XML, EPUB, MSG | MarkItDown 0.1.7 |
| DOC, PPT | **LibreOffice** headless → DOCX, PPTX, then the line of the modern format |

The choice comes from a comparison on the same inputs, after the real cleaner, with expectations
written before (`archive/eval-results/verifica_finale_20260910/`). Spreadsheets
(`archive/eval-results/excel_diretto_20260911/RESOCONTO.md`): MarkItDown goes from pandas, which empties
the cells «NA», «N/A», «null» and writes `7.0` and `NaN`; Docling splits a row into multiple tables
with empty intermediate cells; LibreOffice rounds XLS numbers to 15 digits and converts the
booleans into numbers. Direct reading produces, per sheet, cell ranges with the
original coordinates (an empty column throughout the sheet separates the ranges, a row
empty the blocks: no header or inferred table) and the stored values, without
recalculation nor display format; formats, merged cells, comments, links and text
From a numerical point of view, they are listed per sheet, excluding formulas, drawings, and charts, and have a
warning. No fallback: file unreadable, protected, or over 1,000,000 cells
represent = explicit error. Ambiguous DOCX (better Docling
with Title style, worse with a Heading 1 title): remains MarkItDown. PPTX: MarkItDown
keep the speaker's notes. CSV: Docling fails on `;` latin-1. HTML and EPUB to
equal. DOC and PPT (`intake.libreoffice`): LibreOffice brings a COPY to the modern format,
with a new temporary profile for each conversion (macros off, external links never
updated, no recalculation of formulas, process tree terminated at timeout), then
Decides the row of the modern format; without LibreOffice DOC and PPT they give an error. Never the
LibreOffice internal of Docling (default profile:
measured, download the linked images). In modern formats, LibreOffice does not improve anything
and is not used (`archive/eval-results/libreoffice_20260910/`). An invalid container (DOCX,
PPTX, XLSX, EPUB not ZIP; DOC, XLS, PPT without the expected OLE structure; MSG without OLE signature) is
an error, not a raw byte document; an encrypted OOXML or XLS is 'password protected'.
PDF configuration, that of the final pilot:
`StandardPdfPipeline`, explicit CPU, TableFormer ACCURATE with cell matching, text of the
backend, hierarchy of titles by style, no VLM or remote services. The weights are in
`intake.docling.models_dir`, fixed to known revisions and verified for SHA-256 on first use:
`uv run python scripts/docling_models.py` unloads them, `--verifica` checks them. Only one
PDF with pages without selectable text (scan) goes through the local RapidOCR; a
Never digital PDF. If Docling is not available (dependency, weights) or fails, the PDF goes through
from MarkItDown with a **declared fallback** (`metadata.fallback` and a warning in the
preview), never presented as an equivalent conversion; a scan without Docling is a
error, not an empty document. Engine, version, fallback, warnings and, for PDFs, pages,
pages without text and use of OCR reach the preview; engine, version and any
fallback also in the `intake` field of the frontmatter. The images do not go into `docs/`:
Docling does not export them, and the references to local images of MarkItDown (PPTX, HTML) do
They remove with a notice — the original remains in staging. The whitelist remains ours
(`intake.allowed_formats`); extension and size (`intake.max_upload_mb`) are validated
BEFORE reading the entire body into memory, it is a duplicate (same SHA-256 as a document)
staged or approved) is rejected before conversion. Docling conversions are serial
in the process and they run in the threadpool, never on the event loop; `intake.docling.timeout_seconds`
limits a document (besides, partial result declared as INCOMPLETE).
MarkItDown's output always goes through
[core/intake_clean.py](core/intake_clean.py), which removes the layout furnishings of the
source — headers and footers repeated on every page, page numbers, indexes with
guide dots, base64 images, syllabification and line break for justification. It's cleaning
**deterministic and idempotent**: no content word is lost (on a PDF
institutional still removes 20-60% of the dump). Without it, all that noise ends up
identical in the RAG chunks. The output of Docling, already structured and without headers or footers
page, passes only through `normalize_markdown` (NFC, invisible characters, empty lines): the
furnishing rules would remove lines of content, like an isolated KPI value.
- **Refine with LLM** (`POST /api/intake/staged/{id}/refine`,
[core/intake_refine.py](core/intake_refine.py)): **opt-in** step of the review cycle that
transform the converter dump into a structured spec — sections `##` (the unit of
chunking), tables for field lists, code blocks for XML/XSD — plus a
semantic **frontmatter** deduced from the document (`title`, `document_type`, `domain`,
`tags`), which `approve` merges at the end of the regulatory fields without ever overwriting them. Job
async (pattern S3) because on a long document there are dozens of calls to the model
(~2 min per window on local GPU). Two guardrails against the real risk of this
step, which is to betray the document: it is refined to **windows**
(`intake.refine.window_chars`, well below `num_ctx` — beyond, Ollama cuts off in silence) and
a window whose rewriting falls outside the **length range** is **discarded** at
in favor of the clean text. Too short means that the model has summarized (and a
summary loses requirements); too long that commented or hypothesized instead of
reformat — on a fragmentary source tends to fill in the gaps with conjectures
("inferred", "could refer to") that in a regulatory document are worse than the text
raw. The roof **depends on the shape of the source**: the prose is underneath
`max_output_ratio`, while dense sources (class trees, lists of fields — rows
on average shorter than `dense_line_chars`) are entitled to `max_output_ratio_dense`,
because by becoming tables with a description column they grow by 3-4× without one
word has been invented. The raw markdown remains in staging next to the refined one:
Rerunning the refine always starts from that, never from the rewrite.
- **Review staging** (`GET /api/intake/staged`, `.../preview`, `POST .../approve`,
`POST .../reject`): markdown preview, then **approve** (writes
`docs/<categoria>/<nome_file>` with compliant frontmatter, under writer lock of the
project, without reindex) or **reject** (reason in the journal, files moved
in `staging/rejected/`, never deleted). `approve` **never overwrites** a file
existing in `docs/`, and the composed document must pass parse/chunking BEFORE
any writing. Under writer lock, check again that the document is still in staging
and that the destination is free and creates the file exclusively. You can approve more
documents and then press **Update index** only once: until then the index
stay on the previous version, with the status **to be updated**. If the indexing
fails, the approved files remain in `docs/` for a new attempt. Also `reject` and
the final writing of the refinement goes through the same writer lock, rechecking it
state: a refusal or a refinement arrived late do not affect a document already
approved. Enters in `docs/`
only the `.md` compound; the original remains in `staging/docs/` (or `staging/rejected/`).
Every app publication in `docs/` is a `.md` — the approval of the intake and the historical copy
from the canvas review to the archive —, but the app cannot prevent external manual writings.
The explicit update also takes into account the other changes/removals present
in the project's source code. The PDF still on disk remains a source
distinct even when approving a derived `.md`.
- **Weights of Docling, Docker, and CI**: the weights (layout, TableFormer, RapidOCR, ~540 MB) are not
neither in the repository nor in the image. Locally: `uv run python scripts/docling_models.py`
(download at the fixed revisions and check the SHA-256; `--verifica` check only).
In Docker they go into the index volume: `docker compose --profile cpu run --rm app-cpu`
python scripts/docling_models.py`. The image includes the native OpenCV libraries and
`fonts-liberation`: without fonts, PDFs with non-embedded fonts were rendered differently and
the layout downgraded a title. In CI the job `test` retrieves the weights from a keyed cache
on the hashes of the files that declare revisions and SHA, it rechecks them and runs with
`VIBECRAFT_REQUIRE_DOCLING=1` (without weights the tests fail, they don't jump); the job `docker`
It really converts a PDF, a scan, DOC, PPT, XLSX, and XLS into the constructed image.
- **Import project from path** (`POST /api/intake/project/plan` + `.../apply`,
[core/project_import.py](core/project_import.py)): import of a local project into
`code/<target>` (an existing subfolder of `code/`, e.g. `backend`, `frontend`,
`logicAgent`, or a new one created by the page) with the **plan/apply** pattern.
The plan is a **pure dry-run** (zero writes) that classifies the files into
new/identical/conflicts/excluded (exclusions reused from `CODE_EXCLUDED_DIRS`).
Additive and non-destructive, binding semantics: empty folder → bootstrap
(copy everything that can be copied); populated folder → additive (copy ONLY the new files;
existing files with different content are **conflicts**, reported in the plan and
**never applied**). `apply` makes a zip backup of the target folder, copies only the
new, rejects a **stale** plan (target fingerprint changed after the preview)
and reindexes the code in delta (explicit warning if a full rebuild is needed for the
code-link). **Never an overwrite, never a deletion** of an existing file
in `code/`.

**Project brief** (`POST /api/intake/project/brief`, [core/project_brief.py](core/project_brief.py)):
after a successful import, generate an architectural summary of the project via Ollama
(components, entrypoint, dependencies, symbol map→spec from the arcs `IMPLEMENTS` of
graph, candidate areas for refactoring), **grounded on the real data of the graph** — never
made up. Precondition: an import `applied` for that target/project in the journal
(otherwise 409); graph without symbols → result with warning, never a crash. The brief
enters staging like any other document (`source "brief"`) and goes through the same
review S2: **no direct path to `docs/`**.

The unit of the brief is the **project**, not the target. `target` is a bucket
(`backend`/`frontend`/`logicAgent`) and the import is additive, so `code/backend/` can
host multiple projects side by side (`GD102_WSGDAProtocolloManager` **and**
`GD172_WSProtocollo`): a grounding filtered for only `dev_type` takes the symbols of
everyone, and the roof `_MAX_SIMBOLI_NEL_PROMPT` fills the prompt with the first in order of
`id` — the brief requested for a project describes the other. The field `progetto` of the
request select the folder under `code/<target>/`; **if omitted, the last project is used
imported** into that target, never the "whole bucket". `GET /api/intake/project/imports`
list the imported projects (from the journal) to populate the selection on the page.

In the prompt, the symbols are a **chosen sample, not a truncation**. A real project
he has thousands (`GD172_WSProtocollo`: 4100 symbols in 309 files) and in the context of
qwen3.5:9b there are dozens of them: `simboli[:80]` on an ordered list by path showed only
the initial folders in alphabetical order and, of the 337 endpoints, only those that start
for A. `seleziona_simboli` instead makes **a loop through rows** (a `Reference.cs` generated by
1650 symbols are worth like any other file) and inside each one it first takes what has value
architectural (`_RANGO_KIND`: types and entry points before properties, all else being equal
nature wins the degree in the subgraph), sampling **at a constant step** the bands
homogeneous too long — so all 337 SOAP operations are traversed instead of
stop at A. Next to the sample, the prompt shows the **counts per module, complete**:
I am the only grounding that covers 100% of the project, and the prompt explicitly says to
model that the list of symbols is partial. The prompt ceilings are **in characters**
(`_BUDGET_CHAR_*`), not only in entries: the length of a line depends on the paths of the
project, and with only roof entries the prompt came out to ~48,000 characters (~13,700 tokens) —
barely inside `num_ctx 16384`, with Ollama cutting the excess **from the beginning**, that is
exactly the instructions. Now it stays under ~6,500 tokens, the rest of the window is for the
answer.

The **format rules** in the prompt are instructions for the model, not guarantees: before
validation the output goes through `normalize_generated_markdown`
([core/doc_generation.py](core/doc_generation.py)), which repairs the three recurring ways
the document outline comes out wrong — document wrapped in a `` ```markdown `` fence,
frontmatter opened and **never closed**, frontmatter not loadable as YAML — without
touching the body. Generated frontmatter is transitional material (the conforming one is
recomputed by `approve`), so a broken outline no longer costs the whole document; only
what has no usable body is discarded, with the reason in the journal. In parallel the
indexing parser recognizes frontmatter **only** as a well-formed `---`…`---` block at the
top of the file (`core.chunking.split_frontmatter`, line comparison): an unclosed block
counts as absent and no longer swallows the document body into YAML.

## Retrieval eval: from bench tool to guardrail


## Eval del retrieval: da attrezzo da banco a guardrail

The quality of retrieval is measured on the golden set
([eval/golden_set.yaml](eval/golden_set.yaml)) con [eval/run.py](eval/run.py),
which queries the real server (`GET /api/retrieve`, thus reusing the model already
loaded) and saves each run in`eval/results/`. The guardrail mode gives exit code 1 if the
recall **alla `k` dell'eval-gate** scende sotto la soglia dell'eval-gate — oggi
`recall@2 < 0.75` — con il report scritto comunque; `--assert-min` sostituisce quella
soglia per una corsa singola.

**Comando consigliato prima di ogni merge che tocca chunking, ranking o pesi
of authority** (server on):

```bash
uv run python -m eval.run
```

Ultima misura (2026-08-25, 59 casi, corpus 26 documenti / 181 chunk, baseline
ripristinato, `safeguards_security.md` istanziato sul dominio v2.2.0 e scheda
`BUDGET_ANNUO` aggiunta al glossario):
`recall@1 0.576 · @2 0.797 · @5 0.983 · @10 1.000`.

**Il guardrail asserisce sulla `k` dell'eval-gate, e con la sua soglia** — entrambe lette
da `eval_gate` in [rag_config.yaml](rag_config.yaml), oggi `recall@2 ≥ 0.75`. `--k`
sceglie quali colonne *leggere*, mai su cosa si fallisce, e la `k` del gate viene misurata
comunque anche se non la chiedi. `--assert-min` resta per abbassare o alzare la soglia in
una corsa singola.

**Earlier he asserted on the highest passed k** (A2b), and the two night scripts do not pass`--k`:
il loro confronto cadeva su `recall@10`, **satura a 1.000**, contro un `--assert-min 0.90`
handwritten. A`--assert-min`on a saturated metric is not severe, it is blind — it surpasses it
qualunque regressione che non faccia uscire una fonte dai primi dieci — e quello era un
check notturno che, per costruzione, non poteva fallire.

`recall@5`was saturated at 1.000 after instantiation and returned to 0.983 when the
The corpus has been further enriched: **the gate still remains at k=2**. A gate that changes
`k`with every change of the corpus is not a gate — the stability of the threshold is worth more than
some point of sensitivity.

Il criterio *«/ask inietta 8 sezioni, quindi conta se la fonte entra nella
finestra, non a che rango»* resterebbe valido — ma un gate deve prima di tutto
**distinguish a regression**, and at @5 it no longer distinguishes anything. Even if
`recall@2`if it became saturated there would be no lower useful k left: it will mean that the
golden-set ha smesso di essere una misura e va **esteso** con casi che il sistema
sbaglia, non abbassata un'altra soglia.

This command requires the server to be on (model loaded): for this, it is NOT
in the CI pipeline (see[sezione CI](#ci)), it remains manual pre-merge until
The promotion rule described there matures.

**Tre letture, non una media sola** (S5, [ADR 0002](adr/0002-autorita-dichiarata-e-fiducia-sul-cammino.md)).
La corsa standard riporta il recall a **k ∈ {1, 2, 5, 10}**, e non per completezza:

- **the saturation is reported as a defect, not as 100%.** A recall that counts
1,000 out of *all* cases is not a good result: it is a measure that has stopped
discriminate. The report marks it`⚠️ SATURA`on the metric row. It is a
error already made: the recalibration of authority weights of 2026-07-22 turned
  a k=10 e k=5 su una griglia interamente satura e concluse — correttamente ma
  inutilmente — che nessuna combinazione era distinguibile.
- **the adversarial subset has its own voice.** The marked cases
  `adversarial: true` nel golden-set (oggi 5 su 58) contrappongono una fonte a
low authority that matches lexically *better* than the regulation that answers:
I am the only place where the authority boost can be faked, and in the
  media coi casi facili il loro movimento sarebbe invisibile.
- **the authority weights are calibrated with[eval/calibrate_authority.py](eval/calibrate_authority.py)**,
  che gira in-process (niente server) e **non applica nulla**: scrive una proposta
  in `eval/results/authority_calibrated.yaml` da rivedere a mano. Calibrare
  **sempre** con split di validazione, **sempre** a un k non saturo e **sempre**
on multiple seeds — the default is 5-fold on 5 seeds with standard deviation reported,
because on a single split a gain above threshold has already proven to be noise of
partition. The script also reports the **dead axes**, that is, the parameters that on the
  corpus corrente non muovono la metrica di un millesimo.
- **`boost_alpha` e `section_restatement_weight` sono accoppiati: calibrarli uno alla
time is a mistake already made (S11,[rag_config.yaml](rag_config.yaml)).** Are
  entrambi un moltiplicatore sullo stesso composito di `/ask` (pertinenza × fiducia ×
authority), so the gain of one depends on the value of the other. A grid
  congiunta su `boost_alpha` × `default_weight` × `unclassified_weight` ×
  `section_restatement_weight` (2160 punti, 5-fold × 5 seed) ha confermato in
  produzione `boost_alpha: 0.3` (era 0.1 dal 2026-07-14, calibrato allora da solo) e
  `section_restatement_weight: 0.92` (confermato, non spostato): a k=1 il guadagno
held-out is **+0.038**, and at alpha 0.3 the context ceiling from the graph
(`graph_context_max_chunks`) rose to 3 — at 2 a multihop chain was losing the
  terza fonte in finestra. Dettagli in [AUDIT.md §S11](../archive/adr/AUDIT.md).
- **and what recall DOES NOT measure: to whom the response attributes the constraint.** The
recall says if the correct source has been *retrieved*;`/ask`injects up to 8 of them and
The LLM reads them all, so the recall can be excellent while the response quotes
as the source of the constraint the document that *illustrates* it. It really happened — 2 cases
  avversariali su 4, indagine A3 in [AUDIT.md](../archive/adr/AUDIT.md) — e la correzione
  (`[CLASSE-FONTI]`: la classe dichiarata nell'intestazione di ogni blocco del
context, plus the ranking of the classes present) **has not triggered the recall of a
decimal**, because the ranking was already correct. Whoever touches the`/ask`prompt does not
  ha una metrica che lo protegga: legga le risposte.

```bash
uv run python -m eval.calibrate_authority --k 5   # proposal, never automatic application
```

### La seconda suite: strutturale e multihop

[eval/golden_multihop.yaml](eval/golden_multihop.yaml) + [eval/run_multihop.py](eval/run_multihop.py)
misurano le domande che il golden-set classico non copre: **enumerare** («quali documenti
esistono nel corpus?»), **navigare** («cosa impatta la modifica di X?») e **combinare due o
tre documenti collegati**. Su ogni domanda misura due strade — **A** il retrieval puro
(`/api/retrieve`, k=10) and **B** the deterministic query on the graph (`/api/graph/query`) — like this
The gap between the two is a number, not an impression.

```bash
uv run python -m eval.run_multihop        # server up; exit 1 below threshold
```

### La terza misura: a chi la risposta attribuisce il vincolo

[eval/golden_attribution.yaml](eval/golden_attribution.yaml) + [eval/attribution.py](eval/attribution.py):
the right source always fits into the context (A3), and it is **inside** the window that the model
decide chi stabilisce un vincolo e chi lo motiva. Un giudice LLM legge ogni risposta — una
chiamata per esecuzione, mai aggregata per caso — e nomina la fonte a cui la risposta lo
attribuisce; i passi fra virgolette sono verificati con un `in` sul documento attribuito.
It is neither a gate nor a nightly check: calling LLM costs money and the numbers need to be read (AUDIT.md, S14).

```bash
uv run python -m eval.attribution --repeats 3   # (a) validates the judge offline: Ollama only
uv run python -m eval.attribution --live        # (b) measure /ask: server WITHOUT cache
```

**Il giudice, misurato: 20/24 in-sample, e non passa il criterio fissato per validarlo**
([AUDIT.md §S14](../archive/adr/AUDIT.md)). Sei formulazioni del prompt provate sugli stessi 24 record
d'archivio (temperatura 0, un'unica chiamata per esecuzione, JSON frase→verbo→fonte); tenuta
la migliore (v4: 20/24 d'accordo con l'umano, 5/7 sui negativi, 24/24 di giudizi ripetibili in
three executions). The S6 criterion was 'if it does not match the human verdict, the judge is not
pronto»: non coincide, e in 3 casi su 4 dei disaccordi il giudice sceglie il documento che
**illustra** il vincolo invece di quello che la risposta dice lo **stabilisce** — la stessa
confusione che la metrica esiste per misurare nel modello giudicato, riprodotta nel modello
giudice (sono lo stesso modello, `qwen3.5:9b`, l'unico installato). Sul conto binario del modo
(b) — "the source is the expected one, yes/no" — the agreement rises to 22/24 with **0 missing negatives on
7**: uno schermo utile per decidere quali risposte far rileggere a un umano, non ancora una
metrica automatica. Apre **R29** (AUDIT.md, RESIDUI.md): serve un giudice su un modello diverso
prima di poter promuovere questa misura a gate.

**Four cases out of 14 cannot pass A, and it is the measurement, not a defect.**
L'enumerazione chiede 11 fonti a un top-10, e le tre catene che spandono tre documenti si
they stop at two: it is exactly the gap that motivated the deterministic router. For this reason the
soglia — `eval_multihop` in [rag_config.yaml](rag_config.yaml) — sta sulla **recall media di
A** (0.85, con 0.896 misurato) e sull'**esattezza piena delle attese strutturali di B**, mai
on the number of 'successful' cases: it would be a number that the system cannot make rise.

Unlike`recall@10`on the classic golden set, **this metric has never been saturated**.

Fino al 2026-09-03 la suite girava solo a mano (A4): ora ogni corsa lascia una riga in
`history.jsonl` (`source="multihop"`, chiavi prefissate per non mescolarsi con l'altra
suite) and, below threshold, a critical alert — and it is in the nightly check along with the classic evaluation.

**The case that didn't pass, and why his story remains here** (closed the
2026-08-25). *«posso usare un sinonimo per nominare una variabile o devo seguire
The glossary* had been for weeks the only one of the 59 not to appear in the top 10.
L'attesa puntava a `coding_standards § Tracciabilità della Governance`, e sembrava
un caso scritto male.

Non lo era. Quando il golden-set fu redatto (commit `3a95322`, 2026-07-22)
`coding_standards.md` era alla **v2.0.0 cross-progetto** e possedeva
`[REGOLA-CLEAN-07] Allineamento terminologico rigido`, che risponde esattamente a
that question. However, the working copy had returned to **v1.0.0
dominio-specifica**, ferma a `CLEAN-04`: la regola esisteva solo nel committato, e
il RAG indicizza il disco. Tre file divergevano, e la divergenza era **invisibile a
`git status`** because the files of`docs/`are`skip-worktree`. The defect was neither
in neither the index nor the ranking: it was in the corpus, and nothing looked at it.

Ripristinato il baseline committato, il caso **passa** (atteso a rango 3) e
The entire golden set is in the top 10. Two side effects that are worth more
della singola riga verde:

- **due casi avversariali erano stati scartati per il motivo sbagliato.** «Estrazione
  dei magic numbers» e «isolamento delle regole di business» erano stati giudicati
*you rejected* because`coding_standards.md`did not deal with those topics: they are
  `[REGOLA-CLEAN-05]` e `[CLEAN-06]`, presenti nel baseline e assenti dalla copia di
  lavoro. Il giudizio era una conseguenza della divergenza, non del caso.
- **an adversarial case has ceased to be one.** «Bidirectional traceability in
comments» it was because`vibe_coding_workflow.md`v1.0.0 redefined
  `[REGOLA-CLEAN-*]` con una numerazione collidente. La v2.0.0 rimanda a
  `coding_standards.md` invece di duplicarlo: sparita la collisione, l'atteso va a
rank 1 and the marker`adversarial`has been removed — a case that the system overcomes
  gonfierebbe la recall del sottoinsieme. Gli avversariali sono passati da 10 a 9.

Da qui il check [`docs_git`](#reindex-automatico-lindice-non-invecchia-mai): la
Divergence has become visible again, and at every nightly check it remains so.
I test pytest, che non possono caricare bge-m3, coprono la **meccanica** del
guardrail con un retriever fake deterministico
([tests/test_eval_guardrail.py](tests/test_eval_guardrail.py)): parsing del
golden-set, matcher, calcolo del recall, soglia che scatta, estrazione e
promotion of candidates. Saturation, adversarial subset, and integrity of
matcher avversariali (devono puntare a documenti e sezioni realmente esistenti nel
corpus) sono in [tests/test_retrieval_eval.py](tests/test_retrieval_eval.py). Le
metriche vere restano i comandi qui sopra.

**Il golden-set cresce dalle change (ciclo archive → golden-set):**

1. **Canvas** — alla generazione del canvas il server persiste in
   `changes/<feature>/meta.json` i documenti normativi usati dal retrieval
   governato (`governed_sources`, parsati dagli header del contesto).
2. **Archive → candidato** — `archive_feature` estrae deterministicamente
   (nessun LLM) un caso candidato: query = nome feature + prima riga del
   canvas, expected = quei documenti. Lo accoda a `eval/candidates.yaml`
   (append-only, dedup per query, **mai** nel golden-set diretto).
3. **Revisione umana** — `uv run python -m eval.run --review-candidates`
   mostra i candidati; `--promote 0 2` SPOSTA quelli scelti nel
   `golden_set.yaml` (append testuale: i commenti del file sopravvivono).
4. **Soglia** — con il golden-set aggiornato, rilancia l'eval e rifissa
`eval_gate.min_recall`just below the new measured value. That is where it lives
threshold, and from there they read gate, guardrail, night check, and dashboard.

## CI

Pipeline minima, senza servizi esterni: [scripts/ci.sh](scripts/ci.sh) (POSIX,
usato anche dalla pipeline) / [scripts/ci.ps1](scripts/ci.ps1) (Windows) fanno
`uv sync --frozen` (installazione riproducibile da `uv.lock`), poi `uv run ruff
check .` (selezione esplicita in `pyproject.toml`: import inutilizzati, variabili
morte, nomi ambigui, import fuori ordine — non il default del tool, che su questo
codebase mai linterato aggiungerebbe ~380 preferenze di stile discrezionali),
infine `uv run pytest -q`. Il primo comando che fallisce ferma la pipeline:

```bash
scripts/ci.sh
```

```powershell
pwsh -File scripts/ci.ps1
```

Qdrant e Ollama possono restare spenti: la suite li mocka ovunque (httpx2.MockTransport,
attributi di `core.llm` monkeypatchati, `fastapi.testclient.TestClient` in-process). I
soli 5 test che parlano con un Qdrant reale
([tests/test_qdrant_blue_green.py](tests/test_qdrant_blue_green.py), sezione
"OPZIONALE / SKIPPABLE") richiedono l'opt-in `VIBECRAFT_TEST_QDRANT_URL` verso un
servizio dedicato ai test. Senza questa variabile saltano prima di connettersi;
non usano il `QDRANT_URL` dell'applicazione. In CI `VIBECRAFT_REQUIRE_QDRANT=1`
makes both explicit configuration and service availability mandatory.

**Eseguire quei cinque su un Qdrant di test dedicato prima di toccare il
blue/green**, per esempio impostando `VIBECRAFT_TEST_QDRANT_URL=http://127.0.0.1:16333`
when that service is set up: they are the place where assumptions about Qdrant's semantics
(atomicity of the batch of aliases, resolution of the alias in point-operations —
`upsert` *e* `delete`-by-filter —, invalidazione degli alias alla cancellazione
della collection) vengono verificate contro il servizio vero invece che contro
`AliasAwareFakeQdrant`, che quelle stesse assunzioni le replica. Un fake e il
codice che verifica possono sbagliare insieme; il servizio reale no.

**CSS Tailwind precompilato.** Console, Pipeline e Guida usano `static/tailwind.css` e
`static/tailwind-infografica.css`, generati da [scripts/build_css.sh](scripts/build_css.sh)
(Tailwind 3.4.17 via `npx`, configurazioni in `static/tailwind/`). Dopo aver aggiunto
classi Tailwind nuove a template o script di pagina va rilanciato e il CSS committato:
the CI regenerates it and fails if it differs, because a class without rules would leave
l'elemento senza stile in silenzio.

```bash
bash scripts/build_css.sh
```

The actual remote of the repo determines the pipeline configuration: on GitHub it is
[.github/workflows/ci.yml](../.github/workflows/ci.yml) (job `test` che chiama
`scripts/ci.sh`); su GitLab sarebbe `.gitlab-ci.yml` con uno stage `test` equivalente.
Nota: il resto del progetto (webhook `X-Gitlab-Token`, `extract_gitlab_paths`,
l'indicizzatore `.gitlab-ci.yml` in [code_index/ci.py](code_index/ci.py)) presuppone
GitLab come piattaforma — se il remote cambia, la config della pipeline va allineata di
conseguenza.

**Eval is NOT in the pipeline (for now):**`uv run python -m eval.run`(see above)
requires the server to be on with the models loaded — a pipeline cannot launch it
che non prevede servizi. Resta un comando manuale
pre-merge for those who deal with chunking, ranking, or authority weights.

**Regola di promozione a stadio bloccante:** l'eval diventa uno stadio CI
bloccante SOLO dopo **10 esecuzioni locali consecutive verdi** (nessun flake)
registrate in `eval/results/`. Fino ad allora resta un comando manuale, non
gating. When the threshold is reached, add a stage to the pipeline
`eval` opzionale/non bloccante prima, poi promuoverlo a bloccante.

**Known intermittent test:** in local runs without services the full suite may
occasionalmente andare in errore a cascata (molti `ERROR` di setup/teardown con
`UnicodeDecodeError`) instead of in a single failed test. The known cause is a
thread daemon di `ReindexManager` che sopravvive al teardown di
`test_archive_stream_route_queues_full_and_emits_final_event`
([tests/test_reindex.py](tests/test_reindex.py)) e logga (`api/deps.py:263`,
accented characters) after the pytest capture has already been torn down — on console
non-UTF-8 questo corrompe il file di capture FD-level e fa fallire in cascata i
test successivi. `scripts/ci.sh`/`ci.ps1` impostano `PYTHONUTF8=1` per evitare la
cascata, ma non eliminano la causa: il fix corretto (sincronizzare il test con la
real end of the thread via`ReindexManager.join_all`) already exists elsewhere in the
storia del repo e va portato su questa linea prima di considerare la suite
completamente stabile in CI.

## Benchmark baseline

[scripts/bench.py](scripts/bench.py) misura le latenze delle vie critiche (server
acceso) e salva uno snapshot in `eval/results/bench_<timestamp UTC>.json`:

```bash
uv run python scripts/bench.py                    # without full rebuild (default)
uv run python scripts/bench.py --url http://127.0.0.1:8000
uv run python scripts/bench.py --with-rebuild      # also queues a full rebuild (slow: minutes)
```

Per il carico concorrente read-only di `/ask`, che non esegue reindex, usare il percorso
separato con un servizio isolato e una provenienza del server distinta dal checkout client.
Per questa cohort avviare il server dedicato con `VIBECRAFT_ASK_CACHE_SIZE=0`:

```bash
uv run python scripts/bench.py --concurrency-bench --url http://127.0.0.1:18000 \
--concurrency 1 4 8 --requests 30 --warmup 3 --response-mode json "
--queries adr/horizontal-bench/queries.json --out adr/horizontal-bench/run \
--metadata adr/horizontal-bench/server-metadata.json --cache-cohort cache-off --timeout 300
```

Scrive raw JSONL e un summary per ogni livello; cache off e cache calda vanno eseguite in
distinct cohorts declared with`--cache-cohort`. In stream mode,
`--cancel-probes 3` aggiunge tre sonde per k che chiudono la risposta dopo il primo
testo, salvate separatamente dai percentili principali. `--sample-gpu` abilita il
campionamento opzionale della memoria GPU dell’intero dispositivo condiviso;
`--api-pid` e `--engine-pid` campionano RSS del processo e dei suoi figli.

Cosa misura, in ordine: `GET /api/retrieve` su 10 query del golden-set (p50/p95);
`POST /ask` su 10 query del golden-set (p50/p95/max del totale + medie del
breakdown — vedi nota sotto); `GET
/api/graph/semantic-map` (latenza end-to-end + `truncated`); un reindex incrementale
NO-OP reale (nessun file toccato: misura solo l'overhead fisso del job, dal journal
`GET /api/reindex`); un full rebuild, **solo con `--with-rebuild`** (di default
`skipped`, it is a long and costly operation). If a dependency is down the section
the correspondent is`skipped`with reason: the bench is a **measurement**, never a gate —
exit code sempre 0.

**Note on the latency fields of`/ask`:** from F3 the breakdown is **also in the
JSON response**, not only in the structured end-of-request log (observability M3,
vedi [api/routes_retrieval.py](api/routes_retrieval.py)): `/ask` restituisce
`latency: {retrieval_ms, generation_ms, total_ms}` accanto a `request_id` e
`index_version`. Il bench legge questi campi dalla risposta e, per robustezza,
affianca `avg_latency_total_ms_client` misurato lato client.

### Budget di latenza di `/ask` — misurato, non stimato

Baseline of **2026-09-04** — local run`bench_20260904T075210Z`, whose JSON **is not
versionato** (vedi `eval/results/.gitignore`: i numeri della baseline vivono qui e nel
messaggio di commit). Server locale, `qwen3.5:9b` su RTX 3070 Ti, `top_k` di default
(5), cache di `/ask` fredda, 10 query del golden-set:

| | valore |
|---|---|
| `p50` totale | **24.1 s** |
| `p95` totale | **32.0 s** |
| max osservato | 33.7 s |
| media retrieval | 0,50 s |
| media generation | 22,2 s |

**Where does the time go: 97.8% is the LLM generation.** The retrieval — dense + sparse +
rerank ColBERT + expansion on the graph, that is everything that this repository
implementa — pesa mezzo secondo su trenta. Ogni lavoro di latenza che non tocchi il
model or the hardware therefore has a ceiling of 2.2%: it is the number to reread before
optimize the ranking 'because it seems slow'.

The p95 on 10 samples is in fact at the maximum observed — it is a sample limit,
non della misura, e va letto come "l'attesa peggiore vista in questa run", non come un
percentile stabile. La console non lascia comunque quell'attesa muta: il loader di
`/ask`counts the elapsed seconds, so 30 seconds remain distinguishable from a block.
Questa baseline storica precede lo **streaming incrementale** e misura il JSON unico
con risposta, contesto grafo e punteggi. Non misura il tempo al primo testo della
streaming mode described below, nor the concurrent load.

### Delta reale isolato

The`--real-delta`mode generates a synthetic corpus in a dedicated checkout with
`docs/`, `code/` e `rag/database/` inizialmente vuoti. Il checkout deve essere
esattamente `rag/eval/results/<run>/sandbox/experiment`; la collection Qdrant deve
iniziare con `sidecar_0628_`. Server e Qdrant usano solo `127.0.0.1:18000` e
`127.0.0.1:16333`. Eseguire un processo fresco per ciascuna delle nove famiglie
`N=10,30,100 × docs,code,mixed`, con output e collection nuovi per famiglia:

```bash
python -B scripts/bench.py --real-delta --checkout C:/path/to/rag/eval/results/<run>/sandbox/experiment --output-dir C:/path/to/rag/eval/results/<run>/delta-output --n 10 --mode docs --k 0,1,10 --repeats 5
```

Per `N=100` aggiungere `100` a `--k`; `k>N` fallisce. Il driver avvia bootstrap
incrementale e server HTTP reali, poi per ogni campione verifica job, readiness,
Integrity and concurrent queries. Restore source bytes, artifacts, and snapshots
Qdrant prima del campione seguente. `result.json` conserva eventi monotoni,
journal e campioni anche se la run fallisce; `summary.csv` contiene mediana/min/max
e differenze abbinate `T(N,k)-T(N,0)`. Il restore I/O resta fuori dal tempo
misurato. L'esecuzione richiede il runtime/modello offline e il container Qdrant
dedicati documentati in `../archive/adr/sidecar-work/phase2-report.md`; il comando ordinario
sopra resta il benchmark del servizio esistente.

### Risultati sidecar del 21 settembre 2026

Le [curve prima/dopo](../archive/eval-results/sidecar_npy_20260921/evidence/PHASE6.md)
coprono 30 celle e 150 prove valide per versione: cinque ripetizioni per
combinazione di N, k e corpus. Su Windows/CPU a quattro thread, N=100 e k=100,
la mediana fino allo snapshot pronto passa da 15,934 a 58,099 s per i documenti,
da 18,804 a 19,497 s per il codice e da 19,132 a 38,602 s per il misto.
L'encoding per documento penalizza i delta numerosi di piccoli testi.

La [prova full](../archive/eval-results/sidecar_npy_20260921/evidence/PHASE5.md), su un corpus
diverso di 32 documenti / 64 chunk, riduce RSS massimo campionato da 6,436 a
3,152 GiB e USS da 5,087 a 1,753 GiB. Una sola prova per variante, formato e
raggruppamento dell'encoding cambiati insieme: non isola l'effetto del formato.
Non va confrontata con i delta per ricavare una soglia full/incrementale.

Per k=1, a N=100 documenti, il writer scrive 51.328 byte NPY e riusa 99 file
tramite hard link; sono byte logici, non traffico fisico del disco. Il batching
It is limited to just a study; sharding and Qdrant multi-vectors are not activated.
La [matrice finale](adr/SCALABILITA_SIDECAR_DELTA_MATRICE.md) documenta le decisioni.

Nel codice delle misure storiche le scritture NPY per documento erano incluse in
`parsing_embedding`. La revisione integrata su main le attribuisce a `save_hash`,
inclusi fsync e hash, sia nel full sia nel delta. I raw storici non sono stati
riscritti: i totali restano validi, il breakdown conserva questo limite.

**Regola:** nessuna ottimizzazione di retrieval, chunking, ranking o indicizzazione
senza prima confrontare un bench "prima" e uno "dopo" — la sensazione che qualcosa
being faster does not replace a number saved in`eval/results/`.

I test pytest ([tests/test_bench.py](tests/test_bench.py)) coprono solo la
**meccanica** dello script (percentili, aggregazione, polling del journal, struttura
del JSON) con un server finto (`httpx2.MockTransport`): le latenze vere restano il
comando qui sopra, da eseguire ed allegare alla PR.

## Streaming e repliche locali opt-in

`POST /ask` mantiene il JSON storico come default. Con `"stream": true` restituisce
NDJSON:`meta`, zero or more`delta`with field`text`, finally`result`with field`value`
contenente il payload completo, oppure `error` con `detail`. Il risultato finale
normalizza anche l'astensione; i delta sono provvisori. `meta.streaming_native`
distingue il provider nativo da un adattatore che emette tutto il testo alla fine.
The dashboard uses this mode. Cache and graph responses may not be required
una generazione: vanno misurate separatamente.

| Variabile | Default | Ambito |
|---|---|---|
| `VIBECRAFT_ASK_MAX_ACTIVE` | 8 | Richieste `/ask` attive per processo; eccesso 429 |
| `VIBECRAFT_LLM_CONCURRENCY` | 2 | Generazioni `/ask` contemporanee per processo |
| `VIBECRAFT_LLM_QUEUE_TIMEOUT_SECONDS` | 30 | Attesa massima dello slot di generazione |
|`VIBECRAFT_ASK_TIMEOUT_SECONDS`| Timeout Ollama + 60 | Pipeline expiration; a thread already started ends before returning capacity |
| `VIBECRAFT_GENERATION_MAX_ACTIVE` | 2 | Job LLM attivi per processo, in totale tra generate, refine e project brief; eccesso 429 |
|`VIBECRAFT_GENERATION_MAX_FINISHED`| 100 | Completed jobs are stored by type (generate, refine, brief) for status polling; older ones beyond this are discarded (never those in progress), the GET responds 404 |
| `VIBECRAFT_ROLE` | `standalone` | `standalone`, `reader` oppure `writer` |
| `VIBECRAFT_INDEX_MODE` | `legacy` | `legacy` oppure `immutable` |
| `VIBECRAFT_DELTA_MODE` | `cow` | Delta dei progetti a snapshot immutabili: `cow` (copy-on-write) oppure `rebuild` (full rebuild a ogni delta) |
|`VIBECRAFT_REINDEX_DEVICE`|`auto`| Embedding of reindex jobs, in a separate process.`auto`tries CUDA (NVIDIA, also Spark/GB10, or AMD if PyTorch is the ROCm build), then Metal, then an OpenVINO GPU, then the NPU, then the CPU.`cuda`,`mps`,`intel`and`npu`force that backend. On a discrete GPU the weights of the reindex are all there if there is also space for the LLM (about 8 GB plus a buffer); on Apple the threshold is 24 GB installed, because the system is in the same pool. Below that, it is split. An AMD GPU without ROCm and without OpenVINO is not used.`/ask`stays on CPU |
|`VIBECRAFT_REINDEX_GPU_MIN_FREE_MB`| 3072 | Minimum free memory to use the accelerator: free VRAM on the most free NVIDIA GPU; out of the total pool for unified NVIDIA chips (with at least 1024 MB not mapped); reclaimable memory on Apple |
| `VIBECRAFT_DATABASE_DIR` | `rag/database` | Sorgente storica per diagnostica/migrazione; gli indici attivi sono nelle root registrate |
| `VIBECRAFT_PROJECTS_DIR` | `<installazione>/projects` | Registry e nuove root; percorso assoluto, `/app/projects` in Compose |
| `VIBECRAFT_PROJECT_ID` | legacy | Progetto fisso per MCP e script di manutenzione; la CLI index usa `--project` |

8 and 2 are configurable initial limits, not demonstrated capacities. More processes
moltiplicano sia i limiti verso il motore sia la memoria del modello embedding e
degli snapshot. Non aumentare automaticamente il numero di worker.

### Un writer e due reader sulla stessa macchina

Reader e writer richiedono `VIBECRAFT_INDEX_MODE=immutable`. Preparare un database
dedicato, con Qdrant e motore esplicitamente selezionati, usando il full rebuild
`python index.py` nel profilo writer. Il marker persistente `.immutable-index`
impedisce successivi incrementali anche se un comando dimentica la variabile di
environment; a failed full can intentionally leave this protection active.
Questo rifiuto riguarda il percorso legacy. Per i progetti ordinari l'indice
It is immutable and non-empty`--incremental`is copy-on-write (fallback full rebuild).

Esempio di configurazione PowerShell da applicare **in ogni processo**, adattando
the paths to a dedicated environment already set up. It does not start or modify the services:

```powershell
$env:VIBECRAFT_INDEX_MODE = 'immutable'
$env:VIBECRAFT_DATABASE_DIR = 'C:/vibecraft-lab/database'
$env:QDRANT_URL = 'http://127.0.0.1:16333'
$env:VIBECRAFT_OLLAMA_URL = 'http://127.0.0.1:21434'
# Set VIBECRAFT_API_KEY in the process through your own secret manager.
```

| Processo | Variabili aggiuntive | Comando da `rag/` |
|---|---|---|
| Writer designato | `VIBECRAFT_ROLE=writer`, `VIBECRAFT_PORT=18000` | `python server.py` |
| Reader A | `VIBECRAFT_ROLE=reader`, `VIBECRAFT_PORT=18001` | `python server.py` |
| Reader B | `VIBECRAFT_ROLE=reader`, `VIBECRAFT_PORT=18002` | `python server.py` |

Tutti devono usare gli stessi modelli/configurazione indice e la stessa directory
locale. Il reader richiede una chiave API esplicita anche da loopback: un proxy
locale deve inoltrare una credenziale verificata, senza fidarsi di
`X-Forwarded-For`. Se il proxy inoltra un header `Host` diverso dal loopback, quel nome
va aggiunto a `VIBECRAFT_ALLOWED_HOSTS` nei processi a valle: ogni processo rifiuta con
400 gli `Host` non riconosciuti (difesa dal DNS rebinding, vedi
[SECURITY_SURFACE.md](SECURITY_SURFACE.md) Fatto 9).
La UI richiede la chiave al primo 401 e non la riceve dal server.
Le route di scrittura e i relativi manager non sono caricati nel reader.
Quando il servizio Qdrant offre credenziali di sola lettura, configurare quelle
nei processi reader tramite `QDRANT_API_KEY`; non distribuire loro la chiave writer.

I dati nelle directory di versione possono essere in sola lettura; il
coordinamento `.reader-locks` richiede scrittura condivisa locale. Ogni snapshot
trattiene una lease fino al termine delle richieste che lo usano: retention e GC
they thus also preserve the manifest and the associated Qdrant collection. Do not mount
l'intero database come strettamente read-only. Il lock OS coordina un writer
designated and its CLI commands; it is not an election or failover system.
All'avvio/reload il reader confronta manifest e hash degli artefatti usando il
validatore storage esistente. Per NPY controlla indice e hash registrati; questo
controllo non equivale a una nuova scansione profonda di tutti i byte dei vettori.

### Limiti verificati e prossima misura

Con Ollama 0.34.4 e il modello locale qwen3.5:9b, il motore impone un solo slot per
l'architettura qwen35: richieste HTTP sovrapposte non producono inferenze parallele.
Le [prove reali](../archive/adr/horizontal-bench/preflight-20260928/README.md) lo documentano.
La matrice applicativa k=1,4,8 e il confronto tra uno e due reader non sono ancora
performed; no improvement in throughput or TTFT is declared.

Le repliche su host diversi richiedono un meccanismo verificato di distribuzione
delle versioni e di conservazione delle collection ancora in uso. Le lease locali
they do not constitute a distributed protocol; this scenario is not supported
dall'implementazione corrente. Specifica, gate e stato sono in
[SCALABILITA_ORIZZONTALE.md](adr/SCALABILITA_ORIZZONTALE.md) e documenti collegati.

## Artefatti dell'indice: formati sicuri, ispezionabili e versionati (blue/green)

L'indice persiste in `<root-progetto>/database/` (iniziale: `projects/legacy/database/`)
tramite [core/artifacts.py](core/artifacts.py)
e il reader/writer per documento [core/colbert_store.py](core/colbert_store.py).
The formats are safe (no`pickle`, which is fragile between versions)
e un vettore d'attacco se qualcuno scrive in `database/`) e ispezionabili:

| Artefatto | File | Formato |
|-----------|------|---------|
| Grafo NetworkX | `graph.json` | node-link JSON (`nx.node_link_data`), attributi normalizzati JSON-safe |
| Multivettori ColBERT | `colbert/index.json` + `colbert/d-<hash>.npy` | NPY fp16 per documento, indice con file e offset per `chunk_id`; lettura del solo chunk richiesto |
| Vettori densi dei chunk | `dense.npz` | `np.savez_compressed`, fp16, chiave = `chunk_id` |
| Vettori densi dei simboli | `code.npz` | `np.savez_compressed`, fp16, chiave = `symbol_id` |
| Sidecar testuale dei chunk | `chunks.json` | `chunk_id → {doc_id, section, text}` |
| Sidecar testuale del codice | `code.json` | `symbol_id → {name, kind, file, dev_type, text, deps, refs, links}` |

Gli attributi dei nodi-documento vengono dal frontmatter YAML e possono contenere
tipi non-JSON (date, `Path`): `_json_safe` li normalizza (una data → la sua ISO
string) so`graph.json`is always serializable. The arrays remain **fp16
bit-identical** to the round-trip. Each write is **atomic** (`_atomic_write`): a
A mid-crash does not leave truncated files.

Le nuove build scrivono solo il formato ColBERT NPY. I delta riusano i file dei
documenti invariati tramite hard link, con copia come fallback; i file riusati non
vengono modificati. Full e delta persistono un documento alla volta: il limite dei
Temporary vectors still depend on the larger document and the model batch.
Grafo, metadati, dense e codice conservano costi globali.

Le versioni precedenti in `colbert.npz` restano leggibili, anche per il rollback.
Prima di un nuovo delta su un indice NPZ esistente, convertire la versione
**already versioned** active, without new embedding:

```bash
python index.py --check-integrity
python index.py --migrate-colbert-npy
python index.py --check-integrity
```

La conversione crea una candidata separata, verifica array e hash e solo dopo
sposta CURRENT; conserva la collection Qdrant esistente. Un errore prima della
promotion leaves the previous version active. It neither checks nor repairs the points
Qdrant: if the integrity indicates a misalignment, compare the IDs and the related ones
payload con `chunks.json`, senza eliminare punti solo per far coincidere i conteggi.
The divergence of a local document from Git is a separate warning: a reindex uses
la copia su disco e non decide quale versione del documento sia autoritativa.
Explicit integrity check
rilegge tutti i byte. Il delta legacy verifica indice e file nuovi, ma eredita
gli hash attestati dei file immutati: non equivale a riverificare quei byte e non
rileva una loro successiva alterazione esterna senza il controllo profondo.

### Versionamento blue/green: swap atomico, rollback istantaneo

Ogni build scrive gli artefatti in una **directory di versione nuova**
(`database/versions/v<timestamp UTC>/`, es. `v20260714T153045/`) contenente
grafo, vettori, sidecar **e il manifest di quella build** (`index_manifest.json`:
SHA-256 hash of the sources and artifact files — each version is self-describing,
so after a rollback even staleness and integrity are measured against the version
active). The text file`database/CURRENT`is the **pointer to the version
active**: reading (`load_artifacts`) always follows it, and its writing is
atomic (`_atomic_write`), so the swap is instantaneous and never halfway.

Build e promozione sono **due passi espliciti**: `save_artifacts()` restituisce
il nome della nuova versione (senza toccare CURRENT), `promote_version(nome)`
sposta il puntatore. Gli **incrementali legacy** promuovono a fine build riuscita, senza
go through the gate (until M6 decides otherwise). The **full** — both the CLI
(`python index.py`) sia i job del ReindexManager — prima di promuovere eseguono
l'**eval-gate del golden-set sulla nuova versione** (in process, config
`rag_config.yaml` → `eval_gate.*`: `enabled`, `k` (oggi 2), `min_recall` — 0.90 se
assente, oggi 0.75 in config —, `blocking`):
sotto soglia (e gate bloccante) la versione resta su disco **non promossa**, il job
termina `completed_not_promoted` col report nell'esito e il server continua a
serve the previous version. If the gate is inactive, the golden set is missing or
`cases: []`declares, bootstrap is allowed and the report indicates that the gate
it has not been evaluated. A golden set is present but invalid or an error occurred during
the evaluation blocks the promotion when`blocking: true`; in advisory mode
it allows it with an explicit warning. An empty YAML file is not a valid empty baseline.
A candidate that cannot be loaded correctly instead blocks the
promozione; le candidate NPY devono superare anche i controlli di completezza e
coerenza degli artefatti prima dello spostamento di CURRENT.

Il gate misura anche la **saturazione** della propria metrica e, se `recall@k`
It is worth 1,000 on all cases, writes an alert`warning`: at that k it is not a gate
strict, it's a blind gate — any candidate passes it, even a worse one.
It does not block (it is not a regression), but it should be read as 'lower`eval_gate.k`to a'
k that discriminates. It is not theoretical: on the golden set of 49 cases, measured in July
sul corpus di allora (11 documenti), il recall@10 era saturo a 1.000 su tutta la
calibration grid. Today it is 0.983 and discriminates, for two reasons that are worth it
hard to keep separate: the corpus has grown to 26 documents (and a classic case not
arrives higher in the top-10, see below) and adversarial cases lower the recall@1. The server detects every
spostamento di CURRENT (`maybe_reload_graph`) e ricarica lo snapshot alla prima
richiesta.

**Rollback istantaneo** — sposta solo il puntatore, nessuna build:

```bash
python index.py --rollback              # returns to the previous version
python index.py --rollback v20260713T031500   # or to a specific version
```

Equivalente HTTP: `POST /api/index/rollback` (corpo opzionale
`{"version": "v..."}`) ricarica anche lo snapshot in memoria;
`GET /api/index/versions` elenca le versioni disponibili e quella attiva.

**Retention**: dopo ogni promozione restano le ultime N versioni (default 5, env
`VIBECRAFT_INDEX_KEEP`); la versione puntata da CURRENT non viene **mai** eliminata,
even if older than the N retained (post-rollback case).
Le versioni ancora usate da lettori, anche in altri processi, vengono conservate
tramite lease OS. Il prune ritenta alla chiamata successiva; registra una rimozione
solo se riuscita e segnala gli errori. I piccoli file in `database/.reader-locks/`
They deliberately persist and should not be deleted while the system is in use.

### Blue/green Qdrant (collection versionate + alias)

Ogni full rebuild scrive su una collection Qdrant *candidata* e versionata
(`{collection_name}__{version}`), valuta l'eval-gate su quella stessa candidata, e
solo a gate passato promuove CURRENT e sposta un **alias** Qdrant (il nome
del progetto: `vibecraft_<id>`, oppure `vector_database.collection_name` nel
legacy; retrieval usa la collection fisica del manifest dello snapshot catturato) sulla candidata — la collection di produzione
non viene mai toccata durante il build, solo alla promozione. Se il gate blocca la
promozione, la collection candidata resta su Qdrant non referenziata da alcuna
versione attiva: il GC del prossimo job writer riuscito la rimuove (nessuna
collezione orfana si accumula).

**Migrazione one-shot legacy→alias.** Se la collection di produzione esiste ancora
come collection *fisica* (un'installazione mai passata da questo meccanismo —
Qdrant non ammette un alias con lo stesso nome di una collection esistente), alla
first promotion is **canceled and recreated as an alias** towards the candidate. It is
l'**unica operazione irreversibile** del meccanismo: una finestra di
short but real unavailability (milliseconds) between the delete and the create, logged
explicitly. From that moment on, the production name is no longer a collection
physics: it is always an alias to the latest promoted version. A crash exactly
in quella finestra lascia l'alias mancante: il reconciler lo ripara alla manutenzione writer successiva (o al prossimo job full) se la collection candidata esiste ancora,
senza bisogno di un nuovo rebuild.

**Rollback**: `python index.py --rollback [VERSIONE]` (o `POST /api/index/rollback`)
sposta CURRENT **e** riallinea l'alias Qdrant alla collection dichiarata nel
manifest della versione target — cross-lineage esegue lo swap, intra-lineage (alias
already corrected) is a no-op. If the target version collection no longer exists on
Qdrant (e.g., removed from the GC because the lineage had already been rotated), the rollback is
**rifiutato PRIMA di qualunque mutazione**: CURRENT non si muove, l'alias nemmeno, e
il messaggio nomina la collection mancante e prescrive una re-indicizzazione completa
(CLI: exit 1; route: **409**). Prima CURRENT si spostava lo stesso e restava uno stato
misto — sidecar della versione target, vettori di un'altra build — che nessun
reconciler repairs and that the integrity check reported`ok: true`(see`AUDIT.md`,
A20). If Qdrant is unreachable, the pre-check is **skipped**: a local rollback does not
It depends on the reachability of Qdrant, and the alias is repaired at the next writer maintenance.
Lo stato `"qdrant_alias": {"state": "missing_target_collection"}` nella risposta resta
possibile solo se la collection sparisce fra il pre-check e lo swap, o se il pre-check
It was skipped — no collection is ever 'invented'.

**Riconciliazione e GC.** Avvio e lettura non riparano alias e non eseguono GC.
Maintenance is explicit in the lifecycle writer/CLI under writer lock, with namespace
del progetto. Nessuna riparazione inventa collection mancanti.
`GET /api/index/integrity` espone la classificazione READ-ONLY `qdrant_alias`:
`legacy`/`aligned`/`missing`/`diverging`/`unknown`.

### Backward compatibility and legacy formats

`save_artifacts()` scrive **solo** i formati correnti, sempre in una directory di
versione nuova (mai riscritta). In lettura, se `CURRENT` non esiste ma in
`database/` ci sono i file flat storici (JSON/`.npz`), `load_artifacts()` li carica
come versione `legacy`; la prima build successiva crea la struttura versionata e la
promozione fa vincere CURRENT sul layout flat. Il fallback ai vecchi pickle `*.pkl`
has been **removed** (A13,`../archive/adr/AUDIT.md`): no installation writes to it anymore
dal passaggio ai formati JSON/NumPy (oggi NPY per ColBERT e NPZ per dense/code).
Mantenere `pickle.load` su un
format that nobody produces anymore was surface of arbitrary deserialization
senza alcun beneficio.

## Embedding (bge-m3): CPU per le query, acceleratore per il reindex

- **Server e `/ask`** (`api/deps.py`, `state["embed_model"]`, usato anche da
  `/api/graph/query`): `BGEM3FlagModel` su `devices="cpu"`. Una singola query costa ms
  anche su CPU, e lasciare la GPU libera evita che Ollama carichi `qwen3.5:9b` in
split GPU/CPU (much slower — see LLM section above). The same CPU model is the
  ripiego dei job di reindex (`_reindex_embed_model()` in `api/routes_reindex.py`).
- **Job di reindex** (`core/job_embedder.py`, scelta in `core/accelerator.py`): al
  primo embedding del job, `VIBECRAFT_REINDEX_DEVICE=auto` prova i backend che PyTorch
  esegue davvero, in quest'ordine.
1. **CUDA**, if`torch.cuda`is available and there is enough memory. It applies to the RTX
     discrete, per i chip NVIDIA a memoria unificata (DGX Spark, RTX Spark, GB10,
     Grace) e per una GPU AMD sulla build ROCm di PyTorch: ROCm si presenta come
CUDA, the probe is`rocm-smi`and not a new backend. The GPU with the most is chosen
     memoria libera. Su una scheda discreta servono almeno
     `VIBECRAFT_REINDEX_GPU_MIN_FREE_MB` liberi; su un chip unificato NVIDIA la
the threshold applies to the total of the pool, provided that at least 1 GiB remains unmapped.
  2. **Metal (`mps`)** su Apple Silicon, da M1 a M6, base, Pro, Max e Ultra, se
CUDA is not present or the NVIDIA card has no free memory. The name comes from
     `machdep.cpu.brand_string`, la RAM installata da `hw.memsize` (non il massimo
list price: a 36 GB M5 Max is not treated like a 128 GB one). The probe for
     salire su Metal resta `vm_stat`. Sotto i 24 GB installati — un M1 da 8 GB, un
     Pro da 16, un M6 da 16 — embedding e `qwen3.5:9b` non hanno margine nel pool
     unico: il reindex prende Metal solo per il job, con un tetto sull'allocatore
(`PYTORCH_MPS_HIGH_WATERMARK_RATIO`under 1; the default of PyTorch is 1.7 and
macOS kills the process) and a smaller batch (4 or 8). From 24 GB onwards the
     pesi interi dell'embedding stanno su Metal (`embedding_placement=gpu`) e il
     batch segue la classe: 12 sul base, 24 sul Pro, 32 sul Max, 48 sull'Ultra.
     I pesi restano fp32, gli stessi dell'indice su CPU. Il figlio parte con
`PYTORCH_ENABLE_MPS_FALLBACK=1`. In October 2026 the M6 on the market is the chip
     base; Pro, Max e Ultra di quella generazione non sono un prodotto, ma un nome
     che li contiene si classifica lo stesso.
  3. **GPU OpenVINO** (Arc, Xe, iGPU Intel). Una GPU AMD ci finisce solo se
     OpenVINO la elenca: senza ROCm e senza OpenVINO non viene eseguita.
     Ci gira l'encoder; le teste sparse e ColBERT restano sulla CPU del figlio.
It is not a dependency of`uv sync`.
4. **NPU**, if next to the project there is a runtime that really compiles
     l'encoder: OpenVINO per Intel, `QNNExecutionProvider` per Qualcomm Hexagon,
     `VitisAIExecutionProvider` per AMD Ryzen AI, `CoreMLExecutionProvider` per
     l'Apple Neural Engine. Le teste restano sulla CPU del figlio. Su Apple
     Metal viene prima: il Neural Engine condivide la stessa memoria e non
It takes the place of Metal. This runtime is not in`uv sync`either.
  5. **CPU**. All'avvio del modello condiviso torch usa `cpu_threads()`: su Apple
     i core performanti meno uno, altrove i core logici meno uno, al massimo 8.

  Dove finiscono i pesi. bge-m3 fp32 sta intorno ai 2,2 GB; `qwen3.5:9b` in
Ollama does not fit together on 8 GB (this is the size of this project, not a
license plate). If the chosen GPU has at least that amount plus an extra 1 GB, the
  reindex ci mette l'intero modello (`embedding_placement=gpu`) e l'LLM usa la
same card in turn. On Apple the threshold is not that joint: below 24 GB
  installati il sistema occupa lo stesso pool, quindi si resta in `split` anche
  quando Metal accetta il job. Altrimenti si divide: l'LLM tiene la scheda
big, the reindex goes to the other accelerator or does it go up only until it finds
  memoria libera, e le teste piccole restano sulla CPU del figlio.
  `/ask` resta sulla CPU del server in ogni caso: la generazione dello stesso
  turno usa la GPU subito dopo, e un contesto CUDA residente la manderebbe in
  split. Una sonda `nvidia-smi`/`rocm-smi` muta non viene mascherata con un
another accelerator; the VRAM occupied by the LLM yes, because this is exactly the case in
  cui il lavoro va diviso.

  `cuda`, `mps`, `intel` e `npu` forzano quel backend; `cpu` li esclude. Il
  modello gira in `python -m core.gpu_worker --device cuda:N`, `mps`, `ov:GPU`
  oppure `npu`, fermato a fine job. Il processo del server non crea un contesto
  CUDA o Metal e non compila un modello. L'avvio costa ~10 s per job; la prima
OpenVINO compilation costs more (cache in`~/.cache/vibecraft/npu`or
  `VIBECRAFT_NPU_CACHE`). Se il processo esaurisce la memoria o muore, il resto
  del job usa la CPU. Su CPU un `full` rebuild passa da minuti a **decine di
  ore** (misurato: ~10s/embedding CPU contro ~6-10 it/s GPU). Lo stderr del
  processo finisce nel log del server col prefisso `[gpu-worker]`. Il job
  riporta `embedding_device`, `embedding_placement` (`gpu`, `split` o `cpu`) e
  `embedding_accelerator`.
- Il percorso CUDA richiede la build CUDA di torch (vedi `[tool.uv.sources]` in
  [pyproject.toml](pyproject.toml) — su Windows PyPI serve solo la wheel CPU-only,
that CUDA lives on the official index`download.pytorch.org`). That index is
  vincolato da un **marcatore di piattaforma**: vale su Linux e Windows x86-64, dove le
  sue wheel esistono; su macOS Apple Silicon torch arriva da PyPI (e con lui Metal),
otherwise`uv sync`would fail there (A15 — the measured matrix is in the root README).
  Su Windows-on-Arm (RTX Spark) l'uso di CUDA dipende dalla wheel CUDA di torch per
that platform: if`torch.cuda`is not available the job stays on CPU, and the
  motivo sta nel report.

## Check drift (Step 4): rilievi verificati, verdetto calcolato

`core.drift_check.check_drift` orchestra, `core/drift.py` contiene la logica pura. Il check
storico passava all'LLM il solo Canvas e 40.000 caratteri di codice troncati alla cieca, e
ne mostrava il testo libero: su BE1 segnalava come drift requisiti imposti dalla Spec,
librerie "mancanti" che stavano nei file tagliati, verdetti NO che si davano torto da soli.

1. **Contratto = Canvas + Spec**, con precedenza dichiarata alla Spec: uno scenario vince
On the Canvas, an open dot is not a flaw.
2. **Lotti, non troncamento**: i file (prima quelli citati dal Canvas) sono distribuiti in
lots within`ollama_num_ctx`; a large file is divided into parts. Each prompt lists the files
   che il modello *non* vede. Test e migrazioni generate restano fuori dai lotti.
3. **Pre-check deterministico**: le tecnologie in grassetto nel Canvas sono cercate tra le
   dipendenze dei manifest (csproj, pom, gradle, package.json, dal code index) e date al
model as facts; a technical alternative already satisfied ("MinIO or Azure") cannot
   diventare una mancanza.
4. **Rilievi JSON verificati in Python**: la citazione del codice deve esistere nei file
   visti; ogni "mancanza" porta dei termini che non devono comparire nel codice (commenti e
   test esclusi); il JSON malformato del modello locale si recupera rilievo per rilievo.
5. **Controllo di copertura** sull'indice dei simboli di tutto il progetto.
6. **Riesame mirato** di ogni drift sopravvissuto: scenario intero, codice citato, indice
   dei simboli e righe che citano gli identificativi del requisito; esito `violato`,
   `rispettato` (scartato) o `punto_aperto` (declassato ma visibile).
7. **Verdetto calcolato**: `✅ NESSUN DRIFT`, `⚠️ DRIFT RILEVATO`, `⚠️ PUNTI APERTI DA
   DECIDERE` (requisito assente ma aperto nella Spec) o `⚠️ VERIFICA INCOMPLETA` (risposta
   non interpretabile). La UI colora lo Step 4 da questa prima riga; gli scartati restano
   nel report con il motivo.

Cost: one batch every ~17,500 lines of code, plus coverage and reviews. On BE1 they are needed
40–85 s con qwen3.5:9b sulla RTX 3070 Ti, contro i 12–20 s del check storico.

Misurato il 2026-09-16 su BE1 (5 run per caso, temperatura 0.1):

| Caso | Check storico | Check attuale |
|---|---|---|
| Compliant code | NO in 2/2 run, 6–9 false findings (files “missing” only because truncated) | ✅ in 4/5 run; 1 run with 1 false positive |
| Copia senza export Excel (vero drift) | Excel non citato; report "NO" chiuso da "✅ NESSUN DRIFT" | segnalato in 5/5 run (4 DRIFT, 1 PUNTI APERTI) |

Known limit: the residual false positive is always a 'missing' with an invented name of which
il riesame non riconosce l'implementazione altrove. Il modello locale resta un giudice
weak: the report always shows the rejected ones and their reason, so the outcome is checked by hand.

## Esclusioni dalla scansione del codice generato

`CODE_EXCLUDED_DIRS`(core/config.py) is the shared list of folders never
scansionate sotto `code/`: dipendenze installate e output di build
(`node_modules`, `.next`, `dist`, `build`, `coverage`, `.venv`, `venv`,
`__pycache__`, `.turbo`, `.cache`, `bin`, `obj`, `.vs`, `TestResults`,
`packages`), more`.git`. Used by three points that would otherwise each make their own
`rglob("*")` senza filtro:

1. `core.indexing._code_hashes` — base del delta incrementale;
2. `code_index.collect_code_symbols` — estrazione simboli per il grafo (full
   rebuild E incrementale: l'incrementale filtra a valle sui file "toccati",
but the raw scan below is the same);
3. il check drift (`core.drift_check`, scansione per il confronto codice↔canvas).

Without this filter, a`npm install`/`dotnet build`already executed in the repo does
esplodere sia il prompt di drift (Ollama risponde 500) sia il grafo di codice:
misurato +16708 nodi/+131780 archi da un solo `node_modules`, che rendeva
`/api/graph/all` irrenderizzabile in browser. Aggiungere un linguaggio con una
propria cartella di build (es. `target/` per Maven) va aggiunto qui.

## Entity extraction: only real references in the graph

`core.chunking.extract_entities` cerca nel corpo dei documenti i riferimenti fra
square brackets in the form`[UTENTE]`(domain entity) or`[REGOLA-VAL-07]`
(identificatore di regola) e li trasforma in nodi `entity` + archi `MENTIONS`.
L'estrattore originale (`re.findall(r"\[(.*?)]", text)`) catturava **qualunque**
what among squares: on the real corpus it produced 22 entity nodes devoid of semantics
su 109 token estratti — checkbox Markdown `- [ ]`, etichette dei link
`[testo](url)`, destrutturazioni JS `[k, v]`, literal `'[REDACTED]'`, classi
regex `[A-Z_]` e segnaposto dei template (`[REGOLA-XXX-NN]`,
`[SAFEGUARD-YYY-NN]`) citati a scopo esplicativo nella prosa.

The filter is now two-stage:

1. **Rimozione delle regioni non-riferimento** prima dell'estrazione: blocchi
   di codice ``` ``` (dove le quadre sono sintassi) e link Markdown (dove sono
   navigazione). Il codice inline fra backtick singoli **non** viene scartato:
The convention of the documents cites the rules just like that
   (`` `[REGOLA-HITL-01]` ``) nei titoli e nelle tabelle, e in alcuni documenti
It is the only form in which certain families of rules appear.
2. **Vaglio di forma** sul token candidato: `_RULE_ID_RE`
   (`[A-Z][A-Z0-9]*(-[A-Z0-9]+)*-\d+`, ultimo segmento numerico — il
   discriminante fra una regola vera e un segnaposto di formato) oppure
   `_ENTITY_ID_RE` (`[A-Z][A-Z0-9_]{2,}`, sole maiuscole/cifre/underscore, MAI
the dash, so the wildcards`[REGOLA-*]`stay out).

Effetto misurato sul grafo (full rebuild `v20260722T105547`): nodi 226→204
(entity 124→102, section/document invariati), archi 332→302 (`MENTIONS`
183→153, nessun'altra relazione toccata) — zero token legittimi persi.
Test in [tests/test_chunking.py](tests/test_chunking.py).

## Code index: aggiungere un nuovo linguaggio

L'estrazione dei simboli dal codice generato (`code/`) vive in
[code_index/](code_index/__init__.py); i parser tree-sitter in
[code_index/ts.py](code_index/ts.py) (TS/TSX/JS/JSX/Svelte),
[code_index/java.py](code_index/java.py) (Java + pom.xml/build.gradle +
Kogito .bpmn/.dmn), [code_index/csharp.py](code_index/csharp.py)
(C#/.NET + .csproj/packages.config) [code_index/razor.py](code_index/razor.py)
(famiglia Razor: view MVC, Razor Pages, componenti Blazor) e
[code_index/sql.py](code_index/sql.py) (SQL: T-SQL, PL/SQL, generico —
archi semantici READS/WRITES/EXECUTES e ponte codice→stored procedure
dai parser C#/Java) [code_index/config.py](code_index/config.py)
(file di configurazione riconosciuti per nome: web/app.config,
appsettings*.json, package.json, WSDL/XSD — secret sempre mascherati,
nodi collegati al progetto di appartenenza) e
[code_index/shell.py](code_index/shell.py) (script operazionali Bash e
PowerShell via tree-sitter — archi EXECUTES script→script e riferimenti
incrociati verso i progetti/file invocati) e
[code_index/ci.py](code_index/ci.py) (pipeline GitLab CI / Azure DevOps
riconosciute per nome — nodi pipeline/job, archi verso template, progetti
buildati e repo esterni dai trigger),
[code_index/frontend.py](code_index/frontend.py) (semantica React/Angular
sopra il parser TS: componenti, hook, DI, route, template — framework
rilevato dal package.json del progetto, non dall'estensione) e
[code_index/docker.py](code_index/docker.py) (artefatti di containerizzazione
riconosciuti per nome — Docker Compose via pyyaml e Dockerfile via scanner
riga-per-riga: nodi service/image, archi service→service da `depends_on` e
service→Dockerfile dal build context; environment/ARG sensibili sempre
masked). The interface of a parser is a function
`(text: str, stem: str, suffix: str) -> list[tuple]` con tuple
`(kind, name, snippet)`or`(kind, name, snippet, meta)`:`kind`is e.g.
`function`/`class`/`endpoint`/`component`,`name`is unique in the file,
`snippet`is the textual context used for embedding (max ~1500 char) and
`meta` (opzionale) porta `deps` (nomi di altri simboli del progetto, risolti
best-effort in archi DEPENDS_ON da `link_symbols`) e `package`.

Per aggiungere un linguaggio:

1. **Grammatica** — aggiungi il wheel della grammatica con `uv add
`tree-sitter-<lang>` (o usa `tree-sitter-language-pack`, already as a dependency,
   se il wheel singolo non esiste: `get_parser("<lang>")`). Niente
   compilazione manuale: solo wheel precompilati.
2. **Parser** — implementa in `code_index/ts.py` una funzione con
   l'interfaccia sopra. Per linguaggi C-like spesso basta estendere
   `_DECL_KINDS`/`_walk_symbols`; per formati contenitore (vedi
   `svelte_symbols`) localizza i blocchi di codice con la grammatica del
   formato e ri-parsa il contenuto con la grammatica del linguaggio interno.
3. **Dispatch** — in `code_index/` registra l'estensione in `CODE_EXTS` e
   aggiungi un ramo `if suffix == "...":` in `_extract` che chiama il parser
directly: it is the pattern that java/csharp/razor/sql/shell already use, not
   un flag di configurazione — un dispatch pluggable per-linguaggio (`_PARSER_LANG`
   / `_PARSER_DEFAULTS`) esisteva solo per TS/JS/Svelte durante la migrazione da
regex a tree-sitter, and it was removed with that (A12, 2026-09-03: none
language has more than two implementations to choose from). If one day a
   linguaggio ne avesse davvero due, `code_parsers.<lang>` in
   [rag_config.yaml](rag_config.yaml) resta il posto dove dichiarare quale.
4. **Test diretti** — un corpus rappresentativo del linguaggio con le coppie
   (kind, name) attese per file, come [tests/test_ts_parser.py](tests/test_ts_parser.py):
   se sostituisci un parser esistente, verifica sul corpus che il nuovo trovi
at least everything the old man found, then replace the expectations.

**Secondo esempio del pattern — Java** (`code_index/java.py`): grammatica
`java` dal language-pack; estrazione framework-aware via annotation (JAX-RS
`@Path`+`@GET/...` → `endpoint`, CDI `@Inject` → nodo `field` + dep verso il
bean, messaging `@ConsumeEvent/@Incoming/@Outgoing` → `listener`), stesso
pattern dei decoratori FastAPI nel parser Python. Gli artefatti di progetto
non hanno bisogno di tree-sitter: pom.xml/.bpmn/.dmn sono XML (ElementTree),
build.gradle is regex best-effort. No equivalence testing: it did not exist
parser Java precedente (i test sono su un mini-progetto fittizio in
[tests/test_java_index.py](tests/test_java_index.py)).

**Esempio completo del pattern — C#/.NET** (`code_index/csharp.py`): mostra
tutti i pezzi in un modulo solo. Grammatica `csharp` dal language-pack (punto
1 della guida); simboli con namespace nel meta `package` e using come `deps`;
estrazione framework-aware via attributi, runtime-agnostica: [HttpGet]/
[HttpPost]/[Route] (ASP.NET Core) e [OperationContract] su [ServiceContract]
(WCF, .NET Framework legacy) → kind `endpoint`; file di progetto senza
tree-sitter: `.csproj` (PackageReference/ProjectReference → DEPENDS_ON tra
progetti, base dell'impact analysis multi-repo) e `packages.config` legacy;
dispatch + flag `code_parsers.csharp` (punto 3); corpus fittizio in
[tests/test_csharp_index.py](tests/test_csharp_index.py) (punto 4, senza
equivalenza: parser nuovo). Fuori scope per questo modulo: Razor/.cshtml, che
ha il proprio scanner ibrido dedicato (`code_index/razor.py`, vedi sotto) —
The tree-sitter Razor grammar is immature, hence the choice of a scanner
invece che una nuova grammatica. VB.NET resta fuori scope per entrambi.

**Variante senza grammatica — Razor** (`code_index/razor.py`): quando la
tree-sitter grammar does not exist or is immature, the parser can be one
scanner ibrido: regex per direttive/markup, delega al parser tree-sitter di
un altro linguaggio per i frammenti incassati (i blocchi `@code` vanno al
parser C#, come gli `<script>` Svelte vanno alla grammatica TS). I link che
richiedono la vista d'insieme dei file (code-behind per convenzione di nome,
`View()` → `Views/{Controller}/{Azione}.cshtml`, tag componente Blazor) si
esprimono come **dep tipizzate** (`view:...`, `page:...`, `component:...`)
risolte da `resolve_links` dopo la scansione di tutto `code/`: le dep
risolte diventano archi DEPENDS_ON, quelle non risolte finiscono nel report
di governance (`code_index.razor_report()`: link rotti e view orfane), mai
in nodi fantasma. `refs` nel meta crea archi REFERENCES codice→codice
(es. view → `@model`).

The historical regex parser for TS/JS/Svelte (`_js_symbols`) has been **removed**
(A12, 2026-09-03): 53 giorni senza incidenti dalla migrazione a tree-sitter
del 2026-07-12 erano il segnale che il debito poteva chiudersi per davvero,
not just giving back.`code_index.ts`(tree-sitter) is today the only one
implementazione per quei tre linguaggi.

## L'indice come acceleratore per l'agente che scrive il codice

`GET /api/code/search?q=...&k=...` espone a un agente esterno (Claude Code,
Cursor) la stessa ricerca semantica sui simboli che alimenta `/ask`: coseno fra
the query and the dense vectors of the symbols, already calculated at indexing and
persistiti in `code.npz`. Nessun LLM, nessuna query a Qdrant — una forward pass
di bge-m3 e un prodotto matriciale in memoria.

Serve a un problema misurato: un agente che deve integrare codice in `code/` non
he knows where what he needs is and folds over Glob+Read thoroughly, that is, he reads (and
paga) l'intero ambito per trovare i due file che gli servono. Su questo repo,
una ricerca `k=5` in `code/frontend` restituisce ~2,2 KB che puntano a 3 file per
21 KB complessivi, contro i ~101 KB dell'intero `src/`.

That gain, however, easily turns into its opposite — if the answer is
Basically, the agent pays the index tokens **and then** those of the files. Therefore the
the answer is **navigational**, not documentary:

- **niente testo dei simboli per default**: solo `symbol_id`, `file`, `kind`,
`dev_type`and`score`, plus the`files`aggregate — the list of files to open, which
It is the only thing that the agent really has to derive from it;
- `&snippet=true` aggiunge il testo, **troncato** a `code_search_api_snippet_chars`
(400): on the same example the answer doubles, and this is why it is an exception
  dichiarata nel prompt, non il default;
-`&k=`is limited by`code_search_api_max_k`(25) and`max_per_file`prevents a
  file autogenerato di occupare tutte le posizioni;
- `&dev_type=` restringe all'ambito della feature. Il filtro agisce **prima** dei
  top-k (`search_code_symbols(subset_idx=...)`, indici per ambito precalcolati una
  volta per snapshot in `api/deps._prep_dev_type_index`): applicato a valle, un
  ambito poco rappresentato sparirebbe ogni volta che i top-k globali appartengono
  a un altro ambito.

The final prompt is built in`core/pipeline.py`. The variant`external`, from
copiare in Claude Code/Cursor, descrive le API HTTP. Per l'esecuzione in-app la
dashboard richiede `/api/pipeline/final-prompt?feature=<feature>&consumer=agent&mode=<mode>`:
Suggest e Agentic consultano l'indice tramite i tre tool MCP locali; One-shot
receives Canvas and Spec attached in JSON, because it does not have reading tools.
I percorsi in-app sono assoluti: Agentic lavora dentro `code/`, mentre l'indice
returns paths relative to the project root. If the mode prompt
It is not available, the execution does not start with an incompatible external prompt.

Il prompt in-app richiede contesto su domanda: ricerca codice con `k=5`, ambito
`dev_type` e `snippet=false`; grafo e norme solo quando necessari. Per ogni
scenario chiede modifica o proposta, copertura dei test e lacune residue.
Suggest remains read-only; Agentic can write code and tests but cannot execute them,
because Bash remains excluded. The report must distinguish implemented from verified.

Il bridge configura direttamente il processo stdio usando lo stesso interprete
Python del backend. Il backend HTTP deve essere avviato e raggiungibile tramite
`VIBECRAFT_MCP_BACKEND_URL` (default `http://127.0.0.1:8000`); URL, timeout e chiave
sono ereditati dall'ambiente; l'ID del progetto catturato viene passato al MCP
come `VIBECRAFT_PROJECT_ID`, indipendentemente dalla selezione corrente nel browser.
Il prompt esportato dichiara l'header progetto per HTTP e l'ID per il client MCP.
`strict_mcp_config=True` esclude altri server MCP,
`tools` limita i tool nativi e `allowed_tools` autorizza solo i tre tool MCP nominati.
`VIBECRAFT_AGENT_MAX_TURNS` limita il ciclo a 30 turni per default (intero 1–200);
One-shot ha un solo turno. Gli errori di configurazione chiudono lo stream con errore.
Su Windows viene usato, se presente accanto allo shim npm, il binario nativo
`node_modules/@anthropic-ai/claude-code/bin/claude.exe`; lo shim `.cmd` non viene eseguito.

### Runner dell'agente: Claude, Ollama, Codex, Cursor

`POST /api/pipeline/agent/run` accetta `runner` (`claude` | `local` | `codex` | `cursor`,
default `claude`) accanto a `mode`; `GET /api/pipeline/agent/runners` elenca quelli
con capability esplicite (binario installato, modelli Ollama, export e lancio disponibili).
Ammissione, gate, journal e formato NDJSON dello stream sono gli stessi per tutti
([agent_runners.py](agent_runners.py)). The model name is bound by a regex: it ends
in the CLI arguments, so no initial`-`or metacharacters.

| runner | mode | context | perimeter |
|---|---|---|---|
| `claude` | suggest, agentic, oneshot | tre tool MCP | bridge SDK descritto sopra |
| `local` (Ollama `/api/chat`) | suggest, agentic, oneshot | `read_file`/`list_files`/`grep` | i tool li esegue VibeCraft, niente shell; letture nella root del progetto, escludendo altre root, link, `.git` e `.env*`; in agentic `write_file`/`edit_file` passano da `_path_escapes_code`, la stessa decisione dell'hook Claude; output dei tool troncato a 6.000 caratteri |
| `codex` | export prompt | MCP esterno con ID esplicito | integrato disabilitato: isolamento letture non verificato |
| `cursor` | export prompt | MCP esterno con ID esplicito | integrato disabilitato: isolamento letture non verificato |

L'avvio integrato resta disponibile per `claude` e `local`. Per `codex` e
`cursor` il server restituisce 400 `native_read_isolation_unverified` prima
di avviare la CLI: cwd e sola lettura non dimostrano isolamento fra progetti.
`GET /api/pipeline/agent/runners` distingue `installed`, `available`,
`export_available`is a reason for unavailability; the installed track does not
rende disponibile il lancio. Export prompt e MCP esterno sono utilizzabili
anche senza binario. Il nome modello e i timeout conservano i vincoli esistenti.
Claude/local catturano root, code_root e ID del progetto; Read e scansioni
sicure restano disponibili, scritture soltanto in `code/`. Link, segreti,
`.git` e progetti annidati sono esclusi; uno scan SDK di un subtree che li
contains is denied, the local runner applies pruning.

Verifica locale senza provider o corpus privato:
`python -m pytest tests/test_agent_bridge_perimeter.py tests/test_agent_runners.py tests/test_pipeline.py tests/test_mcp_server.py tests/test_mcp_http.py`
e `node tests/pipeline_agent.cjs`. Il test stdio avvia il server dalla configurazione
del bridge e controlla i tre tool contro un backend HTTP con dati sintetici.

Il blocco dice tre cose che ne delimitano l'uso, e sono la parte che conta:
The index is used **only** to choose what to read, it is a snapshot of the last
indexing and can be misaligned (the code-links remain stale until
rebuild), quindi ogni file va letto per intero prima di modificarlo e nessuna riga
va dedotta dai frammenti dell'indice; e se l'indice non risponde, l'agente procede
with Read/Grep — it is a shortcut, not a dependency.

## MCP locale di sola lettura

The local HTTP backend must already be started with a ready index. From PowerShell,
nella directory `rag`, avviare l'adattatore con:

```powershell
uv sync --frozen
$env:VIBECRAFT_MCP_BACKEND_URL = 'http://127.0.0.1:8000'
$env:VIBECRAFT_PROJECT_ID = '<project-id>'  # omit for legacy
uv run --frozen python -B mcp_server.py
```

The process is waiting for the protocol on stdin; it is not an interactive console.
Per Claude Code, `.\scripts\install_mcp.ps1 [-Scope user|local|project]
[-BackendUrl http://127.0.0.1:8000]` esegue `uv sync --frozen` e registra il server
`vibecraft` con il Python di `.venv`; rieseguirlo sostituisce la registrazione.
Configurazione essenziale di un **client locale** che eredita l'ambiente:

```json
{
"mcpServers": {"
"vibecraft": {"
"command": "C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe", 
"args": ["-B", "C:/Users/Silve/Desktop/vibecraft/rag/mcp_server.py"]
    }
  }
}
```

Adapt the paths to the checkout to use.
`VIBECRAFT_MCP_BACKEND_URL` is valid by default `http://127.0.0.1:8000`;
only HTTP, `127.0.0.1`, `::1` and `localhost` are allowed (rewritten in `127.0.0.1`,
without DNS). No path, credentials in the URL, environment proxy, or redirect.
`VIBECRAFT_API_KEY`, if necessary, must be inherited from the client's environment:
The adapter forwards it to `X-API-Key` and does not read secret files.
`VIBECRAFT_PROJECT_ID` is captured once and forwarded as
`X-VibeCraft-Project`; restart the MCP session to change the project. Without
ID is used only legacy. Auth remains unchanged: bypass loopback for
standalone/writer, mandatory key even on loopback in reader.
`VIBECRAFT_MCP_TIMEOUT_SECONDS` sets the total timeout and HTTP: default 30 s,
Interval 0.1–120 s. No new MCP gate.

The only tools are `vibecraft_retrieve`, `vibecraft_code_search` and
`vibecraft_graph_query`. The arguments are contained in the object `params`, for example
`{"params":{"q":"quali documenti esistono?","limit":20}}` for the graph.
Structured responses preserve order, identifiers, and HTTP scores.

- Retrieval: `q` 1–4000 characters, `k` 1–50 (default 5), `include_text` default true
in the tool and false in the HTTP API;`text_max_chars`1–8000 (default 2000) per chunk.
`text_chars`, `text_truncated`, `source_label` and `index_version` declare origin
and cut. The collection is that of the manifest of the captured snapshot.
- Code: `q` 1–2000, `k` 1–25 (default 8), `dev_type` up to 64 characters,
`snippet` default false. `min_score` 0–1 and `max_per_file` 0–10 are optional:
if omitted, the backend defaults are used. The actual limits and the text cutoff
They are explicit. A backend configured with a lower limit can reject the request.
- Graph: `q` 1–2000, `target` optional up to 1000 characters, `limit` 1–1000
(default 100), shared between lists and rings. `count` keeps the original total;
`returned_count` counts the returned elements (including the root in the rings).
`truncated` reports the omitted elements. Impact limited to two hops; no Cypher/SQL.
The HTTP API without `limit` preserves the historical response.

Top-k, filters, outdated index, and truncation prevent deducing an absence
in the project from an empty or partial list. The sources are data, not instructions.
Over 2 MiB the response is completely rejected; reduce the limits.
Input errors, authentication, backend unavailable, timeout, redirect, and JSON
invalid produce MCP errors without HTTP body, sensitive URL or keys. Log to stderr.

Shutdown: disable the voice in the client and close the stdio process, or
Ctrl+C if started manually. The HTTP backend remains independent; no rebuild
or additional switch. In the container, run the process **inside the same
backend container**, for example `docker exec -i <container> python -B mcp_server.py`
(without `-t`); the backend remains on loopback from the adapter's point of view.

The in-app execution links these tools to the runner only `claude`: the requested extracts
They enter into the context of the remote model. One-shot, on the other hand, sends Canvas and Spec in the prompt.
For external Codex/Cursor, the prompt can be exported and this MCP can be configured
in the client with the explicit ID: the integrated launch remains disabled. The
external client maintains their own file access policy; VibeCraft does not
certifies its sandbox. Only `local` remains entirely on the machine.
Access to the private corpus from other clients or providers requires authorization
explicit. Automatic tests use synthetic data and do not call the model.
The MCP server remains read-only: it does not expose `/ask`,
intake, writings, shell, reindex or the agent startup.

Reproducible benchmark, with ready backend and without concurrent loads:
`python -B -m scripts.bench_mcp --pairs 30`. Three warm-ups per tool are excluded;
JSON on stdout with each pair and p50/p95. The matched delta also includes the
variability between the two backend executions: it is not the total retrieval time.
The acceptance limit for delta p95 is **10 seconds (10,000 ms)**, updated
at the request of the maintenance technician after the measurements of session 5. The JSON records
`overhead_limit_ms` together with the outcome; the call timeout remains 30 s by default.

### Research and open points: advisory perimeter

Agent's proposal and conclusion share the pattern `core/open_points.py`:
final section `## Punti aperti`, a fence `json` with `{"open_points":[...]}`,
outside the Gherkin scenarios. Each point retains ID, feature, original question
(`original_question`), current question, assumption to confirm, uncovered cases,
reason and report of the last search round. Before each search, the agent
state the question and the missing information; then state the new evidence.
If he does not obtain any, he closes that branch with `reason: no_new_evidence` and keeps it
in the same list of open points of Propose. The closure concerns the research,
not the resolution of the point: the other independent branches can continue.

Only relevant content not already in the accumulated context, referring to
document/chunk and read portion, file/symbol or relation. Ranking, paraphrase,
Different IDs or versions with the same content are not enough; read the part
first truncated can add evidence. The runtime **does not check** for news,
relevance, sequence of searches or branch stopping: `research_policy`
declares `enforcement: advisory` and `verification: agent_reported`.
The IDs are assigned by the agent: `id_reuse_verified: false` and
`original_question_verified: false` expose the anti-paraphrase limit.
The original question makes two similar points inspectable, but the agent can
still change it or assign another ID; no semantic comparison is applied.

Propose, read/save Spec, export the contract and NDJSON result
they return `open_points_status`:

| State | Payload | Meaning |
| --- | --- | --- |
| `missing` | `open_points` absent | Report/field not provided, even for previous Specs |
| `invalid` | `open_points: null`, `open_points_error` | Report present but malformed |
| `valid` | `open_points: []` or list | Valid schema, content declared by the agent |

Only `valid` with empty list shows «Finished with no open points» in UI,
with the advisory limit next to it. The other states are distinct and one stream
without a final result is reported as interrupted. The original text remains
in the Spec (also `spec.raw.md` for Propose) or in the textual events of the bridge.
The external prompt uses the same protocol, but its output does not fit
automatically in the pipeline. The following gate constrains agentic starts
executed by the server; it does not manage externally initiated executions autonomously.

### Gate — enforcement agentic, validation and decisions

**Starting agentic requires a successful validation of the current contract.**
`POST /api/pipeline/agent/run` receives features and validation_id and recalculates
`evaluate_gate` on the server; does not accept allowed/force and ignores the client prompt
in agentic. The prompt is built from Canvas, Spec, and decisions frozen in
record. Suggest/oneshot remain available, with the reasons for the gate visible.
The gate is identical for every runner; agentic is allowed only with `claude` and `local`.
The UI «Compare with the validated version» shows the stored texts and those
currents; without validation, it declares the absence of comparison.
409 indicates documents, validation, and remedy; 503 indicates the infrastructure
and also preserves the other reasons. The agentic start does not begin if it cannot be
recorded in `database/pipeline/events.jsonl`.
[Piano e schema dei record](adr/PIPELINE_GATE.md).

The kernel distinguishes missing/invalid, unaddressed, mismatch, failed/stale and
unavailable, with actions user_action/operator_action/retryable. Blocks on only
documents provided to the validator; the rest of the corpus produces a warning. None
TTL, JSON repair, normalize_spec in hash calculation or force.
Canvas, Propose, dry-run, and agent context distinguish retrieval failures
governed by valid but empty results. An operational failure returns 503
without calling the model or overwriting the feature artifacts.

Original sequence: **minimum recorder provider → prompt ablation → decision
on the pilot → possible baseline A → commit dedicated to the isolation of
settings → gate → measures B and C**. No starter before the decision;
if approved, checkpoint after an hour of preparation. The recorder SDK is postponed
to the pilot. `eval/provider_recorder.py` observes Ollama only if explicitly activated
from an evaluation runner in a separate, serial process. The server does not
Important: no production logging. Copy the payloads before extraction
of the text, without changing requests, retry or cache; keep the returned counters,
never estimated tokens. The recorder's errors make the measurement incomplete, without
retry the generation. The on/off tests use the actual provider path
with simulated HTTP responses, including errors and retries. It does not promise zero overhead.
Phase 2 is now [chiusa](eval/results/FASE2_PROPOSE_20260914.md), without pilot.
The approved sequence is settings isolation → V3 adoption → gate,
with a checkpoint for each commit. Isolation is applied as follows;
The start enforcement and the events are implemented.

The bridge sets `setting_sources=[]` explicitly
for **suggest, oneshot and agentic**, preserving the confinement SDK hook
of the writings of agentic. `tests/test_agent_settings_isolation.py` uses the
Real CLI/SDK in all three modes: harmless `SessionStart` hooks in
user, project and local settings create sentinels in a temporary environment
when the sources are explicitly loaded; with the real options isolated
they do not create them. The test only initializes the session, without prompts or
generations. The positive control and the reason for keeping it are at the top
in the test: the mere absence of the tools or the sentinel is not enough as proof.
Execution from `rag/`: `python -m pytest tests/test_agent_settings_isolation.py -q`.
Requires the Claude CLI installed (the one included in the SDK or the native one)
selected by the bridge), not a provider credential. A positive check
failed makes the test fail: it is not turned into a skip.
If operational dependencies on local settings emerge, stop the work
and notify them before proceeding, without implicitly enabling them.
Guarantee for suggestions and oneshots: **no application writing controllable by the agent or local hooks**; agentic retains the
confined application writings provided. It is not promised that the process does not
it writes any byte, for example in its session files.

Guarantee of acceptance in the approved design:

> Acceptance is not exposed to the agent's instruments; it is not certified
> as a human decision from the shared credential.

The guarantee is also in the writer's docstring `PipelineStore.record_decision`
and of the decision route; the requirements to change `origin_verified` are
next to the point where the writer imposes it. `core/open_points.py` distinguishes
the advisory report of the agent from the decisions recorded by the server.

A point `accepted` remains explicitly unresolved; `resolved` records a
resolution, while `unaddressed` indicates the absence of a decision. Acceptance
it is linked to the full content of the item, not just the ID, and the decision comes into
in the footprint of the executable contract. Accepting a gap does not make one satisfied
the scenarios concerned; `uncovered_scenarios: []` does not certify the marginality.

The decision record preserves declared origin, metadata
observed from the call and active executions on the same feature, with
**`origin_verified: false` mandatory and imposed by the server**, not configurable
nor promotable through caller input. Schema and test reject
`true` in the protocol based on the shared key.
To be able to introduce `true`, an authenticated personal identity will be required
(not a shared key), a server-verified link between identity and
origin of the request and an explicit review of this warranty.
A declared name, a header that says "UI" or possession of the key are not enough;
Not even personal identity alone proves that someone has read the point.

We can count the acceptances **that occurred during** an execution of the agent,
we cannot call them acceptances **made by the agent**. The correlation
Temporal does not distinguish a concurrent UI session from an automatic request.
The current correlation observes only the server process: `activity_scope`
It reports the PID, executions without features are listed separately.
An empty list does not prove the absence of agents on other processes; the feature of the
client in suggest/oneshot remains declared; in agentic it is compared with
the validated record. The events of Phase 2 are in the pipeline journal,
separated from the history of evaluations. An attempt without a concluding event
does not certify completion; a recording error indicates incomplete measurement.

The global structural surveys `scenari_insufficienti` and `caso_negativo_mancante`
they remain blocking until the operator explicitly associates them with a point
accepted. No preselected association, no GIVEN/WHEN/THEN exception.
They remain visible, decisively, the declared author and `origin_verified: false`.
The integral association enters the hash; by changing the Spec both the
The decision is up to the association. An accepted gap does not certify coverage.
The choice that emerged in implementation and its limits are in the gate plan.

## Multi-project check — October 5, 2026

Final gate: **2,348 passed, 20 skipped**, lint and Node check passed,
Independent review approved. HTTP/Qdrant/real browsers have been verified,
A/B with names/queries/homonymous feature, competing jobs and Docker persistence. The 20
skip depend on Windows file-symlink privileges; complementary Linux tests
they run real links. Docling and LibreOffice were run with local assets.
The providers are simulated at the boundaries. Docker is tested with the current source
mounted on existing runtime CPU: build image from scratch and GitHub Actions
not executed. These results do not verify remote providers or released versions.

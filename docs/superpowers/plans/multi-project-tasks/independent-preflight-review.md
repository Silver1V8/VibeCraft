# Independent review preflight — multi-project

Reviewer: final_independent_review, read-only product inspection. Snapshot: committed HEAD `4223b84`; baseline `34b46dfeabcff05820240a1241baae1a215d3e1b`. Task 4 is still being edited and is excluded from this verdict. This is not final branch acceptance.

## Inspected boundaries

| Boundary | Observation / next gate |
| --- | --- |
| Registry → context | IDs and roots are validated; ordinary paths derive from root; settings are copied. HTTP captures context once in request state. |
| Context → snapshot | Runtime and snapshot keys use project ID; the two-entry LRU drops references, preserving snapshots held by requests. Reload errors remain project-local. |
| Snapshot → retrieval | Routes pass captured snapshot collection, data and context through retrieval; shared client/model initialization is separately locked. |
| Runner → MCP | Options copy mode configuration, capture cwd/code root and use installation MCP script with fixed project ID. This bounded seam does not establish read confinement; full Task 5 remains necessary. |
| Workflow → store/thread | Task 4 review will trace callback capture, feature/gate separation, shared indexing lock and linked-path rejection before I/O. No Task 4 conclusion yet. |
| Distribution | Full Task 7/8 container and integration gates remain necessary. No final suite or baseline repeated. |

## Fresh focused checks

Command from worktree `rag/`, using the existing interpreter with `PYTHONUTF8=1` and `PYTHONPATH` pointing at this worktree:

```text
python -m pytest -q -rs
  tests/test_project_runtime.py::test_snapshots_are_isolated_and_eviction_keeps_inflight_lease
  tests/test_project_runtime.py::test_concurrent_capture_loads_once_and_reload_error_is_local
  tests/test_project_runtime.py::test_shared_resources_initialize_once
  tests/test_project_runner_seam.py::test_sdk_options_cwd_hook_mcp_and_modes_are_project_local
  tests/test_project_runner_seam.py::test_mcp_project_header_is_fixed_for_all_transport_calls
```

Result: exit 0, five tests passed (`..... [100%]`), no skips shown. Checks use temporary project data and mocked providers/transport; no real corpus or production Qdrant access. This establishes only the named boundaries.

No concrete new blocking finding from this bounded preflight. Existing native Codex/Cursor read-isolation ruling is retained: availability must fail closed until independently verified, including legacy and default context. Full Task 5 is not yet implemented/reviewed.

## Additional integration finding — P2, readable unindexed errors

`rag/static/pages/intake.js:118` passes the structured HTTP `detail` object directly to `new Error`. The new workflow admission contract returns `{detail: {code: "project_not_indexed", message: "Project has no index"}}` when generation requires an absent snapshot. A user selecting a newly created, unindexed project and starting generation therefore sees `Errore: [object Object]` and loses the actionable reason. Related intake and pipeline consumers have the same old pattern; audit them while applying the fix, without changing successful responses.

Minimal remedy: use the existing shared `apiErrorMessage(data.detail, fallback)` helper, already introduced for query consumers, at project workflow error boundaries.

Fresh concrete repro (Node, worktree root; no server/provider/user data):

```javascript
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('rag/static/pages/intake.js', 'utf8');
const code = source.slice(source.indexOf('    async function startGeneration()'),
  source.indexOf('    /* ──────────── (b) IMPORTA DOCUMENTI'));
const nodes = new Map();
for (const id of ['gen-descrizione','gen-nfile','gen-categoria','gen-btn','gen-status','gen-result'])
  nodes.set(id, {value: id === 'gen-nfile' ? '1' : 'synthetic fixture'});
const context = {
  document: {getElementById: id => nodes.get(id)},
  fetch: async () => ({ok: false, status: 409, json: async () => ({
    detail: {code:'project_not_indexed', message:'Project has no index'}
  })})
};
vm.createContext(context);
vm.runInContext(code, context);
(async () => {
  await context.startGeneration();
  const actual = nodes.get('gen-status').textContent;
  assert.equal(actual, 'Errore: [object Object]');
  console.log(actual);
})().catch(error => { console.error(error); process.exitCode = 1; });
```

Observed: exit 0 and `Errore: [object Object]`. This reproduces the actual UI function, not just JavaScript's generic object conversion. Task 4 is still unstable; the finding concerns its frozen structured-error contract consumed by existing UI. PM notified for ownership/ruling. No product files edited.

## Additional workflow finding — P2, blocking lazy loads on the event loop

Working-tree inspection (Task 4, not yet committed): `rag/api/routes_intake.py:247-248` calls synchronous `require_snapshot(project)` and `ensure_shared_resources()` directly from `async def start_generation`. `start_project_brief` also loads the snapshot directly; several async pipeline handlers repeat these calls. These helpers acquire locks and can load the full on-disk snapshot or initialize BGE. A first workflow request can therefore block all HTTP handling, including liveness and another project's query, for the load duration. The Task 3 retrieval routes already offload these helpers with `await run_in_threadpool(...)`.

Repro ran the actual `start_generation` handler, substituting only its blocking dependency work and preventing job dispatch. Two synchronous loader sentinels of 120ms each recorded the current thread. A concurrently scheduled 10ms asyncio heartbeat ran after 241ms. Both dependency functions ran on the event-loop thread. No model/provider/index data was accessed.

```python
import asyncio
import threading
import time
from api import routes_intake as routes
seen = []
def load(project):
    seen.append(('snapshot', threading.get_ident()))
    time.sleep(0.12)
    return object()
def resources():
    seen.append(('resources', threading.get_ident()))
    time.sleep(0.12)
routes.require_snapshot = load
routes.ensure_shared_resources = resources
routes._project_manager = lambda *args: object()
routes._start_job = lambda *args: object()
routes._job_content = lambda job: {'status': 'running'}
async def main():
    loop_thread = threading.get_ident()
    started = time.monotonic()
    ticks = []
    async def heartbeat():
        await asyncio.sleep(0.01)
        ticks.append(time.monotonic() - started)
    beat = asyncio.create_task(heartbeat())
    await asyncio.sleep(0)
    response = await routes.start_generation(
        routes.GenerateRequest(descrizione='synthetic fixture'), project=object())
    await beat
    assert response.status_code == 202
    assert all(thread == loop_thread for _, thread in seen)
    assert ticks[0] >= 0.20
    print({'same_event_loop_thread': True,
           'heartbeat_delay_seconds': round(ticks[0], 3),
           'loaders': [name for name, _ in seen]})
asyncio.run(main())
```

Observed: exit 0, `{'same_event_loop_thread': True, 'heartbeat_delay_seconds': 0.241, 'loaders': ['snapshot', 'resources']}`. Remedy: offload these blocking helpers at async route boundaries, keeping synchronous worker callbacks synchronous. PM notified. No product edit.

"""HTTP project selection must never borrow another project's runtime."""
import json

import pytest
from fastapi.testclient import TestClient

from api import deps
from core.projects import ProjectRegistry


@pytest.fixture
def client(tmp_path, monkeypatch):
    import server
    registry = ProjectRegistry(tmp_path / "projects", bootstrap_legacy=False)
    monkeypatch.setattr(deps, "project_registry", lambda: registry, raising=False)
    monkeypatch.setattr(deps, "_project_states", {}, raising=False)
    monkeypatch.setattr(deps, "_snapshots", __import__('collections').OrderedDict(), raising=False)
    monkeypatch.setitem(deps.state, "snapshot", None)
    monkeypatch.setitem(deps.state, "qdrant", None)
    monkeypatch.setitem(deps.state, "embed_model", None)
    monkeypatch.setattr(deps, "BGEM3FlagModel", lambda *a, **k: pytest.fail("eager model load"))
    with TestClient(server.app, base_url="http://127.0.0.1", client=("127.0.0.1", 1234)) as value:
        yield value, registry


def test_empty_shell_registry_and_liveness(client):
    http, registry = client
    assert http.get("/").status_code == 200
    assert http.get("/api/projects").json() == {"projects": [], "read_only": False}
    assert http.get("/api/health/live").json()["status"] == "ok"
    response = http.get("/api/retrieve?q=same")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "project_required"


def test_historical_legacy_has_migration_diagnostics(client):
    http, registry = client
    registry.registry_path.write_text(json.dumps({"schema_version": 1, "projects": [{
        "id": "legacy", "name": "Initial", "root": str(registry._legacy.root), "legacy": True
    }]}))
    result = http.get("/api/projects").json()["projects"][0]
    assert result["index_status"] == "error"
    assert result["error"] == "project_migration_required"
    response = http.get("/api/retrieve?q=same")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "project_migration_required"


def test_create_selection_no_fallback_and_unindexed(client):
    http, registry = client
    created = http.post("/api/projects", json={"name": "Project A"})
    assert created.status_code == 201
    metadata = created.json()
    assert metadata["index_status"] == "not_indexed"
    assert metadata["index_version"] is None
    assert registry.get(metadata["id"]).name == "Project A"
    for project_id, status, code in [(None, 409, "project_required"),
                                   ("../bad", 422, "invalid_project_id"),
                                   ("f" * 32, 404, "project_not_found"),
                                   (metadata["id"], 409, "project_not_indexed")]:
        headers = {"X-VibeCraft-Project": project_id} if project_id else {}
        response = http.get("/api/retrieve?q=same", headers=headers)
        assert (response.status_code, response.json()["detail"]["code"]) == (status, code)


def test_bad_manifest_does_not_hide_healthy_project(client):
    http, registry = client
    a, b = registry.create("A"), registry.create("B")
    (a.root / "project.yaml").write_text("[broken", encoding="utf-8")
    response = http.get("/api/projects")
    assert response.status_code == 200
    rows = {r["id"]: r for r in response.json()["projects"]}
    assert rows[a.id]["index_status"] == "error"
    assert rows[b.id]["index_status"] == "not_indexed"
    assert http.get("/api/projects/" + b.id).status_code == 200
    registry.registry_path.write_text("{broken", encoding="utf-8")
    assert http.get("/api/projects").status_code == 503
    assert http.get("/api/health/live").status_code == 200


def test_registry_mutations_cross_site_and_local_bind(client, monkeypatch):
    http, registry = client
    assert http.post("/api/projects", json={"name": "A"},
                     headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    monkeypatch.setattr(deps, "SERVER_BIND_IS_LOCAL", False)
    assert http.post("/api/projects/register", json={"root": str(registry.projects_dir)}).status_code == 403


def test_remote_registration_confines_before_manifest_read(client, monkeypatch, tmp_path):
    from api import routes_projects
    import server
    http, registry = client
    # Real roots/manifests; registration must not inspect a denied host path.
    inside = ProjectRegistry(registry.projects_dir / "mounted", bootstrap_legacy=False).create("Mounted")
    outside = ProjectRegistry(tmp_path / "outside", bootstrap_legacy=False).create("Outside")
    monkeypatch.setattr(deps, "SERVER_BIND_IS_LOCAL", False)
    monkeypatch.setattr(deps, "API_KEY", "managed-test-key")
    remote = TestClient(server.app, base_url="http://127.0.0.1", client=("192.0.2.1", 1234))
    headers = {"X-API-Key": "managed-test-key"}
    assert remote.post("/api/projects/register", json={"root": str(inside.root)}).status_code == 401
    assert http.post("/api/projects/register", json={"root": str(inside.root)},
                     headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert remote.post("/api/projects/register", json={"root": str(inside.root)}, headers=headers).status_code == 201
    original = registry.register
    monkeypatch.setattr(registry, "register", lambda root: pytest.fail("denied root reached manifest reader"))
    for root in (outside.root, registry.projects_dir, inside.root / ".." / inside.root.name):
        assert remote.post("/api/projects/register", json={"root": str(root)}, headers=headers).status_code == 403
    monkeypatch.setattr(registry, "register", original)
    monkeypatch.setattr(deps, "SERVER_BIND_IS_LOCAL", True)
    assert http.post("/api/projects/register", json={"root": str(outside.root)}).status_code == 201
    monkeypatch.setattr(routes_projects, "ROLE", "reader")
    assert http.post("/api/projects/register", json={"root": str(inside.root)}).status_code == 403


def test_remote_registration_rejects_directory_links(client, monkeypatch, tmp_path):
    import os
    import subprocess
    http, registry = client
    outside = ProjectRegistry(tmp_path / "outside", bootstrap_legacy=False).create("Outside")
    registry.projects_dir.mkdir(exist_ok=True)
    linked = registry.projects_dir / "linked"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(linked), str(outside.root)], check=True, capture_output=True)
    else:
        linked.symlink_to(outside.root, target_is_directory=True)
    try:
        monkeypatch.setattr(deps, "SERVER_BIND_IS_LOCAL", False)
        monkeypatch.setattr(registry, "register", lambda root: pytest.fail("link reached manifest reader"))
        assert http.post("/api/projects/register", json={"root": str(linked)}).status_code == 403
    finally:
        linked.rmdir() if os.name == "nt" else linked.unlink()


def test_remote_metadata_and_errors_never_expose_paths(client, monkeypatch):
    http, registry = client
    import server
    a = registry.create("A")
    monkeypatch.setattr(deps, "API_KEY", "secret")
    remote = TestClient(server.app, base_url="http://127.0.0.1", client=("192.0.2.1", 1234))
    assert remote.get("/api/projects").status_code == 401
    headers = {"X-API-Key": "secret"}
    data = remote.get("/api/projects/" + a.id, headers=headers).json()
    assert "root" not in data and "settings" not in data
    (a.root / "project.yaml").unlink()
    response = remote.get("/api/projects/" + a.id, headers=headers)
    assert response.status_code == 503
    assert str(a.root) not in json.dumps(response.json())

class _Embed:
    def encode(self, texts, **kwargs):
        import numpy as np
        return {"dense_vecs": np.ones((len(texts), 2), dtype=np.float32),
                "lexical_weights": [{1: 1.0} for _ in texts],
                "colbert_vecs": [np.ones((1, 2), dtype=np.float32) for _ in texts]}


class _Qdrant:
    def query_points(self, **kwargs):
        from types import SimpleNamespace
        return SimpleNamespace(points=[SimpleNamespace(score=1.0, payload={
            "chunk_id": "same.md#1", "doc_id": "same.md", "classification": "POLICY"})])

    def get_collections(self):
        from types import SimpleNamespace
        return SimpleNamespace(collections=[])

    def close(self):
        pass


@pytest.fixture
def ab(client, monkeypatch):
    from test_project_runtime import indexed
    http, registry = client
    a, b = registry.create("A"), registry.create("B")
    indexed(a, "CORPUS_ALPHA")
    indexed(b, "CORPUS_BETA")
    monkeypatch.setitem(deps.state, "qdrant", _Qdrant())
    monkeypatch.setitem(deps.state, "embed_model", _Embed())
    # Gli ID nascono dal nome ("A", "B"), uguali in ogni test: la cache /ask dell'app
    # (chiave progetto + versione indice) non deve portare risposte da un test all'altro.
    from core import ask_cache
    ask_cache.for_app(http.app).clear()
    return http, a, b


def test_retrieve_graph_and_cache_keep_same_version_projects_apart(ab, monkeypatch):
    from core import llm
    http, a, b = ab
    calls = []

    async def answer(prompt, **kwargs):
        calls.append(prompt)
        return "A" if "CORPUS_ALPHA" in prompt else "B"

    monkeypatch.setattr(llm, "agenerate", answer)
    for project, text in [(a, "CORPUS_ALPHA"), (b, "CORPUS_BETA")]:
        headers = {"X-VibeCraft-Project": project.id}
        result = http.get("/api/retrieve?q=same&include_text=true", headers=headers).json()
        assert result["results"][0]["text"] == text
        assert result["project_id"] == project.id and result["index_version"] == "v1"
        graph = http.get("/api/graph/all", headers=headers).json()
        assert graph["project_id"] == project.id and graph["index_version"] == "v1"
        assert graph["nodes"][0]["description"] == text
        # use_thread=false: append del filo cambierebbe il fingerprint e annullerebbe l'hit.
        ask_body = {"question": "Come funziona il requisito?", "use_thread": False}
        result = http.post("/ask", json=ask_body, headers=headers).json()
        assert result["answer"] == project.name
        assert result["cached"] is False
        cached = http.post("/ask", json=ask_body, headers=headers).json()
        assert cached["cached"] is True and cached["answer"] == project.name
        assert cached["project_id"] == project.id
    assert len(calls) == 2


def test_stream_captures_a_while_b_loads_and_a_is_evicted(ab, client, monkeypatch):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from core import llm
    from test_project_runtime import indexed
    http, a, b = ab
    registry = client[1]
    started, release = threading.Event(), threading.Event()
    c = registry.create("C")
    indexed(c, "CORPUS_GAMMA")

    async def stream(prompt, **kwargs):
        assert "CORPUS_ALPHA" in prompt
        yield "A"
        started.set()
        await asyncio.to_thread(release.wait, 10)
        yield " captured"

    monkeypatch.setattr(llm, "astream", stream)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(http.post, "/ask", json={"question": "Come funziona?", "stream": True},
                             headers={"X-VibeCraft-Project": a.id})
        try:
            assert started.wait(10)
            for project in (b, c):
                assert http.get("/api/graph/all", headers={"X-VibeCraft-Project": project.id}).status_code == 200
            assert a.id not in deps._snapshots
            indexed(a, "NEW_A", version="v2")
            assert deps.reload_index_state(a) == "v2"
        finally:
            release.set()
        events = [json.loads(line) for line in future.result(timeout=10).text.splitlines()]
    assert events[0]["project_id"] == a.id
    assert events[-1]["value"]["project_id"] == a.id
    assert events[-1]["value"]["answer"] == "A captured"
    assert events[-1]["value"]["index_version"] == "v1"
    assert "CORPUS_ALPHA" in events[-1]["value"]["graph_context"]["context_text"]


def test_reader_empty_boot_and_selected_marker_validation(ab, monkeypatch):
    from core.artifacts import IMMUTABLE_MARKER_FILENAME
    from core import config
    http, a, b = ab
    monkeypatch.setattr(deps, "ROLE", "reader")
    monkeypatch.setattr(deps, "API_KEY", "reader-secret")
    monkeypatch.setattr(config, "ROLE", "reader")
    headers = {"X-API-Key": "reader-secret", "X-VibeCraft-Project": a.id}
    assert http.get("/api/graph/all", headers=headers).status_code == 200
    (b.database_dir / IMMUTABLE_MARKER_FILENAME).unlink()
    headers["X-VibeCraft-Project"] = b.id
    assert http.get("/api/graph/all", headers=headers).status_code == 503
    assert http.post("/api/projects", headers=headers, json={"name": "forbidden"}).status_code == 409
    assert http.get("/api/health/live", headers=headers).status_code == 200


def test_health_deps_creates_qdrant_client_and_skips_index_scan(client, monkeypatch):
    from api import routes_health

    class FakeQdrant:
        def __init__(self, **_):
            pass

        def get_collections(self):
            return []

        def close(self):
            pass

    http, _ = client
    monkeypatch.setattr(deps, "QdrantClient", FakeQdrant)
    monkeypatch.setattr(routes_health, "check_ollama", lambda: False)
    monkeypatch.setattr(routes_health, "index_status", lambda **_: pytest.fail("index scan"), raising=False)
    provider = {"active_provider": "ollama"}
    monkeypatch.setattr(routes_health.llm, "_llm_settings",
                        lambda: __import__("types").SimpleNamespace(**provider))
    # Senza progetto e prima di qualunque richiesta indicizzata (state["qdrant"] è None).
    assert http.get("/api/health/deps").json() == {"qdrant": True, "ollama": False}
    provider["active_provider"] = "anthropic"  # Ollama spento ma non in uso: niente allarme
    assert http.get("/api/health/deps").json() == {"qdrant": True, "ollama": None}


def test_index_health_and_history_are_project_local(ab, monkeypatch):
    from api import routes_health
    from datetime import datetime, timezone
    http, a, b = ab
    monkeypatch.setattr(routes_health, "check_ollama", lambda: True)
    row = {"timestamp": datetime.now(timezone.utc).isoformat(), "recall": {"recall@2": 0.7}}
    (a.database_dir / "eval" / "history.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    (a.database_dir / "alerts.jsonl").write_text(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(), "source": "test", "message": "Alert A"}) + "\n", encoding="utf-8")
    for project, expected in ((a, 1), (b, 0)):
        response = http.get("/api/eval/history", headers={"X-VibeCraft-Project": project.id})
        assert response.status_code == 200
        assert response.json()["n"] == expected
        assert response.json()["project_id"] == project.id
        health = http.get("/api/health", headers={"X-VibeCraft-Project": project.id})
        assert health.status_code == 200, health.text
        assert health.json()["project_id"] == project.id
        assert bool(health.json()["last_alert"]) == bool(expected)


def test_project_code_search_defaults_are_local(ab):
    import yaml
    http, a, b = ab
    manifest_path = a.root / "project.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["settings"] = {"retrieval": {"code_search_api_max_k": 3,
        "code_search_min_score": 0.8, "code_search_max_per_file": 1, "code_search_api_snippet_chars": 5}}
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    result_a = http.get("/api/code/search?q=same&snippet=true", headers={"X-VibeCraft-Project": a.id}).json()
    result_b = http.get("/api/code/search?q=same&snippet=true", headers={"X-VibeCraft-Project": b.id}).json()
    assert result_a["limits"] == {"k": 3, "min_score": 0.8, "max_per_file": 1,
                                  "snippet_chars": 5, "exhaustive": False}
    assert result_b["limits"]["k"] == 8


def test_manifest_sidecar_link_never_reads_other_project(ab):
    from core.artifacts import manifest_path
    http, a, b = ab
    target = manifest_path("v1", project=b)
    path = manifest_path("v1", project=a)
    before = path.read_bytes()
    path.unlink()
    try:
        path.symlink_to(target)
    except OSError as exc:
        path.write_bytes(before)
        pytest.skip(f"File symlink unavailable: {exc}")
    try:
        metadata = http.get("/api/projects/" + a.id)
        assert metadata.json()["index_status"] == "error"
        response = http.get("/api/graph/all", headers={"X-VibeCraft-Project": a.id})
        assert response.status_code == 503
        assert http.get("/api/graph/all", headers={"X-VibeCraft-Project": b.id}).status_code == 200
    finally:
        path.unlink()
        path.write_bytes(before)


def test_indexing_status_is_local_to_running_project(client):
    from types import SimpleNamespace
    http, registry = client
    a, b = registry.create("A"), registry.create("B")
    deps.project_runtime(a)["reindex_manager"] = SimpleNamespace(is_running=True, pending_id=None)
    assert http.get("/api/projects/" + a.id).json()["index_status"] == "indexing"
    assert http.get("/api/projects/" + b.id).json()["index_status"] == "not_indexed"


def test_real_index_metadata_reports_staleness_for_captured_version(client, monkeypatch):
    from core import artifacts, indexing
    from test_project_runtime import indexed
    http, registry = client
    a = registry.create("A")
    doc = a.docs_dir / "same.md"
    doc.write_text("original", encoding="utf-8")
    indexed(a, "original")
    indexing.write_index_manifest(1, version="v1", qdrant_collection=a.collection_name + "__v1",
                                  immutable=True, project=a)
    initial = http.get("/api/projects/" + a.id).json()
    assert initial["index_version"] == "v1" and initial["stale"] is False
    doc.write_text("changed", encoding="utf-8")
    assert http.get("/api/projects/" + a.id).json()["stale"] is True
    # Promotion between metadata capture and staleness calculation must not label
    # v1 with the fresh v2 document hashes.
    indexed(a, "changed", version="v2")
    indexing.write_index_manifest(1, version="v2", qdrant_collection=a.collection_name + "__v2",
                                  immutable=True, project=a)
    artifacts.promote_version("v1", project=a)
    original = indexing.index_status

    def promoted(*args, **kwargs):
        artifacts.promote_version("v2", project=a)
        return original(*args, **kwargs)

    monkeypatch.setattr(indexing, "index_status", promoted)
    captured = http.get("/api/projects/" + a.id).json()
    assert captured["index_version"] == "v1" and captured["stale"] is True


def test_fast_project_list_defers_staleness(client, monkeypatch):
    """?stale=0 è la prima richiesta della shell: deve rispondere senza calcolare gli hash
    di docs/ e code/ e dichiarare che lo stato arriva dopo, non che manca."""
    from core import indexing
    from test_project_runtime import indexed
    http, registry = client
    a = registry.create("A")
    (a.docs_dir / "same.md").write_text("original", encoding="utf-8")
    indexed(a, "original")
    indexing.write_index_manifest(1, version="v1", qdrant_collection=a.collection_name + "__v1",
                                  immutable=True, project=a)

    def forbidden(*args, **kwargs):
        raise AssertionError("index_status non deve girare con ?stale=0")

    original = indexing.index_status
    monkeypatch.setattr(indexing, "index_status", forbidden)
    fast = http.get("/api/projects", params={"stale": "0"}).json()["projects"][0]
    assert fast["index_status"] == "ready" and fast["stale"] is None and fast["stale_pending"] is True
    monkeypatch.setattr(indexing, "index_status", original)
    full = http.get("/api/projects").json()["projects"][0]
    assert full["stale"] is False and "stale_pending" not in full


def test_status_hash_cache_reuses_digest_until_file_changes(tmp_path, monkeypatch):
    import os
    from core import indexing
    source = tmp_path / "a.py"
    source.write_text("value = 1", encoding="utf-8")
    calls = []
    real = indexing.sha256_file
    monkeypatch.setattr(indexing, "sha256_file", lambda path: calls.append(path) or real(path))
    monkeypatch.setattr(indexing, "_STATUS_HASH_CACHE", {})
    first = indexing._status_sha256(source)
    assert indexing._status_sha256(source) == first and len(calls) == 1
    # Stessa dimensione, contenuto diverso: cambia mtime e il digest va ricalcolato.
    source.write_text("value = 2", encoding="utf-8")
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert indexing._status_sha256(source) == real(source) != first and len(calls) == 2


def test_ask_cache_settings_change_same_project_query_and_version(ab, monkeypatch):
    import yaml
    from core import llm
    http, a, _ = ab
    calls = []

    async def answer(prompt, **kwargs):
        calls.append(prompt)
        return f"answer {len(calls)}"

    monkeypatch.setattr(llm, "agenerate", answer)
    headers = {"X-VibeCraft-Project": a.id}
    # use_thread=false: bench isolati sul hit-rate storico della cache /ask.
    query = {"question": "Come funziona il requisito?", "use_thread": False}
    first = http.post("/ask", json=query, headers=headers).json()
    assert first["cached"] is False
    assert http.post("/ask", json=query, headers=headers).json()["cached"] is True
    path = a.root / "project.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for settings in ({"authority": {"boost_alpha": 0.1}},
                     {"retrieval": {"graph_context_max_chunks": 1}}):
        data["settings"] = settings
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        changed = http.post("/ask", json=query, headers=headers).json()
        assert changed["index_version"] == first["index_version"]
        assert changed["cached"] is False
        assert changed["answer"] != first["answer"]
        assert http.post("/ask", json=query, headers=headers).json()["cached"] is True
    assert len(calls) == 3


def test_legacy_ask_fallback_rejects_docs_junction_after_capture(ab, monkeypatch):
    import os
    import subprocess
    from dataclasses import replace
    from api import routes_retrieval
    from core import llm
    http, a, b = ab
    captured = replace(a, legacy=True)
    snapshot = replace(deps.require_snapshot(a), chunks={})
    monkeypatch.setattr(routes_retrieval, "get_project", lambda request: captured)
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: snapshot)
    prompts = []

    async def answer(prompt, **kwargs):
        prompts.append(prompt)
        return "unexpected foreign answer"

    monkeypatch.setattr(llm, "agenerate", answer)
    (b.docs_dir / "same.md").write_text("B private", encoding="utf-8")
    assert a.docs_dir.is_relative_to(a.root) and not list(a.docs_dir.iterdir())
    a.docs_dir.rmdir()  # Empty fixture directory only.
    try:
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(a.docs_dir), str(b.docs_dir)],
                           check=True, capture_output=True)
        else:
            a.docs_dir.symlink_to(b.docs_dir, target_is_directory=True)
        response = http.post("/ask", json={"question": "Come funziona il requisito?"},
                             headers={"X-VibeCraft-Project": a.id})
        assert response.status_code == 503
        assert "B private" not in response.text
        assert prompts == []
    finally:
        if a.docs_dir.is_junction():
            a.docs_dir.rmdir()
        elif a.docs_dir.is_symlink():
            a.docs_dir.unlink()
        a.docs_dir.mkdir(exist_ok=True)

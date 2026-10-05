"""Actual HTTP, storage, jobs and Qdrant; only model/provider boundaries are fake."""
from collections import OrderedDict
from functools import partial
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time

import httpx
import numpy as np
import pytest
from qdrant_client import QdrantClient
import uvicorn

import agent_runners
from api import deps, routes_pipeline, routes_reindex
from core import artifacts, indexing, llm, pipeline, qdrant_versions
from core.config import DENSE_DIM
from core.projects import ProjectRegistry


class FixtureEmbedding:
    """Uniform positive vectors make same-query results depend on real collection scope."""
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def encode(self, texts, **kwargs):
        if any("HELD_ALPHA_REBUILD" in text for text in texts):
            self.entered.set()
            assert self.release.wait(20), "controlled indexing provider was not released"
        dense = np.zeros((len(texts), DENSE_DIM), dtype=np.float32)
        dense[:, 0] = 1
        result = {"dense_vecs": dense}
        if kwargs.get("return_sparse"):
            result["lexical_weights"] = [{1: 1.0} for _ in texts]
        if kwargs.get("return_colbert_vecs"):
            result["colbert_vecs"] = [v[None, :] for v in dense]
        return result


@pytest.fixture
def integrated_server(tmp_path, monkeypatch):
    from server import app
    # Historical adapters must restore their exact scope; do not conceal a leaked override.
    assert not app.dependency_overrides, "historical HTTP fixture leaked dependency overrides"
    url = os.environ.get("VIBECRAFT_TEST_QDRANT_URL")
    if not url:
        if os.environ.get("VIBECRAFT_REQUIRE_QDRANT") == "1":
            pytest.fail("Dedicated Qdrant URL required")
        pytest.skip("Dedicated Qdrant URL absent")
    registry = ProjectRegistry(tmp_path / "managed projects", bootstrap_legacy=False)
    monkeypatch.setattr(deps, "project_registry", lambda: registry)
    monkeypatch.setattr(deps, "_project_states", {})
    monkeypatch.setattr(deps, "_snapshots", OrderedDict())
    monkeypatch.setattr(deps, "API_KEY", "integration-fixture-key")
    monkeypatch.setattr(deps, "ROLE", "writer")
    monkeypatch.setattr(deps, "SERVER_BIND_IS_LOCAL", True)
    qdrant, embed = QdrantClient(url=url), FixtureEmbedding()
    monkeypatch.setitem(deps.state, "qdrant", qdrant)
    monkeypatch.setitem(deps.state, "embed_model", embed)
    monkeypatch.setattr(indexing, "_new_version_name", lambda **kwargs: "v1")
    prompts = []

    async def generate(prompt, *, purpose, **kwargs):
        prompts.append((purpose, prompt))
        if purpose == "validate":
            return json.dumps({"summary": "Fixture validation", "findings": [], "suggestions": []})
        assert purpose == "ask"
        found = [text for text in ("ALPHA_SENTINEL", "BETA_SENTINEL") if text in prompt]
        assert len(found) == 1, "actual retrieved context crossed project boundaries"
        return found[0]

    async def stream(prompt, *, purpose, resolved):
        yield await generate(prompt, purpose=purpose)

    monkeypatch.setattr(llm, "agenerate", generate)
    monkeypatch.setattr(llm, "astream", stream)

    def chat(model, messages, tools):
        if len(messages) == 2:
            assert "ALPHA_SENTINEL" in messages[1]["content"]
            assert "BETA_SENTINEL" not in messages[1]["content"]
            return {"message": {"tool_calls": [{"function": {"name": "write_file",
                "arguments": {"path": "runner.txt", "content": "ALPHA_RUNNER"}}}]}}
        assert messages[-1]["content"].startswith("scritto")
        return {"message": {"content": '{"open_points":[]}'}}

    monkeypatch.setattr(agent_runners, "run_local", partial(agent_runners.run_local, chat=chat))
    # Metadata's provider discovery is also bounded; no Ollama requests during browser startup.
    class Tags:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return b'{"models":[{"name":"fixture-model"}]}'
    monkeypatch.setattr(agent_runners.urllib.request, "urlopen", lambda *args, **kwargs: Tags())
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="off", log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}",
                          headers={"X-API-Key": "integration-fixture-key"}, timeout=30)
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(.01)
        assert server.started
        yield client, registry, qdrant, embed, prompts
    finally:
        embed.release.set()
        for project in registry.list():
            manager = deps.project_runtime(project).get("reindex_manager")
            if manager:
                assert manager.join_all(20)
        client.close()
        server.should_exit = True
        thread.join(10)
        assert not thread.is_alive()
        for project in registry.list():
            snapshot = deps.current_snapshot(project)
            if snapshot:
                snapshot.colbert_store.close()
                snapshot.version_lease.close()
            # Exact UUID namespace admitted by this fixture, never generic-prefix cleanup.
            owned = {project.collection_name + "__" + version for version in ("v1", "v2", "v3", "unused")}
            for collection in qdrant.get_collections().collections:
                if collection.name in owned:
                    qdrant.delete_collection(collection.name)
        qdrant.close()


def test_actual_http_projects_workflows_jobs_qdrant_and_browser(integrated_server, tmp_path, monkeypatch):
    client, registry, qdrant, embed, prompts = integrated_server
    projects = []
    for name in ("A", "B"):
        response = client.post("/api/projects", json={"name": name})
        assert response.status_code == 201, response.text
        project = registry.get(response.json()["id"])
        projects.append(project)
        for directory in (project.code_dir, project.docs_dir, project.changes_dir, project.database_dir):
            assert directory.is_dir()
    a, b = projects
    def headers(project):
        return {"X-VibeCraft-Project": project.id}
    for project, sentinel in ((a, "ALPHA_SENTINEL"), (b, "BETA_SENTINEL")):
        (project.docs_dir / "same.md").write_text("# Shared title\n\n" + sentinel, encoding="utf-8")
        (project.code_dir / "backend").mkdir()
        (project.code_dir / "backend/same.py").write_text(f"def shared(): return '{sentinel}'\n", encoding="utf-8")
        assert indexing.build_graph_and_index(qdrant, embed, project=project) == "v1"

    def ask(project, sentinel):
        response = client.post("/ask", headers=headers(project), json={"question": "same question"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["answer"] == sentinel and body["project_id"] == project.id and body["index_version"] == "v1"
        return body

    assert not ask(a, "ALPHA_SENTINEL").get("cached")
    assert not ask(b, "BETA_SENTINEL").get("cached")
    assert ask(a, "ALPHA_SENTINEL")["cached"]
    assert [purpose for purpose, _ in prompts] == ["ask", "ask"]

    # Actual plan cache, copy/journal, writer lock, delta and snapshot reload.
    monkeypatch.setattr(indexing, "_new_version_name", lambda **kwargs: "v2")
    source = tmp_path / "import source"
    source.mkdir()
    (source / "imported.py").write_text("def imported(): return 'ALPHA_IMPORT'\n", encoding="utf-8")
    planned = client.post("/api/intake/project/plan", headers=headers(a),
                          json={"path": str(source), "target": "backend"})
    assert planned.status_code == 200, planned.text
    payload = {"plan_id": planned.json()["plan_id"]}
    assert client.post("/api/intake/project/apply", headers=headers(b), json=payload).status_code == 404
    applied = client.post("/api/intake/project/apply", headers=headers(a), json=payload)
    assert applied.status_code == 200, applied.text
    assert (a.code_dir / "backend" / source.name / "imported.py").read_bytes() == (source / "imported.py").read_bytes()
    assert not (b.code_dir / "backend" / source.name / "imported.py").exists()

    canvas = "\n".join("## " + section for section in pipeline.CANVAS_SECTIONS)
    spec = ('```gherkin\nSCENARIO: S01 - Invio richiesta\n  GIVEN una richiesta pronta\n'
            '  WHEN viene inviata\n  THEN viene registrata\n```\n'
            '```gherkin\nSCENARIO: S02 - Errore richiesta\n  GIVEN una richiesta incompleta\n'
            '  WHEN viene inviata\n  THEN viene rifiutata\n```\n'
            '## 4. Punti aperti\n```json\n{"open_points": []}\n```')
    validated = {}
    for project in projects:
        sentinel = "ALPHA_SENTINEL" if project == a else "BETA_SENTINEL"
        for filename, text in (("canvas.md", canvas + "\n" + sentinel), ("spec.md", spec)):
            saved = client.post("/api/pipeline/file/save", headers=headers(project),
                json={"feature": "same-feature", "name": filename, "content": text})
            assert saved.status_code == 200, saved.text
        response = client.post("/api/pipeline/validate", headers=headers(project), json={"feature": "same-feature"})
        assert response.status_code == 200, response.text
        validated[project.id] = response.json()
        assert response.json()["gate"]["allowed"], response.text
        record = routes_pipeline.project_store(project).read_validation("same-feature", response.json()["validation_id"])
        assert record.sources.index_version == ("v2" if project == a else "v1")
        assert record.sources.provided and all(sentinel in source.text_supplied for source in record.sources.provided)
    run = {"runner": "local", "model": "fixture-model", "mode": "agentic", "feature": "same-feature",
           "validation_id": validated[a.id]["validation_id"], "max_attempts": 1}
    assert client.post("/api/pipeline/agent/run", headers=headers(b), json=run).status_code == 409
    response = client.post("/api/pipeline/agent/run", headers=headers(a), json=run)
    assert response.status_code == 200, response.text
    assert any(json.loads(line).get("type") == "result" for line in response.text.splitlines())
    assert (a.code_dir / "runner.txt").read_text() == "ALPHA_RUNNER"
    assert not (b.code_dir / "runner.txt").exists()
    assert routes_pipeline.project_store(b).read_validation("same-feature", run["validation_id"]) is None

    b_pointer = (b.database_dir / "CURRENT").read_bytes()
    b_hashes = artifacts.artifact_hashes("v1", project=b)
    b_alias = qdrant_versions._read_alias_target(qdrant, b.collection_name)
    b_vectors = qdrant.scroll(b_alias, with_vectors=True, limit=100)[0]
    monkeypatch.setattr(indexing, "_new_version_name", lambda **kwargs: "v3")
    (a.docs_dir / "same.md").write_text("# Shared title\n\nALPHA_SENTINEL HELD_ALPHA_REBUILD", encoding="utf-8")
    started = client.post("/api/reindex", headers=headers(a), json={"full": True})
    assert started.status_code == 202, started.text
    job_id = started.json()["job_id"]
    try:
        assert embed.entered.wait(10)
        assert client.get("/api/reindex/" + job_id, headers=headers(b)).status_code == 404
        assert client.get("/api/projects/" + b.id).json()["index_status"] == "ready"
        retrieved = client.get("/api/retrieve", headers=headers(b), params={"q": "same question", "include_text": True})
        assert retrieved.status_code == 200 and "BETA_SENTINEL" in retrieved.text, retrieved.text
        assert "ALPHA_SENTINEL" not in retrieved.text
        ask(b, "BETA_SENTINEL")
        assert (b.database_dir / "CURRENT").read_bytes() == b_pointer
    finally:
        embed.release.set()
    assert routes_reindex.project_manager(a).join_all(20)
    completed = client.get("/api/reindex/" + job_id, headers=headers(a)).json()
    assert completed["status"] == "completed" and completed["published_token"] == "v3", completed
    assert deps.current_snapshot(a).version == "v3" and deps.current_snapshot(b).version == "v1"
    journal = (a.database_dir / "reindex_jobs.jsonl").read_text(encoding="utf-8")
    assert job_id in journal and not (b.database_dir / "reindex_jobs.jsonl").exists()

    rollback = client.post("/api/index/rollback", headers=headers(a), json={"version": "v1"})
    assert rollback.status_code == 200, rollback.text
    assert artifacts.current_version(project=a) == "v1"
    orphan = a.collection_name + "__unused"
    indexing._ensure_collection(qdrant, collection_name=orphan)
    assert orphan in qdrant_versions.gc_orphaned_qdrant_collections(qdrant, project=a)
    assert (b.database_dir / "CURRENT").read_bytes() == b_pointer
    assert artifacts.artifact_hashes("v1", project=b) == b_hashes
    assert qdrant_versions._read_alias_target(qdrant, b.collection_name) == b_alias
    assert qdrant.scroll(b_alias, with_vectors=True, limit=100)[0] == b_vectors
    assert indexing.check_index_integrity(qdrant, project=b)["ok"]

    # CI installs its browser tooling after the Python gate. Enable for the combined gate.
    if os.environ.get("VIBECRAFT_INTEGRATION_BROWSER") == "1":
        node = shutil.which("node")
        assert node, "Node is required for the actual browser integration gate"
        existing = ProjectRegistry(tmp_path / "mounted existing", bootstrap_legacy=False).create("UI opened")
        browser = subprocess.run([node, str(Path(__file__).with_name("project_integration_browser.cjs")),
            str(client.base_url).rstrip("/"), a.id, b.id, str(existing.root)], capture_output=True, text=True, timeout=60)
        assert browser.returncode == 0, browser.stdout + browser.stderr
        by_name = {project.name: project for project in registry.list()}
        assert set(by_name) == {"A", "B", "UI created", "UI opened"}
        assert by_name["UI opened"].root == existing.root
        assert len({project.root for project in by_name.values()}) == 4
        for name in ("UI created", "UI opened"):
            project = by_name[name]
            assert all(directory.is_dir() for directory in (
                project.code_dir, project.docs_dir, project.changes_dir, project.database_dir))
            assert artifacts.current_version(project=project) is None

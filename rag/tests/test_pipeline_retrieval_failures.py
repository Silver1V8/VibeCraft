"""Required retrieval failures never become empty context or persisted contracts."""
from dataclasses import replace
from types import SimpleNamespace

import networkx as nx
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import deps, routes_pipeline
from core import pipeline
from core.projects import legacy_project_context


SPEC = "```gherkin\nSCENARIO: S01 - Invio\n  GIVEN una richiesta\n  WHEN invia\n  THEN registra\n```\n"


class Model:
    def encode(self, questions, **kwargs):
        return dict(dense_vecs=[np.array([1.0])], lexical_weights=[{}],
                    colbert_vecs=[np.array([[1.0]])])


class Qdrant:
    def query_points(self, **kwargs):
        return SimpleNamespace(points=[])


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    project = replace(legacy_project_context(), root=tmp_path,
                      changes_dir=tmp_path / "changes", database_dir=tmp_path / "database")
    graph = nx.DiGraph()
    graph.add_node("spec.md", type="document")
    snap = SimpleNamespace(graph=graph, chunks={}, colbert_store={}, collection_name="candidate")
    monkeypatch.setattr(routes_pipeline, "require_snapshot", lambda project: snap)
    monkeypatch.setattr(routes_pipeline, "ensure_shared_resources", lambda: None)
    monkeypatch.setitem(deps.state, "qdrant", Qdrant())
    monkeypatch.setitem(deps.state, "embed_model", Model())
    monkeypatch.setattr(deps, "_project_states", {})
    application = FastAPI()
    application.include_router(routes_pipeline.router)
    application.dependency_overrides[deps.get_project] = lambda: project
    application.dependency_overrides[deps.require_api_key] = lambda: None
    folder = project.changes_dir / "feature-a"
    folder.mkdir(parents=True)
    originals = {name: f"original {name}" for name in
                 ("explore.md", "canvas.md", "spec.md", "spec.raw.md", "meta.json")}
    originals["meta.json"] = '{"governed_sources":["original.md"]}'
    for name, value in originals.items():
        (folder / name).write_text(value, encoding="utf-8")
    return TestClient(application), snap, folder, originals


def fail_retrieval(monkeypatch, snap, failure):
    def unavailable(*args, **kwargs):
        raise ConnectionError("private-host:6333 credential")

    if failure in ("qdrant", "embedding"):
        monkeypatch.setattr(deps.state["qdrant"] if failure == "qdrant" else deps.state["embed_model"],
                            "query_points" if failure == "qdrant" else "encode", unavailable)
    elif failure == "missing_model":
        monkeypatch.setitem(deps.state, "embed_model", None)
    elif failure == "missing_graph":
        snap.graph = None
    elif failure == "missing_text":
        monkeypatch.setattr(deps.state["qdrant"], "query_points", lambda **kwargs:
                            SimpleNamespace(points=[SimpleNamespace(score=0.9,
                                payload={"doc_id": "spec.md", "chunk_id": "spec.md#01"})]))


@pytest.mark.parametrize("stage", ["canvas", "propose"])
@pytest.mark.parametrize("failure", ["qdrant", "embedding", "missing_model", "missing_graph", "missing_text"])
def test_required_retrieval_failure_preserves_contract(runtime, monkeypatch, stage, failure):
    client, snap, folder, originals = runtime
    fail_retrieval(monkeypatch, snap, failure)

    async def forbidden_llm(*args, **kwargs):
        pytest.fail("Required retrieval failed but the LLM was called")

    monkeypatch.setattr(routes_pipeline.llm, "agenerate", forbidden_llm)
    response = client.post(f"/api/pipeline/{stage}/generate", json={
        "feature_name" if stage == "canvas" else "feature_folder": "feature-a"})
    assert response.status_code == 503, response.text
    assert "Retrieval" in response.json()["detail"]
    assert "private-host" not in response.text and "credential" not in response.text
    assert {name: (folder / name).read_text(encoding="utf-8") for name in originals} == originals


@pytest.mark.parametrize("stage", ["canvas", "propose"])
def test_zero_results_still_generates(runtime, monkeypatch, stage):
    client, _, folder, _ = runtime

    async def generate(prompt, purpose):
        return "## Requirements\nCanvas generato" if purpose == "canvas" else SPEC

    monkeypatch.setattr(routes_pipeline.llm, "agenerate", generate)
    response = client.post(f"/api/pipeline/{stage}/generate", json={
        "feature_name" if stage == "canvas" else "feature_folder": "feature-a"})
    assert response.status_code == 200, response.text
    filename = "canvas.md" if stage == "canvas" else "spec.md"
    assert (folder / filename).read_text(encoding="utf-8") == response.json()["content"]


@pytest.mark.parametrize("endpoint", ["canvas/dry-run", "agent-context", "export"])
@pytest.mark.parametrize("failure", ["qdrant", "embedding", "missing_model", "missing_graph"])
def test_read_consumers_report_search_failure(runtime, monkeypatch, endpoint, failure):
    client, snap, folder, originals = runtime
    fail_retrieval(monkeypatch, snap, failure)
    response = (client.post("/api/pipeline/canvas/dry-run", json={"feature_name": "feature-a"})
                if endpoint == "canvas/dry-run" else
                client.get(f"/api/pipeline/{endpoint}", params={"feature": "feature-a"}))
    assert response.status_code == 503, response.text
    assert "private-host" not in response.text
    assert {name: (folder / name).read_text(encoding="utf-8") for name in originals} == originals


def test_canvas_technical_retrieval_failure_preserves_metadata(runtime, monkeypatch):
    client, _, folder, originals = runtime

    def query(**kwargs):
        if kwargs.get("query_filter") is not None:
            raise ConnectionError("Technical search unavailable")
        return SimpleNamespace(points=[])

    monkeypatch.setattr(deps.state["qdrant"], "query_points", query)

    async def forbidden_llm(*args, **kwargs):
        pytest.fail("Technical retrieval failed but the LLM was called")

    monkeypatch.setattr(routes_pipeline.llm, "agenerate", forbidden_llm)
    response = client.post("/api/pipeline/canvas/generate",
                           json={"feature_name": "feature-a", "dev_type": "backend"})
    assert response.status_code == 503, response.text
    assert {name: (folder / name).read_text(encoding="utf-8") for name in originals} == originals


def test_offline_agent_context_declares_unavailable_retrieval(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "CHANGES_DIR", tmp_path)
    context = pipeline.build_agent_context("feature-a", graph=None, qdrant=None,
                                          embed_model=None, colbert_store={})
    assert any("non disponibile" in risk.lower() for risk in context["risks"])

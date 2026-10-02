"""GET /api/retrieve deve ricaricare lo snapshot come /ask.

Era l'unica route di retrieval a non chiamare `maybe_reload_graph()`: dopo una promozione
o un rollback l'alias Qdrant punta già alla collection nuova mentre i sidecar in memoria
restano vecchi, e il ranking esce da uno stato MISTO. È la route su cui gira eval.run,
quindi l'errore falsava proprio la misura con cui si decide se il sistema è migliorato —
in silenzio, con numeri plausibili. Vedi api/routes_retrieval.api_retrieve.
"""
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.deps as deps
from api import routes_retrieval
from core import retrieval


class _StubEmbed:
    def encode(self, texts, **kw):
        out = {"dense_vecs": np.zeros((len(texts), 2), dtype="float32")}
        if kw.get("return_sparse"):
            out["lexical_weights"] = [{} for _ in texts]
        if kw.get("return_colbert_vecs"):
            out["colbert_vecs"] = [np.zeros((1, 2), dtype="float32") for _ in texts]
        return out


@pytest.fixture
def retrieve_env(monkeypatch):
    """TestClient sulla sola route /api/retrieve, con un contatore sui reload."""
    monkeypatch.setattr(deps, "API_KEY", None)

    reloads = {"n": 0}


    snap = deps.IndexSnapshot(
        graph=None, colbert_store={}, chunks={}, rule_descriptions={},
        code_store={}, version="v-test", code_ids=[], code_matrix=None,
    )
    def capture(project):
        reloads["n"] += 1
        return snap

    monkeypatch.setattr(routes_retrieval, "require_snapshot", capture)
    monkeypatch.setattr(routes_retrieval, "qdrant_collection_for_version", lambda v, project=None: "test-collection")
    monkeypatch.setitem(deps.state, "qdrant", object())
    monkeypatch.setitem(deps.state, "embed_model", _StubEmbed())
    monkeypatch.setattr(retrieval, "hybrid_search", lambda *a, **kw: [])

    app = FastAPI()
    app.include_router(routes_retrieval.router)
    return TestClient(app, client=("127.0.0.1", 54321)), reloads


def test_retrieve_ricarica_lo_snapshot(retrieve_env):
    """Il test che prima falliva: il contatore restava a 0."""
    client, reloads = retrieve_env

    r = client.get("/api/retrieve", params={"q": "domanda", "k": 2})

    assert r.status_code == 200
    assert reloads["n"] == 1, "api_retrieve deve chiamare maybe_reload_graph come /ask"


def test_reload_index_state_returns_published_snapshot_token(monkeypatch):
    arts = type("Artifacts", (), {
        "graph": None, "colbert_store": {}, "chunks_store": {}, "code_store": {},
        "version": "v-published",
    })()
    monkeypatch.setattr(deps, "load_artifacts", lambda required=(), **_kwargs: arts)
    monkeypatch.setattr(deps, "load_rule_descriptions", lambda: {})
    assert deps.reload_index_state() == "v-published"


pytestmark = pytest.mark.usefixtures("legacy_http_project")

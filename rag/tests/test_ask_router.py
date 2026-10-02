"""Test M2: i due rami di POST /ask dietro il router deterministico.

Ramo "graph"  : domanda strutturale ⇒ status "graph_answer" con l'output di
                graph_ops.graph_query, SENZA chiamata LLM e SENZA hybrid_search;
                log M3 con retrieval_strategy=graph.
Ramo "hybrid" : domanda semantica ⇒ percorso attuale invariato (hybrid_search + LLM),
                log M3 con retrieval_strategy=hybrid.
Stesso pattern di fixture di test_ask_observability (stato del server, provider LLM e
hybrid_search finti), con contatori di chiamata per provare i "senza".
"""
import json
import logging

import networkx as nx
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.deps as deps
from api import routes_retrieval
from core import llm, retrieval

_CHUNK_ID = "spec.md#01-form"




class _StubEmbed:
    """Da S3 il route codifica SEMPRE la domanda (la forward pass avviene comunque dentro
    hybrid_search: spostarla nel route non costa nulla in più), quindi lo stato del server
    deve portare un embed_model che sappia rispondere a encode() anche con hybrid_search
    finto."""

    def encode(self, texts, **kw):
        out = {"dense_vecs": np.zeros((len(texts), 2), dtype="float32")}
        if kw.get("return_sparse"):
            out["lexical_weights"] = [{} for _ in texts]
        if kw.get("return_colbert_vecs"):
            out["colbert_vecs"] = [np.zeros((1, 2), dtype="float32") for _ in texts]
        return out


def _snapshot(version: str) -> deps.IndexSnapshot:
    g = nx.DiGraph()
    g.add_node("spec.md", type="document")
    g.add_node("glossario.md", type="document")
    g.add_node(_CHUNK_ID, type="chunk")
    g.add_edge("spec.md", _CHUNK_ID, relation="HAS_SECTION")
    return deps.IndexSnapshot(
        graph=g,
        colbert_store={},
        chunks={_CHUNK_ID: {"text": "testo della sezione"}},
        rule_descriptions={},
        code_store={},
        version=version,
        code_ids=[],
        code_matrix=None,
    )


@pytest.fixture(autouse=True)
def _clear_manifest_cache():
    deps._qdrant_collection_by_version.clear()
    yield
    deps._qdrant_collection_by_version.clear()


@pytest.fixture
def ask_env(monkeypatch, tmp_path):
    """TestClient sulla sola route /ask con contatori: calls["llm"] e calls["search"]
    contano le invocazioni del provider LLM finto e di hybrid_search."""
    monkeypatch.setattr(deps, "API_KEY", None)

    calls = {"llm": 0, "search": 0}

    settings = {"active_provider": "fake", "models": {"fake": "fake-model"}, "purposes": {}}
    monkeypatch.setitem(llm.config, "llm_settings", settings)

    def fake_provider(model, prompt, timeout):
        calls["llm"] += 1
        return "RISPOSTA"

    llm.register_provider("fake", fake_provider)

    version = "v-m2"
    snap = _snapshot(version)
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: snap)
    monkeypatch.setitem(deps.state, "qdrant", object())
    monkeypatch.setitem(deps.state, "embed_model", _StubEmbed())

    def fake_search(*a, **kw):
        calls["search"] += 1
        return [{"chunk_id": _CHUNK_ID, "doc_id": "spec.md", "section": "form",
                 "dense_score": 0.9, "colbert_score": None}]

    monkeypatch.setattr(retrieval, "hybrid_search", fake_search)

    manifest_file = tmp_path / f"manifest-{version}.json"
    manifest_file.write_text(json.dumps({"qdrant_collection": "vc__" + version}), encoding="utf-8")
    monkeypatch.setattr(deps, "manifest_path", lambda v, project=None: manifest_file)

    app = FastAPI()
    app.include_router(routes_retrieval.router)
    return TestClient(app, client=("127.0.0.1", 54321)), calls


# ---------------------------------------------------------------------------
# Ramo "graph": graph_answer senza LLM né retrieval
# ---------------------------------------------------------------------------
def test_domanda_strutturale_risponde_graph_answer_senza_llm(ask_env, caplog):
    client, calls = ask_env

    with caplog.at_level(logging.INFO, logger="api.routes_retrieval"):
        r = client.post("/ask", json={"question": "quali documenti esistono nel corpus?"})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "graph_answer"
    assert body["graph_result"]["intent"] == "documenti"
    assert body["graph_result"]["answer"] == ["glossario.md", "spec.md"]
    assert body["graph_result"]["count"] == 2
    assert body["index_version"] == "v-m2"
    assert isinstance(body["request_id"], str) and len(body["request_id"]) == 32

    # SENZA chiamata LLM e SENZA ricerca ibrida
    assert calls["llm"] == 0
    assert calls["search"] == 0

    # Log M3: stessa riga strutturata, con la strategia scelta dal router
    lines = [rec.message for rec in caplog.records
             if rec.name == "api.routes_retrieval" and rec.message.startswith("ask ")]
    assert len(lines) == 1
    assert "retrieval_strategy=graph" in lines[0]
    assert "qdrant_collection=vc__v-m2" in lines[0]
    for key in ("request_id=", "index_version=", "n_results=", "latency_retrieval_ms=",
                "latency_generation_ms=", "latency_total_ms="):
        assert key in lines[0]


# ---------------------------------------------------------------------------
# Ramo "graph" con target esplicito: passthrough a graph_query (semantica di
# /api/graph/query — il chiamante che conosce il nodo, es. Semantic Map, lo dichiara;
# il rilevamento testuale non risolve i riferimenti in linguaggio naturale)
# ---------------------------------------------------------------------------
def test_target_esplicito_passato_a_graph_query(ask_env):
    client, calls = ask_env

    r = client.post("/ask", json={
        "question": "quali relazioni ha la specifica del form?",
        "target": "spec.md",
    })

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "graph_answer"
    assert body["graph_result"]["intent"] == "relazioni"
    assert body["graph_result"]["target"] == "spec.md"
    assert body["graph_result"]["out"] == [{"relation": "HAS_SECTION", "to": _CHUNK_ID}]
    assert calls["llm"] == 0 and calls["search"] == 0


# ---------------------------------------------------------------------------
# Ramo "hybrid": percorso attuale invariato
# ---------------------------------------------------------------------------
def test_domanda_semantica_segue_il_percorso_ibrido(ask_env, caplog):
    client, calls = ask_env

    with caplog.at_level(logging.INFO, logger="api.routes_retrieval"):
        r = client.post("/ask", json={"question": "come funziona il lock sui posti?"})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["answer"] == "RISPOSTA"
    assert calls["llm"] == 1
    assert calls["search"] == 1

    lines = [rec.message for rec in caplog.records
             if rec.name == "api.routes_retrieval" and rec.message.startswith("ask ")]
    assert len(lines) == 1
    assert "retrieval_strategy=hybrid" in lines[0]


pytestmark = pytest.mark.usefixtures("legacy_http_project")

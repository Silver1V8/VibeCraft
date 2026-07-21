"""Test M3: log strutturato di fine richiesta di POST /ask (request_id, index_version,
qdrant_collection/alias, retrieval_strategy, top_k/n_results, latenze) e campi additivi
in risposta (request_id, index_version). Copre anche la cache {version: qdrant_collection}
di api.deps.qdrant_collection_for_version: il manifest si legge dal disco UNA volta per
versione, mai per-request."""
import json
import logging

import networkx as nx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.deps as deps
from api import routes_retrieval
from core import llm, retrieval

_CHUNK_ID = "spec.md#01-form"


def _snapshot(version) -> deps.IndexSnapshot:
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
    )


@pytest.fixture(autouse=True)
def _clear_manifest_cache():
    """La cache di qdrant_collection_for_version è a livello di modulo (sopravvive tra
    i test): la svuotiamo prima di ogni test così ciascuno parte da zero letture."""
    deps._qdrant_collection_by_version.clear()
    yield
    deps._qdrant_collection_by_version.clear()


@pytest.fixture
def ask_env(monkeypatch, tmp_path):
    """Factory di TestClient con la sola route /ask: stato del server (snapshot, qdrant,
    embed_model), hybrid_search e provider LLM finti. `manifest` (se non None) viene
    scritto su disco in tmp_path e api.deps.manifest_path viene fatto puntare lì, così i
    test controllano il contenuto del manifest senza toccare database/ reale."""
    monkeypatch.setattr(deps, "API_KEY", None)
    monkeypatch.setattr(routes_retrieval, "maybe_reload_graph", lambda: None)

    settings = {"active_provider": "fake", "models": {"fake": "fake-model"}, "purposes": {}}
    monkeypatch.setitem(llm.config, "llm_settings", settings)
    llm.register_provider("fake", lambda model, prompt, timeout: "RISPOSTA")

    def _make(version="v20260101T000000", manifest: dict | None = None,
              manifest_exists: bool = True):
        snap = _snapshot(version)
        monkeypatch.setattr(routes_retrieval, "current_snapshot", lambda: snap)
        monkeypatch.setitem(deps.state, "qdrant", object())
        monkeypatch.setitem(deps.state, "embed_model", object())
        results = [{"chunk_id": _CHUNK_ID, "doc_id": "spec.md", "section": "form",
                    "dense_score": 0.9, "colbert_score": None}]
        monkeypatch.setattr(retrieval, "hybrid_search", lambda *a, **kw: results)

        manifest_file = tmp_path / f"manifest-{version}.json"
        if manifest_exists:
            manifest_file.write_text(
                json.dumps(manifest if manifest is not None else {"qdrant_collection": "vc__" + str(version)}),
                encoding="utf-8",
            )
        monkeypatch.setattr(deps, "manifest_path", lambda v: manifest_file)

        app = FastAPI()
        app.include_router(routes_retrieval.router)
        return TestClient(app, client=("127.0.0.1", 54321))

    return _make


# ---------------------------------------------------------------------------
# La riga di log contiene tutte le chiavi elencate
# ---------------------------------------------------------------------------
def test_ask_log_contiene_tutte_le_chiavi(ask_env, caplog):
    client = ask_env(version="v1", manifest={"qdrant_collection": "vibecraft_docs__v1"})

    with caplog.at_level(logging.INFO, logger="api.routes_retrieval"):
        r = client.post("/ask", json={"question": "Quali vincoli?"})

    assert r.status_code == 200
    records = [rec for rec in caplog.records if rec.name == "api.routes_retrieval"
               and rec.message.startswith("ask ")]
    assert len(records) == 1
    line = records[0].message
    for key in ("request_id=", "index_version=", "qdrant_collection=", "qdrant_alias=",
                "retrieval_strategy=", "top_k=", "n_results=", "latency_retrieval_ms=",
                "latency_generation_ms=", "latency_total_ms="):
        assert key in line
    assert "qdrant_collection=vibecraft_docs__v1" in line
    assert "index_version=v1" in line
    assert "retrieval_strategy=hybrid" in line
    assert "top_k=5" in line
    assert "n_results=1" in line


# ---------------------------------------------------------------------------
# La risposta contiene request_id e index_version
# ---------------------------------------------------------------------------
def test_ask_risposta_contiene_request_id_e_index_version(ask_env):
    client = ask_env(version="v2", manifest={"qdrant_collection": "vibecraft_docs__v2"})

    r = client.post("/ask", json={"question": "Quali vincoli?"})

    assert r.status_code == 200
    body = r.json()
    assert body["index_version"] == "v2"
    request_id = body["request_id"]
    assert isinstance(request_id, str) and len(request_id) == 32
    int(request_id, 16)  # hex valido (uuid4().hex)

    # F3: campo "latency" additivo in risposta, stessi valori del log M3
    latency = body["latency"]
    assert set(latency) == {"retrieval_ms", "generation_ms", "total_ms"}
    assert latency["total_ms"] >= latency["generation_ms"]
    assert latency["total_ms"] >= latency["retrieval_ms"]


# ---------------------------------------------------------------------------
# F3: la risposta del ramo "graph" contiene lo stesso campo "latency"
# ---------------------------------------------------------------------------
def test_ask_risposta_graph_contiene_latency(ask_env):
    client = ask_env(version="v5", manifest={"qdrant_collection": "vibecraft_docs__v5"})

    r = client.post("/ask", json={"question": "quali documenti esistono nel corpus?"})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "graph_answer"
    latency = body["latency"]
    assert set(latency) == {"retrieval_ms", "generation_ms", "total_ms"}
    assert latency["generation_ms"] == 0
    assert latency["total_ms"] >= latency["generation_ms"]
    assert latency["total_ms"] >= latency["retrieval_ms"]


# ---------------------------------------------------------------------------
# Cache del manifest: due richieste sulla stessa versione ⇒ una sola lettura file
# ---------------------------------------------------------------------------
def test_cache_manifest_una_sola_lettura_per_versione(ask_env, monkeypatch):
    client = ask_env(version="v3", manifest={"qdrant_collection": "vibecraft_docs__v3"})

    read_count = {"n": 0}
    from pathlib import Path
    original_read_text = Path.read_text

    def counting_read_text(self, *a, **kw):
        read_count["n"] += 1
        return original_read_text(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    r1 = client.post("/ask", json={"question": "prima domanda"})
    r2 = client.post("/ask", json={"question": "seconda domanda"})

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["index_version"] == r2.json()["index_version"] == "v3"
    assert read_count["n"] == 1


# ---------------------------------------------------------------------------
# Fallback "unknown" con manifest assente
# ---------------------------------------------------------------------------
def test_fallback_unknown_con_manifest_assente(ask_env, caplog):
    client = ask_env(version="v4", manifest_exists=False)

    with caplog.at_level(logging.INFO, logger="api.routes_retrieval"):
        r = client.post("/ask", json={"question": "Quali vincoli?"})

    assert r.status_code == 200
    records = [rec for rec in caplog.records if rec.name == "api.routes_retrieval"
               and rec.message.startswith("ask ")]
    assert "qdrant_collection=unknown" in records[0].message

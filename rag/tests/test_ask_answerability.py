"""G1 — gate di rispondibilità dentro /ask (rag/adr/2026-11-03-gate-rispondibilita-plan.md).

Stessa impalcatura minima di test_ask_abstention.py. Il reranker è uno stub che registra le
coppie ricevute: si verifica che il gate giudichi le sezioni EFFETTIVAMENTE iniettate, che in
shadow non cambi l'esito, e che senza sezioni da giudicare non esprima un'opinione."""
import networkx as nx
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.deps as deps
from api import routes_retrieval
from core import llm, retrieval

_CHUNKS = {
    "spec.md#01-form": {"doc_id": "spec.md", "section": "form", "text": "testo del form"},
    "spec.md#02-lock": {"doc_id": "spec.md", "section": "lock", "text": "testo del lock"},
}


class _StubEmbed:
    def encode(self, texts, **kw):
        n = len(texts)
        out = {"dense_vecs": np.zeros((n, 4), dtype="float32")}
        if kw.get("return_sparse"):
            out["lexical_weights"] = [{} for _ in texts]
        if kw.get("return_colbert_vecs"):
            out["colbert_vecs"] = [np.zeros((1, 4), dtype="float32") for _ in texts]
        return out


class _StubReranker:
    def __init__(self, punteggio):
        self.punteggio = punteggio
        self.coppie = []

    def compute_score(self, coppie, **kw):
        self.coppie = list(coppie)
        return [self.punteggio] * len(self.coppie)


def _snapshot() -> deps.IndexSnapshot:
    g = nx.DiGraph()
    g.add_node("spec.md", type="document")
    for cid in _CHUNKS:
        g.add_node(cid, type="chunk")
        g.add_edge("spec.md", cid, relation="HAS_SECTION")
    return deps.IndexSnapshot(
        graph=g, colbert_store={}, chunks=dict(_CHUNKS), rule_descriptions={},
        code_store={}, version="v1", code_ids=[], code_matrix=None,
    )


@pytest.fixture
def ask_env(monkeypatch):
    monkeypatch.setattr(deps, "API_KEY", None)
    monkeypatch.setitem(llm.config, "llm_settings",
                        {"active_provider": "fake", "models": {"fake": "fake-model"}, "purposes": {}})

    def _make(*, mode="shadow", punteggio=0.05, soglia=0.5, reranker="stub",
              risultati=None, codice=None):
        chiamate_llm = []

        def _llm(model, prompt, timeout):
            chiamate_llm.append(prompt)
            return "RISPOSTA"

        llm.register_provider("fake", _llm)
        stub = _StubReranker(punteggio) if reranker == "stub" else reranker
        caricamenti = []

        def _ensure():
            caricamenti.append(1)
            return stub

        monkeypatch.setattr(routes_retrieval, "ANSWERABILITY_MODE", mode)
        monkeypatch.setattr(routes_retrieval, "ANSWERABILITY_THRESHOLD", soglia)
        monkeypatch.setattr(routes_retrieval, "ensure_reranker", _ensure)
        monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: _snapshot())
        monkeypatch.setitem(deps.state, "qdrant", object())
        monkeypatch.setitem(deps.state, "embed_model", _StubEmbed())
        if risultati is None:
            risultati = [{"chunk_id": cid, "doc_id": "spec.md", "section": c["section"],
                          "dense_score": 0.9, "colbert_score": None} for cid, c in _CHUNKS.items()]
        monkeypatch.setattr(retrieval, "hybrid_search", lambda *a, **kw: risultati)
        if codice is not None:
            monkeypatch.setattr(retrieval, "search_code_symbols", lambda *a, **kw: codice)
        monkeypatch.setattr(deps, "manifest_path", lambda v, project=None: None)
        monkeypatch.setattr(routes_retrieval, "qdrant_collection_for_version", lambda v, project=None: "coll")

        app = FastAPI()
        app.include_router(routes_retrieval.router)
        client = TestClient(app, client=("127.0.0.1", 54321))
        return client, stub, chiamate_llm, caricamenti

    return _make


_DOMANDA = {"question": "domanda?", "use_thread": False}


def test_off_non_carica_il_modello(ask_env):
    client, _stub, chiamate_llm, caricamenti = ask_env(mode="off")
    body = client.post("/ask", json=_DOMANDA).json()
    assert body["answerability"] is None
    assert caricamenti == [] and len(chiamate_llm) == 1


def test_shadow_osserva_senza_decidere(ask_env):
    client, _stub, chiamate_llm, _ = ask_env(punteggio=0.05, soglia=0.5)
    body = client.post("/ask", json=_DOMANDA).json()
    assert body["status"] == "success" and body["answer"] == "RISPOSTA"
    assert len(chiamate_llm) == 1
    assert body["answerability"]["would_abstain"] is True
    assert body["answerability"]["score"] == 0.05


def test_giudica_le_sezioni_iniettate_nell_ordine_del_contesto(ask_env):
    client, stub, _, _ = ask_env()
    client.post("/ask", json=_DOMANDA)
    assert stub.coppie == [("domanda?", "testo del form"), ("domanda?", "testo del lock")]


def test_solo_codice_nessun_giudizio(ask_env):
    """Focus di review 2: una domanda implementativa non ha sezioni da giudicare."""
    codice = [{"symbol_id": "code:a.py::f", "file": "a.py", "name": "f", "kind": "function",
               "implements": None, "text": "def f(): pass", "score": 0.9}]
    client, stub, chiamate_llm, _ = ask_env(risultati=[], codice=codice)
    body = client.post("/ask", json=_DOMANDA).json()
    assert body["answerability"] is None
    assert stub.coppie == [] and len(chiamate_llm) == 1


def test_modello_non_caricato_risposta_normale(ask_env):
    """Focus di review 4: fail-open, il LLM risponde come prima."""
    client, _stub, chiamate_llm, _ = ask_env(reranker=None)
    body = client.post("/ask", json=_DOMANDA).json()
    assert body["status"] == "success" and body["answerability"] is None
    assert len(chiamate_llm) == 1

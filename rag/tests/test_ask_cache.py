"""Test 4.1: cache semantica di POST /ask, invalidata per `index_version`.

Coperti: hit di una domanda ripetuta (nessuna seconda chiamata LLM né retrieval), miss al
cambio di index_version e al cambio dei parametri (top_k/bfs_depth), normalizzazione della
domanda, esclusione dei rami non cachabili (ramo "graph" e esiti a vuoto), tetto LRU e
disattivazione via env, e infine il comportamento best-effort (un errore della cache non
fa fallire /ask).

Stesso pattern di fixture di test_ask_router (stato del server, provider LLM e
hybrid_search finti, con contatori di chiamata), con due differenze necessarie: l'app —
e quindi l'istanza di cache, che vive su `app.state` — è UNA sola per test (è la
condizione per osservare un hit fra due richieste), e lo snapshot è sostituibile a caldo
per simulare una re-indicizzazione fra una richiesta e l'altra.
"""
import logging
from types import SimpleNamespace

import networkx as nx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.deps as deps
from api import routes_retrieval
from core import ask_cache, llm, retrieval

_CHUNK_ID = "spec.md#01-form"
_QUESTION = "come funziona il lock sui posti?"


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
    """Ambiente di test di /ask: `env.client` (una sola app, quindi una sola cache),
    `env.calls` con i contatori di provider LLM e hybrid_search, `env.current` per
    sostituire a caldo snapshot e risultati del retrieval."""
    monkeypatch.setattr(deps, "API_KEY", None)
    monkeypatch.setattr(routes_retrieval, "maybe_reload_graph", lambda: None)

    calls = {"llm": 0, "search": 0}

    settings = {"active_provider": "fake", "models": {"fake": "fake-model"}, "purposes": {}}
    monkeypatch.setitem(llm.config, "llm_settings", settings)

    def fake_provider(model, prompt, timeout):
        calls["llm"] += 1
        # Risposta DIVERSA a ogni chiamata: due risposte uguali provano che la seconda
        # non è passata dall'LLM.
        return f"RISPOSTA-{calls['llm']}"

    llm.register_provider("fake", fake_provider)

    current = {
        "snap": _snapshot("v-cache-1"),
        "results": [{"chunk_id": _CHUNK_ID, "doc_id": "spec.md", "section": "form",
                     "dense_score": 0.9, "colbert_score": None}],
    }
    monkeypatch.setattr(routes_retrieval, "current_snapshot", lambda: current["snap"])
    monkeypatch.setitem(deps.state, "qdrant", object())
    monkeypatch.setitem(deps.state, "embed_model", object())

    def fake_search(*a, **kw):
        calls["search"] += 1
        return list(current["results"])

    monkeypatch.setattr(retrieval, "hybrid_search", fake_search)
    # Manifest assente: qdrant_collection ricade su "unknown" (irrilevante qui).
    monkeypatch.setattr(deps, "manifest_path", lambda v: tmp_path / f"manifest-{v}.json")

    app = FastAPI()
    app.include_router(routes_retrieval.router)
    client = TestClient(app, client=("127.0.0.1", 54321))
    return SimpleNamespace(client=client, app=app, calls=calls, current=current)


# ---------------------------------------------------------------------------
# Hit: la seconda domanda identica non ripaga né embedding né LLM
# ---------------------------------------------------------------------------
def test_domanda_ripetuta_servita_dalla_cache_senza_llm(ask_env, caplog):
    with caplog.at_level(logging.INFO, logger="api.routes_retrieval"):
        first = ask_env.client.post("/ask", json={"question": _QUESTION})
        second = ask_env.client.post("/ask", json={"question": _QUESTION})

    assert first.status_code == 200 and second.status_code == 200
    body1, body2 = first.json(), second.json()
    assert body1["cached"] is False
    assert body2["cached"] is True
    # Il provider risponde "RISPOSTA-2" alla seconda invocazione: risposte uguali ⇒ la
    # seconda richiesta NON è passata dall'LLM. I contatori lo confermano.
    assert body1["answer"] == body2["answer"] == "RISPOSTA-1"
    assert ask_env.calls == {"llm": 1, "search": 1}
    # Il payload cachato è servito integralmente (contesto grafo e scores compresi) ...
    assert body2["graph_context"] == body1["graph_context"]
    assert body2["qdrant_scores"] == body1["qdrant_scores"]
    assert body2["index_version"] == body1["index_version"] == "v-cache-1"
    # ... tranne i campi propri della richiesta: request_id nuovo e latenze reali.
    assert body2["request_id"] != body1["request_id"]
    assert body2["latency"] == {"retrieval_ms": 0, "generation_ms": 0,
                                "total_ms": body2["latency"]["total_ms"]}
    assert body2["elaboration_seconds"] == 0.0

    # Log M3: una riga per richiesta, la seconda marcata cached=true
    lines = [rec.message for rec in caplog.records
             if rec.name == "api.routes_retrieval" and rec.message.startswith("ask ")]
    assert len(lines) == 2
    assert "cached=true" not in lines[0]
    assert "cached=true" in lines[1]
    assert "retrieval_strategy=hybrid" in lines[1] and "n_results=1" in lines[1]


def test_domanda_equivalente_a_meno_di_spazi_e_maiuscole_e_un_hit(ask_env):
    ask_env.client.post("/ask", json={"question": _QUESTION})

    r = ask_env.client.post("/ask", json={"question": f"  Come  FUNZIONA il lock sui posti?\n"})

    assert r.json()["cached"] is True
    assert ask_env.calls["llm"] == 1


# ---------------------------------------------------------------------------
# Miss: index_version diversa ⇒ la risposta viene ricalcolata (invalidazione)
# ---------------------------------------------------------------------------
def test_cambio_index_version_invalida_la_cache(ask_env):
    first = ask_env.client.post("/ask", json={"question": _QUESTION})

    # Re-indicizzazione: stessa app, stessa cache, ma indice (e versione) nuovi.
    ask_env.current["snap"] = _snapshot("v-cache-2")
    second = ask_env.client.post("/ask", json={"question": _QUESTION})

    assert first.json()["answer"] == "RISPOSTA-1"
    assert second.json()["cached"] is False
    assert second.json()["answer"] == "RISPOSTA-2"
    assert second.json()["index_version"] == "v-cache-2"
    assert ask_env.calls == {"llm": 2, "search": 2}


def test_parametri_diversi_sono_voci_diverse(ask_env):
    ask_env.client.post("/ask", json={"question": _QUESTION})

    altro_k = ask_env.client.post("/ask", json={"question": _QUESTION, "top_k": 7})
    altra_depth = ask_env.client.post("/ask", json={"question": _QUESTION, "bfs_depth": 3})

    assert altro_k.json()["cached"] is False
    assert altra_depth.json()["cached"] is False
    assert ask_env.calls["llm"] == 3
    assert len(ask_cache.for_app(ask_env.app)) == 3


# ---------------------------------------------------------------------------
# Rami non cachabili: risposte a vuoto e ramo "graph"
# ---------------------------------------------------------------------------
def test_no_results_non_viene_cachato(ask_env):
    ask_env.current["results"] = []

    first = ask_env.client.post("/ask", json={"question": _QUESTION})
    second = ask_env.client.post("/ask", json={"question": _QUESTION})

    assert first.json()["status"] == second.json()["status"] == "no_results"
    assert "cached" not in second.json()
    # Il retrieval è stato rifatto (nessun hit) e nulla è finito in cache.
    assert ask_env.calls["search"] == 2
    assert len(ask_cache.for_app(ask_env.app)) == 0


def test_no_graph_nodes_non_viene_cachato(ask_env):
    # Documento trovato in Qdrant ma assente dal grafo ⇒ nessun seed, nessun codice.
    ask_env.current["results"] = [{"chunk_id": "altro.md#01", "doc_id": "altro.md",
                                   "section": "x", "dense_score": 0.9, "colbert_score": None}]

    first = ask_env.client.post("/ask", json={"question": _QUESTION})
    second = ask_env.client.post("/ask", json={"question": _QUESTION})

    assert first.json()["status"] == second.json()["status"] == "no_graph_nodes"
    assert "cached" not in second.json()
    assert len(ask_cache.for_app(ask_env.app)) == 0


def test_ramo_graph_non_viene_cachato(ask_env):
    domanda = "quali documenti esistono nel corpus?"

    first = ask_env.client.post("/ask", json={"question": domanda})
    second = ask_env.client.post("/ask", json={"question": domanda})

    assert first.json()["status"] == second.json()["status"] == "graph_answer"
    assert "cached" not in second.json()
    assert ask_env.calls == {"llm": 0, "search": 0}
    assert len(ask_cache.for_app(ask_env.app)) == 0


# ---------------------------------------------------------------------------
# Best-effort: un errore della cache degrada al percorso completo, non a un 500
# ---------------------------------------------------------------------------
def test_errore_della_cache_non_fa_fallire_ask(ask_env, monkeypatch, caplog):
    def esplode(app):
        raise RuntimeError("cache rotta")

    monkeypatch.setattr(ask_cache, "for_app", esplode)

    with caplog.at_level(logging.WARNING, logger="api.routes_retrieval"):
        r = ask_env.client.post("/ask", json={"question": _QUESTION})

    assert r.status_code == 200
    assert r.json()["answer"] == "RISPOSTA-1"
    # Sia la lettura sia la scrittura falliscono, entrambe loggate come warning.
    warnings = [rec.message for rec in caplog.records if rec.levelno == logging.WARNING]
    assert any("non consultabile" in m for m in warnings)
    assert any("non aggiornata" in m for m in warnings)


# ---------------------------------------------------------------------------
# Unit sulla struttura: chiave, tetto LRU, disattivazione
# ---------------------------------------------------------------------------
def test_make_key_normalizza_la_domanda_e_separa_il_resto():
    base = ask_cache.make_key("v1", "hybrid", 5, 2, "Quali  vincoli?")

    assert base == ask_cache.make_key("v1", "hybrid", 5, 2, "  quali vincoli?  ")
    assert base != ask_cache.make_key("v2", "hybrid", 5, 2, "Quali vincoli?")
    assert base != ask_cache.make_key("v1", "hybrid", 6, 2, "Quali vincoli?")
    assert base != ask_cache.make_key("v1", "hybrid", 5, 3, "Quali vincoli?")
    assert base != ask_cache.make_key("v1", "hybrid", 5, 2, "Quali altri vincoli?")
    # index_version float (layout legacy senza CURRENT): stringificata, chiave valida.
    assert ask_cache.make_key(1712345.5, "hybrid", 5, 2, "q")[0] == "1712345.5"
    # La domanda in chiaro non è trattenuta: solo il suo digest esadecimale.
    assert len(base[4]) == 64 and "vincoli" not in base[4]


def test_lru_espelle_la_voce_meno_recente():
    cache = ask_cache.AskCache(max_size=2)
    k1, k2, k3 = (ask_cache.make_key("v1", "hybrid", 5, 2, q) for q in ("a", "b", "c"))
    cache.set(k1, {"answer": "A"})
    cache.set(k2, {"answer": "B"})

    cache.get(k1)          # k1 torna la più recente ⇒ a essere espulsa sarà k2
    cache.set(k3, {"answer": "C"})

    assert len(cache) == 2
    assert cache.get(k1) == {"answer": "A"}
    assert cache.get(k3) == {"answer": "C"}
    assert cache.get(k2) is None


def test_size_zero_disattiva_la_cache():
    cache = ask_cache.AskCache(max_size=0)
    key = ask_cache.make_key("v1", "hybrid", 5, 2, "q")

    cache.set(key, {"answer": "A"})

    assert cache.get(key) is None
    assert len(cache) == 0


def test_max_size_from_env(monkeypatch):
    monkeypatch.delenv("VIBECRAFT_ASK_CACHE_SIZE", raising=False)
    assert ask_cache.max_size_from_env() == ask_cache.DEFAULT_ASK_CACHE_SIZE

    monkeypatch.setenv("VIBECRAFT_ASK_CACHE_SIZE", "0")
    assert ask_cache.max_size_from_env() == 0

    monkeypatch.setenv("VIBECRAFT_ASK_CACHE_SIZE", "-5")
    assert ask_cache.max_size_from_env() == 0

    monkeypatch.setenv("VIBECRAFT_ASK_CACHE_SIZE", "non-numerica")
    assert ask_cache.max_size_from_env() == ask_cache.DEFAULT_ASK_CACHE_SIZE


def test_for_app_crea_una_sola_istanza_per_app(monkeypatch):
    monkeypatch.setenv("VIBECRAFT_ASK_CACHE_SIZE", "3")
    app = FastAPI()

    cache = ask_cache.for_app(app)

    assert cache.max_size == 3
    assert ask_cache.for_app(app) is cache
    assert ask_cache.for_app(FastAPI()) is not cache

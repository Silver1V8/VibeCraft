"""WP3: wire project ask-thread into /ask (prompt block, cache fingerprint, append).

Storage unit coverage lives in test_ask_thread.py (WP1). GET/DELETE routes are WP2.
"""
from __future__ import annotations

from types import SimpleNamespace

import networkx as nx
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.deps as deps
from api import routes_retrieval
from core import ask_cache, ask_thread, llm, retrieval
from core.projects import ProjectRegistry

_CHUNK_ID = "spec.md#01-form"
_Q1 = "quali vincoli sul lock?"
_Q2 = "e per i vincoli di quella regola?"


class _StubEmbed:
    def encode(self, texts, **kw):
        n = len(texts)
        out = {"dense_vecs": np.zeros((n, 4), dtype="float32")}
        if kw.get("return_sparse"):
            out["lexical_weights"] = [{} for _ in texts]
        if kw.get("return_colbert_vecs"):
            out["colbert_vecs"] = [np.zeros((1, 4), dtype="float32") for _ in texts]
        return out


def _snapshot(version: str = "v-thread-1") -> deps.IndexSnapshot:
    g = nx.DiGraph()
    g.add_node("spec.md", type="document")
    g.add_node(_CHUNK_ID, type="chunk")
    g.add_edge("spec.md", _CHUNK_ID, relation="HAS_SECTION")
    return deps.IndexSnapshot(
        graph=g,
        colbert_store={},
        chunks={_CHUNK_ID: {"text": "il lock richiede SELECT FOR UPDATE sulla riga"}},
        rule_descriptions={},
        code_store={},
        version=version,
        code_ids=[],
        code_matrix=None,
        # Non-legacy projects reject collection "unknown" with 503.
        collection_name=f"vibecraft_docs__{version}",
    )


@pytest.fixture(autouse=True)
def _clear_manifest_cache():
    deps._qdrant_collection_by_version.clear()
    yield
    deps._qdrant_collection_by_version.clear()


@pytest.fixture
def thread_ask_env(monkeypatch, tmp_path):
    """Real registered project (writable database/ask) + stubbed retrieval/LLM."""
    monkeypatch.setattr(deps, "API_KEY", None)
    registry = ProjectRegistry(tmp_path / "projects", bootstrap_legacy=False)
    project = registry.create("ThreadAcme")

    calls = {"llm": 0, "search": 0, "last_prompt": ""}
    settings = {"active_provider": "fake", "models": {"fake": "fake-model"}, "purposes": {}}
    monkeypatch.setitem(llm.config, "llm_settings", settings)

    def fake_provider(model, prompt, timeout):
        calls["llm"] += 1
        calls["last_prompt"] = prompt
        return f"RISPOSTA-{calls['llm']} con citazione spec.md"

    llm.register_provider("fake", fake_provider)

    current = {
        "snap": _snapshot(),
        "results": [{"chunk_id": _CHUNK_ID, "doc_id": "spec.md", "section": "lock",
                     "dense_score": 0.91, "colbert_score": 0.88, "authority": 0.9}],
    }
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda p: current["snap"])
    monkeypatch.setattr(routes_retrieval, "get_project", lambda request: project)
    monkeypatch.setitem(deps.state, "qdrant", object())
    monkeypatch.setitem(deps.state, "embed_model", _StubEmbed())

    def fake_search(*a, **kw):
        calls["search"] += 1
        return list(current["results"])

    monkeypatch.setattr(retrieval, "hybrid_search", fake_search)
    monkeypatch.setattr(deps, "manifest_path", lambda v, project=None: tmp_path / f"m-{v}.json")

    app = FastAPI()
    app.include_router(routes_retrieval.router)
    client = TestClient(app, client=("127.0.0.1", 54321))
    return SimpleNamespace(
        client=client, app=app, calls=calls, current=current, project=project,
    )


# ---------------------------------------------------------------------------
# Prompt block presence / absence
# ---------------------------------------------------------------------------
def test_format_thread_block_assente_su_filo_vuoto():
    assert ask_thread.format_thread_block(None) == ""
    assert ask_thread.format_thread_block(ask_thread.empty_thread("p")) == ""


def test_format_thread_block_presente_con_turni_e_budget():
    thread = ask_thread.empty_thread("p", max_turns=4)
    ask_thread.append_turn(
        thread,
        ask_thread.build_turn(
            question="Prima domanda lunga " + ("x" * 500),
            answer_excerpt="Risposta " + ("y" * 2000),
            status="success",
            turn_id="t-11111111",
            index_version="v1",
            citation_ids=["spec.md"],
        ),
        citations=[{"doc_id": "spec.md", "last_score": 0.8, "authority": 0.9}],
    )
    block = ask_thread.format_thread_block(thread, current_index_version="v1")
    assert block.startswith("[FILO-THREAD]")
    assert "Prima domanda" in block
    assert "spec.md" in block
    assert "inventare dalla sola memoria" in block
    assert len(block) <= ask_thread.THREAD_BLOCK_MAX_CHARS


def test_format_thread_block_segnala_indice_stale():
    thread = ask_thread.empty_thread("p")
    ask_thread.append_turn(
        thread,
        ask_thread.build_turn(question="Q", answer_excerpt="A", index_version="v-old"),
    )
    block = ask_thread.format_thread_block(thread, current_index_version="v-new")
    assert "ATTENZIONE" in block and "stale" in block


def test_build_ask_prompt_senza_thread_block_invariato():
    base = retrieval.build_ask_prompt("CTX", "domanda?")
    assert "[FILO-THREAD]" not in base
    with_empty = retrieval.build_ask_prompt("CTX", "domanda?", thread_block="")
    assert with_empty == base
    with_none = retrieval.build_ask_prompt("CTX", "domanda?", thread_block=None)
    assert with_none == base


def test_build_ask_prompt_injects_filo_thread_prima_del_contesto():
    block = "[FILO-THREAD]: prova\nQ: prima\nA(success): risposta"
    prompt = retrieval.build_ask_prompt("CTX", "follow-up?", thread_block=block)
    assert "[FILO-THREAD]" in prompt
    assert prompt.index("[FILO-THREAD]") < prompt.index("Contesto grafo:")
    assert prompt.index("Contesto grafo:") < prompt.index("Domanda: follow-up?")


# ---------------------------------------------------------------------------
# /ask wiring
# ---------------------------------------------------------------------------
def test_ask_use_thread_false_non_scrive_e_senza_blocco(thread_ask_env):
    r = thread_ask_env.client.post(
        "/ask", json={"question": _Q1, "use_thread": False})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert "thread" not in body
    assert "[FILO-THREAD]" not in thread_ask_env.calls["last_prompt"]
    assert ask_thread.load_thread(thread_ask_env.project)["turns"] == []


def test_ask_primo_turno_senza_blocco_poi_secondo_con_filo(thread_ask_env):
    first = thread_ask_env.client.post("/ask", json={"question": _Q1})
    assert first.status_code == 200
    body1 = first.json()
    assert body1["status"] == "success"
    assert body1["thread"]["turn_count"] == 1
    assert body1["thread"]["citations"][0]["doc_id"] == "spec.md"
    assert "[FILO-THREAD]" not in thread_ask_env.calls["last_prompt"]

    second = thread_ask_env.client.post("/ask", json={"question": _Q2})
    assert second.status_code == 200
    body2 = second.json()
    assert body2["thread"]["turn_count"] == 2
    assert "[FILO-THREAD]" in thread_ask_env.calls["last_prompt"]
    assert _Q1.split()[0] in thread_ask_env.calls["last_prompt"]
    assert body2["thread"]["citations"]
    loaded = ask_thread.load_thread(thread_ask_env.project)
    assert len(loaded["turns"]) == 2
    assert loaded["turns"][0]["question"] == _Q1


def test_ask_reset_thread_prima_della_domanda(thread_ask_env):
    thread_ask_env.client.post("/ask", json={"question": _Q1})
    assert ask_thread.load_thread(thread_ask_env.project)["turns"]

    r = thread_ask_env.client.post(
        "/ask", json={"question": _Q2, "reset_thread": True})
    assert r.status_code == 200
    body = r.json()
    assert body["thread"]["turn_count"] == 1
    assert body["thread"]["turns"][0]["question"] == _Q2
    # Reset cleared prior turns before this ask, so no FILO block on the prompt.
    assert "[FILO-THREAD]" not in thread_ask_env.calls["last_prompt"]


def test_ask_cache_miss_dopo_append_con_stessa_domanda(thread_ask_env):
    """Stessa domanda dopo un append: fingerprint cambiato ⇒ niente hit del turno-1."""
    first = thread_ask_env.client.post("/ask", json={"question": _Q1})
    assert first.json()["cached"] is False
    assert thread_ask_env.calls["llm"] == 1

    second = thread_ask_env.client.post("/ask", json={"question": _Q1})
    assert second.status_code == 200
    assert second.json()["cached"] is False
    assert second.json()["answer"] == "RISPOSTA-2 con citazione spec.md"
    assert thread_ask_env.calls["llm"] == 2
    assert second.json()["thread"]["turn_count"] == 2


def test_ask_cache_hit_isolato_con_use_thread_false(thread_ask_env):
    first = thread_ask_env.client.post(
        "/ask", json={"question": _Q1, "use_thread": False})
    second = thread_ask_env.client.post(
        "/ask", json={"question": _Q1, "use_thread": False})
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert thread_ask_env.calls["llm"] == 1
    assert "thread" not in second.json()


def test_ask_stream_result_include_thread(thread_ask_env):
    with thread_ask_env.client.stream(
        "POST", "/ask", json={"question": _Q1, "stream": True},
    ) as response:
        assert response.status_code == 200
        lines = [ln for ln in response.iter_lines() if ln]
    import json
    events = [json.loads(ln) for ln in lines]
    assert events[0]["type"] == "meta"
    assert events[-1]["type"] == "result"
    result = events[-1]["value"]
    assert result["status"] == "success"
    assert result["thread"]["turn_count"] == 1
    assert result["thread"]["max_turns"] >= 1


def test_ask_graph_answer_appende_turno(thread_ask_env):
    domanda = "quali documenti esistono nel corpus?"
    r = thread_ask_env.client.post("/ask", json={"question": domanda})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "graph_answer"
    assert body["thread"]["turn_count"] == 1
    assert body["thread"]["turns"][0]["status"] == "graph_answer"
    assert thread_ask_env.calls["llm"] == 0


def test_ask_abstained_appende_turno(thread_ask_env, monkeypatch):
    settings = {"active_provider": "fake", "models": {"fake": "fake-model"}, "purposes": {}}
    monkeypatch.setitem(llm.config, "llm_settings", settings)

    def abstain_provider(model, prompt, timeout):
        thread_ask_env.calls["llm"] += 1
        thread_ask_env.calls["last_prompt"] = prompt
        return f"{retrieval.ASK_ABSTENTION_MARKER}\nContesto insufficiente."

    llm.register_provider("fake", abstain_provider)
    r = thread_ask_env.client.post("/ask", json={"question": _Q1})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "abstained"
    assert body["thread"]["turn_count"] == 1
    assert body["thread"]["turns"][0]["status"] == "abstained"


def test_make_key_fingerprint_separa_turni():
    isolated = ask_cache.make_key("v1", "hybrid", 5, 2, _Q1, project_id="p")
    t1 = ask_cache.make_key(
        "v1", "hybrid", 5, 2, _Q1, project_id="p", thread_fingerprint="1:t-a:aaa")
    t2 = ask_cache.make_key(
        "v1", "hybrid", 5, 2, _Q1, project_id="p", thread_fingerprint="2:t-b:bbb")
    assert isolated != t1 != t2
    assert len(isolated) == 7 and len(t1) == 8

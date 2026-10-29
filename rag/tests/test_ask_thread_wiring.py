"""WP3 wiring + WP6 ask-thread matrix: prompt, cache, isolation, streaming, status paths.

Storage unit + GET/DELETE coverage: test_ask_thread.py.
"""
from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# WP6 — acceptance matrix (isolation, caps, reset, no_results, streaming)
# ---------------------------------------------------------------------------
@pytest.fixture
def dual_thread_ask_env(monkeypatch, tmp_path):
    """Two real projects; get_project resolves X-VibeCraft-Project."""
    monkeypatch.setattr(deps, "API_KEY", None)
    registry = ProjectRegistry(tmp_path / "projects", bootstrap_legacy=False)
    project_a = registry.create("Alpha")
    project_b = registry.create("Beta")
    by_id = {project_a.id: project_a, project_b.id: project_b}

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

    def get_project(request):
        pid = request.headers.get("X-VibeCraft-Project") or ""
        if pid not in by_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail={"code": "project_required"})
        return by_id[pid]

    monkeypatch.setattr(routes_retrieval, "get_project", get_project)
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
        client=client, calls=calls, current=current,
        project_a=project_a, project_b=project_b,
        headers_a={"X-VibeCraft-Project": project_a.id},
        headers_b={"X-VibeCraft-Project": project_b.id},
    )


def test_ask_empty_thread_payload_additive_only(thread_ask_env):
    """Acceptance #1: empty-thread ask matches isolated shape; thread summary is additive."""
    isolated = thread_ask_env.client.post(
        "/ask", json={"question": _Q1, "use_thread": False}).json()
    threaded = thread_ask_env.client.post(
        "/ask", json={"question": _Q1, "reset_thread": True}).json()
    assert isolated["status"] == threaded["status"] == "success"
    assert "thread" not in isolated
    assert "thread" in threaded
    for key in ("answer", "status", "qdrant_scores", "index_version", "project_id"):
        assert key in isolated and key in threaded
    assert threaded["thread"]["turn_count"] == 1
    assert threaded["answer"].startswith("RISPOSTA-")


def test_ask_project_isolation_a_b(dual_thread_ask_env):
    """Acceptance #5: project A's thread never appears under B."""
    env = dual_thread_ask_env
    r_a = env.client.post("/ask", json={"question": "solo alpha"}, headers=env.headers_a)
    assert r_a.status_code == 200
    assert r_a.json()["thread"]["turns"][0]["question"] == "solo alpha"

    got_b = env.client.get("/api/ask/thread", headers=env.headers_b)
    assert got_b.status_code == 200
    assert got_b.json()["thread"]["turn_count"] == 0

    r_b = env.client.post("/ask", json={"question": "solo beta"}, headers=env.headers_b)
    assert r_b.status_code == 200
    assert r_b.json()["thread"]["turn_count"] == 1
    assert r_b.json()["thread"]["turns"][0]["question"] == "solo beta"
    # Follow-up on B must not inject A's question into the prompt.
    env.client.post("/ask", json={"question": _Q2}, headers=env.headers_b)
    assert "solo alpha" not in env.calls["last_prompt"]
    assert "solo beta" in env.calls["last_prompt"]

    got_a = env.client.get("/api/ask/thread", headers=env.headers_a).json()
    assert got_a["thread"]["turn_count"] == 1
    assert got_a["thread"]["turns"][0]["question"] == "solo alpha"


def test_ask_fifo_cap_via_http(thread_ask_env, monkeypatch):
    """Acceptance #7: fifth ask drops the oldest when max_turns=4."""
    monkeypatch.setenv("VIBECRAFT_ASK_THREAD_MAX_TURNS", "4")
    # Seed empty with env cap by resetting first.
    thread_ask_env.client.delete("/api/ask/thread")
    questions = [f"turno-{i}" for i in range(5)]
    for q in questions:
        r = thread_ask_env.client.post("/ask", json={"question": q})
        assert r.status_code == 200
    body = r.json()
    assert body["thread"]["turn_count"] == 4
    assert body["thread"]["max_turns"] == 4
    qs = [t["question"] for t in body["thread"]["turns"]]
    assert qs == ["turno-1", "turno-2", "turno-3", "turno-4"]
    loaded = ask_thread.load_thread(thread_ask_env.project)
    assert [t["question"] for t in loaded["turns"]] == qs


def test_ask_delete_then_isolated_again(thread_ask_env):
    """Acceptance #4: DELETE clears; next ask has no FILO block."""
    thread_ask_env.client.post("/ask", json={"question": _Q1})
    assert ask_thread.load_thread(thread_ask_env.project)["turns"]
    deleted = thread_ask_env.client.delete("/api/ask/thread")
    assert deleted.status_code == 200
    assert deleted.json()["thread"]["turn_count"] == 0

    r = thread_ask_env.client.post("/ask", json={"question": _Q2})
    assert r.status_code == 200
    assert r.json()["thread"]["turn_count"] == 1
    assert r.json()["thread"]["turns"][0]["question"] == _Q2
    assert "[FILO-THREAD]" not in thread_ask_env.calls["last_prompt"]


def test_ask_reset_flag_with_use_thread_false_clears_only(thread_ask_env):
    thread_ask_env.client.post("/ask", json={"question": _Q1})
    r = thread_ask_env.client.post(
        "/ask", json={"question": _Q2, "use_thread": False, "reset_thread": True})
    assert r.status_code == 200
    assert "thread" not in r.json()
    assert ask_thread.load_thread(thread_ask_env.project)["turns"] == []
    assert "[FILO-THREAD]" not in thread_ask_env.calls["last_prompt"]


def test_ask_cache_miss_after_delete_reset(thread_ask_env):
    """Append ⇒ miss; DELETE restores empty fingerprint so the original empty-key may hit."""
    first = thread_ask_env.client.post("/ask", json={"question": _Q1})
    assert first.json()["cached"] is False
    answer_empty = first.json()["answer"]
    # Identical question while thread non-empty: fingerprint differs from empty ⇒ miss.
    second = thread_ask_env.client.post("/ask", json={"question": _Q1})
    assert second.json()["cached"] is False
    assert second.json()["answer"] != answer_empty
    assert thread_ask_env.calls["llm"] == 2

    thread_ask_env.client.delete("/api/ask/thread")
    # Empty fingerprint again: may hit the first (empty-key) entry — not the mid-thread one.
    third = thread_ask_env.client.post("/ask", json={"question": _Q1})
    assert third.json()["cached"] is True
    assert third.json()["answer"] == answer_empty
    assert thread_ask_env.calls["llm"] == 2
    assert third.json()["thread"]["turn_count"] == 1


def test_ask_no_results_appende_turno(thread_ask_env):
    thread_ask_env.current["results"] = []
    r = thread_ask_env.client.post("/ask", json={"question": "nessun hit?"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "no_results"
    assert body["thread"]["turn_count"] == 1
    assert body["thread"]["turns"][0]["status"] == "no_results"
    assert thread_ask_env.calls["llm"] == 0
    loaded = ask_thread.load_thread(thread_ask_env.project)
    assert loaded["turns"][0]["status"] == "no_results"


def test_ask_index_version_changed_in_thread_summary(thread_ask_env):
    first = thread_ask_env.client.post("/ask", json={"question": _Q1})
    assert first.json()["thread"]["index_version_changed"] is False
    # Simulate reindex between turns.
    thread_ask_env.current["snap"] = _snapshot("v-thread-2")
    second = thread_ask_env.client.post("/ask", json={"question": _Q2})
    assert second.status_code == 200
    # After append, summary is computed against the *current* (new) index: last turn
    # matches current ⇒ flag false on the response; prompt block still warns stale.
    assert "[FILO-THREAD]" in thread_ask_env.calls["last_prompt"]
    assert "stale" in thread_ask_env.calls["last_prompt"]
    assert "ATTENZIONE" in thread_ask_env.calls["last_prompt"]


def test_ask_stream_second_turn_thread_summary(thread_ask_env):
    """Acceptance #9: streaming result includes thread after multi-turn."""
    thread_ask_env.client.post("/ask", json={"question": _Q1})
    with thread_ask_env.client.stream(
        "POST", "/ask", json={"question": _Q2, "stream": True},
    ) as response:
        assert response.status_code == 200
        lines = [ln for ln in response.iter_lines() if ln]
    events = [json.loads(ln) for ln in lines]
    assert events[0]["type"] == "meta"
    assert events[-1]["type"] == "result"
    result = events[-1]["value"]
    assert result["thread"]["turn_count"] == 2
    assert result["thread"]["citations"]
    assert len(result["thread"]["turns"]) == 2
    assert result["thread"]["turns"][0]["question"] == _Q1


def test_ask_accumulated_citations_union_across_turns(thread_ask_env):
    """Acceptance #3: citations grow as deduped union."""
    thread_ask_env.client.post("/ask", json={"question": _Q1})
    thread_ask_env.current["results"] = [
        {"chunk_id": "other.md#1", "doc_id": "other.md", "section": "x",
         "dense_score": 0.5, "colbert_score": 0.4, "authority": 0.3},
        {"chunk_id": _CHUNK_ID, "doc_id": "spec.md", "section": "lock",
         "dense_score": 0.95, "colbert_score": 0.9, "authority": 0.9},
    ]
    second = thread_ask_env.client.post("/ask", json={"question": _Q2})
    cites = second.json()["thread"]["citations"]
    ids = {c["doc_id"] for c in cites}
    assert ids == {"spec.md", "other.md"}
    spec = next(c for c in cites if c["doc_id"] == "spec.md")
    assert spec["last_score"] >= 0.9

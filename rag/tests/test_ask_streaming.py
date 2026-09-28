"""Contratto P1 di POST /ask: JSON storico, NDJSON e pin della collection."""
import asyncio
import json
import math
import threading

import networkx as nx
import numpy as np
import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect, Request

import api.deps as deps
from api import routes_retrieval
from api.models import AskQuery
from core import ask_cache, llm, retrieval


REAL_HYBRID_SEARCH = retrieval.hybrid_search


@pytest.fixture
def ask_app(monkeypatch):
    graph = nx.DiGraph()
    graph.add_node("spec.md", type="document")
    graph.add_node("spec.md#01", type="chunk")
    graph.add_edge("spec.md", "spec.md#01", relation="HAS_SECTION")
    snapshot = deps.IndexSnapshot(
        graph=graph,
        colbert_store={},
        chunks={"spec.md#01": {"text": "Testo verificato"}},
        rule_descriptions={},
        code_store={},
        version="v-stream",
        code_ids=[],
        code_matrix=None,
        collection_name="collection_v1",
    )
    monkeypatch.setattr(deps, "API_KEY", None)
    monkeypatch.setattr(routes_retrieval, "maybe_reload_graph", lambda: None)
    monkeypatch.setattr(routes_retrieval, "current_snapshot", lambda: snapshot)
    monkeypatch.setitem(deps.state, "qdrant", object())
    monkeypatch.setitem(deps.state, "embed_model", object())
    monkeypatch.setattr(
        retrieval, "encode_query",
        lambda *_a, **_k: {"dense": np.array([1.0]), "lexical": {},
                           "colbert": np.zeros((1, 1))},
    )
    calls = {"collections": [], "json": 0, "stream": 0}

    def search(*_args, **kwargs):
        calls["collections"].append(kwargs.get("collection_name"))
        return [{"chunk_id": "spec.md#01", "doc_id": "spec.md", "section": "s",
                 "dense_score": 0.9, "colbert_score": None}]

    monkeypatch.setattr(retrieval, "hybrid_search", search)
    monkeypatch.setitem(llm.config, "llm_settings", {
        "active_provider": "fake", "models": {"fake": "fake-model"},
        "purposes": {"ask": {"model": "ask-model"}},
    })

    def generate(*_args):
        calls["json"] += 1
        return "risposta completa"

    async def stream(*_args):
        calls["stream"] += 1
        yield "risposta "
        yield "progressiva"

    llm.register_provider("fake", generate)
    llm.register_streaming_provider("fake", stream)
    app = FastAPI()
    app.include_router(routes_retrieval.router)
    return app, calls


def test_stream_emette_meta_delta_e_result_con_payload_finale(ask_app):
    app, calls = ask_app
    with TestClient(app, client=("127.0.0.1", 54321)) as client:
        response = client.post("/ask", json={"question": "Quali vincoli?", "stream": True})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["type"] for event in events] == ["meta", "delta", "delta", "result"]
    assert events[0] | {"type": "meta"} == {
        "type": "meta", "request_id": events[0]["request_id"],
        "index_version": "v-stream", "qdrant_collection": "collection_v1",
        "retrieval_strategy": "hybrid", "cached": False, "streaming_native": True,
    }
    assert "".join(event["text"] for event in events if event["type"] == "delta") == "risposta progressiva"
    assert events[-1]["value"]["answer"] == "risposta progressiva"
    assert events[-1]["value"]["status"] == "success"
    assert calls["stream"] == 1 and calls["json"] == 0
    assert calls["collections"] == ["collection_v1"]


def test_stream_asgi_invia_il_primo_delta_prima_che_il_provider_finisca(
    ask_app, monkeypatch,
):
    app, _calls = ask_app
    runtime = deps.AskRuntime(max_active=8, llm_concurrency=2, llm_queue_timeout=3,
                              total_timeout=10)
    app.state.ask_runtime = runtime
    monkeypatch.setattr(routes_retrieval.question_router, "route_question", lambda _q: "hybrid")
    release = asyncio.Event()
    provider_finished = asyncio.Event()
    delta_sent = asyncio.Event()
    messages = []

    async def controlled_stream(*_args):
        try:
            yield "prima"
            await release.wait()
            yield "fine"
        finally:
            provider_finished.set()

    llm.register_streaming_provider("fake", controlled_stream)

    async def scenario():
        request_sent = False
        disconnected = asyncio.Event()
        body = json.dumps({"question": "stream reale", "stream": True}).encode()
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "POST", "scheme": "http", "path": "/ask", "raw_path": b"/ask",
            "query_string": b"", "root_path": "", "headers": [
                (b"content-type", b"application/json"),
            ],
            "client": ("127.0.0.1", 54321), "server": ("test", 80), "state": {},
        }

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)
            if (message["type"] == "http.response.body"
                    and b'"type": "delta"' in message.get("body", b"")
                    and b"prima" in message["body"]):
                delta_sent.set()

        request = asyncio.create_task(app(scope, receive, send))
        await asyncio.wait_for(delta_sent.wait(), timeout=2)
        assert provider_finished.is_set() is False
        assert release.is_set() is False
        assert runtime.active == 1
        release.set()
        await asyncio.wait_for(request, timeout=2)

    asyncio.run(scenario())
    response_body = b"".join(
        message.get("body", b"") for message in messages
        if message["type"] == "http.response.body"
    )
    events = [json.loads(line) for line in response_body.splitlines()]
    assert [event["type"] for event in events] == ["meta", "delta", "delta", "result"]
    assert events[-1]["value"]["answer"] == "primafine"
    assert provider_finished.is_set() is True
    assert runtime.active == 0


def _ask_asgi_scope(body: bytes) -> dict:
    return {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": "/ask", "raw_path": b"/ask", "query_string": b"", "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 54321), "server": ("test", 80), "state": {},
        "_body": body,
    }


async def _receive_once(scope):
    body = scope.pop("_body", None)
    if body is not None:
        return {"type": "http.request", "body": body, "more_body": False}
    await asyncio.Event().wait()


def test_stream_send_start_fallito_non_perde_slot(ask_app):
    app, _calls = ask_app
    runtime = deps.AskRuntime(max_active=8, llm_concurrency=2, llm_queue_timeout=3,
                              total_timeout=10)
    app.state.ask_runtime = runtime
    scope = _ask_asgi_scope(json.dumps({"question": "start", "stream": True}).encode())

    async def send(message):
        if message["type"] == "http.response.start":
            raise OSError("client disconnesso prima degli header")

    async def scenario():
        with pytest.raises(ClientDisconnect):
            await app(scope, lambda: _receive_once(scope), send)

    asyncio.run(scenario())
    assert runtime.active == 0


def test_stream_send_body_fallito_chiude_provider_e_libera_slot(ask_app, monkeypatch):
    app, _calls = ask_app
    runtime = deps.AskRuntime(max_active=8, llm_concurrency=2, llm_queue_timeout=3,
                              total_timeout=10)
    app.state.ask_runtime = runtime
    monkeypatch.setattr(routes_retrieval.question_router, "route_question", lambda _q: "hybrid")
    closed = asyncio.Event()
    never = asyncio.Event()

    async def provider(*_args):
        try:
            yield "prima"
            await never.wait()
        finally:
            closed.set()

    llm.register_streaming_provider("fake", provider)
    scope = _ask_asgi_scope(json.dumps({"question": "body", "stream": True}).encode())

    async def send(message):
        if (message["type"] == "http.response.body"
                and b'"type": "delta"' in message.get("body", b"")):
            raise OSError("client disconnesso sul body")

    async def scenario():
        with pytest.raises(ClientDisconnect):
            await app(scope, lambda: _receive_once(scope), send)
        await asyncio.wait_for(closed.wait(), timeout=2)

    asyncio.run(scenario())
    assert runtime.active == 0


def test_stream_send_fallito_non_blocca_se_il_cleanup_provider_fallisce(
    ask_app, monkeypatch,
):
    app, _calls = ask_app
    runtime = deps.AskRuntime(max_active=8, llm_concurrency=2, llm_queue_timeout=3,
                              total_timeout=10)
    app.state.ask_runtime = runtime
    monkeypatch.setattr(routes_retrieval.question_router, "route_question", lambda _q: "hybrid")
    closed = asyncio.Event()
    never = asyncio.Event()

    async def provider(*_args):
        try:
            yield "prima"
            await never.wait()
        finally:
            closed.set()
            raise RuntimeError("cleanup provider fallito")

    llm.register_streaming_provider("fake", provider)
    scope = _ask_asgi_scope(json.dumps({"question": "body", "stream": True}).encode())

    async def send(message):
        if (message["type"] == "http.response.body"
                and b'"type": "delta"' in message.get("body", b"")):
            raise OSError("client disconnesso sul body")

    async def scenario():
        task = asyncio.create_task(app(scope, lambda: _receive_once(scope), send))
        done, pending = await asyncio.wait({task}, timeout=2)
        if pending:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert task in done, "la risposta è rimasta bloccata nel cleanup del provider"
        with pytest.raises(Exception):
            task.result()
        await asyncio.wait_for(closed.wait(), timeout=2)

    asyncio.run(scenario())
    assert runtime.active == 0


def test_stream_deadline_include_client_lento_e_libera_slot(ask_app, monkeypatch):
    app, _calls = ask_app
    runtime = deps.AskRuntime(max_active=8, llm_concurrency=2, llm_queue_timeout=3,
                              total_timeout=0.02)
    app.state.ask_runtime = runtime
    monkeypatch.setattr(routes_retrieval.question_router, "route_question", lambda _q: "hybrid")
    closed = asyncio.Event()
    never = asyncio.Event()

    async def provider(*_args):
        try:
            yield "prima"
            await never.wait()
        finally:
            closed.set()

    llm.register_streaming_provider("fake", provider)
    scope = _ask_asgi_scope(json.dumps({"question": "lento", "stream": True}).encode())

    async def send(message):
        if (message["type"] == "http.response.body"
                and b'"type": "delta"' in message.get("body", b"")):
            await never.wait()

    async def scenario():
        task = asyncio.create_task(app(scope, lambda: _receive_once(scope), send))
        done, pending = await asyncio.wait({task}, timeout=0.5)
        if pending:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert task in done, "la deadline non ha interrotto il client lento"
        with pytest.raises(TimeoutError):
            task.result()
        await asyncio.wait_for(closed.wait(), timeout=2)

    asyncio.run(scenario())
    assert runtime.active == 0


def test_json_resta_sul_provider_agenerate(ask_app):
    app, calls = ask_app
    with TestClient(app, client=("127.0.0.1", 54321)) as client:
        response = client.post("/ask", json={"question": "Quali vincoli?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "risposta completa"
    assert calls["json"] == 1 and calls["stream"] == 0
    assert calls["collections"] == ["collection_v1"]


def test_reader_non_ripiega_sui_documenti_live_se_manca_un_chunk(ask_app, monkeypatch):
    app, _calls = ask_app
    snapshot = routes_retrieval.current_snapshot()
    snapshot.chunks.clear()
    monkeypatch.setattr(routes_retrieval, "ROLE", "reader")

    with TestClient(app, client=("127.0.0.1", 54321)) as client:
        response = client.post("/ask", json={"question": "chunk mancante"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Testo dei chunk assente dallo snapshot immutabile."


def test_reader_risponde_con_solo_codice_senza_fallback_ai_documenti(ask_app, monkeypatch):
    app, _calls = ask_app
    monkeypatch.setattr(routes_retrieval, "ROLE", "reader")
    monkeypatch.setattr(retrieval, "hybrid_search", lambda *_a, **_k: [])
    monkeypatch.setattr(retrieval, "search_code_symbols", lambda *_a, **_k: [{
        "symbol_id": "api.dto.Request",
        "file": "api/dto.py",
        "name": "Request",
        "kind": "class",
        "implements": "",
        "text": "class Request: pass",
        "source": "semantic",
        "score": 0.9,
    }])

    with TestClient(app, client=("127.0.0.1", 54321)) as client:
        response = client.post("/ask", json={"question": "Mostra il DTO"})

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["implementing_code"][0]["symbol_id"] == "api.dto.Request"


def test_runtime_ammette_solo_il_numero_configurato_e_recupera_slot():
    runtime = deps.AskRuntime(max_active=2, llm_concurrency=1, llm_queue_timeout=3,
                              total_timeout=10)
    assert runtime.try_admit() is True
    assert runtime.try_admit() is True
    assert runtime.try_admit() is False
    runtime.release()
    assert runtime.try_admit() is True


def test_runtime_rifiuta_limiti_non_positivi():
    with pytest.raises(ValueError, match="max_active"):
        deps.AskRuntime(max_active=0, llm_concurrency=1, llm_queue_timeout=3,
                        total_timeout=10)


@pytest.mark.parametrize("value", [math.inf, math.nan])
def test_runtime_rifiuta_timeout_non_finiti(value):
    with pytest.raises(ValueError, match="llm_queue_timeout"):
        deps.AskRuntime(max_active=8, llm_concurrency=2, llm_queue_timeout=value,
                        total_timeout=10)
    with pytest.raises(ValueError, match="total_timeout"):
        deps.AskRuntime(max_active=8, llm_concurrency=2, llm_queue_timeout=3,
                        total_timeout=value)


def test_stream_non_apre_headers_se_snapshot_non_pronto(ask_app, monkeypatch):
    app, _calls = ask_app
    monkeypatch.setattr(routes_retrieval, "current_snapshot", lambda: None)

    with TestClient(app, client=("127.0.0.1", 54321)) as client:
        response = client.post("/ask", json={"question": "pronto?", "stream": True})

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == "Server non ancora inizializzato."


def test_ammissione_rifiuta_la_nona_prima_dell_upstream(ask_app):
    app, _calls = ask_app
    runtime = deps.AskRuntime(max_active=8, llm_concurrency=8, llm_queue_timeout=3,
                              total_timeout=10)
    app.state.ask_runtime = runtime
    entered = 0
    all_entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked_stream(*_args):
        nonlocal entered
        entered += 1
        if entered == 8:
            all_entered.set()
        await release.wait()
        yield "ok"

    llm.register_streaming_provider("fake", blocked_stream)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            tasks = [asyncio.create_task(client.post(
                "/ask", json={"question": f"domanda {i}", "stream": True},
            )) for i in range(8)]
            await asyncio.wait_for(all_entered.wait(), timeout=2)
            rejected = await client.post("/ask", json={"question": "nona", "stream": True})
            assert rejected.status_code == 429
            assert rejected.headers["retry-after"] == "1"
            assert entered == 8
            release.set()
            responses = await asyncio.gather(*tasks)
            assert all(response.status_code == 200 for response in responses)

    asyncio.run(scenario())
    assert runtime.active == 0


def test_limite_llm_accoda_la_terza_senza_superare_due():
    runtime = deps.AskRuntime(max_active=8, llm_concurrency=2, llm_queue_timeout=3,
                              total_timeout=10)

    async def scenario():
        await runtime.acquire_llm()
        await runtime.acquire_llm()
        third = asyncio.create_task(runtime.acquire_llm())
        await asyncio.sleep(0)  # solo checkpoint dell'event loop, nessuna attesa temporale
        assert third.done() is False
        runtime.release_llm()
        await third
        runtime.release_llm()
        runtime.release_llm()

    asyncio.run(scenario())


def test_route_esegue_due_generazioni_in_parallelo_e_accoda_la_terza(ask_app, monkeypatch):
    app, _calls = ask_app
    runtime = deps.AskRuntime(max_active=8, llm_concurrency=2, llm_queue_timeout=3,
                              total_timeout=10)
    app.state.ask_runtime = runtime
    monkeypatch.setattr(routes_retrieval.question_router, "route_question", lambda _q: "hybrid")

    async def unbounded_embed(fn, *args, **kwargs):
        return await deps.run_in_threadpool_until_complete(fn, *args, **kwargs)

    monkeypatch.setattr(routes_retrieval, "embed_in_threadpool", unbounded_embed)
    two_entered = asyncio.Event()
    release = asyncio.Event()
    active = 0
    maximum = 0
    calls = 0

    async def measured_stream(*_args):
        nonlocal active, maximum, calls
        calls += 1
        active += 1
        maximum = max(maximum, active)
        if active == 2:
            two_entered.set()
        try:
            await release.wait()
            yield "ok"
        finally:
            active -= 1

    llm.register_streaming_provider("fake", measured_stream)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            tasks = [asyncio.create_task(client.post(
                "/ask", json={"question": question, "stream": True},
            )) for question in ("domanda alpha", "domanda beta", "domanda gamma")]
            await asyncio.wait_for(two_entered.wait(), timeout=2)
            assert calls == maximum == active == 2
            release.set()
            responses = await asyncio.gather(*tasks)
            assert all(response.status_code == 200 for response in responses)
            assert all(json.loads(response.text.splitlines()[-1])["type"] == "result"
                       for response in responses)

    asyncio.run(scenario())
    assert calls == 3
    assert maximum == 2
    assert active == runtime.active == 0


def test_route_pinna_la_collection_fisica_per_dense_e_sparse(ask_app, monkeypatch):
    app, _calls = ask_app

    class EmptyPoints:
        points = []

    class AliasSwitchingQdrant:
        def __init__(self):
            self.alias_target = "collection_v1"
            self.requested = []
            self.resolved = []

        def query_points(self, *, collection_name, **_kwargs):
            self.requested.append(collection_name)
            self.resolved.append(
                self.alias_target
                if collection_name == routes_retrieval.COLLECTION_NAME
                else collection_name
            )
            if len(self.requested) == 1:
                self.alias_target = "collection_v2"
            return EmptyPoints()

    qdrant = AliasSwitchingQdrant()
    monkeypatch.setitem(deps.state, "qdrant", qdrant)
    monkeypatch.setattr(retrieval, "hybrid_search", REAL_HYBRID_SEARCH)

    with TestClient(app, client=("127.0.0.1", 54321)) as client:
        response = client.post(
            "/ask", json={"question": "pin collection", "stream": True},
        )

    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]["value"]["status"] == "no_results"
    assert qdrant.requested == ["collection_v1", "collection_v1"]
    assert qdrant.resolved == ["collection_v1", "collection_v1"]


def test_cancel_dopo_delta_chiude_provider_non_popola_cache_e_libera_slot(ask_app):
    app, _calls = ask_app
    runtime = deps.AskRuntime(max_active=8, llm_concurrency=2, llm_queue_timeout=3,
                              total_timeout=10)
    app.state.ask_runtime = runtime
    started = asyncio.Event()
    closed = asyncio.Event()
    release = asyncio.Event()

    async def blocked_stream(*_args):
        try:
            started.set()
            yield "parziale"
            await release.wait()
            yield "fine"
        finally:
            closed.set()

    llm.register_streaming_provider("fake", blocked_stream)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            task = asyncio.create_task(client.post(
                "/ask", json={"question": "cancel", "stream": True},
            ))
            await asyncio.wait_for(started.wait(), timeout=2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(closed.wait(), timeout=2)

    asyncio.run(scenario())
    assert runtime.active == 0
    assert len(ask_cache.for_app(app)) == 0


def test_cancel_durante_emit_chiude_subito_lo_stream_llm_esterno(ask_app):
    app, _calls = ask_app
    delta_entered = asyncio.Event()
    never = asyncio.Event()
    closed = asyncio.Event()

    async def provider(*_args):
        try:
            yield "prima"
            yield "seconda"
        finally:
            closed.set()

    async def blocked_emit(event):
        if event["type"] == "delta":
            delta_entered.set()
            await never.wait()

    llm.register_streaming_provider("fake", provider)

    async def scenario():
        request = Request({"type": "http", "app": app})
        resources = routes_retrieval._ask_resources()
        task = asyncio.create_task(routes_retrieval._ask_pipeline(
            request, AskQuery(question="backpressure"),
            emit=blocked_emit, resources=resources,
        ))
        await asyncio.wait_for(delta_entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(closed.wait(), timeout=2)

    asyncio.run(scenario())
    assert len(ask_cache.for_app(app)) == 0


def test_cancel_durante_cpu_non_libera_slot_prima_della_fine_del_thread(ask_app, monkeypatch):
    app, _calls = ask_app
    runtime = deps.AskRuntime(max_active=8, llm_concurrency=2, llm_queue_timeout=3,
                              total_timeout=10)
    app.state.ask_runtime = runtime
    entered = threading.Event()
    release = threading.Event()

    def blocked_encode(*_args):
        entered.set()
        release.wait(timeout=2)
        return {"dense": np.array([1.0]), "lexical": {}, "colbert": np.zeros((1, 1))}

    monkeypatch.setattr(retrieval, "encode_query", blocked_encode)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            task = asyncio.create_task(client.post(
                "/ask", json={"question": "cpu", "stream": True},
            ))
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            cancellation_ack = asyncio.Event()

            async def observe_cancellation():
                with pytest.raises(asyncio.CancelledError):
                    await task
                cancellation_ack.set()

            observer = asyncio.create_task(observe_cancellation())
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(
                    asyncio.shield(cancellation_ack.wait()), timeout=0.05,
                )
            assert runtime.active == 1
            assert task.done() is False
            release.set()
            await asyncio.wait_for(cancellation_ack.wait(), timeout=2)
            await observer

    asyncio.run(scenario())
    assert runtime.active == 0


def test_cancel_cpu_ha_precedenza_anche_se_il_worker_finisce_con_errore():
    entered = threading.Event()
    release = threading.Event()

    def failing_worker():
        entered.set()
        release.wait(timeout=2)
        raise RuntimeError("errore tardivo")

    async def scenario():
        task = asyncio.create_task(
            deps.run_in_threadpool_until_complete(failing_worker),
        )
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_errore_dopo_delta_e_terminale_e_non_entra_in_cache(ask_app):
    app, _calls = ask_app

    async def failing_stream(*_args):
        yield "parziale"
        raise llm.LLMError("provider interrotto")

    llm.register_streaming_provider("fake", failing_stream)
    with TestClient(app, client=("127.0.0.1", 54321)) as client:
        response = client.post("/ask", json={"question": "errore", "stream": True})

    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["type"] for event in events] == ["meta", "delta", "error"]
    assert events[-1]["detail"] == "provider interrotto"
    assert len(ask_cache.for_app(app)) == 0


def test_stream_completato_popola_cache_e_hit_non_richiama_provider(ask_app):
    app, calls = ask_app
    with TestClient(app, client=("127.0.0.1", 54321)) as client:
        first = client.post("/ask", json={"question": "cache", "stream": True})
        second = client.post("/ask", json={"question": "cache", "stream": True})

    assert first.status_code == second.status_code == 200
    events = [json.loads(line) for line in second.text.splitlines()]
    assert [event["type"] for event in events] == ["meta", "delta", "result"]
    assert events[0]["cached"] is True
    assert events[-1]["value"]["cached"] is True
    assert calls["stream"] == 1


def test_astensione_spezzata_resta_nel_delta_ma_il_result_e_normalizzato(ask_app):
    app, _calls = ask_app

    async def abstaining_stream(*_args):
        yield "**[ASTEN"
        yield "SIONE]** contesto insufficiente"

    llm.register_streaming_provider("fake", abstaining_stream)
    with TestClient(app, client=("127.0.0.1", 54321)) as client:
        response = client.post("/ask", json={"question": "astensione", "stream": True})

    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]["type"] == "result"
    assert events[-1]["value"]["status"] == "abstained"
    assert events[-1]["value"]["answer"] == "contesto insufficiente"


def test_timeout_coda_llm_diventa_errore_stream_terminale(ask_app):
    app, _calls = ask_app
    runtime = deps.AskRuntime(max_active=8, llm_concurrency=2, llm_queue_timeout=3,
                              total_timeout=10)
    app.state.ask_runtime = runtime

    async def queue_timeout():
        raise TimeoutError

    runtime.acquire_llm = queue_timeout
    with TestClient(app, client=("127.0.0.1", 54321)) as client:
        response = client.post("/ask", json={"question": "coda", "stream": True})

    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["type"] for event in events] == ["meta", "error"]
    assert events[-1]["detail"] == "Coda inferenza piena: riprova più tardi."
    assert runtime.active == 0


def test_timeout_totale_e_finito_per_json_e_stream(ask_app, monkeypatch):
    app, _calls = ask_app
    runtime = deps.AskRuntime(max_active=8, llm_concurrency=2, llm_queue_timeout=3,
                              total_timeout=0.01)
    app.state.ask_runtime = runtime
    never = asyncio.Event()

    async def blocked_pipeline(*_args, **_kwargs):
        await never.wait()

    monkeypatch.setattr(routes_retrieval, "_ask_pipeline", blocked_pipeline)
    with TestClient(app, client=("127.0.0.1", 54321)) as client:
        json_response = client.post("/ask", json={"question": "timeout JSON"})
        with pytest.raises(TimeoutError):
            client.post(
                "/ask", json={"question": "timeout stream", "stream": True},
            )

    assert json_response.status_code == 504
    assert json_response.json()["detail"] == "Timeout totale della richiesta /ask."
    assert runtime.active == 0

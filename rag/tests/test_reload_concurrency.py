"""Auto-reload dell'indice fuori dall'event loop e serializzato.

Prima `maybe_reload_graph()` (→ reload_index_state: load_artifacts, scansione dei documenti,
matrice del codice) girava in modo sincrono dentro handler `async def`: per tutta la durata
del caricamento l'event loop era fermo e NESSUNA richiesta veniva servita (health compreso).
In più due trigger concorrenti (due richieste, o una richiesta e l'on_success del thread di
reindex) caricavano entrambi, senza lock. Vedi api.deps._reload_lock.
"""
import asyncio
import threading
import time

import httpx
import pytest
from fastapi import FastAPI

import api.deps as deps
from api import routes_graph


def _snapshot(version: str) -> deps.IndexSnapshot:
    return deps.IndexSnapshot(
        graph=None, colbert_store={}, chunks={}, rule_descriptions={},
        code_store={}, version=version, code_ids=[], code_matrix=None,
    )


@pytest.fixture
def reload_env(monkeypatch):
    """Snapshot v1 servito, CURRENT già su v2: il primo trigger deve ricaricare.
    `gate` tiene fermo il caricamento finché il test non lo rilascia."""
    monkeypatch.setattr(deps, "API_KEY", None)
    monkeypatch.setitem(deps.state, "snapshot", _snapshot("v1"))
    monkeypatch.setitem(deps.state, "_graph_mtime", "v1")
    monkeypatch.setitem(deps.state, "reload_error", None)
    monkeypatch.setattr(deps, "_graph_version", lambda: "v2")

    env = {"loads": 0, "started": threading.Event(), "done": threading.Event(),
           "gate": threading.Event()}

    def slow_load(**_kwargs):
        env["loads"] += 1
        env["started"].set()
        env["gate"].wait(2)
        env["done"].set()
        return _snapshot("v2")

    monkeypatch.setattr(deps, "_load_index_snapshot", slow_load)
    return env


def test_reload_lento_non_blocca_l_event_loop(reload_env):
    """Mentre /api/graph/all è fermo nel reload, una route che non ricarica risponde subito.
    Senza offload il loop resta bloccato ~2s nel caricamento e il ping arriva a load finito."""
    app = FastAPI()
    app.include_router(routes_graph.router)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            reload_req = asyncio.create_task(client.get("/api/graph/all"))
            deadline = time.monotonic() + 3
            while not reload_env["started"].is_set() and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            assert reload_env["started"].is_set()

            t0 = time.monotonic()
            pong = await client.get("/ping")
            elapsed = time.monotonic() - t0
            assert pong.status_code == 200
            assert elapsed < 0.5
            assert not reload_env["done"].is_set(), "ping servito solo a reload finito"

            reload_env["gate"].set()
            resp = await reload_req
            # graph=None nello snapshot finto: 503, ma dopo aver pubblicato v2.
            assert resp.status_code == 503

    asyncio.run(scenario())
    assert reload_env["loads"] == 1
    assert deps.state["snapshot"].version == "v2"


def test_due_trigger_concorrenti_un_solo_caricamento(reload_env):
    """Due richieste che vedono CURRENT cambiato insieme: una carica, l'altra attende il
    lock, ricontrolla la baseline (già v2) e non ricarica."""
    barrier = threading.Barrier(2)

    def trigger():
        barrier.wait()
        deps.maybe_reload_graph()

    threads = [threading.Thread(target=trigger) for _ in range(2)]
    for t in threads:
        t.start()
    assert reload_env["started"].wait(2)
    time.sleep(0.2)  # il secondo thread è arrivato al lock (o al controllo veloce)
    reload_env["gate"].set()
    for t in threads:
        t.join(3)
    assert reload_env["loads"] == 1
    assert deps.state["snapshot"].version == "v2"
    assert deps.state["_graph_mtime"] == "v2"


def test_reload_del_job_e_richiesta_concorrente_un_solo_caricamento(reload_env):
    """L'on_success del thread di reindex (reload_index_state esplicito) sta caricando v2;
    una richiesta che nel frattempo vede CURRENT=v2 attende e non ricarica di nuovo."""
    job = threading.Thread(target=deps.reload_index_state)
    job.start()
    assert reload_env["started"].wait(2)

    request = threading.Thread(target=deps.maybe_reload_graph)
    request.start()
    time.sleep(0.2)
    reload_env["gate"].set()
    job.join(3)
    request.join(3)
    assert reload_env["loads"] == 1
    assert deps.state["snapshot"].version == "v2"

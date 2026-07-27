"""Test di scripts/bench.py — solo meccanica (parser/aggregatori/struttura JSON), con
httpx2.MockTransport per fingere le risposte del server: nessuna rete, nessun modello.
La run REALE (server acceso) è manuale e va allegata alla PR — vedi README, sezione
"Benchmark baseline"."""
import json

import httpx2
import pytest

import scripts.bench as bench

URL = "http://test-server"


def _client(handler) -> httpx2.Client:
    return httpx2.Client(transport=httpx2.MockTransport(handler))


# ---------------------------------------------------------------------------
# Percentili: fondamenta di ogni sezione del bench
# ---------------------------------------------------------------------------

def test_percentile_su_lista_vuota_e_none():
    assert bench.p50([]) is None
    assert bench.p95([]) is None


def test_percentile_su_singolo_valore():
    assert bench.p50([42.0]) == 42.0
    assert bench.p95([42.0]) == 42.0


def test_p50_p95_su_valori_noti():
    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert bench.p50(values) == pytest.approx(55.0)
    assert bench.p95(values) == pytest.approx(95.5)


def test_avg_su_lista_vuota_e_none():
    assert bench._avg([]) is None


def test_avg_arrotonda_a_due_decimali():
    assert bench._avg([1, 2, 4]) == pytest.approx(2.33)


# ---------------------------------------------------------------------------
# bench_retrieve: p50/p95 su n query del golden-set reale
# ---------------------------------------------------------------------------

def test_bench_retrieve_calcola_p50_p95_su_n_query():
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/api/retrieve"
        return httpx2.Response(200, json={"query": "q", "k": 5, "results": []})

    with _client(handler) as client:
        result = bench.bench_retrieve(client, URL, n=10)

    assert result["n"] == 10
    assert len(result["queries"]) == 10
    assert result["p50_ms"] >= 0
    assert result["p95_ms"] >= result["p50_ms"]
    assert "skipped" not in result


def test_bench_retrieve_skipped_se_server_giu():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connessione rifiutata", request=request)

    with _client(handler) as client:
        result = bench.bench_retrieve(client, URL, n=3)

    assert result["skipped"] is True
    assert "/api/retrieve" in result["reason"]


# ---------------------------------------------------------------------------
# bench_ask: media delle latenze, con o senza i campi in risposta
# ---------------------------------------------------------------------------

def test_bench_ask_senza_campi_latency_in_risposta_aggiunge_nota():
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/ask"
        return httpx2.Response(200, json={"status": "success", "answer": "ok"})

    with _client(handler) as client:
        result = bench.bench_ask(client, URL, queries=["domanda 1", "domanda 2"])

    assert result["n"] == 2
    assert result["avg_latency_retrieval_ms"] is None
    assert result["avg_latency_generation_ms"] is None
    assert result["avg_latency_total_ms"] is None
    assert result["avg_latency_total_ms_client"] > 0
    assert "note" in result
    assert "non è presente nella risposta" in result["note"]


def test_bench_ask_con_campi_latency_in_risposta_li_usa():
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={
            "status": "success", "answer": "ok",
            "latency": {"retrieval_ms": 12.5, "generation_ms": 800.0, "total_ms": 815.0},
        })

    with _client(handler) as client:
        result = bench.bench_ask(client, URL, queries=["domanda 1"])

    assert result["avg_latency_retrieval_ms"] == pytest.approx(12.5)
    assert result["avg_latency_generation_ms"] == pytest.approx(800.0)
    assert result["avg_latency_total_ms"] == pytest.approx(815.0)
    assert "note" not in result


def test_bench_ask_skipped_se_server_giu():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("giu", request=request)

    with _client(handler) as client:
        result = bench.bench_ask(client, URL, queries=["q"])

    assert result["skipped"] is True


# ---------------------------------------------------------------------------
# bench_semantic_map
# ---------------------------------------------------------------------------

def test_bench_semantic_map_riporta_truncated_e_n_points():
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/api/graph/semantic-map"
        return httpx2.Response(200, json={
            "points": [{"id": "a"}, {"id": "b"}], "duplicates": [], "truncated": True,
        })

    with _client(handler) as client:
        result = bench.bench_semantic_map(client, URL)

    assert result["n"] == 1
    assert result["n_points"] == 2
    assert result["truncated"] is True
    assert result["latency_ms"] >= 0


def test_bench_semantic_map_skipped_se_server_giu():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("giu", request=request)

    with _client(handler) as client:
        result = bench.bench_semantic_map(client, URL)

    assert result["skipped"] is True


# ---------------------------------------------------------------------------
# incremental_noop / full_rebuild: coda + polling del journal
# ---------------------------------------------------------------------------

def _job_sequence_handler(statuses: list[str]):
    """Handler che simula POST /api/reindex (accoda un job) seguito da GET
    /api/reindex/{job_id} che avanza attraverso `statuses` a ogni chiamata successiva
    (l'ultimo status si ripete se interrogato oltre la lunghezza della lista)."""
    calls = {"get": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            return httpx2.Response(202, json={"job_id": "job-1", "status": "queued"})
        idx = min(calls["get"], len(statuses) - 1)
        calls["get"] += 1
        status = statuses[idx]
        return httpx2.Response(200, json={
            "job_id": "job-1", "status": status,
            "created_at": "2026-07-21T10:00:00+00:00",
            "finished_at": "2026-07-21T10:00:05+00:00" if status in bench._TERMINAL_JOB_STATES else None,
        })

    return handler


def test_bench_incremental_noop_polla_fino_a_stato_terminale(monkeypatch):
    monkeypatch.setattr(bench.time, "sleep", lambda s: None)
    handler = _job_sequence_handler(["queued", "running", "completed"])

    with _client(handler) as client:
        result = bench.bench_incremental_noop(client, URL)

    assert result["status"] == "completed"
    assert result["job_id"] == "job-1"
    assert result["duration_seconds"] == pytest.approx(5.0)
    assert "note" in result


def test_bench_incremental_noop_skipped_senza_job_id():
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(202, json={})

    with _client(handler) as client:
        result = bench.bench_incremental_noop(client, URL)

    assert result["skipped"] is True


def test_bench_full_rebuild_skipped_di_default():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("non deve chiamare il server se enabled=False")

    with _client(handler) as client:
        result = bench.bench_full_rebuild(client, URL, enabled=False)

    assert result == {"skipped": True,
                      "reason": "full rebuild eseguito solo con --with-rebuild esplicito (operazione lunga)"}


def test_bench_full_rebuild_gira_se_abilitato(monkeypatch):
    monkeypatch.setattr(bench.time, "sleep", lambda s: None)
    handler = _job_sequence_handler(["running", "completed"])

    with _client(handler) as client:
        result = bench.bench_full_rebuild(client, URL, enabled=True)

    assert result["status"] == "completed"
    assert "skipped" not in result


# ---------------------------------------------------------------------------
# get_index_version
# ---------------------------------------------------------------------------

def test_get_index_version_legge_current():
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"current": "v20260721T100000", "versions": []})

    with _client(handler) as client:
        assert bench.get_index_version(client, URL) == "v20260721T100000"


def test_get_index_version_none_se_server_giu():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("giu", request=request)

    with _client(handler) as client:
        assert bench.get_index_version(client, URL) is None


# ---------------------------------------------------------------------------
# save_results: struttura del JSON scritto su disco
# ---------------------------------------------------------------------------

def test_save_results_scrive_json_valido_con_le_chiavi_attese(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "RESULTS_DIR", tmp_path)
    payload = {
        "timestamp": "2026-07-21T10:00:00+00:00", "url": URL, "index_version": "v1",
        "retrieve": {"n": 10, "p50_ms": 1.0, "p95_ms": 2.0, "queries": []},
        "ask": {"n": 3},
        "semantic_map": {"n": 1},
        "incremental_noop": {"n": 1},
        "full_rebuild": {"skipped": True, "reason": "x"},
    }

    out = bench.save_results(payload)

    assert out.exists()
    assert out.name.startswith("bench_") and out.name.endswith(".json")
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == payload


# ---------------------------------------------------------------------------
# run_bench: assembla tutte le sezioni end-to-end (fake server unico)
# ---------------------------------------------------------------------------

def test_run_bench_assembla_tutte_le_sezioni(monkeypatch):
    monkeypatch.setattr(bench.time, "sleep", lambda s: None)

    def handler(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path == "/api/index/versions":
            return httpx2.Response(200, json={"current": "v1", "versions": ["v1"]})
        if path == "/api/retrieve":
            return httpx2.Response(200, json={"results": []})
        if path == "/ask":
            return httpx2.Response(200, json={"status": "success", "answer": "ok"})
        if path == "/api/graph/semantic-map":
            return httpx2.Response(200, json={"points": [], "duplicates": [], "truncated": False})
        if path == "/api/reindex" and request.method == "POST":
            return httpx2.Response(202, json={"job_id": "job-1", "status": "queued"})
        if path == "/api/reindex/job-1":
            return httpx2.Response(200, json={
                "job_id": "job-1", "status": "completed",
                "created_at": "2026-07-21T10:00:00+00:00",
                "finished_at": "2026-07-21T10:00:01+00:00",
            })
        raise AssertionError(f"path inatteso: {path}")

    with _client(handler) as client:
        payload = bench.run_bench(client, URL, with_rebuild=False)

    assert set(payload.keys()) == {
        "timestamp", "url", "index_version", "retrieve", "ask",
        "semantic_map", "incremental_noop", "full_rebuild",
    }
    assert payload["index_version"] == "v1"
    assert payload["retrieve"]["n"] == 10
    assert payload["full_rebuild"]["skipped"] is True

"""Test HTTP delle route S3 (piano: docs/00_meta_governance/piano_intake_import.md):
POST /api/intake/generate avvia un job in background e risponde subito col job_id; GET
/api/intake/generate/{job_id} ne riporta lo stato. Il lavoro vero (retrieval + LLM) è
stubbato via _server_generate — già coperto senza HTTP da test_doc_generation.py; qui si
esercita solo il wiring: risposta 202, polling, mappatura degli errori, 404 su id
sconosciuto, 422 su descrizione vuota."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import routes_intake
from core import doc_generation, intake


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(intake, "INTAKE_STAGING_DIR", tmp_path / "staging")
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    monkeypatch.setattr(intake, "DOCS_DIR", docs)
    monkeypatch.setattr(routes_intake, "_server_reindex", lambda paths: {"noop": False})
    monkeypatch.setattr(routes_intake, "reload_index_state", lambda: None)
    # Manager fresco per test: isola i job (e i thread daemon) di questo test da quelli
    # accumulati dal singleton di modulo in test precedenti.
    monkeypatch.setattr(routes_intake, "_generation_manager", doc_generation.GenerationManager())
    app = FastAPI()
    app.include_router(routes_intake.router)
    return TestClient(app, client=("127.0.0.1", 54321))


def _poll_until_terminal(client: TestClient, job_id: str):
    """I job girano su un thread daemon reale (nessun mock di threading in questi test):
    join_all del manager di modulo sincronizza senza polling attivo."""
    assert routes_intake._generation_manager.join_all(timeout=5)
    return client.get(f"/api/intake/generate/{job_id}")


def test_route_generate_returns_202_with_job_id_then_done_status(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(routes_intake, "_server_generate",
                        lambda descrizione, n_file, categoria_target: {
                            "generati": [{"id": "abc"}], "scartati": [],
                            "n_generati": 1, "n_scartati": 0,
                            "latency": {"retrieval_ms": 1.0, "generation_ms": 2.0, "total_ms": 3.0},
                        })

    resp = client.post("/api/intake/generate", json={
        "descrizione": "genera la doc di una feature", "n_file": 1,
        "categoria_suggerita": "04_knowledge_informative",
    })
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    assert resp.json()["status"] in ("pending", "running", "done")

    status = _poll_until_terminal(client, job_id)
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "done"
    assert body["result"]["n_generati"] == 1


def test_route_generate_empty_descrizione_returns_422(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/api/intake/generate", json={"descrizione": "   "})
    assert resp.status_code == 422


def test_route_generate_status_unknown_job_returns_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.get("/api/intake/generate/non-esiste")
    assert resp.status_code == 404


def test_route_generate_job_failed_is_reported_not_raised(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    def _boom(descrizione, n_file, categoria_target):
        raise RuntimeError("Ollama irraggiungibile")

    monkeypatch.setattr(routes_intake, "_server_generate", _boom)

    resp = client.post("/api/intake/generate", json={"descrizione": "una feature"})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    status = _poll_until_terminal(client, job_id)
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "failed"
    assert "Ollama irraggiungibile" in body["error"]


def test_route_generate_defaults_n_file_and_categoria(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    captured = {}

    def _capture(descrizione, n_file, categoria_target):
        captured.update(descrizione=descrizione, n_file=n_file, categoria_target=categoria_target)
        return {"n_generati": 0, "n_scartati": 0, "generati": [], "scartati": [],
                "latency": {"retrieval_ms": 0, "generation_ms": 0, "total_ms": 0}}

    monkeypatch.setattr(routes_intake, "_server_generate", _capture)
    resp = client.post("/api/intake/generate", json={"descrizione": "una feature"})
    assert resp.status_code == 202
    _poll_until_terminal(client, resp.json()["job_id"])

    assert captured["categoria_target"] == "04_knowledge_informative"
    from core.config import INTAKE_GENERATION_MAX_FILES
    assert captured["n_file"] == INTAKE_GENERATION_MAX_FILES

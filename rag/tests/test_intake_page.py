"""Test della route S4/S5 (piano: docs/00_meta_governance/piano_intake_import.md):
GET /intake serve la pagina unificata con le 4 zone (Genera con Ollama, Importa documenti,
In staging, Importa progetto da path). Nessuna logica di dominio da testare qui: la pagina
è self-contained e passa dalle API già testate in test_intake_staging.py /
test_intake_generate_routes.py / test_project_import.py."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import routes_pages


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes_pages.router)
    return TestClient(app, client=("127.0.0.1", 54321))


def test_intake_route_returns_200_with_four_blocks():
    client = _client()
    resp = client.get("/intake")
    assert resp.status_code == 200
    body = resp.text
    assert "section-genera" in body
    assert "section-importa" in body
    assert "section-staging" in body
    assert "section-progetti" in body


def test_intake_route_wires_the_existing_apis_not_new_ones():
    client = _client()
    body = client.get("/intake").text
    assert "/api/intake/generate" in body
    assert "/api/intake/docs" in body
    assert "/api/intake/staged" in body
    assert "/api/intake/project/plan" in body
    assert "/api/intake/project/apply" in body


def test_intake_route_exposes_project_brief_control():
    """S6: la zona import contiene il controllo Project brief cablato sull'endpoint
    /api/intake/project/brief (attivo lato UI solo dopo un import riuscito)."""
    client = _client()
    body = client.get("/intake").text
    assert "prj-brief-btn" in body
    assert "/api/intake/project/brief" in body

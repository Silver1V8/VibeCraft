"""Test della route S4/S5 (piano: docs/00_meta_governance/piano_intake_import.md):
GET /intake serve la pagina unificata con le 4 zone (Genera con Ollama, Importa documenti,
In staging, Importa progetto da path). Nessuna logica di dominio da testare qui: la pagina
è self-contained e passa dalle API già testate in test_intake_staging.py /
test_intake_generate_routes.py / test_project_import.py."""
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import routes_pages
from core.config import STATIC_DIR


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes_pages.router)
    return TestClient(app, client=("127.0.0.1", 54321))


def _page_and_scripts(client: TestClient) -> str:
    """HTML di /intake più gli script di pagina che referenzia: il codice che chiama le API
    sta in /static/pages/intake.js (fuori dal template per la CSP)."""
    html = client.get("/intake?workspace=1").text
    scripts = re.findall(r'<script src="/static/(pages/[\w.-]+\.js)"', html)
    assert scripts, "la pagina non carica il proprio script"
    return html + "".join((STATIC_DIR / rel).read_text(encoding="utf-8") for rel in scripts)


def test_intake_route_returns_200_with_four_blocks():
    client = _client()
    resp = client.get("/intake?workspace=1")
    assert resp.status_code == 200
    body = resp.text
    assert "section-genera" in body
    assert "section-importa" in body
    assert "section-staging" in body
    assert "section-progetti" in body


def test_intake_route_wires_the_existing_apis_not_new_ones():
    client = _client()
    body = _page_and_scripts(client)
    assert "/api/intake/generate" in body
    assert "/api/intake/docs" in body
    assert "/api/intake/staged" in body
    assert "/api/intake/project/plan" in body
    assert "/api/intake/project/apply" in body


def test_intake_route_exposes_project_brief_control():
    """S6: la zona import contiene il controllo Project brief cablato sull'endpoint
    /api/intake/project/brief."""
    client = _client()
    body = _page_and_scripts(client)
    assert "prj-brief-btn" in body
    assert "/api/intake/project/brief" in body


def test_intake_route_lets_you_choose_the_project_for_the_brief():
    """Il brief è di un PROGETTO, non di un target: la pagina espone la scelta e la
    popola dagli import registrati, senza dipendere da un import fatto in questa
    sessione (altrimenti un reload spegneva il controllo per sempre)."""
    client = _client()
    body = _page_and_scripts(client)
    assert "prj-brief-progetto" in body
    assert "/api/intake/project/imports" in body

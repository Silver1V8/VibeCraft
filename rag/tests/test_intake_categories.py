"""Cartelle docs/ personalizzate per progetto (2026-11-03): la tendina «Categoria docs/
target» di Intake elenca le sottocartelle reali di docs/ e l'utente ne crea di nuove.
Il nome arriva dal client, quindi è un confine di fiducia: qui si fissano validazione,
normalizzazione, elenco e ammissione in approve."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import intake, llm

pytestmark = pytest.mark.usefixtures("legacy_workflow_project")


@pytest.mark.parametrize("raw,expected", [
    ("06_game_design", "06_game_design"),
    ("  Note di team  ", "Note_di_team"),
    ("tetris-browser", "tetris-browser"),
    ("A" * 64, "A" * 64),
])
def test_create_doc_category_normalizes_and_creates(tmp_path, raw, expected):
    assert intake.create_doc_category(raw, docs_dir=tmp_path) == expected
    assert (tmp_path / expected).is_dir()


@pytest.mark.parametrize("raw", [
    "", "   ", ".", "..", "../fuori", "a/b", "a\\b", "C:", "C:\\x", ".nascosta", "nome.md",
    "con", "CON", "nul", "lpt1", "Com9", "è_bello", "a\x00b", "-trattino", "A" * 65,
])
def test_create_doc_category_rejects_unsafe_names(tmp_path, raw):
    with pytest.raises(intake.InvalidCategoryError):
        intake.create_doc_category(raw, docs_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_create_doc_category_is_idempotent_case_insensitive(tmp_path):
    (tmp_path / "Design").mkdir()
    assert intake.create_doc_category("design", docs_dir=tmp_path) == "Design"
    assert [p.name for p in tmp_path.iterdir()] == ["Design"]


def test_doc_categories_lists_only_real_visible_folders(tmp_path):
    for name in ("04_knowledge_informative", "00_meta_governance", "mie_note", ".git"):
        (tmp_path / name).mkdir()
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    assert intake.doc_categories(docs_dir=tmp_path) == [
        "00_meta_governance", "04_knowledge_informative", "mie_note"]
    assert intake.doc_categories(docs_dir=tmp_path / "manca") == []


def _client(tmp_path, monkeypatch) -> TestClient:
    from api import routes_intake
    monkeypatch.setattr(intake, "INTAKE_STAGING_DIR", tmp_path / "staging")
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    monkeypatch.setattr(intake, "DOCS_DIR", docs)
    app = FastAPI()
    app.include_router(routes_intake.router)
    return TestClient(app, client=("127.0.0.1", 54321))


def test_routes_list_and_create_category(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    (tmp_path / "docs" / "00_meta_governance").mkdir()
    assert client.get("/api/intake/categories").json() == {"categorie": ["00_meta_governance"]}

    resp = client.post("/api/intake/categories", json={"nome": "Game design"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"categoria": "Game_design",
                           "categorie": ["00_meta_governance", "Game_design"]}
    assert (tmp_path / "docs" / "Game_design").is_dir()

    bad = client.post("/api/intake/categories", json={"nome": "../fuori"})
    assert bad.status_code == 422
    assert "Nome di cartella non valido" in bad.json()["detail"]
    assert not (tmp_path / "fuori").exists()


def test_approve_accepts_custom_folder_with_prudent_classification(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/intake/categories", json={"nome": "game_design"}).status_code == 200
    doc_id = client.post("/api/intake/docs",
                         files={"file": ("d.txt", b"regole del tetris", "text/plain")}).json()["id"]
    resp = client.post(f"/api/intake/staged/{doc_id}/approve",
                       json={"categoria": "game_design", "nome_file": "regole"})
    assert resp.status_code == 200, resp.text
    written = (tmp_path / "docs" / "game_design" / "regole.md").read_text(encoding="utf-8")
    assert "classification: METHODOLOGY" in written
    assert "path: docs/game_design/regole.md" in written


def test_generation_has_its_own_llm_purpose(monkeypatch):
    # Riga dedicata in Impostazioni → per attività: la generazione può andare su un LLM
    # cloud senza spostare il Canvas. Senza override resta sulla scelta del Canvas (prima
    # era lo stesso scopo): nessun corpus verso il cloud per il solo cambio di scopo.
    from types import SimpleNamespace
    from core import doc_generation, llm_settings_store
    assert "intake" in llm.PURPOSES
    overlay = llm_settings_store.build_overlay(
        {"mode": "custom", "purposes": {"intake": {"provider": "anthropic", "model": "claude-opus-5-5"}}})
    assert overlay["purposes"]["intake"] == {"provider": "anthropic", "model": "claude-opus-5-5"}

    monkeypatch.setattr(llm, "_llm_settings", lambda: SimpleNamespace(purposes={"canvas": {"provider": "ollama"}}))
    assert doc_generation._generation_purpose() == "canvas"
    monkeypatch.setattr(llm, "_llm_settings", lambda: SimpleNamespace(purposes=overlay["purposes"]))
    assert doc_generation._generation_purpose() == "intake"


def _junction(link, target) -> bool:
    try:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
        return True
    except (ImportError, OSError):
        return False


def test_links_in_docs_are_skipped_and_never_created_through(tmp_path, monkeypatch):
    """Una junction in docs/ non compare in tendina, non blocca l'approve sulle categorie
    standard e non diventa una cartella «esistente» attraverso cui creare o scrivere."""
    from core.projects import ProjectError
    client = _client(tmp_path, monkeypatch)
    fuori = tmp_path / "fuori"
    fuori.mkdir()
    if not _junction(tmp_path / "docs" / "link", fuori):
        pytest.skip("junction non disponibili su questa piattaforma")
    (tmp_path / "docs" / "vera").mkdir()
    assert intake.doc_categories(docs_dir=tmp_path / "docs") == ["vera"]
    with pytest.raises(ProjectError):
        intake.create_doc_category("link", docs_dir=tmp_path / "docs")

    doc_id = client.post("/api/intake/docs",
                         files={"file": ("d.txt", b"contenuto", "text/plain")}).json()["id"]
    assert client.post(f"/api/intake/staged/{doc_id}/approve",
                       json={"categoria": "link", "nome_file": "x"}).status_code == 422
    resp = client.post(f"/api/intake/staged/{doc_id}/approve",
                       json={"categoria": "04_knowledge_informative", "nome_file": "x"})
    assert resp.status_code == 200, resp.text
    assert list(fuori.iterdir()) == []

"""Test mirati sul blocco P0/P1 della code review (2026-07-17):

1. Path traversal sui nomi feature (slugify_feature / resolve_feature_dir / feature_dir,
   core.drift_check.check_drift / core.feature_archive.archive_feature, e i route handler di api/routes_pipeline.py
   che compongono un percorso da un feature name fornito dal chiamante).
2. X-API-Key SEMPRE richiesta (anche da localhost) SOLO su /api/pipeline/agent/run
   (api.deps.require_api_key_strict) — l'unico endpoint con esecuzione shell/scrittura
   file arbitraria (Claude Agent SDK in modalità "agentic"). Gli altri endpoint mutanti
   (explore/save, canvas/generate, propose/generate, archive, archive/stream, file/save,
   reindex, rollback) restano su require_api_key (bypass su localhost, invariato): il
   frontend non invia X-API-Key, quindi renderli strict rompeva la UI nel setup keyless
   di default — vedi la review del 2026-07-17 sulla patch P0/P1.
3. Gli errori LLM non vengono mai persistiti in canvas.md/spec.md: la generazione fallita
   restituisce un errore HTTP esplicito (502) senza scrivere alcun file — anche quando
   Ollama risponde 200 con un campo 'response' assente o vuoto (core.llm._extract_ollama_text).

I route handler sono funzioni async pure (i decorator di APIRouter non le avvolgono):
le funzioni pure si chiamano direttamente con asyncio.run. Per il wiring dell'auth,
dove conta che sia FastAPI a valutare le dependency (non solo la loro presenza nella
lista), si usa invece un vero fastapi.testclient.TestClient.
"""
import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import api.deps as deps
from api import (
    routes_graph,
    routes_health,
    routes_projects,
    routes_intake,
    routes_pages,
    routes_pipeline,
    routes_reindex,
    routes_retrieval,
)
from api.models import (
    ArchiveRequest,
    CanvasGenerateRequest,
    DriftCheckRequest,
    ExploreSaveRequest,
    PipelineFileSaveRequest,
    ProposeGenerateRequest,
    ValidateRequest,
)
from core import drift_check, feature_archive, llm, pipeline


# ===========================================================================
# 1. Path traversal sui nomi feature
# ===========================================================================

# Input che devono essere RIFIUTATI: dopo normalizzazione non restano caratteri
# validi (vuoto, solo separatori, equivalenti a '.'/'..').
_EMPTY_AFTER_NORMALIZATION = ["", "   ", ".", "..", "../..", "///", "---", "___", "  ..  "]


@pytest.mark.parametrize("bad_name", _EMPTY_AFTER_NORMALIZATION)
def test_slugify_feature_rejects_empty_after_normalization(bad_name):
    with pytest.raises(pipeline.InvalidFeatureNameError):
        pipeline.slugify_feature(bad_name)


def test_slugify_feature_still_accepts_valid_names():
    # Comportamento invariato per input validi (compatibilità con l'esistente).
    assert pipeline.slugify_feature("  Gestione Eventi  ") == "gestione-eventi"
    assert pipeline.slugify_feature("logicAgent_v2") == "logicagent-v2"


def test_slugify_feature_sanitizes_traversal_attempts_without_raising():
    # Un tentativo di traversal che contiene ANCHE testo valido non viene "riscritto"
    # in un path: i separatori/punti sono scartati, non trascritti, quindi il risultato
    # è uno slug innocuo, mai un percorso che possa uscire da CHANGES_DIR.
    assert pipeline.slugify_feature("../../etc/passwd") == "etcpasswd"
    assert pipeline.slugify_feature("..\\..\\windows\\system32") == "windowssystem32"


def test_resolve_feature_dir_stays_within_base(tmp_path):
    base = tmp_path / "changes"
    result = pipeline.resolve_feature_dir(base, "Gestione Eventi")
    assert result == base / "gestione-eventi"
    assert result.resolve().is_relative_to(base.resolve())


def test_resolve_feature_dir_rejects_invalid_slug(tmp_path):
    base = tmp_path / "changes"
    with pytest.raises(pipeline.InvalidFeatureNameError):
        pipeline.resolve_feature_dir(base, "..")


def test_resolve_feature_dir_containment_check_is_defense_in_depth(tmp_path, monkeypatch):
    """Anche se slugify_feature restituisse (per un bug futuro) qualcosa che esce da
    base_dir, resolve_feature_dir lo rifiuta comunque grazie al controllo esplicito di
    contenimento — indipendente dalla whitelist dei caratteri dello slug."""
    base = tmp_path / "changes"
    base.mkdir()
    monkeypatch.setattr(pipeline, "slugify_feature", lambda name: "../../escaped")
    with pytest.raises(pipeline.InvalidFeatureNameError):
        pipeline.resolve_feature_dir(base, "qualsiasi")


def test_feature_dir_rejects_traversal_and_creates_nothing(tmp_path, monkeypatch):
    changes = tmp_path / "changes"
    monkeypatch.setattr(pipeline, "CHANGES_DIR", changes)
    with pytest.raises(pipeline.InvalidFeatureNameError):
        pipeline.feature_dir("..")
    assert not changes.exists()  # rifiutato prima di qualunque mkdir


# ---------------------------------------------------------------------------
# core.drift_check.check_drift / core.feature_archive.archive_feature — riproducono l'attacco critico
# della code review (feature_name=".." risolveva a CHANGES_DIR/".." nel codice
# pre-fix, ossia la directory PADRE di changes/).
# ---------------------------------------------------------------------------
def test_archive_feature_rejects_dotdot_traversal_no_filesystem_touch(tmp_path, monkeypatch):
    changes = tmp_path / "changes"
    docs = tmp_path / "docs"
    docs.mkdir()
    # tmp_path rappresenta la "project root": nel codice pre-fix l'intero tmp_path
    # sarebbe stato spostato dentro changes/archive/.. da shutil.move.
    marker = tmp_path / "should-never-move.txt"
    marker.write_text("canary", encoding="utf-8")
    monkeypatch.setattr(feature_archive, "CHANGES_DIR", changes)
    monkeypatch.setattr(feature_archive, "DOCS_DIR", docs)

    log = feature_archive.archive_feature("..", emit=lambda m: None)

    assert "Nome feature non valido" in log
    assert marker.exists()        # la project root non è stata toccata
    assert not changes.exists()   # rifiutato prima di qualunque I/O: nessuna dir creata


def test_archive_feature_sanitizes_traversal_with_extra_text(tmp_path, monkeypatch):
    """Un nome che contiene sia un tentativo di traversal sia testo valido non riesce
    a scappare da changes/: viene sanificato in uno slug innocuo e trattato come una
    feature (inesistente) qualunque — mai un path fuori da CHANGES_DIR."""
    changes = tmp_path / "changes"
    docs = tmp_path / "docs"
    docs.mkdir()
    monkeypatch.setattr(feature_archive, "CHANGES_DIR", changes)
    monkeypatch.setattr(feature_archive, "DOCS_DIR", docs)

    log = feature_archive.archive_feature("../../escape", emit=lambda m: None)

    assert "Non c'è nulla da archiviare" in log or "non esiste" in log
    assert not changes.exists()  # nessuna directory creata: lo slug sanificato non esiste


def test_check_drift_rejects_dotdot_traversal(tmp_path, monkeypatch):
    changes = tmp_path / "changes"
    monkeypatch.setattr(drift_check, "CHANGES_DIR", changes)
    monkeypatch.setattr(drift_check, "CODE_DIR", tmp_path / "code")

    report = drift_check.check_drift("..", emit=lambda m: None)

    assert "Nome feature non valido" in report
    assert not changes.exists()


# ---------------------------------------------------------------------------
# api/routes_pipeline.py: gli handler compongono un percorso da un feature name
# fornito dal chiamante e devono convertire un nome invalido in 400, mai in 500
# né in un'operazione sul filesystem fuori da CHANGES_DIR.
# ---------------------------------------------------------------------------
@pytest.fixture
def changes_env(tmp_path, monkeypatch):
    """CHANGES_DIR isolata e monkeypatchata sia nel modulo route sia in core.pipeline
    (feature_dir usa core.pipeline.CHANGES_DIR internamente)."""
    changes = tmp_path / "changes"
    monkeypatch.setattr(routes_pipeline, "CHANGES_DIR", changes)
    monkeypatch.setattr(pipeline, "CHANGES_DIR", changes)
    return changes


def _assert_bad_request(coro):
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(coro)
    assert exc_info.value.status_code == 400
    return exc_info.value


def test_route_explore_save_rejects_traversal(changes_env):
    req = ExploreSaveRequest(feature_name="..", interview_log="log", dev_type="")
    _assert_bad_request(routes_pipeline.pipeline_explore_save(req))
    assert not changes_env.exists()


def test_route_canvas_generate_rejects_traversal(changes_env):
    req = CanvasGenerateRequest(feature_name="..", dev_type="")
    _assert_bad_request(routes_pipeline.pipeline_canvas_generate(req))
    assert not changes_env.exists()


def test_route_propose_generate_rejects_traversal(changes_env):
    req = ProposeGenerateRequest(feature_folder="..", dev_type="")
    _assert_bad_request(routes_pipeline.pipeline_propose_generate(req))
    assert not changes_env.exists()


def test_route_archive_rejects_traversal_before_enqueueing(changes_env):
    req = ArchiveRequest(feature="..")
    _assert_bad_request(routes_pipeline.pipeline_archive(req))
    assert not changes_env.exists()


def test_route_drift_check_rejects_traversal(changes_env):
    req = DriftCheckRequest(feature="..")
    _assert_bad_request(routes_pipeline.pipeline_drift_check(req))


def test_route_validate_rejects_traversal(changes_env):
    req = ValidateRequest(feature="..")
    _assert_bad_request(routes_pipeline.pipeline_validate(req))


def test_route_save_file_rejects_traversal(changes_env):
    req = PipelineFileSaveRequest(feature="..", name="canvas.md", content="x")
    _assert_bad_request(routes_pipeline.pipeline_save_file(req))
    assert not changes_env.exists()


def test_route_canvas_dry_run_rejects_traversal(changes_env):
    req = CanvasGenerateRequest(feature_name="..", dev_type="")
    _assert_bad_request(routes_pipeline.pipeline_canvas_dry_run(req))
    assert not changes_env.exists()


def test_route_canvas_dry_run_does_not_create_feature_folder(changes_env):
    """canvas/dry-run è classificato read-only in SECURITY_SURFACE.md (riga #22 della matrice §2) e per
    questo escluso dalla guardia anti-cross-site (§2C): se creasse comunque la cartella
    della feature, una pagina cross-site potrebbe farle creare cartelle a piacere su
    disco. Una feature MAI vista prima non deve produrre alcuna cartella (né changes_env
    stessa, che non esiste ancora prima della chiamata) — fallisce senza la modifica,
    che passava create=True a _safe_feature_dir."""
    req = CanvasGenerateRequest(feature_name="feature mai vista", dev_type="")
    result = asyncio.run(routes_pipeline.pipeline_canvas_dry_run(req))
    assert result["feature_folder"] == "feature-mai-vista"
    assert not changes_env.exists()


def test_route_canvas_dry_run_works_on_existing_feature(changes_env):
    """Compatibilità: se la cartella esiste già (explore.md salvato in precedenza), il
    dry-run continua a leggerla e a rispondere come prima — read-only non significa
    'rompe il flusso normale'."""
    folder = changes_env / "feat-demo"
    folder.mkdir(parents=True)
    (folder / "explore.md").write_text("intervista di esempio", encoding="utf-8")
    req = CanvasGenerateRequest(feature_name="feat demo", dev_type="")

    result = asyncio.run(routes_pipeline.pipeline_canvas_dry_run(req))

    assert result["feature_folder"] == "feat-demo"
    assert "intervista di esempio" in result["query_preview"]
    assert result["sources"] == []  # nessun indice pronto nel test: ramo "Indice non ancora pronto."
    assert folder.exists()  # la cartella pre-esistente non viene toccata/rimossa


def test_route_status_rejects_traversal(changes_env):
    _assert_bad_request(routes_pipeline.pipeline_status(feature=".."))


def test_route_get_file_rejects_traversal(changes_env):
    _assert_bad_request(routes_pipeline.pipeline_get_file(feature="..", name="canvas.md"))


def test_route_export_rejects_traversal(changes_env):
    _assert_bad_request(routes_pipeline.pipeline_export(feature=".."))


def test_route_agent_context_rejects_traversal(changes_env):
    _assert_bad_request(routes_pipeline.pipeline_agent_context(feature=".."))


def test_route_accepts_valid_feature_name_unchanged(changes_env):
    """Compatibilità: un nome valido continua a creare/leggere la cartella attesa."""
    req = ExploreSaveRequest(feature_name="Gestione Eventi", interview_log="log", dev_type="")
    result = asyncio.run(routes_pipeline.pipeline_explore_save(req))
    assert result["feature_folder"] == "gestione-eventi"
    assert (changes_env / "gestione-eventi" / "explore.md").exists()


# ===========================================================================
# 2. X-API-Key sempre richiesta (anche da localhost) sugli endpoint mutanti
# ===========================================================================
class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, headers=None, host="127.0.0.1"):
        self.headers = headers or {}
        self.client = _FakeClient(host)


def test_require_api_key_strict_rejects_localhost_without_key(monkeypatch):
    monkeypatch.setattr(deps, "API_KEY", "s3cret")
    with pytest.raises(HTTPException) as exc_info:
        deps.require_api_key_strict(_FakeRequest(host="127.0.0.1"))
    assert exc_info.value.status_code == 401


def test_require_api_key_strict_accepts_localhost_with_correct_key(monkeypatch):
    monkeypatch.setattr(deps, "API_KEY", "s3cret")
    deps.require_api_key_strict(_FakeRequest(headers={"X-API-Key": "s3cret"}, host="127.0.0.1"))


def test_require_api_key_strict_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(deps, "API_KEY", "s3cret")
    with pytest.raises(HTTPException):
        deps.require_api_key_strict(_FakeRequest(headers={"X-API-Key": "nope"}, host="127.0.0.1"))


def test_require_api_key_strict_fails_closed_when_unconfigured(monkeypatch):
    monkeypatch.setattr(deps, "API_KEY", None)
    with pytest.raises(HTTPException) as exc_info:
        deps.require_api_key_strict(_FakeRequest(host="127.0.0.1"))
    assert exc_info.value.status_code == 401


def test_valid_api_key_uses_constant_time_comparison(monkeypatch):
    """_valid_api_key confronta con hmac.compare_digest (come require_gitlab_token), non
    con `==`: il confronto che esce al primo carattere diverso rende la chiave
    indovinabile per prefissi via timing. Lo spy registra le chiamate e delega al vero
    compare_digest, così l'esito resta quello reale."""
    import hmac as _hmac
    calls = []
    real = _hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(deps.hmac, "compare_digest", spy)
    monkeypatch.setattr(deps, "API_KEY", "s3cret")
    assert deps._valid_api_key(_FakeRequest(headers={"X-API-Key": "s3cret"}))
    assert not deps._valid_api_key(_FakeRequest(headers={"X-API-Key": "s3creX"}))
    assert len(calls) == 2
    # Chiave non ASCII: compare_digest su str solleverebbe TypeError; sui bytes UTF-8 no,
    # e l'esito coincide con il vecchio `==`.
    monkeypatch.setattr(deps, "API_KEY", "chiavè")
    assert deps._valid_api_key(_FakeRequest(headers={"X-API-Key": "chiavè"}))
    assert not deps._valid_api_key(_FakeRequest(headers={"X-API-Key": "chiave"}))
    # Header assente o chiave non configurata: False senza nemmeno confrontare.
    calls.clear()
    assert not deps._valid_api_key(_FakeRequest())
    monkeypatch.setattr(deps, "API_KEY", None)
    assert not deps._valid_api_key(_FakeRequest(headers={"X-API-Key": "s3cret"}))
    monkeypatch.setattr(deps, "API_KEY", "")
    assert not deps._valid_api_key(_FakeRequest(headers={"X-API-Key": ""}))
    assert calls == []


def test_require_api_key_strict_differs_from_bypassing_require_api_key(monkeypatch):
    """La regressione esatta descritta dalla code review: require_api_key lascia
    passare localhost senza chiave; require_api_key_strict no. Stessa richiesta,
    esiti diversi — è la garanzia che il bypass non copra più gli endpoint mutanti."""
    monkeypatch.setattr(deps, "API_KEY", "s3cret")
    request = _FakeRequest(host="127.0.0.1")  # nessun header X-API-Key
    deps.require_api_key(request)  # non solleva: bypass su localhost (invariato)
    with pytest.raises(HTTPException):
        deps.require_api_key_strict(request)  # nessun bypass: rifiutata


# Agent/run e le nuove decisioni dell'operatore richiedono la chiave anche da localhost.
# Il precedente revert resta valido per le altre route mutanti della UI keyless.
_STRICT_ROUTES = [
    (routes_pipeline.router, "POST", "/api/pipeline/agent/run"),
    (routes_pipeline.router, "POST", "/api/pipeline/open-points/decision"),
]

_REVERTED_TO_PLAIN_KEY_ROUTES = [
    (routes_pipeline.router, "POST", "/api/pipeline/explore/save"),
    (routes_pipeline.router, "POST", "/api/pipeline/canvas/generate"),
    (routes_pipeline.router, "POST", "/api/pipeline/propose/generate"),
    (routes_pipeline.router, "POST", "/api/pipeline/archive"),
    (routes_pipeline.router, "POST", "/api/pipeline/archive/stream"),
    (routes_pipeline.router, "POST", "/api/pipeline/file/save"),
    (routes_reindex.router, "POST", "/api/reindex"),
    (routes_reindex.router, "POST", "/api/index/rollback"),
]


def _route_dependency_fns(router, method, path):
    for route in router.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return [d.dependency for d in route.dependencies]
    raise AssertionError(f"Route non trovata: {method} {path}")


@pytest.mark.parametrize("router,method,path", _STRICT_ROUTES)
def test_mutating_route_declares_strict_api_key_dependency(router, method, path):
    assert deps.require_api_key_strict in _route_dependency_fns(router, method, path)


@pytest.mark.parametrize("router,method,path", _REVERTED_TO_PLAIN_KEY_ROUTES)
def test_reverted_route_no_longer_declares_strict_api_key_dependency(router, method, path):
    # Regressione diretta del blocker: queste route avevano require_api_key_strict
    # nella patch precedente, il che rompeva la UI (il frontend non invia X-API-Key)
    # nel setup keyless di default. Devono restare su require_api_key (il vettore
    # cross-site è coperto da require_not_cross_site_request — sezione R2 in coda).
    assert deps.require_api_key_strict not in _route_dependency_fns(router, method, path)


@pytest.mark.parametrize("path", ["/api/pipeline/validate", "/api/pipeline/drift/check",
                                  "/api/pipeline/canvas/dry-run"])
def test_never_strict_route_does_not_require_strict_key(path):
    # Route che non hanno mai avuto require_api_key_strict (fuori scope in entrambe
    # le patch): restano protette solo da require_api_key.
    assert deps.require_api_key_strict not in _route_dependency_fns(routes_pipeline.router, "POST", path)


# ---------------------------------------------------------------------------
# Wiring HTTP reale (fastapi.testclient.TestClient): non solo introspezione della
# lista `dependencies`, ma una richiesta che FastAPI valuta davvero — è l'unico modo
# per cui il blocker (UI rotta dal fail-closed su localhost) sarebbe stato visibile
# prima del merge.
# ---------------------------------------------------------------------------
def _make_client(*routers):
    app = FastAPI()
    for r in routers:
        app.include_router(r)
    # client=("127.0.0.1", ...): request.client.host è un vero "localhost", lo stesso
    # che require_api_key bypassa e che require_api_key_strict deve invece rifiutare.
    return TestClient(app, client=("127.0.0.1", 54321))


def test_http_agent_run_rejects_localhost_without_key(monkeypatch):
    monkeypatch.setattr(deps, "API_KEY", None)  # setup keyless, il default locale
    client = _make_client(routes_pipeline.router)
    r = client.post("/api/pipeline/agent/run", json={"prompt": "x", "mode": "suggest"})
    assert r.status_code == 401


@pytest.mark.parametrize('configured_key', [None, 's3cret'])
def test_http_operator_decision_rejects_localhost_without_key(monkeypatch, configured_key):
    monkeypatch.setattr(deps, 'API_KEY', configured_key)
    client = _make_client(routes_pipeline.router)
    assert client.post('/api/pipeline/open-points/decision', json={}).status_code == 401


def test_http_operator_decision_with_key_still_validates_payload(monkeypatch):
    monkeypatch.setattr(deps, 'API_KEY', 's3cret')
    client = _make_client(routes_pipeline.router)
    assert client.post('/api/pipeline/open-points/decision', json={},
                       headers={'X-API-Key': 's3cret'}).status_code == 422


def test_http_agent_run_accepts_localhost_with_correct_key(monkeypatch, tmp_path):
    monkeypatch.setattr(deps, "API_KEY", "s3cret")

    from core.pipeline_store import PipelineStore
    monkeypatch.setattr(routes_pipeline, "pipeline_store", PipelineStore(tmp_path / "pipeline"))

    def fake_stream(runner, prompt, mode, model, **kwargs):
        yield '{"type": "result", "is_error": false}\n'

    monkeypatch.setattr(routes_pipeline, "run_agent_streaming", fake_stream)
    client = _make_client(routes_pipeline.router)
    r = client.post(
        "/api/pipeline/agent/run",
        json={"prompt": "x", "mode": "suggest"},
        headers={"X-API-Key": "s3cret"},
    )
    assert r.status_code == 200


def test_http_explore_save_bypasses_localhost_without_key(changes_env, monkeypatch):
    """Prova diretta del fix del blocker: senza questa route torna a require_api_key,
    la stessa identica richiesta (localhost, nessun header) che prima falliva con 401
    ora deve passare — è il comportamento che il frontend, che non manda X-API-Key,
    richiede per funzionare."""
    monkeypatch.setattr(deps, "API_KEY", None)
    client = _make_client(routes_pipeline.router)
    r = client.post(
        "/api/pipeline/explore/save",
        json={"feature_name": "http demo", "interview_log": "log"},
    )
    assert r.status_code == 200, r.text
    assert (changes_env / "http-demo" / "explore.md").exists()


def test_http_canvas_generate_bypasses_localhost_without_key(changes_env, fake_llm_settings, monkeypatch):
    monkeypatch.setattr(deps, "API_KEY", None)
    _register_working_llm_provider("## Requirements\nOK")
    client = _make_client(routes_pipeline.router)
    r = client.post("/api/pipeline/canvas/generate", json={"feature_name": "http demo"})
    assert r.status_code == 200, r.text
    assert (changes_env / "http-demo" / "canvas.md").read_text(encoding="utf-8") == "## Requirements\nOK"


def test_http_reindex_bypasses_localhost_without_key(monkeypatch):
    """La route accoda il job su un ReindexManager reale (thread + modello di
    embedding): per un test HTTP veloce e deterministico si sostituisce il manager
    con un fake minimale — l'unica cosa sotto esame qui è l'auth, non il reindex."""
    class _FakeJob:
        id = "fake-job-id"

        def to_dict(self):
            return {"job_id": self.id, "status": "running"}

    class _FakeManager:
        def start(self, changed_paths, run_reindex, on_success, kind="incremental"):
            return _FakeJob(), False

    monkeypatch.setattr(deps, "API_KEY", None)
    monkeypatch.setattr(routes_reindex, "manager", _FakeManager())
    client = _make_client(routes_reindex.router)
    r = client.post("/api/reindex", json={})
    assert r.status_code == 202, r.text


def test_http_rollback_bypasses_localhost_without_key(monkeypatch, tmp_path):
    """Nessuna versione su disco => 404 (fallimento di dominio), non 401: prova che
    la richiesta ha superato l'auth ed è arrivata alla logica di rollback."""
    from core import artifacts
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(deps, "API_KEY", None)
    client = _make_client(routes_reindex.router)
    r = client.post("/api/index/rollback", json={})
    assert r.status_code == 404, r.text


# ===========================================================================
# 3. Errori LLM mai persistiti in canvas.md / spec.md
# ===========================================================================
@pytest.fixture
def fake_llm_settings(monkeypatch):
    settings = {"active_provider": "fake", "models": {"fake": "fake-model"}}
    monkeypatch.setitem(llm.config, "llm_settings", settings)
    return settings


def _register_broken_llm_provider():
    def broken(model, prompt, timeout):
        raise llm.LLMError("[ERRORE DI CONNESSIONE]: Impossibile raggiungere Ollama.")
    llm.register_provider("fake", broken)


def _register_working_llm_provider(response_text: str):
    llm.register_provider("fake", lambda model, prompt, timeout: response_text)


# Spec minimo ma NORMALIZZABILE, per i test di propose/generate: la route scrive spec.md solo
# dopo core.spec_format.normalize_spec, e un testo privo di scenari e' fail-closed (502).
SPEC_LLM_STUB = (
    "```gherkin\n"
    "SCENARIO: S01 - Caso nominale\n"
    "  GIVEN una premessa\n"
    "  WHEN accade qualcosa\n"
    "  THEN il sistema risponde\n"
    "```\n"
)


def test_canvas_generate_does_not_persist_llm_error(changes_env, fake_llm_settings):
    _register_broken_llm_provider()
    req = CanvasGenerateRequest(feature_name="feat demo", dev_type="")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(routes_pipeline.pipeline_canvas_generate(req))

    assert exc_info.value.status_code == 502
    assert "ERRORE DI CONNESSIONE" in exc_info.value.detail
    canvas_path = changes_env / "feat-demo" / "canvas.md"
    assert not canvas_path.exists()  # l'errore non è mai diventato contenuto del file


def test_propose_generate_does_not_persist_llm_error(changes_env, fake_llm_settings):
    folder = changes_env / "feat-demo"
    folder.mkdir(parents=True)
    (folder / "canvas.md").write_text("## Requirements\ncontratto", encoding="utf-8")
    _register_broken_llm_provider()
    req = ProposeGenerateRequest(feature_folder="feat-demo", dev_type="")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(routes_pipeline.pipeline_propose_generate(req))

    assert exc_info.value.status_code == 502
    assert not (folder / "spec.md").exists()


def test_canvas_generate_still_persists_on_success(changes_env, fake_llm_settings):
    """Compatibilità: con l'LLM funzionante il comportamento resta invariato (200,
    contenuto scritto su disco)."""
    _register_working_llm_provider("## Requirements\nOK")
    req = CanvasGenerateRequest(feature_name="feat demo", dev_type="")

    result = asyncio.run(routes_pipeline.pipeline_canvas_generate(req))

    assert result["content"] == "## Requirements\nOK"
    canvas_path = changes_env / "feat-demo" / "canvas.md"
    assert canvas_path.read_text(encoding="utf-8") == "## Requirements\nOK"


def test_propose_generate_still_persists_on_success(changes_env, fake_llm_settings):
    folder = changes_env / "feat-demo"
    folder.mkdir(parents=True)
    (folder / "canvas.md").write_text("## Requirements\ncontratto", encoding="utf-8")
    # La risposta dev'essere uno spec normalizzabile: propose/generate scrive spec.md solo
    # dopo core.spec_format.normalize_spec, e un testo senza scenari e' fail-closed (502).
    _register_working_llm_provider(SPEC_LLM_STUB)
    req = ProposeGenerateRequest(feature_folder="feat-demo", dev_type="")

    result = asyncio.run(routes_pipeline.pipeline_propose_generate(req))

    assert result["content"] == (folder / "spec.md").read_text(encoding="utf-8")
    assert "SCENARIO: S01 - Caso nominale" in result["content"]
    # Il grezzo del modello resta accanto allo spec, intatto.
    assert (folder / "spec.raw.md").read_text(encoding="utf-8") == SPEC_LLM_STUB


# ===========================================================================
# 5. Path escape via dev_type: consentito solo se in list_dev_types() — la stessa
# whitelist che già popola la tendina di scelta, nessuna regex nuova. dev_type
# diventa un componente di path (CODE_DIR / dev_type) in core.drift_check.check_drift.
# ===========================================================================
@pytest.fixture
def code_dir_env(changes_env, tmp_path, monkeypatch):
    """CODE_DIR isolata con una sola sottocartella nota ('backend'): list_dev_types()
    e validate_dev_type() leggono core.pipeline.CODE_DIR."""
    code_dir = tmp_path / "code"
    (code_dir / "backend").mkdir(parents=True)
    monkeypatch.setattr(pipeline, "CODE_DIR", code_dir)
    return changes_env


@pytest.mark.parametrize("bad_dev_type", ["../../etc", "..\\..\\windows", "/etc/passwd", "database"])
def test_route_explore_save_rejects_unknown_dev_type(code_dir_env, bad_dev_type):
    req = ExploreSaveRequest(feature_name="feat demo", interview_log="log", dev_type=bad_dev_type)
    exc = _assert_bad_request(routes_pipeline.pipeline_explore_save(req))
    assert "Tipo di sviluppo non valido" in exc.detail
    assert not (code_dir_env / "feat-demo" / "meta.json").exists()
    assert not (code_dir_env / "feat-demo" / "explore.md").exists()


def test_route_explore_save_accepts_known_dev_type(code_dir_env):
    req = ExploreSaveRequest(feature_name="feat demo", interview_log="log", dev_type="backend")
    result = asyncio.run(routes_pipeline.pipeline_explore_save(req))
    assert result["feature_folder"] == "feat-demo"
    assert (code_dir_env / "feat-demo" / "meta.json").exists()


def test_route_explore_save_accepts_empty_dev_type(code_dir_env):
    # Nessun ambito scelto resta sempre valido (comportamento invariato).
    req = ExploreSaveRequest(feature_name="feat demo", interview_log="log", dev_type="")
    result = asyncio.run(routes_pipeline.pipeline_explore_save(req))
    assert result["feature_folder"] == "feat-demo"
    assert not (code_dir_env / "feat-demo" / "meta.json").exists()  # save_dev_type("") è no-op


def test_route_canvas_generate_rejects_unknown_dev_type_before_llm_call(code_dir_env, fake_llm_settings):
    calls = []
    llm.register_provider("fake", lambda model, prompt, timeout: calls.append(1) or "## Requirements\nOK")
    req = CanvasGenerateRequest(feature_name="feat demo", dev_type="../../etc")

    exc = _assert_bad_request(routes_pipeline.pipeline_canvas_generate(req))

    assert "Tipo di sviluppo non valido" in exc.detail
    assert calls == []  # nessuna chiamata LLM sprecata: validato prima di generare
    assert not (code_dir_env / "feat-demo" / "canvas.md").exists()


def test_route_canvas_generate_accepts_known_dev_type(code_dir_env, fake_llm_settings):
    _register_working_llm_provider("## Requirements\nOK")
    req = CanvasGenerateRequest(feature_name="feat demo", dev_type="backend")

    result = asyncio.run(routes_pipeline.pipeline_canvas_generate(req))

    assert result["content"] == "## Requirements\nOK"
    assert (code_dir_env / "feat-demo" / "canvas.md").exists()


def test_route_propose_generate_rejects_unknown_dev_type_before_llm_call(code_dir_env, fake_llm_settings):
    folder = code_dir_env / "feat-demo"
    folder.mkdir(parents=True)
    (folder / "canvas.md").write_text("## Requirements\ncontratto", encoding="utf-8")
    calls = []
    llm.register_provider("fake", lambda model, prompt, timeout: calls.append(1) or "GIVEN x")
    req = ProposeGenerateRequest(feature_folder="feat-demo", dev_type="../../etc")

    exc = _assert_bad_request(routes_pipeline.pipeline_propose_generate(req))

    assert "Tipo di sviluppo non valido" in exc.detail
    assert calls == []
    assert not (folder / "spec.md").exists()


def test_route_propose_generate_accepts_known_dev_type(code_dir_env, fake_llm_settings):
    folder = code_dir_env / "feat-demo"
    folder.mkdir(parents=True)
    (folder / "canvas.md").write_text("## Requirements\ncontratto", encoding="utf-8")
    _register_working_llm_provider(SPEC_LLM_STUB)
    req = ProposeGenerateRequest(feature_folder="feat-demo", dev_type="backend")

    result = asyncio.run(routes_pipeline.pipeline_propose_generate(req))

    assert "SCENARIO: S01 - Caso nominale" in result["content"]
    assert (folder / "spec.md").exists()


def test_route_propose_generate_rejects_stale_or_tampered_meta_dev_type(code_dir_env, fake_llm_settings):
    """Un dev_type già persistito (meta.json scritto da prima di questo fix, o
    modificato a mano) viene rivalidato al momento dell'uso: non basta bloccarlo in
    scrittura, dev_type deve essere valido ogni volta che diventa un componente di
    path — qui tramite req.dev_type="" che ricade su load_dev_type(folder)."""
    folder = code_dir_env / "feat-demo"
    folder.mkdir(parents=True)
    (folder / "canvas.md").write_text("## Requirements\ncontratto", encoding="utf-8")
    (folder / "meta.json").write_text('{"dev_type": "../../etc"}', encoding="utf-8")
    calls = []
    llm.register_provider("fake", lambda model, prompt, timeout: calls.append(1) or "GIVEN x")
    req = ProposeGenerateRequest(feature_folder="feat-demo", dev_type="")

    exc = _assert_bad_request(routes_pipeline.pipeline_propose_generate(req))

    assert "Tipo di sviluppo non valido" in exc.detail
    assert calls == []


# ===========================================================================
# R2 (M7): dependency anti-cross-site sugli endpoint mutanti keyless
# (api.deps.require_not_cross_site_request — matrice in SECURITY_SURFACE.md §2)
# ===========================================================================

# Route della matrice M7 (SECURITY_SURFACE.md §2, "Sintesi ambito"): TUTTI i POST del
# progetto tranne i due esclusi con motivazione (agent/run, già strict; canvas/dry-run,
# read-only) — 22 su 24. Corrispondenza 1:1 con la matrice, verificata in entrambi i
# versi: ogni riga qui deve dichiarare la dependency (test sotto) e ogni POST del codice
# deve comparire qui o fra le esclusioni (test_every_post_route_is_classified).
_ANTI_XSITE_ROUTES = [
    (routes_projects.router, "POST", "/api/projects"),
    (routes_projects.router, "POST", "/api/projects/register"),
    (routes_reindex.router, "POST", "/api/reindex"),
    (routes_reindex.router, "POST", "/api/index/rollback"),
    (routes_pipeline.router, "POST", "/api/pipeline/explore/save"),
    (routes_pipeline.router, "POST", "/api/pipeline/canvas/generate"),
    (routes_pipeline.router, "POST", "/api/pipeline/propose/generate"),
    (routes_pipeline.router, "POST", "/api/pipeline/archive"),
    (routes_pipeline.router, "POST", "/api/pipeline/archive/stream"),
    (routes_pipeline.router, "POST", "/api/pipeline/file/save"),
    (routes_pipeline.router, "POST", "/api/pipeline/explore/turn"),
    (routes_pipeline.router, "POST", "/api/pipeline/drift/check"),
    (routes_pipeline.router, "POST", "/api/pipeline/drift/check/stream"),
    (routes_pipeline.router, "POST", "/api/pipeline/validate"),
    (routes_retrieval.router, "POST", "/ask"),
    # Intake & Import (S0-S6): 9 POST, tutti mutanti o LLM. Tre di questi sono
    # STRUTTURALMENTE raggiungibili cross-site anche senza preflight — `docs` ha un body
    # multipart (content-type "simple", nessun preflight) e `refine`/`browse-path` non
    # dichiarano alcun body — quindi qui la dependency non è defense-in-depth: è l'unico
    # controllo. Vedi SECURITY_SURFACE.md §1 "Nota sulle route a corpo consegnabile".
    (routes_intake.router, "POST", "/api/intake/docs"),
    (routes_intake.router, "POST", "/api/intake/staged/{doc_id}/approve"),
    (routes_intake.router, "POST", "/api/intake/staged/{doc_id}/reject"),
    (routes_intake.router, "POST", "/api/intake/generate"),
    (routes_intake.router, "POST", "/api/intake/staged/{doc_id}/refine"),
    (routes_intake.router, "POST", "/api/intake/project/browse-path"),
    (routes_intake.router, "POST", "/api/intake/project/plan"),
    (routes_intake.router, "POST", "/api/intake/project/apply"),
    (routes_intake.router, "POST", "/api/intake/project/brief"),
]

# POST deliberatamente FUORI dalla matrice, con la motivazione della matrice §2C. Lista
# chiusa: serve al test di classificazione qui sotto, che è ciò che impedisce a un nuovo
# POST di entrare nel codice senza una decisione esplicita.
_ANTI_XSITE_EXCLUDED = [
    (routes_pipeline.router, "POST", "/api/pipeline/agent/run"),      # già require_api_key_strict
    (routes_pipeline.router, "POST", "/api/pipeline/open-points/decision"),  # chiave obbligatoria
    (routes_pipeline.router, "POST", "/api/pipeline/canvas/dry-run"),  # read-only
]

_ALL_ROUTERS = [routes_pages.router, routes_pipeline.router, routes_reindex.router,
                routes_retrieval.router, routes_graph.router, routes_health.router,
                routes_intake.router, routes_projects.router]


def _concrete(path: str) -> str:
    """Template di route → URL concreto per le richieste HTTP. Gli id inesistenti sono
    voluti: il ramo "come oggi" deve fermarsi su un 404/422, mai su un documento vero."""
    return path.replace("{doc_id}", "non-esiste").replace("{job_id}", "non-esiste")


# --- Semantica della dependency, in isolamento (stesso pattern _FakeRequest) ---
def test_not_cross_site_rejects_cross_site_without_key(monkeypatch):
    monkeypatch.setattr(deps, "API_KEY", None)  # keyless: nessuna chiave da esibire
    with pytest.raises(HTTPException) as exc_info:
        deps.require_not_cross_site_request(
            _FakeRequest(headers={"Sec-Fetch-Site": "cross-site"}))
    assert exc_info.value.status_code == 403
    assert "cross-site" in exc_info.value.detail


@pytest.mark.parametrize("value", [None, "same-origin", "same-site", "none"])
def test_not_cross_site_passes_absent_or_non_cross_site_values(monkeypatch, value):
    # Header assente (curl/script/browser legacy/file://) o con valore non ostile:
    # comportamento odierno invariato, la dependency non solleva.
    monkeypatch.setattr(deps, "API_KEY", None)
    headers = {} if value is None else {"Sec-Fetch-Site": value}
    deps.require_not_cross_site_request(_FakeRequest(headers=headers))


def test_not_cross_site_passes_with_valid_api_key(monkeypatch):
    # Client API autenticato: passa anche se il browser dichiara cross-site.
    monkeypatch.setattr(deps, "API_KEY", "s3cret")
    deps.require_not_cross_site_request(
        _FakeRequest(headers={"Sec-Fetch-Site": "cross-site", "X-API-Key": "s3cret"}))


# --- Introspezione: matrice e codice devono coincidere 1:1 ---
@pytest.mark.parametrize("router,method,path", _ANTI_XSITE_ROUTES)
def test_matrix_route_declares_anti_cross_site_dependency(router, method, path):
    assert deps.require_not_cross_site_request in _route_dependency_fns(router, method, path)


@pytest.mark.parametrize("router,method,path", _ANTI_XSITE_EXCLUDED)
def test_excluded_route_does_not_declare_anti_cross_site_dependency(router, method, path):
    # agent/run resta SOLO strict (matrice §2C: non toccato né indebolito);
    # canvas/dry-run è read-only, escluso dalla matrice — nessuna protezione "per eccesso".
    assert deps.require_not_cross_site_request not in _route_dependency_fns(router, method, path)


def test_every_post_route_is_classified():
    """Il verso che mancava: ogni POST registrato deve stare nella matrice O fra le
    esclusioni motivate. È il test che avrebbe fatto fallire l'ingresso dei 9 POST di
    intake senza una riga corrispondente in SECURITY_SURFACE.md — la matrice non può
    restare indietro rispetto al codice senza che la suite lo dica."""
    classified = {(m, p) for _, m, p in _ANTI_XSITE_ROUTES + _ANTI_XSITE_EXCLUDED}
    registered = {
        ("POST", route.path)
        for router in _ALL_ROUTERS for route in router.routes
        if "POST" in getattr(route, "methods", set())
    }
    assert registered - classified == set(), (
        "POST non classificati: aggiungili a _ANTI_XSITE_ROUTES (con la dependency) o a "
        "_ANTI_XSITE_EXCLUDED (con la motivazione), e aggiorna SECURITY_SURFACE.md §1-§2."
    )
    # E nessuna riga fantasma: una route rimossa dal codice non deve restare in matrice.
    assert classified - registered == set()


# --- Wiring HTTP reale su tutte le route della matrice ---
@pytest.fixture
def xsite_client(monkeypatch, tmp_path):
    """Client HTTP localhost con i quattro router della matrice e le dipendenze a valle
    di reindex/rollback sostituite da fake (stesso schema dei test di bypass sopra):
    sotto esame c'è solo il gate anti-cross-site, mai il reindex/rollback reale. Per le
    route Pydantic (incluso /ask, il cui AskQuery richiede `question`) i test inviano un
    body volutamente NON valido ({}): quando il gate passa la risposta è il 422 di
    validazione — la business logic non viene mai eseguita.

    `_native_folder_dialog` è sostituita perché `project/browse-path` non dichiara alcun
    body: nel ramo "come oggi" l'handler viene raggiunto davvero e aprirebbe un dialogo
    tkinter MODALE sulla macchina che esegue i test, bloccando la suite finché qualcuno
    non lo chiude a mano. (Che una POST bodyless apra una finestra sul desktop del server
    è anche il motivo per cui questa route è in matrice.)"""
    class _FakeJob:
        id = "fake-job-id"

        def to_dict(self):
            return {"job_id": self.id, "status": "running"}

    class _FakeManager:
        def start(self, changed_paths, run_reindex, on_success, kind="incremental"):
            return _FakeJob(), False

    from core import artifacts
    monkeypatch.setattr(routes_reindex, "manager", _FakeManager())
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)  # rollback => 404, mai il reale
    monkeypatch.setattr(routes_intake, "_native_folder_dialog", lambda: None)
    return _make_client(routes_pipeline.router, routes_reindex.router,
                        routes_retrieval.router, routes_intake.router, routes_projects.router)


@pytest.mark.parametrize("router,method,path", _ANTI_XSITE_ROUTES)
def test_http_cross_site_post_rejected_with_403(xsite_client, monkeypatch, router, method, path):
    """A. Cross-site keyless ⇒ 403. POST senza corpo, come la vera simple request di un
    attaccante: la dependency scatta prima della validazione Pydantic del body."""
    monkeypatch.setattr(deps, "API_KEY", None)
    r = xsite_client.request(method, _concrete(path), headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403, r.text
    assert "cross-site" in r.json()["detail"]


@pytest.mark.parametrize("router,method,path", _ANTI_XSITE_ROUTES)
def test_http_without_fetch_metadata_behaves_as_today(xsite_client, monkeypatch, router, method, path):
    """B. Senza Sec-Fetch-Site ⇒ MAI 403: l'esito è quello di sempre (422 di validazione
    per le route Pydantic col body {}, 202 dal manager fake, 404 dal rollback senza
    versioni) — non si fissa un codice unico, si dimostra che il gate non è scattato."""
    monkeypatch.setattr(deps, "API_KEY", None)
    r = xsite_client.request(method, _concrete(path), json={})
    assert r.status_code != 403, r.text


@pytest.mark.parametrize("router,method,path", _ANTI_XSITE_ROUTES)
def test_http_same_origin_behaves_as_today(xsite_client, monkeypatch, router, method, path):
    """C. Sec-Fetch-Site: same-origin (la dashboard keyless) ⇒ MAI 403."""
    monkeypatch.setattr(deps, "API_KEY", None)
    r = xsite_client.request(method, _concrete(path), json={},
                             headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code != 403, r.text


@pytest.mark.parametrize("router,method,path", _ANTI_XSITE_ROUTES)
def test_http_cross_site_with_valid_api_key_passes(xsite_client, monkeypatch, router, method, path):
    """D. Cross-site MA con API key valida ⇒ MAI 403: il bypass per i client autenticati."""
    monkeypatch.setattr(deps, "API_KEY", "s3cret")
    r = xsite_client.request(method, _concrete(path), json={},
                             headers={"Sec-Fetch-Site": "cross-site", "X-API-Key": "s3cret"})
    assert r.status_code != 403, r.text


def test_http_reindex_bodyless_curl_still_reaches_handler(xsite_client, monkeypatch):
    """Criterio di accettazione esplicito: `curl -X POST /api/reindex` — nessun corpo,
    nessun Sec-Fetch-Site — continua a NON essere bloccato dalla nuova dependency
    (202 dal manager fake: la richiesta è arrivata all'handler)."""
    monkeypatch.setattr(deps, "API_KEY", None)
    r = xsite_client.post("/api/reindex")
    assert r.status_code == 202, r.text


# ===========================================================================
# Route locali-per-costruzione: spente quando il bind supera il loopback
# (api.deps.require_local_bind — SECURITY_SURFACE.md §4 #7-#8)
# ===========================================================================

# Le uniche due route che hanno senso SOLO se server e utente sono la stessa macchina:
# una apre un dialogo nativo sul desktop del server, l'altra scansiona un path arbitrario
# del suo filesystem. Con un bind aperto non sono "più rischiose": sono prive di senso.
_LOCAL_ONLY_ROUTES = [
    (routes_projects.router, "POST", "/api/projects/register"),
    (routes_intake.router, "POST", "/api/intake/project/browse-path"),
    (routes_intake.router, "POST", "/api/intake/project/plan"),
]


def test_require_local_bind_passes_when_bound_to_loopback(monkeypatch):
    monkeypatch.setattr(deps, "SERVER_BIND_IS_LOCAL", True)
    deps.require_local_bind(_FakeRequest())  # non solleva: è il default del progetto


def test_require_local_bind_rejects_when_bind_is_open(monkeypatch):
    monkeypatch.setattr(deps, "SERVER_BIND_IS_LOCAL", False)
    monkeypatch.setattr(deps, "SERVER_HOST", "0.0.0.0")
    with pytest.raises(HTTPException) as exc_info:
        deps.require_local_bind(_FakeRequest())
    assert exc_info.value.status_code == 403
    # Il messaggio deve dire QUALE valore ha causato lo spegnimento: senza, chi ha aperto
    # il bind legge un 403 e non ha modo di collegarlo alla propria configurazione.
    assert "0.0.0.0" in exc_info.value.detail


def test_require_local_bind_is_not_bypassable_by_api_key(monkeypatch):
    """Differenza deliberata da require_not_cross_site_request, che una API key valida
    bypassa: lì la chiave identifica un client legittimo e il threat model è il browser di
    terzi; qui non esiste chiamante per cui la funzione torni sensata. Un bypass sarebbe
    una riapertura, non un'eccezione."""
    monkeypatch.setattr(deps, "SERVER_BIND_IS_LOCAL", False)
    monkeypatch.setattr(deps, "API_KEY", "s3cret")
    with pytest.raises(HTTPException):
        deps.require_local_bind(_FakeRequest(headers={"X-API-Key": "s3cret"}))


@pytest.mark.parametrize("router,method,path", _LOCAL_ONLY_ROUTES)
def test_local_only_route_declares_local_bind_dependency(router, method, path):
    deps_fns = _route_dependency_fns(router, method, path)
    assert deps.require_local_bind in deps_fns
    # La disabilitazione si AGGIUNGE all'anti-cross-site, non lo sostituisce: con bind
    # locale (il caso normale) resta il gate che protegge dal browser di terzi.
    assert deps.require_not_cross_site_request in deps_fns


def test_no_other_route_is_disabled_by_bind():
    """Nessuna disabilitazione "per eccesso": spegnere una route è un costo di funzionalità,
    quindi solo queste due lo pagano."""
    local_only = {(m, p) for _, m, p in _LOCAL_ONLY_ROUTES}
    for router in _ALL_ROUTERS:
        for route in router.routes:
            declared = deps.require_local_bind in [d.dependency for d in route.dependencies]
            for method in getattr(route, "methods", set()) - {"HEAD"}:
                assert declared == ((method, route.path) in local_only), route.path


@pytest.mark.parametrize("router,method,path", _LOCAL_ONLY_ROUTES)
def test_http_local_only_route_returns_403_when_bind_is_open(monkeypatch, router, method, path):
    """Wiring HTTP: con bind aperto la route risponde 403 anche a un client 127.0.0.1 con
    la chiave valida — è spenta, non protetta.

    `_native_folder_dialog` è sostituita da una funzione che SOLLEVA, non dal dialogo vero:
    se il gate non scattasse, l'handler verrebbe raggiunto e il test deve fallire in modo
    pulito (500 ≠ 403), non bloccare la suite su una finestra modale aperta sul desktop di
    chi esegue i test."""
    def _handler_non_deve_essere_raggiunto():
        raise AssertionError("require_local_bind non ha fermato la richiesta")

    monkeypatch.setattr(deps, "SERVER_BIND_IS_LOCAL", False)
    monkeypatch.setattr(deps, "API_KEY", "s3cret")
    monkeypatch.setattr(routes_intake, "_native_folder_dialog", _handler_non_deve_essere_raggiunto)
    client = _make_client(router)
    r = client.request(method, path, json={"path": "C:/tmp", "target": "backend"},
                       headers={"X-API-Key": "s3cret"})
    assert r.status_code == 403, r.text
    assert "disabilitato" in r.json()["detail"]


def test_http_local_only_route_reaches_handler_with_loopback_bind(monkeypatch):
    """Non-regressione del caso normale (bind 127.0.0.1): la route resta raggiungibile.
    Si usa `plan`, che non apre finestre; il path inesistente la ferma sul 422 di
    validazione del dominio, ma dopo le dependency — cioè il gate non è scattato."""
    monkeypatch.setattr(deps, "SERVER_BIND_IS_LOCAL", True)
    monkeypatch.setattr(deps, "API_KEY", None)
    client = _make_client(routes_intake.router)
    r = client.post("/api/intake/project/plan",
                    json={"path": "/percorso/che/non/esiste", "target": "backend"})
    assert r.status_code != 403, r.text


# ===========================================================================
# Classificazione ESAUSTIVA di TUTTE le route (punto #11 della review): il verso che
# `test_every_post_route_is_classified` non copriva (solo POST). Qui il confronto non è
# con un secondo elenco Python da tenere sincronizzato a mano, ma con un PARSER della
# tabella §1 e dell'Appendice A di SECURITY_SURFACE.md — lo stesso file che il documento
# dichiara "mappa del codice corrente": se la tabella non viene aggiornata, il parser
# legge il testo vecchio e il confronto con le route vere fallisce.
# ===========================================================================
RAG_DIR = Path(__file__).parents[1]
SECURITY_SURFACE_PATH = RAG_DIR / "SECURITY_SURFACE.md"

# Righe numerate della tabella §1: "| 12 | POST | `/api/pipeline/...` | ...". Il gruppo
# path è sempre il primo (e unico) backtick-quoted token dopo il metodo.
_MATRIX_ROW_RE = re.compile(
    r"^\|\s*\d+\s*\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|\s*`([^`]+)`", re.MULTILINE)
# Righe dell'Appendice A: "| GET | `/openapi.json` | ...` (nessun numero in colonna 1).
_APPENDIX_ROW_RE = re.compile(
    r"^\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|\s*`([^`]+)`\s*\|", re.MULTILINE)


def _security_surface_text() -> str:
    return SECURITY_SURFACE_PATH.read_text(encoding="utf-8")


def _parse_matrix_routes() -> set[tuple[str, str]]:
    """(metodo, path) di ogni riga numerata della tabella §1 — i 60 route registrati sui
    router applicativi."""
    text = _security_surface_text()
    section = text.split("## 1. Tabella completa delle route", 1)[1]
    section = section.split("\n---", 1)[0]
    routes = {(m, p) for m, p in _MATRIX_ROW_RE.findall(section)}
    assert len(routes) >= 55, "parser della tabella §1 vuoto o rotto: pattern non trovato"
    return routes


def _parse_appendix_a_routes() -> set[tuple[str, str]]:
    """(metodo, path) dell'Appendice A: route montate direttamente su `app` in server.py,
    fuori dai 8 router applicativi. `/static/*` (riga leggibile per un umano) è
    normalizzato al path del Mount vero, `/static` (nessuna route letterale con quel
    path esiste: è StaticFiles)."""
    text = _security_surface_text()
    section = text.split("## Appendice A", 1)[1]
    routes = set()
    for method, path in _APPENDIX_ROW_RE.findall(section):
        if path == "/static/*":
            path = "/static"
        routes.add((method, path))
    assert len(routes) >= 6, "parser dell'Appendice A vuoto o rotto: pattern non trovato"
    return routes


def _all_router_routes() -> set[tuple[str, str]]:
    """(metodo, path) di OGNI route registrata sui 8 router applicativi (ruolo
    standalone/writer: è il superinsieme che include anche tutto ciò che il ruolo
    `reader` monta — vedi server.py, `if ROLE != "reader"`), con TUTTI i metodi
    dichiarati — non solo POST. HEAD è escluso: FastAPI lo aggiunge da sé a ogni GET,
    non è una route dichiarata separatamente né una riga a parte in tabella."""
    result = set()
    for router in _ALL_ROUTERS:
        for route in router.routes:
            methods = getattr(route, "methods", None) or set()
            for method in methods - {"HEAD"}:
                result.add((method, route.path))
    return result


def _app_level_extra_routes() -> set[tuple[str, str]]:
    """(metodo, path) delle route montate direttamente su `app` in server.py, FUORI dai 7
    router applicativi: le due route esplicite shared.css/shared.js, il mount /static e
    le route di default di FastAPI (/docs, /redoc, /openapi.json, /docs/oauth2-redirect)
    — esattamente l'Appendice A. Importa il modulo server reale (stesso pattern di
    tests/test_host_header.py) e ne ispeziona app.routes filtrando via i 8 router
    applicativi (`_IncludedRouter`, già coperti da _all_router_routes)."""
    import server as _server
    from starlette.routing import Mount

    result = set()
    for route in _server.app.routes:
        if type(route).__name__ == "_IncludedRouter":
            continue
        if isinstance(route, Mount):
            result.add(("GET", route.path))
            continue
        methods = getattr(route, "methods", None) or set()
        for method in methods - {"HEAD"}:
            result.add((method, route.path))
    return result


def test_no_websocket_route_is_registered():
    """Precondizione del punto #11: la classificazione qui sotto copre solo route
    HTTP (GET/POST/...). Se in futuro compare un WebSocket, questo test lo segnala PRIMA
    che sfugga silenziosamente alla matrice (che non ha una colonna per il protocollo)."""
    from starlette.routing import WebSocketRoute
    for router in _ALL_ROUTERS:
        for route in router.routes:
            assert not isinstance(route, WebSocketRoute), (
                f"nuova route WebSocket non classificata: {route.path} — "
                "estendi il parser e la matrice prima di aggiungerla"
            )


def test_every_route_is_classified_in_security_surface():
    """Il verso esteso a TUTTI i metodi (non solo POST) e a TUTTE le route (non solo
    quelle sui router: anche le extra montate su `app`). Ogni route del codice deve
    comparire nella tabella §1 o nell'Appendice A di SECURITY_SURFACE.md, e nessuna riga
    della tabella/Appendice deve essere fantasma (route rimossa dal codice ma rimasta
    documentata)."""
    documented = _parse_matrix_routes() | _parse_appendix_a_routes()
    registered = _all_router_routes() | _app_level_extra_routes()
    missing = registered - documented
    assert missing == set(), (
        f"Route registrate ma non documentate in SECURITY_SURFACE.md: {sorted(missing)} "
        "— aggiungile alla tabella §1 (o all'Appendice A se montate fuori dai router) e "
        "aggiorna §Metodologia/Report finale."
    )
    phantom = documented - registered
    assert phantom == set(), (
        f"Route documentate ma non registrate nel codice (fantasma): {sorted(phantom)} "
        "— rimuovile dalla tabella §1/Appendice A e aggiorna i conteggi."
    )


def test_declared_route_counts_match_code():
    """I conteggi dichiarati in §Metodologia (totale + per-file) non sono più affermazioni
    a mano: sono ricontati da `_ALL_ROUTERS` (stessa fonte di verità di
    `test_every_route_is_classified_in_security_surface`) e confrontati col testo del
    documento. Un router che guadagna una route senza che il documento venga aggiornato fa
    fallire QUESTO test, non solo quello di classificazione — i due proteggono aspetti
    diversi: qui i conteggi, sopra il contenuto riga per riga."""
    text = _security_surface_text()

    total_match = re.search(r"Route registrate sui router:\s*(\d+)", text)
    assert total_match, "sezione §Metodologia non trovata o riformulata: aggiorna il parser"
    declared_total = int(total_match.group(1))
    actual_total = sum(len(r.routes) for r in _ALL_ROUTERS)
    assert declared_total == actual_total, (
        f"§Metodologia dichiara {declared_total} route registrate, il codice ne ha "
        f"{actual_total}: aggiorna 'Route registrate sui router' e la tabella §1."
    )

    # Righe "`routes_X.py` → N" nella stessa sezione: confrontate 1:1 col router
    # corrispondente (stesso ordine dei nomi file usato dal resto del documento).
    per_file_declared = dict(re.findall(r"`(routes_\w+\.py)`\s*→\s*(\d+)", text))
    per_file_declared = {k: int(v) for k, v in per_file_declared.items()}
    module_by_filename = {
        "routes_pages.py": routes_pages.router,
        "routes_pipeline.py": routes_pipeline.router,
        "routes_reindex.py": routes_reindex.router,
        "routes_retrieval.py": routes_retrieval.router,
        "routes_graph.py": routes_graph.router,
        "routes_health.py": routes_health.router,
        "routes_projects.py": routes_projects.router,
        "routes_intake.py": routes_intake.router,
    }
    assert set(per_file_declared) == set(module_by_filename), (
        "l'elenco per-file di §Metodologia non elenca esattamente i 8 router applicativi"
    )
    for filename, declared_count in per_file_declared.items():
        actual_count = len(module_by_filename[filename].routes)
        assert declared_count == actual_count, (
            f"§Metodologia dichiara {declared_count} route per {filename}, il codice ne "
            f"ha {actual_count}."
        )

    # La tabella §1 dichiara il proprio conteggio nel titolo di sezione ("N righe") e nel
    # numero effettivo di righe numerate: entrambi devono coincidere col totale sopra.
    title_match = re.search(r"## 1\. Tabella completa delle route \((\d+) righe\)", text)
    assert title_match, "titolo della tabella §1 non trovato o riformulato"
    assert int(title_match.group(1)) == actual_total
    assert len(_parse_matrix_routes()) == actual_total


def _reader_role_env(tmp_path):
    return dict(
        os.environ, VIBECRAFT_ROLE="reader", VIBECRAFT_INDEX_MODE="immutable",
        VIBECRAFT_DATABASE_DIR=str(tmp_path), VIBECRAFT_API_KEY="reader-secret",
        QDRANT_URL="http://127.0.0.1:16333", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
    )


def _dump_app_routes_script() -> str:
    """Script eseguito in un sottoprocesso pulito (ROLE è letto una volta a import time da
    core.config, quindi va cambiato PRIMA dell'import: stesso schema di
    tests/test_host_header.py::test_guard_is_active_in_reader_role). Stampa la lista
    (metodo, path) di server.app come JSON, una riga, sull'ultimo rigo di stdout."""
    return (
        "import json\n"
        "import server\n"
        "from starlette.routing import Mount\n"
        "out = []\n"
        "for route in server.app.routes:\n"
        "    if type(route).__name__ == '_IncludedRouter':\n"
        "        for r in route.original_router.routes:\n"
        "            for method in (getattr(r, 'methods', None) or set()) - {'HEAD'}:\n"
        "                out.append([method, r.path])\n"
        "        continue\n"
        "    if isinstance(route, Mount):\n"
        "        out.append(['GET', route.path])\n"
        "        continue\n"
        "    for method in (getattr(route, 'methods', None) or set()) - {'HEAD'}:\n"
        "        out.append([method, route.path])\n"
        "print(json.dumps(out))\n"
    )


def _dump_app_routes(env) -> set[tuple[str, str]]:
    result = subprocess.run([sys.executable, "-c", _dump_app_routes_script()],
                            cwd=RAG_DIR, env=env, check=True,
                            capture_output=True, text=True, encoding="utf-8")
    return {tuple(pair) for pair in json.loads(result.stdout.strip().splitlines()[-1])}


def test_writer_role_app_routes_match_router_introspection(tmp_path):
    """Il ruolo standalone/writer (il default; nessun VIBECRAFT_ROLE impostato) monta TUTTI
    i router applicativi con `router` (non `reader_router`): l'app reale (server.app)
    deve corrispondere esattamente a _all_router_routes() + _app_level_extra_routes(),
    così la garanzia di test_every_route_is_classified_in_security_surface (che introspeziona
    i router direttamente, senza costruire l'app) vale davvero per l'app che gira."""
    env = dict(os.environ, VIBECRAFT_DATABASE_DIR=str(tmp_path),
              QDRANT_URL="http://127.0.0.1:16333", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    env.pop("VIBECRAFT_ROLE", None)
    app_routes = _dump_app_routes(env)
    assert app_routes == _all_router_routes() | _app_level_extra_routes()


def test_reader_role_routes_are_a_subset_of_matrix(tmp_path):
    """Il ruolo `reader` (VIBECRAFT_ROLE=reader) monta un sottoinsieme ridotto — mai
    aggiuntivo — dei router/route del ruolo standalone/writer (server.py: reader_router al
    posto di router per pages/graph/health; pipeline/reindex/intake del tutto assenti).
    Qui non si assume che sia un sottoinsieme: si costruisce l'app reale col ruolo reader
    e si verifica contro la STESSA matrice (§1 + Appendice A) usata per il writer — se un
    domani reader_router guadagnasse una route propria non presente altrove, questo test
    la scoprirebbe comunque, perché il confronto è con la documentazione, non con l'app
    writer."""
    documented = _parse_matrix_routes() | _parse_appendix_a_routes()
    reader_routes = _dump_app_routes(_reader_role_env(tmp_path))
    missing = reader_routes - documented
    assert missing == set(), (
        f"Route del ruolo reader non documentate in SECURITY_SURFACE.md: {sorted(missing)}"
    )
    # Nessuna route "solo reader": tutto ciò che reader monta è già coperto dal
    # writer/standalone (nessun endpoint esclusivo del ruolo a bassi privilegi).
    writer_routes = _all_router_routes() | _app_level_extra_routes()
    assert reader_routes <= writer_routes, (
        "il ruolo reader espone una route che il ruolo writer non ha: "
        f"{sorted(reader_routes - writer_routes)}"
    )

"""Test dell'import progetti da path (S5, piano: docs/00_meta_governance/
piano_intake_import.md): plan/apply additivo in core/project_import.py e le route
/api/intake/project/* in api/routes_intake.py.

Fixture mini-progetto in tmp_path (mai i progetti reali di code/), reindex stubbato via
DI, writer lock su lock file in tmp_path (seam lock_path), staging in tmp_path (seam
base_dir + monkeypatch di intake.INTAKE_STAGING_DIR per le route)."""
import hashlib
import zipfile
from pathlib import Path

import pytest
from api import deps

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import intake, project_import
from core.config import PROJECT_ROOT

pytestmark = pytest.mark.usefixtures("legacy_workflow_project")


# ---------------------------------------------------------------------------
# Fixture: mini-progetto sorgente + sandbox code/ e staging
# ---------------------------------------------------------------------------
def _make_source_project(root: Path) -> Path:
    """Mini-progetto realistico: file copiabili (py/ts/cs + pom.xml per nome), un
    node_modules e un bin/ finti (da escludere) e un file con estensione ignota."""
    src = root / "sorgente"
    (src / "app").mkdir(parents=True)
    (src / "web").mkdir()
    (src / "app" / "main.py").write_text("print('main')\n", encoding="utf-8")
    (src / "app" / "service.cs").write_text("class Service {}\n", encoding="utf-8")
    (src / "web" / "index.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (src / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    (src / "node_modules" / "lib").mkdir(parents=True)
    (src / "node_modules" / "lib" / "dep.js").write_text("module.exports = 1;\n", encoding="utf-8")
    (src / "bin").mkdir()
    (src / "bin" / "out.cs").write_text("compiled\n", encoding="utf-8")
    (src / "note.rst").write_text("appunti non-codice\n", encoding="utf-8")
    return src


COPIABLE = ["app/main.py", "app/service.cs", "pom.xml", "web/index.ts"]


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """(src, code_dir, staging, lock) tutto in tmp_path."""
    src = _make_source_project(tmp_path)
    code_dir = tmp_path / "code"
    code_dir.mkdir()
    staging = tmp_path / "staging"
    monkeypatch.setattr(intake, "INTAKE_STAGING_DIR", staging)
    return src, code_dir, staging, tmp_path / "writer.lock"


def _noop_reindex(_paths, **kwargs):
    return {"noop": False, "reindexed_docs": 0, "upserted_chunks": 0, "version": "vtest"}


def _plan(src, code_dir, target="backend"):
    return project_import.plan_project_import(str(src), target, code_dir=code_dir)


def _apply(plan, code_dir, staging, lock, reindex=_noop_reindex):
    return project_import.apply_project_import(
        plan, code_dir=code_dir, base_dir=staging, reindex=reindex, lock_path=lock)


# ---------------------------------------------------------------------------
# plan: dry-run puro, classificazione, esclusioni
# ---------------------------------------------------------------------------
def test_plan_is_pure_dry_run_zero_writes(sandbox):
    src, code_dir, _staging, _lock = sandbox
    plan = _plan(src, code_dir)
    assert plan.mode == "bootstrap"
    assert plan.nuovi == COPIABLE
    assert plan.identici == [] and plan.conflitti == []
    # zero scritture: code/ e la sorgente sono intatte
    assert list(code_dir.rglob("*")) == []


def test_plan_exclusions_node_modules_bin_and_unknown_ext(sandbox):
    src, code_dir, _staging, _lock = sandbox
    plan = _plan(src, code_dir)
    assert "node_modules/" in plan.esclusi        # potata come directory...
    assert "bin/" in plan.esclusi
    assert "note.rst" in plan.esclusi             # ...estensione non-codice come file
    assert not any(p.startswith("node_modules/") and p != "node_modules/" for p in plan.esclusi)
    assert all(not p.startswith(("node_modules/", "bin/")) for p in plan.nuovi)


def test_plan_additive_classifies_new_identical_conflict(sandbox):
    src, code_dir, _staging, _lock = sandbox
    target_dir = code_dir / "backend" / src.name
    (target_dir / "app").mkdir(parents=True)
    # identico (stessi byte) + conflitto (contenuto diverso)
    (target_dir / "app" / "main.py").write_text("print('main')\n", encoding="utf-8")
    (target_dir / "app" / "service.cs").write_text("class ServiceVecchio {}\n", encoding="utf-8")

    plan = _plan(src, code_dir)
    assert plan.mode == "additivo"
    assert plan.identici == ["app/main.py"]
    assert plan.conflitti == ["app/service.cs"]
    assert plan.nuovi == ["pom.xml", "web/index.ts"]


def test_target_with_only_gitkeep_is_bootstrap(sandbox):
    src, code_dir, _staging, _lock = sandbox
    target_dir = code_dir / "logicAgent"
    target_dir.mkdir()
    (target_dir / ".gitkeep").write_text("", encoding="utf-8")
    plan = _plan(src, code_dir, target="logicAgent")
    assert plan.mode == "bootstrap"


# ---------------------------------------------------------------------------
# apply: bootstrap, additivo mai-sovrascrivere, backup, stale, journal
# ---------------------------------------------------------------------------
def test_apply_bootstrap_copies_everything_copiable(sandbox):
    src, code_dir, staging, lock = sandbox
    plan = _plan(src, code_dir)
    result = _apply(plan, code_dir, staging, lock)

    target_dir = code_dir / "backend" / src.name
    assert result["copiati"] == COPIABLE
    for rel in COPIABLE:
        assert (target_dir / rel).read_bytes() == (src / rel).read_bytes()
    # gli esclusi non passano MAI
    assert not (target_dir / "node_modules").exists()
    assert not (target_dir / "bin").exists()
    assert not (target_dir / "note.rst").exists()
    # bootstrap su cartella vuota: nessun backup (nulla da proteggere)
    assert result["backup"] is None
    assert result["reindex"] == _noop_reindex(None)


def test_apply_additive_never_modifies_existing_files_sha_before_after(sandbox):
    src, code_dir, staging, lock = sandbox
    target_dir = code_dir / "backend" / src.name
    (target_dir / "app").mkdir(parents=True)
    identical = target_dir / "app" / "main.py"
    conflict = target_dir / "app" / "service.cs"
    identical.write_text("print('main')\n", encoding="utf-8")
    conflict.write_text("class ServiceVecchio {}\n", encoding="utf-8")
    sha_before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (identical, conflict)}

    plan = _plan(src, code_dir)
    result = _apply(plan, code_dir, staging, lock)

    # i file preesistenti sono BYTE-identici a prima (mai sovrascrittura)
    for p, sha in sha_before.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == sha
    # copiati solo i nuovi; i conflitti riportati e mai applicati
    assert result["copiati"] == ["pom.xml", "web/index.ts"]
    assert result["conflitti"] == ["app/service.cs"]
    assert conflict.read_text(encoding="utf-8") == "class ServiceVecchio {}\n"


def test_apply_backup_zip_created_and_reopenable(sandbox):
    src, code_dir, staging, lock = sandbox
    target_dir = code_dir / "backend" / src.name
    (target_dir / "app").mkdir(parents=True)
    existing = target_dir / "app" / "esistente.py"
    existing.write_text("originale\n", encoding="utf-8")
    bytes_before = existing.read_bytes()

    plan = _plan(src, code_dir)
    result = _apply(plan, code_dir, staging, lock)

    backup = Path(result["backup"])
    assert backup.exists() and backup.parent == staging / "projects" / "backups"
    with zipfile.ZipFile(backup) as zf:
        assert zf.testzip() is None                       # archivio integro
        assert "app/esistente.py" in zf.namelist()        # lo stato PRE-import
        assert zf.read("app/esistente.py") == bytes_before


def test_apply_stale_plan_rejected_before_any_write(sandbox):
    src, code_dir, staging, lock = sandbox
    plan = _plan(src, code_dir)
    # lo stato del target cambia DOPO il plan: compare un file copiabile
    target_dir = code_dir / "backend" / src.name
    target_dir.mkdir(parents=True)
    (target_dir / "sorpresa.py").write_text("arrivato dopo\n", encoding="utf-8")

    with pytest.raises(project_import.StaleImportPlanError, match="ripeti l'anteprima"):
        _apply(plan, code_dir, staging, lock)
    # nessuna scrittura: solo il file "sorpresa" nel target, nessun backup
    assert [p.name for p in target_dir.rglob("*") if p.is_file()] == ["sorpresa.py"]
    assert not (staging / "projects" / "backups").exists()


def test_apply_journals_target_source_totals_and_backup(sandbox):
    src, code_dir, staging, lock = sandbox
    plan = _plan(src, code_dir)
    result = _apply(plan, code_dir, staging, lock)

    lines = (staging / "intake.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    import json
    rec = json.loads(lines[0])
    assert rec["type"] == "project_import" and rec["status"] == "applied"
    assert rec["target"] == "backend" and rec["src"] == str(src)
    assert rec["totali"]["copiati"] == len(COPIABLE)
    assert rec["backup"] == result["backup"]


def test_apply_failed_reindex_keeps_copied_files_and_reports_warning(sandbox):
    src, code_dir, staging, lock = sandbox
    plan = _plan(src, code_dir)

    def _boom(_paths):
        raise RuntimeError("reindex esploso")

    result = _apply(plan, code_dir, staging, lock, reindex=_boom)
    # additivo mai distruttivo: i file copiati restano, l'esito non nasconde nulla
    assert (code_dir / "backend" / src.name / "app" / "main.py").exists()
    assert "reindex esploso" in result["reindex_error"]
    assert "full rebuild" in result["avviso"]


def test_apply_same_plan_twice_is_stale_no_double_effect(sandbox):
    src, code_dir, staging, lock = sandbox
    plan = _plan(src, code_dir)
    _apply(plan, code_dir, staging, lock)
    with pytest.raises(project_import.StaleImportPlanError):
        _apply(plan, code_dir, staging, lock)


# ---------------------------------------------------------------------------
# Validazioni path/target
# ---------------------------------------------------------------------------
def test_plan_rejects_path_inside_repo(sandbox):
    _src, code_dir, _staging, _lock = sandbox
    with pytest.raises(project_import.InvalidImportPathError, match="dentro il repo"):
        _plan(PROJECT_ROOT / "docs", code_dir)


@pytest.mark.parametrize("bad", ["relativo/senza-radice", "sorgente"])
def test_plan_rejects_relative_path(sandbox, bad):
    _src, code_dir, _staging, _lock = sandbox
    with pytest.raises(project_import.InvalidImportPathError, match="non assoluto"):
        _plan(bad, code_dir)


def test_plan_rejects_missing_or_file_path(sandbox, tmp_path):
    _src, code_dir, _staging, _lock = sandbox
    with pytest.raises(project_import.InvalidImportPathError, match="inesistente"):
        _plan(tmp_path / "non-esiste", code_dir)
    f = tmp_path / "un-file.py"
    f.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(project_import.InvalidImportPathError, match="non è una directory"):
        _plan(f, code_dir)


def test_plan_rejects_unknown_target(sandbox):
    src, code_dir, _staging, _lock = sandbox
    with pytest.raises(project_import.InvalidImportTargetError):
        _plan(src, code_dir, target="altrove")


# ---------------------------------------------------------------------------
# Route /api/intake/project/* (wiring HTTP reale, sandbox completa via monkeypatch)
# ---------------------------------------------------------------------------
def _client(tmp_path, monkeypatch) -> tuple[TestClient, Path, Path]:
    from api import routes_intake
    src = _make_source_project(tmp_path)
    code_dir = tmp_path / "code"
    code_dir.mkdir()
    monkeypatch.setattr(project_import, "CODE_DIR", code_dir)
    monkeypatch.setattr(intake, "INTAKE_STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(routes_intake, "_server_reindex", _noop_reindex)
    monkeypatch.setattr(routes_intake, "reload_index_state", lambda project=None, **kwargs: None)
    monkeypatch.setitem(deps.project_runtime(None), "import_plans", {})
    app = FastAPI()
    app.include_router(routes_intake.router)
    return TestClient(app, client=("127.0.0.1", 54321)), src, code_dir


def test_route_plan_then_apply_cycle(tmp_path, monkeypatch):
    client, src, code_dir = _client(tmp_path, monkeypatch)

    resp = client.post("/api/intake/project/plan",
                       json={"path": str(src), "target": "backend"})
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    assert plan["mode"] == "bootstrap"
    assert plan["totali"]["nuovi"] == len(COPIABLE)

    resp = client.post("/api/intake/project/apply", json={"plan_id": plan["plan_id"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["totali"]["copiati"] == len(COPIABLE)
    assert (code_dir / "backend" / src.name / "app" / "main.py").exists()
    # un piano applicato non è riutilizzabile: secondo apply → 404 (piano dimenticato)
    assert client.post("/api/intake/project/apply",
                       json={"plan_id": plan["plan_id"]}).status_code == 404


def test_route_plan_validation_errors(tmp_path, monkeypatch):
    client, src, _code_dir = _client(tmp_path, monkeypatch)
    # path relativo → 422
    assert client.post("/api/intake/project/plan",
                       json={"path": "relativo", "target": "backend"}).status_code == 422
    # path dentro il repo → 422
    assert client.post("/api/intake/project/plan",
                       json={"path": str(PROJECT_ROOT / "docs"), "target": "backend"}).status_code == 422
    # target non ammesso → 422
    assert client.post("/api/intake/project/plan",
                       json={"path": str(src), "target": "altrove"}).status_code == 422


def test_route_apply_stale_plan_returns_409(tmp_path, monkeypatch):
    client, src, code_dir = _client(tmp_path, monkeypatch)
    plan = client.post("/api/intake/project/plan",
                       json={"path": str(src), "target": "backend"}).json()
    target_dir = code_dir / "backend" / src.name
    target_dir.mkdir(parents=True)
    (target_dir / "dopo.py").write_text("x = 1\n", encoding="utf-8")
    resp = client.post("/api/intake/project/apply", json={"plan_id": plan["plan_id"]})
    assert resp.status_code == 409
    assert "anteprima" in resp.json()["detail"]


def test_route_apply_without_plan_id_or_plan_is_422(tmp_path, monkeypatch):
    client, _src, _code_dir = _client(tmp_path, monkeypatch)
    assert client.post("/api/intake/project/apply", json={}).status_code == 422
    assert client.post("/api/intake/project/apply",
                       json={"plan_id": "sconosciuto"}).status_code == 404

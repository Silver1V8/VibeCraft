"""Creazione di un tipo di sviluppo (code/<nome>) dall'interfaccia: su un progetto nuovo
code/ è vuota e senza un ambito selezionabile la pipeline non può partire."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api import routes_pipeline
from api.models import DevTypeCreateRequest
from core import pipeline


@pytest.fixture
def project(tmp_path):
    return SimpleNamespace(code_dir=tmp_path / "code")


def test_create_on_missing_code_dir_makes_it_selectable(project):
    assert pipeline.list_dev_types(project=project) == []
    assert pipeline.create_dev_type(" logicAgent ", project=project) == "logicAgent"
    assert (project.code_dir / "logicAgent").is_dir()
    assert pipeline.list_dev_types(project=project) == ["logicAgent"]
    assert pipeline.validate_dev_type("logicAgent", project=project) == "logicAgent"


def test_create_is_idempotent_and_case_insensitive(project):
    (project.code_dir / "backend").mkdir(parents=True)
    assert pipeline.create_dev_type("backend", project=project) == "backend"
    assert pipeline.create_dev_type("Backend", project=project) == "backend"
    assert pipeline.list_dev_types(project=project) == ["backend"]


@pytest.mark.parametrize("bad", ["", "   ", "..", "../etc", "a/b", "a\\b", ".hidden", "-x", "con", "LPT1",
                                 "con spazi", "x" * 65, "C:evil"])
def test_create_rejects_unsafe_names(project, bad):
    with pytest.raises(pipeline.InvalidDevTypeError):
        pipeline.create_dev_type(bad, project=project)
    assert not project.code_dir.exists()


def test_route_creates_and_returns_updated_list(project):
    result = asyncio.run(routes_pipeline.pipeline_create_dev_type(
        DevTypeCreateRequest(name="frontend"), project=project))
    assert result == {"dev_type": "frontend", "dev_types": ["frontend"]}


def test_route_rejects_invalid_name_with_400(project):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes_pipeline.pipeline_create_dev_type(DevTypeCreateRequest(name="../x"), project=project))
    assert exc.value.status_code == 400
    assert not project.code_dir.exists()

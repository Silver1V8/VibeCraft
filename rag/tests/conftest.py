"""Explicit legacy seam for historical HTTP tests; A/B tests use the real registry."""
import os

# I test non caricano mai bge-m3 sulla GPU: i job di reindex restano su CPU (modelli
# finti) salvo i test che lo abilitano esplicitamente con monkeypatch. Il valore viene
# forzato anche se la shell esporta VIBECRAFT_REINDEX_DEVICE=auto; solo con
# VIBECRAFT_TEST_GPU=1 (opt-in per la macchina con CUDA) resta quello dell'utente.
if os.environ.get("VIBECRAFT_TEST_GPU") != "1":
    os.environ["VIBECRAFT_REINDEX_DEVICE"] = "cpu"

from dataclasses import replace

import pytest


@pytest.fixture
def legacy_http_project(monkeypatch, tmp_path):
    from api import routes_retrieval, routes_graph, routes_health
    from core.projects import legacy_project_context
    # database_dir su tmp: i test /ask con use_thread=true (default VC-3) non
    # scrivono thread.json nella database/ del repo.
    database_dir = tmp_path / "legacy-http-database"
    (database_dir / "ask").mkdir(parents=True)
    project = replace(legacy_project_context(), settings={}, database_dir=database_dir)
    for routes in (routes_retrieval, routes_graph, routes_health):
        monkeypatch.setattr(routes, "get_project", lambda request: project)


@pytest.fixture
def legacy_workflow_project(tmp_path, monkeypatch):
    """Opt-in historical HTTP adapters; real A/B tests never request this fixture.

    Historical tests patch legacy path globals and provider/snapshot seams. Capture
    those paths at request admission, with temporary database storage and an explicit
    dependency override rather than teaching production routes an implicit fallback.
    """
    from fastapi import FastAPI
    from api import deps, routes_pipeline, routes_intake, routes_reindex
    from core import intake, project_import
    from core.projects import legacy_project_context
    monkeypatch.setattr(deps, '_project_states', {})

    def context():
        return replace(legacy_project_context(), root=tmp_path / "managed",
            changes_dir=routes_pipeline.CHANGES_DIR, code_dir=project_import.CODE_DIR,
            docs_dir=intake.DOCS_DIR, staging_dir=intake.INTAKE_STAGING_DIR,
            database_dir=tmp_path/'database')

    include = FastAPI.include_router
    def include_router(application, router, **kwargs):
        if router in (routes_pipeline.router, routes_intake.router, routes_reindex.router):
            application.dependency_overrides[deps.get_project] = context
        return include(application, router, **kwargs)
    monkeypatch.setattr(FastAPI, 'include_router', include_router)
    for routes in (routes_pipeline, routes_intake, routes_reindex):
        monkeypatch.setattr(routes, 'ensure_shared_resources', lambda **kwargs: None)
    monkeypatch.setattr(routes_pipeline, 'require_snapshot', lambda project: routes_pipeline.current_snapshot(project))
    monkeypatch.setattr(routes_intake, 'require_snapshot', lambda project: routes_intake.current_snapshot(project))
    return context

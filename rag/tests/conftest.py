"""Explicit legacy seam for historical HTTP tests; A/B tests use the real registry."""
from dataclasses import replace

import pytest


@pytest.fixture
def legacy_http_project(monkeypatch):
    from api import routes_retrieval, routes_graph, routes_health
    from core.projects import legacy_project_context
    project = replace(legacy_project_context(), settings={})
    for routes in (routes_retrieval, routes_graph, routes_health):
        monkeypatch.setattr(routes, "get_project", lambda request: project)

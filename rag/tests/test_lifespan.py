"""Lazy lifespan: shell availability, resource ownership and snapshot release."""
import asyncio
import gc
import weakref

import pytest
from fastapi import FastAPI

from api import deps
from core.projects import ProjectRegistry
from test_project_runtime import indexed


@pytest.fixture
def empty_runtime(monkeypatch, tmp_path):
    from collections import OrderedDict
    monkeypatch.setattr(deps, "_snapshots", OrderedDict())
    monkeypatch.setattr(deps, "_project_states", {})
    registry = ProjectRegistry(tmp_path / 'registry', readonly=True)
    monkeypatch.setattr(deps, 'project_registry', lambda: registry)
    for key in ("snapshot", "embed_model", "qdrant"):
        monkeypatch.setitem(deps.state, key, None)


def test_lifespan_boot_never_touches_models_storage_or_qdrant(empty_runtime, monkeypatch):
    from core import indexing
    from core import writer_lock

    def forbidden(*args, **kwargs):
        pytest.fail("Startup must not initialize resources or mutate project indexes")

    for name in ("BGEM3FlagModel", "QdrantClient", "load_artifacts"):
        monkeypatch.setattr(deps, name, forbidden)
    monkeypatch.setattr(indexing, "reconcile_and_repair_qdrant_alias", forbidden)
    monkeypatch.setattr(indexing, "gc_orphaned_qdrant_collections", forbidden)
    monkeypatch.setattr(writer_lock, "writer_lock", forbidden)

    async def exercise():
        async with deps.lifespan(FastAPI()):
            assert deps.state["qdrant"] is None
            assert deps.current_snapshot() is None

    asyncio.run(exercise())


def test_lifespan_releases_superseded_graph_without_readers(empty_runtime, tmp_path):
    project = ProjectRegistry(tmp_path / "projects", bootstrap_legacy=False).create("A")
    indexed(project, "A", "v1")

    async def exercise():
        async with deps.lifespan(FastAPI()):
            first = weakref.ref(deps.require_snapshot(project).graph)
            indexed(project, "B", "v2")
            assert deps.reload_index_state(project) == "v2"
            gc.collect()
            assert first() is None

    asyncio.run(exercise())


def test_lifespan_closes_only_initialized_shared_client_even_on_error(empty_runtime, monkeypatch):
    closed = []

    class Client:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(deps, "QdrantClient", lambda **kwargs: Client())

    async def exercise():
        with pytest.raises(ValueError):
            async with deps.lifespan(FastAPI()):
                deps.ensure_shared_resources(embedding=False)
                raise ValueError("application shutdown")
        assert closed == [True]
        assert deps.state["qdrant"] is None

    asyncio.run(exercise())


def test_shutdown_drops_snapshot_refs_without_closing_inflight_store(empty_runtime, tmp_path):
    project = ProjectRegistry(tmp_path / "projects", bootstrap_legacy=False).create("A")
    indexed(project, "A")

    async def exercise():
        async with deps.lifespan(FastAPI()):
            snapshot = deps.require_snapshot(project)
        assert not deps._snapshots
        assert snapshot.colbert_store["same.md#1"].shape == (1, 2)

    asyncio.run(exercise())

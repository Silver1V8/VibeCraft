"""Project bootstrap and migration use disposable roots and real verified files."""
from contextlib import closing
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess

import pytest

from core import config
from core.projects import ProjectError, ProjectRegistry, legacy_project_context, _create_project_root


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / "installation"
    root.mkdir()
    context = replace(legacy_project_context(), root=root, name="Initial",
        code_dir=root / "code", docs_dir=root / "docs", changes_dir=root / "changes",
        database_dir=root / "database", staging_dir=tmp_path / "external staging")
    context.docs_dir.mkdir()
    (context.docs_dir / "baseline.md").write_text("# Baseline\n\nA rule.", encoding="utf-8")
    context.code_dir.mkdir()
    (context.code_dir / "backend").mkdir()
    (context.code_dir / "backend" / ".gitkeep").touch()
    monkeypatch.setattr(config, "GOLDEN_SET_PATH", root / "rag" / "eval" / "golden_set.yaml")
    return context


def test_clean_bootstrap_is_ordinary_and_idempotent(tmp_path, source):
    registry = ProjectRegistry(tmp_path / "managed", legacy_context=source)
    project = registry.get("legacy")
    assert project.root == tmp_path / "managed" / "legacy"
    assert project.legacy is False
    assert project.collection_name == "vibecraft_legacy"
    assert (project.docs_dir / "baseline.md").read_bytes() == (source.docs_dir / "baseline.md").read_bytes()
    assert (project.code_dir / "backend").is_dir()
    assert not (project.database_dir / "CURRENT").exists()
    (project.docs_dir / "baseline.md").write_text("Local edit")
    assert ProjectRegistry(registry.projects_dir, legacy_context=source).get("legacy") == project
    assert (project.docs_dir / "baseline.md").read_text() == "Local edit"
    assert (source.docs_dir / "baseline.md").read_text().startswith("# Baseline")


def test_server_start_prepares_clean_registry_without_heavy_resources(tmp_path, source, monkeypatch):
    import asyncio
    from fastapi import FastAPI
    from api import deps
    monkeypatch.setattr(deps, '_registry', None)
    monkeypatch.setattr(deps, 'ProjectRegistry', lambda: ProjectRegistry(tmp_path / 'managed', legacy_context=source))
    monkeypatch.setattr(deps, 'state', {'qdrant': None, 'embed_model': None})
    monkeypatch.setattr(deps, '_snapshots', {})
    monkeypatch.setattr(deps, '_project_states', {})
    async def start():
        async with deps.lifespan(FastAPI()):
            assert (tmp_path / 'managed' / 'legacy' / 'project.yaml').is_file()
            assert deps.state['qdrant'] is None and deps.state['embed_model'] is None
    asyncio.run(start())


@pytest.mark.parametrize("location", ["index", "changes", "staging", "pipeline", "code"])
def test_bootstrap_with_historical_state_requires_migration(tmp_path, source, location):
    target = {"index": source.database_dir / "CURRENT", "changes": source.changes_dir / "feat" / "canvas.md",
        "staging": source.staging_dir / "docs" / "pending.md",
        "pipeline": source.database_dir / "pipeline" / "contract.json",
        "code": source.code_dir / "main.py"}[location]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("real state")
    with pytest.raises(ProjectError) as exc:
        ProjectRegistry(tmp_path / "managed", legacy_context=source)
    assert exc.value.code == "project_migration_required"
    assert not (tmp_path / "managed" / "projects.json").exists()


def test_copy_rejects_links_and_foreign_destination(tmp_path, source):
    from core.project_migration import prepare_project_copy
    target = _create_project_root(tmp_path / "target", "legacy", "Initial")
    (target.docs_dir / "other.md").write_text("foreign")
    checkpoint = tmp_path / "copy.json"
    with pytest.raises(ProjectError):
        prepare_project_copy(source, target, checkpoint_path=checkpoint, include_history=False)
    assert not checkpoint.exists()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = source.docs_dir / "linked"
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
        assert result.returncode == 0
    else:
        link.symlink_to(outside, target_is_directory=True)
    other = _create_project_root(tmp_path / "other", "legacy", "Initial")
    with pytest.raises(ProjectError):
        prepare_project_copy(source, other, checkpoint_path=checkpoint, include_history=False)
    assert not list(other.docs_dir.iterdir())


def test_copy_does_not_ignore_foreign_indexable_temporary_name(tmp_path, source):
    from core.project_migration import copy_source_tree
    target = tmp_path / 'target docs'
    target.mkdir()
    (target / '.vibecraft-copy-foreign.md').write_text('Foreign indexed document')
    with pytest.raises(ProjectError):
        copy_source_tree(source.docs_dir, target)


def test_copy_resumes_after_interruption(tmp_path, source, monkeypatch):
    from core import project_migration as migration
    target = _create_project_root(tmp_path / "target", "legacy", "Initial")
    checkpoint = tmp_path / "copy.json"
    real_copy = migration.shutil.copy2
    monkeypatch.setattr(migration.shutil, "copy2", lambda *a, **k: (_ for _ in ()).throw(OSError("interrupted")))
    with pytest.raises(OSError):
        migration.prepare_project_copy(source, target, checkpoint_path=checkpoint, include_history=False)
    assert json.loads(checkpoint.read_text())["phase"] == "prepared"
    monkeypatch.setattr(migration.shutil, "copy2", real_copy)
    result = migration.prepare_project_copy(source, target, checkpoint_path=checkpoint, include_history=False)
    assert result["phase"] == "copied"
    assert (target.docs_dir / "baseline.md").read_bytes() == (source.docs_dir / "baseline.md").read_bytes()


def test_reader_never_bootstraps(tmp_path, source, monkeypatch):
    monkeypatch.setattr(config, "ROLE", "reader")
    registry = ProjectRegistry(tmp_path / "managed", legacy_context=source)
    assert registry.records() == []
    assert not registry.projects_dir.exists()


def test_bootstrap_without_heavy_resources(tmp_path, source, monkeypatch):
    # No indexing/embedding client is needed to copy and register a baseline.
    import builtins
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.startswith(("core.indexing", "FlagEmbedding", "qdrant_client")):
            pytest.fail("bootstrap imported an indexing resource")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    assert ProjectRegistry(tmp_path / "managed", legacy_context=source).get("legacy").legacy is False


def test_bootstrap_resumes_after_layout_interruption(tmp_path, source, monkeypatch):
    from core import projects
    original = projects._create_project_root
    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("interrupted after layout")
    monkeypatch.setattr(projects, "_create_project_root", interrupted)
    with pytest.raises(ProjectError):
        ProjectRegistry(tmp_path / "managed", legacy_context=source)
    monkeypatch.setattr(projects, "_create_project_root", original)
    project = ProjectRegistry(tmp_path / "managed", legacy_context=source).get("legacy")
    assert (project.docs_dir / "baseline.md").read_text().startswith("# Baseline")


def historical_registry(tmp_path, source, *, indexed=False):
    registry = ProjectRegistry(tmp_path / "managed", legacy_context=source, bootstrap_legacy=False)
    registry.registry_path.write_text(json.dumps({"schema_version": 1, "projects": [
        {"id": "legacy", "name": source.name, "root": str(source.root), "legacy": True}
    ]}))
    if indexed:
        source.database_dir.mkdir(parents=True, exist_ok=True)
        (source.database_dir / "graph.json").write_text('{"historical": true}')
    return registry


def test_migrate_unindexed_legacy_preserves_all_sources(tmp_path, source):
    from core.project_migration import migrate_legacy_project
    for file, data in [(source.code_dir / "main.py", b"def own(): return 1\n"),
                       (source.changes_dir / "feature" / "canvas.md", b"Canvas"),
                       (source.staging_dir / "docs" / "pending.pdf", b"raw staged bytes"),
                       (source.database_dir / "pipeline" / "events.jsonl", b'{"history":true}\n')]:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
    registry = historical_registry(tmp_path, source)
    original = registry.registry_path.read_bytes()
    project = migrate_legacy_project(registry)
    assert project.root == registry.projects_dir / "legacy" and project.legacy is False
    assert registry.get("legacy") == project
    assert (registry.projects_dir / "projects.v1.backup.json").read_bytes() == original
    for old, new in [(source.code_dir, project.code_dir), (source.docs_dir, project.docs_dir),
                     (source.changes_dir, project.changes_dir), (source.staging_dir, project.staging_dir),
                     (source.database_dir / "pipeline", project.database_dir / "pipeline")]:
        for file in old.rglob("*"):
            if file.is_file():
                assert (new / file.relative_to(old)).read_bytes() == file.read_bytes()
    assert not (project.database_dir / "CURRENT").exists()
    assert migrate_legacy_project(registry) == project


def test_migrate_indexed_legacy_publishes_only_verified_build(tmp_path, source):
    from qdrant_client import QdrantClient
    from test_project_indexing import Embed
    from core import indexing, artifacts, qdrant_versions
    from core.project_migration import migrate_legacy_project
    registry = historical_registry(tmp_path, source, indexed=True)
    with closing(QdrantClient(":memory:")) as qdrant:
        indexing._ensure_collection(qdrant, collection_name=source.collection_name)
        project = migrate_legacy_project(registry, qdrant=qdrant, embed_model=Embed())
        assert artifacts.current_version(project=project)
        assert indexing.check_index_integrity(qdrant, project=project)["ok"] is True
        assert qdrant.collection_exists(source.collection_name)
        assert qdrant_versions._read_alias_target(qdrant, project.collection_name).startswith("vibecraft_legacy__")
    assert (source.database_dir / "graph.json").read_text() == '{"historical": true}'


@pytest.mark.parametrize("failure", ["copy", "hash", "gate", "qdrant", "namespace"])
def test_migration_failure_preserves_registry_and_sources(tmp_path, source, monkeypatch, failure):
    from qdrant_client import QdrantClient
    from test_project_indexing import Embed
    from core import indexing, project_migration as migration
    registry = historical_registry(tmp_path, source, indexed=True)
    original = registry.registry_path.read_bytes()
    original_doc = (source.docs_dir / "baseline.md").read_bytes()
    with closing(QdrantClient(":memory:")) as qdrant:
        indexing._ensure_collection(qdrant, collection_name=source.collection_name)
        if failure == "copy":
            monkeypatch.setattr(migration.shutil, "copy2", lambda *a, **k: (_ for _ in ()).throw(OSError("copy failed")))
        if failure == "hash":
            real = migration.shutil.copy2
            def corrupted(old, new, **kw):
                real(old, new, **kw)
                Path(new).write_bytes(b"corrupt")
            monkeypatch.setattr(migration.shutil, "copy2", corrupted)
        if failure == "gate":
            monkeypatch.setattr(indexing, "gate_promotion", lambda *a, **k: {"passed": False})
        if failure == "qdrant":
            monkeypatch.setattr(qdrant, "get_collections", lambda: (_ for _ in ()).throw(OSError("qdrant down")))
        if failure == "namespace":
            indexing._ensure_collection(qdrant, collection_name="vibecraft_legacy")
        with pytest.raises((ProjectError, OSError)):
            migration.migrate_legacy_project(registry, qdrant=qdrant, embed_model=Embed())
        assert qdrant.collection_exists(source.collection_name)
        if failure == "namespace":
            assert qdrant.collection_exists("vibecraft_legacy")
    assert registry.registry_path.read_bytes() == original
    assert (source.docs_dir / "baseline.md").read_bytes() == original_doc


def test_migration_resumes_after_index_verification(tmp_path, source, monkeypatch):
    from qdrant_client import QdrantClient
    from test_project_indexing import Embed
    from core import indexing, project_migration as migration
    registry = historical_registry(tmp_path, source, indexed=True)
    original = registry.registry_path.read_bytes()
    write = registry._write
    monkeypatch.setattr(registry, "_write", lambda *a: (_ for _ in ()).throw(OSError("publication interrupted")))
    with closing(QdrantClient(":memory:")) as qdrant:
        with pytest.raises(ProjectError):
            migration.migrate_legacy_project(registry, qdrant=qdrant, embed_model=Embed())
        assert registry.registry_path.read_bytes() == original
        assert json.loads((registry.projects_dir / ".legacy-migration.json").read_text())["phase"] == "index_verified"
        monkeypatch.setattr(registry, "_write", write)
        monkeypatch.setattr(indexing, "build_graph_and_index", lambda *a, **k: pytest.fail("verified index rebuilt"))
        project = migration.migrate_legacy_project(registry, qdrant=qdrant, embed_model=Embed())
        assert registry.get("legacy") == project
        assert migration.migrate_legacy_project(registry, qdrant=qdrant) == project


def test_migration_preserves_golden_and_requires_contract_revalidation(tmp_path, source):
    from core import pipeline_gate as gate
    from core.pipeline_store import PipelineStore
    from core.project_migration import migrate_legacy_project
    config.GOLDEN_SET_PATH.parent.mkdir(parents=True)
    config.GOLDEN_SET_PATH.write_text("cases: []\n")
    contract = gate.make_contract("feature", "Canvas", "Spec")
    record = gate.new_validation(contract)
    old_store = PipelineStore(root=source.database_dir / "pipeline")
    old_store.write_validation(record)
    registry = historical_registry(tmp_path, source)
    target = migrate_legacy_project(registry)
    assert (target.root / "eval" / "golden.yaml").read_bytes() == config.GOLDEN_SET_PATH.read_bytes()
    actual = PipelineStore(project=target).read_validation("feature", record.validation_id)
    assert actual.status == "stale" and actual.passed is False
    assert old_store.read_validation("feature", record.validation_id).status == "running"


def test_migration_reader_does_not_write(tmp_path, source, monkeypatch):
    from core.project_migration import migrate_legacy_project
    registry = historical_registry(tmp_path, source)
    original = registry.registry_path.read_bytes()
    monkeypatch.setattr(config, "ROLE", "reader")
    with pytest.raises(ProjectError):
        migrate_legacy_project(registry)
    assert registry.registry_path.read_bytes() == original
    assert not (registry.projects_dir / "legacy").exists()


def test_migration_cli_unindexed_does_not_import_indexing(tmp_path, source, monkeypatch, capsys):
    import sys
    from scripts import migrate_project_layout as cli
    registry = historical_registry(tmp_path, source)
    monkeypatch.setattr(cli, "ProjectRegistry", lambda **kw: registry)
    monkeypatch.setitem(sys.modules, "core.indexing", None)
    cli.main([])
    assert "Migrated project legacy" in capsys.readouterr().out
    assert registry.get("legacy").legacy is False


def test_migration_without_registry_preserves_absence_on_failure(tmp_path, source, monkeypatch):
    from core import project_migration as migration
    registry = ProjectRegistry(tmp_path / "managed", legacy_context=source, initialize=False)
    monkeypatch.setattr(migration.shutil, "copy2", lambda *a: (_ for _ in ()).throw(OSError("copy failed")))
    with pytest.raises(ProjectError):
        migration.migrate_legacy_project(registry)
    assert not registry.registry_path.exists()


def test_migration_requires_source_writer_lock(tmp_path, source):
    from core.writer_lock import writer_lock
    from core.project_migration import migrate_legacy_project
    registry = historical_registry(tmp_path, source)
    original = registry.registry_path.read_bytes()
    with writer_lock(project=source):
        with pytest.raises(ProjectError):
            migrate_legacy_project(registry)
    assert registry.registry_path.read_bytes() == original
    assert not (registry.projects_dir / "legacy").exists()


def test_migration_repairs_owned_current_alias_interruption(tmp_path, source, monkeypatch):
    from qdrant_client import QdrantClient
    from test_project_indexing import Embed
    from core import indexing, qdrant_versions, project_migration as migration
    registry = historical_registry(tmp_path, source, indexed=True)
    original = registry.registry_path.read_bytes()
    swap = indexing._swap_alias
    monkeypatch.setattr(indexing, "_swap_alias", lambda *a: (_ for _ in ()).throw(OSError("alias interrupted")))
    with closing(QdrantClient(":memory:")) as qdrant:
        indexing._ensure_collection(qdrant, collection_name=source.collection_name)
        with pytest.raises(ProjectError):
            migration.migrate_legacy_project(registry, qdrant=qdrant, embed_model=Embed())
        assert registry.registry_path.read_bytes() == original
        monkeypatch.setattr(indexing, "_swap_alias", swap)
        with pytest.raises(ProjectError):
            migration.migrate_legacy_project(registry, qdrant=qdrant)
        project = migration.migrate_legacy_project(registry, qdrant=qdrant, repair=True)
        assert qdrant_versions._read_alias_target(qdrant, project.collection_name)
        assert qdrant.collection_exists(source.collection_name)


@pytest.mark.parametrize("failed_walk", [1, 2])
def test_copy_aborts_on_directory_enumeration_error(tmp_path, source, monkeypatch, failed_walk):
    from core.project_migration import copy_source_tree
    walk = Path.walk
    calls = 0
    def failing_walk(path, *, on_error=None, **kwargs):
        nonlocal calls
        calls += 1
        if calls == failed_walk:
            if on_error:
                on_error(PermissionError("nested directory unavailable"))
            return
        yield from walk(path, on_error=on_error, **kwargs)
    monkeypatch.setattr(Path, "walk", failing_walk)
    with pytest.raises(PermissionError):
        copy_source_tree(source.docs_dir, tmp_path / "copy")


@pytest.mark.parametrize("location", ["staging", "pipeline"])
def test_migration_discovers_history_without_corpus_or_registry(tmp_path, source, location):
    from core.project_migration import migrate_legacy_project
    (source.docs_dir / "baseline.md").unlink()
    old = (source.staging_dir if location == "staging" else source.database_dir / "pipeline") / "history.txt"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(b"Only historical content")
    with pytest.raises(ProjectError, match="migration"):
        ProjectRegistry(tmp_path / "managed", legacy_context=source)
    registry = ProjectRegistry(tmp_path / "managed", legacy_context=source, initialize=False)
    target = migrate_legacy_project(registry)
    new = (target.staging_dir if location == "staging" else target.database_dir / "pipeline") / "history.txt"
    assert new.read_bytes() == old.read_bytes()
    assert registry.get("legacy") == target


def test_migration_repair_preserves_foreign_alias(tmp_path, source, monkeypatch):
    from qdrant_client import QdrantClient
    from test_project_indexing import Embed
    from core import indexing, qdrant_versions, project_migration as migration
    registry = historical_registry(tmp_path, source, indexed=True)
    original = registry.registry_path.read_bytes()
    monkeypatch.setattr(indexing, "_swap_alias", lambda *a: (_ for _ in ()).throw(OSError("alias interrupted")))
    with closing(QdrantClient(":memory:")) as qdrant:
        with pytest.raises(ProjectError):
            migration.migrate_legacy_project(registry, qdrant=qdrant, embed_model=Embed())
        indexing._ensure_collection(qdrant, collection_name="foreign_documents")
        qdrant_versions._swap_alias(qdrant, "vibecraft_legacy", "foreign_documents")
        with pytest.raises(ProjectError):
            migration.migrate_legacy_project(registry, qdrant=qdrant, repair=True)
        assert qdrant_versions._read_alias_target(qdrant, "vibecraft_legacy") == "foreign_documents"
        assert registry.registry_path.read_bytes() == original


@pytest.mark.parametrize("interruption", ["verification", "promotion"])
def test_migration_resumes_owned_candidate_without_rebuilding(tmp_path, source, monkeypatch, interruption):
    from qdrant_client import QdrantClient
    from test_project_indexing import Embed
    from core import indexing, artifacts, project_migration as migration
    registry = historical_registry(tmp_path, source, indexed=True)
    original = registry.registry_path.read_bytes()
    attribute = "check_index_integrity" if interruption == "verification" else "promote_version"
    real = getattr(indexing, attribute)
    monkeypatch.setattr(indexing, attribute, lambda *a, **k: (_ for _ in ()).throw(OSError("interrupted")))
    with closing(QdrantClient(":memory:")) as qdrant:
        with pytest.raises(ProjectError):
            migration.migrate_legacy_project(registry, qdrant=qdrant, embed_model=Embed())
        checkpoint = json.loads((registry.projects_dir / ".legacy-migration.json").read_text())
        assert checkpoint.get("version")
        assert registry.registry_path.read_bytes() == original
        monkeypatch.setattr(indexing, attribute, real)
        monkeypatch.setattr(indexing, "build_graph_and_index", lambda *a, **k: pytest.fail("owned candidate rebuilt"))
        target = migration.migrate_legacy_project(registry, qdrant=qdrant, repair=interruption == "promotion")
        assert artifacts.current_version(project=target) == checkpoint["version"]
        assert registry.get("legacy") == target

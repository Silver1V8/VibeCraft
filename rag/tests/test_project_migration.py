"""Project bootstrap and migration use disposable roots and real verified files."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess

import pytest

from core import config
from core.projects import ProjectError, ProjectRegistry, legacy_project_context, _create_project_root


@pytest.fixture
def source(tmp_path):
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

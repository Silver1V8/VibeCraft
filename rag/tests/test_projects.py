"""Registry guarantees, using only disposable project roots and real OS locks."""
import json
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import replace

import pytest
import yaml

from core import config as installation
from core.projects import ProjectError, ProjectRegistry, legacy_project_context


def registry(tmp_path):
    return ProjectRegistry(tmp_path / "managed", bootstrap_legacy=False)


def manifest(directory, project_id="a" * 32, name="External", **extra):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "project.yaml").write_text(yaml.safe_dump({
        "schema_version": 1, "id": project_id, "name": name, **extra,
    }), encoding="utf-8")
    return directory


def test_project_id_from_name_is_readable_and_safe():
    from core.projects import project_id_from_name, validate_project_id
    assert project_id_from_name("SGD_FE", set()) == "SGD-FE"
    assert project_id_from_name("Città ünica", set()) == "Citta-unica"
    assert project_id_from_name("SGD_FE", {"sgd-fe", "SGD-FE-2"}) == "SGD-FE-3"
    assert project_id_from_name("legacy", set()) == "legacy-2"
    assert project_id_from_name("CON", set()) == "CON-2"
    assert project_id_from_name("../..", set()) == "progetto"
    assert len(project_id_from_name("x" * 200, {"x" * 56})) <= 64
    for bad in ("Legacy", "nul", "a_b", "-a", "a/b", "x" * 65):
        with pytest.raises(ProjectError):
            validate_project_id(bad)
    assert validate_project_id("a" * 32) == "a" * 32  # ID esadecimali già esistenti


def test_create_project_layout_and_unique_ids(tmp_path):
    store = registry(tmp_path)
    a, b = store.create("<b>Same ../name</b>"), store.create("<b>Same ../name</b>")
    assert a.id != b.id and a.root != b.root and a.database_dir != b.database_dir
    assert a.collection_name == "vibecraft_" + a.id
    assert b.collection_name == "vibecraft_" + b.id
    # ID leggibile dal nome, "-2" solo per l'omonimo; mai separatori di path né "_".
    assert (a.id, b.id) == ("b-Same-name-b", "b-Same-name-b-2")
    assert a.name == "<b>Same ../name</b>"
    for project in (a, b):
        assert project.root.name == project.id
        for relative in ("code", "docs", "changes", "database", "database/staging",
                         "database/versions", "database/pipeline", "database/eval",
                         "database/ask"):
            assert (project.root / relative).is_dir()
        assert not (project.database_dir / "CURRENT").exists()
        assert not (project.database_dir / "models").exists()
        assert store.get(project.id) == project
    assert [p.id for p in store.list()] == [a.id, b.id]


def test_concurrent_processes_do_not_lose_records(tmp_path):
    store = registry(tmp_path)
    source = ("from core.projects import ProjectRegistry; import sys; "
              "ProjectRegistry(sys.argv[1], bootstrap_legacy=False).create('Same')")
    processes = [subprocess.Popen([sys.executable, "-c", source, str(store.projects_dir)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for _ in range(6)]
    for process in processes:
        stdout, stderr = process.communicate(timeout=60)
        assert process.returncode == 0, (stdout, stderr)
    assert len({p.id for p in store.list()}) == 6


def test_duplicate_id_and_canonical_root_leave_registry_unchanged(tmp_path):
    store = registry(tmp_path)
    external = manifest(tmp_path / "External root with spaces")
    registered = store.register(external)
    before = store.registry_path.read_bytes()
    for path in (external / ".", manifest(tmp_path / "second", registered.id)):
        with pytest.raises(ProjectError) as error:
            store.register(path)
        assert error.value.status_code == 409
        assert store.registry_path.read_bytes() == before


@pytest.mark.parametrize("payload", ["{", '{"schema_version": 3, "projects": []}',
    '{"schema_version": 1, "projects": {}}',
    '{"schema_version": true, "projects": []}'])
def test_corrupt_registry_is_never_overwritten(tmp_path, payload):
    store = registry(tmp_path)
    store.registry_path.write_text(payload, encoding="utf-8")
    before = store.registry_path.read_bytes()
    for action in (store.list, lambda: store.create("New"),
                   lambda: store.rename("any-id", "New"),
                   lambda: ProjectRegistry(store.projects_dir)):
        with pytest.raises(ProjectError) as error:
            action()
        assert error.value.status_code == 503
        assert store.registry_path.read_bytes() == before


@pytest.mark.parametrize("extra", [{"schema_version": 2}, {"id": "../outside"},
    {"id": "LEGACY"}, {"name": " "}, {"root": "/other"},
    {"settings": {"vector_database": {"collection_name": "other"}}},
    {"settings": {"authority": {"endpoint": "http://other"}}},
    {"settings": {"verification": {"commands": {"web": "npm test"}}}},
    {"settings": {"retrieval": {"governed_max_chunks": "many"}}}])
def test_invalid_manifest_never_changes_registry(tmp_path, extra):
    store = registry(tmp_path)
    root = manifest(tmp_path / "external", **extra)
    before = store.registry_path.read_bytes()
    with pytest.raises(ProjectError) as error:
        store.register(root)
    assert error.value.status_code == 422
    assert store.registry_path.read_bytes() == before


def test_settings_are_validated_and_do_not_mutate_installation(tmp_path):
    store = registry(tmp_path)
    root = manifest(tmp_path / "external", settings={
        "authority": {"class_weights": {"CUSTOM": 0.8}},
        "retrieval": {"governed_max_chunks": 3},
        "verification": {"commands": {"web": ["npm", "test"]}},
    })
    before = json.dumps(installation.config, sort_keys=True)
    context = store.register(root)
    assert context.settings["retrieval"]["governed_max_chunks"] == 3
    assert context.settings["verification"]["commands"]["web"] == ["npm", "test"]
    context.settings["authority"]["class_weights"]["CUSTOM"] = 1
    assert store.get(context.id).settings["authority"]["class_weights"]["CUSTOM"] == 0.8
    assert json.dumps(installation.config, sort_keys=True) == before


def test_missing_or_modified_project_fails_without_fallback(tmp_path):
    store = registry(tmp_path)
    a = store.create("A")
    store.create("B")
    (a.root / "project.yaml").unlink()
    with pytest.raises(ProjectError):
        store.get(a.id)
    with pytest.raises(ProjectError) as error:
        store.get("f" * 32)
    assert error.value.status_code == 404
    with pytest.raises(ProjectError) as error:
        store.get("../other")
    assert error.value.status_code == 422


def test_linked_project_directories_and_registry_are_rejected(tmp_path):
    store = registry(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    root = manifest(tmp_path / "external")
    link = root / "code"
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                                capture_output=True)
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProjectError):
        store.register(root)
    assert not list(outside.iterdir())


def test_v1_legacy_requires_explicit_migration(tmp_path):
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    db = tmp_path / "custom database"
    db.mkdir()
    artifact = db / "graph.json"
    artifact.write_bytes(b'{"untouched": true}')
    base = legacy_project_context()
    legacy = replace(base, root=legacy_root, code_dir=legacy_root / "code",
                     docs_dir=legacy_root / "custom-docs", changes_dir=legacy_root / "changes",
                     database_dir=db, staging_dir=legacy_root / "rag" / "old-staging")
    before = artifact.read_bytes()
    store = ProjectRegistry(tmp_path / "managed", legacy_context=legacy, bootstrap_legacy=False)
    store.registry_path.write_text(json.dumps({"schema_version": 1, "projects": [
        {"id": "legacy", "name": legacy.name, "root": str(legacy.root), "legacy": True}
    ]}), encoding="utf-8")
    registry_before = store.registry_path.read_bytes()
    for action in (lambda: store.get("legacy"), lambda: store.create("Other"),
                   lambda: store.register(manifest(tmp_path / "external")),
                   lambda: store.rename("legacy", "Renamed")):
        with pytest.raises(ProjectError) as error:
            action()
        assert error.value.code == "project_migration_required"
        assert error.value.status_code == 409
        assert store.registry_path.read_bytes() == registry_before
        assert artifact.read_bytes() == before
        assert not (legacy_root / "project.yaml").exists()
    assert store.historical_project() == legacy


def test_legacy_id_uses_an_ordinary_manifest(tmp_path):
    store = registry(tmp_path)
    project = store.register(manifest(tmp_path / "managed" / "legacy", "legacy", "Initial"))
    assert project.id == "legacy" and project.legacy is False
    assert project.collection_name == "vibecraft_legacy"
    assert store.get("legacy") == project
    assert json.loads(store.registry_path.read_text())["schema_version"] == 2


def test_v1_ordinary_records_remain_openable(tmp_path):
    store = registry(tmp_path)
    project = store.create("A")
    raw = json.loads(store.registry_path.read_text())
    raw["schema_version"] = 1
    store.registry_path.write_text(json.dumps(raw))
    original = store.registry_path.read_bytes()
    assert ProjectRegistry(store.projects_dir, readonly=True).get(project.id) == project
    assert store.registry_path.read_bytes() == original
    store.create("B")
    assert json.loads(store.registry_path.read_text())["schema_version"] == 2


def test_empty_v2_registry_stays_empty(tmp_path):
    store = registry(tmp_path)
    store.registry_path.write_text('{"schema_version": 2, "projects": []}')
    assert ProjectRegistry(store.projects_dir).list() == []


def test_empty_installation_does_not_bootstrap_legacy(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    legacy = replace(legacy_project_context(), root=root, code_dir=root / "code",
                     docs_dir=root / "docs", changes_dir=root / "changes",
                     database_dir=root / "database", staging_dir=root / "staging")
    assert ProjectRegistry(tmp_path / "managed", legacy_context=legacy).list() == []
    assert not legacy.database_dir.exists()


def _clean_clone(tmp_path):
    root = tmp_path / "clone"
    (root / "templates" / "docs" / "area").mkdir(parents=True)
    (root / "templates" / "docs" / "area" / "norma.md").write_text("# Norma\n", encoding="utf-8")
    (root / "templates" / "code" / "backend").mkdir(parents=True)
    (root / "templates" / "code" / "backend" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (root / "templates" / "template_spec.md").write_text("segnaposto\n", encoding="utf-8")
    return root, replace(legacy_project_context(), root=root, code_dir=root / "code",
                         docs_dir=root / "docs", changes_dir=root / "changes",
                         database_dir=root / "database", staging_dir=root / "staging")


def test_clean_clone_bootstraps_legacy_from_templates(tmp_path):
    """Un clone locale non ha docs/ e code/ alla radice: la baseline versionata è in
    templates/, e da lì nasce il progetto iniziale (come nell'immagine Docker)."""
    root, legacy = _clean_clone(tmp_path)
    store = ProjectRegistry(tmp_path / "managed", legacy_context=legacy)
    [project] = store.list()
    assert project.id == "legacy"
    assert (project.docs_dir / "area" / "norma.md").read_text(encoding="utf-8") == "# Norma\n"
    assert (project.code_dir / "backend" / "app.py").is_file()
    assert not (project.docs_dir / "template_spec.md").exists()
    assert (root / "templates" / "docs" / "area" / "norma.md").is_file()   # copia, non spostamento


def test_root_baseline_takes_precedence_over_templates(tmp_path):
    root, legacy = _clean_clone(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "locale.md").write_text("# Locale\n", encoding="utf-8")
    [project] = ProjectRegistry(tmp_path / "managed", legacy_context=legacy).list()
    assert (project.docs_dir / "locale.md").is_file()
    assert not (project.docs_dir / "area").exists()


def test_reader_registry_is_read_only(tmp_path, monkeypatch):
    store = registry(tmp_path)
    project = store.create("A")
    monkeypatch.setattr(installation, "ROLE", "reader")
    reader = ProjectRegistry(store.projects_dir)
    assert reader.get(project.id) == project
    before = store.registry_path.read_bytes()
    with pytest.raises(ProjectError) as error:
        reader.create("B")
    assert error.value.status_code == 409
    assert store.registry_path.read_bytes() == before
    with pytest.raises(ProjectError) as error:
        reader.rename(project.id, "Renamed")
    assert error.value.status_code == 409
    assert error.value.code == "read_only"
    assert store.registry_path.read_bytes() == before
    missing = tmp_path / "reader absent"
    assert ProjectRegistry(missing).list() == []
    assert not missing.exists()


def test_rename_updates_display_name_only(tmp_path):
    store = registry(tmp_path)
    project = store.create("Original")
    other = store.create("Other")
    root_before = project.root
    collection_before = project.collection_name
    renamed = store.rename(project.id, "  Nuovo nome  ")
    assert renamed.id == project.id
    assert renamed.root == root_before
    assert renamed.collection_name == collection_before
    assert renamed.name == "Nuovo nome"
    assert store.get(project.id).name == "Nuovo nome"
    assert yaml.safe_load((root_before / "project.yaml").read_text(encoding="utf-8"))["name"] == "Nuovo nome"
    assert store.get(other.id) == other
    assert [p.id for p in store.list()] == [project.id, other.id]


def test_rename_allows_duplicate_display_names(tmp_path):
    store = registry(tmp_path)
    a, b = store.create("Alpha"), store.create("Beta")
    renamed = store.rename(b.id, "Alpha")
    assert renamed.name == "Alpha"
    assert store.get(a.id).name == "Alpha"
    assert {p.id for p in store.list()} == {a.id, b.id}


def test_rename_rejects_empty_name_and_unknown_id(tmp_path):
    store = registry(tmp_path)
    project = store.create("Keep")
    before = store.registry_path.read_bytes()
    manifest_before = (project.root / "project.yaml").read_bytes()
    for bad in ("", "   ", "\t"):
        with pytest.raises(ProjectError) as error:
            store.rename(project.id, bad)
        assert error.value.status_code == 422
        assert error.value.code == "invalid_project_name"
        assert store.registry_path.read_bytes() == before
        assert (project.root / "project.yaml").read_bytes() == manifest_before
    with pytest.raises(ProjectError) as error:
        store.rename("missing-project", "Nope")
    assert error.value.status_code == 404
    assert error.value.code == "project_not_found"
    assert store.registry_path.read_bytes() == before


def test_rename_is_idempotent_for_same_name(tmp_path):
    store = registry(tmp_path)
    project = store.create("Same")
    before = store.registry_path.read_bytes()
    again = store.rename(project.id, "Same")
    assert again == project
    assert store.registry_path.read_bytes() == before


def test_rename_preserves_manifest_settings(tmp_path):
    store = registry(tmp_path)
    root = manifest(tmp_path / "external", settings={
        "retrieval": {"governed_max_chunks": 3},
    })
    project = store.register(root)
    renamed = store.rename(project.id, "External Renamed")
    raw = yaml.safe_load((project.root / "project.yaml").read_text(encoding="utf-8"))
    assert raw == {
        "schema_version": 1,
        "id": project.id,
        "name": "External Renamed",
        "settings": {"retrieval": {"governed_max_chunks": 3}},
    }
    assert renamed.settings["retrieval"]["governed_max_chunks"] == 3


def test_rename_fails_closed_when_manifest_disagrees(tmp_path):
    store = registry(tmp_path)
    project = store.create("A")
    raw = yaml.safe_load((project.root / "project.yaml").read_text(encoding="utf-8"))
    raw["name"] = "Desynced"
    (project.root / "project.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    before = store.registry_path.read_bytes()
    with pytest.raises(ProjectError):
        store.rename(project.id, "Fixed")
    assert store.registry_path.read_bytes() == before
    assert yaml.safe_load((project.root / "project.yaml").read_text(encoding="utf-8"))["name"] == "Desynced"


def test_relative_projects_dir_is_rejected(tmp_path):
    with pytest.raises(ProjectError):
        ProjectRegistry(Path("relative"), bootstrap_legacy=False)


def test_duplicate_yaml_keys_and_nested_settings_are_rejected(tmp_path):
    store = registry(tmp_path)
    root = manifest(tmp_path / "external")
    with (root / "project.yaml").open("a", encoding="utf-8") as stream:
        stream.write("name: Replacement\n")
    with pytest.raises(ProjectError):
        store.register(root)


def test_registry_rejects_duplicate_records_and_missing_roots(tmp_path):
    store = registry(tmp_path)
    project = store.create("A")
    data = json.loads(store.registry_path.read_text(encoding="utf-8"))
    data["projects"].append(data["projects"][0].copy())
    store.registry_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ProjectError) as error:
        store.list()
    assert error.value.status_code == 503
    data["projects"].pop()
    data["projects"][0]["root"] = str((tmp_path / "missing").resolve())
    store.registry_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ProjectError) as error:
        store.get(project.id)
    assert error.value.status_code == 503


def test_registering_registry_directory_is_rejected(tmp_path):
    store = registry(tmp_path)
    manifest(store.projects_dir)
    before = store.registry_path.read_bytes()
    with pytest.raises(ProjectError):
        store.register(store.projects_dir)
    assert store.registry_path.read_bytes() == before


def test_registered_link_is_rejected_on_reopen(tmp_path):
    store = registry(tmp_path)
    project = store.create("A")
    project.code_dir.rmdir()  # Verified empty, test-owned directory only.
    outside = tmp_path / "outside"
    outside.mkdir()
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(project.code_dir), str(outside)],
                                capture_output=True)
        assert result.returncode == 0, result.stderr
    else:
        project.code_dir.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProjectError) as error:
        store.get(project.id)
    assert error.value.status_code == 503


def test_linked_registry_storage_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "managed"
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProjectError):
        ProjectRegistry(link, bootstrap_legacy=False)
    assert not list(outside.iterdir())


@pytest.mark.parametrize("directory", ["versions", "pipeline", "eval", "ask"])
def test_linked_database_subdirectories_are_rejected(tmp_path, directory):
    store = registry(tmp_path)
    project = store.create("A")
    link = project.database_dir / directory
    link.rmdir()  # Verified empty, test-owned directory only.
    outside = tmp_path / "outside"
    outside.mkdir()
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProjectError) as error:
        store.get(project.id)
    assert error.value.status_code == 503


@pytest.mark.parametrize("location", ["parent", "nested"])
def test_registered_roots_cannot_overlap_external_legacy_staging(tmp_path, location):
    root = tmp_path / "legacy"
    root.mkdir()
    db = root / "database"
    db.mkdir()
    (db / "graph.json").write_text("{}", encoding="utf-8")
    stage_parent = tmp_path / "custom stage area"
    stage = stage_parent / "staging"
    stage.mkdir(parents=True)
    legacy = replace(legacy_project_context(), root=root, code_dir=root / "code",
                     docs_dir=root / "docs", changes_dir=root / "changes",
                     database_dir=db, staging_dir=stage)
    store = ProjectRegistry(tmp_path / "managed", legacy_context=legacy, bootstrap_legacy=False)
    store.registry_path.write_text(json.dumps({"schema_version": 1, "projects": [
        {"id": "legacy", "name": legacy.name, "root": str(root), "legacy": True}
    ]}))
    external = manifest(stage_parent if location == "parent" else stage / "nested project")
    before = store.registry_path.read_bytes()
    with pytest.raises(ProjectError) as error:
        store.register(external)
    assert error.value.status_code == 409
    assert store.registry_path.read_bytes() == before

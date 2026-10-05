"""Project collisions exercise real disk artifacts, OS leases and Qdrant operations."""
import json
import os
import subprocess
from contextlib import closing
from uuid import uuid4

import numpy as np
import pytest
from qdrant_client import QdrantClient

from core import artifacts, indexing, qdrant_versions as versions
from core.config import DENSE_DIM
from core.projects import ProjectRegistry
from core.writer_lock import WriterLockBusyError, writer_lock


class Embed:
    def encode(self, texts, **kwargs):
        dense = np.zeros((len(texts), DENSE_DIM), dtype=np.float32)
        for i, text in enumerate(texts):
            dense[i, 0] = 1 if "ALPHA" in text else -1
        result = {"dense_vecs": dense}
        if kwargs.get("return_sparse"):
            result["lexical_weights"] = [{1: 1.0} for _ in texts]
        if kwargs.get("return_colbert_vecs"):
            result["colbert_vecs"] = [v[None, :] for v in dense]
        return result


@pytest.fixture
def projects(tmp_path):
    registry = ProjectRegistry(tmp_path / "projects", bootstrap_legacy=False)
    return registry.create("A"), registry.create("B")


@pytest.fixture(params=["memory", "server"])
def qdrant(request, projects):
    url = os.environ.get("VIBECRAFT_TEST_QDRANT_URL")
    if request.param == "server" and not url:
        if os.environ.get("VIBECRAFT_REQUIRE_QDRANT") == "1":
            pytest.fail("dedicated VIBECRAFT_TEST_QDRANT_URL required")
        pytest.skip("dedicated Qdrant endpoint absent")
    client = QdrantClient(":memory:") if request.param == "memory" else QdrantClient(url=url)
    yield client
    # Only UUID project namespaces created by this test; never clean unrelated collections.
    for c in client.get_collections().collections:
        if any(c.name == p.collection_name or c.name.startswith(p.collection_name + "__") for p in projects):
            client.delete_collection(c.name)
    client.close()


def build(project, qdrant):
    return indexing.build_graph_and_index(qdrant, Embed(), project=project)


def body(project, text):
    (project.docs_dir / "same.md").write_text("# Shared title\n\n" + text, encoding="utf-8")


def test_build_delta_rollback_same_names_and_versions(projects, qdrant, monkeypatch):
    a, b = projects
    monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v1")
    body(a, "ALPHA")
    body(b, "BETA")
    (a.code_dir / "same.py").write_text("def shared(): return 'ALPHA'\n", encoding="utf-8")
    (b.code_dir / "same.py").write_text("def shared(): return 'BETA'\n", encoding="utf-8")
    assert build(a, qdrant) == build(b, qdrant) == "v1"
    a_manifest = artifacts._read_manifest(project=a)
    b_manifest = artifacts._read_manifest(project=b)
    assert a_manifest["doc_hashes"]["same.md"] != b_manifest["doc_hashes"]["same.md"]
    assert a_manifest["code_hashes"]["same.py"] != b_manifest["code_hashes"]["same.py"]
    a_snapshot = artifacts.load_artifacts(project=a)
    b_snapshot = artifacts.load_artifacts(project=b)
    try:
        key = next(iter(a_snapshot.colbert_store))
        assert a_snapshot.colbert_store[key][0, 0] == 1
        assert b_snapshot.colbert_store[key][0, 0] == -1
        assert versions._read_alias_target(qdrant, a.collection_name) == a.collection_name + "__v1"
        assert versions._read_alias_target(qdrant, b.collection_name) == b.collection_name + "__v1"
        monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v2")
        body(a, "ALPHA changed")
        stats = indexing.incremental_index(qdrant, Embed(), project=a, changed_paths=["docs/same.md"])
        assert stats["reindexed_docs"] == 1
        assert artifacts.current_version(project=a) == "v2"
        assert artifacts.current_version(project=b) == "v1"
        assert indexing.index_status(project=b)["stale"] is False
        assert indexing.check_index_integrity(qdrant, project=b)["ok"] is True
        b_points, _ = qdrant.scroll(b.collection_name, with_vectors=True)
        assert b_points and all(point.vector["dense"][0] == -1 for point in b_points)
        monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v3")
        body(a, "BETA replacement")
        build(a, qdrant)
        versions.assert_rollback_target_has_vectors(qdrant, "v1", project=a)
        artifacts.rollback_version("v1", project=a)
        versions.rollback_qdrant_alias_if_needed(qdrant, "v1", project=a)
        assert versions.reconcile_qdrant_alias(qdrant, project=a)["state"] == "aligned"
        assert artifacts.current_version(project=b) == "v1"
        assert b_snapshot.colbert_store[key][0, 0] == -1
        assert a_snapshot.colbert_store[key][0, 0] == 1
        assert not list(a.database_dir.glob(".colbert-staging/*"))
        assert not list(b.database_dir.glob(".colbert-staging/*"))
    finally:
        a_snapshot.colbert_store.close()
        b_snapshot.colbert_store.close()


def test_gc_never_deletes_other_project_collections(projects, qdrant, monkeypatch):
    a, b = projects
    monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v1")
    body(a, "ALPHA")
    body(b, "BETA")
    build(a, qdrant)
    build(b, qdrant)
    a_candidate = a.collection_name + "__v2"
    b_orphan = b.collection_name + "__v2"
    legacy = "vibecraft_testlegacy_" + uuid4().hex + "__v1"
    for collection in (a_candidate, b_orphan, legacy):
        indexing._ensure_collection(qdrant, collection_name=collection)
    assert versions.gc_orphaned_qdrant_collections(qdrant, project=b) == [b_orphan]
    assert versions._qdrant_collection_exists(qdrant, a_candidate)
    assert versions._qdrant_collection_exists(qdrant, legacy)
    qdrant.delete_collection(legacy)


def test_lease_and_writer_lock_are_project_scoped(projects, qdrant, monkeypatch):
    a, b = projects
    monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v1")
    for project in (a, b):
        body(project, "ALPHA")
        build(project, qdrant)
    reader = artifacts.load_artifacts(version="v1", project=a, retain_lease=True)
    try:
        monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v2")
        for project in (a, b):
            body(project, "BETA")
            build(project, qdrant)
        assert artifacts.prune_versions(keep=1, project=b) == ["v1"]
        assert artifacts.prune_versions(keep=1, project=a) == []
        assert next(iter(reader.colbert_store.values()))[0, 0] == 1
        with writer_lock(project=a, timeout_seconds=0):
            with writer_lock(project=b, timeout_seconds=0):
                with pytest.raises(WriterLockBusyError):
                    with writer_lock(project=a, timeout_seconds=0):
                        pass
    finally:
        reader.colbert_store.close()
        reader.version_lease.close()
    assert artifacts.prune_versions(keep=1, project=a) == ["v1"]
    assert versions.gc_orphaned_qdrant_collections(qdrant, project=a) == [a.collection_name + "__v1"]


@pytest.fixture
def project_artifacts(projects):
    import networkx as nx

    for project in projects:
        for version in ("v1", "v2"):
            graph = nx.DiGraph()
            graph.add_node(project.name)
            artifacts.save_artifacts(graph, {}, {}, {}, {}, version=version, project=project)
            indexing.write_index_manifest(0, version=version, immutable=True,
                                          qdrant_collection=project.collection_name + "__" + version,
                                          project=project)
        artifacts.promote_version("v1", project=project)
    return projects


@pytest.mark.parametrize("link_kind", ["symlink", "junction"])
@pytest.mark.parametrize("filename,operation", [
    ("CURRENT", "token"), ("CURRENT", "promote"), ("CURRENT", "rollback"),
    ("index_manifest.json", "manifest"),
    ("chunks.json", "integrity"),
    *[(name, operation) for name in ("graph.json", "chunks.json", "dense.npz", "code.json", "code.npz", "colbert.npz")
      for operation in ("load", "hash")],
])
def test_project_artifact_file_link_is_rejected(project_artifacts, filename, operation, link_kind):
    a, b = project_artifacts
    relative = filename if filename == "CURRENT" else "versions/v1/" + filename
    link, target = a.database_dir / relative, b.database_dir / relative
    if filename == "colbert.npz":
        artifacts._save_vectors(target, {})
    original_b = target.read_bytes()
    link.unlink(missing_ok=True)
    try:
        if link_kind == "junction" and os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target.parent)], check=True, capture_output=True)
        else:
            link.symlink_to(target if link_kind == "symlink" else target.parent,
                            target_is_directory=link_kind == "junction")
    except OSError as exc:
        if os.name == "nt" and exc.winerror == 1314:
            pytest.skip("Windows user lacks CreateSymbolicLink privilege")
        raise
    try:
        with pytest.raises(ValueError, match="linked|escaping"):
            if operation == "token":
                artifacts.current_version_token(project=a)
            elif operation == "promote":
                artifacts.promote_version("v2", project=a)
            elif operation == "rollback":
                artifacts.rollback_version("v2", project=a)
            elif operation == "manifest":
                artifacts._read_manifest(project=a)
            elif operation == "hash":
                artifacts.artifact_hashes("v1", project=a)
            elif operation == "integrity":
                with closing(QdrantClient(":memory:")) as q:
                    indexing.check_index_integrity(q, project=a)
            else:
                loaded = artifacts.load_artifacts(version="v1", project=a)
                loaded.colbert_store.close()
        assert target.read_bytes() == original_b
    finally:
        if link.exists():
            if link_kind == "junction" and os.name == "nt":
                link.rmdir()
            else:
                link.unlink()


def test_retention_rejects_project_version_junction(project_artifacts):
    a, b = project_artifacts
    link = a.database_dir / "versions" / "v0"
    target = b.database_dir / "versions" / "v1"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="linked|escaping"):
            artifacts.prune_versions(keep=1, project=a)
        assert (target / "graph.json").is_file()
    finally:
        if link.exists():
            if os.name == "nt":
                link.rmdir()
            else:
                link.unlink()


def test_new_project_never_loads_legacy_flat_artifacts(projects, tmp_path, monkeypatch):
    a, b = projects
    import networkx as nx
    legacy = tmp_path / "legacy-graph.json"
    artifacts._atomic_write_json(legacy, artifacts._graph_to_json(nx.DiGraph([(1, 2)])))
    monkeypatch.setattr(artifacts, "GRAPH_JSON_PATH", legacy)
    assert artifacts.load_artifacts(project=a).graph is None
    assert artifacts.current_version(project=b) is None


def test_gate_uses_project_golden_and_history(projects, monkeypatch):
    from core import eval_gate

    a, b = projects
    original_loader = eval_gate.load_golden_cases
    monkeypatch.setattr(eval_gate, "load_golden_cases", lambda path=None: [{"q": "legacy"}] if path is None else [])
    assert eval_gate.gate_promotion("v1", None, None, {}, project=b)["skipped"] == "no_golden_set"
    monkeypatch.setattr(eval_gate, "load_golden_cases", original_loader)
    (a.root / "eval").mkdir()
    (a.root / "eval" / "golden.yaml").write_text("cases: [{q: ALPHA, expected: [same.md]}]", encoding="utf-8")
    a.settings["eval_gate"].update(enabled=True, k=1, min_recall=0.9, blocking=True)
    monkeypatch.setattr(eval_gate.retrieval, "hybrid_search", lambda *args, **kw: [])
    assert eval_gate.gate_promotion("v1", None, None, {}, project=a)["passed"] is False
    assert json.loads((a.database_dir / "eval" / "history.jsonl").read_text())["version"] == "v1"
    assert (a.database_dir / "alerts.jsonl").is_file()
    assert not (b.database_dir / "eval" / "history.jsonl").exists()


def test_disabled_project_gate_does_not_load_golden(projects, monkeypatch):
    from core import eval_gate

    project, _ = projects
    project.settings["eval_gate"]["enabled"] = False

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled gate must not read or evaluate golden cases")

    monkeypatch.setattr(eval_gate, "load_golden_cases", forbidden)
    monkeypatch.setattr(eval_gate, "evaluate_recall", forbidden)
    res = eval_gate.gate_promotion("candidate", None, None, {}, project=project)
    assert res["passed"] is True and res["skipped"] == "disabled"


@pytest.mark.parametrize("entrypoint", ["cli", "api"])
def test_invalid_project_golden_keeps_current_and_aliases(projects, qdrant, monkeypatch, entrypoint):
    from api import routes_reindex

    a, b = projects
    monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v1")
    for project, text in ((a, "ALPHA"), (b, "BETA")):
        body(project, text)
        build(project, qdrant)
    (a.root / "eval").mkdir()
    (a.root / "eval" / "golden.yaml").write_text("cases: [", encoding="utf-8")
    a.settings["eval_gate"].update(enabled=True, blocking=True)
    monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v2")
    body(a, "BETA replacement")
    if entrypoint == "cli":
        assert build(a, qdrant) == "v2"
    else:
        monkeypatch.setattr(routes_reindex, "_reindex_embed_model", lambda: Embed())
        monkeypatch.setitem(routes_reindex.state, "qdrant", qdrant)
        result = routes_reindex._run_full_rebuild(None, project=a)
        assert result["promoted"] is False and result["job_status"] == "completed_not_promoted"
        assert result["eval"]["skipped"] == "error"
    assert artifacts.current_version(project=a) == "v1"
    assert artifacts.current_version(project=b) == "v1"
    assert versions._read_alias_target(qdrant, a.collection_name) == a.collection_name + "__v1"
    assert versions._read_alias_target(qdrant, b.collection_name) == b.collection_name + "__v1"
    assert (a.database_dir / "versions" / "v2" / "index_manifest.json").is_file()
    alert = json.loads((a.database_dir / "alerts.jsonl").read_text(encoding="utf-8"))
    assert alert["level"] == "critical" and alert["version"] == "v2"
    assert not (a.database_dir / "eval" / "history.jsonl").exists()
    assert not (b.database_dir / "alerts.jsonl").exists()


def test_corrupt_project_manifest_and_pointer_fail_explicitly(projects):
    project, _ = projects
    (project.database_dir / "CURRENT").write_text("missing", encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError, FileNotFoundError)):
        artifacts.current_version(project=project)
    (project.database_dir / "versions" / "v1").mkdir(parents=True)
    (project.database_dir / "CURRENT").write_text("v1", encoding="utf-8")
    (project.database_dir / "versions" / "v1" / "index_manifest.json").write_text("{", encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError)):
        artifacts._read_manifest(project=project)


def test_foreign_collection_manifest_cannot_repair_alias(projects, qdrant, monkeypatch):
    a, b = projects
    monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v1")
    for project in (a, b):
        body(project, "ALPHA")
        build(project, qdrant)
    path = artifacts.manifest_path(project=b)
    manifest = json.loads(path.read_text())
    manifest["qdrant_collection"] = a.collection_name + "__v1"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError)):
        versions.repair_qdrant_alias(qdrant, project=b)
    assert versions._read_alias_target(qdrant, b.collection_name) == b.collection_name + "__v1"


def test_first_delta_creates_versioned_collection(projects, qdrant):
    a, _ = projects
    body(a, "ALPHA")
    stats = indexing.incremental_index(qdrant, Embed(), project=a)
    assert stats["reindexed_docs"] == 1
    physical = versions._read_alias_target(qdrant, a.collection_name)
    assert physical == a.collection_name + "__" + artifacts.current_version(project=a)


@pytest.mark.parametrize("version", ["../escape", "..\\escape", "", "/absolute"])
def test_version_paths_reject_traversal(projects, version):
    project, _ = projects
    with pytest.raises(ValueError):
        artifacts.version_dir(version, project=project)


@pytest.mark.parametrize("kind", ["docs", "code"])
@pytest.mark.parametrize("operation", ["hash", "full", "delta", "scanner"])
def test_source_junction_cannot_index_other_project(projects, kind, operation):
    a, b = projects
    root = a.docs_dir if kind == "docs" else a.code_dir
    target = b.docs_dir if kind == "docs" else b.code_dir
    (target / ("same.md" if kind == "docs" else "same.py")).write_text(
        "# B private\n" if kind == "docs" else "def private(): return 'B secret'\n", encoding="utf-8")
    link = root / "linked"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)
    try:
        with closing(QdrantClient(":memory:")) as q:
            with pytest.raises(ValueError, match="linked|escaping"):
                if operation == "hash":
                    (indexing.docs_hashes if kind == "docs" else indexing._code_hashes)(project=a)
                elif operation == "full":
                    build(a, q)
                elif operation == "delta":
                    indexing.incremental_index(q, Embed(), project=a)
                elif kind == "code":
                    from code_index import collect_code_symbols
                    collect_code_symbols(root)
                else:
                    indexing._build_full_state(Embed(), root, a.code_dir)
    finally:
        if os.name == "nt":
            link.rmdir()  # Remove only the junction, never its target.
        else:
            link.unlink()


def test_colbert_staging_junction_cannot_write_other_project(projects):
    a, b = projects
    link = a.database_dir / ".colbert-staging"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(b.database_dir)], check=True, capture_output=True)
    else:
        link.symlink_to(b.database_dir, target_is_directory=True)
    before = set(b.database_dir.iterdir())
    try:
        with closing(QdrantClient(":memory:")) as q:
            with pytest.raises(ValueError, match="linked"):
                build(a, q)
        assert set(b.database_dir.iterdir()) == before
    finally:
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()


def test_razor_auxiliary_scan_does_not_read_excluded_project_junction(projects):
    from code_index.razor import _collect_imports_usings

    a, b = projects
    (b.code_dir / "_Imports.razor").write_text("@using PrivateProjectB\n", encoding="utf-8")
    excluded = a.code_dir / "node_modules"
    excluded.mkdir()
    link = excluded / "linked"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(b.code_dir)], check=True, capture_output=True)
    else:
        link.symlink_to(b.code_dir, target_is_directory=True)
    try:
        assert _collect_imports_usings(a.code_dir) == {}
    finally:
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()


@pytest.mark.parametrize("component", ["eval", "golden.yaml"])
def test_project_gate_rejects_linked_golden_before_fail_open(projects, component):
    from core import eval_gate

    a, b = projects
    target = b.root / "eval"
    target.mkdir()
    (target / "golden.yaml").write_text("cases: [{q: PRIVATE_B, expected: [private.md]}]", encoding="utf-8")
    if component == "golden.yaml":
        (a.root / "eval").mkdir()
    link = a.root / "eval" if component == "eval" else a.root / "eval" / "golden.yaml"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="linked|escaping"):
            eval_gate.gate_promotion("v1", None, None, {}, project=a)
    finally:
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()


@pytest.mark.parametrize("reader", ["token", "current", "version_dir", "artifact_dir", "load"])
def test_ordinary_project_rejects_synthetic_legacy_version(projects, reader):
    project, _ = projects
    (project.database_dir / "CURRENT").write_text("legacy", encoding="utf-8")
    with pytest.raises(ValueError, match="legacy"):
        if reader == "token":
            artifacts.current_version_token(project=project)
        elif reader == "current":
            artifacts.current_version(project=project)
        elif reader == "version_dir":
            artifacts.version_dir("legacy", project=project)
        elif reader == "artifact_dir":
            artifacts.artifact_dir("legacy", project=project)
        else:
            artifacts.load_artifacts(version="legacy", project=project)


def test_ordinary_delta_keeps_pinned_vectors_and_rollback_restores_query(projects, qdrant, monkeypatch):
    a, b = projects
    monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v1")
    for project, text in ((a, "ALPHA"), (b, "BETA")):
        body(project, text)
        build(project, qdrant)
    reader = artifacts.load_artifacts(version="v1", project=a, retain_lease=True)
    old_collection = versions._qdrant_collection_for_version("v1", project=a)
    query = [1.0] + [0.0] * (DENSE_DIM - 1)

    def score(collection):
        return qdrant.query_points(collection, query=query, using="dense", limit=1).points[0].score

    try:
        assert score(old_collection) == pytest.approx(1)
        monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v2")
        body(a, "BETA replacement")
        indexing.incremental_index(qdrant, Embed(), project=a)
        assert score(old_collection) == pytest.approx(1)
        assert score(a.collection_name) == pytest.approx(-1)
        assert artifacts._read_manifest(project=a)["immutable"] is True
        assert (a.database_dir / artifacts.IMMUTABLE_MARKER_FILENAME).is_file()
        assert versions._qdrant_collection_for_version("v2", project=a) == a.collection_name + "__v2"
        assert next(iter(reader.colbert_store.values()))[0, 0] == 1
        artifacts.rollback_version("v1", project=a)
        versions.rollback_qdrant_alias_if_needed(qdrant, "v1", project=a)
        assert score(a.collection_name) == pytest.approx(1)
        assert score(b.collection_name) == pytest.approx(-1)
        assert artifacts.current_version(project=b) == "v1"
    finally:
        reader.colbert_store.close()
        reader.version_lease.close()

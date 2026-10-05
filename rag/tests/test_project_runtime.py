"""Real A/B artifacts share version names and chunk IDs, never their contents."""
from concurrent.futures import ThreadPoolExecutor
import json

import networkx as nx
import numpy as np
import pytest

from api import deps
from core import artifacts, ask_cache
from core.projects import ProjectRegistry, _create_project_root


def indexed(project, text, version="v1"):
    graph = nx.DiGraph()
    graph.add_node("same.md", type="document", title=text, description=text)
    chunks = {"same.md#1": {"doc_id": "same.md", "text": text}}
    artifacts.save_artifacts(graph, {"same.md#1": np.ones((1, 2), dtype=np.float16)},
                             chunks, {}, {}, version=version, project=project)
    manifest = {"version": version, "immutable": True,
                "qdrant_collection": project.collection_name + "__" + version,
                "artifact_hashes": artifacts.artifact_hashes(version, project=project)}
    artifacts.manifest_path(version, project=project).write_text(json.dumps(manifest), encoding="utf-8")
    artifacts.activate_immutable_index(project=project)
    artifacts.promote_version(version, project=project)


@pytest.fixture
def projects(tmp_path, monkeypatch):
    registry = ProjectRegistry(tmp_path / "projects", bootstrap_legacy=False)
    monkeypatch.setitem(deps.state, "snapshot", None)
    monkeypatch.setitem(deps.state, "reload_error", None)
    monkeypatch.setattr(deps, "_project_states", {}, raising=False)
    monkeypatch.setattr(deps, "_snapshots", __import__('collections').OrderedDict(), raising=False)
    initial = _create_project_root(registry.projects_dir / "legacy", "legacy", "A")
    return [registry.register(initial.root), registry.create("B"), registry.create("C")]


def test_snapshots_are_isolated_and_eviction_keeps_inflight_lease(projects):
    for project in projects:
        indexed(project, project.name)
    a, b, c = projects
    snap_a = deps.require_snapshot(a)
    snap_b = deps.require_snapshot(b)
    assert snap_a.chunks["same.md#1"]["text"] == "A"
    assert snap_b.chunks["same.md#1"]["text"] == "B"
    deps.require_snapshot(c)
    assert len(deps._snapshots) == 2
    assert a.id not in deps._snapshots
    assert snap_a.colbert_store["same.md#1"].shape == (1, 2)
    assert deps.qdrant_collection_for_version("v1", project=a) != deps.qdrant_collection_for_version("v1", project=b)
    assert deps.require_snapshot(a).chunks == snap_a.chunks


def test_concurrent_capture_loads_once_and_reload_error_is_local(projects, monkeypatch):
    a, b, _ = projects
    indexed(a, "A")
    indexed(b, "B")
    with ThreadPoolExecutor(6) as pool:
        snapshots = list(pool.map(deps.require_snapshot, [a] * 12))
    assert all(s is snapshots[0] for s in snapshots)
    (a.database_dir / "CURRENT").write_text("../bad", encoding="utf-8")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        deps.require_snapshot(a)
    assert error.value.status_code == 503
    assert deps.require_snapshot(b).chunks["same.md#1"]["text"] == "B"


def test_ask_cache_project_key():
    a = ask_cache.make_key("v1", "hybrid", 5, 2, "same", project_id="a" * 32)
    b = ask_cache.make_key("v1", "hybrid", 5, 2, "same", project_id="b" * 32)
    cache = ask_cache.AskCache()
    cache.set(a, {"answer": "A"})
    assert cache.get(b) is None


def test_initial_project_gate_reads_its_own_golden(projects):
    from dataclasses import replace
    from core import eval_gate
    project = replace(projects[0], settings={"eval_gate": {"enabled": True, "blocking": True}})
    golden = project.root / "eval" / "golden.yaml"
    golden.parent.mkdir()
    golden.write_text("invalid: golden")
    result = eval_gate.gate_promotion("v1", None, None, {}, project=project)
    assert result["passed"] is False
    assert result["error_stage"] == "load"
    assert (project.database_dir / "alerts.jsonl").exists()


def test_shared_resources_initialize_once(projects, monkeypatch):
    calls = []
    monkeypatch.setitem(deps.state, "qdrant", None)
    monkeypatch.setitem(deps.state, "embed_model", None)
    monkeypatch.setattr(deps, "QdrantClient", lambda **kw: calls.append("qdrant") or object())
    monkeypatch.setattr(deps, "BGEM3FlagModel", lambda *a, **kw: calls.append("embed") or object())
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _: deps.ensure_shared_resources(), projects))
    assert sorted(calls) == ["embed", "qdrant"]



def test_project_authority_and_restatement_settings_are_explicit(projects):
    from dataclasses import replace
    from core import retrieval
    from types import SimpleNamespace
    a, b, _ = projects
    a = replace(a, settings={"authority": {"class_weights": {"POLICY": 1.0, "METHODOLOGY": 0.1},
                                         "boost_alpha": 1.0, "section_restatement_weight": 1.0}})
    b = replace(b, settings={"authority": {"class_weights": {"POLICY": 0.1, "METHODOLOGY": 1.0},
                                         "boost_alpha": 1.0, "section_restatement_weight": 0.5}})
    chunks = {"a": {"text": "See [RULE-X-01]"}}
    assert retrieval.restatement_sections(chunks, project=a) == frozenset({"a"})
    assert retrieval.restatement_sections(chunks, project=b) == frozenset({"a"})

    class Qdrant:
        def query_points(self, **kwargs):
            return SimpleNamespace(points=[SimpleNamespace(score=1.0, payload={
                "chunk_id": key, "doc_id": key, "classification": classification})
                for key, classification in (("a", "POLICY"), ("b", "METHODOLOGY"))])

    for project, winner in ((a, "a"), (b, "b")):
        results = retrieval.hybrid_search("same", 2, qdrant=Qdrant(), embed_model=None,
            colbert_store={}, query_encoding={"dense": [1.0], "lexical": {1: 1.0}, "colbert": None},
            project=project)
        assert results[0]["chunk_id"] == winner
        assert results[0]["authority"] == 1.0


def test_governed_retrieval_propagates_project_collection_and_ranking(projects):
    from core import retrieval
    from types import SimpleNamespace
    a, _, _ = projects
    seen = []

    class Qdrant:
        def query_points(self, **kwargs):
            seen.append(kwargs["collection_name"])
            return SimpleNamespace(points=[])

    class Embed:
        def encode(self, texts, **kwargs):
            return {"dense_vecs": [[1.0]], "lexical_weights": [{1: 1.0}], "colbert_vecs": [None]}

    retrieval.retrieve_governed_context("same", graph=nx.DiGraph(), chunks_store={},
        qdrant=Qdrant(), embed_model=Embed(), colbert_store={}, project=a,
        collection_name=a.collection_name + "__v1")
    assert seen == [a.collection_name + "__v1"] * 2


def test_eval_recall_uses_project_ranking(projects):
    from dataclasses import replace
    from core import eval_gate
    from types import SimpleNamespace
    a, _, _ = projects
    a = replace(a, settings={"authority": {"class_weights": {"POLICY": 0.01, "METHODOLOGY": 1.0},
                                         "boost_alpha": 1.0}})

    class Qdrant:
        def query_points(self, **kwargs):
            return SimpleNamespace(points=[SimpleNamespace(score=1.0, payload={
                "chunk_id": key, "doc_id": key, "classification": classification})
                for key, classification in (("a", "POLICY"), ("b", "METHODOLOGY"))])

    class Embed:
        def encode(self, texts, **kwargs):
            return {"dense_vecs": [[1.0]], "lexical_weights": [{1: 1.0}], "colbert_vecs": [None]}

    report = eval_gate.evaluate_recall(Qdrant(), Embed(), {}, k=1,
        cases=[{"q": "same", "expected": [{"doc": "b"}]}], project=a)
    assert report["recall"] == 1.0


def test_http_retrieval_real_qdrant_shared_resources(projects, monkeypatch):
    """Dedicated test server only; UUID namespaces are removed in finally."""
    import os
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from qdrant_client import QdrantClient
    from api import routes_retrieval
    from core import indexing
    from test_project_indexing import Embed
    url = os.environ.get("VIBECRAFT_TEST_QDRANT_URL")
    if not url:
        if os.environ.get("VIBECRAFT_REQUIRE_QDRANT") == "1":
            pytest.fail("Dedicated Qdrant test URL required")
        pytest.skip("Dedicated Qdrant test URL absent")
    a, b, _ = projects
    registry = ProjectRegistry(a.root.parent, bootstrap_legacy=False)
    monkeypatch.setattr(deps, "project_registry", lambda: registry)
    qdrant = QdrantClient(url=url)
    embed = Embed()
    monkeypatch.setitem(deps.state, "qdrant", qdrant)
    monkeypatch.setitem(deps.state, "embed_model", embed)
    monkeypatch.setattr(indexing, "_new_version_name", lambda **kwargs: "v1")
    app = FastAPI()
    app.include_router(routes_retrieval.router)
    client = TestClient(app, client=("127.0.0.1", 1234))
    try:
        for project, text in ((a, "ALPHA"), (b, "BETA")):
            (project.docs_dir / "same.md").write_text("# Shared\n\n" + text, encoding="utf-8")
            indexing.build_graph_and_index(qdrant, embed, project=project)
        for project, text in ((a, "ALPHA"), (b, "BETA"), (a, "ALPHA")):
            response = client.get("/api/retrieve?q=same&include_text=true", headers={"X-VibeCraft-Project": project.id})
            assert response.status_code == 200, response.text
            result = response.json()
            assert text in result["results"][0]["text"]
            assert result["project_id"] == project.id and result["index_version"] == "v1"
        assert deps.state["qdrant"] is qdrant and deps.state["embed_model"] is embed
    finally:
        for collection in qdrant.get_collections().collections:
            if any(collection.name == project.collection_name or
                   collection.name.startswith(project.collection_name + "__") for project in (a, b)):
                qdrant.delete_collection(collection.name)
        qdrant.close()


def test_legacy_flat_graph_remains_available_without_optional_sidecars(projects):
    from dataclasses import replace
    from starlette.requests import Request
    from api.routes_projects import project_metadata
    project = replace(projects[0], id="legacy", legacy=True)
    graph = nx.DiGraph()
    graph.add_node("same.md", type="document")
    (project.database_dir / "graph.json").write_text(json.dumps(artifacts._graph_to_json(graph)), encoding="utf-8")
    (project.database_dir / "index_manifest.json").write_text(json.dumps({"doc_hashes": {}}), encoding="utf-8")
    (project.docs_dir / "rule.md").write_text("`[REGOLA-LEGACY]`: Original description", encoding="utf-8")
    snapshot = deps.require_snapshot(project)
    assert "same.md" in snapshot.graph
    assert snapshot.rule_descriptions == {"REGOLA-LEGACY": "Original description"}
    request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1234)})
    assert project_metadata(project, request)["index_status"] == "ready"


def test_restatement_settings_change_without_reloading_snapshot(projects):
    import yaml
    from core import retrieval
    a, b, c = projects
    registry = ProjectRegistry(a.root.parent, bootstrap_legacy=False)
    path = a.root / "project.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["settings"] = {"authority": {"section_restatement_weight": 1.0}}
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    indexed(a, "See [RULE-X-01]")
    first = deps.require_snapshot(registry.get(a.id))
    data["settings"]["authority"]["section_restatement_weight"] = 0.5
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    changed = registry.get(a.id)
    reused = deps.require_snapshot(changed)
    assert reused is first

    def winner(snapshot):
        results = [{"chunk_id": "same.md#1", "authority": 1.0, "colbert_score": 1.0},
                   {"chunk_id": "declared#1", "authority": 1.0, "colbert_score": 0.8}]
        return retrieval.rank_by_authority(results, restatements=snapshot.restatements,
                                           project=changed)[0]["chunk_id"]

    assert winner(reused) == "declared#1"
    for project in (b, c):
        indexed(project, project.name)
        deps.require_snapshot(project)
    reloaded = deps.require_snapshot(changed)
    assert reloaded is not first
    assert winner(reloaded) == winner(reused)


@pytest.mark.parametrize("replaced", ["docs", "root", "nested"])
def test_legacy_descriptions_reject_junction_after_context_capture(projects, replaced):
    import os
    import subprocess
    from dataclasses import replace
    from code_index import source_files
    a, b, _ = projects
    captured = replace(a, legacy=True)
    (b.docs_dir / "secret.md").write_text("`[SECRET]`: B private", encoding="utf-8")
    link = a.root if replaced == "root" else a.docs_dir if replaced == "docs" else a.docs_dir / "nested"
    target = b.root if replaced == "root" else b.docs_dir
    backup = link.with_name(link.name + "-saved")
    # Both paths are test-created children of this isolated projects fixture.
    assert link.is_relative_to(a.root.parent) and backup.is_relative_to(a.root.parent)
    moved = link.exists()
    if moved:
        link.rename(backup)
    try:
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                           check=True, capture_output=True)
        else:
            link.symlink_to(target, target_is_directory=True)
        with pytest.raises(ValueError, match="linked|escaping"):
            deps.load_rule_descriptions(captured)
        with pytest.raises(ValueError, match="linked|escaping"):
            source_files(captured.docs_dir)
    finally:
        if link.is_junction():
            link.rmdir()  # Remove this junction only; preserve B.
        elif link.is_symlink():
            link.unlink()
        if moved:
            backup.rename(link)
    assert (b.docs_dir / "secret.md").read_text(encoding="utf-8") == "`[SECRET]`: B private"


@pytest.mark.parametrize("filename", ["spec.md", "spec.MD"])
def test_legacy_descriptions_accept_markdown_extension_case(projects, filename):
    from dataclasses import replace
    project = replace(projects[0], legacy=True)
    (project.docs_dir / filename).write_text("`[RULE-CASE-01]`: Description", encoding="utf-8")
    assert deps.load_rule_descriptions(project) == {"RULE-CASE-01": "Description"}

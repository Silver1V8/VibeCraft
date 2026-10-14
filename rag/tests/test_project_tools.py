"""Captured CLI/agent targets and real filesystem denial, without providers."""
import asyncio
import os
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from functools import partial
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

import agent_bridge as bridge
import agent_runners as runners
from core import config, indexing, artifacts, writer_lock
from core.projects import ProjectRegistry, _create_project_root


@pytest.fixture
def projects(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "registry")
    monkeypatch.setattr(config, "setup_logging", lambda: None)
    registry = ProjectRegistry(bootstrap_legacy=False)
    # Nomi lunghi: gli ID nascono dal nome, e "B" comparirebbe come lettera in qualunque testo.
    return registry, registry.create("Progetto-Alfa"), registry.create("Progetto-Beta")


@pytest.mark.parametrize("flag,fn,result", [
    ([], "build_graph_and_index", None), (["--incremental"], "incremental_index", None),
    (["--index-status"], "index_status", {}),
    (["--check-integrity"], "check_index_integrity", {"ok": True}),
    (["--check-graph"], "check_graph_consistency", {"consistent": True}),
    (["--check-drift", "feat"], "check_drift", None),
    (["--archive", "feat"], "archive_feature", None),
    (["--migrate-colbert-npy"], "migrate_colbert_npy", "v2"),
])
def test_cli_dispatch_captures_selected_project(projects, monkeypatch, flag, fn, result):
    _, a, b = projects
    calls = []
    module = artifacts if fn == "migrate_colbert_npy" else indexing
    monkeypatch.setattr(module, fn, lambda *args, **kwargs: calls.append(kwargs.get("project")) or result)
    locks = []
    @contextmanager
    def lock(*args, **kwargs):
        locks.append(kwargs.get("project"))
        yield
    monkeypatch.setattr(writer_lock, "writer_lock", lock)
    for selected in (a, b):
        monkeypatch.setattr(sys, "argv", ["index.py", "--project", selected.id, *flag])
        try:
            runpy.run_path(str(Path(bridge.__file__).parent / "index.py"), run_name="__main__")
        except SystemExit as exc:
            assert exc.code == 0
        assert calls[-1] == selected
    assert all(p in (a, b) for p in locks)


def test_cli_absent_flag_ignores_mcp_environment(projects, monkeypatch):
    _, _, b = projects
    monkeypatch.setenv("VIBECRAFT_PROJECT_ID", b.id)
    calls = []
    monkeypatch.setattr(indexing, "index_status", lambda **kwargs: calls.append(kwargs.get("project")) or {})
    monkeypatch.setattr(sys, "argv", ["index.py", "--index-status"])
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(Path(bridge.__file__).parent / "index.py"), run_name="__main__")
    assert error.value.code == 2
    assert calls == []


def test_cli_default_resolves_registered_legacy(projects, monkeypatch):
    registry, _, _ = projects
    target = _create_project_root(registry.projects_dir / "legacy", "legacy", "Initial")
    registry.register(target.root)
    calls = []
    monkeypatch.setattr(indexing, "index_status", lambda **kwargs: calls.append(kwargs.get("project")) or {})
    monkeypatch.setattr(sys, "argv", ["index.py", "--index-status"])
    runpy.run_path(str(Path(bridge.__file__).parent / "index.py"), run_name="__main__")
    assert calls == [target]


def test_root_docs_are_never_an_implicit_corpus(projects, monkeypatch, tmp_path):
    root_docs = tmp_path / "root docs"
    root_docs.mkdir()
    (root_docs / "private.md").write_text("Root-only document")
    monkeypatch.setattr(indexing, "DOCS_DIR", root_docs)
    monkeypatch.setattr(sys, "argv", ["index.py", "--index-status"])
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(Path(bridge.__file__).parent / "index.py"), run_name="__main__")
    assert error.value.code == 2


@pytest.mark.parametrize("flag", ["--rollback", "--archive", "--check-drift"])
def test_cli_empty_operation_cannot_fall_back_to_full_build(projects, monkeypatch, flag):
    _, a, _ = projects
    operations = []
    monkeypatch.setattr(indexing, "build_graph_and_index", lambda **kwargs: operations.append("full"))
    @contextmanager
    def lock(**kwargs):
        yield
    monkeypatch.setattr(writer_lock, "writer_lock", lock)
    monkeypatch.setattr(sys, "argv", ["index.py", "--project", a.id, flag, ""])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(Path(bridge.__file__).parent / "index.py"), run_name="__main__")
    assert exc.value.code == 2
    assert operations == []


def test_mcp_benchmark_http_uses_the_same_captured_project_as_stdio(monkeypatch):
    from types import SimpleNamespace
    from scripts import bench_mcp
    captured = []
    monkeypatch.setenv("VIBECRAFT_PROJECT_ID", "a" * 32)
    class Client:
        def __init__(self, params):
            captured.append(("stdio", params.env["VIBECRAFT_PROJECT_ID"]))
        async def __aenter__(self):
            monkeypatch.setenv("VIBECRAFT_PROJECT_ID", "b" * 32)
            return self
        async def __aexit__(self, *args):
            pass
        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in
                ("vibecraft_retrieve", "vibecraft_code_search", "vibecraft_graph_query")])
        async def call_tool(self, *args):
            return SimpleNamespace(is_error=False, structured_content={"index_version": "v1"})
    class HTTP:
        def __init__(self, **kwargs):
            captured.append(("http", kwargs["headers"].get("X-VibeCraft-Project")))
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, *args, **kwargs):
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"index_version": "v1"})
    monkeypatch.setattr(bench_mcp, "Client", Client)
    monkeypatch.setattr(bench_mcp.httpx, "AsyncClient", HTTP)
    result = asyncio.run(bench_mcp.benchmark(1))
    assert result["index_version"] == "v1"
    assert captured == [("stdio", "a" * 32), ("http", "a" * 32)]


@pytest.mark.parametrize("runner", ["codex", "cursor"])
def test_native_launch_is_denied_for_every_context_before_popen(projects, monkeypatch, runner):
    _, a, b = projects
    legacy = replace(a, id="legacy", legacy=True)
    calls = []
    monkeypatch.setattr(runners, "run_cli", partial(runners.run_cli, popen=lambda *args, **kwargs: calls.append(args)))
    for project in (a, b, legacy, None):
        with pytest.raises(ValueError, match="native_read_isolation_unverified"):
            runners.run_streaming(runner, "p", "suggest", "", project=project)
    with pytest.raises(ValueError, match="native_read_isolation_unverified"):
        list(runners.run_cli(runner, "p", "suggest", "", popen=lambda *args, **kw: calls.append(args)))
    assert calls == []


def test_native_metadata_preserves_export_and_installation(projects, monkeypatch):
    _, a, _ = projects
    monkeypatch.setattr(runners.shutil, "which", lambda name: name)
    monkeypatch.setattr(runners.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(OSError()))
    for metadata in runners.list_runners(project=a):
        if metadata["id"] in ("codex", "cursor"):
            assert metadata["installed"] and metadata["export_available"]
            assert not metadata["available"]
            assert metadata["unavailable_code"] == "native_read_isolation_unverified"


@pytest.mark.parametrize("relative", [".git/config", ".env.local", "secrets/token", "credentials.json", "id_rsa"])
def test_sdk_and_local_deny_reserved_reads_and_writes(projects, relative):
    _, a, _ = projects
    file = a.code_dir / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("PRIVATE")
    for mode in ("suggest", "agentic"):
        opts = bridge._build_agent_options(mode, "sonnet", project=a)
        hook = opts.hooks["PreToolUse"][0].hooks[0]
        for name in ("Read", "Write") if mode == "agentic" else ("Read",):
            denial = asyncio.run(hook({"tool_name": name, "tool_input": {"file_path": str(file)}}, None, {}))
            assert denial["hookSpecificOutput"]["permissionDecision"] == "deny"
            assert str(file) not in str(denial)
    assert runners.execute_tool("read_file", {"path": str(file)}, mode="suggest", project_root=a.root,
                                code_root=a.code_dir).startswith("negato")
    assert runners.execute_tool("write_file", {"path": str(file), "content": "changed"}, mode="agentic",
                                project_root=a.root, code_root=a.code_dir).startswith("negato")
    assert file.read_text() == "PRIVATE"


@pytest.mark.parametrize("ancestor", [".codex", "secrets", "docs", "rag"])
def test_own_absolute_write_ignores_harmless_trusted_root_ancestors(tmp_path, monkeypatch, ancestor):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / ancestor / "registry")
    project = ProjectRegistry(bootstrap_legacy=False).create("A")
    target = project.code_dir / "app.py"
    assert runners.execute_tool("write_file", {"path": str(target), "content": "OWN"}, mode="agentic",
                                project_root=project.root, code_root=project.code_dir).startswith("scritto")
    assert target.read_text() == "OWN"
    denied = project.code_dir / "secrets" / "key.txt"
    assert runners.execute_tool("write_file", {"path": str(denied), "content": "BAD"}, mode="agentic",
                                project_root=project.root, code_root=project.code_dir).startswith("negato")


@pytest.mark.parametrize("raw_default", [False, True])
@pytest.mark.parametrize("manifest", ["missing", "corrupt"])
def test_legacy_foreign_registration_survives_missing_manifest_and_refreshes(projects, tmp_path, monkeypatch,
                                                                           raw_default, manifest):
    registry, a, _ = projects
    legacy = replace(a, id="legacy", legacy=True, root=tmp_path, code_dir=tmp_path / "code")
    legacy.code_dir.mkdir()
    monkeypatch.setattr(bridge, "PROJECT_ROOT", legacy.root)
    monkeypatch.setattr(bridge, "CODE_ROOT", legacy.code_dir)
    modes = deepcopy(bridge.AGENT_MODES)
    modes["suggest"]["cwd"] = legacy.root
    monkeypatch.setattr(bridge, "AGENT_MODES", modes)
    hook = bridge._build_agent_options("suggest", "sonnet", project=None if raw_default else legacy).hooks["PreToolUse"][0].hooks[0]
    foreign = tmp_path / "outside-managed"  # registered inside legacy, outside PROJECTS_DIR
    foreign.mkdir()
    (foreign / "project.yaml").write_text("schema_version: 1\nid: " + "d" * 32 + "\nname: Nested\n")
    registry.register(foreign)
    if manifest == "missing":
        (foreign / "project.yaml").unlink()
    else:
        (foreign / "project.yaml").write_text("broken")
    secret = foreign / "same.txt"
    secret.write_text("FOREIGN")
    denial = asyncio.run(hook({"tool_name": "Read", "tool_input": {"file_path": str(secret)}}, None, {}))
    assert denial["hookSpecificOutput"]["permissionDecision"] == "deny"
    for name in ("Grep", "Glob"):
        denial = asyncio.run(hook({"tool_name": name, "tool_input": {"pattern": "**/*"}}, None, {}))
        assert denial["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert runners.execute_tool("read_file", {"path": str(secret)}, mode="suggest", project_root=legacy.root,
                                code_root=legacy.code_dir).startswith("negato")
    for tool in ("grep", "list_files"):
        result = runners.execute_tool(tool, {"path": ".", "pattern": "FOREIGN" if tool == "grep" else "**/*"},
                                      mode="suggest", project_root=legacy.root, code_root=legacy.code_dir)
        assert "FOREIGN" not in result and str(foreign) not in result


@pytest.mark.parametrize("tool", ["Grep", "Glob"])
def test_sdk_scan_denies_unsafe_descendants_but_keeps_safe_subtree(projects, tool):
    _, a, _ = projects
    safe = a.code_dir / "src"
    safe.mkdir()
    (safe / "app.py").write_text("SAFE")
    (a.code_dir / ".env").write_text("SECRET")
    hook = bridge._build_agent_options("agentic", "sonnet", project=a).hooks["PreToolUse"][0].hooks[0]
    assert asyncio.run(hook({"tool_name": tool, "tool_input": {"pattern": "**/*"}}, None, {}))["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert asyncio.run(hook({"tool_name": tool, "tool_input": {"path": "src", "pattern": "**/*"}}, None, {})) == {}


def test_readonly_registry_never_bootstraps_and_detects_deletion(projects, tmp_path):
    registry, _, _ = projects
    absent = tmp_path / "absent"
    assert ProjectRegistry(absent, readonly=True).records() == []
    assert not absent.exists()
    view = ProjectRegistry(registry.projects_dir, readonly=True)
    assert view.records()
    registry.registry_path.unlink()
    with pytest.raises(Exception, match="registry"):
        view.records()


def test_readonly_view_cannot_create_or_register(projects, tmp_path):
    registry, a, _ = projects
    view = ProjectRegistry(registry.projects_dir, readonly=True)
    before = registry.registry_path.read_bytes(), registry.registry_path.stat().st_mtime_ns
    entries = set(registry.projects_dir.iterdir())
    for call in (lambda: view.create("C"), lambda: view.register(a.root)):
        with pytest.raises(Exception, match="[Rr]ead"):
            call()
    assert (registry.registry_path.read_bytes(), registry.registry_path.stat().st_mtime_ns) == before
    assert set(registry.projects_dir.iterdir()) == entries


@pytest.mark.parametrize("runner", ["codex", "cursor"])
def test_http_native_run_rejects_but_external_prompt_remains_available(projects, monkeypatch, runner):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import deps, routes_pipeline
    registry, a, b = projects
    monkeypatch.setattr(deps, "project_registry", lambda: registry)
    monkeypatch.setattr(deps, "ROLE", "writer")
    monkeypatch.setattr(deps, "API_KEY", "synthetic-task5")
    monkeypatch.setattr(runners.shutil, "which", lambda name: None)
    monkeypatch.setattr(runners.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(OSError()))
    calls = []
    monkeypatch.setattr(routes_pipeline, "run_agent_streaming", lambda *args, **kwargs: calls.append(args))
    app = FastAPI()
    app.include_router(routes_pipeline.router)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        for selected, other in ((a, b), (b, a)):
            folder = selected.changes_dir / "same"
            folder.mkdir()
            (selected.code_dir / "backend").mkdir()
            headers = {"X-VibeCraft-Project": selected.id, "X-API-Key": "synthetic-task5"}
            metadata = client.get("/api/pipeline/agent/runners", headers=headers)
            assert metadata.status_code == 200
            native = next(r for r in metadata.json()["runners"] if r["id"] == runner)
            assert not native["installed"] and not native["available"] and native["export_available"]
            run = client.post("/api/pipeline/agent/run", headers=headers,
                              json={"runner": runner, "mode": "suggest", "prompt": "p"})
            assert run.status_code == 400
            assert run.json()["detail"]["code"] == "native_read_isolation_unverified"
            assert calls == []
            prompt = client.get("/api/pipeline/final-prompt", headers=headers,
                params={"feature": "same", "dev_type": "backend", "consumer": "external", "runner": runner, "mode": "suggest"})
            assert prompt.status_code == 200, prompt.text
            assert selected.id in prompt.json()["final_prompt"] and other.id not in prompt.json()["final_prompt"]
            unauth = client.post("/api/pipeline/agent/run", headers={"X-VibeCraft-Project": selected.id},
                json={"runner": runner, "mode": "suggest", "prompt": "p"})
            assert unauth.status_code == 401


def test_benchmark_join_uses_admitted_legacy_manager(projects, tmp_path, monkeypatch):
    from api import deps, routes_reindex
    from scripts import bench_delta
    registry = ProjectRegistry(tmp_path / "legacy-registry", bootstrap_legacy=False)
    legacy = _create_project_root(registry.projects_dir / "legacy", "legacy", "Initial")
    registry.register(legacy.root)
    (legacy.code_dir / "app.py").write_text("data")
    monkeypatch.setattr(deps, "project_registry", lambda: registry)
    contexts = []
    class Manager:
        def join_all(self, timeout):
            return True
    def manager(project):
        contexts.append(project)
        return Manager()
    monkeypatch.setattr(routes_reindex, "project_manager", manager)
    bench_delta._join_writer()
    assert contexts == [legacy]


def test_junction_file_and_ancestor_denied_before_read_write_or_scan(projects):
    _, a, b = projects
    (b.code_dir / "same.txt").write_text("FOREIGN")
    hook = bridge._build_agent_options("agentic", "sonnet", project=a).hooks["PreToolUse"][0].hooks[0]
    linked = a.code_dir / "linked"
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(linked), str(b.code_dir)], check=True, capture_output=True)
    else:
        linked.symlink_to(b.code_dir, target_is_directory=True)
    for tool, field in (("Read", "file_path"), ("Write", "file_path"), ("Grep", "path"), ("Glob", "path")):
        path = linked if field == "path" else linked / "same.txt"
        assert asyncio.run(hook({"tool_name": tool, "tool_input": {field: str(path)}}, None, {}))["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert runners.execute_tool("read_file", {"path": str(linked / "same.txt")}, mode="suggest",
                                project_root=a.root, code_root=a.code_dir).startswith("negato")
    assert runners.execute_tool("write_file", {"path": "linked/same.txt", "content": "BAD"}, mode="agentic",
                                project_root=a.root, code_root=a.code_dir).startswith("negato")
    assert "FOREIGN" not in runners.execute_tool("grep", {"path": ".", "pattern": "FOREIGN"}, mode="agentic",
                                                project_root=a.root, code_root=a.code_dir)
    assert (b.code_dir / "same.txt").read_text() == "FOREIGN"


def test_glob_absolute_pattern_is_denied_even_with_file_base(projects):
    _, a, b = projects
    safe = a.code_dir / "app.py"
    safe.write_text("SAFE")
    hook = bridge._build_agent_options("agentic", "sonnet", project=a).hooks["PreToolUse"][0].hooks[0]
    for base in (str(safe), "."):
        for pattern in (str(b.code_dir / "*"), "../*/code/*"):
            result = asyncio.run(hook({"tool_name": "Glob", "tool_input": {"path": base, "pattern": pattern}}, None, {}))
            assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("replacement", ["root", "code", "ancestor"])
def test_captured_sdk_guard_denies_replaced_roots_and_ancestors(projects, replacement):
    _, a, b = projects
    hook = bridge._build_agent_options("agentic", "sonnet", project=a).hooks["PreToolUse"][0].hooks[0]
    (b.code_dir / "same.txt").write_text("FOREIGN")
    if replacement == "root":
        replaced, destination = a.root, b.root
    elif replacement == "code":
        replaced, destination = a.code_dir, b.code_dir
    else:
        replaced, destination = a.code_dir / "sub", b.code_dir
        replaced.mkdir()
    replaced.rename(replaced.with_name(replaced.name + "-retained"))
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(replaced), str(destination)], check=True, capture_output=True)
    else:
        replaced.symlink_to(destination, target_is_directory=True)
    relative = "sub/same.txt" if replacement == "ancestor" else "same.txt"
    for name in ("Read", "Write"):
        result = asyncio.run(hook({"tool_name": name, "tool_input": {"file_path": relative}}, None, {}))
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert str(b.root) not in str(result)
    assert (b.code_dir / "same.txt").read_text() == "FOREIGN"


def test_file_symlink_is_never_read_listed_or_grepped(projects):
    _, a, b = projects
    foreign = b.code_dir / "private.txt"
    foreign.write_text("FOREIGN_FILE")
    link = a.code_dir / "public.txt"
    try:
        os.symlink(foreign, link)
    except OSError as exc:
        if sys.platform == "win32" and exc.winerror == 1314:
            pytest.skip("Windows file symlinks require unavailable privilege; run this case on Linux")
        raise
    hook = bridge._build_agent_options("agentic", "sonnet", project=a).hooks["PreToolUse"][0].hooks[0]
    for name, field in (("Read", "file_path"), ("Grep", "path"), ("Glob", "path"), ("Write", "file_path")):
        result = asyncio.run(hook({"tool_name": name, "tool_input": {field: str(link), "pattern": ".*"}}, None, {}))
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    for name in ("read_file", "grep", "list_files"):
        result = runners.execute_tool(name, {"path": str(link), "pattern": ".*"}, mode="suggest",
                                      project_root=a.root, code_root=a.code_dir)
        assert result.startswith("negato") and "FOREIGN_FILE" not in result
    assert "public.txt" not in runners.execute_tool("list_files", {"path": ".", "pattern": "**/*"},
        mode="agentic", project_root=a.root, code_root=a.code_dir)
    assert "FOREIGN_FILE" not in runners.execute_tool("grep", {"path": ".", "pattern": "FOREIGN"},
        mode="agentic", project_root=a.root, code_root=a.code_dir)


def test_tilde_and_rooted_glob_patterns_cannot_expand_outside_project(projects):
    _, a, _ = projects
    hook = bridge._build_agent_options("agentic", "sonnet", project=a).hooks["PreToolUse"][0].hooks[0]
    for pattern in (("\\outside\\*", "~/outside/*") if sys.platform == "win32" else ("/outside/*", "~/outside/*")):
        result = asyncio.run(hook({"tool_name": "Glob", "tool_input": {"pattern": pattern}}, None, {}))
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    result = asyncio.run(hook({"tool_name": "Read", "tool_input": {"file_path": "~/outside.txt"}}, None, {}))
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("damage", ["corrupt", "deleted"])
def test_captured_read_guard_fails_closed_when_registry_breaks(projects, damage):
    registry, a, _ = projects
    file = a.code_dir / "app.py"
    file.write_text("SAFE")
    hook = bridge._build_agent_options("agentic", "sonnet", project=a).hooks["PreToolUse"][0].hooks[0]
    data = {"tool_name": "Read", "tool_input": {"file_path": "app.py"}}
    assert asyncio.run(hook(data, None, {})) == {}
    if damage == "deleted":
        registry.registry_path.unlink()
    else:
        registry.registry_path.write_text("broken")
    assert asyncio.run(hook(data, None, {}))["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_cli_rollback_captures_every_stage_and_project_lock(projects, monkeypatch):
    import qdrant_client
    _, a, b = projects
    observed = []
    for module, name, result in (
        (artifacts, "resolve_rollback_target", "v1"), (artifacts, "rollback_version", "v1"),
        (artifacts, "list_versions", ["v1"]),
        (indexing, "assert_rollback_target_has_vectors", None),
        (indexing, "rollback_shares_collection_with_later_versions", []),
        (indexing, "rollback_qdrant_alias_if_needed", {"state": "noop"}),
    ):
        def stage(*args, _name=name, _result=result, **kwargs):
            observed.append((_name, kwargs.get("project")))
            return _result
        monkeypatch.setattr(module, name, stage)
    @contextmanager
    def lock(*args, **kwargs):
        observed.append(("lock", kwargs.get("project")))
        yield
    monkeypatch.setattr(writer_lock, "writer_lock", lock)
    monkeypatch.setattr(qdrant_client, "QdrantClient", lambda **kwargs: object())
    for selected in (a, b):
        observed.clear()
        monkeypatch.setattr(sys, "argv", ["index.py", "--project", selected.id, "--rollback"])
        runpy.run_path(str(Path(bridge.__file__).parent / "index.py"), run_name="__main__")
        assert [name for name, _ in observed] == ["lock", "resolve_rollback_target", "assert_rollback_target_has_vectors",
            "rollback_version", "list_versions", "rollback_shares_collection_with_later_versions", "rollback_qdrant_alias_if_needed"]
        assert all(project == selected for _, project in observed)


def test_cli_rollback_still_locks_when_read_flag_is_also_present(projects, monkeypatch):
    import qdrant_client
    _, a, _ = projects
    monkeypatch.setattr(qdrant_client, "QdrantClient", lambda **kwargs: object())
    operations = []
    @contextmanager
    def lock(**kwargs):
        assert kwargs["project"] == a
        raise writer_lock.WriterLockBusyError("busy")
        yield
    monkeypatch.setattr(writer_lock, "writer_lock", lock)
    monkeypatch.setattr(artifacts, "resolve_rollback_target", lambda *args, **kwargs: operations.append("rollback"))
    monkeypatch.setattr(sys, "argv", ["index.py", "--project", a.id, "--rollback", "--index-status"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(Path(bridge.__file__).parent / "index.py"), run_name="__main__")
    assert exc.value.code == 2
    assert operations == []


def test_real_delta_plan_defers_shared_model_until_content_changes(tmp_path, monkeypatch):
    from api import routes_reindex
    from test_incremental_indexing import _wire_tmp_index, StatefulFakeQdrant, StubEmbed, _spec
    docs, _ = _wire_tmp_index(monkeypatch, tmp_path)
    source = docs / "spec.md"
    source.write_text(_spec("ALPHA"), encoding="utf-8")
    qdrant = StatefulFakeQdrant()
    indexing.incremental_index(qdrant=qdrant, embed_model=StubEmbed())
    monkeypatch.setitem(routes_reindex.state, "qdrant", qdrant)
    monkeypatch.setitem(routes_reindex.state, "embed_model", None)
    initialized = []
    def resources(*, embedding=True):
        if embedding and routes_reindex.state.get("embed_model") is None:
            initialized.append(True)
            routes_reindex.state["embed_model"] = StubEmbed()
    monkeypatch.setattr(routes_reindex, "ensure_shared_resources", resources)
    monkeypatch.setattr(routes_reindex, "current_version", lambda project=None: None)
    monkeypatch.setattr(routes_reindex, "_graph_version", lambda project=None: None)
    monkeypatch.setattr(routes_reindex, "current_snapshot", lambda project=None: None)
    assert routes_reindex._run_reindex(None)["noop"]
    assert initialized == []
    for marker in ("BETA", "GAMMA"):
        source.write_text(_spec(marker), encoding="utf-8")
        assert routes_reindex._run_reindex(None).get("noop") is not True
    assert initialized == [True]
    monkeypatch.setitem(routes_reindex.state, "embed_model", None)
    source.unlink()
    assert routes_reindex._run_reindex(None).get("noop") is not True
    assert initialized == [True]  # legacy delete-only never needs an embedding model


def test_default_registry_initial_project_keeps_ordinary_tools_usable(tmp_path, monkeypatch):
    for name, path in (("PROJECT_ROOT", tmp_path), ("CODE_DIR", tmp_path / "code"),
                       ("DOCS_DIR", tmp_path / "docs"), ("CHANGES_DIR", tmp_path / "changes"),
                       ("DATABASE_DIR", tmp_path / "database"),
                       ("INTAKE_STAGING_DIR", tmp_path / "staging"),
                       ("PROJECTS_DIR", tmp_path / "projects")):
        monkeypatch.setattr(config, name, path)
    config.CODE_DIR.mkdir()
    config.DOCS_DIR.mkdir()
    (config.DOCS_DIR / "baseline.md").write_text("Baseline")
    registry = ProjectRegistry()
    assert registry.get("legacy").root == tmp_path / "projects" / "legacy"
    a, b = registry.create("A"), registry.create("B")
    for project in (a, b):
        safe = project.code_dir / "src"
        safe.mkdir()
        target = safe / "app.py"
        target.write_text("OWN")
        kwargs = {"mode": "agentic", "project_root": project.root, "code_root": project.code_dir}
        assert "OWN" in runners.execute_tool("read_file", {"path": str(target)}, **kwargs)
        assert runners.execute_tool("write_file", {"path": str(target), "content": "UPDATED"}, **kwargs).startswith("scritto")
        hook = bridge._build_agent_options("agentic", "sonnet", project=project).hooks["PreToolUse"][0].hooks[0]
        for name, data in (("Read", {"file_path": "src/app.py"}),
                           ("Write", {"file_path": "src/app.py"}),
                           ("Grep", {"path": "src", "pattern": "UPDATED"}),
                           ("Glob", {"path": "src", "pattern": "**/*"})):
            assert asyncio.run(hook({"tool_name": name, "tool_input": data}, None, {})) == {}
        assert "app.py" in runners.execute_tool("list_files", {"path": "src", "pattern": "**/*"}, **kwargs)
        assert "UPDATED" in runners.execute_tool("grep", {"path": "src", "pattern": "UPDATED"}, **kwargs)
        legacy = registry.get("legacy")
        assert runners.execute_tool("read_file", {"path": str(target)}, mode="suggest",
                                    project_root=legacy.root, code_root=legacy.code_dir).startswith("negato")


def test_ordinary_delta_factory_supplies_full_candidate_model(projects, monkeypatch):
    _, a, _ = projects
    (a.docs_dir / "spec.md").write_text("CONTENT")
    model = object()
    calls = []
    def factory():
        calls.append("factory")
        return model
    def build(qdrant, embed_model, emit, *, collector, project):
        assert project == a and embed_model is model
        calls.append("build")
        collector.update(counts={"docs_added": 1, "chunks_indexed": 1},
                         phase_timings_seconds={"init_model": 0.0})
        return "v1"
    monkeypatch.setattr(indexing, "build_graph_and_index", build)
    result = indexing.incremental_index(qdrant=object(), project=a, embed_model_factory=factory)
    assert calls == ["factory", "build"] and result["version"] == "v1"
    assert result["phase_timings_seconds"]["init_model"] >= 0
    calls.clear()
    indexing.incremental_index(qdrant=object(), embed_model=model, project=a, embed_model_factory=factory)
    assert calls == ["build"]


def test_real_git_checkout_keeps_safe_code_tools_and_denies_git_reads(projects):
    _, a, _ = projects
    subprocess.run(["git", "init", "--quiet", str(a.code_dir)], check=True, capture_output=True)
    safe = a.code_dir / "src"
    safe.mkdir()
    target = safe / "app.py"
    target.write_text("LEGITIMATE_CODE")
    hook = bridge._build_agent_options("agentic", "sonnet", project=a).hooks["PreToolUse"][0].hooks[0]
    for name, data in (("Read", {"file_path": "src/app.py"}),
                       ("Grep", {"path": "src", "pattern": "LEGITIMATE_CODE"}),
                       ("Glob", {"path": "src", "pattern": "**/*"})):
        assert asyncio.run(hook({"tool_name": name, "tool_input": data}, None, {})) == {}
    for name, data in (("Read", {"file_path": ".git/config"}),
                       ("Grep", {"pattern": "LEGITIMATE_CODE"}),
                       ("Glob", {"pattern": "**/*"})):
        denial = asyncio.run(hook({"tool_name": name, "tool_input": data}, None, {}))
        assert denial["hookSpecificOutput"]["permissionDecision"] == "deny"
    kwargs = {"mode": "agentic", "project_root": a.root, "code_root": a.code_dir}
    assert "LEGITIMATE_CODE" in runners.execute_tool("read_file", {"path": "src/app.py"}, **kwargs)
    assert "LEGITIMATE_CODE" in runners.execute_tool("grep", {"pattern": "LEGITIMATE_CODE"}, **kwargs)
    assert ".git" not in runners.execute_tool("list_files", {"pattern": "**/*"}, **kwargs)
    assert runners.execute_tool("read_file", {"path": ".git/config"}, **kwargs).startswith("negato")


def test_cli_subprocess_without_registered_default_never_builds_root(tmp_path):
    env = dict(os.environ, VIBECRAFT_PROJECTS_DIR=str(tmp_path / 'managed'),
               VIBECRAFT_PROJECT_ID='b' * 32, PYTHONUTF8='1')
    result = subprocess.run([sys.executable, str(Path(bridge.__file__).parent / 'index.py')],
                            env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert result.returncode == 2 and 'project_required' in result.stderr
    assert not (tmp_path / 'managed').exists()


@pytest.mark.parametrize('name', ['nightly_consistency', 'weekly_consistency'])
@pytest.mark.parametrize('extension', ['ps1', 'sh'])
def test_maintenance_scripts_select_same_project_for_cli_and_http(name, extension):
    path = Path(bridge.__file__).parent / 'scripts' / (name + '.' + extension)
    text = path.read_text(encoding='utf-8')
    assert 'VIBECRAFT_PROJECT_ID' in text and 'X-VibeCraft-Project' in text
    commands = [line for line in text.splitlines() if 'uv run python index.py' in line and not line.lstrip().startswith('#')]
    assert commands and all('--project' in line for line in commands)


def test_eval_cli_measures_only_selected_project(projects, monkeypatch):
    from eval import run
    _, a, _ = projects
    golden = a.root / 'eval' / 'golden.yaml'
    golden.parent.mkdir()
    golden.write_text('cases:\n  - q: Own question\n    expected: [own.md]\n')
    seen = []
    class Client:
        def __init__(self, **kwargs):
            seen.append(kwargs['headers']['X-VibeCraft-Project'])
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url, **kwargs):
            assert kwargs['params']['q'] == 'Own question'
            class Response:
                def raise_for_status(self):
                    pass
                def json(self):
                    return {'results': [{'file': 'own.md', 'chunk_id': 'own.md#0', 'text': 'Own answer'}]}
            return Response()
    monkeypatch.setattr(run.httpx2, 'Client', Client)
    monkeypatch.setattr(sys, 'argv', ['eval.run', '--project', a.id])
    assert run.main() == 0
    assert seen == [a.id]
    assert list((a.database_dir / 'eval').glob('eval_*.json'))
    assert (a.database_dir / 'eval' / 'history.jsonl').is_file()


@pytest.mark.parametrize('module,filename', [('run', 'golden.yaml'), ('run_multihop', 'golden_multihop.yaml')])
@pytest.mark.parametrize('empty', [False, True])
def test_eval_cli_without_cases_is_not_success(projects, monkeypatch, capsys, module, filename, empty):
    from importlib import import_module
    cli = import_module('eval.' + module)
    _, a, _ = projects
    if empty:
        golden = a.root / 'eval' / filename
        golden.parent.mkdir()
        golden.write_text('cases: []\n')
    monkeypatch.setattr(sys, 'argv', ['eval.' + module, '--project', a.id])
    monkeypatch.setattr(cli.httpx2, 'Client', lambda **kw: pytest.fail('empty suite contacted server'))
    assert cli.main() == 3
    assert 'not evaluated' in capsys.readouterr().out
    assert not list((a.database_dir / 'eval').glob('*'))

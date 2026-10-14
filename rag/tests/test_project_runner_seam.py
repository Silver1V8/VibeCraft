"""Bounded runner seam: real options, tool files and MCP transport; no providers."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from functools import partial
import json
from pathlib import Path
import threading

import httpx
import pytest
from mcp import Client
from claude_agent_sdk.types import ResultMessage

import agent_bridge as bridge
import agent_runners as runners
from core.projects import ProjectRegistry
from mcp_server import create_server


@pytest.fixture
def projects(tmp_path):
    registry = ProjectRegistry(tmp_path / "external projects", bootstrap_legacy=False)
    return [registry.create(name) for name in ("A", "B")]


@pytest.fixture
def tracking(monkeypatch):
    from core import pipeline_activity
    seen = []

    @contextmanager
    def track(feature, attempt_id, *, project=None):
        seen.append((feature, attempt_id, project.id if project else None))
        yield attempt_id

    monkeypatch.setattr(pipeline_activity, "track", track)
    return seen


def test_sdk_options_cwd_hook_mcp_and_modes_are_project_local(projects):
    a, b = projects
    original = deepcopy(bridge.AGENT_MODES)
    with ThreadPoolExecutor(2) as pool:
        options = list(pool.map(lambda p: bridge._build_agent_options("agentic", "sonnet", project=p), projects))
    for project, other, opts in ((a, b, options[0]), (b, a, options[1])):
        assert Path(opts.cwd) == project.code_dir
        mcp = opts.mcp_servers["vibecraft"]
        assert Path(mcp["args"][1]) == Path(bridge.__file__).resolve().parent / "mcp_server.py"
        assert mcp["env"]["VIBECRAFT_PROJECT_ID"] == project.id
        hook = opts.hooks["PreToolUse"][0].hooks[0]
        own = {"tool_name": "Write", "tool_input": {"file_path": str(project.code_dir / "same.py")}}
        foreign = {"tool_name": "Write", "tool_input": {"file_path": str(other.code_dir / "same.py")}}
        assert asyncio.run(hook(own, None, {})) == {}
        assert asyncio.run(hook(foreign, None, {}))["hookSpecificOutput"]["permissionDecision"] == "deny"
        for mode in ("suggest", "oneshot"):
            assert Path(bridge._build_agent_options(mode, "sonnet", project=project).cwd) == project.root
    options[0].disallowed_tools.append("TEST-ONLY")
    assert "TEST-ONLY" not in options[1].disallowed_tools
    assert bridge.AGENT_MODES == original


def test_sdk_streaming_forwards_captured_project_to_options_and_tracking(projects, monkeypatch, tracking):
    by_id = {p.id: p for p in projects}
    seen = []

    async def query(*, prompt, options):
        project = by_id[options.mcp_servers["vibecraft"]["env"]["VIBECRAFT_PROJECT_ID"]]
        seen.append(project.id)
        assert Path(options.cwd) == project.root
        await asyncio.sleep(0.01)
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                            num_turns=1, session_id=project.id, result='{"open_points":[]}')

    monkeypatch.setattr(bridge, "query", query)
    def run(project):
        return [json.loads(line) for line in runners.run_streaming("claude", "prompt", "suggest", "sonnet",
                    feature="same", attempt_id=project.id, project=project)]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(run, projects))
    assert all(events[-1]["type"] == "result" and not events[-1]["is_error"] for events in results)
    assert sorted(seen) == sorted(by_id)
    assert {project_id for _, _, project_id in tracking} == set(by_id)


def test_local_streaming_writes_same_filename_only_in_captured_project(projects, monkeypatch, tracking):
    by_name = {p.name: p for p in projects}
    barrier = threading.Barrier(2)

    def chat(model, messages, tools):
        project = by_name[messages[1]["content"]]
        if len(messages) == 2:
            barrier.wait(timeout=5)
            assert str(project.code_dir) in messages[0]["content"]
            return {"message": {"tool_calls": [{"function": {"name": "write_file",
                "arguments": {"path": "same.txt", "content": project.name}}}]}}
        assert messages[-1]["content"].startswith("scritto")
        return {"message": {"content": '{"open_points":[]}'}}

    monkeypatch.setattr(runners, "run_local", partial(runners.run_local, chat=chat))
    def run(project):
        return [json.loads(line) for line in runners.run_streaming("local", project.name, "agentic", "fake",
                    feature="same", attempt_id=project.id, project=project)]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(run, projects))
    assert all(events[-1]["type"] == "result" for events in results)
    for project in projects:
        assert (project.code_dir / "same.txt").read_text(encoding="utf-8") == project.name
    assert {item[2] for item in tracking} == {p.id for p in projects}


@pytest.mark.parametrize("runner", ["codex", "cursor"])
def test_cli_command_helper_keeps_external_project_root(projects, monkeypatch, runner):
    monkeypatch.setattr(runners.shutil, "which", lambda name: name)
    for project in projects:
        argv = runners.cli_command(runner, "", project.root, project.database_dir / "last.txt")
        flag = "-C" if runner == "codex" else "--workspace"
        assert Path(argv[argv.index(flag) + 1]) == project.root
        assert "private prompt" not in argv
        if runner == "codex":
            assert argv[-1] == "-"


def test_mcp_project_header_is_fixed_for_all_transport_calls(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"ok": True})
    servers = []
    for project_id in ("a" * 32, "b" * 32, "legacy", None):
        if project_id is None:
            monkeypatch.delenv("VIBECRAFT_PROJECT_ID", raising=False)
        else:
            monkeypatch.setenv("VIBECRAFT_PROJECT_ID", project_id)
        servers.append((project_id, create_server(transport=httpx.MockTransport(handler))))
    monkeypatch.setenv("VIBECRAFT_PROJECT_ID", "c" * 32)

    async def run():
        for project_id, server in servers:
            async with Client(server) as client:
                for tool in ("vibecraft_retrieve", "vibecraft_code_search", "vibecraft_graph_query"):
                    result = await client.call_tool(tool, {"params": {"q": "same"}})
                    assert not result.is_error
                    assert calls[-1].headers.get("X-VibeCraft-Project") == project_id
    asyncio.run(run())
    assert len(calls) == 12


@pytest.mark.parametrize("project_id", ["", "../escape", "a_b", "-a", "a/b", "x" * 65, "legacy\n"])
def test_mcp_invalid_project_id_fails_before_transport(monkeypatch, project_id):
    monkeypatch.setenv("VIBECRAFT_PROJECT_ID", project_id)
    with pytest.raises(ValueError, match="VIBECRAFT_PROJECT_ID"):
        create_server(transport=httpx.MockTransport(lambda request: pytest.fail("transport reached")))


def test_sdk_mcp_launch_uses_install_script_and_fixed_project_over_real_stdio(projects):
    import os
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from mcp.client.stdio import StdioServerParameters
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path, self.headers.get("X-VibeCraft-Project"), self.headers.get("X-API-Key")))
            payload = json.dumps({"project": self.headers.get("X-VibeCraft-Project")}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()

    async def session(project):
        config = bridge._build_agent_options("suggest", "sonnet", project=project).mcp_servers["vibecraft"]
        env = {**os.environ, "VIBECRAFT_PROJECT_ID": "f" * 32,
               "VIBECRAFT_MCP_BACKEND_URL": f"http://127.0.0.1:{http.server_port}",
               "VIBECRAFT_API_KEY": "synthetic-seam-key", **config["env"]}
        params = StdioServerParameters(command=config["command"], args=config["args"], env=env)
        async with Client(params) as client:
            for tool in ("vibecraft_retrieve", "vibecraft_code_search", "vibecraft_graph_query"):
                result = await client.call_tool(tool, {"params": {"q": "same"}})
                assert not result.is_error
                assert result.structured_content["project"] == (project.id if project else "legacy")

    async def run():
        await asyncio.gather(*(session(project) for project in [*projects, None]))

    try:
        asyncio.run(run())
    finally:
        http.shutdown()
        thread.join(timeout=5)
        http.server_close()
    assert len(calls) == 9
    assert {project_id for _, project_id, _ in calls} == {projects[0].id, projects[1].id, "legacy"}
    assert all(key == "synthetic-seam-key" for _, _, key in calls)


@pytest.mark.parametrize("runner", ["local", "claude"])
def test_streaming_activity_uses_real_project_registry_until_completion(projects, monkeypatch, runner):
    from core import pipeline_activity
    a, b = projects
    started = {p.id: threading.Event() for p in projects}
    release = {p.id: threading.Event() for p in projects}

    def chat(model, messages, tools):
        project_id = messages[1]["content"]
        started[project_id].set()
        assert release[project_id].wait(timeout=10)
        return {"message": {"content": '{"open_points":[]}'}}

    async def query(*, prompt, options):
        project_id = options.mcp_servers["vibecraft"]["env"]["VIBECRAFT_PROJECT_ID"]
        started[project_id].set()
        assert await asyncio.to_thread(release[project_id].wait, 10)
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                            num_turns=1, session_id=project_id, result='{"open_points":[]}')

    monkeypatch.setattr(runners, "run_local", partial(runners.run_local, chat=chat))
    monkeypatch.setattr(bridge, "query", query)
    streams = []
    try:
        for project in projects:
            streams.append(runners.run_streaming(runner, project.id, "suggest", "sonnet",
                feature="same", attempt_id=project.id, project=project))
        assert all(event.wait(timeout=5) for event in started.values())
        assert pipeline_activity.snapshot("same", project=a)[0] == [a.id]
        assert pipeline_activity.snapshot("same", project=b)[0] == [b.id]
        assert pipeline_activity.snapshot("same")[0] == []
        release[a.id].set()
        assert json.loads(list(streams[0])[-1])["type"] == "result"
        assert pipeline_activity.snapshot("same", project=a)[0] == []
        assert pipeline_activity.snapshot("same", project=b)[0] == [b.id]
        release[b.id].set()
        assert json.loads(list(streams[1])[-1])["type"] == "result"
        assert pipeline_activity.snapshot("same", project=b)[0] == []
    finally:
        for event in release.values():
            event.set()
        for stream in streams:
            list(stream)

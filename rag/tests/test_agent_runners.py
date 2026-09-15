"""Runner alternativi a Claude (agent_runners.py): perimetro dei tool del LLM locale,
loop di tool, comando e parsing delle CLI esterne, streaming NDJSON con on_finish.
Nessun Ollama né CLI reali: chat e popen sono iniettati."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import agent_runners as ar


@pytest.fixture
def project(tmp_path):
    (tmp_path / "code").mkdir()
    (tmp_path / "rag").mkdir()
    (tmp_path / "rag" / "cfg.yaml").write_text("x")
    (tmp_path / ".env").write_text("SECRET=1")
    return tmp_path


def tool(project, name, args, mode="agentic"):
    return ar.execute_tool(name, args, mode=mode, project_root=project, code_root=project / "code")


def test_validate_run():
    assert ar.validate_run("local", "agentic", "qwen3.5:9b") is None
    assert ar.validate_run("claude", "suggest", "sonnet") is None
    assert ar.validate_run("codex", "agentic", "") is not None  # agentic solo claude/local
    assert ar.validate_run("cursor", "suggest", "--force") is not None
    assert ar.validate_run("nope", "suggest", "") is not None


@pytest.mark.parametrize("path", ["../rag/cfg.yaml", "rag/x.py", "../../evil.txt", str(Path("/evil.txt").resolve())])
def test_local_write_outside_code_is_denied(project, path):
    assert tool(project, "write_file", {"path": path, "content": "pwned"}).startswith("negato")
    assert tool(project, "edit_file", {"path": path, "old": "x", "new": "pwned"}).startswith("negato")
    assert (project / "rag" / "cfg.yaml").read_text() == "x"


def test_local_write_and_edit_inside_code(project):
    assert tool(project, "write_file", {"path": "app/main.py", "content": "a = 1\n"}).startswith("scritto")
    assert tool(project, "edit_file", {"path": "app/main.py", "old": "a = 1", "new": "a = 2"}).startswith("modificato")
    assert (project / "code" / "app" / "main.py").read_text() == "a = 2\n"


def test_suggest_has_no_write_tools(project):
    assert tool(project, "write_file", {"path": "a.txt", "content": "x"}, mode="suggest").startswith("negato")
    assert not (project / "a.txt").exists()


@pytest.mark.parametrize("path", ["../outside.txt", ".env", ".git/config"])
def test_local_reads_stay_inside_project(project, path):
    assert tool(project, "read_file", {"path": path}, mode="suggest").startswith("negato")


def test_list_and_grep_skip_env(project):
    assert ".env" not in tool(project, "list_files", {"path": ".", "pattern": "*"}, mode="suggest")
    assert "SECRET" not in tool(project, "grep", {"path": ".", "pattern": "SECRET"}, mode="suggest")
    assert "cfg.yaml" in tool(project, "list_files", {"path": ".", "pattern": "**/*"}, mode="suggest")


def test_local_loop_feeds_denials_back_and_reports(project, monkeypatch):
    monkeypatch.setenv("VIBECRAFT_AGENT_MAX_TURNS", "5")
    replies = iter([
        {"message": {"content": "", "tool_calls": [{"function": {
            "name": "write_file", "arguments": {"path": "../rag/cfg.yaml", "content": "pwned"}}}]}},
        {"message": {"content": '{"open_points":[]}'}},
    ])
    sent = []

    def chat(model, messages, tools):
        sent.append(messages[-1])
        return next(replies)

    events = list(ar.run_local("p", "agentic", "m", chat=chat, project_root=project, code_root=project / "code"))
    assert [e["type"] for e in events] == ["tool_use", "text", "result"]
    assert sent[1]["role"] == "tool" and sent[1]["content"].startswith("negato")
    assert (project / "rag" / "cfg.yaml").read_text() == "x"
    assert events[-1]["open_points_status"] == "valid"


def test_local_loop_stops_at_turn_limit(project, monkeypatch):
    monkeypatch.setenv("VIBECRAFT_AGENT_MAX_TURNS", "2")

    def chat(*_):
        return {"message": {"content": "", "tool_calls": [{"function": {"name": "list_files", "arguments": "{}"}}]}}

    events = list(ar.run_local("p", "suggest", "m", chat=chat, project_root=project, code_root=project / "code"))
    assert events[-1]["type"] == "error"


def test_local_oneshot_sends_no_tools(project):
    seen = []

    def chat(model, messages, tools):
        seen.append(tools)
        return {"message": {"content": "ok"}}

    list(ar.run_local("p", "oneshot", "m", chat=chat, project_root=project, code_root=project / "code"))
    assert seen == [[]]


def test_cli_commands_are_read_only_and_keep_prompt_off_argv(monkeypatch, tmp_path):
    monkeypatch.setattr(ar.shutil, "which", lambda b: f"C:/bin/{b}.cmd")
    codex = ar.cli_command("codex", "gpt-5", tmp_path, tmp_path / "last.txt")
    assert codex[1] == "exec" and codex[codex.index("--sandbox") + 1] == "read-only" and codex[-1] == "-"
    cursor = ar.cli_command("cursor", "", tmp_path, tmp_path / "last.txt")
    assert "--force" not in cursor and "--yolo" not in cursor


def test_cli_missing_binary_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(ar.shutil, "which", lambda b: None)
    with pytest.raises(RuntimeError, match="PATH"):
        ar.cli_command("codex", "", tmp_path, tmp_path / "l")


class FakeProc:
    def __init__(self, lines, code=0):
        self.stdin, self.stdout, self.code = MagicMock(), iter(lines), code

    def wait(self):
        return self.code

    def poll(self):
        return self.code

    def kill(self):
        pass


def _run_cli(monkeypatch, tmp_path, runner, events, code=0):
    monkeypatch.setattr(ar.shutil, "which", lambda b: b)
    seen = {}

    def popen(cmd, **kwargs):
        seen["cmd"], seen["proc"] = cmd, FakeProc([json.dumps(e) + "\n" for e in events], code)
        return seen["proc"]

    return list(ar.run_cli(runner, "PROMPT", "suggest", "", project_root=tmp_path, popen=popen)), seen


def test_cursor_stream_is_translated(monkeypatch, tmp_path):
    events, seen = _run_cli(monkeypatch, tmp_path, "cursor", [
        {"type": "system", "subtype": "init"},
        {"type": "tool_call", "subtype": "started", "tool_call": {"readToolCall": {}}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "fatto"}]}},
        {"type": "result", "is_error": False, "duration_ms": 7, "result": '{"open_points":[]}'},
    ])
    assert [e["type"] for e in events] == ["tool_use", "text", "result"]
    assert events[-1]["open_points_status"] == "valid"
    seen["proc"].stdin.write.assert_called_once_with("PROMPT")
    assert "PROMPT" not in seen["cmd"]


def test_codex_stream_and_failure(monkeypatch, tmp_path):
    events, _ = _run_cli(monkeypatch, tmp_path, "codex", [
        {"type": "item.completed", "item": {"type": "agent_message", "text": '{"open_points":[]}'}},
    ])
    assert [e["type"] for e in events] == ["text", "result"]
    assert events[-1]["open_points_status"] == "valid"
    events, _ = _run_cli(monkeypatch, tmp_path, "codex", [], code=2)
    assert events[-1]["type"] == "error" and "codice 2" in events[-1]["message"]


def test_run_streaming_records_finish_and_errors(monkeypatch):
    monkeypatch.setattr(ar, "run_local", lambda *a, **k: iter([{"type": "result", "is_error": False}]))
    finished = []
    lines = list(ar.run_streaming("local", "p", "suggest", "m", on_finish=finished.append))
    assert json.loads(lines[-1])["type"] == "result" and finished[0]["type"] == "result"

    def boom(*a, **k):
        raise ar.llm.LLMError("Ollama giù")
        yield

    monkeypatch.setattr(ar, "run_local", boom)
    finished.clear()
    lines = list(ar.run_streaming("local", "p", "suggest", "m", on_finish=finished.append))
    assert "Ollama giù" in json.loads(lines[-1])["message"] and finished[0]["type"] == "error"
    with pytest.raises(ValueError):
        ar.run_streaming("codex", "p", "agentic", "")

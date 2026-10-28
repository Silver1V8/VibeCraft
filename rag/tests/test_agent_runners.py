"""Runner alternativi a Claude (agent_runners.py): perimetro dei tool del LLM locale,
loop di tool, comando e parsing delle CLI esterne, streaming NDJSON con on_finish.
Nessun Ollama né CLI reali: chat e popen sono iniettati."""
import json
from pathlib import Path

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


def test_validate_run(monkeypatch):
    assert ar.validate_run("local", "agentic", "qwen3.5:9b") is None
    assert ar.validate_run("claude", "suggest", "sonnet") is None
    assert ar.validate_run("codex", "suggest", "") is not None  # letture native non verificate
    assert ar.validate_run("cursor", "suggest", "--force") is not None
    assert ar.validate_run("nope", "suggest", "") is not None
    monkeypatch.setattr(ar, "probe_write_isolation",
                        lambda runner, force=False: __import__("native_sandbox").ProbeResult(
                            runner, False, "mocked fail"))
    assert ar.validate_run("codex", "agentic", "").startswith("native_write_isolation_unverified")
    monkeypatch.setattr(ar, "probe_write_isolation",
                        lambda runner, force=False: __import__("native_sandbox").ProbeResult(
                            runner, True, "mocked ok", True, True))
    assert ar.validate_run("codex", "agentic", "") is None


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
    disabled = {codex[i + 1] for i, arg in enumerate(codex) if arg == "--disable"}
    assert {"plugins", "computer_use", "browser_use", "hooks"} <= disabled
    agentic = ar.cli_command("codex", "", tmp_path / "code", tmp_path / "last.txt", "agentic")
    assert agentic[agentic.index("--sandbox") + 1] == "workspace-write"
    assert 'windows.sandbox="unelevated"' in agentic
    assert Path(agentic[agentic.index("-C") + 1]) == tmp_path / "code"
    for mode, expected in (("suggest", "plan"), ("oneshot", "ask")):
        cursor = ar.cli_command("cursor", "", tmp_path, tmp_path / "last.txt", mode)
        # `agent -p` da solo ha scrittura e shell: la sola lettura è --mode plan|ask.
        assert cursor[cursor.index("--mode") + 1] == expected
        assert cursor[cursor.index("--sandbox") + 1] == "enabled"
        assert "--force" not in cursor and "--yolo" not in cursor


def test_cli_missing_binary_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(ar.shutil, "which", lambda b: None)
    with pytest.raises(RuntimeError, match="PATH"):
        ar.cli_command("codex", "", tmp_path, tmp_path / "l")


def test_cursor_events_are_translated_without_execution():
    events = [ar.translate_cli_event("cursor", item) for item in [
        {"type": "system", "subtype": "init"},
        {"type": "tool_call", "subtype": "started", "tool_call": {"readToolCall": {}}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "fatto"}]}},
    ]]
    assert events == [None, {"type": "tool_use", "tool": "readToolCall"}, {"type": "text", "text": "fatto"}]


def test_codex_events_and_failure_are_translated_without_execution():
    event = ar.translate_cli_event("codex", {"type": "item.completed", "item": {
        "type": "agent_message", "text": '{"open_points":[]}'}})
    assert event == {"type": "text", "text": '{"open_points":[]}'}
    assert ar.translate_cli_event("codex", {"type": "turn.failed", "error": "errore"}) == {
        "type": "text", "text": "[turn.failed] errore"}


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
    monkeypatch.setattr(
        ar, "probe_write_isolation",
        lambda runner, force=False: __import__("native_sandbox").ProbeResult(
            runner, False, "unit-test force fail"))
    with pytest.raises(ValueError, match="native_write_isolation_unverified"):
        ar.run_streaming("codex", "p", "agentic", "")

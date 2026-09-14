"""Perimetro di sicurezza della modalità "agentic" del bridge Claude Agent SDK
(security/r8-agent-perimeter).

Copre tre livelli:

1. Costruzione delle ClaudeAgentOptions per ogni modalità — asserzioni ESATTE
   (uguaglianza, non "contiene"): agentic ha cwd=<root>/code, il set di tool
   atteso, Bash rimosso e l'hook PreToolUse; suggest/oneshot restano su
   PROJECT_ROOT senza hook. MCP è disponibile solo a suggest/agentic.
2. La funzione di decisione pura `_agentic_tool_denial` contro path avversari.
3. L'hook `_deny_out_of_sandbox_writes` (struttura del deny / astensione) e il
   contratto di streaming NDJSON di `run_agent_streaming` (con `query` fasullo),
   che il refactoring del confinamento non deve rompere.
"""
import asyncio
import json
import queue
import shutil
import sys

import pytest

import agent_bridge
from agent_bridge import (
    CODE_ROOT,
    PROJECT_ROOT,
    _agentic_tool_denial,
    _build_agent_options,
    _deny_out_of_sandbox_writes,
)
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

MCP_TOOLS = [
    "mcp__vibecraft__vibecraft_retrieve",
    "mcp__vibecraft__vibecraft_code_search",
    "mcp__vibecraft__vibecraft_graph_query",
]


# ===========================================================================
# 1. Costruzione delle opzioni — asserzioni esatte
# ===========================================================================
def test_agentic_options_confine_to_code_dir_exactly():
    opts = _build_agent_options("agentic", "sonnet")

    # cwd = <PROJECT_ROOT>/code (uguaglianza esatta).
    assert opts.cwd == str(CODE_ROOT)
    assert opts.cwd == str(PROJECT_ROOT / "code")

    # Set di tool auto-approvati esatto: NIENTE Bash.
    assert opts.allowed_tools == ["Read", "Write", "Edit", "Glob", "Grep"] + MCP_TOOLS
    assert opts.tools == ["Read", "Write", "Edit", "Glob", "Grep"]
    assert "Bash" not in opts.allowed_tools

    # Bash rimosso anche dal contesto del modello.
    assert opts.disallowed_tools == ["Bash"]

    assert opts.permission_mode == "dontAsk"
    assert opts.model == "sonnet"


def test_agentic_options_register_exactly_one_pretooluse_hook():
    opts = _build_agent_options("agentic", "sonnet")

    assert set(opts.hooks.keys()) == {"PreToolUse"}
    matchers = opts.hooks["PreToolUse"]
    assert len(matchers) == 1

    matcher = matchers[0]
    assert matcher.matcher == "Write|Edit|MultiEdit|NotebookEdit|Bash"
    assert matcher.hooks == [agent_bridge._deny_out_of_sandbox_writes]


def test_suggest_options_read_only_with_mcp_no_hooks():
    opts = _build_agent_options("suggest", "sonnet")

    assert opts.cwd == str(PROJECT_ROOT)  # NON confinata a code/
    assert opts.allowed_tools == ["Read", "Grep", "Glob"] + MCP_TOOLS
    assert opts.tools == ["Read", "Grep", "Glob"]
    assert opts.disallowed_tools == []
    assert opts.permission_mode == "dontAsk"
    assert opts.hooks is None  # nessun hook di confinamento


def test_oneshot_options_unchanged_no_tools_no_hooks():
    opts = _build_agent_options("oneshot", "sonnet")

    assert opts.cwd == str(PROJECT_ROOT)
    assert opts.allowed_tools == []
    assert opts.disallowed_tools == []
    assert opts.permission_mode == "dontAsk"
    assert opts.hooks is None
    assert opts.tools == []
    assert opts.mcp_servers == {}
    assert opts.strict_mcp_config is True
    assert opts.max_turns == 1


@pytest.mark.parametrize("mode", ["suggest", "agentic"])
def test_mcp_is_local_explicit_and_does_not_mutate_modes(mode, monkeypatch):
    monkeypatch.setenv("VIBECRAFT_AGENT_MAX_TURNS", "12")
    opts = _build_agent_options(mode, "sonnet")
    assert opts.mcp_servers == {"vibecraft": {
        "type": "stdio", "command": sys.executable,
        "args": ["-B", str(PROJECT_ROOT / "rag" / "mcp_server.py")],
    }}
    assert opts.strict_mcp_config is True
    assert opts.max_turns == 12
    assert _build_agent_options(mode, "sonnet").allowed_tools == opts.allowed_tools
    assert not any(t.startswith("mcp__") for t in agent_bridge.AGENT_MODES[mode]["allowed_tools"])


@pytest.mark.parametrize("value", ["0", "-1", "201", "nope"])
def test_invalid_turn_limit_closes_stream_instead_of_hanging(monkeypatch, value):
    monkeypatch.setenv("VIBECRAFT_AGENT_MAX_TURNS", value)
    monkeypatch.setattr(agent_bridge, "query", _fake_query_factory([], raise_exc=AssertionError("SDK non deve partire")))
    out = queue.Queue()
    asyncio.run(agent_bridge._run_agent("hi", "suggest", "sonnet", out))
    event = out.get_nowait()
    assert event["type"] == "error"
    assert "VIBECRAFT_AGENT_MAX_TURNS" in event["message"]
    assert out.get_nowait() is None


def test_model_is_forwarded():
    assert _build_agent_options("agentic", "opus").model == "opus"
    assert _build_agent_options("suggest", "haiku").model == "haiku"


def test_windows_npm_shim_uses_installed_native_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_bridge.sys, "platform", "win32")
    monkeypatch.setattr(shutil, "which", lambda name: str(tmp_path / "claude.cmd"))
    native = tmp_path / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    native.parent.mkdir(parents=True)
    native.touch()
    assert _build_agent_options("suggest", "sonnet").cli_path == str(native)
    native.unlink()
    assert _build_agent_options("suggest", "sonnet").cli_path is None


# ===========================================================================
# 2. Funzione di decisione pura — path avversari
# ===========================================================================
# Path che DEVONO essere negati (deny => motivo non-None). Copre gli scenari
# richiesti: area riservata rag/, traversal ../ verso rag/, path assoluto fuori
# da code/, area riservata .git/, area riservata docs/.
_DENIED_WRITE_PATHS = [
    "rag/database/CURRENT",
    "../rag/rag_config.yaml",
    str(PROJECT_ROOT / "outside_zone" / "evil.txt"),  # assoluto, fuori da code/
    ".git/config",
    "docs/spec_tech_frontend.md",
    "../../etc/passwd",
    "backend/../../rag/database/CURRENT",  # rientra in code/ ma nomina rag/
]

# Path LEGITTIMI sotto code/ (allow => None). "backend/app.py" e
# "frontend/hello.txt" sono relativi alla working dir code/.
_ALLOWED_WRITE_PATHS = [
    "backend/app.py",
    "frontend/hello.txt",
    "backend/src/Portal.Api/Program.cs",
]


@pytest.mark.parametrize("path", _DENIED_WRITE_PATHS)
def test_write_outside_code_is_denied(path):
    reason = _agentic_tool_denial("Write", {"file_path": path}, CODE_ROOT)
    assert reason is not None, f"atteso deny per {path!r}"


@pytest.mark.parametrize("path", _ALLOWED_WRITE_PATHS)
def test_write_inside_code_is_allowed(path):
    reason = _agentic_tool_denial("Write", {"file_path": path}, CODE_ROOT)
    assert reason is None, f"atteso allow per {path!r}, negato con: {reason}"


@pytest.mark.parametrize("path", _DENIED_WRITE_PATHS)
def test_edit_outside_code_is_denied(path):
    # Edit usa lo stesso campo file_path: stessa decisione di Write.
    assert _agentic_tool_denial("Edit", {"file_path": path}, CODE_ROOT) is not None


def test_notebook_edit_uses_notebook_path():
    assert _agentic_tool_denial(
        "NotebookEdit", {"notebook_path": "../rag/x.ipynb"}, CODE_ROOT
    ) is not None
    assert _agentic_tool_denial(
        "NotebookEdit", {"notebook_path": "frontend/nb.ipynb"}, CODE_ROOT
    ) is None


def test_bash_is_always_denied_in_agentic():
    # Bash non è confinabile: negato a prescindere dal comando.
    assert _agentic_tool_denial("Bash", {"command": "echo hi"}, CODE_ROOT) is not None
    assert _agentic_tool_denial(
        "Bash", {"command": "npm run build"}, CODE_ROOT
    ) is not None


def test_write_without_path_fails_closed():
    # Un tool di scrittura senza path riconoscibile viene negato (fail-closed).
    assert _agentic_tool_denial("Write", {}, CODE_ROOT) is not None
    assert _agentic_tool_denial("Write", {"file_path": ""}, CODE_ROOT) is not None


def test_absolute_path_inside_code_is_allowed():
    # Un path assoluto che cade DENTRO code/ è consentito (confinamento reale,
    # non un divieto cieco sugli assoluti).
    inside = str(CODE_ROOT / "backend" / "app.py")
    assert _agentic_tool_denial("Write", {"file_path": inside}, CODE_ROOT) is None


# ===========================================================================
# 3a. Hook PreToolUse — struttura del deny e astensione
# ===========================================================================
def test_hook_denies_out_of_sandbox_write_with_correct_shape():
    out = asyncio.run(
        _deny_out_of_sandbox_writes(
            {"tool_name": "Write", "tool_input": {"file_path": "../rag/rag_config.yaml"}},
            None,
            {"signal": None},
        )
    )
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny"
    assert "rag" in hso["permissionDecisionReason"]


def test_hook_denies_bash():
    out = asyncio.run(
        _deny_out_of_sandbox_writes(
            {"tool_name": "Bash", "tool_input": {"command": "rm -rf ../docs"}},
            None,
            {"signal": None},
        )
    )
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_hook_abstains_on_in_sandbox_write():
    # In-bounds => dict vuoto: l'hook si astiene, decide allowed_tools + dontAsk.
    out = asyncio.run(
        _deny_out_of_sandbox_writes(
            {"tool_name": "Write", "tool_input": {"file_path": "frontend/hello.txt"}},
            None,
            {"signal": None},
        )
    )
    assert out == {}


# ===========================================================================
# 3b. Streaming NDJSON — il refactoring non rompe il contratto
# ===========================================================================
def _fake_query_factory(messages, raise_exc=None):
    async def fake_query(*, prompt, options):
        for m in messages:
            yield m
        if raise_exc is not None:
            raise raise_exc
    return fake_query


def test_run_agent_streaming_emits_valid_ndjson(monkeypatch):
    messages = [
        AssistantMessage(content=[TextBlock(text="ciao")], model="m"),
        AssistantMessage(
            content=[ToolUseBlock(id="t1", name="Read", input={})], model="m"
        ),
        ResultMessage(
            subtype="success", duration_ms=5, duration_api_ms=1,
            is_error=False, num_turns=1, session_id="s",
        ),
    ]
    monkeypatch.setattr(agent_bridge, "query", _fake_query_factory(messages))

    lines = list(agent_bridge.run_agent_streaming("hi", "suggest", "sonnet"))

    # Ogni linea è JSON valido e termina con newline.
    events = []
    for line in lines:
        assert line.endswith("\n")
        events.append(json.loads(line))

    assert events[0] == {"type": "text", "text": "ciao"}
    assert events[1] == {"type": "tool_use", "tool": "Read"}
    assert events[2]["type"] == "result"
    assert events[2]["is_error"] is False


def test_run_agent_streaming_reports_errors_as_ndjson(monkeypatch):
    monkeypatch.setattr(
        agent_bridge, "query",
        _fake_query_factory([], raise_exc=RuntimeError("boom")),
    )

    lines = list(agent_bridge.run_agent_streaming("hi", "agentic", "sonnet"))

    events = [json.loads(line) for line in lines]
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "boom" in events[0]["message"]


def test_run_agent_streaming_rejects_unknown_mode():
    with pytest.raises(ValueError):
        list(agent_bridge.run_agent_streaming("hi", "nonexistent", "sonnet"))

"""Prove di isolamento scrittura per Codex/Cursor (native_sandbox.py).

I test unitari non dipendono dai binari. La prova live Codex gira solo su Windows
con `codex` nel PATH: è il gate che abilita agentic.
"""
import sys
from pathlib import Path

import pytest

import native_sandbox as ns


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    ns.clear_probe_cache()
    yield
    ns.clear_probe_cache()


def test_probe_rejects_unknown_runner():
    with pytest.raises(ValueError, match="non supportato"):
        ns.probe_write_isolation("claude")


def test_codex_probe_fails_closed_without_binary(monkeypatch):
    monkeypatch.setattr(ns.shutil, "which", lambda name: None)
    result = ns.probe_write_isolation("codex")
    assert not result.ok
    assert result.reason.startswith(ns.WRITE_UNAVAILABLE_CODE)
    assert "assente" in result.detail


def test_codex_probe_fails_closed_off_windows(monkeypatch):
    monkeypatch.setattr(ns.shutil, "which", lambda name: "codex")
    monkeypatch.setattr(ns.sys, "platform", "linux")
    result = ns.probe_write_isolation("codex")
    assert not result.ok
    assert "Windows" in result.detail


def test_probe_result_is_cached(monkeypatch):
    calls = []

    def fake_run(runner):
        calls.append(runner)
        return ns.ProbeResult(runner, False, "once")

    monkeypatch.setattr(ns, "_run_probe", fake_run)
    first = ns.probe_write_isolation("cursor")
    second = ns.probe_write_isolation("cursor")
    assert first is second and calls == ["cursor"]
    ns.probe_write_isolation("cursor", force=True)
    assert calls == ["cursor", "cursor"]


def test_cursor_probe_reports_missing_sandbox_helper(monkeypatch):
    monkeypatch.setattr(ns.sys, "platform", "win32")
    monkeypatch.setattr(ns, "_find_cursor_sandbox", lambda: None)
    result = ns.probe_write_isolation("cursor")
    assert not result.ok
    assert "cursorsandbox" in result.detail


def test_cursor_probe_fails_when_outside_write_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr(ns.sys, "platform", "win32")
    sb = tmp_path / "cursorsandbox.exe"
    sb.write_text("dummy")
    monkeypatch.setattr(ns, "_find_cursor_sandbox", lambda: sb)

    def fake_run(cmd, **kwargs):
        # Simula il fallimento misurato su PcLavoro: scrive anche fuori dal cwd.
        policy = Path(cmd[cmd.index("--policy") + 1])
        root = policy.parent
        (root / "code" / "inside.txt").write_text("ok")
        (root / "docs" / "outside.txt").write_text("pwn")
        return type("P", (), {"returncode": 0, "stdout": "in=True out=True", "stderr": ""})()

    monkeypatch.setattr(ns.subprocess, "run", fake_run)
    result = ns.probe_write_isolation("cursor")
    assert not result.ok
    assert result.inside_allowed is True
    assert result.outside_denied is False


@pytest.mark.skipif(sys.platform != "win32", reason="sandbox Codex Windows-only")
@pytest.mark.skipif(not __import__("shutil").which("codex"), reason="codex non nel PATH")
def test_live_codex_workspace_write_isolation():
    """Gate prodotto: scrittura in code/ ok, fuori negata (unelevated :workspace)."""
    result = ns.probe_write_isolation("codex", force=True)
    assert result.ok, result.detail
    assert result.inside_allowed is True
    assert result.outside_denied is True
    assert ns.write_isolation_ok("codex")

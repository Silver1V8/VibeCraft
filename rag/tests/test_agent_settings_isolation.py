# Il controllo positivo prova che l'hook è eseguibile: senza, il test negativo
# potrebbe passare perché il fixture è rotto, non perché l'isolamento funziona.
"""CLI/SDK reali, sole inizializzazioni: nessun prompt o generazione del modello."""
import asyncio
from dataclasses import replace
import json
import sys

import anyio
from claude_agent_sdk import ClaudeSDKClient
import pytest

import agent_bridge


@pytest.mark.parametrize("mode", ["suggest", "oneshot", "agentic"])
def test_local_hooks_excluded_with_live_positive_control(mode, tmp_path, monkeypatch):
    project = tmp_path / "project"
    cwd = project / "code" if mode == "agentic" else project
    cwd.mkdir(parents=True)
    config = tmp_path / "config"
    config.mkdir()
    monkeypatch.setitem(agent_bridge.AGENT_MODES[mode], "cwd", cwd)
    monkeypatch.setattr(agent_bridge, "CODE_ROOT", project / "code")
    # Isola impostazioni e credenziali reali. connect() non invia messaggi utente;
    # anche un'eventuale richiesta provider accidentale non può raggiungere il cloud.
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")

    hook = tmp_path / "sentinel.py"
    hook.write_text(
        "from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text('ran')\n",
        encoding="utf-8",
    )
    settings_dir = cwd / ".claude"
    settings_dir.mkdir()
    sources = {
        "user": config / "settings.json",
        "project": settings_dir / "settings.json",
        "local": settings_dir / "settings.local.json",
    }
    sentinels = []
    for source, path in sources.items():
        sentinel = tmp_path / f"{source}.sentinel"
        sentinels.append(sentinel)
        command = f'"{sys.executable}" "{hook}" "{sentinel}"'
        path.write_text(json.dumps({"hooks": {"SessionStart": [{
            "matcher": "startup",
            "hooks": [{"type": "command", "command": command}],
        }]}}), encoding="utf-8")

    options = agent_bridge._build_agent_options(mode, "sonnet")
    if mode == "agentic":
        matcher = options.hooks["PreToolUse"][0]
        assert matcher.matcher == "Read|Grep|Glob|Write|Edit|MultiEdit|NotebookEdit|Bash"
        assert len(matcher.hooks) == 1
        assert matcher.hooks[0].func is agent_bridge._guard_project_tools

    async def initialize_only(opts):
        with anyio.fail_after(45):
            async with ClaudeSDKClient(options=opts) as client:
                assert await client.get_server_info()

    # Identiche opzioni applicative: cambia soltanto il caricamento delle fonti.
    asyncio.run(initialize_only(replace(options, setting_sources=list(sources))))
    assert all(path.is_file() for path in sentinels), "Controllo positivo: hook non eseguiti"
    for path in sentinels:
        path.unlink()

    asyncio.run(initialize_only(options))
    assert not any(path.exists() for path in sentinels), "Hook locali eseguiti dal bridge"
    assert options.setting_sources == []

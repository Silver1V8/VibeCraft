"""
Bridge tra il server FastAPI e il Claude Agent SDK.

Problema architetturale: FastAPI/uvicorn possiede un event loop asyncio, e il
Claude Agent SDK gestisce a sua volta sottoprocessi asincroni. Farli convivere
nello stesso loop causa race condition (su Windows anche incompatibilità di
policy tra Selector/Proactor per i sottoprocessi). Soluzione: l'SDK vive su un
thread daemon dedicato con il proprio event loop; le chiamate vi vengono
instradate con `asyncio.run_coroutine_threadsafe`, senza mai bloccare il server.

Tre modalità di fiducia (dalla più conservativa alla più autonoma):
  - suggest : sola lettura (Read/Grep/Glob) — l'agente analizza e propone,
              non tocca il filesystem.
  - agentic : accesso completo al filesystem del progetto con perimetro di
              sicurezza (tool pre-approvati, tutto il resto negato).
  - oneshot : nessun tool — pura generazione di testo/codice.
"""

import asyncio
import json
import queue
import sys
import threading
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Modalità di fiducia: ogni voce definisce il perimetro dei tool auto-approvati.
# permission_mode="dontAsk" nega tutto ciò che non è pre-approvato: essenziale
# in un contesto server non interattivo, dove nessuno può rispondere ai prompt.
AGENT_MODES: dict[str, dict] = {
    "suggest": {
        "label": "Suggest-only (sola lettura)",
        "allowed_tools": ["Read", "Grep", "Glob"],
        "permission_mode": "dontAsk",
    },
    "agentic": {
        "label": "Agentic completo (scrive nel progetto)",
        "allowed_tools": ["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
        "permission_mode": "dontAsk",
    },
    "oneshot": {
        "label": "One-shot (generazione pura, nessun tool)",
        "allowed_tools": [],
        "permission_mode": "dontAsk",
    },
}

# ---------------------------------------------------------------------------
# Event loop dedicato su thread daemon
# ---------------------------------------------------------------------------
_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """Avvia (una sola volta) il thread daemon che ospita l'event loop dell'SDK."""
    global _loop
    with _loop_lock:
        if _loop is not None and _loop.is_running():
            return _loop

        loop_ready = threading.Event()

        def _runner() -> None:
            global _loop
            if sys.platform == "win32":
                # I sottoprocessi asyncio su Windows richiedono il ProactorEventLoop
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _loop = loop
            loop_ready.set()
            loop.run_forever()

        threading.Thread(target=_runner, name="claude-agent-loop", daemon=True).start()
        loop_ready.wait(timeout=10)
        if _loop is None:
            raise RuntimeError("Impossibile avviare l'event loop dell'Agent SDK.")
        return _loop


# ---------------------------------------------------------------------------
# Esecuzione con streaming degli eventi
# ---------------------------------------------------------------------------
async def _run_agent(prompt: str, mode: str, out: queue.Queue) -> None:
    """Esegue query() sull'event loop dedicato e pubblica gli eventi sulla coda."""
    mode_cfg = AGENT_MODES[mode]
    options = ClaudeAgentOptions(
        cwd=str(PROJECT_ROOT),
        allowed_tools=mode_cfg["allowed_tools"],
        permission_mode=mode_cfg["permission_mode"],
    )
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        out.put({"type": "text", "text": block.text})
                    elif isinstance(block, ToolUseBlock):
                        out.put({"type": "tool_use", "tool": block.name})
            elif isinstance(message, ResultMessage):
                out.put({
                    "type": "result",
                    "is_error": bool(getattr(message, "is_error", False)),
                    "duration_ms": getattr(message, "duration_ms", None),
                    "total_cost_usd": getattr(message, "total_cost_usd", None),
                    "num_turns": getattr(message, "num_turns", None),
                })
    except Exception as exc:  # noqa: BLE001 — l'errore va riportato al client
        out.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
    finally:
        out.put(None)  # sentinella di fine stream


def run_agent_streaming(prompt: str, mode: str):
    """
    Generatore sincrono di eventi NDJSON, consumabile da StreamingResponse.
    FastAPI lo esegue nel threadpool, quindi la lettura bloccante dalla coda
    non ferma mai l'event loop del server.
    """
    if mode not in AGENT_MODES:
        raise ValueError(f"Modalità sconosciuta: {mode!r}. Valide: {list(AGENT_MODES)}")

    loop = _ensure_loop()
    out: queue.Queue = queue.Queue()
    asyncio.run_coroutine_threadsafe(_run_agent(prompt, mode, out), loop)

    while True:
        event = out.get()
        if event is None:
            break
        yield json.dumps(event, ensure_ascii=False) + "\n"

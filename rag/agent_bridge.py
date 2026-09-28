"""
Bridge tra il server FastAPI e il Claude Agent SDK.

Problema architetturale: FastAPI/uvicorn possiede un event loop asyncio, e il
Claude Agent SDK gestisce a sua volta sottoprocessi asincroni. Farli convivere
nello stesso loop causa race condition (su Windows anche incompatibilità di
policy tra Selector/Proactor per i sottoprocessi). Soluzione: l'SDK vive su un
thread daemon dedicato con il proprio event loop; le chiamate vi vengono
instradate con `asyncio.run_coroutine_threadsafe`, senza mai bloccare il server.

Tre modalità di fiducia (dalla più conservativa alla più autonoma):
  - suggest : sola lettura (Read/Grep/Glob + MCP) su tutto il progetto — l'agente
              analizza e propone, senza scritture applicative.
  - agentic : scrive SOLO dentro PROJECT_ROOT/code (il codice generato). La
              working dir è code/ e un hook PreToolUse nega meccanicamente ogni
              Write/Edit fuori da quel perimetro; MCP è di sola lettura, Bash è rimosso.
  - oneshot : nessun tool — pura generazione di testo/codice su PROJECT_ROOT.

Perimetro di sicurezza della modalità "agentic" (SDK claude-agent-sdk 0.2.115)
-----------------------------------------------------------------------------
La modalità agentic è l'unico endpoint con scrittura file / esecuzione: è dietro
require_api_key_strict (X-API-Key sempre, anche da localhost). Il confinamento
del *filesystem* usa due primitive dell'SDK, entrambe verificate presenti in
questa versione installata:

1. ``ClaudeAgentOptions.cwd`` = PROJECT_ROOT/code — la radice operativa.
2. Un hook ``PreToolUse`` che restituisce ``permissionDecision="deny"`` per ogni
   Write/Edit il cui path risolve fuori da code/ (o tocca aree riservate del
   progetto: rag/, docs/, .git/). È la primitiva più forte disponibile: il CLI
   invoca il PreToolUse hook per OGNI tool call — anche quelle auto-approvate da
   ``allowed_tools`` — e un deny la blocca comunque (types.py: la callback
   ``can_use_tool`` è invece "shadowed" da allowed_tools e richiede un prompt
   AsyncIterable, quindi non è adatta qui). Gli hook funzionano anche con prompt
   stringa perché il client interno forza sempre ``is_streaming_mode=True``.

Bash è RIMOSSO dalla modalità agentic (``disallowed_tools=["Bash"]``). Motivo:
il path-scoping di Bash non è confinabile in modo affidabile con questa versione.
``allowed_tools`` supporta pattern come ``Bash(npm:*)`` ma vincolano solo il
*prefisso del comando*, non i path toccati: ``npm`` (o ``python``, ``dotnet``)
può scrivere ovunque via script, ``..``, path assoluti, redirezioni o subshell.
Un hook che tenta di estrarre i path da una riga di shell (linguaggio
Turing-completo: eval, variabili, base64, subshell) è aggirabile. La sandbox di
esecuzione dell'SDK (``SandboxSettings``) è dichiarata macOS/Linux-only e questo
deploy è Windows. Conclusione netta: meglio perdere Bash che lasciare una RCE con
scrittura non confinata. Build/test del codice generato restano da fare fuori
dalla modalità agentic (pipeline dedicata / esecuzione manuale).
"""

import asyncio
import logging
import math
import json
import os
import queue
import shutil
import sys
import threading
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from core import llm
from core.open_points import read_report

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Radice operativa della modalità agentic: l'unica area in cui può scrivere.
CODE_ROOT = PROJECT_ROOT / "code"

# Segmenti di path riservati: aree del progetto che la modalità agentic non deve
# mai toccare, nemmeno con un nome che *sembra* interno a code/. La confinazione
# vera (risoluzione contro CODE_ROOT) protegge già i percorsi reali rag//docs/
# /.git/ (che stanno FUORI da code/, a livello di PROJECT_ROOT); questo blocklist
# è difesa in profondità: rifiuta a priori qualunque path che nomini quelle aree,
# così un "rag/database/CURRENT" o ".git/config" è negato a prescindere.
_RESERVED_SEGMENTS = frozenset({".git", "rag", "docs"})

# Tool che possono scrivere/eseguire: l'hook PreToolUse li intercetta. Bash è
# incluso per difesa in profondità (viene già rimosso via disallowed_tools): se
# in futuro qualcuno lo riaggiungesse a allowed_tools, l'hook lo negherebbe
# comunque invece di lasciare una RCE non confinata.
_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit", "Bash")
_GUARDED_TOOLS_MATCHER = "|".join(_GUARDED_TOOLS)


# ---------------------------------------------------------------------------
# Decisione di confinamento (funzioni pure, testabili in isolamento)
# ---------------------------------------------------------------------------
def _path_escapes_code(path_str: str, code_root: Path) -> str | None:
    """Restituisce un motivo di deny se `path_str` non è una scrittura sicura
    dentro `code_root`, altrimenti None (consentito).

    Fail-closed: qualunque path assoluto fuori da code/, qualunque `..` che esce
    dal sandbox, e qualunque riferimento a un'area riservata del progetto viene
    rifiutato. Il path viene interpretato come lo interpreta l'agente, ossia
    relativo a code_root (la sua working dir)."""
    if not str(path_str).strip():
        return "path vuoto"

    raw = Path(path_str)

    # 1) Blocklist di aree riservate, sui segmenti grezzi (prima della
    #    risoluzione): cattura "rag/...", ".git/config", "docs/..." anche quando
    #    risolverebbero dentro code/. Confronto case-insensitive (Windows).
    lowered = {part.lower() for part in raw.parts}
    reserved_hit = lowered & _RESERVED_SEGMENTS
    if reserved_hit:
        return f"path tocca un'area riservata del progetto: {sorted(reserved_hit)}"

    # 2) Confinamento reale: risolvi contro code_root e pretendi che resti dentro.
    base = code_root.resolve()
    candidate = raw if raw.is_absolute() else base / raw
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError, ValueError):
        return f"path non risolvibile: {path_str}"

    if resolved != base and base not in resolved.parents:
        return f"path fuori dal sandbox code/: {resolved}"

    return None


def _agentic_tool_denial(
    tool_name: str, tool_input: dict[str, Any], code_root: Path
) -> str | None:
    """Decisione di deny per la modalità agentic. Restituisce il motivo del
    rifiuto (str) oppure None se il tool call è consentito.

    Funzione pura: nessun effetto collaterale oltre la risoluzione di path, così
    da essere testabile direttamente con path avversari."""
    # Bash non è confinabile in modo affidabile (vedi docstring del modulo):
    # negato a priori. Difesa in profondità con disallowed_tools=["Bash"].
    if tool_name == "Bash":
        return "Bash non è consentito in modalità agentic (RCE non confinabile)."

    # Tool di scrittura: il path può stare sotto file_path o notebook_path.
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if file_path is None:
        # Un tool di scrittura senza path riconoscibile non è verificabile:
        # fail-closed, meglio negare che consentire una scrittura opaca.
        return f"scrittura senza path verificabile (tool {tool_name!r})"

    return _path_escapes_code(str(file_path), code_root)


async def _deny_out_of_sandbox_writes(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Hook PreToolUse per la modalità agentic. Nega Write/Edit fuori da code/
    e qualunque Bash; per tutto il resto si astiene (dict vuoto), lasciando che
    allowed_tools + permission_mode='dontAsk' decidano."""
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input") or {}
    reason = _agentic_tool_denial(tool_name, tool_input, CODE_ROOT)
    if reason is None:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"[perimetro agentic] {reason}",
        }
    }


# ---------------------------------------------------------------------------
# Modalità di fiducia
# ---------------------------------------------------------------------------
# Ogni voce definisce il perimetro dei tool auto-approvati e la working dir.
# permission_mode="dontAsk" nega tutto ciò che non è pre-approvato: essenziale in
# un contesto server non interattivo, dove nessuno può rispondere ai prompt.
AGENT_MODES: dict[str, dict] = {
    "suggest": {
        "label": "Suggest-only (sola lettura)",
        "allowed_tools": ["Read", "Grep", "Glob"],
        "permission_mode": "dontAsk",
        "cwd": PROJECT_ROOT,
    },
    "agentic": {
        "label": "Agentic completo (scrive solo in code/)",
        # Bash rimosso: non confinabile (vedi docstring). Solo lettura + scrittura.
        "allowed_tools": ["Read", "Write", "Edit", "Glob", "Grep"],
        "disallowed_tools": ["Bash"],
        "permission_mode": "dontAsk",
        "cwd": CODE_ROOT,
        # Attiva l'hook PreToolUse che confina le scritture dentro code/.
        "confine_writes": True,
    },
    "oneshot": {
        "label": "One-shot (generazione pura, nessun tool)",
        "allowed_tools": [],
        "permission_mode": "dontAsk",
        "cwd": PROJECT_ROOT,
    },
}


def _max_turns() -> int:
    """Tetto di turni per le modalità con tool, condiviso con i runner di agent_runners."""
    try:
        max_turns = int(os.environ.get("VIBECRAFT_AGENT_MAX_TURNS", "30"))
        if not 1 <= max_turns <= 200:
            raise ValueError
    except ValueError:
        raise ValueError("VIBECRAFT_AGENT_MAX_TURNS deve essere un intero fra 1 e 200.") from None
    return max_turns


def _build_agent_options(mode: str, model: str) -> ClaudeAgentOptions:
    """Costruisce le ClaudeAgentOptions per una modalità. Isolata dal resto per
    essere asseribile con precisione nei test."""
    cfg = AGENT_MODES[mode]
    cwd = cfg["cwd"]

    kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        # Esclude impostazioni/hook user, project e local in tutte le modalità.
        # Gli hook SDK espliciti di confinamento restano registrati più sotto.
        "setting_sources": [],
        "tools": list(cfg["allowed_tools"]),
        "allowed_tools": list(cfg["allowed_tools"]),
        "disallowed_tools": cfg.get("disallowed_tools", []),
        "permission_mode": cfg["permission_mode"],
        "model": model,
        "strict_mcp_config": True,
        "max_turns": 1,
    }

    # L'SDK rifiuta gli shim .cmd; npm può già contenere il binario nativo
    # senza esporlo direttamente nel PATH. Non eseguire lo shim tramite shell.
    if sys.platform == "win32" and (cli := shutil.which("claude")):
        if Path(cli).suffix.lower() in (".cmd", ".bat"):
            native = Path(cli).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
            if native.is_file():
                kwargs["cli_path"] = str(native)

    if mode != "oneshot":
        kwargs["max_turns"] = _max_turns()
        # Stesso interprete/checkout del backend; ambiente ereditato, nessuna chiave
        # nel prompt o negli argomenti CLI. Il server MCP resta un adattatore HTTP.
        kwargs["mcp_servers"] = {"vibecraft": {
            "type": "stdio", "command": sys.executable,
            "args": ["-B", str(PROJECT_ROOT / "rag" / "mcp_server.py")],
        }}
        kwargs["allowed_tools"] += [
            "mcp__vibecraft__vibecraft_retrieve",
            "mcp__vibecraft__vibecraft_code_search",
            "mcp__vibecraft__vibecraft_graph_query",
        ]

    if cfg.get("confine_writes"):
        # La working dir deve esistere: il transport dell'SDK fallisce se cwd non
        # esiste. mkdir non distruttivo (exist_ok).
        Path(cwd).mkdir(parents=True, exist_ok=True)
        kwargs["hooks"] = {
            "PreToolUse": [
                HookMatcher(
                    matcher=_GUARDED_TOOLS_MATCHER,
                    hooks=[_deny_out_of_sandbox_writes],
                )
            ]
        }

    return ClaudeAgentOptions(**kwargs)


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
            # Su Windows i sottoprocessi asyncio richiedono il ProactorEventLoop.
            # Lo costruiamo direttamente invece di impostare una policy globale:
            # le event loop policy sono deprecate a partire da Python 3.14.
            if sys.platform == "win32":
                loop = asyncio.ProactorEventLoop()
            else:
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
async def _run_agent(prompt: str, mode: str, model: str, out: queue.Queue, *, feature: str | None = None,
                     attempt_id=None, on_finish=None) -> None:
    """Esegue query() sull'event loop dedicato e pubblica gli eventi sulla coda."""
    from core.pipeline_activity import track
    with track(feature, attempt_id):
        await _run_agent_messages(prompt, mode, model, out, on_finish=on_finish)


async def _run_agent_messages(prompt, mode, model, out, *, on_finish=None):
    final_text = []
    terminated = False
    cost_usd = None  # costo dichiarato dall'SDK nel ResultMessage (anche con is_error)
    outcome = {'type': 'error', 'message': 'Esecuzione interrotta', **read_report(None)}
    try:
        options = _build_agent_options(mode, model)
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        final_text.append(block.text)
                        out.put({"type": "text", "text": block.text})
                    elif isinstance(block, ToolUseBlock):
                        final_text.clear()  # Un report precedente ad altri tool non è quello finale.
                        out.put({"type": "tool_use", "tool": block.name})
            elif isinstance(message, ResultMessage):
                terminated = True
                cost_usd = getattr(message, "total_cost_usd", None)
                report = getattr(message, "structured_output", None)
                if report is None:
                    report = getattr(message, "result", None)
                if report is None:
                    report = '\n'.join(final_text)
                outcome = {
                    "type": "result",
                    "is_error": bool(getattr(message, "is_error", False)),
                    "duration_ms": getattr(message, "duration_ms", None),
                    "total_cost_usd": getattr(message, "total_cost_usd", None),
                    "num_turns": getattr(message, "num_turns", None),
                    **read_report(report),
                }
                out.put(outcome)
        if not terminated:
            out.put({"type": "error", "message": "Stream interrotto senza risultato finale",
                     **read_report(None)})
    except Exception as exc:  # noqa: BLE001 — l'errore va riportato al client
        outcome = {"type": "error", "message": f"{type(exc).__name__}: {exc}", **read_report(None)}
        out.put(outcome)
    finally:
        _record_run_cost(cost_usd)
        _finish(out, outcome, on_finish)


def _record_run_cost(cost_usd) -> None:
    """Registra il costo del run nello stesso contatore giornaliero delle chiamate LLM
    (core.llm._record_spend), su cui POST /api/pipeline/agent/run valuta il budget.
    Vale anche per run falliti o interrotti dopo il ResultMessage: la spesa è avvenuta.
    Senza costo noto (stream interrotto prima del risultato) non c'è nulla da contare."""
    try:
        if cost_usd is not None:
            cost = float(cost_usd)
            if not math.isfinite(cost):  # NaN/inf avvelenerebbero il totale del giorno
                raise ValueError
            llm._record_spend(cost)
    except (TypeError, ValueError):
        logging.getLogger(__name__).warning("Costo del run agente non numerico: %r", cost_usd)


def _finish(out: queue.Queue, outcome: dict, on_finish) -> None:
    """Registra la fine (anche se il client è uscito) e chiude lo stream. Condivisa con
    i runner di agent_runners, così ogni esecuzione termina allo stesso modo."""
    if on_finish:
        try:
            on_finish(outcome)
        except Exception as exc:
            logging.getLogger(__name__).error('Registrazione fine esecuzione fallita: %s', exc)
            out.put({'type': 'error', 'message': f'Registrazione fine esecuzione fallita: {exc}',
                     **read_report(None)})
    out.put(None)  # sentinella di fine stream


def run_agent_streaming(prompt: str, mode: str, model: str = "sonnet", *, feature: str | None = None,
                        attempt_id=None, on_finish=None):
    """
    Generatore sincrono di eventi NDJSON, consumabile da StreamingResponse.
    FastAPI lo esegue nel threadpool, quindi la lettura bloccante dalla coda
    non ferma mai l'event loop del server.
    """
    if mode not in AGENT_MODES:
        raise ValueError(f"Modalità sconosciuta: {mode!r}. Valide: {list(AGENT_MODES)}")

    loop = _ensure_loop()
    out: queue.Queue = queue.Queue()
    # Ammissione e scheduling avvengono ora, sotto il lock della feature del chiamante;
    # non attendono la prima lettura HTTP. La fine viene registrata anche se il client esce.
    asyncio.run_coroutine_threadsafe(_run_agent(prompt, mode, model, out, feature=feature,
                                               attempt_id=attempt_id, on_finish=on_finish), loop)
    def consume():
        while True:
            event = out.get()
            if event is None:
                break
            yield json.dumps(event, ensure_ascii=False) + "\n"
    return consume()

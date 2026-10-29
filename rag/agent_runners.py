"""Runner alternativi a Claude Code per POST /api/pipeline/agent/run: LLM locale via
Ollama e CLI esterne (Codex, Cursor). Emettono lo stesso NDJSON di agent_bridge
(text / tool_use / result / error) e ne condividono ammissione, tracking e chiusura.

Perimetri, runner per runner:
  - local : i tool li esegue VibeCraft, non il modello, e non esiste shell. Letture solo
            dentro PROJECT_ROOT (niente .git né file .env*); in agentic le scritture passano
            da agent_bridge._path_escapes_code, la stessa decisione testata dell'hook Claude.
  - codex : suggest/oneshot restano chiusi (isolamento letture non verificato). Agentic si
            apre solo dopo `native_sandbox.probe_write_isolation("codex")` ok (fail-closed);
            cwd = code/, sandbox workspace-write + windows.sandbox=unelevated.
  - cursor: avvio integrato negato (letture e scritture); export/IDE restano disponibili.
Il prompt CLI va sempre su stdin, mai negli argomenti: gli shim .cmd
di npm su Windows passerebbero il testo a cmd.exe, che ne interpreta i metacaratteri.
"""
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import agent_bridge
from agent_bridge import CODE_ROOT, PROJECT_ROOT, _path_escapes_code, _read_path
from core import llm
from core.config import OLLAMA_TIMEOUT_SECONDS, OLLAMA_URL, config
from core.open_points import read_report
from core.projects import ProjectError, ProjectRegistry
from native_sandbox import (
    READ_UNAVAILABLE_CODE,
    WRITE_UNAVAILABLE_CODE,
    probe_write_isolation,
    write_isolation_ok,
)

RUNNERS: dict[str, dict] = {
    "claude": {"label": "Claude Code", "modes": ("suggest", "agentic", "oneshot"), "bin": "claude"},
    "local": {"label": "LLM locale (Ollama)", "modes": ("suggest", "agentic", "oneshot")},
    # agentic è nella lista per Codex: validate_run lo ammette solo se la prova scrittura passa.
    "codex": {"label": "Codex CLI", "modes": ("suggest", "oneshot", "agentic"), "bin": "codex"},
    "cursor": {"label": "Cursor CLI", "modes": ("suggest", "oneshot"), "bin": "agent"},
}
CLAUDE_MODELS = ["sonnet", "opus", "haiku"]
# Il modello finisce negli argomenti delle CLI: niente '-' iniziale (flag) né metacaratteri.
MODEL_RE = re.compile(r"^(|[A-Za-z0-9][\w.:/-]{0,99})$")

_TOOL_OUTPUT_CHARS = 6000  # num_ctx 16K: un solo file grande non deve saturare la finestra
_LIST_LIMIT = 200
_GREP_LIMIT = 100
_SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}
# Nomi da `codex features list` (codex-cli 0.154.0).
_CODEX_DISABLED_FEATURES = ("plugins", "apps", "browser_use", "computer_use", "image_generation",
                            "multi_agent", "hooks", "skill_mcp_dependency_install")


# Alias storico: i test e la route HTTP usavano un solo codice per il blocco nativo.
NATIVE_UNAVAILABLE_CODE = READ_UNAVAILABLE_CODE
NATIVE_UNAVAILABLE_MESSAGE = ("Avvio integrato non disponibile: l'isolamento delle letture del progetto "
                            "non è verificato. Il prompt può essere esportato per l'IDE.")
NATIVE_UNAVAILABLE_REASON = f"{NATIVE_UNAVAILABLE_CODE}: {NATIVE_UNAVAILABLE_MESSAGE}"
NATIVE_UNAVAILABLE_CODES = frozenset({READ_UNAVAILABLE_CODE, WRITE_UNAVAILABLE_CODE})


def native_detail(reason: str) -> dict | str:
    """Mappa un motivo validate_run a detail HTTP strutturato, se è un codice nativo."""
    for code in NATIVE_UNAVAILABLE_CODES:
        prefix = code + ": "
        if reason.startswith(prefix):
            return {"code": code, "message": reason.removeprefix(prefix)}
    return reason


def validate_run(runner: str, mode: str, model: str, *, project=None) -> str | None:
    """Motivo del rifiuto (400) o None."""
    if runner not in RUNNERS:
        return f"Runner non valido: {runner!r}. Validi: {list(RUNNERS)}"
    if mode not in RUNNERS[runner]["modes"]:
        return f"{RUNNERS[runner]['label']} non supporta la modalità {mode!r}."
    if not MODEL_RE.match(model or ""):
        return f"Nome modello non valido: {model!r}"
    if runner == "cursor":
        return NATIVE_UNAVAILABLE_REASON
    if runner == "codex":
        if mode != "agentic":
            return NATIVE_UNAVAILABLE_REASON
        probe = probe_write_isolation("codex")
        if not probe.ok:
            return probe.reason
    return None


def list_runners(*, project=None) -> list[dict]:
    """Runner con disponibilità reale sulla macchina del server (PATH e modelli Ollama)."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL.rstrip('/')}/api/tags", timeout=2) as r:
            local_models = [m["name"] for m in json.loads(r.read().decode()).get("models", [])]
    except (OSError, ValueError, KeyError):
        local_models = []
    out = []
    for rid, cfg in RUNNERS.items():
        if rid == "local":
            installed, models = bool(local_models), local_models
            available = installed
            code = reason = None
        elif rid == "claude":
            installed = shutil.which(cfg["bin"]) is not None
            models = CLAUDE_MODELS
            available = installed
            code = reason = None
        elif rid == "codex":
            installed = shutil.which(cfg["bin"]) is not None
            models = []
            # Disponibile solo se agentic può partire (prova scrittura ok). Suggest resta chiuso.
            available = bool(installed and write_isolation_ok("codex"))
            if not installed:
                code, reason = None, "Runner non installato o modello locale non disponibile."
            elif available:
                code = reason = None
            else:
                probe = probe_write_isolation("codex")
                code, reason = WRITE_UNAVAILABLE_CODE, probe.detail
        else:  # cursor
            installed = shutil.which(cfg["bin"]) is not None
            models = []
            available = False
            code = NATIVE_UNAVAILABLE_CODE if installed else None
            reason = NATIVE_UNAVAILABLE_MESSAGE if installed else (
                "Runner non installato o modello locale non disponibile.")
        if rid in ("claude", "local") and not available and reason is None:
            reason = "Runner non installato o modello locale non disponibile."
        out.append({"id": rid, "label": cfg["label"], "modes": list(cfg["modes"]),
                    "installed": installed, "export_available": True,
                    "available": available, "models": models,
                    "unavailable_code": code if not available else None,
                    "unavailable_reason": reason if not available else None})
    return out


# ---------------------------------------------------------------------------
# LLM locale: tool eseguiti da VibeCraft
# ---------------------------------------------------------------------------
def _fn(name, description, **props):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": {k: {"type": "string", "description": v}
                                                        for k, v in props.items()},
                       "required": list(props)}}}


_READ_TOOLS = [
    _fn("read_file", "Legge un file di testo del progetto.", path="percorso del file"),
    _fn("list_files", "Elenca file e cartelle (con '/' finale) sotto una cartella che corrispondono a un glob.",
        path="cartella di partenza", pattern="glob, es. **/*.py"),
    _fn("grep", "Cerca una regex nei file sotto una cartella; restituisce file:riga: testo.",
        path="cartella di partenza", pattern="espressione regolare"),
]
_WRITE_TOOLS = [
    _fn("write_file", "Crea o sovrascrive un file sotto code/.", path="percorso", content="contenuto completo"),
    _fn("edit_file", "Sostituisce un testo che compare una sola volta in un file sotto code/.",
        path="percorso", old="testo esistente", new="testo nuovo"),
]


def tool_specs(mode: str) -> list[dict]:
    return {"oneshot": [], "suggest": _READ_TOOLS, "agentic": _READ_TOOLS + _WRITE_TOOLS}[mode]


def _resolve_read(path_str: str, cwd: Path, project_root: Path, registry=None) -> Path:
    return _read_path(path_str, cwd, project_root, registry)


def _write_target(path_str: str, code_root: Path) -> Path:
    reason = _path_escapes_code(path_str, code_root)
    if reason:
        raise PermissionError(reason)
    raw = Path(path_str)
    return (raw if raw.is_absolute() else code_root.resolve() / raw).resolve()


def execute_tool(name: str, args: dict, *, mode: str, project_root: Path = PROJECT_ROOT,
                 code_root: Path = CODE_ROOT, registry=None) -> str:
    """Esegue un tool chiesto dal modello. Ogni errore torna al modello come testo."""
    if name not in {t["function"]["name"] for t in tool_specs(mode)}:
        return f"negato: tool {name!r} non disponibile in modalità {mode}"
    cwd = code_root if mode == "agentic" else project_root
    try:
        registry = registry if registry is not None else ProjectRegistry(readonly=True)
        if name == "read_file":
            text = _resolve_read(args.get("path", ""), cwd, project_root, registry).read_text(
                encoding="utf-8", errors="replace")
        elif name == "list_files":
            base = _resolve_read(args.get("path", "."), cwd, project_root, registry)
            found = []
            pattern = args.get("pattern") or "**/*"
            if Path(pattern).anchor or ".." in Path(pattern).parts or "~" in Path(pattern).parts:
                raise PermissionError("pattern esterno al progetto")
            for f in _safe_files(base, cwd, project_root, registry):
                if len(found) >= _LIST_LIMIT:
                    break
                if f.relative_to(base).full_match(pattern):
                    found.append(str(f) + ("/" if f.is_dir() else ""))
            text = "\n".join(found) or "(nessuna voce)"
        elif name == "grep":
            base = _resolve_read(args.get("path", "."), cwd, project_root, registry)
            rx = re.compile(args.get("pattern", ""))
            hits = []
            for f in _safe_files(base, cwd, project_root, registry):
                if not f.is_file() or f.stat().st_size > 1_000_000:
                    continue
                for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{f}:{n}: {line.strip()[:200]}")
                        if len(hits) >= _GREP_LIMIT:
                            return "\n".join(hits)
            text = "\n".join(hits) or "(nessuna corrispondenza)"
        elif name == "write_file":
            target = _write_target(args.get("path", ""), code_root)
            _resolve_read(str(target), cwd, project_root, registry)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(args.get("content", ""), encoding="utf-8")
            text = f"scritto {target}"
        else:  # edit_file
            target = _write_target(args.get("path", ""), code_root)
            _resolve_read(str(target), cwd, project_root, registry)
            current = target.read_text(encoding="utf-8")
            old = args.get("old", "")
            if not old or current.count(old) != 1:
                return "errore: il testo da sostituire deve comparire esattamente una volta"
            target.write_text(current.replace(old, args.get("new", "")), encoding="utf-8")
            text = f"modificato {target}"
    except (PermissionError, ProjectError):
        return "negato: path o storage del progetto non disponibile per questo tool"
    except (OSError, ValueError, re.error) as exc:
        return f"errore: {exc}"
    if len(text) > _TOOL_OUTPUT_CHARS:
        text = text[:_TOOL_OUTPUT_CHARS] + f"\n[troncato: {len(text)} caratteri totali]"
    return text


def _safe_files(base, cwd, project_root, registry):
    """Prune before enumeration; validate every file before stat/open."""
    if base.is_file():
        yield base
        return
    for parent, dirs, files in os.walk(base, followlinks=False):
        for entry in dirs[:] + files:
            path = Path(parent) / entry
            try:
                _resolve_read(str(path), cwd, project_root, registry)
            except (PermissionError, ProjectError):
                if entry in dirs:
                    dirs.remove(entry)
                continue
            if entry in dirs and entry in _SKIP_DIRS:
                dirs.remove(entry)
                continue
            yield path


def _ollama_chat(model: str, messages: list, tools: list) -> dict:
    # Riusa _ollama_payload per think/num_ctx/temperature e per il guardrail sulla finestra:
    # senza num_ctx Ollama taglierebbe la conversazione dall'alto in silenzio.
    payload = llm._ollama_payload(model, json.dumps(messages, ensure_ascii=False))
    del payload["prompt"]
    payload["messages"] = messages
    if tools:
        payload["tools"] = tools
    req = urllib.request.Request(f"{OLLAMA_URL.rstrip('/')}/api/chat",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise llm.LLMError(f"[ERRORE OLLAMA]: modello '{model}' non trovato. Esegui 'ollama pull {model}'.") from e
        raise llm.LLMError(f"[ERRORE OLLAMA]: {e}") from e
    except OSError as e:
        raise llm.LLMError("[ERRORE DI CONNESSIONE]: impossibile raggiungere Ollama.") from e


def run_local(prompt: str, mode: str, model: str, *, chat=_ollama_chat,
              project_root: Path = PROJECT_ROOT, code_root: Path = CODE_ROOT, registry=None):
    """Loop di tool su Ollama. Solo l'ultimo messaggio senza tool call vale come report,
    come in agent_bridge."""
    model = model or (config.get("llm_settings") or {}).get("models", {}).get("ollama", "")
    tools = tool_specs(mode)
    turns = 1 if mode == "oneshot" else agent_bridge._max_turns()
    cwd = code_root if mode == "agentic" else project_root
    registry = registry if registry is not None else ProjectRegistry(readonly=True)
    messages = [{"role": "system", "content": (
        "Sei un agente di sviluppo. Usa solo i tool forniti; i percorsi relativi partono da "
        f"'{cwd}'. Non hai shell." if tools else "Non hai tool: rispondi solo con testo.")},
        {"role": "user", "content": prompt}]
    started = time.monotonic()
    for turn in range(1, turns + 1):
        message = chat(model, messages, tools).get("message") or {}
        text, calls = message.get("content") or "", message.get("tool_calls") or []
        messages.append({"role": "assistant", "content": text, **({"tool_calls": calls} if calls else {})})
        if text.strip():
            yield {"type": "text", "text": text}
        if not calls:
            yield {"type": "result", "is_error": False, "duration_ms": int((time.monotonic() - started) * 1000),
                   "total_cost_usd": None, "num_turns": turn, **read_report(text)}
            return
        for call in calls:
            fn = call.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            yield {"type": "tool_use", "tool": fn.get("name", "")}
            messages.append({"role": "tool", "tool_name": fn.get("name", ""),
                             "content": execute_tool(fn.get("name", ""), args, mode=mode,
                                                     project_root=project_root, code_root=code_root, registry=registry)})
    yield {"type": "error", "message": f"Limite di {turns} turni raggiunto senza risposta finale",
           **read_report(None)}


# ---------------------------------------------------------------------------
# CLI esterne
# ---------------------------------------------------------------------------
def cli_command(runner: str, model: str, cwd: Path, last_message: Path, mode: str = "suggest") -> list[str]:
    exe = shutil.which(RUNNERS[runner]["bin"])
    if not exe:
        raise RuntimeError(f"'{RUNNERS[runner]['bin']}' non trovato nel PATH: installa {RUNNERS[runner]['label']}.")
    if runner == "codex":
        # suggest/oneshot: read-only (storico). agentic: workspace-write con cwd=code/ —
        # ammessi solo dopo native_sandbox.probe_write_isolation("codex").
        sandbox = "workspace-write" if mode == "agentic" else "read-only"
        cmd = [exe, "exec", "--json", "--sandbox", sandbox, "--skip-git-repo-check", "--ephemeral",
               "-C", str(cwd), "--output-last-message", str(last_message)]
        if mode == "agentic":
            # Elevated richiede UAC; MXC assente in 0.154.0. Unelevated è la prova
            # misurata su PcLavoro (scrittura in cwd ok, fuori negata).
            cmd[1:1] = ["-c", 'windows.sandbox="unelevated"']
        # Disabilita feature accessorie; questo non prova un confine di lettura o config.
        # Senza, Codex carica plugin e skill da
        # ~/.codex (misurato: leggeva SKILL.md fuori dal progetto) e ha tool che comandano
        # desktop e browser, che il sandbox read-only sui comandi shell non copre.
        for feature in _CODEX_DISABLED_FEATURES:
            cmd += ["--disable", feature]
    else:
        # `agent -p` ha TUTTI i tool, scrittura e shell compresi (agent --help, 2026.09.10): senza
        # --force non è sola lettura. La sola lettura sono le modalità plan/ask; --trust evita il
        # prompt interattivo di fiducia sul workspace, che bloccherebbe un'esecuzione headless.
        cmd = [exe, "-p", "--output-format", "stream-json", "--mode", "plan" if mode == "suggest" else "ask",
               "--sandbox", "enabled", "--trust", "--workspace", str(cwd)]
    if model:
        cmd += ["--model", model]
    return cmd + (["-"] if runner == "codex" else [])


def translate_cli_event(runner: str, ev: dict) -> dict | None:
    """Evento JSONL della CLI → evento NDJSON VibeCraft (None = ignorato)."""
    kind = ev.get("type")
    if runner == "cursor":
        if kind == "assistant":
            text = "".join(c.get("text", "") for c in (ev.get("message") or {}).get("content", [])
                           if c.get("type") == "text")
            return {"type": "text", "text": text} if text else None
        if kind == "tool_call" and ev.get("subtype") == "started":
            return {"type": "tool_use", "tool": next(iter(ev.get("tool_call") or {}), "tool")}
        return None
    item = ev.get("item") or {}
    if kind == "item.completed" and item.get("type") == "agent_message":
        return {"type": "text", "text": item.get("text", "")}
    if kind == "item.started" and item.get("type"):
        return {"type": "tool_use", "tool": item.get("command") or item["type"]}
    if kind in ("error", "turn.failed"):
        return {"type": "text", "text": f"[{kind}] {ev.get('message') or ev.get('error')}"}
    return None


def run_cli(runner: str, prompt: str, mode: str, model: str, *, project_root: Path = PROJECT_ROOT,
            code_root: Path = CODE_ROOT, popen=subprocess.Popen):
    if reason := validate_run(runner, mode, model):
        raise ValueError(reason)
    # Agentic scrive solo sotto code/: allinea cwd CLI alla stessa radice del runner local/Claude.
    cwd = code_root if mode == "agentic" else project_root
    if mode == "agentic":
        Path(cwd).mkdir(parents=True, exist_ok=True)
    timeout = float(os.environ.get("VIBECRAFT_AGENT_TIMEOUT_SECONDS", "1800"))
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        last_message, stderr_path = Path(tmp) / "last.txt", Path(tmp) / "stderr.txt"
        with stderr_path.open("w+", encoding="utf-8", errors="replace") as stderr:
            proc = popen(cli_command(runner, model, cwd, last_message, mode), cwd=cwd,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
                         text=True, encoding="utf-8", errors="replace")
            timer = threading.Timer(timeout, proc.kill)
            timer.start()
            texts, final = [], None
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
                for line in proc.stdout:
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if runner == "cursor" and ev.get("type") == "result":
                        final = ev
                        continue
                    event = translate_cli_event(runner, ev)
                    if event:
                        if event["type"] == "tool_use":
                            texts.clear()  # un testo seguito da altri tool non è il report finale
                        else:
                            texts.append(event["text"])
                        yield event
                code = proc.wait()
            finally:
                timer.cancel()
                if proc.poll() is None:
                    proc.kill()
            stderr.seek(0)
            err_tail = stderr.read()[-2000:]
        duration = int((time.monotonic() - started) * 1000)
        if time.monotonic() - started >= timeout:
            yield {"type": "error", "message": f"Timeout dopo {int(timeout)}s", **read_report(None)}
        elif runner == "cursor" and final is not None:
            yield {"type": "result", "is_error": bool(final.get("is_error")),
                   "duration_ms": final.get("duration_ms", duration), "total_cost_usd": None,
                   "num_turns": None, **read_report(final.get("result"))}
        elif code == 0:
            report = last_message.read_text(encoding="utf-8") if last_message.is_file() else "\n".join(texts)
            yield {"type": "result", "is_error": False, "duration_ms": duration, "total_cost_usd": None,
                   "num_turns": None, **read_report(report)}
        else:
            yield {"type": "error", "message": f"{RUNNERS[runner]['label']} uscito con codice {code}: {err_tail}",
                   **read_report(None)}


# ---------------------------------------------------------------------------
# Streaming: stesso contratto di agent_bridge.run_agent_streaming
# ---------------------------------------------------------------------------
def _pump(events, out: queue.Queue, feature, attempt_id, on_finish, project=None) -> None:
    from core.pipeline_activity import track
    outcome = {"type": "error", "message": "Esecuzione interrotta", **read_report(None)}
    try:
        with track(feature, attempt_id, project=project):
            for event in events:
                if event["type"] in ("result", "error"):
                    outcome = event
                out.put(event)
    except Exception as exc:  # noqa: BLE001 — l'errore va riportato al client
        outcome = {"type": "error", "message": f"{type(exc).__name__}: {exc}", **read_report(None)}
        out.put(outcome)
    finally:
        agent_bridge._finish(out, outcome, on_finish)


def run_streaming(runner: str, prompt: str, mode: str, model: str, *, feature=None, attempt_id=None,
                  on_finish=None, project=None):
    if reason := validate_run(runner, mode, model, project=project):
        raise ValueError(reason)
    if runner == "claude":
        return agent_bridge.run_agent_streaming(prompt, mode, model or "sonnet", feature=feature,
                                                attempt_id=attempt_id, on_finish=on_finish, project=project)
    roots = {}
    if project is not None:
        roots["project_root"] = project.root
        roots["code_root"] = project.code_dir
    if runner == "local":
        events = run_local(prompt, mode, model, **roots, registry=ProjectRegistry(readonly=True))
    else:
        events = run_cli(runner, prompt, mode, model, **roots)
    out: queue.Queue = queue.Queue()
    threading.Thread(target=_pump, args=(events, out, feature, attempt_id, on_finish, project),
                     name=f"agent-runner-{runner}", daemon=True).start()

    def consume():
        while (event := out.get()) is not None:
            yield json.dumps(event, ensure_ascii=False) + "\n"
    return consume()

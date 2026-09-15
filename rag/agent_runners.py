"""Runner alternativi a Claude Code per POST /api/pipeline/agent/run: LLM locale via
Ollama e CLI esterne (Codex, Cursor). Emettono lo stesso NDJSON di agent_bridge
(text / tool_use / result / error) e ne condividono ammissione, tracking e chiusura.

Perimetri, runner per runner:
  - local : i tool li esegue VibeCraft, non il modello, e non esiste shell. Letture solo
            dentro PROJECT_ROOT (niente .git né file .env*); in agentic le scritture passano
            da agent_bridge._path_escapes_code, la stessa decisione testata dell'hook Claude.
  - codex : solo suggest/oneshot, `codex exec --sandbox read-only`.
  - cursor: solo suggest/oneshot, `agent -p` senza --force: per la documentazione Cursor le
            modifiche restano proposte. Non verificato dai nostri test.
Agentic resta a claude e local perché il confinamento delle scritture delle CLI esterne
non è verificabile qui. Il prompt va sempre su stdin, mai negli argomenti: gli shim .cmd
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
from agent_bridge import CODE_ROOT, PROJECT_ROOT, _path_escapes_code
from core import llm
from core.config import OLLAMA_TIMEOUT_SECONDS, OLLAMA_URL, config
from core.open_points import read_report

RUNNERS: dict[str, dict] = {
    "claude": {"label": "Claude Code", "modes": ("suggest", "agentic", "oneshot"), "bin": "claude"},
    "local": {"label": "LLM locale (Ollama)", "modes": ("suggest", "agentic", "oneshot")},
    "codex": {"label": "Codex CLI", "modes": ("suggest", "oneshot"), "bin": "codex"},
    "cursor": {"label": "Cursor CLI", "modes": ("suggest", "oneshot"), "bin": "agent"},
}
CLAUDE_MODELS = ["sonnet", "opus", "haiku"]
# Il modello finisce negli argomenti delle CLI: niente '-' iniziale (flag) né metacaratteri.
MODEL_RE = re.compile(r"^(|[A-Za-z0-9][\w.:/-]{0,99})$")

_TOOL_OUTPUT_CHARS = 6000  # num_ctx 16K: un solo file grande non deve saturare la finestra
_LIST_LIMIT = 200
_GREP_LIMIT = 100
_SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}


def validate_run(runner: str, mode: str, model: str) -> str | None:
    """Motivo del rifiuto (400) o None."""
    if runner not in RUNNERS:
        return f"Runner non valido: {runner!r}. Validi: {list(RUNNERS)}"
    if mode not in RUNNERS[runner]["modes"]:
        return f"{RUNNERS[runner]['label']} non supporta la modalità {mode!r}."
    if not MODEL_RE.match(model or ""):
        return f"Nome modello non valido: {model!r}"
    return None


def list_runners() -> list[dict]:
    """Runner con disponibilità reale sulla macchina del server (PATH e modelli Ollama)."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL.rstrip('/')}/api/tags", timeout=2) as r:
            local_models = [m["name"] for m in json.loads(r.read().decode()).get("models", [])]
    except (OSError, ValueError, KeyError):
        local_models = []
    out = []
    for rid, cfg in RUNNERS.items():
        if rid == "local":
            available, models = bool(local_models), local_models
        else:
            available = shutil.which(cfg["bin"]) is not None
            models = CLAUDE_MODELS if rid == "claude" else []
        out.append({"id": rid, "label": cfg["label"], "modes": list(cfg["modes"]),
                    "available": available, "models": models})
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


def _resolve_read(path_str: str, cwd: Path, project_root: Path) -> Path:
    root = project_root.resolve()
    raw = Path(path_str or ".")
    p = (raw if raw.is_absolute() else cwd / raw).resolve()
    if p != root and root not in p.parents:
        raise PermissionError(f"fuori dal progetto: {p}")
    parts = {part.lower() for part in p.relative_to(root).parts}
    if ".git" in parts or any(part.startswith(".env") for part in parts):
        raise PermissionError(f"area riservata: {p}")
    return p


def _write_target(path_str: str, code_root: Path) -> Path:
    reason = _path_escapes_code(path_str, code_root)
    if reason:
        raise PermissionError(reason)
    raw = Path(path_str)
    return (raw if raw.is_absolute() else code_root.resolve() / raw).resolve()


def execute_tool(name: str, args: dict, *, mode: str, project_root: Path = PROJECT_ROOT,
                 code_root: Path = CODE_ROOT) -> str:
    """Esegue un tool chiesto dal modello. Ogni errore torna al modello come testo."""
    if name not in {t["function"]["name"] for t in tool_specs(mode)}:
        return f"negato: tool {name!r} non disponibile in modalità {mode}"
    cwd = code_root if mode == "agentic" else project_root
    try:
        if name == "read_file":
            text = _resolve_read(args.get("path", ""), cwd, project_root).read_text(
                encoding="utf-8", errors="replace")
        elif name == "list_files":
            base = _resolve_read(args.get("path", "."), cwd, project_root)
            found = []
            for f in base.glob(args.get("pattern") or "**/*"):
                if len(found) >= _LIST_LIMIT:
                    break
                try:
                    # Anche le cartelle (con '/' finale): senza, un modello non sa dove scendere.
                    found.append(str(_resolve_read(str(f), cwd, project_root)) + ("/" if f.is_dir() else ""))
                except PermissionError:
                    continue
            text = "\n".join(found) or "(nessuna voce)"
        elif name == "grep":
            base = _resolve_read(args.get("path", "."), cwd, project_root)
            rx = re.compile(args.get("pattern", ""))
            hits = []
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
                for fname in filenames:
                    f = Path(dirpath) / fname
                    if fname.startswith(".env") or f.stat().st_size > 1_000_000:
                        continue
                    for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                        if rx.search(line):
                            hits.append(f"{f}:{n}: {line.strip()[:200]}")
                            if len(hits) >= _GREP_LIMIT:
                                return "\n".join(hits)
            text = "\n".join(hits) or "(nessuna corrispondenza)"
        elif name == "write_file":
            target = _write_target(args.get("path", ""), code_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(args.get("content", ""), encoding="utf-8")
            text = f"scritto {target}"
        else:  # edit_file
            target = _write_target(args.get("path", ""), code_root)
            current = target.read_text(encoding="utf-8")
            old = args.get("old", "")
            if not old or current.count(old) != 1:
                return "errore: il testo da sostituire deve comparire esattamente una volta"
            target.write_text(current.replace(old, args.get("new", "")), encoding="utf-8")
            text = f"modificato {target}"
    except PermissionError as exc:
        return f"negato: {exc}"
    except (OSError, ValueError, re.error) as exc:
        return f"errore: {exc}"
    if len(text) > _TOOL_OUTPUT_CHARS:
        text = text[:_TOOL_OUTPUT_CHARS] + f"\n[troncato: {len(text)} caratteri totali]"
    return text


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
              project_root: Path = PROJECT_ROOT, code_root: Path = CODE_ROOT):
    """Loop di tool su Ollama. Solo l'ultimo messaggio senza tool call vale come report,
    come in agent_bridge."""
    model = model or (config.get("llm_settings") or {}).get("models", {}).get("ollama", "")
    tools = tool_specs(mode)
    turns = 1 if mode == "oneshot" else agent_bridge._max_turns()
    cwd = code_root if mode == "agentic" else project_root
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
                                                     project_root=project_root, code_root=code_root)})
    yield {"type": "error", "message": f"Limite di {turns} turni raggiunto senza risposta finale",
           **read_report(None)}


# ---------------------------------------------------------------------------
# CLI esterne
# ---------------------------------------------------------------------------
def cli_command(runner: str, model: str, cwd: Path, last_message: Path) -> list[str]:
    exe = shutil.which(RUNNERS[runner]["bin"])
    if not exe:
        raise RuntimeError(f"'{RUNNERS[runner]['bin']}' non trovato nel PATH: installa {RUNNERS[runner]['label']}.")
    if runner == "codex":
        cmd = [exe, "exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral",
               "-C", str(cwd), "--output-last-message", str(last_message)]
    else:
        cmd = [exe, "-p", "--output-format", "stream-json"]
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
            popen=subprocess.Popen):
    timeout = float(os.environ.get("VIBECRAFT_AGENT_TIMEOUT_SECONDS", "1800"))
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        last_message, stderr_path = Path(tmp) / "last.txt", Path(tmp) / "stderr.txt"
        with stderr_path.open("w+", encoding="utf-8", errors="replace") as stderr:
            proc = popen(cli_command(runner, model, project_root, last_message), cwd=project_root,
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
def _pump(events, out: queue.Queue, feature, attempt_id, on_finish) -> None:
    from core.pipeline_activity import track
    outcome = {"type": "error", "message": "Esecuzione interrotta", **read_report(None)}
    try:
        with track(feature, attempt_id):
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
                  on_finish=None):
    if reason := validate_run(runner, mode, model):
        raise ValueError(reason)
    if runner == "claude":
        return agent_bridge.run_agent_streaming(prompt, mode, model or "sonnet", feature=feature,
                                                attempt_id=attempt_id, on_finish=on_finish)
    events = run_local(prompt, mode, model) if runner == "local" else run_cli(runner, prompt, mode, model)
    out: queue.Queue = queue.Queue()
    threading.Thread(target=_pump, args=(events, out, feature, attempt_id, on_finish),
                     name=f"agent-runner-{runner}", daemon=True).start()

    def consume():
        while (event := out.get()) is not None:
            yield json.dumps(event, ensure_ascii=False) + "\n"
    return consume()

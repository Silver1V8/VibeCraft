"""Canvas che apprende (parte 1): al momento dell'archive confronta il diff reale del
codice della change con le sezioni Operations/Structure/Safeguards del REASONS Canvas
tramite l'LLM locale e produce canvas_review.md (divergenze, sezioni accurate, giudizio
di fedeltà). Logica pura e iniettabile: il chiamante (core/indexing.archive_feature)
decide dove salvare il file e come reagire se l'LLM non è raggiungibile."""
import json
import re
import subprocess
import urllib.request
from pathlib import Path

from core.config import (
    OLLAMA_TIMEOUT_SECONDS,
    PIPELINE_MODEL_NAME,
    PIPELINE_OLLAMA_URL,
    PROJECT_ROOT,
)

# Le sezioni del Canvas confrontate con il codice: cosa fa (Operations), come è
# organizzato (Structure) e quali protezioni promette (Safeguards).
REVIEW_SECTIONS = ("Operations", "Structure", "Safeguards")
REVIEW_FILENAME = "canvas_review.md"
# Sottocartella di docs/ dove la review diventa contesto storico indicizzabile.
HISTORICAL_SUBDIR = "03_changes_historical"

# Estensioni considerate "codice della change" quando si legge dai file di tasks.md.
_CODE_EXTS = (".js", ".ts", ".tsx", ".py", ".html", ".css")


def extract_canvas_sections(canvas_text: str, names: tuple[str, ...] = REVIEW_SECTIONS) -> str:
    """Estrae dal canvas solo le sezioni `## <nome>` richieste (corpo incluso, fino
    alla sezione successiva). Restituisce il testo concatenato, o '' se nessuna trovata."""
    parts: list[str] = []
    for name in names:
        match = re.search(
            rf"^(#{{1,3}}\s*(?:\d+[\.\)]\s*)?{name}\b.*?)(?=^#{{1,3}}\s|\Z)",
            canvas_text, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
        )
        if match:
            parts.append(match.group(1).strip())
    return "\n\n".join(parts)


def _git(args: list[str], cwd: Path) -> str:
    """Esegue un comando git restituendo lo stdout; '' su qualunque errore (repo
    assente, ref inesistente...): il chiamante ha sempre un fallback non-git."""
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def _tasks_file_paths(tasks_text: str) -> list[str]:
    """Estrae da tasks.md i percorsi di file di codice citati (token con '/' ed
    estensione riconosciuta, con o senza backtick)."""
    candidates = re.findall(r"[\w./\\-]+\.\w+", tasks_text)
    return [c for c in candidates if "/" in c.replace("\\", "/") and c.endswith(_CODE_EXTS)]


def collect_change_diff(feature_folder: str, change_dir: Path, repo_root: Path = PROJECT_ROOT) -> str:
    """Raccoglie il diff reale del codice associato alla change.

    Strategia: 1) git diff tra il primo e l'ultimo commit il cui messaggio cita lo
    slug della feature; 2) fallback sul contenuto corrente dei file elencati in
    tasks.md; 3) stringa vuota se non c'è nulla di ricostruibile.
    """
    shas = _git(["log", "--reverse", "--format=%H", "-i", f"--grep={feature_folder}"], repo_root).split()
    if shas:
        first, last = shas[0], shas[-1]
        base = _git(["rev-parse", f"{first}^"], repo_root).strip()
        diff = _git(["diff", base, last], repo_root) if base else _git(["show", "--format=", last], repo_root)
        if diff.strip():
            return diff

    tasks_path = change_dir / "tasks.md"
    if tasks_path.exists():
        pieces = []
        for rel in _tasks_file_paths(tasks_path.read_text(encoding="utf-8")):
            p = repo_root / rel.replace("\\", "/")
            if p.is_file():
                pieces.append(f"--- FILE: {rel} ---\n{p.read_text(encoding='utf-8')}")
        if pieces:
            return "\n\n".join(pieces)

    return ""


def build_canvas_review_prompt(feature_folder: str, canvas_sections: str, code_diff: str) -> str:
    """Prompt deterministico per il confronto canvas <-> codice all'archive."""
    return f"""
Sei un Revisore Tecnico. La feature '{feature_folder}' sta per essere archiviata.
Confronta il contratto di design (sezioni Operations, Structure e Safeguards del
REASONS Canvas) con le modifiche reali al codice.

--- SEZIONI DEL CANVAS ---
{canvas_sections if canvas_sections else "(sezioni Operations/Structure/Safeguards non trovate nel canvas)"}

--- MODIFICHE REALI AL CODICE (diff o file della change) ---
{code_diff if code_diff else "(nessun diff o file di codice ricostruibile per questa change)"}

Produci un report in italiano, in Markdown, con ESATTAMENTE queste tre sezioni:

## Divergenze
Elenca cosa il codice fa che il canvas non prevedeva, e cosa il canvas prevedeva
che il codice non fa. Se non ci sono divergenze, scrivi "Nessuna divergenza rilevata."

## Sezioni accurate
Indica quali tra Operations, Structure e Safeguards sono risultate fedeli al codice.

## Fedeltà
Un giudizio sintetico su una sola riga: "Fedeltà: alto", "Fedeltà: medio" o "Fedeltà: basso",
seguito da una frase di motivazione.
"""


def _call_llm_sync(prompt: str) -> str:
    """Chiamata sincrona al layer LLM locale (stesso endpoint/modello della pipeline).
    A differenza dei chiamanti della pipeline, QUI gli errori si propagano: l'archive
    deve poter distinguere 'LLM non raggiungibile' e saltare la review con un warning."""
    data = {"model": PIPELINE_MODEL_NAME, "prompt": prompt, "stream": False}
    req = urllib.request.Request(
        PIPELINE_OLLAMA_URL, data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
        result = json.loads(response.read().decode())
    text = result.get("response", "").strip()
    if not text:
        raise RuntimeError("risposta vuota dal modello")
    return text


def generate_canvas_review(feature_folder: str, change_dir: Path,
                           repo_root: Path = PROJECT_ROOT, llm=None) -> tuple[str | None, str | None]:
    """Genera il contenuto di canvas_review.md per la change in archiviazione.

    Restituisce (contenuto, None) in caso di successo oppure (None, warning) se la
    review va saltata (canvas assente o LLM non raggiungibile). Non solleva mai:
    l'archive non deve fallire per colpa della review.
    """
    canvas_path = change_dir / "canvas.md"
    if not canvas_path.exists():
        return None, "canvas.md assente: nessun contratto da confrontare con il codice."

    try:
        canvas_text = canvas_path.read_text(encoding="utf-8")
        sections = extract_canvas_sections(canvas_text)
        diff = collect_change_diff(feature_folder, change_dir, repo_root)
        prompt = build_canvas_review_prompt(feature_folder, sections, diff)
        review = (llm or _call_llm_sync)(prompt)
    except Exception as e:
        return None, f"LLM non raggiungibile o review fallita: {e}"

    content = (
        f"# Canvas Review: {feature_folder}\n\n"
        f"Confronto automatico canvas <-> codice eseguito all'archiviazione della change.\n\n"
        f"{review.strip()}\n"
    )
    return content, None

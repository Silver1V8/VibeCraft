"""Canvas che apprende (parte 1): al momento dell'archive confronta il diff reale del
codice della change con le sezioni Operations/Structure/Safeguards del REASONS Canvas
tramite l'LLM locale e produce canvas_review.md (divergenze, sezioni accurate, giudizio
di fedeltà). Logica pura e iniettabile: il chiamante (core/feature_archive.archive_feature)
decide dove salvare il file e come reagire se l'LLM non è raggiungibile."""
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from core.projects import _unlinked, ProjectError

import yaml

from code_index import CODE_EXTS
from core import llm
from core.config import OLLAMA_NUM_CTX, PROJECT_ROOT, RAG_DIR

# Le sezioni del Canvas confrontate con il codice: cosa fa (Operations), come è
# organizzato (Structure) e quali protezioni promette (Safeguards).
REVIEW_SECTIONS = ("Operations", "Structure", "Safeguards")
REVIEW_FILENAME = "canvas_review.md"
# Sottocartella di docs/ dove la review diventa contesto storico indicizzabile.
HISTORICAL_SUBDIR = "03_changes_historical"

# Estensioni considerate "codice della change" quando si legge dai file di tasks.md.
_CODE_EXTS = tuple(CODE_EXTS)


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
    # Solo i commit che citano lo slug nel SUBJECT come parola intera: --grep cerca anche
    # nel corpo, e un commit di vibecraft che nomina "BE1" come banco di prova veniva
    # scambiato per il codice della change BE1 (83 KB di diff estraneo).
    git_root = _git(["rev-parse", "--show-toplevel"], repo_root).strip()
    owns_repository = bool(git_root) and Path(git_root).resolve() == _unlinked(repo_root)
    log_out = (_git(["log", "--reverse", "--format=%H %s", "-i", f"--grep={feature_folder}"], repo_root)
               if owns_repository else "")
    word = re.compile(rf"(?<![\w-]){re.escape(feature_folder)}(?![\w-])", re.IGNORECASE)
    shas = [sha for sha, _, subject in (line.partition(" ") for line in log_out.splitlines())
            if word.search(subject)]
    if shas:
        first, last = shas[0], shas[-1]
        base = _git(["rev-parse", f"{first}^"], repo_root).strip()
        diff = _git(["diff", base, last], repo_root) if base else _git(["show", "--format=", last], repo_root)
        if diff.strip():
            return diff

    tasks_path = _unlinked(change_dir / "tasks.md")
    if tasks_path.exists():
        pieces = []
        for rel in _tasks_file_paths(tasks_path.read_text(encoding="utf-8")):
            p = _unlinked(repo_root / rel.replace("\\", "/"))
            if not p.is_relative_to(_unlinked(repo_root)):
                raise ProjectError("Review task path outside project")
            if p.is_file():
                pieces.append(f"--- FILE: {rel} ---\n{p.read_text(encoding='utf-8')}")
        if pieces:
            return "\n\n".join(pieces)

    return ""


def build_canvas_review_prompt(feature_folder: str, canvas_sections: str, code_diff: str,
                               spec: str = "") -> str:
    """Prompt deterministico per il confronto canvas <-> codice all'archive. La spec
    (scenari Gherkin) ha precedenza sul canvas, come nel check drift: senza, una regola
    imposta da uno scenario ma non nominata dal canvas (su BE1 la capienza minima 5 di S04)
    veniva riportata come divergenza del codice."""
    spec_block = f"""
--- SPEC DELLA FEATURE (scenari; ha PRECEDENZA sul canvas) ---
{spec}
""" if spec.strip() else ""
    return f"""
Sei un Revisore Tecnico. La feature '{feature_folder}' sta per essere archiviata.
Confronta il contratto di design (sezioni Operations, Structure e Safeguards del
REASONS Canvas) con le modifiche reali al codice.
Il codice che implementa una regola richiesta dalla spec NON è una divergenza, anche se
il canvas non la nomina: segnalala semmai come lacuna del canvas.

--- SEZIONI DEL CANVAS ---
{canvas_sections if canvas_sections else "(sezioni Operations/Structure/Safeguards non trovate nel canvas)"}
{spec_block}
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


def is_review_doc(doc_id: str) -> bool:
    """True se il doc_id (percorso relativo a docs/) è la copia storica di una
    canvas review archiviata (scritta da archive_feature in 03_changes_historical/)."""
    normalized = doc_id.replace("\\", "/")
    return normalized.startswith(HISTORICAL_SUBDIR) and normalized.endswith("-canvas-review.md")


# Sezioni delle review usate come "lezioni": i punti ciechi (Divergenze) e il
# giudizio sintetico (Fedeltà) — le sezioni accurate non insegnano nulla di nuovo.
_LESSON_SECTIONS = ("divergenze", "fedeltà", "fedelta")


def retrieve_canvas_lessons(query: str, *, qdrant, embed_model, colbert_store,
                            chunks_store: dict, top_n: int = 3, top_k: int = 12,
                            max_chars_per_doc: int = 1500, search=None, project=None, collection_name=None) -> str:
    """Recupera le "lezioni dalle change precedenti" per la generazione di un nuovo canvas:
    dalle canvas review archiviate più simili all'intent corrente (retrieval semantico
    esistente) estrae Divergenze e giudizio di Fedeltà. Restituisce '' se non ci sono
    review indicizzate o risorse pronte: il flusso canvas resta identico senza review.
    `search` è iniettabile nei test al posto di retrieval.hybrid_search."""
    if not chunks_store or qdrant is None or embed_model is None:
        return ""
    from core import retrieval  # import locale: evita il ciclo canvas_review <-> retrieval
    try:
        results = (search or retrieval.hybrid_search)(
            query, top_k, qdrant=qdrant, embed_model=embed_model, colbert_store=colbert_store,
            **({"project": project, "collection_name": collection_name or project.collection_name} if project else {}),
        )
    except Exception:
        return ""  # retrieval non disponibile: nessuna lezione, nessun errore

    review_docs: list[str] = []
    for r in results:
        d = r.get("doc_id", "")
        if is_review_doc(d) and d not in review_docs:
            review_docs.append(d)
        if len(review_docs) >= top_n:
            break
    if not review_docs:
        return ""

    parts: list[str] = []
    for doc_id in review_docs:
        body = "\n".join(
            entry["text"] for entry in chunks_store.values()
            if entry.get("doc_id") == doc_id
            and str(entry.get("section", "")).strip().lower().startswith(_LESSON_SECTIONS)
        ).strip()
        if not body:
            continue
        if len(body) > max_chars_per_doc:
            body = body[:max_chars_per_doc].rstrip() + "\n… [troncato] …"
        feature = Path(doc_id).name.removesuffix("-canvas-review.md")
        parts.append(f"--- Lezioni dalla change '{feature}' ({doc_id}) ---\n{body}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Canvas quality: parsing delle review archiviate per il pannello di governance
# ---------------------------------------------------------------------------

_FIDELITY_RE = re.compile(r"Fedelt[aà]\s*:\s*(alto|medio|basso)", re.IGNORECASE)


def parse_fidelity(review_text: str) -> str | None:
    """Estrae il giudizio sintetico ('alto'/'medio'/'basso') da una canvas review."""
    m = _FIDELITY_RE.search(review_text)
    return m.group(1).lower() if m else None


# Marcatore di elenco ("- ", "*   ", "• ", "1. "): solo questo va tolto. Lo strip dei
# caratteri "-*•" mangiava anche il "**" del grassetto iniziale, e il pannello mostrava
# "canvas vs codice (…):**".
_BULLET_RE = re.compile(r"^(?:[-*•+]|\d+[.)])\s+")
# Riga fatta solo di grassetto, con i due punti dentro o fuori: è il titolo di un gruppo
# ("**Codice vs Canvas (…):**"), non una divergenza. Contarla la faceva risultare la
# divergenza più frequente, presente in ogni review.
_GROUP_HEADING_RE = re.compile(r"\*\*[^*]+\*\*:?")
# Linea orizzontale Markdown ("---", "***", "- - -"): separatore, non contenuto.
_HORIZONTAL_RULE_RE = re.compile(r"(?:[-*_]\s*){3,}")


def parse_divergences(review_text: str) -> list[str]:
    """Estrae le voci della sezione '## Divergenze' di una review (esclusi i
    'nessuna divergenza' e i titoli di gruppo in grassetto), come frasi su una riga
    con il Markdown in linea intatto."""
    m = re.search(r"^#{1,3}\s*Divergenze\b.*?\n(.*?)(?=^#{1,3}\s|\Z)",
                  review_text, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if not m:
        return []
    out = []
    for line in m.group(1).splitlines():
        if _HORIZONTAL_RULE_RE.fullmatch(line.strip()):
            continue
        stripped = _BULLET_RE.sub("", line.strip(), count=1).strip()
        if (stripped and not _GROUP_HEADING_RE.fullmatch(stripped)
                and "nessuna divergenza" not in stripped.lower()):
            out.append(stripped)
    return out


def canvas_quality_stats(archive_dir: Path, last_n: int = 10) -> dict:
    """Dati per il pannello 'Canvas quality': trend del giudizio di fedeltà delle
    ultime `last_n` change archiviate (dalla più vecchia alla più recente) e le
    divergenze più frequenti tra le loro review. Robusto ad archive vuoto/assente."""
    reviews: list[tuple[float, str, str]] = []  # (mtime, feature, testo)
    archive_dir = _unlinked(archive_dir)
    if archive_dir.exists():
        for review_path in archive_dir.glob(f"*/{REVIEW_FILENAME}"):
            review_path = _unlinked(review_path)
            try:
                reviews.append((review_path.stat().st_mtime, review_path.parent.name,
                                review_path.read_text(encoding="utf-8")))
            except Exception:
                continue
    reviews.sort(key=lambda t: t[0])
    reviews = reviews[-last_n:]

    trend = []
    divergence_counts: dict[str, int] = {}
    # Il conteggio raggruppa senza distinguere maiuscole; il testo mostrato è la prima
    # forma incontrata, con le maiuscole originali (sigle, nomi di classi).
    divergence_text: dict[str, str] = {}
    fidelity_counts = {"alto": 0, "medio": 0, "basso": 0, "sconosciuto": 0}
    for mtime, feature, text in reviews:
        fidelity = parse_fidelity(text) or "sconosciuto"
        fidelity_counts[fidelity] += 1
        trend.append({"feature": feature, "fidelity": fidelity})
        for d in parse_divergences(text):
            shown = re.sub(r"\s+", " ", d).strip().rstrip(".")
            key = shown.lower()
            divergence_counts[key] = divergence_counts.get(key, 0) + 1
            divergence_text.setdefault(key, shown)

    top_divergences = [
        {"text": divergence_text[k], "count": c}
        for k, c in sorted(divergence_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    ]
    return {
        "total_reviews": len(reviews),
        "trend": trend,  # dalla più vecchia alla più recente
        "fidelity_counts": fidelity_counts,
        "top_divergences": top_divergences,
    }


# ---------------------------------------------------------------------------
# Golden-set che cresce dalle change: candidato di eval estratto all'archive
# ---------------------------------------------------------------------------

# Candidati per il golden-set di eval: append-only, MAI promossi automaticamente.
# La promozione in eval/golden_set.yaml è una revisione umana (eval.run --review-candidates).
EVAL_CANDIDATES_PATH = RAG_DIR / "eval" / "candidates.yaml"


def canvas_first_line(canvas_text: str) -> str:
    """Prima riga significativa del canvas (senza marcatori '#'), usata come intent."""
    for line in canvas_text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped
    return ""


def extract_eval_candidate(feature_folder: str, change_dir: Path) -> dict | None:
    """Estrae in modo DETERMINISTICO (nessun LLM/embedding) un caso candidato per il
    golden-set di eval dalla change in archiviazione: la query è l'intento della feature
    (nome + prima riga del canvas), gli expected sono i documenti normativi che il
    retrieval governato ha effettivamente usato per generare quel canvas (persistiti in
    meta.json da save_governed_sources). None se manca il canvas o le sorgenti."""
    canvas_path = _unlinked(change_dir / "canvas.md")
    meta_path = _unlinked(change_dir / "meta.json")
    if not canvas_path.exists() or not meta_path.exists():
        return None
    try:
        first_line = canvas_first_line(canvas_path.read_text(encoding="utf-8"))
        sources = json.loads(meta_path.read_text(encoding="utf-8")).get("governed_sources") or []
    except Exception:
        return None
    if not sources:
        return None
    query = feature_folder if not first_line else f"{feature_folder}: {first_line}"
    return {
        "q": query,
        "expected": [{"doc": str(d)} for d in sources],
        "from_feature": feature_folder,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def append_eval_candidate(candidate: dict, path: Path = EVAL_CANDIDATES_PATH) -> bool:
    """Accoda il candidato a eval/candidates.yaml (creandolo se assente). Dedup per
    query: se un candidato con la stessa `q` esiste già non viene riproposto.
    Restituisce True se il candidato è stato aggiunto."""
    path = _unlinked(path)
    data = {"candidates": []}
    if path.exists():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            data["candidates"] = loaded.get("candidates") or []
        except Exception:
            pass  # file corrotto: si riparte da lista vuota senza bloccare l'archive
    if any(c.get("q") == candidate["q"] for c in data["candidates"]):
        return False
    data["candidates"].append(candidate)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Candidati per eval/golden_set.yaml estratti all'archive delle change.\n"
        "# NON usati dall'eval: la promozione è una revisione umana\n"
        "# (uv run python -m eval.run --review-candidates [--promote N ...]).\n"
        + yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return True


def _call_llm_sync(prompt: str) -> str:
    """Chiamata sincrona al layer LLM (core/llm.py, purpose 'review'). A differenza
    dei chiamanti della pipeline, QUI gli errori si propagano (LLMError): l'archive
    deve poter distinguere 'LLM non raggiungibile' e saltare la review con un warning."""
    text = llm.generate(prompt, purpose="review").strip()
    if not text:
        raise RuntimeError("risposta vuota dal modello")
    return text


def generate_canvas_review(feature_folder: str, change_dir: Path,
                           repo_root: Path = PROJECT_ROOT, llm=None,
                           code: str | None = None) -> tuple[str | None, str | None]:
    """Genera il contenuto di canvas_review.md per la change in archiviazione.

    `code` è il codice che il check drift analizza (cartella della change + code/<dev_type>):
    anche vuoto ha la precedenza sul diff git. Solo None richiede il fallback storico.

    Restituisce (contenuto, None) in caso di successo oppure (None, warning) se la
    review va saltata (canvas assente o LLM non raggiungibile). Non solleva mai:
    l'archive non deve fallire per colpa della review.
    """
    canvas_path = _unlinked(change_dir / "canvas.md")
    if not canvas_path.exists():
        return None, "canvas.md assente: nessun contratto da confrontare con il codice."

    try:
        canvas_text = canvas_path.read_text(encoding="utf-8")
        sections = extract_canvas_sections(canvas_text)
        spec_path = _unlinked(change_dir / "spec.md")
        spec = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
        diff = collect_change_diff(feature_folder, change_dir, repo_root) if code is None else code
        prompt = build_canvas_review_prompt(feature_folder, sections, diff, spec)
        if OLLAMA_NUM_CTX and len(diff) > 0:
            # Stessa stima del guardrail di core/llm.py (~3 caratteri/token): il diff
            # riempie al più il 60% della finestra, il resto va a prompt e generazione.
            # ponytail: taglio in coda, un riassunto per file se le review parziali non bastano
            room = int(OLLAMA_NUM_CTX * 3 * 0.6) - (len(prompt) - len(diff))
            if len(diff) > room:
                diff = diff[:max(room, 0)] + "\n… [diff troncato: supera la finestra di contesto] …"
                prompt = build_canvas_review_prompt(feature_folder, sections, diff, spec)
        review = (llm or _call_llm_sync)(prompt)
    except Exception:
        return None, "LLM non raggiungibile o review fallita: consulta il log del server."

    content = (
        f"# Canvas Review: {feature_folder}\n\n"
        f"Confronto automatico canvas <-> codice eseguito all'archiviazione della change.\n\n"
        f"{review.strip()}\n"
    )
    return content, None

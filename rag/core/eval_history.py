"""Storico della qualità del retrieval (Epic 5). Ogni valutazione — manuale (eval.run) o
automatica (eval-gate alla promozione) — appende una riga a eval/results/history.jsonl. Così la
recall@k nel tempo e per-versione diventa un trend leggibile: le regressioni lente (non solo i
tuffi sotto la soglia del gate) diventano un segnale, non una scoperta accidentale.

Append-only: NON riscrive i JSON puntuali di eval/results/, aggiunge solo. Best-effort: un errore
di I/O non deve mai far fallire un'eval o un build."""
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

RAG_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = RAG_DIR / "eval" / "results"
HISTORY_PATH = RESULTS_DIR / "history.jsonl"

_TREND_EPS = 0.005  # variazione minima di recall per non essere "flat" (mezzo punto percentuale)


def _git_commit() -> str | None:
    """Hash breve del commit corrente (best-effort: None se git non è disponibile)."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAG_DIR,
                             capture_output=True, text=True, timeout=3)
        return out.stdout.strip() or None
    except Exception:
        return None


def record_history(recall: dict, *, n_cases: int, version, source: str,
                   gate: dict | None = None, path: Path | None = None) -> dict:
    """Appende una riga di storico. `recall` è {"recall@5": .., "recall@10": ..}; `source` è
    'eval.run' o 'gate'; `gate` (opzionale) porta l'esito del gate (passed/min_recall). `path` è
    risolto a runtime così i test lo reindirizzano."""
    path = path if path is not None else HISTORY_PATH
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commit": _git_commit(),
        "version": version,
        "recall": recall,
        "n_cases": n_cases,
        "source": source,
    }
    if gate is not None:
        entry["gate"] = gate
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Impossibile scrivere lo storico eval: %s", exc)
    return entry


def load_history(limit: int | None = None, path: Path | None = None) -> list[dict]:
    """Righe dello storico in ordine cronologico (le ultime `limit` se indicato); [] se assente."""
    path = path if path is not None else HISTORY_PATH
    try:
        rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except (OSError, json.JSONDecodeError):
        return []
    return rows[-limit:] if limit else rows


def _series(key: str, path: Path | None = None) -> list[float]:
    return [e["recall"][key] for e in load_history(path=path)
            if isinstance(e.get("recall"), dict) and key in e["recall"]]


def latest_recall(key: str = "recall@10", path: Path | None = None) -> float | None:
    """Ultimo valore registrato di `key`, o None se lo storico non ne ha."""
    series = _series(key, path=path)
    return series[-1] if series else None


def compute_trend(key: str = "recall@10", window: int = 5, path: Path | None = None) -> str:
    """'up' / 'flat' / 'down' confrontando l'ultimo valore con la media mobile dei `window`
    precedenti. 'flat' se non ci sono abbastanza dati o la variazione è entro _TREND_EPS."""
    series = _series(key, path=path)
    if len(series) < 2:
        return "flat"
    last = series[-1]
    prev = series[-(window + 1):-1] or series[:-1]
    avg = sum(prev) / len(prev)
    if last > avg + _TREND_EPS:
        return "up"
    if last < avg - _TREND_EPS:
        return "down"
    return "flat"


def detect_regression(key: str = "recall@10", *, window: int = 5, floor: float | None = None,
                      min_drop: float = 0.03, path: Path | None = None) -> dict | None:
    """Rileva una regressione di qualità: ritorna un riassunto se l'ultima recall è sotto `floor`
    OPPURE è calata di più di `min_drop` rispetto alla media mobile dei `window` valori precedenti;
    None se tutto ok o se i dati sono insufficienti. È il segnale del check notturno (Epic 5.2):
    non solo i tuffi sotto la soglia del gate, ma anche le derive lente."""
    series = _series(key, path=path)
    if len(series) < 2:
        return None
    last = series[-1]
    prev = series[-(window + 1):-1] or series[:-1]
    avg = sum(prev) / len(prev)
    below_floor = floor is not None and last < floor
    sustained_drop = last < avg - min_drop
    if not (below_floor or sustained_drop):
        return None
    return {"key": key, "last": round(last, 4), "moving_avg": round(avg, 4),
            "window": len(prev), "floor": floor, "below_floor": below_floor,
            "sustained_drop": sustained_drop, "min_drop": min_drop}


def eval_health(key: str = "recall@10", path: Path | None = None) -> dict:
    """Riassunto per GET /api/health: ultima recall registrata e trend vs media mobile."""
    return {"last_recall_at_10": latest_recall(key, path=path),
            "trend": compute_trend(key, path=path),
            "history_points": len(load_history(path=path))}

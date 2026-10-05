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

from core.config import EVAL_GATE_K, EVAL_GATE_MIN_RECALL
from core.projects import _unlinked

logger = logging.getLogger(__name__)

RAG_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = RAG_DIR / "eval" / "results"
HISTORY_PATH = RESULTS_DIR / "history.jsonl"

_TREND_EPS = 0.005  # variazione minima di recall per non essere "flat" (mezzo punto percentuale)

# LA CHIAVE SEGUE IL GATE, e non è una preferenza di stile (A2b).
#
# Qui il default era `recall@10` scritto a mano, mentre `eval_gate.k` è migrata 10 → 5 → 2
# perché a ogni passo l'alert di saturazione del progetto stesso diceva che quel k aveva
# smesso di discriminare. Il cancello si è spostato, l'osservabilità no: il rilevatore di
# regressione e il numero in evidenza sulla dashboard sono rimasti su una metrica satura a
# 1.000, cioè su un valore che non può scendere e quindi non può segnalare nulla. La
# promozione era difesa, la deriva lenta — che è esattamente ciò per cui lo storico esiste —
# no.
#
# Derivarla da EVAL_GATE_K significa che spostare il gate sposta anche la sorveglianza, senza
# che nessuno debba ricordarsene. Il prezzo è che la serie si accorcia quando il gate cambia
# k (le righe storiche portano la chiave del k di allora): sono punti in meno, ma di una
# misura che discrimina — e 79 punti di una metrica satura valgono meno di 22 punti veri.
#
# QUEL PREZZO SI PAGA UNA VOLTA SOLA (R12, 2026-09-07). Da qui in avanti ogni riga porta
# TUTTI i k misurati — eval.run lo faceva già, il gate e l'advisory incrementale ne
# scrivevano uno — quindi la serie del prossimo k è già popolata il giorno in cui il gate ci
# si sposta, e non c'è più nulla da azzerare. Ciò che NON succede: le righe già scritte non
# vengono riscritte. Un grafico che si allunga da oggi non è un grafico che recupera il
# passato — la serie di un k mai misurato prima parte dal 2026-09-07, non dal 2026-07-15.
#
# SECONDA DISCONTINUITÀ, STESSO GIORNO (R26, 2026-09-07). Le righe source="gate" scritte
# PRIMA di questa data misurano l'ordinamento NUDO: hybrid_search senza `restatements` (peso
# di sezione, N4) né `graph` (precedenza, S4). Da qui in avanti il gate riceve entrambi, come
# il server, e la sua riga coincide con quella di eval.run sullo stesso indice. Misurato sulla
# stessa versione e lo stesso golden set (58 casi): nudo recall@2=0.845, pieno 0.862. Il
# salto fra una riga gate del 2026-09-07 mattina e una del pomeriggio è questo, non l'indice.
GATE_RECALL_KEY = f"recall@{EVAL_GATE_K}"


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
    """Appende una riga di storico. `source` è 'eval.run', 'gate' o 'multihop'; `gate`
    (opzionale) porta l'esito del gate (passed/min_recall). `path` è risolto a runtime
    così i test lo reindirizzano.

    Nel file esiste anche source='incremental_advisory' (23 righe, 2026-07-21 → 2026-09-01):
    l'esperimento M6 che le scriveva è stato RIMOSSO il 2026-09-07 perché la sua stessa
    regola di decisione lo bocciava sul costo. Nessuno le scrive più, ma lo storico è
    append-only e restano leggibili: un consumatore che filtra per source deve aspettarsele.

    `recall` è {"recall@1": .., "recall@2": .., ..}: TUTTI i k che il chiamante ha misurato,
    non solo quello che lo interessa oggi (R12). Scrivere una chiave in più non costa nulla —
    `_series` seleziona per chiave esatta, quindi le colonne inutilizzate sono invisibili a
    chi legge — e risparmia al grafico di ripartire da zero al prossimo spostamento del gate.
    Chiavi PREFISSATE per le suite che misurano altro (vedi eval.run_multihop.history_keys):
    finiscono nello stesso file, e un "recall@10" nudo si mescolerebbe con quello del golden
    set single-hop."""
    path = _unlinked(path if path is not None else HISTORY_PATH)
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
    path = _unlinked(path if path is not None else HISTORY_PATH)
    try:
        rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except (OSError, json.JSONDecodeError):
        return []
    return rows[-limit:] if limit else rows


def _series(key: str, path: Path | None = None) -> list[float]:
    """Valori di UNA chiave lungo lo storico, in ordine cronologico. Selezione per chiave
    esatta, mai "la prima che c'è": è ciò che rende innocua una riga larga (più k) e ciò che
    tiene separate le suite che scrivono nello stesso file. Le righe che quella chiave non ce
    l'hanno — perché scritte quando il gate stava altrove — semplicemente non sono punti."""
    return [e["recall"][key] for e in load_history(path=path)
            if isinstance(e.get("recall"), dict) and key in e["recall"]]


def latest_recall(key: str = GATE_RECALL_KEY, path: Path | None = None) -> float | None:
    """Ultimo valore registrato di `key`, o None se lo storico non ne ha."""
    series = _series(key, path=path)
    return series[-1] if series else None


def compute_trend(key: str = GATE_RECALL_KEY, window: int = 5, path: Path | None = None) -> str:
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


def detect_regression(key: str = GATE_RECALL_KEY, *, window: int = 5, floor: float | None = None,
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


def eval_health(key: str = GATE_RECALL_KEY, path: Path | None = None) -> dict:
    """Riassunto per GET /api/health: ultima recall registrata e trend vs media mobile.

    `key` e `min_recall` viaggiano nel payload perché chi legge deve sapere QUALE metrica sta
    guardando e contro quale soglia: il campo si chiamava `last_recall_at_10` con il 10 nel
    nome, e la dashboard coloriva il numero contro uno 0.9 scritto a mano mentre il gate era
    già a 0.75. Un numero senza la sua chiave e la sua soglia non è osservabilità, è una cifra.

    `history_points` conta i punti DELLA SERIE, non le righe del file: è su quelli che il
    trend è calcolato, e le righe scritte quando il gate stava a un altro k non ne fanno parte."""
    return {"key": key,
            "last_recall": latest_recall(key, path=path),
            "trend": compute_trend(key, path=path),
            "history_points": len(_series(key, path=path)),
            "min_recall": EVAL_GATE_MIN_RECALL}

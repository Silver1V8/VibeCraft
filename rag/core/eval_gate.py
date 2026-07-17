"""Eval-gate continuo: misura la recall del retrieval sul golden set e decide se una nuova
versione dell'indice può essere promossa (blue/green). È il guardrail di qualità che chiude
l'anello con la calibrazione (Epic 3) e la baseline (Epic 0): una regressione del ranking non
diventa più CURRENT in silenzio, ma blocca la promozione e scrive un alert critico.

Posizionamento nel build: dopo l'upsert su Qdrant e il salvataggio della versione candidata,
PRIMA di spostare il puntatore CURRENT. Lo stato candidato (colbert_store/chunks_store) è ancora
in memoria e Qdrant contiene già i suoi vettori, quindi la valutazione riflette esattamente ciò
che il retrieval servirebbe una volta promosso — senza ricaricare artefatti.

Vincolo noto: Qdrant NON è versionato (upsert in-place). Se il gate blocca un FULL rebuild, i
vettori nuovi restano in Qdrant mentre CURRENT punta al sidecar precedente: stato degradato che
richiede indagine/rebuild (l'alert lo segnala). Perciò il gate è più prezioso come rete su una
regressione vera; per i primi build (golden set assente) è fail-open e non blocca nulla.

Nessuna dipendenza dal package eval/: il golden set è caricato via GOLDEN_SET_PATH e la metrica
da core.eval_metrics (stesso layer)."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from core import retrieval
from core.config import (
    ALERTS_PATH,
    COLLECTION_NAME,
    EVAL_GATE_BLOCKING,
    EVAL_GATE_ENABLED,
    EVAL_GATE_K,
    EVAL_GATE_MIN_RECALL,
    GOLDEN_SET_PATH,
)
from core.eval_history import record_history
from core.eval_metrics import evaluate

logger = logging.getLogger(__name__)


def load_golden_cases(path: Path = GOLDEN_SET_PATH) -> list[dict]:
    """Casi del golden set (lista di {q, expected}); [] se il file manca o è illeggibile."""
    try:
        return yaml.safe_load(Path(path).read_text(encoding="utf-8")).get("cases") or []
    except Exception:
        return []


def record_alert(level: str, message: str, *, path: Path | None = None, **details) -> dict:
    """Appende un alert a database/alerts.jsonl (stesso formato letto da GET /api/health e dai
    check notturni). Best-effort: un errore di I/O non deve far fallire il build. `path` è
    risolto a runtime (default ALERTS_PATH) così i test possono reindirizzarlo via monkeypatch."""
    path = path if path is not None else ALERTS_PATH
    alert = {"timestamp": datetime.now(timezone.utc).isoformat(), "level": level,
             "source": "eval_gate", "message": message, **details}
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(alert, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Impossibile scrivere l'alert dell'eval-gate: %s", exc)
    return alert


def evaluate_recall(qdrant, embed_model, colbert_store: dict, *, k: int = EVAL_GATE_K,
                    cases: list[dict] | None = None,
                    collection_name: str = COLLECTION_NAME) -> dict:
    """Misura recall@k del retrieval sul golden set contro (qdrant, colbert_store) dati. Riusa il
    percorso di produzione (retrieval.hybrid_search) e la metrica (core.eval_metrics.evaluate), così
    il numero del gate coincide con quello di eval.run. recall=None se non ci sono casi.

    `collection_name` (opzionale, default COLLECTION_NAME): propagata a hybrid_search. Serve
    al blue/green di Qdrant, che dovrà far valutare il gate contro la collection candidata
    invece che quella di produzione. Nessun chiamante di produzione lo passa ancora."""
    cases = cases if cases is not None else load_golden_cases()
    if not cases:
        return {"recall": None, "n": 0, "k": k}

    def _retrieve(query: str, kk: int) -> list[dict]:
        return retrieval.hybrid_search(query, kk, qdrant=qdrant, embed_model=embed_model,
                                       colbert_store=colbert_store, collection_name=collection_name)

    report = evaluate(cases, _retrieve, ks=[k])
    return {"recall": report["aggregate"][f"recall@{k}"], "n": report["n"], "k": k}


def gate_promotion(version: str, qdrant, embed_model, colbert_store: dict, *,
                   k: int = EVAL_GATE_K, min_recall: float = EVAL_GATE_MIN_RECALL,
                   blocking: bool = EVAL_GATE_BLOCKING, cases: list[dict] | None = None,
                   emit=None, collection_name: str = COLLECTION_NAME) -> dict:
    """Decide se la versione candidata può essere promossa. Restituisce un dict con almeno
    `passed` (bool) e, quando valutato, `recall`/`k`/`min_recall`/`n`.

    Fail-open: gate disattivo o golden set assente ⇒ passed=True (non blocca i build privi di
    baseline). Su regressione: scrive un alert critico; blocca la promozione solo se blocking=True
    (advisory altrimenti — promuove ma segnala).

    `collection_name` (opzionale, default COLLECTION_NAME): propagata a evaluate_recall.
    Nessun chiamante di produzione lo passa ancora."""
    _log = emit or logger.info
    if not EVAL_GATE_ENABLED:
        return {"passed": True, "skipped": "disabled", "version": version}

    try:
        res = evaluate_recall(qdrant, embed_model, colbert_store, k=k, cases=cases,
                              collection_name=collection_name)
    except Exception as exc:  # un gate che crasha NON deve bloccare un build: fail-open + warn
        _log(f"⚠️  Eval-gate non eseguito ({type(exc).__name__}: {exc}); fail-open, promozione consentita.")
        return {"passed": True, "skipped": "error", "error": str(exc), "version": version}
    res["version"] = version
    if res["recall"] is None:
        _log("ℹ️  Eval-gate saltato: golden set assente o vuoto (fail-open, promozione consentita).")
        res["passed"] = True
        res["skipped"] = "no_golden_set"
        return res

    res["min_recall"] = min_recall
    ok = res["recall"] >= min_recall
    # Storicizza ogni valutazione del gate (trend di qualità, Epic 5): source="gate".
    record_history({f"recall@{k}": res["recall"]}, n_cases=res["n"], version=version,
                   source="gate", gate={"passed": ok, "min_recall": min_recall})
    if ok:
        res["passed"] = True
        _log(f"✅ Eval-gate: recall@{k}={res['recall']:.3f} ≥ soglia {min_recall} "
             f"({res['n']} casi) — promozione consentita.")
        return res

    msg = (f"Eval-gate: recall@{k}={res['recall']:.3f} < soglia {min_recall} su {res['n']} casi. "
           f"Versione candidata {version} sotto la qualità minima.")
    record_alert("critical", msg, recall=res["recall"], k=k, threshold=min_recall, version=version)
    if blocking:
        res["passed"] = False
        _log(f"❌ {msg} PROMOZIONE BLOCCATA (CURRENT invariato). "
             f"NB: Qdrant contiene già i vettori candidati (non versionato) → indagare/rebuild.")
    else:
        res["passed"] = True
        res["advisory"] = True
        _log(f"⚠️  {msg} Modalità advisory: promuovo comunque, ma l'alert critico è stato registrato.")
    return res

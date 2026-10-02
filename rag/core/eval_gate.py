"""Eval-gate continuo: misura la recall del retrieval sul golden set e decide se una nuova
versione dell'indice può essere promossa (blue/green). È il guardrail di qualità che chiude
l'anello con la calibrazione (Epic 3) e la baseline (Epic 0): una regressione del ranking non
diventa più CURRENT in silenzio, ma blocca la promozione e scrive un alert critico.

Posizionamento nel build: dopo l'upsert su Qdrant e il salvataggio della versione candidata,
PRIMA di spostare il puntatore CURRENT. Lo stato candidato (colbert_store/chunks_store) è ancora
in memoria e Qdrant contiene già i suoi vettori, quindi la valutazione riflette esattamente ciò
che il retrieval servirebbe una volta promosso — senza ricaricare artefatti.

Vincolo noto: post-S10 un FULL rebuild scrive su una collection Qdrant CANDIDATA versionata
(mai quella di produzione); se il gate blocca la promozione, CURRENT e l'alias restano invariati
e la candidata resta su Qdrant non referenziata da alcuna versione attiva — il GC del prossimo
job/boot riuscito la rimuove, nessuno stato degradato da investigare. Il limite vero riguarda gli
INCREMENTALI: mutano in place la collection già promossa (nessuna candidata, nessun gate
bloccante), quindi un rollback blue/green intra-lineage non riavvolge i punti Qdrant scritti
da un incrementale successivo alla build a cui si torna. Per i primi build (golden set
assente) il gate è fail-open e non blocca nulla.

Nessuna dipendenza dal package eval/: il golden set è caricato via GOLDEN_SET_PATH e la metrica
da core.eval_metrics (stesso layer)."""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.projects import ProjectContext

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
from core.eval_metrics import DEFAULT_KS, evaluate

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


def evaluate_recall(qdrant, embed_model, colbert_store: Mapping, *, k: int = EVAL_GATE_K,
                    cases: list[dict] | None = None,
                    collection_name: str = COLLECTION_NAME,
                    graph=None, restatements=frozenset()) -> dict:
    """Misura recall@k del retrieval sul golden set contro (qdrant, colbert_store) dati. Riusa il
    percorso di produzione (retrieval.hybrid_search) e la metrica (core.eval_metrics.evaluate), così
    il numero del gate coincide con quello di eval.run. recall=None se non ci sono casi.

    `graph` e `restatements` sono gli stessi due argomenti che api/routes_retrieval passa a
    hybrid_search (precedenza dichiarata, S4; peso di sezione, N4). Senza, il gate misurava
    l'ordinamento NUDO — 0.875 dove il server misurava 0.893 sullo stesso indice (R26,
    2026-09-07) — e la coincidenza promessa qui sopra era falsa dal 2026-09-05. I default
    vuoti restano per i doppi dei test; ogni chiamante di produzione li passa.

    `recall` è il numero su cui il gate DECIDE, alla sola `k`. `recall_by_k` porta tutti i k
    misurati (DEFAULT_KS più `k`) e serve allo storico: vedi il commento sotto.

    `collection_name` (opzionale, default COLLECTION_NAME): propagata a hybrid_search. Serve
    al blue/green di Qdrant, che dovrà far valutare il gate contro la collection candidata
    invece che quella di produzione. Nessun chiamante di produzione lo passa ancora."""
    cases = cases if cases is not None else load_golden_cases()
    if not cases:
        return {"recall": None, "n": 0, "k": k}

    def _retrieve(query: str, kk: int) -> list[dict]:
        return retrieval.hybrid_search(query, kk, qdrant=qdrant, embed_model=embed_model,
                                       colbert_store=colbert_store, collection_name=collection_name,
                                       graph=graph, restatements=restatements)

    # TUTTI i k misurati, non solo quello del gate (R12). Le righe dello storico portano la
    # chiave del k in vigore quando furono scritte e `_series` seleziona per chiave ESATTA:
    # spostare eval_gate.k azzerava quasi il grafico (10 → 2 ha accorciato la serie da 79 a
    # 22 punti). Misurando anche gli altri k, la serie del PROSSIMO k esiste già il giorno in
    # cui il gate ci si sposta. La decisione resta sul solo `k`: le altre colonne si
    # scrivono, non votano.
    #
    # COSTA UNA COSA, e va detta. `evaluate` interroga il retrieval una volta sola, ma a
    # max(ks): 10 risultati per caso invece di max(k, 3). hybrid_search dimensiona il pool di
    # candidati su top_k (fetch_k = max(top_k * 3, 10)), e su un pool più profondo il rerank
    # ColBERT può riordinare anche le prime posizioni — quindi la recall@k del gate può
    # muoversi di poco rispetto a ieri. È il verso giusto: è la profondità a cui eval.run
    # misura da sempre, e le righe delle due sorgenti finiscono nella STESSA serie. Prima
    # quella serie mescolava un recall@k letto su 3 risultati con uno letto su 10.
    ks = sorted({*DEFAULT_KS, k})
    report = evaluate(cases, _retrieve, ks=ks)
    # `saturated`: recall@k = 1.000 su OGNI caso. Un gate valutato lì non è un gate
    # severo, è un gate cieco — qualunque candidata lo supera, compresa una peggiorata
    # (S5, ADR 0002). Non blocca (non è una regressione), ma va detto ad alta voce.
    return {"recall": report["aggregate"][f"recall@{k}"], "n": report["n"], "k": k,
            "recall_by_k": {f"recall@{kk}": report["aggregate"][f"recall@{kk}"] for kk in ks},
            "saturated": f"recall@{k}" in (report.get("saturated") or [])}


def gate_promotion(version: str, qdrant, embed_model, colbert_store: Mapping, *,
                   k: int = EVAL_GATE_K, min_recall: float = EVAL_GATE_MIN_RECALL,
                   blocking: bool = EVAL_GATE_BLOCKING, cases: list[dict] | None = None,
                   emit=None, collection_name: str | None = None,
                   graph=None, restatements=frozenset(),
                   project: ProjectContext | None = None) -> dict:
    """Decide se la versione candidata può essere promossa. Restituisce un dict con almeno
    `passed` (bool) e, quando valutato, `recall`/`k`/`min_recall`/`n`.

    Fail-open: gate disattivo o golden set assente ⇒ passed=True (non blocca i build privi di
    baseline). Su regressione: scrive un alert critico; blocca la promozione solo se blocking=True
    (advisory altrimenti — promuove ma segnala).

    `collection_name` (opzionale, default COLLECTION_NAME): propagata a evaluate_recall.
    Nessun chiamante di produzione lo passa ancora."""
    _log = emit or logger.info
    collection_name = collection_name or (project.collection_name if project is not None else COLLECTION_NAME)
    enabled = EVAL_GATE_ENABLED
    alert_kwargs = {}
    history_kwargs = {}
    if project is not None:
        settings = project.settings.get("eval_gate", {})
        enabled = settings.get("enabled", enabled)
        k = settings.get("k", k)
        min_recall = settings.get("min_recall", min_recall)
        blocking = settings.get("blocking", blocking)
        if not project.legacy:
            if cases is None:
                golden = project.root / "eval" / "golden.yaml"
                for component in (golden, *golden.parents):
                    if component.is_symlink() or component.is_junction():
                        raise ValueError(f"linked project golden path forbidden: {component}")
                if not golden.resolve().is_relative_to(project.root.resolve()):
                    raise ValueError("escaping project golden path forbidden")
                cases = load_golden_cases(golden)
            alert_kwargs = {"path": project.database_dir / "alerts.jsonl"}
            history_kwargs = {"path": project.database_dir / "eval" / "history.jsonl"}
    if not enabled:
        return {"passed": True, "skipped": "disabled", "version": version}

    try:
        res = evaluate_recall(qdrant, embed_model, colbert_store, k=k, cases=cases,
                              collection_name=collection_name,
                              graph=graph, restatements=restatements)
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
    if res.get("saturated"):
        msg_sat = (f"Eval-gate valutato a un k SATURO: recall@{k}=1.000 su tutti i {res['n']} "
                   f"casi del golden set. A questo k il gate non distingue una candidata "
                   f"buona da una peggiorata — abbassare eval_gate.k a un k che discrimina.")
        record_alert("warning", msg_sat, k=k, version=version, saturated=True, **alert_kwargs)
        _log(f"⚠️  {msg_sat}")
    ok = res["recall"] >= min_recall
    # Storicizza ogni valutazione del gate (trend di qualità, Epic 5): source="gate", con
    # TUTTI i k misurati (R12) e non solo quello in vigore. Il fallback copre un
    # `evaluate_recall` sostituito da un doppio: siamo fuori dal try/except, e un KeyError
    # qui farebbe fallire proprio il build che il fail-open del gate esiste per proteggere.
    record_history(res.get("recall_by_k") or {f"recall@{k}": res["recall"]},
                   n_cases=res["n"], version=version,
                   source="gate", gate={"passed": ok, "min_recall": min_recall}, **history_kwargs)
    if ok:
        res["passed"] = True
        _log(f"✅ Eval-gate: recall@{k}={res['recall']:.3f} ≥ soglia {min_recall} "
             f"({res['n']} casi) — promozione consentita.")
        return res

    msg = (f"Eval-gate: recall@{k}={res['recall']:.3f} < soglia {min_recall} su {res['n']} casi. "
           f"Versione candidata {version} sotto la qualità minima.")
    record_alert("critical", msg, recall=res["recall"], k=k, threshold=min_recall, version=version, **alert_kwargs)
    if blocking:
        res["passed"] = False
        _log(f"❌ {msg} PROMOZIONE BLOCCATA (CURRENT invariato, alias di produzione "
             f"invariato). La collection candidata resta su Qdrant, non referenziata "
             f"da alcuna versione attiva: il GC del prossimo job/boot riuscito la rimuove.")
    else:
        res["passed"] = True
        res["advisory"] = True
        _log(f"⚠️  {msg} Modalità advisory: promuovo comunque, ma l'alert critico è stato registrato.")
    return res

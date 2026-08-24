"""Test dell'eval-gate (core/eval_gate.py): decisione di promozione, alert su regressione,
fail-open. La misura della recall è mockata per controllare gli scenari senza modello reale."""
import json

from core import eval_gate


def test_alerts_path_isolato_dalla_fixture_autouse():
    """Guardia di regressione sull'ISOLAMENTO, non sull'eval-gate: la fixture autouse
    conftest._isolate_telemetry deve reindirizzare ANCHE eval_gate.ALERTS_PATH, non solo lo
    storico eval. Senza, ogni test che innesca l'advisory appende al database/alerts.jsonl
    REALE e /api/health resta "degraded" con una recall fasulla per 48h (successo davvero:
    32 alert spuri scritti dalla suite il 2026-07-27). Nessun monkeypatch qui: si verifica
    proprio il valore di default che la fixture lascia ai test."""
    from core.config import ALERTS_PATH as REAL_ALERTS_PATH
    assert eval_gate.ALERTS_PATH != REAL_ALERTS_PATH


def test_gate_passes_when_recall_above_threshold(monkeypatch):
    monkeypatch.setattr(eval_gate, "evaluate_recall", lambda *a, **k: {"recall": 0.95, "n": 34, "k": 10})
    res = eval_gate.gate_promotion("v1", None, None, {}, min_recall=0.90, blocking=True)
    assert res["passed"] is True and res["recall"] == 0.95


def test_gate_blocks_and_alerts_on_regression(monkeypatch, tmp_path):
    monkeypatch.setattr(eval_gate, "evaluate_recall", lambda *a, **k: {"recall": 0.70, "n": 34, "k": 10})
    alerts = tmp_path / "alerts.jsonl"
    monkeypatch.setattr(eval_gate, "ALERTS_PATH", alerts)
    res = eval_gate.gate_promotion("v2", None, None, {}, min_recall=0.90, blocking=True)
    assert res["passed"] is False                       # regressione → promozione bloccata
    line = json.loads(alerts.read_text(encoding="utf-8").splitlines()[-1])
    assert line["level"] == "critical" and line["source"] == "eval_gate"
    assert line["recall"] == 0.70 and line["version"] == "v2"


def test_gate_advisory_promotes_but_alerts(monkeypatch, tmp_path):
    monkeypatch.setattr(eval_gate, "evaluate_recall", lambda *a, **k: {"recall": 0.70, "n": 34, "k": 10})
    monkeypatch.setattr(eval_gate, "ALERTS_PATH", tmp_path / "a.jsonl")
    res = eval_gate.gate_promotion("v3", None, None, {}, min_recall=0.90, blocking=False)
    assert res["passed"] is True and res.get("advisory") is True   # advisory: promuove ma segnala
    assert (tmp_path / "a.jsonl").exists()


def test_gate_fail_open_without_golden_set(monkeypatch):
    monkeypatch.setattr(eval_gate, "evaluate_recall", lambda *a, **k: {"recall": None, "n": 0, "k": 10})
    res = eval_gate.gate_promotion("v4", None, None, {})
    assert res["passed"] is True and res["skipped"] == "no_golden_set"


def test_gate_fail_open_on_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("qdrant giù")
    monkeypatch.setattr(eval_gate, "evaluate_recall", _boom)
    res = eval_gate.gate_promotion("v5", None, None, {})
    assert res["passed"] is True and res["skipped"] == "error"      # un gate rotto non blocca il build


def test_gate_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(eval_gate, "EVAL_GATE_ENABLED", False)
    res = eval_gate.gate_promotion("v6", None, None, {})
    assert res["passed"] is True and res["skipped"] == "disabled"


# ---------------------------------------------------------------------------
# collection_name: parametrizzazione blue/green Qdrant (S3). Default invariato
# (COLLECTION_NAME, propagato a evaluate_recall/hybrid_search), passaggio esplicito
# propagato correttamente lungo la catena gate_promotion -> evaluate_recall -> hybrid_search.
# ---------------------------------------------------------------------------
def test_gate_promotion_default_collection_name_propagated_to_evaluate_recall(monkeypatch):
    captured = {}

    def _fake_evaluate_recall(*a, **k):
        captured.update(k)
        return {"recall": 0.95, "n": 34, "k": 10}

    monkeypatch.setattr(eval_gate, "evaluate_recall", _fake_evaluate_recall)
    eval_gate.gate_promotion("v7", None, None, {}, min_recall=0.90)
    assert captured["collection_name"] == eval_gate.COLLECTION_NAME


def test_gate_promotion_explicit_collection_name_propagated_to_evaluate_recall(monkeypatch):
    captured = {}

    def _fake_evaluate_recall(*a, **k):
        captured.update(k)
        return {"recall": 0.95, "n": 34, "k": 10}

    monkeypatch.setattr(eval_gate, "evaluate_recall", _fake_evaluate_recall)
    eval_gate.gate_promotion(
        "v8", None, None, {}, min_recall=0.90, collection_name="vibecraft_events__v8"
    )
    assert captured["collection_name"] == "vibecraft_events__v8"


def test_evaluate_recall_default_collection_name_propagated_to_hybrid_search(monkeypatch):
    captured = {}

    def _fake_hybrid_search(query, kk, *, qdrant, embed_model, colbert_store, collection_name):
        captured["collection_name"] = collection_name
        return []

    monkeypatch.setattr(eval_gate.retrieval, "hybrid_search", _fake_hybrid_search)
    eval_gate.evaluate_recall(None, None, {}, cases=[{"q": "domanda"}])
    assert captured["collection_name"] == eval_gate.COLLECTION_NAME


def test_evaluate_recall_explicit_collection_name_propagated_to_hybrid_search(monkeypatch):
    captured = {}

    def _fake_hybrid_search(query, kk, *, qdrant, embed_model, colbert_store, collection_name):
        captured["collection_name"] = collection_name
        return []

    monkeypatch.setattr(eval_gate.retrieval, "hybrid_search", _fake_hybrid_search)
    eval_gate.evaluate_recall(
        None, None, {}, cases=[{"q": "domanda"}], collection_name="vibecraft_events__v9"
    )
    assert captured["collection_name"] == "vibecraft_events__v9"


# ─────────────────────────────────────────────────────────────────────────────────
# S5 (ADR 0002): il gate non deve essere valutato a un k dove la metrica è satura.
# ─────────────────────────────────────────────────────────────────────────────────

def test_eval_gate_usa_un_k_non_saturo(monkeypatch, tmp_path):
    """Un gate valutato a un k SATURO (recall 1.000 su ogni caso) non è severo, è cieco:
    lo supera qualunque candidata, anche una peggiorata. Non è una regressione — non c'è
    niente da bloccare — ma deve gridarlo, altrimenti il 100% viene letto come un successo.

    Il difetto è documentato: la calibrazione del 2026-07-22 girò a k=10 e k=5 su una
    griglia interamente satura e concluse "nessuna combinazione è distinguibile"."""
    alerts = tmp_path / "alerts.jsonl"
    monkeypatch.setattr(eval_gate, "ALERTS_PATH", alerts)

    # 1. k saturo: passa (recall 1.0 ≥ soglia) MA scrive l'alert di saturazione.
    monkeypatch.setattr(eval_gate, "evaluate_recall",
                        lambda *a, **k: {"recall": 1.0, "n": 59, "k": 10, "saturated": True})
    res = eval_gate.gate_promotion("v-saturo", None, None, {}, k=10, min_recall=0.90)
    assert res["passed"] is True
    riga = json.loads(alerts.read_text(encoding="utf-8").splitlines()[-1])
    assert riga["level"] == "warning" and riga["saturated"] is True and riga["k"] == 10
    assert "SATURO" in riga["message"]

    # 2. k che discrimina: nessun alert di saturazione, il gate misura davvero.
    prima = len(alerts.read_text(encoding="utf-8").splitlines())
    monkeypatch.setattr(eval_gate, "evaluate_recall",
                        lambda *a, **k: {"recall": 0.95, "n": 59, "k": 2, "saturated": False})
    res = eval_gate.gate_promotion("v-discriminante", None, None, {}, k=2, min_recall=0.90)
    assert res["passed"] is True
    assert len(alerts.read_text(encoding="utf-8").splitlines()) == prima


def test_evaluate_recall_riporta_la_saturazione(monkeypatch):
    """La saturazione dev'essere calcolata dove si misura, non dedotta a valle: è
    `evaluate_recall` a vedere i singoli casi, il chiamante vede solo la media."""
    casi = [{"q": f"q{i}", "expected": [{"doc": f"d{i}.md"}]} for i in range(3)]
    trovati = lambda q, k: [{"chunk_id": f"d{q[-1]}.md#00", "doc_id": f"d{q[-1]}.md", "section": ""}]
    monkeypatch.setattr(eval_gate.retrieval, "hybrid_search",
                        lambda q, k, **kw: trovati(q, k))
    res = eval_gate.evaluate_recall(None, None, {}, k=10, cases=casi)
    assert res["recall"] == 1.0 and res["saturated"] is True

    # Un caso che manca e la metrica torna a discriminare.
    casi[2] = {"q": "q2", "expected": [{"doc": "assente.md"}]}
    res = eval_gate.evaluate_recall(None, None, {}, k=10, cases=casi)
    assert res["recall"] < 1.0 and res["saturated"] is False

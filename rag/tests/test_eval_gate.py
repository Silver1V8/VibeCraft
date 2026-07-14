"""Test dell'eval-gate (core/eval_gate.py): decisione di promozione, alert su regressione,
fail-open. La misura della recall è mockata per controllare gli scenari senza modello reale."""
import json

from core import eval_gate


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

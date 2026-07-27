"""Configurazione pytest: mette rag/ su sys.path così che i test possano importare
index / server / code_index (che usano import fratelli: `from index import ...`)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest


@pytest.fixture(autouse=True)
def _isolate_telemetry(tmp_path_factory, monkeypatch):
    """Isola per OGNI test i file di telemetria (storico eval + alert): i test che esercitano
    l'eval-gate o run_eval non devono inquinare eval/results/history.jsonl né database/alerts.jsonl
    reali. Reindirizza i path-modulo su una sandbox temporanea (i test che vogliono ispezionare
    l'alert continuano a fare il proprio monkeypatch mirato, che ha la precedenza)."""
    from core import eval_gate, eval_history
    tmp = tmp_path_factory.mktemp("telemetry")
    monkeypatch.setattr(eval_history, "HISTORY_PATH", tmp / "history.jsonl")
    # ALERTS_PATH va reindirizzato QUI e non solo nei test che ispezionano l'alert: senza,
    # ogni test che innesca l'advisory dell'eval-gate appende al database/alerts.jsonl REALE,
    # e GET /api/health riporta "degraded" con una recall fasulla per 48h (ALERT_MAX_AGE_HOURS).
    monkeypatch.setattr(eval_gate, "ALERTS_PATH", tmp / "alerts.jsonl")

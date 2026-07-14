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
    from core import eval_history
    tmp = tmp_path_factory.mktemp("telemetry")
    monkeypatch.setattr(eval_history, "HISTORY_PATH", tmp / "history.jsonl")

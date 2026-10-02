"""Configurazione pytest: mette rag/ su sys.path così che i test possano importare
index / server / code_index (che usano import fratelli: `from index import ...`)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest


@pytest.fixture(autouse=True)
def _isolate_production_paths(tmp_path_factory, monkeypatch):
    """Isola per OGNI test i file che il codice scriverebbe nella `database/` REALE del
    progetto. Reindirizza i path-modulo su una sandbox temporanea; i test che vogliono
    ispezionare uno di questi file continuano a fare il proprio monkeypatch mirato, che
    essendo applicato dopo ha la precedenza."""
    from core import eval_gate, eval_history, intake, writer_lock
    tmp = tmp_path_factory.mktemp("telemetry")
    monkeypatch.setattr(eval_history, "HISTORY_PATH", tmp / "history.jsonl")
    # ALERTS_PATH va reindirizzato QUI e non solo nei test che ispezionano l'alert: senza,
    # ogni test che innesca l'advisory dell'eval-gate appende al database/alerts.jsonl REALE,
    # e GET /api/health riporta "degraded" con una recall fasulla per 48h (ALERT_MAX_AGE_HOURS).
    monkeypatch.setattr(eval_gate, "ALERTS_PATH", tmp / "alerts.jsonl")
    # R24 — misurato il 2026-09-07: 21 test ACQUISIVANO davvero il writer lock di produzione
    # (database/.writer.lock ne portava pid e timestamp, che writer_lock scrive solo DOPO aver
    # preso il lock OS) e 6 creavano staging/. Su una macchina con un indice vero la suite si
    # serializzava contro gli scrittori di quell'indice, nei due sensi.
    # Reindirizzati qui e non test per test per la stessa ragione di ALERTS_PATH: questi due
    # sono l'unico punto da cui passano TUTTI i chiamanti — writer_lock() senza `lock_path`
    # e ensure_staging_dirs() senza `base_dir` — quindi un test nuovo nasce già isolato.
    monkeypatch.setattr(writer_lock, "default_lock_path", lambda project=None:
                        (project.database_dir if project is not None else tmp) / ".writer.lock")
    monkeypatch.setattr(intake, "INTAKE_STAGING_DIR", tmp / "staging")

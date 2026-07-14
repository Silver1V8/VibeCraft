"""Test dell'osservabilità: report di /api/health (build_health con fake iniettati:
snapshot presente/assente, Qdrant raggiungibile/no, ultimo job e alert), lettura
dell'ultimo alert da alerts.jsonl (finestra 48h) e configurabilità del livello di log
via VIBECRAFT_LOG_LEVEL (setup_logging)."""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import networkx as nx

from api.deps import IndexSnapshot
from api.routes_health import build_health, check_qdrant, read_last_alert
from core.config import setup_logging


# ---------------------------------------------------------------------------
# Fake leggeri
# ---------------------------------------------------------------------------
class FakeManager:
    def __init__(self, jobs=None, pending=None):
        self._jobs = jobs or []
        self._pending = pending

    def list_recent(self, limit=20):
        return self._jobs[:limit]

    @property
    def pending_id(self):
        return self._pending


class FakeQdrant:
    def __init__(self, ok=True):
        self.ok = ok

    def get_collections(self):
        if not self.ok:
            raise ConnectionError("qdrant giù")
        return []


def _snapshot() -> IndexSnapshot:
    g = nx.DiGraph()
    g.add_edge("a.md", "ENTITA")
    return IndexSnapshot(graph=g, colbert_store={}, chunks={"a.md#00-x": {}},
                         rule_descriptions={}, version=1000.0)


def _status_ok():
    return {"indexed": True, "stale": False, "version": "v1", "changed": []}


def _build(**kw):
    defaults = dict(
        snapshot=_snapshot(),
        manager=FakeManager(),
        qdrant=FakeQdrant(ok=True),
        status_fn=_status_ok,
        ollama_check=lambda: True,
        alerts_path=Path("alerts-inesistenti.jsonl"),
        now=2000.0,
    )
    defaults.update(kw)
    return build_health(**defaults)


# ---------------------------------------------------------------------------
# build_health
# ---------------------------------------------------------------------------
def test_health_ok_with_snapshot_and_qdrant():
    report = _build()
    assert report["status"] == "ok"
    assert report["reasons"] == []
    assert report["snapshot"]["loaded"] is True
    assert report["snapshot"]["graph_nodes"] == 2
    assert report["snapshot"]["chunks"] == 1
    assert report["snapshot"]["age_seconds"] == 1000.0
    assert report["manifest"] == {"indexed": True, "version": "v1", "stale": False, "changed_count": 0}
    assert report["dependencies"] == {"qdrant": True, "ollama": True}
    assert report["last_alert"] is None


def test_health_degraded_without_snapshot():
    report = _build(snapshot=None)
    assert report["status"] == "degraded"
    assert any("snapshot" in r for r in report["reasons"])
    assert report["snapshot"] == {"loaded": False}


def test_health_degraded_qdrant_down():
    report = _build(qdrant=FakeQdrant(ok=False))
    assert report["status"] == "degraded"
    assert "Qdrant non raggiungibile" in report["reasons"]
    assert report["dependencies"]["qdrant"] is False


def test_health_qdrant_missing_client():
    assert check_qdrant(None) is False


def test_health_manifest_stale_and_without_file_list():
    def stale():
        return {"indexed": True, "stale": True, "version": "v1", "changed": ["+ a.md", "~ b.md"]}
    report = _build(status_fn=stale)
    assert report["status"] == "degraded"
    assert report["manifest"]["stale"] is True
    assert report["manifest"]["changed_count"] == 2
    assert "changed" not in report["manifest"]  # niente lista completa nel report


def test_health_last_reindex_job_and_pending():
    jobs = [{"job_id": "j1", "kind": "full", "status": "failed",
             "finished_at": "2026-01-01T00:00:00+00:00", "error": "boom"}]
    report = _build(manager=FakeManager(jobs=jobs, pending="j2"))
    assert report["reindex"]["last_job"]["job_id"] == "j1"
    assert report["reindex"]["pending"] is True
    assert any("reindex fallito" in r for r in report["reasons"])


def test_health_ollama_down_is_degraded_but_reported():
    report = _build(ollama_check=lambda: False)
    assert report["dependencies"]["ollama"] is False
    assert "Ollama non raggiungibile" in report["reasons"]


# ---------------------------------------------------------------------------
# Ultimo alert da alerts.jsonl (finestra 48h)
# ---------------------------------------------------------------------------
def _write_alert(path, ts):
    path.write_text(json.dumps({"timestamp": ts, "script": "nightly_consistency.sh",
                                "error": "full rebuild fallito"}) + "\n", encoding="utf-8")


def test_read_last_alert_recent(tmp_path):
    p = tmp_path / "alerts.jsonl"
    _write_alert(p, datetime.now(timezone.utc).isoformat())
    alert = read_last_alert(p)
    assert alert is not None and alert["error"] == "full rebuild fallito"


def test_read_last_alert_too_old(tmp_path):
    p = tmp_path / "alerts.jsonl"
    _write_alert(p, (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat())
    assert read_last_alert(p) is None


def test_read_last_alert_missing_or_corrupted(tmp_path):
    assert read_last_alert(tmp_path / "assente.jsonl") is None
    p = tmp_path / "alerts.jsonl"
    p.write_text("non-json\n", encoding="utf-8")
    assert read_last_alert(p) is None


def test_health_reports_recent_alert(tmp_path):
    p = tmp_path / "alerts.jsonl"
    _write_alert(p, datetime.now(timezone.utc).isoformat())
    report = _build(alerts_path=p)
    assert report["status"] == "degraded"
    assert report["last_alert"]["script"] == "nightly_consistency.sh"
    assert any("alert notturno" in r for r in report["reasons"])


# ---------------------------------------------------------------------------
# Logging configurabile via VIBECRAFT_LOG_LEVEL
# ---------------------------------------------------------------------------
def test_log_level_from_env(monkeypatch):
    monkeypatch.setenv("VIBECRAFT_LOG_LEVEL", "DEBUG")
    setup_logging()
    assert logging.getLogger().level == logging.DEBUG
    monkeypatch.setenv("VIBECRAFT_LOG_LEVEL", "WARNING")
    setup_logging()
    assert logging.getLogger().level == logging.WARNING
    monkeypatch.delenv("VIBECRAFT_LOG_LEVEL")
    setup_logging()  # default INFO (e ripristina un livello sano per gli altri test)
    assert logging.getLogger().level == logging.INFO


def test_log_level_invalid_falls_back_to_info(monkeypatch):
    monkeypatch.setenv("VIBECRAFT_LOG_LEVEL", "NONSENSE")
    setup_logging()
    assert logging.getLogger().level == logging.INFO
    monkeypatch.delenv("VIBECRAFT_LOG_LEVEL")
    setup_logging()

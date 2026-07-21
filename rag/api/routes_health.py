"""GET /api/health — osservabilità minima del servizio: stato dello snapshot in memoria,
freschezza del manifest (riusa index_status senza la lista dei file), ultimo job di reindex
e pending in coda, raggiungibilità delle dipendenze (Qdrant, Ollama best-effort) e ultimo
alert dei batch notturni (database/alerts.jsonl, entro 48h). La logica vive in
`build_health`, pura rispetto allo stato del server: ogni pezzo è iniettabile, così i test
usano fake senza FastAPI né rete."""
import json
import logging
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from api.deps import current_snapshot, require_api_key, state
from api.routes_reindex import manager
from core.config import ALERTS_PATH
from core.eval_history import eval_health, load_history
from core.indexing import index_status
from core import llm

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_key)])

# Un alert dei batch notturni più vecchio di così non degrada più lo stato.
ALERT_MAX_AGE_HOURS = 48

# Il ping a Ollama è best-effort e non deve MAI bloccare l'health check a lungo.
OLLAMA_PING_TIMEOUT_SECONDS = 2.0


def check_qdrant(qdrant) -> bool:
    """True se il client Qdrant risponde a get_collections (client assente ⇒ False).
    Il client del server è creato con il timeout di default (5s), quindi il check
    resta breve anche a Qdrant spento."""
    if qdrant is None:
        return False
    try:
        qdrant.get_collections()
        return True
    except Exception as exc:
        logger.warning("Qdrant non raggiungibile: %s", exc)
        return False


def check_ollama(timeout: float = OLLAMA_PING_TIMEOUT_SECONDS) -> bool:
    """Ping best-effort a Ollama (GET /api/tags derivato dall'endpoint generate,
    letto da core.llm a ogni chiamata: stessa origine di VIBECRAFT_OLLAMA_URL),
    mai bloccante oltre `timeout` secondi."""
    url = llm.OLLAMA_GENERATE_URL.rsplit("/api/", 1)[0] + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except Exception:
        return False


def read_last_alert(path: Path = ALERTS_PATH, max_age_hours: float = ALERT_MAX_AGE_HOURS,
                    now: datetime | None = None) -> dict | None:
    """Ultimo alert del file JSONL, se non più vecchio di `max_age_hours` (None se il
    file manca, è vuoto, l'ultima riga è corrotta o l'alert è troppo vecchio)."""
    try:
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError:
        return None
    if not lines:
        return None
    try:
        alert = json.loads(lines[-1])
        ts = datetime.fromisoformat(str(alert["timestamp"]))
    except Exception:
        return None
    if ts.tzinfo is None:
        ts = ts.astimezone()  # timestamp naive: interpretato come ora locale
    now = now or datetime.now(timezone.utc)
    age_hours = (now - ts).total_seconds() / 3600
    if age_hours > max_age_hours:
        return None
    return alert


def build_health(*, snapshot, manager, qdrant, status_fn=index_status,
                 ollama_check=check_ollama, alerts_path: Path = ALERTS_PATH,
                 now: float | None = None) -> dict:
    """Assembla il report di health. `status` è "ok" solo se `reasons` è vuota;
    ogni difetto (snapshot assente, indice stale, dipendenza giù, ultimo reindex
    fallito, alert notturno recente) aggiunge un motivo leggibile."""
    now = now if now is not None else time.time()
    reasons: list[str] = []

    # Snapshot in memoria (version = nome della versione blue/green da CURRENT, oppure
    # — layout legacy — l'mtime float di graph.json; age_seconds ha senso solo per l'mtime).
    if snapshot is None or snapshot.graph is None:
        snap_report = {"loaded": False}
        reasons.append("snapshot indice non caricato in memoria")
    else:
        snap_report = {
            "loaded": True,
            "version": snapshot.version,
            "age_seconds": (round(now - snapshot.version, 1)
                            if isinstance(snapshot.version, (int, float)) and snapshot.version
                            else None),
            "graph_nodes": snapshot.graph.number_of_nodes(),
            "graph_edges": snapshot.graph.number_of_edges(),
            "chunks": len(snapshot.chunks),
        }

    # Manifest: riusa index_status ma senza la lista completa dei file cambiati.
    st = status_fn()
    manifest_report = {
        "indexed": st.get("indexed", False),
        "version": st.get("version"),
        "stale": st.get("stale", True),
        "changed_count": len(st.get("changed", [])),
    }
    if not manifest_report["indexed"]:
        reasons.append(f"manifest assente o illeggibile ({st.get('reason', '?')})")
    elif manifest_report["stale"]:
        reasons.append(f"indice stale: {manifest_report['changed_count']} file cambiati rispetto al manifest")

    # Ultimo job di reindex + pending in coda.
    recent = manager.list_recent(1)
    last_job = None
    if recent:
        j = recent[0]
        last_job = {"job_id": j["job_id"], "kind": j["kind"],
                    "status": j["status"], "finished_at": j["finished_at"]}
        if j["status"] == "failed":
            reasons.append(f"ultimo reindex fallito: {j.get('error') or j['job_id']}")
    reindex_report = {"last_job": last_job, "pending": manager.pending_id is not None}

    # Dipendenze: Qdrant (necessario), Ollama (best-effort, mai bloccante > 2s).
    qdrant_ok = check_qdrant(qdrant)
    ollama_ok = ollama_check()
    if not qdrant_ok:
        reasons.append("Qdrant non raggiungibile")
    if not ollama_ok:
        reasons.append("Ollama non raggiungibile")

    # Ultimo alert (solo se più recente di 48h): due formati coesistono in alerts.jsonl —
    # gli script notturni scrivono {script, error}, mentre core.eval_gate.record_alert
    # (eval-gate e il warning di rollback su collection condivisa) scrive
    # {level, source, message, ...}. Il campo "script" distingue i due formati.
    alert = read_last_alert(alerts_path)
    if alert is not None:
        if "script" in alert:
            reasons.append(f"alert notturno recente: {alert.get('script', '?')} — {alert.get('error', '?')}")
        else:
            reasons.append(f"alert recente ({alert.get('source', '?')}): {alert.get('message', '?')}")

    return {
        "status": "ok" if not reasons else "degraded",
        "reasons": reasons,
        "snapshot": snap_report,
        "manifest": manifest_report,
        "reindex": reindex_report,
        "dependencies": {"qdrant": qdrant_ok, "ollama": ollama_ok},
        "last_alert": alert,
        # Trend di qualità del retrieval (Epic 5): ultima recall@10 registrata + direzione
        # rispetto alla media mobile. Se è "down" la recall sta calando: segnale da indagare.
        "eval": eval_health(),
    }


@router.get("/api/health")
async def api_health():
    """Stato complessivo del servizio: snapshot, manifest, coda di reindex, dipendenze
    e ultimo alert notturno. "ok" oppure "degraded" con l'elenco dei motivi."""
    return await run_in_threadpool(
        build_health,
        snapshot=current_snapshot(),
        manager=manager,
        qdrant=state.get("qdrant"),
    )


@router.get("/api/eval/history")
async def api_eval_history(limit: int = 100):
    """Storico della qualità del retrieval (eval/results/history.jsonl): recall@k nel tempo e
    per-versione, con marcatori di provenienza (eval.run / gate). Read-only; ultimi `limit`."""
    rows = await run_in_threadpool(load_history, limit)
    return {"n": len(rows), "history": rows, "summary": eval_health()}

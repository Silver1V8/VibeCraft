"""GET /api/health — osservabilità minima del servizio: stato dello snapshot in memoria,
freschezza del manifest (riusa index_status senza la lista dei file), ultimo job di reindex
e pending in coda, raggiungibilità delle dipendenze (Qdrant, Ollama best-effort) e ultimo
alert dei batch notturni (database/alerts.jsonl, entro 48h). La logica vive in
`build_health`, pura rispetto allo stato del server: ogni pezzo è iniettabile, così i test
usano fake senza FastAPI né rete."""
import asyncio
import json
import logging
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.concurrency import run_in_threadpool

from api.deps import (get_project, require_snapshot, project_runtime, require_api_key, state,
                      _is_local_request, ensure_shared_resources)
from core.artifacts import _project_artifact_path
from core.config import ALERTS_PATH, ROLE
from core import llm

if ROLE != "reader":
    from api.reindex import ReindexManager
    from core.eval_history import eval_health, load_history
    from core.indexing import index_status

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_key)])
reader_router = APIRouter(dependencies=[Depends(require_api_key)])

# Un alert dei batch notturni più vecchio di così non degrada più lo stato.
ALERT_MAX_AGE_HOURS = 48

# Il ping a Ollama è best-effort e non deve MAI bloccare l'health check a lungo.
OLLAMA_PING_TIMEOUT_SECONDS = 2.0


def _qdrant_collection_names(qdrant) -> set[str] | None:
    """Collection visibili, oppure None se Qdrant non è raggiungibile."""
    if qdrant is None:
        return None
    try:
        response = qdrant.get_collections()
        collections = getattr(response, "collections", response) or []
        names: set[str] = set()
        for item in collections:
            name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
            if isinstance(name, str):
                names.add(name)
        return names
    except Exception as exc:
        logger.warning("Qdrant non raggiungibile: %s", exc)
        return None


def check_qdrant(qdrant) -> bool:
    """True se il client Qdrant risponde a get_collections (client assente ⇒ False)."""
    return _qdrant_collection_names(qdrant) is not None


def _shared_qdrant():
    """Client Qdrant condiviso, creato se manca: nasce alla prima richiesta indicizzata,
    e prima di allora l'health dava Qdrant "non raggiungibile" anche quando era su."""
    try:
        ensure_shared_resources(embedding=False)
    except HTTPException:
        pass
    return state.get("qdrant")


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


def build_health(*, snapshot, manager=None, qdrant, status_fn=None,
                 ollama_check=check_ollama, alerts_path: Path = ALERTS_PATH,
                 now: float | None = None, role: str = ROLE,
                 reload_error: str | None = None, eval_health_fn=None) -> dict:
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
            "qdrant_collection": snapshot.collection_name,
        }

    if role == "reader":
        manifest = snapshot.index_manifest if snapshot is not None else {}
        manifest_report = {
            "indexed": bool(manifest),
            "version": snapshot.version if snapshot is not None else None,
            "stale": reload_error is not None,
            "changed_count": 0,
            "immutable": manifest.get("immutable"),
            "qdrant_collection": manifest.get("qdrant_collection"),
        }
        if not manifest:
            reasons.append("manifest immutabile non caricato nello snapshot")
        if reload_error:
            reasons.append(f"reload indice fallito: {reload_error}")
        reindex_report = None
    else:
        # Manifest: riusa index_status ma senza la lista completa dei file cambiati.
        status_fn = status_fn or index_status
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
            reasons.append(
                f"indice stale: {manifest_report['changed_count']} file cambiati rispetto al manifest"
            )

        # Ultimo job di reindex + pending in coda.
        recent = manager.list_recent(1) if manager is not None else []
        last_job = None
        if recent:
            j = recent[0]
            last_job = {"job_id": j["job_id"], "kind": j["kind"],
                        "status": j["status"], "finished_at": j["finished_at"]}
            if j["status"] == "failed":
                reasons.append(f"ultimo reindex fallito: {j.get('error') or j['job_id']}")
        reindex_report = {"last_job": last_job, "pending": manager is not None and manager.pending_id is not None}

    # Dipendenze: Qdrant (necessario), Ollama (best-effort, mai bloccante > 2s).
    qdrant_collections = _qdrant_collection_names(qdrant)
    qdrant_ok = qdrant_collections is not None
    ollama_ok = ollama_check()
    if not qdrant_ok:
        reasons.append("Qdrant non raggiungibile")
    elif (role == "reader" and snapshot is not None and snapshot.collection_name
          and snapshot.collection_name not in qdrant_collections):
        reasons.append(
            f"collection Qdrant dello snapshot assente: {snapshot.collection_name}"
        )
    if not ollama_ok:
        reasons.append("Ollama non raggiungibile")

    # Ultimo alert (solo se più recente di 48h): due formati coesistono in alerts.jsonl —
    # gli script notturni scrivono {script, error}, mentre core.eval_gate.record_alert
    # (eval-gate e il warning di rollback su collection condivisa) scrive
    # {level, source, message, ...}. Il campo "script" distingue i due formati.
    alert = None if role == "reader" else read_last_alert(alerts_path)
    if alert is not None:
        if "script" in alert:
            reasons.append(f"alert notturno recente: {alert.get('script', '?')} — {alert.get('error', '?')}")
        else:
            reasons.append(f"alert recente ({alert.get('source', '?')}): {alert.get('message', '?')}")

    eval_report = None
    if role != "reader":
        eval_report = (eval_health_fn or eval_health)()
    return {
        "status": "ok" if not reasons else "degraded",
        "role": role,
        "read_only": role == "reader",
        "reasons": reasons,
        "snapshot": snap_report,
        "manifest": manifest_report,
        "reindex": reindex_report,
        "dependencies": {"qdrant": qdrant_ok, "ollama": ollama_ok},
        "last_alert": alert,
        # Trend di qualità del retrieval (Epic 5): ultima recall registrata + direzione
        # rispetto alla media mobile. Se è "down" la recall sta calando: segnale da indagare.
        # La metrica è quella del gate (`key` nel payload, oggi recall@2), non un k fisso: vedi
        # il commento su GATE_RECALL_KEY in core/eval_history.py.
        "eval": eval_report,
    }


@reader_router.get("/api/health/live")
@router.get("/api/health/live")
def api_liveness():
    return {"status": "ok", "role": ROLE, "read_only": ROLE == "reader"}


@reader_router.get("/api/health/deps")
@router.get("/api/health/deps")
async def api_health_deps():
    """Solo le dipendenze, per l'indicatore della shell: niente index_status, che su
    progetti grandi scansiona migliaia di file a ogni chiamata."""
    qdrant = await run_in_threadpool(_shared_qdrant)
    qdrant_ok, ollama_ok = await asyncio.gather(run_in_threadpool(check_qdrant, qdrant),
                                                run_in_threadpool(check_ollama))
    # shortcut: guarda solo active_provider, non gli override per scopo
    # (llm_settings.purposes); se un override punta a Ollama con provider attivo diverso,
    # l'indicatore tace. Ollama spento non è un problema se nessuno lo usa: None = non in uso.
    if llm._llm_settings().active_provider != "ollama":
        ollama_ok = None
    return {"qdrant": qdrant_ok, "ollama": ollama_ok}


@reader_router.get("/api/health")
@router.get("/api/health")
async def api_health(request: Request):
    project = get_project(request)
    runtime = project_runtime(project)
    try:
        snapshot = await run_in_threadpool(require_snapshot, project)
    except HTTPException:
        snapshot = None
    kwargs = {}
    if not project.legacy:
        try:
            kwargs["alerts_path"] = _project_artifact_path(project.database_dir / "alerts.jsonl", project)
            history = _project_artifact_path(project.database_dir / "eval" / "history.jsonl", project)
        except ValueError as exc:
            raise HTTPException(503, detail={"code": "project_storage_error",
                                            "message": "Project health unavailable"}) from exc
        kwargs["eval_health_fn"] = lambda: eval_health(path=history)
    if ROLE != "reader":
        kwargs["status_fn"] = lambda: index_status(project=project)
    try:
        with runtime['lock']:
            manager = runtime.get('reindex_manager')
        if ROLE != 'reader' and manager is None:
            manager = await run_in_threadpool(ReindexManager, project=project, recover_journal=False)
        report = await run_in_threadpool(
            build_health, snapshot=snapshot,
            manager=manager,
            qdrant=await run_in_threadpool(_shared_qdrant), role=ROLE, ollama_check=check_ollama,
            reload_error=runtime.get("reload_error"), **kwargs,
        )
    except Exception as exc:
        logger.exception("Project health unavailable: %s", project.id)
        raise HTTPException(503, detail={"code": "project_storage_error",
                                        "message": "Project health unavailable"}) from exc
    if not _is_local_request(request):
        # Jobs and batch alerts may contain OS paths or provider error details.
        report["reasons"] = ["Project or dependency unavailable"] if report["reasons"] else []
        report["last_alert"] = None
    return {**report, "project_id": project.id, "live": True}


@router.get("/api/eval/history")
async def api_eval_history(request: Request, limit: int = 100):
    project = get_project(request)
    try:
        path = None if project.legacy else _project_artifact_path(
            project.database_dir / "eval" / "history.jsonl", project)
    except ValueError as exc:
        raise HTTPException(503, detail={"code": "project_storage_error",
                                        "message": "Project history unavailable"}) from exc
    rows = await run_in_threadpool(load_history, limit, path=path)
    return {"n": len(rows), "history": rows, "summary": eval_health(path=path),
            "project_id": project.id}

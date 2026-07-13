"""Route del reindex incrementale automatico: POST /api/reindex lancia (o accoda) un reindex
in background e risponde 202 con il job-id — se un reindex è già in corso la richiesta viene
accodata/fusa in un unico pending (coalescing dei path) invece di essere rifiutata, così i
webhook GitLab ravvicinati non si perdono. GET /api/reindex/{job_id} ne riporta lo stato
(queued/running/completed/failed). L'endpoint accetta anche un payload webhook GitLab
(push/merge) da cui estrae i path modificati, per limitare il delta a ciò che è cambiato.
A fine job riusa reload_index_state (il meccanismo di auto-reload esistente)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from api.deps import (
    reload_index_state,
    require_api_key,
    require_gitlab_token,
    state,
)
from api.reindex import ReindexManager, extract_gitlab_paths
from core.config import REINDEX_JOURNAL_PATH
from core.indexing import incremental_index

router = APIRouter(dependencies=[Depends(require_api_key)])

# Un solo manager per processo: serializza i reindex e conserva lo stato dei job. Il journal
# JSONL rende lo storico persistente ai riavvii (ricostruito dal manager al boot).
manager = ReindexManager(journal_path=REINDEX_JOURNAL_PATH)


def _run_reindex(changed_paths) -> dict:
    """Esegue l'incrementale riusando il modello di embedding e il client Qdrant già
    caricati dal server (evita il ricaricamento del modello, minuti di CPU). Gira sul
    thread daemon del ReindexManager, quindi è bloccante ma fuori dall'event loop."""
    return incremental_index(
        qdrant=state.get("qdrant"),
        embed_model=state.get("embed_model"),
        changed_paths=changed_paths,
    )


@router.post("/api/reindex", dependencies=[Depends(require_gitlab_token)])
async def start_reindex(request: Request):
    """Avvia (o accoda) un reindex incrementale in background e risponde 202 con il job-id.

    Il corpo è opzionale: se contiene un payload webhook GitLab (push) o un override
    esplicito `{"paths": [...]}`, i path modificati limitano il delta; altrimenti si fa
    un incrementale completo su docs/ + code/. Se un reindex è già in corso la richiesta
    NON viene rifiutata: è accodata/fusa in un unico pending e la risposta riporta
    `{"job_id": <id del pending>, "queued": true}`."""
    try:
        payload = await request.json()
    except Exception:
        payload = None  # corpo assente o non-JSON: incrementale completo

    changed_paths = extract_gitlab_paths(payload) if payload is not None else None

    job, queued = manager.start(changed_paths, _run_reindex, reload_index_state)
    content = job.to_dict()
    if queued:
        content["queued"] = True
    return JSONResponse(status_code=202, content=content)


@router.get("/api/reindex")
async def list_reindex(limit: int = 20):
    """Lista degli ultimi `limit` job di reindex (default 20), più recente prima — utile
    per debug e per la UI. Ricostruita dal journal al boot, quindi sopravvive ai riavvii."""
    if limit < 1:
        limit = 1
    jobs = await run_in_threadpool(manager.list_recent, limit)
    return {"jobs": jobs}


@router.get("/api/reindex/{job_id}")
async def reindex_status(job_id: str):
    """Stato di un job di reindex (running/completed/failed) con il risultato o l'errore."""
    job = await run_in_threadpool(manager.get, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job di reindex non trovato: {job_id}")
    return job.to_dict()

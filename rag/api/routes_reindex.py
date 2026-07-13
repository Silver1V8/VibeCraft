"""Route del reindex incrementale automatico: POST /api/reindex lancia un reindex in
background (un job alla volta, 409 se già in corso) e risponde subito con il job-id; GET
/api/reindex/{job_id} ne riporta lo stato. L'endpoint accetta anche un payload webhook
GitLab (push/merge) da cui estrae i path modificati, per limitare il delta a ciò che è
cambiato. A fine job riusa reload_index_state (il meccanismo di auto-reload esistente)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from api.deps import reload_index_state, require_api_key, state
from api.reindex import ReindexManager, extract_gitlab_paths
from core.indexing import incremental_index

router = APIRouter(dependencies=[Depends(require_api_key)])

# Un solo manager per processo: serializza i reindex e conserva lo stato dei job.
manager = ReindexManager()


def _run_reindex(changed_paths) -> dict:
    """Esegue l'incrementale riusando il modello di embedding e il client Qdrant già
    caricati dal server (evita il ricaricamento del modello, minuti di CPU). Gira sul
    thread daemon del ReindexManager, quindi è bloccante ma fuori dall'event loop."""
    return incremental_index(
        qdrant=state.get("qdrant"),
        embed_model=state.get("embed_model"),
        changed_paths=changed_paths,
    )


@router.post("/api/reindex")
async def start_reindex(request: Request):
    """Avvia un reindex incrementale in background e risponde 202 con il job-id.

    Il corpo è opzionale: se contiene un payload webhook GitLab (push) o un override
    esplicito `{"paths": [...]}`, i path modificati limitano il delta; altrimenti si fa
    un incrementale completo su docs/ + code/. Se un reindex è già in corso → 409."""
    try:
        payload = await request.json()
    except Exception:
        payload = None  # corpo assente o non-JSON: incrementale completo

    changed_paths = extract_gitlab_paths(payload) if payload is not None else None

    job = manager.start(changed_paths, _run_reindex, reload_index_state)
    if job is None:
        raise HTTPException(status_code=409, detail="Un reindex è già in corso.")
    return JSONResponse(status_code=202, content=job.to_dict())


@router.get("/api/reindex/{job_id}")
async def reindex_status(job_id: str):
    """Stato di un job di reindex (running/completed/failed) con il risultato o l'errore."""
    job = await run_in_threadpool(manager.get, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job di reindex non trovato: {job_id}")
    return job.to_dict()

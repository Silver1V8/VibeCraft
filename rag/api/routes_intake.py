"""Route del ciclo Intake & Import — staging con review (S2, piano:
docs/00_meta_governance/piano_intake_import.md): upload multipart → staging → preview →
approve (docs/ + reindex delta) / reject. Handler sottili: la logica vive in
core/intake.py; qui solo validazioni HTTP (estensione e dimensione PRIMA di leggere tutto
in memoria), mappatura degli errori tipizzati su status code e iniezione delle risorse di
runtime (client Qdrant + modello embedding del server) nel reindex."""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from api.deps import (
    reload_index_state,
    require_api_key,
    require_not_cross_site_request,
    state,
)
from core import intake
from core.config import INTAKE_ALLOWED_FORMATS, INTAKE_MAX_UPLOAD_MB
from core.intake_convert import ConversionError
from core.writer_lock import WriterLockBusyError

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_key)])

# Lettura dell'upload a fette: la soglia max_upload_mb viene applicata DURANTE la
# lettura, mai dopo aver materializzato l'intero body in memoria.
_UPLOAD_CHUNK_BYTES = 1024 * 1024

# Errori tipizzati di core.intake → status code HTTP. L'ordine conta (isinstance sulle
# sottoclassi prima della base IntakeError non serve: nessuna sovrapposizione).
_ERROR_STATUS: tuple[tuple[type[Exception], int], ...] = (
    (intake.StagedDocumentNotFoundError, 404),
    (intake.DocumentAlreadyProcessedError, 409),
    (intake.DuplicateStagedDocumentError, 409),
    (intake.TargetFileExistsError, 409),
    (intake.InvalidCategoryError, 422),
    (intake.InvalidFilenameError, 422),
    (intake.InvalidComposedDocumentError, 422),
    (WriterLockBusyError, 409),
    (ConversionError, 422),
)


def _raise_http(exc: Exception) -> None:
    """Rilancia un errore di dominio come HTTPException (o lo propaga se sconosciuto)."""
    for klass, status_code in _ERROR_STATUS:
        if isinstance(exc, klass):
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    raise exc


class ApproveRequest(BaseModel):
    categoria: str
    nome_file: str


class RejectRequest(BaseModel):
    motivo: str = ""


def _server_reindex(changed_paths):
    """Reindex delta con le risorse del server: client Qdrant del lifespan e modello di
    embedding già caricato (CPU — un approve indicizza un solo documento, pochi chunk).
    Import lazy di core.indexing per non pagare torch all'import del router."""
    from core.indexing import incremental_index
    return incremental_index(
        qdrant=state.get("qdrant"),
        embed_model=state.get("embed_model"),
        changed_paths=changed_paths,
    )


@router.post("/api/intake/docs", dependencies=[Depends(require_not_cross_site_request)])
async def upload_intake_document(file: UploadFile = File(...)):
    """Upload multipart di un documento verso lo staging. Estensione validata contro
    intake.allowed_formats e dimensione contro intake.max_upload_mb PRIMA di leggere
    l'intero contenuto in memoria (Content-Length quando presente, poi conteggio a fette
    durante la lettura). Risponde con l'entry 'staged' del journal."""
    filename = file.filename or ""
    fmt = Path(filename).suffix.lower().lstrip(".")
    if fmt not in INTAKE_ALLOWED_FORMATS:
        raise HTTPException(
            status_code=415,
            detail=f"formato non supportato: {fmt or '(nessuna estensione)'} "
                   f"(ammessi: {', '.join(INTAKE_ALLOWED_FORMATS)})",
        )
    max_bytes = INTAKE_MAX_UPLOAD_MB * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"file troppo grande ({file.size} byte): massimo {INTAKE_MAX_UPLOAD_MB} MB",
        )
    pieces: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"file troppo grande (oltre {INTAKE_MAX_UPLOAD_MB} MB): upload interrotto",
            )
        pieces.append(chunk)
    content = b"".join(pieces)
    try:
        return await run_in_threadpool(intake.stage_document, filename, content)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/intake/staged")
async def list_staged_documents():
    """Documenti attualmente in staging (stato 'staged'), in ordine di arrivo."""
    staged = await run_in_threadpool(intake.list_staged)
    return {"staged": staged}


@router.get("/api/intake/staged/{doc_id}/preview")
async def preview_staged_document(doc_id: str):
    """Entry del journal + markdown derivato, per la review prima di approve/reject."""
    try:
        return await run_in_threadpool(intake.get_preview, doc_id)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/intake/staged/{doc_id}/approve",
             dependencies=[Depends(require_not_cross_site_request)])
async def approve_staged_document(doc_id: str, payload: ApproveRequest):
    """Approva un documento in staging verso docs/<categoria>/<nome_file> con reindex
    delta della sola path aggiunta (writer lock in core.intake.approve). Risponde con
    l'esito e le stats del job di reindex; a lock occupato (altro writer in corso) → 409."""
    try:
        record = await run_in_threadpool(
            intake.approve, doc_id, payload.categoria, payload.nome_file,
            reindex=_server_reindex,
        )
    except Exception as exc:
        _raise_http(exc)
    # Il reindex ha promosso una nuova versione: allinea subito lo snapshot in memoria
    # (stesso meccanismo di auto-reload dei job di reindex). Best-effort: reload_index_state
    # non solleva mai per artefatti mancanti/incoerenti.
    await run_in_threadpool(reload_index_state)
    return record


@router.post("/api/intake/staged/{doc_id}/reject",
             dependencies=[Depends(require_not_cross_site_request)])
async def reject_staged_document(doc_id: str, payload: RejectRequest):
    """Rifiuta un documento in staging (motivo nel journal, file in staging/rejected/):
    docs/ e indice restano intatti."""
    try:
        return await run_in_threadpool(intake.reject, doc_id, payload.motivo)
    except Exception as exc:
        _raise_http(exc)

"""Route del ciclo Intake & Import — staging con review (S2, piano:
docs/00_meta_governance/piano_intake_import.md): upload multipart → staging → preview →
approve (docs/ + reindex delta) / reject. Handler sottili: la logica vive in
core/intake.py; qui solo validazioni HTTP (estensione e dimensione PRIMA di leggere tutto
in memoria), mappatura degli errori tipizzati su status code e iniezione delle risorse di
runtime (client Qdrant + modello embedding del server) nel reindex.

S3 aggiunge la generazione di documentazione via Ollama (core/doc_generation.py): POST
/api/intake/generate avvia un job in background (pattern api.reindex.ReindexManager) e
risponde subito col job_id; GET /api/intake/generate/{job_id} ne riporta lo stato. Il
lavoro (retrieval + chiamata LLM) chiude sulle risorse di runtime del server (snapshot
Qdrant/embedding), mai su un percorso diretto verso docs/: ogni documento generato e
validato entra in staging come un documento importato qualunque."""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.deps import (
    current_snapshot,
    reload_index_state,
    require_api_key,
    require_not_cross_site_request,
    state,
)
from core import doc_generation, intake, intake_refine, project_brief, project_import
from core.config import INTAKE_ALLOWED_FORMATS, INTAKE_GENERATION_MAX_FILES, INTAKE_MAX_UPLOAD_MB
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
    (intake_refine.RefineError, 422),
    (project_brief.BriefWithoutImportError, 409),
    (project_brief.ProjectBriefError, 422),
    (project_import.StaleImportPlanError, 409),
    (project_import.InvalidImportPathError, 422),
    (project_import.InvalidImportTargetError, 422),
    (project_import.ProjectImportError, 422),
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


class GenerateRequest(BaseModel):
    descrizione: str
    n_file: int = INTAKE_GENERATION_MAX_FILES
    categoria_suggerita: str = "04_knowledge_informative"


# Un solo manager per processo: nessuna coda/coalescing (i job di generazione sono
# indipendenti, non toccano mai il writer lock di docs/+indice — vedi core.doc_generation).
_generation_manager = doc_generation.GenerationManager()


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


# ---------------------------------------------------------------------------
# S3 — Generazione doc via Ollama: job in background + polling dello stato
# ---------------------------------------------------------------------------
def _server_generate(descrizione: str, n_file: int, categoria_target: str) -> dict:
    """Chiude sulle risorse di runtime del server (snapshot Qdrant/embedding), pattern di
    _server_reindex. Gira sul thread daemon del GenerationManager: bloccante ma fuori
    dall'event loop."""
    snap = current_snapshot()
    return doc_generation.generate_docs(
        descrizione, n_file, categoria_target,
        qdrant=state.get("qdrant"), embed_model=state.get("embed_model"),
        colbert_store=snap.colbert_store if snap else None,
        chunks_store=snap.chunks if snap else None,
    )


@router.post("/api/intake/generate", dependencies=[Depends(require_not_cross_site_request)])
async def start_generation(payload: GenerateRequest):
    """Avvia (subito, in background) un job di generazione documentazione grounded e
    risponde 202 col job_id. Il corpo dell'esito (documenti generati/scartati, latenze)
    si legge da GET /api/intake/generate/{job_id}."""
    if not payload.descrizione.strip():
        raise HTTPException(status_code=422, detail="descrizione vuota")
    job = _generation_manager.start(
        payload.descrizione, payload.n_file, payload.categoria_suggerita,
        lambda: _server_generate(payload.descrizione, payload.n_file, payload.categoria_suggerita),
    )
    return JSONResponse(status_code=202, content=job.to_dict())


@router.get("/api/intake/generate/{job_id}")
async def generation_status(job_id: str):
    """Stato di un job di generazione (pending/running/done/failed) con l'esito
    (generati/scartati/latenze) o l'errore leggibile."""
    job = await run_in_threadpool(_generation_manager.get, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job di generazione non trovato: {job_id}")
    return job.to_dict()


# ---------------------------------------------------------------------------
# Raffinazione LLM di un documento in staging (core/intake_refine.py): job async come
# la generazione — su un documento lungo sono decine di chiamate al modello, minuti di
# lavoro, mai sull'event loop. L'esito resta in STAGING: la review S2 non si scavalca.
# ---------------------------------------------------------------------------
# Manager dedicato: stessi thread daemon degli altri job, istanza separata per non
# mescolare i job di raffinazione con quelli di generazione e brief.
_refine_manager = doc_generation.GenerationManager()


@router.post("/api/intake/staged/{doc_id}/refine",
             dependencies=[Depends(require_not_cross_site_request)])
async def refine_staged_document(doc_id: str):
    """Avvia la raffinazione di un documento in staging e risponde 202 col job_id: il
    dump del convertitore diventa una spec strutturata (sezioni, tabelle, blocchi di
    codice) con frontmatter semantico. Il markdown grezzo resta in staging accanto al
    raffinato e la preview mostrerà quest'ultimo. Precondizione verificata PRIMA di
    avviare il job: il documento è ancora in stato 'staged' (404/409 altrimenti)."""
    try:
        await run_in_threadpool(intake.require_staged, doc_id)
    except Exception as exc:
        _raise_http(exc)
    job = _refine_manager.start(
        f"refine {doc_id}", 1, "",
        lambda: intake_refine.refine_staged_document(doc_id),
    )
    return JSONResponse(status_code=202, content=job.to_dict())


@router.get("/api/intake/refine/{job_id}")
async def refine_status(job_id: str):
    """Stato di un job di raffinazione (pending/running/done/failed) con l'entry
    aggiornata del journal (stats delle finestre, frontmatter semantico) o l'errore."""
    job = await run_in_threadpool(_refine_manager.get, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job di raffinazione non trovato: {job_id}")
    return job.to_dict()


# ---------------------------------------------------------------------------
# S5 — Import progetti da path locale: plan (anteprima, dry-run) + apply (additivo)
# ---------------------------------------------------------------------------
class ProjectPlanRequest(BaseModel):
    path: str
    target: str


class ProjectApplyRequest(BaseModel):
    plan_id: str | None = None
    plan: dict | None = None


# Piani recenti per plan_id (l'anteprima li produce, l'applica li consuma): stato di
# processo come il GenerationManager — un riavvio del server li dimentica e l'utente
# ripete semplicemente l'anteprima (che è comunque l'unica cosa sicura da fare dopo
# un riavvio: lo stato di code/ potrebbe essere cambiato).
_project_plans: dict[str, project_import.ImportPlan] = {}
_PROJECT_PLANS_MAX = 20


def _remember_plan(plan: project_import.ImportPlan) -> None:
    _project_plans[plan.plan_id] = plan
    while len(_project_plans) > _PROJECT_PLANS_MAX:
        _project_plans.pop(next(iter(_project_plans)))


def _native_folder_dialog() -> str | None:
    """Apre il selettore di cartelle nativo del SO sulla macchina del server (tkinter,
    stdlib): ha senso solo perché questo tool gira in locale e server/browser sono la
    stessa macchina (vedi api.deps.require_api_key, bypass su localhost). Bloccante —
    va sempre invocata dentro run_in_threadpool. None se l'utente annulla."""
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", 1)
    try:
        selected = filedialog.askdirectory(
            title="Seleziona la cartella del progetto da importare")
    finally:
        root.destroy()
    return selected or None


@router.post("/api/intake/project/browse-path",
             dependencies=[Depends(require_not_cross_site_request)])
async def browse_project_path():
    """Apre l'esplora risorse nativo sulla macchina del server per scegliere la
    cartella sorgente e ne risponde il path assoluto (None se l'utente annulla).
    Nessuna validazione qui: resta a plan_project_import (path assoluto, esistente,
    directory, mai dentro il repo/staging)."""
    try:
        path = await run_in_threadpool(_native_folder_dialog)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"selettore di cartelle non disponibile: {exc}") from exc
    return {"path": path}


@router.post("/api/intake/project/plan",
             dependencies=[Depends(require_not_cross_site_request)])
async def plan_project(payload: ProjectPlanRequest):
    """Anteprima dell'import (DRY-RUN puro, zero scritture): scansiona il path
    sorgente e classifica i file contro code/<target>/ (nuovi/identici/conflitti/
    esclusi). Validazioni in core.project_import: path assoluto, esistente,
    directory, MAI dentro il repo né dentro staging; target solo tra i tre ammessi."""
    try:
        plan = await run_in_threadpool(
            project_import.plan_project_import, payload.path, payload.target)
    except Exception as exc:
        _raise_http(exc)
    _remember_plan(plan)
    return plan.as_dict()


@router.post("/api/intake/project/apply",
             dependencies=[Depends(require_not_cross_site_request)])
async def apply_project(payload: ProjectApplyRequest):
    """Applica un piano di import (per plan_id di un'anteprima recente, o piano
    completo nel body): backup zip, copia dei SOLI file nuovi, journal, reindex delta
    del codice — tutto sotto writer lock (core.project_import.apply_project_import).
    Piano stale (stato di code/<target>/ cambiato dopo l'anteprima) → 409."""
    if payload.plan_id is not None:
        plan = _project_plans.get(payload.plan_id)
        if plan is None:
            raise HTTPException(
                status_code=404,
                detail=f"piano di import non trovato: {payload.plan_id} — ripeti l'anteprima")
    elif payload.plan is not None:
        try:
            plan = project_import.ImportPlan.from_dict(payload.plan)
        except Exception as exc:
            _raise_http(exc)
    else:
        raise HTTPException(status_code=422, detail="serve plan_id o plan")
    try:
        result = await run_in_threadpool(
            project_import.apply_project_import, plan, reindex=_server_reindex)
    except Exception as exc:
        _raise_http(exc)
    # Un piano applicato non è riutilizzabile: lo stato di code/ è cambiato per
    # costruzione (fingerprint diverso), inutile tenerlo in memoria.
    _project_plans.pop(plan.plan_id, None)
    # Il reindex delta ha promosso una nuova versione: allinea lo snapshot in memoria
    # (stesso meccanismo dell'approve dei documenti). Best-effort, mai un errore.
    await run_in_threadpool(reload_index_state)
    return result


# ---------------------------------------------------------------------------
# S6 — Project brief: sintesi architetturale grounded sul grafo, job async
# (pattern S3), esito in STAGING (source "brief") → review S2 come ogni doc.
# ---------------------------------------------------------------------------
class ProjectBriefRequest(BaseModel):
    target: str
    # Cartella sotto code/<target>/ di cui scrivere il brief. Omesso = l'ultimo progetto
    # importato in quel target: un target ne ospita più d'uno (import additivo), e senza
    # questa distinzione il brief descriveva il primo progetto in ordine di simboli.
    progetto: str | None = None


# Manager dedicato ai brief: stessi thread daemon del GenerationManager S3, istanza
# separata per non mescolare i job (e i monkeypatch dei test) con la generazione doc.
_brief_manager = doc_generation.GenerationManager()


def _server_brief(target: str, progetto: str | None) -> dict:
    """Chiude sullo snapshot di runtime del server (grafo + code_store coerenti fra
    loro, vedi IndexSnapshot): gira sul thread daemon del manager, mai sull'event loop."""
    snap = current_snapshot()
    return project_brief.generate_project_brief(
        target,
        progetto=progetto,
        graph=snap.graph if snap else None,
        code_store=snap.code_store if snap else None,
    )


@router.get("/api/intake/project/imports")
async def list_project_imports(target: str | None = None):
    """Progetti importati con successo (uno per target/cartella, dal journal), così la
    pagina può far scegliere DI QUALE progetto scrivere il brief invece di indovinare."""
    try:
        imports = await run_in_threadpool(project_brief.applied_imports, target)
    except Exception as exc:
        _raise_http(exc)
    return {"imports": imports}


@router.post("/api/intake/project/brief",
             dependencies=[Depends(require_not_cross_site_request)])
async def start_project_brief(payload: ProjectBriefRequest):
    """Avvia il job di project brief per un progetto di code/<target>/ e risponde 202 col
    job_id. Precondizioni verificate PRIMA di avviare il job: target ammesso (422) e
    import riuscito per quel target/progetto nel journal intake (altrimenti 409)."""
    try:
        await run_in_threadpool(project_brief.require_applied_import, payload.target,
                                None, payload.progetto)
    except Exception as exc:
        _raise_http(exc)
    etichetta = f"{payload.target}/{payload.progetto}" if payload.progetto else payload.target
    job = _brief_manager.start(
        f"project brief {etichetta}", 1, project_brief.BRIEF_CATEGORIA_SUGGERITA,
        lambda: _server_brief(payload.target, payload.progetto),
    )
    return JSONResponse(status_code=202, content=job.to_dict())


@router.get("/api/intake/project/brief/{job_id}")
async def project_brief_status(job_id: str):
    """Stato di un job di brief (pending/running/done/failed) con l'esito (documento
    staged, scartati, avviso "grafo senza simboli") o l'errore leggibile."""
    job = await run_in_threadpool(_brief_manager.get, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job di brief non trovato: {job_id}")
    return job.to_dict()

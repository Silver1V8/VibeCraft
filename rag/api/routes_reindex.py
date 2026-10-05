"""Route del reindex incrementale automatico: POST /api/reindex lancia (o accoda) un reindex
in background e risponde 202 con il job-id — se un reindex è già in corso la richiesta viene
accodata/fusa in un unico pending (coalescing dei path) invece di essere rifiutata, così i
webhook GitLab ravvicinati non si perdono. GET /api/reindex/{job_id} ne riporta lo stato
(queued/running/completed/failed). L'endpoint accetta anche un payload webhook GitLab
(push/merge) da cui estrae i path modificati, per limitare il delta a ciò che è cambiato.
A fine job riusa reload_index_state (il meccanismo di auto-reload esistente).

Qui vive anche la gestione delle VERSIONI blue/green dell'indice: i job full scrivono
una versione nuova e la promuovono a fine build riuscita, solo dopo che l'eval-gate
(core.eval_gate, config eval_gate.*) conferma la recall sul golden-set sopra soglia; POST
/api/index/rollback sposta il puntatore CURRENT alla versione precedente (o a quella
indicata) e ricarica lo snapshot."""
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from api.deps import (
    _graph_version,
    current_snapshot,
    reload_index_state,
    require_api_key,
    require_gitlab_token,
    require_not_cross_site_request,
    state,
    get_project, project_runtime, ensure_shared_resources,
)
from api.reindex import ReindexManager, extract_gitlab_paths
from core.artifacts import (
    current_version,
    list_versions,
    load_artifacts,
    promote_version,
    resolve_rollback_target,
    rollback_version,
)
from core import retrieval
from core.eval_gate import gate_promotion, record_alert
from core.config import COLLECTION_NAME
from core.indexing_lock import indexing_lock
from core.projects import ProjectError
from core.indexing import (
    RollbackTargetCollectionMissing,
    _migrate_legacy_collection_if_needed,
    _qdrant_collection_for_version,
    _swap_alias,
    assert_rollback_target_has_vectors,
    build_graph_and_index,
    gc_orphaned_qdrant_collections,
    incremental_index,
    rollback_qdrant_alias_if_needed,
    rollback_shares_collection_with_later_versions,
)
from core.writer_lock import WriterLockBusyError, writer_lock

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_key)])

# Timeout CORTO del writer lock attorno al rollback via HTTP: è una richiesta
# interattiva, mentre un job full del ReindexManager tiene il lock per MINUTI. Meglio
# un 409 rapido ("riprova a job finito") che un'attesa lunga sull'event loop. Distinto
# dai 30s del manager (api.reindex._WRITER_LOCK_TIMEOUT_SECONDS): là il job È il lavoro.
_ROLLBACK_WRITER_LOCK_TIMEOUT_SECONDS = 2

def project_manager(project):
    runtime = project_runtime(project)
    with runtime["lock"]:
        try:
            if "reindex_manager" not in runtime:
                runtime["reindex_manager"] = ReindexManager(project=project)
            manager = runtime["reindex_manager"]
            manager._guard_journal()
            return manager
        except (ProjectError, OSError, ValueError) as exc:
            logger.warning("Reindex storage unavailable for %s", project.id if project else "legacy", exc_info=True)
            raise HTTPException(503, detail={"code": "project_storage_error", "message": "Journal di indicizzazione non disponibile."}) from exc


def _reindex_embed_model():
    ensure_shared_resources()
    return state["embed_model"]


def _job_content(job):
    content = job.to_dict()
    if content.get("error"):
        content["error"] = "Indicizzazione non riuscita; consulta il log del server."
    if content.get("reload_error"):
        content["reload_error"] = "Caricamento dello snapshot non riuscito; consulta il log del server."
    return content


def _run_reindex(changed_paths, *, project=None) -> dict:
    """Reindex delta con le risorse condivise inizializzate una volta."""
    ensure_shared_resources()
    result = incremental_index(
        qdrant=state.get("qdrant"),
        embed_model=state.get("embed_model"),
        changed_paths=changed_paths, project=project,
    )
    if result.get("noop") is True:
        disk_version = current_version(project) or _graph_version(project)
        snapshot = current_snapshot(project)
        if snapshot is not None and snapshot.version == disk_version:
            result["snapshot_token"] = snapshot.version
    return result


def _eval_gate(version: str, embed_model, *, project=None) -> dict:
    """Eval-gate sulla versione APPENA COSTRUITA (non ancora promossa): carica i suoi sidecar
    e delega alla logica canonica core.eval_gate.gate_promotion, valutando la STESSA
    collection candidata su cui quella versione è stata costruita (letta dal suo
    manifest), mai la produzione. Un candidato illeggibile non supera il gate."""
    try:
        arts = load_artifacts(required=("graph", "colbert", "chunks"), version=version, project=project)
    except Exception as exc:
        logger.warning("Eval-gate: artefatti candidati %s non caricabili (%s): promozione bloccata.",
                       version, exc)
        return {"passed": False, "skipped": "load_error", "version": version,
                "error": "Artefatti candidati non disponibili"}
    collection_name = _qdrant_collection_for_version(version, project=project)
    try:
        return gate_promotion(version, state.get("qdrant"), embed_model,
                              arts.colbert_store, emit=logger.info, collection_name=collection_name,
                              graph=arts.graph,
                              restatements=retrieval.restatement_sections(arts.chunks_store), project=project)
    finally:
        close = getattr(arts.colbert_store, "close", None)
        if close is not None:
            close()


def _run_full_rebuild(changed_paths, *, project=None) -> dict:
    """Job "full": ricostruzione completa (build_graph_and_index) con un modello di embedding
    condiviso (vedi _reindex_embed_model), riusato anche per l'eval-gate che segue.
    `changed_paths` è ignorato (un full non ha delta). Gira sul thread daemon del
    ReindexManager: è così che OGNI scrittura degli artefatti passa da un solo scrittore.

    Blue/green: la build scrive una versione NUOVA (su una collection candidata
    versionata) senza promuoverla; la promozione passa dall'eval-gate (config
    eval_gate.*): se la recall sul golden-set scende sotto soglia e il gate è in
    modalità blocking, la versione resta su disco NON promossa (CURRENT invariato) e
    il job termina "completed_not_promoted" col report nell'esito — la collection
    candidata resta orfana su Qdrant, rimossa dal GC del prossimo job/boot riuscito.

    A gate passato, la promozione sposta PRIMA CURRENT (il commit point locale) e
    SOLO DOPO l'alias `COLLECTION_NAME` sulla collection candidata — la stessa
    dichiarata nel manifest della versione appena promossa
    (`_qdrant_collection_for_version`: unico source of truth, mai una ricostruzione
    indipendente del nome). In mezzo, SOLO se necessario, la migrazione one-shot
    legacy→alias (`_migrate_legacy_collection_if_needed`): se `COLLECTION_NAME` esiste
    ancora come collection FISICA (installazione non ancora migrata), viene
    cancellata per liberare il nome subito prima dello swap che la ricrea come alias
    — l'UNICA operazione irreversibile di questo meccanismo, con una finestra di
    indisponibilità breve ma reale fra le due chiamate. Se il layout è già migrato o
    l'installazione è fresca, la migrazione è un no-op. Subito dopo lo swap, il GC
    rimuove le collection versionate orfane."""
    started = time.perf_counter()
    embed_model = _reindex_embed_model()
    init_model = time.perf_counter() - started
    collector = {
        "phase_timings_seconds": {phase: 0.0 for phase in
                                  ("init_model", "scan_hash", "load", "parsing_embedding",
                                   "qdrant", "relink", "save_hash", "eval_gate", "promote")},
        "counts": {},
    }
    version = build_graph_and_index(qdrant=state.get("qdrant"),
                                    embed_model=embed_model, promote=False,
                                    collector=collector, project=project)
    timings = collector["phase_timings_seconds"]
    timings["init_model"] += init_model
    result = {"full_rebuild": True, "version": version,
              "phase_timings_seconds": timings, "counts": collector["counts"]}
    if "colbert_io_bytes" in collector:
        result["colbert_io_bytes"] = collector["colbert_io_bytes"]
    if version:  # None solo con build finta nei test
        started = time.perf_counter()
        gate = _eval_gate(version, embed_model, project=project)
        timings["eval_gate"] = time.perf_counter() - started
        result["eval"] = {kk: gate[kk] for kk in
                          ("recall", "k", "min_recall", "n", "skipped", "advisory") if kk in gate}
        if not gate.get("passed"):
            result["promoted"] = False
            result["job_status"] = "completed_not_promoted"
            logger.warning("Full rebuild %s NON promosso: eval-gate sotto soglia (%s).",
                           version, result["eval"])
            return result

        started = time.perf_counter()
        promote_version(version, project=project)
        collection_name = _qdrant_collection_for_version(version, project=project)
        _migrate_legacy_collection_if_needed(state.get("qdrant"), project.collection_name if project else COLLECTION_NAME, emit=logger.info)
        _swap_alias(state.get("qdrant"), project.collection_name if project else COLLECTION_NAME, collection_name)
        # GC: stesso punto consentito del path CLI (core.indexing.build_graph_and_index)
        # — dopo promote (retention locale già applicata) e dopo lo swap, dentro il
        # single-writer del ReindexManager (mai job full concorrenti).
        gc_orphaned_qdrant_collections(state.get("qdrant"), emit=logger.info, project=project)
        timings["promote"] += time.perf_counter() - started
    result["promoted"] = True
    return result


def enqueue_full_rebuild(project) -> tuple:
    """Accoda (o fonde) un full rebuild nella coda del manager. Restituisce `(job, queued)`.
    Usata anche dalle route dell'archive (Step 5), che non devono più chiamare
    build_graph_and_index inline: un solo scrittore per costruzione."""
    return project_manager(project).start(None, lambda paths: _run_full_rebuild(paths, project=project),
                                          lambda: reload_index_state(project), kind="full")


@router.post("/api/reindex", dependencies=[Depends(require_gitlab_token),
                                           Depends(require_not_cross_site_request)])
async def start_reindex(request: Request, project=Depends(get_project)):
    """Avvia (o accoda) un reindex incrementale in background e risponde 202 con il job-id.

    Il corpo è opzionale: se contiene un payload webhook GitLab (push) o un override
    esplicito `{"paths": [...]}`, i path modificati limitano il delta; altrimenti si fa
    un incrementale completo su docs/ + code/. Un corpo `{"full": true}` richiede invece
    un FULL REBUILD (build_graph_and_index) via coda. Se un reindex è già in corso la
    richiesta NON viene rifiutata: è accodata/fusa in un unico pending e la risposta
    riporta `{"job_id": <id del pending>, "queued": true}`."""
    try:
        payload = await request.json()
    except Exception:
        payload = None  # corpo assente o non-JSON: incrementale completo

    if isinstance(payload, dict) and payload.get("full") is True:
        job, queued = enqueue_full_rebuild(project)
    else:
        changed_paths = extract_gitlab_paths(payload) if payload is not None else None
        job, queued = project_manager(project).start(changed_paths, lambda paths: _run_reindex(paths, project=project),
                                                     lambda: reload_index_state(project))
    content = _job_content(job)
    if queued:
        content["queued"] = True
    return JSONResponse(status_code=202, content=content)


@router.get("/api/reindex")
async def list_reindex(limit: int = 20, project=Depends(get_project)):
    """Lista degli ultimi `limit` job di reindex (default 20), più recente prima — utile
    per debug e per la UI. Ricostruita dal journal al boot, quindi sopravvive ai riavvii."""
    if limit < 1:
        limit = 1
    jobs = await run_in_threadpool(project_manager(project).list_recent, limit)
    for job in jobs:
        if job.get("error"):
            job["error"] = "Indicizzazione non riuscita; consulta il log del server."
        if job.get("reload_error"):
            job["reload_error"] = "Caricamento dello snapshot non riuscito; consulta il log del server."
    return {"jobs": jobs}


@router.get("/api/reindex/{job_id}")
async def reindex_status(job_id: str, project=Depends(get_project)):
    """Stato di un job di reindex (running/completed/completed_not_promoted/failed)
    con il risultato o l'errore."""
    job = await run_in_threadpool(project_manager(project).get, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job di reindex non trovato: {job_id}")
    return _job_content(job)


# ---------------------------------------------------------------------------
# Versioni blue/green: lista e rollback istantaneo
# ---------------------------------------------------------------------------
@router.get("/api/index/versions")
async def index_versions(project=Depends(get_project)):
    """Versioni dell'indice presenti su disco (ordine cronologico) e quella attiva."""
    versions = await run_in_threadpool(list_versions, project)
    return {"current": await run_in_threadpool(current_version, project), "versions": versions}


def _rollback_under_writer_lock(target, project) -> tuple:
    """Esegue l'INTERA mutazione del rollback — rollback_version (sposta CURRENT) +
    rollback_qdrant_alias_if_needed (riallinea l'alias Qdrant) — dentro un solo writer
    lock cross-processo, restituendo `(name, qdrant_alias, shared_later)`.

    `shared_later` (rollback_shares_collection_with_later_versions, core.qdrant_versions) è
    la lista delle versioni POSTERIORI al target che dichiarano la sua stessa
    collection Qdrant: lista non vuota = incrementali successivi l'hanno mutata in
    place e il rollback locale NON riavvolge Qdrant. La detection legge i manifest,
    quindi sta anch'essa sotto il lock: mai interlacciata con la promote di un full.

    Perché entrambe sotto lo STESSO lock: muovono CURRENT e l'alias Qdrant e non devono
    interlacciarsi con la promote di un full rebuild del ReindexManager (che promuove
    vN e poi swappa l'alias su c(vN)); senza mutua esclusione un rollback in mezzo
    lascerebbe CURRENT=vOld ma la produzione su c(vN) — stato divergente.

    Il lock è per-handle e bloccante: va acquisito e rilasciato NELLO STESSO thread,
    dentro questa unica funzione sync passata a run_in_threadpool — mai spezzato su due
    chiamate né tenuto attraverso l'event loop. Timeout corto
    (_ROLLBACK_WRITER_LOCK_TIMEOUT_SECONDS): a lock occupato solleva WriterLockBusyError,
    mappato a 409 dal chiamante. reload_index_state resta FUORI (sola lettura, dopo la
    mutazione)."""
    ensure_shared_resources(embedding=False)
    if not indexing_lock.acquire(timeout=_ROLLBACK_WRITER_LOCK_TIMEOUT_SECONDS):
        raise WriterLockBusyError("Process indexing slot busy")
    try:
        with writer_lock(timeout_seconds=_ROLLBACK_WRITER_LOCK_TIMEOUT_SECONDS, project=project):
            # Pre-check PRIMA della mutazione (R14): se la collection Qdrant della versione
            # target non esiste più, il rollback lascerebbe CURRENT sul target e la
            # produzione altrove — stato misto che nessuno ripara e che il check di
            # integrità non vedeva. Solleva RollbackTargetCollectionMissing senza aver
            # toccato nulla; Qdrant irraggiungibile ⇒ nessun blocco (vedi la funzione).
            name = resolve_rollback_target(target, project=project)
            if state.get("qdrant") is not None:
                assert_rollback_target_has_vectors(state.get("qdrant"), name, project=project)
            name = rollback_version(name, project=project)
            shared_later = rollback_shares_collection_with_later_versions(name, project=project)
            qdrant_alias = rollback_qdrant_alias_if_needed(state.get("qdrant"), name, logger.info, project=project)
    finally:
        indexing_lock.release()
    return name, qdrant_alias, shared_later


def _record_shared_collection_rollback_alert(name: str, later_versions: list[str], project) -> None:
    """Alert warning su database/alerts.jsonl quando un rollback lascia Qdrant non
    riavvolto (collection condivisa con versioni posteriori): è il canale che degrada
    GET /api/health per 48h (api.routes_health.read_last_alert). Riusa
    core.eval_gate.record_alert col path di default — stesso file, stesso formato;
    `source` passato nei details sovrascrive il "eval_gate" del formato base."""
    record_alert(
        "warning",
        f"Rollback a {name}: la collection Qdrant del target è condivisa con versioni "
        f"successive ({', '.join(later_versions)}) — incrementali posteriori l'hanno "
        f"mutata in place, Qdrant NON riavvolto. Full rebuild consigliato.",
        source="rollback", target_version=name, later_versions=later_versions,
        **({"path": project.database_dir / "alerts.jsonl"} if project else {}),
    )


@router.post("/api/index/rollback",
             dependencies=[Depends(require_not_cross_site_request)])
async def index_rollback(request: Request, project=Depends(get_project)):
    """Rollback blue/green ISTANTANEO: sposta il puntatore database/CURRENT alla
    versione indicata (corpo JSON opzionale `{"version": "v..."}`; default: la
    precedente) e ricarica subito lo snapshot in memoria. Nessuna build, nessuna copia.

    core.artifacts.rollback_version resta puro locale (sposta solo CURRENT). DOPO il
    rollback locale l'alias `COLLECTION_NAME` viene riallineato alla collection della
    versione target (rollback_qdrant_alias_if_needed, core.qdrant_versions): cross-lineage →
    swap; intra-lineage (alias già corretto) → no-op.

    Se la collection della versione target NON esiste più su Qdrant il rollback è
    RIFIUTATO con 409 PRIMA di qualunque mutazione (assert_rollback_target_has_vectors):
    CURRENT non si muove, l'alias nemmeno, e il messaggio nomina la collection mancante
    e il rimedio (re-indicizzazione completa). Prima si mutava CURRENT lo stesso e la
    risposta portava solo uno stato "missing_target_collection": stato misto durevole
    (sidecar del target, vettori di un'altra build) che nessun reconciler ripara — vedi
    rag/AUDIT.md A20 / RESIDUI R14. Lo stato "missing_target_collection" resta possibile
    solo se la collection sparisce fra il pre-check e lo swap, o se il pre-check è stato
    saltato perché Qdrant non era raggiungibile.

    Se versioni POSTERIORI al target condividono la sua collection Qdrant (incrementali
    intra-lineage che l'hanno mutata in place), la risposta porta anche una
    "qdrant_note" ("shared_collection_not_rewound") e viene registrato un alert warning
    su alerts.jsonl (source="rollback"), che degrada GET /api/health per 48h.

    L'intera mutazione (CURRENT + alias) gira sotto il writer lock cross-processo, in
    mutua esclusione con la promote dei job full (vedi _rollback_under_writer_lock). Se
    un job full tiene il lock, si risponde 409 senza toccare nulla, invitando a
    riprovare a job finito."""
    try:
        payload = await request.json()
    except Exception:
        payload = None
    target = payload.get("version") if isinstance(payload, dict) else None
    try:
        name, qdrant_alias, shared_later = await run_in_threadpool(
            _rollback_under_writer_lock, target, project)
    except WriterLockBusyError:
        # Distinto dal 409 del ValueError sotto: qui il rollback NON è stato tentato,
        # un altro scrittore (tipicamente un job full) detiene il lock. Il messaggio
        # dell'eccezione porta pid/timestamp del detentore.
        raise HTTPException(
            status_code=409,
            detail="Writer lock occupato: un reindex/full rebuild è in corso, "
                   "rollback non eseguito — riprova a job finito.",
        )
    except RollbackTargetCollectionMissing as exc:
        # 409 come gli altri conflitti di stato, ma qui NULLA è stato mutato: CURRENT
        # non si è mosso e l'alias nemmeno. Il messaggio nomina la collection mancante
        # e il rimedio (re-indicizzazione completa).
        raise HTTPException(status_code=409, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Rollback non disponibile: controlla la versione e ripeti una indicizzazione completa.")
    except ValueError:
        raise HTTPException(status_code=409, detail="Rollback non disponibile: controlla la versione e ripeti una indicizzazione completa.")
    await run_in_threadpool(reload_index_state, project)
    response = {
        "rolled_back_to": name,
        "versions": await run_in_threadpool(list_versions, project),
        "qdrant_alias": qdrant_alias,
    }
    if shared_later:
        # Collection condivisa con versioni posteriori (incrementali intra-lineage):
        # il rollback locale è avvenuto ma Qdrant NON è stato riavvolto. Warning, non
        # errore: nota esplicita nella risposta + alert su alerts.jsonl (degrada
        # /api/health per 48h).
        response["qdrant_note"] = {
            "state": "shared_collection_not_rewound",
            "later_versions": shared_later,
            "hint": "Qdrant non riavvolto: full rebuild consigliato",
        }
        await run_in_threadpool(_record_shared_collection_rollback_alert, name, shared_later, project)
    return response

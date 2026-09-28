"""Route della pipeline Explore -> Canvas -> Propose -> Validate -> Drift -> Archivio, più
esecuzione via Claude Agent SDK, dry-run, [AGENT CONTEXT], export e gestione file. Gli
handler orchestrano I/O e concorrenza (async/threadpool/streaming) e iniettano le risorse
di runtime dallo stato (api.deps) nelle funzioni pure di core.pipeline / core.retrieval."""
import functools
from datetime import datetime, timedelta, timezone
from contextlib import nullcontext, contextmanager
from uuid import uuid4
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

from agent_bridge import AGENT_MODES
from agent_runners import RUNNERS, list_runners, run_streaming as run_agent_streaming, validate_run
from api.deps import (
    IndexSnapshot,
    current_snapshot,
    embed_in_threadpool,
    require_api_key,
    require_api_key_strict,
    require_not_cross_site_request,
    run_streaming,
    state,
)
from api.models import (
    AgentRunRequest,
    ArchiveRequest,
    CanvasGenerateRequest,
    DriftCheckRequest,
    ExploreSaveRequest,
    ExploreTurnRequest,
    PipelineFileSaveRequest,
    ProposeGenerateRequest,
    ValidateRequest,
    OpenPointDecisionRequest,
)
from api.routes_reindex import enqueue_full_rebuild
from core import canvas_review, llm, pipeline, retrieval, spec_format, pipeline_gate as gate, pipeline_validation as validation
from core import pipeline_activity, verification
from core.artifacts import manifest_path
from core.pipeline_store import PipelineStore, PipelineStorageError, PipelineStorageBusyError
from core.writer_lock import WriterLockBusyError
from core.open_points import read_report
from core.config import (
    CHANGES_DIR,
    GOVERNED_MAX_CHUNKS,
    PROJECT_ROOT,
    TECH_MAX_CHUNKS,
    TECH_SCOPE_TAG_KEY,
)
from core.indexing import archive_feature, check_drift, check_index_integrity, index_status, _docs_hashes
from core.pipeline import (
    FINAL_PROMPT_CONSUMERS,
    InvalidDevTypeError,
    InvalidFeatureNameError,
    build_final_prompt,
    feature_dir,
    generate_tolerant,
    list_dev_types,
    load_dev_type,
    resolve_feature_dir,
    save_dev_type,
    slugify_feature,
    validate_dev_type,
)

router = APIRouter(dependencies=[Depends(require_api_key)])
pipeline_store = PipelineStore()

PIPELINE_FILES = ("explore.md", "canvas.md", "spec.md")


def _safe_slug(feature_name: str) -> str:
    """slugify_feature con conversione esplicita in 400 Bad Request: un nome feature
    non valido (vuoto, solo separatori, tentativo di path traversal) diventa un errore
    HTTP chiaro invece di propagare fino a un 500 non gestito."""
    try:
        return slugify_feature(feature_name)
    except InvalidFeatureNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _safe_dev_type(dev_type: str) -> str:
    """validate_dev_type con conversione esplicita in 400 Bad Request: un dev_type
    fuori dalla whitelist di list_dev_types() (diventerebbe CODE_DIR / dev_type in
    core.indexing.check_drift) viene rifiutato PRIMA di generare/scrivere alcunché,
    invece di far fallire a metà lavoro la chiamata a save_dev_type."""
    try:
        return validate_dev_type(dev_type)
    except InvalidDevTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _safe_feature_dir(feature_name: str, *, create: bool = False) -> Path:
    """Risolve changes/<slug(feature_name)>, convertendo un nome non valido (o un
    tentativo di uscire da CHANGES_DIR) in 400 Bad Request. `create=True` crea la
    cartella se assente (equivalente a pipeline.feature_dir, ma con errore HTTP
    esplicito invece di propagare l'eccezione)."""
    try:
        if create:
            return feature_dir(feature_name)
        return resolve_feature_dir(CHANGES_DIR, feature_name)
    except InvalidFeatureNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _snap_fields(snap: IndexSnapshot | None):
    """Estrae (graph, chunks, colbert_store) dallo snapshot, con fallback vuoti se assente.
    Le connessioni qdrant/embed_model vivono fuori dallo snapshot (state[...])."""
    if snap is None:
        return None, {}, None
    return snap.graph, snap.chunks, snap.colbert_store


def _governed_context(question: str, snap: IndexSnapshot | None) -> str:
    """Contesto NORMATIVO governato per `question` (safeguard, permessi, glossario): quello
    che i prompt presentano come «vincoli da rispettare e verificare». Iniezione delle risorse
    dallo snapshot, preso una volta dal chiamante.
    Sincrono (CPU-bound: embedding della query) → threadpool."""
    graph, chunks, colbert_store = _snap_fields(snap)
    return retrieval.retrieve_governed_context(
        question,
        graph=graph, chunks_store=chunks, max_chunks=GOVERNED_MAX_CHUNKS,
        qdrant=state.get("qdrant"), embed_model=state.get("embed_model"),
        colbert_store=colbert_store,
    )


def _tech_context(dev_type: str, snap: IndexSnapshot | None) -> str:
    """Contesto TECNICO dell'ambito `dev_type`: con quale stack e quali pattern si costruisce.
    Tenuto separato dal normativo perché ha un ruolo opposto — non è un vincolo da verificare
    con scenari, è il COME — e i prompt lo presentano con istruzioni proprie.

    Due accorgimenti: una domanda dedicata (una query di dominio non fa mai risalire una spec
    tecnologica) e il filtro sull'ambito dichiarato dai documenti (le spec tecnologiche di
    ambiti diversi sono quasi gemelle e la semantica da sola non le separa).
    '' se non c'è un dev_type o se il progetto non dichiara gli ambiti."""
    tech_query = pipeline.build_tech_query(dev_type)
    if not tech_query:
        return ""
    graph, chunks, colbert_store = _snap_fields(snap)
    return retrieval.retrieve_governed_context(
        tech_query,
        graph=graph, chunks_store=chunks, max_chunks=TECH_MAX_CHUNKS,
        qdrant=state.get("qdrant"), embed_model=state.get("embed_model"),
        colbert_store=colbert_store,
        query_filter=retrieval.scope_tag_filter(TECH_SCOPE_TAG_KEY,
                                                pipeline.dev_type_tag_variants(dev_type)),
    )


def _canvas_lessons(query: str, snap: IndexSnapshot | None) -> str:
    """Lezioni dalle canvas review archiviate più simili all'intent corrente (retrieval
    semantico). '' se non ci sono review indicizzate o l'indice non è pronto: il flusso
    canvas funziona identico. Sincrono (embedding della query) → threadpool."""
    _, chunks, colbert_store = _snap_fields(snap)
    return canvas_review.retrieve_canvas_lessons(
        query,
        qdrant=state.get("qdrant"), embed_model=state.get("embed_model"),
        colbert_store=colbert_store, chunks_store=chunks,
    )


def _agent_context(feature: str, dev_type: str, snap: IndexSnapshot | None) -> dict:
    """Blocco [AGENT CONTEXT] iniettando le risorse dallo snapshot. Sincrono → threadpool."""
    graph, _, colbert_store = _snap_fields(snap)
    return pipeline.build_agent_context(
        feature, dev_type,
        graph=graph, qdrant=state.get("qdrant"),
        embed_model=state.get("embed_model"), colbert_store=colbert_store,
    )


@router.get("/api/pipeline/agent/modes")
async def agent_modes():
    """Elenca le modalità di fiducia disponibili per l'esecuzione con Claude Code."""
    return {"modes": [{"id": k, "label": v["label"]} for k, v in AGENT_MODES.items()]}


@router.get("/api/pipeline/agent/runners")
async def agent_runners():
    """Runner disponibili (Claude, LLM locale, Codex, Cursor) con modalità e modelli.

    `max_attempts` è il tetto dei run per richiesta agentic (il primo più i rilanci
    automatici sulle failure della suite): lo espone il server perché la tendina della UI
    non offra un numero che poi verrebbe tagliato in silenzio."""
    return {"runners": await run_in_threadpool(list_runners),
            "max_attempts": int((verification._settings().get('max_attempts') or 1))}


def _verification_event(result, attempt_id, attempts_left) -> str:
    payload = dict(result.as_dict(), type='verification', attempt_id=attempt_id,
                   attempts_left=attempts_left)
    payload.pop('output', None)  # l'output intero resta fuori dallo stream di controllo
    payload['output_tail'] = result.output[-1200:]
    return json.dumps(payload, ensure_ascii=False) + '\n'


def _verified_runs(req, record, prompt, stream, attempt, retry, details):
    """Stream del run, poi la VERIFICA ESEGUITA dal server, poi l'eventuale rilancio.

    È qui che "implementato" smette di essere una dichiarazione: l'agente non ha shell e
    il suo resoconto è agent_reported, quindi l'unico esito osservato è quello della suite
    eseguita dal server su code/<dev_type> (core/verification.py).

    Il rilancio è un `while` sul risultato di quella suite, non un secondo modello che
    giudica il primo: finché la suite è rossa e restano tentativi, si riparte dallo stesso
    contratto con l'output delle failure in coda al prompt. Ogni giro è un retry registrato
    nel journal (retry_of_attempt_id), quindi la catena resta ispezionabile.

    Un esito 'unavailable' NON conta come verde e NON viene ritentato: manca lo strumento
    di misura, e rilanciare l'agente non produrrebbe informazione nuova."""
    yield from stream
    # Solo agentic scrive codice: in suggest non si applica (sola lettura) e oneshot non ha file.
    if req.mode != 'agentic' or record is None:
        return

    ceiling = int((verification._settings().get('max_attempts') or 1))
    attempts_left = max(0, min(req.max_attempts, ceiling) - 1)
    current, current_details = attempt, details

    while True:
        result = verification.run_suite(record.dev_type)
        try:
            pipeline_store.append_event(
                'verification_finished', feature=current_details['feature'], attempt_id=current,
                retry_of_attempt_id=current_details.get('retry_of_attempt_id'),
                status=result.status, dev_type=result.dev_type, command=result.command,
                exit_code=result.exit_code, duration_seconds=result.duration_seconds,
                reason=result.reason)
        except PipelineStorageError as exc:
            # Il journal non registra: l'esito resta comunque nello stream, dichiarato come
            # non registrato. Non si finge che la verifica non sia avvenuta.
            yield json.dumps(dict(type='verification_unrecorded', attempt_id=current,
                                  detail=str(exc)), ensure_ascii=False) + '\n'

        retry_possible = result.status == verification.FAILED and attempts_left > 0
        yield _verification_event(result, current, attempts_left if retry_possible else 0)
        if not retry_possible:
            return
        if blocked := _budget_block(req.runner):
            yield json.dumps(dict(type='retry_blocked', attempt_id=current, detail=blocked),
                             ensure_ascii=False) + '\n'
            return

        attempts_left -= 1
        previous, current = current, 'attempt-' + uuid4().hex
        current_details = dict(details, attempt_id=current, retry_of_attempt_id=previous)
        retry_prompt = prompt + verification.failure_brief(result)
        try:
            pipeline_store.append_event('execution_started', **current_details)
        except PipelineStorageError as exc:
            yield json.dumps(dict(type='retry_blocked', attempt_id=current,
                                  detail=f'Rilancio non registrabile: {exc}'), ensure_ascii=False) + '\n'
            return

        yield json.dumps(dict(type='retry', attempt_id=current, retry_of_attempt_id=previous,
                              attempts_left=attempts_left), ensure_ascii=False) + '\n'
        try:
            next_stream = run_agent_streaming(req.runner, retry_prompt, req.mode, req.model,
                                              feature=current_details['feature'], attempt_id=current,
                                              on_finish=_finished_recorder(current_details))
        except Exception as exc:
            _finished_recorder(current_details)({'type': 'error'})
            yield json.dumps(dict(type='retry_blocked', attempt_id=current,
                                  detail=f'Runtime agente non disponibile: {exc}'), ensure_ascii=False) + '\n'
            return
        yield from next_stream


# Runner il cui costo finisce nel budget Claude giornaliero (llm_settings.budget): solo
# `claude` spende sull'account Anthropic e riporta total_cost_usd. `local` (Ollama) è
# gratuito; codex/cursor fatturano su account propri e non riportano un costo.
_BUDGETED_RUNNERS = frozenset({'claude'})


def _budget_block(runner: str) -> str | None:
    """Messaggio di rifiuto se il runner è a pagamento e il budget del giorno è esaurito."""
    if runner not in _BUDGETED_RUNNERS or (hit := llm.budget_exhausted()) is None:
        return None
    spent, threshold = hit
    return (f'Budget Claude giornaliero esaurito (spesa {spent:.2f} USD, soglia {threshold:.2f} USD): '
            'i run del runner claude riprendono dopo la mezzanotte UTC. Usa il runner locale '
            'o alza llm_settings.budget.daily_usd.')


def _seconds_to_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    return max(1, int((now.replace(hour=0, minute=0, second=0, microsecond=0)
                       + timedelta(days=1) - now).total_seconds()))


def _finished_recorder(attempt_details):
    def finished(outcome):
        pipeline_store.append_event('execution_finished', **attempt_details,
            outcome='failed' if outcome.get('is_error') or outcome['type'] != 'result' else 'completed',
            result_open_points_status=outcome.get('open_points_status', 'missing'))
    return finished


@router.post("/api/pipeline/agent/run", dependencies=[Depends(require_api_key_strict)])
async def agent_run(req: AgentRunRequest):
    """Ammissione ricalcolata dal server; solo agentic richiede il contratto validato."""
    if req.mode not in AGENT_MODES:
        raise HTTPException(status_code=400, detail=f"Modalità non valida: {req.mode}")
    if reason := validate_run(req.runner, req.mode, req.model):
        raise HTTPException(status_code=400, detail=reason)
    if req.mode != 'agentic' and not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt vuoto.")
    # Budget prima di gate e journal: il rifiuto non è un esito del contratto. 429 come le
    # altre quote del server (/ask), con Retry-After fino all'azzeramento del contatore.
    if blocked := await run_in_threadpool(_budget_block, req.runner):
        raise HTTPException(status_code=429, detail=blocked,
                            headers={'Retry-After': str(_seconds_to_utc_midnight())})
    feature = _safe_slug(req.feature) if req.feature else None
    attempt = 'attempt-' + uuid4().hex

    def admit():
        with pipeline_store.feature_lock(feature) if req.mode == 'agentic' else nullcontext():
            contract, record, issues = None, None, []
            try:
                if feature:
                    contract = _read_gate_contract(feature)
                    if req.validation_id:
                        record = pipeline_store.read_validation(feature, req.validation_id)
            except (PipelineStorageError, OSError, UnicodeError) as exc:
                issues.append(gate.AvailabilityIssue(code='storage_unavailable', message=str(exc),
                                                    action=getattr(exc, 'action', 'operator_action')))
            retry_valid = True
            try:
                retry_valid = pipeline_store.retry_exists(feature, req.retry_of_attempt_id)
            except PipelineStorageError as exc:
                retry_valid = None  # non verificato: non propagare la provenienza dichiarata dal client
                issues.append(gate.AvailabilityIssue(code='storage_unavailable', message=str(exc), action=exc.action))
            payload = _gate_payload(contract, record, issues, retry_reference_valid=retry_valid is not False)
            decision = payload['gate']
            retry = req.retry_of_attempt_id if retry_valid else None
            details = dict(feature=feature, attempt_id=attempt, retry_of_attempt_id=retry,
                           validation_id=req.validation_id, mode=req.mode, gate=decision,
                           open_points_status=decision['open_points_status'])
            if req.mode == 'agentic' and not decision['allowed']:
                attempt_recorded = False
                try:
                    pipeline_store.append_event('execution_blocked', **details)
                    attempt_recorded = True
                except PipelineStorageError as exc:
                    issues.append(gate.AvailabilityIssue(code='storage_unavailable', message=str(exc), action=exc.action))
                    decision = _gate_payload(contract, record, issues, retry_reference_valid=retry_valid is not False)['gate']
                raise HTTPException(status_code=decision['http_status'], detail={**decision, 'attempt_id':attempt,
                                     'retry_of_attempt_id':retry, 'attempt_recorded':attempt_recorded})
            prompt = req.prompt
            if req.mode == 'agentic':
                prompt = pipeline.build_agent_prompt(record.feature, record.dev_type, 'agentic',
                                                     contract=record.contract, mcp=req.runner == 'claude')
                prompt += '\nValidazione autorizzante: ' + record.validation_id
            try:
                pipeline_store.append_event('execution_started', **details)
            except PipelineStorageError as exc:
                if req.mode == 'agentic':
                    issues.append(gate.AvailabilityIssue(code='storage_unavailable', message=str(exc), action=exc.action))
                    decision = _gate_payload(contract, record, issues)['gate']
                    raise HTTPException(status_code=503, detail={**decision, 'attempt_id':attempt,
                                         'retry_of_attempt_id':retry, 'attempt_recorded':False}) from exc
                issues.append(gate.AvailabilityIssue(code='storage_unavailable',
                    message=str(exc) + '; misura incompleta.', action=exc.action))
                decision = _gate_payload(contract, record, issues)['gate']
            finished = _finished_recorder(details)
            try:
                stream = run_agent_streaming(req.runner, prompt, req.mode, req.model, feature=feature,
                                             attempt_id=attempt, on_finish=finished)
            except Exception as exc:
                finished({'type':'error'})
                raise _gate_storage_error(PipelineStorageError(f'Runtime agente non disponibile: {exc}')) from exc
            def output():
                yield json.dumps(dict(type='gate', gate=decision, attempt_id=attempt,
                                      retry_of_attempt_id=retry), ensure_ascii=False) + '\n'
                yield from _verified_runs(req, record, prompt, stream, attempt, retry, details)
            return StreamingResponse(output(), media_type='application/x-ndjson')
    try:
        return await run_in_threadpool(admit)
    except PipelineStorageError as exc:
        error = _gate_storage_error(exc)
        recorded = False
        try:
            pipeline_store.append_event('execution_blocked', feature=feature, attempt_id=attempt,
                validation_id=req.validation_id, mode=req.mode, gate=error.detail,
                open_points_status=error.detail['open_points_status'])
            recorded = True
        except PipelineStorageError:
            pass  # il 503 resta esplicito; nessun riferimento verificabile alla ripresa
        error.detail.update(attempt_id=attempt, retry_of_attempt_id=None, attempt_recorded=recorded)
        raise error from exc


@router.get("/api/pipeline/dev-types")
async def pipeline_dev_types():
    """Elenca le tipologie di sviluppo disponibili (sottocartelle di 'code/') per la tendina di selezione."""
    return {"dev_types": list_dev_types()}


@router.post("/api/pipeline/explore/turn",
             dependencies=[Depends(require_not_cross_site_request)])
async def pipeline_explore_turn(req: ExploreTurnRequest):
    """Esegue un turno di intervista (equivalente al loop input() di explore.py)."""
    scope_note = (
        f" Il tipo di sviluppo richiesto per questa feature è '{req.dev_type}' (cartella code/{req.dev_type}): "
        f"concentra le domande esclusivamente sugli aspetti pertinenti a questo ambito."
        if req.dev_type else ""
    )
    history = req.history or (
        f"Sei un Tech Lead e un 'thinking partner'. Stiamo definendo i requisiti per "
        f"la feature: {req.feature_name}.{scope_note} Fai domande brevi e mirate per sviscerare i casi limite.\n"
    )
    prompt = history + f"\nUtente: {req.user_input}\nRispondi in modo conciso:"
    ai_response = await generate_tolerant(prompt, purpose="explore")
    new_history = history + f"\nUtente: {req.user_input}\nIA: {ai_response}"
    return {"ai_response": ai_response, "history": new_history}


@router.post("/api/pipeline/explore/save",
             dependencies=[Depends(require_not_cross_site_request)])
async def pipeline_explore_save(req: ExploreSaveRequest):
    """Salva il log dell'intervista in changes/<feature>/explore.md."""
    folder = _safe_feature_dir(req.feature_name, create=True)
    dev_type = _safe_dev_type(req.dev_type)
    with _feature_lock(folder.name):
        save_dev_type(folder, dev_type)
    dev_type_line = f"**Tipo di sviluppo:** {dev_type}\n\n" if dev_type else ""
    file_path = folder / "explore.md"
    content = f"# Intervista Explore: {req.feature_name}\n\n{dev_type_line}{req.interview_log}"
    file_path.write_text(content, encoding="utf-8")
    return {"feature_folder": folder.name, "path": "explore.md", "content": content}


@router.post("/api/pipeline/canvas/generate",
             dependencies=[Depends(require_not_cross_site_request)])
async def pipeline_canvas_generate(req: CanvasGenerateRequest):
    """Genera il REASONS Canvas a partire dall'intervista Explore (equivalente a canvas.py)."""
    folder = _safe_feature_dir(req.feature_name, create=True)
    explore_path = folder / "explore.md"

    if explore_path.exists():
        contesto_intervista = explore_path.read_text(encoding="utf-8")
    else:
        contesto_intervista = "Nessun log di intervista dettagliato disponibile."

    # Àncora il Canvas al knowledge base governato: recupera dal Graph RAG i documenti
    # normativi pertinenti (safeguard, glossario, matrice permessi), pesati per autorità,
    # invece di affidarsi a un contesto statico scritto a mano. Il dev_type è risolto qui
    # perché guida anche il ramo tecnico del retrieval, non solo la cartella di output.
    # Validato SUBITO (whitelist di list_dev_types()), prima di spendere un retrieval/LLM:
    # diventa un componente di path (CODE_DIR / dev_type) in core.indexing.check_drift.
    dev_type = _safe_dev_type(req.dev_type or load_dev_type(folder))
    snap = current_snapshot()
    query = f"{req.feature_name}\n{contesto_intervista[:2000]}"
    governed_context = await embed_in_threadpool(_governed_context, query, snap)
    contesto_progetto_base = governed_context or "Nessun documento normativo pertinente recuperato dal Graph RAG."
    # Contesto tecnico: blocco separato nel prompt (vedi build_canvas_prompt), non fuso col
    # normativo — hanno ruoli diversi e istruzioni diverse.
    contesto_tecnico = await embed_in_threadpool(_tech_context, dev_type, snap)

    # Persiste in meta.json QUALI documenti hanno ancorato questo canvas (normativi + tecnici):
    # all'archive diventano gli `expected` di un caso candidato per il golden-set di eval.
    with _feature_lock(folder.name):
        pipeline.save_governed_sources(
            folder, pipeline.governed_docs_from_context(governed_context + "\n\n" + contesto_tecnico))

    # Canvas che apprende (parte 2): le divergenze emerse nelle review delle change
    # archiviate più simili diventano "lezioni" nel prompt ('' se non esistono review).
    lessons = await embed_in_threadpool(_canvas_lessons, query, snap)

    prompt_strutturato = pipeline.build_canvas_prompt(
        req.feature_name, contesto_intervista, contesto_progetto_base, dev_type, lessons,
        contesto_tecnico
    )

    # Generazione DIRETTA (non generate_tolerant): un errore LLM non deve mai diventare il
    # contenuto di canvas.md — un canvas che dice "[ERRORE DI CONNESSIONE]" verrebbe letto da
    # propose/validate/archive come contratto reale. L'errore è restituito esplicitamente
    # come 502 (dipendenza esterna, non input malformato), senza scrivere alcun file.
    try:
        canvas_content = await llm.agenerate(prompt_strutturato, purpose="canvas")
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Generazione del Canvas fallita: {exc}") from exc
    with _feature_lock(folder.name):
        (folder / "canvas.md").write_text(canvas_content, encoding="utf-8")
        save_dev_type(folder, dev_type)
    return {"feature_folder": folder.name, "path": "canvas.md", "content": canvas_content}


@router.post("/api/pipeline/propose/generate",
             dependencies=[Depends(require_not_cross_site_request)])
async def pipeline_propose_generate(req: ProposeGenerateRequest):
    """Genera spec.md dal Canvas e il prompt finale per Claude Code (equivalente a propose.py)."""
    folder = _safe_feature_dir(req.feature_folder)
    folder_name = folder.name
    canvas_path = folder / "canvas.md"

    if not canvas_path.exists():
        raise HTTPException(status_code=404, detail=f"Non trovo {canvas_path.name}. Devi prima generare il Canvas.")

    canvas_content = canvas_path.read_text(encoding="utf-8")
    # Validato SUBITO (whitelist di list_dev_types()), prima di spendere un retrieval/LLM:
    # diventa un componente di path (CODE_DIR / dev_type) in core.indexing.check_drift.
    dev_type = _safe_dev_type(req.dev_type or load_dev_type(folder))

    # Recupera i vincoli normativi dal Graph RAG per generare scenari BDD che coprano
    # anche i safeguard e le policy pertinenti, non solo ciò che è nel Canvas.
    #
    # Niente ramo tecnico qui: lo stack lo porta il Canvas (vedi build_spec_prompt). Il
    # dev_type serve solo a delimitare l'ambito degli scenari.
    governed_context = await embed_in_threadpool(
        _governed_context, f"{req.feature_folder}\n{canvas_content[:2000]}", current_snapshot()
    )
    prompt_strutturato = pipeline.build_spec_prompt(canvas_content, governed_context, dev_type,
                                                    req.feature_folder)

    # Generazione DIRETTA (non generate_tolerant): stessa ragione del Canvas — un errore LLM
    # non deve mai diventare il contenuto di spec.md (validate/archive lo tratterebbero come
    # spec reale). Errore restituito esplicitamente come 502, nessun file scritto.
    try:
        spec_grezza = await llm.agenerate(prompt_strutturato, purpose="propose")
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Generazione della Spec fallita: {exc}") from exc
    folder.mkdir(parents=True, exist_ok=True)

    # L'output GREZZO del modello si conserva sempre, prima di qualunque riscrittura: quando
    # lo spec finale sorprende, la prima domanda è «l'ha scritto così il modello o l'ha
    # cambiato la normalizzazione?», e senza il grezzo non ha risposta.
    with _feature_lock(folder.name):
        (folder / "spec.raw.md").write_text(spec_grezza, encoding="utf-8")

    # Normalizzazione SINTATTICA: il modello locale sbaglia sistematicamente la forma (tutti
    # gli scenari in un blocco solo, `E` al posto di AND) e nessuna riformulazione del prompt
    # lo corregge in modo stabile; la forma però è ricostruibile in modo deterministico. Il
    # contenuto non viene toccato: ciò che riguarda la sostanza resta al validate, che deve
    # poter ancora bocciare.
    try:
        spec_content = spec_format.normalize_spec(spec_grezza)
    except spec_format.SpecNormalizationError as exc:
        # Fail-closed: spec.md NON viene sovrascritto con un documento che non si riesce
        # nemmeno a interpretare. Il grezzo è già su disco e resta ispezionabile.
        raise HTTPException(
            status_code=502,
            detail=(f"La Spec generata non è normalizzabile: {exc} "
                    f"L'output grezzo del modello è in changes/{folder_name}/spec.raw.md. "
                    "Rigenera la Spec."),
        ) from exc
    with _feature_lock(folder.name):
        (folder / "spec.md").write_text(spec_content, encoding="utf-8")
        save_dev_type(folder, dev_type)

    final_prompt = build_final_prompt(folder_name, dev_type)

    return {
        "feature_folder": folder.name,
        "path": "spec.md",
        "content": spec_content,
        "final_prompt": final_prompt,
        **read_report(spec_content),
    }


@router.get("/api/pipeline/final-prompt")
async def pipeline_final_prompt(feature: str, dev_type: str = "", consumer: str = "external",
                                mode: str = "agentic", runner: str = "claude"):
    """Template unico per HTTP esterno e MCP in-app. One-shot riceve Canvas/Spec
    nel prompt perché non ha strumenti di lettura. Nessuna chiamata al modello."""
    if consumer not in FINAL_PROMPT_CONSUMERS:
        raise HTTPException(
            status_code=400,
            detail=f"Consumatore non valido: {consumer!r}. Validi: {list(FINAL_PROMPT_CONSUMERS)}",
        )
    if consumer == "agent" and mode not in AGENT_MODES:
        raise HTTPException(status_code=400, detail=f"Modalità non valida: {mode}")
    if runner not in RUNNERS:
        raise HTTPException(status_code=400, detail=f"Runner non valido: {runner}")
    folder = _safe_feature_dir(feature)
    dev = _safe_dev_type(dev_type or load_dev_type(folder))
    prompt = build_final_prompt(folder.name, dev, consumer, mode=mode, mcp=runner == "claude")
    if consumer == "agent" and mode == "oneshot":
        try:
            contract = {name: (folder / name).read_text(encoding="utf-8")
                        for name in ("canvas.md", "spec.md")}
        except FileNotFoundError:
            raise HTTPException(status_code=409, detail="Genera prima Canvas e Spec per One-shot.") from None
        if not all(text.strip() for text in contract.values()):
            raise HTTPException(status_code=409, detail="Canvas e Spec non possono essere vuoti.")
        prompt += "\n\nContratto della feature (JSON):\n" + json.dumps(contract, ensure_ascii=False)
    return {
        "feature_folder": folder.name,
        "dev_type": dev,
        "consumer": consumer,
        "mode": mode if consumer == "agent" else None,
        "final_prompt": prompt,
    }


@router.post("/api/pipeline/drift/check",
             dependencies=[Depends(require_not_cross_site_request)])
async def pipeline_drift_check(req: DriftCheckRequest):
    """Step 4 — Verifica del Drift: confronta il canvas (contratto) con il codice
    generato tramite LLM locale e restituisce il report. Equivale a 'index.py --check-drift'."""
    if not req.feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    feature_folder = _safe_slug(req.feature)
    # La chiamata a Ollama è bloccante e potenzialmente lunga: la eseguiamo in un
    # thread separato per non bloccare l'event loop del server.
    report = await run_in_threadpool(check_drift, req.feature)
    return {"feature_folder": feature_folder, "report": report}


@router.post("/api/pipeline/archive",
             dependencies=[Depends(require_not_cross_site_request)])
async def pipeline_archive(req: ArchiveRequest):
    """Step 5 — Archiviazione e Re-indicizzazione: sposta changes/<feature> in
    changes/archive/ (con canvas review) e ACCODA un full rebuild al ReindexManager
    invece di ricostruire inline — un solo scrittore per costruzione, così un archive
    non può mai correre in parallelo con un reindex da webhook. Il reload in memoria
    avviene al completamento del job (on_success → reload_index_state)."""
    if not req.feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    # Validato PRIMA di toccare filesystem/coda: un nome non valido non deve accodare
    # un full rebuild inutile né chiamare archive_feature.
    feature_folder = _safe_slug(req.feature)
    log = await run_in_threadpool(
        archive_feature, req.feature, state["qdrant"], state["embed_model"],
        None, False,  # emit=None, reindex=False: la ricostruzione passa dalla coda
    )
    job, queued = enqueue_full_rebuild()
    return {
        "feature_folder": feature_folder,
        "log": log,
        "reindex_job_id": job.id,
        "reindex_queued": queued,
    }


@router.post("/api/pipeline/drift/check/stream",
             dependencies=[Depends(require_not_cross_site_request)])
async def pipeline_drift_check_stream(req: DriftCheckRequest):
    """Come /api/pipeline/drift/check ma con progresso in streaming (NDJSON): l'interfaccia
    mostra i passi (avvio, analisi, report) man mano che arrivano, senza box bloccante."""
    if not req.feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    return StreamingResponse(run_streaming(check_drift, req.feature), media_type="application/x-ndjson")


@router.post("/api/pipeline/archive/stream",
             dependencies=[Depends(require_not_cross_site_request)])
async def pipeline_archive_stream(req: ArchiveRequest):
    """Come /api/pipeline/archive ma con progresso in streaming (NDJSON): l'utente vede
    l'archiviazione avanzare passo per passo. La ricostruzione dell'indice NON avviene
    nello stream: viene accodata al ReindexManager e lo stream chiude con
    {"type": "reindex_queued", "job_id": ...}; il reload in memoria avviene al
    completamento del job (on_success → reload_index_state)."""
    if not req.feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    # Validato PRIMA di accodare un full rebuild: un nome invalido non deve mai
    # innescare una ricostruzione completa inutile (stessa guardia di pipeline_archive).
    _safe_slug(req.feature)

    def gen():
        yield from run_streaming(
            functools.partial(archive_feature, reindex=False),
            req.feature, state["qdrant"], state["embed_model"],
        )
        job, _ = enqueue_full_rebuild()
        yield json.dumps({"type": "reindex_queued", "job_id": job.id}, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@contextmanager
def _feature_lock(feature):
    try:
        with pipeline_store.feature_lock(feature):
            yield
    except PipelineStorageError as exc:
        raise _gate_storage_error(exc) from exc


def _read_gate_contract(feature: str):
    folder = _safe_feature_dir(feature)
    def read(name):
        try:
            return (folder / name).read_bytes()
        except FileNotFoundError:
            return b""
    return gate.make_contract(folder.name, read("canvas.md"), read("spec.md"),
                              pipeline_store.decisions(folder.name), dev_type=load_dev_type(folder))


def _validation_manifest(snap):
    if snap is None:
        raise validation.ValidationUnavailable("Indice non disponibile")
    path = manifest_path(snap.version if isinstance(snap.version, str) else "legacy")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        hashes = data["doc_hashes"]
        if not isinstance(hashes, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in hashes.items()):
            raise ValueError("doc_hashes non valido")
        return hashes
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise validation.ValidationUnavailable(f"Manifest dello snapshot non disponibile: {exc}") from exc


def _validation_source_state():
    snap = current_snapshot()
    _validation_manifest(snap)  # assenza/corruzione non diventa corpus vuoto
    return gate.SourceState(index_version=snap.version, doc_hashes=_docs_hashes())


def _gate_storage_error(exc):
    issue = gate.AvailabilityIssue(code="storage_unavailable", message=str(exc),
                                   action=getattr(exc, "action", "operator_action"))
    return HTTPException(status_code=503, detail=gate.evaluate_gate(None, None, gate.SourceState(), [issue]).model_dump())


def _gate_payload(contract, record, issues=(), *, retry_reference_valid=True):
    issues = list(issues)
    if contract is None:
        return dict(feature_folder=record.feature if record else None, spec_hash=None, validation_id=record.validation_id if record else None,
                    gate=gate.evaluate_gate(None, record, gate.SourceState(), issues, retry_reference_valid=retry_reference_valid).model_dump(),
                    point_decisions=None, structural_findings=[], comparison=None, execution_enforced=True)
    try:
        sources = _validation_source_state()
    except (validation.ValidationUnavailable, OSError) as exc:
        sources = gate.SourceState()
        issues.append(gate.AvailabilityIssue(code="sources_unavailable", message=str(exc), action="operator_action"))
    structural, _, findings = validation.structural_check(contract)
    return dict(feature_folder=contract.feature, spec_hash=contract.spec.hash,
                validation_id=record.validation_id if record else None,
                gate=gate.evaluate_gate(contract, record, sources, issues, retry_reference_valid=retry_reference_valid).model_dump(),
                structural=structural, structural_findings=findings,
                point_decisions=validation.point_states(contract), execution_enforced=True,
                comparison=(dict(validation_id=record.validation_id,
                    **{name: dict(current=getattr(contract, name).text, validated=getattr(record.contract, name).text)
                       for name in ('canvas', 'spec')}) if record and record.feature == contract.feature else None))


@router.get("/api/pipeline/gate")
async def pipeline_gate_status(feature: str, validation_id: str | None = None):
    slug = _safe_slug(feature)
    def read():
        contract = _read_gate_contract(slug)
        record = (pipeline_store.read_validation(slug, validation_id) if validation_id else
                  pipeline_store.latest_validation(slug, contract.hash))
        return _gate_payload(contract, record)
    try:
        return await run_in_threadpool(read)
    except (PipelineStorageError, OSError, UnicodeError) as exc:
        raise _gate_storage_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/pipeline/open-points/decision", dependencies=[Depends(require_api_key_strict)])
async def pipeline_point_decision(req: OpenPointDecisionRequest, request: Request):
    """L'accettazione non è esposta agli strumenti dell'agente; non è
    certificata come decisione umana dalla credenziale condivisa.
    """
    feature = _safe_slug(req.feature)
    def record():
        with _feature_lock(feature):
            contract = _read_gate_contract(feature)
            states = validation.point_states(contract)
            point = next((p['point'] for p in states or [] if p['point_hash'] == req.point_hash), None)
            if point is None or contract.spec.hash != req.spec_hash:
                raise HTTPException(status_code=409, detail="Punto o Spec cambiati: ricarica e riesamina prima di decidere.")
            _, _, findings = validation.structural_check(contract)
            available = {f['finding_hash']: f for f in findings if f['associable']}
            if any(h not in available for h in req.coverage_finding_hashes):
                raise HTTPException(status_code=409, detail="Rilievo assente o non associabile: nessuna deroga a GIVEN/WHEN/THEN.")
            selected = [{k: available[h][k] for k in ('line', 'scenario', 'rule', 'message')}
                        for h in req.coverage_finding_hashes]
            active, unscoped, scope = pipeline_activity.snapshot(feature)
            observed = {"client_host": request.client.host if request.client else "unknown",
                        "user_agent": request.headers.get("user-agent", ""),
                        "origin": request.headers.get("origin", ""),
                        "sec_fetch_site": request.headers.get("sec-fetch-site", ""),
                        "activity_scope": scope, "unscoped_active_attempt_ids": json.dumps(unscoped)}
            decision = pipeline_store.record_decision(feature=feature, point=point, spec_hash=contract.spec.hash,
                status=req.status, motivation=req.motivation, declared_by=req.declared_by,
                declared_origin=req.declared_origin, observed_metadata=observed, active_attempt_ids=active,
                coverage_findings=selected)
            pipeline_store.append_event('open_point_decision_recorded', feature=feature,
                attempt_id='attempt-' + uuid4().hex, decision_id=decision.decision_id,
                point_hash=decision.point_hash, status=decision.status, declared_by=decision.declared_by,
                declared_origin=decision.declared_origin, origin_verified=decision.origin_verified,
                observed_metadata=decision.observed_metadata, active_attempt_ids=decision.active_attempt_ids,
                coverage_findings=[f.model_dump() for f in decision.coverage_findings])
            return {"decision": decision.model_dump(), "execution_enforced": True}
    try:
        return await run_in_threadpool(record)
    except WriterLockBusyError as exc:
        raise _gate_storage_error(PipelineStorageBusyError("Decisione concorrente: riprova")) from exc
    except (PipelineStorageError, OSError, UnicodeError) as exc:
        raise _gate_storage_error(exc) from exc


async def _validate_feature(feature: str) -> dict:
    """Valida uno snapshot; verifica finale e persistenza coordinate con l’ammissione."""
    def start_validation():
        with _feature_lock(feature):
            initial = gate.new_validation(_read_gate_contract(feature))
            pipeline_store.write_validation(initial)
            return initial
    started = await run_in_threadpool(start_validation)
    contract = started.contract
    structural, structural_check, structural_findings = validation.structural_check(contract)
    snap = current_snapshot()
    scope = pipeline.check_scenario_scope(contract.spec.text, contract.canvas.text,
        pipeline.glossary_entities(snap.graph if snap else None), feature_name=feature)
    sources = gate.ValidationSources()
    evidence = gate.ValidatorEvidence()
    semantic_check = gate.Check(status="unavailable")
    semantic_findings, semantic_report, error = [], None, None
    try:
        doc_hashes = await run_in_threadpool(_validation_manifest, snap)
        context, sources = await embed_in_threadpool(validation.validation_context,
            f"{feature}\n{contract.canvas.text[:2000]}", snap, doc_hashes,
            qdrant=state.get("qdrant"), embed_model=state.get("embed_model"), max_chunks=GOVERNED_MAX_CHUNKS)
        prompt = pipeline.build_validate_prompt(contract.canvas.text, contract.spec.text, context,
                                                 validation.point_states(contract))
        provider, model = llm.resolve("validate")
        evidence = gate.ValidatorEvidence(model=f"{provider}:{model}", prompt_hash=gate.content_hash(prompt))
        raw = await llm.agenerate(prompt, purpose="validate")
        if not isinstance(raw, str):
            raise validation.ValidationUnavailable("Risposta del validatore non testuale")
        evidence.raw_response = raw
        semantic_report, semantic_check, semantic_findings = validation.read_semantic(raw, contract, sources)
    except (validation.ValidationUnavailable, llm.LLMError, ValueError, OSError) as exc:
        error = str(exc)
        semantic_check = gate.Check(status="unavailable", details=[error])
    def finish():
        with _feature_lock(feature):
            final_error, final_semantic_check = error, semantic_check
            issues = []
            try:
                current = _read_gate_contract(feature)
            except (PipelineStorageError, OSError, UnicodeError) as exc:
                current, final_error = None, str(exc)
                issues.append(gate.AvailabilityIssue(code='storage_unavailable', message=final_error, action='operator_action'))
                final_semantic_check = gate.Check(status='unavailable', details=[final_error])
            result = gate.finish_validation(started, current or started.contract,
                gate.ValidationChecks(structural=structural_check, semantic=final_semantic_check), sources=sources, validator=evidence)
            result.structural_findings = structural_findings
            result.semantic_findings = semantic_findings
            result.suggestions = semantic_report.suggestions if semantic_report else None
            payload = _gate_payload(current, result, issues)
            result.warnings = [gate.Notice.model_validate(w) for w in payload['gate']['warnings']]
            pipeline_store.write_validation(result)
            pipeline_store.append_event('validation_finished', feature=feature, attempt_id=result.attempt_id,
                validation_id=result.validation_id, status=result.status, passed=result.passed,
                open_points_status=result.open_points_status, gate=payload['gate'])
            return {**payload, "status": result.status, "passed": result.passed,
                    "validation_available": result.status != "unavailable", "validation_error": final_error,
                    "llm_error": final_error, "report": semantic_report.summary if semantic_report else None,
                    "checks": result.checks.model_dump(), "structural": structural, "scenario_scope": scope,
                    "structural_findings": structural_findings, "semantic_findings": semantic_findings,
                    "suggestions": result.suggestions}
    return await run_in_threadpool(finish)


@router.post("/api/pipeline/validate", dependencies=[Depends(require_not_cross_site_request)])
async def pipeline_validate(req: ValidateRequest):
    feature = _safe_slug(req.feature)
    try:
        result = await _validate_feature(feature)
    except (PipelineStorageError, OSError, UnicodeError) as exc:
        raise _gate_storage_error(exc) from exc
    return JSONResponse(result, status_code=503) if result['status'] == 'unavailable' else result


@router.get("/api/index/status")
async def api_index_status():
    """Segnala se l'indice Graph RAG è aggiornato rispetto ai documenti in docs/ (drift di
    indicizzazione): confronta gli hash correnti con lo snapshot salvato dall'ultima build."""
    return await run_in_threadpool(index_status)


@router.get("/api/index/integrity")
async def api_index_integrity():
    """Check economico di integrità dell'indice (zero embedding): manifest, hash dei
    sorgenti, integrità degli artefatti in database/ e allineamento del conteggio Qdrant
    col sidecar chunk. Riusa il client Qdrant del server se disponibile."""
    return await run_in_threadpool(
        check_index_integrity, state.get("qdrant"), lambda *_a, **_k: None
    )


@router.post("/api/pipeline/canvas/dry-run")
async def pipeline_canvas_dry_run(req: CanvasGenerateRequest):
    """Dry-run del Canvas: mostra le sorgenti che verrebbero recuperate (con punteggi
    dense/sparse/ColBERT/autorità) e i documenti normativi che verrebbero iniettati,
    SENZA generare nulla — così si ispeziona il contesto prima di spendere token.

    Rispecchia i DUE rami di _governed_context (dominio + tecnico per dev_type): mostrarne
    uno solo farebbe promettere al dry-run un contesto diverso da quello che il canvas
    riceve davvero. Ogni sorgente porta il ramo da cui viene.

    read-only per davvero (SECURITY_SURFACE.md, riga #22 della matrice §2): NON crea la cartella della
    feature (create=False, il default) — se non esiste ancora semplicemente non c'è
    explore.md/meta.json da leggere. Creare una cartella qui sarebbe una scrittura da
    un endpoint escluso dalla guardia anti-cross-site perché dichiarato read-only."""
    folder = _safe_feature_dir(req.feature_name)
    explore_path = folder / "explore.md"
    interview = explore_path.read_text(encoding="utf-8") if explore_path.exists() else ""
    query = f"{req.feature_name}\n{interview[:2000]}"
    dev_type = req.dev_type or load_dev_type(folder)

    snap = current_snapshot()

    def work() -> dict:
        if snap is None or snap.graph is None or state.get("qdrant") is None or state.get("embed_model") is None:
            return {"sources": [], "governed_docs": [], "note": "Indice non ancora pronto."}
        graph = snap.graph
        search = functools.partial(retrieval.hybrid_search, qdrant=state["qdrant"],
                                   embed_model=state["embed_model"], colbert_store=snap.colbert_store)
        branches: list[tuple[str, str, Any]] = [("normativo", query, None)]
        tech_query = pipeline.build_tech_query(dev_type)
        if tech_query:
            branches.append(("tecnico", tech_query,
                             retrieval.scope_tag_filter(TECH_SCOPE_TAG_KEY,
                                                        pipeline.dev_type_tag_variants(dev_type))))

        sources, doc_ids = [], []
        for label, q, query_filter in branches:
            try:
                results = search(q, 6, query_filter=query_filter)
            except Exception as exc:
                return {"sources": [], "governed_docs": [], "note": f"Retrieval fallito: {exc}"}
            sources += [
                {"doc_id": r["doc_id"], "section": r.get("section", ""), "branch": label,
                 "dense_score": r["dense_score"], "sparse_score": r["sparse_score"],
                 "colbert_score": r["colbert_score"], "authority": r["authority"]}
                for r in results
            ]
            for d in retrieval.select_governed_docs(q, graph=graph, results=results):
                if d not in doc_ids:
                    doc_ids.append(d)

        governed = []
        for d in doc_ids:
            p = PROJECT_ROOT / "docs" / d
            governed.append({
                "doc_id": d,
                "authority": round(retrieval._authority_weight(graph.nodes[d]) if d in graph else 0.0, 3),
                "classification": graph.nodes[d].get("classification", "") if d in graph else "",
                "chars": len(p.read_text(encoding="utf-8")) if p.exists() else 0,
            })
        return {"sources": sources, "governed_docs": governed}

    data = await embed_in_threadpool(work)
    return {"feature_folder": folder.name, "query_preview": query[:300], **data}


@router.get("/api/pipeline/agent-context")
async def pipeline_agent_context(feature: str, dev_type: str = ""):
    """Blocco strutturato [AGENT CONTEXT] con confidence score (Articolo 1), costruito in
    modo deterministico dal retrieval governato e dallo stato di canvas/spec."""
    if not feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    feature_folder = _safe_slug(feature)
    ctx = await embed_in_threadpool(_agent_context, feature, dev_type, current_snapshot())
    return {"feature_folder": feature_folder, **ctx}


@router.get("/api/pipeline/export")
async def pipeline_export(feature: str, dev_type: str = ""):
    """Export JSON versionabile del design contract (explore/canvas/spec + prompt finale +
    [AGENT CONTEXT]), da archiviare come artefatto o dare in pasto a una pipeline."""
    folder = _safe_feature_dir(feature)
    folder_name = folder.name

    def rd(name: str) -> str:
        p = folder / name
        return p.read_text(encoding="utf-8") if p.exists() else ""

    dev = dev_type or load_dev_type(folder)
    ctx = await embed_in_threadpool(_agent_context, feature, dev, current_snapshot())
    spec = rd("spec.md")
    return {
        "feature": feature,
        "feature_folder": folder_name,
        "dev_type": dev,
        "explore": rd("explore.md"),
        "canvas": rd("canvas.md"),
        "spec": spec,
        **read_report(spec),
        "final_prompt": build_final_prompt(folder_name, dev),
        "agent_context": ctx,
    }


@router.get("/api/pipeline/status")
async def pipeline_status(feature: str):
    """Restituisce quali file (explore/canvas/spec) esistono già per la feature, per il pannello di controllo."""
    folder = _safe_feature_dir(feature)
    files = {
        name.split(".")[0]: (folder / name).exists()
        for name in PIPELINE_FILES
    }
    return {
        "feature_folder": folder.name,
        "exists": folder.exists(),
        "files": files,
        "dev_type": load_dev_type(folder),
    }


@router.get("/api/pipeline/file")
async def pipeline_get_file(feature: str, name: str):
    """Restituisce il contenuto di un file md della pipeline, per la visualizzazione di controllo."""
    if name not in PIPELINE_FILES:
        raise HTTPException(status_code=400, detail=f"File non consentito: {name}")
    folder = _safe_feature_dir(feature)
    file_path = folder / name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"{name} non trovato per la feature '{folder.name}'.")
    content = file_path.read_text(encoding="utf-8")
    return {"feature_folder": folder.name, "path": name, "content": content,
            **(read_report(content) if name == "spec.md" else {})}


@router.post("/api/pipeline/file/save",
             dependencies=[Depends(require_not_cross_site_request)])
async def pipeline_save_file(req: PipelineFileSaveRequest):
    """Salva modifiche manuali a un file md prima dell'approvazione (revisione umana)."""
    if req.name not in PIPELINE_FILES:
        raise HTTPException(status_code=400, detail=f"File non consentito: {req.name}")
    folder = _safe_feature_dir(req.feature, create=True)
    try:
        with _feature_lock(folder.name):
            (folder / req.name).write_text(req.content, encoding="utf-8")
    except PipelineStorageError as exc:
        raise _gate_storage_error(exc) from exc
    return {"feature_folder": folder.name, "path": req.name, "content": req.content,
            **(read_report(req.content) if req.name == "spec.md" else {})}

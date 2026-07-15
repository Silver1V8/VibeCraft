"""Route della pipeline Explore -> Canvas -> Propose -> Validate -> Drift -> Archivio, più
esecuzione via Claude Agent SDK, dry-run, [AGENT CONTEXT], export e gestione file. Gli
handler orchestrano I/O e concorrenza (async/threadpool/streaming) e iniettano le risorse
di runtime dallo stato (api.deps) nelle funzioni pure di core.pipeline / core.retrieval."""
import functools
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from agent_bridge import AGENT_MODES, run_agent_streaming
from api.deps import (
    IndexSnapshot,
    current_snapshot,
    require_api_key,
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
)
from api.routes_reindex import enqueue_full_rebuild
from core import canvas_review, pipeline, retrieval
from core.config import (
    CHANGES_DIR,
    GOVERNED_MAX_CHUNKS,
    PROJECT_ROOT,
    TECH_MAX_CHUNKS,
    TECH_SCOPE_TAG_KEY,
)
from core.indexing import archive_feature, check_drift, check_index_integrity, index_status
from core.pipeline import (
    build_final_prompt,
    feature_dir,
    generate_tolerant,
    list_dev_types,
    load_dev_type,
    save_dev_type,
    slugify_feature,
)

router = APIRouter(dependencies=[Depends(require_api_key)])

PIPELINE_FILES = ("explore.md", "canvas.md", "spec.md")


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


@router.post("/api/pipeline/agent/run")
async def agent_run(req: AgentRunRequest):
    """
    Esegue il prompt finale della pipeline direttamente tramite il Claude Agent SDK,
    trasformando la dashboard da finestra sul progetto a strumento operativo.
    L'SDK gira su un thread dedicato (vedi agent_bridge.py); gli eventi arrivano
    al client come stream NDJSON.
    """
    if req.mode not in AGENT_MODES:
        raise HTTPException(status_code=400, detail=f"Modalità non valida: {req.mode}")
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt vuoto.")

    return StreamingResponse(
        run_agent_streaming(req.prompt, req.mode, req.model),
        media_type="application/x-ndjson",
    )


@router.get("/api/pipeline/dev-types")
async def pipeline_dev_types():
    """Elenca le tipologie di sviluppo disponibili (sottocartelle di 'code/') per la tendina di selezione."""
    return {"dev_types": list_dev_types()}


@router.post("/api/pipeline/explore/turn")
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


@router.post("/api/pipeline/explore/save")
async def pipeline_explore_save(req: ExploreSaveRequest):
    """Salva il log dell'intervista in changes/<feature>/explore.md."""
    folder = feature_dir(req.feature_name)
    save_dev_type(folder, req.dev_type)
    dev_type_line = f"**Tipo di sviluppo:** {req.dev_type}\n\n" if req.dev_type else ""
    file_path = folder / "explore.md"
    content = f"# Intervista Explore: {req.feature_name}\n\n{dev_type_line}{req.interview_log}"
    file_path.write_text(content, encoding="utf-8")
    return {"feature_folder": folder.name, "path": "explore.md", "content": content}


@router.post("/api/pipeline/canvas/generate")
async def pipeline_canvas_generate(req: CanvasGenerateRequest):
    """Genera il REASONS Canvas a partire dall'intervista Explore (equivalente a canvas.py)."""
    folder = feature_dir(req.feature_name)
    explore_path = folder / "explore.md"

    if explore_path.exists():
        contesto_intervista = explore_path.read_text(encoding="utf-8")
    else:
        contesto_intervista = "Nessun log di intervista dettagliato disponibile."

    # Àncora il Canvas al knowledge base governato: recupera dal Graph RAG i documenti
    # normativi pertinenti (safeguard, glossario, matrice permessi), pesati per autorità,
    # invece di affidarsi a un contesto statico scritto a mano. Il dev_type è risolto qui
    # perché guida anche il ramo tecnico del retrieval, non solo la cartella di output.
    dev_type = req.dev_type or load_dev_type(folder)
    snap = current_snapshot()
    query = f"{req.feature_name}\n{contesto_intervista[:2000]}"
    governed_context = await run_in_threadpool(_governed_context, query, snap)
    contesto_progetto_base = governed_context or "Nessun documento normativo pertinente recuperato dal Graph RAG."
    # Contesto tecnico: blocco separato nel prompt (vedi build_canvas_prompt), non fuso col
    # normativo — hanno ruoli diversi e istruzioni diverse.
    contesto_tecnico = await run_in_threadpool(_tech_context, dev_type, snap)

    # Persiste in meta.json QUALI documenti hanno ancorato questo canvas (normativi + tecnici):
    # all'archive diventano gli `expected` di un caso candidato per il golden-set di eval.
    pipeline.save_governed_sources(
        folder, pipeline.governed_docs_from_context(governed_context + "\n\n" + contesto_tecnico))

    # Canvas che apprende (parte 2): le divergenze emerse nelle review delle change
    # archiviate più simili diventano "lezioni" nel prompt ('' se non esistono review).
    lessons = await run_in_threadpool(_canvas_lessons, query, snap)

    prompt_strutturato = pipeline.build_canvas_prompt(
        req.feature_name, contesto_intervista, contesto_progetto_base, dev_type, lessons,
        contesto_tecnico
    )

    canvas_content = await generate_tolerant(prompt_strutturato, purpose="canvas")
    (folder / "canvas.md").write_text(canvas_content, encoding="utf-8")
    save_dev_type(folder, dev_type)
    return {"feature_folder": folder.name, "path": "canvas.md", "content": canvas_content}


@router.post("/api/pipeline/propose/generate")
async def pipeline_propose_generate(req: ProposeGenerateRequest):
    """Genera spec.md dal Canvas e il prompt finale per Claude Code (equivalente a propose.py)."""
    folder_name = slugify_feature(req.feature_folder)
    folder = CHANGES_DIR / folder_name
    canvas_path = folder / "canvas.md"

    if not canvas_path.exists():
        raise HTTPException(status_code=404, detail=f"Non trovo {canvas_path.name}. Devi prima generare il Canvas.")

    canvas_content = canvas_path.read_text(encoding="utf-8")
    dev_type = req.dev_type or load_dev_type(folder)

    # Recupera i vincoli normativi dal Graph RAG per generare scenari BDD che coprano
    # anche i safeguard e le policy pertinenti, non solo ciò che è nel Canvas.
    #
    # Niente ramo tecnico qui: lo stack lo porta il Canvas (vedi build_spec_prompt). Il
    # dev_type serve solo a delimitare l'ambito degli scenari.
    governed_context = await run_in_threadpool(
        _governed_context, f"{req.feature_folder}\n{canvas_content[:2000]}", current_snapshot()
    )
    prompt_strutturato = pipeline.build_spec_prompt(canvas_content, governed_context, dev_type)

    spec_content = await generate_tolerant(prompt_strutturato, purpose="propose")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "spec.md").write_text(spec_content, encoding="utf-8")
    save_dev_type(folder, dev_type)

    final_prompt = build_final_prompt(folder_name, dev_type)

    return {
        "feature_folder": folder.name,
        "path": "spec.md",
        "content": spec_content,
        "final_prompt": final_prompt,
    }


@router.post("/api/pipeline/drift/check")
async def pipeline_drift_check(req: DriftCheckRequest):
    """Step 4 — Verifica del Drift: confronta il canvas (contratto) con il codice
    generato tramite LLM locale e restituisce il report. Equivale a 'index.py --check-drift'."""
    if not req.feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    # La chiamata a Ollama è bloccante e potenzialmente lunga: la eseguiamo in un
    # thread separato per non bloccare l'event loop del server.
    report = await run_in_threadpool(check_drift, req.feature)
    return {"feature_folder": slugify_feature(req.feature), "report": report}


@router.post("/api/pipeline/archive")
async def pipeline_archive(req: ArchiveRequest):
    """Step 5 — Archiviazione e Re-indicizzazione: sposta changes/<feature> in
    changes/archive/ (con canvas review) e ACCODA un full rebuild al ReindexManager
    invece di ricostruire inline — un solo scrittore per costruzione, così un archive
    non può mai correre in parallelo con un reindex da webhook. Il reload in memoria
    avviene al completamento del job (on_success → reload_index_state)."""
    if not req.feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    log = await run_in_threadpool(
        archive_feature, req.feature, state["qdrant"], state["embed_model"],
        None, False,  # emit=None, reindex=False: la ricostruzione passa dalla coda
    )
    job, queued = enqueue_full_rebuild()
    return {
        "feature_folder": slugify_feature(req.feature),
        "log": log,
        "reindex_job_id": job.id,
        "reindex_queued": queued,
    }


@router.post("/api/pipeline/drift/check/stream")
async def pipeline_drift_check_stream(req: DriftCheckRequest):
    """Come /api/pipeline/drift/check ma con progresso in streaming (NDJSON): l'interfaccia
    mostra i passi (avvio, analisi, report) man mano che arrivano, senza box bloccante."""
    if not req.feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    return StreamingResponse(run_streaming(check_drift, req.feature), media_type="application/x-ndjson")


@router.post("/api/pipeline/archive/stream")
async def pipeline_archive_stream(req: ArchiveRequest):
    """Come /api/pipeline/archive ma con progresso in streaming (NDJSON): l'utente vede
    l'archiviazione avanzare passo per passo. La ricostruzione dell'indice NON avviene
    nello stream: viene accodata al ReindexManager e lo stream chiude con
    {"type": "reindex_queued", "job_id": ...}; il reload in memoria avviene al
    completamento del job (on_success → reload_index_state)."""
    if not req.feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")

    def gen():
        yield from run_streaming(
            functools.partial(archive_feature, reindex=False),
            req.feature, state["qdrant"], state["embed_model"],
        )
        job, _ = enqueue_full_rebuild()
        yield json.dumps({"type": "reindex_queued", "job_id": job.id}, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


async def _validate_feature(feature: str) -> dict:
    """Validazione pre-apply: controlli strutturali deterministici su canvas/spec +
    analisi LLM di coerenza e conflitti contro il contesto normativo del Graph RAG.
    Il retrieval (CPU) gira in threadpool, la chiamata Ollama (I/O) è async. La logica
    (controlli strutturali e costruzione dei prompt) è in core/pipeline.py."""
    folder_name = slugify_feature(feature)
    folder = CHANGES_DIR / folder_name
    canvas_path = folder / "canvas.md"
    spec_path = folder / "spec.md"

    canvas_text = canvas_path.read_text(encoding="utf-8") if canvas_path.exists() else ""
    spec_text = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""

    # 1. Controlli strutturali deterministici (nessun LLM).
    structural = pipeline.validate_structural(canvas_text, spec_text)

    if not canvas_text:
        return {"structural": structural, "report": "❌ canvas.md assente: genera prima il Canvas."}

    # 2. Analisi semantica: coerenza e conflitti rispetto al contesto normativo governato.
    #    Il retrieval è CPU-bound (embedding della query) → threadpool; l'LLM è I/O → async.
    governed = await run_in_threadpool(_governed_context, f"{feature}\n{canvas_text[:2000]}", current_snapshot())
    prompt = pipeline.build_validate_prompt(canvas_text, spec_text, governed)
    report = await generate_tolerant(prompt, purpose="validate")
    return {"structural": structural, "report": report}


@router.post("/api/pipeline/validate")
async def pipeline_validate(req: ValidateRequest):
    """Step di validazione pre-apply: verifica strutturale (7 sezioni del Canvas, BDD nella
    spec) e coerenza semantica contro i vincoli normativi del Graph RAG, prima di lanciare Claude."""
    if not req.feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    result = await _validate_feature(req.feature)
    return {"feature_folder": slugify_feature(req.feature), **result}


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
    riceve davvero. Ogni sorgente porta il ramo da cui viene."""
    folder = feature_dir(req.feature_name)
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

    data = await run_in_threadpool(work)
    return {"feature_folder": slugify_feature(req.feature_name), "query_preview": query[:300], **data}


@router.get("/api/pipeline/agent-context")
async def pipeline_agent_context(feature: str, dev_type: str = ""):
    """Blocco strutturato [AGENT CONTEXT] con confidence score (Articolo 1), costruito in
    modo deterministico dal retrieval governato e dallo stato di canvas/spec."""
    if not feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    ctx = await run_in_threadpool(_agent_context, feature, dev_type, current_snapshot())
    return {"feature_folder": slugify_feature(feature), **ctx}


@router.get("/api/pipeline/export")
async def pipeline_export(feature: str, dev_type: str = ""):
    """Export JSON versionabile del design contract (explore/canvas/spec + prompt finale +
    [AGENT CONTEXT]), da archiviare come artefatto o dare in pasto a una pipeline."""
    folder_name = slugify_feature(feature)
    folder = CHANGES_DIR / folder_name

    def rd(name: str) -> str:
        p = folder / name
        return p.read_text(encoding="utf-8") if p.exists() else ""

    dev = dev_type or load_dev_type(folder)
    ctx = await run_in_threadpool(_agent_context, feature, dev, current_snapshot())
    return {
        "feature": feature,
        "feature_folder": folder_name,
        "dev_type": dev,
        "explore": rd("explore.md"),
        "canvas": rd("canvas.md"),
        "spec": rd("spec.md"),
        "final_prompt": build_final_prompt(folder_name, dev),
        "agent_context": ctx,
    }


@router.get("/api/pipeline/status")
async def pipeline_status(feature: str):
    """Restituisce quali file (explore/canvas/spec) esistono già per la feature, per il pannello di controllo."""
    folder_name = slugify_feature(feature)
    folder = CHANGES_DIR / folder_name
    files = {
        name.split(".")[0]: (folder / name).exists()
        for name in PIPELINE_FILES
    }
    return {
        "feature_folder": folder_name,
        "exists": folder.exists(),
        "files": files,
        "dev_type": load_dev_type(folder),
    }


@router.get("/api/pipeline/file")
async def pipeline_get_file(feature: str, name: str):
    """Restituisce il contenuto di un file md della pipeline, per la visualizzazione di controllo."""
    if name not in PIPELINE_FILES:
        raise HTTPException(status_code=400, detail=f"File non consentito: {name}")
    folder_name = slugify_feature(feature)
    file_path = CHANGES_DIR / folder_name / name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"{name} non trovato per la feature '{folder_name}'.")
    return {"feature_folder": folder_name, "path": name, "content": file_path.read_text(encoding="utf-8")}


@router.post("/api/pipeline/file/save")
async def pipeline_save_file(req: PipelineFileSaveRequest):
    """Salva modifiche manuali a un file md prima dell'approvazione (revisione umana)."""
    if req.name not in PIPELINE_FILES:
        raise HTTPException(status_code=400, detail=f"File non consentito: {req.name}")
    folder = feature_dir(req.feature)
    (folder / req.name).write_text(req.content, encoding="utf-8")
    return {"feature_folder": folder.name, "path": req.name, "content": req.content}

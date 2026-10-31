"""Route di analisi del grafo: grafo completo, Impact Ripple, Semantic Map e query
deterministica. Handler sottili: leggono lo stato, validano e delegano a core.graph_ops."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from api.deps import (get_project, require_snapshot, ensure_shared_resources, require_api_key,
                      require_cpu_get_rate_limit, run_in_threadpool_until_complete, state, logger)
from core import graph_ops
from core.config import ROLE

if ROLE != "reader":
    from core.canvas_review import canvas_quality_stats

router = APIRouter(dependencies=[Depends(require_api_key)])
reader_router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/api/canvas-quality")
async def canvas_quality(request: Request, last_n: int = Query(default=10, ge=1, le=50)):
    """Dati del pannello 'Canvas quality' (governance): trend del giudizio di fedeltà
    delle ultime N change archiviate e le divergenze canvas<->codice più frequenti,
    letti dalle canvas_review.md prodotte all'archive. Stessa auth X-API-Key delle
    altre route (dependency del router)."""
    return await run_in_threadpool_until_complete(
        canvas_quality_stats, get_project(request).changes_dir / "archive", last_n,
    )


@reader_router.get("/api/graph/all")
@router.get("/api/graph/all")
async def get_full_graph(request: Request):
    """Restituisce l'intero grafo statico (tutti i nodi e gli archi) in formato JSON."""
    project = get_project(request)
    snap = await run_in_threadpool(require_snapshot, project)
    if snap is None or snap.graph is None:
        raise HTTPException(status_code=503, detail="Grafo non ancora inizializzato.")
    result = await run_in_threadpool_until_complete(
        graph_ops.full_graph, snap.graph, snap.rule_descriptions,
    )
    return {**result, "project_id": project.id, "index_version": snap.version}


@reader_router.get("/api/graph/impact")
@router.get("/api/graph/impact")
async def graph_impact(
    request: Request,
    node: str = Query(min_length=1),
    depth: int = Query(default=3, ge=1, le=6),
):
    """Impact Ripple: espansione BFS a cerchi concentrici da un nodo. Ogni 'ring' è
    un livello di distanza nel grafo (impatto potenziale, non un effetto accertato).
    Il payload degli archi aggiunge natura, peso, affidabilità e provenienza quando
    il grafo li ha già; non li deduce.

    Input validato: `node` non vuoto, `depth` in [1, 6] (evita BFS incontrollate)."""
    project = get_project(request)
    snap = await run_in_threadpool(require_snapshot, project)
    if snap is None or snap.graph is None:
        raise HTTPException(status_code=503, detail="Grafo non ancora inizializzato.")
    if node not in snap.graph:
        raise HTTPException(status_code=404, detail=f"Nodo non presente nel grafo: {node}")
    return {**graph_ops.impact(snap.graph, node, depth),
            "project_id": project.id, "index_version": snap.version}


@reader_router.get("/api/graph/semantic-map", dependencies=[Depends(require_cpu_get_rate_limit)])
@router.get("/api/graph/semantic-map", dependencies=[Depends(require_cpu_get_rate_limit)])
async def graph_semantic_map(request: Request):
    """Semantic Map: proietta i CHUNK (sezioni) in 2D per prossimità semantica (PCA via
    SVD sui vettori densi bge-m3 in Qdrant). Le community e i nodi 'ponte' sono calcolati
    a livello di documento padre (co-menzione di entità) e ereditati dai chunk; i duplicati
    sono sezioni molto simili appartenenti a documenti diversi. Solo numpy/networkx."""
    project = get_project(request)
    snap = await run_in_threadpool(require_snapshot, project)
    await run_in_threadpool(ensure_shared_resources, embedding=False)
    qdrant: QdrantClient = state["qdrant"]
    if snap is None or snap.graph is None or qdrant is None:
        raise HTTPException(status_code=503, detail="Grafo/Qdrant non inizializzati.")
    collection_name = snap.collection_name or project.collection_name
    missing_vectors = HTTPException(409, detail={"code": "project_vectors_missing",
        "message": "I vettori dell'indice non sono allineati. Ricostruisci l'indice del progetto."})
    try:
        result = await run_in_threadpool_until_complete(
            graph_ops.semantic_map, snap.graph, qdrant,
            collection_name=collection_name,
        )
    except (ResponseHandlingException, UnexpectedResponse) as exc:
        logger.warning("Semantic map Qdrant unavailable for project %s", project.id, exc_info=True)
        if isinstance(exc, UnexpectedResponse) and exc.status_code == 404:
            raise missing_vectors from exc
        raise HTTPException(503, detail={"code": "qdrant_unavailable",
            "message": "Qdrant non è raggiungibile o non è disponibile. Avvia il servizio e premi Ricarica."}) from exc
    if not result.get("truncated") and len(snap.chunks) >= 2 and len(result["points"]) != len(snap.chunks):
        raise missing_vectors
    return {**result, "project_id": project.id, "index_version": snap.version}


@reader_router.get("/api/graph/query")
@router.get("/api/graph/query")
async def graph_query(
    request: Request,
    q: str = Query(min_length=1, max_length=2000),
    target: str | None = Query(default=None, max_length=1000),
    limit: int | None = Query(default=None, ge=1, le=1000),
):
    """Query DETERMINISTICA sul grafo (nessun LLM): risponde a domande strutturali —
    'quali documenti/entità/codice esistono?', 'relazioni di X', 'cosa impatta X' — leggendo
    direttamente nodi e archi. Incarna il principio 'determinismo prima dell'LLM' (Articolo 1).

    `target` opzionale: nodo bersaglio esplicito (es. doc_id da un click sulla Semantic Map),
    così l'intent resta dedotto da `q` ma il nodo non dipende dal match testuale."""
    project = get_project(request)
    snap = await run_in_threadpool(require_snapshot, project)
    if snap is None or snap.graph is None:
        raise HTTPException(status_code=503, detail="Grafo non ancora inizializzato.")
    result = graph_ops.graph_query(q, snap.graph, target=target)
    result.update(project_id=project.id, index_version=snap.version)
    if limit is None:
        return result
    # Budget condiviso fra gli elenchi: ordine e count originale restano intatti.
    remaining = limit
    total = 0
    for key in ("answer", "out", "in", "rings"):
        if key not in result:
            continue
        lists = result[key] if key == "rings" else [result[key]]
        bounded = []
        for items in lists:
            total += len(items)
            bounded.append(items[:remaining])
            remaining -= len(bounded[-1])
        result[key] = bounded if key == "rings" else bounded[0]
    return {**result, "index_version": snap.version, "limit": limit,
            "returned_count": limit - remaining, "truncated": total > limit,
            "scope": "Due hop per impatto; solo nodi e archi dello snapshot indicizzato."}

"""Route di analisi del grafo: grafo completo, Impact Ripple, Semantic Map e query
deterministica. Handler sottili: leggono lo stato, validano e delegano a core.graph_ops."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from qdrant_client import QdrantClient

from api.deps import current_snapshot, maybe_reload_graph, require_api_key, state
from core import graph_ops
from core.canvas_review import canvas_quality_stats
from core.config import CHANGES_DIR

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/api/canvas-quality")
async def canvas_quality(last_n: int = Query(default=10, ge=1, le=50)):
    """Dati del pannello 'Canvas quality' (governance): trend del giudizio di fedeltà
    delle ultime N change archiviate e le divergenze canvas<->codice più frequenti,
    letti dalle canvas_review.md prodotte all'archive. Stessa auth X-API-Key delle
    altre route (dependency del router)."""
    return await run_in_threadpool(canvas_quality_stats, CHANGES_DIR / "archive", last_n)


@router.get("/api/graph/all")
async def get_full_graph():
    """Restituisce l'intero grafo statico (tutti i nodi e gli archi) in formato JSON."""
    maybe_reload_graph()
    snap = current_snapshot()
    if snap is None or snap.graph is None:
        raise HTTPException(status_code=503, detail="Grafo non ancora inizializzato.")
    return await run_in_threadpool(graph_ops.full_graph, snap.graph, snap.rule_descriptions)


@router.get("/api/graph/impact")
async def graph_impact(
    node: str = Query(min_length=1),
    depth: int = Query(default=3, ge=1, le=6),
):
    """Impact Ripple: espansione BFS a cerchi concentrici da un nodo. Ogni 'ring' è
    un livello di distanza (1 hop, 2 hop, ...). Risponde 'cosa viene impattato se
    modifico questo nodo?' in modo deterministico (nessun LLM).

    Input validato: `node` non vuoto, `depth` in [1, 6] (evita BFS incontrollate)."""
    maybe_reload_graph()
    snap = current_snapshot()
    if snap is None or snap.graph is None:
        raise HTTPException(status_code=503, detail="Grafo non ancora inizializzato.")
    if node not in snap.graph:
        raise HTTPException(status_code=404, detail=f"Nodo non presente nel grafo: {node}")
    return graph_ops.impact(snap.graph, node, depth)


@router.get("/api/graph/semantic-map")
async def graph_semantic_map():
    """Semantic Map: proietta i CHUNK (sezioni) in 2D per prossimità semantica (PCA via
    SVD sui vettori densi bge-m3 in Qdrant). Le community e i nodi 'ponte' sono calcolati
    a livello di documento padre (co-menzione di entità) e ereditati dai chunk; i duplicati
    sono sezioni molto simili appartenenti a documenti diversi. Solo numpy/networkx."""
    maybe_reload_graph()
    snap = current_snapshot()
    qdrant: QdrantClient = state["qdrant"]
    if snap is None or snap.graph is None or qdrant is None:
        raise HTTPException(status_code=503, detail="Grafo/Qdrant non inizializzati.")
    return await run_in_threadpool(graph_ops.semantic_map, snap.graph, qdrant)


@router.get("/api/graph/query")
async def graph_query(
    q: str = Query(min_length=1, max_length=2000),
    target: str | None = Query(default=None, max_length=1000),
):
    """Query DETERMINISTICA sul grafo (nessun LLM): risponde a domande strutturali —
    'quali documenti/entità/codice esistono?', 'relazioni di X', 'cosa impatta X' — leggendo
    direttamente nodi e archi. Incarna il principio 'determinismo prima dell'LLM' (Articolo 1).

    `target` opzionale: nodo bersaglio esplicito (es. doc_id da un click sulla Semantic Map),
    così l'intent resta dedotto da `q` ma il nodo non dipende dal match testuale."""
    if current_snapshot() is None or current_snapshot().graph is None:
        raise HTTPException(status_code=503, detail="Grafo non ancora inizializzato.")
    maybe_reload_graph()
    snap = current_snapshot()
    return graph_ops.graph_query(q, snap.graph, target=target)

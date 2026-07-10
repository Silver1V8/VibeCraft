"""Route di analisi del grafo: grafo completo, Impact Ripple, Semantic Map e query
deterministica. Handler sottili: leggono lo stato, validano e delegano a core.graph_ops."""
import networkx as nx
from fastapi import APIRouter, Depends, HTTPException
from qdrant_client import QdrantClient

from api.deps import maybe_reload_graph, require_api_key, state
from core import graph_ops

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/api/graph/all")
async def get_full_graph():
    """Restituisce l'intero grafo statico (tutti i nodi e gli archi) in formato JSON."""
    maybe_reload_graph()
    graph: nx.DiGraph = state["graph"]
    if graph is None:
        raise HTTPException(status_code=503, detail="Grafo non ancora inizializzato.")
    return graph_ops.full_graph(graph, state["rule_descriptions"])


@router.get("/api/graph/impact")
async def graph_impact(node: str, depth: int = 3):
    """Impact Ripple: espansione BFS a cerchi concentrici da un nodo. Ogni 'ring' è
    un livello di distanza (1 hop, 2 hop, ...). Risponde 'cosa viene impattato se
    modifico questo nodo?' in modo deterministico (nessun LLM)."""
    maybe_reload_graph()
    graph: nx.DiGraph = state["graph"]
    if graph is None:
        raise HTTPException(status_code=503, detail="Grafo non ancora inizializzato.")
    if node not in graph:
        raise HTTPException(status_code=404, detail=f"Nodo non presente nel grafo: {node}")
    return graph_ops.impact(graph, node, depth)


@router.get("/api/graph/semantic-map")
async def graph_semantic_map():
    """Semantic Map: proietta i CHUNK (sezioni) in 2D per prossimità semantica (PCA via
    SVD sui vettori densi bge-m3 in Qdrant). Le community e i nodi 'ponte' sono calcolati
    a livello di documento padre (co-menzione di entità) e ereditati dai chunk; i duplicati
    sono sezioni molto simili appartenenti a documenti diversi. Solo numpy/networkx."""
    maybe_reload_graph()
    graph: nx.DiGraph = state["graph"]
    qdrant: QdrantClient = state["qdrant"]
    if graph is None or qdrant is None:
        raise HTTPException(status_code=503, detail="Grafo/Qdrant non inizializzati.")
    return graph_ops.semantic_map(graph, qdrant)


@router.get("/api/graph/query")
async def graph_query(q: str):
    """Query DETERMINISTICA sul grafo (nessun LLM): risponde a domande strutturali —
    'quali documenti/entità/codice esistono?', 'relazioni di X', 'cosa impatta X' — leggendo
    direttamente nodi e archi. Incarna il principio 'determinismo prima dell'LLM' (Articolo 1)."""
    if state.get("graph") is None:
        raise HTTPException(status_code=503, detail="Grafo non ancora inizializzato.")
    maybe_reload_graph()
    return graph_ops.graph_query(q, state["graph"])

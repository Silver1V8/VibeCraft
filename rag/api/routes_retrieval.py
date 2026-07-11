"""Route di retrieval: /ask (RAG completo con sintesi LLM e contesto grafo) e /api/retrieve
(retrieval puro per eval/debug). Gli handler iniettano le risorse di runtime dallo stato
(api.deps) nelle funzioni pure di core.retrieval / core.graph_ops."""
import time

import networkx as nx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from qdrant_client import QdrantClient
from FlagEmbedding import BGEM3FlagModel

from api.deps import maybe_reload_graph, require_api_key, state
from api.models import AskQuery
from core import graph_ops, retrieval
from core.config import PROJECT_ROOT

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/ask")
async def ask_rag(query: AskQuery):
    maybe_reload_graph()
    graph: nx.DiGraph = state["graph"]
    qdrant: QdrantClient = state["qdrant"]
    embed_model: BGEM3FlagModel = state["embed_model"]

    if graph is None or qdrant is None or embed_model is None:
        raise HTTPException(status_code=503, detail="Server non ancora inizializzato.")

    # 1-2. Ricerca ibrida: dense + sparse (fusione per rank) + rerank ColBERT
    search_results = retrieval.hybrid_search(
        query.question, query.top_k,
        qdrant=qdrant, embed_model=embed_model, colbert_store=state["colbert_store"],
    )

    if not search_results:
        return {
            "status": "no_results",
            "answer": "Nessun documento rilevante trovato nel knowledge base.",
            "graph_context": {},
            "qdrant_scores": [],
        }

    # 3. Nodi seed nel grafo dai risultati (documenti padre dei chunk, deduplicati
    #    preservando l'ordine di rilevanza).
    seed_nodes = list(dict.fromkeys(r["doc_id"] for r in search_results if r["doc_id"] in graph))

    if not seed_nodes:
        return {
            "status": "no_graph_nodes",
            "answer": "Documenti trovati in Qdrant ma non presenti nel grafo.",
            "graph_context": {},
            "qdrant_scores": [
                {**r, "score": r["colbert_score"] if r["colbert_score"] is not None else r["dense_score"]}
                for r in search_results
            ],
        }

    # 4a. Espansione BFS per il GRAFO (usa sempre depth >= 1 per la visualizzazione)
    graph_depth = max(query.bfs_depth, 1)
    expanded_nodes = graph_ops.bfs_expand(graph, seed_nodes, depth=graph_depth)

    # Raccoglie gli archi tra i nodi espansi per la dashboard
    expanded_set = set(expanded_nodes)
    graph_edges = [
        {"from": u, "to": v, "relation": data.get("relation", "")}
        for u, v, data in graph.edges(data=True)
        if u in expanded_set and v in expanded_set
    ]

    # Arricchisce i nodi espansi con tipo e descrizione (per il frontend)
    rule_descriptions: dict = state["rule_descriptions"]
    expanded_nodes_data = [
        {
            "id": node_id,
            "type": graph.nodes[node_id].get("type", "unknown"),
            "description": rule_descriptions.get(node_id, ""),
            # Pilastro REASONS di appartenenza (dal frontmatter YAML), per la colorazione cromatica del grafo
            "classification": graph.nodes[node_id].get("classification", ""),
        }
        for node_id in sorted(expanded_nodes)
    ]

    # -----------------------------------------------------------------------
    # 4b. Costruisce il contesto per l'LLM (Separazione logica / Ottimizzazione)
    # -----------------------------------------------------------------------

    # === INIEZIONE CHUNK-AWARE ===
    # Inietta il testo delle SEZIONI recuperate (i chunk), non i documenti interi:
    # più preciso e senza saturare il contesto. La struttura multi-hop del grafo
    # (seed + nodi espansi) resta comunque esposta in graph_context.
    chunks_store: dict = state.get("chunks", {})
    context_parts: list[str] = []
    seen_chunks: set[str] = set()
    for r in search_results:
        cid = r.get("chunk_id")
        entry = chunks_store.get(cid) if cid else None
        if entry is None or cid in seen_chunks:
            continue
        seen_chunks.add(cid)
        context_parts.append(f"--- {r['doc_id']} § {r.get('section', '')} ---\n{entry['text']}")

    # Fallback legacy: senza sidecar dei chunk, inietta i documenti seed interi
    if not context_parts:
        for doc_id in seed_nodes:
            doc_path = PROJECT_ROOT / "docs" / doc_id
            if doc_path.exists():
                context_parts.append(f"--- Inizio Documento: {doc_id} ---\n{doc_path.read_text(encoding='utf-8')}\n--- Fine Documento: {doc_id} ---")
    context = "\n\n".join(context_parts)
    # -----------------------------------------------------------------------

    # 5. Sintesi finale tramite LLM configurato.
    #    call_llm è multi-provider e sincrono (SDK anthropic/openai + httpx ollama): lo
    #    eseguiamo in threadpool per non bloccare l'event loop. TODO: rendere async anche
    #    il branch ollama di call_llm (gli SDK anthropic/openai restano sync → threadpool).
    start_time = time.time()
    answer = await run_in_threadpool(retrieval.call_llm, context, query.question)
    end_time = time.time()

    elaborazione_secondi = round(end_time - start_time, 2)
    print(f"\n[TIMER] Tempo impiegato per la generazione: {elaborazione_secondi} secondi\n")

    return {
        "status": "success",
        "answer": answer,
        "elaboration_seconds": elaborazione_secondi,
        "graph_context": {
            "seed_nodes": seed_nodes,
            "expanded_nodes": expanded_nodes_data,
            "graph_edges": graph_edges,
            "context_text": context,
        },
        # Breakdown completo del ranking ibrido: rank dense/sparse, fusione e
        # punteggio ColBERT. "score" resta il campo principale per il frontend.
        "qdrant_scores": [
            {**r, "score": r["colbert_score"] if r["colbert_score"] is not None else r["dense_score"]}
            for r in search_results
        ],
    }


@router.get("/api/retrieve")
async def api_retrieve(
    q: str = Query(min_length=1, max_length=4000),
    k: int = Query(default=5, ge=1, le=50),
):
    """Retrieval PURO (dense + sparse + ColBERT + authority), senza sintesi LLM. Restituisce
    i chunk pertinenti con il breakdown del ranking. Serve per valutare la qualità del ranking
    (golden-set / eval.run) e per il debug, senza il costo di Ollama.

    Input validato da FastAPI: `q` non vuota, `k` in [1, 50] (422 altrimenti)."""
    if state.get("qdrant") is None or state.get("embed_model") is None:
        raise HTTPException(status_code=503, detail="Indice non ancora pronto.")
    results = await run_in_threadpool(
        retrieval.hybrid_search, q, k,
        qdrant=state["qdrant"], embed_model=state["embed_model"], colbert_store=state["colbert_store"],
    )
    return {"query": q, "k": k, "results": results}

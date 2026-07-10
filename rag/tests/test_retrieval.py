"""Test delle funzioni pure di core/retrieval.py con dipendenze iniettate (nessun
FastAPI, nessun Qdrant reale): peso di autorità e selezione del contesto governato
nel percorso 'results forniti' (che non richiede il client Qdrant)."""
import networkx as nx

from core import retrieval


def _graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("spec.md", type="document")
    g.add_node("safeguards.md", type="document")
    return g


def test_authority_weights_and_penalty():
    w = retrieval._authority_weight
    assert w({"classification": "IRON_MEMORY", "status": "ENFORCED"}) == 1.0
    assert w({"classification": "AUTHORIZATION_POLICY"}) == 0.9
    assert w({"classification": "METHODOLOGY"}) == 0.5
    assert w({"classification": "SCONOSCIUTA"}) == 0.4                      # default
    assert w({"classification": "IRON_MEMORY", "status": "ARCHIVED"}) == 0.3  # penalizzazione archiviati


def test_select_governed_chunks_filters_to_graph_and_caps():
    g = _graph()
    results = [
        {"chunk_id": "spec.md#01-a", "doc_id": "spec.md", "section": "A"},
        {"chunk_id": "orfano.md#00", "doc_id": "orfano.md", "section": "B"},  # padre non nel grafo
        {"chunk_id": "safeguards.md#02-c", "doc_id": "safeguards.md", "section": "C"},
    ]
    chunks = retrieval.select_governed_chunks("q", graph=g, results=results, max_chunks=8)
    assert [c["doc_id"] for c in chunks] == ["spec.md", "safeguards.md"]   # orfano filtrato
    capped = retrieval.select_governed_chunks("q", graph=g, results=results, max_chunks=1)
    assert len(capped) == 1


def test_select_governed_chunks_no_graph_returns_empty():
    results = [{"chunk_id": "spec.md#01", "doc_id": "spec.md", "section": "A"}]
    assert retrieval.select_governed_chunks("q", graph=None, results=results) == []


def test_select_governed_docs_dedup_parents():
    g = _graph()
    results = [
        {"chunk_id": "spec.md#01", "doc_id": "spec.md", "section": "A"},
        {"chunk_id": "spec.md#02", "doc_id": "spec.md", "section": "B"},   # stesso padre
        {"chunk_id": "safeguards.md#00", "doc_id": "safeguards.md", "section": "C"},
    ]
    docs = retrieval.select_governed_docs("q", graph=g, results=results, max_docs=4)
    assert docs == ["spec.md", "safeguards.md"]   # padri unici, ordine di rilevanza


def test_retrieve_governed_context_empty_without_graph():
    # Senza grafo la selezione è vuota → contesto vuoto, nessun accesso a qdrant.
    out = retrieval.retrieve_governed_context(
        "q", graph=None, chunks_store={}, qdrant=None, embed_model=None, colbert_store={}
    )
    assert out == ""

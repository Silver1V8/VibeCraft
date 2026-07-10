"""Test del core deterministico ora estratto in core/: query deterministica sul grafo
(core.graph_ops.graph_query), authority weighting e selezione dei chunk governati
(core.retrieval). Nessun FastAPI: le funzioni prendono il grafo come parametro esplicito."""
import networkx as nx

from core import graph_ops, retrieval


# ---------------------------------------------------------------------------
# Authority weighting
# ---------------------------------------------------------------------------
def test_authority_weights():
    w = retrieval._authority_weight
    assert w({"classification": "IRON_MEMORY", "status": "ENFORCED"}) == 1.0
    assert w({"classification": "AUTHORIZATION_POLICY"}) == 0.9
    assert w({"classification": "METHODOLOGY"}) == 0.5
    assert w({"classification": "SCONOSCIUTA"}) == 0.4          # default
    assert w({"classification": "IRON_MEMORY", "status": "ARCHIVED"}) == 0.3  # archiviato penalizzato


def test_authority_normative_over_informative():
    w = retrieval._authority_weight
    assert w({"classification": "AUTHORIZATION_POLICY"}) > w({"classification": "METHODOLOGY"})


# ---------------------------------------------------------------------------
# Query deterministica sul grafo (nessun LLM)
# ---------------------------------------------------------------------------
def _synthetic_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("spec.md", type="document")
    g.add_node("safeguards.md", type="document")
    g.add_node("EVENTO", type="entity")
    g.add_node("svc.py::f", type="code", kind="function")
    g.add_edge("spec.md", "EVENTO", relation="MENTIONS")
    g.add_edge("svc.py::f", "spec.md", relation="IMPLEMENTS")
    return g


_G = _synthetic_graph()


def _q(text: str) -> dict:
    return graph_ops.graph_query(text, _G)


def test_query_lists_documents():
    r = _q("quali documenti esistono?")
    assert r["intent"] == "documenti"
    assert r["count"] == 2


def test_query_lists_entities():
    assert _q("quali entità?")["intent"] == "entità"


def test_query_lists_code():
    assert _q("quale codice c'è?")["answer"] == ["svc.py::f"]


def test_query_relations_not_confused_with_listing():
    # Regressione: "spec.md" contiene "spec" (keyword di listing documenti); l'intento
    # legato al nodo bersaglio deve avere precedenza sulle domande generiche di elenco.
    r = _q("relazioni di spec.md")
    assert r["intent"] == "relazioni"
    assert r["count"] == 2  # 1 arco uscente (EVENTO) + 1 entrante (svc.py::f)


def test_query_impact_rings():
    r = _q("cosa impatta EVENTO")
    assert r["intent"] == "impatto"
    assert r["rings"][0] == ["EVENTO"]


def test_query_unknown():
    assert _q("ciao come stai")["intent"] == "sconosciuto"


# ---------------------------------------------------------------------------
# Selezione dei chunk governati (usato da canvas/propose/validate/dry-run)
# ---------------------------------------------------------------------------
def test_select_governed_chunks_filters_to_graph_and_caps():
    g = _synthetic_graph()
    results = [
        {"chunk_id": "spec.md#01-a", "doc_id": "spec.md", "section": "A"},
        {"chunk_id": "orfano.md#00", "doc_id": "orfano.md", "section": "B"},  # padre non nel grafo
        {"chunk_id": "safeguards.md#02-c", "doc_id": "safeguards.md", "section": "C"},
    ]
    chunks = retrieval.select_governed_chunks("q", graph=g, results=results, max_chunks=8)
    parents = [c["doc_id"] for c in chunks]
    assert "orfano.md" not in parents          # filtrato: non è nel grafo
    assert parents == ["spec.md", "safeguards.md"]

    # cap rispettato
    capped = retrieval.select_governed_chunks("q", graph=g, results=results, max_chunks=1)
    assert len(capped) == 1


def test_select_governed_docs_dedup_parents():
    g = _synthetic_graph()
    results = [
        {"chunk_id": "spec.md#01", "doc_id": "spec.md", "section": "A"},
        {"chunk_id": "spec.md#02", "doc_id": "spec.md", "section": "B"},  # stesso padre
        {"chunk_id": "safeguards.md#00", "doc_id": "safeguards.md", "section": "C"},
    ]
    docs = retrieval.select_governed_docs("q", graph=g, results=results, max_docs=4)
    assert docs == ["spec.md", "safeguards.md"]  # padri unici, ordine di rilevanza

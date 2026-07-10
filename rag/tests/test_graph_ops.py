"""Test delle funzioni pure di core/graph_ops.py (grafo iniettato, nessun FastAPI):
bfs_expand, build_context, full_graph, impact. La query strutturale è già coperta
end-to-end da test_server_core.graph_query (che passa per il route handler)."""
import networkx as nx

from core import graph_ops


def _graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("spec.md", type="document", title="Spec", classification="AUTHORIZATION_POLICY")
    g.add_node("safeguards.md", type="document", title="Safeguards")
    g.add_node("EVENTO", type="entity")
    g.add_node("svc.py::f", type="code", kind="function", file="svc.py", dev_type="backend")
    g.add_edge("spec.md", "EVENTO", relation="MENTIONS")
    g.add_edge("svc.py::f", "spec.md", relation="IMPLEMENTS")
    return g


def test_bfs_expand_bidirectional():
    g = _graph()
    # da EVENTO: 1 hop raggiunge spec.md (predecessore), 2 hop raggiunge svc.py::f
    assert graph_ops.bfs_expand(g, ["EVENTO"], depth=1) == {"EVENTO", "spec.md"}
    assert graph_ops.bfs_expand(g, ["EVENTO"], depth=2) == {"EVENTO", "spec.md", "svc.py::f"}


def test_build_context_documents_and_entities():
    g = _graph()
    ctx = graph_ops.build_context(g, {"spec.md", "EVENTO"})
    assert "[DOCUMENTO: spec.md]" in ctx
    assert "-> MENTIONS -> [EVENTO]" in ctx
    assert "[ENTITÀ: EVENTO]" in ctx
    assert "<- MENTIONS <- [spec.md]" in ctx


def test_full_graph_serializes_nodes_and_edges():
    g = _graph()
    out = graph_ops.full_graph(g, rule_descriptions={"EVENTO": "un evento aziendale"})
    ids = {n["id"] for n in out["nodes"]}
    assert ids == {"spec.md", "safeguards.md", "EVENTO", "svc.py::f"}
    evento = next(n for n in out["nodes"] if n["id"] == "EVENTO")
    assert evento["description"] == "un evento aziendale"   # descrizione iniettata
    code = next(n for n in out["nodes"] if n["id"] == "svc.py::f")
    assert code["kind"] == "function" and code["file"] == "svc.py"
    assert {"from": "spec.md", "to": "EVENTO", "relation": "MENTIONS"} in out["edges"]


def test_impact_rings_and_membership():
    g = _graph()
    out = graph_ops.impact(g, "spec.md", depth=3)
    assert out["center"] == "spec.md"
    assert out["rings"][0] == 1                     # solo il centro nel ring 0
    ids = {n["id"] for n in out["nodes"]}
    assert {"spec.md", "EVENTO", "svc.py::f"} <= ids  # vicini entranti e uscenti
    # gli archi restituiti sono solo quelli interni all'insieme visitato
    for e in out["edges"]:
        assert e["from"] in ids and e["to"] in ids

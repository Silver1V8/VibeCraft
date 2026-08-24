"""Test delle funzioni pure di core/graph_ops.py (grafo iniettato, nessun FastAPI):
bfs_expand, build_context, full_graph, impact. La query strutturale è già coperta
end-to-end da test_server_core.graph_query (che passa per il route handler)."""
import networkx as nx
import pytest

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


# ---------------------------------------------------------------------------
# Fiducia sugli archi (S2, ADR 0002): edge_nature, edge_reliability,
# implements_reliability. Puro metadato — non entra in bfs_expand/build_context/
# full_graph/impact sopra, quindi non li si ritesta.
# ---------------------------------------------------------------------------
def test_natura_per_relazione():
    """PART_OF/MENTIONS sono strutturali (filesystem/regex deterministica), gli archi
    tipizzati dal frontmatter sono curati, IMPLEMENTS/REFERENCES sono inferiti (euristica)."""
    assert graph_ops.edge_nature("PART_OF") == "structural"
    assert graph_ops.edge_nature("MENTIONS") == "structural"
    assert graph_ops.edge_nature("IMPLEMENTS") == "inferred"
    assert graph_ops.edge_nature("REFERENCES") == "inferred"
    assert graph_ops.edge_nature("EREDITA_VINCOLI") == "curated"  # arco tipizzato del frontmatter


def test_relazione_sconosciuta_ricade_su_curated():
    """Una relazione del frontmatter mai vista (`type: "PIPPO"`) non fa esplodere nulla e
    ricade su 'curated': arriva comunque da una dichiarazione umana, non da un algoritmo."""
    assert graph_ops.edge_nature("PIPPO") == "curated"
    attrs = graph_ops.edge_trust_attrs("PIPPO")
    assert attrs["nature"] == "curated"
    assert attrs["reliability"] == graph_ops.GRAPH_TRUST_NATURE_RELIABILITY["curated"]


def test_implements_forte_piu_affidabile_di_implements_debole():
    """Due IMPLEMENTS con coseno diverso (0.92 forte, 0.46 appena sopra soglia 0.45): quello
    forte ha reliability STRETTAMENTE maggiore. Si asserisce la relazione d'ordine, non i
    valori assoluti (che sono empirici e ricalibrabili)."""
    forte = graph_ops.implements_reliability(0.92)
    debole = graph_ops.implements_reliability(0.46)
    assert forte > debole


def test_edge_reliability_fallback_su_grafo_legacy():
    """Un arco costruito SENZA i nuovi attributi (com'è ogni arco in database/graph.json
    prima di questa modifica) restituisce comunque un'affidabilità sensata, derivata dalla
    relazione: niente KeyError, niente re-indicizzazione necessaria."""
    assert graph_ops.edge_reliability({"relation": "PART_OF"}) == 1.0
    assert graph_ops.edge_reliability({"relation": "IMPLEMENTS"}) == 0.6
    # Se reliability è già presente (grafo post-S2), quella vince e basta.
    assert graph_ops.edge_reliability({"relation": "PART_OF", "reliability": 0.42}) == 0.42


# ---------------------------------------------------------------------------
# trust_paths: fiducia sul cammino (S3, ADR 0002)
# ---------------------------------------------------------------------------
def _catena() -> nx.DiGraph:
    """a -> b -> c con archi identici (EREDITA_VINCOLI, curated 0.9)."""
    g = nx.DiGraph()
    g.add_edge("a", "b", relation="EREDITA_VINCOLI", nature="curated", reliability=0.9)
    g.add_edge("b", "c", relation="EREDITA_VINCOLI", nature="curated", reliability=0.9)
    return g


def test_trust_seed_e_uno():
    out = graph_ops.trust_paths(_catena(), ["a"], depth=2)
    assert out["a"]["trust"] == 1.0
    assert out["a"]["hops"] == 0


def test_trust_decresce_con_la_distanza():
    out = graph_ops.trust_paths(_catena(), ["a"], depth=2)
    assert out["a"]["trust"] > out["b"]["trust"] > out["c"]["trust"]


def test_cammino_curato_batte_cammino_inferito():
    """Due cammini della STESSA lunghezza dal seed: quello di archi dichiarati da un umano
    vale piu' di quello congetturato per coseno. E' la proprieta' che giustifica S2."""
    g = nx.DiGraph()
    g.add_edge("seed", "curato", relation="EREDITA_VINCOLI", nature="curated", reliability=0.9)
    g.add_edge("seed", "inferito", relation="IMPLEMENTS", nature="inferred", reliability=0.6)
    out = graph_ops.trust_paths(g, ["seed"], depth=1)
    assert out["curato"]["hops"] == out["inferito"]["hops"] == 1
    assert out["curato"]["trust"] > out["inferito"]["trust"]


def test_prodotto_affidabilita_lungo_il_cammino():
    g = nx.DiGraph()
    g.add_edge("a", "b", relation="X", nature="curated", reliability=0.8)
    g.add_edge("b", "c", relation="Y", nature="inferred", reliability=0.5)
    out = graph_ops.trust_paths(g, ["a"], depth=2)
    assert out["b"]["trust"] == pytest.approx(0.8)
    assert out["c"]["trust"] == pytest.approx((0.8 * 0.5) / 2)


def test_via_ricostruisce_il_cammino():
    out = graph_ops.trust_paths(_catena(), ["a"], depth=2)
    assert out["a"]["via"] == ["a"]
    assert out["b"]["via"] == ["a", "b"]
    assert out["c"]["via"] == ["a", "b", "c"]
    # `via` include il seed, quindi ha sempre hops + 1 elementi
    for info in out.values():
        assert len(info["via"]) == info["hops"] + 1


def test_bfs_bidirezionale():
    """Stessa copertura di bfs_expand: un nodo raggiungibile solo risalendo un arco."""
    g = _graph()
    out = graph_ops.trust_paths(g, ["EVENTO"], depth=2)
    assert set(out) == {"EVENTO", "spec.md", "svc.py::f"}
    # spec.md e' predecessore di EVENTO: risalire l'arco non cambia l'affidabilita'
    assert out["spec.md"]["hops"] == 1
    assert set(out) == graph_ops.bfs_expand(g, ["EVENTO"], depth=2)


def test_depth_zero_restituisce_solo_i_seed():
    out = graph_ops.trust_paths(_catena(), ["a"], depth=0)
    assert set(out) == {"a"}
    assert out["a"]["trust"] == 1.0


def test_grafo_ciclico_termina():
    """Su a -> b -> c -> a ogni nodo prende la fiducia del cammino PIU' BREVE, non
    dell'ultimo visitato, e la funzione termina."""
    g = nx.DiGraph()
    for u, v in (("a", "b"), ("b", "c"), ("c", "a")):
        g.add_edge(u, v, relation="X", nature="curated", reliability=0.9)
    out = graph_ops.trust_paths(g, ["a"], depth=5)
    assert set(out) == {"a", "b", "c"}
    # b e c sono entrambi a 1 hop da a (c risalendo l'arco c -> a)
    assert out["b"]["hops"] == out["c"]["hops"] == 1
    assert out["b"]["trust"] == out["c"]["trust"] == pytest.approx(0.9)


def test_trust_su_grafo_legacy_senza_reliability():
    """Un grafo persistito PRIMA di S2 non ha nature/reliability sugli archi: il fallback
    di edge_reliability deve produrre comunque punteggi sensati (e discriminanti)."""
    g = nx.DiGraph()
    g.add_edge("seed", "strutturale", relation="MENTIONS")     # -> 1.0
    g.add_edge("seed", "inferito", relation="IMPLEMENTS")      # -> 0.6
    out = graph_ops.trust_paths(g, ["seed"], depth=1)
    assert out["strutturale"]["trust"] == pytest.approx(1.0)
    assert out["inferito"]["trust"] == pytest.approx(0.6)


def test_a_parita_di_lunghezza_vince_il_cammino_piu_affidabile():
    """Due cammini di 2 hop verso lo stesso nodo: il tie-break tiene il prodotto migliore,
    cosi' il punteggio non dipende dall'ordine di visita (le ancore del codice ci si
    ordinano sopra)."""
    g = nx.DiGraph()
    g.add_edge("seed", "forte", relation="X", nature="structural", reliability=1.0)
    g.add_edge("seed", "debole", relation="Y", nature="inferred", reliability=0.5)
    g.add_edge("forte", "meta", relation="X", nature="structural", reliability=1.0)
    g.add_edge("debole", "meta", relation="Y", nature="inferred", reliability=0.5)
    out = graph_ops.trust_paths(g, ["seed"], depth=2)
    assert out["meta"]["via"] == ["seed", "forte", "meta"]
    assert out["meta"]["trust"] == pytest.approx(1.0 / 2)

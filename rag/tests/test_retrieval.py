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
    from core.config import AUTHORITY_DEFAULT_WEIGHT
    assert w({"classification": "SCONOSCIUTA"}) == AUTHORITY_DEFAULT_WEIGHT  # default (da config, calibrabile)
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


def test_scope_tag_filter_matches_any_variant():
    # Il filtro cerca il dev_type sotto la chiave dichiarata dal documento, in una qualsiasi
    # delle grafie possibili: e' il doc che si dichiara, non noi che nominiamo dei file.
    f = retrieval.scope_tag_filter("tags", ["logicagent", "logic-agent"])
    assert f is not None
    cond = f.must[0]
    assert cond.key == "tags"
    assert cond.match.any == ["logicagent", "logic-agent"]


def test_scope_tag_filter_none_when_unconfigured():
    # Senza chiave (config vuota) o senza valori non si filtra: nessuna convenzione inventata.
    assert retrieval.scope_tag_filter("", ["frontend"]) is None
    assert retrieval.scope_tag_filter("tags", []) is None


# ---------------------------------------------------------------------------
# collect_implementing_code: ponte codice (grafo) -> contesto di /ask
# ---------------------------------------------------------------------------
def _code_graph() -> nx.DiGraph:
    """Grafo con una sezione-documento e due simboli di codice che la implementano
    (archi IMPLEMENTS con peso), più un simbolo debolmente linkato e uno REFERENCES."""
    g = nx.DiGraph()
    g.add_node("spec.md#01-form", type="chunk")
    g.add_node("code/frontend/form.tsx::BookingForm", type="code", name="BookingForm")
    g.add_node("code/frontend/api.ts::apiClient", type="code", name="apiClient")
    g.add_node("code/frontend/styles.css::x", type="code", name="x")
    g.add_edge("code/frontend/form.tsx::BookingForm", "spec.md#01-form", relation="IMPLEMENTS", weight=0.72)
    g.add_edge("code/frontend/api.ts::apiClient", "spec.md#01-form", relation="IMPLEMENTS", weight=0.55)
    g.add_edge("code/frontend/styles.css::x", "spec.md#01-form", relation="IMPLEMENTS", weight=0.48)  # sotto soglia
    g.add_edge("code/frontend/form.tsx::BookingForm", "EVENTO", relation="REFERENCES")  # non IMPLEMENTS
    return g


def _code_store() -> dict:
    return {
        "code/frontend/form.tsx::BookingForm": {"name": "BookingForm", "kind": "component",
                                                "file": "frontend/form.tsx", "dev_type": "frontend", "text": "export function BookingForm"},
        "code/frontend/api.ts::apiClient": {"name": "apiClient", "kind": "object",
                                            "file": "frontend/api.ts", "dev_type": "frontend", "text": "export const apiClient"},
        "code/frontend/styles.css::x": {"name": "x", "kind": "stylesheet",
                                        "file": "frontend/styles.css", "dev_type": "frontend", "text": ".x{}"},
    }


def test_collect_implementing_code_ranks_and_thresholds():
    out = retrieval.collect_implementing_code(
        _code_graph(), _code_store(), ["spec.md#01-form"], min_weight=0.5, max_snippets=6)
    # Ordinati per peso decrescente; lo styles.css sotto 0.5 e il REFERENCES sono esclusi.
    assert [c["name"] for c in out] == ["BookingForm", "apiClient"]
    assert out[0]["weight"] == 0.72 and out[0]["file"] == "frontend/form.tsx"
    assert out[0]["implements"] == "spec.md#01-form"
    assert out[0]["text"] == "export function BookingForm"


def test_collect_implementing_code_caps_and_dedups():
    g = _code_graph()
    # Lo stesso simbolo implementa due sezioni diverse con pesi diversi: dedup sul peso migliore.
    g.add_node("spec.md#02-altra", type="chunk")
    g.add_edge("code/frontend/form.tsx::BookingForm", "spec.md#02-altra", relation="IMPLEMENTS", weight=0.90)
    out = retrieval.collect_implementing_code(
        g, _code_store(), ["spec.md#01-form", "spec.md#02-altra"], min_weight=0.5, max_snippets=1)
    assert len(out) == 1
    assert out[0]["name"] == "BookingForm" and out[0]["weight"] == 0.90  # tiene il peso migliore


def test_collect_implementing_code_disabled_or_empty():
    g, cs = _code_graph(), _code_store()
    assert retrieval.collect_implementing_code(g, cs, ["spec.md#01-form"], min_weight=0.5, max_snippets=0) == []
    assert retrieval.collect_implementing_code(None, cs, ["spec.md#01-form"], min_weight=0.5, max_snippets=6) == []
    assert retrieval.collect_implementing_code(g, {}, ["spec.md#01-form"], min_weight=0.5, max_snippets=6) == []
    assert retrieval.collect_implementing_code(g, cs, ["assente"], min_weight=0.5, max_snippets=6) == []

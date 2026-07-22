"""Test delle funzioni pure di core/retrieval.py con dipendenze iniettate (nessun
FastAPI, nessun Qdrant reale): peso di autorità e selezione del contesto governato
nel percorso 'results forniti' (che non richiede il client Qdrant), più hybrid_search
con qdrant/embed_model finti (nessuna rete, nessun modello bge-m3 reale)."""
import networkx as nx
import numpy as np

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


# ---------------------------------------------------------------------------
# hybrid_search: parametrizzazione di collection_name (blue/green Qdrant, S3).
# Nessun Qdrant/bge-m3 reale: qdrant e embed_model sono fake minimali che registrano
# solo il nome di collection ricevuto da query_points.
# ---------------------------------------------------------------------------
class _FakePoints:
    def __init__(self, points):
        self.points = points


class _FakeEmbedModel:
    """Restituisce vettori fissi per QUALSIASI domanda: basta a far girare
    hybrid_search senza bge-m3 reale (colbert_store vuoto -> il vettore colbert
    della query non viene mai usato aritmeticamente)."""
    def encode(self, questions, **kwargs):
        return {
            "dense_vecs": [np.array([0.1, 0.2, 0.3])],
            "lexical_weights": [{}],
            "colbert_vecs": [np.zeros((1, 3))],
        }


class _RecordingQdrant:
    """query_points finto: non cerca nulla, registra solo il collection_name
    ricevuto a ogni chiamata (una per il ramo denso, una per lo sparso)."""
    def __init__(self):
        self.collections_seen: list[str] = []

    def query_points(self, *, collection_name, query, using, limit, query_filter=None):
        self.collections_seen.append(collection_name)
        return _FakePoints([])


def test_hybrid_search_default_collection_name_is_config_constant():
    qdrant = _RecordingQdrant()
    retrieval.hybrid_search("domanda", 5, qdrant=qdrant, embed_model=_FakeEmbedModel(), colbert_store={})
    # Due chiamate (dense + sparse), entrambe sulla collection di default: nessun
    # cambio di comportamento quando collection_name non viene passato.
    assert qdrant.collections_seen == [retrieval.COLLECTION_NAME, retrieval.COLLECTION_NAME]


def test_hybrid_search_explicit_collection_name_is_propagated():
    qdrant = _RecordingQdrant()
    retrieval.hybrid_search(
        "domanda", 5, qdrant=qdrant, embed_model=_FakeEmbedModel(), colbert_store={},
        collection_name="vibecraft_events__v20260717T101530",
    )
    assert qdrant.collections_seen == [
        "vibecraft_events__v20260717T101530", "vibecraft_events__v20260717T101530",
    ]


class _CountingEmbedModel(_FakeEmbedModel):
    """Come _FakeEmbedModel ma conta le forward pass: serve a provare che /ask codifica
    la domanda UNA volta sola anche servendo due rami di ricerca."""
    def __init__(self):
        self.calls = 0

    def encode(self, questions, **kwargs):
        self.calls += 1
        return super().encode(questions, **kwargs)


def test_hybrid_search_reuses_precomputed_query_encoding():
    model = _CountingEmbedModel()
    encoding = retrieval.encode_query(model, "domanda")
    assert model.calls == 1
    assert set(encoding) == {"dense", "lexical", "colbert"}
    retrieval.hybrid_search("domanda", 5, qdrant=_RecordingQdrant(), embed_model=model,
                            colbert_store={}, query_encoding=encoding)
    assert model.calls == 1  # nessuna seconda codifica della stessa domanda


# ---------------------------------------------------------------------------
# search_code_symbols: ricerca semantica DIRETTA sul codice (il ramo che rende il
# codice interrogabile senza passare dai documenti).
# ---------------------------------------------------------------------------
def _vec(*xs) -> np.ndarray:
    return np.array(xs, dtype=np.float16)


def _searchable_code_store() -> dict:
    """Tre simboli con vettori densi noti (già normalizzati sugli assi) più uno privo
    di vettore: quest'ultimo non deve mai comparire nei risultati."""
    return {
        "code/dto.cs::Request": {"name": "Request", "kind": "class", "file": "dto.cs",
                                 "dev_type": "backend", "text": "class Request",
                                 "win_chunk_id": "spec.md#01-form", "dense": _vec(1.0, 0.0, 0.0)},
        "code/dto.cs::Request.Campo": {"name": "Request.Campo", "kind": "property", "file": "dto.cs",
                                       "dev_type": "backend", "text": "string Campo",
                                       "dense": _vec(0.99, 0.14, 0.0)},
        "code/altro.cs::Altro": {"name": "Altro", "kind": "class", "file": "altro.cs",
                                 "dev_type": "backend", "text": "class Altro",
                                 "dense": _vec(0.7, 0.7, 0.0)},
        "code/senza_vettore.cs::X": {"name": "X", "kind": "class", "file": "senza_vettore.cs",
                                     "dev_type": "backend", "text": "class X"},
    }


def test_search_code_symbols_ranks_by_similarity_to_question():
    out = retrieval.search_code_symbols(np.array([1.0, 0.0, 0.0]), _searchable_code_store(),
                                        max_snippets=4, min_score=0.0)
    assert [c["name"] for c in out] == ["Request", "Request.Campo", "Altro"]  # senza_vettore escluso
    assert out[0]["score"] == 1.0 and out[0]["source"] == "semantic"
    assert out[0]["text"] == "class Request"
    # L'ancora è la sezione che il simbolo implementa, se il linking l'ha calcolata.
    assert out[0]["implements"] == "spec.md#01-form"
    assert out[1]["implements"] == ""


def test_search_code_symbols_min_score_and_disabled():
    store = _searchable_code_store()
    q = np.array([1.0, 0.0, 0.0])
    # 'Altro' è a ~0.707 dalla domanda: sopra soglia resta, alzandola cade.
    assert len(retrieval.search_code_symbols(q, store, max_snippets=4, min_score=0.8)) == 2
    assert retrieval.search_code_symbols(q, store, max_snippets=0, min_score=0.0) == []
    assert retrieval.search_code_symbols(q, {}, max_snippets=4, min_score=0.0) == []
    assert retrieval.search_code_symbols(None, store, max_snippets=4, min_score=0.0) == []


def test_search_code_symbols_caps_symbols_per_file():
    # dto.cs ha i due simboli più simili: col tetto a 1 ne passa uno solo e sale altro.cs,
    # così un singolo file (tipicamente autogenerato) non occupa tutte le posizioni.
    out = retrieval.search_code_symbols(np.array([1.0, 0.0, 0.0]), _searchable_code_store(),
                                        max_snippets=2, min_score=0.0, max_per_file=1)
    assert [c["file"] for c in out] == ["dto.cs", "altro.cs"]
    # max_per_file=0 disattiva il limite: tornano i due simboli di dto.cs.
    out = retrieval.search_code_symbols(np.array([1.0, 0.0, 0.0]), _searchable_code_store(),
                                        max_snippets=2, min_score=0.0, max_per_file=0)
    assert [c["file"] for c in out] == ["dto.cs", "dto.cs"]


def test_merge_code_context_dedups_keeping_first_group_and_caps():
    semantic = retrieval.search_code_symbols(np.array([1.0, 0.0, 0.0]), _searchable_code_store(),
                                             max_snippets=1, min_score=0.0)
    linked = retrieval.collect_implementing_code(_code_graph(), _code_store(),
                                                 ["spec.md#01-form"], min_weight=0.5, max_snippets=6)
    merged = retrieval.merge_code_context(semantic, linked, max_snippets=10)
    assert [c["name"] for c in merged] == ["Request", "BookingForm", "apiClient"]
    assert [c["source"] for c in merged] == ["semantic", "implements", "implements"]
    # Il tetto è COMPLESSIVO sui rami sommati, non per ramo.
    assert len(retrieval.merge_code_context(semantic, linked, max_snippets=2)) == 2
    assert retrieval.merge_code_context(semantic, linked, max_snippets=0) == []


def test_merge_code_context_semantic_wins_on_duplicate_symbol():
    """Lo stesso simbolo trovato da entrambi i rami compare una volta sola, con la
    provenienza del ramo prioritario (quello semantico)."""
    entry = {"symbol_id": "s", "name": "n", "source": "semantic", "score": 0.9}
    dup = {"symbol_id": "s", "name": "n", "source": "implements", "score": 0.6}
    merged = retrieval.merge_code_context([entry], [dup], max_snippets=5)
    assert merged == [entry]

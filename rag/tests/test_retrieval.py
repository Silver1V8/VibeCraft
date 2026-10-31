"""Test delle funzioni pure di core/retrieval.py con dipendenze iniettate (nessun
FastAPI, nessun Qdrant reale): peso di autorità e selezione del contesto governato
nel percorso 'results forniti' (che non richiede il client Qdrant), più hybrid_search
con qdrant/embed_model finti (nessuna rete, nessun modello bge-m3 reale)."""
import logging

import networkx as nx
import numpy as np
import pytest

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


def test_authority_dichiarata_vince_sulla_classe():
    """Il coefficiente per-documento del frontmatter precede il peso di classe.

    È il difetto che [REGOLA-VAL-08] prescrive di non avere: `authority` è obbligatoria per
    policy e scritta in ogni documento, ma il peso veniva dedotto dalla sola `classification`.
    La precedenza è per-documento perché due fonti della stessa classe non pesano
    necessariamente uguale — è esattamente l'informazione che la classe non può esprimere."""
    w = retrieval._authority_weight
    assert w({"classification": "METHODOLOGY", "authority": 0.95}) == 0.95
    assert w({"classification": "METHODOLOGY"}) == 0.5          # senza dichiarazione: la classe

    # Vale anche quando la dichiarata è PIÙ BASSA della classe: non è un boost, è una
    # sostituzione. Una fonte che si dichiara poco autorevole va creduta.
    assert w({"classification": "IRON_MEMORY", "authority": 0.2}) == 0.2

    # Gli estremi del range sono valori legittimi, non casi limite da scartare.
    assert w({"classification": "METHODOLOGY", "authority": 0.0}) == 0.0
    assert w({"classification": "METHODOLOGY", "authority": 1.0}) == 1.0


def test_authority_dichiarata_ignorata_se_kill_switch_spento():
    """Col kill-switch spento si torna ESATTAMENTE al comportamento storico (peso di classe).

    Serve perché questo è l'unico intervento che cambia l'ordinamento di produzione senza
    passare da un parametro numerico: `authority.use_declared: false` in rag_config.yaml deve
    bastare a tornare indietro, senza toccare il codice né ri-indicizzare. Il test passa il
    parametro iniettato, che è lo stesso valore su cui la config lega il default all'import."""
    w = retrieval._authority_weight
    attrs = {"classification": "METHODOLOGY", "authority": 0.95}
    assert w(attrs, use_declared=False) == 0.5                  # peso di classe, dichiarata ignorata
    assert w(attrs, use_declared=False) == w({"classification": "METHODOLOGY"})


@pytest.mark.parametrize("valore", ["molto alta", None, -0.5, 1.7, "", float("nan"), True])
def test_authority_invalida_degrada_alla_classe(valore):
    """Un frontmatter scritto male non deve far fallire una richiesta di retrieval.

    Il campo è compilato a mano in ogni documento: prima o poi qualcuno scriverà
    `authority: molto alta`, o lascerà la chiave vuota, o sforerà il range. In tutti questi casi
    si degrada al peso di classe SENZA sollevare — una query non può morire per un typo in un
    documento che nemmeno è quello cercato.

    `True` è nella lista di proposito: in YAML `authority: yes` viene letto come booleano, e
    `float(True)` varrebbe 1.0, cioè il peso MASSIMO regalato a un errore di battitura."""
    w = retrieval._authority_weight
    assert w({"classification": "METHODOLOGY", "authority": valore}) == 0.5


def test_fonte_non_classificata_pesa_meno_di_una_spec():
    """Una fonte priva di qualunque metadato di governance deve pesare MENO di una spec.

    `read_document()` restituisce frontmatter vuoto per ogni formato non-.md (pdf, docx, xlsx,
    txt): un PDF importato entrava nel ranking con lo stesso peso di una spec REQUIREMENTS
    calibrata, perché entrambi ricadevano sull'unico `default_weight`. È l'inversione di
    priorità che [REGOLA-VAL-08] cita come failure mode.

    Si asserisce la RELAZIONE D'ORDINE, non i due numeri: è la proprietà che deve reggere anche
    dopo una ricalibrazione dei pesi (S5), mentre i valori assoluti no."""
    w = retrieval._authority_weight
    pdf_importato = w({})                                       # nessun frontmatter: il non-.md
    spec = w({"classification": "REQUIREMENTS"})                # classe nota ma non elencata
    assert pdf_importato < spec

    # Non è un artefatto della classe assente-come-chiave: vale anche per una classification
    # esplicitamente vuota o nulla, che significa comunque "questa fonte non è classificata".
    assert w({"classification": ""}) == pdf_importato
    assert w({"classification": None}) == pdf_importato


def test_decadimento_archiviati_si_applica_anche_alla_dichiarata():
    """Il decadimento per status archiviato è ORTOGONALE alla provenienza del peso base.

    Se si applicasse solo al ramo di classe, un documento archiviato che dichiara `authority`
    alta scavalcherebbe una fonte vigente — e il giudizio umano "questo non vale più" verrebbe
    annullato proprio dal campo che il documento scrive su se stesso."""
    from core.config import AUTHORITY_ARCHIVED_DECAY
    w = retrieval._authority_weight
    assert w({"authority": 0.98, "status": "ARCHIVED"}) == pytest.approx(0.98 * AUTHORITY_ARCHIVED_DECAY)
    # Vale su tutti gli status che contano come archiviati, non solo su ARCHIVED.
    assert w({"authority": 0.98, "status": "DEPRECATED"}) == pytest.approx(0.98 * AUTHORITY_ARCHIVED_DECAY)
    # E vale anche sul ramo "non classificata", che è il terzo dei quattro.
    assert w({"status": "ARCHIVED"}) < w({})


def test_peso_autorita_e_indipendente_dai_campi_temporali():
    """L'autorità non deve MAI dipendere dalla freschezza del documento.

    È l'invariante più facile da rompere per errore: il frontmatter porta `date`,
    `last_updated` e `version` accanto a `classification`, e `_authority_weight` riceve il
    dict INTERO — basta una riga in più per trasformare il peso di autorità in un peso di
    recency senza che nessun test se ne accorga.

    La distinzione è sostanziale, non stilistica. Il drift detection (hash del contenuto)
    sa che un file è CAMBIATO; non sa se ci si può ancora FIDARE di ciò che dice. Una spec
    di due anni mai toccata resta la fonte primaria del suo ambito; una change di ieri può
    essere già superata. L'unico segnale temporale ammesso resta `status`
    (ARCHIVED/DEPRECATED/…), che è un GIUDIZIO UMANO esplicito — "questo non vale più" —
    e non una data: quello è già coperto da test_authority_weights_and_penalty.

    Vedi rag/adr/0002-autorita-dichiarata-e-fiducia-sul-cammino.md.
    """
    w = retrieval._authority_weight
    vecchio = {"classification": "IRON_MEMORY", "status": "ENFORCED",
               "date": "2020-01-01", "last_updated": "2020-01-01", "version": "1.0.0"}
    recente = {"classification": "IRON_MEMORY", "status": "ENFORCED",
               "date": "2026-08-18", "last_updated": "2026-08-18", "version": "9.9.9"}
    assert w(vecchio) == w(recente)

    # Vale anche per una classe qualsiasi, non solo per quella a peso massimo: se il peso
    # base cambiasse, la penalizzazione temporale potrebbe nascondersi in un solo ramo.
    assert w({**vecchio, "classification": "METHODOLOGY"}) == w({**recente, "classification": "METHODOLOGY"})

    # E il peso non cambia nemmeno TOGLIENDO del tutto i campi temporali: la funzione non
    # deve avere un ramo "se non so quanto è vecchio, penalizzo".
    assert w({"classification": "IRON_MEMORY", "status": "ENFORCED"}) == w(recente)

    # Vale anche sul ramo dell'autorità DICHIARATA, aggiunto dopo questo test: è il punto in cui
    # la tentazione è più forte, perché `authority` sta nello stesso frontmatter di `date` e
    # `version` e chi legge il campo ha gli altri due sotto gli occhi.
    assert w({**vecchio, "authority": 0.87}) == w({**recente, "authority": 0.87}) == 0.87

    # E sul ramo della fonte non classificata: nemmeno "non so nulla di questa fonte, guardo
    # almeno quanto è vecchia" è un ragionamento ammesso.
    solo_date = {"date": "2020-01-01", "last_updated": "2020-01-01", "version": "1.0.0"}
    assert w(solo_date) == w({})


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


@pytest.mark.parametrize("missing", ["qdrant", "embed_model"])
def test_select_governed_chunks_missing_runtime_is_not_empty(missing):
    resources = dict(qdrant=_RecordingQdrant(), embed_model=_FakeEmbedModel())
    resources[missing] = None
    with pytest.raises(RuntimeError, match="Retrieval"):
        retrieval.select_governed_chunks("q", graph=_graph(), **resources)


@pytest.mark.parametrize("failure", ["qdrant", "embedding"])
def test_governed_search_failure_is_not_zero_results(monkeypatch, failure):
    qdrant, model = _RecordingQdrant(), _FakeEmbedModel()

    def unavailable(*args, **kwargs):
        raise ConnectionError("private host:6333 secret")

    monkeypatch.setattr(qdrant if failure == "qdrant" else model,
                        "query_points" if failure == "qdrant" else "encode", unavailable)
    with pytest.raises(RuntimeError, match="Retrieval") as error:
        retrieval.select_governed_docs("q", graph=_graph(), qdrant=qdrant, embed_model=model)
    assert "private host" not in str(error.value)
    assert isinstance(error.value.__cause__, ConnectionError)


def test_governed_search_zero_results_is_valid():
    assert retrieval.retrieve_governed_context(
        "q", graph=_graph(), chunks_store={}, qdrant=_RecordingQdrant(),
        embed_model=_FakeEmbedModel(), colbert_store={}) == ""


def test_governed_context_missing_retrieved_text_is_an_error(monkeypatch):
    monkeypatch.setattr(retrieval, "hybrid_search", lambda *a, **k: [
        {"doc_id": "spec.md", "chunk_id": "spec.md#01", "section": "A"}])
    with pytest.raises(RuntimeError, match="Retrieval"):
        retrieval.retrieve_governed_context(
            "q", graph=_graph(), chunks_store={}, qdrant=object(),
            embed_model=object(), colbert_store={})


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


def test_search_code_symbols_subset_restricts_candidates_before_topk():
    """Il filtro per sottoinsieme (usato da /api/code/search?dev_type=) deve agire PRIMA della
    selezione dei top-k: un simbolo dell'ambito richiesto deve emergere anche quando i migliori
    in assoluto appartengono a un altro ambito — è esattamente il caso che un filtro applicato
    a valle dei top-k perderebbe."""
    from api import deps

    store = _searchable_code_store()
    store["code/altro.cs::Altro"]["dev_type"] = "frontend"
    code_ids, code_matrix = deps._prep_code_matrix(store)
    frontend_idx = deps._prep_dev_type_index(code_ids, store)["frontend"]

    q = np.array([1.0, 0.0, 0.0])  # i due simboli più vicini sono backend (dto.cs)
    out = retrieval.search_code_symbols(q, store, max_snippets=2, min_score=0.0,
                                        code_ids=code_ids, code_matrix=code_matrix,
                                        subset_idx=frontend_idx)
    assert [c["symbol_id"] for c in out] == ["code/altro.cs::Altro"]
    # Lo score è quello globale (coseno col simbolo normalizzato): restringere i candidati
    # non ripondera nulla.
    assert out[0]["score"] == 0.707


def test_search_code_symbols_subset_empty_and_none():
    """Sottoinsieme vuoto = ambito senza simboli, quindi nessun risultato (non 'tutti')."""
    from api import deps

    store = _searchable_code_store()
    code_ids, code_matrix = deps._prep_code_matrix(store)
    q = np.array([1.0, 0.0, 0.0])
    kw = dict(max_snippets=4, min_score=0.0, code_ids=code_ids, code_matrix=code_matrix)

    assert retrieval.search_code_symbols(q, store, subset_idx=np.array([], dtype=np.int64), **kw) == []
    # subset_idx=None è il comportamento storico, invariato.
    assert (retrieval.search_code_symbols(q, store, subset_idx=None, **kw)
            == retrieval.search_code_symbols(q, store, **kw))
    # Un sottoinsieme che copre TUTTE le righe non cambia nulla rispetto al filtro assente.
    full = np.arange(len(code_ids), dtype=np.int64)
    assert (retrieval.search_code_symbols(q, store, subset_idx=full, **kw)
            == retrieval.search_code_symbols(q, store, **kw))


def test_prep_dev_type_index_groups_rows_by_scope():
    from api import deps

    store = _searchable_code_store()
    store["code/altro.cs::Altro"]["dev_type"] = "frontend"
    store["code/dto.cs::Request.Campo"]["dev_type"] = ""  # senza ambito: in nessun gruppo
    code_ids, _ = deps._prep_code_matrix(store)
    groups = deps._prep_dev_type_index(code_ids, store)

    assert sorted(groups) == ["backend", "frontend"]
    assert [code_ids[i] for i in groups["backend"]] == ["code/dto.cs::Request"]
    assert [code_ids[i] for i in groups["frontend"]] == ["code/altro.cs::Altro"]


def test_search_code_symbols_precomputed_matches_on_the_fly():
    """Equivalenza numerica (Gate): a parità di code_store e query, i risultati ottenuti
    passando code_ids/code_matrix precalcolati dallo snapshot (api.deps._prep_code_matrix)
    devono essere IDENTICI a quelli ottenuti lasciando ricostruire la matrice on-the-fly —
    stessi symbol_id, stesso ordine, stessi score. La normalizzazione L2 dei simboli è
    identica nei due path, cambia solo DOVE viene calcolata."""
    from api import deps

    store = _searchable_code_store()
    code_ids, code_matrix = deps._prep_code_matrix(store)

    # Diverse combinazioni di query e parametri: l'equivalenza deve valere in tutte.
    for query in ([1.0, 0.0, 0.0], [0.6, 0.8, 0.0], [0.0, 1.0, 0.0]):
        for max_per_file in (0, 1, 2):
            on_the_fly = retrieval.search_code_symbols(
                np.array(query), store, max_snippets=4, min_score=0.0, max_per_file=max_per_file)
            precomputed = retrieval.search_code_symbols(
                np.array(query), store, max_snippets=4, min_score=0.0, max_per_file=max_per_file,
                code_ids=code_ids, code_matrix=code_matrix)
            assert [c["symbol_id"] for c in precomputed] == [c["symbol_id"] for c in on_the_fly]
            assert ([round(c["score"], 6) for c in precomputed]
                    == [round(c["score"], 6) for c in on_the_fly])
            assert precomputed == on_the_fly  # identità piena delle voci, non solo id/score


def test_prep_code_matrix_empty_returns_none():
    """Store vuoto o senza alcun simbolo con vettore denso: ([], None) — così lo snapshot
    porta code_matrix=None e search_code_symbols ricade sul path on-the-fly (che ritorna [])."""
    from api import deps

    assert deps._prep_code_matrix({}) == ([], None)
    no_dense = {"code/x.cs::X": {"name": "X", "file": "x.cs", "text": "class X"}}
    assert deps._prep_code_matrix(no_dense) == ([], None)


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


# ---------------------------------------------------------------------------
# S4 (ADR 0002) — SUPERA_IN_PRIORITÀ: precedenza esplicita fra fonti
# ---------------------------------------------------------------------------
_REL = "SUPERA_IN_PRIORITÀ"


def _res(*doc_ids: str) -> list[dict]:
    """Risultati finti nell'ordine dato: un chunk per elemento (doc ripetuto = più chunk)."""
    out = []
    for i, d in enumerate(doc_ids):
        out.append({"chunk_id": f"{d}#{i:02d}", "doc_id": d, "colbert_score": 1.0 - i * 0.01})
    return out


def _grafo_prec(*coppie: tuple[str, str]) -> nx.DiGraph:
    g = nx.DiGraph()
    for a, b in coppie:
        g.add_node(a, type="document")
        g.add_node(b, type="document")
        g.add_edge(a, b, relation=_REL, nature="curated", reliability=0.9)
    return g


def _docs(results: list[dict]) -> list[str]:
    return [r["doc_id"] for r in results]


def test_precedenza_promuove_il_documento_prevalente():
    """B primo per punteggio, A terzo, con A SUPERA_IN_PRIORITÀ B: dopo il riordino A precede B."""
    results = _res("B.md", "X.md", "A.md")
    out = retrieval.apply_precedence(results, graph=_grafo_prec(("A.md", "B.md")), relation=_REL)
    assert _docs(out).index("A.md") < _docs(out).index("B.md")


def test_precedenza_preserva_ordine_relativo_degli_altri():
    """I documenti non coinvolti mantengono le loro posizioni relative, e il subordinato scende
    del MINIMO necessario. È la proprietà di stabilità: un sort a chiave composita metterebbe
    B in fondo, scavalcato anche da Y che con quella precedenza non c'entra nulla."""
    results = _res("B.md", "X.md", "A.md", "Y.md")
    out = _docs(retrieval.apply_precedence(
        results, graph=_grafo_prec(("A.md", "B.md")), relation=_REL))
    assert out == ["X.md", "A.md", "B.md", "Y.md"]
    # X prima di Y come all'origine, e B NON è finito oltre Y
    assert out.index("X.md") < out.index("Y.md")
    assert out.index("B.md") < out.index("Y.md")


def test_precedenza_su_vincoli_disgiunti_non_rimescola():
    """Due precedenze indipendenti: ciascun subordinato scende solo sotto il proprio
    prevalente, senza essere spinto in coda insieme all'altro."""
    results = _res("B.md", "D.md", "X.md", "A.md", "C.md")
    out = _docs(retrieval.apply_precedence(
        results, graph=_grafo_prec(("A.md", "B.md"), ("C.md", "D.md")), relation=_REL))
    assert out == ["X.md", "A.md", "B.md", "C.md", "D.md"]


def test_nessuna_precedenza_lascia_invariato():
    """Senza archi di precedenza la lista torna IDENTICA — stesso oggetto, nessuna copia:
    il caso comune (la quasi totalità delle richieste) non paga nulla."""
    results = _res("A.md", "B.md", "C.md")
    g = nx.DiGraph()
    g.add_node("A.md", type="document")
    g.add_node("B.md", type="document")
    g.add_edge("A.md", "B.md", relation="EREDITA_VINCOLI")   # relazione diversa: non è precedenza
    out = retrieval.apply_precedence(results, graph=g, relation=_REL)
    assert out is results
    assert _docs(out) == ["A.md", "B.md", "C.md"]


def test_precedenza_non_e_transitiva():
    """A > B e B > C nel grafo, ma B NON è fra i risultati: nessun arco diretto lega A e C,
    quindi il loro ordine relativo non viene forzato. Non calcoliamo la chiusura transitiva —
    in un corpus governato da umani, se serve A > C lo scrive l'autore.
    (Se invece B fosse presente, A precederebbe C per COMPOSIZIONE dei due archi diretti:
    è una conseguenza dei vincoli dichiarati, non una precedenza inferita da noi.)"""
    results = _res("C.md", "A.md")
    out = _docs(retrieval.apply_precedence(
        results, graph=_grafo_prec(("A.md", "B.md"), ("B.md", "C.md")), relation=_REL))
    assert out == ["C.md", "A.md"]


def test_ciclo_di_precedenza_non_blocca_e_logga(caplog):
    """A > B e B > A è un corpus malformato: la funzione ritorna (nessun loop, nessuna
    eccezione dentro una richiesta), l'ordine di quella coppia resta invariato, e viene
    emesso un warning che nomina i documenti."""
    results = _res("A.md", "B.md")
    grafo = _grafo_prec(("A.md", "B.md"), ("B.md", "A.md"))
    with caplog.at_level(logging.WARNING, logger="core.retrieval"):
        out = retrieval.apply_precedence(results, graph=grafo, relation=_REL)
    assert _docs(out) == ["A.md", "B.md"]
    assert "CICLICA" in caplog.text
    assert "A.md" in caplog.text and "B.md" in caplog.text


def test_grafo_assente_e_no_op():
    results = _res("A.md", "B.md")
    assert retrieval.apply_precedence(results, graph=None, relation=_REL) is results


def test_precedenza_su_chunk_multipli_dello_stesso_documento():
    """Il retrieval lavora su CHUNK, la precedenza è dichiarata fra DOCUMENTI: nessun chunk
    di B può precedere il PRIMO chunk di A, e i chunk di uno stesso documento non si
    rimescolano fra loro."""
    results = _res("B.md", "B.md", "A.md", "B.md", "A.md")
    chunk_b = [r["chunk_id"] for r in results if r["doc_id"] == "B.md"]
    out = retrieval.apply_precedence(
        results, graph=_grafo_prec(("A.md", "B.md")), relation=_REL)
    docs = _docs(out)
    assert docs == ["A.md", "A.md", "B.md", "B.md", "B.md"]
    primo_a = docs.index("A.md")
    assert all(i > primo_a for i, d in enumerate(docs) if d == "B.md")
    # ordine relativo dei chunk di B preservato (permutazione stabile, non rimescolamento)
    assert [r["chunk_id"] for r in out if r["doc_id"] == "B.md"] == chunk_b


def test_precedenza_non_riavvicina_i_chunk_estranei_intercalati():
    """Contratto esplicito: si raggruppano solo i documenti che sono estremi di una
    precedenza. I chunk di un documento estraneo restano nell'ordine in cui sono
    arrivati, anche se intercalati con altri estranei. Accorparli per documento
    cambierebbe chi può entrare nel top-k senza che quel documento sia nel vincolo.

    Ingresso B1, X1, A1, Y1, X2 con la sola relazione A > B.
    """
    results = [
        {"chunk_id": "B1", "doc_id": "B.md"},
        {"chunk_id": "X1", "doc_id": "X.md"},
        {"chunk_id": "A1", "doc_id": "A.md"},
        {"chunk_id": "Y1", "doc_id": "Y.md"},
        {"chunk_id": "X2", "doc_id": "X.md"},
    ]
    out = retrieval.apply_precedence(
        results, graph=_grafo_prec(("A.md", "B.md")), relation=_REL)
    assert [r["chunk_id"] for r in out] == ["X1", "A1", "B1", "Y1", "X2"]


def test_regola_precedenza_assente_dal_prompt_senza_conflitto():
    """Una regola inerte insegna al modello a ignorarla: [PRECEDENZA-FONTI] non compare
    quando nessuna precedenza si applica."""
    assert "[PRECEDENZA-FONTI]" not in retrieval.build_ask_prompt("contesto", "domanda")
    assert "[PRECEDENZA-FONTI]" not in retrieval.build_ask_prompt(
        "contesto", "domanda", precedences=[])


def test_regola_precedenza_nomina_i_documenti():
    prompt = retrieval.build_ask_prompt(
        "contesto", "domanda", precedences=[("safeguards.md", "note.md")])
    assert "[PRECEDENZA-FONTI]" in prompt
    assert "safeguards.md" in prompt and "note.md" in prompt


def test_precedence_pairs_solo_archi_diretti_fra_documenti_presenti():
    """Le coppie riportate sono solo quelle DIRETTE fra documenti entrambi presenti nei
    risultati: è lo stesso fatto che riordina il ranking e che viene dichiarato nel prompt."""
    grafo = _grafo_prec(("A.md", "B.md"), ("A.md", "assente.md"))
    coppie = retrieval.precedence_pairs(_res("A.md", "B.md"), graph=grafo, relation=_REL)
    assert coppie == [("A.md", "B.md")]


# ---------------------------------------------------------------------------
# S3 (miglioria) — quale SEZIONE di un documento raggiunto via grafo mostrare
# ---------------------------------------------------------------------------
def _cq(*v) -> np.ndarray:
    """Vettore ColBERT di query con un solo token."""
    return np.array([list(v)], dtype="float32")


def test_maxsim_none_senza_vettori():
    """Una sezione senza vettori non è "poco pertinente": è NON GIUDICABILE."""
    assert retrieval.colbert_maxsim(_cq(1, 0), None) is None


def test_sezioni_ordinate_per_pertinenza_non_per_ordine_di_file():
    """È il difetto che questa funzione corregge: con l'ordine di documento si iniettava
    il preambolo, che sta in cima al file e non risponde quasi mai alla domanda."""
    store = {
        "doc.md#00-preambolo": np.array([[0.0, 1.0]], dtype="float32"),
        "doc.md#01-termini":   np.array([[1.0, 0.0]], dtype="float32"),
    }
    out = retrieval.rank_sections_by_relevance(
        ["doc.md#00-preambolo", "doc.md#01-termini"],
        colbert_store=store, colbert_query=_cq(1, 0))
    assert [cid for cid, _ in out] == ["doc.md#01-termini", "doc.md#00-preambolo"]
    assert out[0][1] == 1.0


def test_pavimento_scarta_solo_le_sezioni_valutate():
    store = {
        "doc.md#00": np.array([[1.0, 0.0]], dtype="float32"),   # 1.0
        "doc.md#01": np.array([[0.0, 1.0]], dtype="float32"),   # 0.0
    }
    out = retrieval.rank_sections_by_relevance(
        ["doc.md#00", "doc.md#01"], colbert_store=store, colbert_query=_cq(1, 0),
        min_score=0.5)
    assert [cid for cid, _ in out] == ["doc.md#00"]


def test_sezioni_non_giudicabili_in_coda_mai_scartate():
    """Senza sidecar ColBERT (o con sidecar disallineato) non possiamo giudicare: quelle
    sezioni restano, in coda e nell'ordine ricevuto — il comportamento di prima."""
    store = {"doc.md#01": np.array([[1.0, 0.0]], dtype="float32")}
    out = retrieval.rank_sections_by_relevance(
        ["doc.md#00", "doc.md#01", "doc.md#02"],
        colbert_store=store, colbert_query=_cq(1, 0), min_score=0.9)
    assert [cid for cid, _ in out] == ["doc.md#01", "doc.md#00", "doc.md#02"]
    assert out[1][1] is None and out[2][1] is None
    # store vuoto: nessuna sezione perduta, ordine invariato
    tutte = retrieval.rank_sections_by_relevance(
        ["a", "b"], colbert_store={}, colbert_query=_cq(1, 0), min_score=0.9)
    assert [cid for cid, _ in tutte] == ["a", "b"]


# ---------------------------------------------------------------------------
# N4 — peso di SEZIONE: chi RIFORMULA una regola non è chi la STABILISCE
# ---------------------------------------------------------------------------
_STABILISCE = """## 2. Log Strutturati e Correlazione

### `[REGOLA-OBS-03]` Correlazione end-to-end

Ogni richiesta in ingresso riceve un `correlationId` che accompagna ogni log e record di audit.
"""

_RIFORMULA = """## 6. Riepilogo delle Regole

| ID | Vincolo operativo core |
|---|---|
| `[REGOLA-OBS-03]` | `correlationId` propagato su log, tracing, code e audit. |
| `[REGOLA-OBS-06]` | Sanitizer PII nel logger, non nei call site. |
"""

_NESSUN_CODICE = """## Premessa

Questo documento descrive le convenzioni di osservabilità del progetto.
"""


def test_riformula_solo_chi_cita_senza_dichiarare():
    """Il segnale è il codice DICHIARATO in un titolo, non una parola nel titolo: una sezione
    senza codici non è una riformulazione, e non va confusa con chi ne cita e basta."""
    assert retrieval.restates_only(_RIFORMULA) is True
    assert retrieval.restates_only(_STABILISCE) is False
    assert retrieval.restates_only(_NESSUN_CODICE) is False


def test_restatement_sections_legge_il_sidecar_dei_chunk():
    chunks = {"doc.md#02": {"text": _STABILISCE}, "doc.md#06": {"text": _RIFORMULA},
              "doc.md#00": {"text": _NESSUN_CODICE}, "doc.md#99": {}}
    assert retrieval.restatement_sections(chunks) == frozenset({"doc.md#06"})


def _sez(chunk_id, colbert, authority=0.85):
    return {"chunk_id": chunk_id, "doc_id": "doc.md", "colbert_score": colbert,
            "authority": authority, "fused_rank_sum": 2}


def test_il_riepilogo_non_batte_piu_la_sezione_che_stabilisce_la_regola():
    """A3 §4-5: fra sezioni SORELLE il peso di autorità è identico e il moltiplicatore si
    semplifica, quindi nessun alpha può separarle — e il MaxSim premia la riformulazione, che
    ripete le stesse parole più densamente. Il peso di sezione è ciò che le separa.

    Il vantaggio lessicale è del 3%: la penalità calibrata (0.92) lo ribalta. Uno molto più
    grande vincerebbe comunque, ed è voluto — è una modulazione, non un veto."""
    risultati = [_sez("doc.md#06", 0.500), _sez("doc.md#02", 0.485)]
    retrieval.rank_by_authority(risultati, restatements={"doc.md#06"})
    assert [r["chunk_id"] for r in risultati] == ["doc.md#02", "doc.md#06"]


def test_senza_restatements_il_ranking_e_identico_a_prima():
    """Il parametro è additivo: chi chiama rank_by_authority senza il sidecar dei chunk
    (test storici, consumatori esterni) ottiene esattamente l'ordinamento di prima di N4."""
    risultati = [_sez("doc.md#06", 0.500), _sez("doc.md#02", 0.485)]
    retrieval.rank_by_authority(risultati)
    assert [r["chunk_id"] for r in risultati] == ["doc.md#06", "doc.md#02"]


def test_il_peso_di_sezione_non_ribalta_un_divario_di_rilevanza_vero():
    """Il costo dichiarato in rag_config: `definition_of_done § Checklist` cita e non dichiara,
    ma lì la checklist È la norma. La penalità è mite apposta — rompe i pareggi fra sorelle,
    non ribalta un candidato che vince davvero."""
    risultati = [_sez("dod.md#03", 0.600), _sez("altro.md#01", 0.500)]
    retrieval.rank_by_authority(risultati, restatements={"dod.md#03"})
    assert [r["chunk_id"] for r in risultati] == ["dod.md#03", "altro.md#01"]


def test_il_peso_di_sezione_vale_anche_per_i_chunk_senza_colbert():
    """Ramo dei non giudicabili (A7): ordinato per fused_rank_sum / moltiplicatore, quindi la
    penalità deve alzare il quoziente e farli scendere, non l'opposto. Un fattore applicato a
    metà dei due insiemi sarebbe la stessa incoerenza fra rami che A7 ha appena chiuso."""
    a = {"chunk_id": "doc.md#06", "doc_id": "doc.md", "colbert_score": None,
         "authority": 0.85, "fused_rank_sum": 10}
    b = {"chunk_id": "doc.md#02", "doc_id": "doc.md", "colbert_score": None,
         "authority": 0.85, "fused_rank_sum": 10.5}
    risultati = [a, b]
    retrieval.rank_by_authority(risultati, restatements={"doc.md#06"})
    assert [r["chunk_id"] for r in risultati] == ["doc.md#02", "doc.md#06"]

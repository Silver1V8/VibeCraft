"""Guardrail sulla configurazione dei pesi di autorità e sull'ordinamento parametrizzato
(Epic 3). Protegge da una futura (ri)calibrazione che produca pesi assurdi o rompa la
monotonia sensata IRON_MEMORY >= AUTHORIZATION_POLICY >= DATA_DICTIONARY >= METHODOLOGY."""
import networkx as nx

from core import retrieval
from eval import calibrate_authority as calibrate
from core.config import (
    AUTHORITY_BOOST_ALPHA,
    AUTHORITY_CLASS_WEIGHTS,
    AUTHORITY_DEFAULT_WEIGHT,
)


def test_class_weights_in_range_and_monotone():
    for cls, w in AUTHORITY_CLASS_WEIGHTS.items():
        assert 0.0 <= w <= 1.0, f"peso fuori range per {cls}: {w}"
    order = ["IRON_MEMORY", "AUTHORIZATION_POLICY", "DATA_DICTIONARY", "METHODOLOGY"]
    vals = [AUTHORITY_CLASS_WEIGHTS[c] for c in order if c in AUTHORITY_CLASS_WEIGHTS]
    assert vals == sorted(vals, reverse=True), f"ordine di autorità non monotono: {vals}"
    assert 0.0 <= AUTHORITY_DEFAULT_WEIGHT <= 1.0
    assert 0.0 <= AUTHORITY_BOOST_ALPHA <= 1.0


def test_authority_weight_archived_decay():
    active = retrieval._authority_weight({"classification": "IRON_MEMORY", "status": "ENFORCED"})
    archived = retrieval._authority_weight({"classification": "IRON_MEMORY", "status": "ARCHIVED"})
    assert archived < active                       # l'archiviato pesa meno dell'attivo
    # parametri iniettabili: il calibratore varia default/decay senza toccare il codice
    assert retrieval._authority_weight({"classification": "X"}, default=0.9) == 0.9


def test_rank_by_authority_alpha_zero_is_pure_relevance():
    """alpha=0 → l'autorità è ignorata: vince la rilevanza pura (ColBERT più alto), anche se
    l'altro candidato ha autorità massima."""
    low_rel_high_auth = {"colbert_score": 0.30, "authority": 1.0, "fused_rank_sum": 2, "id": "A"}
    high_rel_low_auth = {"colbert_score": 0.90, "authority": 0.1, "fused_rank_sum": 2, "id": "B"}
    out = retrieval.rank_by_authority([low_rel_high_auth, high_rel_low_auth], alpha=0.0)
    assert out[0]["id"] == "B"                      # senza autorità vince la rilevanza
    # con boost forte, l'autorità può ribaltare a parità/vicinanza di rilevanza
    a = {"colbert_score": 0.50, "authority": 1.0, "fused_rank_sum": 2, "id": "A"}
    b = {"colbert_score": 0.55, "authority": 0.1, "fused_rank_sum": 2, "id": "B"}
    assert retrieval.rank_by_authority([a, b], alpha=1.0)[0]["id"] == "A"


# ---------------------------------------------------------------------------
# Fedeltà del calibratore al ranking di PRODUZIONE (ADR 0002 / S1 + S4)
# ---------------------------------------------------------------------------
def _cand(chunk_id, doc_id, colbert, classification="", status=""):
    return {"chunk_id": chunk_id, "doc_id": doc_id, "colbert_score": colbert,
            "fused_rank_sum": 2, "classification": classification, "status": status}


def test_calibratore_onora_authority_dichiarata_come_la_produzione():
    """Il calibratore leggeva solo classification/status, quindi appiattiva sul default_weight
    ogni documento che dichiara `authority:` nel frontmatter — cioè la maggioranza del corpus.
    Ora legge gli attributi dal nodo del grafo, come la produzione legge il payload Qdrant."""
    g = nx.DiGraph()
    g.add_node("spec.md", type="document", classification="REQUIREMENTS", authority=0.87)
    g.add_node("spec.md#00", type="section", classification="REQUIREMENTS", authority=0.87)

    cands = [_cand("spec.md#00", "spec.md", 0.9, classification="REQUIREMENTS")]
    fn = calibrate.make_retrieve_fn({"q": cands}, alpha=0.5, default_weight=0.4, graph=g)
    peso = fn("q", 5)[0]["authority"]

    # il valore dichiarato vince sul default_weight della griglia, esattamente come in produzione
    assert peso == 0.87
    assert peso == round(retrieval._authority_weight(g.nodes["spec.md#00"], default=0.4), 3)


def test_calibratore_senza_authority_dichiarata_usa_il_default_della_griglia():
    """L'asse `default_weight` resta vivo dove deve: sulle fonti che non dichiarano nulla."""
    g = nx.DiGraph()
    g.add_node("nota.md", type="document", classification="REQUIREMENTS")
    g.add_node("nota.md#00", type="section", classification="REQUIREMENTS")
    fn = calibrate.make_retrieve_fn({"q": [_cand("nota.md#00", "nota.md", 0.9)]},
                                    alpha=0.5, default_weight=0.42, graph=g)
    assert fn("q", 5)[0]["authority"] == 0.42


def test_calibratore_applica_la_precedenza_fra_fonti():
    """apply_precedence è l'ultimo stadio in produzione: se il calibratore non lo applica,
    valuta un ordine che il retrieval reale non serve mai."""
    g = nx.DiGraph()
    for n in ("prevalente.md", "subordinato.md"):
        g.add_node(n, type="document", classification="REQUIREMENTS")
        g.add_node(f"{n}#00", type="section", classification="REQUIREMENTS")
    g.add_edge("prevalente.md", "subordinato.md", relation="SUPERA_IN_PRIORITÀ",
               nature="curated", reliability=0.9)

    # il subordinato è nettamente più rilevante: senza precedenza vincerebbe
    cands = [_cand("subordinato.md#00", "subordinato.md", 0.95),
             _cand("prevalente.md#00", "prevalente.md", 0.30)]
    senza = calibrate.make_retrieve_fn({"q": cands}, alpha=0.1, default_weight=0.7,
                                       graph=None)("q", 5)
    assert senza[0]["doc_id"] == "subordinato.md"

    con = calibrate.make_retrieve_fn({"q": cands}, alpha=0.1, default_weight=0.7,
                                     graph=g)("q", 5)
    assert con[0]["doc_id"] == "prevalente.md"


def test_attrs_for_degrada_sul_candidato_se_il_nodo_manca():
    """Un chunk di un documento non presente nel grafo non deve far fallire la calibrazione:
    si ricade sui campi grezzi già in cache."""
    attrs = calibrate._attrs_for(_cand("ignoto.md#00", "ignoto.md", 0.5,
                                       classification="METHODOLOGY", status="ARCHIVED"),
                                 nx.DiGraph())
    assert attrs == {"classification": "METHODOLOGY", "status": "ARCHIVED"}
    assert calibrate._attrs_for(_cand("x#00", "x", 0.5), None) == {"classification": "", "status": ""}

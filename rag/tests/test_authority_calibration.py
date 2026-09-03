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
# A7 — il ramo MISTO: chunk senza vettore ColBERT accanto a chunk che ce l'hanno.
#
# `hybrid_search` tollera esplicitamente `colbert_score=None` (sidecar legacy o
# disallineato rispetto a Qdrant). Prima quei chunk venivano ordinati con un punteggio
# finto di -1.0 MOLTIPLICATO per l'autorità: più autorevole la fonte, più negativo il
# prodotto, più scendeva. L'inversione colpiva le fonti normative, in silenzio, e solo
# quando la copertura ColBERT era parziale — cioè mai, finché è piena.
# ---------------------------------------------------------------------------
def _senza_vettore(id_, authority, fused=2):
    return {"colbert_score": None, "authority": authority, "fused_rank_sum": fused, "id": id_}


def test_senza_vettore_in_coda_e_senza_inversione_dell_autorita():
    """IL test di A7, e serve un candidato giudicabile perché il difetto si manifesti: senza,
    `any(colbert_score is not None)` è falso e si imboccava il ramo di fusione, che era già
    corretto. Con un giudicabile in lista la vecchia regola usciva
    ['debole', 'senza-bassa', 'senza-alta'] — la coda invertita, la fonte più autorevole per
    ultima.

    Non giudicabile non vuol dire "ultimo per punizione": vuol dire che il MaxSim su quel
    chunk non si può calcolare. Sta in coda, ma ORDINATO, e nel verso giusto."""
    giudicabile = {"colbert_score": 0.05, "authority": 0.1, "fused_rank_sum": 99, "id": "debole"}
    out = retrieval.rank_by_authority(
        [_senza_vettore("senza-alta", 1.0), giudicabile, _senza_vettore("senza-bassa", 0.1)],
        alpha=0.1)
    assert [r["id"] for r in out] == ["debole", "senza-alta", "senza-bassa"]


def test_il_posto_di_un_non_giudicabile_non_dipende_dagli_altri():
    """L'incoerenza nascosta fra i due rami di prima: gli stessi due chunk senza vettore
    uscivano in un ordine quando erano soli (fusione / autorità) e nell'ordine INVERSO
    appena un terzo chunk qualsiasi portava un vettore ColBERT."""
    soli = retrieval.rank_by_authority(
        [_senza_vettore("A", 0.1), _senza_vettore("B", 1.0)], alpha=0.1)
    misti = retrieval.rank_by_authority(
        [_senza_vettore("A", 0.1),
         {"colbert_score": 0.7, "authority": 0.5, "fused_rank_sum": 1, "id": "C"},
         _senza_vettore("B", 1.0)], alpha=0.1)
    assert [r["id"] for r in soli] == ["B", "A"]
    assert [r["id"] for r in misti if r["id"] != "C"] == ["B", "A"]


def test_copertura_piena_ordina_come_prima():
    """Il percorso di PRODUZIONE (copertura ColBERT 100%) non deve cambiare di una posizione:
    la correzione riguarda solo l'insieme che prima non esisteva come insieme."""
    cands = [{"colbert_score": 0.40, "authority": 1.0, "fused_rank_sum": 3, "id": "medio-alto"},
             {"colbert_score": 0.80, "authority": 0.3, "fused_rank_sum": 2, "id": "forte"},
             {"colbert_score": 0.10, "authority": 1.0, "fused_rank_sum": 5, "id": "debole"}]
    out = retrieval.rank_by_authority(cands, alpha=0.1)
    assert [r["id"] for r in out] == ["forte", "medio-alto", "debole"]


def test_autorita_zero_ad_alpha_uno_non_divide_per_zero():
    """Ad alpha=1 il moltiplicatore È l'autorità: una fonte che dichiara `authority: 0.0`
    azzerava il divisore del ramo di fusione. Il pavimento la manda in fondo — la direzione
    giusta — invece di far esplodere il retrieval."""
    out = retrieval.rank_by_authority(
        [_senza_vettore("azzerata", 0.0, fused=1), _senza_vettore("normale", 0.8, fused=4)],
        alpha=1.0)
    assert [r["id"] for r in out] == ["normale", "azzerata"]


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
    fn = calibrate.make_retrieve_fn({"q": cands}, alpha=0.5, default_weight=0.4,
                                    unclassified_weight=0.3, graph=g)
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
                                    alpha=0.5, default_weight=0.42,
                                    unclassified_weight=0.3, graph=g)
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
                                       unclassified_weight=0.3, graph=None)("q", 5)
    assert senza[0]["doc_id"] == "subordinato.md"

    con = calibrate.make_retrieve_fn({"q": cands}, alpha=0.1, default_weight=0.7,
                                     unclassified_weight=0.3, graph=g)("q", 5)
    assert con[0]["doc_id"] == "prevalente.md"


def test_attrs_for_degrada_sul_candidato_se_il_nodo_manca():
    """Un chunk di un documento non presente nel grafo non deve far fallire la calibrazione:
    si ricade sui campi grezzi già in cache."""
    attrs = calibrate._attrs_for(_cand("ignoto.md#00", "ignoto.md", 0.5,
                                       classification="METHODOLOGY", status="ARCHIVED"),
                                 nx.DiGraph())
    assert attrs == {"classification": "METHODOLOGY", "status": "ARCHIVED"}
    assert calibrate._attrs_for(_cand("x#00", "x", 0.5), None) == {"classification": "", "status": ""}


def test_calibratore_cerca_anche_sul_peso_della_fonte_non_classificata():
    """Terzo asse della griglia (S5, ADR 0002). `unclassified_weight` è il parametro che S1
    ha separato da `default_weight`: lasciarlo fuori dalla ricerca significherebbe calibrare
    due terzi del meccanismo e tenere fisso il terzo che governa, in questo corpus, i sei
    file senza frontmatter di docs/03_changes_historical/.

    Il test verifica che l'asse abbia PRESA — che il valore passato dalla griglia arrivi
    davvero al peso — e che non si confonda con default_weight, che vale per un'altra cosa."""
    g = nx.DiGraph()
    # nessuna `classification`: è la fonte non classificata (un import senza frontmatter)
    g.add_node("importato.md", type="document")
    g.add_node("importato.md#00", type="section")

    fn = calibrate.make_retrieve_fn({"q": [_cand("importato.md#00", "importato.md", 0.9)]},
                                    alpha=0.5, default_weight=0.7,
                                    unclassified_weight=0.15, graph=g)
    # 0.15 (unclassified), NON 0.7 (default_weight): sono due casi diversi, non due nomi
    # per la stessa cosa — la conflazione è il difetto D2 dell'ADR 0002.
    assert fn("q", 5)[0]["authority"] == 0.15

    # E l'asse dev'essere una ricerca vera: un solo valore in griglia non è calibrazione,
    # ed è la condizione in cui il parametro si trovava prima di S5.
    assert len(set(calibrate.UNCLASSIFIED_WEIGHTS)) > 1
    from core.config import AUTHORITY_UNCLASSIFIED_WEIGHT
    assert AUTHORITY_UNCLASSIFIED_WEIGHT in calibrate.UNCLASSIFIED_WEIGHTS, (
        "il valore in produzione deve stare nella griglia, altrimenti il confronto "
        "'attuale vs calibrato' non è nella ricerca")


def test_grid_best_a_parita_di_recall_tiene_la_configurazione_di_produzione():
    """Un pareggio non è un miglioramento: se nessun punto della griglia batte la
    configurazione attuale, la calibrazione deve proporre di NON toccare nulla.

    Non è estetica. Su questo corpus due assi su tre sono morti (vedi assi_morti), quindi
    ogni alpha ha 30 configurazioni identiche: sciogliere il pareggio per ordine di
    iterazione fa scegliere al caso, e dentro la k-fold quella scelta cambia da fold a fold
    e finisce nella stima held-out come rumore. Misurato: senza questo tie-break il guadagno
    a k=2 è passato da -0.011 a +0.013 fra due corse che differivano per la sola
    ri-segmentazione di UN documento su 26."""
    from core.config import (AUTHORITY_BOOST_ALPHA, AUTHORITY_DEFAULT_WEIGHT,
                             AUTHORITY_UNCLASSIFIED_WEIGHT)
    attuale = (AUTHORITY_BOOST_ALPHA, AUTHORITY_DEFAULT_WEIGHT, AUTHORITY_UNCLASSIFIED_WEIGHT)

    # tutta la griglia pareggia: deve vincere l'incumbent, non il primo punto iterato
    piatta = {(a, dw, uw): 0.5 for a in calibrate.ALPHAS
              for dw in calibrate.DEFAULT_WEIGHTS for uw in calibrate.UNCLASSIFIED_WEIGHTS}
    recall, *scelta = calibrate.grid_best(None, None, k=1, graph=None, tabella=piatta)
    assert tuple(scelta) == attuale and recall == 0.5

    # un punto STRETTAMENTE migliore lo scalza: il tie-break non congela la calibrazione
    migliore = (1.0, 0.4, 0.1)
    piatta[migliore] = 0.6
    recall, *scelta = calibrate.grid_best(None, None, k=1, graph=None, tabella=piatta)
    assert tuple(scelta) == migliore and recall == 0.6


def test_assi_morti_riconosce_un_parametro_che_non_muove_nulla():
    """Un asse che non cambia la recall non è un parametro da calibrare: è una coordinata
    che la ricerca ottimizza a vuoto, e il report deve dirlo invece di lasciar credere che
    il valore 'vincente' su quell'asse significhi qualcosa."""
    # recall dipendente dal solo alpha: gli altri due assi sono morti per costruzione
    tabella = {(a, dw, uw): a for a in calibrate.ALPHAS
               for dw in calibrate.DEFAULT_WEIGHTS for uw in calibrate.UNCLASSIFIED_WEIGHTS}
    assert calibrate.assi_morti(tabella) == ["default_weight", "unclassified_weight"]

    # se anche unclassified_weight muove la metrica, resta morto solo default_weight
    tabella = {(a, dw, uw): a + uw for a in calibrate.ALPHAS
               for dw in calibrate.DEFAULT_WEIGHTS for uw in calibrate.UNCLASSIFIED_WEIGHTS}
    assert calibrate.assi_morti(tabella) == ["default_weight"]

    # griglia in cui tutti e tre contano: nessun asse morto
    tabella = {(a, dw, uw): a + dw + uw for a in calibrate.ALPHAS
               for dw in calibrate.DEFAULT_WEIGHTS for uw in calibrate.UNCLASSIFIED_WEIGHTS}
    assert calibrate.assi_morti(tabella) == []

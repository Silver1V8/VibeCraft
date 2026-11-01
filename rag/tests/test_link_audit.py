"""Audit degli IMPLEMENTS. I testi sono fixture: non sono un corpus normativo."""
import networkx as nx

from eval.link_audit import (
    MEASURED,
    NOT_MEASURED,
    annotator_cards,
    collect_implements,
    compute_metrics,
    draw_sample,
    validate_annotations,
)


def _graph():
    g = nx.DiGraph()
    specs = [
        ("TEST-FIXTURE/a.py::uno", 0.50, "TEST-FIXTURE/spec.md#00"),
        ("TEST-FIXTURE/a.py::due", 0.55, "TEST-FIXTURE/spec.md#01"),
        ("TEST-FIXTURE/b.py::tre", 0.70, "TEST-FIXTURE/spec.md#02"),
        ("TEST-FIXTURE/b.py::quattro", 0.72, "TEST-FIXTURE/spec.md#03"),
        ("TEST-FIXTURE/c.py::cinque", 0.80, "TEST-FIXTURE/spec.md#04"),
        ("TEST-FIXTURE/c.py::sei", 0.95, "TEST-FIXTURE/spec.md#05"),
    ]
    for sid, weight, target in specs:
        g.add_node(sid, type="code", kind="function", file=sid.split("::")[0])
        g.add_node(target, type="section")
        g.add_edge(sid, target, relation="IMPLEMENTS", nature="inferred", weight=weight, reliability=0.7)
    g.add_edge("TEST-FIXTURE/a.py::uno", "TEST-FIXTURE/ENTITA", relation="REFERENCES")
    return g


def _stores():
    code = {}
    chunks = {}
    for sid, weight, target in (
        ("TEST-FIXTURE/a.py::uno", 0.50, "TEST-FIXTURE/spec.md#00"),
        ("TEST-FIXTURE/a.py::due", 0.55, "TEST-FIXTURE/spec.md#01"),
    ):
        code[sid] = {
            "kind": "function", "file": sid.split("::")[0], "dev_type": "backend",
            "text": "TEST-FIXTURE codice",
            "best_score": weight, "second_score": weight - 0.1,
            "win_chunk_id": target, "win_doc_id": "TEST-FIXTURE/spec.md",
        }
        chunks[target] = {
            "doc_id": "TEST-FIXTURE/spec.md", "section": "passo",
            "text": "TEST-FIXTURE il sistema deve rifiutare un importo negativo",
        }
    return code, chunks


def test_raccoglie_solo_implements_e_non_inventa_il_margine():
    rows = collect_implements(_graph(), *_stores())
    assert len(rows) == 6
    assert all("TEST-FIXTURE" in r["symbol_id"] for r in rows)
    known = next(r for r in rows if r["symbol_id"].endswith("uno"))
    assert known["margin"] == 0.1
    assert known["second_score"] == 0.4
    unknown = next(r for r in rows if r["symbol_id"].endswith("sei"))
    assert unknown["best_score"] is None and unknown["margin"] is None


def test_schede_senza_punteggi_e_campione_stabile():
    rows = collect_implements(_graph(), *_stores())
    a = draw_sample(rows, n=6, seed=7)
    b = draw_sample(rows, n=6, seed=7)
    assert [r["edge_id"] for r in a["edges"]] == [r["edge_id"] for r in b["edges"]]
    assert a["status"] == NOT_MEASURED
    card = annotator_cards(a)[0]
    for hidden in ("weight", "reliability", "best_score", "second_score", "margin"):
        assert hidden not in card
    assert card["label"] == "" and card["annotator"] == ""


def test_legacy_senza_peso_resta_nel_campione():
    g = nx.DiGraph()
    g.add_node("TEST-FIXTURE/old.py::f", type="code")
    g.add_edge("TEST-FIXTURE/old.py::f", "TEST-FIXTURE/spec.md", relation="IMPLEMENTS")
    rows = collect_implements(g)
    assert rows[0]["weight"] is None
    assert rows[0]["nature"] is None
    assert rows[0]["stratum"].startswith("peso_assente|")
    sample = draw_sample(rows, n=1, seed=1)
    assert compute_metrics(sample, [])["status"] == NOT_MEASURED


def _filled(sample, labels):
    cards = annotator_cards(sample)
    for card, label in zip(cards, labels, strict=True):
        card["label"] = label
        card["motivation"] = "TEST-FIXTURE giudizio sul comportamento richiesto"
        card["annotator"] = "test-fixture"
    return cards


def test_precisione_stretta_esclude_i_non_valutabili():
    rows = collect_implements(_graph(), *_stores())
    sample = draw_sample(rows, n=6, seed=1)
    labels = ["IMPLEMENTA", "IMPLEMENTA", "CORRELATO", "ERRATO", "NON_VALUTABILE", "NON_VALUTABILE"]
    report = compute_metrics(sample, _filled(sample, labels))
    assert report["status"] == MEASURED
    assert report["strict_precision"] == 0.5
    assert report["non_evaluable_share"] == round(2 / 6, 4)
    assert report["recall"] is None
    assert report["counts"]["IMPLEMENTA"] == 2


def test_disaccordo_e_punteggi_nel_giudizio_bloccano_la_misura():
    rows = collect_implements(_graph(), *_stores())
    sample = draw_sample(rows, n=6, seed=1)
    cards = _filled(sample, ["IMPLEMENTA"] * 6)
    other = dict(cards[0])
    other["annotator"] = "altro-test"
    other["label"] = "ERRATO"
    blocked = compute_metrics(sample, cards + [other])
    assert blocked["status"] == NOT_MEASURED
    leaked = dict(cards[0])
    leaked["weight"] = 0.99
    check = validate_annotations(sample, [leaked])
    assert check["errors"] and check["errors"][0]["error"] == "punteggi presenti nel giudizio"


def _synthetic_sample(strata):
    """Sigillo costruito a mano: {strato: (N_h, n_h)}. Archi TEST-FIXTURE."""
    edges, info = [], []
    for name, (N_h, n_h) in strata.items():
        info.append({"stratum": name, "N_h": N_h, "n_h": n_h, "pi_h": round(n_h / N_h, 6)})
        edges += [{"edge_id": f"{name}-{i}", "stratum": name} for i in range(n_h)]
    return {"status": NOT_MEASURED, "strata": info, "edges": edges}


def _cards(sample, label_of):
    return [{"edge_id": e["edge_id"], "label": label_of(e),
             "motivation": "TEST-FIXTURE giudizio sul comportamento richiesto",
             "annotator": "test-fixture"} for e in sample["edges"]]


def test_le_schede_non_mostrano_la_fascia_del_peso():
    sample = draw_sample(collect_implements(_graph(), *_stores()), n=6, seed=1)
    assert all("stratum" not in card for card in annotator_cards(sample))
    assert all("stratum" in row for row in sample["edges"])


def test_aggregato_rinormalizza_gli_strati_senza_schede_valutabili():
    # A: tutto NON_VALUTABILE; B: tutto IMPLEMENTA. Prima usciva 0.5, non 1.0.
    sample = _synthetic_sample({"A": (100, 5), "B": (100, 5)})
    report = compute_metrics(sample, _cards(
        sample, lambda e: "NON_VALUTABILE" if e["stratum"] == "A" else "IMPLEMENTA"))
    assert report["aggregate_precision"] == 1.0
    assert report["aggregate_population_covered"] == 0.5


def test_uno_strato_censito_non_annulla_l_intervallo():
    # C ha un solo arco, preso: nessuna varianza. Prima l'intervallo diventava None.
    sample = _synthetic_sample({"C": (1, 1), "D": (50, 10)})
    flip = iter(range(100))
    report = compute_metrics(sample, _cards(
        sample, lambda e: "IMPLEMENTA" if next(flip) % 2 else "ERRATO"))
    assert report["aggregate_interval95"] is not None
    low, high = report["aggregate_interval95"]
    assert low <= report["aggregate_precision"] <= high


def test_due_schede_per_strato_quando_n_basta():
    from eval.link_audit import _allocate
    sizes = {"grande": 500, "medio": 20, "piccolo": 3, "unico": 1}
    quota, _ = _allocate(sizes, 12)
    assert sum(quota.values()) == 12
    assert quota["unico"] == 1 and all(quota[k] >= 2 for k in ("grande", "medio", "piccolo"))
    tight, _ = _allocate(sizes, 5)  # non basta per due: una a testa
    assert sum(tight.values()) == 5 and all(v >= 1 for v in tight.values())

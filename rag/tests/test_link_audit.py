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

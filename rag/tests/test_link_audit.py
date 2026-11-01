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
    assert report["sample_precision"] == 0.5
    assert report["sample_non_evaluable_share"] == 2 / 6
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


def test_strato_tutto_non_valutabile_resta_nella_popolazione():
    # A: tutto NON_VALUTABILE; B: tutto IMPLEMENTA. A dà zero ai due totali, non sparisce.
    sample = _synthetic_sample({"A": (100, 5), "B": (100, 5)})
    report = compute_metrics(sample, _cards(
        sample, lambda e: "NON_VALUTABILE" if e["stratum"] == "A" else "IMPLEMENTA"))
    assert report["population_precision"] == 1.0
    assert report["estimated_evaluable_total"] == 100
    assert report["weighted_non_evaluable_share"] == 0.5
    assert report["sampling_coverage"]["population"] == 200
    # A ha 0 valutabili nel campione, ma la popolazione può averne: il limite superiore non è 0.
    a = next(s for s in report["per_stratum"] if s["stratum"] == "A")
    assert a["evaluable_bounds"][0] == 0 and a["evaluable_bounds"][1] > 0


def test_uno_strato_censito_non_annulla_l_intervallo():
    # C ha un solo arco, preso: nessun errore di campionamento.
    sample = _synthetic_sample({"C": (1, 1), "D": (50, 10)})
    flip = iter(range(100))
    report = compute_metrics(sample, _cards(
        sample, lambda e: "IMPLEMENTA" if next(flip) % 2 else "ERRATO"))
    assert report["interval"]["bounds"] is not None
    assert report["interval"]["strata_with_sampling_error"] == 1
    low, high = report["interval"]["bounds"]
    assert 0 <= low <= report["population_precision"] <= high <= 1


def test_due_schede_per_strato_quando_n_basta():
    from eval.link_audit import _allocate
    sizes = {"grande": 500, "medio": 20, "piccolo": 3, "unico": 1}
    quota, _ = _allocate(sizes, 12)
    assert sum(quota.values()) == 12
    assert quota["unico"] == 1 and all(quota[k] >= 2 for k in ("grande", "medio", "piccolo"))
    tight, _ = _allocate(sizes, 5)  # non basta per due: una a testa
    assert sum(tight.values()) == 5 and all(v >= 1 for v in tight.values())


def _labelled_sample(strata):
    """{strato: (N_h, [etichette del campione])}: sigillo e schede TEST-FIXTURE."""
    sample = _synthetic_sample({k: (N, len(labels)) for k, (N, labels) in strata.items()})
    label_of = {f"{k}-{i}": lab for k, (_, labels) in strata.items() for i, lab in enumerate(labels)}
    return sample, _cards(sample, lambda e: label_of[e["edge_id"]])


def test_fixture_di_regressione_rapporto_combinato():
    # Fixture del rilievo, non una misura di VibeCraft. La media delle precisioni locali
    # pesata con N_h dava 0.65: (0.8 + 0.5) / 2.
    sample, cards = _labelled_sample({
        "S1": (100, ["IMPLEMENTA"] * 8 + ["CORRELATO"] * 2),
        "S2": (100, ["IMPLEMENTA"] + ["CORRELATO"] + ["NON_VALUTABILE"] * 8),
    })
    report = compute_metrics(sample, cards)
    assert report["status"] == MEASURED
    assert report["population_precision"] == 0.75
    assert report["weighted_non_evaluable_share"] == 0.40
    assert report["estimated_implements_total"] == 90
    assert report["estimated_evaluable_total"] == 120
    assert report["population_precision"] != 0.65


# Le popolazioni qui sotto sono costruite per i test: verificano il metodo, non misurano VibeCraft.
IMP, COR, ERR, NV = "IMPLEMENTA", "CORRELATO", "ERRATO", "NON_VALUTABILE"


def test_campionamento_sproporzionato_usa_i_pesi():
    # S1 pesa 100 per scheda, S2 è censito: la precisione grezza (0.25) non stima la popolazione.
    sample, cards = _labelled_sample({"S1": (1000, [IMP] * 5 + [COR] * 5), "S2": (10, [ERR] * 10)})
    report = compute_metrics(sample, cards)
    assert report["sample_precision"] == 0.25
    assert report["population_precision"] == 500 / 1010


def test_quote_non_valutabili_uguali_coincidono_con_la_media_pesata():
    sample, cards = _labelled_sample({
        "S1": (100, [IMP] * 6 + [COR] * 2 + [NV] * 2),
        "S2": (300, [IMP] * 2 + [ERR] * 6 + [NV] * 2),
    })
    report = compute_metrics(sample, cards)
    assert report["population_precision"] == (100 * 0.75 + 300 * 0.25) / 400 == 0.375
    assert report["weighted_non_evaluable_share"] == 0.2


def test_campione_tutto_non_valutabile_non_diventa_precisione_zero():
    sample, cards = _labelled_sample({"S1": (100, [NV] * 5), "S2": (50, [NV] * 3)})
    report = compute_metrics(sample, cards)
    assert report["status"] == NOT_MEASURED
    assert report["population_precision"] is None and report["sample_precision"] is None
    assert "non zero" in report["reason"]
    assert report["weighted_non_evaluable_share"] == 1.0
    # Nessun valutabile visto non prova che non ce ne siano: l'intervallo resta [0, 1].
    assert report["interval"]["bounds"] == [0.0, 1.0]
    census, cards = _labelled_sample({"S1": (3, [NV] * 3)})
    report = compute_metrics(census, cards)
    assert report["interval"]["bounds"] is None and report["interval"]["reason"]


def test_annotazioni_mancanti_invalide_o_discordanti_bloccano():
    sample, cards = _labelled_sample({"S1": (20, [IMP, COR, ERR])})
    missing = compute_metrics(sample, cards[:-1])
    assert missing["status"] == NOT_MEASURED and missing["population_precision"] is None
    assert missing["annotation_completeness"]["missing"] == 1
    bad = [dict(cards[0], label="FORSE")] + cards[1:]
    invalid = compute_metrics(sample, bad)
    assert invalid["status"] == NOT_MEASURED and invalid["annotation_completeness"]["errors"] == 1
    other = dict(cards[0], label=ERR, annotator="altro-test")
    split = compute_metrics(sample, cards + [other])
    assert split["status"] == NOT_MEASURED and split["annotation_completeness"]["disagreements"] == 1


def test_tutti_successi_o_insuccessi_senza_censimento_non_danno_certezza():
    ok, cards = _labelled_sample({"S1": (100, [IMP] * 10)})
    report = compute_metrics(ok, cards)
    assert report["population_precision"] == 1.0
    low, high = report["interval"]["bounds"]
    assert high == 1.0 and low < 0.9
    ko, cards = _labelled_sample({"S1": (100, [ERR] * 10)})
    report = compute_metrics(ko, cards)
    low, high = report["interval"]["bounds"]
    assert low == 0.0 and high > 0.1


def test_strato_con_una_sola_osservazione():
    sample, cards = _labelled_sample({"S1": (50, [IMP]), "S2": (40, [IMP, COR, ERR, IMP])})
    report = compute_metrics(sample, cards)
    assert report["status"] == MEASURED
    s1 = next(s for s in report["per_stratum"] if s["stratum"] == "S1")
    assert s1["w_h"] == 50 and s1["implements_bounds"][0] == 1 and s1["implements_bounds"][1] == 50
    low, high = report["interval"]["bounds"]
    assert 0 <= low <= report["population_precision"] <= high <= 1


def test_censimento_completo_ha_intervallo_degenere():
    sample, cards = _labelled_sample({"S1": (4, [IMP, IMP, COR, NV]), "S2": (2, [IMP, ERR])})
    report = compute_metrics(sample, cards)
    assert report["sampling_coverage"]["census"] is True
    assert report["population_precision"] == 3 / 5
    assert report["interval"]["bounds"] == [0.6, 0.6]
    assert "censimento" in report["interval"]["note"]


def test_strato_non_campionato_blocca_senza_inventare_valori():
    sample, cards = _labelled_sample({"S1": (100, [IMP] * 5), "S2": (30, [])})
    report = compute_metrics(sample, cards)
    assert report["status"] == NOT_MEASURED
    assert report["population_precision"] is None
    assert "non è nel campione" in report["reason"]
    assert report["sampling_coverage"]["population_in_sampled_strata"] == 100


def test_nessun_arrotondamento_intermedio():
    # π_h = 3/7 e 3/11 sono arrotondati a 6 cifre nel sigillo: il peso usa N_h/n_h esatto.
    sample, cards = _labelled_sample({"S1": (7, [IMP, COR, COR]), "S2": (11, [IMP, IMP, ERR])})
    report = compute_metrics(sample, cards)
    assert report["population_precision"] == 29 / 54
    assert report["population_precision"] != round(29 / 54, 4)


def test_integrita_dei_pesi_e_del_sigillo():
    sample, cards = _labelled_sample({"S1": (40, [IMP, COR, NV]), "S2": (60, [IMP, ERR])})
    report = compute_metrics(sample, cards)
    assert sum(s["w_h"] * s["n_h"] for s in report["per_stratum"]) == 100
    assert report["estimated_evaluable_total"] + report["weighted_non_evaluable_share"] * 100 == 100
    broken = dict(sample, strata=[dict(sample["strata"][0], n_h=2, pi_h=0.05)] + sample["strata"][1:])
    bad = compute_metrics(broken, cards)
    assert bad["status"] == NOT_MEASURED and bad["design_problems"]
    wrong_pi = dict(sample, strata=[dict(sample["strata"][0], pi_h=0.5)] + sample["strata"][1:])
    assert compute_metrics(wrong_pi, cards)["design_problems"]
    assert compute_metrics(dict(sample, population=99), cards)["design_problems"]


def test_cli_scrive_metriche_v2_e_non_tocca_i_risultati_storici(tmp_path, capsys):
    import json

    from scripts.link_audit import main

    sample, cards = _labelled_sample({
        "S1": (100, [IMP] * 8 + [COR] * 2),
        "S2": (100, [IMP] + [COR] + [NV] * 8),
    })
    (tmp_path / "sigillo.json").write_text(json.dumps(sample), encoding="utf-8")
    (tmp_path / "schede.json").write_text(json.dumps(cards), encoding="utf-8")
    (tmp_path / "metriche.json").write_text('{"aggregate_precision": 0.65}', encoding="utf-8")
    assert main(["metrics", "--run", str(tmp_path)]) == 0
    out = json.loads((tmp_path / "metriche-v2.json").read_text(encoding="utf-8"))
    assert out["methodology_version"] == 2 and out["population_precision"] == 0.75
    assert "aggregate_precision" not in out and out["inputs"]["schede_sha256"]
    assert json.loads((tmp_path / "metriche.json").read_text(encoding="utf-8")) == {"aggregate_precision": 0.65}
    shown = json.loads(capsys.readouterr().out.rsplit("Scritto", 1)[0])
    assert shown["population_precision"] == 0.75 and shown["interval"]["conservative"] is True
    assert main(["metrics", "--run", str(tmp_path)]) == 0  # stesse schede: stesso risultato
    cards[0]["label"] = ERR
    (tmp_path / "schede.json").write_text(json.dumps(cards), encoding="utf-8")
    assert main(["metrics", "--run", str(tmp_path)]) == 1  # schede cambiate: non sovrascrive


def test_limiti_ipergeometrici_uguali_all_enumerazione_delle_estrazioni():
    # Per ogni K si enumerano tutte le estrazioni di n archi su N: il limite tiene K se e solo
    # se entrambe le code esatte superano alpha. Controlla anche l'off-by-one ai bordi.
    from fractions import Fraction
    from itertools import combinations

    from eval.link_audit import hypergeometric_bounds

    alpha = Fraction(1, 40)
    for N in range(1, 8):
        for n in range(1, N + 1):
            draws = list(combinations(range(N), n))
            for x in range(n + 1):
                kept = []
                for K in range(N + 1):
                    hits = [sum(1 for i in d if i < K) for d in draws]
                    ge = Fraction(sum(h >= x for h in hits), len(draws))
                    le = Fraction(sum(h <= x for h in hits), len(draws))
                    if ge > alpha and le > alpha:
                        kept.append(K)
                low, high = hypergeometric_bounds(N, n, x, alpha)
                assert kept == list(range(low, high + 1)), (N, n, x)


def _compositions(N):
    return [(i, o, N - i - o) for i in range(N + 1) for o in range(N + 1 - i)]


def _draws(pop, n):
    """Esiti (xI, xO, xU) con probabilità esatta della ipergeometrica multivariata."""
    from fractions import Fraction
    from math import comb

    ki, ko, ku = pop
    total = comb(ki + ko + ku, n)
    for xi in range(min(ki, n) + 1):
        for xo in range(min(ko, n - xi) + 1):
            xu = n - xi - xo
            if xu <= ku:
                yield (xi, xo, xu), Fraction(comb(ki, xi) * comb(ko, xo) * comb(ku, xu), total)


def test_copertura_esatta_conservativa_su_popolazioni_costruite():
    # Copertura della procedura su estrazioni ripetute, calcolata esattamente: per ogni
    # popolazione finita costruita, somma delle probabilità dei campioni il cui intervallo
    # contiene il rapporto vero. Non è una misura del progetto.
    from fractions import Fraction

    from eval.link_audit import _ratio_interval

    design = ((5, 2), (4, 3))
    worst = Fraction(1)
    for p1 in _compositions(design[0][0]):
        for p2 in _compositions(design[1][0]):
            pops = (p1, p2)
            true_e = sum(i + o for i, o, _ in pops)
            if true_e == 0:
                continue
            truth = Fraction(sum(i for i, _, _ in pops), true_e)
            covered = Fraction(0)
            for s1, q1 in _draws(p1, design[0][1]):
                for s2, q2 in _draws(p2, design[1][1]):
                    rows = [(N, n, s[0], s[0] + s[1]) for (N, n), s in zip(design, (s1, s2), strict=True)]
                    bounds = _ratio_interval(rows)["interval"]["bounds"]
                    if bounds is None:
                        continue
                    low, high = bounds
                    assert 0 <= low <= high <= 1
                    w = [Fraction(N, n) for N, n in design]
                    est_e = sum(wh * (s[0] + s[1]) for wh, s in zip(w, (s1, s2), strict=True))
                    if est_e:
                        point = sum(wh * s[0] for wh, s in zip(w, (s1, s2), strict=True)) / est_e
                        assert low <= point <= high
                    if low <= truth <= high:
                        covered += q1 * q2
            worst = min(worst, covered)
    assert worst >= Fraction(95, 100)

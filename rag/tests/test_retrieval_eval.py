"""Test del MECCANISMO di eval del retrieval (non delle metriche reali).

Non richiede server, Qdrant o modello: usa un retriever fittizio deterministico e un
mini golden-set inline, così verifica che core.eval_metrics calcoli correttamente
recall@k, "sorgente in top-3" e MRR, e che il matching per doc/section/chunk/file funzioni.
Le soglie di qualità reali si misurano invece con `uv run python -m eval.run` (server su).
"""
from core import eval_metrics


def _fake_retriever(ranking: dict):
    """Costruisce una retrieve_fn(query, k) che restituisce, per ogni query, la lista
    ordinata di risultati predefinita in `ranking` (troncata a k)."""
    def retrieve(query: str, k: int) -> list[dict]:
        return list(ranking.get(query, []))[:k]
    return retrieve


def _hit(chunk_id, doc_id, section=""):
    return {"chunk_id": chunk_id, "doc_id": doc_id, "section": section}


def test_result_matches_keys():
    r = _hit("00_meta/safeguards_security.md#03-concorrenza", "00_meta/safeguards_security.md", "Concorrenza Critica")
    assert eval_metrics.result_matches(r, {"doc": "safeguards_security", "section": "Concorrenza"})
    assert eval_metrics.result_matches(r, {"chunk": "safeguards_security.md#03"})
    assert eval_metrics.result_matches(r, {"file": "safeguards_security.md"})
    assert eval_metrics.result_matches(r, {"any": "concorrenza"})
    assert not eval_metrics.result_matches(r, {"doc": "matrice_permessi"})
    assert not eval_metrics.result_matches(r, {"doc": "safeguards_security", "section": "Immutabilità"})
    assert not eval_metrics.result_matches(r, {})  # matcher vuoto non è mai un hit


def test_normalize_expected_new_and_legacy():
    new = eval_metrics.normalize_expected({"q": "x", "expected": ["foo", {"doc": "bar"}]})
    assert new == [{"any": "foo"}, {"doc": "bar"}]
    legacy = eval_metrics.normalize_expected({"q": "x", "expected_doc": "d", "expected_section": "s"})
    assert legacy == [{"doc": "d", "section": "s"}]


def test_evaluate_metrics_on_mini_set():
    # Caso 1: sorgente attesa in posizione 1 (perfetto). Caso 2: in posizione 7
    # (fuori top-3 e fuori recall@5, dentro recall@10). Caso 3: assente (miss totale).
    ranking = {
        "q1": [_hit("a.md#00", "a.md", "Alpha")] + [_hit(f"x{i}.md#00", f"x{i}.md") for i in range(9)],
        "q2": [_hit(f"y{i}.md#00", f"y{i}.md") for i in range(6)] + [_hit("b.md#00", "b.md", "Beta")],
        "q3": [_hit(f"z{i}.md#00", f"z{i}.md") for i in range(10)],
    }
    cases = [
        {"q": "q1", "expected": [{"doc": "a.md"}]},
        {"q": "q2", "expected": [{"doc": "b.md"}]},
        {"q": "q3", "expected": [{"doc": "missing.md"}]},
    ]
    report = eval_metrics.evaluate(cases, _fake_retriever(ranking), ks=(5, 10))

    assert report["n"] == 3
    by_q = {c["q"]: c for c in report["cases"]}
    assert by_q["q1"]["best_rank"] == 1
    assert by_q["q2"]["best_rank"] == 7
    assert by_q["q3"]["best_rank"] is None

    agg = report["aggregate"]
    # recall@5: q1 hit, q2 miss (rank 7), q3 miss -> 1/3
    assert agg["recall@5"] == 1 / 3
    # recall@10: q1 e q2 hit, q3 miss -> 2/3
    assert agg["recall@10"] == 2 / 3
    # source_in_top3: solo q1 -> 1/3
    assert agg["source_in_top3"] == 1 / 3
    # mrr: 1/1 + 1/7 + 0, media / 3
    assert abs(agg["mrr"] - (1.0 + 1 / 7) / 3) < 1e-9


def test_recall_averages_multiple_expected_sources():
    # Un caso con due sorgenti attese: una trovata (rank 1), una assente -> recall = 0.5
    ranking = {"q": [_hit("a.md#00", "a.md")] + [_hit(f"x{i}.md#00", f"x{i}.md") for i in range(9)]}
    cases = [{"q": "q", "expected": [{"doc": "a.md"}, {"doc": "notthere.md"}]}]
    report = eval_metrics.evaluate(cases, _fake_retriever(ranking), ks=(5, 10))
    assert report["aggregate"]["recall@5"] == 0.5
    assert report["cases"][0]["n_expected"] == 2


# ─────────────────────────────────────────────────────────────────────────────────
# S5 (ADR 0002): saturazione, sottoinsieme avversariale, e integrità dei casi nuovi.
# ─────────────────────────────────────────────────────────────────────────────────

def test_report_segnala_metrica_satura():
    """Recall 1.000 su TUTTI i casi non è un buon risultato: è una misura che ha smesso
    di discriminare, ed è il difetto che ha reso cieca la calibrazione del 2026-07-22.
    Deve comparire in `saturated`, non passare per un 100%."""
    ranking = {q: [_hit(f"{q}.md#00", f"{q}.md")] for q in ("q1", "q2", "q3")}
    cases = [{"q": q, "expected": [{"doc": f"{q}.md"}]} for q in ranking]
    report = eval_metrics.evaluate(cases, _fake_retriever(ranking), ks=(1, 2, 5, 10))

    assert report["aggregate"]["recall@5"] == 1.0
    assert report["saturated"] == ["recall@1", "recall@2", "recall@5", "recall@10"]

    # Un solo caso che manca basta a togliere la saturazione: la metrica torna a discriminare.
    cases[2] = {"q": "q3", "expected": [{"doc": "assente.md"}]}
    report = eval_metrics.evaluate(cases, _fake_retriever(ranking), ks=(1, 2, 5, 10))
    assert report["saturated"] == []


def test_metrica_avversariale_separata_dalla_media():
    """I casi `adversarial: true` sono pochi rispetto ai facili: annegati nella media
    generale il loro movimento è invisibile, e sono l'unico numero che l'ADR 0002 deve
    muovere. Vanno esposti come voce a sé."""
    ranking = {
        "facile1": [_hit("a.md#00", "a.md")],
        "facile2": [_hit("b.md#00", "b.md")],
        "facile3": [_hit("c.md#00", "c.md")],
        # l'avversariale sbaglia: il distrattore è primo, la fonte attesa seconda
        "avv": [_hit("distrattore.md#00", "distrattore.md"), _hit("norma.md#00", "norma.md")],
    }
    cases = [
        {"q": "facile1", "expected": [{"doc": "a.md"}]},
        {"q": "facile2", "expected": [{"doc": "b.md"}]},
        {"q": "facile3", "expected": [{"doc": "c.md"}]},
        {"q": "avv", "adversarial": True, "expected": [{"doc": "norma.md"}]},
    ]
    report = eval_metrics.evaluate(cases, _fake_retriever(ranking), ks=(1, 2))

    # La media generale nasconde il fallimento: 3 casi su 4 a rango 1.
    assert report["aggregate"]["recall@1"] == 0.75
    # Il sottoinsieme lo mostra: 0 su 1.
    adv = report["adversarial"]
    assert adv["n"] == 1
    assert adv["aggregate"]["recall@1"] == 0.0
    assert adv["aggregate"]["recall@2"] == 1.0
    # E i casi restano marcati singolarmente, così il report può etichettare le righe.
    assert [c["adversarial"] for c in report["cases"]] == [False, False, False, True]


def test_adversarial_assente_se_nessun_caso_e_marcato():
    """Un golden set senza casi marcati non deve produrre un sottoinsieme vuoto da
    stampare come se fosse una misura: None significa "non pervenuto"."""
    ranking = {"q": [_hit("a.md#00", "a.md")]}
    report = eval_metrics.evaluate([{"q": "q", "expected": [{"doc": "a.md"}]}],
                                   _fake_retriever(ranking), ks=(1,))
    assert report["adversarial"] is None


def test_casi_avversariali_hanno_matcher_validi():
    """Ogni caso avversariale deve puntare a un documento e a una sezione REALMENTE
    esistenti nel corpus. È il difetto che ha già colpito questo progetto una volta:
    la nota del 2026-07-22 nel golden set registra 24 casi su 34 che puntavano a
    documenti eliminati, cioè una recall misurata contro il nulla."""
    import re

    import yaml

    from core.config import DOCS_DIR, GOLDEN_SET_PATH

    cases = yaml.safe_load(GOLDEN_SET_PATH.read_text(encoding="utf-8"))["cases"]
    avversariali = [c for c in cases if c.get("adversarial")]
    assert avversariali, "il golden set non contiene più casi avversariali (S5, ADR 0002)"

    documenti = {p: p.read_text(encoding="utf-8") for p in DOCS_DIR.rglob("*.md")}
    assert documenti, f"corpus non trovato in {DOCS_DIR}"

    for caso in avversariali:
        for matcher in eval_metrics.normalize_expected(caso):
            doc, sezione = matcher.get("doc"), matcher.get("section")
            candidati = [p for p in documenti if doc.lower() in str(p).lower().replace("\\", "/")]
            assert candidati, f"{caso['q']!r}: nessun documento del corpus contiene {doc!r}"
            if not sezione:
                continue
            # La sezione deve corrispondere a un heading REALE (## o ###), con lo stesso
            # confronto per sottostringa case-insensitive che usa result_matches().
            heading = [h for p in candidati
                       for h in re.findall(r"^#{2,3} +(.+)$", documenti[p], re.MULTILINE)
                       if sezione.lower() in h.lower()]
            assert heading, (f"{caso['q']!r}: nessun heading di {[str(p.name) for p in candidati]} "
                             f"contiene la sezione attesa {sezione!r}")

        # Il DISTRATTORE deve esistere quanto l'atteso. Un caso avversariale il cui
        # distrattore manca dal corpus non fallisce: passa, perche' non ha piu' nulla contro
        # cui competere. Misurato il 2026-09-01: tutti e tre i distrattori vivevano fuori
        # dalla baseline committata, e il sottoinsieme leggeva recall@1 = 0.0% in locale e
        # 80% in CI — lo stesso numero, invertito, a seconda della macchina. Una metrica che
        # si capovolge col checkout non misura il sistema, misura il checkout.
        distrattore = caso.get("distractor")
        assert distrattore, (
            f"{caso['q']!r}: caso avversariale senza `distractor` dichiarato. Il documento "
            f"contro cui compete e' parte della misura e va dichiarato, non lasciato a un commento.")
        relativi = {str(p.relative_to(DOCS_DIR)).replace("\\", "/") for p in documenti}
        assert distrattore in relativi, (
            f"{caso['q']!r}: il distrattore {distrattore!r} non esiste nel corpus. "
            f"Il caso passerebbe senza esercitare alcun contrasto.")

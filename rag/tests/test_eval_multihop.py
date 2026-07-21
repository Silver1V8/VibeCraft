"""Test della MECCANICA dell'eval multihop (eval/run_multihop.py) — nessun server/LLM.

Come tests/test_eval_guardrail.py: retriever e graph_query fake deterministici per
validare parsing del golden-set reale, calcolo delle metriche A/B (recall, exact-node-
match) e la regola del trigger M2. La misura REALE si lancia con
`uv run python -m eval.run_multihop` (server su).
"""
import json

from core import eval_metrics
from eval import run_multihop


# ---------------------------------------------------------------------------
# Golden-set reale: parsing, forma dei casi e mix richiesto dalla milestone M1
# ---------------------------------------------------------------------------

def test_real_golden_multihop_parses_and_is_well_formed():
    cases = run_multihop.load_cases()
    assert len(cases) >= 10
    kinds = [c["kind"] for c in cases]
    assert kinds.count("structural") >= 4
    assert kinds.count("multihop") >= 4
    for c in cases:
        assert c["q"].strip()
        assert c["kind"] in ("structural", "multihop")
        assert c["evidence"].strip()
        assert c["answer_note"].strip()
        matchers = c["expected"]["retrieval"]
        assert matchers, f"caso senza matcher retrieval: {c['q']}"
        for m in matchers:
            assert any(m.get(k) for k in ("any", "chunk", "file", "doc", "section"))
        if c["kind"] == "structural":
            g = c["expected"]["graph"]
            assert g["intent"], f"caso structural senza intent atteso: {c['q']}"
            # l'atteso deve vincolare QUALCOSA oltre all'intent (match esatto verificabile)
            assert any(g.get(k) for k in ("count", "nodes", "relations"))


def test_multihop_cases_span_two_or_more_documents():
    """Un multihop 'vero' non è risolvibile da un singolo chunk: i matcher attesi devono
    puntare ad almeno 2 documenti distinti."""
    for c in run_multihop.load_cases():
        if c["kind"] != "multihop":
            continue
        docs = {m.get("doc") for m in c["expected"]["retrieval"] if m.get("doc")}
        assert len(docs) >= 2, f"multihop su un solo documento: {c['q']}"


# ---------------------------------------------------------------------------
# Fake deterministici
# ---------------------------------------------------------------------------

def _case_structural(q="quali documenti esistono?", count=2):
    return {
        "q": q, "kind": "structural",
        "expected": {
            "retrieval": [{"doc": "a.md"}, {"doc": "b.md"}],
            "graph": {"intent": "documenti", "count": count, "nodes": ["a.md", "b.md"]},
        },
        "evidence": "e", "answer_note": "n",
    }


def _case_multihop(q="come si collegano a e b?"):
    return {
        "q": q, "kind": "multihop",
        "expected": {"retrieval": [{"doc": "a.md", "section": "Alfa"}, {"doc": "b.md"}]},
        "evidence": "e", "answer_note": "n",
    }


def _hit(doc, section=""):
    return {"chunk_id": f"{doc}#00", "doc_id": doc, "section": section}


def _perfect_retriever(q, k):
    return [_hit("a.md", "Alfa"), _hit("b.md", "Beta")][:k]


def _half_retriever(q, k):
    """Trova solo il primo dei due documenti attesi: recall 0.5, A fallita."""
    return [_hit("a.md", "Alfa")] + [_hit(f"noise{i}.md") for i in range(k - 1)]


def _good_graph(q, target):
    return {"intent": "documenti", "answer": ["a.md", "b.md"], "count": 2}


def _bad_graph(q, target):
    return {"intent": "sconosciuto", "answer": [], "count": 0}


# ---------------------------------------------------------------------------
# Baseline A: recall e regola "riuscito solo se TUTTI gli attesi sono in top-k"
# ---------------------------------------------------------------------------

def test_retrieval_case_passes_only_when_all_matchers_found():
    case = _case_multihop()
    full = run_multihop.eval_retrieval_case(case, _perfect_retriever("q", 10))
    assert full["passed"] and full["recall"] == 1.0 and not full["missing"]

    half = run_multihop.eval_retrieval_case(case, _half_retriever("q", 10))
    assert not half["passed"] and half["recall"] == 0.5
    assert half["missing"] == [{"doc": "b.md"}]
    assert half["found"] == [{"doc": "a.md", "section": "Alfa"}]


def test_retrieval_case_counts_only_topk():
    """Un atteso oltre il top-k non conta: 'expected non in top-10' = fallito."""
    case = _case_multihop()
    results = [_hit(f"noise{i}.md") for i in range(10)] + [_hit("a.md", "Alfa"), _hit("b.md")]
    out = run_multihop.eval_retrieval_case(case, results, k=10)
    assert out["recall"] == 0.0 and not out["passed"]


# ---------------------------------------------------------------------------
# Riferimento B: exact-node-match su intent/count/nodes/relations
# ---------------------------------------------------------------------------

def test_graph_case_exact_match_and_mismatch_reasons():
    case = _case_structural()
    ok = run_multihop.eval_graph_case(case, _good_graph("q", None))
    assert ok["exact_match"] is True and ok["mismatches"] == []

    wrong_intent = run_multihop.eval_graph_case(case, {"intent": "entità", "answer": ["a.md", "b.md"], "count": 2})
    assert wrong_intent["exact_match"] is False
    assert any("intent" in m for m in wrong_intent["mismatches"])

    wrong_count = run_multihop.eval_graph_case(case, {"intent": "documenti", "answer": ["a.md", "b.md"], "count": 3})
    assert wrong_count["exact_match"] is False
    assert any("count" in m for m in wrong_count["mismatches"])

    missing_node = run_multihop.eval_graph_case(case, {"intent": "documenti", "answer": ["a.md"], "count": 2})
    assert missing_node["exact_match"] is False
    assert any("b.md" in m for m in missing_node["mismatches"])


def test_graph_case_relations_checked_on_both_directions():
    case = {
        "q": "relazioni di a.md", "kind": "structural",
        "expected": {"retrieval": [{"doc": "a.md"}],
                     "graph": {"intent": "relazioni",
                               "relations": [{"relation": "DERIVA_DA", "node": "b.md"},
                                             {"relation": "PART_OF", "node": "a.md#01"}]}},
        "evidence": "e", "answer_note": "n",
    }
    resp = {"intent": "relazioni", "target": "a.md", "count": 2,
            "out": [{"relation": "DERIVA_DA", "to": "b.md"}],
            "in": [{"relation": "PART_OF", "from": "a.md#01"}]}
    assert run_multihop.eval_graph_case(case, resp)["exact_match"] is True

    resp_missing = {"intent": "relazioni", "target": "a.md", "count": 1,
                    "out": [{"relation": "DERIVA_DA", "to": "b.md"}], "in": []}
    out = run_multihop.eval_graph_case(case, resp_missing)
    assert out["exact_match"] is False
    assert any("PART_OF" in m for m in out["mismatches"])


def test_graph_case_without_expected_graph_is_informational():
    out = run_multihop.eval_graph_case(_case_multihop(), _bad_graph("q", None))
    assert out["exact_match"] is None  # B non valutabile: non concorre al trigger


# ---------------------------------------------------------------------------
# Regola del trigger M2: >= TRIGGER_MIN casi con A=fallito E B=riuscito
# ---------------------------------------------------------------------------

def _rows(n_qualifying, n_other=0):
    rows = [{"q": f"q{i}", "A": {"passed": False}, "B": {"exact_match": True}}
            for i in range(n_qualifying)]
    rows += [{"q": f"other{i}", "A": {"passed": True}, "B": {"exact_match": True}}
             for i in range(n_other)]
    return rows


def test_trigger_fires_at_threshold_and_not_below():
    assert run_multihop.trigger_m2(_rows(3))["fired"] is True
    assert run_multihop.trigger_m2(_rows(2, n_other=5))["fired"] is False


def test_trigger_ignores_a_passed_and_b_not_evaluable():
    rows = [{"q": "a-pass", "A": {"passed": True}, "B": {"exact_match": True}},
            {"q": "b-null", "A": {"passed": False}, "B": {"exact_match": None}},
            {"q": "b-fail", "A": {"passed": False}, "B": {"exact_match": False}}]
    out = run_multihop.trigger_m2(rows)
    assert out["fired"] is False and out["n_qualifying"] == 0


# ---------------------------------------------------------------------------
# run(): catena completa con fake, delta per caso e report salvabile
# ---------------------------------------------------------------------------

def test_run_end_to_end_with_fakes_fires_trigger(tmp_path, monkeypatch):
    cases = [_case_structural(f"structural {i}") for i in range(3)] + [_case_multihop()]
    report = run_multihop.run(cases, _half_retriever, _good_graph, k=10)

    assert report["n"] == 4
    assert report["trigger_m2"]["fired"] is True          # 3 structural: A fail + B exact
    assert report["trigger_m2"]["n_qualifying"] == 3
    deltas = [r["delta"] for r in report["cases"]]
    assert deltas == ["B>A", "B>A", "B>A", "A-only"]

    monkeypatch.setattr(run_multihop, "RESULTS_DIR", tmp_path)
    out = run_multihop.save_report(report, url="http://fake")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["trigger_m2"]["fired"] is True
    assert len(payload["cases"]) == 4
    assert out.name.startswith("multihop_")


def test_run_trigger_not_fired_when_retrieval_is_good():
    cases = [_case_structural(f"structural {i}") for i in range(3)]
    report = run_multihop.run(cases, _perfect_retriever, _good_graph, k=10)
    assert report["trigger_m2"]["fired"] is False
    assert all(r["delta"] == "pari" for r in report["cases"])


def test_matcher_semantics_shared_with_core_eval_metrics():
    """La baseline A riusa i matcher di core.eval_metrics: stessa semantica substring
    case-insensitive del golden-set classico."""
    assert eval_metrics.result_matches(_hit("00_meta/A.md", "Sezione Alfa"),
                                       {"doc": "a.md", "section": "alfa"})

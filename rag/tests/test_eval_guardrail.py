"""Test del GUARDRAIL di eval — solo meccanica, nessun modello/LLM/server.

Valida con un retriever fake deterministico l'intera catena che rende l'eval un
guardrail eseguibile: parsing del golden-set reale, matcher, calcolo del recall,
soglia --assert-min che scatta (exit 1) scrivendo comunque il report, estrazione
deterministica dei candidati all'archive e loro promozione nel golden-set.
Le metriche REALI si misurano con `uv run python -m eval.run --assert-min ...`
(server su): comando separato, da lanciare prima di merge che toccano il retrieval.
"""
import json
from pathlib import Path

import yaml

from core import canvas_review, eval_metrics, pipeline
from eval import run as eval_run


# ---------------------------------------------------------------------------
# Golden-set reale: il formato deve restare parsabile e ogni caso ben formato
# ---------------------------------------------------------------------------

def test_real_golden_set_parses_and_is_well_formed():
    cases = eval_run.load_cases()
    assert len(cases) >= 10
    for c in cases:
        assert c["q"].strip()
        matchers = eval_metrics.normalize_expected(c)
        assert matchers, f"caso senza expected: {c['q']}"
        for m in matchers:
            assert any(m.get(k) for k in ("any", "chunk", "file", "doc", "section")), \
                f"matcher vuoto nel caso: {c['q']}"


# ---------------------------------------------------------------------------
# Soglia --assert-min: meccanica di run_eval con retriever fake
# ---------------------------------------------------------------------------

def _perfect_retriever(cases):
    """Retriever fake che restituisce come primo risultato esattamente la sorgente
    attesa di ogni caso (recall = 1.0)."""
    by_q = {}
    for c in cases:
        m = eval_metrics.normalize_expected(c)[0]
        by_q[c["q"]] = [{"chunk_id": f"{m.get('doc', 'x')}#00",
                         "doc_id": m.get("doc", "x"), "section": m.get("section", "")}]

    def retrieve(query, k):
        return by_q.get(query, [])[:k]
    return retrieve


def _blind_retriever(query, k):
    """Retriever fake che non trova mai nulla di atteso (recall = 0.0)."""
    return [{"chunk_id": f"noise{i}.md#00", "doc_id": f"noise{i}.md", "section": ""} for i in range(k)]


def test_assert_min_passes_when_recall_above_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(eval_run, "RESULTS_DIR", tmp_path)
    cases = [{"q": "q1", "expected": [{"doc": "a.md"}]}, {"q": "q2", "expected": [{"doc": "b.md"}]}]
    code = eval_run.run_eval(cases, _perfect_retriever(cases), ks=[5, 10], assert_min=0.9)
    assert code == 0


def test_assert_min_fails_below_threshold_but_still_writes_report(tmp_path, monkeypatch):
    monkeypatch.setattr(eval_run, "RESULTS_DIR", tmp_path)
    cases = [{"q": "q1", "expected": [{"doc": "a.md"}]}]
    code = eval_run.run_eval(cases, _blind_retriever, ks=[5, 10], assert_min=0.9)
    assert code == 1
    reports = list(tmp_path.glob("eval_*.json"))
    assert len(reports) == 1  # il report va scritto ANCHE quando la soglia scatta
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload["aggregate"]["recall@10"] == 0.0


# ---------------------------------------------------------------------------
# Estrazione deterministica del candidato all'archive (core.canvas_review)
# ---------------------------------------------------------------------------

def _make_change_dir(tmp_path, canvas="# REASONS Canvas: pagamenti\ncorpo", sources=("00_meta/safeguards_security.md",)):
    change = tmp_path / "pagamenti-sicuri"
    change.mkdir()
    (change / "canvas.md").write_text(canvas, encoding="utf-8")
    (change / "meta.json").write_text(
        json.dumps({"dev_type": "backend", "governed_sources": list(sources)}), encoding="utf-8")
    return change


def test_governed_docs_from_context_parses_headers():
    ctx = ("--- 00_meta/safeguards_security.md § Concorrenza Critica [IRON_MEMORY] ---\ntesto\n\n"
           "--- 00_meta/glossario_entita.md § EVENTO ---\ntesto\n\n"
           "--- 00_meta/safeguards_security.md § Privacy ---\ntesto")
    docs = pipeline.governed_docs_from_context(ctx)
    assert docs == ["00_meta/safeguards_security.md", "00_meta/glossario_entita.md"]  # unici, in ordine
    assert pipeline.governed_docs_from_context("") == []


def test_extract_eval_candidate_from_change(tmp_path):
    change = _make_change_dir(tmp_path)
    cand = canvas_review.extract_eval_candidate("pagamenti-sicuri", change)
    assert cand["q"] == "pagamenti-sicuri: REASONS Canvas: pagamenti"
    assert cand["expected"] == [{"doc": "00_meta/safeguards_security.md"}]
    assert cand["from_feature"] == "pagamenti-sicuri"


def test_extract_eval_candidate_missing_pieces(tmp_path):
    # senza canvas o senza governed_sources non c'è candidato (mai un'eccezione)
    empty = tmp_path / "vuota"
    empty.mkdir()
    assert canvas_review.extract_eval_candidate("vuota", empty) is None
    change = _make_change_dir(tmp_path, sources=())
    assert canvas_review.extract_eval_candidate("pagamenti-sicuri", change) is None


def test_append_eval_candidate_appends_and_dedupes(tmp_path):
    path = tmp_path / "candidates.yaml"
    cand = {"q": "x: intent", "expected": [{"doc": "a.md"}], "from_feature": "x", "extracted_at": "t"}
    assert canvas_review.append_eval_candidate(cand, path) is True
    assert canvas_review.append_eval_candidate(cand, path) is False  # dedup per query
    other = dict(cand, q="y: altro intent")
    assert canvas_review.append_eval_candidate(other, path) is True
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert [c["q"] for c in data["candidates"]] == ["x: intent", "y: altro intent"]


# ---------------------------------------------------------------------------
# Promozione: sposta dal file candidati al golden-set, preservandone i commenti
# ---------------------------------------------------------------------------

def _seed_files(tmp_path) -> tuple[Path, Path]:
    golden = tmp_path / "golden_set.yaml"
    golden.write_text("# commento di documentazione da preservare\ncases:\n"
                      '  - q: "caso storico"\n    expected:\n      - {doc: storico.md}\n',
                      encoding="utf-8")
    candidates = tmp_path / "candidates.yaml"
    for i in range(3):
        canvas_review.append_eval_candidate(
            {"q": f"feature-{i}: intent {i}", "expected": [{"doc": f"doc{i}.md"}],
             "from_feature": f"feature-{i}", "extracted_at": "2026-07-13T00:00:00+00:00"},
            candidates)
    return candidates, golden


def test_promote_moves_entries_into_golden_set(tmp_path):
    candidates, golden = _seed_files(tmp_path)
    promoted = eval_run.promote_candidates([0, 2], candidates_path=candidates, golden_path=golden)
    assert [c["q"] for c in promoted] == ["feature-0: intent 0", "feature-2: intent 2"]

    # il golden-set risultante è YAML valido, contiene i promossi e conserva i commenti
    text = golden.read_text(encoding="utf-8")
    assert "# commento di documentazione da preservare" in text
    cases = yaml.safe_load(text)["cases"]
    assert [c["q"] for c in cases] == ["caso storico", "feature-0: intent 0", "feature-2: intent 2"]
    assert eval_metrics.normalize_expected(cases[1]) == [{"doc": "doc0.md"}]

    # i promossi sono stati RIMOSSI dai candidati (spostamento, non copia)
    assert [c["q"] for c in eval_run.load_candidates(candidates)] == ["feature-1: intent 1"]


def test_promote_rejects_bad_indices(tmp_path):
    candidates, golden = _seed_files(tmp_path)
    try:
        eval_run.promote_candidates([7], candidates_path=candidates, golden_path=golden)
        raise AssertionError("indice fuori range doveva sollevare ValueError")
    except ValueError:
        pass
    # nessuna modifica ai file su errore
    assert len(eval_run.load_candidates(candidates)) == 3
    assert len(yaml.safe_load(golden.read_text(encoding="utf-8"))["cases"]) == 1

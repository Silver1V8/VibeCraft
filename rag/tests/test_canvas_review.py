"""Test del 'canvas che apprende' (parte 1): estrazione sezioni, raccolta diff
(fallback tasks.md), prompt di review, generazione con LLM iniettato e integrazione
in archive_feature (review salvata + copia storica, oppure skip con warning nel
meta.json della change senza far fallire l'archive). Nessun LLM né Qdrant reale."""
import json

import pytest

from core import canvas_review as cr
from core import indexing as index

CANVAS = """# REASONS Canvas: demo

## Requirements
Requisiti generici.

## Operations
- L'endpoint /api/demo salva l'evento su file.

## Structure
- Modulo core/demo.py con funzione save_event().

## Norms
Norme varie.

## Safeguards
- Input validato prima della scrittura.
"""


def _make_change(tmp_path, name="feat-demo", with_canvas=True):
    change_dir = tmp_path / "changes" / name
    change_dir.mkdir(parents=True)
    if with_canvas:
        (change_dir / "canvas.md").write_text(CANVAS, encoding="utf-8")
    return change_dir


def test_extract_canvas_sections_picks_only_review_sections():
    out = cr.extract_canvas_sections(CANVAS)
    assert "/api/demo" in out and "core/demo.py" in out and "Input validato" in out
    assert "Requisiti generici" not in out and "Norme varie" not in out


def test_collect_change_diff_fallback_tasks_md(tmp_path):
    change_dir = _make_change(tmp_path)
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "demo.py").write_text("def save_event():\n    pass\n", encoding="utf-8")
    (change_dir / "tasks.md").write_text(
        "- [x] Implementare `code/demo.py`\n- [ ] altro task senza file\n", encoding="utf-8"
    )
    # tmp_path non è un repo git -> il ramo git restituisce '' e scatta il fallback.
    diff = cr.collect_change_diff("feat-demo", change_dir, repo_root=tmp_path)
    assert "--- FILE: code/demo.py ---" in diff
    assert "def save_event" in diff


def test_collect_change_diff_empty_when_nothing_available(tmp_path):
    change_dir = _make_change(tmp_path)
    assert cr.collect_change_diff("feat-demo", change_dir, repo_root=tmp_path) == ""


def test_build_review_prompt_contains_sections_diff_and_fidelity_scale():
    prompt = cr.build_canvas_review_prompt("feat-demo", "SEZIONI QUI", "DIFF QUI")
    assert "SEZIONI QUI" in prompt and "DIFF QUI" in prompt
    for word in ("Divergenze", "Sezioni accurate", "Fedeltà", "alto", "medio", "basso"):
        assert word in prompt


def test_generate_canvas_review_success_with_injected_llm(tmp_path):
    change_dir = _make_change(tmp_path)
    seen = {}

    def fake_llm(prompt):
        seen["prompt"] = prompt
        return "## Divergenze\nNessuna.\n\n## Sezioni accurate\nTutte.\n\n## Fedeltà\nFedeltà: alto"

    content, warning = cr.generate_canvas_review("feat-demo", change_dir, repo_root=tmp_path, llm=fake_llm)
    assert warning is None
    assert content.startswith("# Canvas Review: feat-demo")
    assert "Fedeltà: alto" in content
    assert "/api/demo" in seen["prompt"]  # le sezioni del canvas finiscono nel prompt


def test_generate_canvas_review_llm_unreachable_returns_warning(tmp_path):
    change_dir = _make_change(tmp_path)

    def broken_llm(prompt):
        raise ConnectionError("Ollama giù")

    content, warning = cr.generate_canvas_review("feat-demo", change_dir, repo_root=tmp_path, llm=broken_llm)
    assert content is None
    assert "Ollama giù" in warning


def test_generate_canvas_review_missing_canvas(tmp_path):
    change_dir = _make_change(tmp_path, with_canvas=False)
    content, warning = cr.generate_canvas_review("feat-demo", change_dir, repo_root=tmp_path)
    assert content is None and "canvas.md assente" in warning


REVIEW_TEXT = """# Canvas Review: feat-old

## Divergenze
- Il codice valida l'input, il canvas non lo prevedeva.
- Manca la gestione errori promessa nei Safeguards.

## Sezioni accurate
Structure fedele.

## Fedeltà
Fedeltà: medio — divergenze minori.
"""


def test_is_review_doc():
    assert cr.is_review_doc("03_changes_historical/feat-x-canvas-review.md")
    assert cr.is_review_doc("03_changes_historical\\feat-x-canvas-review.md")
    assert not cr.is_review_doc("02_specs_normative/spec.md")
    assert not cr.is_review_doc("03_changes_historical/nota.md")


def test_parse_fidelity_and_divergences():
    assert cr.parse_fidelity(REVIEW_TEXT) == "medio"
    assert cr.parse_fidelity("nessun giudizio") is None
    divs = cr.parse_divergences(REVIEW_TEXT)
    assert len(divs) == 2 and "valida l'input" in divs[0]
    assert cr.parse_divergences("## Divergenze\nNessuna divergenza rilevata.\n") == []


def _fake_resources():
    """Risorse finte per retrieve_canvas_lessons: due review + un doc normativo."""
    chunks_store = {
        "03_changes_historical/feat-old-canvas-review.md#01-divergenze": {
            "doc_id": "03_changes_historical/feat-old-canvas-review.md",
            "section": "Divergenze", "text": "- Il codice valida l'input, il canvas no.",
        },
        "03_changes_historical/feat-old-canvas-review.md#03-fedelta": {
            "doc_id": "03_changes_historical/feat-old-canvas-review.md",
            "section": "Fedeltà", "text": "Fedeltà: medio",
        },
        "03_changes_historical/feat-old-canvas-review.md#02-accurate": {
            "doc_id": "03_changes_historical/feat-old-canvas-review.md",
            "section": "Sezioni accurate", "text": "Structure fedele.",
        },
        "02_specs_normative/spec.md#00-doc": {
            "doc_id": "02_specs_normative/spec.md", "section": "(documento)", "text": "norme",
        },
    }
    results = [
        {"doc_id": "02_specs_normative/spec.md"},
        {"doc_id": "03_changes_historical/feat-old-canvas-review.md"},
        {"doc_id": "03_changes_historical/feat-old-canvas-review.md"},
    ]
    return chunks_store, results


def test_retrieve_canvas_lessons_extracts_divergences_and_fidelity():
    chunks_store, results = _fake_resources()
    lessons = cr.retrieve_canvas_lessons(
        "nuova feature simile", qdrant=object(), embed_model=object(), colbert_store={},
        chunks_store=chunks_store, search=lambda q, k, **kw: results,
    )
    assert "Lezioni dalla change 'feat-old'" in lessons
    assert "valida l'input" in lessons and "Fedeltà: medio" in lessons
    assert "Structure fedele" not in lessons  # le sezioni accurate non sono lezioni
    assert "norme" not in lessons             # i doc non-review sono esclusi


def test_retrieve_canvas_lessons_empty_without_reviews_or_resources():
    chunks_store, _ = _fake_resources()
    # nessun hit review -> ''
    no_reviews = cr.retrieve_canvas_lessons(
        "q", qdrant=object(), embed_model=object(), colbert_store={},
        chunks_store=chunks_store, search=lambda q, k, **kw: [{"doc_id": "02_specs_normative/spec.md"}],
    )
    assert no_reviews == ""
    # risorse non pronte -> ''
    assert cr.retrieve_canvas_lessons("q", qdrant=None, embed_model=None,
                                      colbert_store={}, chunks_store={}) == ""
    # retrieval che esplode -> '' (mai errore)
    def boom(q, k, **kw): raise RuntimeError("indice giù")
    assert cr.retrieve_canvas_lessons("q", qdrant=object(), embed_model=object(),
                                      colbert_store={}, chunks_store=chunks_store, search=boom) == ""


def test_build_canvas_prompt_with_and_without_lessons():
    from core import pipeline
    without = pipeline.build_canvas_prompt("Feat", "log", "ctx")
    assert "Lezioni dalle change precedenti" not in without
    with_lessons = pipeline.build_canvas_prompt("Feat", "log", "ctx", "", "- punto cieco X")
    assert "Lezioni dalle change precedenti" in with_lessons and "punto cieco X" in with_lessons
    # senza lezioni il prompt resta byte-per-byte quello di prima
    assert without == pipeline.build_canvas_prompt("Feat", "log", "ctx", "", "")


def _write_review(archive_dir, feature, fidelity, divergences, mtime=None):
    d = archive_dir / feature
    d.mkdir(parents=True)
    bullets = "\n".join(f"- {x}" for x in divergences) or "Nessuna divergenza rilevata."
    p = d / "canvas_review.md"
    p.write_text(
        f"# Canvas Review: {feature}\n\n## Divergenze\n{bullets}\n\n"
        f"## Sezioni accurate\nTutte.\n\n## Fedeltà\nFedeltà: {fidelity}\n",
        encoding="utf-8",
    )
    if mtime is not None:
        import os
        os.utime(p, (mtime, mtime))


def test_canvas_quality_stats(tmp_path):
    archive = tmp_path / "archive"
    _write_review(archive, "feat-a", "alto", [], mtime=1000)
    _write_review(archive, "feat-b", "basso", ["manca la gestione errori", "endpoint non previsto"], mtime=2000)
    _write_review(archive, "feat-c", "medio", ["Manca la gestione errori."], mtime=3000)
    stats = cr.canvas_quality_stats(archive, last_n=10)
    assert stats["total_reviews"] == 3
    assert [t["feature"] for t in stats["trend"]] == ["feat-a", "feat-b", "feat-c"]  # per mtime
    assert stats["fidelity_counts"] == {"alto": 1, "medio": 1, "basso": 1, "sconosciuto": 0}
    top = stats["top_divergences"]
    assert top[0]["text"] == "manca la gestione errori" and top[0]["count"] == 2  # normalizzata
    # last_n limita alla coda più recente
    assert [t["feature"] for t in cr.canvas_quality_stats(archive, last_n=2)["trend"]] == ["feat-b", "feat-c"]


def test_canvas_quality_stats_empty_archive(tmp_path):
    stats = cr.canvas_quality_stats(tmp_path / "non-esiste")
    assert stats["total_reviews"] == 0 and stats["trend"] == [] and stats["top_divergences"] == []


@pytest.fixture
def archive_env(tmp_path, monkeypatch):
    """Ambiente isolato per archive_feature: changes/ e docs/ temporanee, nessuna
    re-indicizzazione reale."""
    changes = tmp_path / "changes"
    docs = tmp_path / "docs"
    docs.mkdir()
    monkeypatch.setattr(index, "CHANGES_DIR", changes)
    monkeypatch.setattr(index, "DOCS_DIR", docs)
    monkeypatch.setattr(index, "build_graph_and_index", lambda **kw: None)
    return tmp_path


def test_archive_saves_review_and_historical_copy(archive_env, monkeypatch):
    _make_change(archive_env)
    monkeypatch.setattr(
        index, "generate_canvas_review",
        lambda folder, change_dir, **kw: ("# Canvas Review: feat-demo\n\nFedeltà: alto\n", None),
    )
    log = index.archive_feature("feat-demo", emit=lambda m: None)
    archived = archive_env / "changes" / "archive" / "feat-demo"
    assert archived.exists()
    assert (archived / "canvas_review.md").read_text(encoding="utf-8").startswith("# Canvas Review")
    historical = archive_env / "docs" / cr.HISTORICAL_SUBDIR / "feat-demo-canvas-review.md"
    assert historical.exists()  # entra nel reindex come contesto storico
    assert "Canvas review salvata" in log


def test_archive_skips_review_with_warning_when_llm_down(archive_env, monkeypatch):
    _make_change(archive_env)
    monkeypatch.setattr(
        index, "generate_canvas_review",
        lambda folder, change_dir, **kw: (None, "LLM non raggiungibile o review fallita: connessione rifiutata"),
    )
    log = index.archive_feature("feat-demo", emit=lambda m: None)
    archived = archive_env / "changes" / "archive" / "feat-demo"
    assert archived.exists()  # l'archive NON fallisce
    assert not (archived / "canvas_review.md").exists()
    assert "⚠️ Canvas review saltata" in log
    meta = json.loads((archived / "meta.json").read_text(encoding="utf-8"))
    assert meta["canvas_review"]["status"] == "skipped"
    assert "non raggiungibile" in meta["canvas_review"]["reason"]


def test_collect_change_diff_ignora_slug_solo_nel_corpo_del_commit(tmp_path):
    """Un commit che nomina lo slug solo nel corpo (es. 'misurato su BE1') non è codice della change."""
    import subprocess
    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@t"); git("config", "user.name", "t")
    (tmp_path / "a.py").write_text("x = 1\n")
    git("add", "."); git("commit", "-qm", "base")
    (tmp_path / "a.py").write_text("x = 2\n")
    git("add", "."); git("commit", "-qm", "feat(drift): altro", "-m", "Misurato su BE1.")
    assert cr.collect_change_diff("be1", tmp_path / "nochange", repo_root=tmp_path) == ""
    (tmp_path / "a.py").write_text("x = 3\n")
    git("add", "."); git("commit", "-qm", "feat(be1): codice vero")
    assert "+x = 3" in cr.collect_change_diff("be1", tmp_path / "nochange", repo_root=tmp_path)


def test_generate_canvas_review_tronca_diff_oltre_la_finestra(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "OLLAMA_NUM_CTX", 1000)
    monkeypatch.setattr(cr, "collect_change_diff", lambda *a, **k: "+riga\n" * 5000)
    change_dir = _make_change(tmp_path)
    seen = {}
    def fake_llm(prompt):
        seen["prompt"] = prompt
        return "## Fedeltà\nFedeltà: medio"
    content, warning = cr.generate_canvas_review("feat-demo", change_dir, repo_root=tmp_path, llm=fake_llm)
    assert warning is None
    assert "diff troncato" in seen["prompt"]
    assert len(seen["prompt"]) // 3 < 1000


def test_archive_passa_alla_review_il_codice_del_drift(archive_env, monkeypatch):
    """La review riceve il codice di code/<dev_type> (quello del check drift), senza i test."""
    change_dir = _make_change(archive_env)
    (change_dir / "meta.json").write_text('{"dev_type": "backend"}', encoding="utf-8")
    code = archive_env / "code" / "backend"
    (code / "tests").mkdir(parents=True)
    (code / "Reporting.cs").write_text("class Reporting {}", encoding="utf-8")
    (code / "tests" / "ReportingTests.cs").write_text("class ReportingTests {}", encoding="utf-8")
    monkeypatch.setattr(index, "CODE_DIR", archive_env / "code")
    seen = {}

    def fake_review(folder, change_dir, **kw):
        seen["code"] = kw["code"]
        return None, "test"

    monkeypatch.setattr(index, "generate_canvas_review", fake_review)
    index.archive_feature("feat-demo", emit=lambda m: None)
    assert "--- FILE: Reporting.cs ---\nclass Reporting {}" in seen["code"]
    assert "ReportingTests" not in seen["code"]


def test_generate_canvas_review_passa_la_spec_con_precedenza(tmp_path):
    change_dir = _make_change(tmp_path)
    (change_dir / "spec.md").write_text("SCENARIO: S04 - capienza >= 5", encoding="utf-8")
    seen = {}

    def fake_llm(prompt):
        seen["prompt"] = prompt
        return "## Fedeltà\nFedeltà: alto"

    cr.generate_canvas_review("feat-demo", change_dir, repo_root=tmp_path, llm=fake_llm, code="x")
    assert "S04 - capienza >= 5" in seen["prompt"]
    assert "PRECEDENZA" in seen["prompt"]
    assert "SPEC DELLA FEATURE" not in cr.build_canvas_review_prompt("f", "s", "d")

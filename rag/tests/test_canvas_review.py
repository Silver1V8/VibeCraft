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
        lambda folder, change_dir: ("# Canvas Review: feat-demo\n\nFedeltà: alto\n", None),
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
        lambda folder, change_dir: (None, "LLM non raggiungibile o review fallita: connessione rifiutata"),
    )
    log = index.archive_feature("feat-demo", emit=lambda m: None)
    archived = archive_env / "changes" / "archive" / "feat-demo"
    assert archived.exists()  # l'archive NON fallisce
    assert not (archived / "canvas_review.md").exists()
    assert "⚠️ Canvas review saltata" in log
    meta = json.loads((archived / "meta.json").read_text(encoding="utf-8"))
    assert meta["canvas_review"]["status"] == "skipped"
    assert "non raggiungibile" in meta["canvas_review"]["reason"]

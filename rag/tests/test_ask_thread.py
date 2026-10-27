"""WP1: unit tests for core.ask_thread storage (schema, caps, merge, fingerprint).

HTTP routes /ask wiring are out of scope here — covered by later WPs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import ask_thread as at
from core.projects import ProjectContext, ProjectRegistry


def _registry(tmp_path: Path) -> ProjectRegistry:
    return ProjectRegistry(tmp_path / "projects", bootstrap_legacy=False)


def _project(tmp_path: Path, name: str = "Acme") -> ProjectContext:
    return _registry(tmp_path).create(name)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
def test_project_create_includes_database_ask(tmp_path):
    project = _project(tmp_path)
    assert (project.database_dir / "ask").is_dir()
    assert at.thread_path(project) == project.database_dir / "ask" / "thread.json"


def test_ensure_ask_dir_is_idempotent(tmp_path):
    project = _project(tmp_path)
    first = at.ensure_ask_dir(project)
    second = at.ensure_ask_dir(project)
    assert first == second == project.database_dir / "ask"
    assert first.is_dir()


# ---------------------------------------------------------------------------
# Empty / corrupt / missing
# ---------------------------------------------------------------------------
def test_load_missing_file_returns_empty_thread(tmp_path):
    project = _project(tmp_path)
    path = at.thread_path(project)
    assert not path.exists()
    thread = at.load_thread(project)
    assert thread["schema_version"] == 1
    assert thread["project_id"] == project.id
    assert thread["turns"] == []
    assert thread["citations"] == []
    assert thread["max_turns"] == at.DEFAULT_MAX_TURNS


def test_load_corrupt_json_returns_empty_thread(tmp_path):
    project = _project(tmp_path)
    path = at.thread_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    thread = at.load_thread(project)
    assert thread["turns"] == [] and thread["citations"] == []
    assert thread["project_id"] == project.id


def test_load_wrong_schema_version_returns_empty_thread(tmp_path):
    project = _project(tmp_path)
    path = at.thread_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 99,
        "project_id": project.id,
        "turns": [{"question": "x"}],
        "citations": [],
    }), encoding="utf-8")
    thread = at.load_thread(project)
    assert thread["turns"] == []


def test_load_wrong_project_id_returns_empty_thread(tmp_path):
    project = _project(tmp_path)
    path = at.thread_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1,
        "project_id": "other-project",
        "max_turns": 4,
        "turns": [{"turn_id": "t-1", "question": "q"}],
        "citations": [],
    }), encoding="utf-8")
    thread = at.load_thread(project)
    assert thread["turns"] == []


def test_load_empty_file_returns_empty_thread(tmp_path):
    project = _project(tmp_path)
    path = at.thread_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("   \n", encoding="utf-8")
    assert at.load_thread(project)["turns"] == []


# ---------------------------------------------------------------------------
# Save / reset / roundtrip
# ---------------------------------------------------------------------------
def test_save_load_roundtrip(tmp_path):
    project = _project(tmp_path)
    thread = at.empty_thread(project.id, max_turns=4)
    at.append_turn(
        thread,
        at.build_turn(question="Q1?", answer_excerpt="A1", status="success",
                      index_version="v1", retrieval_strategy="hybrid",
                      citation_ids=["doc_a.md"]),
        citations=[{
            "doc_id": "doc_a.md",
            "last_score": 0.81,
            "authority": 0.9,
            "chunk_ids": ["doc_a.md#1"],
        }],
    )
    saved = at.save_thread(project, thread)
    loaded = at.load_thread(project)
    assert loaded["project_id"] == project.id
    assert len(loaded["turns"]) == 1
    assert loaded["turns"][0]["question"] == "Q1?"
    assert loaded["turns"][0]["answer_excerpt"] == "A1"
    assert loaded["citations"][0]["doc_id"] == "doc_a.md"
    assert loaded["citations"][0]["last_score"] == pytest.approx(0.81)
    assert saved["turns"][0]["turn_id"] == loaded["turns"][0]["turn_id"]
    assert at.thread_path(project).is_file()


def test_reset_thread_clears_turns_and_citations(tmp_path):
    project = _project(tmp_path)
    thread = at.empty_thread(project.id)
    at.append_turn(thread, at.build_turn(question="keep?"),
                   citations=[{"doc_id": "x.md", "last_score": 0.5}])
    at.save_thread(project, thread)
    reset = at.reset_thread(project)
    assert reset["turns"] == [] and reset["citations"] == []
    assert at.load_thread(project)["turns"] == []
    # Idempotent
    again = at.reset_thread(project)
    assert again["turns"] == [] and again["citations"] == []


def test_save_is_atomic_no_orphan_tmp(tmp_path):
    project = _project(tmp_path)
    thread = at.empty_thread(project.id)
    at.append_turn(thread, at.build_turn(question="q"))
    at.save_thread(project, thread)
    ask = project.database_dir / "ask"
    names = sorted(p.name for p in ask.iterdir())
    assert names == ["thread.json"]


# ---------------------------------------------------------------------------
# Turn FIFO cap
# ---------------------------------------------------------------------------
def test_turn_fifo_cap_drops_oldest(tmp_path):
    project = _project(tmp_path)
    thread = at.empty_thread(project.id, max_turns=4)
    for i in range(5):
        at.append_turn(thread, at.build_turn(question=f"Q{i}", turn_id=f"t-{i:08d}"))
    assert len(thread["turns"]) == 4
    assert [t["question"] for t in thread["turns"]] == ["Q1", "Q2", "Q3", "Q4"]
    assert thread["turns"][0]["turn_id"] == "t-00000001"
    at.save_thread(project, thread)
    loaded = at.load_thread(project)
    assert [t["question"] for t in loaded["turns"]] == ["Q1", "Q2", "Q3", "Q4"]


def test_apply_turn_cap_helper():
    turns = [{"question": str(i)} for i in range(6)]
    assert at.apply_turn_cap(turns, 4) == turns[-4:]
    assert at.apply_turn_cap(turns, 10) == turns
    assert len(at.apply_turn_cap(turns, 0)) == 1  # floor at 1


def test_max_turns_from_env(monkeypatch):
    monkeypatch.setenv("VIBECRAFT_ASK_THREAD_MAX_TURNS", "2")
    assert at.max_turns_from_env() == 2
    monkeypatch.setenv("VIBECRAFT_ASK_THREAD_MAX_TURNS", "nope")
    assert at.max_turns_from_env() == at.DEFAULT_MAX_TURNS
    monkeypatch.setenv("VIBECRAFT_ASK_THREAD_MAX_TURNS", "0")
    assert at.max_turns_from_env() == 1


# ---------------------------------------------------------------------------
# Citation merge / cap
# ---------------------------------------------------------------------------
def test_merge_citations_dedupes_and_keeps_best_score():
    existing = [{
        "doc_id": "a.md",
        "last_score": 0.4,
        "authority": 0.5,
        "last_seen_turn_id": "t-old",
        "chunk_ids": ["a.md#1"],
    }]
    incoming = [
        {
            "doc_id": "a.md",
            "last_score": 0.9,
            "authority": 0.8,
            "chunk_ids": ["a.md#2"],
        },
        {
            "doc_id": "b.md",
            "last_score": 0.3,
            "authority": 0.2,
            "chunk_ids": ["b.md#1"],
        },
    ]
    merged = at.merge_citations(existing, incoming, turn_id="t-new")
    by_id = {c["doc_id"]: c for c in merged}
    assert set(by_id) == {"a.md", "b.md"}
    assert by_id["a.md"]["last_score"] == pytest.approx(0.9)
    assert by_id["a.md"]["authority"] == pytest.approx(0.8)
    assert by_id["a.md"]["last_seen_turn_id"] == "t-new"
    assert by_id["a.md"]["chunk_ids"] == ["a.md#1", "a.md#2"]
    assert by_id["b.md"]["last_seen_turn_id"] == "t-new"


def test_merge_citations_hard_cap_keeps_highest_scores():
    incoming = [
        {"doc_id": f"doc_{i}.md", "last_score": i / 100.0, "authority": 0.1}
        for i in range(30)
    ]
    merged = at.merge_citations([], incoming, max_citations=24)
    assert len(merged) == 24
    scores = sorted(c["last_score"] for c in merged)
    assert scores[0] >= 0.06  # lowest kept is among the top 24 (6..29)
    assert max(c["last_score"] for c in merged) == pytest.approx(0.29)


def test_append_turn_merges_citations_into_thread():
    thread = at.empty_thread("p", max_turns=4)
    t1 = at.build_turn(question="q1", turn_id="t-aaaaaaaa")
    at.append_turn(thread, t1, citations=[
        {"doc_id": "a.md", "last_score": 0.5, "authority": 0.4},
    ])
    t2 = at.build_turn(question="q2", turn_id="t-bbbbbbbb")
    at.append_turn(thread, t2, citations=[
        {"doc_id": "a.md", "last_score": 0.7, "authority": 0.6},
        {"doc_id": "b.md", "last_score": 0.2, "authority": 0.3},
    ])
    assert len(thread["citations"]) == 2
    a = next(c for c in thread["citations"] if c["doc_id"] == "a.md")
    assert a["last_score"] == pytest.approx(0.7)
    assert a["last_seen_turn_id"] == "t-bbbbbbbb"


def test_merge_skips_invalid_citation_rows():
    merged = at.merge_citations(
        [{"doc_id": "ok.md", "last_score": 0.1}],
        [None, "x", {}, {"doc_id": ""}, {"doc_id": "  "}, {"doc_id": "ok2.md", "last_score": "bad"}],
    )
    assert [c["doc_id"] for c in merged] == ["ok.md", "ok2.md"]
    assert merged[1]["last_score"] == 0.0


# ---------------------------------------------------------------------------
# Answer excerpt truncation
# ---------------------------------------------------------------------------
def test_answer_excerpt_hard_char_cap():
    long = "x" * (at.ANSWER_EXCERPT_MAX_CHARS + 50)
    excerpt = at.truncate_answer_excerpt(long)
    assert len(excerpt) == at.ANSWER_EXCERPT_MAX_CHARS
    assert excerpt.endswith("…")
    turn = at.build_turn(question="q", answer_excerpt=long)
    assert len(turn["answer_excerpt"]) == at.ANSWER_EXCERPT_MAX_CHARS


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------
def test_fingerprint_empty_is_blank():
    assert at.fingerprint(None) == ""
    assert at.fingerprint({}) == ""
    assert at.fingerprint(at.empty_thread("p")) == ""


def test_fingerprint_changes_on_append_and_reset(tmp_path):
    project = _project(tmp_path)
    thread = at.empty_thread(project.id)
    assert at.fingerprint(thread) == ""
    at.append_turn(thread, at.build_turn(question="Q1", turn_id="t-11111111"))
    fp1 = at.fingerprint(thread)
    assert fp1.startswith("1:t-11111111:")
    at.append_turn(thread, at.build_turn(question="Q2", turn_id="t-22222222"))
    fp2 = at.fingerprint(thread)
    assert fp2.startswith("2:t-22222222:")
    assert fp1 != fp2
    at.save_thread(project, thread)
    loaded = at.load_thread(project)
    assert at.fingerprint(loaded) == fp2
    reset = at.reset_thread(project)
    assert at.fingerprint(reset) == ""


def test_fingerprint_stable_for_same_content():
    thread = at.empty_thread("p")
    at.append_turn(thread, at.build_turn(
        question="same", turn_id="t-aaaaaaaa", status="success", index_version="v1",
    ))
    assert at.fingerprint(thread) == at.fingerprint(dict(thread))


# ---------------------------------------------------------------------------
# Isolation / path safety
# ---------------------------------------------------------------------------
def test_threads_are_isolated_per_project(tmp_path):
    store = _registry(tmp_path)
    a, b = store.create("Alpha"), store.create("Beta")
    ta = at.empty_thread(a.id)
    at.append_turn(ta, at.build_turn(question="only-a"))
    at.save_thread(a, ta)
    assert at.load_thread(a)["turns"][0]["question"] == "only-a"
    assert at.load_thread(b)["turns"] == []
    assert at.thread_path(a) != at.thread_path(b)
    assert at.thread_path(a).is_relative_to(a.database_dir)
    assert at.thread_path(b).is_relative_to(b.database_dir)


def test_thread_summary_shape():
    thread = at.empty_thread("p", max_turns=4)
    at.append_turn(
        thread,
        at.build_turn(question="Q?", status="success", turn_id="t-cccccccc",
                      index_version="v9"),
        citations=[{"doc_id": "d.md", "last_score": 0.5, "authority": 0.4}],
    )
    summary = at.thread_summary(thread)
    assert summary["turn_count"] == 1
    assert summary["max_turns"] == 4
    assert summary["fingerprint"].startswith("1:t-cccccccc:")
    assert summary["citations"][0]["doc_id"] == "d.md"
    assert summary["turns"][0]["question"] == "Q?"
    assert "answer_excerpt" not in summary["turns"][0]

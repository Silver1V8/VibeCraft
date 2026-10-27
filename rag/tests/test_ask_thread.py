"""Ask-thread storage (WP1), HTTP API (WP2), and WP6 unit/API matrix.

WP3 /ask wiring coverage lives in test_ask_thread_wiring.py.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import deps, routes_retrieval
from core import ask_thread as at
from core.ask_thread import AskThreadStorageError
from core.projects import ProjectRegistry

_SHARED_JS = Path(__file__).parents[1] / "static" / "shared.js"


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


# ---------------------------------------------------------------------------
# WP2 — GET/DELETE /api/ask/thread
# ---------------------------------------------------------------------------
def _thread_api_client(tmp_path, monkeypatch):
    """Minimal app: retrieval router only; project registry under tmp_path."""
    registry = ProjectRegistry(tmp_path / "projects", bootstrap_legacy=False)
    monkeypatch.setattr(deps, "project_registry", lambda: registry, raising=False)
    app = FastAPI()
    app.include_router(routes_retrieval.router)
    client = TestClient(app, client=("127.0.0.1", 54321))
    return client, registry


def test_api_get_empty_thread_when_missing(tmp_path, monkeypatch):
    client, registry = _thread_api_client(tmp_path, monkeypatch)
    project = registry.create("Acme")
    headers = {"X-VibeCraft-Project": project.id}
    resp = client.get("/api/ask/thread", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == project.id
    thread = body["thread"]
    assert thread["turn_count"] == 0
    assert thread["turns"] == []
    assert thread["citations"] == []
    assert thread["fingerprint"] == ""
    assert thread["max_turns"] == at.DEFAULT_MAX_TURNS
    assert isinstance(thread["updated_at"], str) and thread["updated_at"]


def test_api_get_returns_saved_thread(tmp_path, monkeypatch):
    client, registry = _thread_api_client(tmp_path, monkeypatch)
    project = registry.create("Acme")
    thread = at.empty_thread(project.id)
    at.append_turn(
        thread,
        at.build_turn(question="Vincoli sulla privacy?", turn_id="t-aaaaaaaa",
                      status="success", index_version="v1"),
        citations=[{"doc_id": "privacy.md", "last_score": 0.9}],
    )
    at.save_thread(project, thread)
    resp = client.get("/api/ask/thread", headers={"X-VibeCraft-Project": project.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == project.id
    assert body["thread"]["turn_count"] == 1
    assert body["thread"]["turns"][0]["question"] == "Vincoli sulla privacy?"
    assert body["thread"]["turns"][0]["turn_id"] == "t-aaaaaaaa"
    assert "answer_excerpt" not in body["thread"]["turns"][0]
    assert body["thread"]["citations"][0]["doc_id"] == "privacy.md"
    assert body["thread"]["fingerprint"].startswith("1:t-aaaaaaaa:")


def test_api_get_corrupt_file_returns_empty_thread(tmp_path, monkeypatch):
    client, registry = _thread_api_client(tmp_path, monkeypatch)
    project = registry.create("Acme")
    path = at.thread_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    resp = client.get("/api/ask/thread", headers={"X-VibeCraft-Project": project.id})
    assert resp.status_code == 200
    assert resp.json()["thread"]["turn_count"] == 0
    assert resp.json()["thread"]["turns"] == []


def test_api_delete_resets_thread_idempotently(tmp_path, monkeypatch):
    client, registry = _thread_api_client(tmp_path, monkeypatch)
    project = registry.create("Acme")
    headers = {"X-VibeCraft-Project": project.id}
    thread = at.empty_thread(project.id)
    at.append_turn(thread, at.build_turn(question="Q1", turn_id="t-11111111"))
    at.save_thread(project, thread)
    assert at.load_thread(project)["turns"]

    first = client.delete("/api/ask/thread", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["thread"]["turn_count"] == 0
    assert first.json()["thread"]["turns"] == []
    assert first.json()["thread"]["citations"] == []
    assert first.json()["thread"]["fingerprint"] == ""
    assert at.load_thread(project)["turns"] == []

    second = client.delete("/api/ask/thread", headers=headers)
    assert second.status_code == 200
    assert second.json()["thread"]["turn_count"] == 0
    assert client.get("/api/ask/thread", headers=headers).json()["thread"]["turn_count"] == 0


def test_api_thread_project_isolation(tmp_path, monkeypatch):
    client, registry = _thread_api_client(tmp_path, monkeypatch)
    a, b = registry.create("Alpha"), registry.create("Beta")
    ta = at.empty_thread(a.id)
    at.append_turn(ta, at.build_turn(question="only-alpha", turn_id="t-aaaaaaaa"))
    at.save_thread(a, ta)

    got_a = client.get("/api/ask/thread", headers={"X-VibeCraft-Project": a.id}).json()
    got_b = client.get("/api/ask/thread", headers={"X-VibeCraft-Project": b.id}).json()
    assert got_a["project_id"] == a.id
    assert got_a["thread"]["turns"][0]["question"] == "only-alpha"
    assert got_b["project_id"] == b.id
    assert got_b["thread"]["turn_count"] == 0
    assert got_b["thread"]["turns"] == []

    # Reset A must not create/alter B's thread content.
    reset_a = client.delete("/api/ask/thread", headers={"X-VibeCraft-Project": a.id})
    assert reset_a.status_code == 200
    assert reset_a.json()["thread"]["turn_count"] == 0
    assert client.get("/api/ask/thread", headers={"X-VibeCraft-Project": b.id}).json()[
        "thread"
    ]["turn_count"] == 0
    # Seed B after A's reset and confirm A stays empty.
    tb = at.empty_thread(b.id)
    at.append_turn(tb, at.build_turn(question="only-beta", turn_id="t-bbbbbbbb"))
    at.save_thread(b, tb)
    assert client.get("/api/ask/thread", headers={"X-VibeCraft-Project": a.id}).json()[
        "thread"
    ]["turn_count"] == 0
    assert client.get("/api/ask/thread", headers={"X-VibeCraft-Project": b.id}).json()[
        "thread"
    ]["turns"][0]["question"] == "only-beta"


def test_api_thread_requires_project_header(tmp_path, monkeypatch):
    client, registry = _thread_api_client(tmp_path, monkeypatch)
    registry.create("Acme")
    for method in ("get", "delete"):
        resp = getattr(client, method)("/api/ask/thread")
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["code"] == "project_required"


def test_api_thread_storage_error_maps_to_503(tmp_path, monkeypatch):
    client, registry = _thread_api_client(tmp_path, monkeypatch)
    project = registry.create("Acme")
    headers = {"X-VibeCraft-Project": project.id}
    err = AskThreadStorageError("Archiviazione ask-thread non disponibile.")

    with patch.object(routes_retrieval.ask_thread, "load_thread", side_effect=err):
        resp = client.get("/api/ask/thread", headers=headers)
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "project_storage_error"

    with patch.object(routes_retrieval.ask_thread, "reset_thread", side_effect=err):
        resp = client.delete("/api/ask/thread", headers=headers)
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "project_storage_error"


def test_api_delete_rejects_cross_site_without_key(tmp_path, monkeypatch):
    client, registry = _thread_api_client(tmp_path, monkeypatch)
    project = registry.create("Acme")
    monkeypatch.setattr(deps, "API_KEY", None)
    resp = client.delete(
        "/api/ask/thread",
        headers={"X-VibeCraft-Project": project.id, "Sec-Fetch-Site": "cross-site"},
    )
    assert resp.status_code == 403
    assert "cross-site" in resp.json()["detail"]


def test_api_get_allows_cross_site_read(tmp_path, monkeypatch):
    """GET is read-only: anti-cross-site must not block legitimate embedding/nav."""
    client, registry = _thread_api_client(tmp_path, monkeypatch)
    project = registry.create("Acme")
    monkeypatch.setattr(deps, "API_KEY", None)
    resp = client.get(
        "/api/ask/thread",
        headers={"X-VibeCraft-Project": project.id, "Sec-Fetch-Site": "cross-site"},
    )
    assert resp.status_code == 200
    assert resp.json()["thread"]["turn_count"] == 0


# ---------------------------------------------------------------------------
# WP6 — remaining unit / API matrix (caps, merge helpers, fingerprint, allowlist)
# ---------------------------------------------------------------------------
def test_citations_from_qdrant_scores_maps_score_fields():
    rows = [
        {"doc_id": "a.md", "chunk_id": "a.md#1", "score": 0.9, "authority": 0.8},
        {"doc_id": "b.md", "chunk_id": "b.md#2", "colbert_score": 0.7},
        {"doc_id": "c.md", "dense_score": 0.4, "authority": "bad"},
        {"doc_id": "  ", "score": 1.0},
        {"chunk_id": "orphan"},
        None,
    ]
    cites = at.citations_from_qdrant_scores(rows)
    by_id = {c["doc_id"]: c for c in cites}
    assert set(by_id) == {"a.md", "b.md", "c.md"}
    assert by_id["a.md"]["last_score"] == pytest.approx(0.9)
    assert by_id["a.md"]["chunk_ids"] == ["a.md#1"]
    assert by_id["b.md"]["last_score"] == pytest.approx(0.7)
    assert by_id["c.md"]["last_score"] == pytest.approx(0.4)
    assert by_id["c.md"]["authority"] == 0.0


def test_index_version_changed_helper():
    thread = at.empty_thread("p")
    assert at.index_version_changed(None, "v1") is False
    assert at.index_version_changed(thread, "v1") is False
    at.append_turn(thread, at.build_turn(question="q", index_version="v-old"))
    assert at.index_version_changed(thread, "v-old") is False
    assert at.index_version_changed(thread, "v-new") is True
    assert at.index_version_changed(thread, None) is False


def test_thread_summary_index_version_changed_flag():
    thread = at.empty_thread("p", max_turns=4)
    at.append_turn(
        thread,
        at.build_turn(question="Q", status="success", index_version="v1"),
        citations=[{"doc_id": "d.md", "last_score": 0.5}],
    )
    same = at.thread_summary(thread, current_index_version="v1")
    stale = at.thread_summary(thread, current_index_version="v2")
    assert same["index_version_changed"] is False
    assert stale["index_version_changed"] is True


def test_thread_file_survives_reload_from_disk(tmp_path):
    """Acceptance #6: state under project database survives a process-style reload."""
    project = _project(tmp_path)
    thread = at.empty_thread(project.id, max_turns=4)
    at.append_turn(
        thread,
        at.build_turn(question="persist?", answer_excerpt="yes", turn_id="t-persist1",
                      index_version="v9"),
        citations=[{"doc_id": "n.md", "last_score": 0.66, "authority": 0.5}],
    )
    at.save_thread(project, thread)
    path = at.thread_path(project)
    assert path.is_file()
    assert path.is_relative_to(project.database_dir)
    # Fresh load (no in-memory handle) — same as after server restart.
    reloaded = at.load_thread(project)
    assert reloaded["turns"][0]["question"] == "persist?"
    assert reloaded["citations"][0]["doc_id"] == "n.md"
    assert at.fingerprint(reloaded) == at.fingerprint(thread)


def test_max_citations_from_env(monkeypatch):
    monkeypatch.setenv("VIBECRAFT_ASK_THREAD_MAX_CITATIONS", "3")
    assert at.max_citations_from_env() == 3
    monkeypatch.setenv("VIBECRAFT_ASK_THREAD_MAX_CITATIONS", "nope")
    assert at.max_citations_from_env() == at.DEFAULT_MAX_CITATIONS
    monkeypatch.setenv("VIBECRAFT_ASK_THREAD_MAX_CITATIONS", "0")
    assert at.max_citations_from_env() == 1


def test_merge_keeps_lower_score_authority_refresh():
    """When a later sighting has a lower score, authority may still refresh."""
    existing = [{
        "doc_id": "a.md", "last_score": 0.9, "authority": 0.1,
        "last_seen_turn_id": "t-old", "chunk_ids": [],
    }]
    incoming = [{
        "doc_id": "a.md", "last_score": 0.2, "authority": 0.95, "chunk_ids": ["a.md#z"],
    }]
    merged = at.merge_citations(existing, incoming, turn_id="t-new")
    assert len(merged) == 1
    assert merged[0]["last_score"] == pytest.approx(0.9)
    assert merged[0]["authority"] == pytest.approx(0.95)
    assert merged[0]["last_seen_turn_id"] == "t-new"
    assert merged[0]["chunk_ids"] == ["a.md#z"]


def test_shared_js_project_header_covers_ask_and_thread_routes():
    """Fetch wrapper deny-list must leave /ask and /api/ask/thread project-scoped.

    Pattern mirrors test_dashboard_stream.py: Node eval of the extracted helper, no browser.
    """
    script = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const match = source.match(/function isProjectApi\(url\) \{[\s\S]*?\n\}/);
if (!match) throw new Error('isProjectApi missing');
const document = { baseURI: 'http://127.0.0.1:8000/' };
eval(match[0]);
const cases = {
  '/ask': true,
  '/api/ask/thread': true,
  '/api/projects': false,
  '/api/projects/x': false,
  '/api/health/live': false,
  '/api/intake/project/browse-path': false,
  '/api/retrieve': true,
};
const out = {};
for (const [path, expected] of Object.entries(cases)) {
  out[path] = { got: !!isProjectApi(path), expected };
}
process.stdout.write(JSON.stringify(out));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(_SHARED_JS)],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    cases = json.loads(completed.stdout)
    for path, row in cases.items():
        assert row["got"] is row["expected"], f"{path}: got {row['got']}, expected {row['expected']}"

"""Short per-project /ask thread: schema v1, atomic load/save/reset under database/ask/.

One active thread per project (not a list of chats). Turns are FIFO-capped; citations
accumulate as a deduped ledger with a hard unique-doc cap. The module owns on-disk truth
for WP1 storage; routes and prompt wiring live elsewhere.

Corrupt or missing thread.json → empty thread (atomic writes make mid-write truncation
rare). Path escapes / linked project dirs raise AskThreadStorageError so callers can map
to 503.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.artifacts import _atomic_write_json, _project_artifact_path
from core.projects import ProjectContext, ProjectError, _unlinked

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_MAX_TURNS = 4
DEFAULT_MAX_CITATIONS = 24
ANSWER_EXCERPT_MAX_CHARS = 800
THREAD_DIRNAME = "ask"
THREAD_FILENAME = "thread.json"


class AskThreadStorageError(RuntimeError):
    """Operational storage fault: callers map to 503, not a client input error."""

    action = "operator_action"


def max_turns_from_env() -> int:
    """Hard FIFO turn cap (env `VIBECRAFT_ASK_THREAD_MAX_TURNS`, default 4, at least 1)."""
    raw = os.environ.get("VIBECRAFT_ASK_THREAD_MAX_TURNS", "")
    try:
        value = int(raw) if raw else DEFAULT_MAX_TURNS
    except ValueError:
        logger.warning(
            "VIBECRAFT_ASK_THREAD_MAX_TURNS non numerica (%r): uso il default %d.",
            raw, DEFAULT_MAX_TURNS,
        )
        value = DEFAULT_MAX_TURNS
    return max(1, value)


def max_citations_from_env() -> int:
    """Hard unique-doc citation ledger cap (env `VIBECRAFT_ASK_THREAD_MAX_CITATIONS`, default 24)."""
    raw = os.environ.get("VIBECRAFT_ASK_THREAD_MAX_CITATIONS", "")
    try:
        value = int(raw) if raw else DEFAULT_MAX_CITATIONS
    except ValueError:
        logger.warning(
            "VIBECRAFT_ASK_THREAD_MAX_CITATIONS non numerica (%r): uso il default %d.",
            raw, DEFAULT_MAX_CITATIONS,
        )
        value = DEFAULT_MAX_CITATIONS
    return max(1, value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ask_dir(project: ProjectContext) -> Path:
    """`{project.database_dir}/ask`, validated against the project database boundary."""
    try:
        path = _project_artifact_path(project.database_dir / THREAD_DIRNAME, project)
        return _unlinked(path) if path.exists() else path
    except (ProjectError, OSError, ValueError) as exc:
        raise AskThreadStorageError("Archiviazione ask-thread non disponibile.") from exc


def thread_path(project: ProjectContext) -> Path:
    """Canonical on-disk path: `{project.database_dir}/ask/thread.json`."""
    try:
        path = _project_artifact_path(ask_dir(project) / THREAD_FILENAME, project)
        return _unlinked(path) if path.exists() else path
    except (ProjectError, OSError, ValueError) as exc:
        raise AskThreadStorageError("Archiviazione ask-thread non disponibile.") from exc


def ensure_ask_dir(project: ProjectContext) -> Path:
    """Create `database/ask` if missing (same mkdir style as other project subdirs)."""
    directory = ask_dir(project)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        return _unlinked(directory)
    except (ProjectError, OSError, ValueError) as exc:
        raise AskThreadStorageError("Archiviazione ask-thread non disponibile.") from exc


def empty_thread(
    project_id: str,
    *,
    max_turns: int | None = None,
) -> dict[str, Any]:
    """Schema-v1 empty thread for `project_id` (no turns, no citations)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "updated_at": _utc_now(),
        "max_turns": max_turns if max_turns is not None else max_turns_from_env(),
        "turns": [],
        "citations": [],
    }


def truncate_answer_excerpt(text: str | None, *, limit: int = ANSWER_EXCERPT_MAX_CHARS) -> str:
    """Hard char cap for prompt-safe answer excerpts (full answer stays in the live response)."""
    if not text:
        return ""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def new_turn_id() -> str:
    return f"t-{uuid.uuid4().hex}"


def build_turn(
    *,
    question: str,
    answer_excerpt: str = "",
    status: str = "success",
    index_version: str | None = None,
    request_id: str | None = None,
    retrieval_strategy: str | None = None,
    citation_ids: list[str] | None = None,
    turn_id: str | None = None,
    asked_at: str | None = None,
) -> dict[str, Any]:
    """Construct a schema-v1 turn dict (does not mutate the thread)."""
    return {
        "turn_id": turn_id or new_turn_id(),
        "request_id": request_id or "",
        "asked_at": asked_at or _utc_now(),
        "index_version": "" if index_version is None else str(index_version),
        "question": str(question),
        "answer_excerpt": truncate_answer_excerpt(answer_excerpt),
        "status": str(status),
        "retrieval_strategy": "" if retrieval_strategy is None else str(retrieval_strategy),
        "citation_ids": list(citation_ids or []),
    }


def _normalize_citation(raw: dict) -> dict[str, Any] | None:
    doc_id = raw.get("doc_id")
    if not isinstance(doc_id, str) or not doc_id.strip():
        return None
    score = raw.get("last_score", 0.0)
    authority = raw.get("authority", 0.0)
    try:
        score_f = float(score) if score is not None else 0.0
    except (TypeError, ValueError):
        score_f = 0.0
    try:
        authority_f = float(authority) if authority is not None else 0.0
    except (TypeError, ValueError):
        authority_f = 0.0
    chunk_ids = raw.get("chunk_ids") or []
    if not isinstance(chunk_ids, list):
        chunk_ids = []
    return {
        "doc_id": doc_id.strip(),
        "last_score": score_f,
        "authority": authority_f,
        "last_seen_turn_id": str(raw.get("last_seen_turn_id") or ""),
        "chunk_ids": [str(c) for c in chunk_ids if isinstance(c, str) and c],
    }


def merge_citations(
    existing: list[dict] | None,
    incoming: list[dict] | None,
    *,
    max_citations: int | None = None,
    turn_id: str | None = None,
) -> list[dict[str, Any]]:
    """Dedupe by `doc_id`; keep max score / latest authority; FIFO-trim to hard unique-doc cap.

    When over cap, retain highest `last_score` (then most recently seen turn id as tiebreak).
    """
    cap = max_citations if max_citations is not None else max_citations_from_env()
    by_doc: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for source in (existing or [], incoming or []):
        for raw in source:
            if not isinstance(raw, dict):
                continue
            item = _normalize_citation(raw)
            if item is None:
                continue
            if turn_id and not item["last_seen_turn_id"]:
                item["last_seen_turn_id"] = turn_id
            doc_id = item["doc_id"]
            prev = by_doc.get(doc_id)
            if prev is None:
                by_doc[doc_id] = item
                order.append(doc_id)
                continue
            # Keep best score; refresh authority / last_seen / chunk union on newer sightings.
            if item["last_score"] >= prev["last_score"]:
                prev["last_score"] = item["last_score"]
                prev["authority"] = item["authority"]
            elif item["authority"]:
                prev["authority"] = item["authority"]
            if item["last_seen_turn_id"]:
                prev["last_seen_turn_id"] = item["last_seen_turn_id"]
            seen = set(prev["chunk_ids"])
            for chunk_id in item["chunk_ids"]:
                if chunk_id not in seen:
                    prev["chunk_ids"].append(chunk_id)
                    seen.add(chunk_id)

    merged = [by_doc[doc_id] for doc_id in order if doc_id in by_doc]
    if len(merged) <= cap:
        return merged
    # Prefer highest score; stable secondary by last_seen then original order.
    ranked = sorted(
        enumerate(merged),
        key=lambda pair: (pair[1]["last_score"], pair[1]["last_seen_turn_id"], -pair[0]),
        reverse=True,
    )
    keep_ids = {item["doc_id"] for _, item in ranked[:cap]}
    return [item for item in merged if item["doc_id"] in keep_ids]


def apply_turn_cap(turns: list[dict], max_turns: int) -> list[dict]:
    """Drop oldest turns FIFO when exceeding `max_turns`."""
    if max_turns < 1:
        max_turns = 1
    if len(turns) <= max_turns:
        return list(turns)
    return list(turns[-max_turns:])


def append_turn(
    thread: dict,
    turn: dict,
    citations: list[dict] | None = None,
    *,
    max_turns: int | None = None,
    max_citations: int | None = None,
) -> dict[str, Any]:
    """Append a turn, enforce FIFO turn cap, merge/cap citations; returns the mutated thread."""
    if not isinstance(thread, dict):
        raise AskThreadStorageError("Thread schema non valido.")
    turns = list(thread.get("turns") or [])
    built = dict(turn)
    if "answer_excerpt" in built:
        built["answer_excerpt"] = truncate_answer_excerpt(built.get("answer_excerpt"))
    if not built.get("turn_id"):
        built["turn_id"] = new_turn_id()
    turns.append(built)
    cap = max_turns if max_turns is not None else int(thread.get("max_turns") or max_turns_from_env())
    thread["max_turns"] = cap
    thread["turns"] = apply_turn_cap(turns, cap)
    thread["citations"] = merge_citations(
        thread.get("citations"),
        citations,
        max_citations=max_citations,
        turn_id=built.get("turn_id"),
    )
    thread["updated_at"] = _utc_now()
    thread["schema_version"] = SCHEMA_VERSION
    return thread


def fingerprint(thread: dict | None) -> str:
    """Stable digest for ask_cache keys: turn count + last turn id + content digest.

    Empty / missing thread → empty string so callers can omit the cache dimension.
    """
    if not thread or not isinstance(thread, dict):
        return ""
    turns = thread.get("turns") or []
    if not isinstance(turns, list) or not turns:
        return ""
    last = turns[-1] if isinstance(turns[-1], dict) else {}
    payload = {
        "n": len(turns),
        "last_id": last.get("turn_id") or "",
        "last_q": last.get("question") or "",
        "last_status": last.get("status") or "",
        "last_index": last.get("index_version") or "",
        "cite_n": len(thread.get("citations") or []),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return f"{len(turns)}:{last.get('turn_id') or 'none'}:{digest[:16]}"


def _coerce_thread(raw: Any, project_id: str) -> dict[str, Any] | None:
    """Return a normalized schema-v1 thread, or None if the payload is unusable."""
    if not isinstance(raw, dict):
        return None
    if raw.get("schema_version") != SCHEMA_VERSION:
        return None
    if raw.get("project_id") not in (None, project_id):
        # Wrong project id in file — treat as corrupt rather than silently adopt.
        return None
    max_turns = raw.get("max_turns", DEFAULT_MAX_TURNS)
    try:
        max_turns_i = max(1, int(max_turns))
    except (TypeError, ValueError):
        max_turns_i = DEFAULT_MAX_TURNS
    turns_raw = raw.get("turns")
    citations_raw = raw.get("citations")
    if turns_raw is None:
        turns_raw = []
    if citations_raw is None:
        citations_raw = []
    if not isinstance(turns_raw, list) or not isinstance(citations_raw, list):
        return None
    turns: list[dict] = []
    for item in turns_raw:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        if not isinstance(question, str):
            continue
        turn_id = item.get("turn_id") or new_turn_id()
        turns.append({
            "turn_id": str(turn_id),
            "request_id": str(item.get("request_id") or ""),
            "asked_at": str(item.get("asked_at") or ""),
            "index_version": str(item.get("index_version") or ""),
            "question": question,
            "answer_excerpt": truncate_answer_excerpt(item.get("answer_excerpt") or ""),
            "status": str(item.get("status") or "success"),
            "retrieval_strategy": str(item.get("retrieval_strategy") or ""),
            "citation_ids": [
                str(c) for c in (item.get("citation_ids") or [])
                if isinstance(c, str) and c
            ],
        })
    citations = merge_citations([], citations_raw)
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "updated_at": str(raw.get("updated_at") or _utc_now()),
        "max_turns": max_turns_i,
        "turns": apply_turn_cap(turns, max_turns_i),
        "citations": citations,
    }


def load_thread(project: ProjectContext) -> dict[str, Any]:
    """Load the project thread; missing or corrupt file ⇒ empty thread."""
    path = thread_path(project)
    if not path.exists():
        return empty_thread(project.id)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AskThreadStorageError("Archiviazione ask-thread non disponibile.") from exc
    if not text.strip():
        logger.warning("ask thread vuoto o assente di contenuto (%s): thread vuoto.", path)
        return empty_thread(project.id)
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("ask thread JSON corrotto (%s): thread vuoto.", path)
        return empty_thread(project.id)
    coerced = _coerce_thread(raw, project.id)
    if coerced is None:
        logger.warning("ask thread schema non valido (%s): thread vuoto.", path)
        return empty_thread(project.id)
    return coerced


def save_thread(project: ProjectContext, thread: dict) -> dict[str, Any]:
    """Atomically persist `thread` under the project database ask/ directory."""
    if not isinstance(thread, dict):
        raise AskThreadStorageError("Thread schema non valido.")
    ensure_ask_dir(project)
    path = thread_path(project)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project.id,
        "updated_at": _utc_now(),
        "max_turns": int(thread.get("max_turns") or max_turns_from_env()),
        "turns": list(thread.get("turns") or []),
        "citations": list(thread.get("citations") or []),
    }
    try:
        _atomic_write_json(path, payload)
    except (OSError, ValueError) as exc:
        raise AskThreadStorageError("Archiviazione ask-thread non disponibile.") from exc
    return payload


def reset_thread(project: ProjectContext) -> dict[str, Any]:
    """Clear turns + citations and persist an empty schema-v1 thread (idempotent)."""
    empty = empty_thread(project.id)
    return save_thread(project, empty)


def thread_summary(thread: dict) -> dict[str, Any]:
    """Compact view suitable for API responses (WP2/WP3); pure, no I/O."""
    turns = thread.get("turns") or []
    citations = thread.get("citations") or []
    return {
        "turn_count": len(turns),
        "max_turns": int(thread.get("max_turns") or DEFAULT_MAX_TURNS),
        "updated_at": thread.get("updated_at"),
        "fingerprint": fingerprint(thread),
        "citations": [
            {"doc_id": c.get("doc_id"), "last_score": c.get("last_score"),
             "authority": c.get("authority"), "last_seen_turn_id": c.get("last_seen_turn_id")}
            for c in citations if isinstance(c, dict) and c.get("doc_id")
        ],
        "turns": [
            {
                "turn_id": t.get("turn_id"),
                "question": t.get("question"),
                "status": t.get("status"),
                "asked_at": t.get("asked_at"),
                "index_version": t.get("index_version"),
            }
            for t in turns if isinstance(t, dict)
        ],
    }

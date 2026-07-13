"""Test del reindex incrementale automatico: estrazione dei path da un payload webhook
GitLab, restrizione del piano del delta ai path segnalati, e il ReindexManager (job che
parte, secondo job rifiutato a 409, reload in memoria a fine job). Nessun modello/Qdrant
reale: il reindex è iniettato come fake che controlliamo dai test."""
import threading
import time

from api.reindex import ReindexManager, extract_gitlab_paths
from core import indexing
from core.indexing import IndexPlan


# ---------------------------------------------------------------------------
# extract_gitlab_paths — payload webhook GitLab
# ---------------------------------------------------------------------------
def test_extract_paths_from_push_event():
    payload = {
        "object_kind": "push",
        "commits": [
            {"added": ["docs/a.md"], "modified": ["code/x.py"], "removed": []},
            {"added": [], "modified": ["docs/a.md"], "removed": ["docs/old.md"]},
        ],
    }
    assert extract_gitlab_paths(payload) == ["code/x.py", "docs/a.md", "docs/old.md"]


def test_extract_paths_explicit_override():
    assert extract_gitlab_paths({"paths": ["docs/b.md", " ", "docs/b.md"]}) == ["docs/b.md"]


def test_extract_paths_merge_request_returns_none():
    # Il payload MR non porta l'elenco dei file → None (incrementale completo).
    assert extract_gitlab_paths({"object_kind": "merge_request", "object_attributes": {}}) is None


def test_extract_paths_empty_and_non_dict():
    assert extract_gitlab_paths({"commits": []}) is None
    assert extract_gitlab_paths(None) is None
    assert extract_gitlab_paths("nope") is None


# ---------------------------------------------------------------------------
# Restrizione del piano del delta ai path del webhook
# ---------------------------------------------------------------------------
def test_partition_changed_paths_splits_docs_and_code():
    docs_rel, code_rel = indexing._partition_changed_paths(
        ["docs/spec.md", "code/backend/x.py", "README.md", ".gitlab-ci.yml"]
    )
    assert docs_rel == {"spec.md"}
    assert code_rel == {"backend/x.py"}


def test_restrict_plan_keeps_only_allowed_docs():
    plan = IndexPlan(unchanged=["u.md"], new=["a.md", "b.md"], modified=["c.md"], deleted=["d.md"])
    restricted = indexing._restrict_plan(plan, {"a.md", "d.md"})
    assert restricted.new == ["a.md"]
    assert restricted.modified == []
    assert restricted.deleted == ["d.md"]


def test_incremental_index_restricts_to_changed_paths(monkeypatch):
    """changed_paths limita il lavoro: solo i path del webhook finiscono nel piano eseguito."""
    monkeypatch.setattr(indexing, "_docs_hashes", lambda: {"a.md": "h1", "b.md": "h2"})
    monkeypatch.setattr(indexing, "_code_hashes", lambda: {})
    monkeypatch.setattr(indexing, "_read_manifest", lambda: {"doc_hashes": {}, "code_hashes": {}})
    monkeypatch.setattr(indexing, "_ensure_collection", lambda *a, **k: None)
    # load_artifacts restituisce artefatti vuoti: così `graph` resta un nx.DiGraph nuovo.
    from core.artifacts import Artifacts
    monkeypatch.setattr(indexing, "load_artifacts", lambda *a, **k: Artifacts())
    monkeypatch.setattr(indexing, "save_artifacts", lambda *a, **k: None)
    monkeypatch.setattr(indexing, "write_index_manifest", lambda *a, **k: None)

    captured = {}

    def fake_apply(plan, *a, **k):
        captured["plan"] = plan
        return {"planned": plan.as_dict()}

    monkeypatch.setattr(indexing, "apply_incremental_indexing", fake_apply)

    class _FakeQ:
        def close(self): pass

    indexing.incremental_index(
        qdrant=_FakeQ(), embed_model=object(),
        changed_paths=["docs/a.md"],  # solo a.md, non b.md
    )
    plan = captured["plan"]
    assert plan.new == ["a.md"]  # b.md escluso dal webhook


# ---------------------------------------------------------------------------
# ReindexManager — un job alla volta, 409, reload a fine job
# ---------------------------------------------------------------------------
def test_job_starts_and_reloads_on_success():
    mgr = ReindexManager()
    reloaded = threading.Event()
    result = {"upserted_chunks": 3}

    job = mgr.start(
        changed_paths=["docs/a.md"],
        run_reindex=lambda paths: result,
        on_success=reloaded.set,
    )
    assert job is not None
    assert job.status in ("running", "completed")

    # Attende la fine del job daemon.
    assert reloaded.wait(timeout=5)
    finished = mgr.get(job.id)
    assert finished.status == "completed"
    assert finished.result == result
    assert finished.finished_at is not None
    assert not mgr.is_running  # slot liberato


def test_second_job_rejected_with_409_semantics():
    mgr = ReindexManager()
    gate = threading.Event()

    def slow_reindex(paths):
        gate.wait(timeout=5)  # tiene il primo job occupato
        return {}

    first = mgr.start(["a"], slow_reindex, lambda: None)
    assert first is not None

    # Mentre il primo è in corso, un secondo start è rifiutato (None → il router fa 409).
    second = mgr.start(["b"], slow_reindex, lambda: None)
    assert second is None
    assert mgr.is_running

    gate.set()  # sblocca il primo
    # Attende che lo slot si liberi.
    for _ in range(50):
        if not mgr.is_running:
            break
        time.sleep(0.05)
    assert not mgr.is_running

    # Ora un nuovo job può partire.
    third = mgr.start(["c"], lambda paths: {}, lambda: None)
    assert third is not None


def test_failed_job_frees_slot_and_skips_reload():
    mgr = ReindexManager()
    reloaded = threading.Event()

    def boom(paths):
        raise RuntimeError("indice rotto")

    job = mgr.start(["a"], boom, reloaded.set)
    assert job is not None

    for _ in range(50):
        if mgr.get(job.id).status == "failed":
            break
        time.sleep(0.05)

    finished = mgr.get(job.id)
    assert finished.status == "failed"
    assert "indice rotto" in finished.error
    assert not mgr.is_running          # slot liberato anche su errore
    assert not reloaded.is_set()       # nessun reload se il job fallisce


def test_unknown_job_id_returns_none():
    assert ReindexManager().get("does-not-exist") is None

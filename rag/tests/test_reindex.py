"""Test del reindex incrementale automatico: estrazione dei path da un payload webhook
GitLab, restrizione del piano del delta ai path segnalati, e il ReindexManager (job che
parte, coda con coalescing dei path, reload in memoria a fine job). Nessun modello/Qdrant
reale: il reindex è iniettato come fake che controlliamo dai test."""
import json
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
# ReindexManager — coda con coalescing, reload a fine job
# ---------------------------------------------------------------------------
def _wait(cond, timeout=5.0):
    """Attende attivamente che `cond()` sia vero, entro timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def test_job_starts_and_reloads_on_success():
    mgr = ReindexManager()
    reloaded = threading.Event()
    result = {"upserted_chunks": 3}

    job, queued = mgr.start(
        changed_paths=["docs/a.md"],
        run_reindex=lambda paths: result,
        on_success=reloaded.set,
    )
    assert job is not None
    assert queued is False  # nessun reindex in corso: parte subito
    assert job.status in ("running", "completed")

    # Attende la fine del job daemon.
    assert reloaded.wait(timeout=5)
    finished = mgr.get(job.id)
    assert finished.status == "completed"
    assert finished.result == result
    assert finished.finished_at is not None
    assert not mgr.is_running  # slot liberato


def test_second_request_is_queued_and_paths_coalesced():
    """Il secondo start non è più rifiutato: viene accodato, i path fusi, e parte a fine
    del primo job (non si perde il webhook ravvicinato)."""
    mgr = ReindexManager()
    gate = threading.Event()
    seen_paths = []

    def reindex(paths):
        seen_paths.append(paths)
        gate.wait(timeout=5)  # tiene il job occupato finché non sblocchiamo
        return {}

    first, q1 = mgr.start(["a"], reindex, lambda: None)
    assert q1 is False
    assert _wait(lambda: seen_paths == [["a"]])  # il primo è partito con ["a"]

    # Mentre il primo è in corso: due start ⇒ un solo pending, path fusi.
    second, q2 = mgr.start(["b"], reindex, lambda: None)
    third, q3 = mgr.start(["c"], reindex, lambda: None)
    assert q2 is True and q3 is True
    assert second.id == third.id            # un solo pending massimo
    assert second is not first
    assert second.status == "queued"
    assert second.changed_paths == ["b", "c"]  # unione ordinata
    assert mgr.pending_id == second.id

    gate.set()  # sblocca il primo → il pending deve partire da solo
    assert _wait(lambda: len(seen_paths) == 2)
    assert seen_paths[1] == ["b", "c"]      # il pending gira con i path fusi
    assert _wait(lambda: mgr.get(second.id).status == "completed")
    assert mgr.pending_id is None


def test_pending_complete_absorbs_paths():
    """Un pending "completo" (changed_paths=None) assorbe qualunque path successivo: None
    resta None (incrementale su tutto)."""
    mgr = ReindexManager()
    gate = threading.Event()

    def reindex(paths):
        gate.wait(timeout=5)
        return {}

    mgr.start(["a"], reindex, lambda: None)          # occupa lo slot
    pending, _ = mgr.start(None, reindex, lambda: None)  # pending completo
    assert pending.changed_paths is None
    mgr.start(["x", "y"], reindex, lambda: None)     # si fonde: None assorbe tutto
    assert mgr.get(pending.id).changed_paths is None
    gate.set()


def test_failed_first_job_still_dispatches_pending():
    """Il fallimento del primo job non blocca il pending: parte comunque a fine del primo."""
    mgr = ReindexManager()
    started = threading.Event()
    ran_pending = threading.Event()

    def boom(paths):
        started.set()
        raise RuntimeError("indice rotto")

    first, _ = mgr.start(["a"], boom, lambda: None)
    assert started.wait(timeout=5)

    # Accoda un pending mentre/prima che il primo finisca; potrebbe già essere fallito,
    # in tal caso parte subito lui.
    def pending_reindex(paths):
        ran_pending.set()
        return {}
    pending, queued = mgr.start(["b"], pending_reindex, lambda: None)

    assert _wait(lambda: mgr.get(first.id).status == "failed")
    # Se è stato davvero accodato, deve comunque essere stato avviato dal dispatch.
    if queued:
        assert ran_pending.wait(timeout=5)
        assert _wait(lambda: mgr.get(pending.id).status == "completed")
    assert _wait(lambda: not mgr.is_running)


def test_failed_job_frees_slot_and_skips_reload():
    mgr = ReindexManager()
    reloaded = threading.Event()

    def boom(paths):
        raise RuntimeError("indice rotto")

    job, _ = mgr.start(["a"], boom, reloaded.set)
    assert job is not None

    assert _wait(lambda: mgr.get(job.id).status == "failed" and not mgr.is_running)

    finished = mgr.get(job.id)
    assert finished.status == "failed"
    assert "indice rotto" in finished.error
    assert not mgr.is_running          # slot liberato anche su errore
    assert not reloaded.is_set()       # nessun reload se il job fallisce


def test_unknown_job_id_returns_none():
    assert ReindexManager().get("does-not-exist") is None


# ---------------------------------------------------------------------------
# Job "full" (build completa) — un solo scrittore per costruzione
# ---------------------------------------------------------------------------
def test_full_absorbs_pending_incremental():
    """Un full che arriva su un pending incremental lo sussume: il pending diventa full
    (path azzerati) e a fine job corrente gira la funzione del FULL, non quella del delta."""
    mgr = ReindexManager()
    gate = threading.Event()
    ran = []

    def busy(paths):
        gate.wait(timeout=5)
        return {}

    first, _ = mgr.start(["a"], busy, lambda: None)                    # occupa lo slot
    pending, q1 = mgr.start(["b"], lambda p: ran.append(("inc", p)) or {}, lambda: None)
    assert q1 is True and pending.kind == "incremental"

    full, q2 = mgr.start(None, lambda p: ran.append(("full", p)) or {}, lambda: None,
                         kind="full")
    assert q2 is True
    assert full.id == pending.id            # stesso slot pending, mutato
    assert pending.kind == "full"
    assert pending.changed_paths is None
    assert pending.to_dict()["kind"] == "full"

    gate.set()
    assert _wait(lambda: mgr.get(pending.id).status == "completed")
    assert ran == [("full", None)]          # ha girato il full, non l'incrementale


def test_incremental_merges_into_pending_full_without_changing_it():
    """Un incremental accodato dietro un pending full vi si fonde: il pending resta full,
    senza path (il full copre qualunque delta)."""
    mgr = ReindexManager()
    gate = threading.Event()

    def busy(paths):
        gate.wait(timeout=5)
        return {}

    mgr.start(["a"], busy, lambda: None)                     # occupa lo slot
    pending, _ = mgr.start(None, lambda p: {}, lambda: None, kind="full")
    assert pending.kind == "full"

    inc, queued = mgr.start(["docs/x.md"], lambda p: {}, lambda: None)
    assert queued is True and inc.id == pending.id
    assert pending.kind == "full"
    assert pending.changed_paths is None
    gate.set()
    assert _wait(lambda: mgr.get(pending.id).status == "completed")


def test_full_job_starts_immediately_when_idle_and_reports_kind():
    mgr = ReindexManager()
    done = threading.Event()
    job, queued = mgr.start(None, lambda p: {"full_rebuild": True}, done.set, kind="full")
    assert queued is False
    assert job.kind == "full"
    assert done.wait(timeout=5)
    assert mgr.get(job.id).to_dict()["kind"] == "full"


def test_journal_persists_kind(tmp_path):
    journal = tmp_path / "reindex_jobs.jsonl"
    done = threading.Event()
    mgr = ReindexManager(journal_path=journal)
    job, _ = mgr.start(None, lambda p: {}, done.set, kind="full")
    assert done.wait(timeout=5)
    assert _wait(lambda: mgr.get(job.id).status == "completed")

    revived = ReindexManager(journal_path=journal)
    assert revived.get(job.id).kind == "full"


# ---------------------------------------------------------------------------
# Archive (Step 5): fase (a) sincrona, re-indicizzazione accodata al manager
# ---------------------------------------------------------------------------
def _make_archive_env(tmp_path, monkeypatch):
    """changes/<feature> temporanea, canvas review disattivata, build tracciata."""
    changes = tmp_path / "changes"
    docs = tmp_path / "docs"
    docs.mkdir()
    (changes / "feat-demo").mkdir(parents=True)
    (changes / "feat-demo" / "canvas.md").write_text("# canvas", encoding="utf-8")
    monkeypatch.setattr(indexing, "CHANGES_DIR", changes)
    monkeypatch.setattr(indexing, "DOCS_DIR", docs)
    monkeypatch.setattr(
        indexing, "generate_canvas_review", lambda folder, change_dir: (None, "LLM off")
    )
    built = []
    monkeypatch.setattr(indexing, "build_graph_and_index", lambda **kw: built.append(kw))
    return changes, built


def test_archive_feature_reindex_false_skips_build(tmp_path, monkeypatch):
    """Con reindex=False (modalità server) archive_feature archivia ma NON chiama
    build_graph_and_index: la ricostruzione spetta alla coda del ReindexManager."""
    changes, built = _make_archive_env(tmp_path, monkeypatch)
    log = indexing.archive_feature("feat-demo", emit=lambda m: None, reindex=False)
    assert (changes / "archive" / "feat-demo").exists()
    assert built == []
    assert "Re-indicizzazione completata" not in log


def test_archive_feature_default_still_rebuilds_inline(tmp_path, monkeypatch):
    """Il default (CLI, fuori dal server) resta la ricostruzione inline."""
    changes, built = _make_archive_env(tmp_path, monkeypatch)
    indexing.archive_feature("feat-demo", emit=lambda m: None)
    assert (changes / "archive" / "feat-demo").exists()
    assert len(built) == 1


def test_archive_stream_route_queues_full_and_emits_final_event(tmp_path, monkeypatch):
    """La route streaming dell'archive esegue solo la fase (a) (reindex=False), accoda un
    job full (fake run_reindex: nessuna build reale) e chiude lo stream con
    {"type": "reindex_queued", "job_id": ...}."""
    import asyncio

    import api.routes_pipeline as rp
    import api.routes_reindex as rr
    from api.models import ArchiveRequest

    _make_archive_env(tmp_path, monkeypatch)
    monkeypatch.setitem(rr.state, "qdrant", None)
    monkeypatch.setitem(rr.state, "embed_model", None)
    # Manager pulito (senza journal reale) e run_reindex finto: nessuna build vera.
    monkeypatch.setattr(rr, "manager", ReindexManager())
    ran_full = threading.Event()
    monkeypatch.setattr(rr, "_run_full_rebuild", lambda paths: ran_full.set() or {"full_rebuild": True})

    async def collect():
        resp = await rp.pipeline_archive_stream(ArchiveRequest(feature="feat-demo"))
        events = []
        async for chunk in resp.body_iterator:
            events.append(json.loads(chunk))
        return events

    events = asyncio.run(collect())
    final = events[-1]
    assert final["type"] == "reindex_queued"
    assert final["job_id"]
    # Il job full accodato viene davvero eseguito dal manager (fake run_reindex).
    assert ran_full.wait(timeout=5)
    # E la fase (a) non ha rigenerato l'indice inline: nessun log di re-indicizzazione.
    assert not any("Re-indicizzazione completata" in e.get("line", "") for e in events)


# ---------------------------------------------------------------------------
# Persistenza: journal JSONL append-only + ricostruzione al boot
# ---------------------------------------------------------------------------
def test_journal_round_trip_completed_job_survives_restart(tmp_path):
    """Un job completato sopravvive al "riavvio" = nuovo manager sullo stesso journal."""
    journal = tmp_path / "reindex_jobs.jsonl"
    reloaded = threading.Event()

    mgr = ReindexManager(journal_path=journal)
    job, _ = mgr.start(["docs/a.md"], lambda paths: {"upserted": 7}, reloaded.set)
    assert reloaded.wait(timeout=5)
    assert _wait(lambda: mgr.get(job.id).status == "completed")

    # "Riavvio": un nuovo manager ricostruisce lo storico dal journal.
    revived = ReindexManager(journal_path=journal)
    restored = revived.get(job.id)
    assert restored is not None
    assert restored.status == "completed"
    assert restored.result == {"upserted": 7}
    assert restored.changed_paths == ["docs/a.md"]
    # Compare anche in list_recent, più recente prima.
    listed = revived.list_recent()
    assert listed[0]["job_id"] == job.id


def test_journal_running_job_marked_interrupted_at_load(tmp_path):
    """Un job rimasto 'running' nel journal (crash a metà) è 'interrupted' al load."""
    journal = tmp_path / "reindex_jobs.jsonl"
    # Simula un crash: scriviamo a mano una riga 'running' senza mai completarla.
    running_job = {
        "job_id": "abc123", "status": "running", "created_at": "2026-01-01T00:00:00+00:00",
        "finished_at": None, "changed_paths": ["docs/x.md"], "result": None, "error": None,
    }
    journal.write_text(json.dumps(running_job) + "\n", encoding="utf-8")

    revived = ReindexManager(journal_path=journal)
    restored = revived.get("abc123")
    assert restored is not None
    assert restored.status == "interrupted"
    assert restored.finished_at is not None

    # La transizione 'interrupted' è persistita: un secondo load resta terminale.
    again = ReindexManager(journal_path=journal)
    assert again.get("abc123").status == "interrupted"


def test_journal_compaction_keeps_only_last_state(tmp_path, monkeypatch):
    """Oltre la soglia, il journal è riscritto con una sola riga per job (ultimo stato)."""
    import api.reindex as reindex_mod
    monkeypatch.setattr(reindex_mod, "_JOURNAL_MAX_BYTES", 200)  # soglia minuscola
    journal = tmp_path / "reindex_jobs.jsonl"

    mgr = ReindexManager(journal_path=journal)
    ids = []
    for i in range(5):
        done = threading.Event()
        job, _ = mgr.start([f"docs/{i}.md"], lambda paths: {"i": paths}, done.set)
        assert done.wait(timeout=5)
        assert _wait(lambda jid=job.id: mgr.get(jid).status == "completed")
        ids.append(job.id)

    # Dopo la compattazione ci deve essere al più UNA riga per job.
    lines = [l for l in journal.read_text(encoding="utf-8").splitlines() if l.strip()]
    seen_ids = [json.loads(l)["job_id"] for l in lines]
    assert len(seen_ids) == len(set(seen_ids))  # nessun duplicato: compattato
    # Tutti gli stati compattati sono terminali (completed).
    assert all(json.loads(l)["status"] == "completed" for l in lines)
    # Lo storico resta intero in memoria e ricostruibile.
    revived = ReindexManager(journal_path=journal)
    for jid in ids:
        assert revived.get(jid).status == "completed"


# ---------------------------------------------------------------------------
# Webhook secret: require_gitlab_token (in aggiunta a X-API-Key)
# ---------------------------------------------------------------------------
class _FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


def _call_require_gitlab_token(monkeypatch, env_token, header_token):
    import api.deps as deps
    from fastapi import HTTPException
    monkeypatch.setattr(deps, "GITLAB_TOKEN", env_token)
    headers = {} if header_token is None else {"X-Gitlab-Token": header_token}
    try:
        deps.require_gitlab_token(_FakeRequest(headers))
        return None
    except HTTPException as exc:
        return exc.status_code


def test_gitlab_token_correct_passes(monkeypatch):
    assert _call_require_gitlab_token(monkeypatch, "s3cret", "s3cret") is None


def test_gitlab_token_wrong_rejected(monkeypatch):
    assert _call_require_gitlab_token(monkeypatch, "s3cret", "nope") == 401


def test_gitlab_token_absent_rejected_when_env_set(monkeypatch):
    assert _call_require_gitlab_token(monkeypatch, "s3cret", None) == 401


def test_gitlab_token_not_required_when_env_unset(monkeypatch):
    # Env non impostata → nessun requisito aggiuntivo, anche senza header.
    assert _call_require_gitlab_token(monkeypatch, None, None) is None
    assert _call_require_gitlab_token(monkeypatch, "", "whatever") is None

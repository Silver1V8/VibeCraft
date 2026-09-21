"""Test del reindex incrementale automatico: estrazione dei path da un payload webhook
GitLab, restrizione del piano del delta ai path segnalati, e il ReindexManager (job che
parte, coda con coalescing dei path, reload in memoria a fine job). Nessun modello/Qdrant
reale: il reindex è iniettato come fake che controlliamo dai test."""
import contextlib
import json
import threading
import time

import pytest

from api.reindex import ReindexJob, ReindexManager, extract_gitlab_paths
from core import indexing
from core.indexing import IndexPlan


@pytest.fixture(autouse=True)
def _noop_writer_lock(monkeypatch):
    """Neutralizza il writer lock cross-processo in TUTTI i test di questo file: qui si
    esercitano coda/coalescing/journal, non la mutua esclusione (coperta da
    test_writer_lock.py). Senza il no-op i job (thread daemon, anche residui del test
    precedente) contenderebbero il lock reale su database/.writer.lock."""
    import api.reindex as reindex_mod
    monkeypatch.setattr(reindex_mod, "writer_lock",
                        lambda *a, **k: contextlib.nullcontext())


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
        def get_aliases(self):
            from types import SimpleNamespace
            return SimpleNamespace(aliases=[])  # nessun alias: bootstrap, COLLECTION_NAME libero

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


def test_completed_build_is_not_ready_until_reload_finishes():
    mgr = ReindexManager()
    reload_started = threading.Event()
    release_reload = threading.Event()

    def reload():
        reload_started.set()
        release_reload.wait(timeout=5)
        return "v-ready"

    job, _ = mgr.start(["a"], lambda paths: {"noop": False}, reload)
    assert reload_started.wait(timeout=5)
    current = mgr.get(job.id).to_dict()
    assert current["status"] == "completed"
    assert current["finished_at"] is not None
    assert current["reload_status"] == "pending"
    assert current["snapshot_ready_duration_seconds"] is None

    release_reload.set()
    assert mgr.join_all()
    ready = mgr.get(job.id).to_dict()
    assert ready["reload_status"] == "completed"
    assert ready["published_token"] == "v-ready"
    assert ready["reload_duration_seconds"] is not None
    assert ready["snapshot_ready_duration_seconds"] is not None


def test_noop_uses_served_snapshot_token_without_reload():
    mgr = ReindexManager()
    called = []
    job, _ = mgr.start([], lambda paths: {"noop": True, "snapshot_token": "served-v1"},
                       lambda: called.append("reload") or "wrong")
    assert mgr.join_all()
    ready = mgr.get(job.id).to_dict()
    assert called == []
    assert ready["reload_status"] == "completed"
    assert ready["published_token"] == "served-v1"
    assert ready["reload_duration_seconds"] == 0
    assert ready["snapshot_ready_duration_seconds"] is not None


def test_noop_without_observed_snapshot_is_incomplete():
    mgr = ReindexManager()
    calls = []
    job, _ = mgr.start([], lambda paths: {"noop": True},
                       lambda: calls.append("reload") or None)
    assert mgr.join_all()
    ready = mgr.get(job.id).to_dict()
    assert calls == ["reload"]
    assert ready["reload_status"] == "incomplete"
    assert ready["published_token"] is None


def test_stale_noop_reloads_with_real_duration_and_separate_failure():
    mgr = ReindexManager()
    def reload():
        time.sleep(0.01)
        raise RuntimeError("stale reload failed")
    job, _ = mgr.start([], lambda paths: {"noop": True}, reload)
    assert mgr.join_all()
    ready = mgr.get(job.id).to_dict()
    assert ready["status"] == "completed"
    assert ready["reload_status"] == "failed"
    assert ready["reload_duration_seconds"] >= 0.01
    assert "stale reload failed" in ready["reload_error"]
    assert ready["published_token"] is None


def test_pending_job_waits_for_previous_reload_before_build():
    mgr = ReindexManager()
    reload_started = threading.Event()
    release_reload = threading.Event()
    second_started = threading.Event()

    def reload():
        reload_started.set()
        release_reload.wait(timeout=5)
        return "v1"

    mgr.start(["a"], lambda paths: {"noop": False}, reload)
    second, queued = mgr.start(
        ["b"], lambda paths: second_started.set() or {"noop": False}, lambda: "v2"
    )
    assert queued is True
    assert reload_started.wait(timeout=5)
    assert not second_started.is_set()
    release_reload.set()
    assert mgr.join_all()
    assert second_started.is_set()
    assert mgr.get(second.id).queue_duration_seconds is not None


def test_journal_error_does_not_stall_pending_dispatch(monkeypatch):
    mgr = ReindexManager()
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()

    def first_run(paths):
        first_started.set()
        release_first.wait(timeout=5)
        return {"noop": False}

    mgr.start(["a"], first_run, lambda: "v1")
    assert first_started.wait(timeout=5)
    mgr.start(["b"], lambda paths: second_started.set() or {"noop": False}, lambda: "v2")
    monkeypatch.setattr(mgr, "_record", lambda job: (_ for _ in ()).throw(OSError("disk full")))
    release_first.set()

    assert mgr.join_all()
    assert second_started.is_set()
    assert not mgr.is_running


def test_reload_none_is_observable_without_inventing_token():
    mgr = ReindexManager()
    job, _ = mgr.start(["a"], lambda paths: {"noop": False}, lambda: None)
    assert mgr.join_all()
    final = mgr.get(job.id).to_dict()
    assert final["status"] == "completed"
    assert final["reload_status"] == "incomplete"
    assert final["published_token"] is None
    assert final["snapshot_ready_duration_seconds"] is None
    assert not mgr.is_running  # slot liberato


def test_reload_completed_is_not_serialized_without_readiness_fields():
    job = ReindexJob(["a"])
    job.reload_status = "completed"
    assert job.to_dict()["reload_status"] == "pending"


def test_reload_failure_is_separate_from_build_failure():
    mgr = ReindexManager()

    def boom():
        raise RuntimeError("reload rotto")

    job, _ = mgr.start(["a"], lambda paths: {"noop": False}, boom)
    assert mgr.join_all()
    final = mgr.get(job.id).to_dict()
    assert final["status"] == "completed"
    assert final["error"] is None
    assert final["reload_status"] == "failed"
    assert "reload rotto" in final["reload_error"]
    assert final["published_token"] is None


def test_failed_writer_lock_still_records_wait_duration(monkeypatch):
    import api.reindex as reindex_mod

    class BusyLock:
        def __enter__(self):
            raise RuntimeError("busy")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(reindex_mod, "writer_lock", lambda **kwargs: BusyLock())
    mgr = ReindexManager()
    job, _ = mgr.start(["a"], lambda paths: {}, lambda: "never")
    assert mgr.join_all()
    final = mgr.get(job.id).to_dict()
    assert final["status"] == "failed"
    assert final["writer_lock_wait_seconds"] is not None


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
    # Attendere che la coda si svuoti non e' cortesia: _noop_writer_lock e' un monkeypatch,
    # e monkeypatch si disfa al teardown. Il pending qui sopra veniva dispacciato DOPO la fine
    # del test, quando il no-op non c'era piu', e quel thread daemon acquisiva il writer lock
    # REALE del progetto (database/.writer.lock) — l'unico caso di R24 che nessun seam poteva
    # intercettare, perche' il seam era gia' stato rimesso a posto.
    assert _wait(lambda: not mgr.is_running)


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
    fresh_manager = ReindexManager()
    monkeypatch.setattr(rr, "manager", fresh_manager)
    # on_success (reload_index_state) fatto passare finto: qui si esamina solo il
    # wiring della coda, non il reload reale — che farebbe I/O vera su database/ e
    # docs/ del repo, indipendente dal sandbox di _make_archive_env, e girerebbe nel
    # thread daemon del manager oltre la vita del test se non sincronizzato (vedi
    # join_all sotto).
    monkeypatch.setattr(rr, "reload_index_state", lambda: None)
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
    # Sincronizzazione REALE con la fine del thread daemon (non solo con l'Event sopra,
    # che si accende PRIMA che job.status passi a terminale e PRIMA di on_success —
    # vedi ReindexManager._run): senza questo il thread può ancora essere in volo al
    # ritorno del test, sopravvivendo al teardown di capture/logging del test successivo.
    assert fresh_manager.join_all(timeout=5)
    # E la fase (a) non ha rigenerato l'indice inline: nessun log di re-indicizzazione.
    assert not any("Re-indicizzazione completata" in e.get("line", "") for e in events)


# ---------------------------------------------------------------------------
# Blue/green: promozione dei job full + eval gate (config rag_config.yaml eval_gate.*)
# ---------------------------------------------------------------------------
def test_manager_honors_completed_not_promoted_and_skips_reload():
    """Un run che risponde job_status=completed_not_promoted termina in quello stato
    (terminale) e NON innesca on_success: CURRENT è invariato, niente reload."""
    mgr = ReindexManager()
    reloaded = threading.Event()
    job, _ = mgr.start(None, lambda paths: {"full_rebuild": True,
                                            "job_status": "completed_not_promoted"},
                       reloaded.set, kind="full")
    assert _wait(lambda: mgr.get(job.id).status == "completed_not_promoted")
    time.sleep(0.05)  # dà spazio a un eventuale on_success spurio
    assert not reloaded.is_set()


def _wire_full_rebuild(monkeypatch, gate_result: dict, *,
                       collection_for_version: str = "vibecraft_events__v-nuova"):
    """Prepara _run_full_rebuild con build ed eval-gate finti, e traccia l'ordine
    relativo di promote_version, _migrate_legacy_collection_if_needed, _swap_alias
    e gc_orphaned_qdrant_collections in un'unica `sequence` (tutti e quattro
    eseguono SEMPRE a gate passato, non solo in un ramo condizionale: un solo
    percorso di full rebuild, senza flag). `migrate_calls`/`swap_calls`/`gc_calls`
    isolano le chiamate ai singoli helper.

    La DECISIONE se migrare davvero (collection legacy presente o no) è già testata
    in core/indexing.py con lo StatefulFakeQdrant reale: qui si verifica solo il
    WIRING — che l'helper venga chiamato, nell'ordine giusto, con gli argomenti
    giusti — quindi il fake ritorna sempre False/[] (nessuna vera cancellazione da
    segnalare al chiamante, che comunque ignora il valore di ritorno)."""
    import api.routes_reindex as rr

    monkeypatch.setattr(rr, "_reindex_embed_model", lambda: object())
    monkeypatch.setattr(rr, "build_graph_and_index", lambda **kw: "v-nuova")
    monkeypatch.setattr(rr, "_eval_gate", lambda version, embed_model: gate_result)
    monkeypatch.setattr(rr, "_qdrant_collection_for_version", lambda version: collection_for_version)

    sequence: list = []
    promoted: list[str] = []

    def _tracking_promote(v):
        promoted.append(v)
        sequence.append(("promote", v))

    monkeypatch.setattr(rr, "promote_version", _tracking_promote)

    migrate_calls: list[str] = []

    def _fake_migrate(qdrant, alias, emit=None):
        sequence.append(("migrate", alias))
        migrate_calls.append(alias)
        return False

    monkeypatch.setattr(rr, "_migrate_legacy_collection_if_needed", _fake_migrate)

    swap_calls: list[tuple] = []

    def _fake_swap_alias(qdrant, alias, target):
        sequence.append(("alias_swap", alias, target))
        swap_calls.append((alias, target))

    monkeypatch.setattr(rr, "_swap_alias", _fake_swap_alias)

    gc_calls: list = []

    def _fake_gc(qdrant, emit=None):
        sequence.append("gc")
        gc_calls.append(qdrant)
        return []

    monkeypatch.setattr(rr, "gc_orphaned_qdrant_collections", _fake_gc)
    return rr, promoted, sequence, swap_calls, migrate_calls, gc_calls


def test_full_rebuild_below_gate_is_not_promoted(monkeypatch):
    rr, promoted, sequence, *_ = _wire_full_rebuild(
        monkeypatch, {"passed": False, "recall": 0.1, "k": 10, "min_recall": 0.9})
    result = rr._run_full_rebuild(None)
    assert result["promoted"] is False
    assert result["job_status"] == "completed_not_promoted"
    assert result["version"] == "v-nuova"
    assert result["eval"]["recall"] == 0.1
    assert promoted == []  # CURRENT mai toccato
    assert sequence == []  # né promote, né migrazione, né alias swap, né GC


def test_full_rebuild_above_gate_promotes_then_migrates_then_swaps_then_gcs(monkeypatch):
    """Ordine non negoziabile: CURRENT prima, poi l'eventuale migrazione one-shot (se
    necessaria — qui il fake la chiama sempre, come fa il codice reale; la decisione
    se cancellare davvero è interna all'helper), poi lo swap, poi il GC."""
    rr, promoted, sequence, swap_calls, migrate_calls, gc_calls = _wire_full_rebuild(
        monkeypatch, {"passed": True, "recall": 0.95, "k": 10},
        collection_for_version="vibecraft_events__v-nuova")

    result = rr._run_full_rebuild(None)

    assert result["promoted"] is True and "job_status" not in result
    assert promoted == ["v-nuova"]
    assert sequence == [
        ("promote", "v-nuova"),
        ("migrate", rr.COLLECTION_NAME),
        ("alias_swap", rr.COLLECTION_NAME, "vibecraft_events__v-nuova"),
        "gc",
    ]
    assert migrate_calls == [rr.COLLECTION_NAME]
    assert len(gc_calls) == 1  # chiamato una volta, SOLO DOPO lo swap


def test_full_rebuild_alias_swap_uses_manifest_collection_as_source_of_truth(monkeypatch):
    """Il target dello swap è quello dichiarato dal manifest (_qdrant_collection_for_version),
    non una ricostruzione indipendente del nome: qui il valore è deliberatamente
    diverso da quello che qdrant_collection_name(version) produrrebbe, per provare
    che la fonte usata è davvero il manifest."""
    rr, promoted, sequence, swap_calls, migrate_calls, gc_calls = _wire_full_rebuild(
        monkeypatch, {"passed": True, "recall": 0.95, "k": 10},
        collection_for_version="collection-dichiarata-nel-manifest",
    )

    rr._run_full_rebuild(None)

    assert swap_calls == [(rr.COLLECTION_NAME, "collection-dichiarata-nel-manifest")]


def test_full_rebuild_gate_unavailable_promotes_directly(monkeypatch):
    """Eval non disponibile (fail-open, passed=True + skipped): promozione diretta."""
    rr, promoted, sequence, *_ = _wire_full_rebuild(
        monkeypatch, {"passed": True, "skipped": "no_golden_set"})
    result = rr._run_full_rebuild(None)
    assert result["promoted"] is True
    assert promoted == ["v-nuova"]


def test_full_rebuild_gate_disabled_promotes(monkeypatch):
    """Gate disattivo (config eval_gate.enabled=false): promozione diretta, eval saltata."""
    rr, promoted, sequence, *_ = _wire_full_rebuild(
        monkeypatch, {"passed": True, "skipped": "disabled"})
    result = rr._run_full_rebuild(None)
    assert result["promoted"] is True
    assert promoted == ["v-nuova"]


# ---------------------------------------------------------------------------
# _qdrant_collection_for_version / _eval_gate: il gate del full rebuild deve
# valutare la STESSA collection su cui quella versione è stata costruita (S6.4,
# blue/green Qdrant), letta dal manifest — mai una collection diversa, mai
# hardcoded a COLLECTION_NAME quando il manifest dice altro.
# ---------------------------------------------------------------------------
def _write_manifest(tmp_path, monkeypatch, version: str, manifest: dict):
    from core import artifacts
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)
    vdir = tmp_path / "versions" / version
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "index_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_qdrant_collection_for_version_reads_manifest_field(tmp_path, monkeypatch):
    import api.routes_reindex as rr
    _write_manifest(tmp_path, monkeypatch, "v1", {"qdrant_collection": "vibecraft_events__v1"})
    assert rr._qdrant_collection_for_version("v1") == "vibecraft_events__v1"


def test_qdrant_collection_for_version_falls_back_when_field_absent(tmp_path, monkeypatch):
    """Manifest antecedente a S2 (nessun campo qdrant_collection): fallback a
    COLLECTION_NAME, comportamento invariato — non un'eccezione."""
    import api.routes_reindex as rr
    _write_manifest(tmp_path, monkeypatch, "v1", {"version": "v1"})
    assert rr._qdrant_collection_for_version("v1") == rr.COLLECTION_NAME


def test_qdrant_collection_for_version_falls_back_when_manifest_missing(tmp_path, monkeypatch):
    import api.routes_reindex as rr
    from core import artifacts
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)  # nessun manifest scritto
    assert rr._qdrant_collection_for_version("v-inesistente") == rr.COLLECTION_NAME


def test_eval_gate_passes_the_version_candidate_collection_to_gate_promotion(tmp_path, monkeypatch):
    """Il manifest dichiara la candidata: _eval_gate deve passarla a gate_promotion,
    non valutare mai COLLECTION_NAME al suo posto."""
    from types import SimpleNamespace
    import api.routes_reindex as rr

    _write_manifest(tmp_path, monkeypatch, "v1", {"qdrant_collection": "vibecraft_events__v1"})
    monkeypatch.setattr(rr, "load_artifacts", lambda **kw: SimpleNamespace(colbert_store={}, graph=None, chunks_store={}))

    captured: dict = {}

    def _fake_gate_promotion(version, qdrant, embed_model, colbert_store, emit=None, collection_name=None, **kw):
        captured["collection_name"] = collection_name
        return {"passed": True}

    monkeypatch.setattr(rr, "gate_promotion", _fake_gate_promotion)

    result = rr._eval_gate("v1", embed_model=object())
    assert result["passed"] is True
    assert captured["collection_name"] == "vibecraft_events__v1"
    assert captured["collection_name"] != rr.COLLECTION_NAME


# ---------------------------------------------------------------------------
# POST /api/index/rollback riallinea l'alias Qdrant (rollback_qdrant_alias_if_needed,
# core.indexing) DOPO il rollback locale puro (rollback_version, core.artifacts) — mai
# prima, e mai una correzione automatica se la collection target manca.
# ---------------------------------------------------------------------------
class _FakeJsonRequest:
    def __init__(self, payload=None):
        self._payload = payload

    async def json(self):
        if self._payload is None:
            raise ValueError("nessun corpo")
        return self._payload


def _call_index_rollback(monkeypatch, payload=None, *, rollback_version_result="v1",
                         qdrant_alias_result=None, shared_later_result=None,
                         precheck=None, writer_lock=None):
    import asyncio
    import api.routes_reindex as rr

    # L'autouse _noop_writer_lock neutralizza il lock solo in api.reindex, NON in
    # api.routes_reindex: qui esercitiamo il comportamento a lock LIBERO, quindi lo
    # rendiamo un no-op nel namespace della route (mai il database/.writer.lock reale).
    # `writer_lock=` permette a chi vuole esercitare il lock VERO (su un file di tmp_path)
    # di farlo senza rifarsi a mano tutto il resto delle patch: e' quella duplicazione ad
    # aver lasciato indietro un test quando la route ha iniziato a chiamare
    # resolve_rollback_target.
    monkeypatch.setattr(rr, "writer_lock",
                        writer_lock or (lambda *a, **k: contextlib.nullcontext()))
    monkeypatch.setitem(rr.state, "qdrant", "fake-qdrant-client")
    monkeypatch.setattr(rr, "resolve_rollback_target", lambda target=None: rollback_version_result)
    monkeypatch.setattr(rr, "rollback_version", lambda target: rollback_version_result)
    monkeypatch.setattr(rr, "list_versions", lambda: ["v1", "v2"])
    # Pre-check R14: di base passa. I test che simulano la collection del target
    # distrutta iniettano un `precheck` che solleva.
    monkeypatch.setattr(rr, "assert_rollback_target_has_vectors",
                        precheck or (lambda qdrant, target_version: None))
    monkeypatch.setattr(rr, "reload_index_state", lambda: None)
    # Default []: la detection della collection condivisa non deve leggere il vero
    # database/versions/ nei test che non la esercitano (per quelli che la esercitano
    # su un sandbox reale vedi i test "end to end" più sotto).
    monkeypatch.setattr(rr, "rollback_shares_collection_with_later_versions",
                        lambda name: shared_later_result if shared_later_result is not None else [])

    captured: dict = {}

    def _fake_rollback_qdrant_alias(qdrant, target_version, emit=None):
        captured["qdrant"] = qdrant
        captured["target_version"] = target_version
        return qdrant_alias_result if qdrant_alias_result is not None else {"state": "noop"}

    monkeypatch.setattr(rr, "rollback_qdrant_alias_if_needed", _fake_rollback_qdrant_alias)

    response = asyncio.run(rr.index_rollback(_FakeJsonRequest(payload)))
    return response, captured


def test_index_rollback_reports_target_version_received_by_the_alias_helper(monkeypatch):
    response, captured = _call_index_rollback(
        monkeypatch, qdrant_alias_result={"state": "noop", "expected": "coll-v1", "actual": "coll-v1"})
    assert response["rolled_back_to"] == "v1"
    assert response["qdrant_alias"]["state"] == "noop"
    assert captured["target_version"] == "v1"  # riceve la versione RISULTANTE dal rollback locale


def test_index_rollback_cross_lineage_reports_swapped_state(monkeypatch):
    response, captured = _call_index_rollback(
        monkeypatch, rollback_version_result="v-target",
        qdrant_alias_result={"state": "swapped", "expected": "coll-v-target", "actual": "coll-v-target"},
    )
    assert response["rolled_back_to"] == "v-target"
    assert response["qdrant_alias"]["state"] == "swapped"
    assert captured["target_version"] == "v-target"
    assert captured["qdrant"] == "fake-qdrant-client"


def test_index_rollback_intra_lineage_reports_noop_state(monkeypatch):
    response, _ = _call_index_rollback(
        monkeypatch, qdrant_alias_result={"state": "noop", "expected": "coll-x", "actual": "coll-x"},
    )
    assert response["qdrant_alias"]["state"] == "noop"


def test_index_rollback_missing_target_collection_does_not_raise_and_current_still_moved(monkeypatch):
    """Nessuna correzione automatica distruttiva: la route non solleva un errore HTTP
    quando la collection target manca — lo stato esplicito arriva nel corpo della
    risposta, e il rollback locale (CURRENT) resta comunque effettuato. NB: dal
    pre-check R14 in poi questo ramo resta raggiungibile solo se la collection sparisce
    FRA il pre-check e lo swap, o se il pre-check e' stato saltato (Qdrant giu')."""
    response, _ = _call_index_rollback(
        monkeypatch, rollback_version_result="v1",
        qdrant_alias_result={"state": "missing_target_collection", "expected": "coll-v1", "actual": "coll-v2"},
    )
    assert response["rolled_back_to"] == "v1"
    assert response["qdrant_alias"]["state"] == "missing_target_collection"


def test_index_rollback_rifiutato_409_se_la_collection_del_target_non_esiste(monkeypatch):
    """R14: rollback verso una versione i cui vettori sono stati distrutti (A20). La
    route risponde 409 SENZA aver mutato nulla — ne' CURRENT ne' l'alias — e il detail
    nomina la collection mancante e il rimedio. Patch esplicite invece di
    `_call_index_rollback`: qui il punto e' proprio che rollback_version NON venga
    chiamata, e l'helper la sostituisce con una versione che riesce sempre."""
    import asyncio
    import api.routes_reindex as rr
    from fastapi import HTTPException

    mutazioni: list = []
    monkeypatch.setattr(rr, "writer_lock", lambda *a, **k: contextlib.nullcontext())
    monkeypatch.setitem(rr.state, "qdrant", "fake-qdrant-client")
    monkeypatch.setattr(rr, "resolve_rollback_target", lambda target=None: "v1")
    monkeypatch.setattr(rr, "rollback_version",
                        lambda target: mutazioni.append(("current", target)) or "v1")
    monkeypatch.setattr(rr, "rollback_qdrant_alias_if_needed",
                        lambda *a, **k: mutazioni.append(("alias",)) or {"state": "noop"})
    monkeypatch.setattr(rr, "reload_index_state", lambda: None)

    def _precheck(qdrant, target_version):
        raise rr.RollbackTargetCollectionMissing(
            f"rollback a '{target_version}' RIFIUTATO: la sua collection Qdrant "
            f"'coll-v1' non esiste piu'. Serve una re-indicizzazione completa."
        )

    monkeypatch.setattr(rr, "assert_rollback_target_has_vectors", _precheck)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(rr.index_rollback(_FakeJsonRequest(None)))

    assert exc.value.status_code == 409
    assert "coll-v1" in exc.value.detail
    assert "re-indicizzazione completa" in exc.value.detail
    assert mutazioni == []  # ne' CURRENT ne' l'alias sono stati toccati


def test_index_rollback_without_shared_collection_has_no_note_and_writes_no_alert(monkeypatch, tmp_path):
    """Detection vuota (nessuna versione posteriore sulla stessa collection): la
    risposta NON porta qdrant_note e alerts.jsonl non viene nemmeno creato."""
    import core.eval_gate as eval_gate

    alerts = tmp_path / "alerts.jsonl"
    monkeypatch.setattr(eval_gate, "ALERTS_PATH", alerts)
    response, _ = _call_index_rollback(monkeypatch, shared_later_result=[])
    assert "qdrant_note" not in response
    assert not alerts.exists()


def test_index_rollback_shared_collection_adds_note_and_writes_warning_alert(monkeypatch, tmp_path):
    """Detection non vuota: qdrant_note esplicita nella risposta + alert warning
    source="rollback" su alerts.jsonl (il canale che degrada /api/health per 48h)."""
    import core.eval_gate as eval_gate

    alerts = tmp_path / "alerts.jsonl"
    monkeypatch.setattr(eval_gate, "ALERTS_PATH", alerts)
    response, _ = _call_index_rollback(monkeypatch, shared_later_result=["v2"])
    assert response["rolled_back_to"] == "v1"
    assert response["qdrant_note"] == {
        "state": "shared_collection_not_rewound",
        "later_versions": ["v2"],
        "hint": "Qdrant non riavvolto: full rebuild consigliato",
    }
    alert = json.loads(alerts.read_text(encoding="utf-8").splitlines()[-1])
    assert alert["level"] == "warning"
    assert alert["source"] == "rollback"
    assert alert["target_version"] == "v1"
    assert alert["later_versions"] == ["v2"]
    assert "full rebuild" in alert["message"].lower()


def _sandbox_versions(monkeypatch, tmp_path, versions: dict, current: str):
    """Sandbox REALE di database/ (core.artifacts): manifest con qdrant_collection per
    ogni versione in `versions` ({nome: collection}) + puntatore CURRENT."""
    import core.artifacts as artifacts

    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)
    for v, collection in versions.items():
        vdir = tmp_path / "versions" / v
        vdir.mkdir(parents=True)
        (vdir / "index_manifest.json").write_text(
            json.dumps({"version": v, "qdrant_collection": collection}), encoding="utf-8")
    (tmp_path / "CURRENT").write_text(current + "\n", encoding="utf-8")


def _call_index_rollback_on_sandbox(monkeypatch, tmp_path, versions: dict, current: str):
    """Route rollback contro il sandbox: rollback_version, list_versions e la detection
    della collection condivisa sono quelli VERI (girano sul sandbox); restano finti solo
    lock, snapshot-reload e client/alias Qdrant."""
    import asyncio
    import api.routes_reindex as rr
    import core.eval_gate as eval_gate

    _sandbox_versions(monkeypatch, tmp_path, versions, current)
    alerts = tmp_path / "alerts.jsonl"
    monkeypatch.setattr(eval_gate, "ALERTS_PATH", alerts)
    monkeypatch.setattr(rr, "writer_lock", lambda *a, **k: contextlib.nullcontext())
    monkeypatch.setitem(rr.state, "qdrant", "fake-qdrant-client")
    monkeypatch.setattr(rr, "reload_index_state", lambda: None)
    monkeypatch.setattr(rr, "rollback_qdrant_alias_if_needed",
                        lambda qdrant, name, emit=None: {"state": "noop"})
    # Il pre-check R14 non e' l'oggetto di questi test end-to-end (il client Qdrant e'
    # una stringa finta): reso esplicitamente no-op invece di dipendere dal fatto che
    # degradi da solo su un client non valido.
    monkeypatch.setattr(rr, "assert_rollback_target_has_vectors",
                        lambda qdrant, target_version: None)
    response = asyncio.run(rr.index_rollback(_FakeJsonRequest(None)))
    return response, alerts


def test_index_rollback_end_to_end_incremental_lineage_warns(monkeypatch, tmp_path):
    """Sandbox reale: full v1 su C1 → incrementale v2 che eredita C1 (CURRENT=v2) →
    rollback alla precedente. La detection VERA trova v2, la risposta porta la
    qdrant_note e l'alert warning finisce su alerts.jsonl."""
    response, alerts = _call_index_rollback_on_sandbox(
        monkeypatch, tmp_path,
        versions={"v20260101T000000": "vibecraft_events__v20260101T000000",
                  "v20260102T000000": "vibecraft_events__v20260101T000000"},
        current="v20260102T000000",
    )
    assert response["rolled_back_to"] == "v20260101T000000"
    assert response["qdrant_note"]["state"] == "shared_collection_not_rewound"
    assert response["qdrant_note"]["later_versions"] == ["v20260102T000000"]
    alert = json.loads(alerts.read_text(encoding="utf-8").splitlines()[-1])
    assert alert["level"] == "warning" and alert["source"] == "rollback"


def test_index_rollback_end_to_end_cross_lineage_does_not_warn(monkeypatch, tmp_path):
    """Sandbox reale: full v1 su C1 → full v2 su C2 (CURRENT=v2) → rollback alla
    precedente. Lineage distinti: nessuna qdrant_note, nessun alert."""
    response, alerts = _call_index_rollback_on_sandbox(
        monkeypatch, tmp_path,
        versions={"v20260101T000000": "vibecraft_events__v20260101T000000",
                  "v20260102T000000": "vibecraft_events__v20260102T000000"},
        current="v20260102T000000",
    )
    assert response["rolled_back_to"] == "v20260101T000000"
    assert "qdrant_note" not in response
    assert not alerts.exists()


def test_index_rollback_local_failure_never_calls_qdrant_alias_helper(monkeypatch):
    """Se il rollback locale fallisce (versione inesistente), la route deve uscire
    con l'errore HTTP prima di toccare qualunque logica di alias Qdrant."""
    import api.routes_reindex as rr
    from fastapi import HTTPException

    monkeypatch.setattr(rr, "writer_lock", lambda *a, **k: contextlib.nullcontext())
    monkeypatch.setitem(rr.state, "qdrant", "fake-qdrant-client")
    monkeypatch.setattr(rr, "resolve_rollback_target", lambda target: "v-missing")
    monkeypatch.setattr(rr, "assert_rollback_target_has_vectors", lambda *a: None)

    def _boom(target):
        raise FileNotFoundError(f"versione inesistente: {target}")

    monkeypatch.setattr(rr, "rollback_version", _boom)

    def _should_not_be_called(*a, **k):
        raise AssertionError("rollback_qdrant_alias_if_needed non deve essere chiamata se il rollback locale fallisce")

    monkeypatch.setattr(rr, "rollback_qdrant_alias_if_needed", _should_not_be_called)

    import asyncio
    try:
        asyncio.run(rr.index_rollback(_FakeJsonRequest(None)))
        assert False, "doveva sollevare HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/index/rollback sotto il writer lock cross-processo: l'intera mutazione
# (CURRENT + alias Qdrant) è in mutua esclusione con la promote dei job full. Il lock
# punta sempre a un file in tmp_path (mai il database/.writer.lock reale) e l'autouse
# _noop_writer_lock non copre api.routes_reindex, quindi lo patchiamo esplicitamente.
# ---------------------------------------------------------------------------
def test_index_rollback_409_when_writer_lock_held_and_leaves_state_untouched(tmp_path, monkeypatch):
    """Un altro handle detiene il writer lock (come un job full in promote): il route
    risponde 409 SENZA muovere CURRENT né toccare l'alias Qdrant — nessun rollback
    parziale sotto contesa. Il 409 è distinguibile da quello del ValueError."""
    import asyncio
    import api.routes_reindex as rr
    from fastapi import HTTPException
    from core.writer_lock import writer_lock

    lock_file = tmp_path / ".writer.lock"
    monkeypatch.setattr(rr, "_ROLLBACK_WRITER_LOCK_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(rr, "writer_lock",
                        lambda timeout_seconds: writer_lock(timeout_seconds, lock_path=lock_file))
    monkeypatch.setitem(rr.state, "qdrant", "fake-qdrant-client")

    called = {"rollback_version": False, "alias": False}

    def _rollback_version(target):
        called["rollback_version"] = True
        return "v1"

    def _alias(*a, **k):
        called["alias"] = True
        return {"state": "noop"}

    monkeypatch.setattr(rr, "rollback_version", _rollback_version)
    monkeypatch.setattr(rr, "rollback_qdrant_alias_if_needed", _alias)
    monkeypatch.setattr(rr, "reload_index_state", lambda: None)

    # Un altro handle (thread principale del test) tiene il lock per tutta la richiesta:
    # il thread del threadpool apre un handle diverso e fallisce entro il timeout corto.
    with writer_lock(timeout_seconds=5, lock_path=lock_file):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(rr.index_rollback(_FakeJsonRequest(None)))

    assert exc_info.value.status_code == 409
    assert "writer lock occupato" in exc_info.value.detail.lower()
    assert called["rollback_version"] is False  # CURRENT mai mosso
    assert called["alias"] is False             # alias Qdrant mai toccato


def test_index_rollback_succeeds_when_writer_lock_free(tmp_path, monkeypatch):
    """A lock LIBERO il route si comporta come prima: esegue la mutazione sotto il lock
    VERO (un file in tmp_path, non un no-op) e risponde con rolled_back_to e qdrant_alias.

    Passa da `_call_index_rollback` invece di rifarsi a mano il proprio set di patch. Il
    set duplicato era rimasto indietro quando la route ha iniziato a chiamare
    `resolve_rollback_target` (S2): quella funzione risolve la versione leggendo il
    `database/versions/` VERO, quindi il test continuava a passare su una macchina di
    sviluppo — dove l'indice c'e' — e falliva su un checkout pulito, cioe' esattamente e
    solo in CI. Restavano scoperti allo stesso modo `assert_rollback_target_has_vectors` e
    `rollback_shares_collection_with_later_versions`, che pure leggono lo stato reale.
    """
    import api.routes_reindex as rr
    from core.writer_lock import writer_lock

    lock_file = tmp_path / ".writer.lock"
    monkeypatch.setattr(rr, "_ROLLBACK_WRITER_LOCK_TIMEOUT_SECONDS", 0.3)

    response, _ = _call_index_rollback(
        monkeypatch,
        qdrant_alias_result={"state": "swapped"},
        writer_lock=lambda timeout_seconds: writer_lock(timeout_seconds, lock_path=lock_file),
    )
    assert response["rolled_back_to"] == "v1"
    assert response["qdrant_alias"]["state"] == "swapped"


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
    assert restored.queue_duration_seconds is None
    assert restored.reload_duration_seconds is None
    assert restored.snapshot_ready_duration_seconds is None

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

    assert mgr.join_all()

    # Dopo la compattazione ci deve essere al più UNA riga per job.
    lines = [line for line in journal.read_text(encoding="utf-8").splitlines() if line.strip()]
    seen_ids = [json.loads(line)["job_id"] for line in lines]
    assert len(seen_ids) == len(set(seen_ids))  # nessun duplicato: compattato
    # Tutti gli stati compattati sono terminali (completed).
    assert all(json.loads(line)["status"] == "completed" for line in lines)
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

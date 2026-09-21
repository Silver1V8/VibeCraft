"""Versionamento blue/green degli artefatti (core.artifacts): build→promote con CURRENT
aggiornato, rollback istantaneo, retention che non tocca mai la versione attiva,
retrocompatibilità col layout flat legacy e auto-reload del server che segue CURRENT."""
import networkx as nx
import numpy as np
import pytest
import shutil
import subprocess
import sys

from core import artifacts


@pytest.fixture
def db(monkeypatch, tmp_path):
    """Sandbox su database/: versioni + CURRENT + percorsi flat legacy in tmp_path."""
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)
    mapping = {
        "GRAPH_JSON_PATH": "graph.json",
        "COLBERT_NPZ_PATH": "colbert.npz",
        "CHUNKS_JSON_PATH": "chunks.json",
        "DENSE_NPZ_PATH": "dense.npz",
        "CODE_NPZ_PATH": "code.npz",
        "CODE_JSON_PATH": "code.json",
    }
    for attr, fname in mapping.items():
        monkeypatch.setattr(artifacts, attr, tmp_path / fname)
    return tmp_path


def _graph(marker: str) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node(marker, type="document")
    return g


def _save(marker: str) -> str:
    """Salva una versione il cui grafo contiene il solo nodo `marker` (riconoscibile)."""
    version = artifacts.save_artifacts(_graph(marker), {}, {}, {}, {})
    artifacts._atomic_write_json(artifacts.manifest_path(version),
                                 {"artifact_hashes": artifacts.artifact_hashes(version)})
    return version


# ---------------------------------------------------------------------------
# build → promote: CURRENT aggiornato, lo swap è il solo spostamento del puntatore
# ---------------------------------------------------------------------------
def test_save_creates_new_version_without_touching_current(db):
    v1 = _save("a")
    assert (db / "versions" / v1 / "graph.json").exists()
    # Nessuna promozione: CURRENT non esiste e non c'è alcuna versione attiva
    assert not (db / "CURRENT").exists()
    assert artifacts.current_version() is None


def test_promote_moves_current_and_load_follows(db):
    v1 = _save("a")
    artifacts.promote_version(v1)
    assert (db / "CURRENT").read_text(encoding="utf-8").strip() == v1
    assert artifacts.current_version() == v1

    arts = artifacts.load_artifacts()
    assert "a" in arts.graph and arts.version == v1

    # Una seconda build NON promossa resta invisibile alla lettura (blue/green)...
    v2 = _save("b")
    assert v2 != v1
    assert "a" in artifacts.load_artifacts().graph
    # ...finché non viene promossa: lo swap è atomico (solo CURRENT cambia).
    artifacts.promote_version(v2)
    assert "b" in artifacts.load_artifacts().graph
    # La versione non attiva resta su disco, leggibile esplicitamente.
    assert "a" in artifacts.load_artifacts(version=v1).graph


def test_implicit_load_retries_current_changed_before_lease(db, monkeypatch):
    old, new = _save("old"), _save("new")
    artifacts.promote_version(old)
    real_open = artifacts.ColbertStore.open_version
    calls = 0
    def racing_open(database, version):
        nonlocal calls
        calls += 1
        if version == old:
            artifacts._atomic_write_text(db / "CURRENT", new + "\n")
            shutil.rmtree(artifacts.version_dir(old))
            raise FileNotFoundError("old version pruned before lease")
        return real_open(database, version)
    monkeypatch.setattr(artifacts.ColbertStore, "open_version", racing_open)
    loaded = artifacts.load_artifacts(required=("graph", "colbert"))
    assert loaded.version == new and "new" in loaded.graph
    assert calls == 2
    loaded.colbert_store.close()
    with pytest.raises(FileNotFoundError):
        artifacts.load_artifacts(version=old)


def test_promote_rejects_missing_or_legacy_version(db):
    with pytest.raises(FileNotFoundError):
        artifacts.promote_version("v_inesistente")
    with pytest.raises(ValueError):
        artifacts.promote_version(artifacts.LEGACY_VERSION)


def test_every_save_gets_a_distinct_version(db):
    names = {_save(m) for m in ("a", "b", "c")}
    assert len(names) == 3
    assert artifacts.list_versions() == sorted(names)


# ---------------------------------------------------------------------------
# save_artifacts con nome di versione PRE-GENERATO (blue/green Qdrant, S1): il nome
# deve poter essere deciso a monte del salvataggio, col comportamento di default
# (nessun nome passato) invariato.
# ---------------------------------------------------------------------------
def test_save_with_explicit_version_name_uses_it_verbatim(db):
    v = artifacts.save_artifacts(_graph("a"), {}, {}, {}, {}, version="v-candidata-01")
    assert v == "v-candidata-01"
    assert (db / "versions" / "v-candidata-01" / "graph.json").exists()
    # Nessuna promozione: identico al percorso di default, CURRENT resta intoccato.
    assert not (db / "CURRENT").exists()


def test_save_with_duplicate_explicit_version_name_is_rejected(db):
    artifacts.save_artifacts(_graph("a"), {}, {}, {}, {}, version="v-dup")
    with pytest.raises(FileExistsError):
        artifacts.save_artifacts(_graph("b"), {}, {}, {}, {}, version="v-dup")
    # Il fallimento è sicuro: la versione originale non viene toccata/sovrascritta.
    graph_json = (db / "versions" / "v-dup" / "graph.json").read_text(encoding="utf-8")
    assert '"a"' in graph_json and '"b"' not in graph_json


def test_save_with_legacy_sentinel_as_explicit_version_is_rejected(db):
    with pytest.raises(ValueError):
        artifacts.save_artifacts(_graph("a"), {}, {}, {}, {}, version=artifacts.LEGACY_VERSION)


def test_save_default_behavior_unchanged_when_version_not_passed(db):
    # Nessuna regressione: senza l'argomento, il nome è ancora generato da
    # _new_version_name() come prima di S1.
    v = _save("a")
    assert v.startswith("v")
    assert (db / "versions" / v / "graph.json").exists()


# ---------------------------------------------------------------------------
# Rollback: sposta solo il puntatore, default = versione precedente
# ---------------------------------------------------------------------------
def test_rollback_default_goes_to_previous_version(db):
    v1, v2 = _save("a"), _save("b")
    artifacts.promote_version(v1)
    artifacts.promote_version(v2)

    assert artifacts.rollback_version() == v1
    assert artifacts.current_version() == v1
    assert "a" in artifacts.load_artifacts().graph
    # Rollback esplicito "in avanti": qualunque versione esistente è un target valido.
    assert artifacts.rollback_version(v2) == v2
    assert "b" in artifacts.load_artifacts().graph


def test_rollback_errors(db):
    with pytest.raises(FileNotFoundError):       # nessuna versione su disco
        artifacts.rollback_version()
    v1 = _save("a")
    artifacts.promote_version(v1)
    with pytest.raises(ValueError):              # la più vecchia non ha una precedente
        artifacts.rollback_version()
    with pytest.raises(FileNotFoundError):       # target inesistente
        artifacts.rollback_version("v_fantasma")


def test_resolve_rollback_target_non_sposta_current(db):
    """`resolve_rollback_target` e' la sola risoluzione, senza mutazione: e' cio' che
    permette ai chiamanti di pre-verificare il target (R14) prima di muovere CURRENT.
    Stessa risoluzione e stesse eccezioni di rollback_version."""
    v1, v2 = _save("a"), _save("b")
    artifacts.promote_version(v1)
    artifacts.promote_version(v2)

    assert artifacts.resolve_rollback_target() == v1
    assert artifacts.resolve_rollback_target(v1) == v1
    assert artifacts.current_version() == v2  # nulla e' stato mosso
    with pytest.raises(FileNotFoundError):
        artifacts.resolve_rollback_target("v_fantasma")
    assert artifacts.current_version() == v2


# ---------------------------------------------------------------------------
# Retention: ultime N versioni, mai quella puntata da CURRENT
# ---------------------------------------------------------------------------
def test_retention_prunes_oldest_beyond_keep(db, monkeypatch):
    monkeypatch.setenv("VIBECRAFT_INDEX_KEEP", "2")
    versions = [_save(m) for m in ("a", "b", "c", "d")]
    artifacts.promote_version(versions[-1])  # promote applica la retention

    assert artifacts.list_versions() == versions[-2:]
    assert artifacts.current_version() == versions[-1]


def test_retention_never_removes_active_version(db, monkeypatch):
    """Dopo un rollback la versione attiva può essere antica: la retention la salta."""
    monkeypatch.setenv("VIBECRAFT_INDEX_KEEP", "2")
    old = _save("old")
    artifacts.promote_version(old)
    newer = [_save(m) for m in ("b", "c", "d")]

    removed = artifacts.prune_versions()
    survivors = artifacts.list_versions()
    assert old in survivors                       # attiva, mai eliminata
    assert survivors[-2:] == newer[-2:]           # le ultime 2 restano
    assert newer[0] in removed                    # la vecchia non attiva è stata potata
    assert "old" in artifacts.load_artifacts().graph


def test_retention_env_invalid_falls_back_to_default(db, monkeypatch):
    monkeypatch.setenv("VIBECRAFT_INDEX_KEEP", "banane")
    for m in "abcdefg":
        artifacts.promote_version(_save(m))
    assert len(artifacts.list_versions()) == artifacts.DEFAULT_KEEP_VERSIONS


def test_retention_pinned_reader_and_failed_delete_are_retried(db, monkeypatch):
    old = _save("old")
    reader = artifacts.load_artifacts(version=old).colbert_store
    _save("middle")
    _save("new")
    assert old not in artifacts.prune_versions(keep=1)
    assert artifacts.version_dir(old).exists()
    reader.close()

    real_rmtree = shutil.rmtree
    def fail_old(path, *args, **kwargs):
        if path == artifacts.version_dir(old):
            raise PermissionError("simulated Windows open-file failure")
        return real_rmtree(path, *args, **kwargs)
    monkeypatch.setattr(artifacts.shutil, "rmtree", fail_old)
    assert old not in artifacts.prune_versions(keep=1)
    assert artifacts.version_dir(old).exists()
    monkeypatch.setattr(artifacts.shutil, "rmtree", real_rmtree)
    assert old in artifacts.prune_versions(keep=1)
    assert not artifacts.version_dir(old).exists()


def test_retention_respects_reader_in_another_process(db):
    old = _save("old")
    _save("new")
    script = ("import sys; from core.colbert_store import ColbertStore; "
              "store=ColbertStore.open_version(sys.argv[1],sys.argv[2]); "
              "print('READY',flush=True); sys.stdin.readline(); store.close()")
    child = subprocess.Popen([sys.executable, "-B", "-c", script, str(db), old],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "READY"
        assert old not in artifacts.prune_versions(keep=1)
        assert artifacts.version_dir(old).exists()
    finally:
        child.stdin.write("done\n")
        child.stdin.flush()
        child.communicate(timeout=20)
    assert child.returncode == 0
    assert old in artifacts.prune_versions(keep=1)


# ---------------------------------------------------------------------------
# Retrocompat: layout flat legacy senza CURRENT
# ---------------------------------------------------------------------------
def _write_legacy_flat(db):
    """Simula il layout precedente al versionamento: file flat in database/."""
    artifacts._atomic_write_json(artifacts.GRAPH_JSON_PATH,
                                 artifacts._graph_to_json(_graph("legacy-doc")))
    artifacts._atomic_write_json(artifacts.CHUNKS_JSON_PATH, {"c#00": {"doc_id": "c"}})


def test_legacy_flat_layout_still_loads(db):
    _write_legacy_flat(db)
    assert artifacts.current_version() == artifacts.LEGACY_VERSION
    arts = artifacts.load_artifacts()
    assert "legacy-doc" in arts.graph
    assert arts.version == artifacts.LEGACY_VERSION
    assert arts.source == "json"


def test_first_save_after_legacy_creates_versioned_layout(db):
    _write_legacy_flat(db)
    v1 = _save("nuovo-doc")
    # Finché non si promuove, si continua a leggere il legacy...
    assert "legacy-doc" in artifacts.load_artifacts().graph
    artifacts.promote_version(v1)
    # ...poi CURRENT vince sul flat (che resta su disco, ignorato).
    assert artifacts.current_version() == v1
    assert "nuovo-doc" in artifacts.load_artifacts().graph


def test_current_pointing_to_missing_dir_falls_back(db):
    """CURRENT corrotto (versione cancellata a mano): niente crash, fallback legacy/None."""
    (db / "CURRENT").write_text("v_sparita\n", encoding="utf-8")
    assert artifacts.current_version() is None
    _write_legacy_flat(db)
    assert artifacts.current_version() == artifacts.LEGACY_VERSION


# ---------------------------------------------------------------------------
# Auto-reload del server: _graph_version osserva CURRENT, il reload segue il puntatore
# ---------------------------------------------------------------------------
def _patch_deps(monkeypatch, db):
    from api import deps

    monkeypatch.setattr(deps, "GRAPH_JSON_PATH", db / "graph.json")
    monkeypatch.setattr(deps, "load_rule_descriptions", lambda: {})
    return deps


def test_server_reload_follows_current(db, monkeypatch):
    deps = _patch_deps(monkeypatch, db)

    vector = np.ones((1, 2), dtype=np.float16)
    v1 = artifacts.save_artifacts(_graph("a"), {"c": vector}, {"c": {"doc_id": "a"}}, {}, {})
    artifacts._atomic_write_json(artifacts.manifest_path(v1),
                                 {"artifact_hashes": artifacts.artifact_hashes(v1)})
    artifacts.promote_version(v1)
    deps.reload_index_state()
    assert "a" in deps.current_snapshot().graph
    assert deps.current_snapshot().version == v1    # la version dello snapshot è CURRENT

    # Promozione di una nuova versione: maybe_reload_graph vede CURRENT cambiato.
    v2 = artifacts.save_artifacts(_graph("b"), {"c": vector}, {"c": {"doc_id": "b"}}, {}, {})
    artifacts._atomic_write_json(artifacts.manifest_path(v2),
                                 {"artifact_hashes": artifacts.artifact_hashes(v2)})
    artifacts.promote_version(v2)
    deps.maybe_reload_graph()
    assert "b" in deps.current_snapshot().graph

    # Rollback: CURRENT torna a v1 e il reload segue il puntatore all'indietro.
    artifacts.rollback_version()
    deps.maybe_reload_graph()
    assert "a" in deps.current_snapshot().graph
    assert deps.current_snapshot().version == v1

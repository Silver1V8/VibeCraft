"""Versionamento blue/green degli artefatti (core.artifacts): build→promote con CURRENT
aggiornato, rollback istantaneo, retention che non tocca mai la versione attiva,
retrocompatibilità col layout flat legacy e auto-reload del server che segue CURRENT."""
import networkx as nx
import pytest

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
        "GRAPH_SAVE_PATH": "graph.pkl",
        "COLBERT_SAVE_PATH": "colbert.pkl",
        "CHUNKS_SAVE_PATH": "chunks.pkl",
        "DENSE_SAVE_PATH": "dense.pkl",
        "CODE_SAVE_PATH": "code.pkl",
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
    return artifacts.save_artifacts(_graph(marker), {}, {}, {}, {})


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
    monkeypatch.setattr(deps, "GRAPH_SAVE_PATH", db / "graph.pkl")
    monkeypatch.setattr(deps, "load_rule_descriptions", lambda: {})
    return deps


def test_server_reload_follows_current(db, monkeypatch):
    deps = _patch_deps(monkeypatch, db)

    v1 = artifacts.save_artifacts(_graph("a"), {"c": 1}, {"c": {}}, {}, {})
    artifacts.promote_version(v1)
    deps.reload_index_state()
    assert "a" in deps.current_snapshot().graph
    assert deps.current_snapshot().version == v1    # la version dello snapshot è CURRENT

    # Promozione di una nuova versione: maybe_reload_graph vede CURRENT cambiato.
    v2 = artifacts.save_artifacts(_graph("b"), {"c": 1}, {"c": {}}, {}, {})
    artifacts.promote_version(v2)
    deps.maybe_reload_graph()
    assert "b" in deps.current_snapshot().graph

    # Rollback: CURRENT torna a v1 e il reload segue il puntatore all'indietro.
    artifacts.rollback_version()
    deps.maybe_reload_graph()
    assert "a" in deps.current_snapshot().graph
    assert deps.current_snapshot().version == v1

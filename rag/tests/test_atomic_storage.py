"""Test della robustezza dello storage degli artefatti indice:
1. scrittura ATOMICA (_atomic_write*): un crash a metà scrittura non deve mai lasciare
   un file troncato/corrotto, ma la versione precedente integra (o nessun file);
2. reload COERENTE (api.deps.reload_index_state): se uno dei tre pickle è mancante o
   corrotto, lo stato in memoria precedente va mantenuto, non degradato."""
import pickle

import networkx as nx
import pytest

from core import indexing


# ---------------------------------------------------------------------------
# 1. Scrittura atomica
# ---------------------------------------------------------------------------
def test_atomic_write_pickle_roundtrip(tmp_path):
    path = tmp_path / "graph.pkl"
    obj = {"a": 1, "b": [1, 2, 3]}
    indexing._atomic_write_pickle(path, obj)
    with open(path, "rb") as f:
        assert pickle.load(f) == obj
    # Nessun temporaneo orfano lasciato nella directory
    assert list(tmp_path.iterdir()) == [path]


def test_atomic_write_leaves_previous_version_on_crash(tmp_path):
    """Simula un crash a metà scrittura (il writer solleva prima del completamento):
    il file preesistente deve restare quello VECCHIO e integro, nessun troncamento."""
    path = tmp_path / "colbert.pkl"
    indexing._atomic_write_pickle(path, {"version": "vecchia"})

    def exploding_writer(f):
        f.write(b"dati parziali")   # scrive qualcosa...
        raise RuntimeError("crash simulato a metà scrittura")   # ...poi muore

    with pytest.raises(RuntimeError, match="crash simulato"):
        indexing._atomic_write(path, exploding_writer)

    # Il file su disco è ancora la versione precedente, perfettamente deserializzabile
    with open(path, "rb") as f:
        assert pickle.load(f) == {"version": "vecchia"}
    # E il temporaneo abortito è stato ripulito
    assert list(tmp_path.iterdir()) == [path]


def test_atomic_write_no_partial_file_when_absent(tmp_path):
    """Se il target non esisteva e la scrittura crasha, non deve comparire alcun file
    (né il target né un temporaneo orfano)."""
    path = tmp_path / "chunks.pkl"

    def exploding_writer(f):
        f.write(b"x" * 100)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        indexing._atomic_write(path, exploding_writer)

    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_write_index_manifest_has_version(tmp_path, monkeypatch):
    """Il manifest scritto atomicamente deve contenere il campo `version` (ISO)."""
    import json

    manifest_path = tmp_path / "index_manifest.json"
    monkeypatch.setattr(indexing, "INDEX_MANIFEST_PATH", manifest_path)
    indexing.write_index_manifest(points_count=7, nodes=3, edges=5)

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["version"], "il manifest deve avere un campo version non vuoto"
    # version e created_at sono lo stesso timestamp del giro di indicizzazione
    assert data["version"] == data["created_at"]
    assert list(tmp_path.iterdir()) == [manifest_path]   # nessun .tmp orfano


# ---------------------------------------------------------------------------
# 2. Reload coerente con artefatto corrotto
# ---------------------------------------------------------------------------
def _write_valid_artifacts(tmp_path):
    """Scrive tre pickle validi (graph/colbert/chunks) e ritorna i loro Path."""
    graph_path = tmp_path / "graph.pkl"
    colbert_path = tmp_path / "colbert.pkl"
    chunks_path = tmp_path / "chunks.pkl"
    g = nx.DiGraph()
    g.add_node("nuovo.md", type="document")
    indexing._atomic_write_pickle(graph_path, g)
    indexing._atomic_write_pickle(colbert_path, {"nuovo.md#00": [1, 2]})
    indexing._atomic_write_pickle(chunks_path, {"nuovo.md#00": {"text": "x"}})
    return graph_path, colbert_path, chunks_path


def _patch_paths(monkeypatch, deps, graph_path, colbert_path, chunks_path):
    monkeypatch.setattr(deps, "GRAPH_SAVE_PATH", graph_path)
    monkeypatch.setattr(deps, "COLBERT_SAVE_PATH", colbert_path)
    monkeypatch.setattr(deps, "CHUNKS_SAVE_PATH", chunks_path)
    # load_rule_descriptions fa I/O su docs/: la stubbiamo per isolare il test
    monkeypatch.setattr(deps, "load_rule_descriptions", lambda: {"R": "desc"})


def test_reload_all_valid_replaces_state(tmp_path, monkeypatch):
    from api import deps

    graph_path, colbert_path, chunks_path = _write_valid_artifacts(tmp_path)
    _patch_paths(monkeypatch, deps, graph_path, colbert_path, chunks_path)

    # stato precedente "vecchio"
    old_graph = nx.DiGraph()
    old_graph.add_node("vecchio.md", type="document")
    deps.state.update({"graph": old_graph, "colbert_store": {"old": 1}, "chunks": {"old": 1}})

    deps.reload_index_state()

    assert "nuovo.md" in deps.state["graph"]
    assert deps.state["colbert_store"] == {"nuovo.md#00": [1, 2]}
    assert deps.state["chunks"] == {"nuovo.md#00": {"text": "x"}}


def test_reload_with_corrupt_artifact_keeps_previous(tmp_path, monkeypatch):
    from api import deps

    graph_path, colbert_path, chunks_path = _write_valid_artifacts(tmp_path)
    _patch_paths(monkeypatch, deps, graph_path, colbert_path, chunks_path)

    # Corrompe uno dei tre artefatti (colbert.pkl) con byte non deserializzabili
    colbert_path.write_bytes(b"\x00\x01 non e' un pickle valido")

    old_graph = nx.DiGraph()
    old_graph.add_node("vecchio.md", type="document")
    deps.state.update({
        "graph": old_graph,
        "colbert_store": {"old": 1},
        "chunks": {"old": 1},
        "rule_descriptions": {"OLD": "x"},
    })

    deps.reload_index_state()

    # Stato precedente MANTENUTO: nessun reload parziale/degradato
    assert "vecchio.md" in deps.state["graph"]
    assert "nuovo.md" not in deps.state["graph"]
    assert deps.state["colbert_store"] == {"old": 1}
    assert deps.state["chunks"] == {"old": 1}
    assert deps.state["rule_descriptions"] == {"OLD": "x"}


def test_reload_with_missing_artifact_keeps_previous(tmp_path, monkeypatch):
    from api import deps

    graph_path, colbert_path, chunks_path = _write_valid_artifacts(tmp_path)
    _patch_paths(monkeypatch, deps, graph_path, colbert_path, chunks_path)

    chunks_path.unlink()   # uno dei tre manca del tutto

    old_graph = nx.DiGraph()
    old_graph.add_node("vecchio.md", type="document")
    deps.state.update({"graph": old_graph, "colbert_store": {"old": 1}, "chunks": {"old": 1}})

    deps.reload_index_state()

    assert "vecchio.md" in deps.state["graph"]
    assert deps.state["chunks"] == {"old": 1}

"""Test della robustezza dello storage degli artefatti indice:
1. scrittura ATOMICA (core.artifacts._atomic_write*): un crash a metà scrittura non
   deve mai lasciare un file troncato/corrotto, ma la versione precedente integra (o
   nessun file);
2. reload COERENTE (api.deps.reload_index_state): se uno degli artefatti (grafo,
   ColBERT, chunk) è mancante o corrotto, lo stato in memoria precedente va mantenuto,
   non degradato."""
import numpy as np
import networkx as nx
import pytest

from core import artifacts
from core import indexing


# ---------------------------------------------------------------------------
# 1. Scrittura atomica (primitiva condivisa in core.artifacts)
# ---------------------------------------------------------------------------
def test_atomic_write_roundtrip(tmp_path):
    path = tmp_path / "artifact.bin"
    artifacts._atomic_write(path, lambda f: f.write(b"contenuto"))
    assert path.read_bytes() == b"contenuto"
    # Nessun temporaneo orfano lasciato nella directory
    assert list(tmp_path.iterdir()) == [path]


def test_atomic_write_leaves_previous_version_on_crash(tmp_path):
    """Simula un crash a metà scrittura (il writer solleva prima del completamento):
    il file preesistente deve restare quello VECCHIO e integro, nessun troncamento."""
    path = tmp_path / "artifact.bin"
    artifacts._atomic_write(path, lambda f: f.write(b"vecchia"))

    def exploding_writer(f):
        f.write(b"dati parziali")   # scrive qualcosa...
        raise RuntimeError("crash simulato a metà scrittura")   # ...poi muore

    with pytest.raises(RuntimeError, match="crash simulato"):
        artifacts._atomic_write(path, exploding_writer)

    # Il file su disco è ancora la versione precedente, integra
    assert path.read_bytes() == b"vecchia"
    # E il temporaneo abortito è stato ripulito
    assert list(tmp_path.iterdir()) == [path]


def test_atomic_write_no_partial_file_when_absent(tmp_path):
    """Se il target non esisteva e la scrittura crasha, non deve comparire alcun file
    (né il target né un temporaneo orfano)."""
    path = tmp_path / "artifact.bin"

    def exploding_writer(f):
        f.write(b"x" * 100)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        artifacts._atomic_write(path, exploding_writer)

    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_write_index_manifest_has_version(tmp_path, monkeypatch):
    """Il manifest scritto atomicamente deve contenere il campo `version` (ISO) e la
    sezione `artifact_hashes` (anche vuota se non ci sono artefatti su disco)."""
    import json

    # Sandbox su database/: nessuna versione promossa -> il manifest va nel flat legacy.
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "GRAPH_JSON_PATH", tmp_path / "graph.json")
    monkeypatch.setattr(artifacts, "GRAPH_SAVE_PATH", tmp_path / "graph.pkl")
    manifest_path = tmp_path / "index_manifest.json"
    indexing.write_index_manifest(points_count=7, nodes=3, edges=5)

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["version"], "il manifest deve avere un campo version non vuoto"
    # version e created_at sono lo stesso timestamp del giro di indicizzazione
    assert data["version"] == data["created_at"]
    assert "artifact_hashes" in data
    assert list(tmp_path.iterdir()) == [manifest_path]   # nessun .tmp orfano


# ---------------------------------------------------------------------------
# 2. Reload coerente con artefatto corrotto/mancante
# ---------------------------------------------------------------------------
def _patch_artifact_paths(monkeypatch, tmp_path):
    """Reindirizza database/ (versioni + CURRENT) e i percorsi flat degli artefatti
    (nuovi formati + legacy) su una sandbox, sia in core.artifacts (I/O) sia in
    api.deps (mtime/version)."""
    from api import deps

    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "GRAPH_JSON_PATH", tmp_path / "graph.json")
    monkeypatch.setattr(artifacts, "COLBERT_NPZ_PATH", tmp_path / "colbert.npz")
    monkeypatch.setattr(artifacts, "CHUNKS_JSON_PATH", tmp_path / "chunks.json")
    monkeypatch.setattr(artifacts, "DENSE_NPZ_PATH", tmp_path / "dense.npz")
    monkeypatch.setattr(artifacts, "CODE_NPZ_PATH", tmp_path / "code.npz")
    monkeypatch.setattr(artifacts, "CODE_JSON_PATH", tmp_path / "code.json")
    for name in ("GRAPH_SAVE_PATH", "COLBERT_SAVE_PATH", "CHUNKS_SAVE_PATH",
                 "DENSE_SAVE_PATH", "CODE_SAVE_PATH"):
        monkeypatch.setattr(artifacts, name, tmp_path / name.lower().replace("_save_path", ".pkl"))
    monkeypatch.setattr(deps, "GRAPH_JSON_PATH", tmp_path / "graph.json")
    monkeypatch.setattr(deps, "GRAPH_SAVE_PATH", tmp_path / "graph.pkl")
    # load_rule_descriptions fa I/O su docs/: la stubbiamo per isolare il test
    monkeypatch.setattr(deps, "load_rule_descriptions", lambda: {"R": "desc"})


def _write_valid_artifacts():
    """Scrive e PROMUOVE un set completo di artefatti validi (grafo + ColBERT + chunk):
    la versione diventa quella attiva (CURRENT), come dopo una build reale."""
    g = nx.DiGraph()
    g.add_node("nuovo.md", type="document")
    version = artifacts.save_artifacts(
        g,
        colbert_store={"nuovo.md#00": np.array([[1.0, 2.0]], dtype="float16")},
        chunks_store={"nuovo.md#00": {"doc_id": "nuovo.md", "section": "s", "text": "x"}},
        dense_store={},
        code_store={},
    )
    artifacts.promote_version(version)


def _seed_old_snapshot(deps, rule_descriptions=None):
    """Installa uno snapshot 'vecchio' completo come stato precedente e lo ritorna."""
    old_graph = nx.DiGraph()
    old_graph.add_node("vecchio.md", type="document")
    old = deps.IndexSnapshot(
        graph=old_graph,
        colbert_store={"old": 1},
        chunks={"old": 1},
        rule_descriptions=rule_descriptions if rule_descriptions is not None else {"OLD": "x"},
        code_store={},
        version=1.0,
    )
    deps.state["snapshot"] = old
    return old


def test_reload_all_valid_replaces_snapshot(tmp_path, monkeypatch):
    """(a) Il reload sostituisce lo snapshot in UN colpo solo: un nuovo IndexSnapshot
    con tutti gli artefatti della nuova build, mai una mutazione parziale in place."""
    from api import deps

    _patch_artifact_paths(monkeypatch, tmp_path)
    _write_valid_artifacts()

    old = _seed_old_snapshot(deps)

    deps.reload_index_state()

    snap = deps.current_snapshot()
    # È un OGGETTO nuovo (rebind atomico), non lo stesso mutato
    assert snap is not old
    assert "nuovo.md" in snap.graph
    assert set(snap.colbert_store) == {"nuovo.md#00"}
    assert snap.chunks == {"nuovo.md#00": {"doc_id": "nuovo.md", "section": "s", "text": "x"}}
    assert snap.rule_descriptions == {"R": "desc"}


def test_reference_taken_before_reload_stays_coherent(tmp_path, monkeypatch):
    """(b) Un riferimento allo snapshot preso PRIMA del reload resta internamente coerente
    (la vecchia versione completa), immune al rebind successivo — è il cuore di HARDENING #3."""
    from api import deps

    _patch_artifact_paths(monkeypatch, tmp_path)
    _write_valid_artifacts()

    _seed_old_snapshot(deps)
    # L'handler prende lo snapshot una volta a inizio richiesta
    snap_in_flight = deps.current_snapshot()

    # ...mentre un reload rimpiazza atomicamente lo snapshot globale
    deps.reload_index_state()

    # Il riferimento in mano all'handler è ancora la versione VECCHIA e coerente
    assert "vecchio.md" in snap_in_flight.graph
    assert "nuovo.md" not in snap_in_flight.graph
    assert snap_in_flight.colbert_store == {"old": 1}
    assert snap_in_flight.chunks == {"old": 1}
    # ...e lo stato globale intanto punta alla nuova versione
    assert "nuovo.md" in deps.current_snapshot().graph


def test_reload_with_corrupt_artifact_keeps_previous(tmp_path, monkeypatch):
    """(c) Reload fallito (artefatto corrotto) → lo snapshot precedente resta invariato."""
    from api import deps

    _patch_artifact_paths(monkeypatch, tmp_path)
    _write_valid_artifacts()

    # Corrompe uno degli artefatti della versione ATTIVA con byte non deserializzabili
    (artifacts.artifact_dir() / "colbert.npz").write_bytes(b"\x00\x01 non e' un npz valido")

    old = _seed_old_snapshot(deps)

    deps.reload_index_state()

    # Stato precedente MANTENUTO: stesso oggetto snapshot, nessun reload parziale/degradato
    snap = deps.current_snapshot()
    assert snap is old
    assert "vecchio.md" in snap.graph
    assert "nuovo.md" not in snap.graph
    assert snap.colbert_store == {"old": 1}
    assert snap.chunks == {"old": 1}
    assert snap.rule_descriptions == {"OLD": "x"}


def test_reload_with_missing_artifact_keeps_previous(tmp_path, monkeypatch):
    from api import deps

    _patch_artifact_paths(monkeypatch, tmp_path)
    _write_valid_artifacts()

    (artifacts.artifact_dir() / "chunks.json").unlink()   # uno degli artefatti richiesti manca del tutto

    old = _seed_old_snapshot(deps)

    deps.reload_index_state()

    snap = deps.current_snapshot()
    assert snap is old
    assert "vecchio.md" in snap.graph
    assert snap.chunks == {"old": 1}

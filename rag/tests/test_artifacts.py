"""Round-trip degli artefatti indice nei formati sicuri (JSON/.npz). Verifica che
save_artifacts→load_artifacts sia lossless per grafo (con attributi), vettori (fp16
identici) e sidecar testuali. Il fallback ai vecchi pickle legacy in lettura è stato
rimosso (A13, rag/AUDIT.md): nessun `.pkl` esisteva più nel progetto, e mantenere
pickle.load su un formato mai più prodotto era superficie di deserializzazione
arbitraria senza alcun beneficio."""
from datetime import date
from pathlib import Path

import numpy as np
import networkx as nx
import pytest

from core import artifacts
from core.retrieval import rank_sections_by_relevance


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """Reindirizza database/ (versioni + CURRENT) e tutti i percorsi artefatto flat
    su una dir temporanea."""
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


def _save_promoted(*stores) -> str:
    """save + promote in un colpo: il round-trip via load_artifacts segue CURRENT."""
    version = artifacts.save_artifacts(*stores)
    artifacts._atomic_write_json(artifacts.manifest_path(version),
                                 {"artifact_hashes": artifacts.artifact_hashes(version)})
    artifacts.promote_version(version)
    return version


def _sample_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    # Nodo-documento con attributi dal frontmatter, inclusi tipi NON-JSON (date, Path)
    g.add_node("spec.md", type="document", title="Spec",
               updated=date(2024, 1, 2), source=Path("docs/spec.md"),
               tags=["a", "b"], meta={"owner": "team"})
    g.add_node("UTENTE", type="entity")
    g.add_edge("spec.md", "UTENTE", relation="MENTIONS")
    return g


def test_graph_roundtrip_normalizes_non_json_attrs(sandbox):
    g = _sample_graph()
    _save_promoted(g, {}, {}, {}, {})
    loaded = artifacts.load_artifacts().graph

    # Topologia identica
    assert set(loaded.nodes) == {"spec.md", "UTENTE"}
    assert loaded.nodes["spec.md"]["type"] == "document"
    assert loaded.nodes["UTENTE"]["type"] == "entity"
    assert ("spec.md", "UTENTE") in loaded.edges
    assert loaded.edges["spec.md", "UTENTE"]["relation"] == "MENTIONS"
    assert isinstance(loaded, nx.DiGraph)

    # Attributi non-JSON normalizzati (date/Path -> stringhe), il resto preservato
    attrs = loaded.nodes["spec.md"]
    assert attrs["updated"] == "2024-01-02"
    assert attrs["source"] == "docs/spec.md"
    assert attrs["tags"] == ["a", "b"]
    assert attrs["meta"] == {"owner": "team"}


def test_graph_json_is_human_readable(sandbox):
    """Il grafo è persistito come JSON ispezionabile (non un blob binario)."""
    import json
    _save_promoted(_sample_graph(), {}, {}, {}, {})
    data = json.loads((artifacts.artifact_dir() / "graph.json").read_text(encoding="utf-8"))
    assert data["directed"] is True
    assert any(n["id"] == "spec.md" for n in data["nodes"])


def test_vectors_roundtrip_fp16_identical(sandbox):
    colbert = {
        "a.md#00": np.array([[0.1, 0.2, 0.3]], dtype="float16"),
        "b.md#01": np.array([[1.5, 2.5, 3.5], [3.5, 4.5, 5.5]], dtype="float16"),
    }
    dense = {"a.md#00": np.array([0.25, 0.75, 0.5], dtype="float16")}
    chunks = {"a.md#00": {"doc_id": "a.md"}, "b.md#01": {"doc_id": "b.md"}}
    _save_promoted(nx.DiGraph(), colbert, chunks, dense, {})

    arts = artifacts.load_artifacts()
    assert set(arts.colbert_store) == set(colbert)
    for k in colbert:
        assert arts.colbert_store[k].dtype == np.float16
        assert np.array_equal(arts.colbert_store[k], colbert[k])   # bit-identici (fp16)
    assert arts.dense_store["a.md#00"].dtype == np.float16
    assert np.array_equal(arts.dense_store["a.md#00"], dense["a.md#00"])


def test_chunks_sidecar_roundtrip(sandbox):
    chunks = {"a.md#00": {"doc_id": "a.md", "section": "Intro", "text": "corpo"}}
    _save_promoted(nx.DiGraph(), {"a.md#00": np.ones((1, 3), dtype=np.float16)}, chunks, {}, {})
    assert artifacts.load_artifacts().chunks_store == chunks


def test_code_store_split_merge_roundtrip(sandbox):
    code_store = {
        "svc.py::f": {
            "name": "f", "kind": "function", "file": "svc.py", "dev_type": "backend",
            "text": "def f(): ...", "deps": ["g"], "refs": ["ALPHA"], "links": [],
            "dense": np.array([0.1, 0.2], dtype="float16"),
        },
        # entry stile full-rebuild: senza deps/refs/links
        "svc.py::g": {
            "name": "g", "kind": "function", "file": "svc.py", "dev_type": "backend",
            "text": "def g(): ...", "dense": np.array([0.3, 0.4], dtype="float16"),
        },
    }
    _save_promoted(nx.DiGraph(), {}, {}, {}, code_store)
    loaded = artifacts.load_artifacts().code_store

    assert set(loaded) == set(code_store)
    for sid, entry in code_store.items():
        for k in ("name", "kind", "file", "dev_type", "text"):
            assert loaded[sid][k] == entry[k]
        assert np.array_equal(loaded[sid]["dense"], entry["dense"])
    assert loaded["svc.py::f"]["deps"] == ["g"]
    assert loaded["svc.py::f"]["refs"] == ["ALPHA"]
    # l'entry senza deps/refs/links non li acquisisce spuriamente
    assert "deps" not in loaded["svc.py::g"]


def test_save_writes_only_versioned_json_npz(sandbox):
    version = artifacts.save_artifacts(_sample_graph(), {}, {}, {}, {})
    vdir = artifacts.version_dir(version)
    # Solo i nuovi formati, nella directory della versione: nessun flat
    assert (vdir / "graph.json").exists()
    assert (vdir / "chunks.json").exists()
    assert not artifacts.GRAPH_JSON_PATH.exists()  # il layout flat non viene più scritto


def test_required_missing_raises(sandbox):
    with pytest.raises(FileNotFoundError):
        artifacts.load_artifacts(required=("graph",))


def test_empty_index_roundtrips(sandbox):
    """Un indice vuoto (nessun chunk/simbolo) round-trippa senza errori."""
    _save_promoted(nx.DiGraph(), {}, {}, {}, {})
    arts = artifacts.load_artifacts()
    assert arts.graph.number_of_nodes() == 0
    assert arts.colbert_store == {}
    assert arts.code_store == {}


def _legacy_npz_version(sandbox):
    vectors = {"a.md#00": np.array([[0.1, 0.2, 0.3]], dtype=np.float16),
               "a.md#01": np.array([[1.5, 2.5, 3.5]], dtype=np.float16)}
    chunks = {key: {"doc_id": "a.md"} for key in vectors}
    old = artifacts.save_artifacts(nx.DiGraph(), vectors, chunks, {}, {})
    folder = artifacts.version_dir(old)
    artifacts._save_vectors(folder / "colbert.npz", vectors)
    import shutil
    shutil.rmtree(folder / "colbert")
    artifacts._atomic_write_json(folder / "index_manifest.json",
                                 {"version": "old", "qdrant_collection": "unchanged",
                                  "artifact_hashes": artifacts.artifact_hashes(old)})
    artifacts.promote_version(old)
    return old, vectors


def test_npz_migration_is_exact_and_rollback_keeps_legacy_reader(sandbox):
    old, vectors = _legacy_npz_version(sandbox)
    candidate = artifacts.migrate_colbert_npy()
    assert candidate != old
    assert artifacts.current_version() == candidate
    assert not (artifacts.version_dir(candidate) / "colbert.npz").exists()
    assert (artifacts.version_dir(old) / "colbert.npz").exists()
    candidate_store = artifacts.load_artifacts().colbert_store
    for key, value in vectors.items():
        assert np.array_equal(candidate_store[key], value)
    query = np.array([[0.5, 0.25, 0.1]], dtype=np.float32)
    ranking = rank_sections_by_relevance(list(vectors), colbert_store=candidate_store,
                                         colbert_query=query)
    assert ranking == rank_sections_by_relevance(list(vectors), colbert_store=vectors,
                                                 colbert_query=query)
    assert candidate_store.get("missing") is None
    assert rank_sections_by_relevance(["missing"], colbert_store=candidate_store,
                                      colbert_query=query) == [("missing", None)]
    assert artifacts.artifact_hashes(candidate, deep=True) == artifacts._load_json(
        artifacts.manifest_path(candidate))["artifact_hashes"]
    candidate_store.close()
    artifacts.rollback_version(old)
    for key, value in vectors.items():
        assert np.array_equal(artifacts.load_artifacts().colbert_store[key], value)
    assert ranking == rank_sections_by_relevance(list(vectors),
                                                 colbert_store=artifacts.load_artifacts().colbert_store,
                                                 colbert_query=query)


def test_npz_migration_corruption_keeps_current(sandbox):
    old, _ = _legacy_npz_version(sandbox)
    with (artifacts.version_dir(old) / "colbert.npz").open("ab") as stream:
        stream.write(b"corrupt")
    with pytest.raises(ValueError, match="hashes"):
        artifacts.migrate_colbert_npy()
    assert artifacts.current_version() == old


def test_npz_migration_publish_failure_keeps_current(sandbox, monkeypatch):
    old, _ = _legacy_npz_version(sandbox)
    def reject(_version):
        raise RuntimeError("publish interrupted")
    monkeypatch.setattr(artifacts, "promote_version", reject)
    with pytest.raises(RuntimeError, match="publish interrupted"):
        artifacts.migrate_colbert_npy()
    assert artifacts.current_version() == old


def test_promotion_rejects_corrupt_npy_file_and_index(sandbox):
    vectors = {"a.md#00": np.array([[1, 2, 3]], dtype=np.float16)}
    chunks = {"a.md#00": {"doc_id": "a.md"}}
    version = artifacts.save_artifacts(nx.DiGraph(), vectors, chunks, {}, {})
    folder = artifacts.version_dir(version) / "colbert"
    hashes = artifacts.artifact_hashes(version)
    files = [name for name in hashes if name.endswith(".npy")]
    artifacts._atomic_write_json(artifacts.manifest_path(version),
                                 {"artifact_hashes": hashes, "colbert_new_files": [files[0].split("/")[-1]]})
    file = folder / files[0].split("/")[-1]
    with file.open("r+b") as stream:
        stream.seek(-1, 2)
        stream.write(b"X")
    with pytest.raises(ValueError, match="file hash"):
        artifacts.promote_version(version)
    assert artifacts.current_version_token() is None

    version2 = artifacts.save_artifacts(nx.DiGraph(), vectors, chunks, {}, {})
    folder2 = artifacts.version_dir(version2) / "colbert"
    artifacts._atomic_write_json(artifacts.manifest_path(version2),
                                 {"artifact_hashes": artifacts.artifact_hashes(version2)})
    index = artifacts._load_json(folder2 / "index.json")
    index["chunks"]["a.md#00"]["stop"] = 9999
    artifacts._atomic_write_json(folder2 / "index.json", index)
    with pytest.raises(ValueError):
        artifacts.promote_version(version2)
    assert artifacts.current_version_token() is None


def test_promotion_rejects_missing_npy_manifest(sandbox):
    version = artifacts.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    with pytest.raises(FileNotFoundError, match="manifest missing"):
        artifacts.promote_version(version)
    assert artifacts.current_version_token() is None


def test_promotion_rejects_malformed_candidate_metadata_even_with_matching_hash(sandbox):
    version = artifacts.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    (artifacts.version_dir(version) / "chunks.json").write_text("{invalid", encoding="utf-8")
    artifacts._atomic_write_json(artifacts.manifest_path(version),
                                 {"artifact_hashes": artifacts.artifact_hashes(version)})
    with pytest.raises(ValueError):
        artifacts.promote_version(version)
    assert artifacts.current_version_token() is None

"""Round-trip degli artefatti indice nei formati sicuri (JSON/.npz) e fallback ai
pickle legacy in lettura. Verifica che save_artifacts→load_artifacts sia lossless per
grafo (con attributi), vettori (fp16 identici) e sidecar testuali, e che i vecchi .pkl
vengano ancora letti con un warning che invita a re-indicizzare."""
import pickle
from datetime import date
from pathlib import Path

import numpy as np
import networkx as nx
import pytest

from core import artifacts


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """Reindirizza tutti i percorsi artefatto (nuovi + legacy) su una dir temporanea."""
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
    artifacts.save_artifacts(g, {}, {}, {}, {})
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
    artifacts.save_artifacts(_sample_graph(), {}, {}, {}, {})
    data = json.loads(artifacts.GRAPH_JSON_PATH.read_text(encoding="utf-8"))
    assert data["directed"] is True
    assert any(n["id"] == "spec.md" for n in data["nodes"])


def test_vectors_roundtrip_fp16_identical(sandbox):
    colbert = {
        "a.md#00": np.array([[0.1, 0.2, 0.3]], dtype="float16"),
        "b.md#01": np.array([[1.5, 2.5], [3.5, 4.5]], dtype="float16"),
    }
    dense = {"a.md#00": np.array([0.25, 0.75, 0.5], dtype="float16")}
    artifacts.save_artifacts(nx.DiGraph(), colbert, {}, dense, {})

    arts = artifacts.load_artifacts()
    assert set(arts.colbert_store) == set(colbert)
    for k in colbert:
        assert arts.colbert_store[k].dtype == np.float16
        assert np.array_equal(arts.colbert_store[k], colbert[k])   # bit-identici (fp16)
    assert arts.dense_store["a.md#00"].dtype == np.float16
    assert np.array_equal(arts.dense_store["a.md#00"], dense["a.md#00"])


def test_chunks_sidecar_roundtrip(sandbox):
    chunks = {"a.md#00": {"doc_id": "a.md", "section": "Intro", "text": "corpo"}}
    artifacts.save_artifacts(nx.DiGraph(), {}, chunks, {}, {})
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
    artifacts.save_artifacts(nx.DiGraph(), {}, {}, {}, code_store)
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


def test_save_writes_only_new_formats_no_pickle(sandbox):
    artifacts.save_artifacts(_sample_graph(), {}, {}, {}, {})
    # Nessun file .pkl scritto: solo i nuovi formati
    assert not artifacts.GRAPH_SAVE_PATH.exists()
    assert artifacts.GRAPH_JSON_PATH.exists()
    assert artifacts.CHUNKS_JSON_PATH.exists()


def test_fallback_reads_legacy_pickle_with_warning(sandbox):
    """Se i nuovi file non esistono ma i .pkl sì, load_artifacts legge i pickle e
    logga un warning che invita a re-indicizzare."""
    g = _sample_graph()
    with open(artifacts.GRAPH_SAVE_PATH, "wb") as f:
        pickle.dump(g, f)
    with open(artifacts.COLBERT_SAVE_PATH, "wb") as f:
        pickle.dump({"a.md#00": np.array([[1.0]], dtype="float16")}, f)
    with open(artifacts.CHUNKS_SAVE_PATH, "wb") as f:
        pickle.dump({"a.md#00": {"doc_id": "a.md", "section": "s", "text": "t"}}, f)

    logs: list[str] = []
    arts = artifacts.load_artifacts(emit=logs.append)

    assert arts.source == "pickle"
    assert "spec.md" in arts.graph
    assert arts.chunks_store["a.md#00"]["text"] == "t"
    assert any("legacy" in line.lower() or "re-indicizza" in line.lower() for line in logs)


def test_required_missing_raises(sandbox):
    with pytest.raises(FileNotFoundError):
        artifacts.load_artifacts(required=("graph",))


def test_empty_index_roundtrips(sandbox):
    """Un indice vuoto (nessun chunk/simbolo) round-trippa senza errori."""
    artifacts.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    arts = artifacts.load_artifacts()
    assert arts.graph.number_of_nodes() == 0
    assert arts.colbert_store == {}
    assert arts.code_store == {}

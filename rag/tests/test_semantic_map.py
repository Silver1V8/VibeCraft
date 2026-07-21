"""Test di core/graph_ops._find_duplicates (versione vettorizzata dei duplicati della
Semantic Map) e del troncamento dichiarato di semantic_map quando Qdrant restituisce
un next_page_offset non nullo. Non tocca soglie/semantica, PCA, community o betweenness."""
import logging

import networkx as nx
import numpy as np

from core import graph_ops


# ---------------------------------------------------------------------------
# Oracolo: il vecchio doppio loop O(n^2), reimplementato qui per l'equivalenza.
# ---------------------------------------------------------------------------
def _oracle_duplicates(mat, parents, chunk_ids, threshold=0.9, top=50):
    norm = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8)
    sims = norm @ norm.T
    duplicates = []
    for i in range(len(chunk_ids)):
        for j in range(i + 1, len(chunk_ids)):
            if sims[i, j] >= threshold and parents[i] != parents[j]:
                duplicates.append({"a": chunk_ids[i], "b": chunk_ids[j], "sim": round(float(sims[i, j]), 3)})
    duplicates.sort(key=lambda d: d["sim"], reverse=True)
    return duplicates[:top]


def _synthetic_matrix(seed=0, n=30, dim=16):
    """30 vettori casuali (cos-sim ~0 tra loro), con due doppioni pilotati:
    chunk-1 quasi identico a chunk-0 (documenti DIVERSI, deve contare) e
    chunk-2 quasi identico a chunk-0 (STESSO documento di chunk-0, non deve contare)."""
    rng = np.random.default_rng(seed)
    mat = rng.normal(size=(n, dim)).astype(np.float32)
    chunk_ids = [f"chunk-{i}" for i in range(n)]
    parents = [f"doc-{i % 6}" for i in range(n)]

    mat[1] = mat[0] + rng.normal(scale=1e-4, size=dim).astype(np.float32)  # cross-doc
    parents[2] = parents[0]
    mat[2] = mat[0] + rng.normal(scale=1e-4, size=dim).astype(np.float32)  # same-doc

    return mat, parents, chunk_ids


def test_find_duplicates_matches_oracle_double_loop():
    mat, parents, chunk_ids = _synthetic_matrix()
    got = graph_ops._find_duplicates(mat, parents, chunk_ids)
    expected = _oracle_duplicates(mat, parents, chunk_ids)
    assert got == expected


def test_find_duplicates_never_reports_same_doc_pairs():
    mat, parents, chunk_ids = _synthetic_matrix()
    got = graph_ops._find_duplicates(mat, parents, chunk_ids)
    id_to_parent = dict(zip(chunk_ids, parents))

    for d in got:
        assert id_to_parent[d["a"]] != id_to_parent[d["b"]]

    # coppia same-doc pilotata (chunk-0, chunk-2): mai riportata
    assert not any({d["a"], d["b"]} == {"chunk-0", "chunk-2"} for d in got)
    # coppia cross-doc pilotata (chunk-0, chunk-1): deve comparire
    assert any({d["a"], d["b"]} == {"chunk-0", "chunk-1"} for d in got)


def test_find_duplicates_capped_at_top_and_sorted_descending():
    n = 40
    dim = 8
    rng = np.random.default_rng(1)
    base = rng.normal(size=dim).astype(np.float32)
    # tutti i vettori quasi identici tra loro -> C(40,2)=780 coppie candidate, tutte >= soglia
    mat = np.stack([base + rng.normal(scale=1e-4, size=dim).astype(np.float32) for _ in range(n)])
    chunk_ids = [f"chunk-{i}" for i in range(n)]
    parents = [f"doc-{i}" for i in range(n)]  # tutti documenti diversi

    got = graph_ops._find_duplicates(mat, parents, chunk_ids, threshold=0.5, top=50)

    assert len(got) == 50
    sims = [d["sim"] for d in got]
    assert sims == sorted(sims, reverse=True)


# ---------------------------------------------------------------------------
# Troncamento dichiarato di semantic_map (next_page_offset da Qdrant)
# ---------------------------------------------------------------------------
class _Point:
    def __init__(self, vector, payload):
        self.vector = vector
        self.payload = payload


def _points(n=2):
    return [
        _Point({"dense": [1.0 if i == k else 0.0 for k in range(n)]},
               {"chunk_id": f"d{i}#00-a", "doc_id": f"d{i}"})
        for i in range(n)
    ]


class _FakeQdrantTruncated:
    def scroll(self, **kwargs):
        return _points(), "some-offset-token"


class _FakeQdrantComplete:
    def scroll(self, **kwargs):
        return _points(), None


def test_semantic_map_truncated_when_next_page_offset_present(caplog):
    with caplog.at_level(logging.WARNING, logger="core.graph_ops"):
        result = graph_ops.semantic_map(nx.DiGraph(), _FakeQdrantTruncated())
    assert result["truncated"] is True
    assert any("10000" in rec.message for rec in caplog.records)


def test_semantic_map_not_truncated_when_next_page_offset_none(caplog):
    with caplog.at_level(logging.WARNING, logger="core.graph_ops"):
        result = graph_ops.semantic_map(nx.DiGraph(), _FakeQdrantComplete())
    assert result["truncated"] is False
    assert not any("10000" in rec.message for rec in caplog.records)

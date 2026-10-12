"""Delta copy-on-write degli indici immutabili: copia Qdrant, equivalenza col full
rebuild, ripieghi. Riusa le fixture reali (registry, Qdrant memory/server) di
test_project_indexing."""
from uuid import NAMESPACE_URL, uuid5

import pytest
from qdrant_client.models import PointStruct, SparseVector

from core import indexing
from core.config import DENSE_DIM
from test_project_indexing import Embed, build, projects, qdrant  # noqa: F401


def _point(i: int, doc: str) -> PointStruct:
    dense = [0.0] * DENSE_DIM
    dense[i % DENSE_DIM] = 1.0
    return PointStruct(
        id=str(uuid5(NAMESPACE_URL, f"{doc}#{i}")),
        vector={"dense": dense, "sparse": SparseVector(indices=[i], values=[1.0])},
        payload={"doc_id": doc, "chunk_id": f"{doc}#{i}"},
    )


def _by_chunk(client, collection):
    points, _ = client.scroll(collection, limit=1000, with_payload=True, with_vectors=True)
    return {p.payload["chunk_id"]: p for p in points}


def test_clone_points_copies_vectors_and_payload_excluding_docs(projects, qdrant):  # noqa: F811
    a, _ = projects
    src, dst = a.collection_name + "__src", a.collection_name + "__dst"
    for name in (src, dst):
        indexing._ensure_collection(qdrant, collection_name=name)
    qdrant.upsert(src, points=[_point(i, "keep.md") for i in range(1, 6)] + [_point(9, "drop.md")])

    copied = indexing._clone_points(qdrant, src, dst, exclude_doc_ids=["drop.md"], batch_size=2)

    assert copied == 5
    source, target = _by_chunk(qdrant, src), _by_chunk(qdrant, dst)
    assert sorted(target) == [f"keep.md#{i}" for i in range(1, 6)]
    for chunk_id, point in target.items():
        assert point.id == source[chunk_id].id
        assert point.payload == source[chunk_id].payload
        assert point.vector["dense"] == pytest.approx(source[chunk_id].vector["dense"])
        assert point.vector["sparse"].indices == source[chunk_id].vector["sparse"].indices


def test_clone_points_without_exclusions_copies_everything(projects, qdrant):  # noqa: F811
    a, _ = projects
    src, dst = a.collection_name + "__src", a.collection_name + "__dst"
    for name in (src, dst):
        indexing._ensure_collection(qdrant, collection_name=name)
    qdrant.upsert(src, points=[_point(i, "a.md") for i in range(3)])

    assert indexing._clone_points(qdrant, src, dst) == 3
    assert indexing._clone_points(qdrant, src, dst) == 3  # idempotente: stessi id
    assert qdrant.count(dst).count == 3

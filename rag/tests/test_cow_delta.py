"""Delta copy-on-write degli indici immutabili: copia Qdrant, equivalenza col full
rebuild, ripieghi. Riusa le fixture reali (registry, Qdrant memory/server) di
test_project_indexing."""
from uuid import NAMESPACE_URL, uuid5

import pytest
from qdrant_client.models import PointStruct, SparseVector

from core import artifacts, indexing, qdrant_versions as versions
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


class CountingEmbed(Embed):
    """Embed finto che registra ogni testo vettorializzato (documenti e simboli)."""

    def __init__(self):
        self.texts: list[str] = []

    def encode(self, texts, **kwargs):
        self.texts.extend(texts)
        return super().encode(texts, **kwargs)


def _write(project, rel, text):
    path = (project.docs_dir if rel.endswith(".md") else project.code_dir) / rel
    path.write_text(text, encoding="utf-8")


def _seed(project, qdrant, monkeypatch):  # noqa: F811
    """v1: due documenti e due file di codice, full build promosso."""
    monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v1")
    _write(project, "keep.md", "# Keep\n\nKEEPMARK ALPHA\n")
    _write(project, "edit.md", "# Edit\n\nEDITMARK ALPHA\n")
    _write(project, "keep.py", "def keep():\n    return 'KEEPCODE'\n")
    _write(project, "edit.py", "def edit():\n    return 'EDITCODE'\n")
    assert build(project, qdrant) == "v1"
    monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v2")


def _doc_ids(qdrant, collection):  # noqa: F811
    return {p.payload["doc_id"] for p in _by_chunk(qdrant, collection).values()}


def test_cow_delta_reembeds_only_changed_sources(projects, qdrant, monkeypatch):  # noqa: F811
    a, _ = projects
    _seed(a, qdrant, monkeypatch)
    parent = a.collection_name + "__v1"
    parent_points = _by_chunk(qdrant, parent)
    _write(a, "edit.md", "# Edit\n\nEDIT2MARK BETA\n")
    _write(a, "edit.py", "def edit():\n    return 'EDITCODE2'\n")
    embed = CountingEmbed()

    stats = indexing.incremental_index(qdrant, embed, project=a)

    assert stats["delta_mode"] == "cow" and stats["promoted"] is True
    assert stats["reindexed_docs"] == 1
    assert stats["copied_points"] == sum(p.payload["doc_id"] == "keep.md" for p in parent_points.values())
    assert not any("KEEPMARK" in t or "KEEPCODE" in t for t in embed.texts)
    assert any("EDIT2MARK" in t for t in embed.texts) and any("EDITCODE2" in t for t in embed.texts)
    assert artifacts.current_version(project=a) == "v2"
    assert versions._read_alias_target(qdrant, a.collection_name) == a.collection_name + "__v2"
    assert _by_chunk(qdrant, parent).keys() == parent_points.keys()  # padre intatto
    assert indexing.index_status(project=a)["stale"] is False
    assert indexing.check_index_integrity(qdrant, project=a)["ok"] is True
    assert indexing.check_graph_consistency(Embed(), project=a)["consistent"] is True


def test_cow_delta_matches_full_rebuild_points(projects, qdrant, monkeypatch):  # noqa: F811
    a, _ = projects
    _seed(a, qdrant, monkeypatch)
    _write(a, "edit.md", "# Edit\n\nEDIT2MARK BETA\n")
    indexing.incremental_index(qdrant, Embed(), project=a)
    monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v3")
    build(a, qdrant)

    cow, full = (_by_chunk(qdrant, a.collection_name + f"__{v}") for v in ("v2", "v3"))
    assert cow.keys() == full.keys()
    for chunk_id in cow:
        assert cow[chunk_id].id == full[chunk_id].id
        assert cow[chunk_id].vector["dense"] == pytest.approx(full[chunk_id].vector["dense"])


def test_cow_drops_deleted_doc_and_keeps_parent_pinned(projects, qdrant, monkeypatch):  # noqa: F811
    a, _ = projects
    _seed(a, qdrant, monkeypatch)
    (a.docs_dir / "edit.md").unlink()

    stats = indexing.incremental_index(qdrant, Embed(), project=a)

    assert stats["delta_mode"] == "cow" and stats["deleted_docs"] == 1
    assert _doc_ids(qdrant, a.collection_name + "__v2") == {"keep.md"}
    assert _doc_ids(qdrant, a.collection_name + "__v1") == {"keep.md", "edit.md"}
    assert indexing.index_status(project=a)["stale"] is False


def test_cow_restricted_paths_keep_unprocessed_changes_stale(projects, qdrant, monkeypatch):  # noqa: F811
    a, _ = projects
    _seed(a, qdrant, monkeypatch)
    _write(a, "edit.md", "# Edit\n\nEDIT2MARK BETA\n")
    _write(a, "keep.md", "# Keep\n\nKEEPMARK BETA\n")  # cambiato ma NON segnalato

    stats = indexing.incremental_index(qdrant, Embed(), project=a, changed_paths=["docs/edit.md"])

    assert stats["delta_mode"] == "cow" and stats["reindexed_docs"] == 1
    candidate = _by_chunk(qdrant, a.collection_name + "__v2")
    keep = [p for p in candidate.values() if p.payload["doc_id"] == "keep.md"]
    assert keep and all(p.vector["dense"][0] > 0 for p in keep)  # vettori ALPHA del padre
    assert indexing.index_status(project=a)["stale"] is True


def test_cow_code_only_change_copies_all_points(projects, qdrant, monkeypatch):  # noqa: F811
    a, _ = projects
    _seed(a, qdrant, monkeypatch)
    parent_count = qdrant.count(a.collection_name + "__v1").count
    _write(a, "edit.py", "def edit():\n    return 'EDITCODE2'\n")
    embed = CountingEmbed()

    stats = indexing.incremental_index(qdrant, embed, project=a)

    assert stats["delta_mode"] == "cow" and stats["copied_points"] == parent_count
    assert not any("KEEPCODE" in t or "MARK" in t for t in embed.texts)
    assert indexing.check_graph_consistency(Embed(), project=a)["consistent"] is True


@pytest.mark.parametrize("breakage", ["mode", "model", "parent_collection"])
def test_cow_falls_back_to_rebuild(projects, qdrant, monkeypatch, breakage):  # noqa: F811
    a, _ = projects
    _seed(a, qdrant, monkeypatch)
    if breakage == "mode":
        monkeypatch.setattr(indexing, "DELTA_MODE", "rebuild")
    elif breakage == "model":
        monkeypatch.setattr(indexing, "EMBEDDING_MODEL", "altro-modello")
    else:
        qdrant.delete_collection(a.collection_name + "__v1")
    _write(a, "edit.md", "# Edit\n\nEDIT2MARK BETA\n")

    stats = indexing.incremental_index(qdrant, Embed(), project=a)

    assert stats["delta_mode"] == "rebuild" and stats["fallback_reason"]
    assert artifacts.current_version(project=a) == "v2"
    assert versions._read_alias_target(qdrant, a.collection_name) == a.collection_name + "__v2"


def test_cow_gate_rejection_keeps_parent_active(projects, qdrant, monkeypatch):  # noqa: F811
    a, _ = projects
    _seed(a, qdrant, monkeypatch)
    monkeypatch.setattr(indexing, "gate_promotion", lambda *a_, **k: {"passed": False})
    _write(a, "edit.md", "# Edit\n\nEDIT2MARK BETA\n")

    stats = indexing.incremental_index(qdrant, Embed(), project=a)

    assert stats["delta_mode"] == "cow" and stats["promoted"] is False
    assert artifacts.current_version(project=a) == "v1"
    assert versions._read_alias_target(qdrant, a.collection_name) == a.collection_name + "__v1"

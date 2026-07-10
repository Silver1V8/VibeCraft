"""Test dell'indicizzazione incrementale (delta): planning puro, id deterministici,
rimozione dei nodi-documento dal grafo senza distruggere i code-link, ed esecuzione
(delete-by-filter, idempotenza) con fake leggeri — nessun modello di embedding reale."""
from typing import Any, cast

import networkx as nx
import pytest
from qdrant_client import QdrantClient

from core import indexing as index


# ---------------------------------------------------------------------------
# 1. Planning puro: unchanged / new / modified / deleted / manifest corrotto
# ---------------------------------------------------------------------------
def _manifest(hashes: dict) -> dict:
    return {"doc_hashes": hashes}


def test_plan_all_new_when_manifest_none():
    """Manifest assente ⇒ tutti i documenti correnti sono 'new' (equivale al full rebuild)."""
    current = {"a.md": "h1", "b.md": "h2"}
    plan = index.plan_incremental_indexing(current, None)
    assert sorted(plan.new) == ["a.md", "b.md"]
    assert plan.modified == [] and plan.deleted == [] and plan.unchanged == []
    assert plan.is_noop is False
    assert sorted(plan.to_index()) == ["a.md", "b.md"]
    assert plan.to_delete() == []


def test_plan_unchanged_is_noop():
    """Hash identici ⇒ nulla da fare: is_noop True, tutti in unchanged."""
    current = {"a.md": "h1", "b.md": "h2"}
    plan = index.plan_incremental_indexing(current, _manifest(dict(current)))
    assert plan.is_noop is True
    assert sorted(plan.unchanged) == ["a.md", "b.md"]
    assert plan.to_index() == [] and plan.to_delete() == []


def test_plan_new_modified_deleted_together():
    old = {"keep.md": "h", "change.md": "old", "gone.md": "h"}
    current = {"keep.md": "h", "change.md": "new", "fresh.md": "h"}
    plan = index.plan_incremental_indexing(current, _manifest(old))
    assert plan.new == ["fresh.md"]
    assert plan.modified == ["change.md"]
    assert plan.deleted == ["gone.md"]
    assert plan.unchanged == ["keep.md"]
    # to_index = nuovi + modificati ; to_delete = modificati + cancellati
    assert sorted(plan.to_index()) == ["change.md", "fresh.md"]
    assert sorted(plan.to_delete()) == ["change.md", "gone.md"]
    assert plan.is_noop is False


@pytest.mark.parametrize("bad_manifest", [None, {}, {"doc_hashes": None}, {"nope": 1}, "corrotto", 42])
def test_plan_missing_or_corrupt_manifest_treats_all_as_new(bad_manifest: Any):
    """Manifest assente/vuoto/corrotto/di tipo errato ⇒ fallback sicuro: tutto 'new'.
    bad_manifest è intenzionalmente di tipo arbitrario (anche str/int): è proprio il caso
    limite che plan_incremental_indexing deve gestire in modo difensivo (isinstance check)."""
    current = {"a.md": "h1"}
    plan = index.plan_incremental_indexing(current, bad_manifest)
    assert plan.new == ["a.md"]
    assert plan.modified == [] and plan.deleted == []


# ---------------------------------------------------------------------------
# 2. Id deterministici dei punti Qdrant (presupposto dell'idempotenza)
# ---------------------------------------------------------------------------
def test_point_id_deterministic_and_stable():
    a = index._point_id("docs/x.md#00-intro")
    b = index._point_id("docs/x.md#00-intro")
    assert a == b                               # stesso chunk_id → stesso id
    assert a != index._point_id("docs/x.md#01-body")  # chunk diversi → id diversi
    # è un UUID valido (accettato da Qdrant come point id)
    import uuid
    uuid.UUID(a)


# ---------------------------------------------------------------------------
# 3. Rimozione nodo-documento dal grafo SENZA distruggere i code-link
# ---------------------------------------------------------------------------
def test_remove_doc_node_preserves_code_nodes_and_references():
    G = nx.DiGraph()
    G.add_node("d.md", type="document")
    G.add_node("ENTITA", type="entity")
    G.add_node("code/api.py::foo", type="code")
    G.add_edge("d.md", "ENTITA", relation="MENTIONS")            # arco interno del doc
    G.add_edge("code/api.py::foo", "d.md", relation="IMPLEMENTS")  # code → doc (cadrà)
    G.add_edge("code/api.py::foo", "ENTITA", relation="REFERENCES")  # code → entità (resta)

    removed = index._remove_doc_nodes_from_graph(G, ["d.md"])

    assert removed == 1
    assert "d.md" not in G                        # nodo-documento eliminato
    assert "code/api.py::foo" in G                # nodo codice preservato
    assert "ENTITA" in G                          # entità preservata
    assert G.has_edge("code/api.py::foo", "ENTITA")  # REFERENCES intatto
    # l'IMPLEMENTS verso il doc rimosso non esiste più (accettata staleness sul code-link)
    assert not G.has_edge("code/api.py::foo", "d.md")


def test_remove_doc_node_only_touches_document_type():
    """Non deve rimuovere nodi che non sono di tipo 'document' anche se l'id coincide."""
    G = nx.DiGraph()
    G.add_node("ENTITA", type="entity")
    removed = index._remove_doc_nodes_from_graph(G, ["ENTITA", "inesistente"])
    assert removed == 0
    assert "ENTITA" in G


# ---------------------------------------------------------------------------
# 4. Esecuzione con fake leggeri: delete-by-filter, purge sidecar, idempotenza
# ---------------------------------------------------------------------------
class FakeQdrant:
    """Registra le chiamate delete/upsert senza toccare un vero Qdrant."""
    def __init__(self):
        self.deleted_selectors = []
        self.upserted_points = []

    def delete(self, collection_name, points_selector):
        self.deleted_selectors.append(points_selector)

    def upsert(self, collection_name, points):
        self.upserted_points.extend(points)


def _fake_encode(_embed_model, chunks):
    """Sostituto di _encode_chunks_to_points: niente torch, id deterministici reali."""
    points, colbert_partial, chunks_partial = [], {}, {}
    for c in chunks:
        points.append({"id": index._point_id(c["chunk_id"]), "chunk_id": c["chunk_id"]})
        colbert_partial[c["chunk_id"]] = [0.0]
        chunks_partial[c["chunk_id"]] = {"doc_id": c["doc_id"], "section": c["section"], "text": c["text"]}
    return points, colbert_partial, chunks_partial, []


def test_apply_deletes_modified_and_deleted_via_filter(tmp_path, monkeypatch):
    # docs/ finto con un solo documento (quello 'modificato' che va re-indicizzato)
    (tmp_path / "change.md").write_text("## Sezione\ncorpo nuovo\n", encoding="utf-8")
    monkeypatch.setattr(index, "_encode_chunks_to_points", _fake_encode)

    # Stato preesistente: chunk di change.md (modificato) e gone.md (cancellato)
    graph = nx.DiGraph()
    graph.add_node("change.md", type="document")
    graph.add_node("gone.md", type="document")
    colbert = {"change.md#00-a": [0.0], "gone.md#00-a": [0.0]}
    chunks = {
        "change.md#00-a": {"doc_id": "change.md", "section": "a", "text": "vecchio"},
        "gone.md#00-a": {"doc_id": "gone.md", "section": "a", "text": "vecchio"},
    }

    plan = index.IndexPlan(unchanged=[], new=[], modified=["change.md"], deleted=["gone.md"])
    fake_q = FakeQdrant()
    stats = index.apply_incremental_indexing(
        plan, tmp_path, cast(QdrantClient, fake_q), embed_model=None,
        graph=graph, colbert_store=colbert, chunks_store=chunks,
    )

    # delete-by-filter invocata una volta con i doc_id modificati+cancellati
    assert len(fake_q.deleted_selectors) == 1
    match_any = fake_q.deleted_selectors[0].filter.must[0].match
    assert sorted(match_any.any) == ["change.md", "gone.md"]

    # sidecar dei vecchi chunk purgati; gone.md non è stato re-inserito, change.md sì
    assert "gone.md#00-a" not in chunks and "gone.md#00-a" not in colbert
    assert "gone.md" not in graph            # doc cancellato: nodo rimosso
    assert "change.md" in graph              # doc modificato: nodo re-inserito
    assert any(c.startswith("change.md#") for c in chunks)  # nuovi chunk di change.md
    assert stats["deleted_docs"] == 1 and stats["reindexed_docs"] == 1
    assert stats["upserted_chunks"] >= 1


def test_apply_noop_plan_touches_nothing(monkeypatch):
    monkeypatch.setattr(index, "_encode_chunks_to_points", _fake_encode)
    plan = index.IndexPlan(unchanged=["a.md"], new=[], modified=[], deleted=[])
    assert plan.is_noop is True

    graph = nx.DiGraph()
    graph.add_node("a.md", type="document")
    fake_q = FakeQdrant()
    index.apply_incremental_indexing(
        plan, None, cast(QdrantClient, fake_q), embed_model=None,
        graph=graph, colbert_store={}, chunks_store={},
    )
    # nessuna delete, nessun upsert, grafo intatto
    assert fake_q.deleted_selectors == []
    assert fake_q.upserted_points == []
    assert "a.md" in graph


def test_incremental_index_noop_returns_early(monkeypatch, tmp_path):
    """Con manifest coerente e docs/ invariati, incremental_index è un no-op:
    non costruisce mai il client Qdrant né il modello (idempotenza sulle run ripetute)."""
    current = {"a.md": "h1", "b.md": "h2"}
    monkeypatch.setattr(index, "_docs_hashes", lambda: dict(current))
    monkeypatch.setattr(index, "_read_manifest", lambda: {"doc_hashes": dict(current)})

    # Se venisse costruito un QdrantClient o un modello, questi solleverebbero.
    def _boom(*a, **k):
        raise AssertionError("il no-op non deve creare risorse pesanti")
    monkeypatch.setattr(index, "QdrantClient", _boom)
    monkeypatch.setattr(index, "BGEM3FlagModel", _boom)

    out = index.incremental_index()
    assert out["noop"] is True
    assert out["reindexed_docs"] == 0 and out["deleted_docs"] == 0

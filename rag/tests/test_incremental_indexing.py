"""Test dell'indicizzazione incrementale (delta): planning puro, id deterministici,
rimozione dei nodi-documento dal grafo senza distruggere i code-link, ed esecuzione
(delete-by-filter, idempotenza) con fake leggeri — nessun modello di embedding reale."""
import json
from typing import Any, cast

import networkx as nx
import pytest
from qdrant_client import QdrantClient

from core import artifacts as _artifacts
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
# 3b. _ensure_collection / _delete_doc_chunks: parametrizzazione di collection_name
# (blue/green Qdrant, S3). Default invariato (COLLECTION_NAME), passaggio esplicito
# propagato correttamente fino alle chiamate Qdrant sottostanti.
# ---------------------------------------------------------------------------
class _FakeCollectionInfo:
    def __init__(self, name):
        self.name = name


class _FakeCollectionsResponse:
    def __init__(self, names):
        self.collections = [_FakeCollectionInfo(n) for n in names]


class _RecordingQdrantOps:
    """Fake minimale per _ensure_collection/_delete_doc_chunks: registra i nomi di
    collection ricevuti dalle operazioni di gestione/cancellazione, senza toccare
    un vero Qdrant."""
    def __init__(self, existing=()):
        self._existing = set(existing)
        self.created: list[str] = []
        self.deleted_collections: list[str] = []
        self.deleted_from: list[str] = []

    def get_collections(self):
        return _FakeCollectionsResponse(self._existing)

    def create_collection(self, collection_name, **kw):
        self.created.append(collection_name)
        self._existing.add(collection_name)

    def delete_collection(self, collection_name):
        self.deleted_collections.append(collection_name)
        self._existing.discard(collection_name)

    def delete(self, collection_name, points_selector):
        self.deleted_from.append(collection_name)


def test_ensure_collection_default_uses_config_constant():
    qdrant = _RecordingQdrantOps()
    index._ensure_collection(qdrant)
    assert qdrant.created == [index.COLLECTION_NAME]


def test_ensure_collection_explicit_name_is_propagated():
    qdrant = _RecordingQdrantOps()
    index._ensure_collection(qdrant, collection_name="vibecraft_events__v1")
    assert qdrant.created == ["vibecraft_events__v1"]
    assert index.COLLECTION_NAME not in qdrant.created


def test_ensure_collection_recreate_drops_and_recreates_the_given_name():
    # recreate=True deve droppare e ricreare la collection INDICATA, non quella di
    # default: se punteranno a nomi diversi (candidata vs produzione), la produzione
    # non va mai toccata da un rebuild che opera sulla candidata.
    qdrant = _RecordingQdrantOps(existing={"vibecraft_events__v1"})
    index._ensure_collection(qdrant, recreate=True, collection_name="vibecraft_events__v1")
    assert qdrant.deleted_collections == ["vibecraft_events__v1"]
    assert qdrant.created == ["vibecraft_events__v1"]


def test_delete_doc_chunks_default_uses_config_constant():
    qdrant = _RecordingQdrantOps()
    index._delete_doc_chunks(qdrant, ["a.md"])
    assert qdrant.deleted_from == [index.COLLECTION_NAME]


def test_delete_doc_chunks_explicit_name_is_propagated():
    qdrant = _RecordingQdrantOps()
    index._delete_doc_chunks(qdrant, ["a.md"], collection_name="vibecraft_events__v1")
    assert qdrant.deleted_from == ["vibecraft_events__v1"]


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
    code = {"backend/svc.py": "c1"}
    monkeypatch.setattr(index, "_docs_hashes", lambda: dict(current))
    monkeypatch.setattr(index, "_code_hashes", lambda: dict(code))
    monkeypatch.setattr(index, "_read_manifest",
                        lambda: {"doc_hashes": dict(current), "code_hashes": dict(code)})

    # Se venisse costruito un QdrantClient o un modello, questi solleverebbero.
    def _boom(*a, **k):
        raise AssertionError("il no-op non deve creare risorse pesanti")
    monkeypatch.setattr(index, "QdrantClient", _boom)
    monkeypatch.setattr(index, "BGEM3FlagModel", _boom)

    out = index.incremental_index()
    assert out["noop"] is True
    assert out["reindexed_docs"] == 0 and out["deleted_docs"] == 0


# ---------------------------------------------------------------------------
# 5. Ciclo full→incrementale end-to-end: link spec↔codice non stale, senza rebuild.
#    Fake leggeri (nessun torch, nessun Qdrant reale): un modello stub deterministico
#    che vettorializza contando alcuni "marker" nel testo, e un Qdrant in-memory.
# ---------------------------------------------------------------------------
from types import SimpleNamespace  # noqa: E402

import numpy as np  # noqa: E402

from core import eval_metrics  # noqa: E402


class StubEmbed:
    """Modello di embedding deterministico: il vettore denso conta i marker nel testo,
    così simboli e documenti che parlano dello stesso marker risultano simili (cosine)."""
    MARKERS = ["ALPHA", "BETA", "GAMMA", "ZETA"]

    def _vec(self, text: str) -> np.ndarray:
        v = np.array([float(text.count(m)) for m in self.MARKERS], dtype="float32")
        return v if v.any() else np.full(len(self.MARKERS), 0.01, dtype="float32")

    def encode(self, texts, **kw):
        dense = (np.stack([self._vec(t) for t in texts])
                 if texts else np.zeros((0, len(self.MARKERS)), dtype="float32"))
        out = {"dense_vecs": dense}
        if kw.get("return_sparse"):
            out["lexical_weights"] = [{} for _ in texts]
        if kw.get("return_colbert_vecs"):
            out["colbert_vecs"] = [np.zeros((1, len(self.MARKERS)), dtype="float32") for _ in texts]
        return out


class StatefulFakeQdrant:
    """Qdrant in-memory: tiene i punti per id e onora delete-by-filter su doc_id."""
    def __init__(self):
        self.points: dict = {}
        self.collections: set = set()
        # Nomi di collection ricevuti dalle operazioni di gestione (S6.2: verifica
        # che collection_name resti COLLECTION_NAME nel percorso attuale del full
        # rebuild). Sola registrazione, non altera il comportamento esistente.
        self.created_collection_names: list = []
        self.deleted_collection_names: list = []
        self.upserted_collection_names: list = []
        # Alias (S6.5): alias_name -> collection_name. get_aliases/update_collection_aliases
        # replicano la semantica reale di Qdrant, incluso il rifiuto di un alias
        # omonimo a una collection FISICA esistente (il conflitto del layout legacy
        # non ancora migrato — S6.6, non implementato in questo step).
        self.aliases: dict = {}

    def get_collections(self):
        return SimpleNamespace(collections=[SimpleNamespace(name=n) for n in self.collections])

    def create_collection(self, collection_name, **kw):
        self.collections.add(collection_name)
        self.created_collection_names.append(collection_name)

    def delete_collection(self, collection_name):
        self.collections.discard(collection_name)
        self.points.clear()
        self.deleted_collection_names.append(collection_name)
        for alias_name in [a for a, c in self.aliases.items() if c == collection_name]:
            del self.aliases[alias_name]

    def upsert(self, collection_name, points):
        self.upserted_collection_names.append(collection_name)
        for p in points:
            self.points[p.id] = p

    def delete(self, collection_name, points_selector):
        dead = set(points_selector.filter.must[0].match.any)
        self.points = {pid: p for pid, p in self.points.items() if p.payload.get("doc_id") not in dead}

    def close(self):
        pass

    def get_aliases(self):
        return SimpleNamespace(aliases=[
            SimpleNamespace(alias_name=a, collection_name=c) for a, c in sorted(self.aliases.items())
        ])

    def update_collection_aliases(self, change_aliases_operations):
        """Valida TUTTE le operazioni prima di applicarne una sola (batch atomico,
        come il vero Qdrant): il target di ogni create deve esistere, e alias_name
        non può coincidere con una collection FISICA esistente (Qdrant reale rifiuta
        un alias omonimo a una collection — il conflitto del layout legacy)."""
        pending_creates: list[tuple[str, str]] = []
        pending_deletes: list[str] = []
        for op in change_aliases_operations:
            create = getattr(op, "create_alias", None)
            delete = getattr(op, "delete_alias", None)
            if create is not None:
                if create.collection_name not in self.collections:
                    raise ValueError(f"Collection inesistente: {create.collection_name}")
                if create.alias_name in self.collections:
                    raise ValueError(
                        f"'{create.alias_name}' è già una collection fisica: impossibile "
                        f"crearla anche come alias (serve prima una migrazione — S6.6, non implementata)."
                    )
                pending_creates.append((create.alias_name, create.collection_name))
            elif delete is not None:
                pending_deletes.append(delete.alias_name)
            else:
                raise NotImplementedError("Operazione alias non supportata dal fake.")
        for alias_name in pending_deletes:
            self.aliases.pop(alias_name, None)
        for alias_name, collection_name in pending_creates:
            self.aliases[alias_name] = collection_name


def _wire_tmp_index(monkeypatch, tmp_path):
    """Reindirizza tutti i percorsi persistiti e le directory docs/ code/ dell'indice
    su una sandbox temporanea, e restituisce (docs_dir, code_dir)."""
    docs_dir = tmp_path / "docs"
    code_dir = tmp_path / "code"
    db = tmp_path / "db"
    docs_dir.mkdir(); code_dir.mkdir(); db.mkdir()
    monkeypatch.setattr(index, "DOCS_DIR", docs_dir)
    monkeypatch.setattr(index, "CODE_DIR", code_dir)
    # L'I/O degli artefatti vive in core.artifacts: reindirizziamo LÌ database/
    # (versioni blue/green + CURRENT + manifest) e i percorsi flat dei nuovi formati
    # (JSON/.npz) e dei legacy pickle (per il fallback) sulla sandbox.
    monkeypatch.setattr(_artifacts, "DATABASE_DIR", db)
    monkeypatch.setattr(_artifacts, "GRAPH_JSON_PATH", db / "graph.json")
    monkeypatch.setattr(_artifacts, "COLBERT_NPZ_PATH", db / "colbert.npz")
    monkeypatch.setattr(_artifacts, "CHUNKS_JSON_PATH", db / "chunks.json")
    monkeypatch.setattr(_artifacts, "DENSE_NPZ_PATH", db / "dense.npz")
    monkeypatch.setattr(_artifacts, "CODE_NPZ_PATH", db / "code.npz")
    monkeypatch.setattr(_artifacts, "CODE_JSON_PATH", db / "code.json")
    monkeypatch.setattr(_artifacts, "GRAPH_SAVE_PATH", db / "graph.pkl")
    monkeypatch.setattr(_artifacts, "COLBERT_SAVE_PATH", db / "colbert.pkl")
    monkeypatch.setattr(_artifacts, "CHUNKS_SAVE_PATH", db / "chunks.pkl")
    monkeypatch.setattr(_artifacts, "DENSE_SAVE_PATH", db / "dense.pkl")
    monkeypatch.setattr(_artifacts, "CODE_SAVE_PATH", db / "code.pkl")
    return docs_dir, code_dir


def _spec(marker: str) -> str:
    return f"## Sezione\n[{marker}] regola su {marker}\n"


_CODE_ALPHA = "def handle_alpha():\n    # gestisce ALPHA\n    return 'ALPHA'\n"
_CODE_BETA = "def handle_beta():\n    # gestisce BETA\n    return 'BETA'\n"
_CODE_GAMMA = "def handle_gamma():\n    # gestisce GAMMA\n    return 'GAMMA'\n"


def _load_graph():
    return _artifacts.load_artifacts().graph


def _implements(G):
    return {(u, v) for u, v, d in G.edges(data=True) if d.get("relation") == "IMPLEMENTS"}


def _sec(doc: str) -> str:
    """Id del nodo-SEZIONE vincente per i doc di test generati da _spec(): una sola sezione
    ('## Sezione') → chunk_id '<doc>#00-sezione'. Il codice ora implementa la sezione, non il doc."""
    return f"{doc}#00-sezione"


def _references(G):
    return {(u, v) for u, v, d in G.edges(data=True) if d.get("relation") == "REFERENCES"}


def test_spec_modification_updates_code_links(monkeypatch, tmp_path):
    """Una spec che cambia contenuto cambia i suoi link al codice: l'IMPLEMENTS e il
    REFERENCES che dipendevano dalla vecchia versione spariscono, senza full rebuild, e il
    grafo resta coerente con quello di un rebuild sugli stessi input."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    (code_dir / "backend").mkdir()
    (code_dir / "backend" / "svc.py").write_text(_CODE_ALPHA, encoding="utf-8")
    stub, q = StubEmbed(), StatefulFakeQdrant()

    index.build_graph_and_index(qdrant=q, embed_model=stub)
    G = _load_graph()
    code_id = "backend/svc.py::handle_alpha"
    assert (code_id, _sec("spec.md")) in _implements(G)   # codice implementa la sezione della spec
    assert (code_id, "ALPHA") in _references(G)         # codice referenzia l'entità ALPHA

    # La spec cambia argomento: da ALPHA a ZETA. Nessun overlap col codice (che parla di ALPHA).
    (docs_dir / "spec.md").write_text(_spec("ZETA"), encoding="utf-8")
    stats = index.incremental_index(qdrant=q, embed_model=stub)
    assert stats.get("noop") is not True

    G2 = _load_graph()
    assert (code_id, _sec("spec.md")) not in _implements(G2)  # IMPLEMENTS stale rimosso
    assert (code_id, "ALPHA") not in _references(G2)     # REFERENCES stale rimosso
    assert "ALPHA" not in G2                              # entità non più citata → potata
    assert "ZETA" in G2 and code_id in G2                 # nuova entità presente, codice resta

    report = index.check_graph_consistency(embed_model=stub, docs_dir=docs_dir, code_dir=code_dir)
    assert report["consistent"] is True, report


def test_deleted_linked_file_removes_orphan_nodes_and_edges(monkeypatch, tmp_path):
    """Cancellare la spec collegata rimuove il suo nodo e i chunk da Qdrant, pota l'entità
    rimasta orfana e fa cadere gli archi spec↔codice che vi dipendevano; il nodo-codice
    (il cui file esiste ancora) resta. Il grafo resta coerente col rebuild."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    (code_dir / "backend").mkdir()
    (code_dir / "backend" / "svc.py").write_text(_CODE_ALPHA, encoding="utf-8")
    stub, q = StubEmbed(), StatefulFakeQdrant()

    index.build_graph_and_index(qdrant=q, embed_model=stub)
    assert q.points, "il full rebuild deve aver upsertato dei chunk"

    (docs_dir / "spec.md").unlink()  # la spec sparisce del tutto
    index.incremental_index(qdrant=q, embed_model=stub)

    G = _load_graph()
    code_id = "backend/svc.py::handle_alpha"
    assert "spec.md" not in G                 # nodo-documento rimosso
    assert "ALPHA" not in G                    # entità orfana (nessun doc la cita) rimossa
    assert not any(v == "spec.md" for _, v in _implements(G))
    assert code_id in G                        # il file di codice esiste ancora → nodo resta
    assert not q.points                        # chunk della spec purgati da Qdrant

    report = index.check_graph_consistency(embed_model=stub, docs_dir=docs_dir, code_dir=code_dir)
    assert report["consistent"] is True, report


def test_deleted_code_file_removes_code_node(monkeypatch, tmp_path):
    """Cancellare un file di codice rimuove i suoi nodi-simbolo e gli archi incidenti,
    lasciando intatta la spec e le sue entità. Coerenza col rebuild preservata."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    (code_dir / "backend").mkdir()
    (code_dir / "backend" / "svc.py").write_text(_CODE_ALPHA, encoding="utf-8")
    stub, q = StubEmbed(), StatefulFakeQdrant()

    index.build_graph_and_index(qdrant=q, embed_model=stub)
    (code_dir / "backend" / "svc.py").unlink()
    index.incremental_index(qdrant=q, embed_model=stub)

    G = _load_graph()
    assert "backend/svc.py::handle_alpha" not in G   # simbolo del file rimosso
    assert "spec.md" in G and "ALPHA" in G           # la spec e la sua entità restano
    assert _implements(G) == set() and _references(G) == set()

    report = index.check_graph_consistency(embed_model=stub, docs_dir=docs_dir, code_dir=code_dir)
    assert report["consistent"] is True, report


def test_check_graph_detects_injected_divergence(monkeypatch, tmp_path):
    """Il check di coerenza deve SEGNALARE una divergenza: dopo un build coerente,
    inietto a mano un arco stale nel grafo persistito e verifico che venga rilevato."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    stub, q = StubEmbed(), StatefulFakeQdrant()
    index.build_graph_and_index(qdrant=q, embed_model=stub)

    assert index.check_graph_consistency(embed_model=stub, docs_dir=docs_dir, code_dir=code_dir)["consistent"]

    G = _load_graph()
    G.add_edge("code/ghost.py::x", "spec.md", relation="IMPLEMENTS")  # arco/nodo fantasma
    _artifacts._atomic_write_json(_artifacts.artifact_dir() / "graph.json",
                                  _artifacts._graph_to_json(G))

    report = index.check_graph_consistency(embed_model=stub, docs_dir=docs_dir, code_dir=code_dir)
    assert report["consistent"] is False
    assert report["counts"]["extra_nodes"] >= 1 and report["counts"]["extra_edges"] >= 1


def _full_rebuild_graph(monkeypatch, docs_dir, code_dir, stub):
    """Costruisce da zero il grafo di riferimento sugli input correnti (su un Qdrant
    usa-e-getta) e ne restituisce (nodi tipizzati, archi tipizzati): il full rebuild è
    la verità contro cui misurare l'equivalenza dell'incrementale."""
    ref = index._build_full_state(stub, docs_dir, code_dir, emit=lambda *_a, **_k: None).graph
    return index._node_type_set(ref), index._edge_set(ref)


def test_incremental_matches_full_rebuild_over_edit_sequence(monkeypatch, tmp_path):
    """PROPRIETÀ: una sequenza di modifiche applicate in incrementale (aggiungi doc, modifica
    doc, cancella doc, aggiungi codice) mantiene, A OGNI PASSO, il grafo dei code-link
    deterministicamente equivalente a un full rebuild sugli stessi input — senza mai
    rilincare tutti i simboli. Embedding fake deterministici (StubEmbed), Qdrant in-memory.

    check_graph_consistency è la prova (confronta il grafo incrementale persistito col
    rebuild); in più si verifica direttamente l'uguaglianza nodi/archi e qualche invariante
    di merito, così il test fallisce anche se un giorno il check dovesse degradare."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    stub, q = StubEmbed(), StatefulFakeQdrant()

    # Stato iniziale: due spec (ALPHA, BETA) e un simbolo che parla di ALPHA.
    (docs_dir / "alpha.md").write_text(_spec("ALPHA"), encoding="utf-8")
    (docs_dir / "beta.md").write_text(_spec("BETA"), encoding="utf-8")
    (code_dir / "backend").mkdir()
    (code_dir / "backend" / "a.py").write_text(_CODE_ALPHA, encoding="utf-8")
    index.build_graph_and_index(qdrant=q, embed_model=stub)

    def _assert_consistent_with_rebuild():
        report = index.check_graph_consistency(embed_model=stub, docs_dir=docs_dir, code_dir=code_dir)
        assert report["consistent"] is True, report
        inc_nodes = index._node_type_set(_load_graph())
        inc_edges = index._edge_set(_load_graph())
        ref_nodes, ref_edges = _full_rebuild_graph(monkeypatch, docs_dir, code_dir, stub)
        assert inc_nodes == ref_nodes
        assert inc_edges == ref_edges

    _assert_consistent_with_rebuild()
    a_id = "backend/a.py::handle_alpha"
    assert (a_id, _sec("alpha.md")) in _implements(_load_graph())  # aggancio iniziale

    # PASSO 1 — aggiungi doc (GAMMA): nessun overlap col codice esistente, il simbolo ALPHA
    # resta agganciato ad alpha.md; il nuovo doc non deve spostarne l'argmax.
    (docs_dir / "gamma.md").write_text(_spec("GAMMA"), encoding="utf-8")
    index.incremental_index(qdrant=q, embed_model=stub)
    _assert_consistent_with_rebuild()
    assert (a_id, _sec("alpha.md")) in _implements(_load_graph())

    # PASSO 2 — modifica doc: alpha.md passa da ALPHA a ZETA. Il simbolo (che parla di ALPHA)
    # perde il vincitore e va rilincato; alpha.md non lo implementa più.
    (docs_dir / "alpha.md").write_text(_spec("ZETA"), encoding="utf-8")
    index.incremental_index(qdrant=q, embed_model=stub)
    _assert_consistent_with_rebuild()
    assert (a_id, _sec("alpha.md")) not in _implements(_load_graph())

    # PASSO 3 — aggiungi codice: un nuovo simbolo che parla di GAMMA deve agganciare gamma.md,
    # senza toccare l'aggancio (già assente) del simbolo ALPHA.
    (code_dir / "backend" / "g.py").write_text(_CODE_GAMMA, encoding="utf-8")
    index.incremental_index(qdrant=q, embed_model=stub)
    _assert_consistent_with_rebuild()
    g_id = "backend/g.py::handle_gamma"
    assert (g_id, _sec("gamma.md")) in _implements(_load_graph())

    # PASSO 4 — cancella doc: gamma.md sparisce. Il simbolo GAMMA perde il vincitore, l'entità
    # GAMMA resta orfana e va potata; il grafo resta coerente col rebuild.
    (docs_dir / "gamma.md").unlink()
    index.incremental_index(qdrant=q, embed_model=stub)
    _assert_consistent_with_rebuild()
    G = _load_graph()
    assert (g_id, _sec("gamma.md")) not in _implements(G)
    assert "GAMMA" not in G and g_id in G


def test_selection_leaves_unaffected_symbols_untouched():
    """Il cuore dell'ottimizzazione: quando i documenti cambiano, si selezionano SOLO i
    simboli il cui argmax può spostarsi, non tutti. Verifica diretta sui due criteri."""
    # sym_keep vince su un chunk di keep.md (0.9); sym_move vinceva su change.md (0.8).
    code_store = {
        "sym_keep": {"dense": np.array([1.0, 0.0], dtype="float32"),
                     "best_score": 0.9, "win_doc_id": "keep.md", "win_chunk_id": "keep.md#00-a"},
        "sym_move": {"dense": np.array([0.0, 1.0], dtype="float32"),
                     "best_score": 0.8, "win_doc_id": "change.md", "win_chunk_id": "change.md#00-a"},
    }
    # (a) solo i simboli il cui vincitore sta in un doc rimosso/modificato sono toccati.
    stale = index._symbols_with_stale_argmax(code_store, {"change.md"})
    assert stale == {"sym_move"}
    assert "sym_keep" not in stale

    # (b) un nuovo chunk allineato a sym_keep (>= best) lo tocca; sym_move (ortogonale) no.
    dense_store = {"new.md#00-a": np.array([1.0, 0.0], dtype="float32")}
    beaten = index._symbols_beaten_by_new_chunks(code_store, dense_store, ["new.md#00-a"])
    assert "sym_keep" in beaten
    assert "sym_move" not in beaten

    # nessun cambiamento documenti ⇒ nessun simbolo toccato per via dei documenti.
    assert index._symbols_with_stale_argmax(code_store, set()) == set()
    assert index._symbols_beaten_by_new_chunks(code_store, dense_store, []) == set()


def _mini_retriever(q: StatefulFakeQdrant, stub: StubEmbed):
    """Retriever deterministico sui punti in Qdrant: cosine denso query↔chunk. Serve solo a
    misurare le metriche dell'eval harness (core.eval_metrics) prima/dopo l'incrementale."""
    def retrieve(query: str, k: int) -> list[dict]:
        qv = stub.encode([query], return_dense=True)["dense_vecs"][0]
        qn = qv / (np.linalg.norm(qv) + 1e-8)
        scored = []
        for p in q.points.values():
            dv = np.asarray(p.vector["dense"], dtype="float32")
            dv = dv / (np.linalg.norm(dv) + 1e-8)
            scored.append((float(qn @ dv), p.payload))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [{"chunk_id": pl["chunk_id"], "doc_id": pl["doc_id"], "section": pl.get("section", "")}
                for _, pl in scored[:k]]
    return retrieve


def test_eval_metrics_do_not_regress_after_full_then_incremental(monkeypatch, tmp_path):
    """Dopo un ciclo full→incrementale (con una modifica) le metriche dell'eval harness non
    regrediscono: l'indice risultante produce lo stesso ranking (e quindi le stesse metriche)
    di un full rebuild sugli stessi input. Proxy server-free: si misura core.eval_metrics su
    un retriever deterministico costruito sui punti Qdrant, e si confronta col rebuild."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "alpha.md").write_text(_spec("ALPHA"), encoding="utf-8")
    (docs_dir / "beta.md").write_text(_spec("BETA"), encoding="utf-8")
    (code_dir / "backend").mkdir()
    (code_dir / "backend" / "svc.py").write_text(_CODE_ALPHA, encoding="utf-8")
    stub = StubEmbed()

    cases = [
        {"q": "ALPHA", "expected": [{"doc": "alpha.md"}]},
        {"q": "BETA", "expected": [{"doc": "beta.md"}]},
    ]

    # Full rebuild → metriche di riferimento
    q_full = StatefulFakeQdrant()
    index.build_graph_and_index(qdrant=q_full, embed_model=stub)
    ref = eval_metrics.evaluate(cases, _mini_retriever(q_full, stub), ks=(1, 2))["aggregate"]

    # Ciclo full→incrementale sullo stesso indice: modifico beta.md (contenuto equivalente)
    q_cycle = StatefulFakeQdrant()
    index.build_graph_and_index(qdrant=q_cycle, embed_model=stub)
    (docs_dir / "beta.md").write_text(_spec("BETA") + "\nnota aggiuntiva\n", encoding="utf-8")
    index.incremental_index(qdrant=q_cycle, embed_model=stub)
    after = eval_metrics.evaluate(cases, _mini_retriever(q_cycle, stub), ks=(1, 2))["aggregate"]

    # Nessuna regressione: ogni metrica dopo l'incrementale è >= al riferimento full.
    for key in ("recall@1", "recall@2", "mrr", "source_in_top3"):
        assert after[key] >= ref[key] - 1e-9, (key, ref[key], after[key])
    # E il grafo incrementale resta coerente col rebuild.
    assert index.check_graph_consistency(embed_model=stub, docs_dir=docs_dir, code_dir=code_dir)["consistent"]


def test_resolve_authority_aliases_connects_documents():
    """Le relazioni di autorità del frontmatter (doc -> alias di versione) vengono risolte in
    archi doc -> doc reali, ignorando il suffisso di versione. Non distruttivo: l'arco-alias
    autorato resta. Idempotente: rieseguire non aggiunge duplicati."""
    G = nx.DiGraph()
    # spec dichiara EREDITA_VINCOLI verso 'safeguards-security-v1.2' (versione diversa dal doc)
    G.add_node("spec.md", type="document", id="spec-concurrency-v1.0")
    G.add_node("safeguards.md", type="document", id="safeguards-security-v1.0")
    G.add_node("safeguards-security-v1.2", type="entity")            # alias orfano dal frontmatter
    G.add_node("REGOLA-CONC-01", type="entity")                      # entità reale, non un doc
    G.add_edge("spec.md", "safeguards-security-v1.2", relation="EREDITA_VINCOLI")
    G.add_edge("spec.md", "REGOLA-CONC-01", relation="MENTIONS")

    added = index._resolve_authority_aliases(G)
    assert added == 1
    assert G.has_edge("spec.md", "safeguards.md")                     # doc -> doc risolto
    assert G["spec.md"]["safeguards.md"]["relation"] == "EREDITA_VINCOLI"
    assert G.has_edge("spec.md", "safeguards-security-v1.2")          # alias autorato preservato
    assert not G.has_edge("spec.md", "REGOLA-CONC-01") or \
        G["spec.md"]["REGOLA-CONC-01"]["relation"] == "MENTIONS"      # entità reale non toccata

    assert index._resolve_authority_aliases(G) == 0                   # idempotente


def test_authority_edges_survive_full_rebuild_equivalence(monkeypatch, tmp_path):
    """Con frontmatter graph_rag, l'incrementale resta equivalente al full rebuild anche per gli
    archi doc->doc risolti (il resolver è funzione pura degli archi-alias persistiti)."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    fm = ('---\nid: "{id}"\ngraph_rag:\n  node_id: "{id}"\n  edges:\n{edges}---\n'
          "## Sezione\n[{marker}] regola su {marker}\n")
    (docs_dir / "safe.md").write_text(
        fm.format(id="safe-v1.0", edges="", marker="SAFE"), encoding="utf-8")
    (docs_dir / "spec.md").write_text(
        fm.format(id="spec-v1.0",
                  edges='    - type: "EREDITA_VINCOLI"\n      target: "safe-v1.2"\n',
                  marker="SPEC"), encoding="utf-8")
    stub, q = StubEmbed(), StatefulFakeQdrant()
    index.build_graph_and_index(qdrant=q, embed_model=stub)

    G = _load_graph()
    assert G.has_edge("spec.md", "safe.md")                          # doc->doc risolto nel full build
    report = index.check_graph_consistency(embed_model=stub, docs_dir=docs_dir, code_dir=code_dir)
    assert report["consistent"] is True, report                      # equivalenza col rebuild


# ---------------------------------------------------------------------------
# 6. Refactor parametrico di build_graph_and_index (S6.2, blue/green Qdrant):
# nome versione deciso una sola volta e riusato ovunque; collection_name esplicito
# ma identico a COLLECTION_NAME nel percorso attuale. Nessun cambio di comportamento.
# ---------------------------------------------------------------------------
def test_build_graph_and_index_generates_version_name_exactly_once(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    stub, q = StubEmbed(), StatefulFakeQdrant()

    calls: list[str] = []
    real_new_version_name = index._new_version_name

    def _counting_new_version_name():
        name = real_new_version_name()
        calls.append(name)
        return name

    monkeypatch.setattr(index, "_new_version_name", _counting_new_version_name)

    index.build_graph_and_index(qdrant=q, embed_model=stub)
    assert len(calls) == 1


def test_build_graph_and_index_version_used_for_save_artifacts_matches_rest_of_flow(monkeypatch, tmp_path):
    """Il nome restituito (e usato per manifest/log/promote) deve coincidere con
    quello passato a save_artifacts: una sola identità di versione lungo tutto il
    flusso, non due generazioni indipendenti."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    stub, q = StubEmbed(), StatefulFakeQdrant()

    captured: dict = {}
    real_save_artifacts = index.save_artifacts

    def _spy_save_artifacts(*a, **kw):
        captured["version_passed_in"] = kw.get("version")
        return real_save_artifacts(*a, **kw)

    monkeypatch.setattr(index, "save_artifacts", _spy_save_artifacts)

    logs: list[str] = []
    version = index.build_graph_and_index(qdrant=q, embed_model=stub, emit=logs.append)

    assert captured["version_passed_in"] == version
    assert _artifacts.current_version() == version  # promossa con la stessa identità
    assert any(version in m and "salvati nella versione" in m for m in logs)
    assert any(version in m and "promossa" in m for m in logs)


def test_build_graph_and_index_uses_collection_name_equal_to_config_constant(monkeypatch, tmp_path):
    """collection_name è una variabile locale esplicita (S6.2) ma vale sempre
    COLLECTION_NAME nel percorso attuale: nessuna collection candidata, nessun
    branch blue/green — il full rebuild opera esattamente come prima."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    stub, q = StubEmbed(), StatefulFakeQdrant()

    index.build_graph_and_index(qdrant=q, embed_model=stub)
    assert q.created_collection_names == [index.COLLECTION_NAME]
    assert q.upserted_collection_names == [index.COLLECTION_NAME]

    # Secondo full rebuild: la collection esiste già -> passa anche dal delete
    # (recreate=True), sempre sullo stesso nome, mai una collection diversa.
    index.build_graph_and_index(qdrant=q, embed_model=stub)
    assert set(q.deleted_collection_names) == {index.COLLECTION_NAME}
    assert q.created_collection_names == [index.COLLECTION_NAME, index.COLLECTION_NAME]
    assert q.upserted_collection_names == [index.COLLECTION_NAME, index.COLLECTION_NAME]


# ---------------------------------------------------------------------------
# 7. Build su collection candidata + eval-gate sulla candidata (S6.3/S6.4,
# blue/green Qdrant). Flag spento: comportamento storico byte-per-byte. Flag
# acceso: build e gate operano SOLO sulla candidata versionata, mai sulla
# produzione durante il BUILD (l'alias swap alla promozione è testato nella
# sezione 8, più sotto).
# ---------------------------------------------------------------------------
def _manifest_for_version(version: str) -> dict:
    return json.loads((_artifacts.version_dir(version) / "index_manifest.json").read_text(encoding="utf-8"))


def test_flag_off_full_rebuild_still_uses_collection_name_and_gate_evaluates_it(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", False)
    stub, q = StubEmbed(), StatefulFakeQdrant()

    captured_gate: dict = {}
    real_gate_promotion = index.gate_promotion

    def _spy_gate(*a, **kw):
        captured_gate["collection_name"] = kw.get("collection_name")
        return real_gate_promotion(*a, **kw)

    monkeypatch.setattr(index, "gate_promotion", _spy_gate)

    version = index.build_graph_and_index(qdrant=q, embed_model=stub)

    assert q.created_collection_names == [index.COLLECTION_NAME]
    assert q.upserted_collection_names == [index.COLLECTION_NAME]
    assert _manifest_for_version(version)["qdrant_collection"] == index.COLLECTION_NAME
    assert captured_gate["collection_name"] == index.COLLECTION_NAME


def test_flag_on_full_rebuild_creates_and_uses_only_the_candidate_collection(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    stub, q = StubEmbed(), StatefulFakeQdrant()

    version = index.build_graph_and_index(qdrant=q, embed_model=stub)

    candidate = index.qdrant_collection_name(version)
    assert candidate != index.COLLECTION_NAME
    assert q.created_collection_names == [candidate]
    assert q.upserted_collection_names == [candidate]


def test_flag_on_never_drops_or_touches_legacy_production_during_build(monkeypatch, tmp_path):
    """La produzione (COLLECTION_NAME) preesiste (layout legacy popolato): il full
    rebuild col flag acceso non deve mai droppare né alterare il suo contenuto
    DURANTE il build. Gate mockato a bloccante per restare scoped al build (la
    promozione/alias swap, che con produzione non migrata solleverebbe — vedi
    test_flag_on_legacy_collision_promotes_current_then_alias_swap_fails più sotto —
    non è ciò che questo test vuole esercitare)."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": False})
    stub, q = StubEmbed(), StatefulFakeQdrant()
    q.collections.add(index.COLLECTION_NAME)
    q.points["prod-point-1"] = SimpleNamespace(id="prod-point-1", payload={"doc_id": "legacy.md"})

    index.build_graph_and_index(qdrant=q, embed_model=stub)

    assert index.COLLECTION_NAME not in q.deleted_collection_names
    assert index.COLLECTION_NAME not in q.created_collection_names  # mai ricreata
    assert index.COLLECTION_NAME in q.collections                   # ancora presente
    assert "prod-point-1" in q.points                                # dato di produzione intatto
    assert index.COLLECTION_NAME not in q.upserted_collection_names  # upsert solo sulla candidata


def test_flag_on_manifest_contains_the_candidate_qdrant_collection(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    stub, q = StubEmbed(), StatefulFakeQdrant()

    version = index.build_graph_and_index(qdrant=q, embed_model=stub)

    candidate = index.qdrant_collection_name(version)
    assert _manifest_for_version(version)["qdrant_collection"] == candidate


def test_flag_on_gate_evaluates_the_candidate_not_the_production(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    stub, q = StubEmbed(), StatefulFakeQdrant()

    captured: dict = {}

    def _fake_gate(version, qdrant, embed_model, colbert_store, emit=None, collection_name=None, **kw):
        captured["collection_name"] = collection_name
        return {"passed": True}

    monkeypatch.setattr(index, "gate_promotion", _fake_gate)

    version = index.build_graph_and_index(qdrant=q, embed_model=stub)

    candidate = index.qdrant_collection_name(version)
    assert captured["collection_name"] == candidate
    assert captured["collection_name"] != index.COLLECTION_NAME


def test_flag_on_blocking_gate_leaves_current_and_production_untouched(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    stub, q = StubEmbed(), StatefulFakeQdrant()
    q.collections.add(index.COLLECTION_NAME)
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": False})

    index.build_graph_and_index(qdrant=q, embed_model=stub)

    assert _artifacts.current_version_token() is None  # mai promossa
    assert index.COLLECTION_NAME in q.collections       # produzione intatta
    assert index.COLLECTION_NAME not in q.deleted_collection_names
    assert q.aliases == {}                              # nessuna operazione di alias (S6.5)


# ---------------------------------------------------------------------------
# 8. Alias swap + migrazione one-shot dopo la promozione locale (S6.5/S6.6,
# blue/green Qdrant): ordine CURRENT-poi-migrazione(se serve)-poi-alias, target
# corretto, nessuna operazione col flag spento, nessuna operazione se il gate
# blocca. Layout legacy non ancora migrato: la collection fisica COLLECTION_NAME
# viene cancellata (migrazione one-shot, S6.6) e l'alias creato subito dopo — mai
# più un decline. Layout già migrato o installazione fresca (nessuna collisione):
# nessun delete, solo lo swap.
# ---------------------------------------------------------------------------
def test_flag_off_promote_never_touches_aliases(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", False)
    stub, q = StubEmbed(), StatefulFakeQdrant()
    q.collections.add(index.COLLECTION_NAME)
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": True})

    version = index.build_graph_and_index(qdrant=q, embed_model=stub)

    assert _artifacts.current_version_token() == version  # promossa normalmente
    assert q.aliases == {}                                  # nessuna operazione di alias


def test_flag_on_promote_writes_current_before_alias_swap(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": True})
    stub, q = StubEmbed(), StatefulFakeQdrant()

    sequence: list[str] = []
    real_promote_version = index.promote_version

    def _tracking_promote(version):
        sequence.append("promote")
        return real_promote_version(version)

    monkeypatch.setattr(index, "promote_version", _tracking_promote)

    real_update_aliases = q.update_collection_aliases

    def _tracking_update_aliases(change_aliases_operations):
        sequence.append("alias_swap")
        return real_update_aliases(change_aliases_operations)

    q.update_collection_aliases = _tracking_update_aliases

    index.build_graph_and_index(qdrant=q, embed_model=stub)

    assert sequence == ["promote", "alias_swap"]  # ordine non negoziabile


def test_flag_on_alias_points_to_the_promoted_version_collection(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": True})
    stub, q = StubEmbed(), StatefulFakeQdrant()

    version = index.build_graph_and_index(qdrant=q, embed_model=stub)

    candidate = index.qdrant_collection_name(version)
    assert q.aliases[index.COLLECTION_NAME] == candidate
    assert _artifacts.current_version_token() == version


def test_flag_on_legacy_layout_migrates_deletes_legacy_then_creates_alias(monkeypatch, tmp_path):
    """S6.6: layout legacy NON ancora migrato — COLLECTION_NAME esiste come
    collection FISICA di produzione. La migrazione avviene DAVVERO (sostituisce il
    decline di S6.5): la collection legacy viene cancellata solo dopo che CURRENT è
    già stato promosso (build completata, gate passato), e SUBITO prima che l'alias
    venga creato verso la candidata — ordine esplicito e tracciato."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": True})
    stub, q = StubEmbed(), StatefulFakeQdrant()
    q.collections.add(index.COLLECTION_NAME)  # produzione legacy, non ancora migrata

    sequence: list[str] = []
    real_promote_version = index.promote_version

    def _tracking_promote(version):
        sequence.append("promote")
        return real_promote_version(version)

    monkeypatch.setattr(index, "promote_version", _tracking_promote)

    real_delete_collection = q.delete_collection

    def _tracking_delete(collection_name):
        sequence.append(f"delete:{collection_name}")
        return real_delete_collection(collection_name)

    q.delete_collection = _tracking_delete

    real_update_aliases = q.update_collection_aliases

    def _tracking_update_aliases(change_aliases_operations):
        sequence.append("alias_create")
        return real_update_aliases(change_aliases_operations)

    q.update_collection_aliases = _tracking_update_aliases

    logs: list[str] = []
    version = index.build_graph_and_index(qdrant=q, embed_model=stub, emit=logs.append)

    candidate = index.qdrant_collection_name(version)
    assert sequence == ["promote", f"delete:{index.COLLECTION_NAME}", "alias_create"]
    assert index.COLLECTION_NAME not in q.collections     # collection fisica legacy cancellata
    assert q.aliases[index.COLLECTION_NAME] == candidate    # ora è un alias verso la candidata
    assert _artifacts.current_version_token() == version    # promozione COMPLETA riuscita
    assert any("migrazione" in m.lower() and "irreversibile" in m.lower() for m in logs)


def test_flag_on_legacy_migration_crash_between_delete_and_create_leaves_alias_missing(monkeypatch, tmp_path):
    """Documenta esplicitamente il gap accettato dal design: un crash ESATTAMENTE
    nella finestra fra il delete della collection legacy e la create dell'alias
    (breve ma reale). CURRENT è già promosso (ordine invariato: la migrazione parte
    solo dopo), la collection fisica non esiste più, l'alias non è mai stato creato:
    il reconciler read-only (S5) osserva questo esatto stato come "missing".
    Ripararlo automaticamente NON avviene qui: è lavoro futuro di S8."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": True})
    stub, q = StubEmbed(), StatefulFakeQdrant()
    q.collections.add(index.COLLECTION_NAME)

    def _boom(change_aliases_operations):
        raise ConnectionError("crash simulato: delete già avvenuto, create mai eseguita")

    q.update_collection_aliases = _boom

    with pytest.raises(ConnectionError):
        index.build_graph_and_index(qdrant=q, embed_model=stub)

    assert _artifacts.current_version_token() is not None  # CURRENT già promosso prima della migrazione
    assert index.COLLECTION_NAME not in q.collections        # delete già avvenuto
    assert index.COLLECTION_NAME not in q.aliases             # create mai riuscita: nessun alias

    # Esattamente lo stato "missing" osservato dal reconciler read-only (S5) — non
    # riparato qui: la riparazione automatica di questo gap resta lavoro di S8.
    report = index.reconcile_qdrant_alias(q)
    assert report["state"] == "missing"


def test_flag_on_migrated_layout_promotes_and_swaps_to_new_candidate(monkeypatch, tmp_path):
    """Layout GIA' migrato (ipotetico esito futuro di S6.6): l'alias esiste e punta
    a una vecchia collection, nessuna collection fisica omonima a COLLECTION_NAME.
    Nessuna collisione possibile: promote + swap procedono normalmente, l'alias si
    sposta sulla NUOVA candidata di questa build."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": True})
    stub, q = StubEmbed(), StatefulFakeQdrant()
    q.collections.add("vibecraft_events__v-vecchia")
    q.aliases[index.COLLECTION_NAME] = "vibecraft_events__v-vecchia"

    version = index.build_graph_and_index(qdrant=q, embed_model=stub)

    candidate = index.qdrant_collection_name(version)
    assert q.aliases[index.COLLECTION_NAME] == candidate  # alias spostato sulla nuova candidata
    assert _artifacts.current_version_token() == version


def test_flag_on_full_rebuild_never_calls_reconciler_repair_helpers(monkeypatch, tmp_path):
    """Il full rebuild collega _swap_alias e, da S8, il GC delle collection orfane
    (gc_orphaned_qdrant_collections) SUBITO dopo lo swap — ma non ha alcun motivo di
    invocare la riparazione del reconciler (repair_qdrant_alias/
    reconcile_and_repair_qdrant_alias, riservata a boot pre-serving e a un rollback
    S7 lasciato divergente): un rebuild riuscito produce sempre uno stato "aligned"
    per costruzione, quindi quegli helper restano fuori da questo percorso."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": True})
    stub, q = StubEmbed(), StatefulFakeQdrant()

    def _boom(*a, **k):
        raise AssertionError("il full rebuild non deve chiamare la riparazione del reconciler")

    monkeypatch.setattr(index, "repair_qdrant_alias", _boom)
    monkeypatch.setattr(index, "reconcile_and_repair_qdrant_alias", _boom)

    version = index.build_graph_and_index(qdrant=q, embed_model=stub)
    assert version  # arrivato qui senza eccezioni: nessun helper di riparazione chiamato


# ---------------------------------------------------------------------------
# 9. S7: rollback blue/green (alias swap nel chiamante, mai in core.artifacts) e
# lineage incrementale (il figlio eredita qdrant_collection dal padre, senza mai
# muovere l'alias). GC automatico e reconciler riparatore restano fuori scope.
# ---------------------------------------------------------------------------
def test_rollback_flag_off_never_touches_alias(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", False)
    q = StatefulFakeQdrant()

    v1 = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    index.write_index_manifest(0, version=v1, qdrant_collection=index.qdrant_collection_name(v1))
    index.promote_version(v1)

    result = index.rollback_qdrant_alias_if_needed(q, v1)
    assert result == {"state": "disabled"}
    assert q.aliases == {}


def test_rollback_cross_lineage_swaps_alias_to_target_collection(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    q = StatefulFakeQdrant()

    v1 = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    c1 = index.qdrant_collection_name(v1)
    index.write_index_manifest(0, version=v1, qdrant_collection=c1)
    q.collections.add(c1)
    index.promote_version(v1)
    q.aliases[index.COLLECTION_NAME] = c1

    v2 = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    c2 = index.qdrant_collection_name(v2)
    index.write_index_manifest(0, version=v2, qdrant_collection=c2)
    q.collections.add(c2)
    index.promote_version(v2)
    q.aliases[index.COLLECTION_NAME] = c2  # produzione ora sulla lineage di v2

    # Rollback locale (core.artifacts, puro) verso v1: CURRENT torna indietro.
    target = _artifacts.rollback_version(v1)
    assert target == v1

    logs: list[str] = []
    result = index.rollback_qdrant_alias_if_needed(q, target, logs.append)
    assert result == {"state": "swapped", "expected": c1, "actual": c1}
    assert q.aliases[index.COLLECTION_NAME] == c1
    assert any("🔀" in m for m in logs)


def test_rollback_intra_lineage_is_noop_with_clear_log(monkeypatch, tmp_path):
    """L'alias punta già alla collection della versione target (rollback dentro la
    stessa lineage Qdrant, es. due versioni incrementali sulla stessa collection
    padre): nessuna operazione di alias, solo un log esplicito di no-op."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    q = StatefulFakeQdrant()

    shared_collection = index.qdrant_collection_name("v-shared")
    q.collections.add(shared_collection)
    q.aliases[index.COLLECTION_NAME] = shared_collection

    v1 = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    index.write_index_manifest(0, version=v1, qdrant_collection=shared_collection)
    index.promote_version(v1)

    v2 = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    index.write_index_manifest(0, version=v2, qdrant_collection=shared_collection)
    index.promote_version(v2)

    target = _artifacts.rollback_version(v1)

    real_update_aliases = q.update_collection_aliases
    def _boom(*a, **k):
        raise AssertionError("intra-lineage: nessuna scrittura di alias attesa")
    q.update_collection_aliases = _boom

    logs: list[str] = []
    result = index.rollback_qdrant_alias_if_needed(q, target, logs.append)
    assert result == {"state": "noop", "expected": shared_collection, "actual": shared_collection}
    assert any("nessuna" in m.lower() for m in logs)
    q.update_collection_aliases = real_update_aliases  # ripristino, per igiene


def test_rollback_missing_target_collection_is_explicit_and_not_corrected(monkeypatch, tmp_path):
    """La collection della versione target non esiste più su Qdrant (es. GC manuale
    o installazione incompleta): nessuna correzione automatica, l'alias resta dov'è
    e lo stato lo dice esplicitamente — CURRENT è comunque già tornato al target sul
    lato locale (rollback_version è già stato eseguito prima di questa chiamata)."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    q = StatefulFakeQdrant()

    v1 = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    c1 = index.qdrant_collection_name(v1)
    index.write_index_manifest(0, version=v1, qdrant_collection=c1)
    index.promote_version(v1)
    # NB: c1 non viene mai aggiunta a q.collections: simula la collection sparita.

    v2 = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    c2 = index.qdrant_collection_name(v2)
    index.write_index_manifest(0, version=v2, qdrant_collection=c2)
    q.collections.add(c2)
    index.promote_version(v2)
    q.aliases[index.COLLECTION_NAME] = c2

    target = _artifacts.rollback_version(v1)
    assert _artifacts.current_version_token() == v1  # CURRENT già tornato al target, localmente

    logs: list[str] = []
    result = index.rollback_qdrant_alias_if_needed(q, target, logs.append)
    assert result == {"state": "missing_target_collection", "expected": c1, "actual": c2}
    assert q.aliases[index.COLLECTION_NAME] == c2  # alias INTATTO: nessuna correzione magica
    assert any("non esiste più" in m for m in logs)


def test_incremental_index_child_manifest_inherits_qdrant_collection_from_parent(monkeypatch, tmp_path):
    """Una versione incrementale nata da un padre costruito su una collection
    candidata (blue/green) deve dichiarare nel proprio manifest la STESSA collection
    del padre — non ricadere su COLLECTION_NAME solo perché l'incrementale non passa
    esplicitamente qdrant_collection a write_index_manifest."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": True})
    stub, q = StubEmbed(), StatefulFakeQdrant()

    parent_version = index.build_graph_and_index(qdrant=q, embed_model=stub)
    parent_collection = _manifest_for_version(parent_version)["qdrant_collection"]
    assert parent_collection != index.COLLECTION_NAME  # confermiamo che è la candidata

    (docs_dir / "spec.md").write_text(_spec("BETA"), encoding="utf-8")
    stats = index.incremental_index(qdrant=q, embed_model=stub)
    child_version = stats["version"]

    assert _manifest_for_version(child_version)["qdrant_collection"] == parent_collection


def test_incremental_index_bootstrap_without_parent_manifest_falls_back_to_collection_name(monkeypatch, tmp_path):
    """Fresh install: nessuna versione promossa ancora, quindi nessun manifest padre
    da cui ereditare. L'incrementale (che tratta tutto come 'new', equivalente a un
    full) deve comunque produrre un manifest coerente, con qdrant_collection pari al
    default storico COLLECTION_NAME — nessuna eccezione, nessun None propagato."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    stub, q = StubEmbed(), StatefulFakeQdrant()

    stats = index.incremental_index(qdrant=q, embed_model=stub)
    version = stats["version"]

    assert _manifest_for_version(version)["qdrant_collection"] == index.COLLECTION_NAME


def test_incremental_index_never_calls_swap_alias(monkeypatch, tmp_path):
    """Vincolo esplicito di S7: l'incrementale eredita la collection del padre ma non
    promuove né sposta MAI l'alias, indipendentemente dal flag blue/green."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": True})
    stub, q = StubEmbed(), StatefulFakeQdrant()

    index.build_graph_and_index(qdrant=q, embed_model=stub)

    def _boom(*a, **k):
        raise AssertionError("incremental_index non deve mai chiamare _swap_alias")
    monkeypatch.setattr(index, "_swap_alias", _boom)

    (docs_dir / "spec.md").write_text(_spec("BETA"), encoding="utf-8")
    stats = index.incremental_index(qdrant=q, embed_model=stub)
    assert stats["version"]  # arrivato qui senza eccezioni: _swap_alias mai chiamata


# ---------------------------------------------------------------------------
# 10. S8: reconciler riparatore (diverging/missing -> swap, se sicuro) e GC delle
# collection Qdrant orfane, nei soli punti consentiti (boot pre-serving, writer
# subito dopo promote/alias-swap). Nessuna correzione se la collection target manca.
# ---------------------------------------------------------------------------
def test_repair_qdrant_alias_flag_off_is_disabled_and_writes_nothing(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", False)
    q = StatefulFakeQdrant()

    def _boom(*a, **k):
        raise AssertionError("flag off: nessuna lettura/scrittura Qdrant attesa dal repair")
    q.get_aliases = _boom
    q.update_collection_aliases = _boom

    result = index.repair_qdrant_alias(q)
    assert result == {"state": "disabled"}


def test_repair_qdrant_alias_fixes_diverging_state(monkeypatch, tmp_path):
    """CURRENT è avanzato oltre l'ultimo swap (es. rollback S7 non corretto):
    l'alias diverge dalla collection attesa, ma quella collection esiste -> repair
    la ripara con uno swap reale."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    q = StatefulFakeQdrant()

    v1 = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    c1 = index.qdrant_collection_name(v1)
    index.write_index_manifest(0, version=v1, qdrant_collection=c1)
    index.promote_version(v1)
    q.collections.add(c1)

    old_collection = index.qdrant_collection_name("v-vecchia")
    q.collections.add(old_collection)
    q.aliases[index.COLLECTION_NAME] = old_collection  # alias ancora sulla vecchia

    logs: list[str] = []
    result = index.repair_qdrant_alias(q, emit=logs.append)
    assert result["state"] == "diverging" and result["repaired"] is True
    assert q.aliases[index.COLLECTION_NAME] == c1
    assert any("riparato" in m.lower() for m in logs)


def test_repair_qdrant_alias_fixes_missing_state(monkeypatch, tmp_path):
    """Il crash fra delete legacy e create alias (S6.6) lascia l'alias mancante:
    se la collection attesa esiste, il repair crea l'alias verso di essa."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    q = StatefulFakeQdrant()

    v1 = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    c1 = index.qdrant_collection_name(v1)
    index.write_index_manifest(0, version=v1, qdrant_collection=c1)
    index.promote_version(v1)
    q.collections.add(c1)
    # Nessun alias: esattamente lo stato "missing" del crash S6.6.

    result = index.repair_qdrant_alias(q)
    assert result["state"] == "missing" and result["repaired"] is True
    assert q.aliases[index.COLLECTION_NAME] == c1


def test_repair_qdrant_alias_declines_when_target_collection_missing(monkeypatch, tmp_path):
    """La collection attesa non esiste più su Qdrant: nessuna correzione automatica
    distruttiva, nessun alias creato/spostato — solo repaired=False esplicito."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    q = StatefulFakeQdrant()

    v1 = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    c1 = index.qdrant_collection_name(v1)
    index.write_index_manifest(0, version=v1, qdrant_collection=c1)
    index.promote_version(v1)
    # c1 non viene mai aggiunta a q.collections: simula la collection sparita.

    logs: list[str] = []
    result = index.repair_qdrant_alias(q, emit=logs.append)
    assert result["state"] == "missing" and result["repaired"] is False
    assert q.aliases == {}  # nessuna scrittura
    assert any("non esiste" in m for m in logs)


def test_repair_qdrant_alias_aligned_state_is_a_pure_noop(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    q = StatefulFakeQdrant()

    v1 = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    c1 = index.qdrant_collection_name(v1)
    index.write_index_manifest(0, version=v1, qdrant_collection=c1)
    index.promote_version(v1)
    q.collections.add(c1)
    q.aliases[index.COLLECTION_NAME] = c1

    result = index.repair_qdrant_alias(q)
    assert result == {"state": "aligned", "expected": c1, "actual": c1, "repaired": False}


def test_reconcile_and_repair_qdrant_alias_degrades_to_unknown_on_error(monkeypatch):
    """Come observe_qdrant_alias (S5): un Qdrant irraggiungibile non deve mai
    propagare l'eccezione, né impedire il boot — degrada a stato 'unknown'."""
    class _BoomQdrant:
        def get_aliases(self):
            raise ConnectionError("Qdrant irraggiungibile")

        def close(self):
            pass

    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    result = index.reconcile_and_repair_qdrant_alias(_BoomQdrant())
    assert result["state"] == "unknown" and result["repaired"] is False
    assert "ConnectionError" in result["error"]


def test_flag_on_legacy_migration_crash_converges_after_boot_repair(monkeypatch, tmp_path):
    """Lo stesso scenario testato in S6.6 (crash fra delete legacy e create alias,
    osservato come 'missing') converge ora con la riparazione di S8: senza alcun
    nuovo full rebuild, il boot (reconcile_and_repair_qdrant_alias) ripara l'alias."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": True})
    stub, q = StubEmbed(), StatefulFakeQdrant()
    q.collections.add(index.COLLECTION_NAME)

    def _boom(change_aliases_operations):
        raise ConnectionError("crash simulato: delete già avvenuto, create mai eseguita")
    q.update_collection_aliases = _boom

    with pytest.raises(ConnectionError):
        index.build_graph_and_index(qdrant=q, embed_model=stub)

    report = index.reconcile_qdrant_alias(q)
    assert report["state"] == "missing"  # stato pre-S8: osservato ma non riparato qui

    # Il crash ha lasciato la collection candidata intatta (solo l'alias è mancante):
    # al prossimo boot (o writer successivo) la riparazione converge senza rebuild.
    q.update_collection_aliases = StatefulFakeQdrant.update_collection_aliases.__get__(q)
    repair = index.reconcile_and_repair_qdrant_alias(q)
    assert repair["state"] == "missing" and repair["repaired"] is True
    assert index.reconcile_qdrant_alias(q)["state"] == "aligned"


def test_gc_orphaned_qdrant_collections_flag_off_returns_empty_and_touches_nothing(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", False)
    q = StatefulFakeQdrant()

    def _boom(*a, **k):
        raise AssertionError("flag off: GC non deve toccare Qdrant")
    q.get_collections = _boom
    q.delete_collection = _boom

    assert index.gc_orphaned_qdrant_collections(q) == []


def test_gc_orphaned_qdrant_collections_keeps_alias_target_and_referenced_manifests(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    q = StatefulFakeQdrant()

    v_active = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    c_active = index.qdrant_collection_name(v_active)
    index.write_index_manifest(0, version=v_active, qdrant_collection=c_active)
    index.promote_version(v_active)
    q.collections.add(c_active)
    q.aliases[index.COLLECTION_NAME] = c_active

    v_other = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})  # non promossa, ma manifest sopravvive
    c_other_referenced = index.qdrant_collection_name(v_other)
    index.write_index_manifest(0, version=v_other, qdrant_collection=c_other_referenced)
    q.collections.add(c_other_referenced)

    orphan = index.qdrant_collection_name("v-crashata-senza-manifest")
    q.collections.add(orphan)

    removed = index.gc_orphaned_qdrant_collections(q)
    assert removed == [orphan]
    assert c_active in q.collections           # target dell'alias: mai toccata
    assert c_other_referenced in q.collections  # referenziata da un manifest: mai toccata
    assert orphan not in q.collections          # orfana sicura: rimossa


def test_gc_orphaned_qdrant_collections_removes_safe_orphans_after_prune(monkeypatch, tmp_path):
    """Dopo la retention locale (prune_versions, chiamata da promote_version), le
    collection delle versioni potate non sono più referenziate: il GC le rimuove."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    monkeypatch.setattr(_artifacts, "_keep_from_env", lambda: 1)
    q = StatefulFakeQdrant()

    v1 = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    c1 = index.qdrant_collection_name(v1)
    index.write_index_manifest(0, version=v1, qdrant_collection=c1)
    index.promote_version(v1)
    q.collections.add(c1)
    q.aliases[index.COLLECTION_NAME] = c1

    v2 = index.save_artifacts(nx.DiGraph(), {}, {}, {}, {})
    c2 = index.qdrant_collection_name(v2)
    index.write_index_manifest(0, version=v2, qdrant_collection=c2)
    index.promote_version(v2)  # retention keep=1: v1 viene potata, il suo manifest sparisce
    q.collections.add(c2)
    q.aliases[index.COLLECTION_NAME] = c2

    assert v1 not in index.list_versions()  # confermato: v1 potata dalla retention

    removed = index.gc_orphaned_qdrant_collections(q)
    assert removed == [c1]
    assert c2 in q.collections


def test_full_rebuild_gc_never_touches_the_current_job_candidate(monkeypatch, tmp_path):
    """Vincolo esplicito di S8: la collection appena promossa/swappata dal job in
    corso è per costruzione sempre referenziata dal proprio manifest e sempre il
    target dell'alias -> il GC collegato dopo lo swap non deve mai rimuoverla."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": True})
    stub, q = StubEmbed(), StatefulFakeQdrant()

    # Collection orfana preesistente (es. build crashato precedente, mai referenziata).
    orphan = index.qdrant_collection_name("v-crashata-precedente")
    q.collections.add(orphan)

    version = index.build_graph_and_index(qdrant=q, embed_model=stub)
    candidate = index.qdrant_collection_name(version)

    assert candidate in q.collections
    assert q.aliases[index.COLLECTION_NAME] == candidate
    assert orphan not in q.collections  # orfana rimossa, la candidata del job resta intatta
    assert candidate not in q.deleted_collection_names


def test_full_rebuild_wires_gc_right_after_alias_swap(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", True)
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": True})
    stub, q = StubEmbed(), StatefulFakeQdrant()

    sequence: list[str] = []
    real_swap = index._swap_alias

    def _tracking_swap(qdrant, alias, target):
        sequence.append("alias_swap")
        return real_swap(qdrant, alias, target)

    monkeypatch.setattr(index, "_swap_alias", _tracking_swap)

    real_gc = index.gc_orphaned_qdrant_collections

    def _tracking_gc(qdrant, **kw):
        sequence.append("gc")
        return real_gc(qdrant, **kw)

    monkeypatch.setattr(index, "gc_orphaned_qdrant_collections", _tracking_gc)

    index.build_graph_and_index(qdrant=q, embed_model=stub)
    assert sequence == ["alias_swap", "gc"]


def test_flag_off_full_rebuild_never_calls_gc_or_repair_helpers(monkeypatch, tmp_path):
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "QDRANT_BLUE_GREEN", False)
    stub, q = StubEmbed(), StatefulFakeQdrant()

    def _boom(*a, **k):
        raise AssertionError("flag off: nessun GC/repair atteso")
    monkeypatch.setattr(index, "gc_qdrant_collections", _boom)
    monkeypatch.setattr(index, "repair_qdrant_alias", _boom)

    version = index.build_graph_and_index(qdrant=q, embed_model=stub)
    assert version  # nessuna eccezione: gc_orphaned_qdrant_collections stessa è no-op col flag off

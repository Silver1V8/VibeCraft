"""Test dell'indicizzazione incrementale (delta): planning puro, id deterministici,
rimozione dei nodi-documento dal grafo senza distruggere i code-link, ed esecuzione
(delete-by-filter, idempotenza) con fake leggeri — nessun modello di embedding reale."""
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

    def get_collections(self):
        return SimpleNamespace(collections=[SimpleNamespace(name=n) for n in self.collections])

    def create_collection(self, collection_name, **kw):
        self.collections.add(collection_name)

    def delete_collection(self, collection_name):
        self.collections.discard(collection_name)
        self.points.clear()

    def upsert(self, collection_name, points):
        for p in points:
            self.points[p.id] = p

    def delete(self, collection_name, points_selector):
        dead = set(points_selector.filter.must[0].match.any)
        self.points = {pid: p for pid, p in self.points.items() if p.payload.get("doc_id") not in dead}

    def close(self):
        pass


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

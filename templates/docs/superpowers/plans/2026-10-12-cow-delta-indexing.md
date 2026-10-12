# Delta copy-on-write per gli indici immutabili — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un reindex incrementale non vuoto su un progetto ordinario (snapshot immutabili) ricalcola solo documenti e file di codice cambiati, pubblicando comunque una versione con collection Qdrant dedicata, invece di ricostruire l'intero corpus.

**Architecture:** la versione candidata nasce copiando dal padre i punti Qdrant dei documenti invariati in una collection nuova (`<progetto>__<versione>`), poi riusa il motore delta già esistente (`apply_incremental_indexing`: grafo, sidecar, ColBERT copy-on-write via `ColbertWriter(parent=…)`, code-link mirati) puntandolo sulla candidata. Promozione con lo stesso eval gate, swap alias e GC del full rebuild, estratti in un helper condiviso. Se il padre non è riusabile si ripiega sul full rebuild di oggi, prima di qualunque scrittura.

**Tech Stack:** Python 3.14, qdrant-client (server Qdrant v1.19.0), NetworkX, FlagEmbedding bge-m3, pytest. Nessuna nuova dipendenza.

**Spec:** questo documento (sezioni «Contesto e motivazione» e «Comportamento richiesto»). Valutazione del 2026-10-12: progetto SGD_FE con 38.643 simboli di codice, embedding su CPU stimato in circa 6 ore per ogni delta non vuoto.

## Contesto e motivazione

- In `rag/core/indexing.py`, `incremental_index` ha due rami. Ramo legacy: vero delta in place sulla collection del padre (vietato con indice immutabile). Ramo progetti ordinari (`project.legacy is False`): controllo no-op, poi `build_graph_and_index` completo (commento `ponytail` alla riga ~1807).
- In questa installazione **tutti** i progetti in `projects/projects.json` hanno `"legacy": false`, quindi ogni delta non vuoto oggi è un full rebuild.
- Il costo dominante è `embed_symbols` su tutti i simboli di codice, non i documenti. I punti Qdrant contengono solo chunk dei documenti (vettori `dense` + `sparse`); i simboli vivono in `code.npz`/`code.json`, i multivettori ColBERT in `colbert/` (NPY).

## Comportamento richiesto

1. Delta non vuoto, padre riusabile → versione nuova `vN` con collection `<progetto>__vN` che contiene: punti del padre per i documenti non toccati + punti ricalcolati per nuovi/modificati; nessun punto dei cancellati. La collection del padre resta intatta (le versioni sono immutabili e il rollback deve funzionare).
2. Re-embedding solo dei documenti nuovi/modificati e dei file di codice aggiunti/modificati.
3. Grafo risultante equivalente al full rebuild sugli stessi input (`check_graph_consistency` → `consistent: True`).
4. Promozione solo dopo l'eval gate; gate rifiutato → CURRENT e alias invariati (stesso comportamento del full).
5. Ripiego sul full rebuild, con motivo nel risultato del job (`fallback_reason`), quando: `VIBECRAFT_DELTA_MODE=rebuild`; manifest attivo assente; versione attiva non immutabile; modello di embedding diverso da quello del manifest; collection del padre non dedicata o assente su Qdrant; ColBERT del padre non attestato dal manifest.
6. Il risultato del job dichiara `delta_mode: "cow" | "rebuild"`; con cow anche `copied_points` e `promoted`.
7. Delta ristretto (`changed_paths`, webhook o approve dell'intake): stessa semantica del ramo legacy. I file non segnalati restano con l'hash precedente nel manifest e quindi visibili come stale, e la candidata ne conserva i punti del padre.

## Global Constraints

- Python solo da `rag/.venv/Scripts/python.exe`; comandi lanciati da `rag/`, con `PYTHONUTF8=1` (o `-X utf8`).
- File con terminazioni LF; commenti e messaggi di log in italiano come il codice circostante.
- Mai scrivere sulla collection del padre né sull'alias prima della promozione; mai ricreare una collection esistente.
- Nessuna nuova dipendenza; nessuna modifica al ramo legacy oltre all'estrazione di helper senza cambi di comportamento.
- Branch `feat/cow-delta-indexing` da `main`; commit piccoli, uno per task, con la riga `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Suite completa prima del merge: `bash scripts/ci.sh` (ruff + pytest). I test su Qdrant reale girano solo con `VIBECRAFT_TEST_QDRANT_URL`.

## Review Focus

1. **Delta ristretto con altre modifiche non segnalate**: i documenti cambiati ma non in `changed_paths` devono restare stale e conservare i vettori del padre nella candidata, non sparire. Test in Task 3 (`test_cow_restricted_paths_keep_unprocessed_changes_stale`).
2. **Documento cancellato**: nessun suo punto nella candidata, ma ancora presente nella collection del padre (rollback). Test in Task 3 (`test_cow_drops_deleted_doc_and_keeps_parent_pinned`).
3. **Padre non riusabile** (collection assente, modello cambiato, modalità `rebuild`): ripiego trasparente sul full, mai un job fallito. Test in Task 3 (`test_cow_falls_back_to_rebuild`).
4. **Gate rifiutato**: CURRENT e alias restano sul padre. Test in Task 3 (`test_cow_gate_rejection_keeps_parent_active`).
5. **Modifica di solo codice**: tutti i punti copiati dal padre, simboli ricalcolati solo per il file toccato. Test in Task 3 (`test_cow_code_only_change_copies_all_points`).

---

### Task 1: Copia dei punti Qdrant fra collection

**Files:**
- Modify: `rag/core/indexing.py` (nuova funzione `_clone_points` accanto a `_delete_doc_chunks`, riga ~1383)
- Test: `rag/tests/test_cow_delta.py` (nuovo)

**Interfaces:**
- Produces: `_clone_points(qdrant: QdrantClient, source: str, target: str, *, exclude_doc_ids=(), batch_size: int | None = None) -> int`. Copia id, vettori nominati (`dense`, `sparse`) e payload da `source` a `target`, escludendo i punti con `payload.doc_id` in `exclude_doc_ids`; restituisce il numero di punti copiati.

- [ ] **Step 1: Write the failing test**

Crea `rag/tests/test_cow_delta.py`:

```python
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


def test_clone_points_copies_vectors_and_payload_excluding_docs(projects, qdrant):
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


def test_clone_points_without_exclusions_copies_everything(projects, qdrant):
    a, _ = projects
    src, dst = a.collection_name + "__src", a.collection_name + "__dst"
    for name in (src, dst):
        indexing._ensure_collection(qdrant, collection_name=name)
    qdrant.upsert(src, points=[_point(i, "a.md") for i in range(3)])

    assert indexing._clone_points(qdrant, src, dst) == 3
    assert indexing._clone_points(qdrant, src, dst) == 3  # idempotente: stessi id
    assert qdrant.count(dst).count == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run (da `rag/`): `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_cow_delta.py -v`
Expected: FAIL con `AttributeError: module 'core.indexing' has no attribute '_clone_points'`.

- [ ] **Step 3: Write minimal implementation**

In `rag/core/indexing.py`, subito dopo `_delete_doc_chunks`:

```python
def _clone_points(qdrant: QdrantClient, source: str, target: str, *,
                  exclude_doc_ids=(), batch_size: int | None = None) -> int:
    """Copia i punti (id, vettori nominati dense/sparse, payload) da `source` a `target`,
    saltando quelli il cui payload.doc_id è in `exclude_doc_ids`. È la base del delta
    copy-on-write: la candidata eredita i chunk invariati del padre senza ri-embedding,
    e il padre resta intatto (sola lettura). Id identici ⇒ idempotente."""
    batch_size = batch_size or qdrant_upsert_batch_from_env()
    excluded = list(exclude_doc_ids)
    scroll_filter = (Filter(must_not=[FieldCondition(key="doc_id", match=MatchAny(any=excluded))])
                     if excluded else None)
    copied, offset = 0, None
    while True:
        points, offset = qdrant.scroll(source, scroll_filter=scroll_filter, limit=batch_size,
                                       offset=offset, with_payload=True, with_vectors=True)
        if points:
            qdrant.upsert(collection_name=target, points=[
                PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in points])
            copied += len(points)
        if offset is None:
            return copied
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_cow_delta.py -v`
Expected: PASS (variante `memory`; `server` skipped senza `VIBECRAFT_TEST_QDRANT_URL`).

- [ ] **Step 5: Commit**

```bash
git add rag/core/indexing.py rag/tests/test_cow_delta.py
git commit -m "feat: copy Qdrant points between collections for copy-on-write deltas"
```

---

### Task 2: Estrazione degli helper condivisi (nessun cambio di comportamento)

**Files:**
- Modify: `rag/core/indexing.py`, cioè `build_graph_and_index` (blocco `if promote and version:`, righe ~642-685), `apply_incremental_indexing` (firma e le tre chiamate su `alias_name`), `incremental_index` (attestazione ColBERT righe ~1876-1888 e merge degli hash righe ~1925-1932)
- Test: suite esistente come rete di sicurezza

**Interfaces:**
- Produces:
  - `_gate_and_publish(qdrant, embed_model, version: str, collection_name: str, graph, chunks_store: dict, *, alias_name: str, emit, timings: dict, project, before_promote=None) -> dict` restituisce il dict del gate (`gate.get("passed")`).
  - `_attested_parent_colbert(arts, manifest, project) -> tuple[ColbertStore | None, dict | None]` solleva `RuntimeError` (indice NPZ) o `ValueError` (hash non attestati).
  - `_delta_manifest_hashes(manifest, plan, current: dict, code_delta: tuple[list, list, list], current_code: dict) -> tuple[dict, dict]` con `code_delta = (added, removed, modified)`.
  - `apply_incremental_indexing(..., collection_name: str | None = None)`: con `None` scrive sull'alias come oggi.

- [ ] **Step 1: Baseline verde**

Run: `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_incremental_indexing.py tests/test_index_timings.py tests/test_project_indexing.py tests/test_qdrant_blue_green.py tests/test_reindex.py -q`
Expected: tutti PASS (annota il conteggio).

- [ ] **Step 2: Estrai `_gate_and_publish`**

Aggiungi prima di `build_graph_and_index`:

```python
def _gate_and_publish(qdrant: QdrantClient, embed_model, version: str, collection_name: str,
                      graph: nx.DiGraph, chunks_store: dict, *, alias_name: str, emit,
                      timings: dict, project: ProjectContext | None, before_promote=None) -> dict:
    """Eval-gate sulla candidata e, se passa, promozione blue/green: CURRENT prima (commit
    point locale), poi l'eventuale migrazione legacy→alias, lo swap dell'alias e il GC.
    Condiviso da full rebuild e delta copy-on-write: entrambi pubblicano una collection
    dedicata e devono passare dallo STESSO gate. Restituisce il report del gate."""
    started = time.perf_counter()
    candidate_colbert = load_artifacts(version=version, required=("colbert",), project=project).colbert_store
    try:
        gate = gate_promotion(version, qdrant, embed_model, candidate_colbert, emit=emit,
                              collection_name=collection_name, graph=graph,
                              restatements=restatement_sections(chunks_store), project=project)
    finally:
        if isinstance(candidate_colbert, ColbertStore):
            candidate_colbert.close()
    timings["eval_gate"] = time.perf_counter() - started
    started = time.perf_counter()
    if not gate.get("passed"):
        emit(f"⛔ Promozione RIFIUTATA dall'eval-gate: CURRENT resta invariato. "
             f"Versione {version} salvata ma NON attiva. Investigare il calo di qualità.")
    else:
        if before_promote is not None:
            before_promote(version)
        promote_version(version, project=project)
        if project is None or project.legacy:
            _migrate_legacy_collection_if_needed(qdrant, alias_name, emit=emit)
        _swap_alias(qdrant, alias_name, collection_name)
        emit(f"🔀 Alias Qdrant '{alias_name}' → {collection_name} (blue/green).")
        gc_orphaned_qdrant_collections(qdrant, emit=emit, project=project)
        emit(f"🔁 Versione promossa: CURRENT → {version} (swap atomico, rollback: index.py --rollback).")
    timings["promote"] = time.perf_counter() - started
    return gate
```

In `build_graph_and_index` sostituisci l'intero blocco `if promote and version:` (dal commento «Eval-gate: valuta la recall…» fino a `timings["promote"] = time.perf_counter() - started` incluso) con:

```python
    if promote and version:
        # Eval-gate + promozione: vedi _gate_and_publish (condiviso col delta copy-on-write).
        _gate_and_publish(qdrant, embed_model, version, collection_name, G, state.chunks_store,
                          alias_name=alias_name, emit=_log, timings=timings, project=project,
                          before_promote=before_promote)
```

Conserva i commenti storici sull'ordine non negoziabile spostandoli nel docstring/corpo dell'helper se non già coperti.

- [ ] **Step 3: Estrai `_attested_parent_colbert` e `_delta_manifest_hashes`**

Aggiungi prima di `incremental_index`:

```python
def _attested_parent_colbert(arts, manifest, project: ProjectContext | None):
    """ColBERT del padre riusabile dal ColbertWriter solo se ogni file è attestato dal
    manifest della versione attiva. Restituisce (store, hash) oppure (None, None) se il
    padre non ha ColBERT. RuntimeError: indice NPZ da migrare; ValueError: hash divergenti."""
    colbert_store = arts.colbert_store
    parent_store = colbert_store if isinstance(colbert_store, ColbertStore) else None
    if parent_store is None:
        if colbert_store:
            raise RuntimeError("indice NPZ attivo: migrare prima con index.py --migrate-colbert-npy")
        return None, None
    parent_dir = artifact_dir(arts.version, project=project) / "colbert"
    expected = manifest.get("artifact_hashes", {}) if isinstance(manifest, dict) else {}
    if sha256_file(parent_dir / "index.json") != expected.get("colbert/index.json"):
        raise ValueError("indice ColBERT del padre non attestato dal manifest")
    parent_hashes = {name: meta["sha256"] for name, meta in parent_store.index["files"].items()}
    if any(expected.get(f"colbert/{name}") != digest for name, digest in parent_hashes.items()):
        raise ValueError("hash file ColBERT del padre divergenti dal manifest")
    return parent_store, parent_hashes


def _delta_manifest_hashes(manifest, plan: IndexPlan, current: dict[str, str],
                           code_delta: tuple[list[str], list[str], list[str]],
                           current_code: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Hash del manifest figlio: quelli del padre, meno i cancellati, più i (ri)elaborati.
    Con un delta ristretto i file non elaborati conservano la voce precedente e restano
    visibili come stale (il manifest descrive ciò che l'indice CONTIENE)."""
    code_added, code_removed, code_modified = code_delta
    old_docs = manifest.get("doc_hashes", {}) if isinstance(manifest, dict) else {}
    old_code = manifest.get("code_hashes", {}) if isinstance(manifest, dict) else {}
    doc_hashes = {p: h for p, h in old_docs.items() if p not in plan.deleted}
    doc_hashes.update({p: current[p] for p in [*plan.new, *plan.modified]})
    code_hashes = {p: h for p, h in old_code.items() if p not in code_removed}
    code_hashes.update({p: current_code[p] for p in [*code_added, *code_modified]})
    return doc_hashes, code_hashes
```

Nel ramo legacy di `incremental_index` sostituisci il blocco da `parent_store = colbert_store if isinstance(...)` fino alla chiusura del secondo `raise ValueError(...)` con:

```python
    parent_store, parent_hashes = _attested_parent_colbert(arts, manifest, project)
```

e il blocco da `old_docs = manifest.get("doc_hashes", {})…` fino a `code_hashes.update(...)` con:

```python
    doc_hashes, code_hashes = _delta_manifest_hashes(
        manifest, plan, current, (code_added, code_removed, code_modified), current_code)
```

(`old_code` resta usato più in alto per `_diff_hashes`: non rimuoverlo.)

- [ ] **Step 4: Rendi configurabile la collection di `apply_incremental_indexing`**

Aggiungi alla firma, dopo `project: ProjectContext | None = None,`:

```python
    collection_name: str | None = None,
```

Nel corpo, subito dopo `alias_name = ...`:

```python
    # Collection FISICA su cui scrivere: la candidata del delta copy-on-write, oppure
    # (default, ramo legacy) l'alias che risolve alla collection del padre.
    target = collection_name or alias_name
```

e sostituisci `collection_name=alias_name` con `collection_name=target` nelle tre chiamate: `_delete_doc_chunks(...)`, l'upsert per documento dentro `if colbert_writer is not None and doc_chunks:` e l'upsert di `new_chunks`. Aggiorna il docstring: «`collection_name`: collection su cui scrivere; default l'alias».

- [ ] **Step 5: Run tests to verify nothing changed**

Run: lo stesso comando dello Step 1, più `.venv/Scripts/python.exe -X utf8 -m ruff check core/indexing.py`
Expected: stesso conteggio PASS dello Step 1; ruff pulito.

- [ ] **Step 6: Commit**

```bash
git add rag/core/indexing.py
git commit -m "refactor: share gate/publish, parent ColBERT attestation and delta hashes"
```

---

### Task 3: Delta copy-on-write in `incremental_index`

**Files:**
- Modify: `rag/core/config.py` (accanto a `INDEX_MODE`, riga ~68)
- Modify: `rag/core/indexing.py`: import di `DELTA_MODE`, nuove `_CowUnavailable` e `_cow_delta_index`, ramo non-legacy di `incremental_index` (righe ~1800-1815), docstring di `incremental_index`
- Test: `rag/tests/test_cow_delta.py`

**Interfaces:**
- Consumes: `_clone_points` (Task 1); `_gate_and_publish`, `_attested_parent_colbert`, `_delta_manifest_hashes`, `apply_incremental_indexing(..., collection_name=)` (Task 2).
- Produces: `core.config.DELTA_MODE` (`"cow"` | `"rebuild"`, env `VIBECRAFT_DELTA_MODE`, default `"cow"`); risultato di `incremental_index` per progetti ordinari con le chiavi `delta_mode`, `fallback_reason` (solo rebuild), `copied_points` e `promoted` (solo cow), più quelle esistenti (`noop`, `version`, `reindexed_docs`, `deleted_docs`, `upserted_chunks`, `planned`, `counts`, `phase_timings_seconds`).

- [ ] **Step 1: Write the failing tests**

Aggiungi in fondo a `rag/tests/test_cow_delta.py`:

```python
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


def _seed(project, qdrant, monkeypatch):
    """v1: due documenti e due file di codice, full build promosso."""
    monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v1")
    _write(project, "keep.md", "# Keep\n\nKEEPMARK ALPHA\n")
    _write(project, "edit.md", "# Edit\n\nEDITMARK ALPHA\n")
    _write(project, "keep.py", "def keep():\n    return 'KEEPCODE'\n")
    _write(project, "edit.py", "def edit():\n    return 'EDITCODE'\n")
    assert build(project, qdrant) == "v1"
    monkeypatch.setattr(indexing, "_new_version_name", lambda **_: "v2")


def _doc_ids(qdrant, collection):
    return {p.payload["doc_id"] for p in _by_chunk(qdrant, collection).values()}


def test_cow_delta_reembeds_only_changed_sources(projects, qdrant, monkeypatch):
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


def test_cow_delta_matches_full_rebuild_points(projects, qdrant, monkeypatch):
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


def test_cow_drops_deleted_doc_and_keeps_parent_pinned(projects, qdrant, monkeypatch):
    a, _ = projects
    _seed(a, qdrant, monkeypatch)
    (a.docs_dir / "edit.md").unlink()

    stats = indexing.incremental_index(qdrant, Embed(), project=a)

    assert stats["delta_mode"] == "cow" and stats["deleted_docs"] == 1
    assert _doc_ids(qdrant, a.collection_name + "__v2") == {"keep.md"}
    assert _doc_ids(qdrant, a.collection_name + "__v1") == {"keep.md", "edit.md"}
    assert indexing.index_status(project=a)["stale"] is False


def test_cow_restricted_paths_keep_unprocessed_changes_stale(projects, qdrant, monkeypatch):
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


def test_cow_code_only_change_copies_all_points(projects, qdrant, monkeypatch):
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
def test_cow_falls_back_to_rebuild(projects, qdrant, monkeypatch, breakage):
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


def test_cow_gate_rejection_keeps_parent_active(projects, qdrant, monkeypatch):
    a, _ = projects
    _seed(a, qdrant, monkeypatch)
    monkeypatch.setattr(indexing, "gate_promotion", lambda *a_, **k: {"passed": False})
    _write(a, "edit.md", "# Edit\n\nEDIT2MARK BETA\n")

    stats = indexing.incremental_index(qdrant, Embed(), project=a)

    assert stats["delta_mode"] == "cow" and stats["promoted"] is False
    assert artifacts.current_version(project=a) == "v1"
    assert versions._read_alias_target(qdrant, a.collection_name) == a.collection_name + "__v1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_cow_delta.py -v`
Expected: i nuovi test FALLISCONO, con `KeyError: 'delta_mode'` oppure `AttributeError: ... 'DELTA_MODE'`; i due test del Task 1 restano PASS.

- [ ] **Step 3: Config**

In `rag/core/config.py`, subito dopo la riga `INDEX_MODE = ...`:

```python
# Delta dei progetti a snapshot immutabili: "cow" copia dal padre i punti invariati e
# ricalcola solo i sorgenti cambiati; "rebuild" forza il full rebuild (via d'uscita).
DELTA_MODE = _env_choice("VIBECRAFT_DELTA_MODE", "cow", {"cow", "rebuild"})
```

In `rag/core/indexing.py` aggiungi `DELTA_MODE,` all'import `from core.config import (...)` (ordine alfabetico, dopo `CODE_EXCLUDED_DIRS,`/`COLLECTION_NAME,` e prima di `DENSE_DIM,`).

- [ ] **Step 4: Implementa `_cow_delta_index`**

In `rag/core/indexing.py`, subito prima di `incremental_index`:

```python
class _CowUnavailable(Exception):
    """Precondizione del delta copy-on-write mancante: il chiamante ripiega sul full
    rebuild. Sollevata solo PRIMA di qualunque scrittura (Qdrant, staging, versioni)."""


def _cow_delta_index(qdrant: QdrantClient, embed_model, emit, plan: IndexPlan,
                     current: dict[str, str], manifest, code_delta, current_code: dict[str, str],
                     timings: dict, project: ProjectContext) -> dict:
    """Delta copy-on-write di un progetto a snapshot immutabili: collection candidata
    nuova con i punti invariati copiati dal padre, poi lo stesso motore delta del ramo
    legacy (apply_incremental_indexing) puntato sulla candidata, infine eval-gate e
    promozione come il full rebuild. Il padre non viene mai scritto: rollback intatto."""
    if DELTA_MODE != "cow":
        raise _CowUnavailable(f"VIBECRAFT_DELTA_MODE={DELTA_MODE}")
    if not isinstance(manifest, dict):
        raise _CowUnavailable("manifest della versione attiva assente")
    if manifest.get("immutable") is not True:
        raise _CowUnavailable("versione attiva non immutabile")
    if manifest.get("embedding_model") != EMBEDDING_MODEL:
        raise _CowUnavailable(
            f"modello di embedding cambiato ({manifest.get('embedding_model')} → {EMBEDDING_MODEL})")
    parent_version = artifact_module.current_version(project=project)
    parent_collection = manifest.get("qdrant_collection")
    if parent_version is None or parent_collection != qdrant_collection_name(parent_version, project=project):
        raise _CowUnavailable(f"collection del padre non dedicata: {parent_collection!r}")
    if not _qdrant_collection_exists(qdrant, parent_collection):
        raise _CowUnavailable(f"collection del padre '{parent_collection}' assente su Qdrant")

    started = time.perf_counter()
    arts = load_artifacts(project=project)
    timings["load"] = time.perf_counter() - started
    try:
        if arts.version != parent_version:
            raise ValueError(f"artefatti caricati da {arts.version}, attesa {parent_version}")
        parent_store, parent_hashes = _attested_parent_colbert(arts, manifest, project)
    except (RuntimeError, ValueError) as exc:
        if isinstance(arts.colbert_store, ColbertStore):
            arts.colbert_store.close()
        raise _CowUnavailable(f"artefatti del padre non riusabili: {exc}") from exc

    graph: nx.DiGraph = arts.graph if arts.graph is not None else nx.DiGraph()
    version = _new_version_name(project=project)
    candidate = qdrant_collection_name(version, project=project)
    code_added, code_removed, code_modified = code_delta
    writer = None
    try:
        if embed_model is None:
            started = time.perf_counter()
            emit(f"Caricamento modello embedding: {EMBEDDING_MODEL} ...")
            embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)
            timings["init_model"] += time.perf_counter() - started
        started = time.perf_counter()
        if _qdrant_collection_exists(qdrant, candidate):
            raise RuntimeError(f"collection candidata '{candidate}' già esistente: mai riscritta")
        _ensure_collection(qdrant, recreate=False, collection_name=candidate)
        copied = _clone_points(qdrant, parent_collection, candidate, exclude_doc_ids=plan.to_delete())
        timings["qdrant"] += time.perf_counter() - started
        emit(f"📋 Copy-on-write da {parent_version}: {copied} punti copiati in '{candidate}'. "
             f"Documenti: {len(plan.new)} nuovi, {len(plan.modified)} modificati, "
             f"{len(plan.deleted)} cancellati. Codice: +{len(code_added)} ~{len(code_modified)} "
             f"-{len(code_removed)}.")
        writer = ColbertWriter(project.database_dir / ".colbert-staging" / version / "colbert", None,
                               parent=parent_store, verified_parent_hashes=parent_hashes)
        stats = apply_incremental_indexing(
            plan, project.docs_dir, qdrant, embed_model, graph, arts.colbert_store, arts.chunks_store,
            emit=emit, dense_store=arts.dense_store, code_store=arts.code_store,
            code_delta=(code_added, code_removed, code_modified), code_dir=project.code_dir,
            phase_timings=timings, colbert_writer=writer, project=project, collection_name=candidate,
        )
        started = time.perf_counter()
        version = save_artifacts(graph, writer, arts.chunks_store, arts.dense_store, arts.code_store,
                                 version=version, project=project)
    finally:
        if parent_store is not None:
            parent_store.close()
        if writer is not None and writer.root.exists():
            shutil.rmtree(writer.root)
        if writer is not None and writer.root.parent.exists() and not any(writer.root.parent.iterdir()):
            writer.root.parent.rmdir()
    doc_hashes, code_hashes = _delta_manifest_hashes(manifest, plan, current, code_delta, current_code)
    write_index_manifest(len(arts.chunks_store), graph.number_of_nodes(), graph.number_of_edges(),
                         version=version, qdrant_collection=candidate,
                         doc_hashes=doc_hashes, code_hashes=code_hashes,
                         colbert_new_files=writer.new_files, immutable=True, project=project)
    timings["save_hash"] += time.perf_counter() - started
    gate = _gate_and_publish(qdrant, embed_model, version, candidate, graph, arts.chunks_store,
                             alias_name=project.collection_name, emit=emit, timings=timings,
                             project=project)
    stats.update({"noop": False, "version": version, "delta_mode": "cow",
                  "copied_points": copied, "promoted": bool(gate.get("passed")),
                  "colbert_io_bytes": dict(writer.stats), "phase_timings_seconds": timings})
    return stats
```

Nota per l'implementatore: se un'eccezione nasce dopo `_ensure_collection`, la candidata resta orfana su Qdrant. È lo stesso comportamento del full rebuild: la rimuove `gc_orphaned_qdrant_collections` alla prossima promozione riuscita.

- [ ] **Step 5: Collega il ramo non-legacy**

In `incremental_index` sostituisci il blocco che inizia con `if project is not None and not project.legacy:` (commento `ponytail`, log «Snapshot immutabile…», chiamata a `build_graph_and_index` e relativo `return`) con:

```python
    if project is not None and not project.legacy:
        if qdrant is None:
            qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        try:
            try:
                return _cow_delta_index(qdrant, embed_model, _log, plan, current, manifest,
                                        (code_added, code_removed, code_modified), current_code,
                                        timings, project)
            except _CowUnavailable as exc:
                fallback = str(exc)
            _log(f"Snapshot immutabile: ricostruzione completa dei sorgenti ({fallback}).")
            collector = {}
            version = build_graph_and_index(qdrant, embed_model, emit, collector=collector, project=project)
            collector["phase_timings_seconds"]["init_model"] += timings["init_model"]
            counts = collector["counts"]
            return {"noop": False, "version": version, "delta_mode": "rebuild",
                    "fallback_reason": fallback, "reindexed_docs": counts["docs_added"],
                    "deleted_docs": len(plan.deleted), "upserted_chunks": counts["chunks_indexed"],
                    "planned": plan.as_dict(), **collector}
        finally:
            if own_qdrant:
                qdrant.close()
```

Aggiorna l'ultimo paragrafo del docstring di `incremental_index`:

```
    I progetti ordinari pubblicano snapshot immutabili: dopo il controllo no-op il delta
    è copy-on-write (_cow_delta_index): collection nuova con i punti invariati del padre,
    ri-embedding dei soli sorgenti cambiati, stesso eval-gate del full. Se il padre non
    è riusabile (vedi _CowUnavailable) si ripiega sul full rebuild, con il motivo in
    `fallback_reason`.
```

- [ ] **Step 6: Run the new tests**

Run: `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_cow_delta.py -v`
Expected: tutti PASS (variante memory).

Se `test_cow_falls_back_to_rebuild[parent_collection]` fallisce perché `qdrant.delete_collection` lascia un alias pendente che fa fallire il controllo di occupazione di `build_graph_and_index`, non aggirare il controllo: rimuovi l'alias nel test con `qdrant.update_collection_aliases(...)` (stessa forma usata in `core/qdrant_versions.py::_swap_alias`) prima del delta, e annotalo nel test.

- [ ] **Step 7: Run the related suites**

Run: `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_project_indexing.py tests/test_incremental_indexing.py tests/test_index_timings.py tests/test_project_tools.py tests/test_project_workflows.py tests/test_intake_staging.py tests/test_project_import.py tests/test_reindex.py -q`
Expected: PASS. Due test esistenti devono passare **senza modifiche**, perché fissano gli invarianti dell'immutabilità: `test_build_delta_rollback_same_names_and_versions` e `test_ordinary_delta_keeps_pinned_vectors_and_rollback_restores_query`. Se un altro test asserisce la semantica "delta = rebuild completo" (per esempio conteggi pari a tutti i documenti), aggiornalo alla nuova semantica e spiega il cambio nel messaggio di commit.

- [ ] **Step 8: Commit**

```bash
git add rag/core/config.py rag/core/indexing.py rag/tests/test_cow_delta.py
git commit -m "feat: copy-on-write deltas for immutable project indexes"
```

---

### Task 4: Documentazione e verifica su un progetto reale

**Files:**
- Modify: `README.md` (riga ~115 e ~445), `rag/README.md` (tabella variabili, riga ~1074)

- [ ] **Step 1: README di root**

Sostituisci (riga ~115):

```
writer/CLI. Per progetti ordinari un delta non vuoto usa oggi un full rebuild:
il costo embedding riguarda l'intero corpus; un delta noop non ricostruisce.
```

con:

```
writer/CLI. Per progetti ordinari un delta non vuoto pubblica una versione
copy-on-write: collection nuova con i punti invariati del padre e ri-embedding dei
soli documenti e file di codice cambiati. Se il padre non è riusabile si ripiega sul
full rebuild (motivo in `fallback_reason` del job); un delta noop non scrive nulla.
```

e (riga ~445) `In tutti i progetti il delta non vuoto passa dal rebuild e dal relativo gate.` con `In tutti i progetti il delta non vuoto, copy-on-write o rebuild, passa dall'eval gate prima della promozione.`

- [ ] **Step 2: Tabella variabili in `rag/README.md`**

Dopo la riga `| VIBECRAFT_INDEX_MODE | ...`:

```
| `VIBECRAFT_DELTA_MODE` | `cow` | Delta dei progetti a snapshot immutabili: `cow` (copy-on-write) oppure `rebuild` (full rebuild a ogni delta) |
```

- [ ] **Step 3: CI completa**

Run (da `rag/`): `bash scripts/ci.sh`
Expected: ruff pulito, pytest tutto verde (skip solo per Qdrant server/GPU assenti, elencati da `-rs`).

- [ ] **Step 4: Verifica dal vivo (manuale, con l'utente)**

Ricorda: riavviare il server prima del test, altrimenti il job usa il codice vecchio. Sul progetto SviluppoUrgenteSandro (3 documenti): modifica un documento, premi «Aggiorna indice», poi leggi il job con `GET /api/reindex/{job_id}`. Atteso: `result.delta_mode == "cow"`, `copied_points > 0`, `reindexed_docs == 1`, `promoted == true`. Non avviare reindex sul corpus SGD_FE senza l'accordo dell'utente: su CPU può durare ore se ripiega sul rebuild.

- [ ] **Step 5: Commit**

```bash
git add README.md rag/README.md
git commit -m "docs: describe copy-on-write deltas and VIBECRAFT_DELTA_MODE"
```

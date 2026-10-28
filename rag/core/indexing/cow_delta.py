"""Indicizzazione incrementale e delta copy-on-write (COW).

Estratto da core/indexing.py (R5): IndexPlan, apply_incremental_indexing,
_cow_delta_index, incremental_index. Nessuna modifica di comportamento."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.projects import ProjectContext

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import numpy as np
from FlagEmbedding import BGEM3FlagModel
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    PointStruct,
)

from code_index import (
    add_symbol_nodes,
    collect_code_symbols,
    embed_symbols,
    link_symbols,
    referenced_entity_tokens,
)
from core import artifacts as artifact_module
from core.artifacts import (
    _new_version_name,
    _read_manifest,
    artifact_dir,
    immutable_index_active,
    load_artifacts,
    promote_version,
    save_artifacts,
    sha256_file,
)
from core.chunking import chunk_markdown, read_document
from core.colbert_store import ColbertStore, ColbertWriter
from core.config import (
    CODE_DIR,
    COLLECTION_NAME,
    DELTA_MODE,
    DOCS_DIR,
    EMBEDDING_MODEL,
    PROJECT_ROOT,
    QDRANT_API_KEY,
    QDRANT_URL,
    cow_encode_batch_from_env,
    qdrant_upsert_batch_from_env,
)
from core.qdrant_versions import (
    _qdrant_collection_exists,
    _read_alias_target,
    qdrant_collection_name,
    repair_qdrant_alias,
)

from .common import (
    _code_hashes,
    _colbert_token_count,
    _dense_map,
    _diff_hashes,
    _encode_chunks_to_points,
    _ensure_collection,
    _new_phase_timings,
    docs_hashes,
    write_index_manifest,
)
from .full import _gate_and_publish, build_graph_and_index
from .graph_build import (
    _add_doc_to_graph,
    _add_section_nodes,
    _prune_unsupported_entities,
    _remove_doc_nodes_from_graph,
    _resolve_authority_aliases,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Indicizzazione incrementale (delta): planning deterministico ↔ esecuzione
# ---------------------------------------------------------------------------
@dataclass
class IndexPlan:
    """Piano deterministico del delta di indicizzazione rispetto al manifest.

    - unchanged: doc invariati (hash identico) → SALTATI
    - new:       doc mai visti → da indicizzare
    - modified:  doc con hash cambiato → chunk vecchi da rimuovere + ri-embed
    - deleted:   doc spariti da docs/ → chunk da rimuovere da Qdrant/sidecar
    """
    unchanged: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    def to_index(self) -> list[str]:
        """Documenti da (ri)vettorializzare: nuovi + modificati."""
        return list(self.new) + list(self.modified)

    def to_delete(self) -> list[str]:
        """Documenti i cui chunk vanno purgati da Qdrant/sidecar: modificati + cancellati.
        (Un doc modificato va prima ripulito dei chunk vecchi, poi re-indicizzato.)"""
        return list(self.modified) + list(self.deleted)

    @property
    def is_noop(self) -> bool:
        """True se non c'è nulla da fare: nessun nuovo/modificato/cancellato."""
        return not (self.new or self.modified or self.deleted)

    def as_dict(self) -> dict:
        return {"unchanged": self.unchanged, "new": self.new, "modified": self.modified, "deleted": self.deleted}


def plan_incremental_indexing(current_hashes: dict[str, str], manifest: dict | None) -> IndexPlan:
    """Funzione PURA e deterministica: dato lo stato corrente di docs/ (hash) e il manifest
    precedente (o None se assente/corrotto), produce il piano del delta.

    Manifest assente/corrotto/senza doc_hashes ⇒ tutti i documenti risultano 'new'
    (equivale a un full rebuild), comportamento sicuro e idempotente."""
    old = manifest.get("doc_hashes", {}) if isinstance(manifest, dict) else {}
    if not isinstance(old, dict):
        old = {}
    added, removed, modified, unchanged = _diff_hashes(old, current_hashes)
    return IndexPlan(unchanged=unchanged, new=added, modified=modified, deleted=removed)


def _partition_changed_paths(changed_paths: list[str], project: ProjectContext | None = None) -> tuple[set[str], set[str]]:
    """Mappa i path repo-relative (es. da un webhook GitLab, relativi alla root del repo)
    negli insiemi dei path relativi a docs/ e a code/. I file fuori da questi due alberi
    (config, CI, ecc.) vengono ignorati: non fanno parte dell'indice. Restituisce
    (docs_rel, code_rel), pronti a filtrare il piano del delta e il delta del codice."""
    docs_dir = project.docs_dir if project is not None else DOCS_DIR
    code_dir = project.code_dir if project is not None else CODE_DIR
    root = project.root if project is not None else PROJECT_ROOT
    docs_prefix = docs_dir.relative_to(root).as_posix().rstrip("/") + "/"
    code_prefix = code_dir.relative_to(root).as_posix().rstrip("/") + "/"
    docs_rel: set[str] = set()
    code_rel: set[str] = set()
    for raw in changed_paths:
        posix = str(raw).replace("\\", "/").lstrip("./")
        if posix.startswith(docs_prefix):
            docs_rel.add(posix[len(docs_prefix):])
        elif posix.startswith(code_prefix):
            code_rel.add(posix[len(code_prefix):])
    return docs_rel, code_rel


def _restrict_plan(plan: IndexPlan, allowed: set[str]) -> IndexPlan:
    """Restringe un piano del delta ai soli documenti in `allowed` (path relativi a docs/).
    È un SOTTOINSIEME sicuro del piano completo: si limita il lavoro ai path segnalati dal
    webhook, senza mai indicizzare qualcosa che il diff hash non avrebbe indicizzato. Ciò
    che resta fuori verrà comunque riallineato dal check di coerenza notturno + full rebuild."""
    return IndexPlan(
        unchanged=plan.unchanged,
        new=[p for p in plan.new if p in allowed],
        modified=[p for p in plan.modified if p in allowed],
        deleted=[p for p in plan.deleted if p in allowed],
    )


def _delete_doc_chunks(qdrant: QdrantClient, doc_ids: list[str],
                       collection_name: str = COLLECTION_NAME) -> None:
    """Rimuove da Qdrant TUTTI i punti i cui payload.doc_id è tra quelli indicati,
    con un'unica delete-by-filter (MatchAny). Nessuna dipendenza dall'id del punto.

    `collection_name` (opzionale, default COLLECTION_NAME): vedi _ensure_collection."""
    if not doc_ids:
        return
    qdrant.delete(
        collection_name=collection_name,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="doc_id", match=MatchAny(any=list(doc_ids)))])
        ),
    )


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


def _apply_code_delta(
    graph: nx.DiGraph,
    code_dir: Path,
    code_store: dict,
    embed_model,
    added: list[str],
    removed: list[str],
    modified: list[str],
    emit,
) -> set[str]:
    """Applica il delta sui file di codice: rimuove i nodi/entry dei simboli dei file
    cancellati o modificati (la loro vecchia versione), poi estrae, aggiunge e vettorializza
    i simboli dei file nuovi/modificati. NON calcola gli archi IMPLEMENTS/REFERENCES: quelli
    li (ri)stende `link_symbols` sul solo insieme toccato. Restituisce gli id dei simboli
    toccati (nuovi/modificati), che vanno rilinkati."""
    gone_files = set(removed) | set(modified)
    if gone_files:
        stale_ids = [sid for sid, meta in code_store.items() if meta.get("file") in gone_files]
        for sid in stale_ids:
            code_store.pop(sid, None)
            if sid in graph:
                graph.remove_node(sid)  # cade anche ogni IMPLEMENTS/REFERENCES uscente

    touched: set[str] = set()
    fresh_files = set(added) | set(modified)
    new_syms: list[dict] = []
    for sym in collect_code_symbols(code_dir):
        if sym["file"] in fresh_files:
            new_syms.append(sym)
    if new_syms:
        add_symbol_nodes(graph, new_syms)
        sym_dense = embed_symbols(embed_model, new_syms)
        for i, sym in enumerate(new_syms):
            code_store[sym["id"]] = {
                "name": sym["name"], "kind": sym["kind"], "file": sym["file"],
                "dev_type": sym["dev_type"], "text": sym["text"],
                "deps": sym.get("deps", []),
                "refs": sym.get("refs", []),
                "links": sym.get("links", []),
                "dense": sym_dense[i].astype("float16"),
            }
            touched.add(sym["id"])
    if gone_files or new_syms:
        _log = emit or logger.info
        _log(f"🧩 Codice: {len(removed)} file rimossi, {len(added)} nuovi, {len(modified)} modificati "
             f"→ {len(touched)} simboli (ri)estratti.")
    return touched


def _sorted_chunk_ids(dense_store: dict, chunks_store: dict) -> list[str]:
    """Chunk-documento validi (presenti in entrambi i sidecar) in ORDINE DETERMINISTICO
    (per chunk_id, che incorpora doc + indice zero-paddato): riproduce l'ordine in cui il
    full rebuild presenta i chunk a link_symbols, così l'argmax e i tie-break coincidono."""
    return sorted(cid for cid in dense_store if cid in chunks_store)


def _relink_touched_symbols(graph: nx.DiGraph, code_store: dict, chunks_store: dict,
                            dense_store: dict, touched_ids: set[str]) -> int:
    """Ricalcola IMPLEMENTS/REFERENCES per i soli simboli in `touched_ids`, usando i vettori
    densi già persistiti (nessun re-embed): i simboli dal code_store, i chunk-documento dal
    dense_store. Aggiorna nel code_store lo stato dell'argmax (best/second/win) dei simboli
    rilinkati, così il prossimo delta parte da valori freschi. Restituisce il numero di
    archi IMPLEMENTS creati."""
    ids = [sid for sid in touched_ids if sid in graph and sid in code_store]
    if not ids:
        return 0
    syms = [{"id": sid, "text": code_store[sid]["text"],
             "deps": code_store[sid].get("deps", []),
             "refs": code_store[sid].get("refs", []),
             "links": code_store[sid].get("links", [])} for sid in ids]
    sym_dense = [code_store[sid]["dense"] for sid in ids]

    chunk_ids = _sorted_chunk_ids(dense_store, chunks_store)
    chunk_dense = [dense_store[cid] for cid in chunk_ids]
    chunk_parent = [chunks_store[cid]["doc_id"] for cid in chunk_ids]
    scores: dict = {}
    n_impl = link_symbols(graph, syms, sym_dense, chunk_dense, chunk_parent,
                          chunk_ids=chunk_ids, scores_out=scores)
    for sid, sc in scores.items():
        code_store[sid].update(sc)
    return n_impl


def _entity_nodes(graph: nx.DiGraph) -> set[str]:
    """Insieme degli id dei nodi-entità del grafo (quelli citabili dal codice via REFERENCES)."""
    return {n for n, a in graph.nodes(data=True) if a.get("type") == "entity"}


def _symbols_with_stale_argmax(code_store: dict, dead_docs: set[str]) -> set[str]:
    """Simboli il cui chunk-documento VINCENTE apparteneva a un documento rimosso o
    modificato (`dead_docs` = modificati + cancellati): il loro vincitore è sparito o è
    cambiato, quindi l'argmax IMPLEMENTS va ricalcolato. Gli altri simboli conservano il
    loro vincitore intatto — per costruzione l'argmax non può essersi spostato lì."""
    if not dead_docs:
        return set()
    return {sid for sid, meta in code_store.items() if meta.get("win_doc_id") in dead_docs}


def _symbols_beaten_by_new_chunks(code_store: dict, dense_store: dict,
                                  new_chunk_ids: list[str], eps: float = 1e-4) -> set[str]:
    """Simboli per cui un chunk NUOVO/RI-EMBEDDATO raggiunge una similarità >= al loro
    best_score corrente: solo lì un nuovo chunk può diventare (o pareggiare) l'argmax.
    Confronto vettoriale in blocco (vettori fp16 già in memoria), nessun re-embed.

    Si tocca anche a parità (entro `eps`) per non divergere dai tie-break del rebuild:
    sovra-approssimare è sempre sicuro (si rilinca qualche simbolo in più), sotto-
    approssimare no."""
    valid_new = [cid for cid in new_chunk_ids if cid in dense_store]
    sids = [sid for sid, meta in code_store.items() if "dense" in meta]
    if not valid_new or not sids:
        return set()
    sym_mat = np.asarray([code_store[sid]["dense"] for sid in sids], dtype=np.float32)
    new_mat = np.asarray([dense_store[cid] for cid in valid_new], dtype=np.float32)
    sym_norm = sym_mat / (np.linalg.norm(sym_mat, axis=1, keepdims=True) + 1e-8)
    new_norm = new_mat / (np.linalg.norm(new_mat, axis=1, keepdims=True) + 1e-8)
    max_new = (sym_norm @ new_norm.T).max(axis=1)  # miglior chunk nuovo per simbolo
    touched: set[str] = set()
    for i, sid in enumerate(sids):
        best = code_store[sid].get("best_score")
        if best is None or float(max_new[i]) >= float(best) - eps:
            touched.add(sid)
    return touched


def _symbols_referencing_entities(code_store: dict, changed_entities: set[str]) -> set[str]:
    """Simboli i cui token-entità nel testo intersecano le entità aggiunte/rimosse: sono i
    soli il cui insieme di archi REFERENCES verso le entità può cambiare. (Gli archi verso
    entità potate cadono già con la rimozione del nodo; qui si intercettano soprattutto le
    entità NUOVE, che vanno collegate ai simboli che le citano.)"""
    if not changed_entities:
        return set()
    return {sid for sid, meta in code_store.items()
            if referenced_entity_tokens(meta.get("text", "")) & changed_entities}


def apply_incremental_indexing(
    plan: IndexPlan,
    docs_dir: Path | None,
    qdrant: QdrantClient,
    embed_model,
    graph: nx.DiGraph,
    colbert_store: dict,
    chunks_store: dict,
    emit=None,
    dense_store: dict | None = None,
    code_store: dict | None = None,
    code_delta: tuple[list[str], list[str], list[str]] | None = None,
    code_dir: Path | None = None,
    phase_timings: dict[str, float] | None = None,
    colbert_writer: ColbertWriter | None = None,
    project: ProjectContext | None = None,
    collection_name: str | None = None,
) -> dict:
    """Esegue il piano del delta sugli oggetti passati (Qdrant + grafo + sidecar), mutandoli
    in-place. Con colbert_writer persiste i vettori per documento; il chiamante
    (incremental_index) gestisce il modello, gli altri artefatti e la pubblicazione.

    Passi (idempotenti):
      1. purge dei chunk dei documenti modificati+cancellati da Qdrant (delete-by-filter),
         dai sidecar (colbert/chunks/dense) e dei relativi nodi-documento dal grafo;
      2. (ri)vettorializzazione dei documenti nuovi+modificati e upsert con id deterministici,
         con re-inserimento dei nodi-documento nel grafo;
      3. delta sui file di codice (simboli aggiunti/rimossi/modificati);
      4. ricalcolo mirato degli archi spec<->codice (IMPLEMENTS/REFERENCES) per i SOLI nodi
         che possono essere cambiati: i simboli nuovi/modificati, quelli il cui chunk
         vincente stava in un doc rimosso/modificato, quelli battuti da un chunk nuovo, e
         quelli che citano un'entità aggiunta/rimossa. Gli altri hanno argmax invariato per
         costruzione e non si toccano. Infine potatura delle entità rimaste orfane. Il
         risultato è deterministicamente equivalente al full rebuild (lo prova
         check_graph_consistency), ma il costo è proporzionale al delta, non all'indice.

    `dense_store`/`code_store`/`code_delta`/`code_dir` sono opzionali: se assenti la funzione
    si comporta come prima (nessun ricalcolo dei code-link), preservando i chiamanti legacy.

    `collection_name`: collection su cui scrivere; default l'alias."""
    alias_name = project.collection_name if project is not None else COLLECTION_NAME
    # Collection FISICA su cui scrivere: la candidata del delta copy-on-write, oppure
    # (default, ramo legacy) l'alias che risolve alla collection del padre.
    target = collection_name or alias_name
    _log = emit or logger.info
    apply_started = time.perf_counter()
    qdrant_seconds = 0.0
    save_seconds = 0.0
    # Snapshot delle entità PRIMA di toccare i documenti: serve a capire, a valle, quali
    # entità sono comparse/sparite e quindi quali simboli hanno REFERENCES da ricalcolare.
    entities_before = _entity_nodes(graph)
    to_delete = plan.to_delete()   # modificati + cancellati
    to_index = plan.to_index()     # nuovi + modificati

    # 1. Purge (Qdrant + sidecar + grafo) dei documenti non più validi nella loro forma attuale
    if to_delete:
        started = time.perf_counter()
        _delete_doc_chunks(qdrant, to_delete, collection_name=target)
        qdrant_seconds += time.perf_counter() - started
        dead_set = set(to_delete)
        dead_chunks = [cid for cid, meta in chunks_store.items() if meta.get("doc_id") in dead_set]
        if colbert_writer is not None:
            for doc_id in to_delete:
                colbert_writer.remove_document(doc_id)
        for cid in dead_chunks:
            if colbert_writer is None:
                colbert_store.pop(cid, None)
            chunks_store.pop(cid, None)
            if dense_store is not None:
                dense_store.pop(cid, None)
        _remove_doc_nodes_from_graph(graph, to_delete)
        _log(f"🗑️  Rimossi i chunk di {len(to_delete)} documenti (modificati/cancellati): {len(dead_chunks)} chunk purgati da Qdrant, sidecar e grafo.")

    # 2. (Ri)indicizzazione dei soli documenti nuovi/modificati
    upserted = 0
    processed_colbert_tokens = 0
    new_chunk_ids: list[str] = []
    if to_index:
        assert docs_dir is not None, "docs_dir richiesto quando ci sono documenti da (ri)indicizzare"
        new_chunks: list[dict] = []
        # R9: con ColbertWriter, batch di chunk da docs distinti (bound =
        # VIBECRAFT_COW_ENCODE_BATCH; default produttivo 12). 0 = una encode()
        # per doc (storico). Un doc con più chunk del bound resta unità sola;
        # non tocca /ask né il full.
        encode_batch = cow_encode_batch_from_env() if colbert_writer is not None else 0
        pending_docs: list[tuple[str, list[dict]]] = []
        pending_chunk_count = 0

        def _persist_encoded_doc(rel_path: str, doc_chunks: list[dict], points, colbert_partial,
                                 chunks_partial, doc_dense) -> None:
            nonlocal upserted, processed_colbert_tokens, qdrant_seconds, save_seconds
            processed_colbert_tokens += _colbert_token_count(colbert_partial)
            started = time.perf_counter()
            upsert_batch = qdrant_upsert_batch_from_env()
            for i in range(0, len(points), upsert_batch):
                qdrant.upsert(collection_name=target, points=points[i:i + upsert_batch])
            qdrant_seconds += time.perf_counter() - started
            save_started = time.perf_counter()
            colbert_writer.add_document(rel_path, colbert_partial)
            save_seconds += time.perf_counter() - save_started
            chunks_store.update(chunks_partial)
            if dense_store is not None:
                dense_store.update(_dense_map(doc_chunks, doc_dense))
            new_chunk_ids.extend(c["chunk_id"] for c in doc_chunks)
            upserted += len(points)

        def _flush_encode_batch() -> None:
            nonlocal pending_docs, pending_chunk_count
            if not pending_docs:
                return
            if len(pending_docs) == 1:
                rel_path, doc_chunks = pending_docs[0]
                points, colbert_partial, chunks_partial, doc_dense = _encode_chunks_to_points(
                    embed_model, doc_chunks)
                _persist_encoded_doc(rel_path, doc_chunks, points, colbert_partial,
                                     chunks_partial, doc_dense)
                del points, colbert_partial, chunks_partial, doc_dense
            else:
                all_chunks: list[dict] = []
                spans: list[tuple[str, int, int]] = []
                for rel_path, doc_chunks in pending_docs:
                    start = len(all_chunks)
                    all_chunks.extend(doc_chunks)
                    spans.append((rel_path, start, len(all_chunks)))
                points, colbert_partial, chunks_partial, dense_vecs = _encode_chunks_to_points(
                    embed_model, all_chunks)
                for rel_path, start, end in spans:
                    doc_chunks = all_chunks[start:end]
                    doc_points = points[start:end]
                    doc_colbert = {c["chunk_id"]: colbert_partial[c["chunk_id"]] for c in doc_chunks}
                    doc_meta = {c["chunk_id"]: chunks_partial[c["chunk_id"]] for c in doc_chunks}
                    doc_dense = dense_vecs[start:end]
                    _persist_encoded_doc(rel_path, doc_chunks, doc_points, doc_colbert,
                                         doc_meta, doc_dense)
                del points, colbert_partial, chunks_partial, dense_vecs, all_chunks
            pending_docs = []
            pending_chunk_count = 0

        for rel_path in to_index:
            fp = docs_dir / rel_path
            if not fp.exists():
                _log(f"  (saltato, file assente: {rel_path})")
                continue
            metadata, body = read_document(fp)
            if not body.strip():
                _log(f"  (saltato, corpo vuoto o loader assente: {rel_path})")
                continue
            _add_doc_to_graph(graph, rel_path, metadata, body)
            doc_chunks = chunk_markdown(rel_path, metadata, body)
            _add_section_nodes(graph, rel_path, doc_chunks, metadata)
            for c in doc_chunks:
                c["metadata"] = metadata
            if colbert_writer is not None and doc_chunks:
                n_chunks = len(doc_chunks)
                if encode_batch <= 0:
                    points, colbert_partial, chunks_partial, doc_dense = _encode_chunks_to_points(
                        embed_model, doc_chunks)
                    _persist_encoded_doc(rel_path, doc_chunks, points, colbert_partial,
                                         chunks_partial, doc_dense)
                    del points, colbert_partial, chunks_partial, doc_dense
                elif n_chunks > encode_batch:
                    # Doc più grande del bound: flush del gruppo, poi unità sola.
                    _flush_encode_batch()
                    points, colbert_partial, chunks_partial, doc_dense = _encode_chunks_to_points(
                        embed_model, doc_chunks)
                    _persist_encoded_doc(rel_path, doc_chunks, points, colbert_partial,
                                         chunks_partial, doc_dense)
                    del points, colbert_partial, chunks_partial, doc_dense
                else:
                    if pending_chunk_count + n_chunks > encode_batch:
                        _flush_encode_batch()
                    pending_docs.append((rel_path, doc_chunks))
                    pending_chunk_count += n_chunks
            else:
                new_chunks.extend(doc_chunks)

        _flush_encode_batch()

        if new_chunks:
            _log(f"\nVettorializzazione incrementale di {len(new_chunks)} chunk (da {len(to_index)} documenti)...")
            points, colbert_partial, chunks_partial, _dense = _encode_chunks_to_points(embed_model, new_chunks)
            processed_colbert_tokens = _colbert_token_count(colbert_partial)
            started = time.perf_counter()
            qdrant.upsert(collection_name=target, points=points)
            qdrant_seconds += time.perf_counter() - started
            colbert_store.update(colbert_partial)
            chunks_store.update(chunks_partial)
            if dense_store is not None:
                dense_store.update(_dense_map(new_chunks, _dense))
            new_chunk_ids = [c["chunk_id"] for c in new_chunks]
            upserted = len(points)
        _log(f"➕ (Ri)indicizzati {len(to_index)} documenti → {upserted} chunk upsertati.")

    # 3-4. Delta del codice + ricalcolo mirato dei code-link (solo se i sidecar sono forniti).
    code_added, code_removed, code_modified = code_delta or ([], [], [])
    implements = 0
    orphans = 0
    if code_store is not None and dense_store is not None:
        touched: set[str] = set()
        if code_dir is not None and (code_added or code_removed or code_modified):
            touched |= _apply_code_delta(
                graph, code_dir, code_store, embed_model,
                code_added, code_removed, code_modified, _log,
            )
        relink_started = time.perf_counter()
        # Selezione MIRATA dei simboli il cui argmax IMPLEMENTS può essere cambiato per via
        # del delta documenti — invece di rilincare tutto quando i documenti cambiano.
        # L'argmax è una proprietà globale, ma può spostarsi solo in due casi:
        #   (a) il chunk vincente del simbolo apparteneva a un doc rimosso/modificato → il
        #       vincitore è sparito, va ricalcolato;
        #   (b) un chunk NUOVO/ri-embeddato raggiunge una similarità >= al best_score del
        #       simbolo → il nuovo chunk può diventare il vincitore.
        # Gli altri simboli hanno vincitore intatto e nessun nuovo concorrente più forte:
        # per costruzione l'argmax non si muove, quindi NON si toccano.
        touched |= _symbols_with_stale_argmax(code_store, set(to_delete))
        touched |= _symbols_beaten_by_new_chunks(code_store, dense_store, new_chunk_ids)
        # Prima si potano le entità che nessun documento cita più (rimuove anche i REFERENCES
        # stale del codice verso di esse), POI si ricalcolano i link: così REFERENCES viene
        # ricostruito sull'insieme di entità valido, identico a quello del full rebuild.
        orphans = _prune_unsupported_entities(graph)
        # REFERENCES codice->entità: se l'insieme delle entità citabili è cambiato, i soli
        # simboli i cui token intersecano le entità aggiunte/rimosse possono avere archi
        # diversi (le entità potate hanno già perso gli archi con la rimozione del nodo).
        changed_entities = entities_before ^ _entity_nodes(graph)
        touched |= _symbols_referencing_entities(code_store, changed_entities)
        implements = _relink_touched_symbols(graph, code_store, chunks_store, dense_store, touched)
        if touched or orphans:
            _log(f"🔗 Code-link ricalcolati per {len(touched)} simboli toccati → {implements} IMPLEMENTS; "
                 f"{orphans} entità orfane potate.")

    # Riconnette i doc->doc dalle relazioni di autorità: non distruttivo e idempotente, così
    # il grafo incrementale resta deterministicamente equivalente al full rebuild (che lo fa
    # in _build_full_state). Va eseguito su TUTTO il grafo dopo aver applicato il delta.
    else:
        relink_started = time.perf_counter()
    _resolve_authority_aliases(graph)
    relink_seconds = time.perf_counter() - relink_started
    if phase_timings is not None:
        phase_timings["qdrant"] += qdrant_seconds
        phase_timings["relink"] += relink_seconds
        phase_timings["save_hash"] += save_seconds
        phase_timings["parsing_embedding"] += max(
            0.0, time.perf_counter() - apply_started - qdrant_seconds - relink_seconds - save_seconds,
        )

    return {
        "planned": plan.as_dict(),
        "reindexed_docs": len(to_index),
        "deleted_docs": len(plan.deleted),
        "upserted_chunks": upserted,
        "code_added": len(code_added),
        "code_removed": len(code_removed),
        "code_modified": len(code_modified),
        "implements_edges": implements,
        "pruned_entities": orphans,
        "counts": {
            "docs_added": len(plan.new), "docs_modified": len(plan.modified),
            "docs_removed": len(plan.deleted), "code_added": len(code_added),
            "code_modified": len(code_modified), "code_removed": len(code_removed),
            "chunks_processed": upserted, "chunks_indexed": len(chunks_store),
            "colbert_tokens_processed": processed_colbert_tokens,
            "colbert_tokens_indexed": (colbert_writer.token_count if colbert_writer is not None
                                        else _colbert_token_count(colbert_store)),
            "code_tokens_processed": None,
            "code_tokens_unavailable_reason": "embedding output does not expose code token counts",
        },
    }


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

    graph: nx.DiGraph = nx.DiGraph()
    version = _new_version_name(project=project)
    candidate = qdrant_collection_name(version, project=project)
    started = time.perf_counter()
    arts = None
    try:
        # Tutti gli artefatti sono richiesti: un grafo assente non diventa un grafo vuoto
        # pubblicato nel figlio, un file mancante/corrotto ripiega PRIMA di ogni scrittura.
        arts = load_artifacts(("graph", "chunks", "dense", "code"), project=project)
        timings["load"] = time.perf_counter() - started
        if arts.version != parent_version:
            raise ValueError(f"artefatti caricati da {arts.version}, attesa {parent_version}")
        parent_store, parent_hashes = _attested_parent_colbert(arts, manifest, project)
        if parent_store is None and "colbert/index.json" in (manifest.get("artifact_hashes") or {}):
            raise ValueError("ColBERT attestato dal manifest ma assente nel padre")
        graph = arts.graph
    except (RuntimeError, ValueError, OSError) as exc:
        if arts is not None and isinstance(arts.colbert_store, ColbertStore):
            arts.colbert_store.close()
        raise _CowUnavailable(f"artefatti del padre non riusabili: {exc}") from exc

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


def incremental_index(qdrant: QdrantClient | None = None, embed_model=None, emit=None,
                      changed_paths: list[str] | None = None, project: ProjectContext | None = None,
                      embed_model_factory=None) -> dict:
    """Orchestratore dell'indicizzazione incrementale: manifest → piano → esecuzione → persistenza.

    - Salta del tutto i documenti invariati (nessun re-embed).
    - Se non c'è nulla da fare (e il manifest esiste) è un no-op: nessuna scrittura su
      Qdrant, sidecar o manifest → idempotente sulle run ripetute.
    - Manifest assente/corrotto ⇒ il piano marca tutto come 'new' (equivale al full rebuild),
      ma senza droppare la collection: i punti vengono upsertati con id deterministici.

    `changed_paths` (opzionale, path relativi alla root del repo — es. estratti da un webhook
    GitLab push/merge) restringe il delta ai soli file segnalati: si evita di ri-hashare/ri-
    embeddare tutto quando si sa già cosa è cambiato. È solo un limite superiore al lavoro —
    il diff hash resta la fonte di verità — quindi non può indicizzare nulla che un delta
    completo non avrebbe toccato. Se None, si considera l'intero docs/ + code/ come sempre.

    I progetti ordinari pubblicano snapshot immutabili: dopo il controllo no-op il delta
    è copy-on-write (_cow_delta_index): collection nuova con i punti invariati del padre,
    ri-embedding dei soli sorgenti cambiati, stesso eval-gate del full. Se il padre non
    è riusabile (vedi _CowUnavailable) si ripiega sul full rebuild, con il motivo in
    `fallback_reason`."""
    database_dir = project.database_dir if project is not None else artifact_module.DATABASE_DIR
    alias_name = project.collection_name if project is not None else COLLECTION_NAME
    docs_dir = project.docs_dir if project is not None else DOCS_DIR
    code_dir = project.code_dir if project is not None else CODE_DIR
    if immutable_index_active(project=project) and (project is None or project.legacy):
        raise RuntimeError(
            "Indicizzazione incrementale disabilitata per indice immutabile: usare un full rebuild."
        )
    _log = emit or logger.info
    timings = _new_phase_timings()
    own_qdrant = qdrant is None

    started = time.perf_counter()
    current = docs_hashes(project=project)
    manifest = _read_manifest(project=project)
    plan = plan_incremental_indexing(current, manifest)

    # Delta sul codice: gemello del piano documenti, così l'incrementale reagisce anche a
    # nuovi file di codice / modifiche / cancellazioni sotto code/ (non solo a docs/).
    current_code = _code_hashes(project=project)
    timings["scan_hash"] = time.perf_counter() - started
    old_code = manifest.get("code_hashes", {}) if isinstance(manifest, dict) else {}
    code_added, code_removed, code_modified, _uc = _diff_hashes(old_code, current_code)

    # Webhook: restringi piano documenti e delta codice ai soli path segnalati (limita il lavoro).
    if changed_paths is not None:
        docs_rel, code_rel = _partition_changed_paths(changed_paths, project=project)
        plan = _restrict_plan(plan, docs_rel)
        code_added = [p for p in code_added if p in code_rel]
        code_modified = [p for p in code_modified if p in code_rel]
        code_removed = [p for p in code_removed if p in code_rel]
        _log(f"🎯 Delta ristretto ai path del webhook: {len(docs_rel)} doc, {len(code_rel)} file di codice segnalati.")

    code_changed = bool(code_added or code_removed or code_modified)

    if manifest is not None and plan.is_noop and not code_changed:
        _log("✅ Nessun cambiamento in docs/ o code/: indice già aggiornato (no-op, nessuna scrittura).")
        return {"noop": True, "planned": plan.as_dict(), "reindexed_docs": 0,
                "deleted_docs": 0, "upserted_chunks": 0,
                "phase_timings_seconds": timings,
                "counts": {"docs_added": 0, "docs_modified": 0, "docs_removed": 0,
                           "code_added": 0, "code_modified": 0, "code_removed": 0,
                           "chunks_processed": 0, "chunks_indexed": None,
                           "colbert_tokens_processed": 0, "colbert_tokens_indexed": None,
                           "code_tokens_processed": None,
                           "code_tokens_unavailable_reason": "embedding output does not expose code token counts"}}

    if embed_model is None and embed_model_factory is not None and (
            (project is not None and not project.legacy) or plan.to_index() or code_added or code_modified):
        started = time.perf_counter()
        embed_model = embed_model_factory()
        timings["init_model"] = time.perf_counter() - started

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
                    "fallback_reason": fallback,
                    "promoted": artifact_module.current_version(project=project) == version,
                    "reindexed_docs": counts["docs_added"],
                    "deleted_docs": len(plan.deleted), "upserted_chunks": counts["chunks_indexed"],
                    "planned": plan.as_dict(), **collector}
        finally:
            if own_qdrant:
                qdrant.close()

    _log(f"📋 Piano incrementale: {len(plan.new)} nuovi, {len(plan.modified)} modificati, "
         f"{len(plan.deleted)} cancellati, {len(plan.unchanged)} invariati (saltati). "
         f"Codice: +{len(code_added)} ~{len(code_modified)} -{len(code_removed)}.")

    # Il modello serve solo se c'è qualcosa da (ri)embeddare: documenti nuovi/modificati
    # oppure file di codice nuovi/modificati. Un run di solo-delete non paga bge-m3.
    if embed_model is None and (plan.to_index() or code_added or code_modified):
        started = time.perf_counter()
        _log(f"Caricamento modello embedding: {EMBEDDING_MODEL} ...")
        embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)
        timings["init_model"] = time.perf_counter() - started
    started = time.perf_counter()
    if qdrant is None:
        qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Lineage blue/green: il manifest figlio erediterà qdrant_collection dal padre
    # (`manifest`, letto a inizio funzione — è ancora quello della versione attiva,
    # perché la promote di questa versione avviene solo DOPO).
    parent_qdrant_collection = manifest.get("qdrant_collection") if isinstance(manifest, dict) else None

    if parent_qdrant_collection is not None:
        # Guardia di lineage: PRIMA di qualunque scrittura (delete/upsert/ensure)
        # l'alias deve puntare alla collection del padre. Questo è un punto writer,
        # quindi la riparazione mirata è consentita: repair_qdrant_alias sposta
        # l'alias sulla collection attesa se esiste, e non tocca nulla altrimenti.
        # Se dopo la riparazione lo stato resta divergente o senza alias, si
        # abortisce: le point-operation sotto passano per l'alias, e scrivere con
        # l'alias fuori lineage upserterebbe/cancellerebbe su una collection che
        # non è quella del padre.
        repair = repair_qdrant_alias(qdrant, emit=_log, project=project)
        if repair["state"] in ("diverging", "missing") and not repair["repaired"]:
            raise RuntimeError(
                f"Alias Qdrant '{alias_name}' in stato '{repair['state']}': attesa la "
                f"collection del padre '{repair['expected']}', target attuale "
                f"'{repair['actual']}', e riparazione impossibile (la collection attesa non "
                f"esiste su Qdrant). Incrementale abortito senza scritture: full rebuild richiesto."
            )
        # La collection fisica del padre deve ESISTERE già: il percorso incrementale
        # non crea MAI una collection mancante della lineage — una create qui
        # produrrebbe una collection vuota "legittimata" dall'alias, mascherando la
        # perdita dei vettori del padre. Post-riparazione l'alias punta a questa
        # collection per costruzione, quindi le point-operation sull'alias sono sicure.
        if not _qdrant_collection_exists(qdrant, parent_qdrant_collection):
            raise RuntimeError(
                f"Collection del padre '{parent_qdrant_collection}' assente su Qdrant: "
                f"l'incrementale non la ricrea mai — full rebuild richiesto."
            )
    elif _read_alias_target(qdrant, alias_name) is None:
        # Bootstrap (nessun manifest padre, o manifest antecedente all'introduzione
        # del campo qdrant_collection) SENZA alias: vero fresh install o layout non
        # ancora migrato — COLLECTION_NAME è la collection fisica storica, creata
        # solo se assente (mai ricreata, i punti sono preservati), esattamente come
        # prima di questo fix. Se invece l'alias esiste GIÀ (manifest legacy con
        # migrazione avvenuta altrove, es. rollback molto indietro), non c'è nulla
        # da assicurare né da guardare: l'alias risolve per costruzione a una
        # collection fisica esistente (stato "legacy" del reconciler, nessun abort).
        _ensure_collection(qdrant, recreate=False, collection_name=alias_name)
    timings["qdrant"] += time.perf_counter() - started

    # Carica lo stato precedente dagli artefatti. Gli artefatti assenti diventano il
    # loro default vuoto.
    started = time.perf_counter()
    arts = load_artifacts(project=project)
    timings["load"] = time.perf_counter() - started
    graph: nx.DiGraph = arts.graph if arts.graph is not None else nx.DiGraph()
    colbert_store: dict = arts.colbert_store
    chunks_store: dict = arts.chunks_store
    dense_store: dict = arts.dense_store
    code_store: dict = arts.code_store

    version = _new_version_name(project=project)
    parent_store, parent_hashes = _attested_parent_colbert(arts, manifest, project)
    writer = None
    try:
        writer = ColbertWriter(database_dir / ".colbert-staging" / version / "colbert", None,
                               parent=parent_store, verified_parent_hashes=parent_hashes)
        stats = apply_incremental_indexing(
            plan, docs_dir, qdrant, embed_model, graph, colbert_store, chunks_store, emit=_log,
            dense_store=dense_store, code_store=code_store,
            code_delta=(code_added, code_removed, code_modified), code_dir=code_dir,
            phase_timings=timings,
            colbert_writer=writer, project=project,
        )
        # Persistenza: nuova versione blue/green; promote segue il manifest.
        started = time.perf_counter()
        version = save_artifacts(graph, writer, chunks_store, dense_store, code_store, version=version, project=project)
    finally:
        if parent_store is not None:
            parent_store.close()
        if writer is not None and writer.root.exists():
            shutil.rmtree(writer.root)
        if writer is not None and writer.root.parent.exists() and not any(writer.root.parent.iterdir()):
            writer.root.parent.rmdir()
    # Lineage blue/green: il manifest figlio eredita `parent_qdrant_collection`
    # (calcolato sopra, prima della guardia di lineage). Bootstrap/fresh install senza
    # manifest padre o senza il campo: None qui, che write_index_manifest risolve nel
    # suo stesso default storico (COLLECTION_NAME). L'incrementale non promuove MAI
    # l'alias su una nuova collection: al più lo RIPARA verso quella del padre
    # (guardia sopra, prima di ogni scrittura), e il manifest ne eredita solo il nome.
    # Il manifest descrive ciò che l'indice CONTIENE, non ciò che c'è su disco: con un delta
    # ristretto (changed_paths — l'approve dell'intake, un webhook) i documenti non elaborati,
    # cancellazioni comprese, conservano la voce precedente e restano visibili come stale.
    # Ricalcolarli da disco li faceva sparire dal manifest lasciandone i punti in Qdrant.
    doc_hashes, code_hashes = _delta_manifest_hashes(
        manifest, plan, current, (code_added, code_removed, code_modified), current_code)
    write_index_manifest(len(chunks_store), graph.number_of_nodes(), graph.number_of_edges(),
                         version=version, qdrant_collection=parent_qdrant_collection,
                         doc_hashes=doc_hashes, code_hashes=code_hashes,
                         colbert_new_files=writer.new_files, project=project)
    timings["save_hash"] += time.perf_counter() - started
    started = time.perf_counter()
    if version:  # None solo con save_artifacts finto nei test
        promote_version(version, project=project)
    timings["promote"] = time.perf_counter() - started
    stats["version"] = version
    stats["colbert_io_bytes"] = dict(writer.stats)
    stats["phase_timings_seconds"] = timings

    _log(f"🧾 Manifest aggiornato: {len(chunks_store)} chunk, {graph.number_of_nodes()} nodi, {graph.number_of_edges()} archi.")
    _log(f"🔁 Versione promossa: CURRENT → {version}.")
    _log("🔗 Code-link spec<->codice ricalcolati per i nodi toccati (nessun full rebuild necessario).")

    if own_qdrant:
        qdrant.close()

    return stats

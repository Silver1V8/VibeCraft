"""Full rebuild dell'indice Graph-RAG: FullState, gate di promozione e build_graph_and_index.

Estratto da core/indexing.py (R5): nessuna modifica di comportamento."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.projects import ProjectContext

import logging
import shutil
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
from FlagEmbedding import BGEM3FlagModel
from qdrant_client import QdrantClient

from code_index import (
    add_symbol_nodes,
    collect_code_symbols,
    embed_symbols,
    link_symbols,
    source_files,
)
from core import artifacts as artifact_module
from core.artifacts import (
    _new_version_name,
    activate_immutable_index,
    immutable_index_active,
    load_artifacts,
    manifest_path,
    promote_version,
    save_artifacts,
)
from core.chunking import chunk_markdown, read_document
from core.colbert_store import ColbertStore, ColbertWriter
from core.config import (
    CODE_DIR,
    COLLECTION_NAME,
    DOC_EXTS,
    DOCS_DIR,
    EMBEDDING_MODEL,
    QDRANT_API_KEY,
    QDRANT_URL,
    qdrant_upsert_batch_from_env,
)
from core.eval_gate import gate_promotion
from core.qdrant_versions import (
    _migrate_legacy_collection_if_needed,
    _read_alias_target,
    _swap_alias,
    gc_orphaned_qdrant_collections,
    qdrant_collection_name,
)
from core.retrieval import restatement_sections

from .common import (
    _colbert_token_count,
    _code_hashes,
    _dense_map,
    _encode_chunks_to_points,
    _ensure_collection,
    _new_phase_timings,
    docs_hashes,
    write_index_manifest,
)
from .graph_build import _add_doc_to_graph, _add_section_nodes, _resolve_authority_aliases

logger = logging.getLogger(__name__)

@dataclass
class FullState:
    """Full-build state. The production path streams ColBERT and points per document;
    the graph-consistency path retains vectors and points for comparison."""
    graph: nx.DiGraph
    points: list = field(default_factory=list)
    colbert_store: Mapping | ColbertWriter = field(default_factory=dict)
    chunks_store: dict = field(default_factory=dict)
    dense_store: dict = field(default_factory=dict)
    code_store: dict = field(default_factory=dict)
    n_docs: int = 0
    point_count: int = 0


def _build_full_state(embed_model, docs_dir: Path, code_dir: Path, emit=None,
                      phase_timings: dict[str, float] | None = None,
                      colbert_writer=None, point_sink=None) -> FullState:
    """Build the graph from source documents. Production passes a per-document
    NPY writer and Qdrant sink; the graph-consistency caller omits both and keeps
    the historical in-memory result."""
    _log = emit or logger.info
    parsing_started = time.perf_counter()
    qdrant_before = phase_timings["qdrant"] if phase_timings is not None else 0.0
    save_seconds = 0.0
    G = nx.DiGraph()
    all_chunks: list[dict] = []
    n_docs = 0
    progressive_chunks: dict = {}
    progressive_dense: dict = {}
    progressive_count = 0

    all_docs = [p for p in source_files(docs_dir) if p.suffix.lower() in DOC_EXTS]
    for filepath_obj in all_docs:
        rel_path = filepath_obj.relative_to(docs_dir).as_posix()
        metadata, body = read_document(filepath_obj)
        if not body.strip():
            _log(f"  (saltato, corpo vuoto o loader assente: {rel_path})")
            continue
        n_entities, typed_edges = _add_doc_to_graph(G, rel_path, metadata, body)
        doc_chunks = chunk_markdown(rel_path, metadata, body)
        _add_section_nodes(G, rel_path, doc_chunks, metadata)
        for c in doc_chunks:
            c["metadata"] = metadata
        all_chunks.extend(doc_chunks)
        if colbert_writer is not None and doc_chunks:
            doc_points, doc_colbert, doc_meta, doc_dense = _encode_chunks_to_points(embed_model, doc_chunks)
            save_started = time.perf_counter()
            colbert_writer.add_document(rel_path, doc_colbert)
            save_seconds += time.perf_counter() - save_started
            progressive_chunks.update(doc_meta)
            progressive_dense.update(_dense_map(doc_chunks, doc_dense))
            progressive_count += len(doc_points)
            if point_sink is not None:
                point_sink(doc_points)
            del doc_points, doc_colbert, doc_meta, doc_dense
        n_docs += 1
        _log(f"  Analizzato: {rel_path} — {n_entities} entità, {len(doc_chunks)} chunk, {typed_edges} relazioni tipizzate")

    points: list = []
    colbert_store: dict = {}
    chunks_store: dict = {}
    dense_store: dict = {}
    if colbert_writer is not None:
        colbert_store = colbert_writer
        chunks_store = progressive_chunks
        dense_store = progressive_dense
    elif all_chunks:
        _log(f"\nVettorializzazione di {len(all_chunks)} chunk (da {n_docs} documenti) con {EMBEDDING_MODEL} (dense + sparse + colbert)...")
        points, colbert_store, chunks_store, dense_vecs = _encode_chunks_to_points(embed_model, all_chunks)
        dense_store = _dense_map(all_chunks, dense_vecs)

    # Fase Codice: nodi dei simboli + archi IMPLEMENTS (chunk-doc più simile) e REFERENCES.
    # Indipendente dalla presenza di documenti: i simboli di codice esistono comunque come
    # nodi (senza IMPLEMENTS finché non c'è uno spazio-documenti a cui agganciarsi), così
    # full rebuild e incrementale restano allineati anche quando docs/ è temporaneamente vuoto.
    if phase_timings is not None:
        phase_timings["save_hash"] += save_seconds
        phase_timings["parsing_embedding"] += max(
            0.0, time.perf_counter() - parsing_started - save_seconds
            - (phase_timings["qdrant"] - qdrant_before))
    code_parsing_started = time.perf_counter()
    code_store: dict = {}
    try:
        code_symbols = collect_code_symbols(code_dir)
        if code_symbols:
            add_symbol_nodes(G, code_symbols)
            sym_dense = embed_symbols(embed_model, code_symbols)
            # Linka usando gli STESSI vettori fp16 che finiscono nei sidecar: così il
            # ricalcolo incrementale (che legge fp16) riproduce esattamente questi archi,
            # e il check di coerenza non segnala falsi positivi da differenza di precisione.
            sym_dense16 = sym_dense.astype("float16") if sym_dense.size else sym_dense
            doc_chunk_ids = [c["chunk_id"] for c in all_chunks if c["chunk_id"] in dense_store]
            doc_dense16 = [dense_store[cid] for cid in doc_chunk_ids]
            doc_parent16 = [chunks_store[cid]["doc_id"] for cid in doc_chunk_ids]
            scores: dict = {}
            if phase_timings is not None:
                phase_timings["parsing_embedding"] += time.perf_counter() - code_parsing_started
            relink_started = time.perf_counter()
            n_impl = link_symbols(G, code_symbols, sym_dense16, doc_dense16, doc_parent16,
                                  chunk_ids=doc_chunk_ids, scores_out=scores)
            if phase_timings is not None:
                phase_timings["relink"] += time.perf_counter() - relink_started
            code_parsing_started = time.perf_counter()
            code_store = {
                s["id"]: {"name": s["name"], "kind": s["kind"], "file": s["file"],
                          "dev_type": s["dev_type"], "text": s["text"],
                          "dense": sym_dense16[i],
                          **scores.get(s["id"], {})}
                for i, s in enumerate(code_symbols)
            }
            _log(f"🧩 Codice indicizzato: {len(code_symbols)} simboli, {n_impl} archi IMPLEMENTS verso i documenti.")
        else:
            _log("🧩 Nessun simbolo di codice trovato sotto code/ (verrà indicizzato quando Claude scriverà il codice).")
    except Exception as e:
        _log(f"⚠️ Indicizzazione del codice saltata: {e}")

    if phase_timings is not None:
        phase_timings["parsing_embedding"] += time.perf_counter() - code_parsing_started

    # Connette i documenti tra loro dalle relazioni di autorità del frontmatter (doc->doc),
    # risolvendo gli alias di versione. Ultimo passo: tutti i nodi-documento sono presenti.
    relink_started = time.perf_counter()
    _resolve_authority_aliases(G)
    if phase_timings is not None:
        phase_timings["relink"] += time.perf_counter() - relink_started

    return FullState(G, points, colbert_store, chunks_store, dense_store, code_store,
                     n_docs, progressive_count if colbert_writer is not None else len(points))


def _gate_and_publish(qdrant: QdrantClient, embed_model, version: str, collection_name: str,
                      graph: nx.DiGraph, chunks_store: dict, *, alias_name: str, emit,
                      timings: dict, project: ProjectContext | None, before_promote=None) -> dict:
    """Eval-gate sulla candidata e, se passa, promozione blue/green: CURRENT prima (commit
    point locale), poi l'eventuale migrazione legacy→alias, lo swap dell'alias e il GC.
    Condiviso da full rebuild e delta copy-on-write: entrambi pubblicano una collection
    dedicata e devono passare dallo STESSO gate. Restituisce il report del gate."""
    # Eval-gate: valuta la recall della versione candidata sul golden set PRIMA di spostare
    # CURRENT. Lo stato candidato è in memoria e Qdrant è già popolato: la valutazione
    # riflette il retrieval che verrebbe servito. Se regredisce, la promozione è bloccata.
    # collection_name è la STESSA collection appena costruita dal chiamante: il gate misura
    # sempre ciò che è stato davvero scritto, mai una collection diversa.
    # graph/restatements: il gate deve leggere lo STESSO ordinamento che il server servirà
    # (precedenza S4, peso di sezione N4), non quello nudo — R26.
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
        # Ordine NON NEGOZIABILE: CURRENT prima (il commit point locale), poi
        # l'eventuale migrazione one-shot legacy→alias e infine l'alias swap.
        # `collection_name` è la STESSA variabile usata per costruire questa versione —
        # non una ricostruzione indipendente del nome, quindi mai ambigua.
        if before_promote is not None:
            before_promote(version)
        promote_version(version, project=project)
        if project is None or project.legacy:
            _migrate_legacy_collection_if_needed(qdrant, alias_name, emit=emit)
        _swap_alias(qdrant, alias_name, collection_name)
        emit(f"🔀 Alias Qdrant '{alias_name}' → {collection_name} (blue/green).")
        # promote_version() sopra ha già applicato la retention locale (prune_versions),
        # quindi _referenced_qdrant_collections() qui dentro riflette già le versioni
        # sopravvissute — solo DOPO lo swap, nel single-writer di questo job, mai concorrente.
        gc_orphaned_qdrant_collections(qdrant, emit=emit, project=project)
        emit(f"🔁 Versione promossa: CURRENT → {version} (swap atomico, rollback: index.py --rollback).")
    timings["promote"] = time.perf_counter() - started
    return gate


def build_graph_and_index(qdrant: QdrantClient | None = None, embed_model=None, emit=None,
                          promote: bool = True, collector: dict | None = None, project: ProjectContext | None = None,
                          before_promote=None) -> str | None:
    """Esegue l'indicizzazione completa (Fase 0 e Fase 4) e restituisce il nome della
    versione blue/green scritta.

    Il modello di embedding può essere iniettato dall'esterno: quando il server
    FastAPI innesca la re-indicizzazione riusa quello già caricato, evitando un
    ricaricamento che richiede minuti di CPU. Il client Qdrant (server mode) è
    invece economico da aprire, ma viene comunque riusato quando disponibile.

    `emit` è un callback di log (default: logger.info) usato per lo streaming SSE del
    progresso verso l'interfaccia; se None si stampa su stdout come sempre.

    `promote=False` lascia la nuova versione NON attiva (CURRENT invariato): è il gancio
    per la promozione condizionata dei job full del ReindexManager (eval gate) — il
    chiamante promuove poi con `core.artifacts.promote_version(nome)`.
    `before_promote` permette alla migrazione di salvare la candidata approvata prima di CURRENT.

    Nome di versione e nome di collection sono DECISI UNA SOLA VOLTA all'inizio della
    funzione e riusati fino al salvataggio degli artefatti, al manifest e ai log.

    Blue/green Qdrant: `collection_name` è sempre la collection CANDIDATA versionata
    (`qdrant_collection_name(version)`), creata senza mai droppare/ricreare nulla
    (`recreate=False`: è un nome nuovo per costruzione, e soprattutto non deve MAI
    coincidere con — né quindi mai toccare — la collection di produzione, che resta
    COLLECTION_NAME). Il manifest registra quale collection ospita questa versione
    (`qdrant_collection`) e l'eval-gate valuta quella stessa candidata. Se il gate
    passa, la promozione sposta PRIMA CURRENT (il commit point locale) e SOLO DOPO
    l'alias `COLLECTION_NAME` sulla candidata (`_swap_alias`) — ordine non
    negoziabile. In mezzo, SOLO se necessario, la migrazione one-shot legacy→alias
    (`_migrate_legacy_collection_if_needed`): se `COLLECTION_NAME` esiste ancora come
    collection FISICA (installazione non ancora migrata — Qdrant non ammette un
    alias omonimo a una collection), viene cancellata per liberare il nome, SUBITO
    prima dello swap che la ricrea come alias — l'UNICA operazione irreversibile di
    questo meccanismo, con una finestra di indisponibilità breve ma reale fra le due
    chiamate (loggata esplicitamente). Se il layout è già migrato (alias esistente) o
    l'installazione è fresca (nessuna collisione), la migrazione è un no-op: nessun
    delete, solo lo swap. Subito dopo lo swap, il GC (`gc_orphaned_qdrant_collections`)
    rimuove le collection versionate orfane (build crashati/non promossi, lineage già
    ruotati dalla retention locale).
    """
    database_dir = project.database_dir if project is not None else artifact_module.DATABASE_DIR
    alias_name = project.collection_name if project is not None else COLLECTION_NAME
    docs_dir = project.docs_dir if project is not None else DOCS_DIR
    code_dir = project.code_dir if project is not None else CODE_DIR
    activate_immutable_index(project=project)
    _log = emit or logger.info
    timings = _new_phase_timings()
    own_qdrant = qdrant is None
    if embed_model is None:
        started = time.perf_counter()
        _log(f"Caricamento modello embedding: {EMBEDDING_MODEL} ...")
        embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)
        timings["init_model"] = time.perf_counter() - started
    started = time.perf_counter()
    if qdrant is None:
        qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    if project is not None and not project.legacy:
        try:
            physical = {collection.name for collection in qdrant.get_collections().collections}
            occupied = alias_name in physical
            if not artifact_module.list_versions(project=project):
                occupied = occupied or any(name.startswith(alias_name + '__') for name in physical)
                occupied = occupied or _read_alias_target(qdrant, alias_name) is not None
            if occupied:
                raise ValueError("Project Qdrant namespace is occupied without local ownership")
        except Exception:
            if own_qdrant:
                qdrant.close()
            raise

    version = _new_version_name(project=project)
    collection_name = qdrant_collection_name(version, project=project)

    # Mai recreate: la candidata è un nome nuovo per costruzione, niente da droppare,
    # e la produzione (nome diverso, COLLECTION_NAME) non va mai toccata da questa
    # chiamata — solo alla promozione, tramite l'alias swap più sotto.
    _ensure_collection(qdrant, recreate=False, collection_name=collection_name)
    timings["qdrant"] += time.perf_counter() - started

    staged_colbert = ColbertWriter(database_dir / ".colbert-staging" / version / "colbert", None)

    def _upsert_document(points):
        if not points:
            return
        started_upsert = time.perf_counter()
        batch_size = qdrant_upsert_batch_from_env()
        for i in range(0, len(points), batch_size):
            qdrant.upsert(collection_name=collection_name, points=points[i:i + batch_size])
        timings["qdrant"] += time.perf_counter() - started_upsert

    try:
        state = _build_full_state(embed_model, docs_dir, code_dir, emit=_log,
                                  phase_timings=timings, colbert_writer=staged_colbert,
                                  point_sink=_upsert_document)
    except BaseException:
        shutil.rmtree(staged_colbert.root)
        staged_colbert.root.parent.rmdir()
        raise
    if state.colbert_store is not staged_colbert:
        # Compatibility seam for injected FullState in unit tests. Real builds always
        # use the staged writer; do not leave its unused directory behind.
        shutil.rmtree(staged_colbert.root)
        state.point_count = len(state.points)
    G = state.graph
    started = time.perf_counter()
    try:
        if state.points:
            # Compatibility path for injected FullState tests; the real build upserts
            # each document through point_sink before retaining another document.
            batch_size = qdrant_upsert_batch_from_env()
            for i in range(0, len(state.points), batch_size):
                qdrant.upsert(collection_name=collection_name, points=state.points[i:i + batch_size])
        timings["qdrant"] += time.perf_counter() - started
        started = time.perf_counter()
        doc_hashes = docs_hashes(project=project)
        code_hashes = _code_hashes(project=project)
        timings["scan_hash"] = time.perf_counter() - started
        started = time.perf_counter()
        version = save_artifacts(G, state.colbert_store, state.chunks_store, state.dense_store,
                                 state.code_store, version=version, project=project)
    except BaseException:
        if staged_colbert.root.exists():
            shutil.rmtree(staged_colbert.root)
        if staged_colbert.root.parent.exists() and not any(staged_colbert.root.parent.iterdir()):
            staged_colbert.root.parent.rmdir()
        raise
    if staged_colbert.root.exists():
        if state.colbert_store is staged_colbert:
            raise RuntimeError("ColBERT staged writer was not moved into the candidate version")
        shutil.rmtree(staged_colbert.root)
        staged_colbert.root.parent.rmdir()

    _log(f"\n✅ Artefatti indice salvati nella versione {version} (grafo JSON, ColBERT NPY, dense/code NPZ).")
    _log(f"📊 Grafo: {G.number_of_nodes()} nodi, {G.number_of_edges()} archi.")
    _log(f"📦 Qdrant: {state.point_count} chunk (da {state.n_docs} documenti) nella collection '{collection_name}'.")

    write_index_manifest(state.point_count, G.number_of_nodes(), G.number_of_edges(),
                        version=version, qdrant_collection=collection_name,
                        doc_hashes=doc_hashes, code_hashes=code_hashes,
                        colbert_new_files=staged_colbert.new_files if state.colbert_store is staged_colbert else None,
                        immutable=immutable_index_active(project=project), project=project)
    timings["save_hash"] += time.perf_counter() - started
    _log(f"🧾 Manifest indicizzazione salvato in: {manifest_path(version, project=project)}")

    if promote and version:
        # Eval-gate + promozione: vedi _gate_and_publish (condiviso col delta copy-on-write).
        _gate_and_publish(qdrant, embed_model, version, collection_name, G, state.chunks_store,
                          alias_name=alias_name, emit=_log, timings=timings, project=project,
                          before_promote=before_promote)

    if own_qdrant:
        qdrant.close()
    if collector is not None:
        collector.update({
            "phase_timings_seconds": timings,
            "colbert_io_bytes": dict(staged_colbert.stats),
            "counts": {
                "docs_added": state.n_docs, "docs_modified": 0, "docs_removed": 0,
                "code_added": len(code_hashes), "code_modified": 0, "code_removed": 0,
                "chunks_processed": state.point_count, "chunks_indexed": len(state.chunks_store),
                "colbert_tokens_processed": _colbert_token_count(state.colbert_store),
                "colbert_tokens_indexed": _colbert_token_count(state.colbert_store),
                "code_tokens_processed": None,
                "code_tokens_unavailable_reason": "embedding output does not expose code token counts",
            },
        })
    return version


"""Costruzione dell'indice Graph-RAG: grafo NetworkX + collection Qdrant (hybrid dense/sparse)
+ sidecar ColBERT/chunk, con indicizzazione completa e incrementale (delta), manifest, controllo
del Drift e archiviazione. Il caricamento/chunking dei documenti vive in core/chunking.py; la
configurazione in core/config.py. Le risorse pesanti (Qdrant, embedding) sono iniettabili."""
import hashlib
import json
import os
import pickle
import shutil
import tempfile
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
from FlagEmbedding import BGEM3FlagModel
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from code_index import (
    CODE_EXTS,
    add_symbol_nodes,
    collect_code_symbols,
    embed_symbols,
    link_symbols,
)
from core.canvas_review import (
    HISTORICAL_SUBDIR,
    REVIEW_FILENAME,
    generate_canvas_review,
)
from core.chunking import (
    add_frontmatter_edges,
    chunk_markdown,
    extract_entities,
    read_document,
)
from core.config import (
    CHANGES_DIR,
    CHUNKS_SAVE_PATH,
    CODE_DIR,
    CODE_SAVE_PATH,
    COLBERT_SAVE_PATH,
    COLLECTION_NAME,
    DENSE_DIM,
    DENSE_SAVE_PATH,
    DOC_EXTS,
    DOCS_DIR,
    EMBEDDING_MODEL,
    GRAPH_SAVE_PATH,
    INDEX_MANIFEST_PATH,
    QDRANT_API_KEY,
    QDRANT_URL,
)

# Endpoint e modello Ollama per il controllo del Drift (canvas <-> codice).
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL_NAME = "qwen2.5:7b"

# Namespace fisso per derivare l'ID del punto Qdrant dal chunk_id in modo DETERMINISTICO
# (uuid5): lo stesso chunk_id produce sempre lo stesso id, base dell'incrementale idempotente.
_POINT_ID_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def _point_id(chunk_id: str) -> str:
    """ID Qdrant deterministico e stabile per un chunk (uuid5 del chunk_id)."""
    return str(uuid.uuid5(_POINT_ID_NAMESPACE, chunk_id))


def _atomic_write(path: Path, writer) -> None:
    """Scrittura ATOMICA di un artefatto: `writer(file_object)` scrive su un file
    temporaneo NELLA STESSA directory di `path`, poi `os.replace` lo rinomina in modo
    atomico sul filesystem. Se il processo muore a metà scrittura, `path` resta la
    versione precedente (integra) o non esiste ancora: mai un file troncato/corrotto.
    Il temporaneo va nella stessa dir per garantire che replace sia una rename atomica
    sullo stesso mount (os.replace tra filesystem diversi non è atomico)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            writer(f)
            f.flush()
            os.fsync(f.fileno())  # forza i dati su disco prima del rename
        os.replace(tmp_name, path)
    except BaseException:
        # Non lasciare temporanei orfani se qualcosa va storto prima del replace
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _atomic_write_pickle(path: Path, obj) -> None:
    """Serializza `obj` con pickle in modo atomico (vedi _atomic_write)."""
    _atomic_write(path, lambda f: pickle.dump(obj, f))


def _atomic_write_text(path: Path, text: str) -> None:
    """Scrive testo UTF-8 in modo atomico (vedi _atomic_write)."""
    _atomic_write(path, lambda f: f.write(text.encode("utf-8")))


def _add_doc_to_graph(G: nx.DiGraph, rel_path: str, metadata: dict, body: str) -> tuple[int, int]:
    """Aggiunge (o riaggiunge) al grafo il nodo-documento, le entità citate (archi
    MENTIONS) e le relazioni tipizzate del frontmatter. Condiviso dal full rebuild e
    dall'indicizzazione incrementale, così la costruzione del grafo per-documento è
    identica nei due percorsi. Restituisce (numero_entità, numero_relazioni_tipizzate)."""
    G.add_node(rel_path, type="document", **metadata)
    entities = extract_entities(body)
    for entity in entities:
        G.add_node(entity, type="entity")
        G.add_edge(rel_path, entity, relation="MENTIONS")
    typed_edges = add_frontmatter_edges(G, rel_path, metadata)
    return len(entities), typed_edges


def _remove_doc_nodes_from_graph(G: nx.DiGraph, doc_ids) -> int:
    """Rimuove i soli NODI-DOCUMENTO indicati e gli archi a essi incidenti (MENTIONS
    uscenti, relazioni tipizzate, e l'eventuale IMPLEMENTS entrante da un nodo codice).

    I nodi `code` e i loro archi REFERENCES verso le entità NON vengono toccati: cade
    solo il link `code -> quel documento`. È la staleness accettata sui code-link, che
    viene ripristinata al successivo full rebuild (vedi build_graph_and_index)."""
    removed = 0
    for doc_id in doc_ids:
        if doc_id in G and G.nodes[doc_id].get("type") == "document":
            G.remove_node(doc_id)
            removed += 1
    return removed


def _prune_unsupported_entities(G: nx.DiGraph) -> int:
    """Rimuove i nodi-ENTITÀ che nessun DOCUMENTO cita più (nessun arco entrante da un nodo
    'document'). È l'invariante del full rebuild: un'entità esiste solo se un documento la
    menziona (MENTIONS) o la referenzia dal frontmatter — il codice, con REFERENCES, può solo
    puntare a entità già esistenti, mai crearne. Quando un documento sparisce o cambia, le sue
    entità 'orfane di documento' vanno rimosse (insieme agli eventuali REFERENCES stale del
    codice che le puntavano), altrimenti l'incrementale divergerebbe dal rebuild."""
    doc_nodes = {n for n, a in G.nodes(data=True) if a.get("type") == "document"}
    orphans = [
        n for n, a in G.nodes(data=True)
        if a.get("type") == "entity" and not (doc_nodes & set(G.predecessors(n)))
    ]
    G.remove_nodes_from(orphans)
    return len(orphans)


def _dense_map(chunks: list[dict], dense_vecs) -> dict[str, "object"]:
    """Mappa chunk_id -> vettore denso (fp16) allineando `chunks` e `dense_vecs`. Robusto
    ai fake di test che non producono vettori: se le lunghezze non combaciano restituisce {}."""
    try:
        if dense_vecs is None or len(dense_vecs) != len(chunks):
            return {}
    except TypeError:
        return {}
    return {c["chunk_id"]: dv.astype("float16") for c, dv in zip(chunks, dense_vecs)}


def _encode_chunks_to_points(embed_model, chunks: list[dict]):
    """Vettorializza i chunk (una forward pass bge-m3 → dense+sparse+colbert) e produce
    i PointStruct Qdrant con id DETERMINISTICO (uuid5 del chunk_id) più i due sidecar
    parziali (colbert e testo per chunk_id). Condiviso da full rebuild e incrementale.

    Restituisce (points, colbert_partial, chunks_partial, dense_vecs). `dense_vecs` serve
    solo al full rebuild per collegare i simboli di codice al chunk-documento più vicino."""
    points: list[PointStruct] = []
    colbert_partial: dict[str, list] = {}
    chunks_partial: dict[str, dict] = {}
    if not chunks:
        return points, colbert_partial, chunks_partial, []

    output = embed_model.encode(
        [c["text"] for c in chunks],
        batch_size=12,
        max_length=8192,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=True,
    )
    dense_vecs = output["dense_vecs"]
    lexical_weights = output["lexical_weights"]
    colbert_vecs = output["colbert_vecs"]

    for c, dense_vec, lex_w, col_vec in zip(chunks, dense_vecs, lexical_weights, colbert_vecs):
        sparse_vec = SparseVector(
            indices=[int(token_id) for token_id in lex_w.keys()],
            values=[float(w) for w in lex_w.values()],
        )
        points.append(
            PointStruct(
                id=_point_id(c["chunk_id"]),
                vector={"dense": dense_vec.tolist(), "sparse": sparse_vec},
                # doc_id = documento padre (nodo del grafo); chunk_id = chiave del retrieval
                payload={"chunk_id": c["chunk_id"], "doc_id": c["doc_id"], "section": c["section"], **c["metadata"]},
            )
        )
        # fp16 per dimezzare l'occupazione su disco; il rerank riconverte al volo
        colbert_partial[c["chunk_id"]] = col_vec.astype("float16")
        chunks_partial[c["chunk_id"]] = {"doc_id": c["doc_id"], "section": c["section"], "text": c["text"]}

    return points, colbert_partial, chunks_partial, dense_vecs


def _ensure_collection(qdrant: QdrantClient, recreate: bool = False) -> None:
    """Garantisce l'esistenza della collection Qdrant con la config hybrid (dense+sparse).
    `recreate=True` (full rebuild) la ricostruisce da zero; `recreate=False` (incrementale)
    la crea solo se assente, senza mai cancellare i punti già presenti."""
    existing = {c.name for c in qdrant.get_collections().collections}
    if recreate and COLLECTION_NAME in existing:
        qdrant.delete_collection(COLLECTION_NAME)
        existing.discard(COLLECTION_NAME)
    if COLLECTION_NAME not in existing:
        # Hybrid Search: la stessa collection ospita il vettore denso (semantica generale)
        # e quello sparso (match lessicali esatti). I multivettori ColBERT vivono nel sidecar.
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={"dense": VectorParams(size=DENSE_DIM, distance=Distance.COSINE)},
            sparse_vectors_config={"sparse": SparseVectorParams()},
        )


@dataclass
class FullState:
    """Stato completo prodotto da un'indicizzazione da zero (in memoria, senza I/O):
    grafo + punti Qdrant + tutti i sidecar. È l'output condiviso dal full rebuild (che lo
    persiste) e dal check di coerenza (che confronta il solo grafo con quello persistito)."""
    graph: nx.DiGraph
    points: list = field(default_factory=list)
    colbert_store: dict = field(default_factory=dict)
    chunks_store: dict = field(default_factory=dict)
    dense_store: dict = field(default_factory=dict)
    code_store: dict = field(default_factory=dict)
    n_docs: int = 0


def _build_full_state(embed_model, docs_dir: Path, code_dir: Path, emit=None) -> FullState:
    """Costruisce da zero l'intero stato dell'indice (grafo + chunk + sidecar) a partire
    dai file, SENZA alcun I/O su disco o Qdrant. Funzione pura (a parità di modello e input
    produce lo stesso grafo): è l'unica fonte di verità della topologia 'da rebuild', usata
    sia dal full rebuild reale sia dal check di coerenza (index.py --check-graph)."""
    _log = emit or print
    G = nx.DiGraph()
    all_chunks: list[dict] = []
    n_docs = 0

    all_docs = sorted(p for p in docs_dir.rglob("*") if p.is_file() and p.suffix.lower() in DOC_EXTS)
    for filepath_obj in all_docs:
        rel_path = filepath_obj.relative_to(docs_dir).as_posix()
        metadata, body = read_document(filepath_obj)
        if not body.strip():
            _log(f"  (saltato, corpo vuoto o loader assente: {rel_path})")
            continue
        n_entities, typed_edges = _add_doc_to_graph(G, rel_path, metadata, body)
        doc_chunks = chunk_markdown(rel_path, metadata, body)
        for c in doc_chunks:
            c["metadata"] = metadata
        all_chunks.extend(doc_chunks)
        n_docs += 1
        _log(f"  Analizzato: {rel_path} — {n_entities} entità, {len(doc_chunks)} chunk, {typed_edges} relazioni tipizzate")

    points: list = []
    colbert_store: dict = {}
    chunks_store: dict = {}
    dense_store: dict = {}
    if all_chunks:
        _log(f"\nVettorializzazione di {len(all_chunks)} chunk (da {n_docs} documenti) con {EMBEDDING_MODEL} (dense + sparse + colbert)...")
        points, colbert_store, chunks_store, dense_vecs = _encode_chunks_to_points(embed_model, all_chunks)
        dense_store = _dense_map(all_chunks, dense_vecs)

    # Fase Codice: nodi dei simboli + archi IMPLEMENTS (chunk-doc più simile) e REFERENCES.
    # Indipendente dalla presenza di documenti: i simboli di codice esistono comunque come
    # nodi (senza IMPLEMENTS finché non c'è uno spazio-documenti a cui agganciarsi), così
    # full rebuild e incrementale restano allineati anche quando docs/ è temporaneamente vuoto.
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
            n_impl = link_symbols(G, code_symbols, sym_dense16, doc_dense16, doc_parent16)
            code_store = {
                s["id"]: {"name": s["name"], "kind": s["kind"], "file": s["file"],
                          "dev_type": s["dev_type"], "text": s["text"],
                          "dense": sym_dense16[i]}
                for i, s in enumerate(code_symbols)
            }
            _log(f"🧩 Codice indicizzato: {len(code_symbols)} simboli, {n_impl} archi IMPLEMENTS verso i documenti.")
        else:
            _log("🧩 Nessun simbolo di codice trovato sotto code/ (verrà indicizzato quando Claude scriverà il codice).")
    except Exception as e:
        _log(f"⚠️ Indicizzazione del codice saltata: {e}")

    return FullState(G, points, colbert_store, chunks_store, dense_store, code_store, n_docs)


def build_graph_and_index(qdrant: QdrantClient | None = None, embed_model=None, emit=None) -> None:
    """Esegue l'indicizzazione completa (Fase 0 e Fase 4).

    Il modello di embedding può essere iniettato dall'esterno: quando il server
    FastAPI innesca la re-indicizzazione riusa quello già caricato, evitando un
    ricaricamento che richiede minuti di CPU. Il client Qdrant (server mode) è
    invece economico da aprire, ma viene comunque riusato quando disponibile.

    `emit` è un callback di log (default: print) usato per lo streaming SSE del
    progresso verso l'interfaccia; se None si stampa su stdout come sempre.
    """
    _log = emit or print
    own_qdrant = qdrant is None
    if embed_model is None:
        _log(f"Caricamento modello embedding: {EMBEDDING_MODEL} ...")
        embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)
    if qdrant is None:
        qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Ricrea la collection Qdrant da zero ad ogni indicizzazione completa
    _ensure_collection(qdrant, recreate=True)

    state = _build_full_state(embed_model, DOCS_DIR, CODE_DIR, emit=_log)
    G = state.graph
    if state.points:
        qdrant.upsert(collection_name=COLLECTION_NAME, points=state.points)

    # Salva il grafo, i multivettori ColBERT e i sidecar su disco
    # (scrittura atomica: un crash a metà non lascia artefatti troncati).
    _atomic_write_pickle(GRAPH_SAVE_PATH, G)
    _atomic_write_pickle(COLBERT_SAVE_PATH, state.colbert_store)
    _atomic_write_pickle(CHUNKS_SAVE_PATH, state.chunks_store)
    _atomic_write_pickle(DENSE_SAVE_PATH, state.dense_store)
    _atomic_write_pickle(CODE_SAVE_PATH, state.code_store)

    _log(f"\n✅ Grafo salvato in: {GRAPH_SAVE_PATH}")
    _log(f"✅ Multivettori ColBERT salvati in: {COLBERT_SAVE_PATH}")
    _log(f"✅ Sidecar chunk salvato in: {CHUNKS_SAVE_PATH}")
    _log(f"📊 Grafo: {G.number_of_nodes()} nodi, {G.number_of_edges()} archi.")
    _log(f"📦 Qdrant: {len(state.points)} chunk (da {state.n_docs} documenti) nella collection '{COLLECTION_NAME}'.")

    write_index_manifest(len(state.points), G.number_of_nodes(), G.number_of_edges())
    _log(f"🧾 Manifest indicizzazione salvato in: {INDEX_MANIFEST_PATH}")

    if own_qdrant:
        qdrant.close()


def _docs_hashes() -> dict[str, str]:
    """Calcola l'hash SHA-256 di ogni documento indicizzabile in docs/ (chiave = percorso relativo)."""
    hashes: dict[str, str] = {}
    for filepath_obj in sorted(p for p in DOCS_DIR.rglob("*") if p.is_file() and p.suffix.lower() in DOC_EXTS):
        rel_path = filepath_obj.relative_to(DOCS_DIR).as_posix()
        hashes[rel_path] = hashlib.sha256(filepath_obj.read_bytes()).hexdigest()
    return hashes


def _code_hashes() -> dict[str, str]:
    """Hash SHA-256 di ogni file di codice sotto code/ (chiave = percorso relativo a code/).
    Base del delta incrementale sul codice, gemella di _docs_hashes per i documenti."""
    hashes: dict[str, str] = {}
    if not CODE_DIR.exists():
        return hashes
    for filepath_obj in sorted(p for p in CODE_DIR.rglob("*") if p.is_file() and p.suffix in CODE_EXTS):
        rel_path = filepath_obj.relative_to(CODE_DIR).as_posix()
        hashes[rel_path] = hashlib.sha256(filepath_obj.read_bytes()).hexdigest()
    return hashes


def write_index_manifest(points_count: int, nodes: int = 0, edges: int = 0) -> None:
    """Persiste lo snapshot dell'indice (config modello, conteggi, hash dei documenti).

    Il campo `version` (timestamp ISO) viene scritto INSIEME agli artefatti: identifica
    in modo univoco questo giro di indicizzazione, così un client può confrontarlo con
    quello dell'ultima build vista e capire se sta leggendo un indice coerente (tutti e
    tre i pickle + manifest appartenenti alla stessa versione)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    manifest = {
        "version": now_iso,
        "embedding_model": EMBEDDING_MODEL,
        "collection": COLLECTION_NAME,
        "created_at": now_iso,
        "documents": points_count,
        "graph_nodes": nodes,
        "graph_edges": edges,
        "doc_hashes": _docs_hashes(),
        "code_hashes": _code_hashes(),
    }
    _atomic_write_text(INDEX_MANIFEST_PATH, json.dumps(manifest, ensure_ascii=False, indent=2))


def _diff_hashes(old: dict[str, str], new: dict[str, str]) -> tuple[list[str], list[str], list[str], list[str]]:
    """Confronto deterministico tra due mappe {rel_path: hash}.
    Restituisce (added, removed, modified, unchanged), ciascuno ordinato.
    Unica fonte di verità del delta, condivisa da index_status e plan_incremental_indexing."""
    old_keys, new_keys = set(old), set(new)
    common = old_keys & new_keys
    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    modified = sorted(k for k in common if old[k] != new[k])
    unchanged = sorted(k for k in common if old[k] == new[k])
    return added, removed, modified, unchanged


def _read_manifest() -> dict | None:
    """Legge il manifest se presente e leggibile, altrimenti None (assente o corrotto).
    Il chiamante interpreta None come 'nessuna base nota' → tutto da (ri)indicizzare."""
    if not INDEX_MANIFEST_PATH.exists():
        return None
    try:
        data = json.loads(INDEX_MANIFEST_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def index_status() -> dict:
    """Confronta gli hash correnti di docs/ con quelli del manifest per dire se l'indice
    è aggiornato o va rigenerato, elencando i documenti aggiunti/rimossi/modificati."""
    if not INDEX_MANIFEST_PATH.exists():
        return {"indexed": False, "stale": True, "reason": "manifest assente — indice mai costruito", "changed": []}
    try:
        manifest = json.loads(INDEX_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"indexed": False, "stale": True, "reason": f"manifest illeggibile: {exc}", "changed": []}

    added, removed, modified, _unchanged = _diff_hashes(manifest.get("doc_hashes", {}), _docs_hashes())
    changed = [f"+ {p}" for p in added] + [f"- {p}" for p in removed] + [f"~ {p}" for p in modified]
    return {
        "indexed": True,
        "stale": bool(changed),
        "version": manifest.get("version"),
        "created_at": manifest.get("created_at"),
        "embedding_model": manifest.get("embedding_model"),
        "documents": manifest.get("documents"),
        "changed": changed,
    }


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


def _delete_doc_chunks(qdrant: QdrantClient, doc_ids: list[str]) -> None:
    """Rimuove da Qdrant TUTTI i punti i cui payload.doc_id è tra quelli indicati,
    con un'unica delete-by-filter (MatchAny). Nessuna dipendenza dall'id del punto."""
    if not doc_ids:
        return
    qdrant.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="doc_id", match=MatchAny(any=list(doc_ids)))])
        ),
    )


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
                "dense": sym_dense[i].astype("float16"),
            }
            touched.add(sym["id"])
    if gone_files or new_syms:
        _log = emit or print
        _log(f"🧩 Codice: {len(removed)} file rimossi, {len(added)} nuovi, {len(modified)} modificati "
             f"→ {len(touched)} simboli (ri)estratti.")
    return touched


def _relink_touched_symbols(graph: nx.DiGraph, code_store: dict, chunks_store: dict,
                            dense_store: dict, touched_ids: set[str]) -> int:
    """Ricalcola IMPLEMENTS/REFERENCES per i soli simboli in `touched_ids`, usando i vettori
    densi già persistiti (nessun re-embed): i simboli dal code_store, i chunk-documento dal
    dense_store. Restituisce il numero di archi IMPLEMENTS creati."""
    ids = [sid for sid in touched_ids if sid in graph and sid in code_store]
    if not ids:
        return 0
    syms = [{"id": sid, "text": code_store[sid]["text"]} for sid in ids]
    sym_dense = [code_store[sid]["dense"] for sid in ids]

    chunk_ids = [cid for cid in dense_store if cid in chunks_store]
    chunk_dense = [dense_store[cid] for cid in chunk_ids]
    chunk_parent = [chunks_store[cid]["doc_id"] for cid in chunk_ids]
    return link_symbols(graph, syms, sym_dense, chunk_dense, chunk_parent)


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
) -> dict:
    """Esegue il piano del delta sugli oggetti passati (Qdrant + grafo + sidecar), mutandoli
    in-place. NON fa I/O su disco né gestisce il modello: quelli restano al chiamante
    (incremental_index), così questa funzione è deterministica e testabile con fake leggeri.

    Passi (idempotenti):
      1. purge dei chunk dei documenti modificati+cancellati da Qdrant (delete-by-filter),
         dai sidecar (colbert/chunks/dense) e dei relativi nodi-documento dal grafo;
      2. (ri)vettorializzazione dei documenti nuovi+modificati e upsert con id deterministici,
         con re-inserimento dei nodi-documento nel grafo;
      3. delta sui file di codice (simboli aggiunti/rimossi/modificati);
      4. ricalcolo mirato degli archi spec<->codice (IMPLEMENTS/REFERENCES) per i soli nodi
         toccati: i simboli nuovi/modificati e — se lo spazio dei documenti è cambiato —
         tutti i simboli (l'argmax sui documenti può essersi spostato). Infine potatura
         delle entità rimaste orfane. Questo elimina la staleness dei code-link senza rebuild.

    `dense_store`/`code_store`/`code_delta`/`code_dir` sono opzionali: se assenti la funzione
    si comporta come prima (nessun ricalcolo dei code-link), preservando i chiamanti legacy."""
    _log = emit or print
    to_delete = plan.to_delete()   # modificati + cancellati
    to_index = plan.to_index()     # nuovi + modificati

    # 1. Purge (Qdrant + sidecar + grafo) dei documenti non più validi nella loro forma attuale
    if to_delete:
        _delete_doc_chunks(qdrant, to_delete)
        dead_set = set(to_delete)
        dead_chunks = [cid for cid, meta in chunks_store.items() if meta.get("doc_id") in dead_set]
        for cid in dead_chunks:
            colbert_store.pop(cid, None)
            chunks_store.pop(cid, None)
            if dense_store is not None:
                dense_store.pop(cid, None)
        _remove_doc_nodes_from_graph(graph, to_delete)
        _log(f"🗑️  Rimossi i chunk di {len(to_delete)} documenti (modificati/cancellati): {len(dead_chunks)} chunk purgati da Qdrant, sidecar e grafo.")

    # 2. (Ri)indicizzazione dei soli documenti nuovi/modificati
    upserted = 0
    if to_index:
        assert docs_dir is not None, "docs_dir richiesto quando ci sono documenti da (ri)indicizzare"
        new_chunks: list[dict] = []
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
            for c in doc_chunks:
                c["metadata"] = metadata
            new_chunks.extend(doc_chunks)

        if new_chunks:
            _log(f"\nVettorializzazione incrementale di {len(new_chunks)} chunk (da {len(to_index)} documenti)...")
            points, colbert_partial, chunks_partial, _dense = _encode_chunks_to_points(embed_model, new_chunks)
            qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
            colbert_store.update(colbert_partial)
            chunks_store.update(chunks_partial)
            if dense_store is not None:
                dense_store.update(_dense_map(new_chunks, _dense))
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
        # Se lo spazio dei documenti è cambiato, l'argmax IMPLEMENTS di OGNI simbolo può
        # spostarsi (e le entità citabili cambiano): vanno rilinkati tutti. Altrimenti bastano
        # i simboli toccati dal delta del codice.
        docs_changed = bool(to_index or plan.deleted)
        if docs_changed:
            touched |= set(code_store.keys())
        # Prima si potano le entità che nessun documento cita più (rimuove anche i REFERENCES
        # stale del codice verso di esse), POI si ricalcolano i link: così REFERENCES viene
        # ricostruito sull'insieme di entità valido, identico a quello del full rebuild.
        orphans = _prune_unsupported_entities(graph)
        implements = _relink_touched_symbols(graph, code_store, chunks_store, dense_store, touched)
        if touched or orphans:
            _log(f"🔗 Code-link ricalcolati per {len(touched)} simboli → {implements} IMPLEMENTS; "
                 f"{orphans} entità orfane potate.")

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
    }


def _load_pickle(path: Path, default):
    """Carica un pickle se presente e integro, altrimenti restituisce `default`."""
    if not path.exists():
        return default
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return default


def incremental_index(qdrant: QdrantClient | None = None, embed_model=None, emit=None) -> dict:
    """Orchestratore dell'indicizzazione incrementale: manifest → piano → esecuzione → persistenza.

    - Salta del tutto i documenti invariati (nessun re-embed).
    - Se non c'è nulla da fare (e il manifest esiste) è un no-op: nessuna scrittura su
      Qdrant, sidecar o manifest → idempotente sulle run ripetute.
    - Manifest assente/corrotto ⇒ il piano marca tutto come 'new' (equivale al full rebuild),
      ma senza droppare la collection: i punti vengono upsertati con id deterministici.
    """
    _log = emit or print
    own_qdrant = qdrant is None

    current = _docs_hashes()
    manifest = _read_manifest()
    plan = plan_incremental_indexing(current, manifest)

    # Delta sul codice: gemello del piano documenti, così l'incrementale reagisce anche a
    # nuovi file di codice / modifiche / cancellazioni sotto code/ (non solo a docs/).
    current_code = _code_hashes()
    old_code = manifest.get("code_hashes", {}) if isinstance(manifest, dict) else {}
    code_added, code_removed, code_modified, _uc = _diff_hashes(old_code, current_code)
    code_changed = bool(code_added or code_removed or code_modified)

    if manifest is not None and plan.is_noop and not code_changed:
        _log("✅ Nessun cambiamento in docs/ o code/: indice già aggiornato (no-op, nessuna scrittura).")
        return {"noop": True, "planned": plan.as_dict(), "reindexed_docs": 0, "deleted_docs": 0, "upserted_chunks": 0}

    _log(f"📋 Piano incrementale: {len(plan.new)} nuovi, {len(plan.modified)} modificati, "
         f"{len(plan.deleted)} cancellati, {len(plan.unchanged)} invariati (saltati). "
         f"Codice: +{len(code_added)} ~{len(code_modified)} -{len(code_removed)}.")

    # Il modello serve solo se c'è qualcosa da (ri)embeddare: documenti nuovi/modificati
    # oppure file di codice nuovi/modificati. Un run di solo-delete non paga bge-m3.
    if embed_model is None and (plan.to_index() or code_added or code_modified):
        _log(f"Caricamento modello embedding: {EMBEDDING_MODEL} ...")
        embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)
    if qdrant is None:
        qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # L'incrementale NON ricrea la collection: la crea solo se assente, preservando i punti.
    _ensure_collection(qdrant, recreate=False)

    graph: nx.DiGraph = _load_pickle(GRAPH_SAVE_PATH, nx.DiGraph())
    colbert_store: dict = _load_pickle(COLBERT_SAVE_PATH, {})
    chunks_store: dict = _load_pickle(CHUNKS_SAVE_PATH, {})
    dense_store: dict = _load_pickle(DENSE_SAVE_PATH, {})
    code_store: dict = _load_pickle(CODE_SAVE_PATH, {})

    stats = apply_incremental_indexing(
        plan, DOCS_DIR, qdrant, embed_model, graph, colbert_store, chunks_store, emit=_log,
        dense_store=dense_store, code_store=code_store,
        code_delta=(code_added, code_removed, code_modified), code_dir=CODE_DIR,
    )

    # Persistenza: pickle atomici + manifest coerente (documents = chunk totali correnti)
    _atomic_write_pickle(GRAPH_SAVE_PATH, graph)
    _atomic_write_pickle(COLBERT_SAVE_PATH, colbert_store)
    _atomic_write_pickle(CHUNKS_SAVE_PATH, chunks_store)
    _atomic_write_pickle(DENSE_SAVE_PATH, dense_store)
    _atomic_write_pickle(CODE_SAVE_PATH, code_store)
    write_index_manifest(len(chunks_store), graph.number_of_nodes(), graph.number_of_edges())

    _log(f"🧾 Manifest aggiornato: {len(chunks_store)} chunk, {graph.number_of_nodes()} nodi, {graph.number_of_edges()} archi.")
    _log("🔗 Code-link spec<->codice ricalcolati per i nodi toccati (nessun full rebuild necessario).")

    if own_qdrant:
        qdrant.close()

    return stats


def _edge_set(G: nx.DiGraph) -> set[tuple[str, str, str]]:
    """Rappresenta il grafo come insieme di archi tipizzati (u, v, relation): confronto
    stabile e indipendente dagli attributi non strutturali (es. il peso degli IMPLEMENTS)."""
    return {(u, v, str(d.get("relation"))) for u, v, d in G.edges(data=True)}


def _node_type_set(G: nx.DiGraph) -> set[tuple[str, str]]:
    """Insieme (id, type) dei nodi: cattura sia la presenza sia il tipo di ciascun nodo."""
    return {(n, str(a.get("type"))) for n, a in G.nodes(data=True)}


def check_graph_consistency(embed_model=None, docs_dir: Path | None = None,
                            code_dir: Path | None = None, graph_path: Path | None = None,
                            emit=None) -> dict:
    """Confronta il grafo INCREMENTALE persistito con quello che produrrebbe un full rebuild
    sugli STESSI input (documenti + codice), e segnala le differenze di nodi e archi.

    È il guardrail contro la deriva dell'incrementale: se il ricalcolo mirato dei code-link
    ha lasciato archi stale o nodi orfani, questo check li fa emergere confrontando con la
    topologia di riferimento (_build_full_state). Non tocca Qdrant né riscrive nulla.

    Restituisce un dict con `consistent` (bool) e le liste delle differenze (troncate)."""
    _log = emit or print
    docs_dir = docs_dir or DOCS_DIR
    code_dir = code_dir or CODE_DIR
    graph_path = graph_path or GRAPH_SAVE_PATH

    incremental: nx.DiGraph | None = _load_pickle(graph_path, None)
    if incremental is None:
        return {"consistent": False, "reason": f"grafo incrementale assente o illeggibile: {graph_path}"}

    if embed_model is None:
        _log(f"Caricamento modello embedding: {EMBEDDING_MODEL} ...")
        embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)

    reference = _build_full_state(embed_model, docs_dir, code_dir, emit=lambda *_a, **_k: None).graph

    inc_nodes, ref_nodes = _node_type_set(incremental), _node_type_set(reference)
    inc_edges, ref_edges = _edge_set(incremental), _edge_set(reference)

    missing_nodes = sorted(ref_nodes - inc_nodes)   # attesi dal rebuild, mancanti nell'incrementale
    extra_nodes = sorted(inc_nodes - ref_nodes)     # presenti nell'incrementale, non nel rebuild (stale)
    missing_edges = sorted(ref_edges - inc_edges)
    extra_edges = sorted(inc_edges - ref_edges)

    consistent = not (missing_nodes or extra_nodes or missing_edges or extra_edges)
    _cap = 50
    report = {
        "consistent": consistent,
        "reference_nodes": len(ref_nodes),
        "incremental_nodes": len(inc_nodes),
        "reference_edges": len(ref_edges),
        "incremental_edges": len(inc_edges),
        "missing_nodes": [list(x) for x in missing_nodes[:_cap]],
        "extra_nodes": [list(x) for x in extra_nodes[:_cap]],
        "missing_edges": [list(x) for x in missing_edges[:_cap]],
        "extra_edges": [list(x) for x in extra_edges[:_cap]],
        "counts": {
            "missing_nodes": len(missing_nodes), "extra_nodes": len(extra_nodes),
            "missing_edges": len(missing_edges), "extra_edges": len(extra_edges),
        },
    }
    if consistent:
        _log("✅ Grafo incrementale COERENTE con il full rebuild (stessi nodi e archi).")
    else:
        _log(f"⚠️ Grafo incrementale DIVERGENTE dal rebuild: "
             f"{len(missing_nodes)} nodi mancanti, {len(extra_nodes)} nodi in eccesso, "
             f"{len(missing_edges)} archi mancanti, {len(extra_edges)} archi in eccesso.")
    return report


def _load_dev_type(feature_folder: str) -> str:
    """Legge il tipo di sviluppo salvato in changes/<feature>/meta.json, se presente."""
    meta_path = CHANGES_DIR / feature_folder / "meta.json"
    if not meta_path.exists():
        return ""
    try:
        return json.loads(meta_path.read_text(encoding="utf-8")).get("dev_type", "")
    except Exception:
        return ""


def check_drift(feature_name: str, emit=None) -> str:
    """Controlla se il codice generato si è discostato dalle specifiche del Canvas.

    Restituisce il report testuale (oltre a stamparlo/emetterlo), così da poterlo
    mostrare anche nel box dedicato dell'interfaccia della pipeline, senza terminale.
    `emit` (default: print) permette lo streaming SSE del progresso.
    """
    _log = emit or print
    feature_folder = feature_name.replace(' ', '-').lower()
    _log(f"\n🔍 Avvio controllo Drift (Disallineamento) per: 'changes/{feature_folder}'...")

    canvas_path = CHANGES_DIR / feature_folder / "canvas.md"

    if not canvas_path.exists():
        msg = f"❌ Errore: Non trovo il file {canvas_path}."
        _log(msg)
        return msg

    canvas_content = canvas_path.read_text(encoding="utf-8")

    # Raccoglie il codice da confrontare: sia dall'eventuale codice presente nella
    # cartella della feature, sia dalla sottocartella code/<dev_type> dove Claude
    # Code scrive di fatto l'implementazione (il tipo di sviluppo è in meta.json).
    code_exts = ('.js', '.ts', '.tsx', '.py', '.html', '.css')
    search_dirs = [CHANGES_DIR / feature_folder]
    dev_type = _load_dev_type(feature_folder)
    if dev_type:
        search_dirs.append(CODE_DIR / dev_type)

    codice_generato = ""
    for base in search_dirs:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix in code_exts:
                codice_generato += f"\n--- FILE: {path.name} ---\n{path.read_text(encoding='utf-8')}\n"

    if not codice_generato:
        _log("⚠️ Attenzione: Nessun file di codice sorgente trovato. Claude Code / Cursor ha già scritto il codice?")

    prompt_drift = f"""
    Sei un Revisore del Codice esperto.
    Il tuo compito è verificare il "Drift" (disallineamento) tra il contratto iniziale (REASONS Canvas) e il codice effettivamente scritto.

    --- CONTRATTO (CANVAS) ---
    {canvas_content}

    --- CODICE GENERATO ---
    {codice_generato if codice_generato else "(Nessun file di codice sorgente trovato.)"}

    Rispondi in modo conciso indicando:
    1. Se il codice rispetta le entità e i vincoli del Canvas (SI/NO).
    2. Eventuali difetti, allucinazioni o librerie inventate dal programmatore/IA che non erano previste.
    Se va tutto bene, rispondi con "✅ NESSUN DRIFT RILEVATO. Il codice è conforme."
    """

    _log("🧠 Analisi del codice in corso tramite LLM locale...")
    data = {"model": MODEL_NAME, "prompt": prompt_drift, "stream": False}
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})

    try:
        # Timeout esplicito: senza, una richiesta appesa bloccherebbe il thread del
        # server che esegue il controllo (le generazioni su CPU possono durare minuti).
        with urllib.request.urlopen(req, timeout=900) as response:
            result = json.loads(response.read().decode())
            report = result.get("response", "Errore nella valutazione.")
    except Exception as e:
        report = f"❌ Errore durante il check drift: {e}"

    _log("\n" + "=" * 50)
    _log("📊 REPORT DRIFT:")
    _log(report)
    _log("=" * 50 + "\n")
    return report


def _record_review_skip(change_dir: Path, reason: str) -> None:
    """Registra nel manifest della change (meta.json) che la canvas review è stata
    saltata e perché, così l'assenza del file è documentata e non ambigua."""
    meta_path = change_dir / "meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    meta["canvas_review"] = {
        "status": "skipped",
        "reason": reason,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # anche il fallimento della registrazione non deve bloccare l'archive


def archive_feature(feature_name, qdrant: QdrantClient | None = None, embed_model=None, emit=None) -> str:
    """Sposta la cartella in 'archive' e innesca la re-indicizzazione.

    Restituisce il log testuale dell'operazione (oltre a stamparlo/emetterlo). Le
    risorse pesanti possono essere iniettate dal server per riusare modello e client
    Qdrant già aperti; `emit` permette lo streaming SSE del progresso.
    """
    _emit = emit or print
    lines: list[str] = []

    def log(msg: str) -> None:
        _emit(msg)
        lines.append(msg)

    feature_folder = feature_name.replace(' ', '-').lower()
    log(f"\n📦 Avvio archiviazione per la feature: '{feature_folder}'...")

    source_dir = CHANGES_DIR / feature_folder
    archive_base_dir = CHANGES_DIR / "archive"
    target_dir = archive_base_dir / feature_folder

    if not source_dir.exists():
        log(f"❌ Errore: La cartella {source_dir} non esiste. Non c'è nulla da archiviare.")
        return "\n".join(lines)

    archive_base_dir.mkdir(parents=True, exist_ok=True)

    # Canvas che apprende: confronta il diff reale del codice della change con il
    # canvas e salva canvas_review.md nella cartella (che sta per essere archiviata);
    # una copia va in docs/03_changes_historical/ così la re-indicizzazione la ingloba
    # come contesto storico interrogabile. Se l'LLM non è raggiungibile la review viene
    # saltata con warning nel meta.json: l'archiviazione NON deve mai fallirne.
    try:
        log("🧾 Canvas review: confronto il codice della change con il canvas...")
        review, warning = generate_canvas_review(feature_folder, source_dir)
        if review is not None:
            (source_dir / REVIEW_FILENAME).write_text(review, encoding="utf-8")
            historical = DOCS_DIR / HISTORICAL_SUBDIR / f"{feature_folder}-canvas-review.md"
            historical.parent.mkdir(parents=True, exist_ok=True)
            historical.write_text(review, encoding="utf-8")
            log(f"✅ Canvas review salvata in {REVIEW_FILENAME} (+ copia storica in docs/{HISTORICAL_SUBDIR}/).")
        else:
            log(f"⚠️ Canvas review saltata: {warning}")
            _record_review_skip(source_dir, warning or "motivo sconosciuto")
    except Exception as e:  # difensivo: nessun problema della review blocca l'archive
        log(f"⚠️ Canvas review saltata per errore imprevisto: {e}")
        _record_review_skip(source_dir, str(e))

    try:
        shutil.move(str(source_dir), str(target_dir))
        log(f"✅ Feature archiviata con successo in: {target_dir}")

        log("🔄 Innesco la re-indicizzazione del Graph RAG locale...")
        build_graph_and_index(qdrant=qdrant, embed_model=embed_model, emit=_emit)
        log("✅ Re-indicizzazione completata! Il Graph RAG ha appreso la nuova feature.")

    except Exception as e:
        log(f"❌ Errore durante l'archiviazione: {e}")

    return "\n".join(lines)

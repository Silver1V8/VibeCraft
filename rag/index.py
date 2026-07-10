import argparse
import hashlib
import json
import os
import pickle
import re
import shutil
import sys
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Su Windows lo stdout usa cp1252 quando l'output è rediretto (log/servizio) e le
# emoji dei messaggi di stato lo farebbero crashare. Forza UTF-8 in modo robusto.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

import networkx as nx
import yaml
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

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL_NAME = "qwen2.5:7b" # Usa il modello testuale che state usando (es. llama3)

# Percorsi derivati dalla posizione di questo file (rag/)
RAG_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = RAG_DIR.parent
CONFIG_PATH = RAG_DIR / "rag_config.yaml"
DATABASE_DIR = RAG_DIR / "database"
GRAPH_SAVE_PATH = DATABASE_DIR / "graph.pkl"
# Qdrant in server mode (Docker): niente più storage locale a lock esclusivo.
QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
# Vettori ColBERT (uno per token) salvati come sidecar: troppo pesanti per lo
# storage JSON di Qdrant in modalità locale, ma indispensabili per il rerank
# token-per-token dei candidati migliori.
COLBERT_SAVE_PATH = DATABASE_DIR / "colbert.pkl"
# Sidecar dei chunk: chunk_id -> {doc_id, section, text}. Il retrieval lavora sui
# chunk (una sezione per punto), ma il testo dei chunk pertinenti va letto a runtime
# per il governed context: lo teniamo qui invece che nel payload Qdrant (che resta snello).
CHUNKS_SAVE_PATH = DATABASE_DIR / "chunks.pkl"
# Snapshot dell'indicizzazione: modello, conteggi e hash dei documenti al momento
# dell'indice, per rilevare quando docs/ è cambiato e l'indice è ormai "stale"
# (il drift di indicizzazione descritto nell'articolo, distinto dal drift canvas↔codice).
INDEX_MANIFEST_PATH = DATABASE_DIR / "index_manifest.json"

# Namespace fisso per derivare l'ID del punto Qdrant dal chunk_id in modo
# DETERMINISTICO (uuid5): lo stesso chunk_id produce sempre lo stesso id, così un
# re-upsert sovrascrive il punto esistente invece di duplicarlo. È il presupposto
# dell'indicizzazione incrementale idempotente (niente più id interi posizionali).
_POINT_ID_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def _point_id(chunk_id: str) -> str:
    """ID Qdrant deterministico e stabile per un chunk (uuid5 del chunk_id)."""
    return str(uuid.uuid5(_POINT_ID_NAMESPACE, chunk_id))

# Carica configurazione globale
with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
    config = yaml.safe_load(_f)

COLLECTION_NAME: str = config["vector_database"]["collection_name"]
EMBEDDING_MODEL: str = config["vector_database"]["embedding_model"]
DOCS_DIR: Path = PROJECT_ROOT / config["paths"]["docs_dir"].lstrip("./")
# Cartelle della pipeline Explore -> Canvas -> Propose (percorsi assoluti: le
# funzioni di drift/archiviazione vengono richiamate sia da CLI sia dal server,
# quindi non possono dipendere dalla working directory corrente).
CHANGES_DIR = PROJECT_ROOT / "changes"
CODE_DIR = PROJECT_ROOT / "code"

DENSE_DIM = 1024

def parse_markdown_file(filepath: str) -> tuple[dict, str]:
    """Estrae il Front Matter YAML e il corpo dal file Markdown."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    parts = content.split("---")
    if len(parts) >= 3:
        metadata = yaml.safe_load(parts[1]) or {}
        body = "---".join(parts[2:])
        return metadata, body
    return {}, content


# Estensioni indicizzabili. Il Markdown resta il formato ottimale (frontmatter +
# versionamento); gli altri sono loader opzionali che si attivano solo se la
# libreria è installata, senza introdurre dipendenze obbligatorie.
DOC_EXTS = (".md", ".txt", ".docx", ".xlsx", ".pdf")


def _read_docx(filepath: str) -> str:
    try:
        import docx  # python-docx
    except ImportError:
        print(f"  ⚠️ python-docx non installato: salto {filepath} (pip install python-docx)")
        return ""
    return "\n".join(p.text for p in docx.Document(filepath).paragraphs)


def _read_xlsx(filepath: str) -> str:
    try:
        import openpyxl
    except ImportError:
        print(f"  ⚠️ openpyxl non installato: salto {filepath} (pip install openpyxl)")
        return ""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    lines: list[str] = []
    for ws in wb.worksheets:
        lines.append(f"# Foglio: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _read_pdf(filepath: str) -> str:
    try:
        import pypdf
    except ImportError:
        print(f"  ⚠️ pypdf non installato: salto {filepath} (pip install pypdf)")
        return ""
    reader = pypdf.PdfReader(filepath)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def read_document(filepath_obj: Path) -> tuple[dict, str]:
    """Restituisce (frontmatter, corpo) per un documento. Il frontmatter YAML esiste
    solo nei .md; per gli altri formati è vuoto e si estrae solo il testo."""
    suffix = filepath_obj.suffix.lower()
    filepath = str(filepath_obj)
    if suffix == ".md":
        return parse_markdown_file(filepath)
    if suffix == ".txt":
        return {}, filepath_obj.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".docx":
        return {}, _read_docx(filepath)
    if suffix == ".xlsx":
        return {}, _read_xlsx(filepath)
    if suffix == ".pdf":
        return {}, _read_pdf(filepath)
    return {}, ""

def extract_entities(text: str) -> list[str]:
    """Trova tutte le entità racchiuse tra parentesi quadre, es. [UTENTE]."""
    return re.findall(r"\[(.*?)]", text)


# Heading di livello 2 (## Sezione): unità naturale di chunking dei design contract.
_H2_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")


def _slug(text: str, maxlen: int = 32) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:maxlen].strip("-") or "sez")


def chunk_markdown(rel_path: str, metadata: dict, body: str) -> list[dict]:
    """Divide un documento Markdown in chunk per sezione (heading di livello 2),
    ancorando ogni chunk al titolo del documento (contesto del frontmatter).

    Restituisce una lista di dict {chunk_id, doc_id, section, text} con id stabili
    e leggibili nel formato `doc_id#NN-slug`. Se il documento non ha heading `##`,
    diventa un unico chunk."""
    title = str(metadata.get("title") or rel_path)
    matches = list(_H2_RE.finditer(body))

    sections: list[tuple[str, str]] = []
    if not matches:
        sections.append(("(documento)", body))
    else:
        preamble = body[: matches[0].start()].strip()
        if preamble:
            sections.append(("(preambolo)", preamble))
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            sections.append((m.group(1).strip(), body[start:end].strip()))

    chunks: list[dict] = []
    for i, (heading, sec_body) in enumerate(sections):
        if not sec_body.strip():
            continue
        # Testo per l'embedding: ancorato al documento (titolo) e alla sezione,
        # così il chunk resta interpretabile fuori dal suo documento.
        text = f"# {title}\n## {heading}\n{sec_body}"
        chunks.append({
            "chunk_id": f"{rel_path}#{i:02d}-{_slug(heading)}",
            "doc_id": rel_path,
            "section": heading,
            "text": text,
        })

    if not chunks:  # fallback estremo: intero documento come singolo chunk
        chunks.append({"chunk_id": f"{rel_path}#00-doc", "doc_id": rel_path, "section": "(documento)", "text": body})
    return chunks

def add_frontmatter_edges(G: nx.DiGraph, doc_node_id: str, metadata: dict) -> int:
    """
    Indicizza le relazioni tipizzate dichiarate nel frontmatter YAML
    (graph_rag.edges: DERIVA_DA, VINCOLA, REFERENZIA, ...): archi semantici
    curati dall'autore del documento, molto più ricchi del semplice MENTIONS.
    """
    graph_rag = metadata.get("graph_rag") or {}
    edges = graph_rag.get("edges") or []
    added = 0
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        raw_target = edge.get("target")
        if not raw_target:
            continue
        target = str(raw_target)
        relation = str(edge.get("type", "RELATES_TO"))
        if target not in G:
            G.add_node(target, type="entity")
        G.add_edge(doc_node_id, target, relation=relation)
        added += 1
    return added


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
    G = nx.DiGraph()

    # Ricrea la collection Qdrant da zero ad ogni indicizzazione completa
    _ensure_collection(qdrant, recreate=True)

    points: list[PointStruct] = []
    all_chunks: list[dict] = []
    n_docs = 0

    # Prima passata: costruisce il grafo (a livello documento) e raccoglie i chunk
    # (a livello sezione). Scansione ricorsiva di tutti i formati indicizzabili.
    all_docs = sorted(p for p in DOCS_DIR.rglob("*") if p.is_file() and p.suffix.lower() in DOC_EXTS)
    for filepath_obj in all_docs:
        rel_path = filepath_obj.relative_to(DOCS_DIR).as_posix()
        metadata, body = read_document(filepath_obj)
        if not body.strip():
            _log(f"  (saltato, corpo vuoto o loader assente: {rel_path})")
            continue

        n_entities, typed_edges = _add_doc_to_graph(G, rel_path, metadata, body)

        # Il retrieval invece lavora sui chunk: una sezione per punto Qdrant
        doc_chunks = chunk_markdown(rel_path, metadata, body)
        for c in doc_chunks:
            c["metadata"] = metadata
        all_chunks.extend(doc_chunks)
        n_docs += 1
        _log(f"  Analizzato: {rel_path} — {n_entities} entità, {len(doc_chunks)} chunk, {typed_edges} relazioni tipizzate")

    # Seconda passata: vettorializza tutti i chunk in un batch.
    # Una sola forward pass di bge-m3 produce tutti e tre i tipi di vettore.
    colbert_store: dict[str, list] = {}
    chunks_store: dict[str, dict] = {}
    if all_chunks:
        _log(f"\nVettorializzazione di {len(all_chunks)} chunk (da {n_docs} documenti) con {EMBEDDING_MODEL} (dense + sparse + colbert)...")
        points, colbert_store, chunks_store, dense_vecs = _encode_chunks_to_points(embed_model, all_chunks)
        qdrant.upsert(collection_name=COLLECTION_NAME, points=points)

        # Fase Codice: indicizza i simboli sotto code/ e li collega al documento
        # padre del chunk più simile (archi IMPLEMENTS) + REFERENCES verso le entità.
        try:
            from code_index import add_code_graph, collect_code_symbols
            code_symbols = collect_code_symbols(CODE_DIR)
            parent_docs = [c["doc_id"] for c in all_chunks]  # padre allineato ai dense_vecs dei chunk
            n_code, n_impl = add_code_graph(G, code_symbols, embed_model, parent_docs, dense_vecs)
            if n_code:
                _log(f"🧩 Codice indicizzato: {n_code} simboli, {n_impl} archi IMPLEMENTS verso i documenti.")
            else:
                _log("🧩 Nessun simbolo di codice trovato sotto code/ (verrà indicizzato quando Claude scriverà il codice).")
        except Exception as e:
            _log(f"⚠️ Indicizzazione del codice saltata: {e}")

    # Salva il grafo, i multivettori ColBERT e il sidecar dei chunk su disco
    with open(GRAPH_SAVE_PATH, "wb") as f:
        pickle.dump(G, f)
    with open(COLBERT_SAVE_PATH, "wb") as f:
        pickle.dump(colbert_store, f)
    with open(CHUNKS_SAVE_PATH, "wb") as f:
        pickle.dump(chunks_store, f)

    _log(f"\n✅ Grafo salvato in: {GRAPH_SAVE_PATH}")
    _log(f"✅ Multivettori ColBERT salvati in: {COLBERT_SAVE_PATH}")
    _log(f"✅ Sidecar chunk salvato in: {CHUNKS_SAVE_PATH}")
    _log(f"📊 Grafo: {G.number_of_nodes()} nodi, {G.number_of_edges()} archi.")
    _log(f"📦 Qdrant: {len(points)} chunk (da {n_docs} documenti) nella collection '{COLLECTION_NAME}'.")

    write_index_manifest(len(points), G.number_of_nodes(), G.number_of_edges())
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


def write_index_manifest(points_count: int, nodes: int = 0, edges: int = 0) -> None:
    """Persiste lo snapshot dell'indice (config modello, conteggi, hash dei documenti)."""
    manifest = {
        "embedding_model": EMBEDDING_MODEL,
        "collection": COLLECTION_NAME,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "documents": points_count,
        "graph_nodes": nodes,
        "graph_edges": edges,
        "doc_hashes": _docs_hashes(),
    }
    INDEX_MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


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


def apply_incremental_indexing(
    plan: IndexPlan,
    docs_dir: Path,
    qdrant: QdrantClient,
    embed_model,
    graph: nx.DiGraph,
    colbert_store: dict,
    chunks_store: dict,
    emit=None,
) -> dict:
    """Esegue il piano del delta sugli oggetti passati (Qdrant + grafo + sidecar), mutandoli
    in-place. NON fa I/O su disco né gestisce il modello: quelli restano al chiamante
    (incremental_index), così questa funzione è deterministica e testabile con fake leggeri.

    Passi (idempotenti):
      1. purge dei chunk dei documenti modificati+cancellati da Qdrant (delete-by-filter),
         dai sidecar colbert/chunks e dei relativi nodi-documento dal grafo;
      2. (ri)vettorializzazione dei documenti nuovi+modificati e upsert con id deterministici,
         con re-inserimento dei nodi-documento nel grafo (code-link NON ricalibrati, per scelta).
    """
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
        _remove_doc_nodes_from_graph(graph, to_delete)
        _log(f"🗑️  Rimossi i chunk di {len(to_delete)} documenti (modificati/cancellati): {len(dead_chunks)} chunk purgati da Qdrant, sidecar e grafo.")

    # 2. (Ri)indicizzazione dei soli documenti nuovi/modificati
    upserted = 0
    if to_index:
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
            upserted = len(points)
        _log(f"➕ (Ri)indicizzati {len(to_index)} documenti → {upserted} chunk upsertati.")

    return {
        "planned": plan.as_dict(),
        "reindexed_docs": len(to_index),
        "deleted_docs": len(plan.deleted),
        "upserted_chunks": upserted,
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

    if manifest is not None and plan.is_noop:
        _log("✅ Nessun cambiamento in docs/: indice già aggiornato (no-op, nessuna scrittura).")
        return {"noop": True, "planned": plan.as_dict(), "reindexed_docs": 0, "deleted_docs": 0, "upserted_chunks": 0}

    _log(f"📋 Piano incrementale: {len(plan.new)} nuovi, {len(plan.modified)} modificati, "
         f"{len(plan.deleted)} cancellati, {len(plan.unchanged)} invariati (saltati).")

    # Il modello serve solo se c'è qualcosa da (ri)embeddare: un run di solo-delete
    # non deve pagare il caricamento di bge-m3 (minuti a freddo).
    if embed_model is None and plan.to_index():
        _log(f"Caricamento modello embedding: {EMBEDDING_MODEL} ...")
        embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)
    if qdrant is None:
        qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # L'incrementale NON ricrea la collection: la crea solo se assente, preservando i punti.
    _ensure_collection(qdrant, recreate=False)

    graph: nx.DiGraph = _load_pickle(GRAPH_SAVE_PATH, nx.DiGraph())
    colbert_store: dict = _load_pickle(COLBERT_SAVE_PATH, {})
    chunks_store: dict = _load_pickle(CHUNKS_SAVE_PATH, {})

    stats = apply_incremental_indexing(
        plan, DOCS_DIR, qdrant, embed_model, graph, colbert_store, chunks_store, emit=_log
    )

    # Persistenza: pickle + manifest coerente (documents = chunk totali correnti)
    with open(GRAPH_SAVE_PATH, "wb") as f:
        pickle.dump(graph, f)
    with open(COLBERT_SAVE_PATH, "wb") as f:
        pickle.dump(colbert_store, f)
    with open(CHUNKS_SAVE_PATH, "wb") as f:
        pickle.dump(chunks_store, f)
    write_index_manifest(len(chunks_store), graph.number_of_nodes(), graph.number_of_edges())

    _log(f"🧾 Manifest aggiornato: {len(chunks_store)} chunk, {graph.number_of_nodes()} nodi, {graph.number_of_edges()} archi.")
    _log("ℹ️  Code-link non ricalibrati in incrementale (scelta): esegui un full rebuild per aggiornarli.")

    if own_qdrant:
        qdrant.close()

    return stats


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

    try:
        shutil.move(str(source_dir), str(target_dir))
        log(f"✅ Feature archiviata con successo in: {target_dir}")

        log("🔄 Innesco la re-indicizzazione del Graph RAG locale...")
        build_graph_and_index(qdrant=qdrant, embed_model=embed_model, emit=_emit)
        log("✅ Re-indicizzazione completata! Il Graph RAG ha appreso la nuova feature.")

    except Exception as e:
        log(f"❌ Errore durante l'archiviazione: {e}")

    return "\n".join(lines)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestore indicizzazione, Drift e Archiviazione Graph RAG")
    parser.add_argument("--check-drift", type=str, metavar="FEATURE", help="Esegue il controllo drift per la feature specificata")
    parser.add_argument("--archive", type=str, metavar="FEATURE", help="Archivia la feature e re-indicizza il database")
    parser.add_argument("--index-status", action="store_true", help="Verifica se l'indice è aggiornato rispetto ai documenti in docs/")
    parser.add_argument("--incremental", action="store_true", help="Indicizzazione incrementale: (ri)indicizza solo i doc nuovi/modificati, rimuove i cancellati, salta gli invariati")

    args = parser.parse_args()

    if args.check_drift:
        check_drift(args.check_drift)
    elif args.archive:
        archive_feature(args.archive)
    elif args.index_status:
        status = index_status()
        print(json.dumps(status, ensure_ascii=False, indent=2))
    elif args.incremental:
        print("Avvio indicizzazione incrementale (delta rispetto al manifest)...\n")
        incremental_index()
    else:
        print("Avvio indicizzazione Fase 0 (Base)...\n")
        build_graph_and_index()
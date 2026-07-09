import argparse
import hashlib
import json
import pickle
import re
import shutil
import sys
import urllib.request
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
QDRANT_PATH = str(DATABASE_DIR / "qdrant_data")
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


def build_graph_and_index(qdrant: QdrantClient | None = None, embed_model=None, emit=None) -> None:
    """Esegue l'indicizzazione completa (Fase 0 e Fase 4).

    Le risorse pesanti (modello di embedding e client Qdrant) possono essere
    iniettate dall'esterno: quando il server FastAPI innesca la re-indicizzazione
    riusa quelle già caricate, evitando sia il ricaricamento del modello (minuti
    di CPU) sia il doppio lock sullo storage locale di Qdrant (che è esclusivo).

    `emit` è un callback di log (default: print) usato per lo streaming SSE del
    progresso verso l'interfaccia; se None si stampa su stdout come sempre.
    """
    _log = emit or print
    own_qdrant = qdrant is None
    if embed_model is None:
        _log(f"Caricamento modello embedding: {EMBEDDING_MODEL} ...")
        embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)
    if qdrant is None:
        qdrant = QdrantClient(path=QDRANT_PATH)
    G = nx.DiGraph()

    # Ricrea la collection Qdrant da zero ad ogni indicizzazione
    existing_collections = {c.name for c in qdrant.get_collections().collections}
    if COLLECTION_NAME in existing_collections:
        qdrant.delete_collection(COLLECTION_NAME)

    # Hybrid Search: la stessa collection ospita il vettore denso (semantica
    # generale) e quello sparso (match lessicali esatti su identificatori e
    # termini rari). I multivettori ColBERT vivono nel sidecar COLBERT_SAVE_PATH.
    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={"dense": VectorParams(size=DENSE_DIM, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams()},
    )

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

        doc_node_id = rel_path
        G.add_node(doc_node_id, type="document", **metadata)

        # Le entità sono estratte dall'intero documento (il grafo resta a livello doc)
        entities = extract_entities(body)
        for entity in entities:
            G.add_node(entity, type="entity")
            G.add_edge(doc_node_id, entity, relation="MENTIONS")

        typed_edges = add_frontmatter_edges(G, doc_node_id, metadata)

        # Il retrieval invece lavora sui chunk: una sezione per punto Qdrant
        doc_chunks = chunk_markdown(rel_path, metadata, body)
        for c in doc_chunks:
            c["metadata"] = metadata
        all_chunks.extend(doc_chunks)
        n_docs += 1
        _log(f"  Analizzato: {rel_path} — {len(entities)} entità, {len(doc_chunks)} chunk, {typed_edges} relazioni tipizzate")

    # Seconda passata: vettorializza tutti i chunk in un batch.
    # Una sola forward pass di bge-m3 produce tutti e tre i tipi di vettore.
    colbert_store: dict[str, list] = {}
    chunks_store: dict[str, dict] = {}
    if all_chunks:
        _log(f"\nVettorializzazione di {len(all_chunks)} chunk (da {n_docs} documenti) con {EMBEDDING_MODEL} (dense + sparse + colbert)...")
        output = embed_model.encode(
            [c["text"] for c in all_chunks],
            batch_size=12,
            max_length=8192,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=True,
        )
        dense_vecs = output["dense_vecs"]
        lexical_weights = output["lexical_weights"]
        colbert_vecs = output["colbert_vecs"]

        for point_id, (c, dense_vec, lex_w, col_vec) in enumerate(
            zip(all_chunks, dense_vecs, lexical_weights, colbert_vecs)
        ):
            sparse_vec = SparseVector(
                indices=[int(token_id) for token_id in lex_w.keys()],
                values=[float(w) for w in lex_w.values()],
            )
            points.append(
                PointStruct(
                    id=point_id,
                    vector={"dense": dense_vec.tolist(), "sparse": sparse_vec},
                    # doc_id = documento padre (nodo del grafo); chunk_id = chiave del retrieval
                    payload={"chunk_id": c["chunk_id"], "doc_id": c["doc_id"], "section": c["section"], **c["metadata"]},
                )
            )
            # fp16 per dimezzare l'occupazione su disco; il rerank riconverte al volo
            colbert_store[c["chunk_id"]] = col_vec.astype("float16")
            chunks_store[c["chunk_id"]] = {"doc_id": c["doc_id"], "section": c["section"], "text": c["text"]}

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


def index_status() -> dict:
    """Confronta gli hash correnti di docs/ con quelli del manifest per dire se l'indice
    è aggiornato o va rigenerato, elencando i documenti aggiunti/rimossi/modificati."""
    if not INDEX_MANIFEST_PATH.exists():
        return {"indexed": False, "stale": True, "reason": "manifest assente — indice mai costruito", "changed": []}
    try:
        manifest = json.loads(INDEX_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"indexed": False, "stale": True, "reason": f"manifest illeggibile: {exc}", "changed": []}

    old = manifest.get("doc_hashes", {})
    new = _docs_hashes()
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    modified = sorted(k for k in set(old) & set(new) if old[k] != new[k])
    changed = [f"+ {p}" for p in added] + [f"- {p}" for p in removed] + [f"~ {p}" for p in modified]
    return {
        "indexed": True,
        "stale": bool(changed),
        "created_at": manifest.get("created_at"),
        "embedding_model": manifest.get("embedding_model"),
        "documents": manifest.get("documents"),
        "changed": changed,
    }


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

    args = parser.parse_args()

    if args.check_drift:
        check_drift(args.check_drift)
    elif args.archive:
        archive_feature(args.archive)
    elif args.index_status:
        status = index_status()
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print("Avvio indicizzazione Fase 0 (Base)...\n")
        build_graph_and_index()
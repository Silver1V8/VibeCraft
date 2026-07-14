"""Configurazione centralizzata del package RAG: percorsi, connessione Qdrant,
provider LLM e costanti condivise. Unico punto di verità importato dal server FastAPI
(api/), dalla logica pura (core/) e dagli entrypoint CLI (index.py, server.py)."""
import logging
import os
from pathlib import Path

import yaml


def setup_logging() -> None:
    """Configurazione centrale del logging (chiamata dagli entrypoint server.py e
    index.py): formato con timestamp/livello/modulo, livello da VIBECRAFT_LOG_LEVEL
    (default INFO). `force=True` così una seconda chiamata (o i test) riconfigura."""
    level_name = os.environ.get("VIBECRAFT_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )

# Percorsi. NB: questo file vive in rag/core/, quindi la root del package (rag/) è
# due livelli sopra: parent (core/) -> parent (rag/).
RAG_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = RAG_DIR.parent
CONFIG_PATH = RAG_DIR / "rag_config.yaml"
DATABASE_DIR = RAG_DIR / "database"

# Formati artefatto CORRENTI (sicuri e ispezionabili): il grafo in node-link JSON,
# i vettori in .npz compressi (fp16), i metadati testuali in JSON sidecar. Sono
# l'UNICO formato scritto da core.artifacts.save_artifacts.
GRAPH_JSON_PATH = DATABASE_DIR / "graph.json"
COLBERT_NPZ_PATH = DATABASE_DIR / "colbert.npz"
CHUNKS_JSON_PATH = DATABASE_DIR / "chunks.json"
DENSE_NPZ_PATH = DATABASE_DIR / "dense.npz"
CODE_NPZ_PATH = DATABASE_DIR / "code.npz"
CODE_JSON_PATH = DATABASE_DIR / "code.json"

# Formati LEGACY (pickle): mantenuti solo in LETTURA per la retrocompatibilità.
# core.artifacts.load_artifacts ci ricade con un warning "re-indicizza" se i nuovi
# file non esistono ancora. Non vengono più SCRITTI.
GRAPH_SAVE_PATH = DATABASE_DIR / "graph.pkl"
COLBERT_SAVE_PATH = DATABASE_DIR / "colbert.pkl"
CHUNKS_SAVE_PATH = DATABASE_DIR / "chunks.pkl"
# Sidecar dei vettori densi per chunk-documento e per simbolo di codice: servono a
# ricalcolare gli archi spec<->codice (IMPLEMENTS/REFERENCES) in incrementale, per i
# soli nodi toccati, senza dover ri-embeddare ciò che non è cambiato.
DENSE_SAVE_PATH = DATABASE_DIR / "dense.pkl"
CODE_SAVE_PATH = DATABASE_DIR / "code.pkl"
# Snapshot dell'indicizzazione (modello, conteggi, hash dei documenti): serve a rilevare
# quando docs/ è cambiato e l'indice è "stale". NB: con il versionamento blue/green il
# manifest vive DENTRO la directory di versione (core.artifacts.manifest_path); questo
# percorso flat resta solo per il layout legacy pre-versionamento.
INDEX_MANIFEST_PATH = DATABASE_DIR / "index_manifest.json"
# Journal append-only (JSONL) dei job di reindex: ogni transizione di stato vi appende
# una riga col job serializzato, così lo storico sopravvive ai riavvii del server.
REINDEX_JOURNAL_PATH = DATABASE_DIR / "reindex_jobs.jsonl"
# Alert dei batch notturni (JSONL append-only: timestamp, script, errore): scritti dagli
# script scripts/nightly_* su fallimento, letti da GET /api/health (ultimo alert < 48h).
ALERTS_PATH = DATABASE_DIR / "alerts.jsonl"
TEMPLATES_DIR = RAG_DIR / "templates"
# Asset statici condivisi dai template (shared.css / shared.js): estratti dai
# *.unified.html per non duplicare CSS/JS, serviti come StaticFiles da FastAPI.
STATIC_DIR = RAG_DIR / "static"

# Qdrant in server mode (Docker): niente più storage locale a lock esclusivo.
QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")

with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
    config = yaml.safe_load(_f)

COLLECTION_NAME: str = config["vector_database"]["collection_name"]
EMBEDDING_MODEL: str = config["vector_database"]["embedding_model"]
LLM_PROVIDER: str = config["llm_settings"]["active_provider"]
LLM_MODEL: str = config["llm_settings"]["models"][LLM_PROVIDER]

# Scelta dell'implementazione dei parser di code_index per linguaggio
# (es. {"typescript": "treesitter"}); assente o "regex" = parser storico.
CODE_PARSERS: dict = config.get("code_parsers") or {}

# Configurazione pipeline Explore -> Canvas -> Propose (rag/changes/).
# NB: endpoint e modelli LLM ora vivono in core/llm.py (risoluzione per purpose).
CHANGES_DIR = PROJECT_ROOT / "changes"
CODE_DIR = PROJECT_ROOT / "code"
DOCS_DIR = PROJECT_ROOT / config["paths"]["docs_dir"].lstrip("./")

# Indicizzazione (usati da core/indexing.py e core/chunking.py, Fase 4).
DENSE_DIM = 1024
DOC_EXTS = (".md", ".txt", ".docx", ".xlsx", ".pdf")

# Generazioni con modelli grandi (es. qwen2.5:14b) su CPU possono richiedere diversi minuti:
# un timeout troppo corto interrompe la richiesta anche quando Ollama sta ancora generando.
OLLAMA_TIMEOUT_SECONDS = 900.0

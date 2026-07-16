"""Configurazione centralizzata del package RAG: percorsi, connessione Qdrant,
provider LLM e costanti condivise. Unico punto di verità importato dal server FastAPI
(api/), dalla logica pura (core/) e dagli entrypoint CLI (index.py, server.py)."""
import logging
import os
from pathlib import Path

import yaml


# Cartelle da escludere sempre dalla scansione del codice generato (dipendenze installate
# e output di build, mai scritte dall'agente e potenzialmente enormi): condivisa da
# code_index (estrazione simboli) e core.indexing (hash delta + drift check). Senza questo
# filtro un rglob("*") su un progetto con `npm install`/`dotnet build` già eseguiti include
# node_modules/bin/obj per intero — decine di migliaia di file che gonfiano sia il prompt
# di drift sia il grafo di codice (misurato: +16708 nodi/+131780 edge da un solo
# `npm install`, che rende /api/graph/all irrenderizzabile in browser).
CODE_EXCLUDED_DIRS = frozenset({
    "node_modules", ".git", ".next", "dist", "build", "coverage",
    ".venv", "venv", "__pycache__", ".turbo", ".cache",
    "bin", "obj", ".vs", "TestResults", "packages",
})


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
# Thinking dei modelli Ollama (rag_config.yaml → llm_settings.ollama_think). None = parametro
# non inviato (compatibilità con modelli senza campo `think`); false = disattivato, la scelta
# della pipeline (vedi commento nel config: risposte vuote quando il ragionamento esaurisce
# la generazione).
OLLAMA_THINK: bool | None = config["llm_settings"].get("ollama_think")
# Finestra di contesto richiesta a Ollama (llm_settings.ollama_num_ctx). None = default di
# Ollama (4096), che pero tronca silenziosamente dall'alto i prompt di canvas/propose
# (>4.300 token): vedi il commento nel config. Va inviata a ogni richiesta perche non e
# una proprieta del modello ma della singola generazione.
_num_ctx = config["llm_settings"].get("ollama_num_ctx")
OLLAMA_NUM_CTX: int | None = int(_num_ctx) if _num_ctx else None

# Scelta dell'implementazione dei parser di code_index per linguaggio
# (es. {"typescript": "treesitter"}); assente o "regex" = parser storico.
CODE_PARSERS: dict = config.get("code_parsers") or {}

# Ri-ponderazione per autorità nel retrieval (core/retrieval.py). Default = calibrazione a
# mano storica; sovrascrivibili in rag_config.yaml (authority.*) e ricalibrabili sul golden set
# con eval/calibrate_authority.py. Tenuti separati così la calibrazione tocca solo il config.
_authority_cfg: dict = config.get("authority") or {}
AUTHORITY_CLASS_WEIGHTS: dict = _authority_cfg.get("class_weights") or {
    "IRON_MEMORY": 1.0, "AUTHORIZATION_POLICY": 0.9, "DATA_DICTIONARY": 0.7, "METHODOLOGY": 0.5,
}
AUTHORITY_DEFAULT_WEIGHT: float = float(_authority_cfg.get("default_weight", 0.4))
AUTHORITY_ARCHIVED_DECAY: float = float(_authority_cfg.get("archived_decay", 0.3))
AUTHORITY_BOOST_ALPHA: float = float(_authority_cfg.get("boost_alpha", 0.4))

# Contesto governato di Canvas/Propose: quante sezioni prendere dal ramo di dominio e da
# quello tecnico (rag_config.yaml → retrieval.*). Vedi retrieve_governed_context_multi.
_retrieval_cfg: dict = config.get("retrieval") or {}
GOVERNED_MAX_CHUNKS: int = int(_retrieval_cfg.get("governed_max_chunks", 8))
TECH_MAX_CHUNKS: int = int(_retrieval_cfg.get("tech_max_chunks", 3))
# Template della query del ramo tecnico ('{dev_type}' = ambito, reso a parole). Vive nel
# config perché è vocabolario di progetto, non logica: su un progetto con altra tassonomia
# (o altra lingua) si riscrive qui senza toccare il codice. Vedi pipeline.build_tech_query.
TECH_QUERY_TEMPLATE: str = str(_retrieval_cfg.get("tech_query") or "")
# Campo del payload in cui un documento dichiara il proprio ambito (default: i 'tags' del
# frontmatter). Il ramo tecnico ci filtra sopra col dev_type scelto: senza, le spec
# tecnologiche di ambiti diversi — quasi gemelle — si confondono nel ranking. Vuoto =
# nessuno scoping. Vedi retrieval.scope_tag_filter e pipeline.dev_type_tag_variants.
TECH_SCOPE_TAG_KEY: str = str(_retrieval_cfg.get("tech_scope_tag_key") or "")

# Eval-gate continuo sulla promozione blue/green (core/eval_gate.py) + golden set del retrieval.
_eval_gate_cfg: dict = config.get("eval_gate") or {}
EVAL_GATE_ENABLED: bool = bool(_eval_gate_cfg.get("enabled", True))
EVAL_GATE_K: int = int(_eval_gate_cfg.get("k", 10))
EVAL_GATE_MIN_RECALL: float = float(_eval_gate_cfg.get("min_recall", 0.90))
EVAL_GATE_BLOCKING: bool = bool(_eval_gate_cfg.get("blocking", True))
GOLDEN_SET_PATH = RAG_DIR / "eval" / "golden_set.yaml"

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
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("VIBECRAFT_OLLAMA_TIMEOUT_SECONDS", "1800"))

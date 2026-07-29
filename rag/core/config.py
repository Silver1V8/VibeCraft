"""Configurazione centralizzata del package RAG: percorsi, connessione Qdrant,
provider LLM e costanti condivise. Unico punto di verità importato dal server FastAPI
(api/), dalla logica pura (core/) e dagli entrypoint CLI (index.py, server.py)."""
import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

# Segreti locali di sviluppo (VIBECRAFT_API_KEY ecc.): caricati da rag/.env.local se
# presente, PRIMA che qualunque modulo legga os.environ (in particolare api/deps.py,
# importato più sotto nella catena). Così il valore è disponibile indipendentemente da
# come viene lanciato il processo (uv run, PyCharm/IDE run config, python diretto...),
# non solo da uno script wrapper che esporta l'env a mano. override=False: un env var
# già impostato esplicitamente dal chiamante vince sempre su .env.local.
load_dotenv(Path(__file__).resolve().parent.parent / ".env.local", override=False)


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


class BudgetSettings(BaseModel):
    """Blocco `llm_settings.budget`: tetto di spesa GIORNALIERO (UTC) sulle chiamate
    Anthropic, con degradazione automatica su un provider locale quando è raggiunto.
    Il blocco è opzionale e, se assente, il guard è disattivato (vedi core/llm.py:
    `_budget_fallback`). `daily_usd` a null vale come blocco assente."""

    model_config = ConfigDict(extra="allow")

    daily_usd: float | None = None
    fallback_provider: str = "ollama"
    # File JSON in cui persistere il contatore ({"day": "YYYY-MM-DD", "usd": ...}),
    # relativo a rag/ se non assoluto. Assente = contatore solo in-memory, azzerato
    # a ogni riavvio del processo.
    spend_file: str | None = None


class LLMSettings(BaseModel):
    """Blocco `llm_settings` di rag_config.yaml, tipato. È l'UNICO blocco validato: gli
    altri (retrieval, authority, eval_gate, intake, code_parsers...) restano dict, letti
    con .get() e default espliciti — lì un valore mancante degrada, qui invece un typo
    faceva esplodere una KeyError DENTRO una richiesta (resolve() in core/llm.py), cioè
    nel punto peggiore. Con questo modello un config malformato fallisce al BOOT.

    `extra="allow"`: il formato del file non cambia e chiavi future/sperimentali non
    devono far fallire l'avvio."""

    model_config = ConfigDict(extra="allow")

    active_provider: str
    models: dict[str, str] = {}
    purposes: dict[str, dict] | None = None
    ollama_think: bool | None = None
    ollama_num_ctx: int | None = None
    # Prezzi per-modello (USD/milione di token) usati solo per stimare cost_usd nel log
    # delle chiamate Anthropic: sezione opzionale, vedi core/llm.py:_anthropic_pricing.
    pricing: dict[str, dict[str, float]] | None = None
    # Tetto di spesa giornaliero sulle chiamate Anthropic: sezione opzionale, assente =
    # guard disattivato. Vedi core/llm.py:_budget_fallback.
    budget: BudgetSettings | None = None

    @model_validator(mode="after")
    def _coerenza_al_boot(self, info):
        """Controlli che valgono SOLO alla validazione di avvio (context={"boot": True}),
        non alla ri-validazione per richiesta fatta da core.llm.resolve(): lì un
        `models` vuoto deve continuare a produrre l'LLMError storico, non un errore di
        validazione (retrocompatibilità sui messaggi d'errore)."""
        if not (info.context or {}).get("boot"):
            return self
        if not self.models:
            raise ValueError(
                "llm_settings.models è vuoto: serve almeno una voce provider -> modello.")
        if self.active_provider not in self.models:
            raise ValueError(
                f"llm_settings.models non ha un modello per active_provider "
                f"'{self.active_provider}' (presenti: {', '.join(sorted(self.models)) or 'nessuno'}).")
        return self


def validate_llm_settings(raw, *, boot: bool = False) -> LLMSettings:
    """Valida il blocco llm_settings grezzo (dict da YAML) restituendo il modello tipato.
    Solleva pydantic.ValidationError con un messaggio leggibile se manca active_provider
    o se i tipi non tornano. Il contratto è deliberatamente ASIMMETRICO:
    · boot=True  → aggiunge i controlli di coerenza (models non vuoto e con una voce per
      active_provider): usato solo all'avvio, fallisce presto e forte;
    · boot=False → validazione di soli tipi; i casi di configurazione incompleta restano
      a core.llm.resolve(), che ne produce i messaggi LLMError storici.
    L'asimmetria è bloccata dai test `test_contratto_*` in tests/test_llm.py."""
    return LLMSettings.model_validate(raw or {}, context={"boot": boot} if boot else None)


try:
    LLM_SETTINGS: LLMSettings = validate_llm_settings(config.get("llm_settings"), boot=True)
except ValidationError as _e:
    raise RuntimeError(
        f"Blocco 'llm_settings' non valido in {CONFIG_PATH}:\n{_e}"
    ) from _e

LLM_PROVIDER: str = LLM_SETTINGS.active_provider
LLM_MODEL: str = LLM_SETTINGS.models[LLM_PROVIDER]
# Thinking dei modelli Ollama (rag_config.yaml → llm_settings.ollama_think). None = parametro
# non inviato (compatibilità con modelli senza campo `think`); false = disattivato, la scelta
# della pipeline (vedi commento nel config: risposte vuote quando il ragionamento esaurisce
# la generazione).
OLLAMA_THINK: bool | None = LLM_SETTINGS.ollama_think
# Finestra di contesto richiesta a Ollama (llm_settings.ollama_num_ctx). None = default di
# Ollama (4096), che pero tronca silenziosamente dall'alto i prompt di canvas/propose
# (>4.300 token): vedi il commento nel config. Va inviata a ogni richiesta perche non e
# una proprieta del modello ma della singola generazione. 0/null = parametro non inviato.
OLLAMA_NUM_CTX: int | None = LLM_SETTINGS.ollama_num_ctx or None

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
# Codice implementante iniettato nel contesto di /ask: risalendo gli archi IMPLEMENTS
# (codice -> sezione) dalle sezioni recuperate, l'LLM vede la spec E la sua implementazione
# reale. È il ponte fra il codice indicizzato nel grafo e la ricerca semantica (che interroga
# solo Qdrant/documenti). max=0 disattiva; min_weight filtra gli archi deboli. Vedi
# retrieval.collect_implementing_code e api/routes_retrieval.ask_rag.
CODE_CONTEXT_MAX_SNIPPETS: int = int(_retrieval_cfg.get("code_context_max_snippets", 6))
CODE_CONTEXT_MIN_WEIGHT: float = float(_retrieval_cfg.get("code_context_min_weight", 0.5))
# Ricerca semantica DIRETTA sui simboli di codice (retrieval.search_code_symbols): coseno
# fra la domanda e i vettori densi dei simboli (sidecar code.npz). È il ramo che rende il
# codice interrogabile di per sé, senza passare dai documenti — il ponte IMPLEMENTS sopra
# trova solo il codice agganciato alle sezioni recuperate. max=0 disattiva il ramo.
CODE_SEARCH_MAX_SNIPPETS: int = int(_retrieval_cfg.get("code_search_max_snippets", 8))
CODE_SEARCH_MIN_SCORE: float = float(_retrieval_cfg.get("code_search_min_score", 0.45))
# Quanti simboli al massimo può contribuire uno STESSO file al ramo semantico: i simboli
# sono a grana fine e un file autogenerato (proxy WCF, client di servizio) occuperebbe da
# solo tutte le posizioni con varianti della stessa riga. 0 = nessun limite.
CODE_SEARCH_MAX_PER_FILE: int = int(_retrieval_cfg.get("code_search_max_per_file", 2))
# Tetto COMPLESSIVO sui blocchi di codice iniettati in /ask dai due rami sommati
# (retrieval.merge_code_context): senza, il contesto crescerebbe con la somma dei tetti.
CODE_CONTEXT_TOTAL_SNIPPETS: int = int(
    _retrieval_cfg.get("code_context_total_snippets",
                       CODE_SEARCH_MAX_SNIPPETS + CODE_CONTEXT_MAX_SNIPPETS)
)

# Eval-gate continuo sulla promozione blue/green (core/eval_gate.py) + golden set del retrieval.
_eval_gate_cfg: dict = config.get("eval_gate") or {}
EVAL_GATE_ENABLED: bool = bool(_eval_gate_cfg.get("enabled", True))
EVAL_GATE_K: int = int(_eval_gate_cfg.get("k", 10))
EVAL_GATE_MIN_RECALL: float = float(_eval_gate_cfg.get("min_recall", 0.90))
EVAL_GATE_BLOCKING: bool = bool(_eval_gate_cfg.get("blocking", True))
# M6 (esperimento, default OFF): advisory di recall post-promozione sui job INCREMENTALI.
# La regola di decisione (tenere/rimuovere dopo 2 settimane) è documentata sopra il flag
# in rag_config.yaml e su core.eval_gate.run_incremental_advisory.
EVAL_GATE_INCREMENTAL_ADVISORY: bool = bool(_eval_gate_cfg.get("incremental_advisory", False))
GOLDEN_SET_PATH = RAG_DIR / "eval" / "golden_set.yaml"

# Configurazione pipeline Explore -> Canvas -> Propose (rag/changes/).
# NB: endpoint e modelli LLM ora vivono in core/llm.py (risoluzione per purpose).
CHANGES_DIR = PROJECT_ROOT / "changes"
CODE_DIR = PROJECT_ROOT / "code"
DOCS_DIR = PROJECT_ROOT / config["paths"]["docs_dir"].lstrip("./")

# Indicizzazione (usati da core/indexing.py e core/chunking.py, Fase 4).
DENSE_DIM = 1024
DOC_EXTS = (".md", ".txt", ".docx", ".xlsx", ".pdf")

# Intake & Import (rag_config.yaml → intake.*): ingresso controllato di documenti/progetti
# nell'area di staging, in attesa di review esplicita prima di entrare in docs/ o code/ (piano:
# docs/00_meta_governance/piano_intake_import.md). Vedi core/intake.py per lo scaffold (S0) e
# core/intake_convert.py / core/project_import.py per le fasi successive del piano.
_intake_cfg: dict = config.get("intake") or {}
# Radice dell'area di staging, relativa a RAG_DIR (default: database/staging, accanto agli
# altri artefatti di database/).
INTAKE_STAGING_DIR = RAG_DIR / str(_intake_cfg.get("staging_dir") or "database/staging").lstrip("./")
# Formati sorgente accettati in ingresso (documenti): il resto viene rifiutato a monte, prima
# di leggere il contenuto.
INTAKE_ALLOWED_FORMATS: tuple[str, ...] = tuple(
    _intake_cfg.get("allowed_formats")
    or ["md", "pdf", "docx", "pptx", "xlsx", "xls",
        "html", "htm", "txt", "csv", "json", "xml", "epub", "msg"]
)
INTAKE_MAX_UPLOAD_MB: int = int(_intake_cfg.get("max_upload_mb", 25))
# Authority scritta nel frontmatter dei documenti approvati dallo staging (S2): sotto i
# documenti autorati a mano, sopra il default implicito del retrieval (0.4).
INTAKE_DEFAULT_AUTHORITY: float = float(_intake_cfg.get("default_authority", 0.70))
# Tetto ai file generabili in un'unica richiesta di generazione via Ollama (core/doc_generation.py).
INTAKE_GENERATION_MAX_FILES: int = int(_intake_cfg.get("generation_max_files", 5))
# Raffinazione LLM dei documenti in staging (core/intake_refine.py, passo opt-in del ciclo
# di review): dimensione della finestra inviata al modello e forbice di lunghezza ammessa
# per la riscrittura (sotto il minimo ha riassunto, sopra il massimo ha commentato).
_intake_refine_cfg: dict = _intake_cfg.get("refine") or {}
INTAKE_REFINE_WINDOW_CHARS: int = int(_intake_refine_cfg.get("window_chars", 5000))
INTAKE_REFINE_MIN_OUTPUT_RATIO: float = float(_intake_refine_cfg.get("min_output_ratio", 0.45))
INTAKE_REFINE_MAX_OUTPUT_RATIO: float = float(_intake_refine_cfg.get("max_output_ratio", 2.0))
# Tetto alternativo per le fonti DENSE (alberi di classi, elenchi di campi, tabelle
# sfaldate dal PDF): righe cortissime che, diventando righe di tabella con una colonna di
# descrizione, si allungano legittimamente di 3-4×. Una fonte è densa se la lunghezza media
# delle sue righe non vuote sta sotto INTAKE_REFINE_DENSE_LINE_CHARS.
INTAKE_REFINE_MAX_OUTPUT_RATIO_DENSE: float = float(
    _intake_refine_cfg.get("max_output_ratio_dense", 4.0))
INTAKE_REFINE_DENSE_LINE_CHARS: int = int(_intake_refine_cfg.get("dense_line_chars", 40))

# Base URL di Ollama (host:porta), sovrascrivibile via env per setup non locali
# (Docker, host GPU remoto). core/llm.py ne deriva l'endpoint /api/generate e
# routes_health il ping /api/tags: nessun altro punto del codice deve contenere
# un URL Ollama letterale.
OLLAMA_URL = os.environ.get("VIBECRAFT_OLLAMA_URL", "http://127.0.0.1:11434")

# Generazioni con modelli grandi (es. qwen2.5:14b) su CPU possono richiedere diversi minuti:
# un timeout troppo corto interrompe la richiesta anche quando Ollama sta ancora generando.
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("VIBECRAFT_OLLAMA_TIMEOUT_SECONDS", "1800"))

# Dimensione di default delle fette con cui core.indexing.build_graph_and_index invia i
# punti a Qdrant (override: env VIBECRAFT_QDRANT_UPSERT_BATCH, letta a ogni chiamata —
# stesso pattern di VIBECRAFT_INDEX_KEEP in core.artifacts._keep_from_env). Un unico
# upsert monolitico su migliaia di punti rischia il timeout gRPC/HTTP lato client; a
# fette il rischio si sposta a "quali fette sono già arrivate", non se arrivano.
DEFAULT_QDRANT_UPSERT_BATCH = 256


def qdrant_upsert_batch_from_env() -> int:
    """Quanti punti per chiamata upsert Qdrant (env VIBECRAFT_QDRANT_UPSERT_BATCH,
    default 256, mai meno di 1)."""
    raw = os.environ.get("VIBECRAFT_QDRANT_UPSERT_BATCH", "")
    try:
        batch = int(raw) if raw else DEFAULT_QDRANT_UPSERT_BATCH
    except ValueError:
        logging.getLogger(__name__).warning(
            "VIBECRAFT_QDRANT_UPSERT_BATCH non numerica (%r): uso il default %d.",
            raw, DEFAULT_QDRANT_UPSERT_BATCH)
        batch = DEFAULT_QDRANT_UPSERT_BATCH
    return max(1, batch)

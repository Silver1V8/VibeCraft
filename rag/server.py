import os
import re
import sys
import json
import time
import queue
import pickle
import httpx
import uvicorn
import threading
import numpy as np
import networkx as nx

# Forza UTF-8 su stdout/stderr: le emoji dei log crasherebbero su console cp1252
# (Windows) quando l'output è rediretto verso un file o un servizio.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from typing import Any
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import SparseVector
from FlagEmbedding import BGEM3FlagModel

from agent_bridge import AGENT_MODES, run_agent_streaming
from index import archive_feature, check_drift, index_status
from core import graph_ops, retrieval
from core.graph_ops import bfs_expand, build_context
from core.retrieval import (
    AUTHORITY_CLASS_WEIGHTS,
    _authority_weight,
    _hit_chunk_id,
    _hit_doc_id,
    call_llm,
)

# ---------------------------------------------------------------------------
# Configurazione — centralizzata in core/config.py (unico punto di verità)
# ---------------------------------------------------------------------------
from core.config import (  # noqa: E402  (import dopo il blocco UTF-8 di sys.stdout)
    CHANGES_DIR,
    CHUNKS_SAVE_PATH,
    CODE_DIR,
    COLBERT_SAVE_PATH,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    GRAPH_SAVE_PATH,
    LLM_MODEL,
    LLM_PROVIDER,
    OLLAMA_TIMEOUT_SECONDS,
    PIPELINE_MODEL_NAME,
    PIPELINE_OLLAMA_URL,
    PROJECT_ROOT,
    QDRANT_API_KEY,
    QDRANT_URL,
    TEMPLATES_DIR,
)

# ---------------------------------------------------------------------------
# Autenticazione API — bypass su localhost, X-API-Key per il resto
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("VIBECRAFT_API_KEY")


def require_api_key(request: Request) -> None:
    """Lascia passare le richieste da localhost; per tutte le altre, richiede
    l'header X-API-Key (env VIBECRAFT_API_KEY). Se la chiave non è configurata,
    le richieste non locali vengono sempre rifiutate (fail-closed)."""
    client_host = request.client.host if request.client else None
    if client_host in ("127.0.0.1", "::1"):
        return
    if not API_KEY or request.headers.get("X-API-Key") != API_KEY:
        raise HTTPException(status_code=401, detail="API key richiesta per accesso non locale.")


# ---------------------------------------------------------------------------
# Stato globale del server (popolato durante il lifespan)
# NB: accesso non protetto da lock — vedi nota HARDENING #3 in fondo al file.
# ---------------------------------------------------------------------------
state: dict = {
    "graph": None,
    "qdrant": None,
    "embed_model": None,
    "rule_descriptions": {},
    "colbert_store": {},
    "chunks": {},
}


def load_rule_descriptions() -> dict[str, str]:
    """
    Scansiona tutti i file spec_*.md in docs/ (ricorsivamente) ed estrae le descrizioni
    di regole e termini di glossario nel formato `[CHIAVE]`: <testo>.
    Restituisce un dizionario { "REGOLA-AUTH-01": "...", "UTENTE": "...", ... }.
    """
    descriptions: dict[str, str] = {}
    pattern = re.compile(r"`\[([A-Z0-9][A-Z0-9_\- ]*)]`:\s*(.+)")
    docs_dir = PROJECT_ROOT / "docs"
    # Scansiona tutti i .md: le descrizioni possono vivere in qualsiasi documento
    # del knowledge base, non solo nei file spec_*.md.
    for spec_file in sorted(docs_dir.rglob("*.md")):
        try:
            content = spec_file.read_text(encoding="utf-8")
            for m in pattern.finditer(content):
                key = m.group(1).strip()
                descriptions[key] = m.group(2).strip()
        except Exception as exc:
            print(f"Attenzione: impossibile leggere {spec_file}: {exc}")
    print(f"Entità indicizzate ({len(descriptions)}): {sorted(descriptions.keys())}")
    return descriptions


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Carica le risorse pesanti al boot e le libera allo shutdown."""
    print(f"Caricamento modello embedding: {EMBEDDING_MODEL} ...")
    state["embed_model"] = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)

    print(f"Connessione a Qdrant (server mode): {QDRANT_URL} ...")
    state["qdrant"] = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    print(f"Caricamento grafo NetworkX da {GRAPH_SAVE_PATH} ...")
    if not GRAPH_SAVE_PATH.exists():
        raise RuntimeError(
            "graph.pkl non trovato. Esegui prima 'python index.py' per indicizzare."
        )
    with open(GRAPH_SAVE_PATH, "rb") as f:
        state["graph"] = pickle.load(f)
    state["_graph_mtime"] = GRAPH_SAVE_PATH.stat().st_mtime  # baseline per l'auto-reload

    g: nx.DiGraph = state["graph"]
    print(f"Grafo caricato: {g.number_of_nodes()} nodi, {g.number_of_edges()} archi.")

    # Multivettori ColBERT per il rerank token-per-token (sidecar dell'indice)
    if COLBERT_SAVE_PATH.exists():
        with open(COLBERT_SAVE_PATH, "rb") as f:
            state["colbert_store"] = pickle.load(f)
        print(f"Multivettori ColBERT caricati: {len(state['colbert_store'])} chunk.")
    else:
        print("Attenzione: colbert.pkl non trovato — rerank ColBERT disattivato. Riesegui 'python index.py'.")

    # Sidecar dei chunk (chunk_id -> testo della sezione) per il governed context
    if CHUNKS_SAVE_PATH.exists():
        with open(CHUNKS_SAVE_PATH, "rb") as f:
            state["chunks"] = pickle.load(f)
        print(f"Chunk caricati: {len(state['chunks'])} sezioni.")
    else:
        print("Attenzione: chunks.pkl non trovato — governed context degradato. Riesegui 'python index.py'.")

    print("Caricamento descrizioni regole dai file spec...")
    state["rule_descriptions"] = load_rule_descriptions()
    print("Server pronto.\n")

    yield  # il server è in esecuzione

    print("Shutdown: rilascio risorse.")
    state["qdrant"].close()


app = FastAPI(title="HARO Graph-RAG Console", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Modelli di request / response
# ---------------------------------------------------------------------------
class AskQuery(BaseModel):
    question: str
    top_k: int = 5
    bfs_depth: int = 2


class ExploreTurnRequest(BaseModel):
    feature_name: str
    history: str = ""
    user_input: str
    dev_type: str = ""


class ExploreSaveRequest(BaseModel):
    feature_name: str
    interview_log: str
    dev_type: str = ""


class PipelineFileSaveRequest(BaseModel):
    feature: str
    name: str
    content: str


class CanvasGenerateRequest(BaseModel):
    feature_name: str
    dev_type: str = ""


class ProposeGenerateRequest(BaseModel):
    feature_folder: str
    dev_type: str = ""


class AgentRunRequest(BaseModel):
    prompt: str
    mode: str = "suggest"   # suggest | agentic | oneshot
    model: str = "sonnet"   # alias Claude: sonnet | opus | haiku


class DriftCheckRequest(BaseModel):
    feature: str


class ArchiveRequest(BaseModel):
    feature: str


class ValidateRequest(BaseModel):
    feature: str


# ---------------------------------------------------------------------------
# Funzioni di supporto
# ---------------------------------------------------------------------------
# _hit_doc_id, _hit_chunk_id, _authority_weight, AUTHORITY_CLASS_WEIGHTS e call_llm vivono
# ora in core/retrieval.py e sono re-importati in cima al file. hybrid_search resta qui come
# wrapper sottile che inietta nel core le risorse di runtime lette dallo `state` del server.
def hybrid_search(question: str, top_k: int) -> list[dict]:
    """Wrapper: inietta qdrant/embed_model/colbert_store dallo stato del server in core.retrieval."""
    return retrieval.hybrid_search(
        question, top_k,
        qdrant=state["qdrant"], embed_model=state["embed_model"],
        colbert_store=state["colbert_store"],
    )


# ---------------------------------------------------------------------------
# Pipeline Explore -> Canvas -> Propose (equivalente HTTP di explore.py,
# canvas.py e propose.py, con checkpoint di approvazione tra le fasi)
# ---------------------------------------------------------------------------
def slugify_feature(feature_name: str) -> str:
    return feature_name.strip().replace(" ", "-").lower()


async def call_ollama_generate(prompt: str) -> str:
    """Chiama Ollama in modalità /api/generate in modo ASINCRONO (httpx.AsyncClient),
    per non bloccare l'event loop di FastAPI durante le generazioni (che su CPU durano
    minuti). Semantica, timeout ed error handling invariati rispetto alla versione sync."""
    data = {"model": PIPELINE_MODEL_NAME, "prompt": prompt, "stream": False}
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
            response = await client.post(PIPELINE_OLLAMA_URL, json=data)
        if response.status_code == 404:
            return f"[ERRORE OLLAMA]: Il modello '{PIPELINE_MODEL_NAME}' non è stato trovato. Esegui 'ollama pull {PIPELINE_MODEL_NAME}'."
        response.raise_for_status()
        return response.json().get("response", "Errore nella generazione.")
    except httpx.ConnectError:
        return "[ERRORE DI CONNESSIONE]: Impossibile raggiungere Ollama. Assicurati che l'applicazione Ollama sia avviata."
    except httpx.TimeoutException:
        return "[ERRORE DI TIMEOUT]: Ollama sta impiegando troppo tempo a rispondere."
    except Exception as e:
        return f"[ERRORE GENERICO OLLAMA]: {str(e)}"


# _select_governed_chunks/_docs e retrieve_governed_context sono ora in core/retrieval.py.
# Qui restano wrapper sottili che iniettano nel core le risorse di runtime dallo `state`,
# preservando le firme storiche usate da pipeline e route handler (spariranno in Fase 5).
def _select_governed_chunks(question: str, top_k: int = 10, max_chunks: int = 8,
                            results: list | None = None) -> list[dict]:
    """Wrapper: inietta grafo/qdrant/embed_model/colbert_store dallo stato in core.retrieval."""
    return retrieval.select_governed_chunks(
        question, graph=state.get("graph"), results=results, top_k=top_k, max_chunks=max_chunks,
        qdrant=state.get("qdrant"), embed_model=state.get("embed_model"),
        colbert_store=state.get("colbert_store"),
    )


def _select_governed_docs(question: str, top_k: int = 10, max_docs: int = 4,
                          results: list | None = None) -> list[str]:
    """Wrapper: inietta grafo/qdrant/embed_model/colbert_store dallo stato in core.retrieval."""
    return retrieval.select_governed_docs(
        question, graph=state.get("graph"), results=results, top_k=top_k, max_docs=max_docs,
        qdrant=state.get("qdrant"), embed_model=state.get("embed_model"),
        colbert_store=state.get("colbert_store"),
    )


def retrieve_governed_context(question: str, top_k: int = 10, max_chunks: int = 8,
                              max_chars_per_chunk: int = 3000) -> str:
    """Wrapper: inietta grafo/chunks/qdrant/embed_model/colbert_store dallo stato in core.retrieval."""
    return retrieval.retrieve_governed_context(
        question, graph=state.get("graph"), chunks_store=state.get("chunks", {}),
        qdrant=state.get("qdrant"), embed_model=state.get("embed_model"),
        colbert_store=state.get("colbert_store"),
        top_k=top_k, max_chunks=max_chunks, max_chars_per_chunk=max_chars_per_chunk,
    )


def feature_dir(feature_name: str) -> Path:
    folder = slugify_feature(feature_name)
    path = CHANGES_DIR / folder
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_dev_types() -> list[str]:
    """Elenca le sottocartelle di 'code/' (backend, frontend, logicAgent, ...) da proporre in tendina."""
    if not CODE_DIR.exists():
        return []
    return sorted(p.name for p in CODE_DIR.iterdir() if p.is_dir() and not p.name.startswith("."))


def save_dev_type(folder: Path, dev_type: str) -> None:
    """Persiste il tipo di sviluppo scelto in changes/<feature>/meta.json, per ripristinarlo al resume."""
    if not dev_type:
        return
    meta_path = folder / "meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    meta["dev_type"] = dev_type
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def load_dev_type(folder: Path) -> str:
    """Legge il tipo di sviluppo salvato per la feature, se presente."""
    meta_path = folder / "meta.json"
    if not meta_path.exists():
        return ""
    try:
        return json.loads(meta_path.read_text(encoding="utf-8")).get("dev_type", "")
    except Exception:
        return ""


def build_final_prompt(folder_name: str, dev_type: str = "") -> str:
    """Costruisce il prompt finale per Claude Code, scoperto sull'unica cartella code/<dev_type>
    se una tipologia di sviluppo è stata indicata, altrimenti con la distribuzione multi-cartella storica."""
    base = (
        f"Leggi rigorosamente i file 'changes/{folder_name}/canvas.md' e 'changes/{folder_name}/spec.md'. "
        f"Implementa la funzionalità descritta attenendoti esclusivamente all'approccio tecnico del canvas "
        f"e soddisfacendo al 100% tutti gli scenari comportamentali GIVEN/WHEN/THEN della specifica. "
        f"Non inventare logiche, componenti o comportamenti che non siano esplicitamente normati in questi due documenti. "
    )
    if dev_type:
        return base + (
            f"Scrivi ESCLUSIVAMENTE il codice generato nella cartella 'code/{dev_type}/', poiché il tipo di "
            f"sviluppo richiesto per questa feature è '{dev_type}'. Non creare né modificare file in altre "
            f"sottocartelle di 'code/'."
        )
    return base + (
        f"Scrivi il codice generato nella cartella corretta sotto 'code/', in base al tipo di sviluppo richiesto: "
        f"'code/backend' per la logica lato server e le API, 'code/logicAgent' per la logica degli agenti/LLM, "
        f"'code/frontend' per l'interfaccia utente. Se la funzionalità coinvolge più ambiti, distribuisci i file "
        f"nelle rispettive sottocartelle mantenendo la separazione delle responsabilità."
    )


def _entities_for_docs(graph, doc_ids: list[str], limit: int = 24) -> list[str]:
    """Entità del glossario collegate ai documenti dati (successori di tipo 'entity')."""
    ents: list[str] = []
    for d in doc_ids:
        if d not in graph:
            continue
        for succ in graph.successors(d):
            if graph.nodes[succ].get("type") == "entity" and succ not in ents:
                ents.append(succ)
    return ents[:limit]


def _render_agent_context(c: dict) -> str:
    """Rende il blocco [AGENT CONTEXT] in testo copiabile (formato dell'Articolo 1)."""
    lines = ["[AGENT CONTEXT]", f"- Intento probabile: {c['intent']}"]
    lines.append(f"- Sorgenti normative: {', '.join(c['normative_sources']) or '—'}")
    lines.append(f"- Entità coinvolte: {', '.join(c['entities'][:20]) or '—'}")
    lines.append(f"- Safeguard pertinenti: {', '.join(c['safeguards']) or '—'}")
    lines.append("- Vincoli da rispettare:")
    for x in c["constraints"]:
        lines.append(f"    • {x}")
    lines.append("- Rischi:")
    for x in (c["risks"] or ["(nessuno rilevato)"]):
        lines.append(f"    • {x}")
    lines.append(f"- File da leggere: {', '.join(c['files_to_read'])}")
    lines.append(f"- Confidence: {c['confidence']} ({c['confidence_label']})")
    lines.append("\n--- PROMPT SUGGERITO ---")
    lines.append(c["suggested_prompt"])
    return "\n".join(lines)


def build_agent_context(feature_name: str, dev_type: str = "") -> dict:
    """Costruisce il blocco strutturato [AGENT CONTEXT] (intent / sorgenti / entità /
    vincoli / rischi / file / prompt / confidence) dell'Articolo 1, in modo deterministico
    a partire dal retrieval governato e dallo stato di canvas/spec. Il confidence score è
    una metrica composita (rilevanza + copertura del canvas + spec BDD + copertura normativa)."""
    folder_name = slugify_feature(feature_name)
    folder = CHANGES_DIR / folder_name
    canvas = (folder / "canvas.md").read_text(encoding="utf-8") if (folder / "canvas.md").exists() else ""
    spec = (folder / "spec.md").read_text(encoding="utf-8") if (folder / "spec.md").exists() else ""
    dev_type = dev_type or load_dev_type(folder)

    query = f"{feature_name}\n{canvas[:2000]}"
    graph = state.get("graph")
    results: list = []
    top_score = 0.0
    if graph is not None and state.get("qdrant") is not None and state.get("embed_model") is not None:
        try:
            results = hybrid_search(query, 6)
            if results:
                top_score = max((r.get("colbert_score") or r.get("dense_score") or 0.0) for r in results)
        except Exception:
            results = []
    doc_ids = _select_governed_docs(query, results=results) if results else []

    entities = _entities_for_docs(graph, doc_ids) if graph is not None else []
    safeguards = [e for e in entities if e.upper().startswith("SAFEGUARD")]
    iron = [
        d for d in doc_ids
        if graph is not None and str(graph.nodes[d].get("classification", "")).upper() == "IRON_MEMORY"
    ]

    sections_present = [s for s in CANVAS_SECTIONS if s.lower() in canvas.lower()]
    coverage = len(sections_present) / len(CANVAS_SECTIONS) if canvas else 0.0
    spec_ok = 1.0 if all(k in spec.upper() for k in ("GIVEN", "WHEN", "THEN")) else 0.0
    governance = min(1.0, len(doc_ids) / 3.0)
    retrieval = max(0.0, min(1.0, float(top_score)))
    confidence = round(0.35 * retrieval + 0.30 * coverage + 0.15 * spec_ok + 0.20 * governance, 2)
    label = "alta" if confidence >= 0.75 else ("media" if confidence >= 0.5 else "bassa")

    constraints = []
    if safeguards:
        constraints.append("Rispettare i safeguard: " + ", ".join(safeguards[:8]))
    constraints.append("Usare i termini del glossario in MAIUSCOLO (es. EVENTO, UTENTE), senza sinonimi colloquiali.")
    if iron:
        constraints.append("Documenti IRON_MEMORY vincolanti: " + ", ".join(iron))

    risks = []
    if not spec_ok:
        risks.append("Spec BDD assente o incompleta: scenari di test non verificabili.")
    missing = [s for s in CANVAS_SECTIONS if s not in sections_present]
    if canvas and missing:
        risks.append(f"Canvas incompleto: sezioni mancanti ({', '.join(missing)}).")
    if not doc_ids:
        risks.append("Nessun documento normativo pertinente recuperato: contratto poco ancorato alla governance.")
    for sg in safeguards[:5]:
        risks.append(f"Possibile violazione di [{sg}] se non gestita esplicitamente.")

    files_to_read = [f"changes/{folder_name}/canvas.md", f"changes/{folder_name}/spec.md"]
    files_to_read += [f"code/{dev_type}/"] if dev_type else ["code/backend/", "code/frontend/", "code/logicAgent/"]

    ctx = {
        "intent": f"Implementare la feature '{feature_name}'" + (f" (ambito: {dev_type})" if dev_type else ""),
        "normative_sources": doc_ids,
        "entities": entities,
        "safeguards": safeguards,
        "constraints": constraints,
        "risks": risks,
        "files_to_read": files_to_read,
        "suggested_prompt": build_final_prompt(folder_name, dev_type),
        "confidence": confidence,
        "confidence_label": label,
    }
    ctx["text"] = _render_agent_context(ctx)
    return ctx


PIPELINE_FILES = ("explore.md", "canvas.md", "spec.md")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
# Header anti-cache: impedisce al browser di servire una vecchia versione dell'HTML
# (es. un'infografica precedente senza barra di navigazione o senza selettore tema).
_NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _themed_template(request: Request, matrix_name: str, classic_name: str) -> Path:
    """Sceglie il file da servire in base al tema scelto dall'utente (cookie 'ui_theme')."""
    theme = request.cookies.get("ui_theme", "matrix")
    return TEMPLATES_DIR / (classic_name if theme == "classic" else matrix_name)


@app.get("/", response_class=FileResponse, include_in_schema=False)
async def serve_dashboard(request: Request):
    """Serve la dashboard HTML interattiva (tema Matrix o Classico, a scelta dell'utente)."""
    return FileResponse(_themed_template(request, "dashboard.html", "dashboard_classic.html"), media_type="text/html", headers=_NO_CACHE_HEADERS)


@app.get("/pipeline", response_class=FileResponse, include_in_schema=False)
async def serve_pipeline(request: Request):
    """Serve la console Explore -> Canvas -> Propose (tema Matrix o Classico, a scelta dell'utente)."""
    return FileResponse(_themed_template(request, "pipeline.html", "pipeline_classic.html"), media_type="text/html", headers=_NO_CACHE_HEADERS)


@app.get("/infografica", response_class=FileResponse, include_in_schema=False)
async def serve_infografica(request: Request):
    """Serve l'infografica statica del sistema RAG (tema Matrix o Classico, a scelta dell'utente)."""
    return FileResponse(_themed_template(request, "InfograficaRAG.html", "InfograficaRAG_classic.html"), media_type="text/html", headers=_NO_CACHE_HEADERS)


@app.get("/api/pipeline/agent/modes", dependencies=[Depends(require_api_key)])
async def agent_modes():
    """Elenca le modalità di fiducia disponibili per l'esecuzione con Claude Code."""
    return {"modes": [{"id": k, "label": v["label"]} for k, v in AGENT_MODES.items()]}


@app.post("/api/pipeline/agent/run", dependencies=[Depends(require_api_key)])
async def agent_run(req: AgentRunRequest):
    """
    Esegue il prompt finale della pipeline direttamente tramite il Claude Agent SDK,
    trasformando la dashboard da finestra sul progetto a strumento operativo.
    L'SDK gira su un thread dedicato (vedi agent_bridge.py); gli eventi arrivano
    al client come stream NDJSON.
    """
    if req.mode not in AGENT_MODES:
        raise HTTPException(status_code=400, detail=f"Modalità non valida: {req.mode}")
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt vuoto.")

    return StreamingResponse(
        run_agent_streaming(req.prompt, req.mode, req.model),
        media_type="application/x-ndjson",
    )


@app.get("/api/pipeline/dev-types", dependencies=[Depends(require_api_key)])
async def pipeline_dev_types():
    """Elenca le tipologie di sviluppo disponibili (sottocartelle di 'code/') per la tendina di selezione."""
    return {"dev_types": list_dev_types()}


@app.post("/api/pipeline/explore/turn", dependencies=[Depends(require_api_key)])
async def pipeline_explore_turn(req: ExploreTurnRequest):
    """Esegue un turno di intervista (equivalente al loop input() di explore.py)."""
    scope_note = (
        f" Il tipo di sviluppo richiesto per questa feature è '{req.dev_type}' (cartella code/{req.dev_type}): "
        f"concentra le domande esclusivamente sugli aspetti pertinenti a questo ambito."
        if req.dev_type else ""
    )
    history = req.history or (
        f"Sei un Tech Lead e un 'thinking partner'. Stiamo definendo i requisiti per "
        f"la feature: {req.feature_name}.{scope_note} Fai domande brevi e mirate per sviscerare i casi limite.\n"
    )
    prompt = history + f"\nUtente: {req.user_input}\nRispondi in modo conciso:"
    ai_response = await call_ollama_generate(prompt)
    new_history = history + f"\nUtente: {req.user_input}\nIA: {ai_response}"
    return {"ai_response": ai_response, "history": new_history}


@app.post("/api/pipeline/explore/save", dependencies=[Depends(require_api_key)])
async def pipeline_explore_save(req: ExploreSaveRequest):
    """Salva il log dell'intervista in changes/<feature>/explore.md."""
    folder = feature_dir(req.feature_name)
    save_dev_type(folder, req.dev_type)
    dev_type_line = f"**Tipo di sviluppo:** {req.dev_type}\n\n" if req.dev_type else ""
    file_path = folder / "explore.md"
    content = f"# Intervista Explore: {req.feature_name}\n\n{dev_type_line}{req.interview_log}"
    file_path.write_text(content, encoding="utf-8")
    return {"feature_folder": folder.name, "path": "explore.md", "content": content}


@app.post("/api/pipeline/canvas/generate", dependencies=[Depends(require_api_key)])
async def pipeline_canvas_generate(req: CanvasGenerateRequest):
    """Genera il REASONS Canvas a partire dall'intervista Explore (equivalente a canvas.py)."""
    folder = feature_dir(req.feature_name)
    explore_path = folder / "explore.md"

    if explore_path.exists():
        contesto_intervista = explore_path.read_text(encoding="utf-8")
    else:
        contesto_intervista = "Nessun log di intervista dettagliato disponibile."

    # Àncora il Canvas al knowledge base governato: recupera dal Graph RAG i documenti
    # normativi pertinenti (safeguard, glossario, matrice permessi), pesati per autorità,
    # invece di affidarsi a un contesto statico scritto a mano.
    governed_context = await run_in_threadpool(
        retrieve_governed_context, f"{req.feature_name}\n{contesto_intervista[:2000]}"
    )
    contesto_progetto_base = governed_context or "Nessun documento normativo pertinente recuperato dal Graph RAG."

    dev_type = req.dev_type or load_dev_type(folder)
    scope_note = (
        f"\n\n    Vincolo di ambito: il tipo di sviluppo richiesto per questa feature è ESCLUSIVAMENTE "
        f"'{dev_type}' (il codice finale verrà scritto solo in 'code/{dev_type}/'). "
        f"La sezione Structure deve descrivere layer e componenti pertinenti solo a questo ambito, "
        f"senza proporre modifiche in altre parti del sistema."
        if dev_type else ""
    )

    prompt_strutturato = f"""
    Sei un Tech Lead expert. Il tuo compito è generare un REASONS Canvas in formato Markdown per la seguente feature: "{req.feature_name}".

    Per definire la strategia tecnica, devi basarti PRIORITARIAMENTE sui requisiti e sui casi limite emersi durante l'intervista preliminare (Explore) riportata qui sotto:

    --- INIZIO LOG INTERVISTA (EXPLORE) ---
    {contesto_intervista}
    --- FINE LOG INTERVISTA ---

    Contesto normativo recuperato dal Graph RAG (ordinato per autorità: rispetta TASSATIVAMENTE
    i safeguard, i vincoli della matrice permessi e i termini del glossario riportati qui sotto;
    non contraddirli e riusa i loro codici/entità nelle sezioni Entities, Norms e Safeguards):
    {contesto_progetto_base}{scope_note}

    Il REASONS Canvas generato DEVE contenere tassativamente queste 7 sezioni:
    1. Requirements (Cosa deve fare il modulo, estrapolato dall'intervista)
    2. Entities (Modelli di dominio coinvolti)
    3. Approach (Strategia logica per soddisfare i requisiti)
    4. Structure (Layer e API coinvolte)
    5. Operations (Step sequenziali e testabili per lo sviluppo)
    6. Norms (Standard di naming e sicurezza, es. restrizioni email)
    7. Safeguards (Vincoli non negoziabili e gestione degli errori concordati nell'intervista)

    Rispondi esclusivamente con il contenuto del file Markdown, formattato in modo pulito.
    """

    canvas_content = await call_ollama_generate(prompt_strutturato)
    (folder / "canvas.md").write_text(canvas_content, encoding="utf-8")
    save_dev_type(folder, dev_type)
    return {"feature_folder": folder.name, "path": "canvas.md", "content": canvas_content}


@app.post("/api/pipeline/propose/generate", dependencies=[Depends(require_api_key)])
async def pipeline_propose_generate(req: ProposeGenerateRequest):
    """Genera spec.md dal Canvas e il prompt finale per Claude Code (equivalente a propose.py)."""
    folder_name = slugify_feature(req.feature_folder)
    folder = CHANGES_DIR / folder_name
    canvas_path = folder / "canvas.md"

    if not canvas_path.exists():
        raise HTTPException(status_code=404, detail=f"Non trovo {canvas_path.name}. Devi prima generare il Canvas.")

    canvas_content = canvas_path.read_text(encoding="utf-8")
    dev_type = req.dev_type or load_dev_type(folder)

    # Recupera i vincoli normativi dal Graph RAG per generare scenari BDD che coprano
    # anche i safeguard e le policy pertinenti, non solo ciò che è nel Canvas.
    governed_context = await run_in_threadpool(
        retrieve_governed_context, f"{req.feature_folder}\n{canvas_content[:2000]}"
    )
    norme_block = (
        f"\n\n    Vincoli normativi dal Graph RAG (definisci scenari GIVEN/WHEN/THEN che li verifichino "
        f"esplicitamente, es. tentativi non autorizzati, casi di errore e invarianti dei safeguard):\n"
        f"    {governed_context}"
        if governed_context else ""
    )

    prompt_strutturato = f"""
    Sei un Analista Software esperto in metodologie BDD (Behavior-Driven Development).
    Leggi questo REASONS Canvas:

    {canvas_content}
{norme_block}

    Basandoti sulle regole e sui requisiti del Canvas (e sui vincoli normativi qui sopra, se presenti),
    scrivi il file delle specifiche tecniche (spec.md).
    Devi definire gli scenari di test utilizzando rigorosamente il formato:
    - GIVEN (Dato che...)
    - WHEN (Quando...)
    - THEN (Allora...)
    - AND (E...)

    Non inventare funzionalità non presenti nel Canvas o nei vincoli normativi.
    """

    spec_content = await call_ollama_generate(prompt_strutturato)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "spec.md").write_text(spec_content, encoding="utf-8")
    save_dev_type(folder, dev_type)

    final_prompt = build_final_prompt(folder_name, dev_type)

    return {
        "feature_folder": folder.name,
        "path": "spec.md",
        "content": spec_content,
        "final_prompt": final_prompt,
    }


def _reload_index_state() -> None:
    """Ricarica in memoria grafo, multivettori ColBERT e descrizioni regole dai file
    appena rigenerati dalla re-indicizzazione, così che il server rifletta subito la
    nuova base di conoscenza senza dover essere riavviato."""
    with open(GRAPH_SAVE_PATH, "rb") as f:
        state["graph"] = pickle.load(f)
    if COLBERT_SAVE_PATH.exists():
        with open(COLBERT_SAVE_PATH, "rb") as f:
            state["colbert_store"] = pickle.load(f)
    if CHUNKS_SAVE_PATH.exists():
        with open(CHUNKS_SAVE_PATH, "rb") as f:
            state["chunks"] = pickle.load(f)
    state["rule_descriptions"] = load_rule_descriptions()
    try:
        state["_graph_mtime"] = GRAPH_SAVE_PATH.stat().st_mtime
    except OSError:
        pass


def _maybe_reload_graph() -> None:
    """Auto-reload: se graph.pkl è cambiato su disco (es. una re-indicizzazione lanciata
    da CLI mentre il server è attivo), ricarica l'indice in memoria alla prima richiesta
    successiva, senza dover riavviare il server."""
    if state.get("graph") is None:
        return
    try:
        mtime = GRAPH_SAVE_PATH.stat().st_mtime
    except OSError:
        return
    prev = state.get("_graph_mtime")
    if prev is None:
        state["_graph_mtime"] = mtime
        return
    if mtime != prev:
        print("🔄 graph.pkl cambiato su disco: ricarico grafo/ColBERT/regole in memoria.")
        _reload_index_state()


def _run_streaming(target, *args):
    """Esegue una funzione bloccante (check_drift/archive_feature) su un thread dedicato
    e ne trasmette il log in tempo reale come NDJSON, iniettando `emit` come callback.
    Stessa filosofia dello streaming dell'agent (una riga JSON per evento)."""
    q: queue.Queue = queue.Queue()

    def emit(msg) -> None:
        q.put({"type": "log", "line": str(msg)})

    def worker() -> None:
        try:
            result = target(*args, emit=emit)
            q.put({"type": "result", "value": result})
        except Exception as exc:  # l'errore va riportato al client
            q.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            q.put(None)

    threading.Thread(target=worker, name="pipeline-stream", daemon=True).start()
    while True:
        item = q.get()
        if item is None:
            break
        yield json.dumps(item, ensure_ascii=False) + "\n"


@app.post("/api/pipeline/drift/check", dependencies=[Depends(require_api_key)])
async def pipeline_drift_check(req: DriftCheckRequest):
    """Step 4 — Verifica del Drift: confronta il canvas (contratto) con il codice
    generato tramite LLM locale e restituisce il report. Equivale a 'index.py --check-drift'."""
    if not req.feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    # La chiamata a Ollama è bloccante e potenzialmente lunga: la eseguiamo in un
    # thread separato per non bloccare l'event loop del server.
    report = await run_in_threadpool(check_drift, req.feature)
    return {"feature_folder": slugify_feature(req.feature), "report": report}


@app.post("/api/pipeline/archive", dependencies=[Depends(require_api_key)])
async def pipeline_archive(req: ArchiveRequest):
    """Step 5 — Archiviazione e Re-indicizzazione: sposta changes/<feature> in
    changes/archive/ e ricostruisce il Graph RAG locale. Equivale a 'index.py --archive',
    ma riusa il modello di embedding e il client Qdrant già aperti dal server (necessario:
    lo storage Qdrant locale è a lock esclusivo e non tollera un secondo processo)."""
    if not req.feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    log = await run_in_threadpool(
        archive_feature, req.feature, state["qdrant"], state["embed_model"]
    )
    # Rende visibile alla console Graph-RAG la base di conoscenza appena rigenerata.
    _reload_index_state()
    return {"feature_folder": slugify_feature(req.feature), "log": log}


@app.post("/api/pipeline/drift/check/stream", dependencies=[Depends(require_api_key)])
async def pipeline_drift_check_stream(req: DriftCheckRequest):
    """Come /api/pipeline/drift/check ma con progresso in streaming (NDJSON): l'interfaccia
    mostra i passi (avvio, analisi, report) man mano che arrivano, senza box bloccante."""
    if not req.feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    return StreamingResponse(_run_streaming(check_drift, req.feature), media_type="application/x-ndjson")


@app.post("/api/pipeline/archive/stream", dependencies=[Depends(require_api_key)])
async def pipeline_archive_stream(req: ArchiveRequest):
    """Come /api/pipeline/archive ma con progresso in streaming (NDJSON): l'utente vede la
    re-indicizzazione avanzare passo per passo. Al termine ricarica l'indice in memoria."""
    if not req.feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")

    def gen():
        yield from _run_streaming(archive_feature, req.feature, state["qdrant"], state["embed_model"])
        # La re-indicizzazione ha riscritto graph.pkl: aggiorna lo stato in memoria.
        _reload_index_state()
        yield json.dumps({"type": "reloaded"}, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


CANVAS_SECTIONS = ("Requirements", "Entities", "Approach", "Structure", "Operations", "Norms", "Safeguards")


async def _validate_feature(feature: str) -> dict:
    """Validazione pre-apply: controlli strutturali deterministici su canvas/spec +
    analisi LLM di coerenza e conflitti contro il contesto normativo del Graph RAG.
    Il retrieval (CPU) gira in threadpool, la chiamata Ollama (I/O) è async."""
    folder_name = slugify_feature(feature)
    folder = CHANGES_DIR / folder_name
    canvas_path = folder / "canvas.md"
    spec_path = folder / "spec.md"

    canvas_text = canvas_path.read_text(encoding="utf-8") if canvas_path.exists() else ""
    spec_text = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""

    # 1. Controlli strutturali deterministici (nessun LLM).
    canvas_lower = canvas_text.lower()
    spec_upper = spec_text.upper()
    sezioni_canvas = {sec: (sec.lower() in canvas_lower) for sec in CANVAS_SECTIONS}
    bdd_given = "GIVEN" in spec_upper
    bdd_when = "WHEN" in spec_upper
    bdd_then = "THEN" in spec_upper
    structural = {
        "canvas_presente": bool(canvas_text),
        "spec_presente": bool(spec_text),
        "sezioni_canvas": sezioni_canvas,
        "bdd_given": bdd_given,
        "bdd_when": bdd_when,
        "bdd_then": bdd_then,
        "canvas_completo": all(sezioni_canvas.values()),
        "spec_bdd_valida": bdd_given and bdd_when and bdd_then,
    }

    if not canvas_text:
        return {"structural": structural, "report": "❌ canvas.md assente: genera prima il Canvas."}

    # 2. Analisi semantica: coerenza e conflitti rispetto al contesto normativo governato.
    #    Il retrieval è CPU-bound (embedding della query) → threadpool; l'LLM è I/O → async.
    governed = await run_in_threadpool(retrieve_governed_context, f"{feature}\n{canvas_text[:2000]}")
    prompt = f"""
    Sei un Revisore dell'Architettura. Verifica la COERENZA del design contract (Canvas + Spec)
    rispetto ai vincoli normativi del knowledge base, PRIMA che il codice venga scritto.

    --- CANVAS ---
    {canvas_text}

    --- SPEC (scenari BDD) ---
    {spec_text if spec_text else "(spec.md non ancora generato)"}

    --- VINCOLI NORMATIVI (Graph RAG, ordinati per autorità) ---
    {governed if governed else "(nessun documento normativo recuperato)"}

    Rispondi in modo conciso indicando:
    1. CONFLITTI: il Canvas/Spec viola o contraddice qualche safeguard, policy o termine di glossario? (SI/NO + quali)
    2. COPERTURA: gli scenari BDD coprono i casi di errore e le invarianti dei safeguard pertinenti? Cosa manca?
    3. NON-GOAL: c'è qualcosa fuori ambito rispetto ai vincoli?
    Se tutto è coerente e coperto, rispondi con "✅ VALIDAZIONE SUPERATA. Design contract coerente con la governance."
    """
    report = await call_ollama_generate(prompt)
    return {"structural": structural, "report": report}


@app.post("/api/pipeline/validate", dependencies=[Depends(require_api_key)])
async def pipeline_validate(req: ValidateRequest):
    """Step di validazione pre-apply: verifica strutturale (7 sezioni del Canvas, BDD nella
    spec) e coerenza semantica contro i vincoli normativi del Graph RAG, prima di lanciare Claude."""
    if not req.feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    result = await _validate_feature(req.feature)
    return {"feature_folder": slugify_feature(req.feature), **result}


@app.get("/api/index/status", dependencies=[Depends(require_api_key)])
async def api_index_status():
    """Segnala se l'indice Graph RAG è aggiornato rispetto ai documenti in docs/ (drift di
    indicizzazione): confronta gli hash correnti con lo snapshot salvato dall'ultima build."""
    return await run_in_threadpool(index_status)


@app.post("/api/pipeline/canvas/dry-run", dependencies=[Depends(require_api_key)])
async def pipeline_canvas_dry_run(req: CanvasGenerateRequest):
    """Dry-run del Canvas: mostra le sorgenti che verrebbero recuperate (con punteggi
    dense/sparse/ColBERT/autorità) e i documenti normativi che verrebbero iniettati,
    SENZA generare nulla — così si ispeziona il contesto prima di spendere token."""
    folder = feature_dir(req.feature_name)
    explore_path = folder / "explore.md"
    interview = explore_path.read_text(encoding="utf-8") if explore_path.exists() else ""
    query = f"{req.feature_name}\n{interview[:2000]}"

    def work() -> dict:
        if state.get("graph") is None or state.get("qdrant") is None or state.get("embed_model") is None:
            return {"sources": [], "governed_docs": [], "note": "Indice non ancora pronto."}
        try:
            results = hybrid_search(query, 6)
        except Exception as exc:
            return {"sources": [], "governed_docs": [], "note": f"Retrieval fallito: {exc}"}
        doc_ids = _select_governed_docs(query, results=results)
        graph = state["graph"]
        governed = []
        for d in doc_ids:
            p = PROJECT_ROOT / "docs" / d
            governed.append({
                "doc_id": d,
                "authority": round(_authority_weight(graph.nodes[d]) if d in graph else 0.0, 3),
                "classification": graph.nodes[d].get("classification", "") if d in graph else "",
                "chars": len(p.read_text(encoding="utf-8")) if p.exists() else 0,
            })
        sources = [
            {"doc_id": r["doc_id"], "section": r.get("section", ""),
             "dense_score": r["dense_score"], "sparse_score": r["sparse_score"],
             "colbert_score": r["colbert_score"], "authority": r["authority"]}
            for r in results
        ]
        return {"sources": sources, "governed_docs": governed}

    data = await run_in_threadpool(work)
    return {"feature_folder": slugify_feature(req.feature_name), "query_preview": query[:300], **data}


@app.get("/api/pipeline/agent-context", dependencies=[Depends(require_api_key)])
async def pipeline_agent_context(feature: str, dev_type: str = ""):
    """Blocco strutturato [AGENT CONTEXT] con confidence score (Articolo 1), costruito in
    modo deterministico dal retrieval governato e dallo stato di canvas/spec."""
    if not feature.strip():
        raise HTTPException(status_code=400, detail="Nome feature mancante.")
    ctx = await run_in_threadpool(build_agent_context, feature, dev_type)
    return {"feature_folder": slugify_feature(feature), **ctx}


@app.get("/api/pipeline/export", dependencies=[Depends(require_api_key)])
async def pipeline_export(feature: str, dev_type: str = ""):
    """Export JSON versionabile del design contract (explore/canvas/spec + prompt finale +
    [AGENT CONTEXT]), da archiviare come artefatto o dare in pasto a una pipeline."""
    folder_name = slugify_feature(feature)
    folder = CHANGES_DIR / folder_name

    def rd(name: str) -> str:
        p = folder / name
        return p.read_text(encoding="utf-8") if p.exists() else ""

    dev = dev_type or load_dev_type(folder)
    ctx = await run_in_threadpool(build_agent_context, feature, dev)
    return {
        "feature": feature,
        "feature_folder": folder_name,
        "dev_type": dev,
        "explore": rd("explore.md"),
        "canvas": rd("canvas.md"),
        "spec": rd("spec.md"),
        "final_prompt": build_final_prompt(folder_name, dev),
        "agent_context": ctx,
    }


@app.get("/api/pipeline/status", dependencies=[Depends(require_api_key)])
async def pipeline_status(feature: str):
    """Restituisce quali file (explore/canvas/spec) esistono già per la feature, per il pannello di controllo."""
    folder_name = slugify_feature(feature)
    folder = CHANGES_DIR / folder_name
    files = {
        name.split(".")[0]: (folder / name).exists()
        for name in PIPELINE_FILES
    }
    return {
        "feature_folder": folder_name,
        "exists": folder.exists(),
        "files": files,
        "dev_type": load_dev_type(folder),
    }


@app.get("/api/pipeline/file", dependencies=[Depends(require_api_key)])
async def pipeline_get_file(feature: str, name: str):
    """Restituisce il contenuto di un file md della pipeline, per la visualizzazione di controllo."""
    if name not in PIPELINE_FILES:
        raise HTTPException(status_code=400, detail=f"File non consentito: {name}")
    folder_name = slugify_feature(feature)
    file_path = CHANGES_DIR / folder_name / name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"{name} non trovato per la feature '{folder_name}'.")
    return {"feature_folder": folder_name, "path": name, "content": file_path.read_text(encoding="utf-8")}


@app.post("/api/pipeline/file/save", dependencies=[Depends(require_api_key)])
async def pipeline_save_file(req: PipelineFileSaveRequest):
    """Salva modifiche manuali a un file md prima dell'approvazione (revisione umana)."""
    if req.name not in PIPELINE_FILES:
        raise HTTPException(status_code=400, detail=f"File non consentito: {req.name}")
    folder = feature_dir(req.feature)
    (folder / req.name).write_text(req.content, encoding="utf-8")
    return {"feature_folder": folder.name, "path": req.name, "content": req.content}


@app.post("/ask", dependencies=[Depends(require_api_key)])
async def ask_rag(query: AskQuery):
    _maybe_reload_graph()
    graph: nx.DiGraph = state["graph"]
    qdrant: QdrantClient = state["qdrant"]
    embed_model: BGEM3FlagModel = state["embed_model"]

    if graph is None or qdrant is None or embed_model is None:
        raise HTTPException(status_code=503, detail="Server non ancora inizializzato.")

    # 1-2. Ricerca ibrida: dense + sparse (fusione per rank) + rerank ColBERT
    search_results = hybrid_search(query.question, query.top_k)

    if not search_results:
        return {
            "status": "no_results",
            "answer": "Nessun documento rilevante trovato nel knowledge base.",
            "graph_context": {},
            "qdrant_scores": [],
        }

    # 3. Nodi seed nel grafo dai risultati (documenti padre dei chunk, deduplicati
    #    preservando l'ordine di rilevanza).
    seed_nodes = list(dict.fromkeys(r["doc_id"] for r in search_results if r["doc_id"] in graph))

    if not seed_nodes:
        return {
            "status": "no_graph_nodes",
            "answer": "Documenti trovati in Qdrant ma non presenti nel grafo.",
            "graph_context": {},
            "qdrant_scores": [
                {**r, "score": r["colbert_score"] if r["colbert_score"] is not None else r["dense_score"]}
                for r in search_results
            ],
        }

    # 4a. Espansione BFS per il GRAFO (usa sempre depth >= 1 per la visualizzazione)
    graph_depth = max(query.bfs_depth, 1)
    expanded_nodes = bfs_expand(graph, seed_nodes, depth=graph_depth)

    # Raccoglie gli archi tra i nodi espansi per la dashboard
    expanded_set = set(expanded_nodes)
    graph_edges = [
        {"from": u, "to": v, "relation": data.get("relation", "")}
        for u, v, data in graph.edges(data=True)
        if u in expanded_set and v in expanded_set
    ]

    # Arricchisce i nodi espansi con tipo e descrizione (per il frontend)
    rule_descriptions: dict = state["rule_descriptions"]
    expanded_nodes_data = [
        {
            "id": node_id,
            "type": graph.nodes[node_id].get("type", "unknown"),
            "description": rule_descriptions.get(node_id, ""),
            # Pilastro REASONS di appartenenza (dal frontmatter YAML), per la colorazione cromatica del grafo
            "classification": graph.nodes[node_id].get("classification", ""),
        }
        for node_id in sorted(expanded_nodes)
    ]

    # -----------------------------------------------------------------------
    # 4b. Costruisce il contesto per l'LLM (Separazione logica / Ottimizzazione)
    # -----------------------------------------------------------------------
    
    # === VECCHIA LOGICA (SOLO SEED NODES): Commentata per confronto ===
    # context_parts: list[str] = []
    # for doc_id in seed_nodes:
    #     doc_path = PROJECT_ROOT / "openspec" / doc_id
    #     if doc_path.exists():
    #         with open(doc_path, "r", encoding="utf-8") as f:
    #             context_parts.append(f"--- {doc_id} ---\n{f.read()}")
    # context = "\n\n".join(context_parts)
    # =======================================================================

    # === INIEZIONE CHUNK-AWARE ===
    # Inietta il testo delle SEZIONI recuperate (i chunk), non i documenti interi:
    # più preciso e senza saturare il contesto. La struttura multi-hop del grafo
    # (seed + nodi espansi) resta comunque esposta in graph_context.
    chunks_store: dict = state.get("chunks", {})
    context_parts: list[str] = []
    seen_chunks: set[str] = set()
    for r in search_results:
        cid = r.get("chunk_id")
        entry = chunks_store.get(cid) if cid else None
        if entry is None or cid in seen_chunks:
            continue
        seen_chunks.add(cid)
        context_parts.append(f"--- {r['doc_id']} § {r.get('section', '')} ---\n{entry['text']}")

    # Fallback legacy: senza sidecar dei chunk, inietta i documenti seed interi
    if not context_parts:
        for doc_id in seed_nodes:
            doc_path = PROJECT_ROOT / "docs" / doc_id
            if doc_path.exists():
                context_parts.append(f"--- Inizio Documento: {doc_id} ---\n{doc_path.read_text(encoding='utf-8')}\n--- Fine Documento: {doc_id} ---")
    context = "\n\n".join(context_parts)
    # -----------------------------------------------------------------------

    # 5. Sintesi finale tramite LLM configurato.
    #    call_llm è multi-provider e sincrono (SDK anthropic/openai + httpx ollama): lo
    #    eseguiamo in threadpool per non bloccare l'event loop. TODO: rendere async anche
    #    il branch ollama di call_llm (gli SDK anthropic/openai restano sync → threadpool).
    start_time = time.time()
    answer = await run_in_threadpool(call_llm, context, query.question)
    end_time = time.time()
    
    elaborazione_secondi = round(end_time - start_time, 2)
    print(f"\n[TIMER] Tempo impiegato per la generazione: {elaborazione_secondi} secondi\n")

    return {
        "status": "success",
        "answer": answer,
        "elaboration_seconds": elaborazione_secondi,
        "graph_context": {
            "seed_nodes": seed_nodes,
            "expanded_nodes": expanded_nodes_data,
            "graph_edges": graph_edges,
            "context_text": context,
        },
        # Breakdown completo del ranking ibrido: rank dense/sparse, fusione e
        # punteggio ColBERT. "score" resta il campo principale per il frontend.
        "qdrant_scores": [
            {**r, "score": r["colbert_score"] if r["colbert_score"] is not None else r["dense_score"]}
            for r in search_results
        ],
    }


@app.get("/api/retrieve", dependencies=[Depends(require_api_key)])
async def api_retrieve(q: str, k: int = 5):
    """Retrieval PURO (dense + sparse + ColBERT + authority), senza sintesi LLM. Restituisce
    i chunk pertinenti con il breakdown del ranking. Serve per valutare la qualità del ranking
    (golden-set / eval_retrieval.py) e per il debug, senza il costo di Ollama."""
    if state.get("qdrant") is None or state.get("embed_model") is None:
        raise HTTPException(status_code=503, detail="Indice non ancora pronto.")
    results = await run_in_threadpool(hybrid_search, q, k)
    return {"query": q, "k": k, "results": results}


@app.get("/api/graph/all", dependencies=[Depends(require_api_key)])
async def get_full_graph():
    """Restituisce l'intero grafo statico (tutti i nodi e gli archi) in formato JSON."""
    _maybe_reload_graph()
    graph: nx.DiGraph = state["graph"]
    if graph is None:
        raise HTTPException(status_code=503, detail="Grafo non ancora inizializzato.")
    return graph_ops.full_graph(graph, state["rule_descriptions"])


@app.get("/api/graph/impact", dependencies=[Depends(require_api_key)])
async def graph_impact(node: str, depth: int = 3):
    """Impact Ripple: espansione BFS a cerchi concentrici da un nodo. Ogni 'ring' è
    un livello di distanza (1 hop, 2 hop, ...). Risponde 'cosa viene impattato se
    modifico questo nodo?' in modo deterministico (nessun LLM)."""
    _maybe_reload_graph()
    graph: nx.DiGraph = state["graph"]
    if graph is None:
        raise HTTPException(status_code=503, detail="Grafo non ancora inizializzato.")
    if node not in graph:
        raise HTTPException(status_code=404, detail=f"Nodo non presente nel grafo: {node}")
    return graph_ops.impact(graph, node, depth)


@app.get("/api/graph/semantic-map", dependencies=[Depends(require_api_key)])
async def graph_semantic_map():
    """Semantic Map: proietta i CHUNK (sezioni) in 2D per prossimità semantica (PCA via
    SVD sui vettori densi bge-m3 in Qdrant). Le community e i nodi 'ponte' sono calcolati
    a livello di documento padre (co-menzione di entità) e ereditati dai chunk; i duplicati
    sono sezioni molto simili appartenenti a documenti diversi. Solo numpy/networkx."""
    _maybe_reload_graph()
    graph: nx.DiGraph = state["graph"]
    qdrant: QdrantClient = state["qdrant"]
    if graph is None or qdrant is None:
        raise HTTPException(status_code=503, detail="Grafo/Qdrant non inizializzati.")
    return graph_ops.semantic_map(graph, qdrant)


@app.get("/api/graph/query", dependencies=[Depends(require_api_key)])
async def graph_query(q: str):
    """Query DETERMINISTICA sul grafo (nessun LLM): risponde a domande strutturali —
    'quali documenti/entità/codice esistono?', 'relazioni di X', 'cosa impatta X' — leggendo
    direttamente nodi e archi. Incarna il principio 'determinismo prima dell'LLM' (Articolo 1)."""
    if state.get("graph") is None:
        raise HTTPException(status_code=503, detail="Grafo non ancora inizializzato.")
    _maybe_reload_graph()
    return graph_ops.graph_query(q, state["graph"])


@app.get("/analysis", response_class=FileResponse, include_in_schema=False)
async def serve_analysis(request: Request):
    """Serve la pagina di analisi del grafo (Semantic Map + Impact Ripple), tema Matrix o Classico."""
    return FileResponse(_themed_template(request, "graph_analysis.html", "graph_analysis_classic.html"), media_type="text/html", headers=_NO_CACHE_HEADERS)


# ---------------------------------------------------------------------------
# HARDENING — rischi residui noti (da affrontare prima di un uso non locale)
# ---------------------------------------------------------------------------
# 1. QDRANT: risolto. Qdrant gira in server mode (Docker, vedi docker-compose.yml),
#    niente più lock esclusivo sullo storage — configurabile via QDRANT_URL /
#    QDRANT_API_KEY. L'iniezione di qdrant/embed_model nel re-index resta comunque
#    utile per evitare il ricaricamento del modello di embedding (minuti di CPU).
# 2. BIND & AUTH: risolto. Default host 127.0.0.1; tutti gli endpoint /api/* e /ask
#    richiedono X-API-Key (env VIBECRAFT_API_KEY) per chi non chiama da localhost —
#    vedi require_api_key(). Chi vuole esporre il server sulla rete deve impostare
#    sia VIBECRAFT_HOST che VIBECRAFT_API_KEY.
# 3. STATO GLOBALE NON PROTETTO: `state` è un dict globale che _maybe_reload_graph
#    sostituisce mentre i thread del pool lo leggono. Oggi regge per il GIL e perché
#    le sostituzioni sono atomiche (rebinding di riferimenti), ma è fragile per
#    costruzione. TODO: un threading.RLock attorno a load/reload e alle letture di
#    graph/qdrant/colbert/chunks, oppure uno snapshot immutabile scambiato atomicamente.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    host = os.environ.get("VIBECRAFT_HOST", "127.0.0.1")
    port = int(os.environ.get("VIBECRAFT_PORT", "8000"))
    if host != "127.0.0.1" and not API_KEY:
        print("⚠️  Server esposto oltre localhost (VIBECRAFT_HOST) SENZA VIBECRAFT_API_KEY: "
              "tutte le richieste non-locali ai /api/* verranno rifiutate (fail-closed).")
    uvicorn.run(app, host=host, port=port)
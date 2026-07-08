import re
import json
import time
import yaml
import pickle
import httpx
import uvicorn
import numpy as np
import networkx as nx

from typing import Any
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import SparseVector
from FlagEmbedding import BGEM3FlagModel

from agent_bridge import AGENT_MODES, run_agent_streaming

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------
RAG_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = RAG_DIR.parent
CONFIG_PATH = RAG_DIR / "rag_config.yaml"
DATABASE_DIR = RAG_DIR / "database"
GRAPH_SAVE_PATH = DATABASE_DIR / "graph.pkl"
COLBERT_SAVE_PATH = DATABASE_DIR / "colbert.pkl"
QDRANT_PATH = str(DATABASE_DIR / "qdrant_data")
TEMPLATES_DIR = RAG_DIR / "templates"

with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
    config = yaml.safe_load(_f)

COLLECTION_NAME: str = config["vector_database"]["collection_name"]
EMBEDDING_MODEL: str = config["vector_database"]["embedding_model"]
LLM_PROVIDER: str = config["llm_settings"]["active_provider"]
LLM_MODEL: str = config["llm_settings"]["models"][LLM_PROVIDER]

# ---------------------------------------------------------------------------
# Configurazione pipeline Explore -> Canvas -> Propose (rag/changes/)
# ---------------------------------------------------------------------------
PIPELINE_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
PIPELINE_MODEL_NAME: str = config["llm_settings"]["models"].get("ollama", "qwen2.5:7b")
CHANGES_DIR = PROJECT_ROOT / "changes"
CODE_DIR = PROJECT_ROOT / "code"

# Generazioni con modelli grandi (es. qwen2.5:14b) su CPU possono richiedere diversi minuti:
# un timeout troppo corto interrompe la richiesta anche quando Ollama sta ancora generando.
OLLAMA_TIMEOUT_SECONDS = 900.0

# ---------------------------------------------------------------------------
# Stato globale del server (popolato durante il lifespan)
# ---------------------------------------------------------------------------
state: dict = {
    "graph": None,
    "qdrant": None,
    "embed_model": None,
    "rule_descriptions": {},
    "colbert_store": {},
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
    state["embed_model"] = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=True)

    print("Connessione a Qdrant (storage locale)...")
    state["qdrant"] = QdrantClient(path=QDRANT_PATH)

    print(f"Caricamento grafo NetworkX da {GRAPH_SAVE_PATH} ...")
    if not GRAPH_SAVE_PATH.exists():
        raise RuntimeError(
            "graph.pkl non trovato. Esegui prima 'python index.py' per indicizzare."
        )
    with open(GRAPH_SAVE_PATH, "rb") as f:
        state["graph"] = pickle.load(f)

    g: nx.DiGraph = state["graph"]
    print(f"Grafo caricato: {g.number_of_nodes()} nodi, {g.number_of_edges()} archi.")

    # Multivettori ColBERT per il rerank token-per-token (sidecar dell'indice)
    if COLBERT_SAVE_PATH.exists():
        with open(COLBERT_SAVE_PATH, "rb") as f:
            state["colbert_store"] = pickle.load(f)
        print(f"Multivettori ColBERT caricati: {len(state['colbert_store'])} documenti.")
    else:
        print("Attenzione: colbert.pkl non trovato — rerank ColBERT disattivato. Riesegui 'python index.py'.")

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


# ---------------------------------------------------------------------------
# Funzioni di supporto
# ---------------------------------------------------------------------------
def _hit_doc_id(hit) -> str:
    """Estrae in modo sicuro il doc_id da un punto Qdrant (payload può essere None)."""
    return str((hit.payload or {}).get("doc_id", ""))


def hybrid_search(question: str, top_k: int) -> list[dict]:
    """
    Ricerca ibrida a tre livelli (stessa forward pass di bge-m3 per tutti i vettori):

    1. Dense retrieval  — cattura la semantica generale della domanda.
    2. Sparse retrieval — recupera match lessicali esatti (identificatori,
       termini tecnici rari) che il vettore denso diluisce.
    3. Fusione per somma dei rank: i documenti rilevanti in entrambe le liste
       salgono; quelli presenti in una sola scendono.
    4. Rerank ColBERT — confronto token-per-token (MaxSim) sui candidati fusi,
       per la precisione finale.

    Restituisce i top_k candidati con il breakdown completo del ranking.
    """
    qdrant: QdrantClient = state["qdrant"]
    embed_model: BGEM3FlagModel = state["embed_model"]
    colbert_store: dict = state["colbert_store"]

    # Una sola forward pass produce dense, sparse e colbert per la query
    q_out = embed_model.encode(
        [question],
        batch_size=1,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=True,
    )
    dense_q = q_out["dense_vecs"][0].tolist()
    lex_q = q_out["lexical_weights"][0]
    colbert_q = q_out["colbert_vecs"][0]

    # Recupera più candidati del necessario: la fusione e il rerank scremano
    fetch_k = max(top_k * 3, 10)

    dense_hits = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=dense_q,
        using="dense",
        limit=fetch_k,
    ).points

    # SparseVector è un'interfaccia di query valida a runtime, ma lo stub di
    # query_points tipa 'query' in modo troppo stretto: la variabile Any
    # disattiva il controllo di tipo solo su questo argomento.
    sparse_query: Any = SparseVector(
        indices=[int(t) for t in lex_q.keys()],
        values=[float(w) for w in lex_q.values()],
    )
    sparse_hits = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=sparse_query,
        using="sparse",
        limit=fetch_k,
    ).points

    # Fusione per somma delle posizioni (rank più basso = migliore).
    # Un documento assente da una lista riceve una penalità pari a fetch_k+1.
    dense_rank = {_hit_doc_id(h): i + 1 for i, h in enumerate(dense_hits)}
    sparse_rank = {_hit_doc_id(h): i + 1 for i, h in enumerate(sparse_hits)}
    dense_score = {_hit_doc_id(h): h.score for h in dense_hits}
    sparse_score = {_hit_doc_id(h): h.score for h in sparse_hits}

    missing_penalty = fetch_k + 1
    candidates: dict[str, int] = {}
    for doc_id in set(dense_rank) | set(sparse_rank):
        candidates[doc_id] = dense_rank.get(doc_id, missing_penalty) + sparse_rank.get(doc_id, missing_penalty)

    fused = sorted(candidates.items(), key=lambda kv: kv[1])

    # Rerank ColBERT (MaxSim): per ogni token della query prende la similarità
    # massima con i token del documento, poi media. Precisione token-per-token.
    results: list[dict] = []
    for doc_id, fused_rank_sum in fused:
        entry = {
            "doc_id": doc_id,
            "dense_rank": dense_rank.get(doc_id),
            "sparse_rank": sparse_rank.get(doc_id),
            "dense_score": round(dense_score[doc_id], 4) if doc_id in dense_score else None,
            "sparse_score": round(sparse_score[doc_id], 4) if doc_id in sparse_score else None,
            "fused_rank_sum": fused_rank_sum,
            "colbert_score": None,
        }
        doc_col = colbert_store.get(doc_id)
        if doc_col is not None:
            doc_col = np.asarray(doc_col, dtype=np.float32)
            sim = colbert_q @ doc_col.T                    # [q_tokens x d_tokens]
            entry["colbert_score"] = round(float(sim.max(axis=1).mean()), 4)
        results.append(entry)

    # Ordinamento finale: ColBERT dove disponibile, altrimenti la fusione
    if any(r["colbert_score"] is not None for r in results):
        results.sort(key=lambda r: r["colbert_score"] if r["colbert_score"] is not None else -1.0, reverse=True)

    return results[:top_k]


def bfs_expand(graph: nx.DiGraph, seed_nodes: list[str], depth: int) -> set[str]:
    """Espansione BFS bidirezionale a partire dai nodi seed fino a `depth` livelli."""
    visited: set[str] = set(seed_nodes)
    frontier: set[str] = set(seed_nodes)

    for _ in range(depth):
        next_frontier: set[str] = set()
        for node in frontier:
            neighbors = set(graph.successors(node)) | set(graph.predecessors(node))
            next_frontier |= neighbors - visited
        visited |= next_frontier
        frontier = next_frontier

    return visited


def build_context(graph: nx.DiGraph, nodes: set[str]) -> str:
    """Serializza i nodi espansi e le loro relazioni in una stringa di contesto."""
    lines: list[str] = []
    for node in sorted(nodes):
        attrs = graph.nodes[node]
        node_type = attrs.get("type", "unknown")

        if node_type == "document":
            title = attrs.get("title", node)
            lines.append(f"[DOCUMENTO: {node}] Titolo: {title}")
            for _, neighbor, edge_data in graph.out_edges(node, data=True):
                rel = edge_data.get("relation", "RELATES_TO")
                lines.append(f"  -> {rel} -> [{neighbor}]")

        elif node_type == "entity":
            lines.append(f"[ENTITÀ: {node}]")
            for predecessor, _, edge_data in graph.in_edges(node, data=True):
                rel = edge_data.get("relation", "CITED_IN")
                lines.append(f"  <- {rel} <- [{predecessor}]")

    return "\n".join(lines)


def call_llm(context: str, question: str) -> str:
    """Chiama il provider LLM configurato in rag_config.yaml."""
    system_prompt = (
        "Sei un assistente esperto del sistema HARO. "
        "Rispondi alla domanda usando esclusivamente il contesto del file fornito. "
        "Se il contesto non è sufficiente per rispondere, dillo esplicitamente."
    )
    user_message = f"Contesto grafo:\n{context}\n\nDomanda: {question}"

    if LLM_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=LLM_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return message.content[0].text

    elif LLM_PROVIDER == "openai":
        import openai
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content

    elif LLM_PROVIDER == "ollama":
        try:
            response = httpx.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.0
                    },
                },
                timeout=OLLAMA_TIMEOUT_SECONDS,
            )
            if response.status_code == 404:
                return f"[ERRORE OLLAMA]: Il modello '{LLM_MODEL}' non è stato trovato. Esegui 'ollama pull {LLM_MODEL}' nel terminale."
            response.raise_for_status()
            return response.json()["message"]["content"]
        except httpx.ConnectError:
            return "[ERRORE DI CONNESSIONE]: Impossibile raggiungere Ollama. Assicurati che l'applicazione Ollama sia avviata sul tuo computer."
        except httpx.TimeoutException:
            return "[ERRORE DI TIMEOUT]: Ollama sta impiegando troppo tempo a rispondere."
        except Exception as e:
            return f"[ERRORE GENERICO OLLAMA]: {str(e)}"

    raise ValueError(f"Provider LLM non supportato: '{LLM_PROVIDER}'")


# ---------------------------------------------------------------------------
# Pipeline Explore -> Canvas -> Propose (equivalente HTTP di explore.py,
# canvas.py e propose.py, con checkpoint di approvazione tra le fasi)
# ---------------------------------------------------------------------------
def slugify_feature(feature_name: str) -> str:
    return feature_name.strip().replace(" ", "-").lower()


def call_ollama_generate(prompt: str) -> str:
    """Chiama Ollama in modalità /api/generate (stessa modalità usata da explore/canvas/propose.py)."""
    data = {"model": PIPELINE_MODEL_NAME, "prompt": prompt, "stream": False}
    try:
        response = httpx.post(PIPELINE_OLLAMA_URL, json=data, timeout=OLLAMA_TIMEOUT_SECONDS)
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


@app.get("/api/pipeline/agent/modes")
async def agent_modes():
    """Elenca le modalità di fiducia disponibili per l'esecuzione con Claude Code."""
    return {"modes": [{"id": k, "label": v["label"]} for k, v in AGENT_MODES.items()]}


@app.post("/api/pipeline/agent/run")
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


@app.get("/api/pipeline/dev-types")
async def pipeline_dev_types():
    """Elenca le tipologie di sviluppo disponibili (sottocartelle di 'code/') per la tendina di selezione."""
    return {"dev_types": list_dev_types()}


@app.post("/api/pipeline/explore/turn")
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
    ai_response = call_ollama_generate(prompt)
    new_history = history + f"\nUtente: {req.user_input}\nIA: {ai_response}"
    return {"ai_response": ai_response, "history": new_history}


@app.post("/api/pipeline/explore/save")
async def pipeline_explore_save(req: ExploreSaveRequest):
    """Salva il log dell'intervista in changes/<feature>/explore.md."""
    folder = feature_dir(req.feature_name)
    save_dev_type(folder, req.dev_type)
    dev_type_line = f"**Tipo di sviluppo:** {req.dev_type}\n\n" if req.dev_type else ""
    file_path = folder / "explore.md"
    content = f"# Intervista Explore: {req.feature_name}\n\n{dev_type_line}{req.interview_log}"
    file_path.write_text(content, encoding="utf-8")
    return {"feature_folder": folder.name, "path": "explore.md", "content": content}


@app.post("/api/pipeline/canvas/generate")
async def pipeline_canvas_generate(req: CanvasGenerateRequest):
    """Genera il REASONS Canvas a partire dall'intervista Explore (equivalente a canvas.py)."""
    folder = feature_dir(req.feature_name)
    explore_path = folder / "explore.md"

    if explore_path.exists():
        contesto_intervista = explore_path.read_text(encoding="utf-8")
    else:
        contesto_intervista = "Nessun log di intervista dettagliato disponibile."

    contesto_progetto_base = "Contesto: Progetto PPA. Dominio richiesto @progettopa.it. Entità note: Utente, Evento."

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

    Informazioni generali di contesto del sistema:
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

    canvas_content = call_ollama_generate(prompt_strutturato)
    (folder / "canvas.md").write_text(canvas_content, encoding="utf-8")
    save_dev_type(folder, dev_type)
    return {"feature_folder": folder.name, "path": "canvas.md", "content": canvas_content}


@app.post("/api/pipeline/propose/generate")
async def pipeline_propose_generate(req: ProposeGenerateRequest):
    """Genera spec.md dal Canvas e il prompt finale per Claude Code (equivalente a propose.py)."""
    folder_name = slugify_feature(req.feature_folder)
    folder = CHANGES_DIR / folder_name
    canvas_path = folder / "canvas.md"

    if not canvas_path.exists():
        raise HTTPException(status_code=404, detail=f"Non trovo {canvas_path.name}. Devi prima generare il Canvas.")

    canvas_content = canvas_path.read_text(encoding="utf-8")
    dev_type = req.dev_type or load_dev_type(folder)

    prompt_strutturato = f"""
    Sei un Analista Software esperto in metodologie BDD (Behavior-Driven Development).
    Leggi questo REASONS Canvas:

    {canvas_content}

    Basandoti ESCLUSIVAMENTE sulle regole e sui requisiti scritti qui sopra, scrivi il file delle specifiche tecniche (spec.md).
    Devi definire gli scenari di test utilizzando rigorosamente il formato:
    - GIVEN (Dato che...)
    - WHEN (Quando...)
    - THEN (Allora...)
    - AND (E...)

    Non inventare funzionalità non presenti nel Canvas.
    """

    spec_content = call_ollama_generate(prompt_strutturato)
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


@app.get("/api/pipeline/status")
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


@app.get("/api/pipeline/file")
async def pipeline_get_file(feature: str, name: str):
    """Restituisce il contenuto di un file md della pipeline, per la visualizzazione di controllo."""
    if name not in PIPELINE_FILES:
        raise HTTPException(status_code=400, detail=f"File non consentito: {name}")
    folder_name = slugify_feature(feature)
    file_path = CHANGES_DIR / folder_name / name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"{name} non trovato per la feature '{folder_name}'.")
    return {"feature_folder": folder_name, "path": name, "content": file_path.read_text(encoding="utf-8")}


@app.post("/api/pipeline/file/save")
async def pipeline_save_file(req: PipelineFileSaveRequest):
    """Salva modifiche manuali a un file md prima dell'approvazione (revisione umana)."""
    if req.name not in PIPELINE_FILES:
        raise HTTPException(status_code=400, detail=f"File non consentito: {req.name}")
    folder = feature_dir(req.feature)
    (folder / req.name).write_text(req.content, encoding="utf-8")
    return {"feature_folder": folder.name, "path": req.name, "content": req.content}


@app.post("/ask")
async def ask_rag(query: AskQuery):
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

    # 3. Identifica i nodi seed nel grafo dai risultati della ricerca ibrida
    seed_nodes = [r["doc_id"] for r in search_results if r["doc_id"] in graph]

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

    # === NUOVA LOGICA: EVOLUZIONE GRAPH RAG (Iniezione Documenti Espansi) ===
    # Raccoglie i seed di Qdrant ed esplora i nodi della BFS per trovare documenti correlati (Multi-Hop)
    documenti_da_leggere = set(seed_nodes)
    for node_id in expanded_nodes:
        if graph.nodes[node_id].get("type") == "document":
            documenti_da_leggere.add(node_id)

    # Legge e inietta il testo Markdown fluido di TUTTI i documenti collegati
    context_parts: list[str] = []
    for doc_id in sorted(documenti_da_leggere):
        doc_path = PROJECT_ROOT / "docs" / doc_id
        if doc_path.exists():
            with open(doc_path, "r", encoding="utf-8") as f:
                context_parts.append(f"--- Inizio Documento: {doc_id} ---\n{f.read()}\n--- Fine Documento: {doc_id} ---")
    context = "\n\n".join(context_parts)
    # -----------------------------------------------------------------------

    # 5. Sintesi finale tramite LLM configurato
    start_time = time.time()
    answer = call_llm(context, query.question)
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


@app.get("/api/graph/all")
async def get_full_graph():
    """Restituisce l'intero grafo statico (tutti i nodi e gli archi) in formato JSON."""
    graph: nx.DiGraph = state["graph"]
    rule_descriptions: dict = state["rule_descriptions"]
    if graph is None:
        raise HTTPException(status_code=503, detail="Grafo non ancora inizializzato.")

    nodes = [
        {
            "id": node_id,
            "type": attrs.get("type", "unknown"),
            "title": attrs.get("title", node_id),
            "description": rule_descriptions.get(node_id, ""),
            # Pilastro REASONS di appartenenza (dal frontmatter YAML), per la colorazione cromatica del grafo
            "classification": attrs.get("classification", ""),
        }
        for node_id, attrs in graph.nodes(data=True)
    ]

    edges = [
        {
            "from": u,
            "to": v,
            "relation": data.get("relation", ""),
        }
        for u, v, data in graph.edges(data=True)
    ]

    return {"nodes": nodes, "edges": edges}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
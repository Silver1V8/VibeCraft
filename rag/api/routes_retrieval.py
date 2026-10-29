"""Route di retrieval: /ask (RAG completo con sintesi LLM e contesto grafo) e /api/retrieve
(retrieval puro per eval/debug). Gli handler iniettano le risorse di runtime dallo stato
(api.deps) nelle funzioni pure di core.retrieval / core.graph_ops / core.ask.

R2 (2026-10-28): la pipeline di /ask vive in core/ask.py; qui restano streaming NDJSON,
handler HTTP e le route di retrieve/code-search. I simboli sotto sono re-export / rebind
sul modulo routes_retrieval: i test monkeypatchano QUESTO modulo (require_snapshot,
GRAPH_CONTEXT_MAX_CHUNKS, question_router, …) e il logger strutturato M3 resta
`api.routes_retrieval`.
"""
import asyncio
import json
import logging
import types
from contextlib import aclosing as aclosing  # noqa: F401 — seam rebind /ask

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from FlagEmbedding import BGEM3FlagModel

from api.deps import (
    ask_runtime_for_app as ask_runtime_for_app,  # noqa: F401
    get_project,
    require_snapshot,
    ensure_shared_resources,
    embed_in_threadpool,
    qdrant_collection_for_version,
    require_api_key,
    require_cpu_get_rate_limit,
    require_not_cross_site_request,
    run_in_threadpool_until_complete as run_in_threadpool_until_complete,  # noqa: F401
    state,
)
from api.models import AskQuery
from core import ask as _ask_core
# Simboli usati dal bytecode di core.ask via rebind (e dai test che patchano il modulo).
from core import (  # noqa: F401
    ask_cache as ask_cache,
    ask_thread,
    graph_ops as graph_ops,
    llm as llm,
    retrieval,
    router as question_router,
)
from core.ask_thread import AskThreadStorageError
from core.projects import ProjectError as ProjectError, _unlinked as _unlinked  # noqa: F401
from core.config import (  # noqa: F401
    CODE_CONTEXT_MAX_SNIPPETS as CODE_CONTEXT_MAX_SNIPPETS,
    CODE_CONTEXT_MIN_WEIGHT as CODE_CONTEXT_MIN_WEIGHT,
    CODE_CONTEXT_TOTAL_SNIPPETS as CODE_CONTEXT_TOTAL_SNIPPETS,
    CODE_LINK_MIN_QUESTION_SCORE as CODE_LINK_MIN_QUESTION_SCORE,
    CODE_SEARCH_API_MAX_K,
    CODE_SEARCH_API_SNIPPET_CHARS,
    CODE_SEARCH_MAX_PER_FILE,
    CODE_SEARCH_MAX_SNIPPETS as CODE_SEARCH_MAX_SNIPPETS,
    CODE_SEARCH_MIN_SCORE,
    AUTHORITY_BOOST_ALPHA as AUTHORITY_BOOST_ALPHA,
    AUTHORITY_PRECEDENCE_RELATION as AUTHORITY_PRECEDENCE_RELATION,
    GRAPH_CONTEXT_MAX_CHUNKS as GRAPH_CONTEXT_MAX_CHUNKS,
    GRAPH_CONTEXT_MIN_RATIO as GRAPH_CONTEXT_MIN_RATIO,
    ROLE as ROLE,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_key)])

# --- Re-export / rebind da core.ask (seam monkeypatch stabile post-R2) ----------
# I corpi vivono in core/ask.py; le FunctionType rilegate usano i *globals di questo
# modulo*, così monkeypatch su routes_retrieval.require_snapshot / GRAPH_CONTEXT_* /
# question_router / ask_thread continuano a funzionare senza aggiornare ogni test.


def _rebind(fn):
    # Copia anche __kwdefaults__ (emit=None, resources=None): FunctionType non li porta.
    rebound = types.FunctionType(
        fn.__code__, globals(), fn.__name__, fn.__defaults__, fn.__closure__,
    )
    rebound.__kwdefaults__ = fn.__kwdefaults__
    rebound.__annotations__ = getattr(fn, "__annotations__", {})
    return rebound


ASK_MAX_CHARS_PER_CHUNK = _ask_core.ASK_MAX_CHARS_PER_CHUNK
_ASTENSIONE_RE = _ask_core._ASTENSIONE_RE
_cap_text = _rebind(_ask_core._cap_text)
_cache_get = _rebind(_ask_core._cache_get)
_cache_set = _rebind(_ask_core._cache_set)
_load_ask_thread = _rebind(_ask_core._load_ask_thread)
_persist_ask_turn = _rebind(_ask_core._persist_ask_turn)
_emit = _rebind(_ask_core._emit)
_ask_resources = _rebind(_ask_core._ask_resources)
_ask_pipeline = _rebind(_ask_core._ask_pipeline)

# Globals richiesti dal bytecode di core.ask (rebind): non usati dal testo di questo modulo.
import re as re  # noqa: E402, F401
import time as time  # noqa: E402, F401
import uuid as uuid  # noqa: E402, F401

import networkx as nx  # noqa: E402, F401
from qdrant_client import QdrantClient as QdrantClient  # noqa: E402, F401


def _stream_error(exc: Exception) -> dict:
    if isinstance(exc, HTTPException):
        detail = exc.detail
    elif isinstance(exc, TimeoutError):
        detail = "Timeout totale della richiesta /ask."
    else:
        detail = f"{type(exc).__name__}: {exc}"
    return {"type": "error", "detail": str(detail)}


async def _ask_stream(request: Request, query: AskQuery, runtime, resources):
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)

    async def produce() -> None:
        try:
            payload = await _ask_pipeline(
                request, query, emit=queue.put, resources=resources,
            )
            await queue.put({"type": "result", "value": payload})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Se il consumer ha chiuso la risposta, non può più drenare la coda. In
            # particolare un errore sollevato dal ``finally`` del provider dopo la
            # cancellazione non deve bloccarsi tentando di accodare un evento terminale.
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise
            await queue.put(_stream_error(exc))

    producer = asyncio.create_task(produce())
    try:
        while True:
            event = await queue.get()
            yield json.dumps(event, ensure_ascii=False) + "\n"
            if event["type"] in ("result", "error"):
                break
    finally:
        if not producer.done():
            producer.cancel()
        try:
            await producer
        except asyncio.CancelledError:
            pass


class _AskStreamingResponse(StreamingResponse):
    """Estende deadline e cleanup a header/body ASGI, anche se l'iteratore non parte."""

    def __init__(self, iterator, runtime):
        super().__init__(
            iterator, media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store"},
        )
        self._runtime = runtime

    async def __call__(self, scope, receive, send) -> None:
        try:
            async with asyncio.timeout(self._runtime.total_timeout):
                await super().__call__(scope, receive, send)
        finally:
            close = getattr(self.body_iterator, "aclose", None)
            try:
                if close is not None:
                    await close()
            finally:
                self._runtime.release()


def _thread_http_payload(project, thread: dict) -> dict:
    """Shape shared by GET/DELETE /api/ask/thread (and a guide for WP4 clients)."""
    return {
        "project_id": project.id,
        "thread": ask_thread.thread_summary(thread),
    }


def _map_thread_storage_error(exc: AskThreadStorageError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "project_storage_error",
            "message": str(exc) or "Archiviazione ask-thread non disponibile.",
        },
    )


@router.get("/api/ask/thread")
async def get_ask_thread(request: Request):
    """Return the short per-project /ask thread (empty when missing/corrupt)."""
    project = get_project(request)
    try:
        thread = await run_in_threadpool(ask_thread.load_thread, project)
    except AskThreadStorageError as exc:
        raise _map_thread_storage_error(exc) from exc
    return _thread_http_payload(project, thread)


@router.delete("/api/ask/thread", dependencies=[Depends(require_not_cross_site_request)])
async def delete_ask_thread(request: Request):
    """Reset the project thread (idempotent: empty thread when already clear)."""
    project = get_project(request)
    try:
        thread = await run_in_threadpool(ask_thread.reset_thread, project)
    except AskThreadStorageError as exc:
        raise _map_thread_storage_error(exc) from exc
    return _thread_http_payload(project, thread)


@router.post("/ask", dependencies=[Depends(require_not_cross_site_request)])
async def ask_rag(request: Request, query: AskQuery):
    runtime = ask_runtime_for_app(request.app)
    if not runtime.try_admit():
        raise HTTPException(
            status_code=429, detail="Troppe richieste /ask attive.",
            headers={"Retry-After": "1"},
        )
    try:
        resources = await _ask_resources(get_project(request))
    except Exception:
        runtime.release()
        raise
    if query.stream:
        return _AskStreamingResponse(
            _ask_stream(request, query, runtime, resources), runtime,
        )
    try:
        async with asyncio.timeout(runtime.total_timeout):
            return await _ask_pipeline(request, query, resources=resources)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Timeout totale della richiesta /ask.") from exc
    finally:
        runtime.release()


@router.get("/api/retrieve", dependencies=[Depends(require_cpu_get_rate_limit)])
async def api_retrieve(
    request: Request,
    q: str = Query(min_length=1, max_length=4000),
    k: int = Query(default=5, ge=1, le=50),
    include_text: bool = Query(default=False),
    text_max_chars: int = Query(default=2000, ge=1, le=8000),
):
    """Retrieval PURO (dense + sparse + ColBERT + authority), senza sintesi LLM. Restituisce
    i chunk pertinenti con il breakdown del ranking. Serve per valutare la qualità del ranking
    (golden-set / eval.run) e per il debug, senza il costo di Ollama.

    Input validato da FastAPI: `q` non vuota, `k` in [1, 50] (422 altrimenti). Il tetto resta
    50 — e non 20 come su /ask — perché qui non si costruisce alcun prompt: nessuna finestra
    di contesto da sfondare, il costo di un k alto è solo tempo di ranking.

    `maybe_reload_graph()` come /ask e /api/code/search. Senza, questa route era l'UNICA di
    retrieval a non ricaricare lo snapshot: dopo una promozione o un rollback l'alias Qdrant
    punta già alla collection nuova mentre i sidecar in memoria (ColBERT, chunk) restano
    quelli vecchi, e il ranking esce da uno stato MISTO. Il danno non è teorico: è proprio
    questa la route su cui gira eval.run, cioè lo strumento con cui si decide se una modifica
    ha migliorato o peggiorato il sistema — e lo sbaglio era silenzioso, con numeri plausibili."""
    project = get_project(request)
    snap = await run_in_threadpool(require_snapshot, project)
    await run_in_threadpool(ensure_shared_resources)
    if state.get("qdrant") is None or state.get("embed_model") is None or snap is None:
        raise HTTPException(status_code=503, detail="Indice non ancora pronto.")
    collection = snap.collection_name or qdrant_collection_for_version(snap.version, project=project)
    if collection == "unknown":
        if isinstance(snap.version, str) and snap.version != "legacy":
            raise HTTPException(status_code=503, detail="Collection dello snapshot non disponibile.")
        collection = project.collection_name  # layout flat precedente al blue/green
    results = await embed_in_threadpool(
        retrieval.hybrid_search, q, k,
        qdrant=state["qdrant"], embed_model=state["embed_model"], colbert_store=snap.colbert_store,
        collection_name=collection,
        # Stesso ranking della produzione, precedenza e peso di sezione compresi: eval.run
        # misura QUESTO, ed e' l'unico modo perche' il numero che ne esce voglia dire qualcosa.
        graph=snap.graph, restatements=snap.restatements, project=project,
    )
    if include_text:
        enriched = []
        for hit in results:
            chunk = snap.chunks.get(hit["chunk_id"])
            if chunk is None:
                raise HTTPException(status_code=503, detail="Testo assente nello snapshot del retrieval.")
            text = chunk.get("text", "")
            enriched.append({**hit, "source_label": retrieval.source_label(hit),
                             "text": text[:text_max_chars], "text_chars": len(text),
                             "text_truncated": len(text) > text_max_chars})
        results = enriched
    return {"query": q, "k": k, "results": results, "index_version": snap.version, "project_id": project.id,
            "limits": {"k": k, "text_max_chars": text_max_chars if include_text else None,
                       "exhaustive": False}}


# ---------------------------------------------------------------------------
# GET /api/code/search — l'indice del codice per un agente ESTERNO
#
# Perché esiste: un agente (Claude Code, Cursor) che deve modificare code/ non ha modo di
# sapere DOVE sta ciò che gli serve, e ripiega su Glob+Read a tappeto — il modo più caro
# possibile di rispondere a "dove sta la validazione dell'ordine?". I vettori densi dei simboli
# sono già in memoria (code.npz, precalcolati all'indicizzazione): questo endpoint li espone
# così l'agente sceglie QUALI file aprire e legge solo quelli.
#
# Il rischio è che la cura sia peggiore del male: se la risposta è grossa, l'agente paga i token
# dell'indice E poi quelli dei file. Perciò la risposta è NAVIGAZIONALE per default —
# symbol_id, file, kind, score, e l'aggregato `files` — e NON contiene il testo dei simboli;
# `snippet=true` lo aggiunge troncato, per i casi in cui il nome non basta a decidere.
#
# Nessun LLM e nessuna query a Qdrant: una forward pass di bge-m3 sulla domanda e un prodotto
# matriciale in memoria. È l'unico endpoint di ricerca che non tocca la rete.
# ---------------------------------------------------------------------------
def _code_hit_view(hit: dict, *, with_snippet: bool,
                   snippet_chars: int = CODE_SEARCH_API_SNIPPET_CHARS) -> dict:
    """Voce di risposta di /api/code/search: la forma di retrieval._code_entry meno ciò che
    all'agente non serve per decidere quale file aprire. `source` cade (qui è sempre
    "semantic"), `implements` resta solo se il linking l'ha calcolata, `text` solo su richiesta
    e troncato — è il campo che da solo può decuplicare la risposta."""
    view = {
        "symbol_id": hit["symbol_id"],
        "name": hit["name"],
        "kind": hit["kind"],
        "file": hit["file"],
        "dev_type": hit["dev_type"],
        "score": hit["score"],
    }
    if hit.get("implements"):
        view["implements"] = hit["implements"]
    if with_snippet:
        text = str(hit.get("text") or "")
        view["text_truncated"] = len(text) > snippet_chars
        view["text_chars"] = len(text)
        view["text"] = (text[:snippet_chars].rstrip() + " …"
                        if len(text) > snippet_chars else text)
    return view


def _files_digest(hits: list[dict]) -> list[dict]:
    """Aggregato per FILE dei simboli trovati, in ordine di pertinenza. È la parte di risposta
    che l'agente usa davvero — l'elenco dei file da aprire — e costa poche decine di token:
    tenerla separata gli evita di dover dedurre i path scorrendo i simboli."""
    per_file: dict[str, dict] = {}
    for hit in hits:
        entry = per_file.setdefault(hit["file"], {"file": hit["file"], "symbols": 0,
                                                  "best_score": hit["score"]})
        entry["symbols"] += 1
        entry["best_score"] = max(entry["best_score"], hit["score"])
    return sorted(per_file.values(), key=lambda e: e["best_score"], reverse=True)


@router.get("/api/code/search", dependencies=[Depends(require_cpu_get_rate_limit)])
async def api_code_search(
    request: Request,
    q: str = Query(min_length=1, max_length=2000),
    k: int = Query(default=8, ge=1, le=CODE_SEARCH_API_MAX_K),
    dev_type: str = Query(default="", max_length=64),
    snippet: bool = Query(default=False),
    min_score: float = Query(default=CODE_SEARCH_MIN_SCORE, ge=0.0, le=1.0),
    max_per_file: int = Query(default=CODE_SEARCH_MAX_PER_FILE, ge=0, le=10),
):
    """Ricerca semantica sui SIMBOLI di codice indicizzati (coseno domanda→simbolo sui vettori
    densi già calcolati all'indicizzazione). Risponde a "quali file devo aprire per...".

    Parametri: `k` numero di simboli (tetto CODE_SEARCH_API_MAX_K); `dev_type` restringe a un
    ambito (sottocartella di code/); `snippet=true` include il testo dei simboli, troncato;
    `min_score` soglia di coseno; `max_per_file` quanti simboli può contribuire uno stesso file
    (0 = nessun limite), che impedisce a un file autogenerato di occupare tutte le posizioni.

    La risposta NON è una fonte di verità sul contenuto dei file: è uno snapshot dell'ultima
    indicizzazione e serve solo a scegliere cosa leggere. `index_version` dice su quale versione
    dell'indice è stata calcolata."""
    project = get_project(request)
    settings = project.settings.get("retrieval", {})
    k = min(k, max(1, settings.get("code_search_api_max_k", CODE_SEARCH_API_MAX_K)))
    if "min_score" not in request.query_params:
        min_score = settings.get("code_search_min_score", min_score)
    if "max_per_file" not in request.query_params:
        max_per_file = settings.get("code_search_max_per_file", max_per_file)
    snippet_chars = max(1, settings.get("code_search_api_snippet_chars", CODE_SEARCH_API_SNIPPET_CHARS))
    snap = await run_in_threadpool(require_snapshot, project)
    await run_in_threadpool(ensure_shared_resources)
    embed_model: BGEM3FlagModel = state.get("embed_model")
    if snap is None or embed_model is None:
        raise HTTPException(status_code=503, detail="Indice non ancora pronto.")

    base = {"query": q, "k": k, "dev_type": dev_type, "index_version": snap.version, "project_id": project.id,
            "limits": {"k": k, "min_score": min_score, "max_per_file": max_per_file,
                       "snippet_chars": snippet_chars if snippet else None,
                       "exhaustive": False}}

    # Nessun simbolo indicizzato: risposta esplicita invece di un elenco vuoto ambiguo — la
    # differenza fra "non c'è codice nell'indice" e "non c'è nulla di pertinente" cambia cosa
    # deve fare l'agente (nel primo caso ripiegare su Glob/Grep, non insistere con la ricerca).
    if snap.code_matrix is None or not snap.code_ids:
        return {**base, "count": 0, "files": [], "results": [],
                "note": "Nessun simbolo di codice nell'indice: usa Glob/Grep sul filesystem."}

    subset_idx = None
    if dev_type:
        subset_idx = snap.code_dev_type_idx.get(dev_type)
        if subset_idx is None:
            # Ambito inesistente (typo o cartella non ancora indicizzata): 200 con gli ambiti
            # disponibili, non 404. L'agente può correggersi da solo con la stessa risposta;
            # un errore lo costringerebbe a un giro in più per scoprire i valori validi.
            return {**base, "count": 0, "files": [], "results": [],
                    "available_dev_types": sorted(snap.code_dev_type_idx),
                    "note": f"Nessun simbolo indicizzato per l'ambito '{dev_type}'."}

    encoding = await embed_in_threadpool(retrieval.encode_query, embed_model, q)
    hits = await run_in_threadpool_until_complete(
        retrieval.search_code_symbols, encoding["dense"], snap.code_store,
        max_snippets=k, min_score=min_score, max_per_file=max_per_file,
        code_ids=snap.code_ids, code_matrix=snap.code_matrix, subset_idx=subset_idx,
    )
    return {
        **base,
        "count": len(hits),
        "files": _files_digest(hits),
        "results": [_code_hit_view(h, with_snippet=snippet, snippet_chars=snippet_chars) for h in hits],
    }

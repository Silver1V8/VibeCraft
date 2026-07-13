"""Dependency injection e stato condiviso dello strato HTTP: stato di runtime del server
(grafo, Qdrant, modello di embedding, sidecar), autenticazione, lifespan di caricamento
risorse, auto-reload dell'indice e helper di streaming/template. I router in api/ leggono
questo stato e lo iniettano nelle funzioni pure di core/."""
import json
import os
import queue
import re
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from qdrant_client import QdrantClient
from FlagEmbedding import BGEM3FlagModel

from core.artifacts import load_artifacts
from core.config import (
    EMBEDDING_MODEL,
    GRAPH_JSON_PATH,
    GRAPH_SAVE_PATH,
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
# Snapshot immutabile degli artefatti dell'indice (HARDENING #3, risolto)
# ---------------------------------------------------------------------------
# Gli artefatti che cambiano insieme a ogni re-indicizzazione (grafo, ColBERT,
# chunk, descrizioni regole) vivono in un unico oggetto FROZEN. Il reload NON muta
# lo stato chiave per chiave — costruisce un NUOVO IndexSnapshot completo e lo
# rebinda con un SOLO assegnamento atomico (`state["snapshot"] = ...`). Così un
# handler che legge lo snapshot una volta a inizio richiesta vede sempre una
# versione internamente coerente (grafo + chunk della stessa build), mai un mix.
#
# Le risorse "connessione" (qdrant, embed_model) restano FUORI dallo snapshot:
# sono aperte una volta al boot e non cambiano al reload dell'indice.
@dataclass(frozen=True)
class IndexSnapshot:
    graph: object | None
    colbert_store: dict
    chunks: dict
    rule_descriptions: dict
    version: float | None  # mtime del file-grafo (graph.json) al momento della build dello snapshot


# ---------------------------------------------------------------------------
# Stato globale del server (popolato durante il lifespan)
# `state["snapshot"]` è l'unico riferimento agli artefatti dell'indice: viene
# REBINDATO atomicamente al reload, mai mutato in place. qdrant/embed_model sono
# connessioni stabili. `_graph_mtime` è la baseline che innesca l'auto-reload.
# ---------------------------------------------------------------------------
state: dict = {
    "snapshot": None,
    "qdrant": None,
    "embed_model": None,
}


def current_snapshot() -> IndexSnapshot | None:
    """Riferimento atomico allo snapshot corrente dell'indice. Ogni handler lo chiama
    UNA volta a inizio richiesta e usa solo l'oggetto restituito: essendo frozen e
    rebindato (mai mutato), il contenuto resta internamente coerente anche se un reload
    avviene a metà richiesta (il reload rebinda `state["snapshot"]`, non tocca l'oggetto
    già in mano all'handler)."""
    return state.get("snapshot")


def _graph_version() -> float | None:
    """mtime del file-grafo corrente (graph.json), con fallback al legacy graph.pkl.
    È la baseline che innesca l'auto-reload quando una re-indicizzazione riscrive il grafo."""
    for path in (GRAPH_JSON_PATH, GRAPH_SAVE_PATH):
        try:
            return path.stat().st_mtime
        except OSError:
            continue
    return None


def _build_snapshot(graph, colbert_store, chunks, rule_descriptions) -> IndexSnapshot:
    """Assembla un IndexSnapshot catturando la version (mtime del file-grafo)."""
    version = _graph_version()
    return IndexSnapshot(
        graph=graph,
        colbert_store=colbert_store,
        chunks=chunks,
        rule_descriptions=rule_descriptions,
        version=version,
    )


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

    print("Caricamento artefatti indice (grafo JSON, ColBERT/chunk) ...")
    try:
        arts = load_artifacts(required=("graph",))
    except FileNotFoundError:
        raise RuntimeError(
            "Grafo non trovato (né graph.json né graph.pkl). Esegui prima 'python index.py' per indicizzare."
        )
    graph = arts.graph
    colbert_store = arts.colbert_store
    chunks = arts.chunks_store
    print(f"Grafo caricato: {graph.number_of_nodes()} nodi, {graph.number_of_edges()} archi.")
    print(f"Multivettori ColBERT caricati: {len(colbert_store)} chunk. Chunk sidecar: {len(chunks)} sezioni.")

    print("Caricamento descrizioni regole dai file spec...")
    rule_descriptions = load_rule_descriptions()

    # Rebind atomico dello snapshot iniziale (un solo assegnamento).
    state["snapshot"] = _build_snapshot(graph, colbert_store, chunks, rule_descriptions)
    state["_graph_mtime"] = _graph_version()  # baseline per l'auto-reload
    print("Server pronto.\n")

    yield  # il server è in esecuzione

    print("Shutdown: rilascio risorse.")
    state["qdrant"].close()


# ---------------------------------------------------------------------------
# Auto-reload dell'indice in memoria (dopo una re-indicizzazione da CLI o pipeline)
# ---------------------------------------------------------------------------
def reload_index_state() -> None:
    """Ricarica in memoria grafo, multivettori ColBERT e sidecar chunk dai file appena
    rigenerati dalla re-indicizzazione, così che il server rifletta subito la nuova base
    di conoscenza senza riavvio.

    Il reload è COERENTE (tutto-o-niente): gli artefatti vengono prima caricati in
    variabili locali; solo se grafo + ColBERT + chunk sono tutti presenti e integri lo
    stato viene sostituito. Se anche uno solo è mancante o corrotto (es. una re-
    indicizzazione ancora in corso o abortita), si logga un warning e si MANTIENE la
    versione precedente in memoria, evitando di degradare il server (grafo senza
    ColBERT/chunk)."""
    try:
        arts = load_artifacts(required=("graph", "colbert", "chunks"), emit=lambda *_a, **_k: None)
        rule_descriptions = load_rule_descriptions()
    except Exception as exc:
        print(f"⚠️  Reload indice annullato ({type(exc).__name__}: {exc}): "
              "artefatto mancante o corrotto, mantengo in memoria la versione precedente.")
        # Aggiorna comunque il baseline mtime: se il file è corrotto in modo persistente,
        # evita di ritentare (e ri-loggare) il reload a ogni richiesta successiva. Una
        # nuova build completa cambierà di nuovo l'mtime e ritenterà il reload.
        state["_graph_mtime"] = _graph_version()
        return

    # Rebind ATOMICO: un solo IndexSnapshot completo sostituisce quello precedente.
    # Nessuna mutazione in place → nessun handler può osservare una versione mista.
    state["snapshot"] = _build_snapshot(arts.graph, arts.colbert_store, arts.chunks_store, rule_descriptions)
    state["_graph_mtime"] = _graph_version()


def maybe_reload_graph() -> None:
    """Auto-reload: se graph.pkl è cambiato su disco (es. una re-indicizzazione lanciata
    da CLI mentre il server è attivo), ricarica l'indice in memoria alla prima richiesta
    successiva, senza dover riavviare il server."""
    if current_snapshot() is None:
        return
    mtime = _graph_version()
    if mtime is None:
        return
    prev = state.get("_graph_mtime")
    if prev is None:
        state["_graph_mtime"] = mtime
        return
    if mtime != prev:
        print("🔄 grafo cambiato su disco: ricarico grafo/ColBERT/regole in memoria.")
        reload_index_state()


def run_streaming(target, *args):
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


# ---------------------------------------------------------------------------
# Serving dei template a tema (Matrix / Classico) — TEMPLATES_DIR è assoluto
# (derivato da core/config.py), quindi indipendente dalla working directory.
# ---------------------------------------------------------------------------
NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


def themed_template(request: Request, matrix_name: str, classic_name: str) -> Path:
    """Sceglie il file da servire in base al tema scelto dall'utente (cookie 'ui_theme')."""
    theme = request.cookies.get("ui_theme", "matrix")
    return TEMPLATES_DIR / (classic_name if theme == "classic" else matrix_name)


# ---------------------------------------------------------------------------
# Dedup template (Punto 5): pagina unificata + data-theme iniettato lato server,
# con fallback retrocompatibile sulla vecchia coppia Matrix/Classico finché la
# versione unificata non esiste. Vedi templates/CLAUDE_DESIGN_CONTRACT.md.
# ---------------------------------------------------------------------------
VALID_THEMES = ("matrix", "classic")

_HTML_TAG_RE = re.compile(r"<html\b([^>]*)>", re.IGNORECASE)
_DATA_THEME_ATTR_RE = re.compile(r'data-theme\s*=\s*"[^"]*"', re.IGNORECASE)


def _inject_data_theme(html: str, theme: str) -> str:
    """Imposta (o sostituisce, se già presente) l'attributo data-theme sul tag <html> di
    apertura, lato server, dal cookie 'ui_theme' — evita il flash del tema sbagliato al
    primo paint (il CSS `:root[data-theme=...]` si applica già al primo render).
    Se il tag <html> non viene trovato, restituisce il markup invariato (fail-open: mai
    un 500 per un template imprevisto, solo niente iniezione)."""
    match = _HTML_TAG_RE.search(html)
    if not match:
        return html
    attrs = match.group(1)
    if _DATA_THEME_ATTR_RE.search(attrs):
        new_attrs = _DATA_THEME_ATTR_RE.sub(f'data-theme="{theme}"', attrs)
    else:
        new_attrs = f'{attrs} data-theme="{theme}"'
    return html[:match.start()] + f"<html{new_attrs}>" + html[match.end():]


def serve_page(request: Request, unified_name: str, matrix_name: str, classic_name: str) -> Response:
    """Serve UNA pagina: se `unified_name` esiste sotto TEMPLATES_DIR (versione dedupata,
    un solo file con CSS variables — consegnata da Claude Design), la serve iniettando
    data-theme dal cookie 'ui_theme'. Altrimenti (transizione in corso) ricade sulla
    vecchia coppia di file `matrix_name`/`classic_name`, invariata — così le pagine
    possono essere migrate una alla volta senza rompere le altre.

    Nota sul cache: la lettura del file unificato NON è cachata in process — è I/O locale
    su un template di poche decine di KB, il costo è trascurabile rispetto a NO_CACHE_HEADERS
    che comunque impedisce la cache lato browser."""
    theme = request.cookies.get("ui_theme", "matrix")
    if theme not in VALID_THEMES:
        theme = "matrix"

    unified_path = TEMPLATES_DIR / unified_name
    if unified_path.exists():
        html = unified_path.read_text(encoding="utf-8")
        html = _inject_data_theme(html, theme)
        return HTMLResponse(html, headers=NO_CACHE_HEADERS)

    # Fallback: pagina non ancora unificata -> vecchia coppia di file per tema (invariata).
    legacy_path = themed_template(request, matrix_name, classic_name)
    return FileResponse(legacy_path, media_type="text/html", headers=NO_CACHE_HEADERS)

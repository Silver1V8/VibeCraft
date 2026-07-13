"""Composition root della console HARO Graph-RAG: assembla l'app FastAPI (lifespan +
mount dei router) e la avvia. La logica di dominio vive in core/ (pura, testabile) e lo
strato HTTP in api/ (route handler sottili, modelli Pydantic, dependency injection).
Avvio: `python server.py` oppure `uvicorn server:app` (host/porta via env VIBECRAFT_*)."""
import os
import sys

# Forza UTF-8 su stdout/stderr: le emoji dei log crasherebbero su console cp1252
# (Windows) quando l'output è rediretto verso un file o un servizio.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.deps import API_KEY, lifespan
from api import routes_graph, routes_pages, routes_pipeline, routes_reindex, routes_retrieval
from core.config import STATIC_DIR

app = FastAPI(title="HARO Graph-RAG Console", lifespan=lifespan)

# Asset statici condivisi (shared.css / shared.js) estratti dai template per
# non duplicare CSS/JS: serviti aperti da /static, come le pagine HTML.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Pagine HTML (aperte) + router API protetti da X-API-Key (require_api_key a livello di router).
app.include_router(routes_pages.router)
app.include_router(routes_pipeline.router)
app.include_router(routes_reindex.router)
app.include_router(routes_retrieval.router)
app.include_router(routes_graph.router)


# ---------------------------------------------------------------------------
# HARDENING — rischi residui noti (da affrontare prima di un uso non locale)
# ---------------------------------------------------------------------------
# 1. QDRANT: risolto. Qdrant gira in server mode (Docker, vedi docker-compose.yml),
#    niente più lock esclusivo sullo storage — configurabile via QDRANT_URL /
#    QDRANT_API_KEY. L'iniezione di qdrant/embed_model nel re-index resta comunque
#    utile per evitare il ricaricamento del modello di embedding (minuti di CPU).
# 2. BIND & AUTH: risolto. Default host 127.0.0.1; tutti gli endpoint /api/* e /ask
#    richiedono X-API-Key (env VIBECRAFT_API_KEY) per chi non chiama da localhost —
#    vedi api/deps.py::require_api_key. Chi vuole esporre il server sulla rete deve
#    impostare sia VIBECRAFT_HOST che VIBECRAFT_API_KEY.
# 3. STATO GLOBALE NON PROTETTO: `state` (api/deps.py) è un dict globale che
#    maybe_reload_graph sostituisce mentre i thread del pool lo leggono. Oggi regge per
#    il GIL e perché le sostituzioni sono atomiche (rebinding di riferimenti), ma è
#    fragile per costruzione. TODO: un threading.RLock attorno a load/reload e alle
#    letture di graph/qdrant/colbert/chunks, oppure uno snapshot immutabile atomico.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    host = os.environ.get("VIBECRAFT_HOST", "127.0.0.1")
    port = int(os.environ.get("VIBECRAFT_PORT", "8000"))
    if host != "127.0.0.1" and not API_KEY:
        print("⚠️  Server esposto oltre localhost (VIBECRAFT_HOST) SENZA VIBECRAFT_API_KEY: "
              "tutte le richieste non-locali ai /api/* verranno rifiutate (fail-closed).")
    uvicorn.run(app, host=host, port=port)

"""Composition root della console Graph-RAG: assembla l'app FastAPI (lifespan +
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

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.config import SERVER_BIND_IS_LOCAL, STATIC_DIR, setup_logging

# Configurazione centrale del logging PRIMA degli import applicativi: i moduli usano
# logging.getLogger(__name__) e vedono formato/livello (VIBECRAFT_LOG_LEVEL) coerenti.
setup_logging()
logger = logging.getLogger(__name__)

from api.deps import API_KEY, NO_CACHE_HEADERS, lifespan
from api import (
    routes_graph,
    routes_health,
    routes_intake,
    routes_pages,
    routes_pipeline,
    routes_reindex,
    routes_retrieval,
)

app = FastAPI(title="HARO Graph-RAG Console", lifespan=lifespan)

# shared.css / shared.js cambiano spesso durante lo sviluppo locale, ma
# StaticFiles li servirebbe con caching euristico del browser (nessun
# Cache-Control: solo Last-Modified/ETag). Le pagine HTML sono già servite
# NO_CACHE_HEADERS (vedi api/deps.py::serve_page): senza lo stesso trattamento
# qui, una tab aperta da prima di un aggiornamento continua a vedere il CSS/JS
# vecchio contro un HTML sempre fresco — l'HTML referenzia classi (.app-nav,
# .page-doc, .skip-link, ...) che nel CSS in cache non esistono ancora, e la
# UI si rompe in modo silenzioso e diverso per ogni tab. Route esplicite,
# registrate PRIMA del mount così intercettano questi due file soli; il resto
# di /static (i vendor pinnati) resta sotto la cache di default del browser,
# che qui è corretta: non cambiano fra un deploy e l'altro.
@app.get("/static/shared.css", include_in_schema=False)
def _shared_css() -> FileResponse:
    return FileResponse(STATIC_DIR / "shared.css", media_type="text/css", headers=NO_CACHE_HEADERS)


@app.get("/static/shared.js", include_in_schema=False)
def _shared_js() -> FileResponse:
    return FileResponse(STATIC_DIR / "shared.js", media_type="text/javascript", headers=NO_CACHE_HEADERS)


# Asset statici condivisi (shared.css / shared.js) estratti dai template per
# non duplicare CSS/JS: serviti aperti da /static, come le pagine HTML.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Pagine HTML (aperte) + router API protetti da X-API-Key (require_api_key a livello di router).
app.include_router(routes_pages.router)
app.include_router(routes_pipeline.router)
app.include_router(routes_reindex.router)
app.include_router(routes_retrieval.router)
app.include_router(routes_graph.router)
app.include_router(routes_health.router)
app.include_router(routes_intake.router)


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
# 3. STATO GLOBALE NON PROTETTO: risolto. Gli artefatti dell'indice che cambiano
#    insieme (graph/colbert/chunks/rule_descriptions) vivono in un IndexSnapshot FROZEN
#    (api/deps.py). Il reload costruisce un nuovo snapshot completo e lo rebinda con un
#    solo assegnamento atomico (`state["snapshot"] = ...`), mai mutazione in place; ogni
#    handler prende lo snapshot UNA volta a inizio richiesta (current_snapshot()) e usa
#    solo quello, quindi non può mai osservare una versione mista (graph nuovo + chunk
#    vecchi). Le connessioni qdrant/embed_model restano fuori dallo snapshot (non
#    cambiano al reload).
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    host = os.environ.get("VIBECRAFT_HOST", "127.0.0.1")
    port = int(os.environ.get("VIBECRAFT_PORT", "8000"))
    if host != "127.0.0.1" and not API_KEY:
        logger.warning("Server esposto oltre localhost (VIBECRAFT_HOST) SENZA VIBECRAFT_API_KEY: "
                       "tutte le richieste non-locali ai /api/* verranno rifiutate (fail-closed).")
    if not SERVER_BIND_IS_LOCAL:
        # Detto all'avvio e non solo al 403: chi apre il bind scopre così, subito, che due
        # funzioni della pagina Intake non risponderanno più — invece di leggerlo come un
        # errore inspiegabile al primo click (api.deps.require_local_bind).
        logger.warning("Bind non locale (VIBECRAFT_HOST=%s): il selettore di cartelle nativo "
                       "(POST /api/intake/project/browse-path) e l'anteprima di import "
                       "(POST /api/intake/project/plan) sono DISABILITATI — hanno senso solo "
                       "con server e utente sulla stessa macchina.", host)
    uvicorn.run(app, host=host, port=port)

"""Route delle pagine HTML (dashboard, pipeline, infografica, analisi). Non protette da
API key (sono solo shell statiche, nessun dato). Ogni pagina passa da api.deps.serve_page,
che serve la versione unificata (un file, CSS variables + data-theme iniettato dal server)
se esiste, altrimenti ricade sulla vecchia coppia Matrix/Classico — vedi
templates/CLAUDE_DESIGN_CONTRACT.md per il contratto di migrazione."""
from html import escape

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from api.deps import NO_CACHE_HEADERS, SERVER_BIND_IS_LOCAL, inject_agent_api_key, serve_page as _serve_page

router = APIRouter()
reader_router = APIRouter()


def serve_page(request: Request, *templates):
    response = _serve_page(request, *templates)
    if isinstance(response, HTMLResponse):
        project = escape(request.query_params.get("project", ""), quote=True)
        metadata = (f'<meta name="vibecraft-project" content="{project}">'
                    f'<meta name="vibecraft-local-bind" content="{str(SERVER_BIND_IS_LOCAL).lower()}">')
        html = response.body.decode("utf-8").replace("<head>", "<head>" + metadata, 1)
        return HTMLResponse(html, headers=NO_CACHE_HEADERS)
    return response


@reader_router.get("/", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def serve_dashboard(request: Request):
    """Serve la dashboard HTML interattiva."""
    return serve_page(request, "dashboard.unified.html", "dashboard.html", "dashboard_classic.html")


@router.get("/pipeline", include_in_schema=False)
async def serve_pipeline(request: Request):
    """Serve la console Explore -> Canvas -> Propose, iniettando la X-API-Key di
    /api/pipeline/agent/run (solo per client locali — vedi inject_agent_api_key) così il
    pulsante 'Esegui' funziona subito dopo un riavvio del server, senza doverla reimpostare
    a mano in localStorage da console."""
    response = serve_page(request, "pipeline.unified.html", "pipeline.html", "pipeline_classic.html")
    if isinstance(response, HTMLResponse):
        html = inject_agent_api_key(response.body.decode("utf-8"), request)
        response = HTMLResponse(html, headers=NO_CACHE_HEADERS)
    return response


@reader_router.get("/infografica", include_in_schema=False)
@router.get("/infografica", include_in_schema=False)
async def serve_infografica(request: Request):
    """Serve l'infografica statica del sistema RAG."""
    return serve_page(request, "infografica.unified.html", "InfograficaRAG.html", "InfograficaRAG_classic.html")


@reader_router.get("/analysis", include_in_schema=False)
@router.get("/analysis", include_in_schema=False)
async def serve_analysis(request: Request):
    """Serve la pagina di analisi del grafo (Semantic Map + Impact Ripple)."""
    return serve_page(request, "graph_analysis.unified.html", "graph_analysis.html", "graph_analysis_classic.html")


@router.get("/eval", include_in_schema=False)
async def serve_eval_trend(request: Request):
    """Serve la pagina del trend di qualità del retrieval (recall@10 nel tempo, Epic 5)."""
    return serve_page(request, "eval_trend.unified.html", "eval_trend.unified.html", "eval_trend.unified.html")


@router.get("/intake", include_in_schema=False)
async def serve_intake(request: Request):
    """Serve la pagina Intake & Import (genera con Ollama, importa documenti, review staging)."""
    return serve_page(request, "intake.unified.html", "intake.unified.html", "intake.unified.html")

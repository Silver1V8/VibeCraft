"""Route delle pagine HTML (dashboard, pipeline, infografica, analisi). Non protette da
API key (sono solo shell statiche, nessun dato). Servono i template a tema Matrix/Classico."""
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from api.deps import NO_CACHE_HEADERS, themed_template

router = APIRouter()


@router.get("/", response_class=FileResponse, include_in_schema=False)
async def serve_dashboard(request: Request):
    """Serve la dashboard HTML interattiva (tema Matrix o Classico, a scelta dell'utente)."""
    return FileResponse(themed_template(request, "dashboard.html", "dashboard_classic.html"), media_type="text/html", headers=NO_CACHE_HEADERS)


@router.get("/pipeline", response_class=FileResponse, include_in_schema=False)
async def serve_pipeline(request: Request):
    """Serve la console Explore -> Canvas -> Propose (tema Matrix o Classico, a scelta dell'utente)."""
    return FileResponse(themed_template(request, "pipeline.html", "pipeline_classic.html"), media_type="text/html", headers=NO_CACHE_HEADERS)


@router.get("/infografica", response_class=FileResponse, include_in_schema=False)
async def serve_infografica(request: Request):
    """Serve l'infografica statica del sistema RAG (tema Matrix o Classico, a scelta dell'utente)."""
    return FileResponse(themed_template(request, "InfograficaRAG.html", "InfograficaRAG_classic.html"), media_type="text/html", headers=NO_CACHE_HEADERS)


@router.get("/analysis", response_class=FileResponse, include_in_schema=False)
async def serve_analysis(request: Request):
    """Serve la pagina di analisi del grafo (Semantic Map + Impact Ripple), tema Matrix o Classico."""
    return FileResponse(themed_template(request, "graph_analysis.html", "graph_analysis_classic.html"), media_type="text/html", headers=NO_CACHE_HEADERS)

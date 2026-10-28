"""Dependency injection e stato condiviso dello strato HTTP.

R1 (2026-10-28): la logica è in api/auth.py, api/security_middleware.py,
api/index_runtime.py e api/pages.py. Questo modulo resta il *seam* di
monkeypatch dei test e il punto di import stabile (re-export).
"""
import asyncio
import logging
import os
import threading
from collections import OrderedDict

# Re-export espliciti (`as name`): seam monkeypatchabili e superficie stabile per i test.
from FlagEmbedding import BGEM3FlagModel as BGEM3FlagModel
from qdrant_client import QdrantClient as QdrantClient

from core.artifacts import (
    IMMUTABLE_MARKER_FILENAME as IMMUTABLE_MARKER_FILENAME,
    LEGACY_VERSION as LEGACY_VERSION,
    artifact_hashes as artifact_hashes,
    current_version_token as current_version_token,
    load_artifacts as load_artifacts,
    manifest_path as manifest_path,
    _project_artifact_path as _project_artifact_path,
)
from core.config import (
    COLLECTION_NAME as COLLECTION_NAME,
    DATABASE_DIR as DATABASE_DIR,
    EMBEDDING_MODEL as EMBEDDING_MODEL,
    GRAPH_JSON_PATH as GRAPH_JSON_PATH,
    OLLAMA_TIMEOUT_SECONDS as OLLAMA_TIMEOUT_SECONDS,
    PROJECT_ROOT as PROJECT_ROOT,
    QDRANT_API_KEY as QDRANT_API_KEY,
    QDRANT_URL as QDRANT_URL,
    ROLE as ROLE,
    SERVER_BIND_IS_LOCAL as SERVER_BIND_IS_LOCAL,
    SERVER_HOST as SERVER_HOST,
    TEMPLATES_DIR as TEMPLATES_DIR,
)

logger = logging.getLogger(__name__)

# --- Auth / bind seams (test monkeypatch) ------------------------------------
API_KEY = os.environ.get("VIBECRAFT_API_KEY")
GITLAB_TOKEN = os.environ.get("VIBECRAFT_GITLAB_TOKEN")

# --- Index runtime seams -----------------------------------------------------
# Stato globale del server (popolato durante il lifespan).
# `state["snapshot"]` è l'unico riferimento agli artefatti dell'indice: viene
# REBINDATO atomicamente al reload, mai mutato in place. qdrant/embed_model sono
# connessioni stabili. `_graph_mtime` è la baseline che innesca l'auto-reload.
state: dict = {
    "snapshot": None,
    "qdrant": None,
    "embed_model": None,
    "reload_error": None,
    "lock": threading.RLock(),
}

# Semaforo di concorrenza sull'embedding CPU: state["embed_model"] è un'unica
# istanza CPU condivisa, senza limite più richieste in parallelo mandano la coda
# torch in thrash e il p99 esplode. Bound configurabile, default 2.
EMBED_CONCURRENCY = int(os.environ.get("VIBECRAFT_EMBED_CONCURRENCY", "2"))
embed_semaphore = asyncio.Semaphore(EMBED_CONCURRENCY)

# Rate-limit delle GET CPU-pesanti (/api/retrieve, /api/code/search, /api/graph/semantic-map).
# Il semaforo embed limita la concorrenza; questo limita la FREQUENZA per IP client.
# Default: EMBED_CONCURRENCY * 15 richieste nella finestra (con 2 → 30/60s). Fail-closed 429.
# Debito chiuso: SECURITY_SURFACE.md §4 #4 (quick win R3, 2026-10-28).
_CPU_GET_RATE_DEFAULT = max(EMBED_CONCURRENCY * 15, 15)
CPU_GET_RATE_LIMIT = int(os.environ.get("VIBECRAFT_CPU_GET_RATE_LIMIT", str(_CPU_GET_RATE_DEFAULT)))
CPU_GET_RATE_WINDOW_SECONDS = float(os.environ.get("VIBECRAFT_CPU_GET_WINDOW_SECONDS", "60"))

_qdrant_collection_by_version: dict = {}
_registry = None
_registry_lock = threading.Lock()
_resources_lock = threading.Lock()
_project_states: dict[str, dict] = {}
_snapshots: OrderedDict = OrderedDict()
# Serializza i reload (auto-reload dalle richieste, on_success del thread di reindex,
# rollback, intake): due caricamenti paralleli raddoppierebbero memoria e I/O.
# RLock: require_snapshot cattura il riferimento sotto lo stesso lock del reload e della LRU.
_reload_lock = threading.RLock()

# --- Function modules (after seams so they can `from api import deps`) --------
from api.auth import (  # noqa: E402
    _is_local_request as _is_local_request,
    _valid_api_key as _valid_api_key,
    require_api_key as require_api_key,
    require_api_key_strict as require_api_key_strict,
    require_gitlab_token as require_gitlab_token,
    require_local_bind as require_local_bind,
    require_not_cross_site_request as require_not_cross_site_request,
)
from api.index_runtime import (  # noqa: E402
    AskRuntime as AskRuntime,
    CpuGetRateLimiter,
    IndexSnapshot as IndexSnapshot,
    _ask_runtime_from_env as _ask_runtime_from_env,
    _build_snapshot as _build_snapshot,
    _close_unpublished_artifacts as _close_unpublished_artifacts,
    _graph_version as _graph_version,
    _load_index_snapshot as _load_index_snapshot,
    _prep_code_matrix as _prep_code_matrix,
    _prep_dev_type_index as _prep_dev_type_index,
    _publish_snapshot as _publish_snapshot,
    _reader_manifest as _reader_manifest,
    _reload_index_state_locked as _reload_index_state_locked,
    _reload_project_locked as _reload_project_locked,
    ask_runtime_for_app as ask_runtime_for_app,
    current_snapshot as current_snapshot,
    embed_in_threadpool as embed_in_threadpool,
    ensure_shared_resources as ensure_shared_resources,
    evict_project as evict_project,
    get_project as get_project,
    lifespan as lifespan,
    load_rule_descriptions as load_rule_descriptions,
    maybe_reload_graph as maybe_reload_graph,
    project_http_error as project_http_error,
    project_registry as project_registry,
    project_runtime as project_runtime,
    qdrant_collection_for_version as qdrant_collection_for_version,
    reload_index_state as reload_index_state,
    require_cpu_get_rate_limit as require_cpu_get_rate_limit,
    require_snapshot as require_snapshot,
    rule_descriptions_from_chunks as rule_descriptions_from_chunks,
    run_in_threadpool_until_complete as run_in_threadpool_until_complete,
    run_streaming as run_streaming,
)
from api.pages import (  # noqa: E402
    NO_CACHE_HEADERS as NO_CACHE_HEADERS,
    VALID_THEMES as VALID_THEMES,
    _inject_data_theme as _inject_data_theme,
    inject_agent_api_key as inject_agent_api_key,
    serve_page as serve_page,
    themed_template as themed_template,
)
from api.security_middleware import (  # noqa: E402
    CONTENT_SECURITY_POLICY as CONTENT_SECURITY_POLICY,
    CSP_EXEMPT_PATHS as CSP_EXEMPT_PATHS,
    SECURITY_HEADERS as SECURITY_HEADERS,
    HostHeaderGuard as HostHeaderGuard,
    SecurityHeadersMiddleware as SecurityHeadersMiddleware,
    host_from_header as host_from_header,
    with_security_headers as with_security_headers,
)


def _cpu_get_rate_limiter() -> CpuGetRateLimiter:
    try:
        return CpuGetRateLimiter(
            limit=CPU_GET_RATE_LIMIT, window_seconds=CPU_GET_RATE_WINDOW_SECONDS,
        )
    except ValueError as exc:
        raise RuntimeError(f"Configurazione rate-limit GET CPU non valida: {exc}") from exc


cpu_get_rate_limiter = _cpu_get_rate_limiter()

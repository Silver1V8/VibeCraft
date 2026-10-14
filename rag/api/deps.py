"""Dependency injection e stato condiviso dello strato HTTP: stato di runtime del server
(grafo, Qdrant, modello di embedding, sidecar), autenticazione, lifespan di caricamento
risorse, auto-reload dell'indice e helper di streaming/template. I router in api/ leggono
questo stato e lo iniettano nelle funzioni pure di core/."""
import asyncio
import hmac
import json
import logging
import math
import os
import queue
import re
import threading
from collections import OrderedDict
from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from html import escape as html_escape
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from qdrant_client import QdrantClient
from FlagEmbedding import BGEM3FlagModel

from core import retrieval
from core.artifacts import (IMMUTABLE_MARKER_FILENAME, LEGACY_VERSION,
                            artifact_hashes, current_version_token, load_artifacts,
                            manifest_path, _project_artifact_path)
from core.projects import ProjectContext, ProjectError, ProjectRegistry, resolve_registered_project
from core.config import (
    COLLECTION_NAME,
    DATABASE_DIR,
    EMBEDDING_MODEL,
    GRAPH_JSON_PATH,
    OLLAMA_TIMEOUT_SECONDS,
    PROJECT_ROOT,
    QDRANT_API_KEY,
    QDRANT_URL,
    ROLE,
    SERVER_BIND_IS_LOCAL,
    SERVER_HOST,
    TEMPLATES_DIR,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Autenticazione API — bypass su localhost, X-API-Key per il resto
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("VIBECRAFT_API_KEY")


def _valid_api_key(request: Request) -> bool:
    """True se l'header X-API-Key della richiesta corrisponde a VIBECRAFT_API_KEY (e la
    chiave è configurata). Condivisa da require_api_key (bypass su localhost) e
    require_api_key_strict (nessun bypass, per gli endpoint mutanti).

    Confronto a tempo costante (hmac.compare_digest, come require_gitlab_token): un `==`
    esce al primo carattere diverso e rende la chiave indovinabile per prefissi misurando
    i tempi di risposta. Entrambi i lati sono codificati in UTF-8 perché compare_digest
    rifiuta (TypeError) le str non ASCII: l'uguaglianza dei bytes UTF-8 equivale a quella
    delle str, quindi la semantica resta quella del vecchio `==`."""
    if not API_KEY:
        return False
    provided = request.headers.get("X-API-Key")
    if provided is None:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), API_KEY.encode("utf-8"))


def _is_local_request(request: Request) -> bool:
    """True se la richiesta arriva da 127.0.0.1/::1 (client_host lato server, non
    l'origin del chiamante). Condivisa da require_api_key (bypass) e dall'iniezione
    della chiave nella pagina /pipeline (_inject_agent_api_key)."""
    client_host = request.client.host if request.client else None
    return client_host in ("127.0.0.1", "::1")


def require_api_key(request: Request) -> None:
    """Lascia passare le richieste da localhost; per tutte le altre, richiede
    l'header X-API-Key (env VIBECRAFT_API_KEY). Se la chiave non è configurata,
    le richieste non locali vengono sempre rifiutate (fail-closed)."""
    if ROLE != "reader" and _is_local_request(request):
        return
    if not _valid_api_key(request):
        raise HTTPException(status_code=401, detail="API key richiesta per accesso non locale.")


def require_api_key_strict(request: Request) -> None:
    """Come require_api_key ma SENZA bypass per localhost: l'header X-API-Key è SEMPRE
    richiesto, anche da 127.0.0.1/::1. Oggi è usata da UN SOLO endpoint,
    POST /api/pipeline/agent/run (esecuzione shell/scrittura file via Claude Agent SDK):
    lì il bypass localhost basterebbe a una pagina aperta nel browser dell'utente per
    eseguire comandi via fetch() senza alcuna autenticazione. Gli ALTRI endpoint mutanti
    (explore/save, canvas/generate, propose/generate, archive, archive/stream, file/save,
    reindex, rollback) l'avevano in una patch precedente ma sono stati deliberatamente riportati
    a require_api_key (il frontend non invia X-API-Key: strict rompeva la UI nel setup
    keyless di default — vedi tests/test_security_fixes.py); il loro vettore cross-site
    è coperto da require_not_cross_site_request. Fail-closed se VIBECRAFT_API_KEY non è
    configurata: nessuna richiesta passa senza chiave, nemmeno da localhost. Va usata
    IN AGGIUNTA a require_api_key (dependency di router), non al suo posto — vedi
    require_gitlab_token per lo stesso schema di composizione."""
    if not _valid_api_key(request):
        raise HTTPException(
            status_code=401,
            detail="API key richiesta per questo endpoint, anche da localhost.",
        )


def require_local_bind(request: Request) -> None:
    """Spegne una route quando il server NON è bindato sul loopback (VIBECRAFT_HOST).

    È una disabilitazione, non un controllo d'accesso, e la differenza è il punto: le due
    route che la montano — POST /api/intake/project/browse-path e POST /api/intake/project/plan
    — hanno senso solo perché server e utente sono la stessa macchina. La prima apre un
    selettore di cartelle NATIVO sul desktop del processo server; la seconda scansiona un path
    assoluto arbitrario del filesystem del server e ne restituisce l'elenco file. Con un bind
    aperto (0.0.0.0, un IP di LAN) la prima diventa priva di senso *e* dannosa — il dialogo si
    apre sul desktop di chi ospita il server, non di chi clicca, e occupa un thread del pool
    finché qualcuno non lo chiude a mano — e la seconda diventa enumerazione remota del
    filesystem. Analisi in SECURITY_SURFACE.md §4 #7-#8, che chiedeva esattamente questo:
    disabilitare, non solo proteggere.

    Perché NON è bypassabile con la API key, a differenza di require_not_cross_site_request:
    lì la chiave identifica un client legittimo e il threat model è il browser di terzi; qui
    non c'è alcun chiamante per cui la funzione torni sensata, nemmeno il più autenticato di
    tutti. Un bypass sarebbe una riapertura, non un'eccezione. Per lo stesso motivo non esiste
    un flag di override: un interruttore "riabilitami" impostato una volta e dimenticato è
    esattamente il modo in cui questo rischio tornerebbe.

    Nessun effetto sul default (bind 127.0.0.1): la dependency passa e le route si comportano
    come sempre. Va usata IN AGGIUNTA a require_api_key, come le altre di questo modulo."""
    if SERVER_BIND_IS_LOCAL:
        return
    raise HTTPException(
        status_code=403,
        detail=(f"Endpoint disabilitato: ha senso solo con il server in ascolto su localhost, "
                f"mentre VIBECRAFT_HOST è '{SERVER_HOST}'. Vedi SECURITY_SURFACE.md §4 #7-#8."),
    )


def require_not_cross_site_request(request: Request) -> None:
    """Rifiuta con 403 le richieste browser cross-site sugli endpoint mutanti keyless.

    Modello di minaccia (analisi completa in SECURITY_SURFACE.md): il server non monta
    CORSMiddleware e require_api_key bypassa localhost, quindi nel setup keyless di
    default una pagina ostile aperta nel browser dell'utente può inviare POST cross-site
    "simple request" — in particolare a corpo assente verso gli endpoint che leggono il
    body con request.json() in try/except (/api/reindex, /api/index/rollback) — che
    arrivano agli handler autenticate come localhost. Il preflight CORS blocca già i
    body JSON cross-site, ma è una difesa implicita (un default di FastAPI), non un
    controllo: questa dependency rende il rifiuto esplicito. Sec-Fetch-Site è un
    forbidden header (Fetch Metadata): lo scrive il browser, il JS di una pagina non
    può impostarlo né falsificarlo.

    Semantica:
    - API key valida (X-API-Key == VIBECRAFT_API_KEY): passa SEMPRE — i client API
      autenticati non sono il threat model browser-based mitigato qui;
    - Sec-Fetch-Site esattamente "cross-site": 403;
    - header ASSENTE: passa — curl, script, webhook, browser legacy e UI aperte da
      file:// devono continuare a comportarsi come oggi;
    - "same-origin" / "same-site" / "none": passa (dashboard e navigazioni dirette).

    La protezione è volutamente PER-ROUTE (dependencies=[Depends(...)]), non un
    middleware globale: l'ambito è la matrice M7 (SECURITY_SURFACE.md §2) — i soli POST
    che mutano stato o spendono LLM; GET read-only e pagine HTML restano fuori, e
    l'endpoint già strict (agent/run) non viene toccato. Rischio residuo ACCETTATO:
    i browser legacy che non emettono Sec-Fetch-Site ricadono nel ramo "header assente"
    e non attivano la guardia (Fetch Metadata è su tutti gli evergreen dal ~2019)."""
    if _valid_api_key(request):
        return
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        raise HTTPException(
            status_code=403,
            detail="richiesta cross-site rifiutata su endpoint mutante",
        )


# ---------------------------------------------------------------------------
# Secret token del webhook GitLab — verifica IN AGGIUNTA a require_api_key
# ---------------------------------------------------------------------------
GITLAB_TOKEN = os.environ.get("VIBECRAFT_GITLAB_TOKEN")


def require_gitlab_token(request: Request) -> None:
    """Se VIBECRAFT_GITLAB_TOKEN è impostata, il webhook richiede l'header X-Gitlab-Token
    corrispondente (confronto a tempo costante con hmac.compare_digest). Se l'env non è
    impostata, non aggiunge alcun requisito (comportamento invariato). Va usata IN AGGIUNTA
    a require_api_key, non al suo posto."""
    if not GITLAB_TOKEN:
        return
    provided = request.headers.get("X-Gitlab-Token", "")
    # Bytes UTF-8, come in _valid_api_key: compare_digest su str non ASCII (header decodificato
    # latin-1 o token con accenti) solleva TypeError, cioè un 500 invece del 401.
    if not hmac.compare_digest(provided.encode("utf-8"), GITLAB_TOKEN.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Token webhook GitLab mancante o errato.")


# ---------------------------------------------------------------------------
# Validazione dell'header Host — difesa dal DNS rebinding
# ---------------------------------------------------------------------------
def host_from_header(value: str | None) -> str | None:
    """Hostname normalizzato di un header Host (minuscolo, senza porta, senza parentesi
    IPv6 né punto finale), o None se l'header manca o è malformato. `[::1]:8000` -> `::1`:
    lo split ingenuo sui due punti (quello di starlette TrustedHostMiddleware) darebbe `[`
    e rifiuterebbe il loopback IPv6. Un IPv6 senza parentesi è ambiguo con la porta, quindi
    malformato; lo è anche una porta presente ma vuota o non numerica, e un nome con
    etichette vuote (`..`)."""
    if not value:
        return None
    value = value.strip().lower()
    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            return None
        host, rest = value[1:end], value[end + 1:]
        if rest and not rest.startswith(":"):
            return None
        port = rest[1:] if rest else None
    else:
        if value.count(":") > 1:
            return None
        host, sep, port = value.partition(":")
        port = port if sep else None
    if port is not None and not (port.isascii() and port.isdigit()):
        return None
    if ".." in host:
        return None
    host = host.rstrip(".")
    return host or None


class HostHeaderGuard:
    """Middleware ASGI: 400 per ogni richiesta HTTP/WebSocket il cui header Host non è in
    `allowed_hosts` (core.config.ALLOWED_HOSTS: loopback + bind specifico + host di
    VIBECRAFT_BASE_URL + VIBECRAFT_ALLOWED_HOSTS).

    Perché serve: _is_local_request guarda l'IP del client, non il nome con cui il browser
    crede di parlare al server. Con il DNS rebinding una pagina ostile su attacker.example
    fa risolvere il PROPRIO nome a 127.0.0.1 dopo il caricamento: le sue fetch() verso
    attacker.example:8000 arrivano qui da 127.0.0.1, sono same-origin per il browser
    (quindi può LEGGERE le risposte) e passano il bypass loopback di require_api_key — e
    GET /pipeline le consegnerebbe persino la chiave iniettata (inject_agent_api_key).
    L'unica traccia dell'attacco che il server vede è l'header Host, che il browser scrive
    con il nome dell'origine e il JS non può falsificare (forbidden header): è quello che
    si controlla qui, prima di qualunque route, statici compresi.

    Equivalente minimo di starlette TrustedHostMiddleware, riscritto per il parsing IPv6
    (vedi host_from_header); niente wildcard né redirect www."""

    _MAX_WARNED = 64

    def __init__(self, app, allowed_hosts):
        self.app = app
        self.allowed_hosts = frozenset(allowed_hosts)
        self._warned: set[str] = set()

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        raw = None
        for name, value in scope.get("headers") or ():
            if name == b"host":
                raw = value.decode("latin-1")
                break
        if host_from_header(raw) in self.allowed_hosts:
            await self.app(scope, receive, send)
            return
        # Un WARNING per host distinto (per diagnosticare un nome legittimo mancante), poi
        # DEBUG: una pagina ostile in loop non deve poter inondare il log. L'insieme dei nomi
        # già segnalati è limitato, così nemmeno Host sempre diversi fanno crescere la memoria.
        shown = (raw or "")[:100]
        if shown not in self._warned and len(self._warned) < self._MAX_WARNED:
            self._warned.add(shown)
            log = logger.warning
        else:
            log = logger.debug
        log("Richiesta rifiutata: header Host non consentito %r "
            "(aggiungilo a VIBECRAFT_ALLOWED_HOSTS se è legittimo).", shown)
        response = PlainTextResponse("Invalid host header", status_code=400)
        await response(scope, receive, send)


# ---------------------------------------------------------------------------
# Header di sicurezza su ogni risposta — difesa dal clickjacking
# ---------------------------------------------------------------------------
# Anti-framing, igiene e Content-Security-Policy. Nomi minuscoli: è la forma in cui
# Starlette scrive gli header ASGI.
SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"same-origin"),
)
_CSP = b"content-security-policy"
_FRAME_ANCESTORS = b"frame-ancestors 'none'"

# CSP della console. Il punto è `script-src 'self'` SENZA 'unsafe-inline' né 'unsafe-eval':
# un frammento HTML che sfuggisse all'escape (dato del corpus, titolo di un documento in
# staging) non può eseguire nulla — né <script> iniettati né handler `onerror=`/`onclick=`.
# Per questo i template non hanno script né handler inline: il codice sta in
# /static/pages/*.js e le azioni passano da `data-click`/`data-change`/`data-input`
# (registerActions in /static/shared.js); la chiave di /pipeline arriva in un <meta>.
# Residuo accettato: `style-src 'unsafe-inline'`. Tailwind ora è precompilato
# (/static/tailwind*.css, scripts/build_css.sh, 2026-10-14), ma mermaid e
# vis/3d-force-graph scrivono stili inline e i template usano `style="..."`: togliere
# 'unsafe-inline' richiede di eliminare quelli. Il rischio residuo è l'iniezione di CSS
# (defacement, esfiltrazione lenta via selettori), non l'esecuzione di codice.
# `img-src data: blob:` per le icone SVG inline e gli export dei canvas; `worker-src blob:`
# per i worker che le librerie grafiche possono creare. Tutto il resto solo same-origin:
# la console è local-first, nessuna CDN (vedi i vendor in /static/vendor/).
CONTENT_SECURITY_POLICY = (
    b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    b"img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
    b"worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'; "
    + _FRAME_ANCESTORS
)
# Swagger UI / ReDoc di FastAPI caricano JS e CSS da cdn.jsdelivr.net e hanno uno script
# inline: con la CSP completa sarebbero pagine bianche. Ricevono solo l'anti-framing.
CSP_EXEMPT_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc"})


def with_security_headers(headers, csp: bytes = CONTENT_SECURITY_POLICY) -> list[tuple[bytes, bytes]]:
    """Header ASGI di una risposta con gli header di SECURITY_HEADERS e la CSP `csp`
    aggiunti. Mai sovrascrive ciò che la route ha già deciso: un header già presente
    (confronto case-insensitive sul nome) resta com'è; una CSP già presente riceve
    `frame-ancestors 'none'` in coda solo se non ne dichiara una propria."""
    out = list(headers or ())
    present = {name.lower() for name, _ in out}
    for name, value in SECURITY_HEADERS:
        if name not in present:
            out.append((name, value))
    csp_idx = [i for i, (name, _) in enumerate(out) if name.lower() == _CSP]
    if not csp_idx:
        out.append((_CSP, csp))
    elif not any(b"frame-ancestors" in out[i][1].lower() for i in csp_idx):
        name, value = out[csp_idx[0]]
        value = value.rstrip().rstrip(b";").rstrip()
        out[csp_idx[0]] = (name, (value + b"; " if value else b"") + _FRAME_ANCESTORS)
    return out


class SecurityHeadersMiddleware:
    """Middleware ASGI: aggiunge a OGNI risposta HTTP `X-Frame-Options: DENY`,
    `Content-Security-Policy` (CONTENT_SECURITY_POLICY; solo `frame-ancestors 'none'` per
    CSP_EXEMPT_PATHS), `X-Content-Type-Options: nosniff` e `Referrer-Policy: same-origin`
    (vedi with_security_headers per la regola di fusione).

    Perché serve: le pagine della console hanno pulsanti che scrivono (pipeline, intake,
    reindex, rollback) e nessuna risposta vietava di essere incorniciata. Una pagina ostile
    poteva caricare http://127.0.0.1:8000/pipeline in un <iframe> trasparente e far
    cliccare all'utente i pulsanti veri (clickjacking): le fetch partono DALLA pagina
    incorniciata, quindi sono same-origin — `require_not_cross_site_request` le lascia
    passare e il bypass loopback le autentica. `frame-ancestors` è lo standard, XFO copre i
    browser che non lo applicano.

    Su tutte le risposte, non solo sulle HTML: gli header sono innocui su JSON/statici/NDJSON,
    e un filtro sul content-type lascerebbe fuori proprio i casi imprevisti (/docs, un errore
    HTML di libreria, una pagina nuova servita come file). `nosniff` è sicuro perché ogni
    script/foglio della console arriva con il MIME giusto (server.py registra i tipi degli
    statici senza dipendere dal registro di Windows). `same-origin` non tocca le richieste
    della console (il Referer same-origin resta) e non lo usa nessun controllo lato server.

    Gli header si aggiungono sul messaggio `http.response.start`, prima del body: le
    risposte in streaming (/ask NDJSON, stream della pipeline) passano senza buffering.
    Per questo è ASGI puro come HostHeaderGuard e non BaseHTTPMiddleware. Montato come
    middleware più esterno fra i nostri, copre anche il 400 di HostHeaderGuard; i 500 non
    gestiti li genera ServerErrorMiddleware di Starlette, che sta ancora fuori."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        csp = _FRAME_ANCESTORS if scope.get("path") in CSP_EXEMPT_PATHS else CONTENT_SECURITY_POLICY

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": with_security_headers(message.get("headers"), csp)}
            await send(message)

        await self.app(scope, receive, send_with_headers)


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
    colbert_store: Mapping
    chunks: dict
    rule_descriptions: dict
    # Sidecar dei simboli di codice (symbol_id -> {name, kind, file, dev_type, text, ...}):
    # serve a /ask per iniettare, via archi IMPLEMENTS, il codice che implementa le sezioni
    # recuperate. Fa parte dello snapshot perché cambia insieme al grafo a ogni reindex.
    code_store: dict
    # Versione dell'indice al momento della build dello snapshot: il nome della versione
    # blue/green puntata da database/CURRENT (str), oppure — layout legacy senza
    # CURRENT — l'mtime del file-grafo flat (float).
    version: str | float | None
    # Matrice densa del codice PRECALCOLATA una volta per snapshot (non più per richiesta):
    # `code_ids` sono gli id dei simboli con vettore denso, `code_matrix` è la matrice float32
    # GIÀ normalizzata L2 (stessa formula di core.retrieval.search_code_symbols), allineata per
    # indice a `code_ids`. La normalizzazione L2 dei simboli è identica a ogni richiesta /ask,
    # quindi calcolarla al reload invece che a ogni ricerca è puro risparmio di CPU. `code_matrix`
    # è None (e `code_ids` []) se il code_store è vuoto o nessun simbolo ha un vettore denso.
    code_ids: list[str]
    code_matrix: "np.ndarray | None"
    # Indice per AMBITO dei simboli: dev_type -> array degli indici di riga in `code_ids`
    # (e quindi in `code_matrix`). Precalcolato una volta per snapshot come la matrice, per la
    # stessa ragione: il raggruppamento è identico a ogni richiesta. Lo usa /api/code/search per
    # restringere la ricerca a un ambito PRIMA dei top-k, senza copiare una sottomatrice.
    # Default {} così uno snapshot costruito senza (test, chiamanti storici) resta valido.
    code_dev_type_idx: dict = field(default_factory=dict)
    # Sezioni che RIFORMULANO invece di stabilire (N4): riepiloghi, checklist, scenari BDD —
    # citano codici di regola senza dichiararne nessuno in un titolo. Derivata dal TESTO dei
    # chunk (core.retrieval.restatement_sections), quindi non richiede una re-indicizzazione e
    # vale anche sugli indici gia' su disco. Precalcolata qui per la stessa ragione della
    # matrice del codice: e' identica a ogni richiesta. Default vuoto = peso di sezione
    # disattivato, che e' il comportamento dei chiamanti storici (test, snapshot costruiti a mano).
    restatements: frozenset = frozenset()
    # Collection fisica coerente con gli artefatti; None sui layout/test legacy.
    collection_name: str | None = None
    # Manifest letto mentre la lease della stessa versione era detenuta.
    index_manifest: dict = field(default_factory=dict)
    # Lease condivisa: resta viva quanto lo snapshot, incluse richieste già in volo al reload.
    version_lease: object | None = None


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
    "reload_error": None,
    "lock": threading.RLock(),
}


# ---------------------------------------------------------------------------
# Semaforo di concorrenza sull'embedding CPU: state["embed_model"] è un'unica
# istanza CPU condivisa, senza limite più richieste in parallelo mandano la coda
# torch in thrash e il p99 esplode. Bound configurabile, default 2.
# ---------------------------------------------------------------------------
EMBED_CONCURRENCY = int(os.environ.get("VIBECRAFT_EMBED_CONCURRENCY", "2"))
embed_semaphore = asyncio.Semaphore(EMBED_CONCURRENCY)


class AskRuntime:
    """Limiti per-processo legati alla singola app FastAPI."""

    def __init__(self, *, max_active: int, llm_concurrency: int,
                 llm_queue_timeout: float, total_timeout: float):
        values = {
            "max_active": max_active,
            "llm_concurrency": llm_concurrency,
            "llm_queue_timeout": llm_queue_timeout,
            "total_timeout": total_timeout,
        }
        for name, value in values.items():
            if value <= 0 or not math.isfinite(value):
                raise ValueError(f"{name} deve essere positivo")
        self.max_active = max_active
        self.llm_queue_timeout = llm_queue_timeout
        self.total_timeout = total_timeout
        self.active = 0
        self.llm = asyncio.Semaphore(llm_concurrency)

    def try_admit(self) -> bool:
        # Tutti i chiamanti vivono sull'event loop dell'app: nessun await fra check e incremento.
        if self.active >= self.max_active:
            return False
        self.active += 1
        return True

    def release(self) -> None:
        if self.active > 0:
            self.active -= 1

    async def acquire_llm(self) -> None:
        await asyncio.wait_for(self.llm.acquire(), timeout=self.llm_queue_timeout)

    def release_llm(self) -> None:
        self.llm.release()


def _ask_runtime_from_env() -> AskRuntime:
    try:
        return AskRuntime(
            max_active=int(os.environ.get("VIBECRAFT_ASK_MAX_ACTIVE", "8")),
            llm_concurrency=int(os.environ.get("VIBECRAFT_LLM_CONCURRENCY", "2")),
            llm_queue_timeout=float(os.environ.get("VIBECRAFT_LLM_QUEUE_TIMEOUT_SECONDS", "30")),
            total_timeout=float(os.environ.get(
                "VIBECRAFT_ASK_TIMEOUT_SECONDS", str(OLLAMA_TIMEOUT_SECONDS + 60))),
        )
    except ValueError as exc:
        raise RuntimeError(f"Configurazione limiti /ask non valida: {exc}") from exc


def ask_runtime_for_app(application: FastAPI) -> AskRuntime:
    runtime = getattr(application.state, "ask_runtime", None)
    if runtime is None:
        runtime = _ask_runtime_from_env()
        application.state.ask_runtime = runtime
    return runtime


async def embed_in_threadpool(fn, *a, **k):
    async with embed_semaphore:
        return await run_in_threadpool_until_complete(fn, *a, **k)


async def run_in_threadpool_until_complete(fn, *a, **k):
    """Su cancel attende il worker reale prima di restituire lo slot al chiamante."""
    worker = asyncio.create_task(run_in_threadpool(fn, *a, **k))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                # Una seconda cancel non deve rendere nuovamente abbandonabile il thread.
                continue
            except BaseException:
                # L'esito tardivo viene consumato sotto; il chiamante resta cancellato.
                break
        try:
            worker.result()
        except BaseException:
            # La cancellazione della richiesta ha precedenza sull'esito tardivo del worker.
            pass
        raise


def current_snapshot(project: ProjectContext | None = None) -> IndexSnapshot | None:
    """Riferimento atomico allo snapshot corrente dell'indice. Ogni handler lo chiama
    UNA volta a inizio richiesta e usa solo l'oggetto restituito: essendo frozen e
    rebindato (mai mutato), il contenuto resta internamente coerente anche se un reload
    avviene a metà richiesta (il reload rebinda `state["snapshot"]`, non tocca l'oggetto
    già in mano all'handler)."""
    if project is None or project.legacy:
        return state.get("snapshot")
    with _reload_lock:
        snapshot = _snapshots.get(project.id)
        if snapshot is not None:
            _snapshots.move_to_end(project.id)
        return snapshot


# ---------------------------------------------------------------------------
# Cache {version: qdrant_collection} per il log strutturato di fine richiesta di
# /ask (M3 observability). Il manifest di una versione è immutabile una volta
# scritto (write_index_manifest gira una sola volta per build), quindi leggerlo
# più di una volta per versione sarebbe I/O sprecato: qui lo leggiamo dal disco
# UNA volta e serviamo tutte le richieste successive sulla stessa versione dalla
# cache in-process. Nessuna invalidazione: una versione nuova è semplicemente
# una nuova chiave.
# ---------------------------------------------------------------------------
_qdrant_collection_by_version: dict = {}


def qdrant_collection_for_version(version: str | float | None,
                                  project: ProjectContext | None = None) -> str:
    """Nome della collection Qdrant dichiarata dal manifest di `version` (campo
    "qdrant_collection", scritto da core.indexing.write_index_manifest), con cache
    a livello di modulo per versione. Fallback "unknown" se il manifest è assente,
    illeggibile, non porta il campo, o se `version` non è un nome di versione valido
    (es. mtime float del layout legacy senza CURRENT)."""
    key = (project.id if project else "legacy", version)
    if key in _qdrant_collection_by_version:
        return _qdrant_collection_by_version[key]
    try:
        manifest = json.loads(manifest_path(version, project=project).read_text(encoding="utf-8"))
        name = manifest.get("qdrant_collection") if isinstance(manifest, dict) else None
    except Exception:
        name = None
    name = name or "unknown"
    _qdrant_collection_by_version[key] = name
    return name


def _graph_version(project: ProjectContext | None = None) -> str | float | None:
    """Versione osservabile dell'indice su disco: il contenuto di database/CURRENT
    (nome della versione blue/green attiva — cambia a ogni promote E a ogni rollback),
    con fallback all'mtime del file-grafo flat (graph.json) per i layout senza CURRENT.
    È la baseline che innesca l'auto-reload."""
    token = current_version_token(project=project)
    if token is not None:
        return token
    if project is not None and not project.legacy:
        return None
    path = _project_artifact_path(project.database_dir / "graph.json", project) if project else GRAPH_JSON_PATH
    try:
        return path.stat().st_mtime
    except OSError:
        pass
    return None


def _prep_code_matrix(code_store: dict) -> tuple[list[str], "np.ndarray | None"]:
    """Precalcola, una volta per snapshot, la matrice densa L2-normalizzata dei simboli di
    codice del `code_store` — lo stesso lavoro che core.retrieval.search_code_symbols faceva a
    OGNI richiesta /ask. Prende gli id dei simboli con `dense` non None, costruisce la matrice in
    float32 e la normalizza con `norm + 1e-8` (formula IDENTICA a quella del retrieval, così il
    risultato numerico non cambia). Ritorna `(code_ids, matrix)` allineati per indice, oppure
    `([], None)` se il code_store è vuoto o nessun simbolo ha un vettore denso."""
    if not code_store:
        return [], None
    sym_ids = [sid for sid, e in code_store.items() if e.get("dense") is not None]
    if not sym_ids:
        return [], None
    matrix = np.asarray([code_store[sid]["dense"] for sid in sym_ids], dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8
    return sym_ids, matrix


def _prep_dev_type_index(code_ids: list[str], code_store: dict) -> dict[str, "np.ndarray"]:
    """Raggruppa gli indici di riga di `code_ids` per dev_type (l'ambito dichiarato dal simbolo,
    cioè la prima cartella sotto code/). Precalcolato una volta per snapshot: il raggruppamento
    non dipende dalla query, rifarlo a ogni richiesta sarebbe lavoro identico ripetuto.

    I simboli senza dev_type (file alla radice di code/) non finiscono in nessun gruppo: un
    filtro per ambito non deve mai restituirli, e senza ambito non c'è filtro."""
    groups: dict[str, list[int]] = {}
    for i, sid in enumerate(code_ids):
        dev_type = str((code_store.get(sid) or {}).get("dev_type") or "")
        if dev_type:
            groups.setdefault(dev_type, []).append(i)
    return {dt: np.asarray(idx, dtype=np.int64) for dt, idx in groups.items()}


def _build_snapshot(graph, colbert_store, chunks, rule_descriptions, code_store,
                    *, version=None, collection_name=None, index_manifest=None,
                    version_lease=None, project: ProjectContext | None = None) -> IndexSnapshot:
    """Assembla un IndexSnapshot con la versione degli artefatti già caricati e
    precalcolando la matrice densa del codice e l'indice per ambito (una volta per reindex,
    non per richiesta)."""
    # Il loader ha già catturato CURRENT prima di leggere gli artefatti.
    # Rileggerlo qui attribuirebbe una promozione concorrente ai dati precedenti.
    if version == "legacy":
        path = _project_artifact_path(project.database_dir / "graph.json", project) if project else GRAPH_JSON_PATH
        version = path.stat().st_mtime
    elif version is None:
        version = _graph_version(project=project)
    code_ids, code_matrix = _prep_code_matrix(code_store)
    resolved_collection = collection_name or qdrant_collection_for_version(version, project=project)
    return IndexSnapshot(
        graph=graph,
        colbert_store=colbert_store,
        chunks=chunks,
        rule_descriptions=rule_descriptions,
        code_store=code_store,
        version=version,
        code_ids=code_ids,
        code_matrix=code_matrix,
        code_dev_type_idx=_prep_dev_type_index(code_ids, code_store),
        restatements=retrieval.restatement_sections(chunks, project=project),
        collection_name=None if resolved_collection == "unknown" else resolved_collection,
        index_manifest=index_manifest or {},
        version_lease=version_lease,
    )


def load_rule_descriptions(project: ProjectContext | None = None) -> dict[str, str]:
    """
    Scansiona tutti i file spec_*.md in docs/ (ricorsivamente) ed estrae le descrizioni
    di regole e termini di glossario nel formato `[CHIAVE]`: <testo>.
    Restituisce un dizionario { "REGOLA-AUTH-01": "...", "UTENTE": "...", ... }.
    """
    descriptions: dict[str, str] = {}
    pattern = re.compile(r"`\[([A-Z0-9][A-Z0-9_\- ]*)]`:\s*(.+)")
    docs_dir = project.docs_dir if project else PROJECT_ROOT / "docs"
    # Scansiona tutti i .md: le descrizioni possono vivere in qualsiasi documento
    # del knowledge base, non solo nei file spec_*.md.
    from code_index import source_files
    from core.projects import _unlinked
    for spec_file in source_files(docs_dir):
        if spec_file.suffix.lower() != ".md":
            continue
        try:
            content = _unlinked(spec_file).read_text(encoding="utf-8")
            for m in pattern.finditer(content):
                key = m.group(1).strip()
                descriptions[key] = m.group(2).strip()
        except Exception as exc:
            logger.warning("Impossibile leggere %s: %s", spec_file, exc)
    logger.info("Entità indicizzate (%d): %s", len(descriptions), sorted(descriptions.keys()))
    return descriptions


_RULE_DESCRIPTION_RE = re.compile(r"`\[([A-Z0-9][A-Z0-9_\- ]*)]`:\s*(.+)")


def rule_descriptions_from_chunks(chunks: Mapping) -> dict[str, str]:
    """Deriva le descrizioni dal bundle versionato, senza leggere i documenti live."""
    descriptions: dict[str, str] = {}
    for chunk_id in sorted(chunks):
        text = str((chunks.get(chunk_id) or {}).get("text") or "")
        for match in _RULE_DESCRIPTION_RE.finditer(text):
            descriptions[match.group(1).strip()] = match.group(2).strip()
    return descriptions


def _reader_manifest(version, project: ProjectContext | None = None) -> dict:
    database_dir = project.database_dir if project else DATABASE_DIR
    if not _project_artifact_path(database_dir / IMMUTABLE_MARKER_FILENAME, project).is_file():
        raise RuntimeError(
            f"Reader rifiutato: marker {IMMUTABLE_MARKER_FILENAME} assente in {DATABASE_DIR}."
        )
    if not isinstance(version, str) or not version or version == LEGACY_VERSION:
        raise RuntimeError("Reader rifiutato: serve una versione immutabile non legacy.")
    try:
        manifest = json.loads(manifest_path(version, project=project).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Reader rifiutato: manifest della versione '{version}' assente o illeggibile."
        ) from exc
    expected = f"{project.collection_name if project else COLLECTION_NAME}__{version}"
    if not isinstance(manifest, dict):
        raise RuntimeError(f"Reader rifiutato: manifest della versione '{version}' non valido.")
    if manifest.get("immutable") is not True or manifest.get("qdrant_collection") != expected:
        raise RuntimeError(
            f"Reader rifiutato: la versione '{version}' non dichiara la collection "
            f"fisica immutabile '{expected}'."
        )
    expected_hashes = manifest.get("artifact_hashes")
    if not isinstance(expected_hashes, dict) or artifact_hashes(version, project=project) != expected_hashes:
        raise RuntimeError(
            f"Reader rifiutato: hash degli artefatti della versione '{version}' non coerenti."
        )
    return manifest


def _close_unpublished_artifacts(arts) -> None:
    lease = getattr(arts, "version_lease", None)
    if lease is not None:
        lease.close()
    store = getattr(arts, "colbert_store", None)
    close = getattr(store, "close", None)
    if close is not None:
        close()


def _load_index_snapshot(*, boot: bool = False, project: ProjectContext | None = None) -> IndexSnapshot:
    required = (("graph", "colbert", "chunks")
                if ROLE == "reader" or (project is not None and not project.legacy) or not boot
                else ("graph",))
    arts = load_artifacts(required=required, retain_lease=True, project=project)
    try:
        if ROLE == "reader" or (project is not None and not project.legacy):
            manifest = _reader_manifest(arts.version, project=project)
            if set(arts.colbert_store) != set(arts.chunks_store):
                raise RuntimeError(
                    "Reader rifiutato: chiavi ColBERT e chunks dello snapshot non coincidono."
                )
            if any(not isinstance(entry, dict) or not isinstance(entry.get("text"), str)
                   for entry in arts.chunks_store.values()):
                raise RuntimeError(
                    "Reader rifiutato: ogni chunk deve contenere testo versionato completo."
                )
            descriptions = rule_descriptions_from_chunks(arts.chunks_store)
            collection_name = manifest["qdrant_collection"]
        else:
            descriptions = load_rule_descriptions(project=project) if project else load_rule_descriptions()
            collection_name = None
            try:
                manifest = json.loads(manifest_path(arts.version, project=project).read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                manifest = {}
        return _build_snapshot(
            arts.graph, arts.colbert_store, arts.chunks_store, descriptions,
            arts.code_store, version=arts.version, collection_name=collection_name,
            index_manifest=manifest, version_lease=getattr(arts, "version_lease", None), project=project,
        )
    except BaseException:
        _close_unpublished_artifacts(arts)
        raise


_registry = None
_registry_lock = threading.Lock()
_resources_lock = threading.Lock()
_project_states: dict[str, dict] = {}
_snapshots: OrderedDict[str, IndexSnapshot] = OrderedDict()


def project_registry() -> ProjectRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = ProjectRegistry()
        return _registry


def project_http_error(exc: ProjectError) -> HTTPException:
    logger.warning("Project operation failed (%s): %s", exc.code, exc)
    return HTTPException(status_code=exc.status_code,
                         detail={"code": exc.code, "message": exc.code.replace("_", " ")})


def get_project(request: Request) -> ProjectContext:
    """Capture once per request; missing header means only registered legacy."""
    captured = getattr(request.state, "project", None)
    if captured is not None:
        return captured
    project_id = request.headers.get("X-VibeCraft-Project")
    try:
        project = resolve_registered_project(project_id, registry=project_registry())
    except ProjectError as exc:
        raise project_http_error(exc) from exc
    request.state.project = project
    return project


def project_runtime(project: ProjectContext | None = None) -> dict:
    if project is None or project.legacy:
        return state
    with _reload_lock:
        return _project_states.setdefault(project.id, {"reload_error": None, "lock": threading.RLock()})


def ensure_shared_resources(*, embedding: bool = True) -> None:
    """One shared client/model, initialized only when an indexed request needs them."""
    with _resources_lock:
        try:
            if state.get("qdrant") is None:
                state["qdrant"] = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
            if embedding and state.get("embed_model") is None:
                state["embed_model"] = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False, devices="cpu")
        except Exception as exc:
            logger.exception("Shared resources unavailable")
            raise HTTPException(503, detail={"code": "resources_unavailable",
                                            "message": "Shared resources unavailable"}) from exc


def _publish_snapshot(project: ProjectContext | None, snapshot: IndexSnapshot) -> None:
    project_id = project.id if project else "legacy"
    _snapshots[project_id] = snapshot
    _snapshots.move_to_end(project_id)
    if project is None or project.legacy:
        state["snapshot"] = snapshot
    while len(_snapshots) > 2:
        evicted, _ = _snapshots.popitem(last=False)
        if evicted == "legacy":
            state["snapshot"] = None
    # Eviction drops references only: in-flight requests still own their version lease.


def require_snapshot(project: ProjectContext) -> IndexSnapshot:
    # ponytail: serialize disk loads; per-project locks if load contention becomes material.
    with _reload_lock:
        maybe_reload_graph(project)
        runtime = project_runtime(project)
        if runtime.get("reload_error"):
            raise HTTPException(503, detail={"code": "project_storage_error",
                                            "message": "Project index unavailable"})
        snapshot = current_snapshot(project)
        if snapshot is None:
            raise HTTPException(409, detail={"code": "project_not_indexed",
                                            "message": "Project has no index"})
        _publish_snapshot(project, snapshot)
        return snapshot


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Shell and registry remain available with no index or unavailable resources."""
    if ROLE == "reader" and not API_KEY:
        raise RuntimeError("VIBECRAFT_ROLE=reader richiede VIBECRAFT_API_KEY")
    ask_runtime_for_app(application)
    try:
        project_registry()
    except ProjectError as exc:
        # Keep shell/diagnostic metadata available when migration or storage repair is needed.
        logger.warning("Project registry not ready: %s", exc.code)
    try:
        yield
    finally:
        with _reload_lock:
            _snapshots.clear()
            _project_states.clear()
            state["snapshot"] = None
        if state.get("qdrant") is not None:
            state["qdrant"].close()
            state["qdrant"] = None
        state["embed_model"] = None


# ---------------------------------------------------------------------------
# Auto-reload dell'indice in memoria (dopo una re-indicizzazione da CLI o pipeline)
# ---------------------------------------------------------------------------
# Serializza i reload (auto-reload dalle richieste, on_success del thread di reindex,
# rollback, intake): due caricamenti paralleli raddoppierebbero memoria e I/O, e l'ultimo a
# pubblicare vincerebbe anche se più vecchio. RLock: require_snapshot cattura il riferimento
# sotto lo stesso lock del reload e della LRU; le lease su disco restano non bloccanti.
_reload_lock = threading.RLock()


def reload_index_state(project: ProjectContext | None = None) -> str | float | None:
    """Ricarica in memoria grafo, multivettori ColBERT e sidecar chunk dai file appena
    rigenerati dalla re-indicizzazione, così che il server rifletta subito la nuova base
    di conoscenza senza riavvio.

    Il reload è COERENTE (tutto-o-niente): gli artefatti vengono prima caricati in
    variabili locali; solo se grafo + ColBERT + chunk sono tutti presenti e integri lo
    stato viene sostituito. Se anche uno solo è mancante o corrotto (es. una re-
    indicizzazione ancora in corso o abortita), si logga un warning e si MANTIENE la
    versione precedente in memoria, evitando di degradare il server (grafo senza
    ColBERT/chunk).

    Bloccante (I/O e deserializzazione pesanti): dagli handler async va chiamata via
    run_in_threadpool. Ricarica SEMPRE (i chiamanti espliciti — fine job, rollback,
    intake — possono aver cambiato i documenti senza cambiare versione), ma serializzata
    con gli altri reload tramite _reload_lock."""
    with _reload_lock:
        return _reload_project_locked(project) if project is not None else _reload_index_state_locked()


def _reload_index_state_locked() -> str | float | None:
    """Corpo di reload_index_state: il chiamante DEVE detenere _reload_lock."""
    try:
        snapshot = _load_index_snapshot()
    except Exception as exc:
        state["reload_error"] = f"{type(exc).__name__}: {exc}"
        logger.warning("Reload indice annullato (%s: %s): artefatto mancante o corrotto, "
                       "mantengo in memoria la versione precedente.", type(exc).__name__, exc)
        # Aggiorna comunque il baseline mtime: se il file è corrotto in modo persistente,
        # evita di ritentare (e ri-loggare) il reload a ogni richiesta successiva. Una
        # nuova build completa cambierà di nuovo l'mtime e ritenterà il reload.
        state["_graph_mtime"] = _graph_version()
        return None

    # Rebind ATOMICO: un solo IndexSnapshot completo sostituisce quello precedente.
    # Nessuna mutazione in place → nessun handler può osservare una versione mista.
    _publish_snapshot(None, snapshot)
    state["_graph_mtime"] = state["snapshot"].version
    state["reload_error"] = None
    return state["snapshot"].version


def _reload_project_locked(project: ProjectContext) -> str | float | None:
    runtime = project_runtime(project)
    try:
        version = _graph_version(project)
        if version is None:
            _snapshots.pop(project.id, None)
            if project.legacy:
                state["snapshot"] = None
            runtime.update(reload_error=None, _graph_mtime=None)
            return None
        snapshot = _load_index_snapshot(project=project, boot=current_snapshot(project) is None)
    except Exception as exc:
        logger.exception("Project %s reload failed", project.id)
        runtime["reload_error"] = type(exc).__name__
        return None
    _publish_snapshot(project, snapshot)
    runtime.update(reload_error=None, _graph_mtime=snapshot.version)
    return snapshot.version


def maybe_reload_graph(project: ProjectContext | None = None) -> None:
    """Auto-reload: se la versione dell'indice su disco è cambiata (database/CURRENT
    spostato da una promozione o da un rollback; per i layout legacy, mtime del grafo
    flat), ricarica l'indice in memoria alla prima richiesta successiva, senza dover
    riavviare il server.

    Bloccante: gli handler async la chiamano con `await run_in_threadpool(...)`, così un
    caricamento lungo non ferma l'event loop (health, streaming e le altre route continuano
    a rispondere). Doppio controllo: il confronto senza lock è il percorso veloce di ogni
    richiesta; chi deve ricaricare prende _reload_lock e RICONTROLLA la baseline, perché
    nel frattempo un'altra richiesta (o il thread di reindex) può aver già caricato la
    stessa versione — in quel caso non la si ricarica una seconda volta."""
    if project is not None:
        with _reload_lock:
            runtime = project_runtime(project)
            try:
                version = _graph_version(project)
            except Exception as exc:
                runtime["reload_error"] = type(exc).__name__
                return
            if (current_snapshot(project) is None or version != runtime.get("_graph_mtime")
                    or runtime.get("reload_error")):
                _reload_project_locked(project)
        return
    if current_snapshot() is None:
        return
    mtime = _graph_version()
    if mtime is None:
        return
    prev = state.get("_graph_mtime")
    if prev is None:
        state["_graph_mtime"] = mtime
        return
    if mtime == prev:
        return
    with _reload_lock:
        mtime = _graph_version()
        if mtime is None or mtime == state.get("_graph_mtime"):
            return
        logger.info("Grafo cambiato su disco: ricarico grafo/ColBERT/regole in memoria.")
        _reload_index_state_locked()


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
    """Serve la shell persistente, oppure il documento richiesto con workspace=1.
    Se `unified_name` esiste sotto TEMPLATES_DIR (versione dedupata,
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

    # La shell resta viva durante la navigazione; le pagine sono documenti separati
    # caricati via fetch, così nessuno stream viene chiuso al cambio di sezione.
    workspace_path = TEMPLATES_DIR / "workspace.html"
    if request.query_params.get("workspace") != "1" and workspace_path.exists():
        return HTMLResponse(_inject_data_theme(workspace_path.read_text(encoding="utf-8"), theme),
                            headers=NO_CACHE_HEADERS)

    unified_path = TEMPLATES_DIR / unified_name
    if unified_path.exists():
        html = unified_path.read_text(encoding="utf-8")
        html = _inject_data_theme(html, theme)
        return HTMLResponse(html, headers=NO_CACHE_HEADERS)

    # Fallback: pagina non ancora unificata -> vecchia coppia di file per tema (invariata).
    legacy_path = themed_template(request, matrix_name, classic_name)
    return FileResponse(legacy_path, media_type="text/html", headers=NO_CACHE_HEADERS)


# Subito dopo <head>: il <meta> deve precedere /static/shared.js, che lo legge al caricamento.
_HEAD_OPEN_RE = re.compile(r"<head\b[^>]*>", re.IGNORECASE)


def inject_agent_api_key(html: str, request: Request) -> str:
    """Inietta la X-API-Key richiesta da /api/pipeline/agent/run (require_api_key_strict,
    l'UNICO endpoint che non bypassa mai localhost — esegue shell/scrittura file via Claude
    Agent SDK) in un `<meta name="vibecraft-agent-api-key">` subito dopo `<head>`, SOLO per
    richieste locali (stessa condizione di require_api_key, vedi _is_local_request).
    /static/shared.js lo copia in `window.__VIBECRAFT_AGENT_API_KEY__`. Un <meta> e non uno
    <script> inline: la CSP (CONTENT_SECURITY_POLICY) vieta gli script inline.

    Perché è sicuro anche se sembra "ridare" il bypass che require_api_key_strict nega
    apposta: la Same-Origin Policy del browser impedisce a uno script di un'ALTRA origine
    (una pagina ostile aperta in un'altra tab) di LEGGERE il body di questa risposta — può
    solo farsi navigare o fare fetch() opachi, mai leggerne il contenuto. Solo lo script
    della pagina stessa (same-origin, cioè questa dashboard) può leggere `window.__...__` e
    riusarlo. Un attaccante cross-site non impara nulla che non potrebbe già ottenere aprendo
    lui stesso questa pagina — e se la apre, è comunque un client locale, non l'attaccante.

    Se il server viene esposto oltre localhost (VIBECRAFT_HOST) l'iniezione si disattiva da
    sola (_is_local_request torna False per i client remoti): il fail-closed di
    require_api_key_strict per i non-locali resta intatto, la chiave non trapela mai nella
    pagina servita a un client remoto."""
    if not API_KEY or not _is_local_request(request):
        return html
    match = _HEAD_OPEN_RE.search(html)
    if not match:
        return html
    meta = f'<meta name="vibecraft-agent-api-key" content="{html_escape(API_KEY, quote=True)}" />'
    return html[:match.end()] + meta + html[match.end():]

"""Middleware di sicurezza HTTP: Host guard e header CSP/anti-framing.

R1 (2026-10-28): estratto da deps.py senza cambio di comportamento.
Il logger resta quello di api.deps (caplog/test su logger='api.deps').
"""
from fastapi.responses import PlainTextResponse

from api import deps

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
            log = deps.logger.warning
        else:
            log = deps.logger.debug
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


"""Serving template HTML e iniezione meta API key per agent/run.

R1 (2026-10-28): estratto da deps.py. TEMPLATES_DIR/API_KEY via api.deps.
"""
import re
from html import escape as html_escape
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from api import deps
from api.auth import _is_local_request as auth_is_local

# ---------------------------------------------------------------------------
# Serving dei template a tema (Matrix / Classico) — deps.TEMPLATES_DIR è assoluto
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
    return deps.TEMPLATES_DIR / (classic_name if theme == "classic" else matrix_name)


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
    Se `unified_name` esiste sotto deps.TEMPLATES_DIR (versione dedupata,
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
    workspace_path = deps.TEMPLATES_DIR / "workspace.html"
    if request.query_params.get("workspace") != "1" and workspace_path.exists():
        return HTMLResponse(_inject_data_theme(workspace_path.read_text(encoding="utf-8"), theme),
                            headers=NO_CACHE_HEADERS)

    unified_path = deps.TEMPLATES_DIR / unified_name
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
    richieste locali (stessa condizione di require_api_key, vedi auth_is_local).
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
    sola (auth_is_local torna False per i client remoti): il fail-closed di
    require_api_key_strict per i non-locali resta intatto, la chiave non trapela mai nella
    pagina servita a un client remoto."""
    if not deps.API_KEY or not auth_is_local(request):
        return html
    match = _HEAD_OPEN_RE.search(html)
    if not match:
        return html
    meta = f'<meta name="vibecraft-agent-api-key" content="{html_escape(deps.API_KEY, quote=True)}" />'
    return html[:match.end()] + meta + html[match.end():]


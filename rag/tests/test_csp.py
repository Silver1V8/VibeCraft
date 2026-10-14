"""Content-Security-Policy della console (api.deps.CONTENT_SECURITY_POLICY).

La CSP vale solo se il markup la rispetta: con `script-src 'self'` uno <script> inline o un
handler `onclick="..."` rimasto in un template smette in silenzio di funzionare (il browser lo
blocca, nessun test Python se ne accorge). Questi test tengono insieme le due metà: l'header
servito e il divieto di codice inline nei template e nel markup generato dagli script di
pagina. La verifica in un browser vero (zero violazioni su ogni pagina) è descritta in
SECURITY_SURFACE.md.
"""
import re

import pytest
from fastapi.testclient import TestClient

import api.deps as deps
from api.deps import CONTENT_SECURITY_POLICY, CSP_EXEMPT_PATHS
from core.config import STATIC_DIR, TEMPLATES_DIR

LOCAL_CLIENT = ("127.0.0.1", 50000)
PAGES = ["/", "/pipeline", "/intake", "/eval", "/analysis", "/infografica"]
TEMPLATES = sorted(TEMPLATES_DIR.glob("*.html"))
PAGE_SCRIPTS = sorted((STATIC_DIR / "pages").glob("*.js"))

# <script> senza src (inline), attributi on*= in HTML, URL javascript:.
INLINE_SCRIPT_RE = re.compile(r"<script\b(?![^>]*\bsrc\s*=)[^>]*>", re.IGNORECASE)
INLINE_HANDLER_RE = re.compile(r"""<[^>]*\son[a-z]+\s*=""", re.IGNORECASE)
JS_URL_RE = re.compile(r"""(?:href|src|action)\s*=\s*["']?\s*javascript:""", re.IGNORECASE)
# Nel JS: un attributo on*= dentro markup generato (stringa/template literal), quotato o
# no (`<b onclick=go()>`), anche con `/` al posto dello spazio (`<img/onerror=...>`), e
# l'equivalente via setAttribute('onclick', ...).
GENERATED_HANDLER_RE = re.compile(
    r"""[\s/]on[a-z]+\s*=\s*["'\\`$]"""
    r"""|<[a-z][^<>]*[\s/]on[a-z]+\s*="""
    r"""|setAttribute\(\s*["'`]on[a-z]+""",
    re.IGNORECASE,
)
ACTION_ATTR_RE = re.compile(r"""data-(?:click|change|input)="([^"$]+)\"""")
# Commenti JS: blocchi /* */ e righe che iniziano con //.
COMMENT_RE = re.compile(r"/\*.*?\*/|^[ \t]*//[^\n]*", re.S | re.M)
REGISTER_START_RE = re.compile(r"registerActions\(\s*\{")
JS_TOKEN_RE = re.compile(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|[\w$]+|[{}()[\],:]''')


def _registered_actions(source):
    """Top-level keys, including shorthand and several handlers on one line."""
    for start in REGISTER_START_RE.finditer(source):
        depth, key = 1, True
        for token in JS_TOKEN_RE.findall(source[start.end():]):
            if token in ("{", "(", "["):
                depth += 1
            elif token in ("}", ")", "]"):
                depth -= 1
                if depth == 0:
                    break
            elif depth == 1 and token == ",":
                key = True
            elif depth == 1 and key and re.fullmatch(r"[\w$]+", token):
                yield token
                key = False


def _directives(policy: str) -> dict[str, list[str]]:
    out = {}
    for part in policy.split(";"):
        tokens = part.split()
        if tokens:
            out[tokens[0]] = tokens[1:]
    return out


@pytest.fixture
def client(monkeypatch):
    import server
    monkeypatch.setattr(deps, "API_KEY", "k3y\"<script>")
    return TestClient(server.app, base_url="http://127.0.0.1:8000", client=LOCAL_CLIENT)


# ---------------------------------------------------------------------------
# Header servito
# ---------------------------------------------------------------------------
def test_policy_forbids_inline_and_eval_scripts():
    d = _directives(CONTENT_SECURITY_POLICY.decode())
    assert d["script-src"] == ["'self'"]
    assert d["default-src"] == ["'self'"]
    assert d["object-src"] == ["'none'"] and d["base-uri"] == ["'none'"]
    assert d["frame-ancestors"] == ["'none'"]
    # Nessuna fonte esterna: la console è local-first (vendor in /static/vendor/).
    for sources in d.values():
        assert not any(s.startswith(("http:", "https:", "*")) for s in sources), sources


@pytest.mark.parametrize("path", PAGES)
def test_every_page_is_served_with_the_full_policy(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers.get_list("content-security-policy") == [CONTENT_SECURITY_POLICY.decode()]


@pytest.mark.parametrize("path", sorted(CSP_EXEMPT_PATHS - {"/docs/oauth2-redirect"}))
def test_swagger_keeps_only_anti_framing(client, path):
    """Swagger/ReDoc caricano asset da CDN e hanno script inline: solo frame-ancestors."""
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-security-policy"] == "frame-ancestors 'none'"


def test_agent_key_is_injected_as_escaped_meta_not_inline_script(client):
    html = client.get("/pipeline").text
    assert '<meta name="vibecraft-agent-api-key" content="k3y&quot;&lt;script&gt;" />' in html
    assert "window.__VIBECRAFT_AGENT_API_KEY__" not in html
    # Il <meta> precede shared.js, che lo legge mentre il <head> viene analizzato.
    assert html.index("vibecraft-agent-api-key") < html.index('src="/static/shared.js"')


@pytest.mark.parametrize("script", PAGE_SCRIPTS, ids=lambda p: p.name)
def test_page_scripts_are_served_as_javascript_without_cache(client, script):
    response = client.get(f"/static/pages/{script.name}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "no-store" in response.headers.get("cache-control", "")


def test_unknown_page_script_is_404(client):
    assert client.get("/static/pages/nope.js").status_code == 404


# ---------------------------------------------------------------------------
# Markup: niente codice inline che la CSP bloccherebbe
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_templates_have_no_inline_code(template):
    html = template.read_text(encoding="utf-8")
    assert not INLINE_SCRIPT_RE.findall(html), "<script> inline: spostalo in /static/pages/"
    assert not INLINE_HANDLER_RE.findall(html), "handler on*= inline: usa data-click/data-change/data-input"
    assert not JS_URL_RE.findall(html), "URL javascript:"


@pytest.mark.parametrize("script", PAGE_SCRIPTS + [STATIC_DIR / "shared.js"], ids=lambda p: p.name)
def test_generated_markup_has_no_inline_handlers(script):
    """Anche il markup costruito in JS (innerHTML) finisce sotto la stessa CSP."""
    source = script.read_text(encoding="utf-8")
    # I commenti possono citare esempi di attacco (`<img onerror=…>`): non sono markup.
    codice = COMMENT_RE.sub("", source)
    assert not GENERATED_HANDLER_RE.findall(codice)


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_every_declared_action_is_registered(template):
    """Un data-click con un nome non registrato sarebbe un pulsante morto (solo un
    console.error): ogni azione del template e del suo script dev'essere nel registro."""
    html = template.read_text(encoding="utf-8")
    scripts = re.findall(r'<script src="/static/((?:pages/)?[\w.-]+\.js)"', html)
    sources = [html] + [(STATIC_DIR / rel).read_text(encoding="utf-8") for rel in scripts]
    declared = {name for src in sources for name in ACTION_ATTR_RE.findall(src)}
    registered = {name for src in sources for name in _registered_actions(src)}
    # La guida (infografica) non ha controlli da quando lo stato del progetto è in Console.
    assert declared or template.name == "infografica.unified.html",         "nessuna azione trovata: il template non ha controlli?"
    assert declared <= registered, declared - registered


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_referenced_scripts_exist(template):
    html = template.read_text(encoding="utf-8")
    for rel in re.findall(r'<script src="/static/([^"]+)"', html):
        assert (STATIC_DIR / rel).is_file(), rel

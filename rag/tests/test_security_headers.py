"""Header anti-framing e di igiene (api.deps.SecurityHeadersMiddleware) — difesa dal clickjacking.

Lo scenario chiuso: una pagina ostile incornicia /pipeline (o /intake, /reindex...) in un
<iframe> trasparente e fa cliccare all'utente i pulsanti veri; le fetch partono dalla pagina
incorniciata, quindi sono same-origin e l'anti-cross-site non le ferma. Gli header devono
esserci su OGNI risposta dell'app vera: pagine, API, statici, errori, streaming. I test usano
un base_url loopback (vedi test_host_header.py: `testserver` non è un Host ammesso).
"""
import asyncio

import pytest
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse, StreamingResponse

import api.deps as deps
from api import routes_pipeline
from api.deps import SecurityHeadersMiddleware, with_security_headers

LOCAL_CLIENT = ("127.0.0.1", 50000)
EXPECTED = {
    "x-frame-options": "DENY",
    "content-security-policy": "frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
}


@pytest.fixture
def client(monkeypatch):
    """server.app senza lifespan (Qdrant/embedder non servono a queste risposte)."""
    import server
    monkeypatch.setattr(deps, "API_KEY", None)
    return TestClient(server.app, base_url="http://127.0.0.1:8000", client=LOCAL_CLIENT,
                      raise_server_exceptions=False)


def _assert_security_headers(response):
    for name, value in EXPECTED.items():
        assert response.headers.get(name) == value, (name, dict(response.headers))


# ---------------------------------------------------------------------------
# App reale: pagine HTML, API JSON, statici, errori
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/", "/pipeline", "/intake"])
def test_html_pages_forbid_framing(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    _assert_security_headers(response)


def test_json_api_has_security_headers(client):
    response = client.get("/api/pipeline/dev-types")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    _assert_security_headers(response)


@pytest.mark.parametrize("path, mime", [
    ("/static/shared.js", "text/javascript"),       # route esplicita (FileResponse)
    ("/static/shared.css", "text/css"),
    ("/static/vendor/mermaid.min.js", "text/javascript"),   # mount StaticFiles
    ("/static/vendor/vis.min.css", "text/css"),
    ("/static/favicon.svg", "image/svg+xml"),
])
def test_static_assets_have_headers_and_correct_mime(client, path, mime):
    """Con `nosniff` un <script> servito con MIME sbagliato verrebbe bloccato: ogni asset
    referenziato dai template deve arrivare con il tipo giusto."""
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0].strip() == mime
    _assert_security_headers(response)


def test_404_has_security_headers(client):
    response = client.get("/non-esiste")
    assert response.status_code == 404
    _assert_security_headers(response)


def test_host_guard_400_has_security_headers(client):
    """Il middleware è più esterno di HostHeaderGuard: anche il rifiuto porta gli header."""
    response = client.get("/pipeline", headers={"Host": "attacker.example:8000"})
    assert response.status_code == 400
    _assert_security_headers(response)


def test_streaming_response_on_real_app_has_security_headers(client, monkeypatch):
    def fake_check_drift(feature, emit):
        emit(f"analisi {feature}")
        return {"ok": True}

    monkeypatch.setattr(routes_pipeline, "check_drift", fake_check_drift)
    with client.stream("POST", "/api/pipeline/drift/check/stream",
                       json={"feature": "demo"}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        _assert_security_headers(response)
        body = "".join(response.iter_text())
    assert '"analisi demo"' in body and '"result"' in body


# ---------------------------------------------------------------------------
# Middleware isolato: niente buffering, niente sovrascritture
# ---------------------------------------------------------------------------
def test_streaming_is_not_buffered():
    """Gli header viaggiano su http.response.start, che deve partire PRIMA che lo stream
    finisca: il generatore resta sospeso finché il test non vede lo start (se il middleware
    bufferizzasse, il test andrebbe in timeout)."""
    started = asyncio.Event()

    async def body():
        yield b"primo\n"
        await asyncio.wait_for(started.wait(), timeout=2)
        yield b"ultimo\n"

    app = SecurityHeadersMiddleware(StreamingResponse(body(), media_type="application/x-ndjson"))
    messages = []

    async def receive():
        await asyncio.sleep(10)
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)
        if message["type"] == "http.response.start":
            started.set()

    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}
    asyncio.run(asyncio.wait_for(app(scope, receive, send), timeout=5))
    assert messages[0]["type"] == "http.response.start"
    headers = {k.decode(): v.decode() for k, v in messages[0]["headers"]}
    assert headers["x-frame-options"] == "DENY"
    assert headers["content-security-policy"] == "frame-ancestors 'none'"
    bodies = [m.get("body", b"") for m in messages[1:]]
    assert b"".join(bodies) == b"primo\nultimo\n"


def test_route_headers_are_not_overwritten():
    app = SecurityHeadersMiddleware(JSONResponse({}, headers={
        "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'self';",
    }))
    response = TestClient(app).get("/")
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    # CSP esistente senza frame-ancestors: fusa, non sostituita, e un solo header.
    assert response.headers.get_list("content-security-policy") == [
        "default-src 'self'; frame-ancestors 'none'"]


def test_existing_frame_ancestors_is_left_alone():
    headers = [(b"content-security-policy", b"frame-ancestors 'self'")]
    out = with_security_headers(headers)
    assert [v for k, v in out if k == b"content-security-policy"] == [b"frame-ancestors 'self'"]

"""Validazione dell'header Host (api.deps.HostHeaderGuard) — difesa dal DNS rebinding.

Lo scenario chiuso: una pagina ostile su attacker.example fa risolvere il proprio nome a
127.0.0.1; le sue richieste arrivano dal loopback (bypass di require_api_key) e sono
same-origin per il browser, che quindi le lascia leggere — /pipeline compresa, con la
chiave iniettata. L'unico segnale lato server è l'header Host. I test sull'app vera
(server.app) usano un base_url loopback esplicito: `testserver`, l'host di default di
TestClient, NON è ammesso e non deve diventarlo.
"""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.deps as deps
from core.config import ALLOWED_HOSTS, build_allowed_hosts

RAG_DIR = Path(__file__).parents[1]
LOCAL_CLIENT = ("127.0.0.1", 50000)


@pytest.fixture
def server_client(monkeypatch):
    """server.app con chiave configurata e client loopback (il caso del rebinding). Niente
    `with`: il lifespan (Qdrant, embedder) non serve a /pipeline né a dev-types."""
    import server
    monkeypatch.setattr(deps, "API_KEY", "s3cret-agent-key")
    return TestClient(server.app, base_url="http://127.0.0.1:8000", client=LOCAL_CLIENT)


# ---------------------------------------------------------------------------
# App reale: Host estraneo rifiutato prima di pagine, API e statici
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/pipeline", "/api/pipeline/dev-types", "/api/health",
                                  "/static/shared.js"])
def test_foreign_host_is_rejected_on_real_app(server_client, path):
    response = server_client.get(path, headers={"Host": "attacker.example:8000"})
    assert response.status_code == 400
    assert "s3cret-agent-key" not in response.text


def test_foreign_host_gets_no_injected_key_on_pipeline(server_client):
    """La regressione esatta: da loopback con Host estraneo /pipeline rispondeva 200 con
    window.__VIBECRAFT_AGENT_API_KEY__ nell'HTML."""
    rebound = server_client.get("/pipeline", headers={"Host": "attacker.example:8000"})
    assert rebound.status_code == 400
    assert "__VIBECRAFT_AGENT_API_KEY__" not in rebound.text
    # Controprova: stesso client, Host loopback -> la chiave è iniettata come prima.
    legit = server_client.get("/pipeline")
    assert legit.status_code == 200
    assert "s3cret-agent-key" in legit.text


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:8000", "[::1]:8000",
                                  "localhost", "127.0.0.1", "[::1]", "LocalHost:8000",
                                  "localhost.:8000"])
def test_loopback_hosts_are_allowed_on_real_app(server_client, host):
    response = server_client.get("/api/pipeline/dev-types", headers={"Host": host})
    assert response.status_code == 200


def test_testserver_is_not_allowed_by_default(monkeypatch):
    """Il default di TestClient non è un host di produzione: nessuna eccezione per i test."""
    import server
    client = TestClient(server.app, client=LOCAL_CLIENT)  # base_url http://testserver
    assert client.get("/api/pipeline/dev-types").status_code == 400
    assert "testserver" not in ALLOWED_HOSTS


# ---------------------------------------------------------------------------
# Middleware isolato: parsing dell'header e insiemi configurati
# ---------------------------------------------------------------------------
def _guarded_client(allowed):
    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    app.add_middleware(deps.HostHeaderGuard, allowed_hosts=allowed)
    return TestClient(app, base_url="http://127.0.0.1", client=LOCAL_CLIENT)


@pytest.mark.parametrize("raw, expected", [
    ("127.0.0.1:8000", "127.0.0.1"),
    ("LOCALHOST", "localhost"),
    ("[::1]:8000", "::1"),
    ("[::1]", "::1"),
    ("vibecraft.lan.:8000", "vibecraft.lan"),
    ("", None),
    (None, None),
    ("::1", None),          # IPv6 senza parentesi: ambiguo con la porta
    ("[::1", None),         # parentesi non chiusa
    ("[::1]x", None),       # spazzatura dopo la parentesi
    (":8000", None),        # solo porta
    ("localhost:", None),   # porta presente ma vuota
    ("localhost:80a", None),  # porta non numerica
    ("[::1]:", None),
    ("[::1]:x", None),
    ("localhost:٨٠", None),  # cifre non ASCII
    ("local..host", None),  # etichetta vuota
    ("localhost..", None),
])
def test_host_from_header_parsing(raw, expected):
    assert deps.host_from_header(raw) == expected


def test_guard_rejects_missing_host_header():
    """Richiesta senza Host (HTTP/1.0): chiamata ASGI diretta, perché il transport di
    TestClient l'header lo aggiunge sempre. L'app interna non deve essere raggiunta."""
    reached, sent = [], []

    async def inner(scope, receive, send):
        reached.append(scope)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    guard = deps.HostHeaderGuard(inner, allowed_hosts={"127.0.0.1"})
    scope = {"type": "http", "method": "GET", "path": "/ping", "headers": [],
             "query_string": b"", "http_version": "1.0"}
    asyncio.run(guard(scope, receive, send))
    assert reached == []
    assert sent[0]["status"] == 400


def test_guard_allows_extra_host_and_rejects_others():
    client = _guarded_client(build_allowed_hosts("127.0.0.1", None, "vibecraft.lan"))
    assert client.get("/ping", headers={"Host": "vibecraft.lan:8000"}).status_code == 200
    assert client.get("/ping", headers={"Host": "evil.vibecraft.lan"}).status_code == 400


# ---------------------------------------------------------------------------
# Composizione dell'insieme ammesso (core.config.build_allowed_hosts)
# ---------------------------------------------------------------------------
def test_default_allowed_hosts_are_loopback_only():
    assert build_allowed_hosts("127.0.0.1", None, None) == {"127.0.0.1", "localhost", "::1"}
    # Bind su tutte le interfacce: 0.0.0.0/:: non sono nomi che un browser manda come Host.
    assert build_allowed_hosts("0.0.0.0", None, "") == {"127.0.0.1", "localhost", "::1"}
    assert build_allowed_hosts("::", None, None) == {"127.0.0.1", "localhost", "::1"}


def test_allowed_hosts_include_specific_bind_base_url_and_env_list():
    hosts = build_allowed_hosts(
        "192.168.1.10", "https://RAG.Example.org:8443/base",
        " vibecraft.lan , [fd00::5],,Other.Host. ",
    )
    assert hosts == {"127.0.0.1", "localhost", "::1", "192.168.1.10", "rag.example.org",
                     "vibecraft.lan", "fd00::5", "other.host"}
    assert build_allowed_hosts("127.0.0.1", "http://[::1", None) == {"127.0.0.1", "localhost", "::1"}


def test_allowed_hosts_env_is_read_at_import():
    """VIBECRAFT_ALLOWED_HOSTS e VIBECRAFT_BASE_URL arrivano davvero a core.config.ALLOWED_HOSTS
    (processo fresco: il valore è calcolato all'import)."""
    env = dict(os.environ, VIBECRAFT_ALLOWED_HOSTS="vibecraft.lan,10.0.0.7",
               VIBECRAFT_BASE_URL="http://proxy.example:9000", VIBECRAFT_HOST="127.0.0.1")
    result = subprocess.run(
        [sys.executable, "-c", "from core.config import ALLOWED_HOSTS; print(sorted(ALLOWED_HOSTS))"],
        cwd=RAG_DIR, env=env, check=True, capture_output=True, text=True, encoding="utf-8",
    )
    assert result.stdout.strip().splitlines()[-1] == str(sorted(
        {"127.0.0.1", "localhost", "::1", "vibecraft.lan", "10.0.0.7", "proxy.example"}))


def test_wildcard_entries_in_env_list_are_ignored_with_warning(caplog):
    with caplog.at_level("WARNING", logger="core.config"):
        hosts = build_allowed_hosts("127.0.0.1", None, "*,*.example.org,vibecraft.lan")
    assert hosts == {"127.0.0.1", "localhost", "::1", "vibecraft.lan"}
    assert sum("wildcard" in r.getMessage() for r in caplog.records) == 2


def _config_in_subprocess(expr, **env_overrides):
    """Valuta `expr` su core.config in un processo fresco (i valori sono calcolati
    all'import); le variabili di rete non passate vengono rimosse per non ereditarle."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("VIBECRAFT_BASE_URL", "VIBECRAFT_ALLOWED_HOSTS", "VIBECRAFT_HOST")}
    env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, "-c", f"import core.config as c; print(repr({expr}))"],
        cwd=RAG_DIR, env=env, check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return result.stdout.strip().splitlines()[-1]


@pytest.mark.parametrize("bind", ["0.0.0.0", "::", "[::]"])
def test_wildcard_bind_derives_loopback_base_url_that_is_allowed(bind):
    """Regressione: con il bind wildcard dell'immagine Docker (VIBECRAFT_HOST=0.0.0.0) e
    senza VIBECRAFT_BASE_URL, l'URL scritto nei prompt dell'agente era
    http://0.0.0.0:8000 — che il controllo dell'Host rifiuterebbe con 400. Ora usa il
    loopback, il suo host è fra quelli ammessi e 0.0.0.0 resta escluso."""
    out = _config_in_subprocess(
        "(c.SERVER_BASE_URL, __import__('urllib.parse').parse.urlsplit(c.SERVER_BASE_URL)"
        ".hostname in c.ALLOWED_HOSTS, '0.0.0.0' in c.ALLOWED_HOSTS)",
        VIBECRAFT_HOST=bind, VIBECRAFT_PORT="8000",
    )
    assert out == repr(("http://127.0.0.1:8000", True, False))


def test_specific_ipv6_bind_keeps_bracketed_base_url():
    out = _config_in_subprocess("c.SERVER_BASE_URL", VIBECRAFT_HOST="::1", VIBECRAFT_PORT="8000")
    assert out == repr("http://[::1]:8000")


def test_guard_is_active_in_reader_role(tmp_path):
    """Il ruolo reader monta un insieme ridotto di router ma lo stesso middleware."""
    script = (
        "from fastapi.testclient import TestClient\n"
        "import server\n"
        "c = TestClient(server.app, base_url='http://127.0.0.1:8000', client=('127.0.0.1', 1))\n"
        "print(c.get('/', headers={'Host': 'attacker.example:8000'}).status_code,"
        " c.get('/').status_code)\n"
    )
    env = dict(os.environ, VIBECRAFT_ROLE="reader", VIBECRAFT_INDEX_MODE="immutable",
               VIBECRAFT_DATABASE_DIR=str(tmp_path), VIBECRAFT_API_KEY="reader-secret",
               QDRANT_URL="http://127.0.0.1:16333", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    env.pop("VIBECRAFT_ALLOWED_HOSTS", None)
    result = subprocess.run([sys.executable, "-c", script], cwd=RAG_DIR, env=env, check=True,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.stdout.strip().splitlines()[-1] == "400 200"


def test_rejections_warn_once_per_distinct_host(caplog):
    client = _guarded_client({"127.0.0.1"})
    with caplog.at_level("DEBUG", logger="api.deps"):
        for _ in range(3):
            assert client.get("/ping", headers={"Host": "attacker.example"}).status_code == 400
        assert client.get("/ping", headers={"Host": "other.example"}).status_code == 400
    rejected = [r for r in caplog.records if "header Host non consentito" in r.getMessage()]
    assert [r.levelname for r in rejected] == ["WARNING", "DEBUG", "DEBUG", "WARNING"]

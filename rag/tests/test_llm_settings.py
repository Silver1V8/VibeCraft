"""Menu Impostazioni (2026-10-30): overlay delle scelte LLM sopra rag_config.yaml, API key
dei provider cloud che entrano ma non escono, provider OpenAI-compatibile."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.deps as deps
from api import routes_settings
from core import config as cfg
from core import llm
from core import llm_settings_store as store


@pytest.fixture
def files(tmp_path, monkeypatch):
    settings = tmp_path / "llm_settings.json"
    secrets = tmp_path / "secrets" / "llm_keys.json"
    monkeypatch.setattr(cfg, "LLM_SETTINGS_FILE", settings)
    monkeypatch.setattr(cfg, "LLM_SECRETS_FILE", secrets)
    monkeypatch.setitem(cfg.config, "llm_settings", cfg.merge_llm_overlay(cfg.LLM_SETTINGS_BASE, {}))
    for env in store.KEY_ENV.values():
        monkeypatch.delenv(env, raising=False)
    return settings, secrets


def test_merge_fonde_models_e_sostituisce_il_resto():
    base = {"active_provider": "ollama", "models": {"ollama": "q", "anthropic": "c"}, "purposes": {"ask": {}}}
    merged = cfg.merge_llm_overlay(base, {"models": {"anthropic": "opus"}, "purposes": {}})
    assert merged["models"] == {"ollama": "q", "anthropic": "opus"}
    assert merged["purposes"] == {}
    assert base["models"]["anthropic"] == "c"  # il blocco del YAML non viene toccato


def test_overlay_illeggibile_ferma_il_boot(tmp_path):
    broken = tmp_path / "llm_settings.json"
    broken.write_text("{non json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="illeggibili"):
        cfg.read_llm_overlay(broken)
    assert cfg.read_llm_overlay(tmp_path / "assente.json") == {}


def test_modalita_cloud_e_per_attivita_si_applicano_subito(files):
    settings_file, _ = files
    view = store.save({"mode": "cloud", "cloud_provider": "anthropic",
                       "models": {"anthropic": "claude-opus-5-5"}})
    assert view["mode"] == "cloud"
    assert llm.resolve("canvas") == ("anthropic", "claude-opus-5-5")
    assert json.loads(settings_file.read_text(encoding="utf-8"))["active_provider"] == "anthropic"

    store.save({"mode": "custom", "models": {"anthropic": "claude-sonnet-5-5"},
                "purposes": {"judge": {"provider": "anthropic", "model": "claude-opus-5-5"},
                             "ask": {"provider": "ollama"}}})
    assert llm.resolve("judge") == ("anthropic", "claude-opus-5-5")
    assert llm.resolve("ask")[0] == "ollama"
    assert llm.resolve("drift")[0] == "ollama"  # senza scelta: locale

    store.save({"mode": "local"})
    assert llm.resolve("judge")[0] == "ollama"


def test_salvataggio_invalido_non_scrive_nulla(files):
    settings_file, _ = files
    with pytest.raises(ValueError):
        store.save({"mode": "custom", "purposes": {"ask": {"provider": "gemini"}}})
    for url in ("ftp://x", "http://altro-host/v1"):  # la chiave non parte mai in chiaro
        with pytest.raises(ValueError):
            store.save({"mode": "cloud", "openai_base_url": url, "cloud_provider": "openai"})
    with pytest.raises(ValueError):
        store.save({"mode": "cloud", "pricing": {"m": {"input_per_mtok": float("nan")}}})
    assert not settings_file.exists()
    store.save({"mode": "local", "openai_base_url": "http://localhost:1234/v1"})


def test_api_key_entra_ma_non_esce(files, monkeypatch):
    _, secrets = files
    monkeypatch.setattr(deps, "API_KEY", None)
    app = FastAPI()
    app.include_router(routes_settings.router)
    client = TestClient(app, client=("127.0.0.1", 50000))

    r = client.post("/api/settings/llm/key", json={"provider": "anthropic", "api_key": "sk-ant-segreta"})
    assert r.status_code == 200 and r.json() == {"provider": "anthropic", "key": "file"}
    assert store.api_key("anthropic") == "sk-ant-segreta"
    view = client.get("/api/settings/llm")
    assert "sk-ant-segreta" not in view.text
    assert view.json()["providers"]["anthropic"]["key"] == "file"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "da-ambiente")
    assert store.api_key("anthropic") == "da-ambiente"  # l'ambiente vince
    assert store.key_source("anthropic") == "env"
    monkeypatch.delenv("ANTHROPIC_API_KEY")

    assert client.post("/api/settings/llm/key", json={"provider": "anthropic", "api_key": ""}).json()["key"] is None
    assert json.loads(secrets.read_text(encoding="utf-8")) == {}
    assert client.post("/api/settings/llm/key", json={"provider": "anthropic", "api_key": "a b"}).status_code == 422
    assert client.post("/api/settings/llm/key", json={"provider": "anthropic", "api_key": "skx"}).status_code == 422
    assert client.post("/api/settings/llm", json={"mode": "boh"}).status_code == 422


def test_provider_openai_compatibile(files, monkeypatch):
    store.set_api_key("openai", "sk-test")
    store.save({"mode": "cloud", "cloud_provider": "openai", "models": {"openai": "mistral-large"},
                "openai_base_url": "https://api.mistral.ai/v1/"})
    seen = {}

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "ciao"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 1}}

    class _Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, headers, json):
            seen.update(url=url, auth=headers["Authorization"], model=json["model"])
            return _Response()

    monkeypatch.setattr(llm.httpx2, "Client", _Client)
    assert llm.generate("domanda", purpose="ask") == "ciao"
    assert seen == {"url": "https://api.mistral.ai/v1/chat/completions",
                    "auth": "Bearer sk-test", "model": "mistral-large"}

    _Response.status_code = 401
    with pytest.raises(llm.LLMError, match="API key"):
        llm.generate("domanda", purpose="ask", max_attempts=1)


def test_budget_devia_anche_openai(files, monkeypatch):
    store.save({"mode": "cloud", "cloud_provider": "openai", "models": {"openai": "gpt-x"},
                "budget_daily_usd": 1})
    monkeypatch.setattr(llm, "spend_today_usd", lambda: 2.0)
    assert llm.resolve("ask") == ("ollama", cfg.config["llm_settings"]["models"]["ollama"])


def test_elenco_modelli_senza_chiave(files):
    anthropic = store.list_models("anthropic")
    assert anthropic["source"] == "default" and "claude-opus-5-5" in anthropic["models"]
    assert store.list_models("openai")["models"] == []
    with pytest.raises(ValueError):
        store.list_models("gemini")


def test_provider_claude_code_usa_l_agent_sdk_senza_strumenti(monkeypatch):
    import claude_agent_sdk
    from claude_agent_sdk.types import ResultMessage

    seen = {}

    def fake_query(prompt, options):
        seen.update(prompt=prompt, tools=options.tools, model=options.model, sources=options.setting_sources)

        async def gen():
            yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=seen.get("err", False),
                                num_turns=1, session_id="s", result="giudizio")
        return gen()

    monkeypatch.setattr(claude_agent_sdk, "query", fake_query)
    assert llm._claude_code_generate("claude-opus-5-5", "domanda", 5) == "giudizio"
    assert seen == {"prompt": "domanda", "tools": [], "model": "claude-opus-5-5", "sources": []}
    seen["err"] = True
    with pytest.raises(llm.LLMError, match="CLAUDE CODE"):
        llm._claude_code_generate("claude-opus-5-5", "domanda", 5)
    assert "claude_code" not in store.KEY_PROVIDERS  # niente chiave, prezzo o budget

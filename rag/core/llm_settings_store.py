"""Impostazioni LLM scelte dal menu Impostazioni della console (2026-10-30).

Tre modalità: tutto locale (Ollama), tutto cloud (un provider remoto) o una scelta per
attività (`llm_settings.purposes`, gli scopi di core.llm.PURPOSES). Il risultato è
l'overlay `core.config.LLM_SETTINGS_FILE` sopra il blocco llm_settings di
rag_config.yaml, che resta la fonte dei default commentati e non viene mai riscritto.

Le API key dei provider cloud stanno in `core.config.LLM_SECRETS_FILE`, fuori da git; la
variabile d'ambiente del provider, se c'è, vince. Le chiavi non escono mai da questo
modulo verso HTTP: la UI vede solo da dove arrivano (`env`, `file` o nessuna).
"""
import json
import math
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx2

from core import config as cfg

MODES = ("local", "cloud", "custom")
# claude_code è Claude via Claude Code con il login dell'abbonamento: cloud, ma senza API
# key né prezzo per token, quindi fuori da chiavi, prezzi e budget (KEY_PROVIDERS).
CLOUD_PROVIDERS = ("anthropic", "openai", "claude_code")
KEY_PROVIDERS = ("anthropic", "openai")
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1"
# Mostrati finché manca la chiave: con la chiave la lista viene dall'API (/v1/models).
ANTHROPIC_DEFAULT_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1")
# La CLI accetta anche gli alias, che seguono l'ultima versione disponibile sul piano.
CLAUDE_CODE_MODELS = ANTHROPIC_DEFAULT_MODELS + ("opus", "sonnet", "haiku")
MAX_KEY_LENGTH = 512
# Solo ASCII stampabile: un carattere di controllo farebbe fallire l'header HTTP con un
# errore che riporta la chiave, e list_models lo restituirebbe alla UI.
_KEY_RE = re.compile(r"[!-~]*")
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _write_json_atomic(path: Path, data: dict) -> None:
    """Scrittura atomica: un crash a metà non deve lasciare un overlay troncato, che al
    riavvio fermerebbe il boot (core.config.read_llm_overlay)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_secrets(path: Path | None = None) -> dict:
    try:
        data = json.loads((path or cfg.LLM_SECRETS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def api_key(provider: str, *, path: Path | None = None) -> str | None:
    """Chiave del provider cloud: variabile d'ambiente, poi file delle Impostazioni."""
    env = os.environ.get(KEY_ENV.get(provider, ""), "").strip()
    if env:
        return env
    value = _read_secrets(path).get(provider)
    return value.strip() if isinstance(value, str) and value.strip() else None


def key_source(provider: str, *, path: Path | None = None) -> str | None:
    if os.environ.get(KEY_ENV.get(provider, ""), "").strip():
        return "env"
    return "file" if api_key(provider, path=path) else None


def set_api_key(provider: str, key: str | None, *, path: Path | None = None) -> None:
    """Salva (o con chiave vuota cancella) la chiave del provider nel file dei segreti."""
    if provider not in KEY_PROVIDERS:
        raise ValueError(f"Provider cloud sconosciuto: '{provider}'.")
    key = (key or "").strip()
    if len(key) > MAX_KEY_LENGTH or not _KEY_RE.fullmatch(key):
        raise ValueError("API key non valida: solo caratteri stampabili senza spazi, al massimo 512.")
    target = path or cfg.LLM_SECRETS_FILE
    secrets = _read_secrets(target)
    if key:
        secrets[provider] = key
    else:
        secrets.pop(provider, None)
    _write_json_atomic(target, secrets)


def openai_base_url() -> str:
    raw = (cfg.config.get("llm_settings") or {}).get("openai_base_url")
    return (raw or DEFAULT_OPENAI_BASE_URL).rstrip("/")


def _claude_cli() -> str | None:
    from core.llm import claude_cli_path

    return claude_cli_path() or "bundled"


def _valid_base_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    parts = urlsplit(value)
    # La chiave OpenAI (anche quella della variabile d'ambiente) parte verso questo host:
    # mai in chiaro fuori dalla macchina. http solo per un server locale (vLLM, LM Studio).
    if not parts.netloc or not (parts.scheme == "https"
                                or (parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS)):
        raise ValueError("Base URL OpenAI-compatibile non valido: serve https://host/..., "
                         "oppure http:// solo verso localhost.")
    return value


def _current_mode(raw: dict) -> str:
    if raw.get("mode") in MODES:
        return raw["mode"]
    if raw.get("purposes"):
        return "custom"
    return "local" if raw.get("active_provider") == "ollama" else "cloud"


def current_view() -> dict:
    """Stato per la UI: modalità, modelli, scelte per attività e provenienza delle chiavi."""
    from core.llm import PURPOSES

    raw = cfg.config.get("llm_settings") or {}
    active = raw.get("active_provider")
    return {
        "mode": _current_mode(raw),
        "cloud_provider": active if active in CLOUD_PROVIDERS else (raw.get("cloud_provider") or "anthropic"),
        "models": dict(raw.get("models") or {}),
        "purposes": {k: dict(v) for k, v in (raw.get("purposes") or {}).items() if isinstance(v, dict)},
        "activities": list(PURPOSES),
        "providers": {
            "anthropic": {"key": key_source("anthropic"), "key_env": KEY_ENV["anthropic"]},
            "openai": {"key": key_source("openai"), "key_env": KEY_ENV["openai"], "base_url": openai_base_url()},
            "claude_code": {"cli": bool(_claude_cli()), "api_key_env": bool(os.environ.get("ANTHROPIC_API_KEY"))},
        },
        "pricing": dict(raw.get("pricing") or {}),
        "budget_daily_usd": (raw.get("budget") or {}).get("daily_usd"),
    }


def _price(value) -> float:
    price = float(value)
    # NaN renderebbe NaN il contatore di spesa e il tetto giornaliero non scatterebbe più.
    if not math.isfinite(price) or price < 0:
        raise ValueError("Prezzi e budget devono essere numeri finiti, non negativi.")
    return price


def build_overlay(payload: dict) -> dict:
    """Dal modulo della UI all'overlay da salvare. Valida ciò che la validazione di
    LLMSettings non vede: modalità, provider cloud, URL, prezzi e budget."""
    from core.llm import PURPOSES

    mode = payload.get("mode")
    if mode not in MODES:
        raise ValueError(f"Modalità sconosciuta: '{mode}' (attese: {', '.join(MODES)}).")
    providers = cfg.VALID_LLM_PROVIDERS
    models = {p: str(m).strip() for p, m in (payload.get("models") or {}).items()
              if p in providers and str(m or "").strip()}
    cloud = payload.get("cloud_provider") or "anthropic"
    if cloud not in CLOUD_PROVIDERS:
        raise ValueError(f"Provider cloud sconosciuto: '{cloud}'.")
    overlay: dict = {"mode": mode, "cloud_provider": cloud, "models": models, "purposes": {}}
    if mode == "local":
        overlay["active_provider"] = "ollama"
    elif mode == "cloud":
        overlay["active_provider"] = cloud
    else:
        # Le attività senza scelta ricadono sul locale, come il default del YAML.
        overlay["active_provider"] = "ollama"
        for purpose, choice in (payload.get("purposes") or {}).items():
            if purpose not in PURPOSES or not isinstance(choice, dict):
                continue
            provider = choice.get("provider")
            if provider not in providers:
                raise ValueError(f"Provider sconosciuto per '{purpose}': '{provider}'.")
            entry = {"provider": provider}
            if str(choice.get("model") or "").strip():
                entry["model"] = str(choice["model"]).strip()
            overlay["purposes"][purpose] = entry
    if payload.get("openai_base_url"):
        overlay["openai_base_url"] = _valid_base_url(payload["openai_base_url"])
    pricing = {}
    for model, entry in (payload.get("pricing") or {}).items():
        if not isinstance(entry, dict) or entry.get("input_per_mtok") in (None, ""):
            continue
        pricing[str(model)] = {"input_per_mtok": _price(entry["input_per_mtok"]),
                               "output_per_mtok": _price(entry.get("output_per_mtok") or 0)}
    if pricing:
        overlay["pricing"] = pricing
    daily = payload.get("budget_daily_usd")
    if daily in (None, ""):
        overlay["budget"] = None
    else:
        base_budget = cfg.LLM_SETTINGS_BASE.get("budget") or {}
        overlay["budget"] = {"daily_usd": _price(daily), "fallback_provider": "ollama",
                             "spend_file": base_budget.get("spend_file") or "database/llm_spend.json"}
    return overlay


def save(payload: dict) -> dict:
    """Valida come al boot, scrive l'overlay e lo applica subito: core.llm rilegge
    config["llm_settings"] a ogni chiamata, quindi non serve riavviare il server."""
    overlay = build_overlay(payload)
    merged = cfg.merge_llm_overlay(cfg.LLM_SETTINGS_BASE, overlay)
    cfg.validate_llm_settings(merged, boot=True)
    _write_json_atomic(cfg.LLM_SETTINGS_FILE, overlay)
    cfg.config["llm_settings"] = merged
    return current_view()


def _get_json(url: str, headers: dict, timeout: float) -> dict:
    with httpx2.Client(timeout=timeout, follow_redirects=False) as client:
        response = client.get(url, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}")
    return response.json()


def list_models(provider: str, *, timeout: float = 10.0) -> dict:
    """Modelli disponibili per il selettore della UI. Gli errori tornano come testo
    (mai la chiave): la UI resta usabile scrivendo il nome del modello a mano."""
    if provider not in cfg.VALID_LLM_PROVIDERS:
        raise ValueError(f"Provider sconosciuto: '{provider}'.")
    try:
        if provider == "ollama":
            data = _get_json(f"{cfg.OLLAMA_URL.rstrip('/')}/api/tags", {}, timeout)
            return {"models": sorted(m["name"] for m in data.get("models", [])), "source": "api"}
        if provider == "claude_code":
            return {"models": list(CLAUDE_CODE_MODELS), "source": "default"}
        if provider == "anthropic":
            key = api_key("anthropic")
            if not key:
                return {"models": list(ANTHROPIC_DEFAULT_MODELS), "source": "default"}
            data = _get_json(f"{ANTHROPIC_API_URL}/models?limit=100",
                             {"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout)
            return {"models": [m["id"] for m in data.get("data", [])], "source": "api"}
        key = api_key("openai")
        if not key:
            return {"models": [], "source": "default", "error": "API key assente"}
        data = _get_json(f"{openai_base_url()}/models", {"Authorization": f"Bearer {key}"}, timeout)
        return {"models": sorted(m["id"] for m in data.get("data", [])), "source": "api"}
    except Exception as exc:  # rete, HTTP, JSON inatteso: la UI mostra il motivo
        fallback = list(ANTHROPIC_DEFAULT_MODELS) if provider == "anthropic" else []
        return {"models": fallback, "source": "default", "error": f"{type(exc).__name__}: {exc}"[:200]}

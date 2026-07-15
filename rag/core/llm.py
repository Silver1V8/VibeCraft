"""Layer LLM unico del package: tutte le chiamate generative (drift, canvas, propose,
validate, explore, canvas review) passano da qui invece che da client HTTP sparsi nei
moduli. Il provider e il modello si risolvono da rag_config.yaml per singolo scopo
(`llm_settings.purposes`, con fallback su `active_provider`/`models`), così si può ad
esempio tenere Ollama per il drift e passare a Claude per il canvas senza toccare codice.

Interfaccia: `generate(prompt, *, purpose)` (sincrona) e `agenerate(...)` (async).
Gli errori di rete/configurazione sollevano sempre `LLMError` con un messaggio leggibile:
sono i chiamanti a decidere la politica di tolleranza (il check drift mette il messaggio
nel report, l'archive salta la review con un warning, le route pipeline restituiscono il
messaggio come testo). Per i test si inietta un provider fake con `register_provider`.
"""
import json
import urllib.error
import urllib.request

import httpx

from core.config import OLLAMA_NUM_CTX, OLLAMA_THINK, OLLAMA_TIMEOUT_SECONDS, config


def _ollama_payload(model: str, prompt: str) -> dict:
    """Payload di /api/generate. Entrambi i campi opzionali sono inclusi solo se configurati
    (omessi, il payload resta quello storico):
    · `think` (llm_settings.ollama_think) — con i modelli thinking (qwen3.5) `false` evita
      che il ragionamento esaurisca la generazione lasciando la risposta vuota;
    · `options.num_ctx` (llm_settings.ollama_num_ctx) — senza, Ollama resta a 4096 token e
      TRONCA DALL'ALTO i prompt di canvas/propose (>4.300 token): il modello non vedeva
      l'intervista in cima e la risposta usciva mozzata."""
    payload = {"model": model, "prompt": prompt, "stream": False}
    if OLLAMA_THINK is not None:
        payload["think"] = OLLAMA_THINK
    if OLLAMA_NUM_CTX is not None:
        payload["options"] = {"num_ctx": OLLAMA_NUM_CTX}
    return payload

# Scopi riconosciuti della pipeline: usati solo per validare i typo, la risoluzione
# provider/modello funziona per qualunque chiave presente in llm_settings.purposes.
PURPOSES = ("drift", "canvas", "propose", "validate", "explore", "review")

# Endpoint locale di Ollama (unica copia: prima era duplicato in indexing/pipeline/config).
OLLAMA_GENERATE_URL = "http://127.0.0.1:11434/api/generate"

# max_tokens per il provider anthropic: le generazioni della pipeline (canvas, spec,
# report) sono documenti lunghi ma sotto la soglia che richiederebbe lo streaming.
ANTHROPIC_MAX_TOKENS = 8192


class LLMError(RuntimeError):
    """Errore di generazione (rete, timeout, provider mal configurato). Il messaggio
    è già leggibile dall'utente finale, negli stessi termini dei vecchi client."""


def resolve(purpose: str) -> tuple[str, str]:
    """Risolve (provider, model) per lo scopo dato: override da llm_settings.purposes
    se presente, altrimenti active_provider + models[provider]."""
    if purpose not in PURPOSES:
        raise LLMError(f"Scopo LLM sconosciuto: '{purpose}' (attesi: {', '.join(PURPOSES)})")
    settings = config["llm_settings"]
    override = (settings.get("purposes") or {}).get(purpose) or {}
    provider = override.get("provider") or settings["active_provider"]
    models = settings.get("models") or {}
    model = override.get("model") or models.get(provider)
    if not model:
        raise LLMError(f"Nessun modello configurato per il provider '{provider}' (llm_settings.models).")
    return provider, model


# ---------------------------------------------------------------------------
# Provider: ollama
# ---------------------------------------------------------------------------

def _ollama_generate(model: str, prompt: str, timeout: float) -> str:
    data = json.dumps(_ollama_payload(model, prompt)).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_GENERATE_URL, data=data, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise LLMError(f"[ERRORE OLLAMA]: Il modello '{model}' non è stato trovato. Esegui 'ollama pull {model}'.") from e
        raise LLMError(f"[ERRORE GENERICO OLLAMA]: {e}") from e
    except urllib.error.URLError as e:
        raise LLMError("[ERRORE DI CONNESSIONE]: Impossibile raggiungere Ollama. Assicurati che l'applicazione Ollama sia avviata.") from e
    except TimeoutError as e:
        raise LLMError("[ERRORE DI TIMEOUT]: Ollama sta impiegando troppo tempo a rispondere.") from e
    except Exception as e:
        raise LLMError(f"[ERRORE GENERICO OLLAMA]: {e}") from e
    return result.get("response", "Errore nella generazione.")


async def _ollama_agenerate(model: str, prompt: str, timeout: float) -> str:
    data = _ollama_payload(model, prompt)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(OLLAMA_GENERATE_URL, json=data)
        if response.status_code == 404:
            raise LLMError(f"[ERRORE OLLAMA]: Il modello '{model}' non è stato trovato. Esegui 'ollama pull {model}'.")
        response.raise_for_status()
        return response.json().get("response", "Errore nella generazione.")
    except LLMError:
        raise
    except httpx.ConnectError as e:
        raise LLMError("[ERRORE DI CONNESSIONE]: Impossibile raggiungere Ollama. Assicurati che l'applicazione Ollama sia avviata.") from e
    except httpx.TimeoutException as e:
        raise LLMError("[ERRORE DI TIMEOUT]: Ollama sta impiegando troppo tempo a rispondere.") from e
    except Exception as e:
        raise LLMError(f"[ERRORE GENERICO OLLAMA]: {e}") from e


# ---------------------------------------------------------------------------
# Provider: anthropic (Claude API — SDK ufficiale, API key da ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------

def _anthropic_module():
    try:
        import anthropic
    except ImportError as e:
        raise LLMError(
            "[ERRORE ANTHROPIC]: pacchetto 'anthropic' non installato. Esegui 'uv add anthropic' in rag/."
        ) from e
    return anthropic


def _anthropic_text(message) -> str:
    return "".join(block.text for block in message.content if block.type == "text")


def _anthropic_generate(model: str, prompt: str, timeout: float) -> str:
    anthropic = _anthropic_module()
    try:
        client = anthropic.Anthropic(timeout=timeout)
        message = client.messages.create(
            model=model,
            max_tokens=ANTHROPIC_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return _anthropic_text(message)
    except anthropic.AuthenticationError as e:
        raise LLMError("[ERRORE ANTHROPIC]: API key mancante o non valida. Imposta la variabile d'ambiente ANTHROPIC_API_KEY.") from e
    except anthropic.APITimeoutError as e:
        raise LLMError("[ERRORE DI TIMEOUT]: l'API Anthropic sta impiegando troppo tempo a rispondere.") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("[ERRORE DI CONNESSIONE]: impossibile raggiungere l'API Anthropic.") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"[ERRORE ANTHROPIC {e.status_code}]: {e.message}") from e
    except Exception as e:
        raise LLMError(f"[ERRORE GENERICO ANTHROPIC]: {e}") from e


async def _anthropic_agenerate(model: str, prompt: str, timeout: float) -> str:
    anthropic = _anthropic_module()
    try:
        client = anthropic.AsyncAnthropic(timeout=timeout)
        message = await client.messages.create(
            model=model,
            max_tokens=ANTHROPIC_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return _anthropic_text(message)
    except anthropic.AuthenticationError as e:
        raise LLMError("[ERRORE ANTHROPIC]: API key mancante o non valida. Imposta la variabile d'ambiente ANTHROPIC_API_KEY.") from e
    except anthropic.APITimeoutError as e:
        raise LLMError("[ERRORE DI TIMEOUT]: l'API Anthropic sta impiegando troppo tempo a rispondere.") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("[ERRORE DI CONNESSIONE]: impossibile raggiungere l'API Anthropic.") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"[ERRORE ANTHROPIC {e.status_code}]: {e.message}") from e
    except Exception as e:
        raise LLMError(f"[ERRORE GENERICO ANTHROPIC]: {e}") from e


# ---------------------------------------------------------------------------
# Registry e API pubblica
# ---------------------------------------------------------------------------

# provider -> (fn sincrona, fn async). Le fn hanno firma (model, prompt, timeout) -> str.
_PROVIDERS: dict[str, tuple] = {
    "ollama": (_ollama_generate, _ollama_agenerate),
    "anthropic": (_anthropic_generate, _anthropic_agenerate),
}


def register_provider(name: str, sync_fn, async_fn=None) -> None:
    """Registra (o sostituisce) un provider — pensato per i test, che iniettano un
    fake senza HTTP. `async_fn` opzionale: se assente, la variante async avvolge la
    sincrona (le fn fake sono istantanee)."""
    if async_fn is None:
        async def async_fn(model, prompt, timeout, _sync=sync_fn):
            return _sync(model, prompt, timeout)
    _PROVIDERS[name] = (sync_fn, async_fn)


def _provider_fns(provider: str) -> tuple:
    try:
        return _PROVIDERS[provider]
    except KeyError:
        raise LLMError(f"Provider LLM non supportato: '{provider}'") from None


def generate(prompt: str, *, purpose: str, timeout: float = OLLAMA_TIMEOUT_SECONDS) -> str:
    """Genera testo in modo SINCRONO con il provider/modello risolti per `purpose`.
    Solleva LLMError con messaggio leggibile su qualsiasi errore."""
    provider, model = resolve(purpose)
    sync_fn, _ = _provider_fns(provider)
    return sync_fn(model, prompt, timeout)


async def agenerate(prompt: str, *, purpose: str, timeout: float = OLLAMA_TIMEOUT_SECONDS) -> str:
    """Come `generate` ma ASINCRONA (per i route handler FastAPI: non blocca l'event
    loop durante generazioni che su CPU durano minuti)."""
    provider, model = resolve(purpose)
    _, async_fn = _provider_fns(provider)
    return await async_fn(model, prompt, timeout)

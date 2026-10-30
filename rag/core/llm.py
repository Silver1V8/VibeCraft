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
import asyncio
import json
import logging
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx2

from pydantic import ValidationError

from core.config import (
    OLLAMA_NUM_CTX,
    OLLAMA_THINK,
    OLLAMA_TEMPERATURE,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_URL,
    RAG_DIR,
    VALID_LLM_PROVIDERS,
    LLMSettings,
    config,
    validate_llm_settings,
)
from core.llm_settings_store import KEY_PROVIDERS, api_key, openai_base_url

logger = logging.getLogger(__name__)


def _ollama_payload(model: str, prompt: str, *, stream: bool = False) -> dict:
    """Payload di /api/generate. I campi opzionali sono inclusi solo se configurati
    (omessi, il payload resta quello storico):
    · `think` (llm_settings.ollama_think) — con i modelli thinking (qwen3.5) `false` evita
      che il ragionamento esaurisca la generazione lasciando la risposta vuota;
    · `options.num_ctx` (llm_settings.ollama_num_ctx) — senza, Ollama resta a 4096 token e
      TRONCA DALL'ALTO i prompt di canvas/propose (>4.300 token): il modello non vedeva
      l'intervista in cima e la risposta usciva mozzata;
    · `options.temperature` (llm_settings.ollama_temperature) — senza, Ollama campiona a 0.8:
      sugli step a formato rigido (spec.md) lo stesso prompt sbagliava a ogni run in un modo
      diverso, e il rimedio è la temperatura, non altre istruzioni nel prompt.

    Solleva LLMError se il prompt, da solo, raggiunge o supera `num_ctx` (A1): a quel
    punto il troncamento dall'alto non è più un rischio, è certo — Ollama non ha spazio
    per il prompt intero, figuriamoci per la generazione. Misurato dal vivo il
    2026-09-03: `/ask` con `top_k=20` (il tetto già imposto dal server, non bypassabile
    dal client) produce oggi ~17.013 token stimati su num_ctx=16384 — 104%, non un caso
    limite raro — e senza questo guardrail la risposta tornava comunque `status:
    "success"`. Sotto la soglia resta un `logger.warning` (rischio, non certezza)."""
    payload = {"model": model, "prompt": prompt, "stream": stream}
    if OLLAMA_THINK is not None:
        payload["think"] = OLLAMA_THINK
    options = {}
    if OLLAMA_NUM_CTX is not None:
        options["num_ctx"] = OLLAMA_NUM_CTX
    if OLLAMA_TEMPERATURE is not None:
        options["temperature"] = OLLAMA_TEMPERATURE
    if options:
        payload["options"] = options
    if OLLAMA_NUM_CTX is not None:
        # Guardrail sul troncamento: stima conservativa ~3 caratteri/token per l'italiano.
        est_tokens = len(prompt) // 3
        if est_tokens >= OLLAMA_NUM_CTX:
            # CERTEZZA, non rischio: il prompt da solo eccede la finestra. Un warning qui
            # sarebbe la stessa cosa del difetto che questo guardrail esiste per correggere
            # — un troncamento (e una risposta status:"success") che nessuno vede accadere.
            raise LLMError(
                f"[FINESTRA DI CONTESTO SUPERATA]: prompt stimato in ~{est_tokens} token contro "
                f"num_ctx={OLLAMA_NUM_CTX}. Ollama troncherebbe il prompt dall'alto in modo "
                "silenzioso (perdendo le istruzioni di sistema e le fonti più rilevanti): "
                "riduci top_k o i chunk del contesto governato, oppure alza "
                "llm_settings.ollama_num_ctx in rag_config.yaml."
            )
        if est_tokens > OLLAMA_NUM_CTX * 0.8:
            # Sotto la soglia di certezza, ma vicino: la stima è approssimativa e la
            # generazione può comunque riuscire — un log, non un blocco.
            logger.warning(
                "Prompt vicino alla finestra di contesto di Ollama: ~%d token stimati "
                "su num_ctx=%d. Rischio troncamento silenzioso (prompt tagliato dall'alto, "
                "risposta mozzata): alza llm_settings.ollama_num_ctx in rag_config.yaml o "
                "riduci i chunk del contesto governato.",
                est_tokens, OLLAMA_NUM_CTX,
            )
    return payload

# Scopi riconosciuti (gli step della pipeline, la sintesi di /ask e il giudice di
# attribuzione di eval/attribution.py — "judge", sostituibile per scopo): usati solo per
# validare i typo, la risoluzione provider/modello funziona per qualunque chiave
# presente in llm_settings.purposes.
PURPOSES = ("drift", "canvas", "propose", "validate", "explore", "review", "ask", "judge")

# Endpoint di generazione derivato dalla base OLLAMA_URL (env VIBECRAFT_OLLAMA_URL,
# core/config.py): unica copia dell'URL di Ollama in tutto il codice.
OLLAMA_GENERATE_URL = f"{OLLAMA_URL.rstrip('/')}/api/generate"

# max_tokens per il provider anthropic: le generazioni della pipeline (canvas, spec,
# report) sono documenti lunghi ma sotto la soglia che richiederebbe lo streaming.
ANTHROPIC_MAX_TOKENS = 8192


class LLMError(RuntimeError):
    """Errore di generazione (rete, timeout, provider mal configurato). Il messaggio
    è già leggibile dall'utente finale, negli stessi termini dei vecchi client."""


def _llm_settings() -> LLMSettings:
    """Vista TIPATA del blocco llm_settings corrente. Non usa la costante
    core.config.LLM_SETTINGS ma rilegge il dict `config` a ogni chiamata: i test (e
    l'eventuale ricarica del config) sostituiscono `config["llm_settings"]` a runtime,
    e la risoluzione deve vedere il valore sostituito. La validazione è quella NON di
    boot: `models` vuoto resta ammesso qui, perché il messaggio d'errore storico per
    quel caso lo produce resolve() poco sotto."""
    raw = config.get("llm_settings")
    if isinstance(raw, LLMSettings):
        return raw
    try:
        return validate_llm_settings(raw)
    except ValidationError as e:
        raise LLMError(f"Blocco 'llm_settings' non valido in rag_config.yaml: {e}") from e


# ---------------------------------------------------------------------------
# Budget guard: tetto di spesa GIORNALIERO (UTC) sulle chiamate Anthropic
#
# Il contatore si alimenta dal costo già calcolato per il log strutturato delle
# chiamate Anthropic (_log_anthropic_usage, più sotto): senza `llm_settings.pricing`
# per quel modello il costo non è noto e non viene contato nulla — il guard resta
# quindi inerte, come quando il blocco `budget` manca del tutto. Seconda fonte: il
# costo di fine run dell'agente Claude (agent_bridge), riportato dall'SDK; oltre soglia
# quei run vengono rifiutati con 429 (budget_exhausted), non deviati.
#
# Regola di sicurezza valida per TUTTO questo blocco: il guard non deve MAI far
# fallire una generazione. Ogni errore interno (config malformata, file di spesa
# illeggibile, disco pieno) viene loggato e si resta sul provider originale.
# ---------------------------------------------------------------------------

_spend_lock = threading.Lock()
# Stato in-memory del contatore: giorno UTC di competenza e spesa accumulata. Con un
# file di persistenza configurato è solo una cache di ciò che sta su disco.
_spend_state: dict = {"day": "", "usd": 0.0}


def _utc_day() -> str:
    """Giorno di competenza del contatore, in UTC (non nel fuso locale: la soglia deve
    azzerarsi allo stesso istante ovunque giri il server)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _budget_settings():
    """Blocco `llm_settings.budget` tipato, o None se assente/illeggibile."""
    try:
        return _llm_settings().budget
    except Exception:
        return None


def _spend_file_path() -> Path | None:
    """File JSON in cui persistere la spesa (llm_settings.budget.spend_file, relativo a
    rag/ se non assoluto). None = contatore solo in-memory, azzerato dal riavvio."""
    budget = _budget_settings()
    raw = getattr(budget, "spend_file", None) if budget is not None else None
    if not raw:
        return None
    path = Path(str(raw))
    return path if path.is_absolute() else RAG_DIR / path


def _read_spend(path: Path | None) -> tuple[str, float]:
    """Stato (giorno, spesa) da cui partire: dal file se configurato, altrimenti dalla
    memoria. Un file assente o corrotto vale zero — la spesa è un'informazione di
    controllo, non un dato da recuperare a tutti i costi. Va chiamata sotto lock."""
    if path is not None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return str(data.get("day") or ""), float(data.get("usd") or 0.0)
        except (OSError, ValueError, TypeError):
            return "", 0.0
    return str(_spend_state["day"]), float(_spend_state["usd"])


def _record_spend(cost_usd: float) -> None:
    """Aggiunge il costo di UNA chiamata Anthropic riuscita, o di UN run del runner
    agente `claude` (agent_bridge, anche fallito se l'SDK ne riporta il costo), al totale
    del giorno UTC corrente (azzerandolo se l'ultimo aggiornamento è di ieri). Thread-safe."""
    try:
        if not cost_usd or cost_usd <= 0:
            return
        path = _spend_file_path()
        today = _utc_day()
        with _spend_lock:
            day, usd = _read_spend(path)
            total = (usd if day == today else 0.0) + float(cost_usd)
            _spend_state["day"], _spend_state["usd"] = today, total
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps({"day": today, "usd": round(total, 6)}), encoding="utf-8")
    except Exception:
        logger.warning("Impossibile aggiornare il contatore di spesa Claude.", exc_info=True)


def spend_today_usd() -> float:
    """Spesa Anthropic registrata per il giorno UTC CORRENTE. 0.0 se non c'è nulla di
    registrato o se il totale memorizzato è di un giorno precedente (reset implicito:
    niente job di rollover, il confronto sul giorno basta)."""
    try:
        today = _utc_day()
        with _spend_lock:
            day, usd = _read_spend(_spend_file_path())
        return usd if day == today else 0.0
    except Exception:
        logger.warning("Impossibile leggere il contatore di spesa Claude.", exc_info=True)
        return 0.0


def budget_exhausted() -> tuple[float, float] | None:
    """(spesa, soglia) se il budget giornaliero è attivo (`budget.daily_usd` impostato) e
    la spesa del giorno UTC l'ha raggiunto, altrimenti None. Usata da POST
    /api/pipeline/agent/run: un run dell'agente Claude non ha un provider locale su cui
    degradare, quindi oltre soglia viene rifiutato invece che deviato. Come il resto del
    guard non fa mai fallire la chiamata: un errore interno vale "budget non esaurito"."""
    try:
        budget = _budget_settings()
        if budget is None or budget.daily_usd is None:
            return None
        threshold = float(budget.daily_usd)
        spent = spend_today_usd()
        return (spent, threshold) if spent >= threshold else None
    except Exception:
        logger.warning("Budget guard non applicabile ai run agente.", exc_info=True)
        return None


# Runner il cui costo finisce nel budget Claude giornaliero (llm_settings.budget): solo
# `claude` spende sull'account Anthropic e riporta total_cost_usd. `local` (Ollama) è
# gratuito; codex/cursor fatturano su account propri e non riportano un costo.
BUDGETED_RUNNERS = frozenset({'claude'})


def budget_block(runner: str) -> str | None:
    """Messaggio di rifiuto se il runner è a pagamento e il budget del giorno è esaurito."""
    if runner not in BUDGETED_RUNNERS or (hit := budget_exhausted()) is None:
        return None
    spent, threshold = hit
    return (f'Budget Claude giornaliero esaurito (spesa {spent:.2f} USD, soglia {threshold:.2f} USD): '
            'i run del runner claude riprendono dopo la mezzanotte UTC. Usa il runner locale '
            'o alza llm_settings.budget.daily_usd.')


def seconds_to_utc_midnight() -> int:
    """Retry-After del rifiuto per budget: il contatore si azzera al cambio di giorno UTC."""
    now = datetime.now(timezone.utc)
    return max(1, int((now.replace(hour=0, minute=0, second=0, microsecond=0)
                       + timedelta(days=1) - now).total_seconds()))


def _budget_fallback(provider: str, model: str, settings: LLMSettings) -> tuple[str, str]:
    """Devia (provider, model) sul `fallback_provider` quando il provider risolto è
    un provider cloud (anthropic, openai) e la spesa del giorno ha raggiunto `budget.daily_usd`. Restituisce la
    coppia originale in ogni altro caso: blocco budget assente, soglia non raggiunta,
    fallback senza un modello in `models` (degradare su un provider non configurato
    trasformerebbe un problema di costo in un fallimento di generazione)."""
    if provider not in KEY_PROVIDERS:
        return provider, model
    try:
        budget = settings.budget
        if budget is None or budget.daily_usd is None:
            return provider, model
        threshold = float(budget.daily_usd)
        spent = spend_today_usd()
        if spent < threshold:
            return provider, model
        fallback = budget.fallback_provider or "ollama"
        fallback_model = (settings.models or {}).get(fallback)
        if not fallback_model:
            logger.warning(
                "Budget Claude giornaliero raggiunto (spesa %.4f USD >= soglia %.4f USD) ma "
                "il provider di fallback '%s' non ha un modello in llm_settings.models: "
                "resto su anthropic/%s.", spent, threshold, fallback, model)
            return provider, model
        logger.warning(
            "Budget Claude giornaliero raggiunto (spesa %.4f USD >= soglia %.4f USD): "
            "instrado su %s/%s invece di anthropic/%s.",
            spent, threshold, fallback, fallback_model, model)
        return fallback, fallback_model
    except Exception:
        logger.warning("Budget guard non applicabile: resto sul provider risolto.", exc_info=True)
        return provider, model


def resolve(purpose: str) -> tuple[str, str]:
    """Risolve (provider, model) per lo scopo dato: override da llm_settings.purposes
    se presente, altrimenti active_provider + models[provider]. Se il risultato è
    anthropic e il budget giornaliero è esaurito, la coppia viene deviata sul provider
    di fallback (vedi _budget_fallback): senza il blocco `budget` nulla cambia."""
    if purpose not in PURPOSES:
        raise LLMError(f"Scopo LLM sconosciuto: '{purpose}' (attesi: {', '.join(PURPOSES)})")
    settings = _llm_settings()
    override = (settings.purposes or {}).get(purpose) or {}
    provider = override.get("provider") or settings.active_provider
    model = override.get("model") or (settings.models or {}).get(provider)
    if not model:
        raise LLMError(f"Nessun modello configurato per il provider '{provider}' (llm_settings.models).")
    return _budget_fallback(provider, model, settings)


# ---------------------------------------------------------------------------
# Provider: ollama
# ---------------------------------------------------------------------------

def _extract_ollama_text(payload: dict) -> str:
    """Testo generato da Ollama, o LLMError se il campo 'response' manca o è vuoto.
    Ollama può rispondere 200 senza aver generato nulla (bug noto di qwen3.5 col
    thinking attivo, vedi rag_config.yaml: 'un canvas vuoto è un fallimento
    silenzioso'): una stringa vuota o assente non deve mai essere trattata come
    contenuto valido dai chiamanti (finiva persistita come se fosse la generazione)."""
    text = payload.get("response")
    if not text or not str(text).strip():
        raise LLMError("[ERRORE OLLAMA]: risposta vuota o priva del campo 'response' (generazione fallita).")
    return text


def unload_ollama_models(timeout: float = 30.0) -> list[str]:
    """Scarica dalla VRAM i modelli che Ollama tiene caricati (keep_alive 0) e ne restituisce
    i nomi. Serve al full rebuild: con OLLAMA_KEEP_ALIVE=-1 l'LLM non lascia mai la GPU e
    l'embedding del job ripiegava sempre su CPU (2026-10-29: 431 MB liberi contro 3072, build
    da ~2 a ~30 min). Il modello si ricarica da solo alla prossima generazione. Best-effort:
    Ollama assente o in errore non fa fallire il job, si resta sulla CPU come prima."""
    unloaded: list[str] = []
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL.rstrip('/')}/api/ps", timeout=timeout) as response:
            names = [m["name"] for m in json.loads(response.read().decode()).get("models") or []]
        for name in names:
            req = urllib.request.Request(
                OLLAMA_GENERATE_URL, data=json.dumps({"model": name, "keep_alive": 0}).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                response.read()
            unloaded.append(name)
    except Exception:
        logger.warning("Impossibile scaricare i modelli di Ollama prima del rebuild.", exc_info=True)
    return unloaded


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
    return _extract_ollama_text(result)


async def _ollama_agenerate(model: str, prompt: str, timeout: float) -> str:
    data = _ollama_payload(model, prompt)
    try:
        async with httpx2.AsyncClient(timeout=timeout) as client:
            response = await client.post(OLLAMA_GENERATE_URL, json=data)
        if response.status_code == 404:
            raise LLMError(f"[ERRORE OLLAMA]: Il modello '{model}' non è stato trovato. Esegui 'ollama pull {model}'.")
        response.raise_for_status()
        return _extract_ollama_text(response.json())
    except LLMError:
        raise
    except httpx2.ConnectError as e:
        raise LLMError("[ERRORE DI CONNESSIONE]: Impossibile raggiungere Ollama. Assicurati che l'applicazione Ollama sia avviata.") from e
    except httpx2.TimeoutException as e:
        raise LLMError("[ERRORE DI TIMEOUT]: Ollama sta impiegando troppo tempo a rispondere.") from e
    except Exception as e:
        raise LLMError(f"[ERRORE GENERICO OLLAMA]: {e}") from e


async def _ollama_astream(model: str, prompt: str, timeout: float):
    """Legge lo stream NDJSON nativo di Ollama e chiude la connessione su cancellazione."""
    saw_nonwhitespace = False
    done = False
    try:
        async with httpx2.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", OLLAMA_GENERATE_URL, json=_ollama_payload(model, prompt, stream=True),
            ) as response:
                if response.status_code == 404:
                    raise LLMError(
                        f"[ERRORE OLLAMA]: Il modello '{model}' non è stato trovato. "
                        f"Esegui 'ollama pull {model}'.")
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except (json.JSONDecodeError, TypeError) as exc:
                        raise LLMError("[ERRORE GENERICO OLLAMA]: evento stream non JSON.") from exc
                    if event.get("error"):
                        raise LLMError(f"[ERRORE GENERICO OLLAMA]: {event['error']}")
                    text = event.get("response", "")
                    if not isinstance(text, str):
                        raise LLMError("[ERRORE GENERICO OLLAMA]: campo response non testuale.")
                    if text:
                        saw_nonwhitespace = saw_nonwhitespace or bool(text.strip())
                        yield text
                    if event.get("done") is True:
                        done = True
                        break
        if not done:
            raise LLMError("[ERRORE DI CONNESSIONE]: stream Ollama terminato senza evento done.")
        if not saw_nonwhitespace:
            raise LLMError("[ERRORE OLLAMA]: risposta vuota o priva del campo 'response' (generazione fallita).")
    except LLMError:
        raise
    except httpx2.ConnectError as exc:
        raise LLMError("[ERRORE DI CONNESSIONE]: Impossibile raggiungere Ollama. Assicurati che l'applicazione Ollama sia avviata.") from exc
    except httpx2.TimeoutException as exc:
        raise LLMError("[ERRORE DI TIMEOUT]: Ollama sta impiegando troppo tempo a rispondere.") from exc
    except Exception as exc:
        raise LLMError(f"[ERRORE GENERICO OLLAMA]: {exc}") from exc


# ---------------------------------------------------------------------------
# Provider: anthropic (Claude API — SDK ufficiale, API key da ANTHROPIC_API_KEY o
# dal menu Impostazioni: core.llm_settings_store.api_key)
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


def _anthropic_pricing(model: str) -> tuple[float, float] | None:
    """Prezzi per-modello (USD per milione di token) da rag_config.yaml
    (llm_settings.pricing: {model: {input_per_mtok, output_per_mtok}}). None se la
    sezione o il modello mancano, o se i valori sono malformati: il logging dei token
    resta comunque, semplicemente senza costo stimato (mai un'eccezione da qui)."""
    try:
        pricing = (config.get("llm_settings") or {}).get("pricing") or {}
        entry = pricing.get(model) or {}
        return float(entry["input_per_mtok"]), float(entry["output_per_mtok"])
    except (TypeError, KeyError, ValueError):
        return None


def _cloud_key_kwargs(provider: str) -> dict:
    """La chiave delle Impostazioni, se c'è; altrimenti nessun argomento e l'SDK legge
    la variabile d'ambiente come ha sempre fatto."""
    key = api_key(provider)
    return {"api_key": key} if key else {}


def _log_anthropic_usage(model: str, message) -> None:
    """Logga a INFO la spesa della chiamata Anthropic: token di input/output e, se
    llm_settings.pricing configura un prezzo per questo modello, il costo stimato in
    USD. Stesso stile della riga M3 di observability in api/routes_retrieval.py
    (ask_rag): chiavi=valore ordinate, argomenti % del logger. Non deve mai far
    fallire la generazione: qualunque errore nel calcolo/logging viene inghiottito.

    Lo stesso costo stimato alimenta il contatore giornaliero del budget guard
    (_record_spend): per le chiamate dirette è l'unico punto in cui la spesa Claude
    viene contabilizzata, quindi solo le chiamate RIUSCITE e con un prezzo configurato
    incidono sul tetto. L'altra fonte è il costo di fine run dell'agente Claude
    (agent_bridge), riportato direttamente dall'SDK senza bisogno di `pricing`."""
    usage = getattr(message, "usage", None)
    if usage is not None:
        _log_usage("anthropic", model, getattr(usage, "input_tokens", None),
                   getattr(usage, "output_tokens", None))


def _log_usage(provider: str, model: str, input_tokens, output_tokens) -> None:
    """Riga di spesa comune ai provider cloud, e contatore del budget giornaliero. Non
    deve mai far fallire la generazione: ogni errore di calcolo/logging è inghiottito."""
    try:
        pricing = _anthropic_pricing(model)
        if pricing is None:
            logger.info(
                "llm_usage provider=%s model=%s input_tokens=%s output_tokens=%s",
                provider, model, input_tokens, output_tokens,
            )
            return
        input_per_mtok, output_per_mtok = pricing
        cost_usd = round(
            (input_tokens * input_per_mtok + output_tokens * output_per_mtok) / 1_000_000, 6,
        )
        logger.info(
            "llm_usage provider=%s model=%s input_tokens=%s output_tokens=%s cost_usd=%s",
            provider, model, input_tokens, output_tokens, cost_usd,
        )
        _record_spend(cost_usd)
    except Exception:
        logger.warning("Impossibile loggare la spesa di %s (usage/pricing malformati).", provider, exc_info=True)


def _anthropic_generate(model: str, prompt: str, timeout: float) -> str:
    anthropic = _anthropic_module()
    try:
        client = anthropic.Anthropic(timeout=timeout, **_cloud_key_kwargs("anthropic"))
        message = client.messages.create(
            model=model,
            max_tokens=ANTHROPIC_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        _log_anthropic_usage(model, message)
        return _anthropic_text(message)
    except anthropic.AuthenticationError as e:
        raise LLMError("[ERRORE ANTHROPIC]: API key mancante o non valida. Inseriscila in Impostazioni → Modelli LLM o imposta ANTHROPIC_API_KEY.") from e
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
        client = anthropic.AsyncAnthropic(timeout=timeout, **_cloud_key_kwargs("anthropic"))
        message = await client.messages.create(
            model=model,
            max_tokens=ANTHROPIC_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        _log_anthropic_usage(model, message)
        return _anthropic_text(message)
    except anthropic.AuthenticationError as e:
        raise LLMError("[ERRORE ANTHROPIC]: API key mancante o non valida. Inseriscila in Impostazioni → Modelli LLM o imposta ANTHROPIC_API_KEY.") from e
    except anthropic.APITimeoutError as e:
        raise LLMError("[ERRORE DI TIMEOUT]: l'API Anthropic sta impiegando troppo tempo a rispondere.") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("[ERRORE DI CONNESSIONE]: impossibile raggiungere l'API Anthropic.") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"[ERRORE ANTHROPIC {e.status_code}]: {e.message}") from e
    except Exception as e:
        raise LLMError(f"[ERRORE GENERICO ANTHROPIC]: {e}") from e


# ---------------------------------------------------------------------------
# Provider: openai (qualunque endpoint compatibile con /chat/completions: OpenAI, Mistral,
# OpenRouter, Groq, ...; base URL e chiave dal menu Impostazioni o da OPENAI_API_KEY).
# shortcut: un solo endpoint OpenAI-compatibile alla volta; per usarne due insieme
# servirebbero provider con nome (openai:mistral, ...) in VALID_LLM_PROVIDERS.
# ---------------------------------------------------------------------------

_OPENAI_KEY_ERROR = ("[ERRORE OPENAI]: API key mancante o non valida. Inseriscila in "
                     "Impostazioni → Modelli LLM o imposta OPENAI_API_KEY.")


def _openai_request(model: str, prompt: str) -> tuple[str, dict, dict]:
    key = api_key("openai")
    if not key:
        raise LLMError(_OPENAI_KEY_ERROR)
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    return f"{openai_base_url()}/chat/completions", {"Authorization": f"Bearer {key}"}, payload


def _openai_text(model: str, response) -> str:
    if response.status_code in (401, 403):
        raise LLMError(_OPENAI_KEY_ERROR)
    if response.status_code != 200:
        raise LLMError(f"[ERRORE OPENAI {response.status_code}]: {response.text[:300]}")
    try:
        data = response.json()
        text = data["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise LLMError(f"[ERRORE GENERICO OPENAI]: risposta inattesa ({e}).") from e
    usage = data.get("usage") or {}
    _log_usage("openai", model, usage.get("prompt_tokens"), usage.get("completion_tokens"))
    return text


def _openai_generate(model: str, prompt: str, timeout: float) -> str:
    url, headers, payload = _openai_request(model, prompt)
    try:
        with httpx2.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.post(url, headers=headers, json=payload)
    except httpx2.TimeoutException as e:
        raise LLMError("[ERRORE DI TIMEOUT]: l'endpoint OpenAI-compatibile sta impiegando troppo tempo a rispondere.") from e
    except httpx2.HTTPError as e:
        raise LLMError("[ERRORE DI CONNESSIONE]: impossibile raggiungere l'endpoint OpenAI-compatibile.") from e
    return _openai_text(model, response)


async def _openai_agenerate(model: str, prompt: str, timeout: float) -> str:
    url, headers, payload = _openai_request(model, prompt)
    try:
        async with httpx2.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx2.TimeoutException as e:
        raise LLMError("[ERRORE DI TIMEOUT]: l'endpoint OpenAI-compatibile sta impiegando troppo tempo a rispondere.") from e
    except httpx2.HTTPError as e:
        raise LLMError("[ERRORE DI CONNESSIONE]: impossibile raggiungere l'endpoint OpenAI-compatibile.") from e
    return _openai_text(model, response)


# ---------------------------------------------------------------------------
# Provider: claude_code (Claude via Claude Code / Agent SDK con il login dell'abbonamento,
# menu Impostazioni 2026-10-30). Nessuna API key: consuma i limiti del piano Claude, gli
# stessi di claude.ai e di Claude Code. Una sola chiamata, nessuno strumento, nessuna
# impostazione utente/progetto. Attenzione: se ANTHROPIC_API_KEY è nell'ambiente la CLI
# usa quella e non l'abbonamento. Uso personale: per offrire vibecraft ad altri i termini
# dell'Agent SDK chiedono l'API key.
# ---------------------------------------------------------------------------

def claude_cli_path() -> str | None:
    """CLI di Claude Code da passare all'SDK. Su Windows l'SDK rifiuta lo shim .cmd di npm,
    che può però contenere il binario nativo; None = quella inclusa nell'SDK."""
    cli = shutil.which("claude")
    if sys.platform == "win32" and cli and Path(cli).suffix.lower() in (".cmd", ".bat"):
        native = Path(cli).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        return str(native) if native.is_file() else None
    return None


async def _claude_code_query(model: str, prompt: str) -> str:
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query
        from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock
    except ImportError as e:
        raise LLMError("[ERRORE CLAUDE CODE]: pacchetto 'claude-agent-sdk' non installato.") from e
    options = {"setting_sources": [], "tools": [], "allowed_tools": [], "permission_mode": "dontAsk",
               "model": model, "strict_mcp_config": True, "max_turns": 1}
    if cli := claude_cli_path():
        options["cli_path"] = cli
    parts: list[str] = []
    result = None
    async for message in query(prompt=prompt, options=ClaudeAgentOptions(**options)):
        if isinstance(message, AssistantMessage):
            parts.extend(block.text for block in message.content if isinstance(block, TextBlock))
        elif isinstance(message, ResultMessage):
            result = message
    if result is not None and result.is_error:
        raise LLMError(f"[ERRORE CLAUDE CODE]: {(result.result or result.subtype)[:300]}")
    return result.result if result is not None and result.result else "".join(parts)


def _claude_code_generate(model: str, prompt: str, timeout: float) -> str:
    """Sempre su un event loop proprio: quello di uvicorn su Windows può non saper avviare
    sottoprocessi, e la CLI è un sottoprocesso (stesso motivo del loop dedicato di agent_bridge)."""
    async def run():
        return await asyncio.wait_for(_claude_code_query(model, prompt), timeout)
    try:
        return asyncio.run(run())
    except LLMError:
        raise
    except TimeoutError as e:
        raise LLMError("[ERRORE DI TIMEOUT]: Claude Code sta impiegando troppo tempo a rispondere.") from e
    except Exception as e:
        raise LLMError(f"[ERRORE CLAUDE CODE]: {type(e).__name__}: {str(e)[:300]}") from e


async def _claude_code_agenerate(model: str, prompt: str, timeout: float) -> str:
    return await asyncio.to_thread(_claude_code_generate, model, prompt, timeout)


# ---------------------------------------------------------------------------
# Registry e API pubblica
# ---------------------------------------------------------------------------

# provider -> (fn sincrona, fn async). Le fn hanno firma (model, prompt, timeout) -> str.
_PROVIDERS: dict[str, tuple] = {
    "ollama": (_ollama_generate, _ollama_agenerate),
    "anthropic": (_anthropic_generate, _anthropic_agenerate),
    "openai": (_openai_generate, _openai_agenerate),
    "claude_code": (_claude_code_generate, _claude_code_agenerate),
}
_STREAM_PROVIDERS: dict[str, object] = {"ollama": _ollama_astream}

# Controllo di sincronizzazione al modulo-load: i provider registrati qui devono
# corrispondere esattamente a VALID_LLM_PROVIDERS in config.py. Se divergono,
# la validazione config è compromessa.
_check_sync = set(_PROVIDERS)
if _check_sync != VALID_LLM_PROVIDERS:
    raise RuntimeError(
        f"Errore interno: provider registrati in core/llm.py {_check_sync} non concordano con "
        f"VALID_LLM_PROVIDERS in core/config.py {VALID_LLM_PROVIDERS}. "
        f"Sincronizzali prima di eseguire il server."
    )


def register_provider(name: str, sync_fn, async_fn=None) -> None:
    """Registra (o sostituisce) un provider — pensato per i test, che iniettano un
    fake senza HTTP. `async_fn` opzionale: se assente, la variante async avvolge la
    sincrona (le fn fake sono istantanee)."""
    if async_fn is None:
        async def async_fn(model, prompt, timeout, _sync=sync_fn):
            return _sync(model, prompt, timeout)
    _PROVIDERS[name] = (sync_fn, async_fn)
    _STREAM_PROVIDERS.pop(name, None)


def register_streaming_provider(name: str, async_stream_fn) -> None:
    """Registra lo stream nativo di un provider già presente nel registry storico."""
    if name not in _PROVIDERS:
        raise LLMError(f"Provider LLM non supportato: '{name}'")
    _STREAM_PROVIDERS[name] = async_stream_fn


def resolve_stream(purpose: str) -> tuple[str, str, bool]:
    """Risolve una volta provider, modello e disponibilità dello streaming nativo."""
    provider, model = resolve(purpose)
    return provider, model, provider in _STREAM_PROVIDERS


def streaming_native(purpose: str) -> bool:
    return resolve_stream(purpose)[2]


def _provider_fns(provider: str) -> tuple:
    try:
        return _PROVIDERS[provider]
    except KeyError:
        raise LLMError(f"Provider LLM non supportato: '{provider}'") from None


# Frammenti di messaggio che identificano un fallimento TRANSITORIO (hiccup di rete/
# risposta vuota di qwen3.5): questi soli vengono ritentati. Qualsiasi altro LLMError
# (404 modello, provider/scopo sconosciuto, auth) è un errore di configurazione che
# ritentare non risolverebbe: si rilancia subito.
_TRANSIENT_MARKERS = ("[ERRORE DI TIMEOUT]", "[ERRORE DI CONNESSIONE]", "risposta vuota")


def _is_transient(err: LLMError) -> bool:
    message = str(err)
    return any(marker in message for marker in _TRANSIENT_MARKERS)


def generate(
    prompt: str, *, purpose: str, timeout: float = OLLAMA_TIMEOUT_SECONDS, max_attempts: int = 3,
) -> str:
    """Genera testo in modo SINCRONO con il provider/modello risolti per `purpose`.
    Solleva LLMError con messaggio leggibile su qualsiasi errore.

    Ritenta con backoff esponenziale (min(2**tentativo, 10)s) SOLO i fallimenti
    transitori (risposta vuota, timeout, connessione): il fallimento più frequente
    di Ollama, prima mai ritentato, faceva fallire canvas/propose per un hiccup.
    `max_attempts=1` disattiva il retry. Ogni altro LLMError (es. modello non
    trovato) rilancia immediatamente."""
    provider, model = resolve(purpose)
    sync_fn, _ = _provider_fns(provider)
    attempt = 1
    while True:
        try:
            return sync_fn(model, prompt, timeout)
        except LLMError as e:
            if attempt >= max_attempts or not _is_transient(e):
                raise
            logger.warning("Tentativo %d/%d fallito per '%s' (%s): %s", attempt, max_attempts, purpose, provider, e)
            time.sleep(min(2 ** attempt, 10))
            attempt += 1


async def agenerate(
    prompt: str, *, purpose: str, timeout: float = OLLAMA_TIMEOUT_SECONDS, max_attempts: int = 3,
) -> str:
    """Come `generate` ma ASINCRONA (per i route handler FastAPI: non blocca l'event
    loop durante generazioni che su CPU durano minuti). Stessa politica di retry."""
    provider, model = resolve(purpose)
    _, async_fn = _provider_fns(provider)
    attempt = 1
    while True:
        try:
            return await async_fn(model, prompt, timeout)
        except LLMError as e:
            if attempt >= max_attempts or not _is_transient(e):
                raise
            logger.warning("Tentativo %d/%d fallito per '%s' (%s): %s", attempt, max_attempts, purpose, provider, e)
            await asyncio.sleep(min(2 ** attempt, 10))
            attempt += 1


async def astream(
    prompt: str, *, purpose: str, timeout: float = OLLAMA_TIMEOUT_SECONDS, max_attempts: int = 3,
    resolved: tuple[str, str, bool] | None = None,
):
    """Emette testo incrementale; ritenta errori transitori solo prima del primo delta."""
    provider, model, native = resolved or resolve_stream(purpose)
    _, async_fn = _provider_fns(provider)
    attempt = 1
    while True:
        emitted = False
        try:
            if native:
                stream = _STREAM_PROVIDERS[provider](model, prompt, timeout)
                try:
                    async for part in stream:
                        if part:
                            emitted = True
                            yield part
                finally:
                    close = getattr(stream, "aclose", None)
                    if close is not None:
                        await close()
            else:
                part = await async_fn(model, prompt, timeout)
                if part:
                    emitted = True
                    yield part
            return
        except LLMError as exc:
            if emitted or attempt >= max_attempts or not _is_transient(exc):
                raise
            logger.warning("Tentativo stream %d/%d fallito per '%s' (%s): %s",
                           attempt, max_attempts, purpose, provider, exc)
            await asyncio.sleep(min(2 ** attempt, 10))
            attempt += 1

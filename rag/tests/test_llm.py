"""Test del layer LLM unificato (core/llm.py): risoluzione purpose -> provider/modello
(con e senza override da rag_config), provider fake iniettato end-to-end su uno step
pipeline (niente HTTP) e propagazione tollerante degli errori nei chiamanti
(check_drift mette l'errore nel report, l'archive salta la review con warning)."""
import asyncio

import pytest

from core import llm, pipeline


@pytest.fixture
def fake_settings(monkeypatch):
    """llm_settings controllati: provider fake attivo, nessun purposes override."""
    settings = {
        "active_provider": "fake",
        "models": {"fake": "fake-model", "anthropic": "claude-sonnet-5"},
    }
    monkeypatch.setitem(llm.config, "llm_settings", settings)
    return settings


def _register_echo_provider():
    calls = []

    def echo(model, prompt, timeout):
        calls.append((model, prompt))
        return f"RISPOSTA[{model}]"

    llm.register_provider("fake", echo)
    return calls


# ---------------------------------------------------------------------------
# Risoluzione purpose -> provider/modello
# ---------------------------------------------------------------------------

def test_resolve_fallback_su_active_provider(fake_settings):
    assert llm.resolve("drift") == ("fake", "fake-model")


def test_resolve_con_override_purposes(fake_settings):
    fake_settings["purposes"] = {
        "canvas": {"provider": "anthropic", "model": "claude-opus-4-8"},
        "review": {"provider": "anthropic"},  # model omesso -> models.anthropic
    }
    assert llm.resolve("canvas") == ("anthropic", "claude-opus-4-8")
    assert llm.resolve("review") == ("anthropic", "claude-sonnet-5")
    assert llm.resolve("drift") == ("fake", "fake-model")  # nessun override


def test_resolve_purpose_sconosciuto(fake_settings):
    with pytest.raises(llm.LLMError):
        llm.resolve("traduzione")


def test_resolve_senza_modello_per_il_provider(monkeypatch):
    """models vuoto (o senza voce per il provider attivo) -> LLMError storico, non un
    errore di validazione pydantic: il messaggio è verificato per intero."""
    monkeypatch.setitem(llm.config, "llm_settings", {"active_provider": "fake", "models": {}})
    with pytest.raises(llm.LLMError) as exc:
        llm.resolve("drift")
    assert str(exc.value) == "Nessun modello configurato per il provider 'fake' (llm_settings.models)."


def test_resolve_accetta_anche_un_blocco_gia_tipato(monkeypatch):
    """resolve() accetta indifferentemente il dict grezzo (caso normale) e un
    LLMSettings già validato messo in config: stessa risoluzione."""
    from core.config import LLMSettings

    settings = LLMSettings(
        active_provider="fake", models={"fake": "fake-model"},
        purposes={"canvas": {"provider": "anthropic", "model": "claude-opus-4-8"}},
    )
    monkeypatch.setitem(llm.config, "llm_settings", settings)
    assert llm.resolve("drift") == ("fake", "fake-model")
    assert llm.resolve("canvas") == ("anthropic", "claude-opus-4-8")


# ---------------------------------------------------------------------------
# Validazione pydantic del blocco llm_settings (task 2.3): un config malformato
# deve fallire al BOOT con un messaggio leggibile, non con una KeyError dentro una
# richiesta.
# ---------------------------------------------------------------------------

def test_llm_settings_valido_carica_i_valori_del_config_reale():
    from core.config import LLM_MODEL, LLM_PROVIDER, LLM_SETTINGS, OLLAMA_NUM_CTX, OLLAMA_THINK

    assert LLM_PROVIDER == LLM_SETTINGS.active_provider
    assert LLM_MODEL == LLM_SETTINGS.models[LLM_PROVIDER]
    assert OLLAMA_THINK == LLM_SETTINGS.ollama_think
    assert OLLAMA_NUM_CTX == (LLM_SETTINGS.ollama_num_ctx or None)


def test_llm_settings_accetta_un_blocco_completo():
    from core.config import validate_llm_settings

    s = validate_llm_settings({
        "active_provider": "ollama",
        "models": {"ollama": "qwen3.5:9b"},
        "purposes": {"canvas": {"model": "qwen3.5:27b"}},
        "ollama_think": False,
        "ollama_num_ctx": 16384,
        "pricing": {"claude-sonnet-5": {"input_per_mtok": 3.0, "output_per_mtok": 15.0}},
        "chiave_futura": "ignorata ma non fatale",
    }, boot=True)
    assert (s.active_provider, s.models["ollama"]) == ("ollama", "qwen3.5:9b")
    assert s.ollama_think is False and s.ollama_num_ctx == 16384
    assert s.pricing["claude-sonnet-5"]["input_per_mtok"] == 3.0


def test_llm_settings_active_provider_mancante_e_errore_chiaro():
    from pydantic import ValidationError

    from core.config import validate_llm_settings

    with pytest.raises(ValidationError) as exc:
        validate_llm_settings({"models": {"ollama": "qwen3.5:9b"}}, boot=True)
    assert "active_provider" in str(exc.value)


def test_llm_settings_models_vuoto_e_errore_chiaro_al_boot():
    from pydantic import ValidationError

    from core.config import validate_llm_settings

    with pytest.raises(ValidationError) as exc:
        validate_llm_settings({"active_provider": "ollama", "models": {}}, boot=True)
    assert "models" in str(exc.value)


def test_llm_settings_provider_attivo_senza_modello_e_errore_chiaro_al_boot():
    from pydantic import ValidationError

    from core.config import validate_llm_settings

    with pytest.raises(ValidationError) as exc:
        validate_llm_settings(
            {"active_provider": "ollama", "models": {"anthropic": "claude-sonnet-5"}}, boot=True)
    assert "active_provider" in str(exc.value)


def test_llm_settings_tipi_sbagliati_falliscono():
    from pydantic import ValidationError

    from core.config import validate_llm_settings

    with pytest.raises(ValidationError):
        validate_llm_settings({"active_provider": "ollama", "models": "qwen3.5:9b"}, boot=True)
    with pytest.raises(ValidationError):
        validate_llm_settings(
            {"active_provider": "ollama", "models": {"ollama": "m"}, "ollama_num_ctx": "molto"},
            boot=True)


# ---------------------------------------------------------------------------
# Contratto dell'asimmetria boot/runtime. La validazione di llm_settings è
# volutamente a DUE livelli: severa all'avvio (fail-fast su una configurazione
# incoerente) e permissiva a runtime (solo tipi), perché i casi di configurazione
# incompleta devono continuare a produrre gli LLMError storici di resolve() invece
# di una ValidationError. Questi quattro test lockano entrambi i lati: senza, un
# "irrigidiamo anche il runtime" apparentemente innocuo cambierebbe i messaggi
# d'errore visti dai chiamanti (che li mostrano all'utente) senza far fallire nulla.
# ---------------------------------------------------------------------------

def test_contratto_boot_models_vuoto_e_errore_di_validazione():
    # boot=True è severo: all'avvio una configurazione incoerente deve fermare il
    # processo subito, non lasciar partire un server che fallirà a ogni richiesta.
    from pydantic import ValidationError

    from core.config import validate_llm_settings

    with pytest.raises(ValidationError):
        validate_llm_settings({"active_provider": "fake", "models": {}}, boot=True)


def test_contratto_runtime_models_vuoto_resta_llmerror_storico(monkeypatch):
    # A runtime lo STESSO input non deve dare ValidationError: la validazione è di
    # soli tipi e il caso "nessun modello" resta a resolve(), che ne produce il
    # messaggio storico — verificato alla lettera perché arriva fino all'utente.
    from core.config import validate_llm_settings

    raw = {"active_provider": "fake", "models": {}}
    assert validate_llm_settings(raw).models == {}  # senza boot NON solleva
    monkeypatch.setitem(llm.config, "llm_settings", raw)
    with pytest.raises(llm.LLMError) as exc:
        llm.resolve("drift")
    assert str(exc.value) == "Nessun modello configurato per il provider 'fake' (llm_settings.models)."


def test_contratto_runtime_active_provider_mancante_e_llmerror_non_keyerror(monkeypatch):
    # Cambio di comportamento introdotto dalla tipizzazione: prima era una KeyError
    # grezza che risaliva dentro una richiesta, ora è un LLMError leggibile come
    # ogni altro errore di configurazione. È voluto, quindi va bloccato qui.
    monkeypatch.setitem(llm.config, "llm_settings", {"models": {"fake": "fake-model"}})
    with pytest.raises(llm.LLMError) as exc:
        llm.resolve("drift")
    assert not isinstance(exc.value, KeyError)
    assert str(exc.value).startswith("Blocco 'llm_settings' non valido in rag_config.yaml:")
    assert "active_provider" in str(exc.value)


def test_contratto_runtime_blocco_malformato_e_llmerror_leggibile(monkeypatch):
    # Struttura completamente errata (qui una stringa al posto del blocco): la
    # validazione di soli tipi la intercetta comunque e la riavvolge in LLMError,
    # citando il file da correggere invece di esporre la ValidationError grezza.
    monkeypatch.setitem(llm.config, "llm_settings", "ollama")
    with pytest.raises(llm.LLMError) as exc:
        llm.resolve("drift")
    assert str(exc.value).startswith("Blocco 'llm_settings' non valido in rag_config.yaml:")


def test_provider_non_supportato(monkeypatch):
    monkeypatch.setitem(llm.config, "llm_settings", {
        "active_provider": "inesistente", "models": {"inesistente": "x"},
    })
    with pytest.raises(llm.LLMError, match="non supportato"):
        llm.generate("ciao", purpose="drift")


# ---------------------------------------------------------------------------
# Validazione provider registrati al boot (punto #12)
# ---------------------------------------------------------------------------

def test_valid_llm_providers_sincronizzati_con_registry():
    """VALID_LLM_PROVIDERS in config.py e _PROVIDERS in llm.py devono corrispondere
    esattamente (la discrepanza è un errore di sincronizzazione)."""
    from core.config import VALID_LLM_PROVIDERS

    assert VALID_LLM_PROVIDERS == {"ollama", "anthropic"}
    assert VALID_LLM_PROVIDERS <= set(llm._PROVIDERS)


def test_llm_settings_active_provider_non_registrato_errore_al_boot():
    """active_provider non in VALID_LLM_PROVIDERS -> ValidationError al boot con
    elenco dei provider ammessi."""
    from pydantic import ValidationError

    from core.config import validate_llm_settings

    with pytest.raises(ValidationError) as exc:
        validate_llm_settings(
            {"active_provider": "openai", "models": {"openai": "gpt-4o"}}, boot=True)
    err_msg = str(exc.value)
    assert "active_provider" in err_msg
    assert "openai" in err_msg
    assert "non è registrato" in err_msg
    # Verifica che il messaggio elenchi i provider ammessi in ordine alfabetico
    assert "Provider ammessi: anthropic, ollama" in err_msg


def test_llm_settings_purpose_provider_non_registrato_errore_al_boot():
    """Provider di un purpose non in VALID_LLM_PROVIDERS -> ValidationError al boot."""
    from pydantic import ValidationError

    from core.config import validate_llm_settings

    with pytest.raises(ValidationError) as exc:
        validate_llm_settings(
            {
                "active_provider": "ollama",
                "models": {"ollama": "qwen3.5:9b"},
                "purposes": {
                    "canvas": {"provider": "openai", "model": "gpt-4o"},
                },
            },
            boot=True)
    err_msg = str(exc.value)
    assert "openai" in err_msg
    assert "canvas" in err_msg
    assert "non è registrato" in err_msg


def test_llm_settings_budget_fallback_provider_non_registrato_errore_al_boot():
    """budget.fallback_provider non in VALID_LLM_PROVIDERS -> ValidationError al boot."""
    from pydantic import ValidationError

    from core.config import validate_llm_settings

    with pytest.raises(ValidationError) as exc:
        validate_llm_settings(
            {
                "active_provider": "anthropic",
                "models": {"anthropic": "claude-sonnet-5"},
                "budget": {"daily_usd": 5.0, "fallback_provider": "groq"},
            },
            boot=True)
    err_msg = str(exc.value)
    assert "groq" in err_msg
    assert "fallback_provider" in err_msg
    assert "non è registrato" in err_msg


def test_llm_settings_provider_valido_non_solleva_errore():
    """Config con provider validi (ollama, anthropic) e budget fallback valido passa."""
    from core.config import validate_llm_settings

    s = validate_llm_settings(
        {
            "active_provider": "ollama",
            "models": {"ollama": "qwen3.5:9b", "anthropic": "claude-sonnet-5"},
            "purposes": {
                "canvas": {"provider": "anthropic"},
                "drift": {"provider": "ollama"},
            },
            "budget": {"daily_usd": 5.0, "fallback_provider": "ollama"},
        },
        boot=True)
    assert s.active_provider == "ollama"
    assert s.purposes["canvas"]["provider"] == "anthropic"
    assert s.budget.fallback_provider == "ollama"


# ---------------------------------------------------------------------------
# Provider fake end-to-end (sync + async, step pipeline senza HTTP)
# ---------------------------------------------------------------------------

def test_generate_con_provider_fake(fake_settings):
    calls = _register_echo_provider()
    out = llm.generate("prompt di prova", purpose="drift")
    assert out == "RISPOSTA[fake-model]"
    assert calls == [("fake-model", "prompt di prova")]


def test_pipeline_step_end_to_end_con_fake(fake_settings):
    """generate_tolerant (usato da explore/canvas/propose/validate) col provider fake."""
    _register_echo_provider()
    out = asyncio.run(pipeline.generate_tolerant("genera il canvas", purpose="canvas"))
    assert out == "RISPOSTA[fake-model]"
    # Shim deprecato: stesso percorso.
    assert asyncio.run(pipeline.call_ollama_generate("x")) == "RISPOSTA[fake-model]"


# ---------------------------------------------------------------------------
# Errori di rete: comportamento tollerante dei chiamanti
# ---------------------------------------------------------------------------

def _register_broken_provider():
    def broken(model, prompt, timeout):
        raise llm.LLMError("[ERRORE DI CONNESSIONE]: Impossibile raggiungere Ollama. Assicurati che l'applicazione Ollama sia avviata.")
    llm.register_provider("fake", broken)


def test_generate_tolerant_restituisce_il_messaggio_di_errore(fake_settings):
    _register_broken_provider()
    out = asyncio.run(pipeline.generate_tolerant("x", purpose="validate"))
    assert out.startswith("[ERRORE DI CONNESSIONE]")


def test_check_drift_mette_errore_nel_report(fake_settings, monkeypatch, tmp_path):
    from core import indexing
    _register_broken_provider()
    feature = tmp_path / "changes" / "feat-x"
    feature.mkdir(parents=True)
    (feature / "canvas.md").write_text("## Requirements\ncontratto", encoding="utf-8")
    monkeypatch.setattr(indexing, "CHANGES_DIR", tmp_path / "changes")
    monkeypatch.setattr(indexing, "CODE_DIR", tmp_path / "code")

    report = indexing.check_drift("feat x", emit=lambda _msg: None)
    assert "❌ Errore durante il check drift" in report
    assert "ERRORE DI CONNESSIONE" in report


def test_canvas_review_salta_con_warning_su_errore(fake_settings, tmp_path):
    from core import canvas_review
    _register_broken_provider()
    change = tmp_path / "feat-y"
    change.mkdir()
    (change / "canvas.md").write_text("## Operations\nstep", encoding="utf-8")

    content, warning = canvas_review.generate_canvas_review("feat-y", change, repo_root=tmp_path)
    assert content is None
    assert warning is not None and "LLM non raggiungibile" in warning


def test_errore_ollama_connessione_mappato_su_llmerror(monkeypatch):
    """Il provider ollama sincrono traduce l'errore di rete in LLMError leggibile."""
    import urllib.error
    import urllib.request

    def _fail(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _fail)
    with pytest.raises(llm.LLMError, match="ERRORE DI CONNESSIONE"):
        llm._ollama_generate("qwen2.5:7b", "ciao", timeout=1.0)


# ---------------------------------------------------------------------------
# Ollama può rispondere 200 senza aver generato nulla (bug noto di qwen3.5 col
# thinking attivo: il ragionamento esaurisce la generazione, la risposta esce vuota
# o priva del campo 'response'). Prima del fix questo diventava contenuto valido
# ("Errore nella generazione." o "" scritti in canvas.md/spec.md); ora deve
# sollevare LLMError come qualunque altro errore di generazione.
# ---------------------------------------------------------------------------
def test_extract_ollama_text_raises_on_missing_response_field():
    with pytest.raises(llm.LLMError, match="risposta vuota"):
        llm._extract_ollama_text({"model": "qwen3.5:9b"})  # nessun campo 'response'


def test_extract_ollama_text_raises_on_empty_or_blank_response():
    with pytest.raises(llm.LLMError, match="risposta vuota"):
        llm._extract_ollama_text({"response": ""})
    with pytest.raises(llm.LLMError, match="risposta vuota"):
        llm._extract_ollama_text({"response": "   "})


def test_extract_ollama_text_returns_content_when_present():
    assert llm._extract_ollama_text({"response": "## Requirements\nOK"}) == "## Requirements\nOK"


class _FakeUrlopenResponse:
    """Context manager minimale che imita urllib.request.urlopen(...) as response."""
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def test_ollama_generate_raises_on_missing_response_field(monkeypatch):
    import json
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=None: _FakeUrlopenResponse(json.dumps({"model": "m"}).encode()),
    )
    with pytest.raises(llm.LLMError, match="risposta vuota"):
        llm._ollama_generate("qwen3.5:9b", "ciao", timeout=1.0)


def test_ollama_generate_raises_on_empty_response_field(monkeypatch):
    import json
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=None: _FakeUrlopenResponse(json.dumps({"response": ""}).encode()),
    )
    with pytest.raises(llm.LLMError, match="risposta vuota"):
        llm._ollama_generate("qwen3.5:9b", "ciao", timeout=1.0)


def test_ollama_generate_still_returns_valid_content(monkeypatch):
    import json
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=None: _FakeUrlopenResponse(json.dumps({"response": "canvas ok"}).encode()),
    )
    assert llm._ollama_generate("qwen3.5:9b", "ciao", timeout=1.0) == "canvas ok"


def _make_fake_async_client(payload: dict):
    """httpx2.AsyncClient fake minimale (async context manager + .post()) per testare
    _ollama_agenerate senza rete."""
    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return payload

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None):
            return _FakeResponse()

    return _FakeAsyncClient


def test_ollama_agenerate_raises_on_empty_response(monkeypatch):
    monkeypatch.setattr(llm.httpx2, "AsyncClient", _make_fake_async_client({"response": ""}))
    with pytest.raises(llm.LLMError, match="risposta vuota"):
        asyncio.run(llm._ollama_agenerate("qwen3.5:9b", "ciao", timeout=1.0))


def test_ollama_agenerate_returns_content_when_present(monkeypatch):
    monkeypatch.setattr(llm.httpx2, "AsyncClient", _make_fake_async_client({"response": "spec ok"}))
    assert asyncio.run(llm._ollama_agenerate("qwen3.5:9b", "ciao", timeout=1.0)) == "spec ok"


def test_ollama_payload_include_num_ctx_e_think_solo_se_configurati(monkeypatch):
    # num_ctx e' la difesa contro il default 4096 di Ollama, che tronca dall'alto i prompt
    # di canvas/propose (>4.300 token): senza, il modello non vede l'intervista in cima e
    # la risposta esce mozzata. think:false evita risposte vuote coi modelli thinking.
    monkeypatch.setattr(llm, "OLLAMA_NUM_CTX", 16384)
    monkeypatch.setattr(llm, "OLLAMA_THINK", False)
    monkeypatch.setattr(llm, "OLLAMA_TEMPERATURE", None)
    p = llm._ollama_payload("m", "prompt")
    assert p["options"] == {"num_ctx": 16384}
    assert p["think"] is False
    # Non configurati -> payload storico, per compatibilita' con modelli/versioni che non
    # conoscono questi campi.
    monkeypatch.setattr(llm, "OLLAMA_NUM_CTX", None)
    monkeypatch.setattr(llm, "OLLAMA_THINK", None)
    p2 = llm._ollama_payload("m", "prompt")
    assert p2 == {"model": "m", "prompt": "prompt", "stream": False}


def test_ollama_payload_include_la_temperatura_e_ammette_lo_zero(monkeypatch):
    # La temperatura di default di Ollama (0.8) e' troppo alta per gli step a formato rigido:
    # va inviata esplicitamente. 0.0 e' un valore VALIDO (campionamento greedy) e deve finire
    # nel payload: con un test `if OLLAMA_TEMPERATURE:` sparirebbe in silenzio.
    monkeypatch.setattr(llm, "OLLAMA_NUM_CTX", 16384)
    monkeypatch.setattr(llm, "OLLAMA_THINK", None)
    monkeypatch.setattr(llm, "OLLAMA_TEMPERATURE", 0.1)
    assert llm._ollama_payload("m", "prompt")["options"] == {"num_ctx": 16384, "temperature": 0.1}

    monkeypatch.setattr(llm, "OLLAMA_TEMPERATURE", 0.0)
    assert llm._ollama_payload("m", "prompt")["options"]["temperature"] == 0.0

    # Temperatura sola, senza num_ctx: il blocco options nasce comunque.
    monkeypatch.setattr(llm, "OLLAMA_NUM_CTX", None)
    monkeypatch.setattr(llm, "OLLAMA_TEMPERATURE", 0.1)
    assert llm._ollama_payload("m", "prompt")["options"] == {"temperature": 0.1}


# ---------------------------------------------------------------------------
# Retry con backoff sui fallimenti transitori (task 1.1): il fallimento più
# frequente di Ollama (risposta vuota, timeout, connessione) prima non veniva mai
# ritentato, un hiccup faceva fallire canvas/propose con 502.
# ---------------------------------------------------------------------------

def test_generate_ritenta_su_errore_transitorio_e_poi_riesce(fake_settings, monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    calls = []

    def flaky(model, prompt, timeout):
        calls.append(1)
        if len(calls) < 3:
            raise llm.LLMError("[ERRORE DI CONNESSIONE]: Impossibile raggiungere Ollama.")
        return "RISPOSTA OK"

    llm.register_provider("fake", flaky)
    out = llm.generate("prompt", purpose="drift", max_attempts=3)
    assert out == "RISPOSTA OK"
    assert len(calls) == 3


def test_generate_non_ritenta_su_errore_non_transitorio(fake_settings, monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    calls = []

    def not_found(model, prompt, timeout):
        calls.append(1)
        raise llm.LLMError(f"[ERRORE OLLAMA]: Il modello '{model}' non è stato trovato. Esegui 'ollama pull {model}'.")

    llm.register_provider("fake", not_found)
    with pytest.raises(llm.LLMError, match="non è stato trovato"):
        llm.generate("prompt", purpose="drift", max_attempts=3)
    assert len(calls) == 1


def test_agenerate_ritenta_su_errore_transitorio_e_poi_riesce(fake_settings, monkeypatch):
    async def fake_sleep(_s):
        return None
    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)
    calls = []

    def flaky(model, prompt, timeout):
        calls.append(1)
        if len(calls) < 2:
            raise llm.LLMError("[ERRORE DI TIMEOUT]: Ollama sta impiegando troppo tempo a rispondere.")
        return "RISPOSTA ASYNC OK"

    llm.register_provider("fake", flaky)
    out = asyncio.run(llm.agenerate("prompt", purpose="drift", max_attempts=3))
    assert out == "RISPOSTA ASYNC OK"
    assert len(calls) == 2


def test_agenerate_non_ritenta_su_errore_non_transitorio(fake_settings, monkeypatch):
    async def fake_sleep(_s):
        return None
    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)
    calls = []

    def not_found(model, prompt, timeout):
        calls.append(1)
        raise llm.LLMError(f"[ERRORE OLLAMA]: Il modello '{model}' non è stato trovato. Esegui 'ollama pull {model}'.")

    llm.register_provider("fake", not_found)
    with pytest.raises(llm.LLMError, match="non è stato trovato"):
        asyncio.run(llm.agenerate("prompt", purpose="drift", max_attempts=3))
    assert len(calls) == 1


def test_astream_fallback_emette_la_risposta_completa(fake_settings):
    """Un provider senza protocollo streaming resta utilizzabile e viene dichiarato non nativo."""
    llm.register_provider("fake", lambda model, prompt, timeout: "RISPOSTA COMPLETA")

    async def collect():
        return [part async for part in llm.astream("prompt", purpose="ask")]

    assert llm.streaming_native("ask") is False
    assert asyncio.run(collect()) == ["RISPOSTA COMPLETA"]


def test_astream_non_ritenta_dopo_il_primo_delta(fake_settings, monkeypatch):
    """Un retry dopo testo visibile duplicherebbe la risposta nel client."""
    calls = []

    async def broken_stream(model, prompt, timeout):
        calls.append(1)
        yield "prima parte"
        raise llm.LLMError("[ERRORE DI CONNESSIONE]: stream interrotto")

    llm.register_streaming_provider("fake", broken_stream)

    async def collect():
        parts = []
        with pytest.raises(llm.LLMError, match="stream interrotto"):
            async for part in llm.astream("prompt", purpose="ask", max_attempts=3):
                parts.append(part)
        return parts

    monkeypatch.setattr(llm.asyncio, "sleep", lambda _s: None)
    assert asyncio.run(collect()) == ["prima parte"]
    assert len(calls) == 1


def test_astream_ritenta_prima_del_primo_delta(fake_settings, monkeypatch):
    calls = []

    async def flaky_stream(model, prompt, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise llm.LLMError("[ERRORE DI TIMEOUT]: nessun testo ricevuto")
        yield "ok"

    async def no_sleep(_seconds):
        return None

    llm.register_streaming_provider("fake", flaky_stream)
    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)

    async def collect():
        return [part async for part in llm.astream("prompt", purpose="ask", max_attempts=3)]

    assert asyncio.run(collect()) == ["ok"]
    assert len(calls) == 2


def _make_fake_stream_client(lines, observed):
    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            for line in lines:
                yield line

    class Stream:
        async def __aenter__(self):
            return Response()

        async def __aexit__(self, *exc):
            observed["stream_closed"] = True
            return False

    class Client:
        def __init__(self, *args, **kwargs):
            observed["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            observed["client_closed"] = True
            return False

        def stream(self, method, url, *, json):
            observed.update(method=method, url=url, payload=json)
            return Stream()

    return Client


def test_ollama_astream_emette_delta_ndjson_e_richiede_stream(monkeypatch):
    import json

    observed = {}
    lines = [
        json.dumps({"model": "m", "response": "prima ", "done": False}),
        json.dumps({"model": "m", "response": "parte", "done": False}),
        json.dumps({"model": "m", "response": "", "done": True}),
    ]
    monkeypatch.setattr(llm.httpx2, "AsyncClient", _make_fake_stream_client(lines, observed))

    async def collect():
        return [part async for part in llm._ollama_astream("m", "prompt", timeout=7)]

    assert asyncio.run(collect()) == ["prima ", "parte"]
    assert observed["payload"]["stream"] is True
    assert observed["stream_closed"] is True and observed["client_closed"] is True


def test_ollama_astream_rifiuta_eof_senza_done(monkeypatch):
    import json

    observed = {}
    monkeypatch.setattr(
        llm.httpx2, "AsyncClient",
        _make_fake_stream_client([json.dumps({"response": "parziale", "done": False})], observed),
    )

    async def collect():
        return [part async for part in llm._ollama_astream("m", "prompt", timeout=7)]

    with pytest.raises(llm.LLMError, match="terminato senza evento done"):
        asyncio.run(collect())
    assert observed["stream_closed"] is True and observed["client_closed"] is True


def test_astream_aclose_chiude_subito_il_provider_nativo(fake_settings):
    observed = {"closed": False}

    async def native(*_args):
        try:
            yield "prima"
            yield "seconda"
        finally:
            observed["closed"] = True

    llm.register_provider("fake", lambda *_args: "fallback")
    llm.register_streaming_provider("fake", native)

    async def consume_one():
        stream = llm.astream("prompt", purpose="ask")
        assert await anext(stream) == "prima"
        await stream.aclose()

    asyncio.run(consume_one())
    assert observed["closed"] is True


def test_ollama_astream_rifiuta_response_non_stringa(monkeypatch):
    import json

    observed = {}
    monkeypatch.setattr(
        llm.httpx2, "AsyncClient",
        _make_fake_stream_client([json.dumps({"response": {"bad": True}, "done": True})], observed),
    )

    async def collect():
        return [part async for part in llm._ollama_astream("m", "prompt", timeout=7)]

    with pytest.raises(llm.LLMError, match="campo response non testuale"):
        asyncio.run(collect())


def test_ollama_payload_warna_se_il_prompt_sfiora_la_finestra(monkeypatch, caplog):
    # Il default 4096 di Ollama troncava i prompt SILENZIOSAMENTE (canvas mozzato, intervista
    # mai letta): con num_ctx configurato, un prompt vicino alla finestra deve almeno lasciare
    # una traccia nei log — mai piu' un taglio invisibile. Sotto la soglia di CERTEZZA
    # (>= 100%, vedi il test successivo): qui il rischio esiste ma la generazione puo'
    # ancora riuscire, quindi resta un warning e non un errore.
    import logging
    monkeypatch.setattr(llm, "OLLAMA_NUM_CTX", 1000)
    monkeypatch.setattr(llm, "OLLAMA_THINK", None)
    with caplog.at_level(logging.WARNING, logger="core.llm"):
        llm._ollama_payload("m", "x" * 2700)     # ~900 token stimati = 90% della finestra
    assert any("troncamento" in r.message for r in caplog.records)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="core.llm"):
        llm._ollama_payload("m", "x" * 600)      # ~200 token: nessun warning
    assert not caplog.records


def test_ollama_payload_solleva_se_il_prompt_eccede_certamente_la_finestra(monkeypatch):
    """A1: sotto l'80% e' un rischio (warning), qui e' una certezza — il prompt da solo
    raggiunge num_ctx, quindi Ollama tronca dall'alto per costruzione. Prima di questa
    correzione la richiesta proseguiva comunque e la risposta tornava "success": misurato
    dal vivo, /ask con top_k=20 (il tetto gia' imposto dal server) produce oggi ~104% della
    finestra sul corpus reale — non un caso limite raro."""
    monkeypatch.setattr(llm, "OLLAMA_NUM_CTX", 1000)
    monkeypatch.setattr(llm, "OLLAMA_THINK", None)
    with pytest.raises(llm.LLMError, match="FINESTRA DI CONTESTO SUPERATA"):
        llm._ollama_payload("m", "x" * 3000)     # ~1000 token stimati = 100% della finestra


def test_ollama_payload_non_solleva_appena_sotto_la_soglia_di_certezza(monkeypatch):
    """Confine esatto: appena sotto il 100% resta un warning, non un errore — la stima e'
    approssimativa e non ogni prompt vicino alla finestra tronca davvero."""
    monkeypatch.setattr(llm, "OLLAMA_NUM_CTX", 1000)
    monkeypatch.setattr(llm, "OLLAMA_THINK", None)
    llm._ollama_payload("m", "x" * 2999)         # 999 token stimati = appena sotto 1000


def test_check_drift_esclude_node_modules_e_altre_cartelle_di_build(fake_settings, monkeypatch, tmp_path):
    # rglob("*") senza filtro include node_modules per intero: decine di migliaia di file
    # .js/.ts non scritti dall'agente, che gonfiano il prompt ben oltre num_ctx (misurato:
    # ~53 milioni di token stimati su un solo componente, HTTP 500 da Ollama).
    from core import indexing

    captured = {}

    def _fake_generate(prompt, *, purpose):
        captured["prompt"] = prompt
        return "OK"

    monkeypatch.setattr(indexing.llm, "generate", _fake_generate)

    feature = tmp_path / "changes" / "feat-x"
    feature.mkdir(parents=True)
    (feature / "canvas.md").write_text("## Requirements\ncontratto", encoding="utf-8")
    (feature / "meta.json").write_text('{"dev_type": "frontend"}', encoding="utf-8")
    monkeypatch.setattr(indexing, "CHANGES_DIR", tmp_path / "changes")
    monkeypatch.setattr(indexing, "CODE_DIR", tmp_path / "code")

    code_dir = tmp_path / "code" / "frontend"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "src" / "Form.tsx").write_text("export const Form = () => null;", encoding="utf-8")
    nm = code_dir / "node_modules" / "some-pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("x" * 5000, encoding="utf-8")

    indexing.check_drift("feat x", emit=lambda _msg: None)
    assert "Form.tsx" in captured["prompt"]
    assert "index.js" not in captured["prompt"]
    assert "node_modules" not in captured["prompt"]


def test_check_drift_include_codice_dotnet(fake_settings, monkeypatch, tmp_path):
    # Regressione: la lista estensioni locale escludeva .cs e il drift di una feature
    # backend .NET riportava "Nessun file di codice sorgente trovato".
    from core import indexing

    captured = {}
    monkeypatch.setattr(indexing.llm, "generate", lambda prompt, *, purpose: captured.setdefault("prompt", prompt))

    feature = tmp_path / "changes" / "be1"
    feature.mkdir(parents=True)
    (feature / "canvas.md").write_text("## Requirements\ncontratto", encoding="utf-8")
    (feature / "meta.json").write_text('{"dev_type": "backend"}', encoding="utf-8")
    monkeypatch.setattr(indexing, "CHANGES_DIR", tmp_path / "changes")
    monkeypatch.setattr(indexing, "CODE_DIR", tmp_path / "code")

    src = tmp_path / "code" / "backend" / "src" / "Portal.Api"
    (src / "bin").mkdir(parents=True)
    (src / "Program.cs").write_text("var app = 1;", encoding="utf-8")
    (src / "bin" / "Generated.cs").write_text("// build", encoding="utf-8")

    logs = []
    indexing.check_drift("be1", emit=logs.append)
    assert "Program.cs" in captured["prompt"]
    assert "Generated.cs" not in captured["prompt"]
    assert not any("Nessun file di codice" in m for m in logs)


# ---------------------------------------------------------------------------
# Logging strutturato della spesa Anthropic (token e costo stimato): il layer LLM
# scartava message.usage dopo la risposta di Anthropic. Un fake module iniettato al
# posto del pacchetto 'anthropic' (non installato in questo ambiente) espone un
# messages.create() che ritorna un messaggio con .usage noto, cosi' da poter
# verificare via caplog che _anthropic_generate/_anthropic_agenerate logghino la
# riga senza toccare il testo restituito (_anthropic_text invariato).
# ---------------------------------------------------------------------------

class _FakeAnthropicUsage:
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeAnthropicTextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeAnthropicMessage:
    def __init__(self, text, input_tokens, output_tokens):
        self.content = [_FakeAnthropicTextBlock(text)]
        self.usage = _FakeAnthropicUsage(input_tokens, output_tokens)


class _FakeAnthropicMessagesSync:
    def __init__(self, message):
        self._message = message

    def create(self, **kwargs):
        return self._message


class _FakeAnthropicMessagesAsync:
    def __init__(self, message):
        self._message = message

    async def create(self, **kwargs):
        return self._message


class _FakeAnthropicClient:
    def __init__(self, message, *, timeout=None):
        self.messages = _FakeAnthropicMessagesSync(message)


class _FakeAsyncAnthropicClient:
    def __init__(self, message, *, timeout=None):
        self.messages = _FakeAnthropicMessagesAsync(message)


def _fake_anthropic_module(message):
    """Modulo 'anthropic' fittizio: solo cio' che core/llm.py usa (client sincrono/async
    e le eccezioni tipizzate catturate nei except)."""
    import types

    fake = types.SimpleNamespace()
    fake.Anthropic = lambda timeout=None: _FakeAnthropicClient(message, timeout=timeout)
    fake.AsyncAnthropic = lambda timeout=None: _FakeAsyncAnthropicClient(message, timeout=timeout)
    fake.AuthenticationError = type("AuthenticationError", (Exception,), {})
    fake.APITimeoutError = type("APITimeoutError", (Exception,), {})
    fake.APIConnectionError = type("APIConnectionError", (Exception,), {})

    class _APIStatusError(Exception):
        status_code = 500
        message = "errore"

    fake.APIStatusError = _APIStatusError
    return fake


def test_anthropic_generate_logga_input_output_tokens(monkeypatch, caplog):
    import logging

    message = _FakeAnthropicMessage("risposta claude", input_tokens=123, output_tokens=45)
    monkeypatch.setattr(llm, "_anthropic_module", lambda: _fake_anthropic_module(message))
    monkeypatch.setitem(llm.config, "llm_settings", {"active_provider": "anthropic", "models": {}})

    with caplog.at_level(logging.INFO, logger="core.llm"):
        out = llm._anthropic_generate("claude-sonnet-5", "ciao", timeout=5.0)

    assert out == "risposta claude"  # il testo restituito resta invariato
    righe = [r.getMessage() for r in caplog.records if r.name == "core.llm"]
    assert any(
        "provider=anthropic" in r and "model=claude-sonnet-5" in r
        and "input_tokens=123" in r and "output_tokens=45" in r
        for r in righe
    ), righe


def test_anthropic_agenerate_logga_input_output_tokens(monkeypatch, caplog):
    import logging

    message = _FakeAnthropicMessage("risposta async", input_tokens=10, output_tokens=7)
    monkeypatch.setattr(llm, "_anthropic_module", lambda: _fake_anthropic_module(message))
    monkeypatch.setitem(llm.config, "llm_settings", {"active_provider": "anthropic", "models": {}})

    with caplog.at_level(logging.INFO, logger="core.llm"):
        out = asyncio.run(llm._anthropic_agenerate("claude-sonnet-5", "ciao", timeout=5.0))

    assert out == "risposta async"
    righe = [r.getMessage() for r in caplog.records if r.name == "core.llm"]
    assert any(
        "input_tokens=10" in r and "output_tokens=7" in r for r in righe
    ), righe


def test_anthropic_generate_logga_cost_usd_con_pricing_configurato(monkeypatch, caplog):
    import logging

    message = _FakeAnthropicMessage("x", input_tokens=1_000_000, output_tokens=500_000)
    monkeypatch.setattr(llm, "_anthropic_module", lambda: _fake_anthropic_module(message))
    monkeypatch.setitem(llm.config, "llm_settings", {
        "active_provider": "anthropic",
        "models": {},
        "pricing": {"claude-sonnet-5": {"input_per_mtok": 3.0, "output_per_mtok": 15.0}},
    })

    with caplog.at_level(logging.INFO, logger="core.llm"):
        llm._anthropic_generate("claude-sonnet-5", "ciao", timeout=5.0)

    # 1M input @ $3/Mtok + 0.5M output @ $15/Mtok = 3.0 + 7.5 = 10.5 USD
    righe = [r.getMessage() for r in caplog.records if r.name == "core.llm"]
    assert any("cost_usd=10.5" in r for r in righe), righe


def test_anthropic_generate_senza_pricing_non_crasha_e_logga_solo_token(monkeypatch, caplog):
    import logging

    message = _FakeAnthropicMessage("x", input_tokens=42, output_tokens=8)
    monkeypatch.setattr(llm, "_anthropic_module", lambda: _fake_anthropic_module(message))
    # Nessuna sezione 'pricing': deve restare fail-closed, senza sollevare eccezioni.
    monkeypatch.setitem(llm.config, "llm_settings", {"active_provider": "anthropic", "models": {}})

    with caplog.at_level(logging.INFO, logger="core.llm"):
        out = llm._anthropic_generate("modello-sconosciuto", "ciao", timeout=5.0)

    assert out == "x"
    righe = [r.getMessage() for r in caplog.records if r.name == "core.llm"]
    assert any("input_tokens=42" in r and "output_tokens=8" in r for r in righe), righe
    assert not any("cost_usd" in r for r in righe)


# ---------------------------------------------------------------------------
# Budget guard giornaliero sul costo Claude (task 4.2): oltre la soglia
# llm_settings.budget.daily_usd i purpose risolti su anthropic degradano sul
# provider di fallback. Il guard è OFF finché il blocco `budget` non esiste, e non
# deve mai far fallire una generazione: nel dubbio si resta sul provider originale.
# ---------------------------------------------------------------------------

@pytest.fixture
def spesa_azzerata(monkeypatch):
    """Contatore di spesa isolato dal resto della suite: lo stato di modulo è globale
    (per processo) e monkeypatch lo ripristina a fine test."""
    monkeypatch.setitem(llm._spend_state, "day", "")
    monkeypatch.setitem(llm._spend_state, "usd", 0.0)


def _budget_settings(monkeypatch, budget: dict | None):
    """llm_settings con anthropic attivo e ollama disponibile come fallback."""
    settings = {
        "active_provider": "anthropic",
        "models": {"anthropic": "claude-sonnet-5", "ollama": "qwen3.5:9b"},
    }
    if budget is not None:
        settings["budget"] = budget
    monkeypatch.setitem(llm.config, "llm_settings", settings)
    return settings


def test_budget_guard_degrada_su_ollama_sopra_soglia(monkeypatch, spesa_azzerata, caplog):
    import logging

    _budget_settings(monkeypatch, {"daily_usd": 1.0})
    assert llm.resolve("canvas") == ("anthropic", "claude-sonnet-5")  # sotto soglia: invariato

    llm._record_spend(1.5)
    with caplog.at_level(logging.WARNING, logger="core.llm"):
        assert llm.resolve("canvas") == ("ollama", "qwen3.5:9b")
    righe = [r.getMessage() for r in caplog.records if r.name == "core.llm"]
    assert any("soglia 1.0000 USD" in r for r in righe), righe


def test_budget_assente_lascia_resolve_invariato(monkeypatch, spesa_azzerata):
    """Senza blocco `budget` il guard è disattivato: anche con una spesa registrata
    enorme la risoluzione resta quella di oggi."""
    _budget_settings(monkeypatch, None)
    llm._record_spend(999.0)
    assert llm.resolve("canvas") == ("anthropic", "claude-sonnet-5")
    assert llm.resolve("drift") == ("anthropic", "claude-sonnet-5")


def test_budget_con_daily_usd_nullo_e_come_assente(monkeypatch, spesa_azzerata):
    _budget_settings(monkeypatch, {"fallback_provider": "ollama"})  # nessun daily_usd
    llm._record_spend(999.0)
    assert llm.resolve("canvas") == ("anthropic", "claude-sonnet-5")


def test_spesa_si_azzera_al_cambio_di_giorno_utc(monkeypatch, spesa_azzerata):
    """Il contatore è per giorno UTC: cambiando giorno la spesa di ieri non conta più
    e il purpose torna su anthropic senza alcun job di rollover."""
    _budget_settings(monkeypatch, {"daily_usd": 1.0})
    llm._record_spend(5.0)
    assert llm.spend_today_usd() == 5.0
    assert llm.resolve("canvas") == ("ollama", "qwen3.5:9b")

    monkeypatch.setattr(llm, "_utc_day", lambda: "2999-01-01")
    assert llm.spend_today_usd() == 0.0
    assert llm.resolve("canvas") == ("anthropic", "claude-sonnet-5")


def test_budget_non_degrada_se_il_fallback_non_ha_un_modello(monkeypatch, spesa_azzerata, caplog):
    """Degradare su un provider non configurato trasformerebbe un problema di costo in
    un fallimento di generazione: si resta su anthropic, loggando il perché."""
    import logging

    monkeypatch.setitem(llm.config, "llm_settings", {
        "active_provider": "anthropic",
        "models": {"anthropic": "claude-sonnet-5"},  # nessun modello per il fallback
        "budget": {"daily_usd": 1.0, "fallback_provider": "ollama"},
    })
    llm._record_spend(2.0)
    with caplog.at_level(logging.WARNING, logger="core.llm"):
        assert llm.resolve("canvas") == ("anthropic", "claude-sonnet-5")
    righe = [r.getMessage() for r in caplog.records if r.name == "core.llm"]
    assert any("non ha un modello" in r for r in righe), righe


def test_spesa_persistita_su_file_sopravvive_al_riavvio(monkeypatch, spesa_azzerata, tmp_path):
    import json

    spend_file = tmp_path / "llm_spend.json"
    _budget_settings(monkeypatch, {"daily_usd": 2.0, "spend_file": str(spend_file)})
    llm._record_spend(3.0)
    assert json.loads(spend_file.read_text(encoding="utf-8"))["usd"] == 3.0

    # Stato in-memory azzerato = processo riavviato: la spesa si rilegge dal file.
    llm._spend_state["day"], llm._spend_state["usd"] = "", 0.0
    assert llm.spend_today_usd() == 3.0
    assert llm.resolve("canvas") == ("ollama", "qwen3.5:9b")


def test_file_di_spesa_corrotto_non_fa_fallire_il_guard(monkeypatch, spesa_azzerata, tmp_path):
    spend_file = tmp_path / "llm_spend.json"
    spend_file.write_text("{non json", encoding="utf-8")
    _budget_settings(monkeypatch, {"daily_usd": 1.0, "spend_file": str(spend_file)})
    assert llm.spend_today_usd() == 0.0
    assert llm.resolve("canvas") == ("anthropic", "claude-sonnet-5")


def test_chiamata_anthropic_riuscita_alimenta_il_contatore(monkeypatch, spesa_azzerata):
    """Il ciclo completo: la spesa non è un numero a parte ma quella già stimata per il
    log strutturato (task 2.2), quindi una chiamata reale sposta la risoluzione."""
    message = _FakeAnthropicMessage("x", input_tokens=1_000_000, output_tokens=0)
    monkeypatch.setattr(llm, "_anthropic_module", lambda: _fake_anthropic_module(message))
    monkeypatch.setitem(llm.config, "llm_settings", {
        "active_provider": "anthropic",
        "models": {"anthropic": "claude-sonnet-5", "ollama": "qwen3.5:9b"},
        "pricing": {"claude-sonnet-5": {"input_per_mtok": 3.0, "output_per_mtok": 15.0}},
        "budget": {"daily_usd": 2.0},
    })
    assert llm.resolve("canvas") == ("anthropic", "claude-sonnet-5")

    llm._anthropic_generate("claude-sonnet-5", "ciao", timeout=5.0)  # 1M input @ $3 = 3.0 USD
    assert llm.spend_today_usd() == 3.0
    assert llm.resolve("canvas") == ("ollama", "qwen3.5:9b")


def test_chiamata_senza_pricing_non_incide_sul_budget(monkeypatch, spesa_azzerata):
    """Senza prezzo configurato il costo non è noto: non si contabilizza nulla (meglio
    un guard inerte che una stima inventata)."""
    message = _FakeAnthropicMessage("x", input_tokens=1_000_000, output_tokens=1_000_000)
    monkeypatch.setattr(llm, "_anthropic_module", lambda: _fake_anthropic_module(message))
    _budget_settings(monkeypatch, {"daily_usd": 0.01})

    llm._anthropic_generate("claude-sonnet-5", "ciao", timeout=5.0)
    assert llm.spend_today_usd() == 0.0
    assert llm.resolve("canvas") == ("anthropic", "claude-sonnet-5")


def test_llm_settings_accetta_il_blocco_budget():
    """Il blocco `budget` deve passare la validazione pydantic del task 3.2, altrimenti
    un config che lo usa non arriverebbe nemmeno al boot."""
    from core.config import validate_llm_settings

    s = validate_llm_settings({
        "active_provider": "ollama",
        "models": {"ollama": "qwen3.5:9b"},
        "budget": {"daily_usd": 5.0, "fallback_provider": "ollama",
                   "spend_file": "database/llm_spend.json"},
    }, boot=True)
    assert s.budget.daily_usd == 5.0
    assert s.budget.fallback_provider == "ollama"
    assert s.budget.spend_file == "database/llm_spend.json"
    # Default: fallback ollama e nessuna persistenza.
    minimo = validate_llm_settings({
        "active_provider": "ollama", "models": {"ollama": "m"}, "budget": {"daily_usd": 1},
    }, boot=True)
    assert minimo.budget.fallback_provider == "ollama" and minimo.budget.spend_file is None


def test_llm_settings_budget_con_tipi_sbagliati_fallisce():
    from pydantic import ValidationError

    from core.config import validate_llm_settings

    with pytest.raises(ValidationError):
        validate_llm_settings({
            "active_provider": "ollama", "models": {"ollama": "m"},
            "budget": {"daily_usd": "cinque dollari"},
        }, boot=True)


# ---------------------------------------------------------------------------
# Check drift affidabile (core/drift.py): Spec come fonte normativa, lotti al posto del
# troncamento cieco, rilievi JSON verificati sul codice reale, verdetto calcolato.
# Banco di prova: i falsi positivi dei run reali su BE1 (AUDIT_LOG sull'export imposto
# da S07, "MinIO mancante" in un .csproj tagliato dal troncamento, ...).

def _drift_feature(tmp_path, monkeypatch, canvas="## Requirements\ncontratto", spec=None, dev_type="backend"):
    from core import indexing
    feature = tmp_path / "changes" / "be1"
    feature.mkdir(parents=True)
    (feature / "canvas.md").write_text(canvas, encoding="utf-8")
    if spec is not None:
        (feature / "spec.md").write_text(spec, encoding="utf-8")
    (feature / "meta.json").write_text(f'{{"dev_type": "{dev_type}"}}', encoding="utf-8")
    monkeypatch.setattr(indexing, "CHANGES_DIR", tmp_path / "changes")
    monkeypatch.setattr(indexing, "CODE_DIR", tmp_path / "code")
    code = tmp_path / "code" / dev_type
    code.mkdir(parents=True)
    return code


def _drift_llm(monkeypatch, batch_json='{"rilievi": []}', coverage_json='{"rilievi": []}',
               recheck_json='{"esito": "violato", "motivo": "confermato"}'):
    """LLM finto: risponde in base al tipo di prompt (lotto, riesame o copertura) e li registra."""
    from core import indexing
    prompts = []

    def fake(prompt, *, purpose):
        prompts.append(prompt)
        if "Controllo di COPERTURA" in prompt:
            return coverage_json
        return recheck_json if "AFFERMAZIONE DA VERIFICARE" in prompt else batch_json

    monkeypatch.setattr(indexing.llm, "generate", fake)
    return prompts


def test_check_drift_include_la_spec_nel_prompt_con_precedenza(fake_settings, monkeypatch, tmp_path):
    from core import indexing
    code = _drift_feature(tmp_path, monkeypatch, spec="SCENARIO: S07 - export\nTHEN registra AUDIT_LOG con commento \"ESPORTAZIONE_CSV\"")
    (code / "Reporting.cs").write_text("class Reporting {}", encoding="utf-8")
    prompts = _drift_llm(monkeypatch)

    report = indexing.check_drift("be1", emit=lambda _m: None)

    assert prompts and all("ESPORTAZIONE_CSV" in p for p in prompts)
    assert "SPEC (prevale sul Canvas)" in prompts[0]
    assert report.startswith("✅ NESSUN DRIFT RILEVATO")


def test_check_drift_scarta_rilievo_con_citazione_inesistente(fake_settings, monkeypatch, tmp_path):
    from core import indexing
    code = _drift_feature(tmp_path, monkeypatch, canvas="## Safeguards\n- Ogni endpoint deve verificare l'autorizzazione.")
    (code / "Program.cs").write_text('app.MapGet("/budget").RequireAuthorization("CanManageEvent");', encoding="utf-8")
    finding = ('{"rilievi": [{"categoria": "drift", "gravita": "alta", "sezione": "Canvas §7",'
               ' "requisito": "Ogni endpoint deve verificare l\'autorizzazione", "file": "Program.cs",'
               ' "evidenza": "app.MapDelete(\\"/events\\").AllowAnonymous();", "descrizione": "endpoint aperto"}]}')
    _drift_llm(monkeypatch, batch_json=finding)

    report = indexing.check_drift("be1", emit=lambda _m: None)

    assert report.startswith("✅ NESSUN DRIFT RILEVATO")
    assert "SCARTATI DALLA VERIFICA AUTOMATICA" in report
    assert "citazione del codice non trovata" in report


def test_check_drift_conferma_rilievo_con_citazione_reale(fake_settings, monkeypatch, tmp_path):
    from core import indexing
    code = _drift_feature(tmp_path, monkeypatch, canvas="## Safeguards\n- Ogni endpoint deve verificare l'autorizzazione.")
    (code / "Program.cs").write_text('app.MapDelete("/events")\n    .AllowAnonymous();', encoding="utf-8")
    finding = ('{"rilievi": [{"categoria": "drift", "gravita": "alta", "sezione": "Canvas §7",'
               ' "requisito": "Ogni endpoint deve verificare l\'autorizzazione", "file": "Program.cs",'
               ' "evidenza": "app.MapDelete(\\"/events\\") .AllowAnonymous();", "descrizione": "endpoint aperto"},'
               ' {"categoria": "conforme", "requisito": "RBAC", "evidenza": "x", "descrizione": "ok"}]}')
    _drift_llm(monkeypatch, batch_json=f"```json\n{finding}\n```")

    report = indexing.check_drift("be1", emit=lambda _m: None)

    assert report.startswith("⚠️ DRIFT RILEVATO: 1 ")  # il rilievo "conforme" non conta
    assert "Evidenza: Program.cs" in report


def test_check_drift_riesame_scarta_il_rilievo_smentito(fake_settings, monkeypatch, tmp_path):
    # Citazione reale ma conclusione sbagliata (BE1: "AuditLog solo sull'export" citando
    # proprio la riga dell'export): il riesame mirato la scarta.
    from core import indexing
    code = _drift_feature(tmp_path, monkeypatch, canvas="## Operations\n- Ogni comando di scrittura persiste una riga AuditLog.")
    (code / "Reporting.cs").write_text('db.AuditLogs.Add(new AuditLog("ESPORTAZIONE_CSV"));', encoding="utf-8")
    finding = ('{"rilievi": [{"categoria": "drift", "sezione": "Canvas §5",'
               ' "requisito": "Ogni comando di scrittura persiste una riga AuditLog", "file": "Reporting.cs",'
               ' "evidenza": "db.AuditLogs.Add(new AuditLog(\\"ESPORTAZIONE_CSV\\"));", "descrizione": "audit solo sull\'export"}]}')
    prompts = _drift_llm(monkeypatch, batch_json=finding,
                         recheck_json='{"esito": "rispettato", "motivo": "l\'audit è presente"}')

    report = indexing.check_drift("be1", emit=lambda _m: None)

    recheck = [p for p in prompts if "AFFERMAZIONE DA VERIFICARE" in p]
    assert len(recheck) == 1 and 'db.AuditLogs.Add(new AuditLog("ESPORTAZIONE_CSV"));' in recheck[0]
    assert report.startswith("✅ NESSUN DRIFT RILEVATO")
    assert "riesame: non è una violazione (l'audit è presente)" in report


def test_drift_riesame_riceve_lo_scenario_intero_del_requisito():
    from core import drift
    spec = ("```gherkin\nSCENARIO: S02 - Creazione evento fallita per mancanza di locandina\n"
            "  THEN rifiuta\n  AND non genera alcuna riga nell'entità AUDIT_LOG relativa alla scrittura fallita\n```\n\n"
            "```gherkin\nSCENARIO: S07 - Esportazione\n  AND registra l'esportazione nell'entità AUDIT_LOG\n```")
    context = drift.requirement_context(
        "AND non genera alcuna riga nell'entità AUDIT_LOG relativa alla scrittura fallita", "## Canvas", spec)
    assert "S02 - Creazione evento fallita per mancanza di locandina" in context
    assert "S07" not in context


def test_check_drift_dichiara_i_file_non_visti(fake_settings, monkeypatch, tmp_path):
    from core import indexing
    monkeypatch.setattr(indexing, "_DRIFT_MAX_CODE_CHARS", 300)
    code = _drift_feature(tmp_path, monkeypatch)
    # Ogni file sta in un lotto da 300 caratteri, i due insieme no.
    (code / "A.cs").write_text("class A {}\n" * 12, encoding="utf-8")
    (code / "B.cs").write_text("class B {}\n" * 12, encoding="utf-8")
    prompts = _drift_llm(monkeypatch)

    report = indexing.check_drift("be1", emit=lambda _m: None)

    first, second = prompts[0], prompts[1]
    non_visti = "IN QUESTO LOTTO NON VEDI"
    assert "--- FILE: A.cs ---" in first and "- B.cs" in first.split(non_visti)[1]
    assert "--- FILE: B.cs ---" in second and "- A.cs" in second.split(non_visti)[1]
    assert "2 file analizzati in 2 lotto/i" in report

    # Oltre il numero massimo di lotti i file restano fuori, ma dichiarati.
    monkeypatch.setattr(indexing, "_DRIFT_MAX_BATCHES", 1)
    prompts.clear()
    report = indexing.check_drift("be1", emit=lambda _m: None)
    assert "non analizzati: B.cs" in report
    assert "- B.cs" in prompts[-1].split("FILE NON ANALIZZATI NEI LOTTI")[1]  # anche alla copertura


def test_check_drift_divide_i_file_grandi_invece_di_troncarli(fake_settings, monkeypatch, tmp_path):
    # Il vecchio tetto troncava il codice e l'LLM affermava l'assenza di ciò che stava
    # nella parte tagliata (BE1: "manca MinIO" con Minio nel .csproj).
    from core import indexing
    monkeypatch.setattr(indexing, "_DRIFT_MAX_CODE_CHARS", 300)
    code = _drift_feature(tmp_path, monkeypatch)
    (code / "Big.cs").write_text("".join(f"// riga {i}\n" for i in range(60)), encoding="utf-8")
    prompts = _drift_llm(monkeypatch)

    indexing.check_drift("be1", emit=lambda _m: None)

    batches = [p for p in prompts if "Controllo di COPERTURA" not in p]
    assert len(batches) > 1
    assert "Big.cs (parte 1/" in batches[0]
    seen = "".join(batches)
    assert all(f"// riga {i}\n" in seen for i in range(60))
    assert "[codice troncato" not in seen


def test_check_drift_precheck_dipendenza_presente_nel_manifest(fake_settings, monkeypatch, tmp_path):
    from core import indexing
    code = _drift_feature(tmp_path, monkeypatch, canvas="## Approach\n- Usare **MinIO o Azure Blob Storage** per le locandine.")
    (code / "Portal.Infrastructure.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup>'
        '<PackageReference Include="Minio" Version="7.0.0" /></ItemGroup></Project>', encoding="utf-8")
    (code / "Storage.cs").write_text("class PosterStorage {}", encoding="utf-8")
    coverage = ('{"rilievi": [{"categoria": "drift", "sezione": "Canvas §3",'
                ' "requisito": "Usare MinIO o Azure Blob Storage per le locandine",'
                ' "termini": ["Minio"], "descrizione": "libreria MinIO assente dal csproj"}]}')
    prompts = _drift_llm(monkeypatch, coverage_json=coverage)
    logs = []

    report = indexing.check_drift("be1", emit=logs.append)

    assert "- MinIO: presente come `Minio` in Portal.Infrastructure.csproj" in prompts[0]
    assert any("Pre-check: 'MinIO'" in m for m in logs)
    assert report.startswith("✅ NESSUN DRIFT RILEVATO")
    assert "'Minio' è presente nel codice" in report


def test_check_drift_conferma_mancanza_con_termini_assenti(fake_settings, monkeypatch, tmp_path):
    # Il vero disallineamento trovato su BE1 (export Excel mancante) deve restare un drift.
    from core import indexing
    code = _drift_feature(tmp_path, monkeypatch,
                          canvas="## Requirements\n- Scaricare i partecipanti in formati CSV o Excel.")
    # Un termine citato solo in un commento o in un test non smentisce la mancanza.
    (code / "Reporting.cs").write_text(
        "class Reporting {\n    // CSV compatibile con l'apertura in Excel\n    string ToCsv() => \"\"; /* niente xlsx */\n}",
        encoding="utf-8")
    (code / "tests").mkdir()
    (code / "tests" / "ExportTests.cs").write_text("void Export_Xlsx_IsRejected() {}", encoding="utf-8")
    coverage = ('{"rilievi": [{"categoria": "drift", "gravita": "media", "sezione": "Canvas §1",'
                ' "requisito": "Scaricare i partecipanti in formati CSV o Excel",'
                ' "termini": ["Excel", "Xlsx"], "descrizione": "manca l\'export Excel"}]}')
    _drift_llm(monkeypatch, coverage_json=coverage)

    report = indexing.check_drift("be1", emit=lambda _m: None)

    assert report.startswith("⚠️ DRIFT RILEVATO: 1 ")
    assert "Termini cercati (assenti nel codice): Excel, Xlsx" in report


def test_check_drift_mancanza_dal_lotto_smentita_da_un_altro_file(fake_settings, monkeypatch, tmp_path):
    # BE1: "in Reporting.cs manca la validazione del budget", che sta in EventCommands.cs.
    from core import indexing
    monkeypatch.setattr(indexing, "_DRIFT_MAX_CODE_CHARS", 300)
    code = _drift_feature(tmp_path, monkeypatch, canvas="## Requirements\n- Rifiutare la pubblicazione se il budget è insufficiente.")
    (code / "EventCommands.cs").write_text('throw new ValidationException("BUDGET_INSUFFICIENTE");\n' * 5, encoding="utf-8")
    (code / "Reporting.cs").write_text("public sealed class BudgetQueries { }\n" * 5, encoding="utf-8")
    finding = ('{"rilievi": [{"categoria": "drift", "tipo": "mancanza", "sezione": "Canvas §1",'
               ' "requisito": "Rifiutare la pubblicazione se il budget è insufficiente", "file": "Reporting.cs",'
               ' "evidenza": "public sealed class BudgetQueries { ... }", "termini": ["BUDGET_INSUFFICIENTE"],'
               ' "descrizione": "manca la validazione del budget"}]}')
    _drift_llm(monkeypatch, batch_json=finding)

    report = indexing.check_drift("be1", emit=lambda _m: None)

    assert report.startswith("✅ NESSUN DRIFT RILEVATO")
    assert "'BUDGET_INSUFFICIENTE' è presente nel codice (EventCommands.cs)" in report


def test_check_drift_alternativa_tecnica_soddisfatta_non_e_una_mancanza(fake_settings, monkeypatch, tmp_path):
    from core import indexing
    code = _drift_feature(tmp_path, monkeypatch, canvas="## Approach\n- Usare **MinIO o Azure Blob Storage** per le locandine.")
    (code / "Infra.csproj").write_text(
        '<Project><ItemGroup><PackageReference Include="Minio" /></ItemGroup></Project>', encoding="utf-8")
    coverage = ('{"rilievi": [{"categoria": "drift", "requisito": "Usare MinIO o Azure Blob Storage per le locandine",'
                ' "termini": ["Azure Blob Storage"], "descrizione": "manca Azure"}]}')
    _drift_llm(monkeypatch, coverage_json=coverage)

    report = indexing.check_drift("be1", emit=lambda _m: None)

    assert report.startswith("✅ NESSUN DRIFT RILEVATO")
    assert "alternativa tecnica già soddisfatta da MinIO (Minio in Infra.csproj)" in report


def test_check_drift_riesame_mancanza_vede_il_codice_degli_identificativi(fake_settings, monkeypatch, tmp_path):
    # "Publish() non controlla il budget" con un nome inventato: il riesame deve vedere
    # l'handler (altro file) che cita BUDGET_ANNUO, identificativo dello scenario.
    from core import indexing
    spec = "```gherkin\nSCENARIO: S03 - Pubblicazione fallita\n  AND costo superiore al saldo del BUDGET_ANNUO\n  THEN rifiuta la transizione applicando la validazione del budget\n```"
    code = _drift_feature(tmp_path, monkeypatch, spec=spec)
    (code / "Event.cs").write_text("public void Publish() { Status = PUBBLICATO; }", encoding="utf-8")
    (code / "EventCommands.cs").write_text('if (cost > residual) throw new Err("saldo del BUDGET_ANNUO");', encoding="utf-8")
    finding = ('{"rilievi": [{"categoria": "drift", "tipo": "mancanza", "requisito": "rifiuta la transizione applicando la validazione del budget",'
               ' "file": "Event.cs", "evidenza": "public void Publish()", "termini": ["BudgetExceededException"],'
               ' "descrizione": "nessun controllo del budget"}]}')
    prompts = _drift_llm(monkeypatch, batch_json=finding)

    indexing.check_drift("be1", emit=lambda _m: None)

    recheck = next(p for p in prompts if "AFFERMAZIONE DA VERIFICARE" in p)
    related = recheck.split("CITA GLI IDENTIFICATIVI DEL REQUISITO ---")[1]
    assert "--- EventCommands.cs (riga 1) ---" in related and "saldo del BUDGET_ANNUO" in related


def test_drift_related_code_usa_gli_identificatori_del_rilievo():
    # "Publish() non valida che `MaxCapacity` sia >= 5": il validator è in un altro file e
    # il requisito S04 non ha identificativi MAIUSCOLI che lo raggiungano.
    from core import drift
    sources = {"Event.cs": "public int MaxCapacity { get; }",
               "Validators.cs": "class X {}\n" * 30 + "RuleFor(e => e.MaxCapacity).GreaterThanOrEqualTo(MinCapacity);"}
    requirement = "THEN restituisce un errore: la capienza deve essere almeno 5"
    assert drift.related_code(requirement, sources, 2000) == ""
    out = drift.related_code(requirement, sources, 2000, "Publish() non valida che `MaxCapacity` sia >= 5")
    assert "--- Validators.cs (riga 31) ---" in out and "GreaterThanOrEqualTo(MinCapacity)" in out


def test_check_drift_riesame_anche_per_la_copertura(fake_settings, monkeypatch, tmp_path):
    # Mancanza con nome inventato (ValidateCapacity) ma requisito coperto altrove.
    from core import indexing
    code = _drift_feature(tmp_path, monkeypatch, canvas="## Requirements\n- La capienza deve essere almeno 5.")
    (code / "Validators.cs").write_text("RuleFor(e => e.MaxCapacity).GreaterThanOrEqualTo(5);", encoding="utf-8")
    coverage = ('{"rilievi": [{"categoria": "drift", "requisito": "La capienza deve essere almeno 5",'
                ' "termini": ["ValidateCapacity"], "descrizione": "manca la validazione"}]}')
    prompts = _drift_llm(monkeypatch, coverage_json=coverage,
                         recheck_json='{"esito": "rispettato", "motivo": "coperto dal validator"}')

    report = indexing.check_drift("be1", emit=lambda _m: None)

    recheck = [p for p in prompts if "AFFERMAZIONE DA VERIFICARE" in p]
    assert len(recheck) == 1 and "rilievo di copertura" in recheck[0]
    assert report.startswith("✅ NESSUN DRIFT RILEVATO")
    assert "riesame: non è una violazione (coperto dal validator)" in report


def test_check_drift_contraddizione_con_termini_presenti_e_scartata(fake_settings, monkeypatch, tmp_path):
    from core import indexing
    code = _drift_feature(tmp_path, monkeypatch, canvas="## Norms\n- I log devono usare Serilog.")
    (code / "Program.cs").write_text("builder.Host.UseSerilog();\nvar x = 1;", encoding="utf-8")
    finding = ('{"rilievi": [{"categoria": "drift", "tipo": "contraddizione", "requisito": "I log devono usare Serilog",'
               ' "file": "Program.cs", "evidenza": "var x = 1;", "termini": ["Serilog"], "descrizione": "niente Serilog"}]}')
    _drift_llm(monkeypatch, batch_json=finding)

    report = indexing.check_drift("be1", emit=lambda _m: None)

    assert report.startswith("✅ NESSUN DRIFT RILEVATO")
    assert "'Serilog' è presente nel codice (Program.cs)" in report


def test_check_drift_punto_aperto_non_implementato_resta_nel_verdetto(fake_settings, monkeypatch, tmp_path):
    # BE1 senza export Excel: il Canvas chiede "CSV o Excel", la Spec lascia XLSX aperto
    # (OP-001). Non è un drift, ma non può finire sotto un ✅.
    from core import indexing
    code = _drift_feature(tmp_path, monkeypatch, canvas="## Requirements\n- Scaricare i partecipanti in formati CSV o Excel.")
    (code / "Reporting.cs").write_text("class Reporting { string ToCsv() => \"\"; }", encoding="utf-8")
    coverage = ('{"rilievi": [{"categoria": "punto_aperto", "sezione": "Spec OP-001",'
                ' "requisito": "Scaricare i partecipanti in formati CSV o Excel",'
                ' "termini": ["Xlsx"], "descrizione": "XLSX non implementato"}]}')
    _drift_llm(monkeypatch, coverage_json=coverage)

    report = indexing.check_drift("be1", emit=lambda _m: None)

    assert report.startswith("⚠️ PUNTI APERTI DA DECIDERE: nessun drift, ma 1 ")
    assert "Termini cercati (assenti nel codice): Xlsx" in report


def test_check_drift_riesame_punto_aperto_declassa_senza_nascondere(fake_settings, monkeypatch, tmp_path):
    # BE1 senza Excel: il riesame giudicava XLSX "punto aperto" (Spec OP-001) e il vero
    # disallineamento spariva tra gli scartati.
    from core import indexing
    code = _drift_feature(tmp_path, monkeypatch, canvas="## Requirements\n- Scaricare i partecipanti in formati CSV o Excel.")
    (code / "Reporting.cs").write_text('Formats = { "csv" };', encoding="utf-8")
    coverage = ('{"rilievi": [{"categoria": "drift", "requisito": "Scaricare i partecipanti in formati CSV o Excel",'
                ' "termini": ["Xlsx"], "descrizione": "manca Excel"}]}')
    _drift_llm(monkeypatch, coverage_json=coverage,
               recheck_json='{"esito": "punto_aperto", "motivo": "XLSX è in OP-001"}')

    report = indexing.check_drift("be1", emit=lambda _m: None)

    assert report.startswith("⚠️ PUNTI APERTI DA DECIDERE")
    assert "[riesame: punto aperto — XLSX è in OP-001]" in report


def test_drift_nome_composto_ipotetico_non_prova_una_mancanza():
    # Termini osservati nei run reali su BE1: falsi positivi con nomi inventati le cui parti
    # esistono tutte, veri positivi (export Excel assente) con parti assenti.
    from core import drift
    searchable = {"EventCommands.cs": "logger.logerror(ex); await tx.rollbackasync(); begintransactionasync(); "
                                      "new validationexception(); maxcapacity; capacity",
                  "Reporting.cs": "export csv"}

    def check(terms):
        out = drift._base({"tipo": "mancanza", "termini": terms})
        return drift._terms_absent(out, searchable), out["scartato"]

    ok, reason = check(["CapacityValidationException"])
    assert not ok and reason.startswith("nome ipotetico: le parti di 'CapacityValidationException'")
    assert not check(["RollbackTransaction"])[0]
    assert check(["ExcelExporter", "ToXlsx"]) == (True, "")
    assert check(["XLSX"]) == (True, "")


def test_drift_dedupe_unisce_le_mancanze_con_termini_sovrapposti():
    from core import drift
    gaps = [drift._base({"tipo": "mancanza", "requisito": r, "termini": t})
            for r, t in (("CSV o Excel", ["Xlsx", "Excel"]), ("export excel", ["XlsxDocumentFormat"]),
                         ("S04 capienza", ["MaxCapacity"]))]
    assert [g["requisito"] for g in drift.dedupe(gaps)] == ["CSV o Excel", "S04 capienza"]


def test_drift_parse_findings_recupera_json_malformato():
    # Risposte reali di qwen3.5:9b su BE1: virgolette del codice non escape, rilievi
    # concatenati come chiavi ripetute di un solo oggetto, risposta troncata.
    from core import drift
    text = ('{"rilievi":[{"categoria":"drift","requisito":"S07 export","file":"Reporting.cs",'
            '"evidenza":"Formats = { "csv" };","descrizione":"solo csv","categoria":"drift",'
            '"requisito":"S02 audit","evidenza":"db.AuditLogs.Add(x);","termini":["Audit"],"descrizione":"tronc')
    findings = drift.parse_findings(text)
    assert [f["evidenza"] for f in findings] == ['Formats = { "csv" };', "db.AuditLogs.Add(x);"]
    assert findings[1]["termini"] == ["Audit"] and findings[1]["descrizione"] == "tronc"
    assert drift.parse_findings('{"rilievi": []}') == []
    assert drift.parse_findings("nessun problema") is None
    assert drift.parse_recheck('{"richiesto": "x "y"", "esito": "rispettato", "motivo": "ok"}') == ("rispettato", "ok")
    assert drift.parse_recheck('{"violato": false, "motivo": "ok"}') == ("rispettato", "ok")  # formato booleano
    assert drift.parse_recheck("non so") == (None, "")
    # "Rispettato perché XLSX è un punto aperto" (risposta reale su BE1 senza Excel).
    assert drift.parse_recheck('{"esito": "rispettato", "motivo": "XLSX è un punto aperto della Spec"}')[0] == "punto_aperto"
    # Citazione su più righe con una riga intermedia saltata dal modello.
    code = drift.norm('reports.MapGet("/export", async (h) =>\n{\n    var file = await h.Handle(cmd);\n});')
    assert drift.quote_in('reports.MapGet("/export", async (h) =>\n    var file = await h.Handle(cmd);', code)
    assert not drift.quote_in('reports.MapGet("/export", async (h) =>\n    var file = Inventato();', code)


def test_check_drift_risposta_non_json_rende_la_verifica_incompleta(fake_settings, monkeypatch, tmp_path):
    from core import indexing
    code = _drift_feature(tmp_path, monkeypatch)
    (code / "A.cs").write_text("class A {}", encoding="utf-8")
    _drift_llm(monkeypatch, batch_json="Il codice è conforme, direi.")

    report = indexing.check_drift("be1", emit=lambda _m: None)

    assert report.startswith("⚠️ VERIFICA INCOMPLETA")
    assert "Lotto 1: risposta dell'LLM non interpretabile" in report

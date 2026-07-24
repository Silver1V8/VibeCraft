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


def test_provider_non_supportato(monkeypatch):
    monkeypatch.setitem(llm.config, "llm_settings", {
        "active_provider": "inesistente", "models": {"inesistente": "x"},
    })
    with pytest.raises(llm.LLMError, match="non supportato"):
        llm.generate("ciao", purpose="drift")


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
    """httpx.AsyncClient fake minimale (async context manager + .post()) per testare
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
    monkeypatch.setattr(llm.httpx, "AsyncClient", _make_fake_async_client({"response": ""}))
    with pytest.raises(llm.LLMError, match="risposta vuota"):
        asyncio.run(llm._ollama_agenerate("qwen3.5:9b", "ciao", timeout=1.0))


def test_ollama_agenerate_returns_content_when_present(monkeypatch):
    monkeypatch.setattr(llm.httpx, "AsyncClient", _make_fake_async_client({"response": "spec ok"}))
    assert asyncio.run(llm._ollama_agenerate("qwen3.5:9b", "ciao", timeout=1.0)) == "spec ok"


def test_ollama_payload_include_num_ctx_e_think_solo_se_configurati(monkeypatch):
    # num_ctx e' la difesa contro il default 4096 di Ollama, che tronca dall'alto i prompt
    # di canvas/propose (>4.300 token): senza, il modello non vede l'intervista in cima e
    # la risposta esce mozzata. think:false evita risposte vuote coi modelli thinking.
    monkeypatch.setattr(llm, "OLLAMA_NUM_CTX", 16384)
    monkeypatch.setattr(llm, "OLLAMA_THINK", False)
    p = llm._ollama_payload("m", "prompt")
    assert p["options"] == {"num_ctx": 16384}
    assert p["think"] is False
    # Non configurati -> payload storico, per compatibilita' con modelli/versioni che non
    # conoscono questi campi.
    monkeypatch.setattr(llm, "OLLAMA_NUM_CTX", None)
    monkeypatch.setattr(llm, "OLLAMA_THINK", None)
    p2 = llm._ollama_payload("m", "prompt")
    assert p2 == {"model": "m", "prompt": "prompt", "stream": False}


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


def test_ollama_payload_warna_se_il_prompt_sfiora_la_finestra(monkeypatch, caplog):
    # Il default 4096 di Ollama troncava i prompt SILENZIOSAMENTE (canvas mozzato, intervista
    # mai letta): con num_ctx configurato, un prompt vicino alla finestra deve almeno lasciare
    # una traccia nei log — mai piu' un taglio invisibile.
    import logging
    monkeypatch.setattr(llm, "OLLAMA_NUM_CTX", 1000)
    monkeypatch.setattr(llm, "OLLAMA_THINK", None)
    with caplog.at_level(logging.WARNING, logger="core.llm"):
        llm._ollama_payload("m", "x" * 3000)     # ~1000 token stimati = 100% della finestra
    assert any("troncamento" in r.message for r in caplog.records)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="core.llm"):
        llm._ollama_payload("m", "x" * 600)      # ~200 token: nessun warning
    assert not caplog.records


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


def test_check_drift_tronca_oltre_il_tetto_di_caratteri(fake_settings, monkeypatch, tmp_path):
    # Anche escludendo node_modules, una feature con molti file sorgente legittimi
    # potrebbe superare la finestra di contesto: meglio un troncamento esplicito e
    # segnalato che un prompt enorme spedito a Ollama.
    from core import indexing

    monkeypatch.setattr(indexing, "_DRIFT_MAX_CODE_CHARS", 100)
    captured = {}
    monkeypatch.setattr(indexing.llm, "generate",
                        lambda prompt, *, purpose: captured.setdefault("prompt", prompt) or "OK")

    feature = tmp_path / "changes" / "feat-x"
    feature.mkdir(parents=True)
    (feature / "canvas.md").write_text("## Requirements\n", encoding="utf-8")
    monkeypatch.setattr(indexing, "CHANGES_DIR", tmp_path / "changes")
    monkeypatch.setattr(indexing, "CODE_DIR", tmp_path / "code")
    (feature / "big.py").write_text("y" * 500, encoding="utf-8")

    logs = []
    indexing.check_drift("feat x", emit=logs.append)
    assert "[codice troncato" in captured["prompt"]
    assert any("troncato" in m for m in logs)

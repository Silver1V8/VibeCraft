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

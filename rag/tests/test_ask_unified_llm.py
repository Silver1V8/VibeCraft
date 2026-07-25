"""Test R4 + R12: POST /ask passa dal layer LLM unificato (core.llm, purpose "ask").

Coperti: semantica degli errori (LLMError ⇒ 502 esplicito, MAI un testo d'errore dentro
"answer" con status "success"), risoluzione del purpose "ask", cap per-chunk di 3000
caratteri sul contesto iniettato (sezioni e snippet di codice), guardrail globale di
num_ctx su un prompt di /ask enorme, base URL di Ollama condivisa fra core.llm e
routes_health.check_ollama (env VIBECRAFT_OLLAMA_URL), snapshot testuale del prompt
(system storico invariato) e assenza di riferimenti residui al vecchio secondo layer."""
import importlib
import logging
import re
from pathlib import Path

import networkx as nx
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.deps as deps
from api import routes_health, routes_retrieval
from core import llm, retrieval


_CHUNK_ID = "spec.md#01-form"
_TRUNCATION_MARKER = "… [sezione troncata] …"
# Vettore denso finto della domanda (encode_query è stubbato): i simboli di codice del
# test usano lo stesso vettore, così il coseno è 1.0 e il ramo semantico li trova sempre.
_QUERY_DENSE = [1.0, 0.0, 0.0]


def _snapshot(chunk_text: str, code_text: str,
              orphan_code_text: str | None = None) -> deps.IndexSnapshot:
    """Snapshot minimo ma completo per /ask: un documento con una sezione nel grafo,
    il testo della sezione nel sidecar dei chunk e un simbolo di codice linkato via
    IMPLEMENTS (peso sopra la soglia di config) col suo snippet nel code_store.

    `orphan_code_text` aggiunge un secondo simbolo SENZA archi nel grafo ma CON vettore
    denso: è raggiungibile solo dalla ricerca semantica diretta sul codice."""
    g = nx.DiGraph()
    g.add_node("spec.md", type="document")
    g.add_node(_CHUNK_ID, type="chunk")
    g.add_edge("spec.md", _CHUNK_ID, relation="HAS_SECTION")
    g.add_node("code/frontend/form.tsx::BookingForm", type="code", name="BookingForm")
    g.add_edge("code/frontend/form.tsx::BookingForm", _CHUNK_ID,
               relation="IMPLEMENTS", weight=0.9)
    code_store = {"code/frontend/form.tsx::BookingForm": {
        "name": "BookingForm", "kind": "component", "file": "frontend/form.tsx",
        "dev_type": "frontend", "text": code_text}}
    if orphan_code_text is not None:
        code_store["code/backend/dto.cs::Request"] = {
            "name": "Request", "kind": "class", "file": "backend/dto.cs",
            "dev_type": "backend", "text": orphan_code_text,
            "dense": np.array(_QUERY_DENSE, dtype=np.float16),  # coseno 1.0 con la domanda
        }
    code_ids, code_matrix = deps._prep_code_matrix(code_store)
    return deps.IndexSnapshot(
        graph=g,
        colbert_store={},
        chunks={_CHUNK_ID: {"text": chunk_text}},
        rule_descriptions={},
        code_store=code_store,
        version="vtest",
        code_ids=code_ids,
        code_matrix=code_matrix,
    )


@pytest.fixture
def fake_ask_settings(monkeypatch):
    """llm_settings controllati: provider fake attivo e un modello DEDICATO allo scopo
    "ask" — se la risposta arriva da 'ask-model', la risoluzione è davvero passata
    da purpose="ask" (e non da un altro scopo o dal default)."""
    settings = {
        "active_provider": "fake",
        "models": {"fake": "fake-model"},
        "purposes": {"ask": {"model": "ask-model"}},
    }
    monkeypatch.setitem(llm.config, "llm_settings", settings)
    return settings


@pytest.fixture
def ask_env(monkeypatch):
    """Factory di TestClient con la sola route /ask: stato del server (snapshot, qdrant,
    embed_model) e hybrid_search finti — sotto esame c'è solo il confine con l'LLM."""
    monkeypatch.setattr(deps, "API_KEY", None)
    monkeypatch.setattr(routes_retrieval, "maybe_reload_graph", lambda: None)

    def _make(chunk_text: str = "testo della sezione", code_text: str = "export const x = 1",
              orphan_code_text: str | None = None):
        snap = _snapshot(chunk_text, code_text, orphan_code_text)
        monkeypatch.setattr(routes_retrieval, "current_snapshot", lambda: snap)
        monkeypatch.setitem(deps.state, "qdrant", object())
        monkeypatch.setitem(deps.state, "embed_model", object())
        results = [{"chunk_id": _CHUNK_ID, "doc_id": "spec.md", "section": "form",
                    "dense_score": 0.9, "colbert_score": None}]
        monkeypatch.setattr(retrieval, "hybrid_search", lambda *a, **kw: results)
        # encode_query è la sola forward pass del modello nel percorso: stubbata come il
        # resto del retrieval (nessun bge-m3 reale in questi test).
        monkeypatch.setattr(retrieval, "encode_query",
                            lambda model, question: {"dense": np.array(_QUERY_DENSE),
                                                     "lexical": {}, "colbert": np.zeros((1, 3))})
        app = FastAPI()
        app.include_router(routes_retrieval.router)
        return TestClient(app, client=("127.0.0.1", 54321))

    return _make


# ---------------------------------------------------------------------------
# Semantica degli errori: LLMError ⇒ 502, mai "answer" con status "success"
# ---------------------------------------------------------------------------
def test_ask_502_su_llmerror_senza_campo_answer(ask_env, fake_ask_settings):
    def broken(model, prompt, timeout):
        raise llm.LLMError("[ERRORE DI CONNESSIONE]: Impossibile raggiungere Ollama. "
                           "Assicurati che l'applicazione Ollama sia avviata.")
    llm.register_provider("fake", broken)

    r = ask_env().post("/ask", json={"question": "Quali vincoli?"})

    assert r.status_code == 502
    body = r.json()
    assert "answer" not in body
    assert "ERRORE DI CONNESSIONE" in body["detail"]


def test_ask_200_con_purpose_ask(ask_env, fake_ask_settings):
    prompts = []

    def echo(model, prompt, timeout):
        prompts.append((model, prompt))
        return f"RISPOSTA[{model}]"
    llm.register_provider("fake", echo)

    r = ask_env().post("/ask", json={"question": "Quali vincoli?"})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    # 'ask-model' è l'override di purposes["ask"]: prova che il purpose risolto è "ask".
    assert body["answer"] == "RISPOSTA[ask-model]"
    model, prompt = prompts[0]
    assert model == "ask-model"
    assert prompt.startswith("Sei l'Ispettore di Governance di VibeCraft.")
    assert "Domanda: Quali vincoli?" in prompt


# ---------------------------------------------------------------------------
# Cap per-chunk (3000 char) su sezioni e snippet di codice iniettati nel contesto
# ---------------------------------------------------------------------------
def test_ask_cappa_chunk_e_snippet_oltre_il_tetto(ask_env, fake_ask_settings):
    prompts = []
    llm.register_provider("fake", lambda model, prompt, timeout: prompts.append(prompt) or "ok")

    r = ask_env(chunk_text="A" * 5000, code_text="B" * 4000).post("/ask", json={"question": "q"})

    assert r.status_code == 200
    prompt = prompts[0]
    assert _TRUNCATION_MARKER in prompt
    # Nessun blocco oltre il tetto: il testo sopravvissuto è esattamente il prefisso cappato.
    assert "A" * 3000 in prompt and "A" * 3001 not in prompt
    assert "B" * 3000 in prompt and "B" * 3001 not in prompt


# ---------------------------------------------------------------------------
# Ricerca semantica diretta sul codice: il codice entra nel contesto anche quando
# NESSUN documento lo descrive (il ponte IMPLEMENTS da solo non lo troverebbe).
# ---------------------------------------------------------------------------
def test_ask_inietta_codice_trovato_solo_dalla_ricerca_semantica(ask_env, fake_ask_settings):
    prompts = []
    llm.register_provider("fake", lambda model, prompt, timeout: prompts.append(prompt) or "ok")

    r = ask_env(orphan_code_text="class Request { CampoObbligatorio }").post(
        "/ask", json={"question": "quali campi obbligatori?"})

    assert r.status_code == 200
    # Il simbolo non ha alcun arco nel grafo: se compare, ci è arrivato per somiglianza
    # semantica con la DOMANDA, non di rimbalzo dai documenti recuperati.
    assert "class Request { CampoObbligatorio }" in prompts[0]
    sources = {c["source"]: c["name"] for c in r.json()["implementing_code"]}
    assert sources == {"semantic": "Request", "implements": "BookingForm"}


def test_ask_risponde_col_solo_codice_quando_i_documenti_non_matchano(ask_env, fake_ask_settings,
                                                                     monkeypatch):
    """Retrieval documentale a vuoto ma codice pertinente: la domanda riceve comunque una
    risposta (prima si restituiva 'Nessun documento rilevante')."""
    llm.register_provider("fake", lambda model, prompt, timeout: "ok")
    client = ask_env(orphan_code_text="class Request { CampoObbligatorio }")
    monkeypatch.setattr(retrieval, "hybrid_search", lambda *a, **kw: [])

    r = client.post("/ask", json={"question": "quali campi obbligatori?"})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert [c["name"] for c in body["implementing_code"]] == ["Request"]


def test_guardrail_globale_num_ctx_scatta_su_contesto_enorme(monkeypatch, caplog):
    """Il tetto per-chunk non limita il TOTALE: la difesa globale resta il warning di
    core.llm._ollama_payload quando la stima dei token sfiora num_ctx — deve scattare
    anche per il prompt di /ask."""
    monkeypatch.setattr(llm, "OLLAMA_NUM_CTX", 2000)
    prompt = retrieval.build_ask_prompt("x" * 30000, "domanda")  # ~10k token stimati >> 2000
    with caplog.at_level(logging.WARNING, logger="core.llm"):
        llm._ollama_payload("qwen3.5:9b", prompt)
    assert any("troncamento" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# R12: VIBECRAFT_OLLAMA_URL — core.llm e check_ollama sulla stessa origine
# ---------------------------------------------------------------------------
def test_vibecraft_ollama_url_condiviso_da_core_llm_e_health(monkeypatch):
    import core.config as core_config

    monkeypatch.setenv("VIBECRAFT_OLLAMA_URL", "http://gpu-box:9999")
    try:
        importlib.reload(core_config)
        importlib.reload(llm)
        assert llm.OLLAMA_GENERATE_URL == "http://gpu-box:9999/api/generate"

        seen = {}

        def _fake_urlopen(url, timeout=None):
            seen["url"] = url
            raise OSError("solo derivazione dell'URL, nessuna connessione")

        monkeypatch.setattr(routes_health.urllib.request, "urlopen", _fake_urlopen)
        assert routes_health.check_ollama() is False  # best-effort: errore ⇒ False
        assert seen["url"] == "http://gpu-box:9999/api/tags"  # stessa origine di core.llm
    finally:
        # Ripristina i moduli sul default PRIMA che altri test li usino: la reload con
        # l'env custom altrimenti resterebbe attiva per tutta la sessione.
        monkeypatch.delenv("VIBECRAFT_OLLAMA_URL", raising=False)
        importlib.reload(core_config)
        importlib.reload(llm)


# ---------------------------------------------------------------------------
# Snapshot testuale di build_ask_prompt: system prompt storico INVARIATO
# ---------------------------------------------------------------------------
def test_build_ask_prompt_snapshot_testuale():
    prompt = retrieval.build_ask_prompt("CONTESTO-DI-PROVA", "Qual è il vincolo?")
    assert prompt == (
        "Sei l'Ispettore di Governance di VibeCraft.\n"
        "Rispondi alle domande estraendo i contratti e i vincoli esatti.\n"
        "DEVI citare esplicitamente i codici dei Safeguards (es. [SAFEGUARD-TXN-01]) e i vincoli SQL (es. SELECT ... FOR UPDATE).\n"
        "[REGOLA-DIZIONARIO-RIGIDO]: È tassativamente ed espressamente vietato inventare o usare sinonimi colloquiali per le entità. "
        "DEVI usare esclusivamente i termini in MAIUSCOLO estratti dal glossario (Usa EVENTO e mai 'Posto', usa RICHIESTA e mai 'Domanda').\n"
        "[FONTE-CODICE]: il blocco «CODICE ESISTENTE» del contesto è codice sorgente REALE del progetto ed è una fonte "
        "al pari dei documenti: nomi di classi, campi, parametri, tipi e query che vi compaiono sono FATTI VERIFICATI, "
        "non invenzioni, e vanno citati testualmente (con file e simbolo) quando rispondono alla domanda. "
        "Quando codice e documento divergono, riporta ENTRAMBI e dichiara esplicitamente la divergenza."
        "\n\n"
        "Contesto grafo:\nCONTESTO-DI-PROVA\n\nDomanda: Qual è il vincolo?"
    )


# ---------------------------------------------------------------------------
# Zero riferimenti residui al vecchio secondo layer in rag/ (codice, test, doc)
# ---------------------------------------------------------------------------
_SCAN_EXTS = {".py", ".md", ".yaml", ".yml", ".html", ".js", ".css"}
_SCAN_EXCLUDED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "database"}


def test_zero_riferimenti_residui_al_vecchio_layer():
    """Regressione R4: l'identificatore del secondo layer rimosso non deve riapparire.
    Confine di parola: NON matcha identificatori diversi (es. il privato *_sync di
    canvas_review). Il needle è spezzato per non matchare questo stesso file."""
    needle = re.compile(r"(?<!\w)call_" + r"llm(?!\w)")
    this_file = Path(__file__).resolve()
    rag_root = this_file.parent.parent
    offenders = [
        str(path.relative_to(rag_root))
        for path in sorted(rag_root.rglob("*"))
        if path.suffix.lower() in _SCAN_EXTS
        and not any(part in _SCAN_EXCLUDED_DIRS for part in path.parts)
        and path != this_file
        and needle.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == []

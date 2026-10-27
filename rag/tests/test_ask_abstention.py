"""L'astensione era già corretta in prosa libera, ma illeggibile a macchina (A16):
`status` restava "success" con le fonti elencate, indistinguibile da una risposta vera.
Qui si verifica il contratto end-to-end: il marcatore che core.retrieval.build_ask_prompt
scrive nel prompt, letto e rimosso da api.routes_retrieval.ask_rag."""
import networkx as nx
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.deps as deps
from api import routes_retrieval
from core import llm, retrieval

_CHUNK_ID = "spec.md#01-form"


class _StubEmbed:
    def encode(self, texts, **kw):
        n = len(texts)
        out = {"dense_vecs": np.zeros((n, 4), dtype="float32")}
        if kw.get("return_sparse"):
            out["lexical_weights"] = [{} for _ in texts]
        if kw.get("return_colbert_vecs"):
            out["colbert_vecs"] = [np.zeros((1, 4), dtype="float32") for _ in texts]
        return out


def _snapshot(version="v1") -> deps.IndexSnapshot:
    g = nx.DiGraph()
    g.add_node("spec.md", type="document")
    g.add_node(_CHUNK_ID, type="chunk")
    g.add_edge("spec.md", _CHUNK_ID, relation="HAS_SECTION")
    return deps.IndexSnapshot(
        graph=g, colbert_store={}, chunks={_CHUNK_ID: {"text": "testo della sezione"}},
        rule_descriptions={}, code_store={}, version=version, code_ids=[], code_matrix=None,
    )


@pytest.fixture
def ask_env(monkeypatch):
    """Come in test_ask_observability.py, minimo indispensabile: la risposta dell'LLM
    finto è parametrizzabile per test tramite `risposta_llm`."""
    monkeypatch.setattr(deps, "API_KEY", None)
    monkeypatch.setitem(llm.config, "llm_settings",
                        {"active_provider": "fake", "models": {"fake": "fake-model"}, "purposes": {}})

    def _make(risposta_llm="RISPOSTA", manifest_exists=False):
        llm.register_provider("fake", lambda model, prompt, timeout: risposta_llm)
        monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: _snapshot())
        monkeypatch.setitem(deps.state, "qdrant", object())
        monkeypatch.setitem(deps.state, "embed_model", _StubEmbed())
        results = [{"chunk_id": _CHUNK_ID, "doc_id": "spec.md", "section": "form",
                    "dense_score": 0.9, "colbert_score": None}]
        monkeypatch.setattr(retrieval, "hybrid_search", lambda *a, **kw: results)
        monkeypatch.setattr(deps, "manifest_path", lambda v, project=None: None)
        monkeypatch.setattr(routes_retrieval, "qdrant_collection_for_version", lambda v, project=None: "coll")

        app = FastAPI()
        app.include_router(routes_retrieval.router)
        return TestClient(app, client=("127.0.0.1", 54321))

    return _make


MARCATORE = retrieval.ASK_ABSTENTION_MARKER


def test_marcatore_finisce_nel_prompt():
    """Il prompt deve contenere sia la regola sia il token letterale, o LLM e route
    potrebbero disallinearsi in silenzio se qualcuno rinomina uno dei due."""
    prompt = retrieval.build_ask_prompt("ctx", "domanda?")
    assert "[REGOLA-ASTENSIONE]" in prompt
    assert MARCATORE in prompt


def test_risposta_con_marcatore_diventa_astenuta(ask_env):
    client = ask_env(risposta_llm=f"{MARCATORE}\nIl contesto non contiene la soglia richiesta.")
    body = client.post("/ask", json={"question": "domanda?"}).json()
    assert body["status"] == "abstained"
    # il marcatore non deve mai raggiungere l'utente umano
    assert MARCATORE not in body["answer"]
    assert body["answer"] == "Il contesto non contiene la soglia richiesta."


def test_risposta_normale_resta_success(ask_env):
    client = ask_env(risposta_llm="La soglia è 1500 caratteri, vedi [REGOLA-VAL-02].")
    body = client.post("/ask", json={"question": "domanda?"}).json()
    assert body["status"] == "success"
    assert body["answer"] == "La soglia è 1500 caratteri, vedi [REGOLA-VAL-02]."


def test_marcatore_a_meta_testo_non_conta(ask_env):
    """Solo un PREFISSO conta come astensione: il modello che lo cita a metà frase
    (spiegando la regola, per esempio) non deve far scattare il flag."""
    testo = f"La regola dice di usare {MARCATORE} solo quando il contesto non basta."
    client = ask_env(risposta_llm=testo)
    body = client.post("/ask", json={"question": "domanda?"}).json()
    assert body["status"] == "success"
    assert body["answer"] == testo


def test_spazi_iniziali_prima_del_marcatore_sono_tollerati(ask_env):
    """Un LLM può anteporre whitespace/a-capo al primo token senza che sia una
    violazione della regola: lstrip() prima del confronto."""
    client = ask_env(risposta_llm=f"\n  {MARCATORE}\nNessuna fonte pertinente.")
    body = client.post("/ask", json={"question": "domanda?"}).json()
    assert body["status"] == "abstained"
    assert body["answer"] == "Nessuna fonte pertinente."


def test_astensione_viene_cachata_come_lo_stesso_esito(ask_env, monkeypatch):
    """Stessa domanda, stesso indice: la seconda richiesta non richiama l'LLM e
    l'esito cachato resta "abstained", non silenziosamente "success"."""
    client = ask_env(risposta_llm=f"{MARCATORE}\nNiente in questo corpus.")
    # use_thread=false: altrimenti l'append del primo turno cambia il fingerprint e
    # la seconda richiesta sarebbe un miss (VC-3).
    isolated = {"question": "domanda?", "use_thread": False}
    prima = client.post("/ask", json=isolated).json()
    assert prima["status"] == "abstained" and prima["cached"] is False

    # Se la cache non intercettasse, questa risposta diversa rivelerebbe la mancata cache.
    llm.register_provider("fake", lambda model, prompt, timeout: "RISPOSTA DIVERSA")
    seconda = client.post("/ask", json=isolated).json()
    assert seconda["status"] == "abstained" and seconda["cached"] is True
    assert seconda["answer"] == "Niente in questo corpus."


# R27 — A16 leggeva `answer.lstrip().startswith(MARCATORE)`: due asterischi bastavano a
# mancare l'astensione e il payload usciva "success". Non è un'ipotesi: è il caso 05 run 2
# di eval/golden_attribution.yaml, archiviato col testo integrale. Il set di ornamenti è
# misurato sulle 24 risposte archiviate di qwen3.5:9b, non scelto a naso:
#   ` (backtick)  37 token fra apici nell'archivio — l'abitudine PIÙ frequente del modello
#   *             9 token in grassetto, di cui **[ASTENSIONE]** due volte (il difetto)
#   #             0 nell'archivio, ma [REGOLA-ASTENSIONE] vieta esplicitamente un titolo
#                 prima del token: se è vietato è perché può succedere, e costa un carattere
# Esclusi con la stessa misura: `_` (0 usi di enfasi con underscore) e `>` (0 citazioni).
@pytest.mark.parametrize("ornato", [
    f"**{MARCATORE}**",   # caso 05 run 2, testuale
    f"`{MARCATORE}`",
    f"## {MARCATORE}",
    f"  **{MARCATORE}**  ",
])
def test_marcatore_ornato_conta_come_astensione(ask_env, ornato):
    client = ask_env(risposta_llm=f"{ornato}\nIl contesto non basta.")
    body = client.post("/ask", json={"question": "domanda?"}).json()
    assert body["status"] == "abstained"
    assert body["answer"] == "Il contesto non basta."


def test_motivazione_in_grassetto_non_viene_scorticata(ask_env):
    """Gli ornamenti si tolgono solo se ATTACCATI al marcatore: la motivazione che inizia
    per conto suo con del markdown deve restare intera (il modello formatta molto)."""
    client = ask_env(risposta_llm=f"{MARCATORE}\n**Il contesto** non basta.")
    body = client.post("/ask", json={"question": "domanda?"}).json()
    assert body["status"] == "abstained"
    assert body["answer"] == "**Il contesto** non basta."


pytestmark = pytest.mark.usefixtures("legacy_http_project")

"""Test di GET /api/code/search — l'indice del codice esposto a un agente esterno.

L'endpoint esiste per far leggere MENO codice all'agente: gli dice quali file aprire invece
di fargli scandire code/. Il rischio è che la risposta costi più di ciò che fa risparmiare,
quindi qui si verifica soprattutto ciò che la tiene piccola: niente testo dei simboli per
default, snippet troncato quando richiesto, tetto su k, tetto per file, filtro d'ambito.

Nessuna dipendenza di rete: il modello di embedding è finto e Qdrant resta a None — se
l'endpoint lo toccasse, questi test fallirebbero.
"""
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.deps as deps
from api import routes_retrieval
from core import retrieval
from core.config import CODE_SEARCH_API_MAX_K, CODE_SEARCH_API_SNIPPET_CHARS

_LONG_TEXT = "class Ordine\n" + ("campo obbligatorio; " * 60)


def _code_store() -> dict:
    """Quattro simboli su tre file e due ambiti, con vettori densi noti sugli assi."""
    return {
        "backend/ordini.py::valida_ordine": {
            "name": "valida_ordine", "kind": "function", "file": "backend/ordini.py",
            "dev_type": "backend", "text": _LONG_TEXT, "win_chunk_id": "spec.md#03-ordini",
            "dense": np.array([1.0, 0.0, 0.0], dtype=np.float16)},
        "backend/ordini.py::Ordine": {
            "name": "Ordine", "kind": "class", "file": "backend/ordini.py",
            "dev_type": "backend", "text": "class Ordine",
            "dense": np.array([0.99, 0.14, 0.0], dtype=np.float16)},
        "backend/legacy.py::Proxy": {
            "name": "Proxy", "kind": "class", "file": "backend/legacy.py",
            "dev_type": "backend", "text": "class Proxy",
            "dense": np.array([0.9, 0.44, 0.0], dtype=np.float16)},
        "frontend/form.ts::OrdineForm": {
            "name": "OrdineForm", "kind": "component", "file": "frontend/form.ts",
            "dev_type": "frontend", "text": "component OrdineForm",
            "dense": np.array([0.6, 0.8, 0.0], dtype=np.float16)},
    }


def _snapshot(code_store: dict) -> deps.IndexSnapshot:
    code_ids, code_matrix = deps._prep_code_matrix(code_store)
    return deps.IndexSnapshot(
        graph=None, colbert_store={}, chunks={}, rule_descriptions={},
        code_store=code_store, version="v-test",
        code_ids=code_ids, code_matrix=code_matrix,
        code_dev_type_idx=deps._prep_dev_type_index(code_ids, code_store),
    )


@pytest.fixture
def client(monkeypatch):
    """TestClient sulla sola route, con encode_query finta (nessun caricamento di bge-m3):
    la domanda diventa il versore [1,0,0], così i punteggi attesi sono calcolabili a mano."""
    monkeypatch.setattr(deps, "API_KEY", None)
    monkeypatch.setitem(deps.state, "embed_model", object())
    monkeypatch.setitem(deps.state, "qdrant", None)  # l'endpoint non deve toccarlo
    monkeypatch.setattr(retrieval, "encode_query",
                        lambda model, question: {"dense": np.array([1.0, 0.0, 0.0])})

    snap = _snapshot(_code_store())
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: snap)

    app = FastAPI()
    app.include_router(routes_retrieval.router)
    return TestClient(app, client=("127.0.0.1", 54321))


# ---------------------------------------------------------------------------
# Forma della risposta: navigazionale per default
# ---------------------------------------------------------------------------
def test_risposta_di_default_non_contiene_il_testo_dei_simboli(client):
    """È l'invariante che giustifica l'endpoint: il testo dei simboli è il campo che da solo
    farebbe costare la risposta più dei file che evita di leggere."""
    body = client.get("/api/code/search", params={"q": "validazione ordine", "k": 3}).json()

    assert body["count"] == 3
    assert all("text" not in r for r in body["results"])
    assert all("source" not in r for r in body["results"])  # sempre "semantic": rumore
    # Ciò che resta è quanto serve per decidere cosa aprire.
    assert set(body["results"][0]) >= {"symbol_id", "name", "kind", "file", "dev_type", "score"}
    assert body["index_version"] == "v-test"


def test_files_aggrega_i_file_da_aprire_in_ordine_di_pertinenza(client):
    body = client.get("/api/code/search", params={"q": "ordine", "k": 4}).json()

    assert [f["file"] for f in body["files"]] == ["backend/ordini.py", "backend/legacy.py",
                                                  "frontend/form.ts"]
    ordini = body["files"][0]
    assert ordini["symbols"] == 2 and ordini["best_score"] == 1.0
    # best_score è il massimo dei simboli di quel file, non il primo incontrato.
    assert body["files"][1]["best_score"] == pytest.approx(0.9, abs=0.01)


def test_implements_solo_quando_il_linking_lha_calcolata(client):
    results = client.get("/api/code/search", params={"q": "ordine", "k": 3}).json()["results"]
    assert results[0]["implements"] == "spec.md#03-ordini"
    assert "implements" not in results[1]  # chiave assente, non stringa vuota


# ---------------------------------------------------------------------------
# Tetti di contesto: sono la funzione, non una protezione dagli abusi
# ---------------------------------------------------------------------------
def test_snippet_e_opt_in_e_troncato(client):
    body = client.get("/api/code/search",
                      params={"q": "ordine", "k": 1, "snippet": "true"}).json()
    text = body["results"][0]["text"]

    assert text.endswith("…")
    assert len(text) <= CODE_SEARCH_API_SNIPPET_CHARS + 2
    assert len(_LONG_TEXT) > CODE_SEARCH_API_SNIPPET_CHARS  # il caso è davvero di troncamento


def test_snippet_corto_non_viene_alterato(client):
    body = client.get("/api/code/search",
                      params={"q": "ordine", "k": 3, "snippet": "true"}).json()
    assert body["results"][1]["text"] == "class Ordine"


def test_k_oltre_il_tetto_e_rifiutato(client):
    r = client.get("/api/code/search", params={"q": "ordine", "k": CODE_SEARCH_API_MAX_K + 1})
    assert r.status_code == 422
    assert client.get("/api/code/search",
                      params={"q": "ordine", "k": CODE_SEARCH_API_MAX_K}).status_code == 200


def test_tetto_per_file_evita_che_un_solo_file_occupi_tutte_le_posizioni(client):
    body = client.get("/api/code/search",
                      params={"q": "ordine", "k": 2, "max_per_file": 1}).json()
    assert [r["file"] for r in body["results"]] == ["backend/ordini.py", "backend/legacy.py"]


def test_min_score_scarta_le_corrispondenze_deboli(client):
    body = client.get("/api/code/search",
                      params={"q": "ordine", "k": 5, "min_score": 0.95}).json()
    assert [r["name"] for r in body["results"]] == ["valida_ordine", "Ordine"]


# ---------------------------------------------------------------------------
# Filtro per ambito
# ---------------------------------------------------------------------------
def test_dev_type_restringe_allo_scopo_della_feature(client):
    """Il simbolo frontend è il MENO simile in assoluto: emerge solo perché il filtro
    agisce prima dei top-k."""
    body = client.get("/api/code/search",
                      params={"q": "ordine", "k": 3, "dev_type": "frontend"}).json()
    assert [r["symbol_id"] for r in body["results"]] == ["frontend/form.ts::OrdineForm"]
    assert body["dev_type"] == "frontend"


def test_dev_type_inesistente_risponde_200_con_gli_ambiti_disponibili(client):
    """Non 404: l'agente si corregge con la stessa risposta, senza un giro in più."""
    r = client.get("/api/code/search", params={"q": "ordine", "dev_type": "backand"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0 and body["results"] == [] and body["files"] == []
    assert body["available_dev_types"] == ["backend", "frontend"]


# ---------------------------------------------------------------------------
# Stati degenerati
# ---------------------------------------------------------------------------
def test_indice_senza_codice_lo_dichiara_invece_di_tornare_vuoto(monkeypatch, client):
    """'Non c'è codice nell'indice' e 'non c'è nulla di pertinente' richiedono all'agente
    due comportamenti diversi: la risposta li distingue."""
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: _snapshot({}))
    body = client.get("/api/code/search", params={"q": "ordine"}).json()

    assert body["count"] == 0 and body["results"] == []
    assert "Glob/Grep" in body["note"]


def test_senza_indice_pronto_risponde_503(monkeypatch, client):
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: None)
    assert client.get("/api/code/search", params={"q": "ordine"}).status_code == 503


def test_query_vuota_rifiutata(client):
    assert client.get("/api/code/search", params={"q": ""}).status_code == 422


pytestmark = pytest.mark.usefixtures("legacy_http_project")

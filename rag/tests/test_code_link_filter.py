"""Pavimento di pertinenza alla domanda sul ponte IMPLEMENTS
(core.retrieval.filter_linked_code_by_question, nota S2 in
rag/adr/NOTA_IMPLEMENTAZIONE_MIGLIORIE.md).

Esercita la funzione vera, che a sua volta chiama search_code_symbols con subset_idx:
nessuna replica dell'algoritmo. I casi a livello di /ask stanno in test_ask_unified_llm.py."""
import numpy as np

import api.deps as deps
from core import retrieval

QUERY = np.array([1.0, 0.0, 0.0])


def _store() -> dict:
    """Coseni con QUERY: Vicino 1.0, Medio 0.6, Lontano 0.0; SenzaVettore non valutabile."""
    def sym(name, dense=None):
        entry = {"name": name, "kind": "function", "file": f"{name}.ts", "text": name}
        if dense is not None:
            entry["dense"] = np.array(dense, dtype=np.float16)
        return entry
    return {"Vicino": sym("Vicino", [1.0, 0.0, 0.0]),
            "Medio": sym("Medio", [0.6, 0.8, 0.0]),
            "Lontano": sym("Lontano", [0.0, 1.0, 0.0]),
            "SenzaVettore": sym("SenzaVettore")}


def _ponte(*ids) -> list[dict]:
    return [{"symbol_id": sid, "name": sid, "file": f"{sid}.ts", "weight": 0.9} for sid in ids]


def _filtra(linked, soglia, store=None):
    store = store if store is not None else _store()
    code_ids, code_matrix = deps._prep_code_matrix(store)
    tenuti, scartati = retrieval.filter_linked_code_by_question(
        linked, QUERY, store, min_score=soglia, code_ids=code_ids, code_matrix=code_matrix)
    return [c["symbol_id"] for c in tenuti], [c["symbol_id"] for c in scartati]


def test_soglia_zero_restituisce_la_lista_stessa():
    linked = _ponte("Vicino", "Lontano", "SenzaVettore")
    code_ids, code_matrix = deps._prep_code_matrix(_store())
    tenuti, scartati = retrieval.filter_linked_code_by_question(
        linked, QUERY, _store(), min_score=0.0, code_ids=code_ids, code_matrix=code_matrix)
    assert tenuti is linked and scartati == []


def test_tiene_i_pertinenti_e_scarta_il_non_pertinente():
    assert _filtra(_ponte("Vicino", "Medio", "Lontano"), 0.35) == (["Vicino", "Medio"], ["Lontano"])
    assert _filtra(_ponte("Vicino", "Medio", "Lontano"), 0.9) == (["Vicino"], ["Medio", "Lontano"])


def test_simbolo_senza_vettore_non_valutabile_resta():
    tenuti, scartati = _filtra(_ponte("SenzaVettore", "Lontano"), 0.99)
    assert tenuti == ["SenzaVettore"] and scartati == ["Lontano"]
    assert _filtra(_ponte("SenzaVettore"), 0.99) == (["SenzaVettore"], [])


def test_senza_matrice_nessuno_e_valutabile():
    store = {k: {kk: vv for kk, vv in v.items() if kk != "dense"} for k, v in _store().items()}
    assert _filtra(_ponte("Vicino", "Lontano"), 0.35, store) == (["Vicino", "Lontano"], [])


def test_nessun_candidato():
    assert _filtra([], 0.35) == ([], [])


def test_ordine_del_ponte_conservato_anche_se_contrario_al_coseno():
    # Il ponte ordina per peso dell'arco, non per coseno con la domanda: il filtro scarta,
    # non riordina.
    assert _filtra(_ponte("Medio", "SenzaVettore", "Vicino"), 0.35)[0] == [
        "Medio", "SenzaVettore", "Vicino"]

"""Guardrail sulla configurazione dei pesi di autorità e sull'ordinamento parametrizzato
(Epic 3). Protegge da una futura (ri)calibrazione che produca pesi assurdi o rompa la
monotonia sensata IRON_MEMORY >= AUTHORIZATION_POLICY >= DATA_DICTIONARY >= METHODOLOGY."""
from core import retrieval
from core.config import (
    AUTHORITY_BOOST_ALPHA,
    AUTHORITY_CLASS_WEIGHTS,
    AUTHORITY_DEFAULT_WEIGHT,
)


def test_class_weights_in_range_and_monotone():
    for cls, w in AUTHORITY_CLASS_WEIGHTS.items():
        assert 0.0 <= w <= 1.0, f"peso fuori range per {cls}: {w}"
    order = ["IRON_MEMORY", "AUTHORIZATION_POLICY", "DATA_DICTIONARY", "METHODOLOGY"]
    vals = [AUTHORITY_CLASS_WEIGHTS[c] for c in order if c in AUTHORITY_CLASS_WEIGHTS]
    assert vals == sorted(vals, reverse=True), f"ordine di autorità non monotono: {vals}"
    assert 0.0 <= AUTHORITY_DEFAULT_WEIGHT <= 1.0
    assert 0.0 <= AUTHORITY_BOOST_ALPHA <= 1.0


def test_authority_weight_archived_decay():
    active = retrieval._authority_weight({"classification": "IRON_MEMORY", "status": "ENFORCED"})
    archived = retrieval._authority_weight({"classification": "IRON_MEMORY", "status": "ARCHIVED"})
    assert archived < active                       # l'archiviato pesa meno dell'attivo
    # parametri iniettabili: il calibratore varia default/decay senza toccare il codice
    assert retrieval._authority_weight({"classification": "X"}, default=0.9) == 0.9


def test_rank_by_authority_alpha_zero_is_pure_relevance():
    """alpha=0 → l'autorità è ignorata: vince la rilevanza pura (ColBERT più alto), anche se
    l'altro candidato ha autorità massima."""
    low_rel_high_auth = {"colbert_score": 0.30, "authority": 1.0, "fused_rank_sum": 2, "id": "A"}
    high_rel_low_auth = {"colbert_score": 0.90, "authority": 0.1, "fused_rank_sum": 2, "id": "B"}
    out = retrieval.rank_by_authority([low_rel_high_auth, high_rel_low_auth], alpha=0.0)
    assert out[0]["id"] == "B"                      # senza autorità vince la rilevanza
    # con boost forte, l'autorità può ribaltare a parità/vicinanza di rilevanza
    a = {"colbert_score": 0.50, "authority": 1.0, "fused_rank_sum": 2, "id": "A"}
    b = {"colbert_score": 0.55, "authority": 0.1, "fused_rank_sum": 2, "id": "B"}
    assert retrieval.rank_by_authority([a, b], alpha=1.0)[0]["id"] == "A"

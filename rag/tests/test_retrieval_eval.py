"""Guard di regressione sulla QUALITÀ del retrieval (golden-set).

OPT-IN: si salta automaticamente se il server non è raggiungibile (serve modello + Qdrant
caricati). Quando il server è su, fallisce se section_hit@5 o MRR scendono sotto una soglia
di sicurezza — così un peggioramento del ranking (authority, fusione, chunking) viene notato.
Non importa torch: è un semplice client HTTP verso /api/retrieve.
"""
import httpx
import pytest

import eval_retrieval

URL = "http://127.0.0.1:8000"


def _server_up() -> bool:
    try:
        httpx.get(f"{URL}/api/index/status", timeout=3).raise_for_status()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _server_up(), reason="server non avviato (python server.py) — eval retrieval saltato")
def test_retrieval_quality_floor():
    m = eval_retrieval.evaluate(URL, k=5)
    # Baseline misurata: section_hit@5 = 1.00, MRR = 0.964. Soglie con margine.
    assert m["section_hit_k"] >= 0.85, f"section_hit@5 sceso a {m['section_hit_k']:.2f}"
    assert m["mrr"] >= 0.80, f"MRR sceso a {m['mrr']:.3f}"

"""G1 — script di calibrazione del gate di rispondibilità (eval/calibrate_answerability.py).
Solo la parte pura: scelta della soglia e smistamento delle risposte di /ask. La parte HTTP
gira dal vivo nel Task 6 del piano."""
import pytest

from eval.calibrate_answerability import choose_threshold, classify, summarize


def test_soglia_sotto_il_positivo_piu_basso():
    esito = choose_threshold([0.6, 0.9], [0.1, 0.55, 0.7])
    assert esito["threshold"] == pytest.approx(0.58)
    assert esito["neg_caught"] == 2 and esito["neg_total"] == 3
    assert esito["go_ratio"] is True


def test_negativi_tutti_sopra_niente_go():
    esito = choose_threshold([0.3], [0.5, 0.9])
    assert esito["neg_caught"] == 0 and esito["go_ratio"] is False


def test_senza_positivi_non_si_sceglie():
    with pytest.raises(ValueError):
        choose_threshold([], [0.1])


@pytest.mark.parametrize("payload, atteso", [
    ({"status": "graph_answer"}, "graph_answer"),
    ({"status": "success", "cached": True, "answerability": {"score": 0.4}}, "cached"),
    ({"status": "success", "cached": False}, "missing"),
    ({"status": "success", "cached": False, "answerability": None}, "missing"),
    ({"status": "no_results", "cached": False}, "no_results"),
    ({"status": "abstained", "cached": False, "answerability": {"score": 0.4}}, 0.4),
])
def test_classify(payload, atteso):
    assert classify(payload) == atteso


def test_summarize_conta_gli_scartati_e_non_li_usa_come_punteggi():
    righe = [
        {"group": "pos", "q": "a", "outcome": 0.8, "llm_status": "success", "latency_ms": 10},
        {"group": "pos", "q": "b", "outcome": "cached", "llm_status": "success", "latency_ms": None},
        {"group": "neg", "q": "c", "outcome": 0.2, "llm_status": "abstained", "latency_ms": 30},
        {"group": "neg", "q": "d", "outcome": "missing", "llm_status": "success", "latency_ms": None},
    ]
    report = summarize(righe)
    assert report["skipped"] == {"cached": 1, "missing": 1}
    assert report["threshold"]["neg_caught"] == 1 and report["threshold"]["neg_total"] == 1
    # matrice gate × LLM sui soli righe con punteggio
    assert report["matrix"] == {"gate_abstain&llm_abstained": 1, "gate_answer&llm_success": 1}
    assert report["latency_ms"]["p95"] == 30

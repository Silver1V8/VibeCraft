"""G1 — modulo puro del gate di rispondibilità (core/answerability.py) e la validazione
della sua modalità in core/config.py. Il reranker è uno stub: qui si verifica cosa il
modulo chiede al modello e cosa ne ricava, non il modello."""
import pytest

from core import answerability, config


class _StubReranker:
    def __init__(self, punteggi):
        self.punteggi = punteggi
        self.coppie = None

    def compute_score(self, coppie, **kw):
        self.coppie = list(coppie)
        return self.punteggi


def _assess(reranker, passaggi, *, mode="shadow", top_n=8, threshold=None):
    return answerability.assess(reranker, "domanda?", passaggi,
                                mode=mode, top_n=top_n, threshold=threshold)


def test_off_non_chiama_il_modello():
    stub = _StubReranker([0.9])
    assert _assess(stub, ["a"], mode="off") is None
    assert stub.coppie is None


def test_senza_passaggi_o_senza_modello_non_giudica():
    assert _assess(_StubReranker([0.9]), []) is None
    assert _assess(None, ["a"]) is None


def test_il_punteggio_e_il_massimo():
    esito = _assess(_StubReranker([0.2, 0.7, 0.1]), ["a", "b", "c"])
    assert esito["score"] == 0.7
    assert esito["scores"] == [0.2, 0.7, 0.1]
    assert esito["mode"] == "shadow"
    assert esito["latency_ms"] >= 0


def test_top_n_passa_solo_i_primi_nell_ordine_dato():
    stub = _StubReranker([0.1, 0.2])
    _assess(stub, ["primo", "secondo", "terzo"], top_n=2)
    assert stub.coppie == [("domanda?", "primo"), ("domanda?", "secondo")]


def test_scalare_per_una_sola_coppia():
    assert _assess(_StubReranker(0.3), ["a"])["scores"] == [0.3]


def test_would_abstain_segue_la_soglia():
    assert _assess(_StubReranker([0.4]), ["a"])["would_abstain"] is None
    assert _assess(_StubReranker([0.4]), ["a"], threshold=0.5)["would_abstain"] is True
    assert _assess(_StubReranker([0.6]), ["a"], threshold=0.5)["would_abstain"] is False


@pytest.mark.parametrize("mode, would_abstain, has_code, thread_active, atteso", [
    ("shadow", True, False, False, False),
    ("enforce", True, True, False, False),
    ("enforce", True, False, True, False),
    ("enforce", None, False, False, False),
    ("enforce", False, False, False, False),
    ("enforce", True, False, False, True),
])
def test_should_short_circuit(mode, would_abstain, has_code, thread_active, atteso):
    esito = {"mode": mode, "would_abstain": would_abstain}
    assert answerability.should_short_circuit(
        esito, has_code=has_code, thread_active=thread_active) is atteso


def test_should_short_circuit_senza_giudizio():
    assert answerability.should_short_circuit(None, has_code=False, thread_active=False) is False


def test_modalita_ignota_rifiutata():
    with pytest.raises(ValueError, match="banana"):
        config._answerability_mode("banana")
    assert config._answerability_mode(None) == "off"
    assert config._answerability_mode(" Shadow ") == "shadow"

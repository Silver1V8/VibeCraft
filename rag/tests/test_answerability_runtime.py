"""G1 — caricamento pigro del reranker del gate di rispondibilità
(api.index_runtime.ensure_reranker). Il costruttore è finto: si verifica QUANDO e COME il
modello viene costruito, e che un errore di caricamento non rompa /ask (fail-open)."""
import pytest

import api.deps as deps


class _Costruttore:
    def __init__(self, solleva=False):
        self.chiamate = []
        self.solleva = solleva

    def __call__(self, *args, **kwargs):
        self.chiamate.append((args, kwargs))
        if self.solleva:
            raise OSError("modello assente dalla cache HF")
        return object()


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setitem(deps.state, "reranker", None)
    monkeypatch.setitem(deps.state, "reranker_failed", False)

    def _make(mode, solleva=False):
        costruttore = _Costruttore(solleva)
        monkeypatch.setattr(deps, "ANSWERABILITY_MODE", mode)
        monkeypatch.setattr(deps, "FlagReranker", costruttore)
        return costruttore

    return _make


def test_off_non_costruisce_nulla(runtime):
    costruttore = runtime("off")
    assert deps.ensure_reranker() is None
    assert costruttore.chiamate == []


def test_shadow_costruisce_una_volta_su_cpu_normalizzato(runtime):
    costruttore = runtime("shadow")
    primo = deps.ensure_reranker()
    assert primo is not None and deps.ensure_reranker() is primo
    assert len(costruttore.chiamate) == 1
    args, kwargs = costruttore.chiamate[0]
    assert args == (deps.ANSWERABILITY_MODEL,)
    assert kwargs["devices"] == "cpu" and kwargs["normalize"] is True
    assert kwargs["max_length"] == deps.ANSWERABILITY_MAX_LENGTH


def test_errore_di_caricamento_non_ritenta_e_non_solleva(runtime):
    costruttore = runtime("shadow", solleva=True)
    assert deps.ensure_reranker() is None
    assert deps.ensure_reranker() is None
    assert len(costruttore.chiamate) == 1

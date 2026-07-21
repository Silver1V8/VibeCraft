"""Test M2: core.router.route_question — regole deterministiche derivate dai casi M1.

Contratto verificato:
  - TUTTI i casi "structural" di eval/golden_multihop.yaml (i 6 che hanno fatto
    scattare il trigger M2, tutti B>A nel report M1) instradano su "graph";
  - TUTTI i casi "multihop" dello stesso golden set restano "hybrid" (richiedono
    sintesi LLM su più documenti: il grafo da solo non risponde);
  - TUTTE le domande semantiche del golden set classico (eval/golden_set.yaml, ben
    oltre le 10 richieste) restano "hybrid": ZERO falsi positivi ammessi.
I casi sono letti dai YAML reali, non copiati: se il golden set cambia, il contratto
del router viene ri-verificato automaticamente.
"""
from pathlib import Path

import pytest
import yaml

from core.router import route_question

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"


def _cases(name: str) -> list[dict]:
    return yaml.safe_load((EVAL_DIR / name).read_text(encoding="utf-8"))["cases"]


_M1 = _cases("golden_multihop.yaml")
STRUCTURAL_QS = [c["q"] for c in _M1 if c["kind"] == "structural"]
MULTIHOP_QS = [c["q"] for c in _M1 if c["kind"] == "multihop"]
CLASSIC_QS = [c["q"] for c in _cases("golden_set.yaml")]


# ---------------------------------------------------------------------------
# I set letti dai YAML hanno la dimensione attesa (guardia contro file svuotati)
# ---------------------------------------------------------------------------
def test_i_golden_set_coprono_il_contratto_m2():
    assert len(STRUCTURAL_QS) == 6      # i 6 casi del trigger M2 (report M1)
    assert len(MULTIHOP_QS) >= 8
    assert len(CLASSIC_QS) >= 10        # "almeno 10 domande semantiche reali"


# ---------------------------------------------------------------------------
# Structural M1 ⇒ "graph"
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("q", STRUCTURAL_QS)
def test_structural_m1_instrada_su_graph(q):
    assert route_question(q) == "graph"


# ---------------------------------------------------------------------------
# Multihop M1 ⇒ "hybrid" (il grafo da solo non basta: serve la sintesi LLM)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("q", MULTIHOP_QS)
def test_multihop_m1_resta_hybrid(q):
    assert route_question(q) == "hybrid"


# ---------------------------------------------------------------------------
# Golden set classico ⇒ "hybrid": zero falsi positivi
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("q", CLASSIC_QS)
def test_golden_set_classico_zero_falsi_positivi(q):
    assert route_question(q) == "hybrid"


# ---------------------------------------------------------------------------
# Proprietà delle regole
# ---------------------------------------------------------------------------
def test_case_insensitive():
    assert route_question("QUALI DOCUMENTI ESISTONO NEL CORPUS?") == "graph"
    assert route_question("Quali Relazioni Ha lo standard di codifica?") == "graph"


def test_conservativo_in_dubbio_hybrid():
    # Le keyword nude di graph_query NON bastano: senza la formulazione strutturale
    # completa si resta su "hybrid" (regola enum richiede "esist*", impatto richiede
    # anche "modific*", relazioni richiede "quali relazioni ha").
    assert route_question("documenti") == "hybrid"
    assert route_question("definizione e attributi dell'entità EVENTO") == "hybrid"
    assert route_question("che impatto ha la cache sulle prestazioni?") == "hybrid"
    assert route_question("le relazioni tra i team di sviluppo") == "hybrid"
    assert route_question("") == "hybrid"

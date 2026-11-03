"""G1 — il set di domande SENZA risposta su cui si misura il gate di rispondibilità
(rag/adr/2026-11-03-gate-rispondibilita-plan.md). Qui si controlla solo la forma: la
verifica che il corpus non risponda è fatta a mano e scritta nel campo `why` di ogni caso."""
from collections import Counter
from pathlib import Path

import yaml

from eval.run import GOLDEN, load_cases

PATH = Path(__file__).resolve().parents[1] / "eval" / "golden_unanswerable.yaml"
TIPI = {"fuori_tema_adiacente", "valore_mancante", "presupposto_falso"}


def casi_senza_risposta() -> list[dict]:
    return yaml.safe_load(PATH.read_text(encoding="utf-8"))["cases"]


def test_set_senza_risposta_ben_formato():
    casi = casi_senza_risposta()
    assert len(casi) >= 15
    assert len({c["id"] for c in casi}) == len(casi)
    tipi = Counter(c["kind"] for c in casi)
    assert set(tipi) == TIPI
    assert min(tipi.values()) >= 4 and tipi["valore_mancante"] >= 6
    assert all(c["q"].strip() and c["why"].strip() for c in casi)


def test_nessuna_domanda_coincide_coi_positivi():
    positivi = {c["q"].strip().lower() for c in load_cases(GOLDEN)}
    assert not positivi & {c["q"].strip().lower() for c in casi_senza_risposta()}

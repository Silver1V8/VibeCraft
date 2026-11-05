"""EXP-C: casi etichettati vs router deterministico (nessun LLM router).

Modulo sotto test: core.router.route_question.
Test preesistenti correlati: test_router.py (golden); questo file aggiunge
routing_cases.yaml. Istruzione: implementare il piano eval VibeCraft.
"""
from pathlib import Path

import yaml

from core.router import route_question

CASES = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "eval" / "routing_cases.yaml").read_text(
        encoding="utf-8"
    )
)["cases"]


def test_routing_cases_non_vuoto():
    assert len(CASES) >= 8


def test_ogni_caso_ha_route_attesa():
    for c in CASES:
        assert c["expected_route"] in {"graph", "hybrid"}
        assert route_question(c["q"]) == c["expected_route"], c["id"]

"""Intervista Explore ancorata ai docs (core/interview.py + route explore/turn): le domande
la cui risposta è nei documenti non arrivano all'utente, ma tornano come «già documentato»
con la fonte; i disaccordi fra documenti diventano una scelta; ciò che non è verificabile
resta una domanda aperta."""
import json

import networkx as nx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from core import interview

SECTIONS = [
    {"sid": "S1", "doc_id": "docs/policy.md", "section": "Retention", "tag": "NORMATIVE",
     "source": "docs/policy.md § Retention", "text": "I log di audit sono conservati per 24 mesi."},
    {"sid": "S2", "doc_id": "docs/old.md", "section": "Log", "tag": "INFORMATIVE",
     "source": "docs/old.md § Log", "text": "I log di audit si conservano 12 mesi."},
]
QUESTIONS = ["Per quanto tempo si conservano i log di audit?", "Chi può esportare i report?"]


def test_parse_candidates_reads_fenced_json_and_caps():
    text = '```json\n{"commento": "Ok.", "domande": ' + json.dumps([f"D{i}?" for i in range(9)] + [" ", 3]) + "}\n```"
    comment, questions = interview.parse_candidates(text)
    assert comment == "Ok." and questions == [f"D{i}?" for i in range(interview.MAX_QUESTIONS)]
    assert interview.parse_candidates("Quali ruoli servono?") is None


def test_build_sections_dedups_and_numbers_in_order():
    graph = nx.DiGraph()
    graph.add_node("docs/a.md", classification="normative")
    store = {"c1": {"text": "x" * 5000}, "c2": {"text": "beta"}}
    hits = [[{"chunk_id": "c1", "doc_id": "docs/a.md", "section": "Uno"}],
            [{"chunk_id": "c1", "doc_id": "docs/a.md", "section": "Uno"},
             {"chunk_id": "c2", "doc_id": "docs/b.md", "section": ""},
             {"chunk_id": "assente", "doc_id": "docs/b.md"}]]
    sections = interview.build_sections(hits, chunks_store=store, graph=graph)
    assert [(s["sid"], s["source"], s["tag"]) for s in sections] == [
        ("S1", "docs/a.md § Uno", "normative"), ("S2", "docs/b.md", "")]
    assert len(sections[0]["text"]) == interview.MAX_SECTION_CHARS


def test_classify_keeps_only_verified_known_answers():
    verdict = json.dumps({"esiti": [
        {"domanda": 1, "stato": "nota", "risposta": "24 mesi", "fonte": "S1",
         "citazione": "conservati per 24 mesi"},
        {"domanda": 2, "stato": "nota", "risposta": "Solo admin", "fonte": "S1",
         "citazione": "solo gli amministratori esportano"},  # citazione inventata
    ]})
    result = interview.classify(QUESTIONS, SECTIONS, verdict)
    assert result["known"] == [{"question": QUESTIONS[0], "answer": "24 mesi",
                                "source": "docs/policy.md § Retention", "tag": "NORMATIVE"}]
    assert result["questions"] == [QUESTIONS[1]] and result["conflicts"] == []


@pytest.mark.parametrize("verdict", [
    "non è json",
    json.dumps({"esiti": [{"domanda": 1, "stato": "nota", "risposta": "24", "fonte": "S9",
                           "citazione": "24 mesi"}]}),  # fonte inesistente
    json.dumps({"esiti": [{"domanda": 7, "stato": "nota"}, {"domanda": "x"}, "voce"]}),
    json.dumps({"esiti": [{"domanda": 1, "stato": "conflitto", "opzioni": [  # stessa fonte due volte
        {"risposta": "24", "fonte": "S1", "citazione": "24 mesi"},
        {"risposta": "24!", "fonte": "S1", "citazione": "log di audit"}]}]}),
])
def test_classify_demotes_unverifiable_outcomes_to_open(verdict):
    result = interview.classify(QUESTIONS, SECTIONS, verdict)
    assert result == {"known": [], "conflicts": [], "questions": QUESTIONS}


def test_conflict_between_documents_becomes_a_choice_with_sources():
    verdict = json.dumps({"esiti": [{"domanda": 1, "stato": "conflitto", "opzioni": [
        {"risposta": "24 mesi", "fonte": "S1", "citazione": "conservati per 24 mesi"},
        {"risposta": "12 mesi", "fonte": "[S2]", "citazione": "si conservano 12 mesi"}]},
        {"domanda": 1, "stato": "aperta"}]})  # duplicato: vale il primo esito
    result = interview.classify(QUESTIONS, SECTIONS, verdict)
    assert [c["question"] for c in result["conflicts"]] == [QUESTIONS[0]]
    text = interview.render("", result)
    assert "A) 24 mesi [fonte: docs/policy.md § Retention, NORMATIVE]" in text
    assert "B) 12 mesi [fonte: docs/old.md § Log, INFORMATIVE]" in text
    assert "Domande aperte:\n1. " + QUESTIONS[1] in text


# ----------------------------------------------------------------------- route --

@pytest.fixture
def client(monkeypatch):
    from api import routes_pipeline as routes
    calls = []

    def fake_llm(*answers):
        async def generate(prompt, **kwargs):
            calls.append(prompt)
            return answers[len(calls) - 1]
        monkeypatch.setattr(routes.llm, "agenerate", generate)

    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app, client=("127.0.0.1", 50000)) as test_client:
        yield routes, test_client, fake_llm, calls


def _turn(test_client):
    response = test_client.post("/api/pipeline/explore/turn",
                                json={"feature_name": "audit", "user_input": "Export dei log", "history": "H"})
    assert response.status_code == 200, response.text
    return response.json()


def test_route_does_not_ask_what_docs_already_answer(client, monkeypatch):
    routes, test_client, fake_llm, calls = client
    monkeypatch.setattr(routes, "require_snapshot", lambda project: object())
    monkeypatch.setattr(routes, "ensure_shared_resources", lambda: None)
    seen = []
    monkeypatch.setattr(routes, "_interview_sections",
                        lambda questions, snap, project=None: seen.append(questions) or SECTIONS)
    fake_llm(json.dumps({"commento": "Chiaro.", "domande": QUESTIONS}),
             json.dumps({"esiti": [{"domanda": 1, "stato": "nota", "risposta": "24 mesi",
                                    "fonte": "S1", "citazione": "conservati per 24 mesi"},
                                   {"domanda": 2, "stato": "aperta"}]}))
    result = _turn(test_client)
    assert seen == [QUESTIONS] and "[S1] docs/policy.md § Retention [NORMATIVE]" in calls[1]
    text = result["ai_response"]
    assert text.startswith("Chiaro.")
    assert "→ 24 mesi [fonte: docs/policy.md § Retention]" in text
    assert text.split("Domande aperte:")[1] == "\n1. " + QUESTIONS[1]
    assert result["history"] == "H\nUtente: Export dei log\nIA: " + text


@pytest.mark.parametrize("failure, reason", [
    (HTTPException(409), "progetto non indicizzato"),
    (HTTPException(503), "retrieval non disponibile"),
])
def test_route_without_index_asks_all_and_says_so(client, monkeypatch, failure, reason):
    routes, test_client, fake_llm, calls = client
    def unavailable(project):
        raise failure
    monkeypatch.setattr(routes, "require_snapshot", unavailable)
    fake_llm(json.dumps({"commento": "", "domande": QUESTIONS}))
    text = _turn(test_client)["ai_response"]
    assert f"Documentazione non consultata ({reason})" in text
    assert all(q in text.split("Domande aperte:")[1] for q in QUESTIONS) and len(calls) == 1


def test_route_unstructured_model_output_is_flagged(client):
    _, test_client, fake_llm, _ = client
    fake_llm("Quali ruoli servono?")
    text = _turn(test_client)["ai_response"]
    assert text.startswith("⚠ Risposta del modello non strutturata") and text.endswith("Quali ruoli servono?")

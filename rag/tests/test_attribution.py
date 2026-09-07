"""L'harness di attribuzione (eval/attribution.py) senza LLM: normalizzazione del verdetto,
verifica deterministica della citazione, e il conto dell'accordo — che deve distinguere i
negativi dai positivi, perché un giudice che prende tutti i positivi e nessun negativo
sembrerebbe buono."""
import pytest

from core import llm
from eval import attribution as att

SOURCES = [
    "02_specs_normative/spec.md § 4. Retrieval [REQUIREMENTS]",
    "04_knowledge_informative/strategy.md § 4. Perché [METHODOLOGY]",
    "00_meta_governance/safeguards.md § 5 [IRON_MEMORY; via grafo: 1 hop, fiducia 0.900]",
]


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    (tmp_path / "spec.md").write_text("La forma **attenuata** `score × ((1 − α) + α × authority)`.", encoding="utf-8")
    (tmp_path / "strategy.md").write_text(
        "Il moltiplicatore impone che nessun documento possa mai superare in ranking un documento di authority superiore.",
        encoding="utf-8")
    monkeypatch.setattr(att, "DOCS_DIR", tmp_path)
    att._docs_cache.clear()
    return tmp_path


def test_normalizza_verdetto_su_stem_classe_e_nessuna():
    assert att.normalize_verdict("`02_specs_normative/spec.md`", SOURCES) == "spec"
    assert att.normalize_verdict("spec.md § 4. Retrieval", SOURCES) == "spec"
    assert att.normalize_verdict("[REQUIREMENTS]", SOURCES) == "spec"  # classe unica → documento
    assert att.normalize_verdict("nessuna", SOURCES) == att.NESSUNA
    assert att.normalize_verdict("", SOURCES) == att.NESSUNA
    assert att.parse_judgement("testo\n```json\n{\"attributed_to\": \"x\", \"quote\": \"q\"}\n```")["attributed_to"] == "x"
    assert att.parse_judgement("niente json")["attributed_to"] == att.PARSE_ERROR


def test_verifica_citazione_nel_documento_attribuito(corpus):
    # Il caso 06 run 3 di S12: fonte giusta, passo virgolettato preso dal distrattore.
    answer = ('Secondo [REGOLA-VAL-08] (fonte [REQUIREMENTS]) il testo specifica che "nessun documento '
              'possa mai superare in ranking un documento di authority superiore". Vale «la forma '
              'attenuata score × ((1 − α) + α × authority)», non "una frase breve".')
    assert att.quoted_spans(answer) == [
        "nessun documento possa mai superare in ranking un documento di authority superiore",
        "la forma attenuata score × ((1 − α) + α × authority)"]  # «una frase breve» è sotto soglia
    assert att.check_citations(answer, "spec", SOURCES) == "found_only_in:strategy"
    assert att.check_citations(answer, "strategy", SOURCES) == "found_only_in:spec"
    assert att.check_citations('Vale «la forma attenuata score × ((1 − α) + α × authority)».', "spec", SOURCES) == "verified"
    assert att.check_citations('Dice "una frase che nessun documento del corpus contiene davvero".', "spec", SOURCES) == "unverifiable"
    assert att.check_citations("Nessun passo fra virgolette.", "spec", SOURCES) == "no_quote"
    assert att.check_citations(answer, att.NESSUNA, SOURCES) == "no_quote"
    assert att._mostly_in(att.normalize("il testo specifica che nessun documento possa mai superare"), att.normalize(answer))
    assert not att._mostly_in(att.normalize("frase che il giudice si è inventato di sana pianta"), att.normalize(answer))


def _archive():
    def run(answer, attributed_to, correct):
        return {"date": "2026-09-07", "index_version": "v20260907T094225", "model": "m",
                "status": "success", "context_sources": SOURCES, "answer": answer,
                "verdict": {"attributed_to": attributed_to, "correct": correct, "note": ""}}
    return {"summary": {"index_version": "v20260907T094225"}, "cases": [
        {"id": "c1", "q": "q1", "normative": {"doc": "spec", "section": "x"},
         "runs": [run("Secondo la spec.", "spec", True), run("Secondo strategy.", "strategy", False)]},
        {"id": "c2", "q": "q2", "normative": None,
         "runs": [run("Il contesto non riporta una regola.", "NESSUNA", True)]},
    ]}


def test_accordo_conta_positivi_e_negativi_separatamente(monkeypatch, corpus):
    # Giudice fake: risponde «spec» a tutto — prende i positivi, manca il negativo e la NESSUNA.
    monkeypatch.setitem(llm.config, "llm_settings", {"active_provider": "fake", "models": {"fake": "f"}})
    llm.register_provider("fake", lambda model, prompt, timeout: '{"attributed_to": "spec.md", "quote": ""}')

    res = att.validate(_archive(), repeats=2, log=lambda *_: None)
    s = res["summary"]
    assert (s["records"], s["agree"]) == (3, 1)
    assert (s["positives"], s["positives_agree"]) == (2, 1)
    assert (s["negatives"], s["negatives_agree"]) == (1, 0)
    assert s["unanimous"] == 3
    assert s["disagreements"] == ["c1 run 2", "c2 run 1"]
    assert (s["binary_agree"], s["false_alarms"], s["missed_negatives"]) == (1, ["c2 run 1"], ["c1 run 2"])
    assert res["rows"][0]["judge"] == ["spec", "spec"]
    assert s["quote_not_in_answer"] == []  # quote vuota conta come assente, non inventata


def test_giudizio_per_esecuzione_e_ripetibilita(corpus):
    verdicts = iter(['{"attributed_to": "spec"}', '{"attributed_to": "strategy"}'])
    res = att.validate(_archive(), repeats=2, only_case="c2",
                       generate=lambda prompt: next(verdicts), log=lambda *_: None)
    row = res["rows"][0]
    assert row["judge"] == ["spec", "strategy"] and not row["unanimous"] and not row["agree"]
    assert res["summary"]["records"] == 1  # un record per esecuzione, mai per caso


def test_il_prompt_porta_domanda_fonti_e_risposta_intera():
    p = att.judge_prompt("la domanda", SOURCES, "la risposta\n\nseconda parte")
    assert "la domanda" in p and "seconda parte" in p
    assert all(s in p for s in SOURCES)
    assert "NESSUNA" in p


def test_fonti_del_contesto_rilette_dal_testo_di_ask():
    ctx = ("--- a/b.md § 1. Titolo [NORMS] ---\ntesto\n\n"
           "--- c/d.md § 2 [METADATA; via grafo: 1 hop, fiducia 0.900, pertinenza 0.4] ---\naltro\n\n"
           "--- Codice esistente: x.py :: f (function) ---\ndef f(): ...")
    assert att.context_sources(ctx) == ["a/b.md § 1. Titolo [NORMS]",
                                        "c/d.md § 2 [METADATA; via grafo: 1 hop, fiducia 0.900, pertinenza 0.4]"]

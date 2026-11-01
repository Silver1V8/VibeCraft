"""Protocollo di trasferimento. Nessun corpus reale: le stringhe sono fixture."""
from eval.external_transfer import (
    MEASURED,
    WAITING,
    abstention_outcomes,
    assess_manifest,
    duplicate_questions,
    evaluate_transfer,
    mean_reciprocal_rank,
    recall_at_k,
)
from scripts.external_transfer import main


def _manifest(**overrides):
    data = {
        "terza_parte": True,
        "provenienza": "TEST-FIXTURE ente, versione citata",
        "versione": "TEST-FIXTURE-1",
        "licenza": "TEST-FIXTURE-license",
        "autorizzazione": "TEST-FIXTURE permesso scritto di usare il corpus",
        "originali_conservati": True,
        "metadati_aggiunti_separati": True,
        "generated": False,
        "scritto_per_il_sistema": False,
        "costruito_per_favorire_il_sistema": False,
    }
    data.update(overrides)
    return data


def _cases():
    return [
        {"question": "TEST-FIXTURE uno", "retrieved": ["a", "b"], "relevant": ["b"]},
        {"question": "TEST-FIXTURE due", "retrieved": ["c"], "relevant": ["z"]},
        {"question": "TEST-FIXTURE taci", "retrieved": [], "relevant": [], "no_answer": True, "answered": False},
    ]


def test_senza_corpus_e_bloccato_e_non_validato(tmp_path):
    report = assess_manifest(None)
    assert report["status"] == "bloccato"
    assert report["indipendente"] is False
    assert report["validato"] is False
    assert report["misurato"] is False
    generated = assess_manifest(_manifest(generated=True, scritto_per_il_sistema=True))
    assert generated["indipendente"] is False
    assert any("non è indipendente" in reason for reason in generated["motivi"])
    assert main(["--manifest", str(tmp_path / "manca.json")]) == 2


def test_manifest_completo_non_basta_a_misurare():
    ready = assess_manifest(_manifest())
    assert ready["status"] == "pronto_non_validato"
    assert ready["validato"] is False
    waiting = evaluate_transfer(
        _manifest(), _cases(), human_verified=False, split="test",
        config_frozen=True, used_for_tuning=False, run_id="TEST-FIXTURE-run",
    )
    assert waiting["status"] == WAITING
    assert waiting["recall_at_k"] is None
    tuned = evaluate_transfer(
        _manifest(), _cases(), human_verified=True, split="test",
        config_frozen=True, used_for_tuning=True, run_id="TEST-FIXTURE-run",
    )
    assert tuned["status"] == "bloccato"
    assert tuned["misurato"] is False


def test_definizioni_e_una_run_tracciabile_non_e_validata():
    cases = _cases()
    assert recall_at_k(cases, 5) == 0.5
    assert mean_reciprocal_rank(cases) == 0.25
    report = evaluate_transfer(
        _manifest(), cases, human_verified=True, split="test",
        config_frozen=True, used_for_tuning=False, run_id="TEST-FIXTURE-run",
    )
    assert report["status"] == MEASURED
    assert report["misurato"] is True
    assert report["validato"] is False
    assert report["recall_at_k"]["5"] == 0.5
    assert report["mrr"] == 0.25
    assert report["astensione"]["n"] == 1
    assert report["astensione"]["corrette"] == 1
    copied = [dict(case) for case in cases]
    copied.append({"question": "TEST-FIXTURE   uno", "retrieved": ["a"], "relevant": ["a"]})
    assert duplicate_questions([case["question"] for case in copied])
    blocked = evaluate_transfer(
        _manifest(), copied, human_verified=True, split="test",
        config_frozen=True, used_for_tuning=False, run_id="TEST-FIXTURE-run",
    )
    assert blocked["misurato"] is False


def test_chiavi_di_indipendenza_taciute_non_bastano():
    for key in ("generated", "scritto_per_il_sistema", "costruito_per_favorire_il_sistema"):
        data = _manifest()
        del data[key]
        assert assess_manifest(data)["indipendente"] is False
    assert assess_manifest(_manifest(generated="false"))["indipendente"] is False


def test_senza_casi_non_e_misurato():
    report = evaluate_transfer(
        _manifest(), [], human_verified=True, split="test",
        config_frozen=True, used_for_tuning=False, run_id="TEST-FIXTURE-run",
    )
    assert report["status"] == "bloccato"
    assert report["misurato"] is False


def test_astensione_legge_answered_non_i_recuperati():
    cases = [
        {"question": "TEST-FIXTURE a", "retrieved": ["x"], "relevant": [], "no_answer": True, "answered": False},
        {"question": "TEST-FIXTURE b", "retrieved": ["x"], "relevant": [], "no_answer": True, "answered": True},
        {"question": "TEST-FIXTURE c", "retrieved": ["x"], "relevant": [], "no_answer": True},
    ]
    out = abstention_outcomes(cases)
    assert out == {"n": 2, "corrette": 1, "quota": 0.5, "senza_esito": 1}


def test_cli_tuning_non_dichiarato_blocca(tmp_path):
    import json
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    cases = tmp_path / "c.json"
    cases.write_text(json.dumps(_cases()), encoding="utf-8")
    base = ["--manifest", str(manifest), "--cases", str(cases), "--human-verified",
            "--config-frozen", "--run-id", "TEST-FIXTURE-run"]
    assert main(base) == 2
    assert main(base + ["--used-for-tuning", "no"]) == 0

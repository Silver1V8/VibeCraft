"""EXP-B: un solo passaggio correttivo locale (follow_ref). Testi sintetici.

Modulo sotto test: core.corrective. Nessun test preesistente su questo modulo.
Istruzione utente: «Implement the plan as specified… Don't stop until you have
completed all the to-dos.»
"""
from core.corrective import apply_corrective_pass, extract_refs, find_follow_ref_chunk


def test_extract_refs_ordine_e_dedup():
    refs = extract_refs(
        "Vedi [REGOLA-VAL-01] e poi [regola-val-01] ancora",
        "Anche [SAFEGUARD-SEC-07]",
    )
    assert refs == ["[REGOLA-VAL-01]", "[SAFEGUARD-SEC-07]"]


def test_follow_ref_aggiunge_al_piu_un_chunk():
    chunks = {
        "a.md#01": {
            "doc_id": "a.md",
            "section": "Intro",
            "text": "Rinvio a [REGOLA-VAL-01] senza enunciarla.",
        },
        "a.md#02": {
            "doc_id": "a.md",
            "section": "[REGOLA-VAL-01] Lock",
            "text": "### [REGOLA-VAL-01] Lock\nIl lock è obbligatorio.",
            "classification": "NORMS",
        },
        "b.md#01": {
            "doc_id": "b.md",
            "section": "[REGOLA-VAL-02] Altro",
            "text": "### [REGOLA-VAL-02] Altro\nNon deve entrare.",
        },
    }
    seen = {"a.md#01"}
    hit = find_follow_ref_chunk(
        question="come funziona il lock?",
        search_results=[{"chunk_id": "a.md#01"}],
        chunks_store=chunks,
        seen_chunks=seen,
    )
    assert hit is not None
    assert hit["chunk_id"] == "a.md#02"
    assert hit["ref"] == "[REGOLA-VAL-01]"
    assert hit["action"] == "follow_ref"


def test_apply_disabled_non_muta_contesto():
    parts: list[str] = ["già qui"]
    ordine: list[str] = ["x"]
    fonti: list[dict] = []
    seen: set[str] = set()
    trace = apply_corrective_pass(
        enabled=False,
        action="follow_ref",
        question="[REGOLA-VAL-01]",
        search_results=[],
        chunks_store={"a.md#01": {"doc_id": "a.md", "section": "[REGOLA-VAL-01]", "text": "x"}},
        seen_chunks=seen,
        context_parts=parts,
        ordine_contesto=ordine,
        fonti_nel_contesto=fonti,
        source_label=lambda r: "A",
        cap_text=lambda t: t,
    )
    assert trace["applied"] is False
    assert trace["reason"] == "disabled"
    assert parts == ["già qui"]
    assert ordine == ["x"]


def test_apply_follow_ref_una_volta():
    chunks = {
        "top.md#01": {
            "doc_id": "top.md",
            "section": "Top",
            "text": "Vedi [REGOLA-OBS-04].",
        },
        "norm.md#01": {
            "doc_id": "norm.md",
            "section": "[REGOLA-OBS-04] Log",
            "text": "### [REGOLA-OBS-04] Log\nUsa INFO per eventi attesi.",
        },
    }
    parts: list[str] = []
    ordine: list[str] = []
    fonti: list[dict] = []
    seen: set[str] = {"top.md#01"}
    trace = apply_corrective_pass(
        enabled=True,
        action="follow_ref",
        question="quando usare ERROR?",
        search_results=[{"chunk_id": "top.md#01"}],
        chunks_store=chunks,
        seen_chunks=seen,
        context_parts=parts,
        ordine_contesto=ordine,
        fonti_nel_contesto=fonti,
        source_label=lambda r: "NORMA",
        cap_text=lambda t: t,
    )
    assert trace["applied"] is True
    assert trace["added_chunk_id"] == "norm.md#01"
    assert len(parts) == 1
    assert "via correttivo: follow_ref [REGOLA-OBS-04]" in parts[0]
    assert ordine == ["norm.md#01"]

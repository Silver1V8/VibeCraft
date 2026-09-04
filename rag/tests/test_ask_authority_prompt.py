"""L'autorità dichiarata deve arrivare fino al PROMPT, non fermarsi al ranking (A3).

Il boost di classe riordinava i candidati e poi spariva: /ask consegnava all'LLM blocchi
«--- doc § sezione ---» indistinguibili fra loro. Misurato sui 4 casi avversariali, 2
risposte su 4 attribuivano il vincolo alla fonte METHODOLOGY che lo illustra invece che
alla spec che lo stabilisce — pur avendo entrambe nella finestra di contesto.

Qui si sorvegliano le due funzioni pure che rendono visibile quel segnale e la regola
[CLASSE-FONTI] che ne discende. Vedi core/retrieval.source_label / authority_scale.
"""
from core import retrieval


def test_etichetta_usa_la_classe_dichiarata():
    assert retrieval.source_label({"classification": "NORMS", "status": "ENFORCED"}) == "NORMS"


def test_senza_classe_non_e_una_classe_a_peso_basso():
    """Un file senza frontmatter non ha classe: dirlo è diverso dal dargliene una scarsa."""
    assert retrieval.source_label({}) == "SENZA CLASSE"
    assert retrieval.source_label({"classification": None}) == "SENZA CLASSE"


def test_lo_status_archiviato_compare_quello_vigente_no():
    """ENFORCED su ogni blocco sarebbe rumore; ARCHIVED cambia come va letta la fonte."""
    assert retrieval.source_label({"classification": "NORMS", "status": "ARCHIVED"}) == "NORMS, ARCHIVED"
    assert "ENFORCED" not in retrieval.source_label({"classification": "NORMS", "status": "ENFORCED"})


def test_scala_ordinata_dal_piu_autorevole():
    scala = retrieval.authority_scale([
        {"classification": "METHODOLOGY", "authority": 0.5},
        {"classification": "NORMS", "authority": 0.8},
        {"authority": 0.3},
    ])
    assert scala == [("NORMS", 0.8), ("METHODOLOGY", 0.5), ("SENZA CLASSE", 0.3)]


def test_scala_vuota_quando_non_discrimina():
    """Stessa disciplina di [PRECEDENZA-FONTI]: una regola inerte insegna a ignorarla."""
    assert retrieval.authority_scale([
        {"classification": "NORMS", "authority": 0.8},
        {"classification": "NORMS", "authority": 0.8},
    ]) == []
    assert retrieval.authority_scale([]) == []


def test_stessa_classe_pesi_diversi_tiene_il_massimo():
    """L'`authority` del frontmatter batte la classe, quindi due NORMS possono divergere:
    l'etichetta resta la classe, e la scala deve dire quanto pesa al suo meglio."""
    assert retrieval.authority_scale([
        {"classification": "NORMS", "authority": 0.95},
        {"classification": "NORMS", "authority": 0.80},
        {"classification": "METHODOLOGY", "authority": 0.50},
    ]) == [("NORMS", 0.95), ("METHODOLOGY", 0.5)]


def test_regola_classe_fonti_assente_senza_scala():
    prompt = retrieval.build_ask_prompt("ctx", "domanda?")
    assert "[CLASSE-FONTI]" not in prompt


def test_regola_classe_fonti_enuncia_la_graduatoria():
    prompt = retrieval.build_ask_prompt(
        "ctx", "domanda?", authority_classes=[("NORMS", 0.8), ("METHODOLOGY", 0.5)])
    assert "[CLASSE-FONTI]" in prompt
    assert "NORMS (0.80) > METHODOLOGY (0.50)" in prompt


def test_la_precedenza_dichiarata_viene_dopo_la_graduatoria_di_classe():
    """La graduatoria di classe è la regola generale, la precedenza l'eccezione specifica
    su due documenti precisi: nel prompt si leggono in quest'ordine."""
    prompt = retrieval.build_ask_prompt(
        "ctx", "domanda?", precedences=[("a.md", "b.md")],
        authority_classes=[("NORMS", 0.8), ("METHODOLOGY", 0.5)])
    assert prompt.index("[CLASSE-FONTI]") < prompt.index("[PRECEDENZA-FONTI]")


# ── [CITAZIONE-VERIFICABILE] (R1, sezione 8 di A3) ───────────────────────────────────────
# La riga storica ordinava di citare «i vincoli SQL (es. SELECT ... FOR UPDATE)» su un
# corpus che di SQL non parla, e il modello li produceva: «DEVI citare X» genera X anche
# dove X non c'è. Riprodotto il 2026-09-04 sui casi avversariali 3 e 4.

def test_il_prompt_non_ordina_piu_di_citare_vincoli_sql():
    prompt = retrieval.build_ask_prompt("ctx", "domanda?")
    assert "SQL" not in prompt
    assert "FOR UPDATE" not in prompt


def test_il_prompt_vieta_di_introdurre_cio_che_il_contesto_non_riporta():
    """Il divieto è la metà che porta il peso: togliere l'esempio senza vietare l'aggiunta
    lascerebbe intatta la forma che genera l'invenzione."""
    prompt = retrieval.build_ask_prompt("ctx", "domanda?")
    assert "[CITAZIONE-VERIFICABILE]" in prompt
    assert "vietato introdurre" in prompt

"""Normalizzazione sintattica degli scenari BDD (core/spec_format.py).

Il criterio dei test: ogni modalita' di fallimento REALE osservata diventa una fixture con
input sbagliato -> output atteso. Le fixture stanno in tests/fixtures/spec_format/ e sono
output veri del modello o spec veri del repo, non casi inventati: e' la differenza fra un
normalizzatore che regge la produzione e uno che regge solo i propri esempi.
"""
from pathlib import Path

import pytest

from core.spec_format import (
    SpecNormalizationError,
    normalize_spec,
    parse_scenarios,
)

FIXTURES = Path(__file__).parent / "fixtures" / "spec_format"


def leggi(nome: str) -> str:
    return (FIXTURES / nome).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Modalita' di fallimento 1 (LA2, output reale del modello): tutti gli scenari
# dentro UN SOLO blocco ```gherkin, e la `E` italiana al posto di AND. E' il
# fallimento che il prompt non e' mai riuscito a correggere in modo stabile.
# ---------------------------------------------------------------------------
def test_la2_blocco_unico_diventa_un_blocco_per_scenario():
    out = normalize_spec(leggi("la2_blocco_unico.md"))

    assert out.count("```gherkin") == 7          # un'apertura per scenario
    assert out.count("```") == 14                # e la relativa chiusura
    # Nessun passo comincia piu' con la `E` italiana.
    assert not any(line.strip().startswith("E ") for line in out.splitlines())
    assert "  AND avvia le strategie di invio su canali EMAIL e SLACK in parallelo" in out
    # Numerazione riassegnata in ordine, dal primo all'ultimo.
    numerate = [line for line in out.splitlines() if line.startswith("SCENARIO:")]
    assert [line.split(" - ")[0] for line in numerate] == [f"SCENARIO: S{n:02d}" for n in range(1, 8)]


def test_la2_normalizzato_passa_il_formato():
    # Il contratto che chiude il ciclo: l'output del normalizzatore e' conforme.
    from core import pipeline
    out = normalize_spec(leggi("la2_blocco_unico.md"))
    scenari = parse_scenarios(out)
    assert len(scenari) == 7
    assert all(len(s.steps) >= 3 for s in scenari)
    # Le regole di forma non hanno piu' niente da segnalare: restano solo quelle semantiche.
    violazioni = pipeline.check_bdd_semantics(out)["violations"]
    assert [v["rule"] for v in violazioni if v["rule"].startswith("fence")] == []


def test_il_contenuto_dei_passi_non_viene_toccato():
    # Il normalizzatore riscrive la FORMA. Il testo di ogni passo deve arrivare identico:
    # se qui cambiasse qualcosa, starebbe riscrivendo la specifica.
    src = leggi("la2_blocco_unico.md")
    testi_prima = [t for _, t in
                   [p for s in parse_scenarios(src) for p in s.steps]]
    testi_dopo = [t for _, t in
                  [p for s in parse_scenarios(normalize_spec(src)) for p in s.steps]]
    assert testi_prima == testi_dopo


# ---------------------------------------------------------------------------
# Idempotenza: la garanzia che il normalizzatore non introduca deriva a ogni
# passaggio. E' il test che ha scoperto due bug veri (le recinzioni non
# azzeravano lo stato, e i commenti appesi a un blocco finivano inglobati nel
# passo alla seconda passata), quindi vale su TUTTE le fixture, non su una.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nome", sorted(p.name for p in FIXTURES.glob("*.md")))
def test_normalize_e_idempotente(nome):
    una = normalize_spec(leggi(nome))
    assert normalize_spec(una) == una


def test_uno_spec_gia_conforme_resta_identico():
    conforme = (
        "# Spec demo\n\n"
        "```gherkin\n"
        "SCENARIO: S01 - Invio della richiesta\n"
        "  GIVEN un UTENTE autenticato\n"
        "  WHEN conferma l'invio\n"
        "  THEN il sistema registra la RICHIESTA\n"
        "```\n\n"
        "```gherkin\n"
        "SCENARIO: S02 - Invio rifiutato senza motivazione\n"
        "  GIVEN una RICHIESTA priva di motivazione\n"
        "  WHEN l'utente conferma l'invio\n"
        "  THEN il sistema rifiuta l'operazione\n"
        "```\n"
    )
    assert normalize_spec(conforme) == conforme


# ---------------------------------------------------------------------------
# Le altre forme che il normalizzatore incontra davvero.
# ---------------------------------------------------------------------------
def test_keyword_italiane_e_decorazioni_markdown():
    # Forma degli spec vecchi: keyword italiane, grassetto, elenco puntato.
    src = ("### Scenario 1: Badge sold out\n"
           "*   **Dato che** i posti residui sono zero\n"
           "*   **Quando** l'utente visualizza la card\n"
           "*   **Allora** il pulsante e' disabilitato\n"
           "*   **E** il badge mostra \"Sold out\"\n\n"
           "### Scenario 2: Richiesta rifiutata\n"
           "*   **Dato che** esiste gia' una RICHIESTA\n"
           "*   **Quando** l'utente riprova\n"
           "*   **Allora** il sistema rifiuta l'operazione\n")
    out = normalize_spec(src)
    assert "SCENARIO: S01 - Badge sold out" in out
    assert "  GIVEN i posti residui sono zero" in out
    assert "  WHEN l'utente visualizza la card" in out
    assert "  THEN il pulsante e' disabilitato" in out
    assert "  AND il badge mostra \"Sold out\"" in out
    assert out.count("```gherkin") == 2


def test_dato_che_vince_su_dato():
    # "DATO CHE" e' piu' lungo di "DATO" e va riconosciuto per primo, altrimenti il passo
    # diventerebbe «GIVEN che i posti sono zero».
    src = ("SCENARIO: S01 - Caso\n"
           "  Dato che i posti sono zero\n"
           "  Quando l'utente guarda\n"
           "  Allora vede il badge\n")
    assert "  GIVEN i posti sono zero" in normalize_spec(src)


def test_la_prosa_del_documento_passa_invariata():
    src = ("# Titolo del documento\n\n"
           "Una riga di prosa che descrive la feature.\n\n"
           "| campo | valore |\n|---|---|\n| a | b |\n\n"
           "SCENARIO: S01 - Caso nominale\n"
           "  GIVEN una premessa\n"
           "  WHEN accade qualcosa\n"
           "  THEN il sistema risponde\n\n"
           "SCENARIO: S02 - Caso negativo\n"
           "  GIVEN una premessa\n"
           "  WHEN accade altro\n"
           "  THEN il sistema rifiuta\n")
    out = normalize_spec(src)
    for riga in ("# Titolo del documento", "Una riga di prosa che descrive la feature.",
                 "| campo | valore |", "| a | b |"):
        assert riga in out


def test_il_frontmatter_yaml_non_viene_interpretato():
    # `date:` non e' un GIVEN: nel frontmatter il riconoscimento dei passi produceva i falsi
    # positivi peggiori, perche' e' fatto di righe `chiave: valore`.
    src = ("---\n"
           "id: \"spec-demo\"\n"
           "date: \"2026-07-12\"\n"
           "---\n\n"
           "SCENARIO: S01 - Caso\n"
           "  GIVEN una premessa\n"
           "  WHEN accade qualcosa\n"
           "  THEN il sistema risponde\n")
    out = normalize_spec(src)
    assert "date: \"2026-07-12\"" in out
    assert len(parse_scenarios(src)) == 1


def test_riga_di_intento_fra_titolo_e_passi():
    # Forma di LA1: fra la riga-scenario e il primo GIVEN c'e' una riga che ne descrive
    # l'intento. Non deve chiudere lo scenario lasciandolo senza passi.
    src = ("### Scenario S01: Invio notifica\n"
           "Verifica che il Logic Agent generi la comunicazione.\n\n"
           "**GIVEN**: una RICHIESTA in stato APPROVATA\n"
           "**WHEN**: arriva l'evento asincrono\n"
           "**THEN**: il Logic Agent invia l'email\n")
    out = normalize_spec(src)
    assert "SCENARIO: S01 - Invio notifica" in out
    assert "Verifica che il Logic Agent generi la comunicazione." in out
    assert "  GIVEN una RICHIESTA in stato APPROVATA" in out


def test_passo_spezzato_su_piu_righe_viene_ricongiunto():
    src = ("SCENARIO: S01 - Caso\n"
           "  GIVEN una premessa\n"
           "    che prosegue sulla riga dopo\n"
           "  WHEN accade qualcosa\n"
           "  THEN il sistema risponde\n")
    out = normalize_spec(src)
    assert "  GIVEN una premessa che prosegue sulla riga dopo" in out


def test_un_blocco_sql_attraversa_intatto():
    # Caso reale di spec_auth_1.1.md: un blocco ```sql pieno di righe che cominciano per AND
    # (`AND email NOT LIKE ...`). Se contassero come BDD, la recinzione sparirebbe — cioe' il
    # fatto stesso che quel testo sia SQL — e le clausole della query diventerebbero passi.
    src = ("```gherkin\n"
           "SCENARIO: S01 - Caso nominale\n"
           "  GIVEN una premessa\n"
           "  WHEN accade qualcosa\n"
           "  THEN il sistema risponde\n"
           "```\n\n"
           "**Constraint richiesto:**\n\n"
           "```sql\n"
           "ALTER TABLE utente\n"
           "  ADD CONSTRAINT chk_email\n"
           "  CHECK (\n"
           "    email LIKE '%@progettopa.it'\n"
           "    AND email NOT LIKE '%@%@%'\n"
           "  );\n"
           "```\n\n"
           "```gherkin\n"
           "SCENARIO: S02 - Caso negativo\n"
           "  GIVEN una premessa\n"
           "  WHEN accade altro\n"
           "  THEN il sistema rifiuta l'operazione\n"
           "```\n")
    out = normalize_spec(src)
    assert "```sql\nALTER TABLE utente" in out
    assert "    AND email NOT LIKE '%@%@%'" in out       # rientro e testo intatti
    assert out.count("```sql") == 1
    assert len(parse_scenarios(src)) == 2                # la query non e' uno scenario


def test_un_commento_dopo_il_blocco_non_finisce_nel_passo():
    # Il caso che rompeva l'idempotenza su spec_auth_1.1.md.
    src = ("```gherkin\n"
           "SCENARIO: S01 - Caso\n"
           "  GIVEN una premessa\n"
           "  WHEN accade qualcosa\n"
           "  THEN il sistema risponde\n"
           "```\n"
           "    # nota fuori dal blocco\n\n"
           "```gherkin\n"
           "SCENARIO: S02 - Caso negativo\n"
           "  GIVEN una premessa\n"
           "  WHEN accade altro\n"
           "  THEN il sistema rifiuta\n"
           "```\n")
    out = normalize_spec(src)
    assert "  THEN il sistema risponde\n```" in out
    assert "# nota fuori dal blocco" in out
    assert "risponde # nota" not in out


# ---------------------------------------------------------------------------
# Errori espliciti: il normalizzatore non indovina mai. Un normalizzatore che
# tira a indovinare e' peggio di uno che si ferma, perche' produce uno spec
# plausibile e sbagliato.
# ---------------------------------------------------------------------------
def test_errore_se_il_titolo_non_e_ricavabile():
    src = "  GIVEN una premessa\n  WHEN accade qualcosa\n  THEN il sistema risponde\n"
    with pytest.raises(SpecNormalizationError, match="senza uno scenario"):
        normalize_spec(src)


def test_errore_se_uno_scenario_non_ha_passi():
    src = ("SCENARIO: S01 - Primo\n"
           "  GIVEN una premessa\n"
           "  WHEN accade qualcosa\n"
           "  THEN il sistema risponde\n\n"
           "SCENARIO: S02 - Secondo senza passi\n\n"
           "Testo di chiusura del documento.\n")
    with pytest.raises(SpecNormalizationError, match="senza passi"):
        normalize_spec(src)


def test_errore_se_non_ci_sono_scenari():
    with pytest.raises(SpecNormalizationError, match="Nessuno scenario"):
        normalize_spec("# Solo un titolo\n\nE del testo che non e' BDD.\n")


def test_lerrore_dice_la_riga():
    # La diagnostica deve puntare al punto da correggere, non dire solo "non valido".
    with pytest.raises(SpecNormalizationError, match="riga 3"):
        normalize_spec("Una riga di prosa.\n\n  GIVEN una premessa senza scenario\n")


def test_una_riga_di_prosa_che_comincia_per_e_non_e_un_passo():
    # «E del testo...» e' italiano comunissimo: se contasse come AND, un paragrafo di prosa
    # diventerebbe uno scenario. Una congiunzione non puo' aprire niente.
    with pytest.raises(SpecNormalizationError, match="Nessuno scenario"):
        normalize_spec("# Solo un titolo\n\nE del testo che non e' BDD.\n")


def test_un_heading_prima_dei_passi_fa_da_titolo():
    # Rovescio del test sopra: l'heading E' un titolo valido per i passi che lo seguono, ed
    # e' cosi' che si normalizzano gli spec vecchi senza riga `SCENARIO:`.
    src = ("# Titolo\n\n"
           "  GIVEN una premessa\n  WHEN accade qualcosa\n  THEN il sistema risponde\n")
    assert "SCENARIO: S01 - Titolo" in normalize_spec(src)

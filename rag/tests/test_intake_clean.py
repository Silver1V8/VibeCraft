"""Test della pulizia deterministica del Markdown convertito (core/intake_clean.py):
l'arredo di impaginazione (testate/piè di pagina ripetuti, numeri di pagina, indici coi
puntini, immagini base64, sillabazione, a-capo di giustificazione) sparisce, il CONTENUTO
no. Il contratto che questi test difendono è: nessuna parola di contenuto persa, nessuna
riscrittura, idempotenza."""
import pytest

from core.intake_clean import clean_markdown

# Documento sintetico con tutte le forme di rumore osservate sui PDF/DOCX istituzionali:
# testata ripetuta a ogni pagina, sommario coi puntini di guida, piè di pagina numerato,
# numeri di sezione orfani lasciati dalla colonna di numerazione, frase spezzata a metà,
# parola sillabata a fine riga, spazi multipli del giustificato.
RUMOROSO = """# Specifiche del servizio

Istituto Nazionale Previdenza Sociale

Sommario

1. Introduzione ......................................................... 3

2. Sicurezza ............................................................ 8

Pagina 1 di 14

Istituto Nazionale Previdenza Sociale

1. Introduzione

Il servizio espone un'interfaccia SOAP  auto-
consistente che il consumer deve
invocare tramite DataPower.

Pagina 2 di 14

Istituto Nazionale Previdenza Sociale

2.1

Sicurezza

Ogni richiesta deve contenere l'header Identity.

Pagina 3 di 14

Istituto Nazionale Previdenza Sociale
"""


def test_toglie_arredo_e_tiene_il_contenuto():
    out = clean_markdown(RUMOROSO)

    # Arredo: via.
    assert "Istituto Nazionale Previdenza Sociale" not in out
    assert "Pagina 1 di 14" not in out
    assert "........" not in out
    assert "Sommario" not in out or "Introduzione ....." not in out

    # Contenuto: tutto ancora lì.
    assert "# Specifiche del servizio" in out
    assert "DataPower" in out
    assert "header Identity" in out
    assert "Sicurezza" in out


def test_ricongiunge_sillabazione_e_a_capo_di_impaginazione():
    out = clean_markdown(RUMOROSO)

    assert "autoconsistente" in out          # "auto-\nconsistente" era una parola sola
    assert "consistente che il consumer deve invocare" in out   # a-capo di giustificazione
    assert "SOAP auto" in out                # spazi multipli del giustificato collassati


def test_idempotente():
    una = clean_markdown(RUMOROSO)

    assert clean_markdown(una) == una


def test_non_tocca_il_contenuto_dei_blocchi_di_codice():
    doc = """## Schema

```xml
<Identity>
    <AppName>APP</AppName>



    <UserId>u</UserId>
</Identity>
```

Fine.
"""
    out = clean_markdown(doc)

    # Indentazione, righe vuote e struttura del fence restano intatte: dentro un blocco
    # di codice ogni carattere è contenuto, anche ciò che fuori sarebbe rumore.
    assert "    <AppName>APP</AppName>" in out
    assert out.count("```") == 2


def test_non_scarta_righe_ripetute_ma_strutturali():
    # Le righe di una tabella e le voci di lista si ripetono legittimamente: la regola
    # dell'intestazione ricorrente non deve mai toccarle.
    doc = "\n\n".join(
        ["| Campo | Tipo |", "| --- | --- |"] + ["| AppName | string |"] * 4
    )
    out = clean_markdown(doc)

    assert out.count("| AppName | string |") == 4


def test_immagini_base64_rimosse():
    doc = "Testo prima\n\n![](data:image/png;base64,AAAABBBBCCCC)\n\nTesto dopo"

    out = clean_markdown(doc)

    assert "base64" not in out
    assert "Testo prima" in out and "Testo dopo" in out


@pytest.mark.parametrize("vuoto", ["", "   ", "\n\n\n"])
def test_documento_vuoto(vuoto):
    assert clean_markdown(vuoto) == ""

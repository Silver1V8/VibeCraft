"""Test della raffinazione LLM dei documenti in staging (core/intake_refine.py): finestre,
parsing del frontmatter semantico, guardrail anti-riassunto, aggiornamento del journal e
fusione dei campi semantici nel frontmatter finale di approve.

Nessuna chiamata a Ollama: `generate` è iniettabile e i test passano un fake deterministico
(stesso seam dei test di generazione doc)."""
import json
from pathlib import Path

import pytest

from core import intake, intake_refine
from core.chunking import parse_markdown_file
from core.intake_refine import (
    RefineError,
    parse_semantic_metadata,
    refine_markdown,
    split_windows,
    strip_speculation,
)

METADATA_YAML = """title: Specifiche del Custom SOAP Header
document_type: specifica tecnica
source_version: "3.1"
domain: [INPS, SOAP, DataPower]
tags: [soap, custom-header, datapower]
"""


def _fake_llm(metadata_yaml: str = METADATA_YAML):
    """Fake di `generate`: risponde col YAML dei metadati alla prima chiamata (il prompt
    dei metadati è riconoscibile) e con una riscrittura plausibile per ogni finestra."""
    def generate(prompt: str) -> str:
        if "SOLO un blocco YAML" in prompt:
            return metadata_yaml
        corpo = prompt.split("--- TESTO DA RIFORMATTARE ---")[1].split("--- FINE TESTO ---")[0]
        return f"## Sezione riscritta\n\n{corpo.strip()}\n\n| Campo | Tipo |\n| --- | --- |\n| AppName | string |"
    return generate


# ---------------------------------------------------------------------------
# Finestre
# ---------------------------------------------------------------------------
def test_finestre_tagliano_solo_ai_confini_di_blocco():
    testo = "\n\n".join(f"Paragrafo numero {i} con un po' di testo." for i in range(40))

    windows = split_windows(testo, window_chars=200)

    assert len(windows) > 1
    # Nessun blocco spezzato: ricomponendo si riottiene esattamente il testo di partenza.
    assert "\n\n".join(windows) == testo


def test_blocco_piu_lungo_della_finestra_resta_intero():
    blocco = "x" * 500

    windows = split_windows(f"Intro breve.\n\n{blocco}", window_chars=100)

    assert blocco in windows


# ---------------------------------------------------------------------------
# Frontmatter semantico
# ---------------------------------------------------------------------------
def test_parse_semantic_metadata_normalizza_liste_e_scarta_extra():
    raw = """```yaml
title: Un titolo
document_type: specifica tecnica
domain: INPS, SOAP
tags:
  - soap
  - datapower
authority: 0.99
```"""

    out = parse_semantic_metadata(raw)

    assert out["title"] == "Un titolo"
    assert out["domain"] == ["INPS", "SOAP"]          # stringa separata da virgole → lista
    assert out["tags"] == ["soap", "datapower"]
    assert "authority" not in out                      # campo normativo: mai dall'LLM


@pytest.mark.parametrize("raw", ["non è yaml: [", "- solo - una - lista", ""])
def test_parse_semantic_metadata_tollera_risposte_inutilizzabili(raw):
    assert parse_semantic_metadata(raw) == {}


def test_tag_incollati_in_un_solo_token_vengono_recuperati():
    """Il modello a volte produce un tag solo, lungo quanto una frase. Scartarlo lasciava
    il documento senza tag (osservato su Specifiche Tecniche WsProtocollo): quel token è
    già una lista, solo mal separata."""
    raw = "title: T\ntags: [fascicolo-protocolli-metadati-classificazione-amministrativa]\n"

    out = parse_semantic_metadata(raw)

    assert out["tags"] == ["fascicolo", "protocolli", "metadati", "classificazione",
                           "amministrativa"]


def test_voce_lunga_e_non_spezzabile_viene_scartata():
    raw = "title: T\ntags: ['una intera frase di descrizione senza alcun trattino dentro']\n"

    assert "tags" not in parse_semantic_metadata(raw)


# ---------------------------------------------------------------------------
# Congetture: il prompt le vieta, il modello ogni tanto le produce comunque
# ---------------------------------------------------------------------------
def test_segnaposto_ipotetico_diventa_cella_dichiarata_vuota():
    testo = ("| Esiti previsti | [Dettagli degli esiti] | [Da verificare nel documento completo] |\n"
             "| errore | [Dettagli dell'errore] | [Dettagli non specificati] |")

    out = strip_speculation(testo)

    assert "Da verificare" not in out and "non specificat" not in out
    assert out.count("—") == 4
    # La struttura della tabella resta intatta: stesse celle, stesse righe.
    assert [r.count("|") for r in out.splitlines()] == [4, 4]


def test_inciso_ipotetico_rimosso_lasciando_il_valore_vero():
    testo = ('| cf | Codice fiscale | Si (inferito da contesto tabella 55) |\n'
             '| Valore | Descrizione (inferita) |\n'
             '| out | `ProtocollaEntrataResponse` (inferito dal contesto standard) | - |')

    out = strip_speculation(testo)

    assert "| cf | Codice fiscale | Si |" in out
    assert "| Valore | Descrizione |" in out
    assert "`ProtocollaEntrataResponse` |" in out      # il valore vero resta
    assert "inferit" not in out


def test_nota_di_lettura_del_modello_rimossa():
    testo = ("## Sezione\n"
             "*(Nota sul nome della classe: sembra essere ripetuto erroneamente nel PDF)*\n"
             "Contenuto vero della sezione.")

    out = strip_speculation(testo)

    assert "Nota sul nome" not in out
    assert "Contenuto vero della sezione." in out
    assert "## Sezione" in out


def test_segnaposto_in_corsivo_trattato_come_quello_fra_quadre():
    """Ciò che distingue un riempitivo da un dato è la MARCATURA con cui il modello lo
    scrive: quadre o corsivo dicono "qui sto tappando un buco"."""
    testo = "| *Dettagli tabella non specificati nel testo* | *N/A* | N/D | Parametri di input. |"

    out = strip_speculation(testo)

    assert "Dettagli tabella" not in out and "*N/A*" not in out
    assert out.count("|") == 5                       # struttura della riga intatta
    assert "Parametri di input." in out


def test_lacuna_dichiarata_in_chiaro_non_viene_toccata():
    """"Non specificato" scritto in chiaro come valore di cella NON è una congettura: è la
    dichiarazione onesta di una lacuna, cioè esattamente ciò che il prompt chiede. Toglierla
    perderebbe informazione — la cella diventerebbe indistinguibile da una non compilata."""
    testo = "| — | — | Non specificato | Dati di output del metodo WSP: CreaContainer. |"

    assert strip_speculation(testo) == testo


def test_celle_lasciate_vuote_dal_sorgente_non_vengono_riempite():
    """Una cella in bianco è un dato del documento, non un residuo della pulizia:
    riempirla di trattini sarebbe riscrivere il sorgente."""
    testo = ("| Comp. DS |  |\n"
             "| DocumentId | string |  | L'identificativo del documento |")

    assert strip_speculation(testo) == testo


def test_inciso_editoriale_tolto_dai_titoli_ma_non_dal_corpo():
    """Nei titoli un "(Nota …)" è sempre un commento del modello, e il titolo diventa il
    nome della sezione con cui il chunk finisce nell'indice. Nel corpo invece una nota fra
    parentesi può benissimo venire dal documento sorgente: lì non si tocca."""
    testo = ("#### Parametri input: `ArchiviaDocumento` *(Nota sul nome della classe)*\n"
             "Il campo è obbligatorio (Nota: vale solo per le AOO abilitate).")

    out = strip_speculation(testo)

    assert out.splitlines()[0] == "#### Parametri input: `ArchiviaDocumento`"
    assert "(Nota: vale solo per le AOO abilitate)" in out


def test_strip_speculation_non_tocca_il_testo_legittimo():
    testo = ("## Requisiti\n\n"
             "| Campo | Tipo | Descrizione |\n"
             "| --- | --- | --- |\n"
             "| AppName | string | Identifica l'applicazione Consumer |\n\n"
             "La richiesta deve contenere l'header Identity (namespace `http://inps.it`).")

    assert strip_speculation(testo) == testo
    assert strip_speculation(strip_speculation(testo)) == strip_speculation(testo)


# ---------------------------------------------------------------------------
# refine_markdown
# ---------------------------------------------------------------------------
def test_refine_produce_titolo_semantico_e_sezioni():
    grezzo = "# nome-file-brutto\n\n" + "\n\n".join(
        f"Paragrafo {i} con contenuto da riformattare." for i in range(10))

    result = refine_markdown(grezzo, source_filename="doc.pdf", generate=_fake_llm(),
                             window_chars=200)

    assert result.markdown.startswith("# Specifiche del Custom SOAP Header")
    assert result.markdown.count("# ") >= 2               # titolo + almeno una sezione
    assert "nome-file-brutto" not in result.markdown      # H1 del convertitore sostituito
    assert result.semantic["document_type"] == "specifica tecnica"
    assert result.stats["windows"] >= 2


def test_finestra_riassunta_viene_scartata_a_favore_del_testo_pulito():
    """Il guardrail che conta: se il modello riassume invece di riformattare, la sua
    risposta si butta e si tiene il testo originale — grezzo ma completo."""
    grezzo = "\n\n".join(f"Requisito {i}: il campo {i} è obbligatorio." for i in range(20))

    def riassuntore(prompt: str) -> str:
        if "SOLO un blocco YAML" in prompt:
            return METADATA_YAML
        return "## Requisiti\n\nVari requisiti sui campi."

    result = refine_markdown(grezzo, source_filename="doc.pdf", generate=riassuntore,
                             window_chars=300)

    assert result.stats["windows_kept_raw"] == result.stats["windows"]
    for i in range(20):
        assert f"Requisito {i}:" in result.markdown


def test_finestra_gonfiata_di_commenti_viene_scartata():
    """L'altro lato del guardrail: una riscrittura molto più lunga dell'originale significa
    che il modello ha commentato invece di riformattare. Il riempitivo qui è volutamente
    NEUTRO: le congetture esplicite le toglie già strip_speculation, e un test che le usasse
    misurerebbe quel filtro invece della forbice di lunghezza."""
    grezzo = "\n\n".join(f"Campo {i}: string." for i in range(10))

    def commentatore(prompt: str) -> str:
        if "SOLO un blocco YAML" in prompt:
            return METADATA_YAML
        corpo = prompt.split("--- TESTO DA RIFORMATTARE ---")[1].split("--- FINE TESTO ---")[0]
        return corpo + "\n\n" + "Considerazioni aggiuntive sul campo e sul suo uso. " * 40

    result = refine_markdown(grezzo, source_filename="doc.pdf", generate=commentatore,
                             window_chars=200)

    assert result.stats["windows_kept_raw"] == result.stats["windows"]
    assert result.stats["windows_too_long"] == result.stats["windows"]
    assert "Considerazioni aggiuntive" not in result.markdown


def test_fonte_densa_ammette_espansione_maggiore_della_prosa():
    """Un albero di classi che diventa una tabella con colonna Descrizione cresce di 3-4×
    senza che una parola sia stata inventata: col tetto della prosa (2.0) quelle
    riscritture — proprio quelle che il passo esiste per produrre — verrebbero scartate."""
    denso = "\n".join(f"├─ Campo{i} : string" for i in range(60))
    prosa = "\n".join(
        f"Il campo numero {i} contiene una stringa e va valorizzato dal consumer "
        f"in ogni richiesta inviata al servizio." for i in range(20))

    def espansore(prompt: str) -> str:
        if "SOLO un blocco YAML" in prompt:
            return METADATA_YAML
        corpo = prompt.split("--- TESTO DA RIFORMATTARE ---")[1].split("--- FINE TESTO ---")[0]
        return "## Campi\n\n" + corpo * 3   # tre volte l'originale: né riassunto né loop

    denso_out = refine_markdown(denso, generate=espansore, window_chars=10_000)
    prosa_out = refine_markdown(prosa, generate=espansore, window_chars=10_000)

    assert denso_out.stats["windows_too_long"] == 0    # fonte densa: 3× è lecito
    assert prosa_out.stats["windows_too_long"] == prosa_out.stats["windows"]


def test_refine_documento_vuoto():
    with pytest.raises(RefineError):
        refine_markdown("   \n\n  ", generate=_fake_llm())


def test_errore_llm_diventa_refine_error():
    from core import llm

    def rotto(_prompt: str) -> str:
        raise llm.LLMError("[ERRORE DI CONNESSIONE]: Ollama non raggiungibile")

    with pytest.raises(RefineError, match="ERRORE DI CONNESSIONE"):
        refine_markdown("# Doc\n\nContenuto.", generate=rotto)


# ---------------------------------------------------------------------------
# Integrazione con lo staging: journal, rieseguibilità, approve
# ---------------------------------------------------------------------------
@pytest.fixture
def staging_dir(tmp_path, monkeypatch):
    base = tmp_path / "staging"
    monkeypatch.setattr(intake, "INTAKE_STAGING_DIR", base)
    return base


def _stage_txt(testo: str) -> dict:
    return intake.stage_document("sorgente.txt", testo.encode("utf-8"))


def _journal_lines(staging_dir: Path) -> list[dict]:
    text = (staging_dir / "intake.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_refine_staged_tiene_il_grezzo_e_aggiorna_la_preview(staging_dir):
    entry = _stage_txt("Titolo del documento\n\n" + "\n\n".join(
        f"Paragrafo {i} da riformattare con contenuto." for i in range(8)))
    grezzo = intake.get_preview(entry["id"])["markdown"]

    record = intake_refine.refine_staged_document(entry["id"], generate=_fake_llm())

    # Il grezzo non si perde: resta in staging e l'entry lo indica.
    assert (staging_dir / "docs" / record["files"]["markdown_raw"]).read_text(
        encoding="utf-8") == grezzo
    # La preview (che legge files.markdown) ora mostra il raffinato.
    assert intake.get_preview(entry["id"])["markdown"].startswith(
        "# Specifiche del Custom SOAP Header")
    assert record["semantic"]["document_type"] == "specifica tecnica"
    assert record["refine"]["windows"] >= 1
    # Il documento resta 'staged': la raffinazione non scavalca la review.
    assert record["status"] == "staged"
    assert _journal_lines(staging_dir)[-1]["id"] == entry["id"]


def test_refine_rieseguito_riparte_sempre_dal_grezzo(staging_dir):
    entry = _stage_txt("Titolo\n\n" + "\n\n".join(f"Paragrafo {i}." for i in range(6)))

    primo = intake_refine.refine_staged_document(entry["id"], generate=_fake_llm())
    secondo = intake_refine.refine_staged_document(entry["id"], generate=_fake_llm())

    assert secondo["files"]["markdown_raw"] == primo["files"]["markdown_raw"]
    raffinato = (staging_dir / "docs" / secondo["files"]["markdown"]).read_text(encoding="utf-8")
    # Nessuna riscrittura impilata sulla precedente: una sola sezione per finestra.
    assert raffinato.count("## Sezione riscritta") == secondo["refine"]["windows"]


def test_refine_su_documento_gia_processato(staging_dir):
    entry = _stage_txt("Titolo\n\nContenuto del documento.")
    intake.reject(entry["id"], "non serve")

    with pytest.raises(intake.DocumentAlreadyProcessedError):
        intake_refine.refine_staged_document(entry["id"], generate=_fake_llm())


def test_campi_semantici_finiscono_nel_frontmatter_approvato(staging_dir, tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    monkeypatch.setattr(intake, "DOCS_DIR", docs)
    entry = _stage_txt("Titolo\n\n" + "\n\n".join(f"Paragrafo {i} con testo." for i in range(6)))
    intake_refine.refine_staged_document(entry["id"], generate=_fake_llm())

    intake.approve(entry["id"], "05_project_specs", "spec.md",
                   docs_dir=docs, reindex=lambda _p: {"noop": True},
                   lock_path=tmp_path / "writer.lock")

    metadata, _body = parse_markdown_file(str(docs / "05_project_specs" / "spec.md"))
    assert metadata["title"] == "Specifiche del Custom SOAP Header"   # titolo semantico
    assert metadata["document_type"] == "specifica tecnica"
    assert metadata["domain"] == ["INPS", "SOAP", "DataPower"]
    assert metadata["tags"] == ["soap", "custom-header", "datapower"]
    # I campi normativi restano quelli calcolati da approve, mai quelli dell'LLM.
    assert metadata["id"] == "intake-spec-v1.0"
    assert metadata["classification"] == "REQUIREMENTS"
    assert metadata["status"] == "IMPORTED"

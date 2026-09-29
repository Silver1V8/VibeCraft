"""Test del chunking per sezione (core.chunking.chunk_markdown) e dello slug degli id."""
import typing
from pathlib import Path

from core import chunking as index


def test_split_preamble_and_sections():
    body = "# Titolo\nintro qui\n## Sezione A\ncorpo A\n## Sezione B\ncorpo B\n"
    chunks = index.chunk_markdown("docs/x.md", {"title": "Titolo"}, body)
    sections = [c["section"] for c in chunks]
    assert "(preambolo)" in sections          # testo prima del primo ##
    assert "Sezione A" in sections and "Sezione B" in sections
    for c in chunks:
        assert c["chunk_id"].startswith("docs/x.md#")
        assert c["doc_id"] == "docs/x.md"
        assert c["text"].startswith("# Titolo")  # ogni chunk è ancorato al titolo del documento


def test_stable_readable_ids():
    body = "## Concorrenza Critica\ncorpo\n## Immutabilità dei Log\ncorpo2\n"
    ids = [c["chunk_id"] for c in index.chunk_markdown("d.md", {}, body)]
    # id progressivi, con slug leggibile della sezione
    assert ids[0].startswith("d.md#00-")
    assert "concorrenza-critica" in ids[0]
    assert ids[1].startswith("d.md#01-")


def test_no_headings_single_chunk():
    chunks = index.chunk_markdown("d.md", {}, "solo testo senza alcun heading di livello 2")
    assert len(chunks) == 1
    assert chunks[0]["doc_id"] == "d.md"


def test_empty_sections_are_skipped():
    chunks = index.chunk_markdown("d.md", {"title": "T"}, "## Vuota\n\n## Piena\ncorpo")
    sections = [c["section"] for c in chunks]
    assert "Vuota" not in sections   # sezione senza corpo saltata
    assert "Piena" in sections


def test_sezione_lunga_diventa_parti_sotto_il_tetto_senza_perdere_testo():
    paragrafi = [f"Paragrafo {i} " + "parola " * 60 for i in range(40)]
    chunks = index.chunk_markdown("d.md", {"title": "T"}, "## Lunga\n" + "\n\n".join(paragrafi) + "\n## Breve\nx")
    parti = [c for c in chunks if c["section"] == "Lunga"]
    assert len(parti) > 1
    assert all(len(c["text"]) <= index.MAX_CHUNK_CHARS for c in chunks)
    assert parti[0]["chunk_id"] == "d.md#00-lunga" and parti[1]["chunk_id"] == "d.md#00-lunga-p02"
    assert parti[0]["text"].startswith(f"# T\n## Lunga (parte 1/{len(parti)})\n")
    corpo = "".join("".join(c["text"].split("\n", 2)[2].split()) for c in parti)
    assert corpo == "".join("".join(paragrafi).split())        # nessuna parola persa o duplicata
    assert chunks[-1]["chunk_id"] == "d.md#01-breve" and chunks[-1]["text"] == "# T\n## Breve\nx"


def test_parte_di_sottotitolo_e_blocco_di_codice_resta_autonoma():
    """Una continuazione ripete il `###` (così restates_only vede ancora il codice
    DICHIARATO nel titolo) e riapre il blocco ``` tagliato; una tabella ripete l'intestazione."""
    from core.retrieval import restates_only

    gherkin = "\n".join(f"  Then passo {i} rispetta [REGOLA-VAL-07]" for i in range(150))
    tabella = "| A | B |\n|---|---|\n" + "\n".join(f"| riga {i} | valore {i} |" for i in range(200))
    body = f"## S\n### `[REGOLA-VAL-07]` Validazione\n```gherkin\n{gherkin}\n```\n\n### Tabella\n{tabella}\n"
    parti = index.chunk_markdown("d.md", {}, body)
    assert len(parti) > 2
    for c in parti:
        assert len(c["text"]) <= index.MAX_CHUNK_CHARS
        assert c["text"].count("```") % 2 == 0
        assert not restates_only(c["text"])
    righe = [c for c in parti if "riga 150 " in c["text"]][0]["text"]
    assert "### Tabella (continua)\n| A | B |\n|---|---|" in righe


def test_tetto_dei_chunk_non_supera_i_tagli_dei_consumatori():
    from api.routes_retrieval import ASK_MAX_CHARS_PER_CHUNK
    from core.doc_generation import _GROUNDING_MAX_CHARS_PER_CHUNK

    assert index.MAX_CHUNK_CHARS <= min(ASK_MAX_CHARS_PER_CHUNK, _GROUNDING_MAX_CHARS_PER_CHUNK)


def test_slug_normalization():
    assert index._slug("Categoria 2 — Concorrenza!") == "categoria-2-concorrenza"


# ---------------------------------------------------------------------------
# Regressione: `from pathlib import Path` mancante in core/chunking.py. Con le
# annotazioni posticipate (PEP 649, default da Python 3.14) `read_document(filepath_obj:
# Path)` non falliva all'import né alla chiamata — solo una risoluzione ESPLICITA
# dell'annotazione (typing.get_type_hints, o un runtime più vecchio/una diversa
# configurazione di annotazioni) avrebbe sollevato NameError: 'Path' is not defined.
# ---------------------------------------------------------------------------
def test_read_document_annotation_resolves_path():
    hints = typing.get_type_hints(index.read_document)
    assert hints["filepath_obj"] is Path


def test_read_document_reads_txt_from_path_object(tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("hello world", encoding="utf-8")
    metadata, body = index.read_document(p)
    assert metadata == {}
    assert body == "hello world"
    assert index._slug("###") == "sez"  # fallback quando non resta nulla


def test_frontmatter_only_at_file_start(tmp_path):
    """Regressione: un doc SENZA frontmatter ma con righe orizzontali `---` e `:` nel testo
    non deve crashare né essere interpretato come YAML (bug: split('---') sull'intero file)."""
    doc = tmp_path / "piano.md"
    doc.write_text(
        "# Titolo\n\nPremessa con i due punti: eccoli.\n\n---\n\n## Sezione\ncorpo\n",
        encoding="utf-8",
    )
    meta, body = index.parse_markdown_file(str(doc))
    assert meta == {}                     # nessun frontmatter riconosciuto
    assert "## Sezione" in body           # corpo intatto, incluso il separatore
    assert "Premessa con i due punti" in body


def test_unterminated_frontmatter_is_not_frontmatter(tmp_path):
    """Regressione 2026-07-22 (brief WSProtocollo scartato): frontmatter APERTO e mai
    chiuso. `split("---")` chiudeva il blocco alla prima occorrenza di `---` ovunque nel
    testo, così il corpo Markdown finiva dentro il YAML e la prima riga di elenco
    `-   **Progetto Core**: ...` faceva esplodere yaml.safe_load (ScannerError: `*` apre
    un alias YAML). Senza riga di chiusura NON c'è frontmatter: corpo intero, zero crash."""
    doc = tmp_path / "brief.md"
    doc.write_text(
        "---\ntitle: Project brief backend\nscope: sintesi\n\n"
        "# Project brief\n\n## Componenti\n\n"
        "-   **Progetto Core**: `WSProtocollo` è il servizio principale\n",
        encoding="utf-8",
    )
    meta, body = index.parse_markdown_file(str(doc))
    assert meta == {}
    assert "**Progetto Core**" in body and "## Componenti" in body


def test_frontmatter_closed_by_dots_delimiter(tmp_path):
    """`...` è la chiusura alternativa di un documento YAML: vale come `---`."""
    doc = tmp_path / "spec.md"
    doc.write_text("---\ntitle: X\n...\n# Titolo\ncorpo\n", encoding="utf-8")
    meta, body = index.parse_markdown_file(str(doc))
    assert meta == {"title": "X"}
    assert body.startswith("# Titolo")


def test_frontmatter_non_mapping_counts_as_absent(tmp_path):
    """Un frontmatter che non è un mapping (scalare, lista) non deve arrivare a
    chunk_markdown come metadata: vale come assente, mai come dict finto."""
    doc = tmp_path / "strano.md"
    doc.write_text("---\nsolo una frase\n---\n# T\ncorpo\n", encoding="utf-8")
    meta, body = index.parse_markdown_file(str(doc))
    assert meta == {}
    assert "corpo" in body


def test_frontmatter_parsed_when_delimited_at_top(tmp_path):
    """Il frontmatter valido (delimitato in cima) continua a essere estratto, corpo con `---` incluso."""
    doc = tmp_path / "spec.md"
    doc.write_text(
        "---\nstatus: ENFORCED\nclassification: IRON_MEMORY\n---\n# Titolo\ncorpo\n\n---\n## Coda\nx\n",
        encoding="utf-8",
    )
    meta, body = index.parse_markdown_file(str(doc))
    assert meta["status"] == "ENFORCED" and meta["classification"] == "IRON_MEMORY"
    assert "# Titolo" in body and "## Coda" in body   # separatore `---` nel corpo preservato


# ---------------------------------------------------------------------------
# core.chunking.extract_entities — vaglio dei riferimenti citati fra quadre.
#
# Regressione 2026-07-22: la versione precedente era `re.findall(r"\[(.*?)]", text)`,
# che catturava QUALSIASI cosa fra parentesi quadre. Sul corpus reale produceva 22 nodi
# entità spuri su 109 token (checkbox Markdown, destrutturazioni JS, classi regex, testo
# dei link, segnaposto dei template, wildcard citate nella prosa), gonfiando gli archi
# MENTIONS e sporcando Semantic Map e query di impatto.
# ---------------------------------------------------------------------------
def test_extract_entities_riconosce_regole_ed_entita():
    body = "Vedi [REGOLA-VAL-07] e [SAFEGUARD-TXN-01] per l'entità [AUDIT_LOG]."
    assert index.extract_entities(body) == ["REGOLA-VAL-07", "SAFEGUARD-TXN-01", "AUDIT_LOG"]


def test_extract_entities_accetta_identificatori_fra_backtick():
    """I titoli dei documenti citano le regole come `[REGOLA-HITL-01]`: il backtick
    singolo è la convenzione, non un blocco di codice. Ignorarlo perderebbe riferimenti
    veri (in vibe_coding_workflow le famiglie HITL e PROC compaiono SOLO così)."""
    assert index.extract_entities("### `[REGOLA-HITL-01]` Checkpoint") == ["REGOLA-HITL-01"]


def test_extract_entities_ignora_blocchi_di_codice():
    body = (
        "Testo con [REGOLA-OBS-06].\n"
        "```javascript\n"
        "const PII = [ /* <<CAMPI_PII>> */ ];\n"
        "Object.entries(o).map(([k, v]) => [k, '[REDACTED]']);\n"
        "```\n"
        "```bash\ngrep -rn \"<<[A-Z_]*>>\" docs/\n```\n"
    )
    assert index.extract_entities(body) == ["REGOLA-OBS-06"]


def test_extract_entities_ignora_testo_dei_link_markdown():
    body = "Vedi [`00_meta/safeguards_security.md`](00_meta/safeguards_security.md) e [REGOLA-API-01]."
    assert index.extract_entities(body) == ["REGOLA-API-01"]


def test_extract_entities_ignora_checkbox_markdown():
    assert index.extract_entities("- [ ] voce da fare\n- [x] voce fatta\n") == []


def test_extract_entities_scarta_segnaposto_e_wildcard():
    """I template mostrano il FORMATO di un identificatore, non un identificatore: devono
    restare fuori dal grafo. Discriminante: l'ultimo segmento di una regola vera è numerico."""
    body = "Formato [PREFISSO-CATEGORIA-XX], es. [REGOLA-XXX-NN] o [SAFEGUARD-YYY-NN]. "
    body += "Le famiglie [REGOLA-*] e [SAFEGUARD-*] sono chiavi di grafo."
    assert index.extract_entities(body) == []


def test_extract_entities_deduplica_preservando_l_ordine():
    body = "[REGOLA-API-04] poi [SAFEGUARD-SEC-03] poi ancora [REGOLA-API-04]."
    assert index.extract_entities(body) == ["REGOLA-API-04", "SAFEGUARD-SEC-03"]


def test_le_librerie_dei_lettori_di_documenti_sono_dichiarate():
    """read_document supporta .docx/.xlsx/.pdf, e ciascun formato importa una libreria
    diversa. Finche' quegli import stavano dentro un try/except che degradava a stringa
    vuota, una dipendenza NON dichiarata non faceva fallire nulla: il documento veniva
    indicizzato VUOTO con una riga di warning, indistinguibile a valle da un documento
    davvero senza testo.

    E' successo davvero: pypdf non era in pyproject.toml ne' nel lock ne' installata, e
    openpyxl arrivava solo come transitiva di markitdown, cioe' funzionava per fortuna
    (rag/AUDIT.md, A19). Questo test fallisce nel momento esatto in cui una di loro esce
    dalle dipendenze, invece di lasciare che il difetto si manifesti come corpus vuoto."""
    import docx        # noqa: F401  (.docx)
    import openpyxl    # noqa: F401  (.xlsx)
    import pypdf       # noqa: F401  (.pdf)


def test_pdf_illeggibile_solleva_invece_di_restituire_vuoto(tmp_path):
    """Il rovescio del test sopra: rimosso il try/except, un errore VERO deve emergere.
    Un file che finisce in .pdf ma non e' un PDF non puo' produrre un chunk vuoto in
    silenzio, perche' quel chunk finirebbe nell'indice come documento senza testo."""
    import pytest

    from core.chunking import read_document

    finto = tmp_path / "non_e_un_pdf.pdf"
    finto.write_bytes(b"questo non e' un PDF")

    with pytest.raises(Exception):
        read_document(finto)

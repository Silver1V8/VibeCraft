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

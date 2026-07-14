"""Test del chunking per sezione (core.chunking.chunk_markdown) e dello slug degli id."""
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

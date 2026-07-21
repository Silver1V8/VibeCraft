"""Test dei convertitori multi-formato → Markdown per Intake & Import (S1, piano:
docs/00_meta_governance/piano_intake_import.md). Copre i 4 formati (pdf/docx/html/txt),
la compatibilità con core/chunking.py::parse_markdown_file e chunk_markdown, e gli edge
case elencati nel piano (file vuoto, PDF senza testo, HTML senza body, encoding non
UTF-8, formato non ammesso)."""
import hashlib
from pathlib import Path

import pymupdf
import pytest

from core.chunking import chunk_markdown, parse_markdown_file
from core.intake_convert import ConversionError, convert_to_markdown

FIXTURES = {
    "pdf": "tests/fixtures/intake/sample.pdf",
    "docx": "tests/fixtures/intake/sample.docx",
    "html": "tests/fixtures/intake/sample.html",
    "txt": "tests/fixtures/intake/sample.txt",
}


def _assert_chunkable(markdown: str, rel_path: str, tmp_path):
    """Scrive il markdown su disco e verifica che parse_markdown_file + chunk_markdown
    lo digeriscano senza errori, producendo almeno una sezione non vuota."""
    md_path = tmp_path / rel_path
    md_path.write_text(markdown, encoding="utf-8")

    metadata, body = parse_markdown_file(str(md_path))
    chunks = chunk_markdown(rel_path, metadata, body)

    assert len(chunks) >= 1
    assert any(chunk["text"].strip() for chunk in chunks)


@pytest.mark.parametrize("formato,path", FIXTURES.items())
def test_convert_fixture_produces_chunkable_markdown(formato, path, tmp_path):
    result = convert_to_markdown(Path(path), formato)

    assert result.markdown.strip()
    _assert_chunkable(result.markdown, f"doc.{formato}.md", tmp_path)


@pytest.mark.parametrize("formato,path", FIXTURES.items())
def test_convert_fixture_metadata(formato, path):
    src = Path(path)
    expected_sha = hashlib.sha256(src.read_bytes()).hexdigest()

    result = convert_to_markdown(src, formato)

    assert result.metadata["source_filename"] == src.name
    assert result.metadata["sha256"] == expected_sha
    assert result.metadata["formato"] == formato
    assert result.metadata["converted_at"]
    assert result.metadata["n_chars"] == len(result.markdown)


def test_docx_headings_become_markdown_headings():
    result = convert_to_markdown(Path(FIXTURES["docx"]), "docx")

    assert "# Titolo DOCX di prova" in result.markdown
    assert "## Sezione seconda" in result.markdown


def test_html_strips_script_nav_footer():
    result = convert_to_markdown(Path(FIXTURES["html"]), "html")

    assert "da scartare" not in result.markdown
    assert "Titolo HTML di prova" in result.markdown


# --- Edge case: file vuoto o illeggibile -----------------------------------------


@pytest.mark.parametrize("formato", ["pdf", "docx", "html", "txt"])
def test_empty_file_raises_conversion_error(formato):
    with pytest.raises(ConversionError, match="vuoto"):
        convert_to_markdown(b"", formato, filename=f"vuoto.{formato}")


# --- Edge case: PDF senza testo estraibile (solo immagini) -----------------------


def test_pdf_without_extractable_text_raises_conversion_error():
    doc = pymupdf.open()
    doc.new_page()  # pagina bianca, nessun testo inserito
    pdf_bytes = doc.tobytes()
    doc.close()

    with pytest.raises(ConversionError, match="nessun testo estraibile"):
        convert_to_markdown(pdf_bytes, "pdf", filename="senza_testo.pdf")


# --- Edge case: HTML senza <body> -------------------------------------------------


def test_html_without_body_raises_conversion_error():
    html = b"<html><head><title>Senza body</title></head></html>"

    with pytest.raises(ConversionError, match="senza <body>"):
        convert_to_markdown(html, "html", filename="senza_body.html")


# --- Edge case: encoding non UTF-8 nel TXT (fallback latin-1) ---------------------


def test_txt_latin1_fallback():
    data = "Città, perché, università".encode("latin-1")

    result = convert_to_markdown(data, "txt", filename="latin1.txt")

    assert "Città" in result.markdown
    assert "perché" in result.markdown


# --- Edge case: formato non in allowed_formats → rifiuto a monte -----------------


def test_disallowed_format_is_rejected_upfront():
    with pytest.raises(ConversionError, match="non supportato"):
        convert_to_markdown(b"qualsiasi contenuto", "pptx", filename="file.pptx")

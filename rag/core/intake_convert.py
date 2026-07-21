"""Conversione documenti multi-formato in Markdown per l'evoluzione Intake & Import
(piano: docs/00_meta_governance/piano_intake_import.md, sessione S1). Logica pura: nessuna
scrittura su disco né in staging/docs/ — core/intake.py (S2) chiamerà convert_to_markdown
prima di salvare il .md derivato e i metadata in un frontmatter (qui i metadata restano
separati, non ancora fusi nel markdown)."""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import docx
import mammoth
import pymupdf
from bs4 import BeautifulSoup
from markdownify import markdownify as _html_to_markdown

from core.config import INTAKE_ALLOWED_FORMATS


class ConversionError(RuntimeError):
    """Sollevato quando un documento sorgente non può essere convertito in Markdown:
    formato non ammesso, file vuoto/illeggibile, nessun testo estraibile, encoding
    irriconoscibile. Mai lasciar propagare l'eccezione grezza della libreria sottostante."""


@dataclass(frozen=True)
class ConversionResult:
    markdown: str
    metadata: dict


def _decode_text(data: bytes, nome_file: str) -> str:
    """UTF-8 con fallback latin-1 (i .txt di provenienza Windows/legacy spesso non sono
    UTF-8 validi): solo se anche latin-1 fallisce l'encoding è davvero irriconoscibile,
    perché latin-1 mappa ogni singolo byte a un carattere."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise ConversionError(f"encoding non riconosciuto per {nome_file}") from exc


def _convert_txt(data: bytes, nome_file: str) -> str:
    body = _decode_text(data, nome_file).strip()
    title = Path(nome_file).stem
    return f"# {title}\n\n{body}\n"


def _convert_pdf(data: bytes, nome_file: str) -> str:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # libreria non tipizza le eccezioni di parsing
        raise ConversionError(f"PDF illeggibile: {nome_file} ({exc})") from exc
    try:
        pages = [(page.get_text() or "").strip() for page in doc]
    finally:
        doc.close()
    body = "\n\n".join(p for p in pages if p)
    if not body:
        raise ConversionError(f"nessun testo estraibile da {nome_file}")
    title = Path(nome_file).stem
    return f"# {title}\n\n{body}\n"


def _convert_docx_mammoth(data: bytes) -> str:
    result = mammoth.convert_to_markdown(io.BytesIO(data))
    return result.value.strip()


def _convert_docx_fallback(data: bytes, nome_file: str) -> str:
    """Fallback su python-docx quando mammoth non riesce ad aprire il file: i titoli
    Word (stile 'Heading N') diventano heading Markdown, il resto testo semplice."""
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ConversionError(f"DOCX illeggibile: {nome_file} ({exc})") from exc
    lines: list[str] = []
    for p in document.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style = p.style.name if p.style else ""
        if style == "Heading 1":
            lines.append(f"# {text}")
        elif style and style.startswith("Heading"):
            lines.append(f"## {text}")
        else:
            lines.append(text)
    return "\n\n".join(lines)


def _convert_docx(data: bytes, nome_file: str) -> str:
    try:
        markdown = _convert_docx_mammoth(data)
    except Exception:
        markdown = ""
    if not markdown:
        markdown = _convert_docx_fallback(data, nome_file)
    return markdown


def _convert_html(data: bytes, nome_file: str) -> str:
    text = _decode_text(data, nome_file)
    soup = BeautifulSoup(text, "html.parser")
    if soup.body is None:
        raise ConversionError(f"HTML senza <body>: {nome_file}")
    for tag in soup.body.find_all(["script", "style", "nav", "footer"]):
        tag.decompose()
    return _html_to_markdown(str(soup.body), heading_style="ATX").strip()


_CONVERTERS: dict[str, Callable[[bytes, str], str]] = {
    "pdf": _convert_pdf,
    "docx": _convert_docx,
    "html": _convert_html,
    "txt": _convert_txt,
}


def convert_to_markdown(
    source: bytes | Path, formato: str, filename: str | None = None
) -> ConversionResult:
    """Converte un documento sorgente (bytes o Path) in Markdown. `formato` è
    l'estensione dichiarata (pdf/docx/html/txt), validata contro
    intake.allowed_formats (rag_config.yaml) PRIMA di leggere il contenuto.
    `filename` è il nome originale, usato per i metadata e i messaggi d'errore;
    se `source` è un Path e `filename` è assente, si usa il nome del Path."""
    fmt = formato.lower().lstrip(".")
    if fmt not in INTAKE_ALLOWED_FORMATS:
        raise ConversionError(
            f"formato non supportato: {formato!r} (ammessi: {', '.join(INTAKE_ALLOWED_FORMATS)})"
        )

    if isinstance(source, Path):
        try:
            data = source.read_bytes()
        except OSError as exc:
            raise ConversionError(f"impossibile leggere il file sorgente: {exc}") from exc
        nome_file = filename or source.name
    else:
        data = source
        nome_file = filename or f"documento.{fmt}"

    if not data:
        raise ConversionError(f"file vuoto: {nome_file}")

    converter = _CONVERTERS.get(fmt)
    if converter is None:
        raise ConversionError(f"nessun convertitore per il formato {fmt!r}")

    markdown = converter(data, nome_file)
    if not markdown.strip():
        raise ConversionError(f"nessun testo estraibile da {nome_file}")

    metadata = {
        "source_filename": nome_file,
        "sha256": hashlib.sha256(data).hexdigest(),
        "formato": fmt,
        "converted_at": datetime.now(timezone.utc).isoformat(),
        "n_chars": len(markdown),
    }
    return ConversionResult(markdown=markdown, metadata=metadata)

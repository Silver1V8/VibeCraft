"""Conversione documenti multi-formato in Markdown per l'evoluzione Intake & Import
(piano: docs/00_meta_governance/piano_intake_import.md, sessione S1). Logica pura: nessuna
scrittura su disco né in staging/docs/ — core/intake.py (S2) chiama convert_to_markdown
prima di salvare il .md derivato e i metadata in un frontmatter (qui i metadata restano
separati, non ancora fusi nel markdown).

Il motore di conversione è microsoft/markitdown: UN solo convertitore per TUTTI i formati
non-Markdown (pdf, docx, pptx, xlsx/xls, html, csv, json, xml, epub, msg, ...). I .md NON
passano da qui: sono gestiti nativamente da core/intake.py (solo decodifica, nessuna
conversione). markitdown è permissivo (per estensioni ignote ripiega su plaintext), quindi
la whitelist dei formati resta la nostra (INTAKE_ALLOWED_FORMATS), applicata a monte."""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from markitdown import MarkItDown, StreamInfo
from markitdown._exceptions import MarkItDownException

from core.config import INTAKE_ALLOWED_FORMATS


class ConversionError(RuntimeError):
    """Sollevato quando un documento sorgente non può essere convertito in Markdown:
    formato non ammesso, file vuoto/illeggibile, nessun testo estraibile. Mai lasciar
    propagare l'eccezione grezza di markitdown (MarkItDownException e sottoclassi)."""


@dataclass(frozen=True)
class ConversionResult:
    markdown: str
    metadata: dict


# markitdown carica un modello magika (onnx) alla PRIMA istanza: costoso, quindi una sola
# istanza per processo, creata pigramente (nessun costo al solo import del modulo, coerente
# con la filosofia lazy del resto di core/). enable_plugins=False: niente plugin di terze
# parti, conversione deterministica coi soli convertitori built-in.
_markitdown: MarkItDown | None = None


def _engine() -> MarkItDown:
    global _markitdown
    if _markitdown is None:
        _markitdown = MarkItDown(enable_plugins=False)
    return _markitdown


# Un heading Markdown in QUALSIASI punto del documento (non solo in cima): se markitdown
# non ne produce (tipico di pdf/txt/csv), anteponiamo un titolo dal nome file, così ogni
# documento resta ancorato a un titolo leggibile per il chunking.
_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)

# Formati basati su testo: la rilevazione automatica dell'encoding di markitdown
# (charset-normalizer) sbaglia su campioni brevi di testo legacy (cp1252/latin-1 italiano
# viene decodificato come un'altra codepage). Per questi determiniamo l'encoding noi con la
# stessa strategia storica (UTF-8, poi fallback latin-1 che mappa ogni byte) e lo passiamo
# come hint a markitdown, che lo rispetta invece di indovinare. Per i formati binari
# (pdf/docx/xlsx/...) l'encoding non si applica: charset=None.
_TEXT_FORMATS = frozenset({"txt", "csv", "json", "xml", "html", "htm"})


def _detect_charset(data: bytes) -> str:
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def convert_to_markdown(
    source: bytes | Path, formato: str, filename: str | None = None
) -> ConversionResult:
    """Converte un documento sorgente (bytes o Path) in Markdown con markitdown.
    `formato` è l'estensione dichiarata, validata contro intake.allowed_formats
    (rag_config.yaml) PRIMA di leggere il contenuto — i .md non passano di qui (sono
    nativi in core/intake.py). `filename` è il nome originale, usato per i metadata, il
    titolo di fallback e i messaggi d'errore; se `source` è un Path e `filename` è
    assente, si usa il nome del Path."""
    fmt = formato.lower().lstrip(".")
    if fmt not in INTAKE_ALLOWED_FORMATS:
        raise ConversionError(
            f"formato non supportato: {formato!r} (ammessi: {', '.join(INTAKE_ALLOWED_FORMATS)})"
        )
    if fmt == "md":
        raise ConversionError(
            "i documenti .md sono gestiti nativamente, non passano da markitdown"
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

    charset = _detect_charset(data) if fmt in _TEXT_FORMATS else None
    stream_info = StreamInfo(extension=f".{fmt}", filename=nome_file, charset=charset)
    try:
        result = _engine().convert_stream(io.BytesIO(data), stream_info=stream_info)
    except MarkItDownException as exc:
        raise ConversionError(f"conversione fallita per {nome_file}: {exc}") from exc

    markdown = (result.text_content or "").strip()
    if not markdown:
        raise ConversionError(f"nessun testo estraibile da {nome_file}")

    # Titolo di fallback solo se il documento non ha alcun heading (pdf/txt/csv...): i
    # formati che li producono (docx/html) restano intatti, niente doppio titolo.
    if not _HEADING_RE.search(markdown):
        markdown = f"# {Path(nome_file).stem}\n\n{markdown}"

    metadata = {
        "source_filename": nome_file,
        "sha256": hashlib.sha256(data).hexdigest(),
        "formato": fmt,
        "converted_at": datetime.now(timezone.utc).isoformat(),
        "n_chars": len(markdown),
    }
    return ConversionResult(markdown=markdown, metadata=metadata)

"""Conversione documenti multi-formato in Markdown per l'evoluzione Intake & Import
(piano: docs/00_meta_governance/piano_intake_import.md, sessione S1). Logica pura: nessuna
scrittura su disco — core/intake.py salva originale e .md derivato in staging/.

Matrice dei motori, misurata sulla versione INSTALLATA (docling 2.126.0, markitdown 0.1.7;
rag/adr/NOTA_IMPLEMENTAZIONE_MIGLIORIE.md):

    md                               nativo: non passa di qui (core/intake.py, solo decodifica)
    pdf                              Docling se intake.docling.enabled, altrimenti MarkItDown
    xlsx, xls                        lettura diretta: openpyxl, xlrd (core/intake_excel.py)
    altri formati di allowed_formats MarkItDown
    doc, ppt                         LibreOffice (profilo blindato) -> docx, pptx, poi le righe sopra

Scelta per formato sugli stessi input e dopo il cleaner reale (confronto riproducibile in
archive/eval-results/verifica_finale_20260910/). Fogli di calcolo (archive/eval-results/
excel_diretto_20260911/): MarkItDown passa da pandas, che svuota le celle letterali «NA»/
«N/A»/«null» e scrive 7.0 e NaN; Docling divide in più tabelle una riga con celle vuote
intermedie; LibreOffice, per gli XLS, arrotonda i numeri memorizzati a 15 cifre e trasforma i
booleani in numeri. La lettura diretta conserva valori memorizzati e coordinate, senza inferire
tabelle, e non ha ripieghi. DOCX: esito ambiguo (Docling rende meglio
un titolo in stile Title, ma porta a `##` un titolo in Heading 1), resta MarkItDown. PPTX:
MarkItDown conserva le note del relatore. CSV: Docling fallisce sul `;` latin-1. HTML e EPUB
alla pari; TXT, JSON, XML, MSG solo MarkItDown. DOC/PPT: LibreOffice li porta al
formato moderno e poi vale la riga di quello (archive/eval-results/libreoffice_20260910/).
Configurazione dei PDF = quella del pilot finale:
StandardPdfPipeline, CPU esplicita, TableFormer ACCURATE con cell matching, testo del backend,
gerarchia dei titoli dallo stile (heading_hierarchy + parsed pages), niente VLM/Granite, niente
servizi remoti, pesi locali verificati per SHA-256. L'OCR locale (RapidOCR) si accende SOLO se
almeno una pagina non ha testo selezionabile: mai su un PDF digitale già estraibile.

Se Docling non è disponibile o fallisce, il PDF passa da MarkItDown con un fallback
DICHIARATO (metadata `fallback` + avviso), mai presentato come conversione equivalente. Il
routing normale di un formato non coperto a MarkItDown non è un fallback.

L'uscita di MarkItDown passa per core/intake_clean.clean_markdown (arredo di impaginazione);
quella di Docling, già strutturata e senza testate né piè di pagina, solo per normalize_markdown:
le regole di arredo toglierebbero righe di contenuto. La ristrutturazione semantica resta un
passo opt-in della review (core/intake_refine.py)."""
from __future__ import annotations

import hashlib
import importlib.metadata
import io
import logging
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from markitdown import MarkItDown, StreamInfo
from markitdown._exceptions import MarkItDownException

from core.config import (
    INTAKE_ALLOWED_FORMATS,
    INTAKE_DOCLING_ENABLED,
    INTAKE_DOCLING_MODELS_DIR,
    INTAKE_DOCLING_TIMEOUT_SECONDS,
    INTAKE_LIBREOFFICE_COMMAND,
    INTAKE_LIBREOFFICE_ENABLED,
    INTAKE_LIBREOFFICE_TIMEOUT_SECONDS,
)
from core.intake_clean import _DATA_URI_IMAGE_RE, clean_markdown, normalize_markdown

logger = logging.getLogger(__name__)


class ConversionError(RuntimeError):
    """Sollevato quando un documento sorgente non può essere convertito in Markdown:
    formato non ammesso, file vuoto/illeggibile, nessun testo estraibile. Mai lasciar
    propagare l'eccezione grezza del motore."""


class DoclingUnavailableError(RuntimeError):
    """Docling non usabile in questo processo: dipendenza non importabile, pesi mancanti o
    diversi da quelli verificati. Non è un difetto del documento: convert_to_markdown
    ripiega su MarkItDown e lo dichiara."""


@dataclass(frozen=True)
class ConversionResult:
    markdown: str
    metadata: dict


DOCLING_FORMATS = frozenset({"pdf"})
# Fogli di calcolo: lettura diretta dell'originale (core/intake_excel.py), motore per formato.
EXCEL_FORMATS = {"xlsx": "openpyxl", "xls": "xlrd"}

# Pesi effettivi della catena verificata: layout Heron @8f39ad3c e TableFormer ACCURATE di
# docling-models v2.3.0 @fc0f2d45 (pilot finale), RapidOCR 3.9.2 PP-OCRv6 per l'OCR `it`.
# Percorso relativo a intake.docling.models_dir -> SHA-256: un peso diverso è una catena
# diversa da quella provata. scripts/docling_models.py li scarica a queste revisioni.
DOCLING_WEIGHTS = {
    "docling-project--docling-layout-heron/model.safetensors":
        "00333a43451945aaf89db8ca9c0a17e75d1537c17db60fdb91aa95f4c7929e0c",
    "docling-project--docling-models/model_artifacts/tableformer/accurate/"
    "tableformer_accurate.safetensors":
        "2a7d6c924b3cd12fb99a09280ca9c33a89c5d60b93253617d2e088c1a40374d9",
}
OCR_WEIGHTS = {
    "RapidOcr/PP-OCRv6_det_small.onnx":
        "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f",
    "RapidOcr/PP-OCRv6_rec_small.onnx":
        "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884",
    "RapidOcr/ch_ppocr_mobile_v2.0_cls_mobile.onnx":
        "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
}
OCR_LANG = "it"

# Sotto questa soglia di caratteri (spazi esclusi) una pagina non ha testo selezionabile:
# è una scansione o un'immagine, e il suo contenuto arriva solo dall'OCR.
_MIN_PAGE_CHARS = 20


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


# Un convertitore Docling per modalità OCR, creato al primo PDF: import e caricamento dei
# modelli costano decine di secondi e ~1,6 GB di RSS, mai all'import. Docling non documenta
# la conversione come thread-safe: creazione e conversioni passano tutte da questo lock.
# ponytail: conversioni PDF seriali per processo; un pool se il volume di upload lo chiede.
_docling_lock = threading.Lock()
_docling_converters: dict[bool, object] = {}
_weights_ok: set[Path] = set()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_weights(weights: dict[str, str]) -> None:
    for rel, expected in weights.items():
        path = INTAKE_DOCLING_MODELS_DIR / rel
        if path in _weights_ok:
            continue
        if not path.is_file():
            raise DoclingUnavailableError(
                f"peso mancante: {path} (scaricalo con `uv run python scripts/docling_models.py`)")
        if sha256_file(path) != expected:
            raise DoclingUnavailableError(f"peso diverso da quello verificato (SHA-256): {path}")
        _weights_ok.add(path)


def _docling_converter(ocr: bool):
    converter = _docling_converters.get(ocr)
    if converter is not None:
        return converter
    try:
        from docling.backend.docling_parse_backend import ThreadedDoclingParseDocumentBackend
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            HeadingHierarchyOptions,
            PdfPipelineOptions,
            RapidOcrOptions,
            TableFormerMode,
            TableStructureOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
    except ImportError as exc:
        raise DoclingUnavailableError(f"docling non importabile: {exc}") from exc
    _verify_weights(DOCLING_WEIGHTS | (OCR_WEIGHTS if ocr else {}))
    options = PdfPipelineOptions(
        artifacts_path=INTAKE_DOCLING_MODELS_DIR,
        accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU),
        enable_remote_services=False,
        do_table_structure=True,
        table_structure_options=TableStructureOptions(mode=TableFormerMode.ACCURATE,
                                                      do_cell_matching=True),
        force_backend_text=True,
        generate_parsed_pages=True,
        heading_hierarchy_options=HeadingHierarchyOptions(enabled=True),
        do_ocr=ocr,
        ocr_options=RapidOcrOptions(lang=[OCR_LANG], backend="onnxruntime"),
        do_code_enrichment=False,
        do_formula_enrichment=False,
        do_picture_description=False,
        do_picture_classification=False,
        document_timeout=INTAKE_DOCLING_TIMEOUT_SECONDS or None,
    )
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(
            pipeline_cls=StandardPdfPipeline, pipeline_options=options,
            backend=ThreadedDoclingParseDocumentBackend)},
    )
    _docling_converters[ocr] = converter
    return converter


def engine_version(motore: str) -> str | None:
    """Versione installata del motore (`docling`, `markitdown`, `openpyxl`); None per `nativo`."""
    try:
        return importlib.metadata.version(motore)
    except importlib.metadata.PackageNotFoundError:
        return None


def _pdf_text_per_page(data: bytes, nome_file: str) -> list[int]:
    """Caratteri (spazi esclusi) del livello di testo di ogni pagina, letti con pypdf: dice
    PRIMA della conversione se il PDF è digitale o contiene pagine da riconoscere con l'OCR."""
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        # Cifrato con password vuota (solo permessi): leggibile. Con una password vera no, e
        # va detto in chiaro: non è un file danneggiato.
        if reader.is_encrypted and not reader.decrypt(""):
            raise ConversionError(f"PDF protetto da password: {nome_file} — rimuovi la "
                                  f"protezione e ricaricalo")
        return [len("".join((page.extract_text() or "").split())) for page in reader.pages]
    except ConversionError:
        raise
    except Exception as exc:  # pypdf solleva tipi diversi a seconda del danno
        raise ConversionError(
            f"PDF illeggibile o danneggiato: {nome_file} ({type(exc).__name__}: {exc})") from exc


def _docling_errors(result) -> str:
    return "; ".join(str(e.error_message) for e in result.errors)[:300] or "nessun dettaglio"


def _convert_pdf_docling(data: bytes, nome_file: str, pagine: list[int]) -> tuple[str, list[str], bool]:
    """Markdown, avvisi e uso dell'OCR. ConversionError se il documento non ha testo nemmeno
    con l'OCR; qualunque altra eccezione è un guasto del motore (il chiamante ripiega)."""
    senza_testo = sum(1 for n in pagine if n < _MIN_PAGE_CHARS)
    ocr = senza_testo > 0
    with _docling_lock:
        converter = _docling_converter(ocr)
        from docling.datamodel.base_models import ConversionStatus, DocumentStream
        result = converter.convert(DocumentStream(name=nome_file, stream=io.BytesIO(data)),
                                   raises_on_error=False)
    if result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
        raise RuntimeError(f"Docling: conversione {result.status.value} ({_docling_errors(result)})")
    doc = result.document
    markdown = normalize_markdown(
        doc.export_to_markdown(escape_underscores=False, image_placeholder=""))
    avvisi: list[str] = []
    if result.status == ConversionStatus.PARTIAL_SUCCESS:
        if result.has_timeout_errors():
            avvisi.append(f"Conversione interrotta dopo {INTAKE_DOCLING_TIMEOUT_SECONDS:g} s "
                          f"(timeout): il Markdown è INCOMPLETO, mancano le pagine non elaborate.")
        else:
            avvisi.append(f"Docling ha convertito il documento solo in parte "
                          f"({_docling_errors(result)}): il Markdown può essere incompleto.")
    if ocr:
        avvisi.append(f"{senza_testo} pagine su {len(pagine)} senza testo selezionabile "
                      f"(scansione o immagine): testo riconosciuto con OCR locale. Controlla "
                      f"parole, numeri e accenti prima di approvare.")
    if doc.pictures:
        avvisi.append(f"{len(doc.pictures)} immagini o figure non sono incluse nel Markdown: "
                      f"restano solo nell'originale conservato in staging.")
    if not markdown:
        if ocr and senza_testo == len(pagine):
            raise ConversionError(f"nessun testo estraibile da {nome_file}: nessuna pagina ha "
                                  f"testo selezionabile e l'OCR locale non ha riconosciuto testo")
        if result.status == ConversionStatus.PARTIAL_SUCCESS and result.has_timeout_errors():
            raise RuntimeError(f"timeout di {INTAKE_DOCLING_TIMEOUT_SECONDS:g} s superato prima "
                               f"di produrre testo (intake.docling.timeout_seconds)")
        raise RuntimeError("Docling ha prodotto un Markdown vuoto da un PDF con testo selezionabile")
    return markdown, avvisi, ocr


# Un heading Markdown in QUALSIASI punto del documento (non solo in cima): se il motore
# non ne produce (tipico di pdf/txt/csv), anteponiamo un titolo dal nome file, così ogni
# documento resta ancorato a un titolo leggibile per il chunking.
_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)

# Immagini con un riferimento LOCALE (`![](Picture1.jpg)` dei PPTX, `<img src="logo.png">`
# degli HTML): nel .md pubblicato in docs/ sarebbero link rotti, perché gli asset non vengono
# pubblicati. Restano gli URL http(s) assoluti; i data URI li toglie già il cleaner. Solo
# per i formati il cui convertitore produce quei riferimenti, e mai dentro un blocco di
# codice: in un TXT, CSV, JSON o XML la sintassi `![..](..)` è testo della fonte.
_LOCAL_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((?!\s*https?://)[^)]*\)")
_IMAGE_FORMATS = frozenset({"pdf", "docx", "pptx", "html", "htm", "epub", "msg"})

# Contenitori dei formati binari: un file che non lo è non è un documento da convertire.
# Senza questo controllo markitdown ripiega sul testo semplice e i byte grezzi di un DOCX
# rotto diventavano un "documento" in staging, senza alcun avviso.
_ZIP_FORMATS = frozenset({"docx", "pptx", "xlsx", "epub"})
_OLE_FORMATS = frozenset({"doc", "xls", "ppt", "msg"})
_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# Nome dello stream (UTF-16LE nella directory OLE) di un documento OOXML cifrato (MS-OFFCRYPTO).
_ENCRYPTED_PACKAGE = "EncryptedPackage".encode("utf-16-le")

# Formati binari legacy: LibreOffice headless li NORMALIZZA nel formato moderno, poi decide la
# matrice del formato moderno (DOC→DOCX→MarkItDown, PPT→PPTX→MarkItDown). Misurato in
# archive/eval-results/libreoffice_20260910/: sui formati moderni LibreOffice non migliora
# l'estrazione, quindi non li tocca. Mai il LibreOffice interno di Docling: profilo predefinito
# (misurato: scarica le immagini collegate) e fallito su un PPT reale. XLS non passa di qui:
# la normalizzazione arrotondava i numeri a 15 cifre e trasformava i booleani in numeri
# (archive/eval-results/excel_diretto_20260911/), xlrd legge l'originale come Excel.
LEGACY_FORMATS = {"doc": "docx", "ppt": "pptx"}
# Stream che il binario DEVE contenere: un file troncato conserva la firma OLE ma non la
# struttura, e LibreOffice lo aprirebbe come testo producendo byte spazzatura (misurato).
_OLE_STREAMS = {"doc": ("WordDocument",), "xls": ("Workbook", "Book"), "ppt": ("PowerPoint Document",)}

# Profilo blindato, chiavi e default letti da main.xcd di LibreOffice 25.2: macro disattivate
# (DisableMacrosExecution, livello 3), collegamenti mai aggiornati al caricamento (Calc 1 =
# mai, Writer 2 = mai), campi lasciati come memorizzati, nessun ricalcolo delle formule
# OOXML/ODF (i valori restano quelli salvati), link da posizioni non attendibili bloccati.
# Misurato: col profilo predefinito un DOCX con immagine collegata genera richieste HTTP,
# con questo nessuna.
# L'updater automatico è disattivato solo qui: su Windows può riavviare LibreOffice
# prima della conversione, restituendo successo senza il file di uscita.
_LO_PROFILE = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Update/Update"><prop oor:name="Enabled" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="BlockUntrustedRefererLinks" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Content/Update"><prop oor:name="Link" oor:op="fuse"><value>1</value></prop></item>
<item oor:path="/org.openoffice.Office.Writer/Content/Update"><prop oor:name="Link" oor:op="fuse"><value>2</value></prop></item>
<item oor:path="/org.openoffice.Office.Writer/Content/Update"><prop oor:name="Field" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>1</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="ODFRecalcMode" oor:op="fuse"><value>1</value></prop></item>
</oor:items>
"""
_WIN_SOFFICE = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "LibreOffice" / "program" / "soffice.com"

# Pacchetti Debian/Ubuntu installati dal Dockerfile per i filtri usati qui: se ne manca uno
# (es. immagine con solo libreoffice-core, senza i moduli "-nogui"), `--convert-to` fallisce
# SENZA aprire il documento, con un messaggio del motore che nomina il filtro, non il file.
# Confuso con "file protetto o danneggiato" prima di questa distinzione (v. _FILTRO_ASSENTE_RE).
_LO_PACCHETTI = "libreoffice-writer-nogui, libreoffice-impress-nogui, libreoffice-calc-nogui"

# Frase che LibreOffice stampa quando il filtro di import o export non esiste (modulo
# mancante): CERTA, mai per un documento aperto ma protetto o danneggiato — misurata lanciando
# soffice reale senza il modulo Calc (`Error: no export filter for .../sonda.xlsx found,
# aborting.`). "source file could not be loaded" invece è AMBIGUA: con LO 24.2.7.2 esce
# IDENTICA sia per un modulo assente sia per un DOC/PPT protetto da password o con lo stream
# principale corrotto (misurato: file di prova con password e con lo stream WordDocument
# azzerato producono esattamente questo testo) — va disambiguata con probe_filtro, mai dedotta
# dal solo testo (rivalidazione del punto #13, 2026-09-28).
_FILTRO_ASSENTE_RE = re.compile(r"no (?:export|import) filter", re.IGNORECASE)
_CARICAMENTO_FALLITO_RE = re.compile(r"source file could not be loaded", re.IGNORECASE)


class LibreOfficeUnavailableError(RuntimeError):
    """LibreOffice disattivato o non installato: non è un difetto del documento."""


def _libreoffice_cmd() -> list[str] | None:
    """intake.libreoffice.command, altrimenti soffice/libreoffice nel PATH o l'installazione
    predefinita di Windows. None se disattivato o assente."""
    if not INTAKE_LIBREOFFICE_ENABLED:
        return None
    # L'avviatore console espone anche --version; soffice.exe su Windows non lo stampa.
    cmd = (INTAKE_LIBREOFFICE_COMMAND
           or (shutil.which("soffice.com") if os.name == "nt" else None)
           or shutil.which("soffice") or shutil.which("libreoffice")
           or (str(_WIN_SOFFICE) if _WIN_SOFFICE.is_file() else None))
    return [cmd] if cmd else None


def _libreoffice(argomenti: list[str], tmp: Path, timeout: float) -> tuple[int, str]:
    """LibreOffice con un profilo blindato NUOVO dentro `tmp`: mai quello dell'utente, mai
    condiviso fra conversioni (LibreOffice blocca il profilo in uso). Al timeout termina
    l'intero albero di processi, non solo il lanciatore."""
    cmd = _libreoffice_cmd()
    if cmd is None:
        raise LibreOfficeUnavailableError("LibreOffice non disponibile (intake.libreoffice)")
    profilo = tmp / "profilo"
    (profilo / "user").mkdir(parents=True, exist_ok=True)
    (profilo / "user" / "registrymodifications.xcu").write_text(_LO_PROFILE, encoding="utf-8")
    gruppo = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == "nt"
              else {"start_new_session": True})
    proc = subprocess.Popen(
        [*cmd, f"-env:UserInstallation={profilo.as_uri()}", "--headless", "--invisible", "--nologo",
         "--norestore", "--nodefault", "--nolockcheck", *argomenti],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, **gruppo)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise TimeoutError(f"LibreOffice oltre {timeout:g} s (intake.libreoffice.timeout_seconds): "
                           f"processo terminato") from None
    return proc.returncode, (out + err).decode(errors="replace")


_lo_version: str | None = None


def libreoffice_version(timeout: float = 60) -> str:
    """`timeout` è configurabile (default 60 s, il costo normale di un avvio a freddo): un
    preflight (scripts/doctor.py) può passarne uno più corto per non restare bloccato quanto
    una conversione vera se il motore non risponde. TimeoutError si propaga, mai catturata qui:
    un motore che non risponde non è una versione "sconosciuta", è un errore da segnalare."""
    global _lo_version
    if _lo_version is None:
        tmp = Path(tempfile.mkdtemp(prefix="vibecraft_lo_"))
        try:
            testo = _libreoffice(["--version"], tmp, timeout)[1]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        _lo_version = next((r.strip() for r in testo.splitlines() if r.startswith("LibreOffice")),
                           "sconosciuta")
    return _lo_version


# Sonde minime (ODT/ODP: ZIP con mimetype non compresso, manifest e content.xml essenziali,
# nessun testo dell'utente) usate SOLO da probe_filtro: dicono con certezza se il filtro di
# esportazione verso .docx/.pptx esiste, invece di indovinarlo dal testo dell'errore
# (_FILTRO_ASSENTE_RE), che cambia fra versioni e lingue di LibreOffice. Usate da
# scripts/doctor.py per un preflight a server spento, senza un documento reale sottomano.
_SONDA_MIMETYPE = {"docx": "application/vnd.oasis.opendocument.text",
                   "pptx": "application/vnd.oasis.opendocument.presentation"}
_SONDA_ESTENSIONE = {"docx": "odt", "pptx": "odp"}
_SONDA_CORPO = {
    "docx": b"<office:text><text:p>sonda</text:p></office:text>",
    "pptx": (b'<office:presentation><draw:page draw:name="p1" '
             b'draw:master-page-name="Default"/></office:presentation>'),
}


def _documento_sonda(moderno: str) -> bytes:
    mimetype = _SONDA_MIMETYPE[moderno]
    manifest = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" '
        'manifest:version="1.2">'
        f'<manifest:file-entry manifest:full-path="/" manifest:version="1.2" '
        f'manifest:media-type="{mimetype}"/>'
        '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
        '</manifest:manifest>'
    ).encode()
    content = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<office:document-content '
        b'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        b'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
        b'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
        b'xmlns:presentation="urn:oasis:names:tc:opendocument:xmlns:presentation:1.0" '
        b'office:version="1.2">' + _SONDA_CORPO[moderno] + b'</office:document-content>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, mimetype.encode())
        z.writestr("META-INF/manifest.xml", manifest)
        z.writestr("content.xml", content)
    return buf.getvalue()


# Esito cache-ato di probe_filtro: SOLO True (il filtro funziona e non cambia finché
# l'immagine non cambia). Un False non si cache-a: potrebbe essere un fluke o un problema
# transitorio del motore, ed escluderlo per il resto del processo negherebbe conversioni che
# invece funzionerebbero.
_filtro_ok: dict[str, bool] = {}


def probe_filtro(moderno: str, timeout: float | None = None) -> bool:
    """True se LibreOffice sa esportare verso `moderno` ("docx" o "pptx"): conversione reale di
    una sonda minima valida, mai del documento dell'utente. `timeout` predefinito a
    intake.libreoffice.timeout_seconds; un chiamante che deve fallire in fretta (scripts/
    doctor.py) ne passa uno più corto. LibreOfficeUnavailableError e TimeoutError si propagano
    SENZA essere catturate qui: non sono "filtro assente" (motore assente o bloccato, non
    modulo mancante) e il chiamante deve poterle distinguere, non riceverne un esito silenzioso
    (rivalidazione del punto #13: un True indebito per il timeout mascherava un motore bloccato
    come "filtri a posto")."""
    if _filtro_ok.get(moderno):
        return True
    timeout = INTAKE_LIBREOFFICE_TIMEOUT_SECONDS if timeout is None else timeout
    tmp = Path(tempfile.mkdtemp(prefix="vibecraft_lo_sonda_"))
    try:
        sorgente = tmp / f"sonda.{_SONDA_ESTENSIONE[moderno]}"
        sorgente.write_bytes(_documento_sonda(moderno))
        uscita = tmp / "uscita"
        uscita.mkdir()
        codice, _testo = _libreoffice(
            ["--convert-to", moderno, "--outdir", str(uscita), str(sorgente)], tmp, timeout)
        ok = codice == 0 and (uscita / f"sonda.{moderno}").is_file()
        if ok:
            _filtro_ok[moderno] = True
        return ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _check_ole(data: bytes, fmt: str, nome_file: str) -> None:
    import olefile  # dipendenza di markitdown[outlook], già fissata
    try:
        with olefile.OleFileIO(io.BytesIO(data)) as ole:
            valido = any(ole.exists(s) for s in _OLE_STREAMS[fmt])
    except Exception:  # olefile solleva tipi diversi a seconda del danno
        valido = False
    if not valido:
        raise ConversionError(f"file danneggiato o non è un {fmt.upper()} valido: {nome_file}")


def _normalize_legacy(data: bytes, fmt: str, nome_file: str) -> bytes:
    """DOC/XLS/PPT → DOCX/XLSX/PPTX, su una COPIA in una cartella temporanea rimossa sempre.
    ConversionError se LibreOffice non riesce ad aprire il file: per il DOCUMENTO (password,
    struttura interna danneggiata) o per l'AMBIENTE (modulo Writer/Impress mancante). Il testo
    del motore lo dice con certezza solo per "no export/import filter"; "source file could not
    be loaded" è ambiguo (esce identico per un modulo assente e per un documento protetto o
    corrotto, v. _CARICAMENTO_FALLITO_RE) e va disambiguato con probe_filtro — mai un difetto
    del documento presentato come "modulo mancante", e viceversa.
    LibreOfficeUnavailableError o TimeoutError se il motore manca del tutto o non risponde."""
    moderno = LEGACY_FORMATS[fmt]
    tmp = Path(tempfile.mkdtemp(prefix="vibecraft_lo_"))
    try:
        sorgente = tmp / f"documento.{fmt}"
        sorgente.write_bytes(data)
        uscita = tmp / "uscita"
        uscita.mkdir()
        codice, testo = _libreoffice(["--convert-to", moderno, "--outdir", str(uscita), str(sorgente)],
                                     tmp, INTAKE_LIBREOFFICE_TIMEOUT_SECONDS)
        risultato = uscita / f"documento.{moderno}"
        if codice != 0 or not risultato.is_file():
            filtro_assente = _FILTRO_ASSENTE_RE.search(testo) is not None
            if not filtro_assente and _CARICAMENTO_FALLITO_RE.search(testo):
                try:
                    filtro_assente = not probe_filtro(moderno)
                except (LibreOfficeUnavailableError, TimeoutError):
                    # Il motore ha problemi propri in questo momento: non è una prova che il
                    # filtro manchi, e non trasformiamo un guasto transitorio in una diagnosi
                    # sui pacchetti. Il messaggio predefinito (sotto) resta corretto in ogni
                    # caso: il documento non si è convertito, qualunque sia la causa.
                    filtro_assente = False
            if filtro_assente:
                raise ConversionError(
                    f"LibreOffice qui non ha il modulo per convertire .{fmt} (filtro assente, "
                    f"tipico di un'installazione con solo libreoffice-core): installa "
                    f"{_LO_PACCHETTI} (Debian/Ubuntu, vedi Dockerfile) o l'equivalente per la "
                    f"tua distribuzione, poi ricarica {nome_file}")
            raise ConversionError(f"LibreOffice non ha potuto aprire {nome_file} (protetto da password "
                                  f"o danneggiato): rimuovi l'eventuale protezione e ricaricalo")
        return risultato.read_bytes()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _drop_local_images(markdown: str) -> tuple[str, int]:
    righe, rimosse, in_fence = [], 0, False
    for riga in markdown.split("\n"):
        if riga.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        elif not in_fence:
            riga, n = _LOCAL_IMAGE_RE.subn("", riga)
            rimosse += n
        righe.append(riga)
    return "\n".join(righe), rimosse

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


def _convert_markitdown(data: bytes, fmt: str, nome_file: str) -> tuple[str, int]:
    """Markdown pulito e numero di immagini incorporate (data URI) che il cleaner toglie."""
    charset = _detect_charset(data) if fmt in _TEXT_FORMATS else None
    stream_info = StreamInfo(extension=f".{fmt}", filename=nome_file, charset=charset)
    try:
        result = _engine().convert_stream(io.BytesIO(data), stream_info=stream_info)
    except MarkItDownException as exc:
        raise ConversionError(f"conversione fallita per {nome_file}: {exc}") from exc
    # Pulizia DETERMINISTICA dell'arredo di impaginazione (core/intake_clean.py): markitdown
    # estrae il testo così com'è impaginato. Il controllo "nessun testo estraibile" viene
    # DOPO: un PDF di sole testate ripetute non è un documento convertito con successo.
    grezzo = result.text_content or ""
    markdown = clean_markdown(grezzo)
    if not markdown:
        raise ConversionError(f"nessun testo estraibile da {nome_file}")
    return markdown, len(_DATA_URI_IMAGE_RE.findall(grezzo))


def convert_to_markdown(
    source: bytes | Path, formato: str, filename: str | None = None
) -> ConversionResult:
    """Converte un documento sorgente (bytes o Path) in Markdown col motore della matrice.
    `formato` è l'estensione dichiarata, validata contro intake.allowed_formats
    (rag_config.yaml) PRIMA di leggere il contenuto — i .md non passano di qui (sono
    nativi in core/intake.py). `filename` è il nome originale, usato per i metadata, il
    titolo di fallback e i messaggi d'errore; se `source` è un Path e `filename` è
    assente, si usa il nome del Path.

    Metadata: quelli storici (source_filename, sha256, formato, converted_at, n_chars) più
    `motore` effettivo, `versione_motore`, `fallback` (None, oppure da quale motore e perché),
    `avvisi` per la review e, per i PDF passati da Docling, `pdf` (pagine, pagine senza testo
    selezionabile, OCR usato)."""
    fmt = formato.lower().lstrip(".")
    if fmt not in INTAKE_ALLOWED_FORMATS:
        raise ConversionError(
            f"formato non supportato: {formato!r} (ammessi: {', '.join(INTAKE_ALLOWED_FORMATS)})"
        )
    if fmt == "md":
        raise ConversionError(
            "i documenti .md sono gestiti nativamente, non passano da un convertitore"
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
    # Office cifra DOCX/XLSX/PPTX protetti da password dentro un contenitore OLE con lo stream
    # EncryptedPackage, non in uno ZIP: prima venivano detti «danneggiati».
    if fmt in _ZIP_FORMATS and data.startswith(_OLE_SIGNATURE) and _ENCRYPTED_PACKAGE in data:
        raise ConversionError(f"file protetto da password (cifrato): {nome_file} — rimuovi la "
                              f"protezione e ricaricalo")
    if ((fmt in _ZIP_FORMATS and not zipfile.is_zipfile(io.BytesIO(data)))
            or (fmt in _OLE_FORMATS and not data.startswith(_OLE_SIGNATURE))):
        raise ConversionError(f"file danneggiato o non è un {fmt.upper()} valido: {nome_file}")
    if fmt in _OLE_STREAMS:
        _check_ole(data, fmt, nome_file)

    originale = data
    motore, markdown, fallback = "markitdown", None, None
    avvisi: list[str] = []
    extra: dict = {}
    # `instradamento` decide il motore: per DOC/PPT è il formato moderno prodotto da
    # LibreOffice. `fmt` resta quello dell'originale (metadata, sha256, messaggi).
    instradamento, nome_motore = fmt, nome_file
    if fmt in LEGACY_FORMATS:
        try:
            data = _normalize_legacy(data, fmt, nome_file)
            instradamento = LEGACY_FORMATS[fmt]
            nome_motore = f"{Path(nome_file).stem}.{instradamento}"
            extra["normalizzazione"] = {"motore": "libreoffice", "versione": libreoffice_version(),
                                        "da": fmt, "a": instradamento}
        except ConversionError:
            raise
        except Exception as exc:  # motore assente, disattivato o bloccato
            motivo = f"{type(exc).__name__}: {exc}"[:500]
            raise ConversionError(
                f"i file .{fmt} si convertono solo attraverso LibreOffice, che qui non ha "
                f"funzionato ({motivo}): salva il file come .{LEGACY_FORMATS[fmt]} e ricaricalo") from exc
    if instradamento in EXCEL_FORMATS:
        # Lettura diretta dell'originale: nessun ripiego, un errore resta un errore esplicito.
        from core.intake_excel import convert_excel
        markdown, avvisi_excel = convert_excel(data, instradamento)
        motore = EXCEL_FORMATS[instradamento]
        avvisi.extend(avvisi_excel)
    if instradamento in DOCLING_FORMATS and INTAKE_DOCLING_ENABLED:
        if fmt == "pdf":
            pagine = _pdf_text_per_page(data, nome_file)
            info_pdf = {"pagine": len(pagine),
                        "pagine_senza_testo": sum(1 for n in pagine if n < _MIN_PAGE_CHARS),
                        "ocr": False}
            extra["pdf"] = info_pdf
        try:
            markdown, avvisi_docling, info_pdf["ocr"] = _convert_pdf_docling(data, nome_file, pagine)
            motore = "docling"
            avvisi.extend(avvisi_docling)
        except ConversionError:
            raise
        except Exception as exc:  # dipendenza, pesi o guasto interno: si ripiega, dichiarandolo
            fallback = {"da": "docling", "motivo": f"{type(exc).__name__}: {exc}"[:500]}
            logger.warning("intake: Docling non ha convertito %s, uso MarkItDown: %s",
                           nome_file, fallback["motivo"])

    if markdown is None:
        try:
            markdown, incorporate = _convert_markitdown(data, instradamento, nome_motore)
        except ConversionError as exc:
            if fallback:
                raise ConversionError(
                    f"{exc} (e Docling non ha potuto convertirlo: {fallback['motivo']})") from exc
            raise
        if fallback:
            avvisi.append("Docling non ha convertito questo file: il testo è stato estratto con "
                          "MarkItDown, senza la ricostruzione verificata di tabelle e titoli. "
                          "Controlla la struttura prima di approvare, oppure rifiuta e ricarica "
                          "quando Docling è disponibile.")
            if extra.get("pdf", {}).get("pagine_senza_testo"):
                avvisi.append(f"{extra['pdf']['pagine_senza_testo']} pagine senza testo "
                              f"selezionabile: il loro contenuto manca (MarkItDown non fa OCR).")
        if incorporate:
            avvisi.append(f"{incorporate} immagini incorporate non sono incluse nel Markdown: "
                          f"restano solo nell'originale conservato in staging.")

    rimosse = 0
    if instradamento in _IMAGE_FORMATS:
        markdown, rimosse = _drop_local_images(markdown)
    if rimosse:
        markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
        avvisi.append(f"{rimosse} riferimenti a immagini locali rimossi: in docs/ entra solo il "
                      f"Markdown, le immagini restano nell'originale conservato in staging.")
        if not markdown:
            raise ConversionError(f"nessun testo estraibile da {nome_file}")

    # Titolo di fallback solo se il documento non ha alcun heading (pdf/txt/csv...): i
    # formati che li producono (docx/html) restano intatti, niente doppio titolo.
    if not _HEADING_RE.search(markdown):
        markdown = f"# {Path(nome_file).stem}\n\n{markdown}"

    metadata = {
        "source_filename": nome_file,
        "sha256": hashlib.sha256(originale).hexdigest(),
        "formato": fmt,
        "converted_at": datetime.now(timezone.utc).isoformat(),
        "n_chars": len(markdown),
        "motore": motore,
        "versione_motore": engine_version(motore),
        "fallback": fallback,
        "avvisi": avvisi,
        **extra,
    }
    return ConversionResult(markdown=markdown, metadata=metadata)

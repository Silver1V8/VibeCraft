"""Area di staging dell'evoluzione Intake & Import (piano:
docs/00_meta_governance/piano_intake_import.md). S0 ha posato lo scaffold (bootstrap lazy
delle cartelle e del journal append-only); questa è la S2: il ciclo completo
stage → preview → approve/reject.

Semantica NON negoziabile (decisioni vincolanti del piano):
- NULLA entra in docs/ fuori da approve(): stage/reject/preview scrivono solo in staging/;
- approve non sovrascrive MAI un file esistente in docs/ (errore esplicito);
- ogni scrittura su docs/ + indice avviene sotto il writer lock cross-processo;
- reject non cancella: sposta i file in staging/rejected/ per tracciabilità.

Logica pura con DI (pattern di core/): le risorse pesanti (reindex, docs_dir, staging)
sono iniettabili; i default risolvono i percorsi reali da core.config a CALL time, così
i test possono monkeypatchare i moduli senza toccare il filesystem vero."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from core.chunking import chunk_markdown, parse_markdown_file
from core.config import (
    DOCS_DIR,
    INTAKE_ALLOWED_FORMATS,
    INTAKE_DEFAULT_AUTHORITY,
    INTAKE_STAGING_DIR,
    PROJECT_ROOT,
)
from core.intake_convert import ConversionError, convert_to_markdown
from core.writer_lock import writer_lock

# Sotto-cartelle dell'area di staging: 'docs' per i documenti (generati o importati) in attesa
# di review, 'projects' per i progetti importati da path locale (S5, coi rispettivi backup),
# 'rejected' per ciò che viene rifiutato — mai cancellato, solo spostato qui per tracciabilità.
STAGING_DOCS_DIR = INTAKE_STAGING_DIR / "docs"
STAGING_PROJECTS_DIR = INTAKE_STAGING_DIR / "projects"
STAGING_REJECTED_DIR = INTAKE_STAGING_DIR / "rejected"
# Journal append-only (stesso pattern di database/reindex_jobs.jsonl, vedi api/reindex.py):
# ogni transizione di stato di un documento/progetto in staging vi appende una riga JSON.
INTAKE_JOURNAL_PATH = INTAKE_STAGING_DIR / "intake.jsonl"


# ---------------------------------------------------------------------------
# Errori tipizzati del ciclo di staging: lo strato HTTP (api/routes_intake.py) li
# mappa su status code senza dover ispezionare i messaggi.
# ---------------------------------------------------------------------------
class IntakeError(RuntimeError):
    """Base degli errori del ciclo di staging."""


class StagedDocumentNotFoundError(IntakeError):
    """L'id richiesto non esiste nel journal."""


class DocumentAlreadyProcessedError(IntakeError):
    """Il documento non è più in stato 'staged' (già approvato o rifiutato):
    un secondo approve/reject è un errore idempotente, mai un doppio effetto."""


class DuplicateStagedDocumentError(IntakeError):
    """Upload con lo stesso sha256 di un documento già staged o già approvato."""


class InvalidCategoryError(IntakeError):
    """Categoria docs/ non tra quelle ammesse."""


class InvalidFilenameError(IntakeError):
    """nome_file non valido come semplice nome di file .md (traversal, separatori...)."""


class TargetFileExistsError(IntakeError):
    """Il file di destinazione in docs/<categoria>/ esiste già: mai sovrascrittura."""


class InvalidComposedDocumentError(IntakeError):
    """Il documento composto (frontmatter + corpo) non passa parse_markdown_file/chunking:
    approve fallisce PRIMA di scrivere in docs/."""


# Categoria docs/ → classification del frontmatter (decisa dal piano, S2): è anche la
# whitelist delle categorie ammesse da approve.
CATEGORY_CLASSIFICATION = {
    "00_meta_governance": "METADATA",
    "01_architecture_norms": "NORMS",
    "02_specs_normative": "REQUIREMENTS",
    "03_changes_historical": "METADATA",
    "04_knowledge_informative": "METHODOLOGY",
    "05_project_specs": "REQUIREMENTS",
}

# Nome progetto scritto nel frontmatter, identico ai documenti autorati di docs/.
_PROJECT_NAME = "VibeCraft — Sistema di Gestione Eventi Aziendali"

# Nome file di destinazione: solo nome semplice (niente separatori → niente traversal),
# primo carattere alfanumerico (esclude '.', quindi anche '..' e i dotfile).
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_H1_RE = re.compile(r"(?m)^#\s+(.+?)\s*$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_staging_dirs(base_dir: str | Path | None = None) -> dict[str, Path]:
    """Crea (se mancanti) le cartelle dell'area di staging e il file del journal, e ne
    restituisce i percorsi. Lazy e idempotente — va chiamata dagli entrypoint che toccano
    staging/, mai assunta creata al solo import del modulo (stesso principio degli
    artefatti di database/, vedi core/artifacts.py e core/writer_lock.py).

    `base_dir` è il seam per i test (default: INTAKE_STAGING_DIR, risolta da
    rag_config.yaml → intake.staging_dir)."""
    root = Path(base_dir) if base_dir is not None else INTAKE_STAGING_DIR
    docs_dir = root / "docs"
    projects_dir = root / "projects"
    rejected_dir = root / "rejected"
    journal_path = root / "intake.jsonl"

    for d in (docs_dir, projects_dir, rejected_dir):
        d.mkdir(parents=True, exist_ok=True)
    if not journal_path.exists():
        journal_path.touch()

    return {
        "root": root,
        "docs": docs_dir,
        "projects": projects_dir,
        "rejected": rejected_dir,
        "journal": journal_path,
    }


# ---------------------------------------------------------------------------
# Journal append-only: una riga JSON per transizione, l'ultima riga per id vince
# (stesso folding di api/reindex.py::_load_journal).
# ---------------------------------------------------------------------------
def _append_journal(paths: dict[str, Path], record: dict) -> None:
    with paths["journal"].open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()


def _journal_state(paths: dict[str, Path]) -> dict[str, dict]:
    """Stato corrente per id, ricostruito dal journal (ultima riga per id vince,
    ordine di prima comparsa preservato). Le righe corrotte si saltano, mai un abort."""
    state: dict[str, dict] = {}
    journal = paths["journal"]
    if not journal.exists():
        return state
    with journal.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            doc_id = rec.get("id")
            if not doc_id:
                continue
            state[doc_id] = rec
    return state


def _require_staged(paths: dict[str, Path], doc_id: str) -> dict:
    """Entry del journal per `doc_id`, garantita in stato 'staged'."""
    entry = _journal_state(paths).get(doc_id)
    if entry is None:
        raise StagedDocumentNotFoundError(f"documento in staging non trovato: {doc_id}")
    if entry.get("status") != "staged":
        raise DocumentAlreadyProcessedError(
            f"documento {doc_id} già processato (stato: {entry.get('status')})"
        )
    return entry


def require_staged(doc_id: str, base_dir: str | Path | None = None) -> dict:
    """Come `_require_staged` ma per i moduli che estendono il ciclo di staging senza
    farne parte (core/intake_refine.py): risolve da sé i percorsi e solleva gli stessi
    errori tipizzati, così la regola "si opera solo su ciò che è ancora 'staged'" ha
    un'unica implementazione."""
    return _require_staged(ensure_staging_dirs(base_dir), doc_id)


# ---------------------------------------------------------------------------
# stage / list / preview
# ---------------------------------------------------------------------------
def _decode_markdown_native(content: bytes, filename: str) -> str:
    """Markdown nativo: nessuna conversione, solo decodifica (UTF-8 con fallback latin-1,
    stessa tolleranza di intake_convert per i TXT legacy)."""
    if not content:
        raise ConversionError(f"file vuoto: {filename}")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return content.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise ConversionError(f"encoding non riconosciuto per {filename}") from exc


def stage_document(filename: str, content: bytes, *, base_dir: str | Path | None = None,
                   source: str = "imported") -> dict:
    """Converte `content` in Markdown (via core.intake_convert; i .md entrano nativi) e lo
    salva in staging/docs/ insieme all'originale, appendendo l'entry 'staged' al journal.
    Nessuna scrittura fuori da staging/.

    Un upload col medesimo sha256 di un documento già 'staged' o già 'approved' viene
    RIFIUTATO (DuplicateStagedDocumentError): segnalato, non ri-staged. Un documento
    'rejected' può invece essere ricaricato."""
    paths = ensure_staging_dirs(base_dir)
    fmt = Path(filename).suffix.lower().lstrip(".")
    if fmt not in INTAKE_ALLOWED_FORMATS:
        raise ConversionError(
            f"formato non supportato: {fmt!r} (ammessi: {', '.join(INTAKE_ALLOWED_FORMATS)})"
        )

    if fmt == "md":
        markdown = _decode_markdown_native(content, filename)
        metadata = {
            "source_filename": filename,
            "sha256": hashlib.sha256(content).hexdigest(),
            "formato": "md",
            "converted_at": _now_iso(),
            "n_chars": len(markdown),
        }
    else:
        result = convert_to_markdown(content, fmt, filename=filename)
        markdown, metadata = result.markdown, result.metadata

    sha = metadata["sha256"]
    for entry in _journal_state(paths).values():
        if (entry.get("status") in ("staged", "approved")
                and (entry.get("metadata") or {}).get("sha256") == sha):
            raise DuplicateStagedDocumentError(
                f"documento già presente (sha256 identico a {entry.get('id')}, "
                f"stato {entry.get('status')}): non ri-staged"
            )

    doc_id = uuid.uuid4().hex[:12]
    original_path = paths["docs"] / f"{doc_id}.src.{fmt}"
    markdown_path = paths["docs"] / f"{doc_id}.md"
    original_path.write_bytes(content)
    markdown_path.write_text(markdown, encoding="utf-8")

    record = {
        "id": doc_id,
        "status": "staged",
        "source": source,
        "filename": filename,
        "staged_at": _now_iso(),
        "metadata": metadata,
        "files": {"original": original_path.name, "markdown": markdown_path.name},
    }
    _append_journal(paths, record)
    return record


def list_staged(base_dir: str | Path | None = None) -> list[dict]:
    """Documenti attualmente in stato 'staged', in ordine di staging."""
    paths = ensure_staging_dirs(base_dir)
    return [e for e in _journal_state(paths).values() if e.get("status") == "staged"]


def get_preview(doc_id: str, base_dir: str | Path | None = None) -> dict:
    """Entry + markdown derivato di un documento in staging (solo stato 'staged')."""
    paths = ensure_staging_dirs(base_dir)
    entry = _require_staged(paths, doc_id)
    markdown_path = paths["docs"] / entry["files"]["markdown"]
    try:
        markdown = markdown_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StagedDocumentNotFoundError(
            f"markdown di staging non leggibile per {doc_id}: {exc}"
        ) from exc
    return {**entry, "markdown": markdown}


# ---------------------------------------------------------------------------
# approve: frontmatter conforme + scrittura in docs/ + reindex delta, sotto writer lock
# ---------------------------------------------------------------------------
def _sanitize_target_filename(nome_file: str) -> str:
    nome = (nome_file or "").strip()
    if not nome:
        raise InvalidFilenameError("nome_file vuoto")
    if not nome.lower().endswith(".md"):
        nome += ".md"
    if not _SAFE_FILENAME_RE.match(nome):
        raise InvalidFilenameError(
            f"nome_file non valido: {nome_file!r} (solo nome semplice .md, "
            f"caratteri A-Za-z0-9._- e primo carattere alfanumerico)"
        )
    return nome


def _split_frontmatter(text: str) -> str:
    """Corpo senza l'eventuale frontmatter già presente (i .md nativi possono averne uno):
    il frontmatter conforme viene sempre RIGENERATO da approve, mai duplicato."""
    stripped = text.lstrip("﻿")
    if stripped.startswith("---"):
        parts = stripped.split("---")
        if len(parts) >= 3:
            return "---".join(parts[2:]).lstrip("\n")
    return text


def _compose_document(entry: dict, categoria: str, nome_file: str, staged_markdown: str) -> str:
    """Documento finale per docs/<categoria>/<nome_file>: frontmatter CONFORME alle spec
    esistenti (riferimento: docs/00_meta_governance/change_log.md) + corpo convertito.
    La provenienza (metadata S1) vive nel campo dedicato `intake` del frontmatter.

    Se il documento è passato dalla raffinazione (core/intake_refine.py), l'entry porta
    anche un frontmatter SEMANTICO dedotto dal contenuto (document_type, domain, tags…):
    quei campi si aggiungono in coda, mai al posto dei campi normativi — che restano
    calcolati qui e solo qui."""
    body = _split_frontmatter(staged_markdown).strip()
    metadata = entry.get("metadata") or {}
    semantic = entry.get("semantic") or {}
    stem = Path(nome_file).stem
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-") or "documento"
    doc_semantic_id = f"intake-{slug}-v1.0"
    h1 = _H1_RE.search(body)
    # Il titolo dedotto dalla raffinazione batte l'H1 del convertitore, che sui PDF è il
    # nome del file ("Specifiche Tecniche WsProtocollo bv.0.3.19 (1)").
    title = semantic.get("title") or (h1.group(1).strip() if h1 else stem)
    frontmatter = {
        "id": doc_semantic_id,
        "title": title,
        "project": _PROJECT_NAME,
        "version": "1.0.0",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "status": "IMPORTED",
        "classification": CATEGORY_CLASSIFICATION[categoria],
        "path": f"docs/{categoria}/{nome_file}",
        "authority": INTAKE_DEFAULT_AUTHORITY,
        "graph_rag": {
            "node_type": "DOCUMENT",
            "node_id": doc_semantic_id,
            "scope": f"Documento entrato via Intake ({entry.get('source', 'imported')}, "
                     f"formato {metadata.get('formato', '?')}): {title}",
            "edges": [],
        },
        # Provenienza: i metadata della conversione S1 + l'id di staging, in un campo
        # dedicato — mai mescolati ai campi normativi del frontmatter.
        "intake": {
            "source": entry.get("source", "imported"),
            "staged_id": entry.get("id"),
            "source_filename": metadata.get("source_filename"),
            "sha256": metadata.get("sha256"),
            "formato": metadata.get("formato"),
            "converted_at": metadata.get("converted_at"),
        },
    }
    # Campi semantici della raffinazione: utili al retrieval e alla lettura umana, ma non
    # normativi — whitelist esplicita (mai un dict arbitrario dedotto da un LLM riversato
    # nel frontmatter) e mai in sovrascrittura di quanto già composto sopra.
    # (`source_file` non è in lista di proposito: la provenienza ha già la sua unica fonte
    # di verità in `intake.source_filename`, appena sopra.)
    for key in ("document_type", "source_version", "domain", "tags"):
        value = semantic.get(key)
        if value and key not in frontmatter:
            frontmatter[key] = value
    fm_yaml = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
    return f"---\n{fm_yaml}---\n\n{body}\n"


def _validate_composed(paths: dict[str, Path], doc_id: str, composed: str) -> None:
    """Il documento composto DEVE passare parse_markdown_file (frontmatter dict con id,
    corpo non vuoto) e produrre almeno un chunk non vuoto — PRIMA di qualunque scrittura
    in docs/. La validazione passa da un file candidato in staging (parse_markdown_file
    legge da path), rimosso in ogni caso."""
    candidate = paths["docs"] / f"{doc_id}.approve-candidate.md"
    candidate.write_text(composed, encoding="utf-8")
    try:
        try:
            metadata, body = parse_markdown_file(str(candidate))
        except Exception as exc:
            raise InvalidComposedDocumentError(
                f"frontmatter generato non parsabile ({type(exc).__name__}: {exc}): "
                f"approve annullato prima di scrivere in docs/"
            ) from exc
        if not isinstance(metadata, dict) or not metadata.get("id"):
            raise InvalidComposedDocumentError(
                "frontmatter generato senza campo 'id': approve annullato")
        if not body.strip():
            raise InvalidComposedDocumentError(
                "corpo vuoto dopo la composizione: approve annullato")
        chunks = chunk_markdown("staging-validation.md", metadata, body)
        if not any(c.get("text", "").strip() for c in chunks):
            raise InvalidComposedDocumentError(
                "nessuna sezione non vuota dopo il chunking: approve annullato")
    finally:
        try:
            candidate.unlink()
        except OSError:
            pass


def _default_reindex(changed_paths: list[str] | None) -> dict:
    """Reindex delta di default (CLI/uso diretto): import lazy per non pagare torch al
    solo import di core.intake. Lo strato HTTP inietta la propria variante col client
    Qdrant e il modello del server (api/routes_intake.py)."""
    from core.indexing import incremental_index
    return incremental_index(changed_paths=changed_paths)


def _slim_stats(stats) -> dict:
    """Sottoinsieme leggero delle stats del reindex per il journal (il risultato completo
    torna comunque al chiamante)."""
    if not isinstance(stats, dict):
        return {}
    keep = ("noop", "reindexed_docs", "deleted_docs", "upserted_chunks", "version")
    return {k: stats[k] for k in keep if k in stats}


def approve(doc_id: str, categoria: str, nome_file: str, *,
            base_dir: str | Path | None = None,
            docs_dir: str | Path | None = None,
            reindex=None,
            lock_timeout_seconds: float = 30,
            lock_path: str | Path | None = None) -> dict:
    """Promuove un documento dallo staging a docs/<categoria>/<nome_file> e lancia il
    reindex DELTA della sola path aggiunta — l'UNICO percorso che scrive in docs/.

    Ordine: validazioni (stato staged, categoria, nome file, destinazione libera) →
    composizione frontmatter conforme → validazione parse/chunking del composto → SOTTO
    WRITER LOCK: scrittura del file + reindex delta (plan/apply di core/indexing.py, via
    `reindex(changed_paths)`; default incremental_index). Se il reindex fallisce, il file
    appena scritto viene rimosso: docs/ e indice restano coerenti tra loro.

    Un secondo approve dello stesso id fallisce con DocumentAlreadyProcessedError senza
    alcun effetto (idempotenza degli errori, mai doppio file)."""
    paths = ensure_staging_dirs(base_dir)
    entry = _require_staged(paths, doc_id)
    if categoria not in CATEGORY_CLASSIFICATION:
        raise InvalidCategoryError(
            f"categoria inesistente: {categoria!r} "
            f"(ammesse: {', '.join(sorted(CATEGORY_CLASSIFICATION))})"
        )
    nome = _sanitize_target_filename(nome_file)
    docs_root = Path(docs_dir) if docs_dir is not None else DOCS_DIR
    target = docs_root / categoria / nome
    if target.exists():
        raise TargetFileExistsError(
            f"esiste già un file {nome!r} in docs/{categoria}/: mai sovrascrittura — "
            f"scegli un altro nome"
        )

    staged_md_path = paths["docs"] / entry["files"]["markdown"]
    staged_markdown = staged_md_path.read_text(encoding="utf-8")
    composed = _compose_document(entry, categoria, nome, staged_markdown)
    _validate_composed(paths, doc_id, composed)

    try:
        rel_path = target.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
        changed_paths: list[str] | None = [rel_path]
    except ValueError:
        # docs_dir fuori dal repo (test/sandbox): nessuna restrizione del delta,
        # incremental_index considera l'intero docs_dir come sempre.
        rel_path = str(target)
        changed_paths = None

    reindex_fn = reindex if reindex is not None else _default_reindex
    with writer_lock(timeout_seconds=lock_timeout_seconds, lock_path=lock_path):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(composed, encoding="utf-8")
        try:
            stats = reindex_fn(changed_paths)
        except Exception:
            # docs/ e indice devono restare coerenti: senza reindex riuscito il file
            # non deve sopravvivere in docs/ (il doc resta in staging, riprovabile).
            try:
                target.unlink()
            except OSError:
                pass
            raise

    record = {
        **entry,
        "status": "approved",
        "approved_at": _now_iso(),
        "categoria": categoria,
        "nome_file": nome,
        "doc_path": rel_path,
        "reindex": _slim_stats(stats),
    }
    _append_journal(paths, record)
    return {**record, "reindex": stats if isinstance(stats, dict) else _slim_stats(stats)}


# ---------------------------------------------------------------------------
# reject: marca nel journal e sposta i file in staging/rejected/
# ---------------------------------------------------------------------------
def reject(doc_id: str, motivo: str = "", *, base_dir: str | Path | None = None) -> dict:
    """Rifiuta un documento in staging: entry 'rejected' nel journal (col motivo) e file
    spostati in staging/rejected/. docs/ e indice NON vengono toccati — non c'è nulla da
    toccare: nulla era uscito dallo staging."""
    paths = ensure_staging_dirs(base_dir)
    entry = _require_staged(paths, doc_id)
    moved: dict[str, str] = {}
    for key, name in (entry.get("files") or {}).items():
        src = paths["docs"] / name
        if src.exists():
            dst = paths["rejected"] / name
            shutil.move(str(src), str(dst))
            moved[key] = dst.name
    record = {
        **entry,
        "status": "rejected",
        "rejected_at": _now_iso(),
        "motivo": motivo,
        "files": moved or entry.get("files"),
    }
    _append_journal(paths, record)
    return record

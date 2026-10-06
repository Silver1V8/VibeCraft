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
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from core.chunking import chunk_markdown, parse_markdown_file, split_frontmatter
from core.config import (
    DOCS_DIR,
    INTAKE_ALLOWED_FORMATS,
    INTAKE_DEFAULT_AUTHORITY,
    INTAKE_STAGING_DIR,
    PROJECT_ROOT,
)
from core.intake_convert import ConversionError, convert_to_markdown
from core.writer_lock import writer_lock
from core.projects import _unlinked
from core.indexing_lock import indexing_lock

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

_HEADING_RE = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _staging_paths(base_dir: str | Path | None, *, create: bool, project=None) -> dict[str, Path]:
    """Percorsi dell'area di staging. `create=True` crea le cartelle e il journal se
    mancanti (comportamento storico, usato da ensure_staging_dirs); `create=False` li
    restituisce senza toccare il filesystem — per le sole letture, vedi
    staging_paths_readonly."""
    root = _unlinked(project.staging_dir if project else Path(base_dir) if base_dir is not None else INTAKE_STAGING_DIR)
    docs_dir = _unlinked(root / "docs")
    projects_dir = _unlinked(root / "projects")
    rejected_dir = _unlinked(root / "rejected")
    journal_path = _unlinked(root / "intake.jsonl")

    if create:
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


def ensure_staging_dirs(base_dir: str | Path | None = None, *, project=None) -> dict[str, Path]:
    """Crea (se mancanti) le cartelle dell'area di staging e il file del journal, e ne
    restituisce i percorsi. Lazy e idempotente — va chiamata dagli entrypoint che SCRIVONO
    in staging/ (stage, approve, reject, refine, import), mai assunta creata al solo
    import del modulo (stesso principio degli artefatti di database/, vedi
    core/artifacts.py e core/writer_lock.py).

    Le sole letture (list_staged, get_preview, project_brief.applied_imports) usano invece
    `staging_paths_readonly`: un GET non deve materializzare cartelle/journal su un
    'staging/' mai esistito solo perché è stato interrogato — vedi SECURITY_SURFACE.md §1,
    GET /api/intake/staged, /api/intake/staged/{doc_id}/preview e /api/intake/project/imports.

    `base_dir` è il seam per i test (default: INTAKE_STAGING_DIR, risolta da
    rag_config.yaml → intake.staging_dir)."""
    return _staging_paths(base_dir, create=True, project=project)


def staging_paths_readonly(base_dir: str | Path | None = None, *, project=None) -> dict[str, Path]:
    """Stessi percorsi di ensure_staging_dirs ma SENZA crearli: per le letture. Se
    staging/ non esiste ancora, i path restituiti puntano a file/cartelle inesistenti —
    `_journal_state` gestisce già un journal.exists() False restituendo lo stato vuoto
    ({}), quindi il chiamante vede correttamente 'nessun documento' senza che nulla venga
    scritto su disco."""
    return _staging_paths(base_dir, create=False, project=project)


def staged_file(paths, name, kind='docs') -> Path:
    root = _unlinked(paths[kind])
    path = _unlinked(root / name)
    if not path.is_relative_to(root):
        raise IntakeError('Staged file outside project storage')
    return path


# ---------------------------------------------------------------------------
# Journal append-only: una riga JSON per transizione, l'ultima riga per id vince
# (stesso folding di api/reindex.py::_load_journal).
# ---------------------------------------------------------------------------
# UNICO punto di scrittura del journal (stage, approve, reject, refine, generazione, import).
# Su Windows due handle aperti in "a" da thread diversi si sovrascrivono a vicenda: la CRT
# emula O_APPEND con seek+write (misurato: 8 thread × 400 righe → ~25% di righe perse).
# Uno stage che finiva durante un approve poteva cancellare la riga 'approved' o 'staged'.
# Lock di processo più lock OS su un file accanto al journal: la CLI può scrivere mentre
# il server fa staging. Ordine fisso writer lock → lock del journal, mai il contrario.
_journal_lock = threading.Lock()


def _append_journal(paths: dict[str, Path], record: dict) -> None:
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _journal_lock, writer_lock(timeout_seconds=30,
                                    lock_path=_unlinked(paths["journal"].with_name("intake.jsonl.lock"))):
        with _unlinked(paths["journal"]).open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()


def _journal_state(paths: dict[str, Path]) -> dict[str, dict]:
    """Stato corrente per id, ricostruito dal journal (ultima riga per id vince,
    ordine di prima comparsa preservato). Le righe corrotte si saltano, mai un abort."""
    state: dict[str, dict] = {}
    journal = _unlinked(paths["journal"])
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


def require_staged(doc_id: str, base_dir: str | Path | None = None, *, project=None) -> dict:
    """Come `_require_staged` ma per i moduli che estendono il ciclo di staging senza
    farne parte (core/intake_refine.py): risolve da sé i percorsi e solleva gli stessi
    errori tipizzati, così la regola "si opera solo su ciò che è ancora 'staged'" ha
    un'unica implementazione."""
    return _require_staged(ensure_staging_dirs(base_dir, project=project), doc_id)


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


def _check_not_duplicate(paths: dict[str, Path], sha: str) -> None:
    for entry in _journal_state(paths).values():
        if (entry.get("status") in ("staged", "approved")
                and (entry.get("metadata") or {}).get("sha256") == sha):
            raise DuplicateStagedDocumentError(
                f"documento già presente (sha256 identico a {entry.get('id')}, "
                f"stato {entry.get('status')}): non ri-staged"
            )


# Ricontrollo del duplicato e scrittura in staging sono una sezione critica: la conversione
# (secondi o minuti per un PDF) avviene fuori, quindi due upload identici possono arrivare
# qui insieme. ponytail: lock di processo; il journal non ha altri scrittori concorrenti.
_stage_lock = threading.Lock()


def stage_document(filename: str, content: bytes, *, base_dir: str | Path | None = None,
                   source: str = "imported", project=None) -> dict:
    """Converte `content` in Markdown (via core.intake_convert; i .md entrano nativi) e lo
    salva in staging/docs/ insieme all'originale, appendendo l'entry 'staged' al journal.
    Nessuna scrittura fuori da staging/: l'originale resta qui anche dopo l'approvazione.

    Un upload col medesimo sha256 di un documento già 'staged' o già 'approved' viene
    RIFIUTATO (DuplicateStagedDocumentError): segnalato, non ri-staged — e prima di pagare
    la conversione. Un documento 'rejected' può invece essere ricaricato."""
    paths = ensure_staging_dirs(base_dir, project=project)
    fmt = Path(filename).suffix.lower().lstrip(".")
    if fmt not in INTAKE_ALLOWED_FORMATS:
        raise ConversionError(
            f"formato non supportato: {fmt!r} (ammessi: {', '.join(INTAKE_ALLOWED_FORMATS)})"
        )
    sha = hashlib.sha256(content).hexdigest()
    _check_not_duplicate(paths, sha)

    if fmt == "md":
        markdown = _decode_markdown_native(content, filename)
        metadata = {
            "source_filename": filename,
            "sha256": sha,
            "formato": "md",
            "converted_at": _now_iso(),
            "n_chars": len(markdown),
            "motore": "nativo",
            "versione_motore": None,
            "fallback": None,
            "avvisi": [],
        }
    else:
        result = convert_to_markdown(content, fmt, filename=filename)
        markdown, metadata = result.markdown, result.metadata

    with _stage_lock:
        _check_not_duplicate(paths, sha)
        doc_id = uuid.uuid4().hex[:12]
        original_path = staged_file(paths, f"{doc_id}.src.{fmt}")
        markdown_path = staged_file(paths, f"{doc_id}.md")
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


def list_staged(base_dir: str | Path | None = None, *, project=None) -> list[dict]:
    """Documenti attualmente in stato 'staged', in ordine di staging. Sola lettura: non
    crea staging/ se non esiste ancora (nessun documento è semplicemente lista vuota)."""
    paths = staging_paths_readonly(base_dir, project=project)
    return [e for e in _journal_state(paths).values() if e.get("status") == "staged"]


def get_preview(doc_id: str, base_dir: str | Path | None = None, *, project=None) -> dict:
    """Entry + markdown derivato di un documento in staging (solo stato 'staged'). Sola
    lettura: non crea staging/ se non esiste ancora (doc_id non trovato, come oggi)."""
    paths = staging_paths_readonly(base_dir, project=project)
    entry = _require_staged(paths, doc_id)
    markdown_path = staged_file(paths, entry["files"]["markdown"])
    try:
        markdown = markdown_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StagedDocumentNotFoundError(
            f"markdown di staging non leggibile per {doc_id}: {exc}"
        ) from exc
    return {**entry, "markdown": markdown}


# ---------------------------------------------------------------------------
# approve: frontmatter conforme + scrittura in docs/, sotto writer lock
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
    il frontmatter conforme viene sempre RIGENERATO da approve, mai duplicato. Stessa
    regola di riconoscimento del parser di indicizzazione (core.chunking.split_frontmatter):
    solo un blocco `---`…`---` ben formato in cima al documento, mai la prima occorrenza
    di `---` in mezzo al testo — che taglierebbe via metà corpo."""
    return split_frontmatter(text)[1].lstrip("\n")


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
    # Titolo di livello più alto presente (il primo, a parità): Docling riserva `#` al titolo
    # del documento, e un PDF il cui titolo è riconosciuto come intestazione parte da `##`.
    # Il titolo dedotto dalla raffinazione batte quello del convertitore, che sui PDF di
    # MarkItDown è il nome del file ("Specifiche Tecniche WsProtocollo bv.0.3.19 (1)").
    titoli = _HEADING_RE.findall(body)
    testa = min(titoli, key=lambda t: len(t[0]))[1] if titoli else None
    title = semantic.get("title") or testa or stem
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
            # Motore effettivo ed eventuale fallback, solo se registrati (le entry staged
            # prima dell'introduzione di Docling non li hanno).
            **{k: metadata[k] for k in ("motore", "versione_motore", "fallback", "normalizzazione")
               if metadata.get(k)},
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
    candidate = staged_file(paths, f"{doc_id}.approve-candidate.md")
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
            lock_path: str | Path | None = None, project=None) -> dict:
    """Promuove un documento dallo staging a docs/<categoria>/<nome_file> senza
    indicizzarlo: l'aggiornamento dell'indice è un'azione separata. Scrive solo il .md
    composto; l'originale resta in staging.

    Ordine: validazioni rapide (stato staged, categoria, nome file, destinazione libera) →
    SOTTO WRITER LOCK: ricontrollo di stato e destinazione (nell'attesa un'altra richiesta
    può aver approvato lo stesso documento o occupato lo stesso nome), composizione del
    frontmatter conforme e validazione parse/chunking, creazione ESCLUSIVA del file,
    journal. Un callback `reindex` esplicito permette ancora l'indicizzazione sincrona:
    se fallisce si rimuove solo il file creato da questa richiesta, e solo se è ancora
    quello scritto qui; il documento resta in staging con l'errore, riprovabile.

    Un secondo approve dello stesso id fallisce con DocumentAlreadyProcessedError senza
    alcun effetto (idempotenza degli errori, mai doppio file)."""
    paths = ensure_staging_dirs(base_dir, project=project)
    _require_staged(paths, doc_id)
    if categoria not in CATEGORY_CLASSIFICATION:
        raise InvalidCategoryError(
            f"categoria inesistente: {categoria!r} "
            f"(ammesse: {', '.join(sorted(CATEGORY_CLASSIFICATION))})"
        )
    nome = _sanitize_target_filename(nome_file)
    docs_root = _unlinked(project.docs_dir if project else Path(docs_dir) if docs_dir is not None else DOCS_DIR)
    target = _unlinked(docs_root / categoria / nome)
    occupato = (f"esiste già un file {nome!r} in docs/{categoria}/: mai sovrascrittura — "
                f"scegli un altro nome")
    if target.exists():
        raise TargetFileExistsError(occupato)

    try:
        rel_path = target.resolve().relative_to(_unlinked(project.root if project else PROJECT_ROOT)).as_posix()
        changed_paths: list[str] | None = [rel_path]
    except ValueError:
        # docs_dir fuori dal repo (test/sandbox): nessuna restrizione del delta,
        # incremental_index considera l'intero docs_dir come sempre.
        rel_path = str(target)
        changed_paths = None

    lock_kwargs = {'project': project} if project else {}
    with indexing_lock, writer_lock(timeout_seconds=lock_timeout_seconds, lock_path=lock_path, **lock_kwargs):
        entry = _require_staged(paths, doc_id)
        staged_markdown = staged_file(paths, entry["files"]["markdown"]).read_text(encoding="utf-8")
        composed = _compose_document(entry, categoria, nome, staged_markdown)
        _validate_composed(paths, doc_id, composed)
        target = _unlinked(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            # "x": fallisce se il file esiste, anche se creato fuori da questo processo.
            with target.open("x", encoding="utf-8") as fh:
                fh.write(composed)
        except FileExistsError as exc:
            raise TargetFileExistsError(occupato) from exc
        written = target.read_bytes()
        try:
            stats = reindex(changed_paths) if reindex is not None else {}
        except Exception as exc:
            # docs/ e indice devono restare coerenti: senza reindex riuscito il file di QUESTA
            # richiesta non sopravvive in docs/. Se nel frattempo è cambiato non è più nostro.
            try:
                if _unlinked(target).read_bytes() == written:
                    _unlinked(target).unlink()
            except OSError:
                pass
            _append_journal(paths, {**entry, "approve_error": {
                "at": _now_iso(), "categoria": categoria, "nome_file": nome,
                "errore": "Indicizzazione del documento non riuscita." if project else f"{type(exc).__name__}: {exc}"[:500]}})
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
def reject(doc_id: str, motivo: str = "", *, base_dir: str | Path | None = None,
           lock_timeout_seconds: float = 30, lock_path: str | Path | None = None, project=None) -> dict:
    """Rifiuta un documento in staging: entry 'rejected' nel journal (col motivo) e file
    spostati in staging/rejected/. docs/ e indice NON vengono toccati — non c'è nulla da
    toccare: nulla era uscito dallo staging.

    Sotto lo stesso writer lock di approve, con lo stato ricontrollato dentro: un rifiuto che
    arriva mentre lo stesso documento viene pubblicato attende e trova lo stato già cambiato,
    invece di spostarne i file."""
    paths = ensure_staging_dirs(base_dir, project=project)
    _require_staged(paths, doc_id)
    lock_kwargs = {'project': project} if project else {}
    with writer_lock(timeout_seconds=lock_timeout_seconds, lock_path=lock_path, **lock_kwargs):
        entry = _require_staged(paths, doc_id)
        moved: dict[str, str] = {}
        for key, name in (entry.get("files") or {}).items():
            src = staged_file(paths, name)
            if src.exists():
                dst = staged_file(paths, name, 'rejected')
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

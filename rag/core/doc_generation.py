"""S3 dell'evoluzione Intake & Import (piano: docs/00_meta_governance/piano_intake_import.md):
generazione di documentazione via Ollama, GROUNDED nel Graph RAG (hybrid_search sulla
descrizione, stesso meccanismo di /ask) e nelle lezioni delle canvas review archiviate
(core.canvas_review.retrieve_canvas_lessons, stesso meccanismo del Canvas). VINCOLO LLM:
qwen3.5:9b, num_ctx 16384, think:false (core/llm.py) — non toccati qui.

Nessun percorso privilegiato verso docs/: ogni documento generato e validato entra in
staging (core.intake.stage_document, source="generated") ed è approvabile SOLO dal ciclo
di review S2, esattamente come un documento importato. Un documento che non supera la
validazione viene scartato con il motivo registrato nel journal, mai silenziosamente perso.

Pattern job ASYNC: GenerationManager esegue il lavoro (I/O rete verso Ollama + retrieval)
su un thread daemon in background, stesso principio di api.reindex.ReindexManager — qui
senza coda/coalescing perché i job di generazione sono indipendenti (scrivono solo in
staging/; il writer lock protegge il solo aggiornamento dei metadati)."""
from __future__ import annotations

import re
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from core import canvas_review, intake, llm, retrieval
from core.chunking import chunk_markdown, parse_markdown_file, split_frontmatter
from core.config import INTAKE_GENERATION_MAX_FILES
from core.writer_lock import writer_lock

# Purpose LLM riusato dalla generazione: stesso ruolo del Canvas (documento markdown
# grounded, nessuna chiamata "a caldo" senza contesto) — non si introduce un nuovo purpose
# in core/llm.py per questa sessione (S3 tocca solo doc_generation.py e routes_intake.py).
_GENERATION_PURPOSE = "canvas"

# Riga esatta che separa un documento generato dal successivo nell'output del modello.
_DOC_SEPARATOR = "===DOC==="

# Retrieval di grounding: stessi ordini di grandezza del contesto normativo del Canvas.
_GROUNDING_TOP_K = 10
_GROUNDING_MAX_CHUNKS = 8
_GROUNDING_MAX_CHARS_PER_CHUNK = 2500


class GenerationError(RuntimeError):
    """Errore del job di generazione (LLM non raggiungibile, validazione impossibile)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Grounding: contesto normativo (hybrid_search) + lezioni dalle canvas review
# ---------------------------------------------------------------------------
def _grounded_context(descrizione: str, *, qdrant, embed_model, colbert_store: dict | None,
                      chunks_store: dict | None, search=None) -> str:
    """Sezioni più pertinenti a `descrizione` (hybrid_search, core.retrieval), serializzate
    con citazione "doc_id § sezione". '' se manca qualunque risorsa di retrieval: la
    generazione prosegue senza grounding invece di fallire (stessa tolleranza di
    canvas_review.retrieve_canvas_lessons)."""
    if qdrant is None or embed_model is None or not chunks_store:
        return ""
    try:
        results = (search or retrieval.hybrid_search)(
            descrizione, _GROUNDING_TOP_K, qdrant=qdrant, embed_model=embed_model,
            colbert_store=colbert_store or {},
        )
    except Exception:
        return ""

    parts: list[str] = []
    seen: set[str] = set()
    for r in results:
        cid = r.get("chunk_id")
        entry = chunks_store.get(cid) if cid else None
        if entry is None or cid in seen:
            continue
        seen.add(cid)
        text = entry["text"]
        if len(text) > _GROUNDING_MAX_CHARS_PER_CHUNK:
            text = text[:_GROUNDING_MAX_CHARS_PER_CHUNK].rstrip() + "\n… [sezione troncata] …"
        parts.append(f"--- {r['doc_id']} § {r.get('section', '')} ---\n{text}")
        if len(parts) >= _GROUNDING_MAX_CHUNKS:
            break
    return "\n\n".join(parts)


def _canvas_lessons(descrizione: str, *, qdrant, embed_model, colbert_store: dict | None,
                    chunks_store: dict | None) -> str:
    """Lezioni dalle canvas review archiviate più simili (stesso meccanismo del Canvas,
    core.canvas_review.retrieve_canvas_lessons): '' se non ce ne sono o l'indice non è pronto."""
    return canvas_review.retrieve_canvas_lessons(
        descrizione, qdrant=qdrant, embed_model=embed_model,
        colbert_store=colbert_store, chunks_store=chunks_store or {},
    )


# ---------------------------------------------------------------------------
# Prompt e split dell'output multi-documento
# ---------------------------------------------------------------------------
def build_generation_prompt(descrizione: str, n_file: int, categoria_target: str,
                            contesto: str, lessons: str) -> str:
    """Prompt deterministico per generare `n_file` documenti Markdown grounded."""
    lessons_block = f"\n--- LEZIONI DALLE CHANGE PRECEDENTI ---\n{lessons}\n" if lessons else ""
    return f"""Sei un Tech Writer. Devi generare ESATTAMENTE {n_file} documenti Markdown distinti
per il seguente sviluppo: {descrizione}

I documenti sono destinati alla categoria docs/{categoria_target}.

--- CONTESTO NORMATIVO RECUPERATO DAL GRAPH RAG (citazioni "documento § sezione") ---
{contesto if contesto else "(nessun contesto normativo pertinente recuperato)"}
{lessons_block}
REGOLE DI FORMATO (obbligatorie):
- Ogni documento inizia con un blocco frontmatter YAML delimitato da `---` con SOLO i
  campi `title` (titolo breve) e `scope` (una frase che ne descrive lo scopo).
- Dopo il frontmatter, un titolo `# Titolo` seguito da una o più sezioni `##` con contenuto
  reale e specifico (niente placeholder tipo "TODO" o "da definire").
- Separa OGNI documento dal successivo con una riga contenente ESATTAMENTE `{_DOC_SEPARATOR}`
  (nessun altro testo su quella riga; nessun separatore dopo l'ultimo documento).
- Nessun testo introduttivo o conclusivo fuori dai {n_file} documenti.
"""


def split_generated_documents(raw_output: str, n_file: int) -> list[str]:
    """Divide l'output grezzo del modello nei singoli documenti candidati (per il
    separatore `{_DOC_SEPARATOR}`), scartando parti vuote e troncando a `n_file`: eventuali
    documenti in eccesso non vengono nemmeno validati. Non valuta il CONTENUTO: quello è
    compito di `_validate_generated_markdown`."""
    parts = [p.strip() for p in raw_output.split(_DOC_SEPARATOR)]
    return [p for p in parts if p][:max(1, n_file)]


# ---------------------------------------------------------------------------
# Normalizzazione dell'output del modello PRIMA della validazione.
#
# Le REGOLE DI FORMATO del prompt sono istruzioni, non garanzie: un modello locale le
# viola in modi ricorrenti e sempre gli stessi tre. Ciascuno costava l'intero documento
# (scartato in validazione, decine di secondi di GPU buttati) pur avendo un CORPO
# perfettamente valido — e il frontmatter di un documento staged è comunque materiale
# di passaggio, RIGENERATO da capo all'approve (core.intake._compose_document).
# Si ripara quindi il contorno e si tiene il corpo, invece di scartare tutto.
# ---------------------------------------------------------------------------

# 1) L'intero documento avvolto in un fence ```markdown … ```
_WRAPPING_FENCE_RE = re.compile(r"\A```[A-Za-z0-9_+-]*[ \t]*\r?\n(.*?)\r?\n```[ \t]*\Z", re.DOTALL)

# 2) Riga di frontmatter plausibile: `chiave: valore` o continuazione indentata.
_FM_FIELD_RE = re.compile(r"^[A-Za-z_][\w .-]*:(?:\s|$)")


def _unwrap_code_fence(text: str) -> str:
    match = _WRAPPING_FENCE_RE.match(text)
    return match.group(1).strip() if match else text


def _close_unterminated_frontmatter(text: str) -> str:
    """Chiude un frontmatter aperto e mai chiuso, inserendo il `---` mancante subito dopo
    l'ultima riga che somiglia a un campo. Senza questa riparazione il blocco resta aperto
    e il corpo intero vale come frontmatter — l'origine dello ScannerError su `- **…**:`
    (il `*` apre un alias YAML)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    if split_frontmatter(text)[0] is not None:
        return text  # già chiuso: niente da riparare
    end = 1
    while end < len(lines):
        line = lines[end]
        indented_continuation = line[:1] in (" ", "\t") and line.strip()
        if not (_FM_FIELD_RE.match(line) or indented_continuation):
            break
        end += 1
    if end == 1:
        return text  # nessun campo: quel `---` non era un frontmatter, resta nel corpo
    lines.insert(end, "---")
    return "\n".join(lines)


def _drop_unparsable_frontmatter(text: str) -> str:
    """Frontmatter presente ma non caricabile come mapping YAML (`title: Progetto: X`,
    valori che iniziano per `*`, liste malformate): lo si toglie e si tiene il corpo.
    Nulla va perso — `title`/`scope` generati dal modello non hanno alcun lettore a valle:
    il frontmatter conforme di docs/ lo ricalcola l'approve (core.intake._compose_document,
    che prende il titolo dall'H1), quindi vale la pena tenere il documento e non il
    contorno. Se il corpo è vuoto non si tocca niente: lì lo scarto è corretto."""
    fm_text, body = split_frontmatter(text)
    if fm_text is None:
        return text
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        data = None
    if isinstance(data, dict) or not body.strip():
        return text
    return body.lstrip("\n")


def normalize_generated_markdown(markdown: str) -> str:
    """Ripara i modi ricorrenti in cui il modello sbaglia il CONTORNO di un documento
    (fence di avvolgimento, frontmatter non chiuso, frontmatter non caricabile) senza
    mai alterarne il corpo. Idempotente: su un documento già conforme non cambia nulla."""
    text = _unwrap_code_fence(markdown.strip())
    text = _close_unterminated_frontmatter(text)
    return _drop_unparsable_frontmatter(text)


# ---------------------------------------------------------------------------
# Validazione: stesso criterio di core.intake._validate_composed (parse_markdown_file
# senza eccezioni + almeno una sezione non vuota dopo il chunking), su un file candidato
# temporaneo mai scritto in staging né altrove.
# ---------------------------------------------------------------------------
def _validate_generated_markdown(markdown: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(markdown)
        tmp_path = fh.name
    try:
        try:
            metadata, body = parse_markdown_file(tmp_path)
        except Exception as exc:
            raise GenerationError(
                f"frontmatter generato non parsabile ({type(exc).__name__}: {exc})"
            ) from exc
        if not body.strip():
            raise GenerationError("corpo vuoto dopo la separazione del documento")
        chunks = chunk_markdown("generated-validation.md",
                                metadata if isinstance(metadata, dict) else {}, body)
        if not any(c.get("text", "").strip() for c in chunks):
            raise GenerationError("nessuna sezione non vuota dopo il chunking")
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Journal: arricchimento metadata dei documenti staged + traccia degli scartati.
# Nessuna modifica a core/intake.py: si riusa il journal append-only pubblico
# (ensure_staging_dirs) con lo stesso principio "ultima riga per id vince" già
# implementato da core.intake._journal_state — una riga in più per lo stesso id
# aggiorna ciò che list_staged/get_preview vedono, senza duplicare la logica di staging.
# ---------------------------------------------------------------------------
def _append_journal_line(base_dir, record: dict) -> None:
    intake._append_journal(intake.ensure_staging_dirs(base_dir), record)


def _attach_generation_metadata(base_dir, record: dict, extra: dict) -> dict:
    """Arricchisce l'entry appena stagizzata coi metadata di generazione (descrizione
    richiesta, modello, latenze): core.intake.stage_document non li conosce (sono un
    concetto solo di S3), quindi si appende una riga aggiornata invece di estendere la
    firma di stage_document per un caso d'uso che non le appartiene."""
    paths = intake.ensure_staging_dirs(base_dir)
    # Dopo stage_document la review può aver già cambiato stato o file: arricchire
    # l'ultima entry sotto lo stesso lock di approve/reject/refine, senza riaprirla.
    with writer_lock(timeout_seconds=30):
        latest = intake._journal_state(paths).get(record["id"])
        if latest is None:
            raise intake.StagedDocumentNotFoundError(record["id"])
        updated = {**latest, "metadata": {**(latest.get("metadata") or {}), **extra}}
        intake._append_journal(paths, updated)
    return updated


def _journal_discarded(base_dir, *, indice: int, motivo: str) -> dict:
    """Traccia nel journal un documento generato SCARTATO in validazione: mai entrato in
    staging (nessun file scritto), ma il motivo resta rintracciabile. Stato 'discarded',
    ignorato da list_staged/get_preview/reject/approve (guardano solo 'staged')."""
    record = {
        "id": uuid.uuid4().hex[:12],
        "status": "discarded",
        "source": "generated",
        "indice": indice,
        "motivo": motivo,
        "discarded_at": _now_iso(),
    }
    _append_journal_line(base_dir, record)
    return record


# ---------------------------------------------------------------------------
# generate_docs: l'intero job, SINCRONO (pensato per girare su un thread di background,
# vedi GenerationManager sotto — mai sull'event loop).
# ---------------------------------------------------------------------------
def generate_docs(descrizione: str, n_file: int, categoria_target: str, *,
                  qdrant=None, embed_model=None, colbert_store: dict | None = None,
                  chunks_store: dict | None = None,
                  base_dir: str | Path | None = None,
                  search=None, generate=None) -> dict:
    """Genera fino a `n_file` documenti (clampato a INTAKE_GENERATION_MAX_FILES) grounded
    su `descrizione`, li valida e li mette in staging (source "generated"). NESSUNA
    scrittura in docs/: solo staging, come qualunque documento importato — approvabile
    solo dal ciclo S2.

    Restituisce {"generati": [...record staged...], "scartati": [{"indice", "motivo"}...],
    "n_generati", "n_scartati", "latency": {"retrieval_ms", "generation_ms", "total_ms"}}.

    Solleva GenerationError se la chiamata LLM fallisce (Ollama irraggiungibile, timeout):
    il chiamante (GenerationManager) la registra come job "failed" con errore leggibile,
    mai un'eccezione grezza non gestita."""
    total_start = time.time()
    n_file = max(1, min(int(n_file), INTAKE_GENERATION_MAX_FILES))

    retrieval_start = time.time()
    contesto = _grounded_context(
        descrizione, qdrant=qdrant, embed_model=embed_model,
        colbert_store=colbert_store, chunks_store=chunks_store, search=search,
    )
    lessons = _canvas_lessons(
        descrizione, qdrant=qdrant, embed_model=embed_model,
        colbert_store=colbert_store, chunks_store=chunks_store,
    )
    latency_retrieval_ms = round((time.time() - retrieval_start) * 1000, 2)

    prompt = build_generation_prompt(descrizione, n_file, categoria_target, contesto, lessons)
    generate_fn = generate or (lambda p: llm.generate(p, purpose=_GENERATION_PURPOSE))

    generation_start = time.time()
    try:
        raw_output = generate_fn(prompt)
    except llm.LLMError as exc:
        raise GenerationError(f"generazione fallita: {exc}") from exc
    latency_generation_ms = round((time.time() - generation_start) * 1000, 2)

    try:
        _, modello = llm.resolve(_GENERATION_PURPOSE)
    except llm.LLMError:
        modello = None

    candidates = [normalize_generated_markdown(c)
                  for c in split_generated_documents(raw_output, n_file)]

    generati: list[dict] = []
    scartati: list[dict] = []
    for indice, markdown in enumerate(candidates, start=1):
        try:
            _validate_generated_markdown(markdown)
        except GenerationError as exc:
            _journal_discarded(base_dir, indice=indice, motivo=str(exc))
            scartati.append({"indice": indice, "motivo": str(exc)})
            continue

        filename = f"generato-{uuid.uuid4().hex[:8]}.md"
        try:
            record = intake.stage_document(
                filename, markdown.encode("utf-8"), base_dir=base_dir, source="generated",
            )
        except intake.IntakeError as exc:
            motivo = f"staging fallito: {exc}"
            _journal_discarded(base_dir, indice=indice, motivo=motivo)
            scartati.append({"indice": indice, "motivo": motivo})
            continue

        record = _attach_generation_metadata(base_dir, record, {
            "descrizione_richiesta": descrizione,
            "categoria_suggerita": categoria_target,
            "modello": modello,
            "latenze": {
                "retrieval_ms": latency_retrieval_ms,
                "generation_ms": latency_generation_ms,
            },
        })
        generati.append(record)

    latency_total_ms = round((time.time() - total_start) * 1000, 2)
    return {
        "generati": generati,
        "scartati": scartati,
        "n_generati": len(generati),
        "n_scartati": len(scartati),
        "latency": {
            "retrieval_ms": latency_retrieval_ms,
            "generation_ms": latency_generation_ms,
            "total_ms": latency_total_ms,
        },
    }


# ---------------------------------------------------------------------------
# Job async in background (pattern api.reindex.ReindexManager): POST risponde subito col
# job_id, GET interroga lo stato. Nessuna coda/coalescing: i job di generazione non
# toccano mai docs/ né il writer lock (solo staging/), possono girare in parallelo.
# ---------------------------------------------------------------------------
class GenerationJob:
    """Stato di un singolo job di generazione. `status` ∈ {pending, running, done, failed}."""

    def __init__(self, descrizione: str, n_file: int, categoria_target: str):
        self.id: str = uuid.uuid4().hex
        self.status: str = "pending"
        self.descrizione = descrizione
        self.n_file = n_file
        self.categoria_target = categoria_target
        self.created_at: str = _now_iso()
        self.finished_at: str | None = None
        self.result: dict | None = None
        self.error: str | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.id,
            "status": self.status,
            "descrizione": self.descrizione,
            "n_file": self.n_file,
            "categoria_target": self.categoria_target,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
        }


class GenerationManager:
    """Avvia job di generazione in thread daemon e ne conserva lo stato in memoria
    (nessuna persistenza su journal: a differenza del reindex, un job di generazione
    perso a un riavvio non lascia nulla di incoerente — i documenti già staged restano
    nel journal di core.intake)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, GenerationJob] = {}
        self._threads: list[threading.Thread] = []

    def start(self, descrizione: str, n_file: int, categoria_target: str, run_fn) -> GenerationJob:
        """Avvia subito un job in background. `run_fn()` esegue il lavoro (bloccante,
        nessun argomento: il chiamante chiude sulle risorse di runtime) e deve restituire
        il dict di `generate_docs`."""
        job = GenerationJob(descrizione, n_file, categoria_target)
        with self._lock:
            self._jobs[job.id] = job
            thread = threading.Thread(
                target=self._run, args=(job, run_fn),
                name=f"docgen-{job.id[:8]}", daemon=True,
            )
            self._threads.append(thread)
        thread.start()
        return job

    def get(self, job_id: str) -> GenerationJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def join_all(self, timeout: float = 5.0) -> bool:
        """TEST-ONLY: attende la terminazione di tutti i thread dispatchati finora."""
        deadline = time.monotonic() + timeout
        for thread in list(self._threads):
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        return all(not t.is_alive() for t in self._threads)

    def _run(self, job: GenerationJob, run_fn) -> None:
        job.status = "running"
        try:
            job.result = run_fn()
            job.status = "done"
        except Exception as exc:
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
        finally:
            job.finished_at = _now_iso()

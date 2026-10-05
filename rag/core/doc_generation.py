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

import os
import re
import tempfile
import threading
import time
import uuid
from collections import deque
from collections.abc import Mapping
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
def _grounded_context(descrizione: str, *, qdrant, embed_model, colbert_store: Mapping | None,
                      chunks_store: dict | None, search=None, project=None, collection_name=None) -> str:
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
            **({"project": project, "collection_name": collection_name or project.collection_name} if project else {}),
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


def _canvas_lessons(descrizione: str, *, qdrant, embed_model, colbert_store: Mapping | None,
                    chunks_store: dict | None, project=None, collection_name=None) -> str:
    """Lezioni dalle canvas review archiviate più simili (stesso meccanismo del Canvas,
    core.canvas_review.retrieve_canvas_lessons): '' se non ce ne sono o l'indice non è pronto."""
    return canvas_review.retrieve_canvas_lessons(
        descrizione, qdrant=qdrant, embed_model=embed_model,
        colbert_store=colbert_store, chunks_store=chunks_store or {},
        project=project, collection_name=collection_name,
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
def _append_journal_line(base_dir, record: dict, *, project=None) -> None:
    intake._append_journal(intake.ensure_staging_dirs(base_dir, project=project), record)


def _attach_generation_metadata(base_dir, record: dict, extra: dict, *, project=None) -> dict:
    """Arricchisce l'entry appena stagizzata coi metadata di generazione (descrizione
    richiesta, modello, latenze): core.intake.stage_document non li conosce (sono un
    concetto solo di S3), quindi si appende una riga aggiornata invece di estendere la
    firma di stage_document per un caso d'uso che non le appartiene."""
    paths = intake.ensure_staging_dirs(base_dir, project=project)
    # Dopo stage_document la review può aver già cambiato stato o file: arricchire
    # l'ultima entry sotto lo stesso lock di approve/reject/refine, senza riaprirla.
    with writer_lock(timeout_seconds=30, **({"project": project} if project else {})):
        latest = intake._journal_state(paths).get(record["id"])
        if latest is None:
            raise intake.StagedDocumentNotFoundError(record["id"])
        updated = {**latest, "metadata": {**(latest.get("metadata") or {}), **extra}}
        intake._append_journal(paths, updated)
    return updated


def _journal_discarded(base_dir, *, indice: int, motivo: str, project=None) -> dict:
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
    _append_journal_line(base_dir, record, project=project)
    return record


# ---------------------------------------------------------------------------
# generate_docs: l'intero job, SINCRONO (pensato per girare su un thread di background,
# vedi GenerationManager sotto — mai sull'event loop).
# ---------------------------------------------------------------------------
def generate_docs(descrizione: str, n_file: int, categoria_target: str, *,
                  qdrant=None, embed_model=None, colbert_store: Mapping | None = None,
                  chunks_store: dict | None = None,
                  base_dir: str | Path | None = None,
                  search=None, generate=None, project=None, collection_name=None) -> dict:
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
        colbert_store=colbert_store, chunks_store=chunks_store, search=search, project=project, collection_name=collection_name,
    )
    lessons = _canvas_lessons(
        descrizione, qdrant=qdrant, embed_model=embed_model,
        colbert_store=colbert_store, chunks_store=chunks_store, project=project, collection_name=collection_name,
    )
    latency_retrieval_ms = round((time.time() - retrieval_start) * 1000, 2)

    prompt = build_generation_prompt(descrizione, n_file, categoria_target, contesto, lessons)
    if project is not None:
        prompt = f"Project ID: {project.id}\n" + prompt
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
            _journal_discarded(base_dir, indice=indice, motivo=str(exc), project=project)
            scartati.append({"indice": indice, "motivo": str(exc)})
            continue

        filename = f"generato-{uuid.uuid4().hex[:8]}.md"
        try:
            record = intake.stage_document(
                filename, markdown.encode("utf-8"), base_dir=base_dir, source="generated", project=project,
            )
        except intake.IntakeError as exc:
            motivo = f"staging fallito: {exc}"
            _journal_discarded(base_dir, indice=indice, motivo=motivo, project=project)
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
        }, project=project)
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
# toccano mai docs/ né il writer lock (solo staging/), possono girare in parallelo —
# ma non senza limite. Ogni job è un thread che tiene occupato il modello per minuti:
# oltre VIBECRAFT_GENERATION_MAX_ACTIVE job attivi IN TOTALE fra i manager che
# condividono lo stesso GenerationSlots (in api/routes_intake: generate, refine e
# project brief) il POST risponde 429 (stesso contratto di VIBECRAFT_ASK_MAX_ACTIVE per
# /ask), invece di accodare thread senza tetto. Il registro dei job TERMINATI è limitato,
# per manager, a VIBECRAFT_GENERATION_MAX_FINISHED voci (si scartano i più vecchi; i job
# in corso non vengono mai scartati), altrimenti _jobs cresceva per tutta la vita del
# processo. Entrambe le variabili si leggono alla prima `start`, come i limiti di /ask.
# ---------------------------------------------------------------------------
def _env_positive_int(name: str, default: int) -> int:
    """Intero > 0 da variabile d'ambiente; un valore non valido è un errore esplicito
    (RuntimeError col nome della variabile), mai un limite silenziosamente diverso."""
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
        if value <= 0:
            raise ValueError
    except ValueError:
        raise RuntimeError(f"{name} deve essere un intero positivo (trovato {raw!r}).") from None
    return value


class GenerationBusyError(RuntimeError):
    """Tetto di job attivi raggiunto: la route la traduce in 429."""


class GenerationSlots:
    """Tetto di job attivi, condivisibile fra più GenerationManager. `max_active` None =
    letto da VIBECRAFT_GENERATION_MAX_ACTIVE (default 2) alla prima acquisizione."""

    def __init__(self, max_active: int | None = None):
        if max_active is not None and max_active <= 0:
            raise ValueError("max_active deve essere positivo")
        self._lock = threading.Lock()
        self._max_active = max_active
        self.active = 0

    def acquire(self) -> None:
        """Occupa uno slot o solleva GenerationBusyError (mai attesa: niente coda)."""
        with self._lock:
            if self._max_active is None:
                self._max_active = _env_positive_int("VIBECRAFT_GENERATION_MAX_ACTIVE", 2)
            if self.active >= self._max_active:
                raise GenerationBusyError(
                    f"Troppi job LLM attivi ({self.active}/{self._max_active} fra generazione, "
                    "raffinazione e project brief): riprova quando uno dei job in corso è terminato.")
            self.active += 1

    def release(self) -> None:
        with self._lock:
            if self.active > 0:
                self.active -= 1


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
    nel journal di core.intake).

    Limiti: gli slot di job attivi vengono da `slots` (condiviso fra manager; senza,
    un GenerationSlots privato) e `start` solleva GenerationBusyError quando sono
    esauriti. Per manager, sotto `_lock`: al più `max_finished` job terminati conservati
    per il polling di stato, e `_threads` contiene solo i thread vivi (ogni thread si
    rimuove da sé a fine job)."""

    def __init__(self, slots: GenerationSlots | None = None, max_finished: int | None = None):
        if max_finished is not None and max_finished <= 0:
            raise ValueError("max_finished deve essere positivo")
        self._lock = threading.Lock()
        self._jobs: dict[str, GenerationJob] = {}
        self._threads: list[threading.Thread] = []
        self._slots = slots if slots is not None else GenerationSlots()
        self._max_finished = max_finished  # None = letto dall'env alla prima start
        # Id dei job terminati in ordine di fine: la testa è il primo da scartare.
        self._finished: deque[str] = deque()

    def start(self, descrizione: str, n_file: int, categoria_target: str, run_fn) -> GenerationJob:
        """Avvia subito un job in background. `run_fn()` esegue il lavoro (bloccante,
        nessun argomento: il chiamante chiude sulle risorse di runtime) e deve restituire
        il dict di `generate_docs`. GenerationBusyError se il tetto di job attivi è pieno:
        nessun job viene registrato né thread creato."""
        with self._lock:
            if self._max_finished is None:
                self._max_finished = _env_positive_int("VIBECRAFT_GENERATION_MAX_FINISHED", 100)
        self._slots.acquire()
        job = GenerationJob(descrizione, n_file, categoria_target)
        with self._lock:
            self._jobs[job.id] = job
            thread = threading.Thread(
                target=self._run, args=(job, run_fn),
                name=f"docgen-{job.id[:8]}", daemon=True,
            )
            self._threads.append(thread)
        try:
            thread.start()
        except RuntimeError:
            # Thread non avviabile (risorse del processo esaurite): lo slot va restituito,
            # altrimenti resterebbe occupato per sempre.
            with self._lock:
                self._jobs.pop(job.id, None)
                self._threads.remove(thread)
            self._slots.release()
            raise
        return job

    def get(self, job_id: str) -> GenerationJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def join_all(self, timeout: float = 5.0) -> bool:
        """TEST-ONLY: attende la terminazione di tutti i thread dispatchati finora."""
        deadline = time.monotonic() + timeout
        with self._lock:
            threads = list(self._threads)
        for thread in threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        return all(not t.is_alive() for t in threads)

    def _run(self, job: GenerationJob, run_fn) -> None:
        job.status = "running"
        result, error = None, None
        try:
            result = run_fn()
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        finally:
            # Slot restituito PRIMA di rendere visibile lo stato finale: un client che
            # vede "done" e rilancia subito non deve ricevere un 429 spurio.
            self._slots.release()
            job.result, job.error = result, error
            job.finished_at = _now_iso()
            job.status = "failed" if error is not None else "done"
            self._forget(job)

    def _forget(self, job: GenerationJob) -> None:
        """Fine job: rimuove il thread corrente da `_threads` e applica la retention ai
        soli job terminati (quelli in corso non sono mai nella coda)."""
        with self._lock:
            try:
                self._threads.remove(threading.current_thread())
            except ValueError:
                pass
            self._finished.append(job.id)
            while len(self._finished) > self._max_finished:
                self._jobs.pop(self._finished.popleft(), None)

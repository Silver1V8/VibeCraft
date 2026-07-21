"""Gestione del reindex incrementale in background: coda con coalescing (un job in esecuzione
+ al massimo un pending fuso), con job-id e stato interrogabile, più l'estrazione dei path
modificati da un payload webhook GitLab (push/merge).

Questo modulo è PURO rispetto allo strato HTTP e all'indicizzazione: non importa FastAPI né
core.indexing. Riceve la funzione di reindex e la callback di reload iniettate dal router
(api/routes_reindex.py), così la logica di concorrenza è testabile con fake leggeri."""
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.writer_lock import writer_lock

logger = logging.getLogger(__name__)

# Timeout di acquisizione del writer lock cross-processo attorno all'esecuzione di un
# job: più largo del default CLI (5s) perché il contendente tipico è una CLI che sta
# finendo, ma non infinito — al timeout il job fallisce con l'errore del lock nel journal.
_WRITER_LOCK_TIMEOUT_SECONDS = 30

# Soglia di rotazione del journal: oltre ~1MB il file viene compattato tenendo solo
# l'ultimo stato di ogni job.
_JOURNAL_MAX_BYTES = 1_000_000

# Stati terminali: un job in uno di questi non è "in volo". "completed_not_promoted" è
# un full riuscito la cui versione NON è stata promossa (eval gate sotto soglia): la
# build esiste su disco ma CURRENT non si è mosso.
_TERMINAL_STATES = ("completed", "completed_not_promoted", "failed", "interrupted")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_gitlab_paths(payload) -> list[str] | None:
    """Estrae i path modificati da un payload webhook GitLab, per limitare il delta.

    - Push event: unione di `added`/`modified`/`removed` di tutti i `commits`.
    - Override esplicito: un corpo `{"paths": [...]}` è accettato tal quale (utile per
      trigger manuali o webhook custom).
    - Merge request event (o payload senza liste di file): restituisce None → il reindex
      considera l'intero docs/ + code/ (il payload MR non porta l'elenco dei file).

    Restituisce una lista ordinata e deduplicata, oppure None se non c'è nulla di utile
    (nessun path ⇒ il chiamante fa un incrementale completo, non un no-op)."""
    if not isinstance(payload, dict):
        return None
    explicit = payload.get("paths")
    if isinstance(explicit, list):
        paths = {str(p).strip() for p in explicit if str(p).strip()}
        return sorted(paths) if paths else None
    commits = payload.get("commits")
    if isinstance(commits, list):
        paths: set[str] = set()
        for commit in commits:
            if not isinstance(commit, dict):
                continue
            for key in ("added", "modified", "removed"):
                for p in commit.get(key) or []:
                    if str(p).strip():
                        paths.add(str(p).strip())
        return sorted(paths) if paths else None
    return None


def _coalesce_paths(a: list[str] | None, b: list[str] | None) -> list[str] | None:
    """Fonde due insiemi di path per il coalescing della coda. None assorbe tutto: se una
    delle due richieste è "completa" (changed_paths=None ⇒ incrementale su tutto docs/+code/),
    il risultato è None. Altrimenti unione ordinata e deduplicata dei due insiemi."""
    if a is None or b is None:
        return None
    return sorted(set(a) | set(b))


class ReindexJob:
    """Stato di un singolo job di reindex. `status` ∈ {queued, running, completed, failed};
    `kind` ∈ {incremental, full} — un full è una ricostruzione completa (build_graph_and_index)
    e non ha changed_paths.

    Un job può nascere `queued` (accodato/fuso mentre un altro gira) e passare a `running`
    quando viene effettivamente avviato dal dispatch del pending a fine job precedente."""

    def __init__(self, changed_paths: list[str] | None, status: str = "running",
                 kind: str = "incremental"):
        self.id: str = uuid.uuid4().hex
        self.status: str = status
        self.kind: str = kind
        self.created_at: str = _now_iso()
        self.finished_at: str | None = None
        self.changed_paths: list[str] | None = changed_paths
        self.result: dict | None = None
        self.error: str | None = None
        # Callback iniettate dal chiamante: conservate sul job così un job accodato può
        # essere avviato dal dispatch del pending senza che il chiamante sia più presente.
        self._run_reindex = None
        self._on_success = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.id,
            "status": self.status,
            "kind": self.kind,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "changed_paths": self.changed_paths,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReindexJob":
        """Ricostruisce un job storico dal journal. Il job risultante è "morto": non ha
        callback (sono già state eseguite o perse col riavvio), serve solo alla lettura
        dello stato via get()/list_recent()."""
        job = cls.__new__(cls)
        job.id = data["job_id"]
        job.status = data.get("status", "interrupted")
        job.kind = data.get("kind", "incremental")
        job.created_at = data.get("created_at")
        job.finished_at = data.get("finished_at")
        job.changed_paths = data.get("changed_paths")
        job.result = data.get("result")
        job.error = data.get("error")
        job._run_reindex = None
        job._on_success = None
        return job


class ReindexManager:
    """Serializza i reindex con una coda a coalescing: al massimo uno in esecuzione e al
    massimo UN pending accodato. `start` non rifiuta mai — se un reindex è già in corso,
    accumula la richiesta in un unico slot pending, fondendo i changed_paths (coalescing).
    A fine job (successo O fallimento) il pending viene avviato automaticamente. Il lavoro
    gira su un thread daemon; a job riuscito invoca `on_success` per il reload in memoria."""

    def __init__(self, journal_path: str | Path | None = None):
        self._lock = threading.Lock()
        self._running_id: str | None = None
        self._pending: ReindexJob | None = None
        self._jobs: dict[str, ReindexJob] = {}
        # Persistenza opzionale: se journal_path è None (es. nei test unitari), il manager
        # resta interamente in memoria. Il journal ha un lock dedicato così l'I/O di append
        # non blocca la sezione critica della coda.
        self._journal_path: Path | None = Path(journal_path) if journal_path else None
        self._journal_lock = threading.Lock()
        # storico dei job (ordine di comparsa) per list_recent, indipendente dal dict.
        self._order: list[str] = []
        # Thread daemon dispatchati (append in _dispatch, sempre sotto self._lock): NON
        # serve al funzionamento normale, solo a join_all (vedi sotto) — il job passa a
        # uno stato terminale PRIMA che on_success sia stato invocato (vedi _run), quindi
        # un chiamante che osserva solo lo status può proseguire mentre il thread sta
        # ancora eseguendo side-effect (es. il reload in memoria). I test che vogliono la
        # sincronizzazione REALE con la fine del lavoro in background usano join_all.
        self._threads: list[threading.Thread] = []
        if self._journal_path is not None:
            self._load_journal()

    # ------------------------------------------------------------------
    # Persistenza (journal JSONL append-only + compattazione)
    # ------------------------------------------------------------------
    def _load_journal(self) -> None:
        """Ricostruisce lo storico dei job dal journal: l'ultima riga per job_id vince.
        I job rimasti non-terminali (running/queued: crash a metà) vengono marcati
        "interrupted" e la transizione viene ri-journalata così da persistere."""
        assert self._journal_path is not None
        if not self._journal_path.exists():
            return
        latest: dict[str, dict] = {}
        order: list[str] = []
        with self._journal_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except (ValueError, TypeError):
                    continue  # riga corrotta: la si salta, non si abortisce il boot
                job_id = rec.get("job_id")
                if not job_id:
                    continue
                if job_id not in latest:
                    order.append(job_id)
                latest[job_id] = rec

        interrupted: list[ReindexJob] = []
        for job_id in order:
            job = ReindexJob.from_dict(latest[job_id])
            if job.status not in _TERMINAL_STATES:
                # In volo al momento del crash: nessun thread lo sta più eseguendo.
                job.status = "interrupted"
                if job.finished_at is None:
                    job.finished_at = _now_iso()
                interrupted.append(job)
            self._jobs[job_id] = job
            self._order.append(job_id)

        # Persisti le transizioni "interrupted" così il prossimo load le vede terminali.
        for job in interrupted:
            self._append_journal(job.to_dict())
        self._maybe_compact()

    def _append_journal(self, record: dict) -> None:
        """Appende una riga JSON (col job serializzato) al journal, con flush. No-op se la
        persistenza è disabilitata."""
        if self._journal_path is None:
            return
        with self._journal_lock:
            self._journal_path.parent.mkdir(parents=True, exist_ok=True)
            with self._journal_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                fh.flush()

    def _maybe_compact(self) -> None:
        """Rotazione semplice: se il journal supera ~1MB, lo riscrive tenendo solo l'ultimo
        stato di ogni job (una riga per job, nell'ordine di comparsa)."""
        if self._journal_path is None:
            return
        with self._journal_lock:
            try:
                size = self._journal_path.stat().st_size
            except OSError:
                return
            if size <= _JOURNAL_MAX_BYTES:
                return
            with self._lock:
                snapshot = [self._jobs[jid].to_dict() for jid in self._order if jid in self._jobs]
            tmp = self._journal_path.with_suffix(self._journal_path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                for rec in snapshot:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
            os.replace(tmp, self._journal_path)

    def _record(self, job: ReindexJob) -> None:
        """Journala la transizione corrente di `job` e, se serve, compatta."""
        self._append_journal(job.to_dict())
        self._maybe_compact()

    def get(self, job_id: str) -> ReindexJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_recent(self, limit: int = 20) -> list[dict]:
        """Ultimi `limit` job serializzati, più recente prima — per debug e per la UI."""
        with self._lock:
            ids = self._order[-limit:] if limit else self._order[:]
            jobs = [self._jobs[jid] for jid in ids if jid in self._jobs]
        return [job.to_dict() for job in reversed(jobs)]

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running_id is not None

    @property
    def pending_id(self) -> str | None:
        with self._lock:
            return self._pending.id if self._pending is not None else None

    def start(self, changed_paths, run_reindex, on_success,
              kind: str = "incremental") -> tuple[ReindexJob, bool]:
        """Avvia o accoda un reindex in background. Restituisce `(job, queued)`:
        - `(job, False)` se parte subito (nessun reindex in corso);
        - `(job, True)` se è stato accodato o fuso nel pending esistente.

        `run_reindex(changed_paths) -> dict` esegue l'indicizzazione (bloccante);
        `on_success()` viene chiamato a fine job SOLO se riuscito (reload in memoria).
        `kind` è "incremental" (delta su changed_paths) o "full" (ricostruzione completa,
        senza changed_paths).

        Coalescing: se esiste già un pending, la nuova richiesta vi si fonde. Tra
        incrementali i changed_paths sono l'unione dei due insiemi, e None (richiesta
        completa) assorbe tutto; le callback restano quelle della prima richiesta accodata.
        Un full sussume qualunque incrementale: se arriva un full su un pending
        incremental, il pending DIVENTA full (kind, path azzerati e callback del full);
        un incremental su un pending full si fonde senza cambiare nulla."""
        # `to_record` accumula i job la cui transizione va journalata: il journal viene
        # scritto DOPO aver rilasciato self._lock (la compattazione riacquisisce il lock,
        # scriverlo qui dentro sarebbe un deadlock).
        to_record: list[ReindexJob] = []
        with self._lock:
            if self._running_id is None:
                job = self._make_job(changed_paths, run_reindex, on_success,
                                     status="running", kind=kind)
                self._running_id = job.id
                to_record.append(job)
                self._dispatch(job)
                result = (job, False)
            elif self._pending is not None:
                # Fusione nel pending esistente: un solo pending massimo.
                if self._pending.kind == "full":
                    pass  # un full pending sussume qualunque richiesta successiva
                elif kind == "full":
                    # Il full assorbe il pending incremental: il job cambia natura e
                    # prende le callback del full (build completa, non delta).
                    self._pending.kind = "full"
                    self._pending.changed_paths = None
                    self._pending._run_reindex = run_reindex
                    self._pending._on_success = on_success
                else:
                    self._pending.changed_paths = _coalesce_paths(
                        self._pending.changed_paths, changed_paths
                    )
                result = (self._pending, True)
            else:
                pending = self._make_job(changed_paths, run_reindex, on_success,
                                         status="queued", kind=kind)
                self._pending = pending
                to_record.append(pending)
                result = (pending, True)
        for job in to_record:
            self._record(job)  # transizione "created" (running o queued)
        return result

    def _make_job(self, changed_paths, run_reindex, on_success, status: str,
                  kind: str = "incremental") -> ReindexJob:
        job = ReindexJob(changed_paths, status=status, kind=kind)
        job._run_reindex = run_reindex
        job._on_success = on_success
        self._jobs[job.id] = job
        self._order.append(job.id)
        return job

    def _dispatch(self, job: ReindexJob) -> None:
        """Lancia il thread daemon per `job`. Da chiamare con lo slot già assegnato (sempre
        sotto self._lock: sia da `start`, sia dal dispatch del pending in `_run`)."""
        thread = threading.Thread(
            target=self._run, args=(job,),
            name=f"reindex-{job.id[:8]}", daemon=True,
        )
        self._threads.append(thread)
        thread.start()

    def join_all(self, timeout: float = 5.0) -> bool:
        """TEST-ONLY: attende la terminazione di TUTTI i thread daemon finora dispatchati,
        incluse le callback on_success (es. reload_index_state) — non solo la transizione
        di stato del job, che passa a terminale PRIMA che on_success sia stata invocata
        (vedi _run). Un test che sincronizza solo su job.status/un Event nel body di
        run_reindex può proseguire (e finire, smontando capture/logging) mentre il thread
        sta ancora eseguendo il reload: usare join_all per una sincronizzazione reale prima
        che il test ritorni. Restituisce False se qualche thread è ancora vivo al timeout."""
        deadline = time.monotonic() + timeout
        for thread in list(self._threads):
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        return all(not t.is_alive() for t in self._threads)

    def _run(self, job: ReindexJob) -> None:
        try:
            # Writer lock cross-processo attorno alla SOLA esecuzione del reindex: server
            # e CLI (index.py) non scrivono mai gli artefatti in contemporanea. Un
            # WriterLockBusyError al timeout cade nell'except sotto: job "failed" con
            # l'errore del lock nel journal, slot liberato e pending dispatchato come
            # per qualunque altro fallimento.
            with writer_lock(timeout_seconds=_WRITER_LOCK_TIMEOUT_SECONDS):
                job.result = job._run_reindex(job.changed_paths)
            # Un run può declassare l'esito con result["job_status"]: oggi solo
            # "completed_not_promoted" (eval gate sotto soglia: versione costruita ma
            # CURRENT non spostato). Qualunque altro valore resta "completed".
            override = job.result.get("job_status") if isinstance(job.result, dict) else None
            job.status = "completed_not_promoted" if override == "completed_not_promoted" else "completed"
        except Exception as exc:
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
        finally:
            job.finished_at = _now_iso()
            # Sezione critica unica: libera lo slot e, se c'è un pending, lo promuove a
            # running e lo dispatcha PRIMA di rilasciare il lock. Così non c'è race tra la
            # fine di questo job e un `start` concorrente: o start vede lo slot occupato e
            # accoda (e noi lo raccogliamo qui), o lo vede libero e parte lui.
            next_job: ReindexJob | None = None
            with self._lock:
                self._running_id = None
                if self._pending is not None:
                    next_job = self._pending
                    self._pending = None
                    next_job.status = "running"
                    self._running_id = next_job.id
                    self._dispatch(next_job)
        # Journal fuori dal lock: transizione terminale di questo job e, se promosso, la
        # transizione "running" del pending.
        self._record(job)
        if next_job is not None:
            self._record(next_job)
        # on_success (reload in memoria) solo se la build è stata promossa: dopo un
        # "completed_not_promoted" CURRENT è invariato e non c'è nulla da ricaricare.
        if job.status == "completed":
            try:
                job._on_success()
            except Exception as exc:
                # Il reload è best-effort: reload_index_state è già tollerante agli
                # artefatti incoerenti; qui logghiamo soltanto senza far fallire il job.
                logger.warning("Reload post-reindex fallito (%s: %s).", type(exc).__name__, exc)

"""Gestione del reindex incrementale in background: coda con coalescing (un job in esecuzione
+ al massimo un pending fuso), con job-id e stato interrogabile, più l'estrazione dei path
modificati da un payload webhook GitLab (push/merge).

Questo modulo è PURO rispetto allo strato HTTP e all'indicizzazione: non importa FastAPI né
core.indexing. Riceve la funzione di reindex e la callback di reload iniettate dal router
(api/routes_reindex.py), così la logica di concorrenza è testabile con fake leggeri."""
import threading
import uuid
from datetime import datetime, timezone


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
    """Stato di un singolo job di reindex. `status` ∈ {queued, running, completed, failed}.

    Un job può nascere `queued` (accodato/fuso mentre un altro gira) e passare a `running`
    quando viene effettivamente avviato dal dispatch del pending a fine job precedente."""

    def __init__(self, changed_paths: list[str] | None, status: str = "running"):
        self.id: str = uuid.uuid4().hex
        self.status: str = status
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
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "changed_paths": self.changed_paths,
            "result": self.result,
            "error": self.error,
        }


class ReindexManager:
    """Serializza i reindex con una coda a coalescing: al massimo uno in esecuzione e al
    massimo UN pending accodato. `start` non rifiuta mai — se un reindex è già in corso,
    accumula la richiesta in un unico slot pending, fondendo i changed_paths (coalescing).
    A fine job (successo O fallimento) il pending viene avviato automaticamente. Il lavoro
    gira su un thread daemon; a job riuscito invoca `on_success` per il reload in memoria."""

    def __init__(self):
        self._lock = threading.Lock()
        self._running_id: str | None = None
        self._pending: ReindexJob | None = None
        self._jobs: dict[str, ReindexJob] = {}

    def get(self, job_id: str) -> ReindexJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running_id is not None

    @property
    def pending_id(self) -> str | None:
        with self._lock:
            return self._pending.id if self._pending is not None else None

    def start(self, changed_paths, run_reindex, on_success) -> tuple[ReindexJob, bool]:
        """Avvia o accoda un reindex in background. Restituisce `(job, queued)`:
        - `(job, False)` se parte subito (nessun reindex in corso);
        - `(job, True)` se è stato accodato o fuso nel pending esistente.

        `run_reindex(changed_paths) -> dict` esegue l'indicizzazione (bloccante);
        `on_success()` viene chiamato a fine job SOLO se riuscito (reload in memoria).

        Coalescing: se esiste già un pending, la nuova richiesta vi si fonde — i changed_paths
        sono l'unione dei due insiemi, e None (richiesta completa) assorbe tutto. Le callback
        del pending restano quelle della prima richiesta accodata."""
        with self._lock:
            if self._running_id is None:
                job = self._make_job(changed_paths, run_reindex, on_success, status="running")
                self._running_id = job.id
                self._dispatch(job)
                return job, False
            if self._pending is not None:
                # Fusione nel pending esistente: un solo pending massimo.
                self._pending.changed_paths = _coalesce_paths(
                    self._pending.changed_paths, changed_paths
                )
                return self._pending, True
            pending = self._make_job(changed_paths, run_reindex, on_success, status="queued")
            self._pending = pending
            return pending, True

    def _make_job(self, changed_paths, run_reindex, on_success, status: str) -> ReindexJob:
        job = ReindexJob(changed_paths, status=status)
        job._run_reindex = run_reindex
        job._on_success = on_success
        self._jobs[job.id] = job
        return job

    def _dispatch(self, job: ReindexJob) -> None:
        """Lancia il thread daemon per `job`. Da chiamare con lo slot già assegnato."""
        threading.Thread(
            target=self._run, args=(job,),
            name=f"reindex-{job.id[:8]}", daemon=True,
        ).start()

    def _run(self, job: ReindexJob) -> None:
        try:
            job.result = job._run_reindex(job.changed_paths)
            job.status = "completed"
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
        if job.status == "completed":
            try:
                job._on_success()
            except Exception as exc:
                # Il reload è best-effort: reload_index_state è già tollerante agli
                # artefatti incoerenti; qui logghiamo soltanto senza far fallire il job.
                print(f"⚠️  Reload post-reindex fallito ({type(exc).__name__}: {exc}).")

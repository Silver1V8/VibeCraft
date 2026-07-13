"""Gestione del reindex incrementale in background: un job alla volta, con job-id e stato
interrogabile, più l'estrazione dei path modificati da un payload webhook GitLab (push/merge).

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


class ReindexJob:
    """Stato di un singolo job di reindex. `status` ∈ {running, completed, failed}."""

    def __init__(self, changed_paths: list[str] | None):
        self.id: str = uuid.uuid4().hex
        self.status: str = "running"
        self.created_at: str = _now_iso()
        self.finished_at: str | None = None
        self.changed_paths: list[str] | None = changed_paths
        self.result: dict | None = None
        self.error: str | None = None

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
    """Serializza i reindex: al massimo uno in esecuzione. `start` rifiuta (None) se ce n'è
    già uno in corso — il router traduce None in HTTP 409. Il lavoro gira su un thread daemon;
    a fine job (solo se riuscito) invoca `on_success` per il reload in memoria degli artefatti."""

    def __init__(self):
        self._lock = threading.Lock()
        self._running_id: str | None = None
        self._jobs: dict[str, ReindexJob] = {}

    def get(self, job_id: str) -> ReindexJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running_id is not None

    def start(self, changed_paths, run_reindex, on_success) -> ReindexJob | None:
        """Avvia un reindex in background. Restituisce il job creato, oppure None se un
        reindex è già in corso (richiesta da rifiutare con 409).

        `run_reindex(emit, changed_paths) -> dict` esegue l'indicizzazione (bloccante);
        `on_success()` viene chiamato a fine job SOLO se riuscito (reload in memoria)."""
        with self._lock:
            if self._running_id is not None:
                return None
            job = ReindexJob(changed_paths)
            self._jobs[job.id] = job
            self._running_id = job.id
        threading.Thread(
            target=self._run, args=(job, run_reindex, on_success),
            name=f"reindex-{job.id[:8]}", daemon=True,
        ).start()
        return job

    def _run(self, job: ReindexJob, run_reindex, on_success) -> None:
        try:
            job.result = run_reindex(job.changed_paths)
            job.status = "completed"
        except Exception as exc:
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
        finally:
            job.finished_at = _now_iso()
            # Libera lo slot PRIMA del reload: anche se il reload fallisse, un nuovo
            # reindex deve poter partire.
            with self._lock:
                self._running_id = None
        if job.status == "completed":
            try:
                on_success()
            except Exception as exc:
                # Il reload è best-effort: reload_index_state è già tollerante agli
                # artefatti incoerenti; qui logghiamo soltanto senza far fallire il job.
                print(f"⚠️  Reload post-reindex fallito ({type(exc).__name__}: {exc}).")

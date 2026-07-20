"""Writer lock cross-processo per gli artefatti dell'indice (database/).

UN SOLO writer alla volta: la CLI (index.py: build, --incremental, --archive,
--rollback) e il server (ReindexManager) si escludono a vicenda tramite un lock
advisory a livello di SISTEMA OPERATIVO sul file `database/.writer.lock`
(msvcrt.locking su Windows, fcntl.flock su POSIX).

NON è un lock "a esistenza del file": il file esiste sempre, non viene mai
cancellato, e la sua presenza non significa nulla. Il mutex è il lock OS
sull'handle aperto, che il kernel rilascia AUTOMATICAMENTE alla morte del
processo (crash e kill inclusi): nessun lock stale da ripulire a mano.

Dentro il file il detentore scrive pid e timestamp a scopo puramente DIAGNOSTICO
(compaiono nel messaggio di WriterLockBusyError): la decisione di mutua
esclusione è SOLO del lock OS, mai del contenuto.

Su Windows il byte lockato sta a un offset alto, oltre i dati: msvcrt.locking è
mandatorio sulla regione lockata, e lockare il byte 0 renderebbe illeggibile la
diagnostica agli altri processi mentre il lock è tenuto."""
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from core.config import DATABASE_DIR

if os.name == "nt":
    import msvcrt
else:
    import fcntl

LOCK_FILENAME = ".writer.lock"

# Offset (solo Windows) del byte lockato: lontano dai primi byte del file, dove
# vive la diagnostica pid/timestamp, che così resta leggibile da altri processi.
_WIN_LOCK_OFFSET = 0x7FFF_0000

# Passo di polling tra i tentativi non-bloccanti di acquisizione.
_POLL_INTERVAL_SECONDS = 0.1


class WriterLockBusyError(RuntimeError):
    """Un altro processo detiene il writer lock (timeout di acquisizione scaduto)."""


def default_lock_path() -> Path:
    """Percorso canonico del file di lock: database/.writer.lock."""
    return DATABASE_DIR / LOCK_FILENAME


def _read_holder_info(path: Path) -> str:
    """Diagnostica (pid/timestamp) scritta dall'attuale detentore, best-effort."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return "detentore sconosciuto (file di lock non leggibile)"
    return text or "detentore sconosciuto (nessuna diagnostica nel file)"


def _try_lock(fd: int) -> bool:
    """Tentativo NON bloccante di lock OS esclusivo su `fd`. True se acquisito."""
    try:
        if os.name == "nt":
            os.lseek(fd, _WIN_LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fd: int) -> None:
    if os.name == "nt":
        os.lseek(fd, _WIN_LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def writer_lock(timeout_seconds: float = 5, lock_path: str | Path | None = None):
    """Acquisisce il writer lock esclusivo (o solleva WriterLockBusyError al timeout).

    L'acquisizione è un retry non-bloccante fino a `timeout_seconds`; al timeout il
    messaggio dell'eccezione riporta pid/timestamp letti dal file (diagnostica del
    detentore). `lock_path` è il seam per i test (default: database/.writer.lock);
    il file NON viene mai cancellato al rilascio — cancellarlo aprirebbe la race
    "due processi lockano inode diversi dello stesso path"."""
    path = Path(lock_path) if lock_path is not None else default_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT
    if os.name == "nt":
        flags |= os.O_BINARY
    fd = os.open(path, flags, 0o644)
    acquired = False
    try:
        deadline = time.monotonic() + timeout_seconds
        while True:
            if _try_lock(fd):
                acquired = True
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WriterLockBusyError(
                    f"writer lock occupato ({path}): {_read_holder_info(path)}"
                )
            time.sleep(min(_POLL_INTERVAL_SECONDS, remaining))
        # Diagnostica best-effort: mai bloccante, mai decisionale.
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, f"pid={os.getpid()} acquired_at={datetime.now(timezone.utc).isoformat()}\n"
                     .encode("utf-8"))
        except OSError:
            pass
        yield
    finally:
        if acquired:
            try:
                _unlock(fd)
            except OSError:
                pass
        os.close(fd)

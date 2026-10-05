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
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.projects import ProjectContext

import os
import re
import time
import weakref
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from core.config import DATABASE_DIR

if os.name == "nt":
    import msvcrt
    import ctypes
    from ctypes import wintypes
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


def _unlinked_lock_path(path: Path) -> None:
    # A captured project can outlive a directory replacement; validate before any I/O.
    for component in (path, *path.parents):
        if component.is_symlink() or component.is_junction():
            raise ValueError("Linked lock path forbidden")


class VersionLease:
    """OS lock on a persistent per-version file, outside the deletable version dir."""

    def __init__(self, fd: int):
        self._finalizer = weakref.finalize(self, _close_version_fd, fd)

    def close(self) -> None:
        self._finalizer()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


def try_version_lease(database_dir: str | Path, version: str, *, exclusive: bool = False) -> VersionLease | None:
    """Nonblocking shared reader or exclusive retention lease. Never unlink lock files."""
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z-]*", version):
        raise ValueError(f"invalid version name: {version!r}")
    base = Path(database_dir)
    locks = base / ".reader-locks"
    _unlinked_lock_path(locks)
    locks.mkdir(parents=True, exist_ok=True)
    path = locks / f"{version}.lock"
    _unlinked_lock_path(path)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    if os.name == "nt":
        flags |= os.O_BINARY
    fd = os.open(path, flags, 0o644)
    try:
        if os.name == "nt":
            if not _try_version_lock_windows(fd, exclusive):
                os.close(fd)
                return None
        else:
            try:
                fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                return None
        return VersionLease(fd)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


if os.name == "nt":
    class _OVERLAPPED(ctypes.Structure):
        _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                    ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                    ("hEvent", wintypes.HANDLE)]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _lock_file_ex = _kernel32.LockFileEx
    _lock_file_ex.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                              wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_OVERLAPPED)]
    _lock_file_ex.restype = wintypes.BOOL
    _unlock_file_ex = _kernel32.UnlockFileEx
    _unlock_file_ex.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                wintypes.DWORD, ctypes.POINTER(_OVERLAPPED)]
    _unlock_file_ex.restype = wintypes.BOOL

    def _version_overlap() -> _OVERLAPPED:
        overlap = _OVERLAPPED()
        overlap.Offset = _WIN_LOCK_OFFSET
        return overlap

    def _try_version_lock_windows(fd: int, exclusive: bool) -> bool:
        flags = 0x1 | (0x2 if exclusive else 0)  # FAIL_IMMEDIATELY, EXCLUSIVE_LOCK
        ok = _lock_file_ex(msvcrt.get_osfhandle(fd), flags, 0, 1, 0,
                           ctypes.byref(_version_overlap()))
        if ok:
            return True
        error = ctypes.get_last_error()
        if error == 33:  # ERROR_LOCK_VIOLATION
            return False
        raise ctypes.WinError(error)


def _unlock_version(fd: int) -> None:
    if os.name == "nt":
        ok = _unlock_file_ex(msvcrt.get_osfhandle(fd), 0, 1, 0,
                             ctypes.byref(_version_overlap()))
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _close_version_fd(fd: int) -> None:
    """Release once; weakref.finalize makes explicit close and GC idempotent."""
    try:
        _unlock_version(fd)
    finally:
        os.close(fd)


def default_lock_path(project: ProjectContext | None = None) -> Path:
    """Percorso canonico del file di lock: database/.writer.lock."""
    return (project.database_dir if project is not None else DATABASE_DIR) / LOCK_FILENAME


def _read_holder_info(path: Path) -> str:
    """Diagnostica (pid/timestamp) scritta dall'attuale detentore, best-effort."""
    _unlinked_lock_path(path)
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
def writer_lock(timeout_seconds: float = 5, lock_path: str | Path | None = None, project: ProjectContext | None = None):
    """Acquisisce il writer lock esclusivo (o solleva WriterLockBusyError al timeout).

    L'acquisizione è un retry non-bloccante fino a `timeout_seconds`; al timeout il
    messaggio dell'eccezione riporta pid/timestamp letti dal file (diagnostica del
    detentore). `lock_path` è il seam per i test (default: database/.writer.lock);
    il file NON viene mai cancellato al rilascio — cancellarlo aprirebbe la race
    "due processi lockano inode diversi dello stesso path"."""
    path = Path(lock_path) if lock_path is not None else default_lock_path(project=project)
    _unlinked_lock_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _unlinked_lock_path(path)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
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

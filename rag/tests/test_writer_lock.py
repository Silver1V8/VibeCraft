"""Test del writer lock cross-processo (core/writer_lock.py): mutua esclusione OS-level
(msvcrt/fcntl) su handle separati nello stesso processo e tra PROCESSI reali (subprocess),
rilascio automatico alla morte del processo (anche kill, senza cleanup), e integrazione
nel ReindexManager (job "failed" con l'errore del lock quando un altro writer lo tiene).

I lock usano sempre un file in tmp_path: il database/.writer.lock reale non viene toccato."""
import os
import subprocess
import sys
import threading
import time

import pytest

from core.config import RAG_DIR
from core.writer_lock import WriterLockBusyError, writer_lock


# ---------------------------------------------------------------------------
# Stesso processo, handle separati
# ---------------------------------------------------------------------------
def test_second_acquisition_on_separate_handle_fails_within_timeout(tmp_path):
    """Il lock è per-handle (non rientrante): la seconda acquisizione sullo stesso file
    da un handle diverso fallisce entro il timeout, con la diagnostica del detentore
    (pid di QUESTO processo) nel messaggio."""
    lock_file = tmp_path / ".writer.lock"
    with writer_lock(timeout_seconds=5, lock_path=lock_file):
        t0 = time.monotonic()
        with pytest.raises(WriterLockBusyError) as exc_info:
            with writer_lock(timeout_seconds=0.5, lock_path=lock_file):
                pass
        elapsed = time.monotonic() - t0
        assert elapsed < 3  # ha rispettato il timeout corto, non quello del detentore
        assert f"pid={os.getpid()}" in str(exc_info.value)


def test_release_on_exit_allows_reacquisition(tmp_path):
    """Uscito dal context manager, il lock è di nuovo libero (stesso processo)."""
    lock_file = tmp_path / ".writer.lock"
    with writer_lock(timeout_seconds=1, lock_path=lock_file):
        pass
    with writer_lock(timeout_seconds=1, lock_path=lock_file):
        pass  # nessuna eccezione: il primo rilascio è avvenuto


def test_release_happens_even_when_body_raises(tmp_path):
    lock_file = tmp_path / ".writer.lock"
    with pytest.raises(RuntimeError, match="boom"):
        with writer_lock(timeout_seconds=1, lock_path=lock_file):
            raise RuntimeError("boom")
    with writer_lock(timeout_seconds=1, lock_path=lock_file):
        pass  # il finally ha rilasciato nonostante l'eccezione


# ---------------------------------------------------------------------------
# Processi reali (subprocess)
# ---------------------------------------------------------------------------
# Il figlio acquisisce il lock, stampa "LOCKED <pid>" (sincronizzazione col padre; il
# pid stampato è quello VERO del detentore — su Windows il python.exe del venv è un
# launcher, quindi Popen.pid non coincide) e lo tiene per sys.argv[3] secondi.
# sys.path del padre non si eredita: rag/ va reinserita.
_HOLDER_CODE = """
import os, sys, time
sys.path.insert(0, sys.argv[1])
from core.writer_lock import writer_lock
with writer_lock(timeout_seconds=5, lock_path=sys.argv[2]):
    print(f"LOCKED {os.getpid()}", flush=True)
    time.sleep(float(sys.argv[3]))
"""


def _spawn_holder(lock_file, hold_seconds: float) -> tuple[subprocess.Popen, int]:
    """Avvia il processo detentore; restituisce (Popen, pid reale del detentore)."""
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER_CODE, str(RAG_DIR), str(lock_file), str(hold_seconds)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    line = proc.stdout.readline().strip()
    if not line.startswith("LOCKED "):
        proc.kill()
        raise AssertionError(f"il subprocess non ha acquisito il lock (output: {line!r}, "
                             f"stderr: {proc.stderr.read()!r})")
    return proc, int(line.split()[1])


def test_lock_held_by_real_process_raises_busy(tmp_path):
    """Con un SECONDO processo reale che detiene il lock, l'acquisizione qui fallisce
    con WriterLockBusyError e il messaggio riporta il pid del subprocess."""
    lock_file = tmp_path / ".writer.lock"
    proc, holder_pid = _spawn_holder(lock_file, hold_seconds=60)
    try:
        with pytest.raises(WriterLockBusyError) as exc_info:
            with writer_lock(timeout_seconds=0.5, lock_path=lock_file):
                pass
        assert f"pid={holder_pid}" in str(exc_info.value)
    finally:
        proc.kill()
        proc.wait(timeout=10)


def test_lock_released_when_holder_process_exits(tmp_path):
    """Il figlio tiene il lock ~1.5s e poi esce: un'acquisizione con timeout più largo
    deve prima attendere (retry) e poi riuscire — rilascio automatico a fine processo."""
    lock_file = tmp_path / ".writer.lock"
    proc, _holder_pid = _spawn_holder(lock_file, hold_seconds=1.5)
    try:
        t0 = time.monotonic()
        with writer_lock(timeout_seconds=15, lock_path=lock_file):
            elapsed = time.monotonic() - t0
        assert elapsed < 15  # riuscita ben prima del timeout, appena il figlio è uscito
    finally:
        proc.wait(timeout=10)


def test_lock_released_when_holder_process_is_killed(tmp_path):
    """kill duro del detentore (nessun finally eseguito nel figlio): il lock OS viene
    rilasciato dal kernel alla morte del processo — il punto per cui NON si usa un lock
    a esistenza del file, che qui resterebbe stale per sempre."""
    lock_file = tmp_path / ".writer.lock"
    proc, _holder_pid = _spawn_holder(lock_file, hold_seconds=60)
    proc.kill()
    proc.wait(timeout=10)
    with writer_lock(timeout_seconds=5, lock_path=lock_file):
        pass  # acquisizione riuscita: nessun lock stale sopravvissuto al kill


# ---------------------------------------------------------------------------
# Integrazione ReindexManager: lock attorno a job._run_reindex
# ---------------------------------------------------------------------------
def _wait(cond, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def _manager_on_tmp_lock(monkeypatch, lock_file, timeout_seconds=0.3):
    """ReindexManager il cui writer lock punta a `lock_file` (mai al database/ reale),
    con timeout corto: il monkeypatch è SOLO nei test, nessun flag di produzione."""
    import api.reindex as reindex_mod
    monkeypatch.setattr(reindex_mod, "_WRITER_LOCK_TIMEOUT_SECONDS", timeout_seconds)
    monkeypatch.setattr(reindex_mod, "writer_lock",
                        lambda timeout_seconds: writer_lock(timeout_seconds, lock_path=lock_file))
    return reindex_mod.ReindexManager()


def test_manager_job_fails_readably_when_lock_held_elsewhere(tmp_path, monkeypatch):
    """Lock tenuto da un altro handle: il job va in "failed" SENZA mai eseguire il
    run_reindex, con l'errore del lock (classe + diagnostica) leggibile sul job."""
    lock_file = tmp_path / ".writer.lock"
    mgr = _manager_on_tmp_lock(monkeypatch, lock_file)
    ran = threading.Event()

    with writer_lock(timeout_seconds=5, lock_path=lock_file):
        job, queued = mgr.start(["docs/a.md"], lambda paths: ran.set() or {}, lambda: None)
        assert queued is False
        assert _wait(lambda: mgr.get(job.id).status == "failed")

    failed = mgr.get(job.id)
    assert "WriterLockBusyError" in failed.error
    assert "writer lock occupato" in failed.error
    assert not ran.is_set()  # il reindex non è mai partito: fermato dal lock
    assert not mgr.is_running  # slot liberato come per ogni altro fallimento


def test_manager_holds_lock_during_job_and_releases_after(tmp_path, monkeypatch):
    """A lock libero il job completa; DURANTE il run il lock risulta occupato (il manager
    lo tiene attorno a run_reindex), e a job finito è di nuovo acquisibile."""
    lock_file = tmp_path / ".writer.lock"
    mgr = _manager_on_tmp_lock(monkeypatch, lock_file, timeout_seconds=5)
    held_during_run = {}

    def probing_reindex(paths):
        try:
            with writer_lock(timeout_seconds=0.05, lock_path=lock_file):
                held_during_run["busy"] = False
        except WriterLockBusyError:
            held_during_run["busy"] = True
        return {"ok": True}

    job, _ = mgr.start(["docs/a.md"], probing_reindex, lambda: None)
    assert _wait(lambda: mgr.get(job.id).status == "completed")
    assert held_during_run["busy"] is True  # il manager teneva il lock attorno al run
    with writer_lock(timeout_seconds=1, lock_path=lock_file):
        pass  # e lo ha rilasciato a fine job

"""Embedder dei job di reindex: bge-m3 su GPU in un processo separato (core.gpu_worker)
per la sola durata del job. A fine job il processo esce e restituisce alla GPU tutta la
VRAM che ha usato, contesto CUDA compreso, senza riavviare il server (la GPU è condivisa
con Ollama): il processo del server non crea mai un contesto CUDA. Se CUDA manca, la
VRAM libera è sotto soglia, il processo non parte o un encode esaurisce la memoria, il
resto del job usa il modello CPU condiviso del server. Espone encode() come
BGEM3FlagModel: indicizzazione, code-link ed eval-gate lo usano senza saperlo.

Costi e limiti. Avviare il processo e caricarvi il modello costa ~10 s per ogni job che
usa davvero la GPU (un job no-op non avvia nulla). La VRAM libera si legge con
nvidia-smi (torch.cuda.mem_get_info creerebbe un contesto CUDA nel server e, a VRAM
quasi piena, fallirebbe lui stesso); senza nvidia-smi il job usa la CPU."""
from __future__ import annotations

import logging
import os
import pickle
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import core
from core.config import REINDEX_DEVICE, REINDEX_GPU_MIN_FREE_MB

logger = logging.getLogger(__name__)

GPU_WORKER_READY_TIMEOUT_S = 300.0
GPU_WORKER_STOP_TIMEOUT_S = 30.0


class GpuWorkerUnavailable(Exception):
    """Il processo GPU non può (più) servire il job: il job prosegue sulla CPU. Il
    messaggio è il motivo riportato in embedding_fallback_reason."""


class GpuWorker:
    """Lato server del processo `python -m core.gpu_worker` (protocollo descritto lì).
    encode() solleva GpuWorkerUnavailable se il processo esaurisce la VRAM o muore, e
    RuntimeError con il traceback del figlio per ogni altro errore dell'embedding."""

    def __init__(self, process: subprocess.Popen):
        self.process = process

    def wait_ready(self, timeout: float) -> None:
        """Attende ("ready", ...) entro timeout; altrimenti uccide il processo e solleva
        GpuWorkerUnavailable. La lettura avviene in un thread perché la pipe non ha timeout."""
        box: list = []
        reader = threading.Thread(target=self._read_into, args=(box,), daemon=True)
        reader.start()
        reader.join(timeout)
        if reader.is_alive():
            self._terminate(grace=0)
            # Dopo l'uccisione la pipe dà EOF e il thread esce; le pipe si chiudono solo
            # dopo, perché chiudere uno stream mentre un altro thread lo legge si blocca.
            reader.join(5)
            if not reader.is_alive():
                self._close_pipes()
            raise GpuWorkerUnavailable(f"processo GPU non pronto entro {timeout:g} s")
        reply = box[0]
        if isinstance(reply, BaseException):
            code = self._kill()
            raise GpuWorkerUnavailable(
                f"processo GPU terminato prima di essere pronto (codice di uscita {code})")
        if reply[0] != "ready":
            self._kill()
            raise GpuWorkerUnavailable(f"caricamento del modello su GPU fallito: {reply[1]}")

    def _read_into(self, box: list) -> None:
        try:
            box.append(pickle.load(self.process.stdout))
        except Exception as exc:
            box.append(exc)

    def encode(self, texts, **kwargs):
        # Serializzata prima di scrivere: un errore di pickle non lascia mezzo messaggio
        # nella pipe, e si propaga come errore normale.
        request = pickle.dumps(("encode", texts, kwargs), protocol=pickle.HIGHEST_PROTOCOL)
        try:
            self.process.stdin.write(request)
            self.process.stdin.flush()
            reply = pickle.load(self.process.stdout)
        except (EOFError, OSError, pickle.UnpicklingError):
            code = self._kill()
            raise GpuWorkerUnavailable(
                f"processo GPU terminato durante l'embedding (codice di uscita {code})") from None
        if reply[0] == "ok":
            return reply[1]
        if reply[0] == "oom":
            raise GpuWorkerUnavailable(f"memoria GPU esaurita durante l'embedding: {reply[1]}")
        raise RuntimeError(f"embedding fallito nel processo GPU:\n{reply[1]}")

    def stop(self) -> None:
        """Chiede al processo di uscire; se non lo fa entro GPU_WORKER_STOP_TIMEOUT_S lo
        uccide. Idempotente."""
        if self.process.poll() is None:
            try:
                self.process.stdin.write(pickle.dumps(("stop",)))
                self.process.stdin.flush()
            except OSError:
                pass
        self._kill(grace=GPU_WORKER_STOP_TIMEOUT_S)

    def _kill(self, grace: float = 5.0) -> int:
        """Termina il processo (vedi _terminate), chiude le pipe e ritorna il codice di
        uscita."""
        self._terminate(grace)
        self._close_pipes()
        return self.process.returncode

    def _terminate(self, grace: float) -> None:
        """Attende l'uscita per `grace` secondi (così il codice di uscita è quello vero),
        poi uccide il processo. Con un venv su Windows il processo avviato è il launcher
        di Scripts/python.exe: uccidendolo muore anche l'interprete figlio."""
        try:
            self.process.wait(grace)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

    def _close_pipes(self) -> None:
        for stream in (self.process.stdin, self.process.stdout):
            try:
                stream.close()
            except OSError:
                pass


def start_gpu_worker(*, loader: str | None = None,
                     ready_timeout: float = GPU_WORKER_READY_TIMEOUT_S) -> GpuWorker:
    """Avvia `python -m core.gpu_worker` con l'interprete del server, nella cartella che
    contiene il package core (lo stesso codice del server), e attende che il modello sia
    caricato. stderr è ereditato: i log del figlio finiscono nel log del server."""
    command = [sys.executable, "-m", "core.gpu_worker"]
    if loader:
        command += ["--loader", loader]
    process = subprocess.Popen(
        command, cwd=Path(core.__file__).resolve().parent.parent, env=dict(os.environ),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    worker = GpuWorker(process)
    worker.wait_ready(ready_timeout)
    return worker


class JobEmbedder:
    """Sceglie il device al primo encode (un job no-op non avvia nulla) e lo mantiene per
    il job; dopo un ripiego su CPU non torna mai alla GPU nello stesso job.

    embedding_load_seconds misura il tempo dall'avvio del processo GPU al suo "ready"
    (interprete, import e caricamento del modello). Una VRAM insufficiente emerge come
    OOM durante l'embedding e porta allo stesso ripiego su CPU, come la morte del
    processo; ogni altro errore dell'embedding si propaga e fa fallire il job."""

    def __init__(self, *, start_worker, cpu_model, gpu_available, free_vram_mb,
                 min_free_mb: int, enabled: bool):
        self._start_worker = start_worker
        self._cpu_model = cpu_model
        self._gpu_available = gpu_available
        self._free_vram_mb = free_vram_mb
        self._min_free_mb = min_free_mb
        self._enabled = enabled
        self._worker = None
        self.device: str | None = None
        self.fallback_reason: str | None = None
        self.load_seconds = 0.0

    def encode(self, texts, **kwargs):
        if self.device is None:
            self._choose_device()
        if self.device == "cuda":
            try:
                return self._worker.encode(texts, **kwargs)
            except GpuWorkerUnavailable as exc:
                reason = str(exc)
            self._fall_back(reason)
        return self._cpu_model().encode(texts, **kwargs)

    def _choose_device(self) -> None:
        if not self._enabled:
            self._fall_back("VIBECRAFT_REINDEX_DEVICE=cpu")
            return
        if not self._gpu_available():
            self._fall_back("CUDA non disponibile")
            return
        free = None
        try:
            free = self._free_vram_mb()
        except Exception as exc:
            unavailable = f"VRAM non interrogabile: {exc}"
        if free is None:
            self._fall_back(unavailable)
            return
        if free < self._min_free_mb:
            self._fall_back(f"VRAM libera {free} MB sotto la soglia di {self._min_free_mb} MB")
            return
        started = time.perf_counter()
        failure = None
        try:
            self._worker = self._start_worker()
        except GpuWorkerUnavailable as exc:
            failure = str(exc)
        except Exception as exc:
            failure = f"avvio del processo GPU fallito: {exc}"
        finally:
            self.load_seconds = time.perf_counter() - started
        if failure is not None:
            self._fall_back(failure)
            return
        self.device = "cuda"
        logger.info("Embedding del job di reindex su GPU in un processo separato "
                    "(VRAM libera all'avvio: %s MB, pronto in %.1f s).", free, self.load_seconds)

    def _fall_back(self, reason: str) -> None:
        self.release()
        self.device = "cpu"
        self.fallback_reason = reason
        logger.warning("Embedding del job di reindex su CPU: %s", reason)

    def release(self) -> None:
        """Ferma il processo GPU, se avviato: uscendo restituisce tutta la sua VRAM.
        Idempotente; un job che non lo ha avviato non fa nulla."""
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.stop()

    def report(self) -> dict:
        return {"embedding_device": self.device or "unused",
                "embedding_fallback_reason": self.fallback_reason,
                "embedding_load_seconds": self.load_seconds}


def _cuda_available() -> bool:
    """torch.cuda.is_available() non crea un contesto CUDA nel processo del server."""
    import torch
    return torch.cuda.is_available()


def _free_vram_mb() -> int:
    """VRAM libera (MiB) della GPU 0 via nvidia-smi, che non crea un contesto CUDA nel
    server e vede anche la memoria degli altri processi (Ollama). Qualsiasi errore
    (nvidia-smi assente, uscita non zero, timeout, output illeggibile) è sollevato:
    il chiamante ripiega sulla CPU."""
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=5, check=False)
    if out.returncode != 0:
        raise RuntimeError(f"nvidia-smi uscito con codice {out.returncode}")
    lines = out.stdout.strip().splitlines()
    if not lines:
        raise RuntimeError("nvidia-smi non ha prodotto output")
    return int(lines[0].strip())


_start_gpu_worker = start_gpu_worker


@contextmanager
def reindex_embedder(cpu_model):
    """Embedder di un singolo job: il processo GPU viene fermato all'uscita, anche su
    errore, e con lui torna libera la sua VRAM."""
    embedder = JobEmbedder(start_worker=_start_gpu_worker, cpu_model=cpu_model,
                           gpu_available=_cuda_available, free_vram_mb=_free_vram_mb,
                           min_free_mb=REINDEX_GPU_MIN_FREE_MB,
                           enabled=REINDEX_DEVICE == "auto")
    try:
        yield embedder
    finally:
        embedder.release()

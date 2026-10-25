"""Embedder dei job di reindex: bge-m3 su CUDA, Metal o NPU, in un processo separato
(core.gpu_worker) per la sola durata del job. A fine job il processo esce e
restituisce la memoria che ha usato, senza riavviare il server. Il processo del
server non crea un contesto CUDA o Metal, e non compila un modello sulla NPU.

`auto` prova prima CUDA — NVIDIA, oppure AMD se PyTorch è la build ROCm — poi
Metal, poi una GPU OpenVINO, poi la NPU. Le teste sparse e ColBERT restano sulla
CPU del figlio quando l'encoder non è un device PyTorch. Se la GPU regge i pesi
dell'embedding e dell'LLM, il reindex ci mette l'intero modello; se no, il lavoro
si divide. `/ask` resta sulla CPU del server.

Costi e limiti. Avviare il processo e caricarvi il modello costa ~10 s per ogni
job che usa davvero l'acceleratore (un job no-op non avvia nulla); la prima
compilazione NPU costa di più e resta in cache. La memoria NVIDIA si legge con
nvidia-smi; quella Apple con sysctl e vm_stat. Nessuna delle due sonde crea un
contesto nel server."""
from __future__ import annotations

import atexit
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
GPU_WORKER_LOG_PREFIX = "[gpu-worker] "

# Processi GPU vivi. I thread dei job sono daemon: se il server esce a metà job
# release() non gira, e un figlio bloccato dentro CUDA terrebbe la sua VRAM finché
# qualcuno non lo uccide a mano (il launcher del venv non lo porta con sé).
_live_workers: set[GpuWorker] = set()
_live_workers_lock = threading.Lock()


class GpuWorkerUnavailable(Exception):
    """Il processo GPU non può (più) servire il job: il job prosegue sulla CPU. Il
    messaggio è il motivo riportato in embedding_fallback_reason."""


class GpuWorker:
    """Lato server del processo `python -m core.gpu_worker` (protocollo descritto lì).
    encode() solleva GpuWorkerUnavailable se il processo esaurisce la VRAM o muore, e
    RuntimeError con il traceback del figlio per ogni altro errore dell'embedding."""

    def __init__(self, process: subprocess.Popen):
        self.process = process
        with _live_workers_lock:
            _live_workers.add(self)
        self._stderr_reader = None
        if process.stderr is not None:
            self._stderr_reader = threading.Thread(
                target=_forward_stderr, args=(process.stderr,), daemon=True,
                name="gpu-worker-stderr")
            self._stderr_reader.start()

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
            self._close_pipes(stdout_busy=reader.is_alive())
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

    def _close_pipes(self, *, stdout_busy: bool = False) -> None:
        """Da chiamare dopo _terminate: attende il thread che inoltra lo stderr (finisce
        quando il processo esce), poi chiude le pipe. Uno stream ancora letto da un altro
        thread resta aperto: chiuderlo si bloccherebbe."""
        with _live_workers_lock:
            _live_workers.discard(self)
        streams = [self.process.stdin]
        if not stdout_busy:
            streams.append(self.process.stdout)
        if self._stderr_reader is not None:
            self._stderr_reader.join(5)
            if not self._stderr_reader.is_alive():
                streams.append(self.process.stderr)
        for stream in streams:
            try:
                stream.close()
            except OSError:
                pass


def _forward_stderr(stream) -> None:
    """Inoltra lo stderr del figlio al log del server, riga per riga. Di una barra tqdm,
    che si riscrive con un ritorno carrello, resta lo stato finale."""
    for raw in iter(stream.readline, b""):
        line = raw.decode("utf-8", errors="replace").rstrip().rsplit("\r", 1)[-1].strip()
        if line:
            logger.info("%s%s", GPU_WORKER_LOG_PREFIX, line)


def _kill_live_workers() -> None:
    """Uccide i processi GPU ancora vivi; registrata con atexit."""
    with _live_workers_lock:
        workers = list(_live_workers)
    for worker in workers:
        try:
            worker._kill(grace=0)
        except Exception:
            logger.debug("Uccisione del processo GPU all'uscita fallita", exc_info=True)


atexit.register(_kill_live_workers)


def start_gpu_worker(*, loader: str | None = None, device: str = "cuda:0",
                     ready_timeout: float = GPU_WORKER_READY_TIMEOUT_S) -> GpuWorker:
    """Avvia `python -m core.gpu_worker` con l'interprete del server, nella cartella che
    contiene il package core (lo stesso codice del server), e attende che il modello sia
    caricato. Lo stderr del figlio è una pipe inoltrata al log del server (prefisso
    GPU_WORKER_LOG_PREFIX): ereditarlo non va, perché lo stderr di un server avviato da
    terminale Windows è un handle di console, inutilizzabile da un figlio senza console
    (CREATE_NO_WINDOW): ogni scrittura, compresa la barra tqdm di FlagEmbedding,
    fallirebbe con Errno 9; lo stesso con pythonw o un servizio."""
    command = [sys.executable, "-m", "core.gpu_worker", "--device", device]
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")  # lo stderr inoltrato si decodifica in UTF-8
    if device == "mps":
        # Alcune op di bge-m3 non hanno un kernel Metal: senza questo il figlio
        # muore invece di calcolare quel pezzo sulla CPU.
        env.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    if loader:
        command += ["--loader", loader]
    process = subprocess.Popen(
        command, cwd=Path(core.__file__).resolve().parent.parent, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    worker = GpuWorker(process)
    try:
        worker.wait_ready(ready_timeout)
    except GpuWorkerUnavailable:
        raise  # wait_ready ha già fermato il processo
    except BaseException:
        worker._kill(grace=0)
        raise
    return worker


class JobEmbedder:
    """Sceglie il device al primo encode (un job no-op non avvia nulla) e lo mantiene per
    il job; dopo un ripiego su CPU non torna mai alla GPU nello stesso job.

    embedding_load_seconds misura il tempo dall'avvio del processo GPU al suo "ready"
    (interprete, import e caricamento del modello). Una VRAM insufficiente emerge come
    OOM durante l'embedding e porta allo stesso ripiego su CPU, come la morte del
    processo; ogni altro errore dell'embedding si propaga e fa fallire il job."""

    def __init__(self, *, start_worker, cpu_model, gpu_available, free_vram_mb,
                 min_free_mb: int, enabled: bool, preference: str = "auto",
                 mps_available=lambda: False, apple_memory_mb=None, nvidia_gpus=None,
                 npu_label=lambda: None, npu_runtime=None, amd_gpus=None, intel_gpu=None):
        self._start_worker = start_worker
        self._cpu_model = cpu_model
        self._gpu_available = gpu_available
        self._free_vram_mb = free_vram_mb
        self._min_free_mb = min_free_mb
        self._enabled = enabled
        self._preference = preference
        self._mps_available = mps_available
        self._apple_memory_mb = apple_memory_mb
        self._nvidia_gpus = nvidia_gpus
        self._npu_label = npu_label
        self._npu_runtime = npu_runtime
        self._amd_gpus = amd_gpus
        self._intel_gpu = intel_gpu
        self._worker = None
        self.device: str | None = None
        self.fallback_reason: str | None = None
        self.accelerator: str | None = None
        self.npu: str | None = None
        self.placement: str | None = None
        self.placement_reason: str | None = None
        self.load_seconds = 0.0

    def encode(self, texts, **kwargs):
        if self.device is None:
            self._choose_device()
        if self.device in {"cuda", "mps", "npu", "intel"}:
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
        decision = self._decision()
        if decision.device == "cpu":
            self.npu = decision.npu
            self._fall_back(decision.reason or "nessun acceleratore")
            return
        started = time.perf_counter()
        failure = None
        try:
            self._worker = self._start_worker(decision.torch_device)
        except GpuWorkerUnavailable as exc:
            failure = str(exc)
        except Exception as exc:
            failure = f"avvio del processo GPU fallito: {exc}"
        finally:
            self.load_seconds = time.perf_counter() - started
        if failure is not None:
            self.npu = decision.npu
            self._fall_back(failure)
            return
        self.device = decision.device
        self.accelerator = decision.accelerator
        self.npu = decision.npu
        self.placement = decision.placement
        self.placement_reason = decision.placement_reason
        logger.info("Embedding del job di reindex su %s in un processo separato "
                    "(memoria libera all'avvio: %s MB, pronto in %.1f s).",
                    decision.torch_device, decision.memory_mb, self.load_seconds)

    def _decision(self):
        from core.accelerator import GpuMemory, decide
        cuda = self._gpu_available()
        gpus = None
        gpu_error = None
        if self._nvidia_gpus is not None and cuda and self._preference in {"auto", "cuda"}:
            try:
                gpus = self._nvidia_gpus()
            except Exception as exc:
                gpu_error = exc
        if not gpus and self._amd_gpus is not None and cuda and self._preference in {"auto", "cuda"}:
            try:
                gpus = self._amd_gpus()
                gpu_error = None
            except Exception as exc:
                if gpu_error is None:
                    gpu_error = exc
        elif gpus is None and self._nvidia_gpus is None and self._amd_gpus is None \
                and cuda and self._preference in {"auto", "cuda"}:
            try:
                free = self._free_vram_mb()
                gpus = [GpuMemory(0, "GPU", free, free)]
            except Exception as exc:
                gpu_error = exc
        apple_mb = None
        apple_error = None
        mps_present = self._mps_available()
        mps = mps_present and self._preference in {"auto", "mps"}
        if mps and self._apple_memory_mb is not None:
            try:
                apple_mb = self._apple_memory_mb()
            except Exception as exc:
                apple_error = exc
        elif mps:
            apple_error = RuntimeError("sonda della memoria Apple assente")
        try:
            npu = self._npu_label()
        except Exception:
            npu = None
        npu_ready, npu_name, npu_reason = False, None, None
        intel_name, intel_reason = None, None
        cuda_wins = False
        if cuda and gpus and self._preference == "auto":
            from core.accelerator import _pick_gpu
            cuda_wins = _pick_gpu(gpus, self._min_free_mb) is not None
        mps_wins = (self._preference == "auto" and mps and apple_error is None
                    and apple_mb is not None and apple_mb >= self._min_free_mb)
        secondary = self._preference in {"auto", "npu", "intel"} and not (cuda_wins or mps_wins)
        if self._npu_runtime is not None and secondary and self._preference in {"auto", "npu"}:
            try:
                probe = self._npu_runtime()
                npu_ready, npu_name, npu_reason = probe.ready, probe.name, probe.reason
            except Exception as exc:
                npu_reason = str(exc)
        if self._intel_gpu is not None and secondary and self._preference in {"auto", "intel"}:
            try:
                intel_name = self._intel_gpu()
            except Exception as exc:
                intel_reason = str(exc)
        return decide(self._preference, cuda=cuda, gpus=gpus, gpu_error=gpu_error,
                      mps=mps_present, apple_mb=apple_mb, apple_error=apple_error, npu=npu,
                      min_free_mb=self._min_free_mb, npu_ready=npu_ready, npu_name=npu_name,
                      npu_reason=npu_reason, intel_ready=bool(intel_name),
                      intel_name=intel_name, intel_reason=intel_reason)

    def _fall_back(self, reason: str) -> None:
        self.release()
        self.device = "cpu"
        self.placement = "cpu"
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
                "embedding_load_seconds": self.load_seconds,
                "embedding_accelerator": self.accelerator,
                "embedding_npu": self.npu,
                "embedding_placement": self.placement,
                "embedding_placement_reason": self.placement_reason}


def _cuda_available() -> bool:
    """torch.cuda.is_available() non crea un contesto CUDA nel processo del server."""
    import torch
    return torch.cuda.is_available()


def _free_vram_mb() -> int:
    """MiB liberi della GPU più libera. Tenuta per i chiamanti che vogliono un solo
    numero; la scelta vera usa query_nvidia_gpus."""
    from core.accelerator import query_nvidia_gpus
    gpus = query_nvidia_gpus()
    return max(gpus, key=lambda gpu: gpu.free_mb).free_mb


_start_gpu_worker = start_gpu_worker


@contextmanager
def reindex_embedder(cpu_model):
    """Embedder di un singolo job: il processo accelerato viene fermato all'uscita,
    anche su errore, e con lui torna libera la memoria che aveva preso."""
    from core.accelerator import detect_npu, query_amd_gpus, query_apple_reclaimable_mb, query_nvidia_gpus

    def start(device):
        return _start_gpu_worker(device=device)

    embedder = JobEmbedder(
        start_worker=start, cpu_model=cpu_model,
        gpu_available=_cuda_available, free_vram_mb=_free_vram_mb,
        min_free_mb=REINDEX_GPU_MIN_FREE_MB,
        enabled=REINDEX_DEVICE != "cpu",
        preference="auto" if REINDEX_DEVICE == "cpu" else REINDEX_DEVICE,
        mps_available=_mps_available, apple_memory_mb=query_apple_reclaimable_mb,
        nvidia_gpus=query_nvidia_gpus, amd_gpus=query_amd_gpus, npu_label=detect_npu,
        npu_runtime=_query_npu_runtime, intel_gpu=_query_intel_gpu)
    try:
        yield embedder
    finally:
        embedder.release()


def _query_intel_gpu():
    from core.npu_runtime import query_openvino_gpu
    return query_openvino_gpu()


def _query_npu_runtime():
    """Non compila il modello: guarda solo se un runtime NPU è installato."""
    from core.npu_runtime import query_npu_runtime
    return query_npu_runtime()


def _mps_available() -> bool:
    """Non alloca tensori Metal nel processo del server."""
    import torch
    backend = getattr(torch.backends, "mps", None)
    return backend is not None and backend.is_available()

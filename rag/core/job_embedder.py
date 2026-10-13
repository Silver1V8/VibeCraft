"""Embedder dei job di reindex: bge-m3 su GPU per la sola durata del job, poi la VRAM
torna libera (la GPU è condivisa con Ollama). Se CUDA manca, la VRAM libera è sotto
soglia o un encode la esaurisce, il resto del job usa il modello CPU condiviso del
server. Espone encode() come BGEM3FlagModel: indicizzazione, code-link ed eval-gate
lo usano senza saperlo. torch/FlagEmbedding sono importati solo quando servono.

Limiti noti. La VRAM libera si legge con nvidia-smi (torch.cuda.mem_get_info creerebbe
un contesto CUDA nel server e, a VRAM quasi piena, fallirebbe lui stesso); senza
nvidia-smi il job usa la CPU. A fine di un job che ha davvero usato la GPU si liberano
modello e cache dell'allocatore, ma il contesto CUDA del processo (driver, cuBLAS,
kernel: qualche centinaio di MiB) resta residente fino al riavvio del server."""
from __future__ import annotations

import gc
import logging
import subprocess
import time
from contextlib import contextmanager

from core.config import EMBEDDING_MODEL, REINDEX_DEVICE, REINDEX_GPU_MIN_FREE_MB

logger = logging.getLogger(__name__)


def _is_oom(exc: BaseException) -> bool:
    import torch
    return isinstance(exc, torch.OutOfMemoryError) or "out of memory" in str(exc).lower()


class JobEmbedder:
    """Sceglie il device al primo encode (un job no-op non carica nulla) e lo mantiene
    per il job; dopo un ripiego su CPU non torna mai alla GPU nello stesso job.

    BGEM3FlagModel(...) carica i pesi nella RAM dell'host e li sposta sulla GPU solo al
    primo encode: embedding_load_seconds misura quindi il caricamento su host, e una
    VRAM insufficiente per lo spostamento emerge come OOM durante l'embedding, gestito
    dallo stesso ripiego su CPU. oom_count legge il contatore di OOM di CUDA: un OOM
    reale di FlagEmbedding può uscire come altra eccezione (AttributeError dopo aver
    ridotto il batch a zero), che si riconosce dal contatore cresciuto."""

    def __init__(self, *, load_gpu, cpu_model, gpu_available, free_vram_mb,
                 min_free_mb: int, enabled: bool, empty_cache, oom_count=lambda: 0):
        self._load_gpu = load_gpu
        self._cpu_model = cpu_model
        self._gpu_available = gpu_available
        self._free_vram_mb = free_vram_mb
        self._min_free_mb = min_free_mb
        self._enabled = enabled
        self._empty_cache = empty_cache
        self._oom_count = oom_count
        self._gpu = None
        self._cuda_touched = False
        self.device: str | None = None
        self.fallback_reason: str | None = None
        self.load_seconds = 0.0

    def encode(self, texts, **kwargs):
        if self.device is None:
            self._choose_device()
        if self.device == "cuda":
            ooms_before = self._oom_count()
            try:
                return self._gpu.encode(texts, **kwargs)
            except Exception as exc:
                if not (_is_oom(exc) or self._oom_count() > ooms_before):
                    raise
                reason = f"memoria GPU esaurita durante l'embedding: {exc}"
            # Fuori dal blocco except: l'eccezione e il suo traceback (che tengono vivi
            # tensori e modello) sono già rilasciati quando si svuota la cache CUDA.
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
            self._fall_back(unavailable)  # fuori dall'except: vedi encode()
            return
        if free < self._min_free_mb:
            self._fall_back(f"VRAM libera {free} MB sotto la soglia di {self._min_free_mb} MB")
            return
        started = time.perf_counter()
        self._cuda_touched = True
        failure = None
        try:
            self._gpu = self._load_gpu()
        except Exception as exc:
            failure = f"caricamento del modello su GPU fallito: {exc}"
        finally:
            self.load_seconds = time.perf_counter() - started
        if failure is not None:
            self._fall_back(failure)  # fuori dall'except: vedi encode()
            return
        self.device = "cuda"
        logger.info("Embedding del job di reindex su GPU (VRAM libera all'avvio: %s MB).", free)

    def _fall_back(self, reason: str) -> None:
        self.release()
        self.device = "cpu"
        self.fallback_reason = reason
        logger.warning("Embedding del job di reindex su CPU: %s", reason)

    def release(self) -> None:
        """Libera il modello GPU e, se CUDA è stata toccata, la cache CUDA; idempotente.
        La cache si svuota anche senza modello GPU attivo (dopo un ripiego), perché un
        encode fallito può aver lasciato memoria riservata. Un job senza CUDA non la tocca."""
        if self._gpu is not None:
            try:
                self._gpu.stop_self_pool()
            except Exception:
                logger.debug("stop_self_pool fallito durante il rilascio", exc_info=True)
            self._gpu = None
        if not self._cuda_touched:
            return
        gc.collect()
        self._empty_cache()

    def report(self) -> dict:
        return {"embedding_device": self.device or "unused",
                "embedding_fallback_reason": self.fallback_reason,
                "embedding_load_seconds": self.load_seconds}


def _load_gpu_model():
    from FlagEmbedding import BGEM3FlagModel
    return BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False, devices="cuda:0")


def _cuda_available() -> bool:
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


def _cuda_oom_count() -> int:
    """Numero di OOM CUDA visti dall'allocatore; 0 se le statistiche non sono leggibili."""
    try:
        import torch
        return int(torch.cuda.memory_stats().get("num_ooms", 0))
    except Exception:
        return 0


def _empty_cuda_cache() -> None:
    import torch
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


@contextmanager
def reindex_embedder(cpu_model):
    """Embedder di un singolo job: la VRAM viene liberata all'uscita, anche su errore."""
    embedder = JobEmbedder(load_gpu=_load_gpu_model, cpu_model=cpu_model,
                           gpu_available=_cuda_available, free_vram_mb=_free_vram_mb,
                           min_free_mb=REINDEX_GPU_MIN_FREE_MB, enabled=REINDEX_DEVICE == "auto",
                           empty_cache=_empty_cuda_cache, oom_count=_cuda_oom_count)
    try:
        yield embedder
    finally:
        embedder.release()

"""Embedder dei job di reindex: bge-m3 su GPU per la sola durata del job, poi la VRAM
torna libera (la GPU è condivisa con Ollama). Se CUDA manca, la VRAM libera è sotto
soglia o un encode la esaurisce, il resto del job usa il modello CPU condiviso del
server. Espone encode() come BGEM3FlagModel: indicizzazione, code-link ed eval-gate
lo usano senza saperlo. torch/FlagEmbedding sono importati solo quando servono."""
from __future__ import annotations

import gc
import logging
import time
from contextlib import contextmanager

from core.config import EMBEDDING_MODEL, REINDEX_DEVICE, REINDEX_GPU_MIN_FREE_MB

logger = logging.getLogger(__name__)


def _is_oom(exc: BaseException) -> bool:
    import torch
    return isinstance(exc, torch.OutOfMemoryError) or "out of memory" in str(exc).lower()


class JobEmbedder:
    """Sceglie il device al primo encode (un job no-op non carica nulla) e lo mantiene
    per il job; dopo un ripiego su CPU non torna mai alla GPU nello stesso job."""

    def __init__(self, *, load_gpu, cpu_model, gpu_available, free_vram_mb,
                 min_free_mb: int, enabled: bool, empty_cache):
        self._load_gpu = load_gpu
        self._cpu_model = cpu_model
        self._gpu_available = gpu_available
        self._free_vram_mb = free_vram_mb
        self._min_free_mb = min_free_mb
        self._enabled = enabled
        self._empty_cache = empty_cache
        self._gpu = None
        self.device: str | None = None
        self.fallback_reason: str | None = None
        self.load_seconds = 0.0

    def encode(self, texts, **kwargs):
        if self.device is None:
            self._choose_device()
        if self.device == "cuda":
            try:
                return self._gpu.encode(texts, **kwargs)
            except Exception as exc:
                if not _is_oom(exc):
                    raise
                self._fall_back(f"memoria GPU esaurita durante l'embedding: {exc}")
        return self._cpu_model().encode(texts, **kwargs)

    def _choose_device(self) -> None:
        if not self._enabled:
            self._fall_back("VIBECRAFT_REINDEX_DEVICE=cpu")
            return
        if not self._gpu_available():
            self._fall_back("CUDA non disponibile")
            return
        free = self._free_vram_mb()
        if free < self._min_free_mb:
            self._fall_back(f"VRAM libera {free} MB sotto la soglia di {self._min_free_mb} MB")
            return
        started = time.perf_counter()
        try:
            self._gpu = self._load_gpu()
        except Exception as exc:
            self._fall_back(f"caricamento del modello su GPU fallito: {exc}")
            return
        finally:
            self.load_seconds = time.perf_counter() - started
        self.device = "cuda"
        logger.info("Embedding del job di reindex su GPU (VRAM libera all'avvio: %s MB).", free)

    def _fall_back(self, reason: str) -> None:
        self.release()
        self.device = "cpu"
        self.fallback_reason = reason
        logger.warning("Embedding del job di reindex su CPU: %s", reason)

    def release(self) -> None:
        """Libera il modello GPU e la cache CUDA; idempotente."""
        if self._gpu is None:
            return
        try:
            self._gpu.stop_self_pool()
        except Exception:
            logger.debug("stop_self_pool fallito durante il rilascio", exc_info=True)
        self._gpu = None
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
    import torch
    return torch.cuda.mem_get_info()[0] // 2**20


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
                           empty_cache=_empty_cuda_cache)
    try:
        yield embedder
    finally:
        embedder.release()

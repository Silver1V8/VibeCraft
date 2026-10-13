"""JobEmbedder: GPU solo per la durata del job di reindex, CPU come ripiego."""
import os

import pytest
import torch

from core import job_embedder
from core.job_embedder import JobEmbedder


class FakeModel:
    def __init__(self, name, fail=None):
        self.name, self.fail, self.calls, self.stopped = name, fail, [], False

    def encode(self, texts, **kwargs):
        self.calls.append(list(texts))
        if self.fail is not None:
            raise self.fail
        return {"dense_vecs": [self.name] * len(texts)}

    def stop_self_pool(self):
        self.stopped = True


def make(*, gpu=None, available=True, free=8000, enabled=True, load_error=None):
    gpu, cpu = gpu or FakeModel("gpu"), FakeModel("cpu")
    loads, cleared = [], []

    def load_gpu():
        loads.append(True)
        if load_error is not None:
            raise load_error
        return gpu

    embedder = JobEmbedder(load_gpu=load_gpu, cpu_model=lambda: cpu,
                           gpu_available=lambda: available, free_vram_mb=lambda: free,
                           min_free_mb=3072, enabled=enabled,
                           empty_cache=lambda: cleared.append(True))
    return embedder, gpu, cpu, loads, cleared


def test_noop_job_never_loads_anything():
    embedder, _, _, loads, _ = make()
    embedder.release()
    assert loads == []
    assert embedder.report()["embedding_device"] == "unused"


def test_uses_gpu_then_releases_it():
    embedder, gpu, cpu, loads, cleared = make()
    assert embedder.encode(["a"])["dense_vecs"] == ["gpu"]
    assert embedder.encode(["b"])["dense_vecs"] == ["gpu"]
    assert loads == [True] and cpu.calls == []
    embedder.release()
    assert gpu.stopped and cleared
    report = embedder.report()
    assert report["embedding_device"] == "cuda" and report["embedding_fallback_reason"] is None
    assert report["embedding_load_seconds"] >= 0


def test_low_free_vram_goes_cpu_without_loading():
    embedder, _, cpu, loads, _ = make(free=1000)
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert loads == []
    assert "VRAM" in embedder.report()["embedding_fallback_reason"]


def test_cuda_unavailable_goes_cpu():
    embedder, _, _, loads, _ = make(available=False)
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert loads == [] and embedder.report()["embedding_device"] == "cpu"


def test_disabled_goes_cpu():
    embedder, _, _, loads, _ = make(enabled=False)
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert loads == []
    assert "VIBECRAFT_REINDEX_DEVICE" in embedder.report()["embedding_fallback_reason"]


def test_gpu_load_failure_falls_back_to_cpu():
    embedder, _, _, _, _ = make(load_error=RuntimeError("CUDA driver mismatch"))
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert "caricamento" in embedder.report()["embedding_fallback_reason"]


def test_oom_retries_same_call_on_cpu_and_stays_there():
    gpu = FakeModel("gpu", fail=torch.OutOfMemoryError("CUDA out of memory"))
    embedder, _, cpu, _, cleared = make(gpu=gpu)
    assert embedder.encode(["a", "b"])["dense_vecs"] == ["cpu", "cpu"]
    assert cpu.calls == [["a", "b"]]
    assert gpu.stopped and cleared  # VRAM liberata subito, non a fine job
    embedder.encode(["c"])
    assert len(gpu.calls) == 1 and cpu.calls[-1] == ["c"]
    report = embedder.report()
    assert report["embedding_device"] == "cpu" and "memoria" in report["embedding_fallback_reason"]


def test_non_oom_gpu_error_propagates():
    embedder, _, cpu, _, _ = make(gpu=FakeModel("gpu", fail=ValueError("input malformato")))
    with pytest.raises(ValueError, match="malformato"):
        embedder.encode(["a"])
    assert cpu.calls == []


def test_context_releases_gpu_even_when_job_fails(monkeypatch):
    gpu = FakeModel("gpu")
    monkeypatch.setattr(job_embedder, "REINDEX_DEVICE", "auto")
    monkeypatch.setattr(job_embedder, "_load_gpu_model", lambda: gpu)
    monkeypatch.setattr(job_embedder, "_cuda_available", lambda: True)
    monkeypatch.setattr(job_embedder, "_free_vram_mb", lambda: 8000)
    monkeypatch.setattr(job_embedder, "_empty_cuda_cache", lambda: None)
    with pytest.raises(RuntimeError, match="job fallito"):
        with job_embedder.reindex_embedder(lambda: FakeModel("cpu")) as embedder:
            embedder.encode(["x"])
            raise RuntimeError("job fallito")
    assert gpu.stopped


@pytest.mark.skipif(os.environ.get("VIBECRAFT_TEST_GPU") != "1",
                    reason="opt-in: VIBECRAFT_TEST_GPU=1 su una macchina con CUDA")
def test_real_gpu_model_is_released(monkeypatch):
    monkeypatch.setattr(job_embedder, "REINDEX_DEVICE", "auto")
    with job_embedder.reindex_embedder(lambda: pytest.fail("ripiego CPU inatteso")) as embedder:
        out = embedder.encode(["def f(): pass"] * 12, batch_size=12, return_dense=True)
        assert len(out["dense_vecs"]) == 12
        assert embedder.report()["embedding_device"] == "cuda"
    assert torch.cuda.memory_reserved() < 256 * 2**20

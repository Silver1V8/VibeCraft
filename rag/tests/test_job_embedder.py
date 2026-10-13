"""JobEmbedder: GPU solo per la durata del job di reindex, CPU come ripiego."""
import os
import subprocess
import weakref

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


def make(*, gpu=None, available=True, free=8000, enabled=True, load_error=None,
         oom_count=None):
    gpu, cpu = gpu or FakeModel("gpu"), FakeModel("cpu")
    loads, cleared = [], []
    probe = {} if oom_count is None else {"oom_count": oom_count}

    def free_probe():
        if isinstance(free, BaseException):
            raise free
        return free

    def load_gpu():
        loads.append(True)
        if load_error is not None:
            raise load_error
        return gpu

    embedder = JobEmbedder(load_gpu=load_gpu, cpu_model=lambda: cpu,
                           gpu_available=lambda: available, free_vram_mb=free_probe,
                           min_free_mb=3072, enabled=enabled,
                           empty_cache=lambda: cleared.append(True), **probe)
    return embedder, gpu, cpu, loads, cleared


def test_noop_job_never_loads_anything():
    embedder, _, _, loads, cleared = make()
    embedder.release()
    assert loads == []
    assert cleared == []
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


def test_oom_fallback_empties_cache_again_at_job_end():
    gpu = FakeModel("gpu", fail=torch.OutOfMemoryError("CUDA out of memory"))
    embedder, _, _, _, cleared = make(gpu=gpu)
    embedder.encode(["a"])
    after_fallback = len(cleared)
    embedder.release()  # fine del job: la cache va svuotata anche dopo il ripiego
    assert len(cleared) > after_fallback


def test_load_failure_empties_cache_at_job_end():
    embedder, _, _, _, cleared = make(load_error=RuntimeError("CUDA driver mismatch"))
    embedder.encode(["a"])
    embedder.release()
    assert cleared


def test_oom_fallback_empties_cache_after_the_exception_is_gone():
    class Blob:
        pass

    seen, alive_at_empty = {}, []

    class OOMGpu(FakeModel):
        def encode(self, texts, **kwargs):
            blob = Blob()  # vive nel frame referenziato dal traceback dell'eccezione
            seen["blob"] = weakref.ref(blob)
            raise torch.OutOfMemoryError("CUDA out of memory")

    embedder = JobEmbedder(
        load_gpu=lambda: OOMGpu("gpu"), cpu_model=lambda: FakeModel("cpu"),
        gpu_available=lambda: True, free_vram_mb=lambda: 8000, min_free_mb=3072,
        enabled=True,
        empty_cache=lambda: alive_at_empty.append(seen["blob"]() is not None))
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert alive_at_empty == [False]


def test_free_vram_probe_failure_falls_back_to_cpu_without_touching_cuda():
    embedder, _, cpu, loads, cleared = make(free=RuntimeError("nvidia-smi assente"))
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert loads == [] and cleared == []
    assert "VRAM non interrogabile" in embedder.report()["embedding_fallback_reason"]
    embedder.release()
    assert cleared == []  # la sonda non crea un contesto CUDA: niente da svuotare


def _nvidia_smi(monkeypatch, *, stdout="", returncode=0, error=None):
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if error is not None:
            raise error
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(job_embedder.subprocess, "run", run)
    return calls


def test_free_vram_reads_first_gpu_line_from_nvidia_smi(monkeypatch):
    calls = _nvidia_smi(monkeypatch, stdout="4542\n")
    assert job_embedder._free_vram_mb() == 4542
    cmd, kwargs = calls[0]
    assert cmd[0] == "nvidia-smi" and "--query-gpu=memory.free" in cmd
    assert kwargs["timeout"] == 5


def test_free_vram_uses_device_zero_on_multi_gpu(monkeypatch):
    _nvidia_smi(monkeypatch, stdout="4542\n812\n")
    assert job_embedder._free_vram_mb() == 4542


@pytest.mark.parametrize("kwargs", [
    {"returncode": 9, "stdout": ""},
    {"error": FileNotFoundError("nvidia-smi")},
    {"error": subprocess.TimeoutExpired("nvidia-smi", 5)},
    {"stdout": "No devices were found\n"},
    {"stdout": ""},
])
def test_free_vram_raises_when_nvidia_smi_is_unusable(monkeypatch, kwargs):
    _nvidia_smi(monkeypatch, **kwargs)
    with pytest.raises(Exception):
        job_embedder._free_vram_mb()


class OOMCounter:
    def __init__(self):
        self.value = 0

    def __call__(self):
        return self.value


def test_real_oom_surfacing_as_attribute_error_falls_back_to_cpu():
    counter = OOMCounter()

    class FlagLikeGpu(FakeModel):
        def encode(self, texts, **kwargs):
            self.calls.append(list(texts))
            counter.value += 1  # il contatore di OOM di CUDA cresce, poi l'errore è altro
            raise AttributeError("'list' object has no attribute 'keys'")

    gpu = FlagLikeGpu("gpu")
    embedder, _, cpu, _, cleared = make(gpu=gpu, oom_count=counter)
    assert embedder.encode(["a", "b"])["dense_vecs"] == ["cpu", "cpu"]
    assert cpu.calls == [["a", "b"]] and gpu.stopped and cleared
    assert "memoria GPU" in embedder.report()["embedding_fallback_reason"]


def test_attribute_error_without_oom_counter_increase_propagates():
    gpu = FakeModel("gpu", fail=AttributeError("'list' object has no attribute 'keys'"))
    embedder, _, cpu, _, _ = make(gpu=gpu, oom_count=OOMCounter())
    with pytest.raises(AttributeError):
        embedder.encode(["a"])
    assert cpu.calls == []


def test_oom_count_reading_failure_counts_as_zero(monkeypatch):
    monkeypatch.setattr(torch.cuda, "memory_stats",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no cuda")))
    assert job_embedder._cuda_oom_count() == 0


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


def test_incremental_route_passes_job_embedder_and_reports_device(monkeypatch):
    from api import routes_reindex

    monkeypatch.setattr(routes_reindex, "ensure_shared_resources", lambda **kwargs: None)
    received = {}

    def fake_incremental(**kwargs):
        received.update(kwargs)
        kwargs["embed_model"].encode(["x"])
        return {"noop": False}

    monkeypatch.setattr(routes_reindex, "incremental_index", fake_incremental)
    monkeypatch.setattr(routes_reindex, "_reindex_embed_model", lambda: FakeModel("cpu"))

    result = routes_reindex._run_reindex(None)

    assert isinstance(received["embed_model"], JobEmbedder)
    assert result["embedding_device"] == "cpu"  # conftest: VIBECRAFT_REINDEX_DEVICE=cpu


def test_full_rebuild_route_uses_job_embedder(monkeypatch):
    from api import routes_reindex

    seen = {}

    def fake_build(**kwargs):
        seen["model"] = kwargs["embed_model"]
        kwargs["collector"].update({"phase_timings_seconds": {
            p: 0.0 for p in ("init_model", "scan_hash", "load", "parsing_embedding", "qdrant",
                             "relink", "save_hash", "eval_gate", "promote")}, "counts": {}})
        return None

    monkeypatch.setattr(routes_reindex, "build_graph_and_index", fake_build)
    monkeypatch.setattr(routes_reindex, "_reindex_embed_model",
                        lambda: pytest.fail("modello CPU caricato senza encode"))

    result = routes_reindex._run_full_rebuild(None)

    assert isinstance(seen["model"], JobEmbedder)
    assert result["embedding_device"] == "unused"


@pytest.mark.skipif(os.environ.get("VIBECRAFT_TEST_GPU") == "1",
                    reason="con VIBECRAFT_TEST_GPU=1 il device è scelto dall'utente")
def test_suite_forces_cpu_even_if_the_shell_exports_auto():
    # conftest sovrascrive un eventuale VIBECRAFT_REINDEX_DEVICE=auto esportato
    from core import config
    assert os.environ["VIBECRAFT_REINDEX_DEVICE"] == "cpu"
    assert config.REINDEX_DEVICE == "cpu"

"""JobEmbedder: GPU in un processo figlio per la sola durata del job di reindex, CPU come
ripiego. I test con FakeWorker provano la scelta del device senza avviare processi; quelli
con `real_worker` avviano il worker vero (python -m core.gpu_worker) con un loader finto."""
import functools
import logging
import os
import pickle
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import psutil
import pytest
import torch

import core
from core import job_embedder
from core.job_embedder import GpuWorkerUnavailable, JobEmbedder
from tests import fake_gpu_loader


class FakeModel:
    def __init__(self, name):
        self.name, self.calls = name, []

    def encode(self, texts, **kwargs):
        self.calls.append(list(texts))
        return {"dense_vecs": [self.name] * len(texts)}


class FakeWorker(FakeModel):
    def __init__(self, fail=None):
        super().__init__("gpu")
        self.fail, self.stops = fail, 0

    def encode(self, texts, **kwargs):
        if self.fail is not None:
            self.calls.append(list(texts))
            raise self.fail
        return super().encode(texts, **kwargs)

    def stop(self):
        self.stops += 1


def make(*, worker=None, available=True, free=8000, enabled=True, start_error=None):
    worker, cpu = worker or FakeWorker(), FakeModel("cpu")
    starts = []

    def free_probe():
        if isinstance(free, BaseException):
            raise free
        return free

    def start_worker():
        starts.append(True)
        if start_error is not None:
            raise start_error
        return worker

    embedder = JobEmbedder(start_worker=start_worker, cpu_model=lambda: cpu,
                           gpu_available=lambda: available, free_vram_mb=free_probe,
                           min_free_mb=3072, enabled=enabled)
    return embedder, worker, cpu, starts


def test_noop_job_never_starts_a_worker():
    embedder, worker, _, starts = make()
    embedder.release()
    assert starts == [] and worker.stops == 0
    assert embedder.report()["embedding_device"] == "unused"


def test_uses_gpu_worker_then_stops_it():
    embedder, worker, cpu, starts = make()
    assert embedder.encode(["a"])["dense_vecs"] == ["gpu"]
    assert embedder.encode(["b"])["dense_vecs"] == ["gpu"]
    assert starts == [True] and cpu.calls == []
    embedder.release()
    assert worker.stops == 1
    report = embedder.report()
    assert report["embedding_device"] == "cuda" and report["embedding_fallback_reason"] is None
    assert report["embedding_load_seconds"] >= 0


def test_release_is_idempotent():
    embedder, worker, _, _ = make()
    embedder.encode(["a"])
    embedder.release()
    embedder.release()
    assert worker.stops == 1


def test_low_free_vram_goes_cpu_without_starting_a_worker():
    embedder, _, cpu, starts = make(free=1000)
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert starts == []
    assert "VRAM" in embedder.report()["embedding_fallback_reason"]


def test_cuda_unavailable_goes_cpu():
    embedder, _, _, starts = make(available=False)
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert starts == [] and embedder.report()["embedding_device"] == "cpu"


def test_disabled_goes_cpu():
    embedder, _, _, starts = make(enabled=False)
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert starts == []
    assert "VIBECRAFT_REINDEX_DEVICE" in embedder.report()["embedding_fallback_reason"]


def test_free_vram_probe_failure_falls_back_to_cpu_without_starting_a_worker():
    embedder, _, _, starts = make(free=RuntimeError("nvidia-smi assente"))
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert starts == []
    assert "VRAM non interrogabile" in embedder.report()["embedding_fallback_reason"]


def test_worker_that_cannot_start_falls_back_to_cpu():
    reason = "caricamento del modello su GPU fallito: RuntimeError: driver CUDA non compatibile"
    embedder, _, _, _ = make(start_error=GpuWorkerUnavailable(reason))
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert embedder.report()["embedding_fallback_reason"] == reason


def test_worker_spawn_error_falls_back_to_cpu():
    embedder, _, _, _ = make(start_error=OSError("eseguibile non trovato"))
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    reason = embedder.report()["embedding_fallback_reason"]
    assert "avvio del processo GPU" in reason and "eseguibile non trovato" in reason


def test_unavailable_worker_retries_same_call_on_cpu_and_stays_there():
    worker = FakeWorker(fail=GpuWorkerUnavailable("memoria GPU esaurita durante l'embedding"))
    embedder, _, cpu, _ = make(worker=worker)
    assert embedder.encode(["a", "b"])["dense_vecs"] == ["cpu", "cpu"]
    assert cpu.calls == [["a", "b"]]
    assert worker.stops == 1  # processo fermato subito, non a fine job
    embedder.encode(["c"])
    assert len(worker.calls) == 1 and cpu.calls[-1] == ["c"]
    embedder.release()
    assert worker.stops == 1
    report = embedder.report()
    assert report["embedding_device"] == "cpu" and "memoria" in report["embedding_fallback_reason"]


def test_worker_error_propagates_without_fallback():
    worker = FakeWorker(fail=RuntimeError("embedding fallito nel processo GPU: input malformato"))
    embedder, _, cpu, _ = make(worker=worker)
    with pytest.raises(RuntimeError, match="malformato"):
        embedder.encode(["a"])
    assert cpu.calls == [] and embedder.report()["embedding_device"] == "cuda"


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


def test_context_stops_the_worker_even_when_job_fails(monkeypatch):
    worker = FakeWorker()
    monkeypatch.setattr(job_embedder, "REINDEX_DEVICE", "auto")
    monkeypatch.setattr(job_embedder, "_start_gpu_worker", lambda: worker)
    monkeypatch.setattr(job_embedder, "_cuda_available", lambda: True)
    monkeypatch.setattr(job_embedder, "_free_vram_mb", lambda: 8000)
    with pytest.raises(RuntimeError, match="job fallito"):
        with job_embedder.reindex_embedder(lambda: FakeModel("cpu")) as embedder:
            embedder.encode(["x"])
            raise RuntimeError("job fallito")
    assert worker.stops == 1


class RealWorkers:
    """Avvia il worker vero (python -m core.gpu_worker) con un loader finto. Tiene sia i
    Popen sia i pid annotati dai loader: con un venv su Windows il Popen è il launcher di
    Scripts/python.exe e l'interprete che lavora è un suo figlio."""

    def __init__(self, monkeypatch, pid_file):
        self.spawned, self.pid_file, self._monkeypatch = [], pid_file, monkeypatch

    def use(self, loader, *, ready_timeout=30.0):
        self._monkeypatch.setattr(job_embedder, "_start_gpu_worker", functools.partial(
            job_embedder.start_gpu_worker, loader=f"tests.fake_gpu_loader:{loader}",
            ready_timeout=ready_timeout))
        return self.spawned

    def pids(self):
        if not self.pid_file.exists():
            return []
        return [int(line) for line in self.pid_file.read_text(encoding="utf-8").split()]

    def assert_all_exited(self):
        assert self.spawned and all(p.poll() is not None for p in self.spawned)
        pids = self.pids()
        assert pids
        deadline = time.monotonic() + 5
        while any(psutil.pid_exists(pid) for pid in pids) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not any(psutil.pid_exists(pid) for pid in pids)


@pytest.fixture
def real_worker(monkeypatch, tmp_path):
    """reindex_embedder con il worker vero e i loader di tests.fake_gpu_loader; le sonde
    dicono "GPU disponibile, VRAM sufficiente"."""
    workers = RealWorkers(monkeypatch, tmp_path / "worker.pids")

    class RecordingPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            workers.spawned.append(self)

    monkeypatch.setattr(subprocess, "Popen", RecordingPopen)
    monkeypatch.setenv(fake_gpu_loader.PID_FILE_ENV, str(workers.pid_file))
    monkeypatch.setattr(job_embedder, "REINDEX_DEVICE", "auto")
    monkeypatch.setattr(job_embedder, "_cuda_available", lambda: True)
    monkeypatch.setattr(job_embedder, "_free_vram_mb", lambda: 8000)
    yield workers
    for process in workers.spawned:  # rete di sicurezza: nessun figlio sopravvive al test
        if process.poll() is None:
            process.kill()
            process.wait()


def no_cpu():
    pytest.fail("ripiego CPU inatteso")


def test_real_worker_round_trip_and_graceful_stop(real_worker):
    spawned = real_worker.use("echo")
    texts = ["a\nb", "ccc", ""]
    with job_embedder.reindex_embedder(no_cpu) as embedder:
        out = embedder.encode(texts, batch_size=3)
        assert spawned[0].poll() is None  # vivo per tutto il job
        report = embedder.report()
    expected = fake_gpu_loader.EchoModel().encode(texts, batch_size=3)
    np.testing.assert_array_equal(out["dense_vecs"], expected["dense_vecs"])
    assert out["lexical_weights"] == expected["lexical_weights"]
    for got, want in zip(out["colbert_vecs"], expected["colbert_vecs"], strict=True):
        np.testing.assert_array_equal(got, want)
    assert report["embedding_device"] == "cuda" and report["embedding_load_seconds"] > 0
    assert len(spawned) == 1 and spawned[0].poll() == 0
    real_worker.assert_all_exited()


def test_real_worker_is_a_separate_process_running_the_same_core(real_worker):
    spawned = real_worker.use("introspect")
    with job_embedder.reindex_embedder(no_cpu) as embedder:
        info = embedder.encode(["a"])
    assert real_worker.pids() == [info["pid"]] and info["pid"] != os.getpid()
    assert Path(info["core_file"]).resolve() == Path(core.__file__).resolve()
    assert spawned[0].args[0] == job_embedder.sys.executable
    real_worker.assert_all_exited()


def test_real_worker_oom_falls_back_and_retries_the_same_call(real_worker):
    spawned = real_worker.use("oom")
    cpu = FakeModel("cpu")
    with job_embedder.reindex_embedder(lambda: cpu) as embedder:
        assert embedder.encode(["a", "b"])["dense_vecs"] == ["cpu", "cpu"]
        real_worker.assert_all_exited()  # fermato prima del ripiego, non a fine job
        embedder.encode(["c"])
    assert cpu.calls == [["a", "b"], ["c"]] and len(spawned) == 1
    report = embedder.report()
    assert report["embedding_device"] == "cpu"
    assert "memoria GPU esaurita" in report["embedding_fallback_reason"]
    assert "out of memory" in report["embedding_fallback_reason"]


def test_real_worker_crash_mid_job_falls_back_with_exit_code(real_worker):
    spawned = real_worker.use("crash")
    cpu = FakeModel("cpu")
    with job_embedder.reindex_embedder(lambda: cpu) as embedder:
        assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert cpu.calls == [["a"]]
    reason = embedder.report()["embedding_fallback_reason"]
    assert "terminato" in reason and "codice di uscita 3" in reason
    assert spawned[0].poll() == 3
    real_worker.assert_all_exited()


def test_real_worker_error_raises_with_child_traceback_and_no_fallback(real_worker):
    real_worker.use("bad_input")
    with pytest.raises(RuntimeError) as raised:
        with job_embedder.reindex_embedder(no_cpu) as embedder:
            embedder.encode(["a"])
    message = str(raised.value)
    assert "input malformato" in message and "ValueError" in message and "Traceback" in message
    assert embedder.report()["embedding_device"] == "cuda"
    real_worker.assert_all_exited()


def test_real_worker_load_error_falls_back(real_worker):
    real_worker.use("broken")
    with job_embedder.reindex_embedder(lambda: FakeModel("cpu")) as embedder:
        assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    reason = embedder.report()["embedding_fallback_reason"]
    assert "caricamento" in reason and "driver CUDA non compatibile" in reason
    real_worker.assert_all_exited()


def test_real_worker_exiting_while_loading_falls_back(real_worker):
    spawned = real_worker.use("exit_while_loading")
    with job_embedder.reindex_embedder(lambda: FakeModel("cpu")) as embedder:
        assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert "codice di uscita 5" in embedder.report()["embedding_fallback_reason"]
    assert spawned[0].poll() == 5
    real_worker.assert_all_exited()


def test_real_worker_not_ready_in_time_is_killed_and_falls_back(real_worker, monkeypatch):
    # Il timeout di "ready" parte solo quando il loader lento ha annotato il pid (dopo
    # l'avvio dell'interprete e l'import di numpy, lento a freddo o con l'antivirus):
    # così si può sempre verificare che l'interprete ucciso non esista più.
    real_wait_ready = job_embedder.GpuWorker.wait_ready

    def wait_ready_once_pid_known(self, timeout):
        deadline = time.monotonic() + 20
        while not real_worker.pids() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not real_worker.pids():
            pytest.fail("il loader lento non ha annotato il pid entro 20 s")
        return real_wait_ready(self, timeout)

    monkeypatch.setattr(job_embedder.GpuWorker, "wait_ready", wait_ready_once_pid_known)
    real_worker.use("slow", ready_timeout=1.0)
    with job_embedder.reindex_embedder(lambda: FakeModel("cpu")) as embedder:
        started = time.monotonic()
        assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
        real_worker.assert_all_exited()  # ucciso prima del ripiego, interprete compreso
    assert time.monotonic() - started < 30
    assert "non pronto entro 1 s" in embedder.report()["embedding_fallback_reason"]


def test_start_kills_the_worker_when_the_ready_reply_is_malformed(real_worker, monkeypatch):
    real_worker.use("echo")

    def read_then_garble(self, box):
        pickle.load(self.process.stdout)  # il figlio è pronto (e ha annotato il pid)
        box.append(42)  # risposta che non è una tupla: wait_ready solleva TypeError

    monkeypatch.setattr(job_embedder.GpuWorker, "_read_into", read_then_garble)
    with pytest.raises(TypeError):
        job_embedder.start_gpu_worker(loader="tests.fake_gpu_loader:echo")
    real_worker.assert_all_exited()
    assert not job_embedder._live_workers


def test_live_workers_are_killed_at_server_exit(real_worker):
    real_worker.use("echo")
    worker = job_embedder.start_gpu_worker(loader="tests.fake_gpu_loader:echo")
    assert worker in job_embedder._live_workers and worker.process.poll() is None
    job_embedder._kill_live_workers()  # registrata con atexit: i thread dei job sono daemon
    real_worker.assert_all_exited()
    assert worker not in job_embedder._live_workers


def test_real_worker_stderr_goes_to_the_server_log(real_worker, caplog):
    real_worker.use("chatty")
    caplog.set_level(logging.INFO, logger=job_embedder.logger.name)
    with job_embedder.reindex_embedder(no_cpu) as embedder:
        embedder.encode(["t"] * 12, batch_size=12)  # come FlagEmbedding: barra tqdm attiva
    lines = [r.getMessage() for r in caplog.records if r.name == job_embedder.logger.name]
    forwarded = [line for line in lines if line.startswith("[gpu-worker] ")]
    assert any("rumore nativo su stderr" in line for line in forwarded)
    assert any("Inference Embeddings" in line for line in forwarded)
    real_worker.assert_all_exited()
    assert not job_embedder._live_workers


def test_real_worker_exits_when_the_job_fails(real_worker):
    spawned = real_worker.use("echo")
    with pytest.raises(RuntimeError, match="job fallito"):
        with job_embedder.reindex_embedder(no_cpu) as embedder:
            embedder.encode(["x"])
            raise RuntimeError("job fallito")
    assert spawned[0].poll() == 0
    real_worker.assert_all_exited()


def test_real_worker_that_does_not_exit_after_stop_is_killed(real_worker, monkeypatch):
    monkeypatch.setattr(job_embedder, "GPU_WORKER_STOP_TIMEOUT_S", 0.5)
    real_worker.use("lingering")
    started = time.monotonic()
    with job_embedder.reindex_embedder(no_cpu) as embedder:
        embedder.encode(["x"])
    assert time.monotonic() - started < 10
    real_worker.assert_all_exited()
    embedder.release()  # idempotente anche dopo l'uccisione


@pytest.mark.skipif(sys.platform != "win32", reason="riguarda le console di Windows")
def test_real_worker_survives_a_server_started_from_a_console():
    # pytest cattura il descrittore 2 su file: la console va riprodotta in un processo a
    # parte (tests/console_stderr_helper.py), con STD_ERROR_HANDLE su CONOUT$.
    helper = Path(__file__).resolve().parent / "console_stderr_helper.py"
    result = subprocess.run([sys.executable, str(helper)], cwd=helper.parent.parent,
                            capture_output=True, text=True, timeout=120,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout.strip() == "OK"


def _gpu_memory_used_mb() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=5, check=True)
    return int(out.stdout.strip().splitlines()[0])


@pytest.mark.skipif(os.environ.get("VIBECRAFT_TEST_GPU") != "1",
                    reason="opt-in: VIBECRAFT_TEST_GPU=1 su una macchina con CUDA")
def test_real_gpu_worker_returns_all_its_vram(monkeypatch):
    monkeypatch.setattr(job_embedder, "REINDEX_DEVICE", "auto")
    before = _gpu_memory_used_mb()
    with job_embedder.reindex_embedder(no_cpu) as embedder:
        out = embedder.encode(["def f(): pass"] * 12, batch_size=12, return_dense=True)
        assert len(out["dense_vecs"]) == 12
        assert embedder.report()["embedding_device"] == "cuda"
    deadline = time.monotonic() + 5
    after = _gpu_memory_used_mb()
    while after > before + 150 and time.monotonic() < deadline:
        time.sleep(0.25)
        after = _gpu_memory_used_mb()
    # misurato con questo processo ancora vivo: la VRAM torna senza riavviare il server
    assert after <= before + 150, (before, after)
    assert not torch.cuda.is_initialized()  # il processo del server non crea mai un contesto


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

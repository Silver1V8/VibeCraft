"""core.gpu_worker: protocollo del processo figlio che fa l'embedding su GPU di un job.

La logica (caricamento, risposte, riconoscimento degli OOM) è provata in-process su stream
in memoria; la protezione dello stdout del protocollo su un processo vero."""
import io
import os
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch

from core import gpu_worker

RAG_DIR = Path(__file__).resolve().parent.parent


def _stream(*messages):
    buf = io.BytesIO()
    for message in messages:
        pickle.dump(message, buf, protocol=pickle.HIGHEST_PROTOCOL)
    buf.seek(0)
    return buf


def _read_all(buf):
    buf.seek(0)
    replies = []
    while True:
        try:
            replies.append(pickle.load(buf))
        except EOFError:
            return replies


class Model:
    def __init__(self, fail=None, before=None):
        self.fail, self.before, self.calls = fail, before, []

    def encode(self, texts, **kwargs):
        self.calls.append((list(texts), kwargs))
        if self.before is not None:
            self.before()
        if self.fail is not None:
            raise self.fail
        return {"dense_vecs": [len(t) for t in texts]}


def serve(model, *messages, oom_count=lambda: 0):
    def load():
        if isinstance(model, BaseException):
            raise model
        return model

    out = io.BytesIO()
    code = gpu_worker.serve(load, _stream(*messages), out, oom_count=oom_count)
    return code, _read_all(out)


def test_ready_then_encode_then_stop():
    model = Model()
    code, replies = serve(model, ("encode", ["ab", "c"], {"batch_size": 2}), ("stop",))
    assert code == 0
    assert replies[0][0] == "ready" and replies[0][1] >= 0
    assert replies[1:] == [("ok", {"dense_vecs": [2, 1]})]
    assert model.calls == [(["ab", "c"], {"batch_size": 2})]


def test_end_of_input_exits_cleanly():
    code, replies = serve(Model(), ("encode", ["a"], {}))
    assert code == 0
    assert [kind for kind, *_ in replies] == ["ready", "ok"]


def test_load_error_is_reported_and_the_worker_exits():
    code, replies = serve(RuntimeError("driver CUDA non compatibile"), ("encode", ["a"], {}))
    assert code != 0
    assert len(replies) == 1
    kind, message = replies[0]
    assert kind == "load_error" and "driver CUDA non compatibile" in message


def test_oom_text_is_reported_as_oom():
    model = Model(fail=RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB"))
    _, replies = serve(model, ("encode", ["a"], {}))
    kind, message = replies[1]
    assert kind == "oom" and "out of memory" in message


def test_torch_out_of_memory_error_is_reported_as_oom():
    _, replies = serve(Model(fail=torch.OutOfMemoryError("allocazione fallita")),
                       ("encode", ["a"], {}))
    assert replies[1][0] == "oom"


def test_real_oom_surfacing_as_attribute_error_is_reported_as_oom():
    counter = {"ooms": 0}

    def grow():
        counter["ooms"] += 1  # il contatore di CUDA cresce, poi FlagEmbedding solleva altro

    model = Model(fail=AttributeError("'list' object has no attribute 'keys'"), before=grow)
    _, replies = serve(model, ("encode", ["a"], {}), oom_count=lambda: counter["ooms"])
    assert replies[1][0] == "oom"


def test_other_errors_carry_the_child_traceback_and_the_worker_keeps_serving():
    calls = []

    class Flaky(Model):
        def encode(self, texts, **kwargs):
            calls.append(texts)
            if len(calls) == 1:
                raise AttributeError("'list' object has no attribute 'keys'")
            return super().encode(texts, **kwargs)

    _, replies = serve(Flaky(), ("encode", ["a"], {}), ("encode", ["bb"], {}))
    kind, message = replies[1]
    assert kind == "error"
    assert "Traceback" in message and "AttributeError" in message and "keys" in message
    assert replies[2] == ("ok", {"dense_vecs": [2]})


def test_unknown_message_is_an_error():
    _, replies = serve(Model(), ("boh",))
    assert replies[1][0] == "error" and "boh" in replies[1][1]


def test_oom_count_reading_failure_counts_as_zero(monkeypatch):
    monkeypatch.setattr(torch.cuda, "memory_stats",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no cuda")))
    assert gpu_worker._cuda_oom_count() == 0


def test_oom_count_is_zero_without_importing_torch(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)  # come in un figlio con loader finto
    assert gpu_worker._cuda_oom_count() == 0
    assert gpu_worker._is_oom(RuntimeError("CUDA out of memory"))
    assert not gpu_worker._is_oom(ValueError("input malformato"))


def _talk(loader, *messages):
    """Avvia il worker vero con un loader finto e ne legge tutte le risposte."""
    process = subprocess.Popen(
        [sys.executable, "-m", "core.gpu_worker", "--loader", f"tests.fake_gpu_loader:{loader}"],
        cwd=RAG_DIR, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = process.communicate(_stream(*messages).getvalue(), timeout=30)
    return process.returncode, _read_all(io.BytesIO(out)), err


def test_library_output_on_stdout_does_not_corrupt_the_protocol():
    from tests import fake_gpu_loader

    code, replies, err = _talk("noisy", ("encode", ["a\nb", "cc"], {"batch_size": 2}), ("stop",))
    assert code == 0, err
    assert [kind for kind, *_ in replies] == ["ready", "ok"]
    expected = fake_gpu_loader.EchoModel().encode(["a\nb", "cc"], batch_size=2)
    np.testing.assert_array_equal(replies[1][1]["dense_vecs"], expected["dense_vecs"])
    assert replies[1][1]["lexical_weights"] == expected["lexical_weights"]
    # il rumore finisce su stderr, che nel server è il log
    assert b"rumore durante il caricamento" in err and b"rumore nativo sul descrittore 1" in err


def test_worker_module_does_not_import_torch_with_a_fake_loader():
    code, replies, err = _talk("introspect", ("encode", ["a"], {}))
    assert code == 0, err
    info = replies[1][1]
    assert info["torch_imported"] is False
    assert Path(info["core_file"]).resolve().parent == RAG_DIR / "core"
    assert info["pid"] != os.getpid()

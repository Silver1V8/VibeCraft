"""Loader finti per `python -m core.gpu_worker --loader tests.fake_gpu_loader:<fn>`.

Non importano FlagEmbedding né torch: il processo figlio parte in frazioni di secondo e i
test del protocollo reale (pipe, pickle, uscita del processo) restano veloci."""
import os
import sys
import time

import numpy as np

PID_FILE_ENV = "FAKE_GPU_WORKER_PID_FILE"


def _record_pid():
    """Annota il pid del processo che fa davvero il lavoro: con un venv su Windows il
    Popen del server è il launcher di Scripts/python.exe, l'interprete è un suo figlio."""
    path = os.environ.get(PID_FILE_ENV)
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{os.getpid()}\n")


class EchoModel:
    """Output deterministico con la forma di BGEM3FlagModel.encode: dense ndarray,
    lexical_weights lista di dict, colbert_vecs lista di ndarray. Le chiavi con "\\n" e
    "\\r\\n" verificano che la pipe binaria non traduca i fine riga."""

    def encode(self, texts, **kwargs):
        dense = np.array([[len(t), i, kwargs.get("batch_size", 0), 0.5]
                          for i, t in enumerate(texts)], dtype=np.float32)
        lexical = [{"tok\n": float(len(t)), "tok\r\n": 0.25} for t in texts]
        colbert = [np.full((len(t) + 1, 4), i, dtype=np.float32) for i, t in enumerate(texts)]
        return {"dense_vecs": dense, "lexical_weights": lexical, "colbert_vecs": colbert}


class _Raising:
    def __init__(self, exc):
        self._exc = exc

    def encode(self, texts, **kwargs):
        raise self._exc


class _Crashing:
    def encode(self, texts, **kwargs):
        os._exit(3)


class _Introspecting:
    def encode(self, texts, **kwargs):
        import core
        return {"pid": os.getpid(), "core_file": core.__file__, "cwd": os.getcwd(),
                "torch_imported": "torch" in sys.modules}


class _Noisy(EchoModel):
    def encode(self, texts, **kwargs):
        print("rumore di una libreria su stdout")
        os.write(1, b"rumore nativo sul descrittore 1\n")
        return super().encode(texts, **kwargs)


def echo():
    _record_pid()
    return EchoModel()


def oom():
    _record_pid()
    return _Raising(RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB"))


def crash():
    _record_pid()
    return _Crashing()


def bad_input():
    _record_pid()
    return _Raising(ValueError("input malformato"))


def introspect():
    _record_pid()
    return _Introspecting()


def noisy():
    _record_pid()
    print("rumore durante il caricamento")
    os.write(1, b"rumore nativo durante il caricamento\n")
    return _Noisy()


def broken():
    _record_pid()
    raise RuntimeError("driver CUDA non compatibile")


def exit_while_loading():
    _record_pid()
    os._exit(5)


def slow():
    _record_pid()
    time.sleep(60)
    return EchoModel()


def lingering():
    """Una libreria che lascia un thread non daemon: dopo ("stop",) l'interprete non esce."""
    _record_pid()
    import threading
    threading.Thread(target=time.sleep, args=(60,)).start()
    return EchoModel()


class _Chatty(EchoModel):
    """Come BGEM3FlagModel.encode: barra tqdm su stderr, disattivata sotto batch_size."""

    def encode(self, texts, **kwargs):
        from tqdm import trange
        batch_size = kwargs.get("batch_size", 256)
        for _ in trange(0, len(texts), batch_size, desc="Inference Embeddings",
                        disable=len(texts) < batch_size):
            pass
        os.write(2, b"rumore nativo su stderr\n")
        return super().encode(texts, **kwargs)


def chatty():
    _record_pid()
    return _Chatty()

"""Processo figlio che fa l'embedding bge-m3 su GPU per un singolo job di reindex.

Il server lo avvia con `python -m core.gpu_worker` (cwd = la cartella rag/) e lo ferma a
fine job: uscendo, il processo restituisce alla GPU tutta la VRAM che ha usato, contesto
CUDA compreso, senza riavviare il server (la GPU è condivisa con Ollama). Il lato server
è core.job_embedder.

Protocollo: messaggi pickle sulla stdin/stdout binarie del figlio. Dopo il caricamento il
figlio invia ("ready", secondi) oppure ("load_error", messaggio) ed esce; poi risponde a
("encode", testi, kwargs) con ("ok", output), ("oom", messaggio) o ("error", traceback)
ed esce su ("stop",) o a fine input. Lo stdout vero è riservato al protocollo: print,
tqdm e log delle librerie finiscono su stderr, una pipe che il server legge e inoltra
al proprio log riga per riga, col prefisso [gpu-worker].

`--loader modulo:funzione` sostituisce il caricamento reale (i test usano modelli finti).
"""
from __future__ import annotations

import argparse
import importlib
import os
import pickle
import sys
import time
import traceback


def load_bge_m3(device: str = "cuda:0"):
    from core.config import EMBEDDING_MODEL
    if device == "npu":
        from core.npu_runtime import load_npu_bge_m3
        return load_npu_bge_m3(EMBEDDING_MODEL)
    if device.startswith("ov:"):
        from core.npu_runtime import load_openvino_bge_m3
        return load_openvino_bge_m3(EMBEDDING_MODEL, device.split(":", 1)[1])
    from FlagEmbedding import BGEM3FlagModel
    return BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False, devices=device)


def _torch():
    """torch solo se già importato dal modello: un modello reale lo ha caricato, un
    loader finto no, e non serve pagarne l'import per leggere il contatore di OOM."""
    return sys.modules.get("torch")


def _cuda_oom_count() -> int:
    """Numero di OOM CUDA visti dall'allocatore; 0 se le statistiche non sono leggibili."""
    torch = _torch()
    if torch is None:
        return 0
    try:
        return int(torch.cuda.memory_stats().get("num_ooms", 0))
    except Exception:
        return 0


def _is_oom(exc: BaseException) -> bool:
    torch = _torch()
    if torch is not None and isinstance(exc, getattr(torch, "OutOfMemoryError", ())):
        return True
    return "out of memory" in str(exc).lower()


def serve(load, inp, out, *, oom_count=_cuda_oom_count) -> int:
    """Carica il modello e risponde alle richieste fino a ("stop",) o a fine input.
    Ritorna il codice di uscita del processo. Un OOM reale di FlagEmbedding può uscire
    come altra eccezione (AttributeError dopo aver ridotto il batch a zero): si riconosce
    dal contatore di OOM di CUDA cresciuto durante l'encode."""
    def send(message) -> None:
        pickle.dump(message, out, protocol=pickle.HIGHEST_PROTOCOL)
        out.flush()

    started = time.perf_counter()
    try:
        model = load()
    except Exception as exc:
        send(("load_error", f"{type(exc).__name__}: {exc}"))
        return 1
    send(("ready", time.perf_counter() - started))
    while True:
        try:
            message = pickle.load(inp)
        except EOFError:
            return 0
        if message[0] == "stop":
            return 0
        if message[0] != "encode":
            send(("error", f"messaggio sconosciuto: {message[0]!r}"))
            continue
        _, texts, kwargs = message
        ooms_before = oom_count()
        try:
            reply = ("ok", model.encode(texts, **kwargs))
        except Exception as exc:
            if _is_oom(exc) or oom_count() > ooms_before:
                reply = ("oom", f"{type(exc).__name__}: {exc}")
            else:
                reply = ("error", traceback.format_exc())
        send(reply)


def _protocol_streams():
    """Riserva lo stdout vero al protocollo e devia su stderr sia sys.stdout sia il
    descrittore 1, così nemmeno l'output nativo delle librerie può corromperlo."""
    sys.stdout.flush()
    out = os.fdopen(os.dup(sys.stdout.fileno()), "wb")
    target = sys.stderr if sys.stderr is not None else open(os.devnull, "w")
    os.dup2(target.fileno(), sys.stdout.fileno())
    sys.stdout = target
    return sys.stdin.buffer, out


def _resolve(spec: str):
    module, _, name = spec.partition(":")
    return getattr(importlib.import_module(module), name)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--loader", help="modulo:funzione che restituisce il modello")
    parser.add_argument("--device", default="cuda:0",
                        help="device del modello reale: cuda:N, mps, npu oppure ov:GPU")
    args = parser.parse_args(argv)
    inp, out = _protocol_streams()
    if args.loader:
        def load():  # risolto dentro serve(): un loader sbagliato diventa load_error
            return _resolve(args.loader)()
    else:
        def load():
            return load_bge_m3(args.device)
    return serve(load, inp, out)


if __name__ == "__main__":
    sys.exit(main())

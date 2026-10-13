"""Riproduce un server avviato da un terminale Windows: lo stderr del processo è un
handle di console (CONOUT$). Lanciato come processo a sé da test_job_embedder (mai
dentro pytest: AllocConsole cambierebbe la console del runner).

Alloca una console nascosta, punta STD_ERROR_HANDLE su CONOUT$ e avvia il worker vero
con un loader che scrive una barra tqdm su stderr come FlagEmbedding (>= batch_size
testi). Stampa "OK" ed esce 0 se l'embedding riesce, altrimenti "FAIL ..." ed esce 1;
2 se la console non si può preparare."""
import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

RAG_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAG_DIR))

STD_ERROR_HANDLE = -12
GENERIC_READ_WRITE = 0x80000000 | 0x40000000
FILE_SHARE_READ_WRITE = 0x1 | 0x2
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value


def _console_stderr() -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                     ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                     wintypes.HANDLE]
    kernel32.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
    kernel32.GetConsoleWindow.restype = wintypes.HWND
    kernel32.FreeConsole()
    if not kernel32.AllocConsole():
        raise OSError(ctypes.get_last_error(), "AllocConsole fallita")
    window = kernel32.GetConsoleWindow()
    if window:
        ctypes.WinDLL("user32").ShowWindow(window, 0)  # SW_HIDE
    handle = kernel32.CreateFileW("CONOUT$", GENERIC_READ_WRITE, FILE_SHARE_READ_WRITE,
                                  None, OPEN_EXISTING, 0, None)
    if handle in (None, INVALID_HANDLE_VALUE):
        raise OSError(ctypes.get_last_error(), "CONOUT$ non apribile")
    if not kernel32.SetStdHandle(wintypes.DWORD(STD_ERROR_HANDLE & 0xFFFFFFFF), handle):
        raise OSError(ctypes.get_last_error(), "SetStdHandle fallita")


def main() -> int:
    try:
        _console_stderr()
    except OSError as exc:
        print(f"SETUP {exc}", flush=True)
        return 2
    from core import job_embedder
    worker = None
    try:
        worker = job_embedder.start_gpu_worker(loader="tests.fake_gpu_loader:chatty",
                                               ready_timeout=30)
        out = worker.encode(["testo"] * 12, batch_size=12)
        assert len(out["dense_vecs"]) == 12
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {exc}", flush=True)
        return 1
    finally:
        if worker is not None:
            worker.stop()
    print("OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

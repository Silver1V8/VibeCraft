"""Recorder Ollama opt-in per runner di eval isolati; nessuna attivazione in produzione.

Osserva le funzioni reali di core.llm prima che scartino request/response.
Non cambia prompt, opzioni, cache, timeout o retry. Il tempo di copia non è zero.
Solo payload restituiti dal provider: consumi di richieste senza risposta ignoti.
"""
import json
import time
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from core import llm


class Recording:
    def __init__(self):
        self.attempts = []
        self.errors = []
        self.capture_complete = True
        self.current = None

    def capture(self, key, value):
        self.current[key] = deepcopy(value)

    def observe(self, key, value):
        try:
            self.capture(key, value)
        except Exception as exc:
            # Un guasto dell'osservatore non deve diventare LLMError e causare retry.
            self.capture_complete = False
            self.errors.append(f"{key}: {type(exc).__name__}: {exc}")

    @contextmanager
    def attempt(self, model, timeout):
        started = time.perf_counter()
        self.current = {
            "attempt": len(self.attempts) + 1, "provider": "ollama", "model": model,
            "started_at": datetime.now(timezone.utc).isoformat(), "timeout": timeout,
            "request": None, "response": None, "error": None,
        }
        self.attempts.append(self.current)
        try:
            yield
        except BaseException as exc:
            self.observe("error", {"type": type(exc).__name__, "message": str(exc)})
            raise
        finally:
            self.observe("elapsed_seconds", time.perf_counter() - started)
            self.current = None

    def save(self, path: Path):
        """I/O fuori dalla generazione: un errore di salvataggio non ritenta il provider."""
        path.write_text(json.dumps({
            "schema_version": 1, "capture_complete": self.capture_complete,
            "errors": self.errors, "attempts": self.attempts,
            "usage_policy": "Raw provider counts only; missing counts are unknown, not zero.",
        }, ensure_ascii=False, indent=2), encoding="utf-8")


@contextmanager
def record_ollama():
    """Attiva solo nel processo separato del runner, attorno a generate/agenerate.

    ponytail: patch globali, un recorder e una generazione alla volta; prima di
    introdurre eval concorrenti sostituire con osservazione isolata per richiesta.
    Importare questo modulo non installa patch. Uscendo ripristina tutto, anche
    con eccezioni. Non importarlo dal server e non usarlo in un worker condiviso.
    """
    recording = Recording()
    sync, asynchronous = llm._PROVIDERS["ollama"]
    payload_fn, extract_fn = llm._ollama_payload, llm._extract_ollama_text

    def payload(*args, **kwargs):
        value = payload_fn(*args, **kwargs)
        recording.observe("request", value)
        return value

    def extract(value):
        recording.observe("response", value)
        return extract_fn(value)

    def generate(model, prompt, timeout):
        with recording.attempt(model, timeout):
            return sync(model, prompt, timeout)

    async def agenerate(model, prompt, timeout):
        with recording.attempt(model, timeout):
            return await asynchronous(model, prompt, timeout)

    with patch.dict(llm._PROVIDERS, ollama=(generate, agenerate)), \
            patch.object(llm, "_ollama_payload", payload), \
            patch.object(llm, "_extract_ollama_text", extract):
        yield recording

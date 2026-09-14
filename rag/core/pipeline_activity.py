"""Correlazione osservata nel processo server; non attribuzione di identità."""
import os
from contextlib import contextmanager
from threading import Lock
from uuid import uuid4

_lock = Lock()
_active: dict[str, str | None] = {}


@contextmanager
def track(feature: str | None):
    attempt = 'attempt-' + uuid4().hex
    with _lock:
        _active[attempt] = feature
    try:
        yield attempt
    finally:
        with _lock:
            _active.pop(attempt, None)


def snapshot(feature: str) -> tuple[list[str], list[str], str]:
    # ponytail: osserva un processo; con più worker occorre un registro condiviso.
    with _lock:
        return (sorted(k for k, v in _active.items() if v == feature),
                sorted(k for k, v in _active.items() if v is None), f'process:{os.getpid()}')

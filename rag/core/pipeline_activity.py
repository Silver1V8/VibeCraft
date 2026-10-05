"""Correlazione osservata nel processo server; non attribuzione di identità."""
import os
from contextlib import contextmanager
from threading import Lock
from uuid import uuid4

_lock = Lock()
_active: dict[str, tuple[str | None, str | None]] = {}


@contextmanager
def track(feature: str | None, attempt_id: str | None = None, *, project=None):
    attempt = attempt_id or 'attempt-' + uuid4().hex
    with _lock:
        _active[attempt] = (project.id if project is not None else 'legacy', feature)
    try:
        yield attempt
    finally:
        with _lock:
            _active.pop(attempt, None)


def snapshot(feature: str, *, project=None) -> tuple[list[str], list[str], str]:
    # ponytail: osserva un processo; con più worker occorre un registro condiviso.
    with _lock:
        project_id = project.id if project is not None else 'legacy'
        return (sorted(k for k, v in _active.items() if v == (project_id, feature)),
                sorted(k for k, v in _active.items() if v == (project_id, None)),
                f'process:{os.getpid()}')

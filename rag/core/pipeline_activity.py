"""Registro condiviso su disco delle esecuzioni attive; non attribuzione di identità.

R8: il registro process-local produceva «zero active» senza senso con più worker.
Ora ogni tentativo scrive un record sotto ``database/pipeline/activity/`` (per
progetto), leggibile da tutti i processi che condividono lo stesso database.
Un PID morto o un record illeggibile viene scartato in snapshot; non certifica
chi abbia chiamato l'endpoint né un'identità umana.
"""
import json
import os
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from uuid import uuid4

from core.artifacts import _atomic_write_json
from core.config import DATABASE_DIR
from core.pipeline_gate import _now

_lock = Lock()
_active: dict[str, tuple[str | None, str | None, Path]] = {}


def _activity_dir(project=None) -> Path:
    base = (project.database_dir if project is not None else DATABASE_DIR) / 'pipeline' / 'activity'
    base.mkdir(parents=True, exist_ok=True)
    return base


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == 'nt':
        import ctypes
        # PROCESS_QUERY_LIMITED_INFORMATION: basta per sapere se il processo esiste.
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _record_path(attempt: str, project=None) -> Path:
    return _activity_dir(project) / (attempt + '.json')


def _write_record(attempt: str, project_id: str, feature: str | None, project=None) -> Path:
    path = _record_path(attempt, project)
    _atomic_write_json(path, {
        'attempt_id': attempt,
        'project_id': project_id,
        'feature': feature,
        'pid': os.getpid(),
        'started_at': _now(),
    })
    return path


def _read_record(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    attempt = data.get('attempt_id')
    project_id = data.get('project_id')
    pid = data.get('pid')
    if not isinstance(attempt, str) or not isinstance(project_id, str) or not isinstance(pid, int):
        return None
    if path.stem != attempt:
        return None
    return data


@contextmanager
def track(feature: str | None, attempt_id: str | None = None, *, project=None):
    attempt = attempt_id or 'attempt-' + uuid4().hex
    project_id = project.id if project is not None else 'legacy'
    path = _write_record(attempt, project_id, feature, project)
    with _lock:
        _active[attempt] = (project_id, feature, path)
    try:
        yield attempt
    finally:
        with _lock:
            _active.pop(attempt, None)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def snapshot(feature: str, *, project=None) -> tuple[list[str], list[str], str]:
    """Esecuzioni attive sulla feature e senza feature; scope = registro condiviso."""
    project_id = project.id if project is not None else 'legacy'
    scoped, unscoped = set(), set()
    folder = _activity_dir(project)
    try:
        entries = list(folder.iterdir())
    except OSError:
        entries = []
    for path in entries:
        if path.suffix != '.json':
            continue
        data = _read_record(path)
        if data is None or not _pid_alive(int(data['pid'])):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            continue
        if data['project_id'] != project_id:
            continue
        if data.get('feature') == feature:
            scoped.add(data['attempt_id'])
        elif data.get('feature') is None:
            unscoped.add(data['attempt_id'])
    # Unione con il registro in-process: copre il gap fra write e scan locale.
    with _lock:
        for attempt, (pid_project, feat, _path) in _active.items():
            if pid_project != project_id:
                continue
            if feat == feature:
                scoped.add(attempt)
            elif feat is None:
                unscoped.add(attempt)
    return (sorted(scoped), sorted(unscoped), 'shared-disk')

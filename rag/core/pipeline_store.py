"""Persistenza atomica delle validazioni; nessuna pulizia o rotazione automatica.

L'avvio API non è ancora vincolato. Errori di storage non diventano record assenti.
"""
import json
import re
from pathlib import Path

from pydantic import ValidationError

from core.artifacts import _atomic_write_json
from core.config import DATABASE_DIR
from core.open_points import _unique_keys
from core.pipeline import resolve_feature_dir
from core.pipeline_gate import ValidationRecord
from core.writer_lock import WriterLockBusyError, writer_lock


class PipelineStorageError(RuntimeError):
    """Guasto operativo: il chiamante deve esporre 503, non chiedere di cambiare la Spec."""
    action = 'operator_action'


class PipelineStorageBusyError(PipelineStorageError):
    """Writer concorrente: riprovare, senza modificare il contratto."""
    action = 'retryable'


class PipelineStore:
    def __init__(self, root: Path = DATABASE_DIR / 'pipeline'):
        self.root = root

    def _validation_path(self, feature: str, identifier: str) -> Path:
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', feature):
            raise ValueError('La feature deve essere uno slug canonico')
        if not re.fullmatch(r'val-[0-9a-f]{32}', identifier):
            raise ValueError('Riferimento di validazione non valido')
        folder = resolve_feature_dir(self.root / 'validations', feature)
        path = folder / (identifier + '.json')
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('Validazione fuori dalla directory pipeline')
        return path

    def write_validation(self, record: ValidationRecord) -> None:
        # Rivalida anche istanze mutate in memoria: niente passed introdotto via model_copy.
        checked = ValidationRecord.model_validate(record.model_dump())
        path = self._validation_path(checked.feature, checked.validation_id)
        try:
            with writer_lock(timeout_seconds=0, lock_path=path.parent / '.writer.lock'):
                previous = self.read_validation(checked.feature, checked.validation_id)
                if previous == checked:
                    return
                if previous and (previous.status != 'running' or previous.contract != checked.contract
                                 or previous.started_at != checked.started_at):
                    raise PipelineStorageError('Record concluso o contratto congelato non modificabile')
                _atomic_write_json(path, checked.model_dump())
        except WriterLockBusyError as exc:
            raise PipelineStorageBusyError('Scrittura concorrente della validazione: riprova') from exc
        except OSError as exc:
            raise PipelineStorageError(f'Scrittura della validazione non disponibile: {exc}') from exc

    def read_validation(self, feature: str, identifier: str) -> ValidationRecord | None:
        path = self._validation_path(feature, identifier)
        try:
            raw = path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError) as exc:
            raise PipelineStorageError(f'Lettura della validazione non disponibile: {exc}') from exc
        try:
            record = ValidationRecord.model_validate(json.loads(raw, object_pairs_hook=_unique_keys))
            if record.feature != feature or record.validation_id != identifier:
                raise ValueError('Identità del record diversa dal percorso richiesto')
            return record
        except (ValueError, ValidationError) as exc:
            raise PipelineStorageError(f'Record di validazione corrotto: {exc}') from exc

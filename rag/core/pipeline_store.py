"""Persistenza atomica delle validazioni; nessuna pulizia o rotazione automatica.

L'avvio agentic usa questo gate. Errori di storage non diventano record assenti.
"""
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

from pydantic import ValidationError

from core.artifacts import _atomic_write_json, _project_artifact_path
from core.projects import _unlinked, ProjectError
from core.config import DATABASE_DIR
from core.open_points import _unique_keys
from core.pipeline import resolve_feature_dir
from core.pipeline_gate import PointDecision, ValidationRecord, _now, content_hash
from uuid import uuid4
from core.writer_lock import WriterLockBusyError, writer_lock


class PipelineStorageError(RuntimeError):
    """Guasto operativo: il chiamante deve esporre 503, non chiedere di cambiare la Spec."""
    action = 'operator_action'


class PipelineStorageBusyError(PipelineStorageError):
    """Writer concorrente: riprovare, senza modificare il contratto."""
    action = 'retryable'


class PipelineStore:
    def __init__(self, root: Path | None = None, *, project=None):
        self.project = project
        self.root = root if root is not None else (project.database_dir if project else DATABASE_DIR) / 'pipeline'
        self._path(self.root)

    def _path(self, path):
        try:
            checked = _project_artifact_path(path, self.project) if self.project else _unlinked(path)
            if not checked.is_relative_to(_unlinked(self.root)):
                raise PipelineStorageError('Pipeline path outside project storage')
            return checked
        except (ProjectError, OSError, ValueError) as exc:
            raise PipelineStorageError('Archiviazione pipeline non disponibile.') from exc

    @contextmanager
    def feature_lock(self, feature):
        self._validation_path(feature, 'val-' + '0' * 32)
        try:
            with writer_lock(timeout_seconds=0, lock_path=self._path(self.root / 'locks' / (feature + '.lock'))):
                yield
        except WriterLockBusyError as exc:
            raise PipelineStorageBusyError('Operazione concorrente sulla feature: riprova.') from exc
        except OSError as exc:
            raise PipelineStorageError(f'Storage della feature non disponibile: {exc}') from exc

    def _read_events_unlocked(self):
        path = self._path(self.root / 'events.jsonl')
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('Registro eventi fuori da pipeline')
        if not path.exists():
            return []
        text = path.read_text(encoding='utf-8')
        if text and not text.endswith('\n'):
            raise ValueError('Registro eventi troncato: intervento operativo richiesto')
        events = [json.loads(line, object_pairs_hook=_unique_keys) for line in text.splitlines()]
        if any(not isinstance(e, dict) or not {'event', 'attempt_id', 'feature', 'recorded_at'} <= e.keys()
               for e in events):
            raise ValueError('Record evento incompleto')
        return events

    def read_events(self):
        """Un journal corrotto non equivale a nessun tentativo precedente."""
        try:
            with writer_lock(lock_path=self._path(self.root / '.events.lock')):
                return self._read_events_unlocked()
        except WriterLockBusyError as exc:
            raise PipelineStorageBusyError('Registro eventi occupato: riprova.') from exc
        except (OSError, ValueError, UnicodeError) as exc:
            raise PipelineStorageError(f'Registro eventi non disponibile: {exc}') from exc

    def retry_exists(self, feature, attempt_id):
        return attempt_id is None or any(e['event'] == 'execution_blocked' and e['feature'] == feature
                                        and e['attempt_id'] == attempt_id for e in self.read_events())

    def append_event(self, event, *, feature, attempt_id, retry_of_attempt_id=None, **details):
        if event not in ('validation_finished', 'execution_blocked', 'execution_started',
                         'execution_finished', 'open_point_decision_recorded',
                         # Esito della suite eseguita DAL SERVER dopo un run (core/verification.py):
                         # è l'unico evento del journal che non riporta una dichiarazione dell'agente.
                         'verification_finished'):
            raise ValueError('Evento pipeline non riconosciuto')
        record = dict(details, event=event, feature=feature, attempt_id=attempt_id,
                      retry_of_attempt_id=retry_of_attempt_id, recorded_at=_now())
        data = (json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
        try:
            # ponytail: journal piccolo riletto sotto lock a ogni append; indicizzare se la crescita lo richiede.
            with writer_lock(lock_path=self._path(self.root / '.events.lock')):
                self._read_events_unlocked()  # un tail corrotto non rende registrabile l’avvio
                with self._path(self.root / 'events.jsonl').open('ab') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
        except WriterLockBusyError as exc:
            raise PipelineStorageBusyError('Registrazione evento occupata: riprova.') from exc
        except (OSError, ValueError, UnicodeError) as exc:
            raise PipelineStorageError(f'Registrazione evento non disponibile: {exc}') from exc
        return record

    def _validation_path(self, feature: str, identifier: str) -> Path:
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', feature):
            raise ValueError('La feature deve essere uno slug canonico')
        if not re.fullmatch(r'val-[0-9a-f]{32}', identifier):
            raise ValueError('Riferimento di validazione non valido')
        folder = resolve_feature_dir(self.root / 'validations', feature)
        path = self._path(folder / (identifier + '.json'))
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('Validazione fuori dalla directory pipeline')
        return path

    def write_validation(self, record: ValidationRecord) -> None:
        # Rivalida anche istanze mutate in memoria: niente passed introdotto via model_copy.
        checked = ValidationRecord.model_validate(record.model_dump())
        path = self._validation_path(checked.feature, checked.validation_id)
        try:
            with writer_lock(timeout_seconds=0, lock_path=self._path(path.parent / '.writer.lock')):
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

    def decisions(self, feature: str) -> list[PointDecision]:
        folder = self._validation_path(feature, 'val-' + '0' * 32).parent
        folder = self._path(self.root / 'decisions' / folder.name)
        try:
            if not folder.resolve().is_relative_to(self.root.resolve()):
                raise ValueError('Directory decisioni fuori da pipeline')
            paths = sorted(folder.iterdir()) if folder.exists() else []
            records = []
            for path in paths:
                path = self._path(path)
                if path.suffix != '.json':
                    continue
                if not path.resolve().is_relative_to(self.root.resolve()):
                    raise ValueError('Record decisione fuori da pipeline')
                record = PointDecision.model_validate(json.loads(path.read_text(encoding='utf-8'),
                                                                 object_pairs_hook=_unique_keys))
                if record.feature != feature or path.stem != record.decision_id:
                    raise ValueError('Identità del record decisione non corrispondente')
                records.append(record)
            return records
        except (OSError, ValueError, UnicodeError) as exc:
            raise PipelineStorageError(f'Decisioni non disponibili: {exc}') from exc

    def record_decision(self, *, feature, point, spec_hash, status, motivation, declared_by,
                        declared_origin, observed_metadata, active_attempt_ids, coverage_findings) -> PointDecision:
        """L'accettazione non è esposta agli strumenti dell'agente; non è
        certificata come decisione umana dalla credenziale condivisa.

        Vale anche per le associazioni esplicite ai rilievi: nessuna equivalenza
        dedotta dal modello, nessuna identità umana attestata da un nome dichiarato.
        """
        # Per rendere origin_verified true servirebbero identità personale autenticata
        # (non una chiave condivisa), provenienza verificata dal server e revisione
        # esplicita della garanzia. Un nome/header o una sovrapposizione temporale
        # non bastano. Il chiamante NON può fornire questo campo.
        record = PointDecision(decision_id='dec-' + uuid4().hex, feature=feature, point=point,
            point_hash=content_hash(point), spec_hash=spec_hash, status=status, recorded_at=_now(),
            motivation=motivation, declared_by=declared_by, declared_origin=declared_origin,
            observed_metadata=observed_metadata, active_attempt_ids=active_attempt_ids,
            coverage_findings=coverage_findings, origin_verified=False)
        self._validation_path(feature, 'val-' + '0' * 32)  # stesso controllo dello slug
        path = self._path(self.root / 'decisions' / feature / (record.decision_id + '.json'))
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise PipelineStorageError('Decisione fuori dalla directory pipeline')
        try:
            _atomic_write_json(path, record.model_dump())
        except OSError as exc:
            raise PipelineStorageError(f'Scrittura decisione non disponibile: {exc}') from exc
        return record

    def latest_validation(self, feature: str, contract_hash: str) -> ValidationRecord | None:
        folder = self._validation_path(feature, 'val-' + '0' * 32).parent
        try:
            paths = list(folder.iterdir()) if folder.exists() else []
            records = [self.read_validation(feature, p.stem) for p in paths if p.suffix == '.json']
            records = [r for r in records if r is not None]
            matching = [r for r in records if r.passed and r.contract.hash == contract_hash]
            return max(matching or records, key=lambda r: (r.started_at, r.validation_id), default=None)
        except (OSError, ValueError) as exc:
            raise PipelineStorageError(f'Storico validazioni non disponibile: {exc}') from exc

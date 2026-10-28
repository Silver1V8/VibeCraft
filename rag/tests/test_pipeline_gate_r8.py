"""R8 — retention/GC, coverage contraddittoria, modello topic/defect, registry disco."""
import json

import pytest
from pydantic import ValidationError

from core import pipeline_activity, pipeline_gate as gate, pipeline_validation as validation
from core.pipeline_store import PipelineStore


CANVAS = '## Requirements\n'


def point():
    return dict(id='OP-001', functionality='Invio', original_question='Quale errore?',
                question='Quale errore?', assumption=None, uncovered_scenarios=['Caso negativo'],
                reason='missing_coverage',
                research=dict(status='not_started', new_evidence=[], verification='agent_reported'))


def spec(points=()):
    scenario = ('```gherkin\nSCENARIO: S01 - Invio\n  GIVEN pronto\n  WHEN inviato\n'
                '  THEN registrato\n```\n')
    return scenario + '## 4. Punti aperti\n```json\n' + json.dumps({'open_points': list(points)}) + '\n```'


def semantic(findings=(), suggestions=()):
    return json.dumps(dict(summary='Controllo concluso.', findings=list(findings),
                           suggestions=list(suggestions)))


def finished_record(store: PipelineStore, feature: str, *, suffix: str, started_at: str):
    contract = gate.make_contract(feature, CANVAS, spec())
    started = gate.new_validation(contract)
    data = started.model_dump()
    data['validation_id'] = 'val-' + (suffix * 8)[:32]
    data['attempt_id'] = 'attempt-' + (suffix * 8)[:32]
    data['started_at'] = started_at
    started = gate.ValidationRecord.model_validate(data)
    store.write_validation(started)
    finished = gate.finish_validation(
        started, contract,
        gate.ValidationChecks(structural=gate.Check(status='pass'), semantic=gate.Check(status='pass')),
        sources=gate.ValidationSources(),
        validator=gate.ValidatorEvidence(model='test', raw_response='{}'))
    # freeze finished_at relative order via rewrite of timestamps before final write
    payload = finished.model_dump()
    payload['finished_at'] = started_at.replace('+00:00', '+00:00')
    # finish_validation already wrote? No — caller writes. Adjust timestamps on finished.
    finished = gate.ValidationRecord.model_validate(payload)
    store.write_validation(finished)
    return finished


def test_validation_retention_keeps_latest_and_spares_running(tmp_path, monkeypatch):
    monkeypatch.setenv('VIBECRAFT_PIPELINE_VALIDATIONS_KEEP', '2')
    store = PipelineStore(tmp_path / 'pipeline')
    feature = 'demo-retention'
    keepers = []
    for i in range(4):
        keepers.append(finished_record(
            store, feature, suffix=f'{i:x}' * 4,
            started_at=f'2026-09-1{i}T10:00:00+00:00'))
    running = gate.new_validation(gate.make_contract(feature, CANVAS, spec()))
    store.write_validation(running)
    remaining = {p.stem for p in (store.root / 'validations' / feature).glob('val-*.json')}
    assert running.validation_id in remaining
    assert keepers[0].validation_id not in remaining
    assert keepers[1].validation_id not in remaining
    assert keepers[2].validation_id in remaining
    assert keepers[3].validation_id in remaining
    assert len(remaining) == 3  # 2 finished + running


def test_events_retention_keeps_last_lines(tmp_path, monkeypatch):
    monkeypatch.setenv('VIBECRAFT_PIPELINE_EVENTS_KEEP_LINES', '3')
    store = PipelineStore(tmp_path / 'pipeline')
    for i in range(5):
        store.append_event('execution_blocked', feature='demo',
                           attempt_id=f'attempt-{"%032d" % i}')
    events = store.read_events()
    assert len(events) == 3
    assert [e['attempt_id'] for e in events] == [
        'attempt-' + f'{i:032d}' for i in (2, 3, 4)]


@pytest.mark.parametrize('message', [
    'Nessuna lacuna rilevata nella copertura degli scenari.',
    'La copertura è completa per tutti i requisiti esaminati.',
    'Coverage is complete; no gaps remain.',
    'Tutti i casi sono coperti dagli scenari BDD.',
])
def test_contradictory_coverage_makes_report_nonconforming(message):
    contract = gate.make_contract('demo', CANVAS, spec([point()]))
    raw = semantic([dict(topic='coverage', defect='present', message=message,
                         contract_quote=None, source_doc_id=None, source_quote=None,
                         open_point_hash=None)])
    with pytest.raises(ValueError, match='Coverage contraddittoria'):
        validation.read_semantic(raw, contract, gate.ValidationSources())


def test_real_coverage_gap_still_blocks():
    contract = gate.make_contract('demo', CANVAS, spec([point()]))
    raw = semantic([dict(topic='coverage', defect='present',
                         message='Manca lo scenario negativo per OP-001.',
                         contract_quote=None, source_doc_id=None, source_quote=None,
                         open_point_hash=None)])
    _, check, findings = validation.read_semantic(raw, contract, gate.ValidationSources())
    assert check.status == 'fail'
    assert findings[0]['topic'] == 'coverage'
    assert findings[0]['kind'] == 'coverage'  # alias HTTP/UI
    assert findings[0]['defect'] == 'present'
    assert findings[0]['blocking'] is True


def test_legacy_kind_alias_still_parses_as_topic():
    contract = gate.make_contract('demo', CANVAS, spec())
    raw = semantic([dict(kind='conflict', message='Viola il vincolo.',
                         contract_quote='## Requirements', source_doc_id=None,
                         source_quote=None, open_point_hash=None)])
    _, check, findings = validation.read_semantic(raw, contract, gate.ValidationSources())
    assert check.status == 'fail'
    assert findings[0]['topic'] == 'conflict'
    assert findings[0]['kind'] == 'conflict'


def test_defect_absent_is_rejected():
    with pytest.raises(ValidationError):
        validation.SemanticFinding.model_validate(dict(
            topic='coverage', defect='absent', message='Tutto ok',
            contract_quote=None, source_doc_id=None, source_quote=None,
            open_point_hash=None))


def test_shared_disk_activity_visible_across_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_activity, 'DATABASE_DIR', tmp_path / 'database')
    (tmp_path / 'database').mkdir()
    with pipeline_activity.track('feat-a') as attempt:
        active, unscoped, scope = pipeline_activity.snapshot('feat-a')
        assert attempt in active
        assert scope == 'shared-disk'
        path = tmp_path / 'database' / 'pipeline' / 'activity' / (attempt + '.json')
        assert path.is_file()
        # Simula un secondo worker: svuota solo la mappa in-process e rileggi dal disco.
        with pipeline_activity._lock:
            saved = dict(pipeline_activity._active)
            pipeline_activity._active.clear()
        try:
            active2, _, scope2 = pipeline_activity.snapshot('feat-a')
            assert attempt in active2
            assert scope2 == 'shared-disk'
        finally:
            with pipeline_activity._lock:
                pipeline_activity._active.update(saved)
    assert not (tmp_path / 'database' / 'pipeline' / 'activity' / (attempt + '.json')).exists()
    assert pipeline_activity.snapshot('feat-a')[0] == []


def test_stale_activity_from_dead_pid_is_purged(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_activity, 'DATABASE_DIR', tmp_path / 'database')
    folder = tmp_path / 'database' / 'pipeline' / 'activity'
    folder.mkdir(parents=True)
    attempt = 'attempt-' + 'a' * 32
    (folder / (attempt + '.json')).write_text(json.dumps({
        'attempt_id': attempt, 'project_id': 'legacy', 'feature': 'feat-a',
        'pid': 1_999_999_999, 'started_at': '2026-09-15T10:00:00+00:00',
    }), encoding='utf-8')
    monkeypatch.setattr(pipeline_activity, '_pid_alive', lambda pid: False)
    assert pipeline_activity.snapshot('feat-a')[0] == []
    assert not (folder / (attempt + '.json')).exists()

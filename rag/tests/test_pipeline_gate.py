"""Il gate non confonde assenza di prova, guasti e autorizzazione a eseguire."""
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from core import pipeline_gate as gate
from core.pipeline_store import PipelineStore, PipelineStorageError


def point():
    return dict(id='OP-001', functionality='Accesso', original_question='Chi entra?',
                question='Quali ruoli?', assumption=None, uncovered_scenarios=['S02'],
                reason='unconfirmed_requirement', research=dict(status='not_started',
                new_evidence=[], verification='agent_reported'))


def spec(points=()):
    return '# Spec\n## 4. Punti aperti\n```json\n' + json.dumps({'open_points': list(points)}) + '\n```'


def contract(**kwargs):
    return gate.make_contract('feature-a', 'Canvas', spec(), **kwargs)


def decision(**changes):
    data = dict(decision_id='dec-00000000000000000000000000000001', feature='feature-a',
                point=point(), point_hash=gate.content_hash(point()), status='accepted',
                spec_hash='sha256:' + hashlib.sha256(gate.normalize_text(spec([point()])).encode()).hexdigest(),
                declared_by='Operatore di test',
                recorded_at='2026-09-14T10:00:00+00:00', motivation='Procedere con questa lacuna.',
                declared_origin='ui', observed_metadata={}, active_attempt_ids=[], origin_verified=False)
    data.update(changes)
    return gate.PointDecision.model_validate(data)


def checks(structural='pass', semantic='pass'):
    return gate.ValidationChecks(structural=gate.Check(status=structural), semantic=gate.Check(status=semantic))


def passed(c=None, sources=None):
    c = c or contract()
    started = gate.new_validation(c)
    return gate.finish_validation(started, c, checks(), sources=sources or gate.ValidationSources(),
                                  validator=gate.ValidatorEvidence(model='simulated', raw_response='{}'))


def codes(result):
    return {reason.code for reason in result.reasons}


def test_minimal_normalization_preserves_meaningful_whitespace():
    assert gate.normalize_text(b'\xef\xbb\xbfA\r\nB\r\n\n') == 'A\nB\n'
    assert gate.normalize_text('A\rB') == 'A\nB\n'
    assert gate.normalize_text(' A \t') == ' A \t\n'
    assert gate.normalize_text('\ufeff\ufeffA') == '\ufeffA\n'
    with pytest.raises(UnicodeDecodeError):
        gate.normalize_text(b'\xff')
    a = gate.make_contract('feature-a', 'Canvas\r\n', spec() + '\n')
    b = gate.make_contract('feature-a', b'\xef\xbb\xbfCanvas', spec())
    assert a.hash == b.hash
    assert a.hash != gate.make_contract('feature-a', 'Canvas ', spec()).hash
    assert a.canvas.hash == 'sha256:' + hashlib.sha256(b'Canvas\n').hexdigest()


def test_contract_hash_is_canonical_and_includes_decision_content():
    first = decision()
    reordered = gate.PointDecision.model_validate(dict(reversed(list(first.model_dump().items()))))
    a = gate.make_contract('feature-a', 'Canvas', spec([point()]), [first])
    b = gate.make_contract('feature-a', 'Canvas', spec([point()]), [reordered])
    assert a.hash == b.hash
    changed = decision(motivation='Motivazione diversa.')
    assert a.hash != gate.make_contract('feature-a', 'Canvas', spec([point()]), [changed]).hash
    assert a.hash != gate.make_contract('feature-a', 'Canvas', spec([point()])).hash


@pytest.mark.parametrize('status', ['accepted', 'resolved'])
def test_explicit_decision_allows_but_never_transfers_to_changed_point(status):
    d = decision(status=status)
    c = gate.make_contract('feature-a', 'Canvas', spec([point()]), [d])
    assert gate.evaluate_gate(c, passed(c), gate.SourceState()).allowed
    changed = {**point(), 'question': 'Quali ruoli amministrativi?'}
    other = gate.make_contract('feature-a', 'Canvas', spec([changed]), [d])
    result = gate.evaluate_gate(other, passed(c), gate.SourceState())
    assert not result.allowed
    assert 'open_points_unaddressed' in codes(result)
    assert other.decisions == []


def test_latest_matching_decision_is_frozen_and_other_features_are_excluded():
    first = decision()
    last = decision(decision_id='dec-00000000000000000000000000000002',
                    recorded_at='2026-09-14T11:00:00+00:00', status='resolved')
    foreign = decision(feature='feature-b', recorded_at='2026-09-14T12:00:00+00:00')
    c = gate.make_contract('feature-a', 'Canvas', spec([point()]), [last, foreign, first])
    assert [d.decision_id for d in c.decisions] == [last.decision_id]


def test_unaddressed_blocks_even_when_no_uncovered_scenarios_are_listed():
    c = gate.make_contract('feature-a', 'Canvas', spec([{**point(), 'uncovered_scenarios': []}]))
    result = gate.evaluate_gate(c, passed(c), gate.SourceState())
    assert not result.allowed
    assert 'open_points_unaddressed' in codes(result)


@pytest.mark.parametrize('value', [True, 1, 0, 'false', None])
def test_decision_origin_cannot_be_promoted_or_coerced(value):
    with pytest.raises(ValidationError):
        decision(origin_verified=value)


def test_decision_requires_motivation_and_integral_point_fingerprint():
    with pytest.raises(ValidationError):
        decision(motivation=' ')
    with pytest.raises(ValidationError):
        decision(point_hash='sha256:' + '0' * 64)


@pytest.mark.parametrize('body,status', [('Spec senza resoconto', 'missing'),
    ('## 4. Punti aperti\n```json\n{"open_points":[]\n```', 'invalid')])
def test_missing_and_malformed_reports_are_separate_blockers(body, status):
    c = gate.make_contract('feature-a', 'Canvas', body)
    result = gate.evaluate_gate(c, None, gate.SourceState())
    assert result.open_points_status == status
    assert 'open_points_' + status in codes(result)
    assert not result.allowed
    if status == 'invalid':
        assert 'riga' in next(r.message for r in result.reasons if r.code == 'open_points_invalid')


def test_real_truncated_json_is_blocked_without_repair():
    raw = (Path(__file__).resolve().parents[1] / 'eval/results/propose_adopted_v3_20260914'
           / 'evidence/responses/la2_current_r2.md').read_text(encoding='utf-8')
    c = gate.make_contract('feature-a', 'Canvas', raw)
    result = gate.evaluate_gate(c, None, gate.SourceState())
    assert result.open_points_status == 'invalid'
    assert 'open_points_invalid' in codes(result)
    assert c.spec.text == gate.normalize_text(raw)


def test_mismatch_names_documents_and_validation_and_decisions():
    old = contract()
    validation = passed(old)
    current = gate.make_contract('feature-a', 'Canvas modificato', spec() + '\nTesto diverso')
    result = gate.evaluate_gate(current, validation, gate.SourceState())
    reason = next(r for r in result.reasons if r.code == 'contract_changed')
    assert reason.changed == ['canvas', 'spec']
    assert validation.validation_id in reason.message
    assert ' UTC.' in reason.message
    assert 'Il Canvas e la Spec sono stati modificati' in reason.message
    assert reason.http_status == 409 and reason.action == 'user_action'
    assert 'Valida' in reason.next_step
    c = gate.make_contract('feature-a', 'Canvas', spec([point()]), [decision()])
    other = gate.make_contract('feature-a', 'Canvas', spec([point()]), [decision(motivation='Rischio accettato.')])
    reason = next(r for r in gate.evaluate_gate(other, passed(c), gate.SourceState()).reasons
                  if r.code == 'contract_changed')
    assert reason.changed == ['decisions']
    assert 'Le decisioni registrate sono state modificate' in reason.message
    assert 'Il Canvas e la Spec sono invariati.' in reason.message


@pytest.mark.parametrize('canvas,spec_text,sentence', [
    ('Altro Canvas', None, 'Il Canvas è stato modificato'),
    (None, 'Spec diversa', 'La Spec è stata modificata'),
    ('Altro Canvas', 'Spec diversa', 'Il Canvas e la Spec sono stati modificati'),
])
def test_mismatch_is_readable_and_formats_reference_time_in_utc(monkeypatch, canvas, spec_text, sentence):
    monkeypatch.setattr(gate, '_now', lambda: '2026-09-14T18:11:01.839908+02:00')
    old = contract()
    v = passed(old)
    current = gate.make_contract('feature-a', canvas or old.canvas.text, spec_text or old.spec.text)
    reason = next(r for r in gate.evaluate_gate(current, v, gate.SourceState()).reasons
                  if r.code == 'contract_changed')
    assert reason.message.startswith(sentence + ' rispetto alla validazione ' + v.validation_id)
    assert 'del 14/09/2026 16:11 UTC.' in reason.message
    if canvas is None:
        assert 'Il Canvas è invariato.' in reason.message
    if spec_text is None:
        assert 'La Spec è invariata.' in reason.message


def test_stale_and_unavailable_are_not_negative_validations():
    c = contract()
    start = gate.new_validation(c)
    changed = gate.make_contract('feature-a', 'Altro Canvas', spec())
    stale = gate.finish_validation(start, changed, checks())
    assert stale.status == 'stale' and not stale.passed
    unavailable = gate.finish_validation(start, c, checks(semantic='unavailable'))
    assert unavailable.status == 'unavailable' and not unavailable.passed
    result = gate.evaluate_gate(c, unavailable, gate.SourceState())
    assert result.http_status == 503
    assert next(r for r in result.reasons if r.code == 'validation_unavailable').action == 'retryable'


def test_sources_unavailable_does_not_claim_sources_were_removed():
    c = contract()
    result = gate.evaluate_gate(c, passed(c, sources()), gate.SourceState(), [
        gate.AvailabilityIssue(code='sources_unavailable', message='disk offline', action='operator_action')])
    assert codes(result) == {'sources_unavailable'}
    assert result.http_status == 503 and result.warnings == []


def test_pass_is_derived_from_checks_never_prose_or_claimed_flag():
    c = contract()
    v = gate.finish_validation(gate.new_validation(c), c, checks(semantic='fail'),
        validator=gate.ValidatorEvidence(raw_response='VALIDAZIONE SUPERATA'))
    assert not v.passed and v.status == 'failed'
    result = gate.evaluate_gate(c, v, gate.SourceState())
    assert 'validation_failed' in codes(result)
    tampered = v.model_dump()
    tampered.update(status='passed', passed=True)
    with pytest.raises(ValidationError):
        gate.ValidationRecord.model_validate(tampered)


def sources():
    return gate.ValidationSources(index_version='old', corpus_doc_hashes={'a.md': 'one', 'b.md': 'two'},
        provided=[gate.ProvidedSource(doc_id='a', path='a.md', document_hash='one', chunk_id='a-1',
                    text_supplied='Regola originale', text_hash=gate.content_hash('Regola originale'), truncated=False)])


def test_only_provided_documents_block_other_corpus_changes_warn():
    c = contract()
    v = passed(c, sources())
    state = gate.SourceState(index_version='new', doc_hashes={'a.md': 'one', 'b.md': 'different', 'c.md': 'new'})
    result = gate.evaluate_gate(c, v, state)
    assert result.allowed
    assert result.warnings[0].code == 'unreviewed_corpus_changes'
    assert result.warnings[0].changed == ['b.md', 'c.md']
    for hashes in ({'a.md': 'changed', 'b.md': 'two'}, {'b.md': 'two'}):
        blocked = gate.evaluate_gate(c, v, gate.SourceState(doc_hashes=hashes))
        assert not blocked.allowed
        assert next(r for r in blocked.reasons if r.code == 'provided_sources_changed').changed == ['a.md']


def test_no_expiry_and_new_model_outage_does_not_revoke_passed_record():
    c = contract()
    data = passed(c).model_dump()
    data.update(started_at='2020-01-01T00:00:00+00:00', finished_at='2020-01-01T00:01:00+00:00')
    v = gate.ValidationRecord.model_validate(data)
    outage = gate.AvailabilityIssue(code='validator_unavailable', message='Modello offline', action='retryable')
    assert gate.evaluate_gate(c, v, gate.SourceState(index_version='new'), [outage]).allowed


def test_storage_failure_is_operator_action_and_has_precedence_over_409():
    issue = gate.AvailabilityIssue(code='storage_unavailable', message='Disco pieno', action='operator_action')
    result = gate.evaluate_gate(contract(), None, gate.SourceState(), [issue])
    assert result.http_status == 503 and not result.allowed
    reason = next(r for r in result.reasons if r.code == 'storage_unavailable')
    assert reason.action == 'operator_action'
    assert 'storage' in reason.next_step
    assert 'Spec' not in reason.next_step


def test_empty_contract_and_foreign_validation_are_rejected():
    empty = gate.make_contract('feature-a', '', '')
    assert {'canvas_missing', 'spec_missing'} <= codes(gate.evaluate_gate(empty, None, gate.SourceState()))
    foreign = gate.make_contract('feature-b', 'Canvas', spec())
    assert 'validation_feature_mismatch' in codes(gate.evaluate_gate(contract(), passed(foreign), gate.SourceState()))


def test_store_round_trip_preserves_evidence_and_rejects_corruption(tmp_path):
    store = PipelineStore(tmp_path)
    c = contract()
    v = passed(c, sources())
    store.write_validation(v)
    assert store.read_validation(c.feature, v.validation_id) == v
    assert store.read_validation(c.feature, 'val-' + '0' * 32) is None
    path = tmp_path / 'validations' / c.feature / (v.validation_id + '.json')
    raw = json.loads(path.read_text(encoding='utf-8'))
    raw['contract']['canvas']['text'] = 'Contenuto alterato'
    path.write_text(json.dumps(raw), encoding='utf-8')
    with pytest.raises(PipelineStorageError):
        store.read_validation(c.feature, v.validation_id)


def test_atomic_failure_preserves_old_record_and_surfaces_storage_error(tmp_path, monkeypatch):
    from core import artifacts
    store = PipelineStore(tmp_path)
    start = gate.new_validation(contract())
    store.write_validation(start)
    def fail_replace(*args):
        raise OSError('disk failure')
    monkeypatch.setattr(artifacts.os, 'replace', fail_replace)
    with pytest.raises(PipelineStorageError):
        store.write_validation(gate.finish_validation(start, contract(), checks()))
    assert store.read_validation(start.feature, start.validation_id).status == 'running'
    assert not list(tmp_path.rglob('*.tmp'))


def test_completed_validation_is_immutable_and_cannot_change_frozen_contract(tmp_path):
    store = PipelineStore(tmp_path)
    start = gate.new_validation(contract())
    store.write_validation(start)
    data = start.model_dump()
    data['contract'] = gate.make_contract('feature-a', 'Altro Canvas', spec()).model_dump()
    with pytest.raises(PipelineStorageError):
        store.write_validation(gate.ValidationRecord.model_validate(data))
    finished = gate.finish_validation(start, contract(), checks())
    store.write_validation(finished)
    store.write_validation(finished)  # retry identico, nessuna mutazione
    with pytest.raises(PipelineStorageError):
        store.write_validation(start)
    assert store.read_validation(start.feature, start.validation_id) == finished


def test_store_reports_busy_lock_without_overwriting(tmp_path):
    from core.writer_lock import writer_lock
    store = PipelineStore(tmp_path)
    record = passed()
    lock = tmp_path / 'validations' / record.feature / '.writer.lock'
    with writer_lock(lock_path=lock):
        with pytest.raises(PipelineStorageError) as exc:
            store.write_validation(record)
    assert exc.value.action == 'retryable'
    assert store.read_validation(record.feature, record.validation_id) is None


@pytest.mark.parametrize('feature,identifier', [('../outside', 'val-' + '0' * 32),
    ('feature-a', '../outside'), ('feature-a', 'val-../../outside')])
def test_store_cannot_escape_root(tmp_path, feature, identifier):
    with pytest.raises(ValueError):
        PipelineStore(tmp_path).read_validation(feature, identifier)

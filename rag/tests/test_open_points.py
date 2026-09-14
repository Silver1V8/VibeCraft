"""Il silenzio del modello non certifica l'assenza di punti aperti."""
import json

import pytest

from core.open_points import read_report


def report(points):
    return '## Punti aperti\n```json\n' + json.dumps({'open_points': points}) + '\n```'


def point():
    return dict(id='OP-001', functionality='Accesso', original_question='Chi può accedere?',
                question='Quali ruoli sono ammessi?', assumption=None, uncovered_scenarios=['Accesso negato'],
                reason='no_new_evidence', research=dict(status='closed', new_evidence=[], verification='agent_reported'))


@pytest.mark.parametrize('value,status', [('', 'missing'), ('Spec senza resoconto', 'missing'),
    ('{}', 'missing'), ('{"open_points":null}', 'invalid'), (report([]), 'valid'),
    ('{"open_points":null,"open_points":[]}', 'invalid'), ('[]', 'invalid'),
    ('## Punti aperti\n```json\n{rotto}\n```', 'invalid'),
    ('## Punti aperti\n```json\nnull\n```', 'invalid'),
    ('## Punti aperti\nNessuno.', 'invalid')])
def test_report_states(value, status):
    result = read_report(value)
    assert result['open_points_status'] == status
    if status == 'missing':
        assert 'open_points' not in result
    elif status == 'invalid':
        assert result['open_points'] is None and result['open_points_error']
    else:
        assert result['open_points'] == []
    assert result['research_policy']['enforcement'] == 'advisory'
    assert result['research_policy']['id_reuse_verified'] is False


def test_original_question_is_inspectable_but_semantics_not_certified():
    first = point()
    second = dict(first, id='OP-002', original_question='Quali utenti possono accedere?')
    result = read_report(report([first, second]))
    assert result['open_points_status'] == 'valid'  # Nessun falso controllo anti-parafrasi.
    assert result['open_points'] == [first, second]
    assert result['research_policy']['original_question_verified'] is False


@pytest.mark.parametrize('change', ['duplicate', 'original_missing', 'new_evidence', 'not_closed'])
def test_structurally_invalid_report(change):
    item = point()
    items = [item]
    if change == 'duplicate':
        items.append(item)
    elif change == 'original_missing':
        del item['original_question']
    elif change == 'new_evidence':
        item['research']['new_evidence'] = ['doc:1']
    else:
        item['research']['status'] = 'not_started'
    assert read_report(report(items))['open_points_status'] == 'invalid'


def test_ambiguous_or_nested_report_cannot_become_success():
    assert read_report(report([]) + '\n' + report([]))['open_points_status'] == 'invalid'
    assert read_report('```markdown\n' + report([]) + '\n```')['open_points_status'] != 'valid'
    assert read_report(report([]) + '\nAltro testo')['open_points_status'] == 'invalid'


def test_spec_normalization_preserves_report_and_scenarios():
    from core.spec_format import normalize_spec
    scenario = '```gherkin\nSCENARIO: S01 - Accesso\n  GIVEN un utente\n  WHEN accede\n  THEN entra\n```'
    normalized = normalize_spec(scenario + '\n\n' + report([point()]))
    assert scenario in normalized
    assert read_report(normalized)['open_points'] == [point()]

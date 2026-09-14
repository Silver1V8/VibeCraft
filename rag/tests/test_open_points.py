"""Il silenzio del modello non certifica l'assenza di punti aperti."""
import json
from pathlib import Path

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


@pytest.mark.parametrize('heading', [
    '## Punti aperti', '## 4. Punti aperti', '## 4 Punti aperti',
    '## 4) Punti aperti', '## (4) Punti aperti', '## 4.2. Punti aperti',
    '  ##\t12.3)\tPUNTI   APERTI  ', '## punti aperti',
])
def test_report_heading_numbering_and_spacing(heading):
    result = read_report(report([point()]).replace('## Punti aperti', heading))
    assert result['open_points_status'] == 'valid'
    assert result['open_points'] == [point()]


@pytest.mark.parametrize('heading', [
    '# Punti aperti', '### Punti aperti', '## Altri punti aperti',
    '## Punti aperti risolti', '## 4. Questioni aperte', '## 4Punti aperti',
    '## Punti aperti: dettagli', '##4. Punti aperti',
])
def test_other_headings_are_not_reports(heading):
    assert read_report(report([]).replace('## Punti aperti', heading))['open_points_status'] == 'missing'


def test_numbered_reports_remain_unambiguous_and_outside_fences():
    numbered = report([]).replace('## Punti aperti', '## 4. Punti aperti')
    assert read_report(report([]) + '\n' + numbered)['open_points_status'] == 'invalid'
    assert read_report('````markdown\n' + numbered + '\n````')['open_points_status'] == 'missing'


@pytest.mark.parametrize('sample,status', [
    ('fe3_current_r1', 'valid'), ('fe3_current_r2', 'valid'), ('fe3_current_r3', 'valid'),
    ('la2_current_r1', 'valid'), ('la2_current_r2', 'invalid'), ('la2_current_r3', 'valid'),
])
def test_real_propose_samples_without_json_repair(sample, status):
    # Fixture originali già tracciate: nessuna copia corretta né rigenerazione.
    path = (Path(__file__).resolve().parents[1] / 'eval/results'
            / 'propose_adopted_v3_20260914/evidence/responses' / f'{sample}.md')
    raw = path.read_text(encoding='utf-8')
    result = read_report(raw)
    assert result['open_points_status'] == status
    if status == 'valid':
        assert len(result['open_points']) == 1
        assert result['open_points'][0]['id'] == 'OP-001'
    else:
        assert result['open_points'] is None
        assert 'JSON' in result['open_points_error']
        assert 'riga 1' in result['open_points_error']
        assert 'colonna 447' in result['open_points_error']

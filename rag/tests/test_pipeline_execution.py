"""Ammissione HTTP: contratto congelato, errori espliciti ed eventi persistiti."""
import json

import pytest

from api import routes_pipeline as routes
from core import pipeline_gate as gate
from core.pipeline_store import PipelineStorageError
from test_pipeline_validation import env as validation_env, accept


@pytest.fixture
def env(tmp_path, monkeypatch):
    return validation_env.__wrapped__(tmp_path, monkeypatch)


def validated(client):
    state = client.get('/api/pipeline/gate', params={'feature': 'demo'}).json()
    assert accept(client, state, [f['finding_hash'] for f in state['structural_findings']]).status_code == 200
    result = client.post('/api/pipeline/validate', json={'feature': 'demo'})
    assert result.status_code == 200 and result.json()['passed']
    return result.json()['validation_id']


def runner(monkeypatch):
    calls = []
    def start(runner_id, prompt, mode, model, **kwargs):
        calls.append((prompt, mode, kwargs))
        if kwargs.get('on_finish'):
            kwargs['on_finish']({'type': 'result', 'is_error': False, 'open_points_status': 'valid'})
        return iter(['{"type":"result","is_error":false}\n'])
    monkeypatch.setattr(routes, 'run_streaming', start)
    return calls


def test_external_cli_runners_cannot_start_agentic(env, monkeypatch):
    _, _, client = env
    calls = runner(monkeypatch)
    vid = validated(client)
    for bad in (dict(runner='codex'), dict(runner='cursor'), dict(runner='local', model='--force')):
        r = client.post('/api/pipeline/agent/run', json=dict(feature='demo', validation_id=vid, mode='agentic', **bad))
        assert r.status_code in (400, 422) and not calls


def test_modified_contract_blocks_then_revalidation_admits_frozen_text(env, monkeypatch):
    folder, store, client = env
    calls = runner(monkeypatch)
    vid = validated(client)
    (folder / 'canvas.md').write_text((folder / 'canvas.md').read_text() + '\nNuovo vincolo', encoding='utf-8')
    payload = dict(feature='demo', validation_id=vid, mode='agentic', prompt='CLIENT ARBITRARIO')
    blocked = client.post('/api/pipeline/agent/run', json=payload)
    assert blocked.status_code == 409 and not calls
    detail = blocked.json()['detail']
    mismatch = next(r for r in detail['reasons'] if r['code'] == 'contract_changed')
    assert mismatch['changed'] == ['canvas'] and vid in mismatch['message']
    assert mismatch['action'] == 'user_action' and mismatch['next_step']
    vid2 = client.post('/api/pipeline/validate', json={'feature': 'demo'}).json()['validation_id']
    payload.update(validation_id=vid2, retry_of_attempt_id=detail['attempt_id'])
    admitted = client.post('/api/pipeline/agent/run', json=payload)
    assert admitted.status_code == 200
    assert 'CLIENT ARBITRARIO' not in calls[0][0] and 'Nuovo vincolo' in calls[0][0]
    assert store.read_validation('demo', vid2).contract.spec.text in calls[0][0]
    events = store.read_events()
    assert {'validation_finished', 'open_point_decision_recorded', 'execution_blocked',
            'execution_started', 'execution_finished'} <= {e['event'] for e in events}
    started = next(e for e in events if e['event'] == 'execution_started')
    assert started['retry_of_attempt_id'] == detail['attempt_id']
    assert next(e for e in events if e['event'] == 'execution_finished')['attempt_id'] == started['attempt_id']


def test_client_cannot_authorize_and_no_reference_blocks(env, monkeypatch):
    calls = runner(monkeypatch)
    client = env[2]
    assert client.post('/api/pipeline/agent/run', json={'feature':'demo', 'mode':'agentic', 'allowed':True}).status_code == 422
    assert client.post('/api/pipeline/agent/run', json={'feature':'demo', 'mode':'agentic', 'prompt':'implement'}).status_code == 409
    assert not calls


@pytest.mark.parametrize('mode', ['suggest', 'oneshot'])
def test_advisory_modes_remain_available_with_gate_reasons(env, monkeypatch, mode):
    calls = runner(monkeypatch)
    response = env[2].post('/api/pipeline/agent/run', json={'feature':'demo', 'mode':mode, 'prompt':'Analizza'})
    assert response.status_code == 200 and calls
    prelude = json.loads(response.text.splitlines()[0])
    assert prelude['type'] == 'gate' and not prelude['gate']['allowed']
    assert prelude['gate']['reasons']


def test_unrecordable_admission_returns_503_and_never_starts(env, monkeypatch):
    _, store, client = env
    calls = runner(monkeypatch)
    vid = validated(client)
    def fail(*a, **kw):
        raise PipelineStorageError('events disk full')
    monkeypatch.setattr(store, 'append_event', fail)
    response = client.post('/api/pipeline/agent/run', json={'feature':'demo', 'mode':'agentic', 'validation_id':vid})
    assert response.status_code == 503 and not calls
    assert any(r['action'] == 'operator_action' for r in response.json()['detail']['reasons'])


def test_infrastructure_503_preserves_simultaneous_mismatch(env, monkeypatch):
    folder, _, client = env
    calls = runner(monkeypatch)
    vid = validated(client)
    (folder / 'canvas.md').write_text('Cambiato', encoding='utf-8')
    def fail():
        raise OSError('sources offline')
    monkeypatch.setattr(routes, '_validation_source_state', fail)
    response = client.post('/api/pipeline/agent/run', json={'feature':'demo', 'mode':'agentic', 'validation_id':vid})
    assert response.status_code == 503 and not calls
    codes = {r['code'] for r in response.json()['detail']['reasons']}
    assert {'contract_changed', 'sources_unavailable'} <= codes


def test_comparison_uses_preserved_validation_not_current_files(env):
    folder, store, client = env
    assert client.get('/api/pipeline/gate', params={'feature':'demo'}).json()['comparison'] is None
    vid = validated(client)
    frozen = store.read_validation('demo', vid).contract.canvas.text
    (folder / 'canvas.md').write_text('Modifica corrente', encoding='utf-8')
    data = client.get('/api/pipeline/gate', params={'feature':'demo', 'validation_id':vid}).json()['comparison']
    assert data['canvas']['validated'] == frozen
    assert data['canvas']['current'] == gate.normalize_text('Modifica corrente')


def test_feature_lock_serializes_save_and_admission(env, monkeypatch):
    _, store, client = env
    calls = runner(monkeypatch)
    vid = validated(client)
    with store.feature_lock('demo'):
        save = client.post('/api/pipeline/file/save', json={'feature':'demo', 'name':'canvas.md', 'content':'race'})
        start = client.post('/api/pipeline/agent/run', json={'feature':'demo', 'mode':'agentic', 'validation_id':vid})
    assert save.status_code == start.status_code == 503 and not calls
    assert start.json()['detail']['reasons'][0]['action'] == 'retryable'


def test_unknown_retry_cannot_fabricate_correction(env, monkeypatch):
    client = env[2]
    calls = runner(monkeypatch)
    vid = validated(client)
    response = client.post('/api/pipeline/agent/run', json={'feature':'demo', 'mode':'agentic', 'validation_id':vid,
        'retry_of_attempt_id':'attempt-' + '0'*32})
    assert response.status_code == 409 and not calls
    assert any(r['code'] == 'retry_reference_invalid' for r in response.json()['detail']['reasons'])


@pytest.mark.parametrize('mode', ['suggest', 'oneshot'])
def test_advisory_mode_does_not_require_admission_lock(env, monkeypatch, mode):
    calls = runner(monkeypatch)
    with env[1].feature_lock('demo'):
        response = env[2].post('/api/pipeline/agent/run', json={'feature':'demo','mode':mode,'prompt':'Analizza'})
    assert response.status_code == 200 and calls


def test_corrupt_event_journal_blocks_agentic_even_without_retry(env, monkeypatch):
    _, store, client = env
    calls = runner(monkeypatch)
    vid = validated(client)
    with (store.root / 'events.jsonl').open('ab') as f:
        f.write(b'{truncated')
    response = client.post('/api/pipeline/agent/run', json={'feature':'demo','mode':'agentic','validation_id':vid})
    assert response.status_code == 503 and not calls
    assert response.json()['detail']['attempt_recorded'] is False


def test_sdk_finish_is_recorded_without_http_consumption(monkeypatch):
    import threading
    import agent_bridge
    from core import pipeline_activity
    done = threading.Event()
    outcomes = []
    async def query(**kwargs):
        assert pipeline_activity.snapshot('demo')[0] == ['attempt-test']
        raise RuntimeError('provider offline')
        yield
    def finish(outcome):
        outcomes.append(outcome)
        done.set()
    monkeypatch.setattr(agent_bridge, 'query', query)
    monkeypatch.setattr(agent_bridge, '_build_agent_options', lambda *a: None)
    stream = agent_bridge.run_agent_streaming('test', 'agentic', feature='demo',
                                             attempt_id='attempt-test', on_finish=finish)
    assert done.wait(3), 'La registrazione dipende ancora dalla lettura HTTP'
    assert outcomes[0]['type'] == 'error'
    stream.close()


def test_failed_retry_lookup_never_persists_claimed_link(env, monkeypatch):
    _, store, client = env
    calls = runner(monkeypatch)
    vid = validated(client)
    def fail(*a):
        raise PipelineStorageError('lookup offline')
    monkeypatch.setattr(store, 'retry_exists', fail)
    response = client.post('/api/pipeline/agent/run', json={'feature':'demo','mode':'agentic',
        'validation_id':vid,'retry_of_attempt_id':'attempt-' + '0'*32})
    assert response.status_code == 503 and not calls
    assert response.json()['detail']['retry_of_attempt_id'] is None
    assert store.read_events()[-1]['retry_of_attempt_id'] is None


def test_retry_reference_must_be_blocked_and_same_feature(env):
    store = env[1]
    store.append_event('execution_started', feature='demo', attempt_id='started')
    store.append_event('execution_blocked', feature='other', attempt_id='blocked')
    assert not store.retry_exists('demo', 'started')
    assert not store.retry_exists('demo', 'blocked')
    assert store.retry_exists('other', 'blocked')

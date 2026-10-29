"""Validazione reale con I/O isolato; solo provider e ricerca remoti simulati."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import networkx as nx
import pytest
from api import deps

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import routes_pipeline as routes
from core import pipeline, pipeline_gate as gate, pipeline_validation as validation, retrieval
from core.pipeline_store import PipelineStore

pytestmark = pytest.mark.usefixtures("legacy_workflow_project")

CANVAS = '\n'.join('## ' + s for s in pipeline.CANVAS_SECTIONS)
SCENARIO = ('```gherkin\nSCENARIO: S01 - Invio richiesta\n  GIVEN una richiesta pronta\n'
            '  WHEN viene inviata\n  THEN viene registrata\n```\n')
POINT = dict(id='OP-001', functionality='Invio', original_question='Quale errore?',
             question='Quale errore?', assumption=None, uncovered_scenarios=['Caso negativo'],
             reason='missing_coverage', research=dict(status='not_started', new_evidence=[], verification='agent_reported'))


def spec(points=()):
    return SCENARIO + '## 4. Punti aperti\n```json\n' + json.dumps({'open_points': list(points)}) + '\n```'


def semantic(findings=(), suggestions=()):
    return json.dumps(dict(summary='Controllo concluso.', findings=list(findings), suggestions=list(suggestions)))


def test_suggestions_are_persisted_but_never_cover_findings(env, monkeypatch):
    folder, store, client = env
    (folder / 'spec.md').write_text(spec().replace('## 4. Punti aperti',
        SCENARIO.replace('S01', 'S02').replace('Invio richiesta', 'Errore richiesta') + '## 4. Punti aperti'), encoding='utf-8')
    advice = ['Usare test parametrizzati per verificare i requisiti obbligatori.']
    raw = semantic(suggestions=advice)
    async def generate(*a, **kw):
        return raw
    monkeypatch.setattr(routes.llm, 'agenerate', generate)
    out = client.post('/api/pipeline/validate', json={'feature': 'demo'}).json()
    assert out['status'] == 'passed' and out['gate']['allowed']
    assert out['suggestions'] == advice and out['semantic_findings'] == []
    saved = store.read_validation('demo', out['validation_id'])
    assert saved.suggestions == advice and saved.validator.raw_response == raw
    raw = semantic([dict(kind='coverage', message='Manca un caso richiesto.', contract_quote=None,
        source_doc_id=None, source_quote=None, open_point_hash=None)], advice)
    out = client.post('/api/pipeline/validate', json={'feature': 'demo'}).json()
    assert out['status'] == 'failed' and not out['gate']['allowed']
    assert out['suggestions'] == advice and out['semantic_findings'][0]['blocking']


@pytest.mark.parametrize('suggestions', [None, 'Consiglio', [''], [{'message': 'Consiglio'}]])
def test_suggestions_must_be_an_explicit_list_of_nonempty_text(env, monkeypatch, suggestions):
    async def generate(*a, **kw):
        return json.dumps(dict(summary='Sintesi', findings=[], suggestions=suggestions))
    monkeypatch.setattr(routes.llm, 'agenerate', generate)
    response = env[2].post('/api/pipeline/validate', json={'feature': 'demo'})
    assert response.status_code == 503 and response.json()['status'] == 'unavailable'


def test_recommendation_in_findings_is_not_moved_or_approved(env, monkeypatch):
    raw = semantic([dict(kind='recommendation', message='Consiglio', contract_quote=None,
        source_doc_id=None, source_quote=None, open_point_hash=None)])
    async def generate(*a, **kw):
        return raw
    monkeypatch.setattr(routes.llm, 'agenerate', generate)
    response = env[2].post('/api/pipeline/validate', json={'feature': 'demo'})
    out = response.json()
    assert response.status_code == 503 and out['status'] == 'unavailable'
    assert out['suggestions'] is None
    assert env[1].read_validation('demo', out['validation_id']).validator.raw_response == raw


def test_original_records_are_readable_unchanged_but_old_reports_are_nonconforming():
    folder = Path(__file__).parents[1] / 'eval/results/gate_end_to_end_20260914/evidence/validations'
    paths = list(folder.glob('*.json'))
    assert len(paths) == 3
    for path in paths:
        original = path.read_bytes()
        record = gate.ValidationRecord.model_validate_json(original)
        with pytest.raises(ValueError):
            validation.read_semantic(record.validator.raw_response, record.contract, record.sources)
        assert path.read_bytes() == original


@pytest.fixture
def env(tmp_path, monkeypatch):
    folder = tmp_path / 'changes' / 'demo'
    folder.mkdir(parents=True)
    (folder / 'canvas.md').write_text(CANVAS, encoding='utf-8')
    (folder / 'spec.md').write_text(spec([POINT]), encoding='utf-8')
    monkeypatch.setattr(routes, 'CHANGES_DIR', folder.parent)
    monkeypatch.setattr(pipeline, 'CHANGES_DIR', folder.parent)
    store = PipelineStore(tmp_path / 'database' / 'pipeline')
    monkeypatch.setattr(routes, 'project_store', lambda project, **kwargs: store)
    graph = nx.DiGraph()
    graph.add_node('rule.md', type='document', classification='normative')
    snap = SimpleNamespace(graph=graph, chunks={'chunk': {'text': 'Regola intera', 'doc_id': 'rule.md'}},
                           colbert_store={}, collection_name='test-collection', version='v-test')
    monkeypatch.setattr(routes, 'current_snapshot', lambda project=None, **kwargs: snap)
    monkeypatch.setitem(deps.state, 'qdrant', object())
    monkeypatch.setitem(deps.state, 'embed_model', object())
    monkeypatch.setattr(routes, '_validation_manifest', lambda snap, **kwargs: {'rule.md': 'hash-rule'})
    monkeypatch.setattr(routes, '_validation_source_state', lambda**kwargs: gate.SourceState(
        index_version='v-test', doc_hashes={'rule.md': 'hash-rule'}))
    monkeypatch.setattr(retrieval, 'hybrid_search', lambda *a, **kw: [dict(doc_id='rule.md', chunk_id='chunk', section='Regola')])
    monkeypatch.setattr(routes.llm, 'resolve', lambda purpose: ('test', 'test-model'))
    async def generate(prompt, **kw):
        return semantic()
    monkeypatch.setattr(routes.llm, 'agenerate', generate)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[deps.require_api_key] = lambda: None
    app.dependency_overrides[deps.require_api_key_strict] = lambda: None
    client = TestClient(app)
    return folder, store, client


def accept(client, state, hashes=(), **updates):
    p = state['point_decisions'][0]
    data = dict(feature='demo', point_hash=p['point_hash'], spec_hash=state['spec_hash'],
                status='accepted', motivation='Lacuna esaminata, procedere.', declared_by='Operatore prova',
                declared_origin='ui', coverage_finding_hashes=list(hashes))
    data.update(updates)
    return client.post('/api/pipeline/open-points/decision', json=data)


def test_unassociated_finding_blocks_and_association_is_explicit_visible(env):
    folder, store, client = env
    state = client.get('/api/pipeline/gate', params={'feature': 'demo'}).json()
    result = accept(client, state)
    assert result.status_code == 200
    unexamined = client.post('/api/pipeline/validate', json={'feature': 'demo'}).json()
    assert unexamined['status'] == 'failed'
    assert unexamined['structural_findings'][0]['covered_by'] is None
    assert unexamined['structural_findings'][0]['review_status'] == 'unexamined'
    assert accept(client, state, [state['structural_findings'][0]['finding_hash']]).status_code == 200
    out = client.post('/api/pipeline/validate', json={'feature': 'demo'}).json()
    assert out['passed'] is True
    assert out['gate']['allowed'] is True and out['execution_enforced'] is True
    finding = out['structural_findings'][0]
    assert finding['rule'] == 'scenari_insufficienti'
    assert finding['review_status'] == 'covered'
    assert finding['covered_by']['declared_by'] == 'Operatore prova'
    assert finding['covered_by']['origin_verified'] is False
    assert out['point_decisions'][0]['status'] == 'accepted'
    persisted = store.read_validation('demo', out['validation_id'])
    assert persisted.sources.provided[0].doc_id == 'rule.md'
    assert 'Regola intera' in persisted.sources.provided[0].text_supplied
    assert persisted.validator.raw_response == semantic()
    assert persisted.structural_findings == out['structural_findings']
    assert persisted.contract.decisions[0].coverage_findings


def test_spec_change_expires_decision_and_association_even_if_point_unchanged(env):
    folder, store, client = env
    state = client.get('/api/pipeline/gate', params={'feature': 'demo'}).json()
    saved = accept(client, state, [state['structural_findings'][0]['finding_hash']]).json()
    assert saved['decision']['origin_verified'] is False
    (folder / 'spec.md').write_text(spec([POINT]) + '\n', encoding='utf-8')
    assert client.get('/api/pipeline/gate', params={'feature': 'demo'}).json()['point_decisions'][0]['status'] == 'accepted'
    (folder / 'spec.md').write_text('# Cambio sostanziale\n' + spec([POINT]), encoding='utf-8')
    current = client.get('/api/pipeline/gate', params={'feature': 'demo'}).json()
    assert current['point_decisions'][0]['status'] == 'unaddressed'
    assert current['structural_findings'][0]['covered_by'] is None
    assert accept(client, state).status_code == 409


@pytest.mark.parametrize('extra', [{'origin_verified': True}, {'recorded_at': 'fake'}, {'active_attempt_ids': ['fake']}])
def test_client_cannot_supply_server_evidence(env, extra):
    client = env[2]
    state = client.get('/api/pipeline/gate', params={'feature': 'demo'}).json()
    assert accept(client, state, **extra).status_code == 422


def test_resolved_cannot_cover_finding_and_unknown_association_is_rejected(env):
    client = env[2]
    state = client.get('/api/pipeline/gate', params={'feature': 'demo'}).json()
    h = state['structural_findings'][0]['finding_hash']
    assert accept(client, state, [h], status='resolved').status_code == 422
    assert accept(client, state, ['sha256:' + '0' * 64]).status_code == 409


def test_given_when_then_violation_cannot_be_covered(env):
    folder, _, client = env
    (folder / 'spec.md').write_text(spec([POINT]).replace('  WHEN viene inviata\n', ''), encoding='utf-8')
    state = client.get('/api/pipeline/gate', params={'feature': 'demo'}).json()
    when = next(f for f in state['structural_findings'] if f['rule'] == 'when_mancante')
    assert accept(client, state, [when['finding_hash']]).status_code == 409


@pytest.mark.parametrize('raw', ['VALIDAZIONE SUPERATA', '{}', '{"summary":"ok","findings":[]',
    '{"summary":"ok","findings":[],"passed":true}', '{"summary":"ok","findings":null}'])
def test_malformed_semantic_response_never_passes(env, monkeypatch, raw):
    async def generate(*a, **kw):
        return raw
    monkeypatch.setattr(routes.llm, 'agenerate', generate)
    response = env[2].post('/api/pipeline/validate', json={'feature': 'demo'})
    out = response.json()
    assert response.status_code == 503
    assert out['status'] == 'unavailable' and not out['passed']
    assert not out['validation_available']
    assert env[1].read_validation('demo', out['validation_id']).validator.raw_response == raw


def test_failed_retrieval_is_unavailable_and_does_not_call_model(env, monkeypatch):
    def fail(*a, **kw):
        raise RuntimeError('qdrant offline')
    async def forbidden(*a, **kw):
        pytest.fail('Modello chiamato dopo retrieval fallito')
    monkeypatch.setattr(retrieval, 'hybrid_search', fail)
    monkeypatch.setattr(routes.llm, 'agenerate', forbidden)
    response = env[2].post('/api/pipeline/validate', json={'feature': 'demo'})
    assert response.status_code == 503
    assert response.json()['status'] == 'unavailable'
    assert 'Retrieval non disponibile' in response.json()['validation_error']
    assert 'qdrant offline' not in response.json()['validation_error']


def test_successful_empty_search_is_not_an_outage(env, monkeypatch):
    monkeypatch.setattr(retrieval, 'hybrid_search', lambda *a, **kw: [])
    response = env[2].post('/api/pipeline/validate', json={'feature': 'demo'})
    assert response.status_code == 200
    assert response.json()['validation_available'] is True
    assert env[1].read_validation('demo', response.json()['validation_id']).sources.provided == []


def test_contract_changes_during_model_call_are_stale(env, monkeypatch):
    folder, _, client = env
    async def generate(*a, **kw):
        (folder / 'canvas.md').write_text(CANVAS + '\nRequisito cambiato', encoding='utf-8')
        return semantic()
    monkeypatch.setattr(routes.llm, 'agenerate', generate)
    result = client.post('/api/pipeline/validate', json={'feature': 'demo'}).json()
    assert result['status'] == 'stale' and not result['passed']


def test_operator_decision_during_model_call_is_stale(env, monkeypatch):
    client = env[2]
    state = client.get('/api/pipeline/gate', params={'feature': 'demo'}).json()
    async def generate(*a, **kw):
        assert accept(client, state).status_code == 200
        return semantic()
    monkeypatch.setattr(routes.llm, 'agenerate', generate)
    result = client.post('/api/pipeline/validate', json={'feature': 'demo'}).json()
    assert result['status'] == 'stale'


def test_missing_retrieved_text_is_unavailable_without_model_call(env, monkeypatch):
    routes.current_snapshot().chunks.clear()
    async def forbidden(*a, **kw):
        pytest.fail('Modello chiamato con fonte senza testo')
    monkeypatch.setattr(routes.llm, 'agenerate', forbidden)
    response = env[2].post('/api/pipeline/validate', json={'feature': 'demo'})
    assert response.status_code == 503
    assert 'priva di testo' in response.json()['validation_error']


def test_storage_outage_does_not_invent_missing_documents(env, monkeypatch):
    def unavailable(*a, **kw):
        raise OSError('disk offline')
    monkeypatch.setattr(routes, '_read_gate_contract', unavailable)
    response = env[2].get('/api/pipeline/gate', params={'feature': 'demo'})
    assert response.status_code == 503
    data = response.json()['detail']
    assert data['open_points_status'] is None
    assert [r['code'] for r in data['reasons']] == ['storage_unavailable']
    assert data['reasons'][0]['action'] == 'operator_action'


def test_validate_prompt_keeps_placeholder_shaped_contract_text():
    prompt = pipeline.build_validate_prompt('Canvas {spec_display}', 'Spec {decisions_json}', '', [])
    assert 'Canvas {spec_display}' in prompt and 'Spec {decisions_json}' in prompt


def test_accepted_semantic_gap_stays_visible_and_does_not_become_satisfied(env):
    c = gate.make_contract('demo', CANVAS, spec([POINT]))
    raw = semantic([dict(kind='coverage', message='Manca il caso negativo.', contract_quote=None,
                         source_doc_id=None, source_quote=None, open_point_hash=gate.content_hash(POINT))])
    parsed, check, findings = validation.read_semantic(raw, c, gate.ValidationSources())
    assert check.status == 'fail'
    d = env[1].record_decision(feature='demo', point=POINT, spec_hash=c.spec.hash, status='accepted',
        motivation='Accetto la lacuna', declared_by='Operatore', declared_origin='ui',
        observed_metadata={}, active_attempt_ids=[], coverage_findings=[])
    c = gate.make_contract('demo', CANVAS, spec([POINT]), [d])
    _, check, findings = validation.read_semantic(raw, c, gate.ValidationSources())
    assert check.status == 'pass'
    assert findings[0]['covered_by']['decision_id'] == d.decision_id
    assert findings[0]['scenario_satisfied'] is False


def test_decision_records_observed_activity_not_client_claim(env, monkeypatch):
    from core import pipeline_activity
    client = env[2]
    state = client.get('/api/pipeline/gate', params={'feature': 'demo'}).json()
    with pipeline_activity.track('demo') as attempt:
        with pipeline_activity.track(None) as unscoped:
            result = accept(client, state).json()['decision']
    assert result['active_attempt_ids'] == [attempt]
    assert unscoped in result['observed_metadata']['unscoped_active_attempt_ids']
    assert result['origin_verified'] is False
    assert result['observed_metadata']['activity_scope'] == 'shared-disk'


def test_sdk_activity_is_removed_when_query_fails(monkeypatch):
    import queue
    import agent_bridge
    from core import pipeline_activity
    async def query(**kw):
        assert pipeline_activity.snapshot('demo')[0]
        raise RuntimeError('SDK fallito')
        yield
    monkeypatch.setattr(agent_bridge, 'query', query)
    monkeypatch.setattr(agent_bridge, '_build_agent_options', lambda *a, **kwargs: None)
    asyncio.run(agent_bridge._run_agent('hi', 'agentic', 'test', queue.Queue(), feature='demo'))
    assert pipeline_activity.snapshot('demo')[0] == []

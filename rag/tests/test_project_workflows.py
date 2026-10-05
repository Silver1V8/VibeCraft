"""Real isolated workflow storage and threads; providers are replaced at their boundary."""
import json
import threading
import os
import subprocess
from collections import OrderedDict

import pytest

from api import deps
from core import intake, pipeline, pipeline_gate as gate, project_import, eval_gate
from core.pipeline_store import PipelineStore
from core.projects import ProjectRegistry


@pytest.fixture
def projects(tmp_path, monkeypatch):
    registry = ProjectRegistry(tmp_path / 'projects', bootstrap_legacy=False)
    monkeypatch.setattr(deps, 'project_registry', lambda: registry)
    monkeypatch.setattr(deps, '_project_states', {})
    monkeypatch.setattr(deps, '_snapshots', OrderedDict())
    return registry.create('A'), registry.create('B')


def _commit_git(root, subject):
    subprocess.run(['git', 'add', '.'], cwd=root, check=True, capture_output=True)
    subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                    'commit', '-m', subject], cwd=root, check=True, capture_output=True)


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('has_code', [False, True])
def test_archive_explicit_code_never_collects_foreign_git_or_tasks(projects, tmp_path, monkeypatch, legacy, has_code):
    from dataclasses import replace
    from core import canvas_review, feature_archive
    a, b = projects
    if legacy:
        a = replace(a, id='legacy', legacy=True, root=tmp_path, code_dir=tmp_path/'code',
                    docs_dir=tmp_path/'docs', changes_dir=tmp_path/'changes',
                    database_dir=tmp_path/'database', staging_dir=tmp_path/'staging')
        for path in (a.code_dir, a.docs_dir, a.changes_dir, a.database_dir):
            path.mkdir(exist_ok=True)
    subprocess.run(['git', 'init', str(tmp_path)], check=True, capture_output=True)
    (tmp_path/'seed.txt').write_text('baseline', encoding='utf-8')
    _commit_git(tmp_path, 'baseline')
    (b.code_dir/'backend').mkdir()
    private = b.code_dir/'backend/private.py'
    private.write_text('OTHER_PROJECT_SENTINEL', encoding='utf-8')
    _commit_git(tmp_path, 'same-feature implementation B')
    folder = pipeline.feature_dir('same-feature', project=a)
    (folder/'canvas.md').write_text('## Operations\nA operations', encoding='utf-8')
    (folder/'tasks.md').write_text(os.path.relpath(private, a.root).replace('\\', '/'), encoding='utf-8')
    (a.code_dir/'backend').mkdir()
    pipeline.save_dev_type(folder, 'backend', project=a)
    if has_code:
        (a.code_dir/'backend/own.py').write_text('CAPTURED_A_CODE', encoding='utf-8')
    seen, fallback = [], []
    original = canvas_review.collect_change_diff
    def collect(*args, **kwargs):
        fallback.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(canvas_review, 'collect_change_diff', collect)
    monkeypatch.setattr(canvas_review, '_call_llm_sync', lambda prompt: seen.append(prompt) or '## Fedeltà\nFedeltà: alto')
    feature_archive.archive_feature('same-feature', project=a, reindex=False)
    assert seen and not fallback
    assert 'OTHER_PROJECT_SENTINEL' not in seen[0]
    assert ('CAPTURED_A_CODE' in seen[0]) is has_code
    assert (a.changes_dir/'archive/same-feature/canvas_review.md').exists()


def test_standalone_review_does_not_discover_parent_git(projects, tmp_path):
    from core import canvas_review
    a, b = projects
    subprocess.run(['git', 'init', str(tmp_path)], check=True, capture_output=True)
    (tmp_path/'seed.txt').write_text('baseline', encoding='utf-8')
    _commit_git(tmp_path, 'baseline')
    (b.code_dir/'private.py').write_text('OTHER_PROJECT_SENTINEL', encoding='utf-8')
    _commit_git(tmp_path, 'same-feature implementation B')
    folder = pipeline.feature_dir('same-feature', project=a)
    (a.code_dir/'own.py').write_text('TASK_A_CODE', encoding='utf-8')
    (folder/'tasks.md').write_text('code/own.py', encoding='utf-8')
    diff = canvas_review.collect_change_diff('same-feature', folder, repo_root=a.root)
    assert 'TASK_A_CODE' in diff and 'OTHER_PROJECT_SENTINEL' not in diff


def test_external_prompt_binds_both_transports_to_project(projects):
    a, b = projects
    for project, other in ((a, b), (b, a)):
        prompt = pipeline.build_final_prompt('same-feature', project=project)
        assert f'X-VibeCraft-Project: {project.id}' in prompt
        assert f'VIBECRAFT_PROJECT_ID={project.id}' in prompt
        assert other.id not in prompt
    assert 'X-VibeCraft-Project' not in pipeline.build_final_prompt('same-feature')


def test_explore_provider_failure_preserves_safe_tolerant_history(projects, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import routes_pipeline as routes
    a, _ = projects
    private = f'{a.root} private-provider-key'
    async def broken(*args, **kwargs):
        raise routes.llm.LLMError(private)
    monkeypatch.setattr(routes.llm, 'agenerate', broken)
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        response = client.post('/api/pipeline/explore/turn', headers={'X-VibeCraft-Project': a.id},
                               json={'feature_name': 'same-feature', 'user_input': 'A input', 'history': 'A history'})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['ai_response'].startswith('[ERRORE DI CONNESSIONE]')
        assert 'A history\nUtente: A input\nIA: ' in result['history']
        assert 'private-provider-key' not in response.text and str(a.root) not in result['history']
        async def success(*args, **kwargs):
            return 'A answer'
        monkeypatch.setattr(routes.llm, 'agenerate', success)
        response = client.post('/api/pipeline/explore/turn', headers={'X-VibeCraft-Project': a.id},
                               json={'feature_name': 'same-feature', 'user_input': 'A input', 'history': 'A history'})
        assert response.json() == {'ai_response': 'A answer', 'history': 'A history\nUtente: A input\nIA: A answer'}


def test_missing_staged_markdown_preserves_safe_404(projects, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import routes_intake
    a, _ = projects
    monkeypatch.setattr(deps, 'ROLE', 'writer')
    app = FastAPI()
    app.include_router(routes_intake.router)
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        headers = {'X-VibeCraft-Project': a.id}
        response = client.post('/api/intake/docs', headers=headers,
                               files={'file': ('fixture.md', b'# Test\nTest content', 'text/markdown')})
        assert response.status_code == 200, response.text
        entry = response.json()
        url = f'/api/intake/staged/{entry["id"]}/preview'
        assert client.get(url, headers=headers).json()['markdown'] == '# Test\nTest content'
        markdown = intake.staged_file(intake.staging_paths_readonly(project=a), entry['files']['markdown'])
        assert markdown.is_relative_to(a.staging_dir) and markdown.is_file()
        markdown.unlink()  # Only the derived Markdown just created by this fixture.
        response = client.get(url, headers=headers)
        assert response.status_code == 404, response.text
        assert response.json()['detail'] == 'Documento in staging non disponibile.'
        assert str(a.root) not in response.text.replace('\\\\', '\\')
        assert client.get('/api/intake/staged', headers=headers).json()['staged'][0]['id'] == entry['id']


def _indexed_passing_gate(project):
    from core import artifacts
    from test_project_runtime import indexed
    from api import routes_pipeline as routes
    indexed(project, project.name)
    manifest_path = artifacts.manifest_path('v1', project=project)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['doc_hashes'] = {}
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    folder = pipeline.feature_dir('same-feature', project=project)
    canvas = '\n'.join('## ' + section for section in pipeline.CANVAS_SECTIONS)
    spec = 'GIVEN richiesta WHEN invio THEN successo\n## 4. Punti aperti\n```json\n{"open_points": []}\n```'
    (folder/'canvas.md').write_text(canvas, encoding='utf-8')
    (folder/'spec.md').write_text(spec, encoding='utf-8')
    contract = gate.make_contract('same-feature', canvas, spec)
    passed = gate.finish_validation(gate.new_validation(contract), contract, gate.ValidationChecks(
        structural=gate.Check(status='pass'), semantic=gate.Check(status='pass')),
        sources=gate.ValidationSources(index_version='v1'), validator=gate.ValidatorEvidence(model='simulated', raw_response='{}'))
    routes.project_store(project).write_validation(passed)
    return passed


def test_gate_cold_load_and_eviction_use_healthy_persisted_artifacts(projects, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import routes_pipeline as routes
    a, b = projects
    c = deps.project_registry().create('C')
    records = {project.id: _indexed_passing_gate(project) for project in (a, b, c)}
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        def status(project):
            return client.get('/api/pipeline/gate', headers={'X-VibeCraft-Project': project.id},
                              params={'feature': 'same-feature', 'validation_id': records[project.id].validation_id})
        assert deps.current_snapshot(a) is None
        initial = status(a)
        assert initial.status_code == 200 and initial.json()['gate']['allowed'], initial.text
        persisted = routes.project_store(a)._validation_path('same-feature', records[a.id].validation_id).read_bytes()
        deps.require_snapshot(b)
        deps.require_snapshot(c)
        assert a.id not in deps._snapshots
        assert status(a).json()['gate'] == initial.json()['gate']
        assert routes.project_store(a)._validation_path('same-feature', records[a.id].validation_id).read_bytes() == persisted
        (a.database_dir/'CURRENT').write_text('../unavailable-private-path', encoding='utf-8')
        unavailable = status(a)
        assert unavailable.status_code == 200, unavailable.text
        decision = unavailable.json()['gate']
        assert not decision['allowed'] and decision['http_status'] == 503
        assert any(reason['code'] == 'sources_unavailable' for reason in decision['reasons'])
        assert 'unavailable-private-path' not in unavailable.text and str(a.root) not in unavailable.text
        assert status(b).json()['gate']['allowed']


def test_gate_snapshot_capture_stays_off_event_loop(projects, monkeypatch):
    import asyncio
    import httpx
    from fastapi import FastAPI
    from fastapi.concurrency import run_in_threadpool
    from api import routes_pipeline as routes, routes_intake
    a, b = projects
    passed = _indexed_passing_gate(a)
    original = routes.require_snapshot
    entered, release, loaded = threading.Event(), threading.Event(), threading.Event()
    threads = []
    def held(project):
        threads.append(threading.get_ident())
        entered.set()
        release.wait(2)
        result = original(project)
        loaded.set()
        return result
    monkeypatch.setattr(routes, 'require_snapshot', held)
    app = FastAPI()
    app.include_router(routes.router)
    app.include_router(routes_intake.router)
    async def requests():
        loop_thread = threading.get_ident()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
            pending = asyncio.create_task(client.get('/api/pipeline/gate', headers={'X-VibeCraft-Project': a.id},
                params={'feature': 'same-feature', 'validation_id': passed.validation_id}))
            try:
                assert await run_in_threadpool(entered.wait, 5)
                heartbeat = await client.get('/api/intake/staged', headers={'X-VibeCraft-Project': b.id})
                assert heartbeat.status_code == 200 and heartbeat.json() == {'staged': []}
                assert not loaded.is_set()
            finally:
                release.set()
                result = await pending
            assert result.status_code == 200 and result.json()['gate']['allowed'], result.text
            assert threads and all(thread != loop_thread for thread in threads)
    asyncio.run(requests())


def test_same_feature_storage_and_gate_are_isolated(projects):
    a, b = projects
    for project, text in ((a, 'A spec'), (b, 'B spec')):
        folder = pipeline.feature_dir('same-feature', project=project)
        (folder / 'spec.md').write_text(text, encoding='utf-8')
        (project.code_dir / text[0]).mkdir()
    assert pipeline.list_dev_types(project=a) == ['A']
    assert pipeline.list_dev_types(project=b) == ['B']
    ca = gate.make_contract('same-feature', 'A canvas', 'A spec')
    cb = gate.make_contract('same-feature', 'B canvas', 'B spec')
    started = gate.new_validation(ca)
    passed = gate.finish_validation(started, ca, gate.ValidationChecks(
        structural=gate.Check(status='pass'), semantic=gate.Check(status='pass')),
        sources=gate.ValidationSources(), validator=gate.ValidatorEvidence(model='simulated', raw_response='{}'))
    sa, sb = PipelineStore(project=a), PipelineStore(project=b)
    sa.write_validation(passed)
    assert sa.read_validation('same-feature', passed.validation_id).passed
    assert sb.read_validation('same-feature', passed.validation_id) is None
    assert sb.latest_validation('same-feature', cb.hash) is None
    sa.append_event('execution_blocked', feature='same-feature', attempt_id='a-attempt')
    assert sa.retry_exists('same-feature', 'a-attempt')
    assert not sb.retry_exists('same-feature', 'a-attempt')
    with sa.feature_lock('same-feature'), sb.feature_lock('same-feature'):
        pass


def test_same_open_point_has_independent_operator_decisions(projects):
    from test_pipeline_validation import POINT, spec
    a, b = projects
    contract = gate.make_contract('same-feature', 'Canvas', spec([POINT]))
    sa, sb = PipelineStore(project=a), PipelineStore(project=b)
    for store, status, operator in ((sa, 'accepted', 'operator-A'), (sb, 'resolved', 'operator-B')):
        store.record_decision(feature='same-feature', point=POINT,
            spec_hash=contract.spec.hash, status=status, motivation='Fixture decision',
            declared_by=operator, declared_origin='fixture', observed_metadata={},
            active_attempt_ids=[], coverage_findings=[])
    decisions_a, decisions_b = sa.decisions('same-feature'), sb.decisions('same-feature')
    assert [decision.status for decision in decisions_a] == ['accepted']
    assert [decision.status for decision in decisions_b] == ['resolved']
    ca = gate.make_contract('same-feature', contract.canvas.text, contract.spec.text, decisions_a)
    cb = gate.make_contract('same-feature', contract.canvas.text, contract.spec.text, decisions_b)
    assert ca.hash != cb.hash
    assert ca.decisions[0].declared_by == 'operator-A' and cb.decisions[0].declared_by == 'operator-B'


def test_intake_upload_approve_and_cross_project_id(projects):
    a, b = projects
    staged = intake.stage_document('same.md', b'# A document\nContent A', project=a)
    other = intake.stage_document('same.md', b'# B document\nContent B', project=b)
    assert intake.get_preview(staged['id'], project=a)['markdown'].endswith('Content A')
    with pytest.raises(intake.StagedDocumentNotFoundError):
        intake.get_preview(staged['id'], project=b)
    seen = []
    approved = intake.approve(staged['id'], '04_knowledge_informative', 'same.md',
        project=a, reindex=lambda paths: seen.append(paths) or {'noop': True})
    assert approved['status'] == 'approved'
    assert seen == [['docs/04_knowledge_informative/same.md']]
    assert 'Content A' in (a.docs_dir / '04_knowledge_informative/same.md').read_text(encoding='utf-8')
    assert not (b.docs_dir / '04_knowledge_informative/same.md').exists()
    assert [entry['id'] for entry in intake.list_staged(project=b)] == [other['id']]


def test_import_plan_cannot_be_applied_to_other_project(projects, tmp_path):
    a, b = projects
    source = tmp_path / 'external source'
    source.mkdir()
    (source / 'same.py').write_text('A source', encoding='utf-8')
    plan = project_import.plan_project_import(source, 'backend', project=a)
    with pytest.raises(project_import.ProjectImportError):
        project_import.apply_project_import(plan, project=b, reindex=lambda paths: {})
    assert not list(b.code_dir.iterdir())
    result = project_import.apply_project_import(plan, project=a, reindex=lambda paths: {'noop': True})
    assert result['copiati'] == ['same.py']
    assert (a.code_dir / 'backend/external source/same.py').read_text(encoding='utf-8') == 'A source'
    assert not (b.staging_dir / 'intake.jsonl').exists()


def test_project_golden_history_and_alerts_never_use_other_project(projects, monkeypatch):
    a, b = projects
    (a.root / 'eval').mkdir()
    (a.root / 'eval/golden.yaml').write_text('cases:\n- q: A query\n  expected:\n  - doc: A.md\n', encoding='utf-8')
    seen = []
    evaluate_recall = eval_gate.evaluate_recall
    def recall(*args, **kwargs):
        seen.append(kwargs['cases'])
        return {'recall': 0.0, 'n': 1, 'k': 2}
    monkeypatch.setattr(eval_gate, 'evaluate_recall', recall)
    result = eval_gate.gate_promotion('same-version', None, None, {}, project=a)
    assert result['passed'] is False
    assert seen == [[{'q': 'A query', 'expected': [{'doc': 'A.md'}]}]]
    assert (a.database_dir / 'alerts.jsonl').exists()
    assert (a.database_dir / 'eval/history.jsonl').exists()
    assert not (b.database_dir / 'alerts.jsonl').exists()
    monkeypatch.setattr(eval_gate, 'evaluate_recall', evaluate_recall)
    result = eval_gate.gate_promotion('same-version', None, None, {}, project=b)
    assert result['passed'] is True and result['skipped'] == 'no_golden_set'


def test_reindex_managers_serialize_projects_and_release_after_error(projects):
    from api.reindex import ReindexManager
    a, b = projects
    managers = [ReindexManager(project=p) for p in (a, b)]
    first_started, release_first, second_started = threading.Event(), threading.Event(), threading.Event()
    seen = []
    def first(paths):
        first_started.set()
        assert release_first.wait(5)
        raise RuntimeError('isolated test failure')
    def second(paths):
        second_started.set()
        return {'project': b.id}
    ja, _ = managers[0].start(None, first, lambda: seen.append(a.id))
    assert first_started.wait(5)
    jb, _ = managers[1].start(None, second, lambda: seen.append(b.id) or 'v1')
    assert not second_started.wait(0.15), 'B must wait for the process indexing slot while A builds'
    release_first.set()
    assert all(manager.join_all(5) for manager in managers)
    assert ja.status == 'failed' and jb.status == 'completed'
    assert seen == [b.id]
    assert managers[0].get(jb.id) is None and managers[1].get(ja.id) is None
    for project, job in ((a, ja), (b, jb)):
        records = [json.loads(line) for line in (project.database_dir / 'reindex_jobs.jsonl').read_text(encoding='utf-8').splitlines()]
        assert records and all(record['job_id'] == job.id for record in records)


def test_generated_and_refined_documents_keep_their_project(projects, monkeypatch):
    from core import doc_generation, intake_refine, llm
    a, b = projects
    monkeypatch.setattr(llm, 'resolve', lambda purpose: ('simulated', 'simulated'))
    result = doc_generation.generate_docs('A request', 1, '04_knowledge_informative',
        project=a, generate=lambda prompt: '# A generated\n\n## Content\nA facts')
    entry = result['generati'][0]
    assert intake.get_preview(entry['id'], project=a)['markdown'].endswith('A facts')
    assert intake.list_staged(project=b) == []
    with pytest.raises(intake.StagedDocumentNotFoundError):
        intake_refine.refine_staged_document(entry['id'], project=b, generate=lambda prompt: '')


def test_activity_same_feature_is_project_scoped(projects):
    from core import pipeline_activity
    a, b = projects
    with pipeline_activity.track('same-feature', 'A', project=a), pipeline_activity.track(None, 'B', project=b):
        assert pipeline_activity.snapshot('same-feature', project=a)[:2] == (['A'], [])
        assert pipeline_activity.snapshot('same-feature', project=b)[:2] == ([], ['B'])


def test_activity_none_is_the_canonical_legacy_project():
    from core import pipeline_activity
    from core.projects import legacy_project_context
    legacy = legacy_project_context()
    with pipeline_activity.track('same-feature', 'old-runner'):
        assert pipeline_activity.snapshot('same-feature', project=legacy)[0] == ['old-runner']
    with pipeline_activity.track('same-feature', 'new-runner', project=legacy):
        assert pipeline_activity.snapshot('same-feature')[0] == ['new-runner']


def test_http_intake_and_plans_are_scoped(projects, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from api import routes_intake
    a, b = projects
    monkeypatch.setattr(deps, 'ROLE', 'writer')
    monkeypatch.setattr(deps, 'SERVER_BIND_IS_LOCAL', True)
    app = FastAPI()
    app.include_router(routes_intake.router)
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        ha, hb = {'X-Vibecraft-Project': a.id}, {'X-Vibecraft-Project': b.id}
        entry = client.post('/api/intake/docs', headers=ha,
            files={'file': ('same.md', b'# A document\nContent A', 'text/markdown')})
        assert entry.status_code == 200, entry.text
        doc_id = entry.json()['id']
        assert client.get('/api/intake/staged', headers=hb).json() == {'staged': []}
        assert client.get(f'/api/intake/staged/{doc_id}/preview', headers=hb).status_code == 404
        source = tmp_path / 'external'
        source.mkdir()
        (source / 'same.py').write_text('A source', encoding='utf-8')
        plan = client.post('/api/intake/project/plan', headers=ha, json={'path':str(source),'target':'backend'})
        assert plan.status_code == 200, plan.text
        assert client.post('/api/intake/project/apply', headers=hb,
            json={'plan_id': plan.json()['plan_id']}).status_code == 404


def test_http_pipeline_same_feature_reads_and_writes_selected_project(projects):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import routes_pipeline
    a, b = projects
    app = FastAPI()
    app.include_router(routes_pipeline.router)
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        for project, content in ((a, 'A spec'), (b, 'B spec')):
            headers = {'X-Vibecraft-Project': project.id}
            saved = client.post('/api/pipeline/file/save', headers=headers,
                json={'feature':'same-feature','name':'spec.md','content': content})
            assert saved.status_code == 200, saved.text
            assert (project.changes_dir/'same-feature/spec.md').read_text(encoding='utf-8') == content
        ha = {'X-Vibecraft-Project': a.id}
        assert client.get('/api/pipeline/file', headers=ha,
            params={'feature':'same-feature','name':'spec.md'}).json()['content'] == 'A spec'


def test_archive_and_drift_sources_use_only_selected_project(projects, monkeypatch):
    from core import feature_archive, drift_check
    a, b = projects
    for project in (a, b):
        folder = pipeline.feature_dir('same-feature', project=project)
        (folder/'canvas.md').write_text('# Canvas', encoding='utf-8')
        (project.code_dir/'backend').mkdir()
        pipeline.save_dev_type(folder, 'backend', project=project)
        (project.code_dir/'backend/same.py').write_text(project.name, encoding='utf-8')
    sources = drift_check._feature_code_sources(a.changes_dir/'same-feature', '', project=a)
    assert [path.read_text(encoding='utf-8') for _, files in sources for path in files] == ['A']
    monkeypatch.setattr(feature_archive, 'generate_canvas_review', lambda *args, **kwargs: ('# A review', None))
    log = feature_archive.archive_feature('same-feature', project=a, reindex=False)
    assert 'successo' in log
    assert (a.changes_dir/'archive/same-feature/canvas.md').exists()
    assert (a.docs_dir/'03_changes_historical/same-feature-canvas-review.md').read_text(encoding='utf-8') == '# A review'
    assert (b.changes_dir/'same-feature/canvas.md').exists()
    assert not (b.changes_dir/'archive').exists()


def test_late_generation_job_uses_admitted_snapshot_and_project(projects, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import routes_intake
    a, b = projects
    started, release = threading.Event(), threading.Event()
    snap_a, snap_b = object(), object()
    admitted, completed = [], []
    monkeypatch.setattr(routes_intake, 'require_snapshot', lambda project: snap_a if project.id==a.id else snap_b)
    monkeypatch.setattr(routes_intake, 'ensure_shared_resources', lambda: None)
    def generate(*args, project, snap):
        admitted.append((project.id,snap))
        started.set()
        assert release.wait(5)
        intake.stage_document('late.md', b'# Late A\nA facts', project=project)
        completed.append(project.id)
        return {'project': project.id}
    monkeypatch.setattr(routes_intake, '_server_generate', generate)
    app=FastAPI()
    app.include_router(routes_intake.router)
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        ha,hb={'X-Vibecraft-Project':a.id},{'X-Vibecraft-Project':b.id}
        response=client.post('/api/intake/generate', headers=ha,json={'descrizione':'A request'})
        assert response.status_code==202,response.text
        job_id=response.json()['job_id']
        assert started.wait(5)
        assert client.get('/api/intake/generate/'+job_id,headers=hb).status_code==404
        assert client.get('/api/intake/staged',headers=hb).json()=={'staged':[]}
        release.set()
        manager=routes_intake._project_manager(a,'generation')
        assert manager.join_all(5)
        assert admitted==[(a.id,snap_a)] and completed==[a.id]
        assert len(intake.list_staged(project=a))==1 and intake.list_staged(project=b)==[]


def _directory_link(link, target):
    if os.name == 'nt':
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
            check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.mark.parametrize('area', ['staging', 'pipeline', 'eval_history', 'alerts'])
def test_linked_workflow_ancestors_never_read_or_write_other_project(projects, area):
    from core import eval_history
    from core.projects import ProjectError
    a,b=projects
    if area=='staging':
        a.staging_dir.rmdir()
        link,target=a.staging_dir,b.staging_dir
        def action():
            return intake.stage_document('linked.md',b'# Private B',project=a)
    elif area=='pipeline':
        link,target=a.database_dir/'pipeline',b.database_dir/'pipeline'
        target.mkdir(exist_ok=True)
        link.rmdir()
        def action():
            return PipelineStore(project=a).read_events()
    else:
        link,target=a.database_dir/'eval',b.database_dir/'eval'
        target.mkdir(exist_ok=True)
        link.rmdir()
        action=(lambda: eval_history.record_history({},n_cases=0,version='v1',source='gate',path=link/'history.jsonl')) if area=='eval_history' else (lambda: eval_gate.record_alert('warning','test',path=link/'alerts.jsonl'))
    _directory_link(link,target)
    try:
        with pytest.raises((ProjectError, __import__('core.pipeline_store',fromlist=['PipelineStorageError']).PipelineStorageError)):
            action()
        assert list(target.iterdir())==[]
    finally:
        link.rmdir() if os.name=='nt' else link.unlink()


def test_http_linked_feature_returns_safe_storage_error(projects):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import routes_pipeline
    a,b=projects
    target=pipeline.feature_dir('same-feature',project=b)
    (target/'spec.md').write_text('B private spec',encoding='utf-8')
    link=a.changes_dir/'same-feature'
    _directory_link(link,target)
    app=FastAPI()
    app.include_router(routes_pipeline.router)
    try:
        with TestClient(app,client=('127.0.0.1',50000)) as client:
            response=client.get('/api/pipeline/file',headers={'X-Vibecraft-Project':a.id},params={'feature':'same-feature','name':'spec.md'})
            assert response.status_code==503,response.text
            assert 'storage_unavailable' in response.text
            assert str(a.root) not in response.text and str(b.root) not in response.text
            assert 'B private spec' not in response.text
    finally:
        link.rmdir() if os.name=='nt' else link.unlink()


def test_archived_spec_policy_is_project_local(projects):
    a,b=projects
    archived=a.changes_dir/'archive/demo/spec.md'
    assert pipeline.validate_structural('Canvas','GIVEN x WHEN y THEN z',archived,project=a)['semantica_bdd']['skipped']=='archiviata'
    assert pipeline.validate_structural('Canvas','GIVEN x WHEN y THEN z',archived,project=b)['semantica_bdd']['checked']


def test_http_valid_gate_a_cannot_authorize_b(projects, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import routes_pipeline as routes
    a, b = projects
    monkeypatch.setattr(deps, 'ROLE', 'writer')
    monkeypatch.setattr(deps, 'API_KEY', 'synthetic')
    monkeypatch.setattr(routes, 'validate_run', lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, '_validation_source_state', lambda **kwargs: gate.SourceState())
    canvas = '\n'.join('## ' + section for section in pipeline.CANVAS_SECTIONS)
    spec = 'GIVEN richiesta WHEN invio THEN successo\n## 4. Punti aperti\n```json\n{"open_points": []}\n```'
    contract = gate.make_contract('same-feature', canvas, spec)
    for project in (a, b):
        folder = pipeline.feature_dir('same-feature', project=project)
        (folder/'canvas.md').write_text(canvas, encoding='utf-8')
        (folder/'spec.md').write_text(spec, encoding='utf-8')
    passed = gate.finish_validation(gate.new_validation(contract), contract, gate.ValidationChecks(
        structural=gate.Check(status='pass'), semantic=gate.Check(status='pass')),
        sources=gate.ValidationSources(), validator=gate.ValidatorEvidence(model='simulated', raw_response='{}'))
    routes.project_store(a).write_validation(passed)
    runs = []
    def run(*args, **kwargs):
        runs.append(kwargs['project'].id)
        kwargs['on_finish']({'type': 'result'})
        return iter(['{"type":"result"}\n'])
    monkeypatch.setattr(routes, 'run_agent_streaming', run)
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        headers = {'X-API-Key': 'synthetic', 'X-VibeCraft-Project': a.id}
        status = client.get('/api/pipeline/gate', params={'feature': 'same-feature', 'validation_id': passed.validation_id}, headers=headers)
        assert status.status_code == 200 and status.json()['gate']['allowed'], status.text
        headers['X-VibeCraft-Project'] = b.id
        body = {'runner': 'local', 'mode': 'agentic', 'feature': 'same-feature', 'validation_id': passed.validation_id, 'max_attempts': 1}
        blocked = client.post('/api/pipeline/agent/run', json=body, headers=headers)
        assert blocked.status_code == 409, blocked.text
        assert any(reason['code'] == 'validation_missing' for reason in blocked.json()['detail']['reasons'])
        assert runs == []
        assert routes.project_store(a).read_events() == []
        assert routes.project_store(b).read_events()[-1]['event'] == 'execution_blocked'
        headers['X-VibeCraft-Project'] = a.id
        allowed = client.post('/api/pipeline/agent/run', json=body, headers=headers)
        assert allowed.status_code == 200, allowed.text
        assert runs == [a.id]


def test_http_late_reindex_reload_and_public_error_are_bound(projects, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import routes_reindex as routes
    a, b = projects
    monkeypatch.setattr(deps, 'ROLE', 'writer')
    entered, release = threading.Event(), threading.Event()
    captures = []
    def build(paths, *, project):
        entered.set()
        assert release.wait(5)
        captures.append(('build', project.id))
        return {'version': 'vA'}
    monkeypatch.setattr(routes, '_run_reindex', build)
    monkeypatch.setattr(routes, 'reload_index_state', lambda project: captures.append(('reload', project.id)) or 'vA')
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        headers = {'X-VibeCraft-Project': a.id}
        try:
            response = client.post('/api/reindex', json={'paths': ['docs/same.md']}, headers=headers)
            assert response.status_code == 202, response.text
            job_id = response.json()['job_id']
            assert entered.wait(5)
            headers['X-VibeCraft-Project'] = b.id
            assert client.get('/api/reindex/'+job_id, headers=headers).status_code == 404
            assert client.get('/api/reindex', headers=headers).json()['jobs'] == []
        finally:
            release.set()
        assert routes.project_manager(a).join_all(5)
        assert captures == [('build', a.id), ('reload', a.id)]
        headers['X-VibeCraft-Project'] = a.id
        status = client.get('/api/reindex/'+job_id, headers=headers).json()
        assert status['published_token'] == 'vA' and status['status'] == 'completed'
        def fail(paths, *, project):
            raise OSError(str(project.root) + ' private-key-value')
        monkeypatch.setattr(routes, '_run_reindex', fail)
        failed = client.post('/api/reindex', json={}, headers=headers).json()['job_id']
        assert routes.project_manager(a).join_all(5)
        response = client.get('/api/reindex/'+failed, headers=headers)
        assert response.json()['status'] == 'failed'
        assert str(a.root) not in response.text and 'private-key-value' not in response.text
        assert captures == [('build', a.id), ('reload', a.id)]


def test_interactive_rollback_does_not_wait_for_process_build(projects, monkeypatch):
    from api import routes_reindex as routes
    from core.indexing_lock import indexing_lock
    from core.writer_lock import WriterLockBusyError
    a, _ = projects
    monkeypatch.setattr(routes, '_ROLLBACK_WRITER_LOCK_TIMEOUT_SECONDS', 0.05)
    monkeypatch.setattr(routes, 'ensure_shared_resources', lambda **kwargs: None)
    mutations, errors = [], []
    monkeypatch.setattr(routes, 'resolve_rollback_target', lambda *args, **kwargs: mutations.append('resolve') or 'v1')
    monkeypatch.setattr(routes, 'rollback_version', lambda *args, **kwargs: mutations.append('rollback') or 'v1')
    monkeypatch.setattr(routes, 'rollback_shares_collection_with_later_versions', lambda *args, **kwargs: [])
    monkeypatch.setattr(routes, 'rollback_qdrant_alias_if_needed', lambda *args, **kwargs: {})
    monkeypatch.setitem(routes.state, 'qdrant', None)
    def rollback():
        try:
            routes._rollback_under_writer_lock('v1', a)
        except Exception as exc:
            errors.append(exc)
    indexing_lock.acquire()
    thread = threading.Thread(target=rollback)
    try:
        thread.start()
        thread.join(0.3)
        finished = not thread.is_alive()
    finally:
        indexing_lock.release()
        thread.join(5)
    assert finished, 'Interactive rollback must reject a busy process build within its short timeout'
    assert mutations == [] and len(errors) == 1 and isinstance(errors[0], WriterLockBusyError)


@pytest.mark.parametrize('endpoint', ['/api/pipeline/drift/check', '/api/pipeline/archive', '/api/pipeline/archive/stream'])
def test_workflow_storage_failure_is_safe_and_never_enqueues(projects, monkeypatch, endpoint):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import routes_pipeline as routes
    a, _ = projects
    monkeypatch.setattr(deps, 'ROLE', 'writer')
    queued = []
    def fail(*args, **kwargs):
        raise ValueError(str(a.root) + ' private-provider-key')
    monkeypatch.setattr(routes, 'check_drift', fail)
    monkeypatch.setattr(routes, 'archive_feature', fail)
    monkeypatch.setattr(routes, 'enqueue_full_rebuild', lambda **kwargs: queued.append(True))
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app, client=('127.0.0.1', 50000), raise_server_exceptions=False) as client:
        response = client.post(endpoint, json={'feature': 'same-feature'}, headers={'X-VibeCraft-Project': a.id})
        if endpoint.endswith('/stream'):
            assert response.status_code == 200
            events = [json.loads(line) for line in response.text.splitlines()]
            assert events[-1]['type'] == 'error'
        else:
            assert response.status_code == 503, response.text
            assert response.json()['detail']['reasons'][0]['code'] == 'storage_unavailable'
        assert str(a.root) not in response.text and 'private-provider-key' not in response.text
        assert queued == []


def test_refine_writes_only_a_and_retains_raw_document(projects, monkeypatch):
    from types import SimpleNamespace
    from core import intake_refine
    a, b = projects
    staged = intake.stage_document('same.txt', b'A raw content', project=a)
    raw_path = a.staging_dir/'docs'/staged['files']['markdown']
    raw = raw_path.read_bytes()
    monkeypatch.setattr(intake_refine, 'refine_markdown', lambda *args, **kwargs: SimpleNamespace(
        markdown='A refined content', semantic={}, stats={'windows': 1}))
    result = intake_refine.refine_staged_document(staged['id'], project=a)
    assert raw_path.read_bytes() == raw
    assert result['files']['markdown_raw'] == raw_path.name
    assert intake.get_preview(staged['id'], project=a)['markdown'] == 'A refined content'
    assert intake.list_staged(project=b) == []
    assert not list(b.staging_dir.glob('docs/*.refined.md'))


def test_browse_path_is_global_authenticated_and_local_at_zero_projects(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import routes_intake as routes
    registry = ProjectRegistry(tmp_path/'empty', bootstrap_legacy=False)
    monkeypatch.setattr(deps, 'project_registry', lambda: registry)
    monkeypatch.setattr(deps, 'ROLE', 'writer')
    monkeypatch.setattr(deps, 'API_KEY', 'synthetic')
    monkeypatch.setattr(deps, 'SERVER_BIND_IS_LOCAL', True)
    monkeypatch.setattr(routes, '_native_folder_dialog', lambda: str(tmp_path))
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app, client=('192.0.2.10', 50000)) as client:
        response = client.post('/api/intake/project/browse-path', headers={'X-API-Key': 'synthetic'})
        assert response.status_code == 200 and response.json()['path'] == str(tmp_path), response.text
        assert client.post('/api/intake/project/browse-path', headers={'X-API-Key': 'wrong'}).status_code == 401
        monkeypatch.setattr(deps, 'SERVER_BIND_IS_LOCAL', False)
        assert client.post('/api/intake/project/browse-path', headers={'X-API-Key': 'synthetic'}).status_code == 403



def test_loading_a_does_not_block_asgi_requests_for_b(projects, monkeypatch):
    import asyncio
    import httpx
    from fastapi import FastAPI
    from fastapi.concurrency import run_in_threadpool
    from api import routes_intake as routes
    a, b = projects
    monkeypatch.setattr(deps, 'ROLE', 'writer')
    entered, release, loaded = threading.Event(), threading.Event(), threading.Event()
    threads = []
    def load(project):
        threads.append(threading.get_ident())
        entered.set()
        release.wait(2)
        loaded.set()
        return None
    monkeypatch.setattr(routes, 'require_snapshot', load)
    monkeypatch.setattr(routes, 'ensure_shared_resources', lambda: threads.append(threading.get_ident()))
    monkeypatch.setattr(routes, '_server_generate', lambda *args, **kwargs: {'n_generati': 0})
    app = FastAPI()
    app.include_router(routes.router)
    async def requests():
        loop_thread = threading.get_ident()
        transport = httpx.ASGITransport(app=app, client=('127.0.0.1', 50000))
        async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as client:
            pending = asyncio.create_task(client.post('/api/intake/generate', json={'descrizione': 'A'}, headers={'X-VibeCraft-Project': a.id}))
            try:
                assert await run_in_threadpool(entered.wait, 5)
                heartbeat = client.get('/api/intake/staged', headers={'X-VibeCraft-Project': b.id})
                response = await heartbeat
                assert response.status_code == 200 and response.json()['staged'] == [], response.text
                assert not loaded.is_set(), 'B must respond while the A snapshot loader is still held'
            finally:
                release.set()
                submitted = await pending
                assert submitted.status_code == 202, submitted.text
                assert routes._project_manager(a, 'generation').join_all(5)
            assert threads and all(thread != loop_thread for thread in threads)
    asyncio.run(requests())


@pytest.mark.parametrize('kind,status', [
    ('ConversionError', 422), ('RefineError', 422),
    ('InvalidImportPathError', 422), ('ProjectImportError', 422),
])
def test_typed_workflow_error_keeps_status_without_private_diagnostics(projects, monkeypatch, kind, status):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import routes_intake as routes
    a, _ = projects
    error_type = (routes.ConversionError if kind == 'ConversionError' else
        routes.intake_refine.RefineError if kind == 'RefineError' else
        getattr(project_import, kind))
    def fail(*args, **kwargs):
        raise error_type(str(a.root) + ' private-provider-key')
    monkeypatch.setattr(routes.intake, 'stage_document', fail)
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        response = client.post('/api/intake/docs', headers={'X-VibeCraft-Project': a.id},
            files={'file': ('same.md', b'# A', 'text/markdown')})
        assert response.status_code == status, response.text
        assert str(a.root) not in response.text and 'private-provider-key' not in response.text


def test_server_imports_in_fresh_writer_process(tmp_path):
    import sys
    environment = {**os.environ, 'VIBECRAFT_ROLE': 'writer', 'VIBECRAFT_INDEX_MODE': 'immutable',
        'VIBECRAFT_PROJECTS_DIR': str(tmp_path/'projects'),
        'VIBECRAFT_DATABASE_DIR': str(tmp_path/'database')}
    imported = subprocess.run([sys.executable, '-c', 'import server; assert server.app is not None'],
        cwd=__import__('pathlib').Path(__file__).resolve().parents[1],
        env=environment, capture_output=True, text=True, timeout=45)
    assert imported.returncode == 0, imported.stderr


def test_health_restores_project_history_without_writes(projects, monkeypatch):
    from dataclasses import replace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import routes_health as routes
    from api.reindex import ReindexJob
    a, b = projects
    legacy = replace(a, id='legacy', legacy=True, database_dir=a.root/'legacy-database')
    contexts = (a, b, legacy)
    journals, jobs = {}, {}
    for project in contexts:
        project.database_dir.mkdir(exist_ok=True)
        path = project.database_dir/'reindex_jobs.jsonl'
        job = ReindexJob(None, status='running')
        path.write_text(json.dumps(job.to_dict())+'\n', encoding='utf-8')
        journals[project.id] = (path, path.read_bytes(), path.stat().st_mtime_ns)
        jobs[project.id] = job.id
    resolver = routes.get_project
    monkeypatch.setattr(routes, 'get_project', lambda request: legacy if request.headers.get('X-VibeCraft-Project') == 'legacy' else resolver(request))
    monkeypatch.setattr(routes, 'require_snapshot', lambda project: None)
    monkeypatch.setattr(routes, 'index_status', lambda **kwargs: {'indexed':False})
    monkeypatch.setattr(routes, 'check_ollama', lambda: False)
    monkeypatch.setattr(routes, 'eval_health', lambda **kwargs: {})
    monkeypatch.setattr(routes, 'read_last_alert', lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        for project in contexts:
            response = client.get('/api/health', headers={'X-VibeCraft-Project':project.id})
            assert response.status_code == 200, response.text
            assert response.json()['project_id'] == project.id
            assert response.json()['reindex']['last_job']['job_id'] == jobs[project.id]
            assert response.json()['reindex']['last_job']['status'] == 'interrupted'
            path, content, modified = journals[project.id]
            assert path.read_bytes() == content and path.stat().st_mtime_ns == modified
            assert 'reindex_manager' not in deps.project_runtime(project)
            assert list(project.database_dir.glob('reindex_jobs.jsonl*')) == [path]


def test_readonly_reindex_view_does_not_compact_or_recover(projects, monkeypatch):
    from api import reindex
    a, _ = projects
    path = a.database_dir/'reindex_jobs.jsonl'
    job = reindex.ReindexJob(None, status='running')
    path.write_text((json.dumps(job.to_dict())+'\n') * 3, encoding='utf-8')
    original = path.read_bytes()
    monkeypatch.setattr(reindex, '_JOURNAL_MAX_BYTES', 1)
    path.chmod(0o444)
    try:
        manager = reindex.ReindexManager(project=a, recover_journal=False)
        assert manager.get(job.id).status == 'interrupted'
        assert path.read_bytes() == original
        assert list(a.database_dir.glob('reindex_jobs.jsonl*')) == [path]
    finally:
        path.chmod(0o666)

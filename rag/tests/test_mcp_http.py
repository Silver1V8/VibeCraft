"""Contratti MCP/HTTP: snapshot, default e limiti senza servizi esterni."""
from dataclasses import replace

import networkx as nx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import deps, routes_graph, routes_retrieval
from core import retrieval


@pytest.fixture
def env(monkeypatch):
    graph = nx.DiGraph()
    graph.add_nodes_from((f'doc-{i}', {'type': 'document'}) for i in range(5))
    snap = deps.IndexSnapshot(graph, {}, {'a': {'text': 'abcdef'}}, {}, {},
                              'v-old', [], None)
    monkeypatch.setitem(deps.state, 'snapshot', snap)
    monkeypatch.setitem(deps.state, 'qdrant', object())
    monkeypatch.setitem(deps.state, 'embed_model', object())
    monkeypatch.setattr(routes_retrieval, 'maybe_reload_graph', lambda: None)
    monkeypatch.setattr(routes_graph, 'maybe_reload_graph', lambda: None)
    monkeypatch.setattr(routes_retrieval, 'qdrant_collection_for_version', lambda v: f'collection-{v}')
    app = FastAPI()
    app.include_router(routes_retrieval.router)
    app.include_router(routes_graph.router)
    return TestClient(app, client=('127.0.0.1', 1)), snap


def test_retrieve_snapshot_changes_during_search(env, monkeypatch):
    client, snap = env
    calls = []
    hit = {'chunk_id': 'a', 'doc_id': 'doc-a', 'colbert_score': 0.75,
           'classification': 'normative', 'status': 'active'}

    def search(*args, **kwargs):
        calls.append(kwargs)
        deps.state['snapshot'] = replace(snap, version='v-new', chunks={'a': {'text': 'NEW'}})
        return [hit.copy()]

    monkeypatch.setattr(retrieval, 'hybrid_search', search)
    body = client.get('/api/retrieve', params={'q': 'test', 'include_text': True,
                                              'text_max_chars': 3}).json()
    assert body['index_version'] == 'v-old'
    assert calls[0]['collection_name'] == 'collection-v-old'
    assert calls[0]['graph'] is snap.graph
    result = body['results'][0]
    assert result['text'] == 'abc'
    assert result['text_truncated'] is True
    assert result['text_chars'] == 6
    assert result['source_label'] == retrieval.source_label(hit)
    assert all(result[k] == v for k, v in hit.items())


def test_http_default_results_unchanged(env, monkeypatch):
    client, _ = env
    hits = [{'chunk_id': 'a', 'doc_id': 'd', 'authority': 1.0}]
    monkeypatch.setattr(retrieval, 'hybrid_search', lambda *a, **kw: hits)
    body = client.get('/api/retrieve', params={'q': 'test'}).json()
    assert body['results'] == hits
    assert body['k'] == 5
    assert body['index_version'] == 'v-old'
    assert client.get('/api/retrieve', params={'q': 'x', 'text_max_chars': 0}).status_code == 422


def test_graph_limits_are_explicit_and_read_only(env):
    client, snap = env
    before = nx.node_link_data(snap.graph)
    default = client.get('/api/graph/query', params={'q': 'documenti'}).json()
    body = client.get('/api/graph/query', params={'q': 'documenti', 'limit': 2}).json()
    assert body['answer'] == default['answer'][:2]
    assert body['count'] == 5
    assert body['truncated'] is True
    assert body['returned_count'] == 2
    assert body['index_version'] == 'v-old'
    client.get('/api/graph/query', params={'q': 'MATCH (n) DETACH DELETE n'})
    assert nx.node_link_data(snap.graph) == before


def test_snapshot_build_uses_loaded_artifact_version(monkeypatch):
    monkeypatch.setattr(deps, '_graph_version', lambda: 'v-new')
    snap = deps._build_snapshot(None, {}, {}, {}, {}, version='v-old')
    assert snap.version == 'v-old'


def test_graph_limits_relations_and_rings(env):
    client, snap = env
    snap.graph.add_edges_from(('doc-0', f'doc-{i}') for i in range(1, 5))
    for q in ('relazioni', 'impatto'):
        body = client.get('/api/graph/query', params={'q': q, 'target': 'doc-0', 'limit': 2}).json()
        assert body['returned_count'] == 2 and body['truncated']
        assert body['count'] == 4


def test_missing_snapshot_text_and_collection_fail_closed(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(retrieval, 'hybrid_search', lambda *a, **kw: [{'chunk_id': 'missing'}])
    assert client.get('/api/retrieve', params={'q': 'x', 'include_text': True}).status_code == 503
    monkeypatch.setattr(routes_retrieval, 'qdrant_collection_for_version', lambda v: 'unknown')
    assert client.get('/api/retrieve', params={'q': 'x'}).status_code == 503


def test_authentication_unchanged_for_remote_http(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(deps, 'API_KEY', 'synthetic-key')
    remote = TestClient(client.app, client=('192.0.2.1', 1))
    for route in ('/api/retrieve', '/api/code/search', '/api/graph/query'):
        assert remote.get(route, params={'q': 'documenti'}).status_code == 401
        assert remote.get(route, params={'q': 'documenti'}, headers={'X-API-Key': 'wrong'}).status_code == 401
    assert remote.get('/api/graph/query', params={'q': 'documenti'},
                      headers={'X-API-Key': 'synthetic-key'}).status_code == 200


def test_legacy_snapshot_does_not_reload_unchanged_files(tmp_path, monkeypatch):
    from types import SimpleNamespace
    path = tmp_path / 'graph.json'
    path.write_text('{}')
    monkeypatch.setattr(deps, 'GRAPH_JSON_PATH', path)
    monkeypatch.setattr(deps, 'current_version_token', lambda: None)
    monkeypatch.setattr(deps, 'load_rule_descriptions', lambda: {})
    monkeypatch.setitem(deps.state, 'snapshot', None)
    monkeypatch.setitem(deps.state, '_graph_mtime', None)
    calls = []
    def load(**kwargs):
        calls.append(1)
        return SimpleNamespace(graph=None, colbert_store={}, chunks_store={},
                               code_store={}, version='legacy')
    monkeypatch.setattr(deps, 'load_artifacts', load)
    deps.reload_index_state()
    deps.maybe_reload_graph()
    deps.maybe_reload_graph()
    assert len(calls) == 1

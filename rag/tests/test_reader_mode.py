"""Contratto del processo replica read-only, senza servizi esterni."""
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import networkx as nx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import deps, routes_graph, routes_health
from core.artifacts import Artifacts, IMMUTABLE_MARKER_FILENAME


RAG_DIR = Path(__file__).parents[1]


def test_reader_import_server_non_importa_writer_e_non_tocca_journal(tmp_path):
    journal = tmp_path / "reindex_jobs.jsonl"
    journal.write_text('{"status":"pending"}\n', encoding="utf-8")
    before = hashlib.sha256(journal.read_bytes()).hexdigest()
    script = r"""
import hashlib, json, sys
from pathlib import Path
path = Path(sys.argv[1])
before = hashlib.sha256(path.read_bytes()).hexdigest()
import server
after = hashlib.sha256(path.read_bytes()).hexdigest()
paths = set()
for route in server.app.routes:
  if getattr(route, "path", None):
    paths.add(route.path)
  nested = getattr(route, "original_router", None)
  if nested is not None:
    paths.update(item.path for item in nested.routes)
print(json.dumps({
  "before": before, "after": after,
  "reindex_imported": "api.routes_reindex" in sys.modules,
  "paths": sorted(paths),
}))
"""
    env = dict(os.environ, VIBECRAFT_ROLE="reader", VIBECRAFT_INDEX_MODE="immutable",
               VIBECRAFT_DATABASE_DIR=str(tmp_path), VIBECRAFT_API_KEY="reader-secret",
               QDRANT_URL="http://127.0.0.1:16333", HF_HUB_OFFLINE="1",
               TRANSFORMERS_OFFLINE="1")
    result = subprocess.run(
        [sys.executable, "-c", script, str(journal)], cwd=RAG_DIR, env=env,
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    report = json.loads(result.stdout.splitlines()[-1])
    assert report["before"] == report["after"] == before
    assert report["reindex_imported"] is False
    assert {"/", "/analysis", "/infografica", "/ask", "/api/retrieve",
            "/api/code/search", "/api/graph/all", "/api/graph/impact",
            "/api/graph/semantic-map", "/api/graph/query", "/api/health"} <= set(report["paths"])
    assert not ({"/pipeline", "/eval", "/intake", "/api/reindex",
                 "/api/index/rollback", "/api/canvas-quality"} & set(report["paths"]))
    assert not any(path.startswith("/api/pipeline") or path.startswith("/api/intake")
                   for path in report["paths"])


def test_reader_richiede_api_key_anche_loopback_e_ignora_xff(monkeypatch):
    graph = nx.DiGraph()
    graph.add_node("doc.md", type="document")
    monkeypatch.setattr(deps, "ROLE", "reader")
    monkeypatch.setattr(deps, "API_KEY", "reader-secret")
    monkeypatch.setattr(routes_graph, "maybe_reload_graph", lambda: None)
    monkeypatch.setitem(deps.state, "snapshot", deps.IndexSnapshot(
        graph, {}, {}, {}, {}, "v1", [], None, collection_name="physical-v1",
    ))
    app = FastAPI()
    app.include_router(routes_graph.router)
    client = TestClient(app, client=("127.0.0.1", 1234))

    assert client.get("/api/graph/query", params={"q": "documenti"}).status_code == 401
    assert client.get("/api/graph/query", params={"q": "documenti"}, headers={
        "X-Forwarded-For": "127.0.0.1", "X-API-Key": "wrong",
    }).status_code == 401
    assert client.get("/api/graph/query", params={"q": "documenti"}, headers={
        "X-API-Key": "reader-secret",
    }).status_code == 200


class _Lease:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _Qdrant:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _reader_manifest(tmp_path, version="v1", *, immutable=True, collection=None):
    version_dir = tmp_path / "versions" / version
    version_dir.mkdir(parents=True, exist_ok=True)
    collection = collection or f"vibecraft_events__{version}"
    manifest = {"version": version, "immutable": immutable,
                "qdrant_collection": collection, "artifact_hashes": {}}
    (version_dir / "index_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def _patch_reader_boot(monkeypatch, tmp_path, artifacts):
    monkeypatch.setattr(deps, "ROLE", "reader")
    monkeypatch.setattr(deps, "API_KEY", "reader-secret")
    monkeypatch.setattr(deps, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(deps, "BGEM3FlagModel", lambda *_a, **_k: object())
    monkeypatch.setattr(deps, "QdrantClient", lambda *_a, **_k: _Qdrant())
    monkeypatch.setattr(deps, "manifest_path", lambda version=None:
                        tmp_path / "versions" / str(version) / "index_manifest.json")
    monkeypatch.setattr(deps, "artifact_hashes", lambda version=None: {})
    calls = []

    def load(**kwargs):
        calls.append(kwargs)
        return artifacts

    monkeypatch.setattr(deps, "load_artifacts", load)
    monkeypatch.setattr(deps, "reconcile_and_repair_qdrant_alias",
                        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("repair")))
    monkeypatch.setattr(deps, "gc_orphaned_qdrant_collections",
                        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("gc")))
    monkeypatch.setattr(deps, "writer_lock",
                        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("lock")))
    return calls


def test_reader_lifespan_carica_snapshot_pinnato_senza_mutazioni(monkeypatch, tmp_path):
    (tmp_path / IMMUTABLE_MARKER_FILENAME).write_text("immutable\n", encoding="utf-8")
    manifest = _reader_manifest(tmp_path)
    lease = _Lease()
    chunks = {"doc.md#01": {"doc_id": "doc.md", "text": "`[REGOLA-X]`: Descrizione X"}}
    artifacts = Artifacts(graph=nx.DiGraph(), colbert_store={"doc.md#01": object()},
                          chunks_store=chunks, version="v1", version_lease=lease)
    calls = _patch_reader_boot(monkeypatch, tmp_path, artifacts)
    before = {p.relative_to(tmp_path): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in tmp_path.rglob("*") if p.is_file()}
    captured = {}

    async def run():
        async with deps.lifespan(FastAPI()):
            captured["snapshot"] = deps.current_snapshot()

    asyncio.run(run())
    after = {p.relative_to(tmp_path): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in tmp_path.rglob("*") if p.is_file()
             and ".reader-locks" not in p.parts}
    assert before == after
    assert calls == [{"required": ("graph", "colbert", "chunks"), "retain_lease": True}]
    snap = captured["snapshot"]
    assert snap.version_lease is lease
    assert snap.collection_name == manifest["qdrant_collection"]
    assert snap.index_manifest == manifest
    assert snap.rule_descriptions == {"REGOLA-X": "Descrizione X"}
    assert lease.closed is False


def test_reader_boot_rifiuta_bundle_con_chunk_mancante(monkeypatch, tmp_path):
    (tmp_path / IMMUTABLE_MARKER_FILENAME).write_text("immutable\n", encoding="utf-8")
    _reader_manifest(tmp_path)
    lease = _Lease()
    artifacts = Artifacts(graph=nx.DiGraph(), colbert_store={"chunk-rimosso": object()},
                          chunks_store={}, version="v1", version_lease=lease)
    _patch_reader_boot(monkeypatch, tmp_path, artifacts)

    async def run():
        async with deps.lifespan(FastAPI()):
            pass

    with pytest.raises(RuntimeError, match="ColBERT e chunks"):
        asyncio.run(run())
    assert lease.closed is True


def test_reader_boot_rifiuta_hash_artefatti_non_coerenti(monkeypatch, tmp_path):
    (tmp_path / IMMUTABLE_MARKER_FILENAME).write_text("immutable\n", encoding="utf-8")
    _reader_manifest(tmp_path)
    lease = _Lease()
    artifacts = Artifacts(
        graph=nx.DiGraph(), colbert_store={"c": object()},
        chunks_store={"c": {"text": "x"}}, version="v1", version_lease=lease,
    )
    _patch_reader_boot(monkeypatch, tmp_path, artifacts)
    monkeypatch.setattr(deps, "artifact_hashes", lambda version=None: {"chunks.json": "changed"})

    async def run():
        async with deps.lifespan(FastAPI()):
            pass

    with pytest.raises(RuntimeError, match="hash degli artefatti"):
        asyncio.run(run())
    assert lease.closed is True


@pytest.mark.parametrize("marker,version,immutable,collection", [
    (False, "v1", True, "vibecraft_events__v1"),
    (True, "legacy", True, "vibecraft_events__legacy"),
    (True, "v1", False, "vibecraft_events__v1"),
    (True, "v1", True, "wrong"),
])
def test_reader_boot_rifiuta_layout_non_immutabile(
    monkeypatch, tmp_path, marker, version, immutable, collection,
):
    if marker:
        (tmp_path / IMMUTABLE_MARKER_FILENAME).write_text("immutable\n", encoding="utf-8")
    _reader_manifest(tmp_path, version, immutable=immutable, collection=collection)
    lease = _Lease()
    artifacts = Artifacts(graph=nx.DiGraph(), colbert_store={"c": object()},
                          chunks_store={"c": {"text": "x"}}, version=version,
                          version_lease=lease)
    _patch_reader_boot(monkeypatch, tmp_path, artifacts)

    async def run():
        async with deps.lifespan(FastAPI()):
            pass

    with pytest.raises(RuntimeError):
        asyncio.run(run())
    assert lease.closed is marker


def test_reader_boot_senza_api_key_fallisce_prima_delle_risorse(monkeypatch, tmp_path):
    monkeypatch.setattr(deps, "ROLE", "reader")
    monkeypatch.setattr(deps, "API_KEY", None)
    monkeypatch.setattr(deps, "BGEM3FlagModel",
                        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("model")))

    async def run():
        async with deps.lifespan(FastAPI()):
            pass

    with pytest.raises(RuntimeError, match="API_KEY"):
        asyncio.run(run())


def test_rule_descriptions_reader_derivano_dai_chunk_in_ordine_stabile():
    chunks = {
        "b": {"text": "`[REGOLA-X]`: seconda\n`[REGOLA-Y]`: ipsilon"},
        "a": {"text": "`[REGOLA-X]`: prima"},
    }
    assert deps.rule_descriptions_from_chunks(chunks) == {
        "REGOLA-X": "seconda", "REGOLA-Y": "ipsilon",
    }


def test_reader_reload_atomico_trattiene_lease_e_degrada_su_candidato_incompleto(
    monkeypatch, tmp_path,
):
    (tmp_path / IMMUTABLE_MARKER_FILENAME).write_text("immutable\n", encoding="utf-8")
    for version in ("v1", "v2", "v3"):
        _reader_manifest(tmp_path, version)
    monkeypatch.setattr(deps, "ROLE", "reader")
    monkeypatch.setattr(deps, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(deps, "manifest_path", lambda version=None:
                        tmp_path / "versions" / str(version) / "index_manifest.json")
    monkeypatch.setattr(deps, "artifact_hashes", lambda version=None: {})
    monkeypatch.setattr(deps, "_graph_version", lambda: "v3")

    def bundle(version, lease, *, complete=True):
        graph = nx.DiGraph()
        graph.add_node(f"{version}.md", type="document")
        chunks = ({f"{version}#1": {"text": f"`[R-{version.upper()}]`: {version}"}}
                  if complete else {})
        return Artifacts(
            graph=graph, colbert_store={f"{version}#1": object()}, chunks_store=chunks,
            version=version, version_lease=lease,
        )

    lease1, lease2, lease3, lease1b = _Lease(), _Lease(), _Lease(), _Lease()
    first = deps._build_snapshot(
        nx.DiGraph(), {}, {}, {}, {}, version="v1", collection_name="vibecraft_events__v1",
        index_manifest={"immutable": True}, version_lease=lease1,
    )
    deps.state["snapshot"] = first
    deps.state["reload_error"] = None
    loads = iter((bundle("v2", lease2), bundle("v3", lease3, complete=False),
                  bundle("v1", lease1b)))
    monkeypatch.setattr(deps, "load_artifacts", lambda **_kwargs: next(loads))

    assert deps.reload_index_state() == "v2"
    second = deps.current_snapshot()
    assert second.collection_name == "vibecraft_events__v2"
    assert first.collection_name == "vibecraft_events__v1"
    assert lease1.closed is False and lease2.closed is False

    assert deps.reload_index_state() is None
    assert deps.current_snapshot() is second
    assert lease3.closed is True
    assert "ColBERT e chunks" in deps.state["reload_error"]

    assert deps.reload_index_state() == "v1"
    assert deps.current_snapshot().collection_name == "vibecraft_events__v1"
    assert deps.state["reload_error"] is None
    assert lease1.closed is False and lease2.closed is False and lease1b.closed is False


def test_reader_health_usa_solo_manifest_pinnato_e_segnala_reload_fallito(tmp_path):
    graph = nx.DiGraph()
    manifest = {"immutable": True, "qdrant_collection": "vibecraft_events__v1"}
    snap = deps.IndexSnapshot(
        graph, {}, {"c": {"text": "x"}}, {}, {}, "v1", [], None,
        collection_name="vibecraft_events__v1", index_manifest=manifest,
    )

    class HealthyQdrant:
        def get_collections(self):
            return SimpleNamespace(collections=[
                SimpleNamespace(name="vibecraft_events__v1"),
            ])

    def forbidden(*_args, **_kwargs):
        raise AssertionError("reader non deve leggere stato live")

    report = routes_health.build_health(
        snapshot=snap, manager=SimpleNamespace(list_recent=forbidden),
        qdrant=HealthyQdrant(), status_fn=forbidden, ollama_check=lambda: True,
        alerts_path=tmp_path / "alerts.jsonl", role="reader",
        reload_error="ValueError: candidate corrotto", eval_health_fn=forbidden,
    )
    assert report["status"] == "degraded"
    assert report["role"] == "reader" and report["read_only"] is True
    assert report["manifest"]["qdrant_collection"] == "vibecraft_events__v1"
    assert report["manifest"]["stale"] is True
    assert report["reindex"] is None and report["eval"] is None
    assert any("reload indice fallito" in reason for reason in report["reasons"])


@pytest.mark.parametrize("collections,expected_status", [
    (["vibecraft_events__v1"], "ok"),
    ([], "degraded"),
])
def test_reader_health_verifica_la_collection_fisica(collections, expected_status):
    graph = nx.DiGraph()
    manifest = {"immutable": True, "qdrant_collection": "vibecraft_events__v1"}
    snap = deps.IndexSnapshot(
        graph, {}, {"c": {"text": "x"}}, {}, {}, "v1", [], None,
        collection_name="vibecraft_events__v1", index_manifest=manifest,
    )

    class Qdrant:
        def get_collections(self):
            return SimpleNamespace(collections=[SimpleNamespace(name=name)
                                                for name in collections])

    report = routes_health.build_health(
        snapshot=snap, qdrant=Qdrant(), ollama_check=lambda: True,
        role="reader", reload_error=None,
    )
    assert report["status"] == expected_status
    missing = [reason for reason in report["reasons"] if "collection Qdrant" in reason]
    assert bool(missing) is (expected_status == "degraded")


def test_semantic_map_route_usa_collection_fisica_dello_snapshot(monkeypatch):
    graph = nx.DiGraph()
    snap = deps.IndexSnapshot(graph, {}, {}, {}, {}, "v1", [], None,
                              collection_name="physical-v1")
    monkeypatch.setattr(routes_graph, "maybe_reload_graph", lambda: None)
    monkeypatch.setattr(routes_graph, "current_snapshot", lambda: snap)
    monkeypatch.setitem(deps.state, "qdrant", object())
    seen = {}

    def semantic_map(g, qdrant, collection_name=None):
        seen["collection"] = collection_name
        return {"points": []}

    monkeypatch.setattr(routes_graph.graph_ops, "semantic_map", semantic_map)
    app = FastAPI()
    app.include_router(routes_graph.router)
    response = TestClient(app, client=("127.0.0.1", 1)).get("/api/graph/semantic-map")
    assert response.status_code == 200
    assert seen["collection"] == "physical-v1"

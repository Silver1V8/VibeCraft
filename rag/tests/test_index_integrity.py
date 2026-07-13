"""Test di check_index_integrity: il check notturno ECONOMICO (zero embedding).
Manifest, hash sorgenti, integrità artefatti e conteggio Qdrant sono tutti
finti/iniettati: nessun modello, nessun server, millisecondi."""
import json

import pytest

from core import indexing


class _FakeCount:
    def __init__(self, n):
        self.count = n


class _FakeQdrant:
    """Client Qdrant finto: risponde solo a count() con un numero fisso."""

    def __init__(self, n):
        self._n = n
        self.closed = False

    def count(self, collection_name, exact=True):
        return _FakeCount(self._n)

    def close(self):
        self.closed = True


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Ambiente coerente di default: manifest allineato a sorgenti, artefatti e sidecar
    (3 chunk). I singoli test rompono UN pezzo alla volta."""
    manifest_path = tmp_path / "index_manifest.json"
    chunks_path = tmp_path / "chunks.json"

    doc_hashes = {"a.md": "h1", "b.md": "h2"}
    code_hashes = {"x.py": "c1"}
    art_hashes = {"graph.json": "g1", "chunks.json": "k1"}

    manifest_path.write_text(json.dumps({
        "doc_hashes": doc_hashes,
        "code_hashes": code_hashes,
        "artifact_hashes": art_hashes,
    }), encoding="utf-8")
    chunks_path.write_text(json.dumps({"c1": {}, "c2": {}, "c3": {}}), encoding="utf-8")

    monkeypatch.setattr(indexing, "INDEX_MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(indexing, "CHUNKS_JSON_PATH", chunks_path)
    monkeypatch.setattr(indexing, "_docs_hashes", lambda: dict(doc_hashes))
    monkeypatch.setattr(indexing, "_code_hashes", lambda: dict(code_hashes))
    monkeypatch.setattr(indexing, "artifact_hashes", lambda: dict(art_hashes))
    return {"manifest": manifest_path, "chunks": chunks_path, "monkeypatch": monkeypatch}


def _check(env, points=3):
    return indexing.check_index_integrity(qdrant=_FakeQdrant(points), emit=lambda m: None)


def test_all_aligned_is_ok(env):
    report = _check(env)
    assert report == {
        "ok": True, "stale": False, "artifacts_corrupted": False,
        "qdrant_mismatch": False, "problems": [],
    }


def test_manifest_absent(env):
    env["manifest"].unlink()
    report = _check(env)
    assert report["ok"] is False and report["stale"] is True
    assert any("manifest assente" in p for p in report["problems"])


def test_manifest_corrupt(env):
    env["manifest"].write_text("{not json", encoding="utf-8")
    report = _check(env)
    assert report["ok"] is False and report["stale"] is True
    assert any("manifest" in p for p in report["problems"])


def test_source_hash_divergence_marks_stale(env):
    # b.md modificato e nuovo.md aggiunto rispetto al manifest.
    env["monkeypatch"].setattr(
        indexing, "_docs_hashes", lambda: {"a.md": "h1", "b.md": "DIVERSO", "nuovo.md": "h9"}
    )
    report = _check(env)
    assert report["ok"] is False
    assert report["stale"] is True
    assert report["artifacts_corrupted"] is False and report["qdrant_mismatch"] is False
    assert any("stale (docs/)" in p and "1 aggiunti" in p and "1 modificati" in p
               for p in report["problems"])


def test_missing_artifact_marks_corrupted(env):
    env["monkeypatch"].setattr(indexing, "artifact_hashes", lambda: {"graph.json": "g1"})
    report = _check(env)
    assert report["ok"] is False
    assert report["artifacts_corrupted"] is True
    assert report["stale"] is False
    assert any("artefatto mancante" in p and "chunks.json" in p for p in report["problems"])


def test_artifact_hash_mismatch_marks_corrupted(env):
    env["monkeypatch"].setattr(
        indexing, "artifact_hashes", lambda: {"graph.json": "ALTRO", "chunks.json": "k1"}
    )
    report = _check(env)
    assert report["artifacts_corrupted"] is True
    assert any("hash diverso" in p and "graph.json" in p for p in report["problems"])


def test_manifest_without_artifact_hashes_marks_corrupted(env):
    env["manifest"].write_text(json.dumps({"doc_hashes": {}, "code_hashes": {}}), encoding="utf-8")
    env["monkeypatch"].setattr(indexing, "_docs_hashes", lambda: {})
    env["monkeypatch"].setattr(indexing, "_code_hashes", lambda: {})
    report = _check(env)
    assert report["artifacts_corrupted"] is True
    assert any("artifact_hashes" in p for p in report["problems"])


def test_qdrant_count_divergence(env):
    report = _check(env, points=7)  # sidecar ha 3 chunk
    assert report["ok"] is False
    assert report["qdrant_mismatch"] is True
    assert report["stale"] is False and report["artifacts_corrupted"] is False
    assert any("7" in p and "3" in p and "non allineati" in p for p in report["problems"])


def test_qdrant_unreachable_is_reported(env, monkeypatch):
    class _Boom:
        def count(self, collection_name, exact=True):
            raise ConnectionError("giù")

    report = indexing.check_index_integrity(qdrant=_Boom(), emit=lambda m: None)
    assert report["qdrant_mismatch"] is True
    assert any("non verificabile" in p for p in report["problems"])


def test_injected_client_not_closed(env):
    q = _FakeQdrant(3)
    indexing.check_index_integrity(qdrant=q, emit=lambda m: None)
    assert q.closed is False  # il client del server non va chiuso dal check

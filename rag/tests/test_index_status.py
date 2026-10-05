"""Test del manifest di indicizzazione e del rilevamento drift (index.index_status).
Usa i documenti reali in docs/ per gli hash, ma scrive il manifest in una dir temporanea
(sandbox su database/: nessuna versione promossa -> layout flat legacy)."""
import json
from dataclasses import replace

import pytest

from core import artifacts
from core import indexing as index
from core.projects import legacy_project_context


@pytest.mark.parametrize("change", ["modify", "add", "remove"])
def test_code_only_changes_make_project_index_stale(tmp_path, change):
    project = replace(legacy_project_context(), database_dir=tmp_path / "database",
                      docs_dir=tmp_path / "docs", code_dir=tmp_path / "code")
    for directory in (project.database_dir, project.docs_dir, project.code_dir):
        directory.mkdir()
    source = project.code_dir / "app.py"
    source.write_text("value = 1", encoding="utf-8")
    index.write_index_manifest(0, project=project)
    assert index.index_status(project=project)["stale"] is False
    if change == "modify":
        source.write_text("value = 2", encoding="utf-8")
    elif change == "add":
        (project.code_dir / "other.py").write_text("value = 1", encoding="utf-8")
    else:
        source.unlink()
    status = index.index_status(project=project)
    assert status["stale"] is True
    assert status["changed"] == []
    assert status["code_changed"]


def _sandbox_db(monkeypatch, tmp_path):
    """Reindirizza database/ (e la rilevazione del layout legacy) sulla sandbox: il
    manifest della "versione attiva" si risolve nel flat tmp_path/index_manifest.json."""
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "GRAPH_JSON_PATH", tmp_path / "graph.json")
    return tmp_path / "index_manifest.json"


def test_no_manifest_is_stale(tmp_path, monkeypatch):
    _sandbox_db(monkeypatch, tmp_path)
    st = index.index_status()
    assert st["indexed"] is False
    assert st["stale"] is True


def test_fresh_then_tampered_goes_stale(tmp_path, monkeypatch):
    manifest_path = _sandbox_db(monkeypatch, tmp_path)

    # manifest coerente con gli hash correnti di docs/ -> non stale
    index.write_index_manifest(points_count=42, nodes=10, edges=20)
    st = index.index_status()
    assert st["stale"] is False
    assert st["documents"] == 42
    assert st["changed"] == []

    # altero un hash -> il file risulta "modificato" e l'indice diventa stale
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["doc_hashes"], "il manifest deve contenere hash dei documenti"
    key = next(iter(manifest["doc_hashes"]))
    manifest["doc_hashes"][key] = "deadbeef"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    st2 = index.index_status()
    assert st2["stale"] is True
    assert any(c.startswith("~") for c in st2["changed"])  # documento modificato


# ---------------------------------------------------------------------------
# Campo qdrant_collection nel manifest (blue/green Qdrant, S2): per ora vale sempre
# COLLECTION_NAME (layout legacy), ma deve essere presente e i lettori esistenti
# devono restare indifferenti alla sua presenza/assenza.
# ---------------------------------------------------------------------------
def test_manifest_includes_qdrant_collection_field(tmp_path, monkeypatch):
    manifest_path = _sandbox_db(monkeypatch, tmp_path)
    index.write_index_manifest(points_count=1, nodes=1, edges=0)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["qdrant_collection"] == index.COLLECTION_NAME
    # Distinto (per ora identico in valore, ma è un campo a sé) dal "collection"
    # già esistente, che descrive solo il nome configurato in rag_config.yaml.
    assert manifest["collection"] == index.COLLECTION_NAME


def test_index_status_tolerates_manifest_without_qdrant_collection(tmp_path, monkeypatch):
    """Un manifest scritto PRIMA di S2 (nessun campo qdrant_collection) deve continuare
    a essere letto senza eccezioni: index_status non lo richiede."""
    manifest_path = _sandbox_db(monkeypatch, tmp_path)
    index.write_index_manifest(points_count=1, nodes=1, edges=0)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["qdrant_collection"]  # simula un manifest legacy pre-S2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    st = index.index_status()  # non deve sollevare (KeyError o altro)
    assert st["indexed"] is True
    assert st["documents"] == 1

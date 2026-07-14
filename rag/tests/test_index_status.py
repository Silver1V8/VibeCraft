"""Test del manifest di indicizzazione e del rilevamento drift (index.index_status).
Usa i documenti reali in docs/ per gli hash, ma scrive il manifest in una dir temporanea
(sandbox su database/: nessuna versione promossa -> layout flat legacy)."""
import json

from core import artifacts
from core import indexing as index


def _sandbox_db(monkeypatch, tmp_path):
    """Reindirizza database/ (e la rilevazione del layout legacy) sulla sandbox: il
    manifest della "versione attiva" si risolve nel flat tmp_path/index_manifest.json."""
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "GRAPH_JSON_PATH", tmp_path / "graph.json")
    monkeypatch.setattr(artifacts, "GRAPH_SAVE_PATH", tmp_path / "graph.pkl")
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

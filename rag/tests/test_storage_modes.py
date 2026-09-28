"""Storage-mode configuration and immutable-index guardrails."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core import artifacts
from core import indexing as index


RAG_DIR = Path(__file__).resolve().parents[1]


def _config_probe(tmp_path, *, role=None, mode=None):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
               VIBECRAFT_DATABASE_DIR=str(tmp_path / "shared-db"))
    for name, value in (("VIBECRAFT_ROLE", role), ("VIBECRAFT_INDEX_MODE", mode)):
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    code = ("import json; from core.config import ROLE, INDEX_MODE, DATABASE_DIR; "
            "print(json.dumps([ROLE, INDEX_MODE, str(DATABASE_DIR)]))")
    return subprocess.run([sys.executable, "-B", "-c", code], cwd=RAG_DIR, env=env,
                          capture_output=True, text=True)


def test_storage_config_defaults_and_database_override(tmp_path):
    result = _config_probe(tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["standalone", "legacy", str(tmp_path / "shared-db")]


@pytest.mark.parametrize("role", ["reader", "writer"])
def test_reader_and_writer_require_immutable_mode(tmp_path, role):
    result = _config_probe(tmp_path, role=role, mode="legacy")
    assert result.returncode != 0
    assert "richiede VIBECRAFT_INDEX_MODE=immutable" in result.stderr


def test_reader_accepts_explicit_immutable_mode(tmp_path):
    result = _config_probe(tmp_path, role="reader", mode="immutable")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[:2] == ["reader", "immutable"]


def test_full_immutable_activation_is_sticky_even_when_build_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "INDEX_MODE", "immutable")
    monkeypatch.setattr(index, "BGEM3FlagModel",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        index.build_graph_and_index()

    assert artifacts.immutable_index_active()
    assert (tmp_path / artifacts.IMMUTABLE_MARKER_FILENAME).is_file()


def test_observing_immutable_mode_never_creates_reader_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "INDEX_MODE", "immutable")
    assert artifacts.immutable_index_active()
    assert not (tmp_path / artifacts.IMMUTABLE_MARKER_FILENAME).exists()


class _NoMutationQdrant:
    def __getattr__(self, name):
        raise AssertionError(f"Qdrant touched before immutable rejection: {name}")


def test_persistent_marker_rejects_incremental_before_qdrant_without_env(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "INDEX_MODE", "legacy")
    artifacts._atomic_write_text(tmp_path / artifacts.IMMUTABLE_MARKER_FILENAME, "immutable\n")

    with pytest.raises(RuntimeError, match="full rebuild"):
        index.incremental_index(qdrant=_NoMutationQdrant(), embed_model=object())


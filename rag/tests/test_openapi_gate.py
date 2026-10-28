"""OpenAPI spento su bind non-loopback / VIBECRAFT_DISABLE_OPENAPI (quick win)."""
import json
import os
import subprocess
import sys
from pathlib import Path

RAG_DIR = Path(__file__).resolve().parents[1]


def _dump_paths(env: dict) -> set[str]:
    script = (
        "import json\n"
        "import server\n"
        "paths = []\n"
        "for route in server.app.routes:\n"
        "    path = getattr(route, 'path', None)\n"
        "    if path:\n"
        "        paths.append(path)\n"
        "print(json.dumps(paths))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=RAG_DIR, env=env,
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return set(json.loads(result.stdout.strip().splitlines()[-1]))


def test_openapi_routes_present_on_default_local_bind(tmp_path):
    env = dict(os.environ, VIBECRAFT_DATABASE_DIR=str(tmp_path),
               QDRANT_URL="http://127.0.0.1:16333",
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    env.pop("VIBECRAFT_DISABLE_OPENAPI", None)
    env.pop("VIBECRAFT_ENABLE_OPENAPI", None)
    env.pop("VIBECRAFT_HOST", None)
    paths = _dump_paths(env)
    assert {"/docs", "/redoc", "/openapi.json"} <= paths


def test_openapi_routes_absent_when_disabled(tmp_path):
    env = dict(os.environ, VIBECRAFT_DATABASE_DIR=str(tmp_path),
               QDRANT_URL="http://127.0.0.1:16333",
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
               VIBECRAFT_DISABLE_OPENAPI="1")
    env.pop("VIBECRAFT_ENABLE_OPENAPI", None)
    paths = _dump_paths(env)
    assert "/docs" not in paths
    assert "/redoc" not in paths
    assert "/openapi.json" not in paths

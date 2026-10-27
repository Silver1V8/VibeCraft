"""WP6 — project lifecycle matrix: rename/delete/search gaps vs acceptance criteria.

Covers isolation, busy/confirm refusals, external unregister, rename sync, `q`+`stale=0`,
CSRF registration, create/register regression, UI name+id filter helpers, and i18n keys.
Existing suites (`test_projects`, `test_project_api`, `test_security_fixes`) own the
core paths; this module fills gaps and keeps the matrix assertable in one place.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient

from api import deps
from core.projects import ProjectError, ProjectRegistry
from core.writer_lock import writer_lock

_RAG_ROOT = Path(__file__).resolve().parents[1]
_WORKSPACE_JS = _RAG_ROOT / "static" / "pages" / "workspace.js"
_MESSAGES_JS = _RAG_ROOT / "static" / "i18n" / "messages.js"

_LIFECYCLE_I18N_KEYS = (
    "workspace.rename",
    "workspace.renameTitle",
    "workspace.renameSave",
    "workspace.renameFailed",
    "workspace.delete",
    "workspace.deleteTitle",
    "workspace.deleteBodyDestroy",
    "workspace.deleteBodyUnregister",
    "workspace.deleteConfirmLabel",
    "workspace.deleteConfirmHint",
    "workspace.deleteConfirmAction",
    "workspace.deleteBusy",
    "workspace.deleteFailed",
    "workspace.deletePartialCleanup",
    "workspace.searchHintId",
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    import server
    registry = ProjectRegistry(tmp_path / "projects", bootstrap_legacy=False)
    monkeypatch.setattr(deps, "project_registry", lambda: registry, raising=False)
    monkeypatch.setattr(deps, "_project_states", {}, raising=False)
    monkeypatch.setattr(deps, "_snapshots", __import__("collections").OrderedDict(), raising=False)
    monkeypatch.setitem(deps.state, "snapshot", None)
    monkeypatch.setitem(deps.state, "qdrant", None)
    monkeypatch.setitem(deps.state, "embed_model", None)
    monkeypatch.setattr(deps, "BGEM3FlagModel", lambda *a, **k: pytest.fail("eager model load"))
    with TestClient(server.app, base_url="http://127.0.0.1", client=("127.0.0.1", 1234)) as value:
        yield value, registry


# --- AC1/2: rename sync (registry + manifest) + duplicate names via API -------------

def test_patch_rename_syncs_registry_and_manifest(client):
    http, registry = client
    project = registry.create("Prima")
    root, collection = project.root, project.collection_name
    response = http.patch(f"/api/projects/{project.id}", json={"name": "  Dopo  "})
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == project.id and body["name"] == "Dopo"
    updated = registry.get(project.id)
    assert updated.root == root and updated.collection_name == collection
    raw = yaml.safe_load((root / "project.yaml").read_text(encoding="utf-8"))
    assert raw["id"] == project.id and raw["name"] == "Dopo"
    twin = registry.create("Altro")
    dup = http.patch(f"/api/projects/{twin.id}", json={"name": "Dopo"})
    assert dup.status_code == 200
    assert dup.json()["name"] == "Dopo"
    assert {row["id"] for row in http.get("/api/projects").json()["projects"]} == {
        project.id, twin.id,
    }


# --- AC3/4/7: destroy + external unregister + A/B isolation (API, deeper) -----------

def test_delete_isolation_ab_preserves_sibling_files_and_registry(client, tmp_path):
    http, registry = client
    a, b = registry.create("Alpha Keep"), registry.create("Beta Drop")
    (a.root / "docs" / "keep.md").parent.mkdir(parents=True, exist_ok=True)
    (a.root / "docs" / "keep.md").write_text("alpha-secret", encoding="utf-8")
    (b.root / "docs" / "gone.md").parent.mkdir(parents=True, exist_ok=True)
    (b.root / "docs" / "gone.md").write_text("beta-only", encoding="utf-8")
    response = http.delete(
        f"/api/projects/{b.id}", params={"confirm": "Beta Drop", "mode": "destroy"})
    assert response.status_code == 200
    assert not b.root.exists()
    assert (a.root / "docs" / "keep.md").read_text(encoding="utf-8") == "alpha-secret"
    assert registry.get(a.id).name == "Alpha Keep"
    assert http.get(f"/api/projects/{b.id}").status_code == 404
    listed = http.get("/api/projects").json()["projects"]
    assert [row["id"] for row in listed] == [a.id]


def test_delete_external_unregister_leaves_host_tree(client, tmp_path):
    http, registry = client
    host = ProjectRegistry(tmp_path / "host", bootstrap_legacy=False).create("Hosted")
    marker = host.root / "docs" / "stay.md"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("persist", encoding="utf-8")
    registered = registry.register(host.root)
    response = http.delete(
        f"/api/projects/{registered.id}", params={"confirm": registered.name})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "unregister" and body["managed"] is False
    assert body["cleanup"] == {"filesystem": "skipped", "qdrant": "skipped"}
    assert marker.read_text(encoding="utf-8") == "persist"
    assert (host.root / "project.yaml").is_file()
    assert http.get(f"/api/projects/{registered.id}").status_code == 404


# --- AC5: confirm failures (missing / mismatch / casefold name / id) ----------------

def test_delete_confirm_accepts_id_and_name_casefold_refuses_mismatch(client):
    http, registry = client
    project = registry.create("Mixed Case Name")
    wrong = http.delete(f"/api/projects/{project.id}", params={"confirm": "mixed case"})
    assert wrong.status_code == 422
    assert wrong.json()["detail"]["code"] == "project_delete_confirm"
    assert registry.get(project.id).name == "Mixed Case Name"
    by_name = http.delete(
        f"/api/projects/{project.id}",
        params={"confirm": "mixed case name", "mode": "destroy"})
    # confirm matched (casefold on name) — project gone
    assert by_name.status_code == 200
    assert http.get(f"/api/projects/{project.id}").status_code == 404

    other = registry.create("Id Confirm")
    by_id = http.delete(
        f"/api/projects/{other.id}", params={"confirm": other.id, "mode": "destroy"})
    assert by_id.status_code == 200
    assert http.get(f"/api/projects/{other.id}").status_code == 404


# --- AC6: busy 409 via writer lock (HTTP) -------------------------------------------

def test_delete_busy_when_writer_lock_held(client):
    http, registry = client
    project = registry.create("Locked")
    with writer_lock(project=project, timeout_seconds=1):
        response = http.delete(
            f"/api/projects/{project.id}", params={"confirm": project.name})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "project_busy"
    assert registry.get(project.id).name == "Locked"
    assert project.root.is_dir()


# --- AC8: reader may list+search; mutations stay read_only --------------------------

def test_reader_list_and_q_ok_mutations_blocked(client, monkeypatch):
    from api import routes_projects
    import core.config as config
    import core.projects as projects_mod

    http, registry = client
    alpha = registry.create("Alpha Reader")
    beta = registry.create("Beta Reader")
    monkeypatch.setattr(routes_projects, "ROLE", "reader")
    monkeypatch.setattr(deps, "ROLE", "reader")
    monkeypatch.setattr(deps, "API_KEY", "reader-secret")
    monkeypatch.setattr(config, "ROLE", "reader")
    monkeypatch.setattr(projects_mod.installation, "ROLE", "reader")
    headers = {"X-API-Key": "reader-secret"}

    listed = http.get("/api/projects", headers=headers).json()
    assert listed["read_only"] is True
    assert {row["id"] for row in listed["projects"]} == {alpha.id, beta.id}
    filtered = http.get("/api/projects", params={"q": "alpha"}, headers=headers).json()
    assert [row["id"] for row in filtered["projects"]] == [alpha.id]
    assert filtered["read_only"] is True

    renamed = http.patch(
        f"/api/projects/{alpha.id}", json={"name": "Nope"}, headers=headers)
    assert renamed.status_code == 409
    assert renamed.json()["detail"]["code"] == "read_only"
    deleted = http.delete(
        f"/api/projects/{alpha.id}", params={"confirm": alpha.name}, headers=headers)
    assert deleted.status_code == 409
    assert deleted.json()["detail"]["code"] == "read_only"
    assert registry.get(alpha.id).name == "Alpha Reader"


# --- AC9: CSRF dependency still declared on PATCH/DELETE ----------------------------

def test_csrf_dependency_still_on_project_mutations():
    from api import routes_projects

    def deps_for(method: str, path: str):
        for route in routes_projects.router.routes:
            if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
                return [d.dependency for d in route.dependencies]
        raise AssertionError(f"Route missing: {method} {path}")

    for method, path in (
        ("POST", "/api/projects"),
        ("POST", "/api/projects/register"),
        ("PATCH", "/api/projects/{project_id}"),
        ("DELETE", "/api/projects/{project_id}"),
    ):
        assert deps.require_not_cross_site_request in deps_for(method, path)


# --- AC10: q filter + stale=0 together ----------------------------------------------

def test_list_q_with_stale_zero_skips_hash_scan(client, monkeypatch):
    from core import indexing
    from test_project_runtime import indexed

    http, registry = client
    alpha = registry.create("Alpha Filter")
    registry.create("Beta Filter")
    (alpha.docs_dir / "same.md").write_text("original", encoding="utf-8")
    indexed(alpha, "original")
    indexing.write_index_manifest(
        1, version="v1", qdrant_collection=alpha.collection_name + "__v1",
        immutable=True, project=alpha)

    def boom(*_a, **_k):
        raise AssertionError("index_status must not run with stale=0")

    monkeypatch.setattr(indexing, "index_status", boom)
    fast = http.get("/api/projects", params={"q": "alpha", "stale": "0"}).json()
    assert [row["id"] for row in fast["projects"]] == [alpha.id]
    row = fast["projects"][0]
    assert row["index_status"] == "ready"
    assert row["stale"] is None and row.get("stale_pending") is True
    empty = http.get("/api/projects", params={"q": "zzz-none", "stale": "0"}).json()
    assert empty["projects"] == []
    by_id = http.get(
        "/api/projects", params={"q": alpha.id[:6], "stale": "0"}).json()
    assert [row["id"] for row in by_id["projects"]] == [alpha.id]


# --- AC5/partial: 207 cleanup partial leaves project unregistered -------------------

def test_delete_partial_cleanup_returns_207(client, monkeypatch):
    http, registry = client
    project = registry.create("Partial")
    root = project.root
    monkeypatch.setattr(registry, "_cleanup_filesystem", lambda _root: "error")
    response = http.delete(
        f"/api/projects/{project.id}",
        params={"confirm": project.name, "mode": "destroy"})
    assert response.status_code == 207
    body = response.json()
    assert body["code"] == "project_cleanup_partial"
    assert body["cleanup"]["filesystem"] == "error"
    assert http.get(f"/api/projects/{project.id}").status_code == 404
    # Best-effort failed: tree may still exist; registry must not resurrect.
    with pytest.raises(ProjectError) as error:
        registry.get(project.id)
    assert error.value.code == "project_not_found"
    assert root.exists()


# --- create / register regression after rename + delete -----------------------------

def test_create_register_survive_rename_and_delete_cycle(client, tmp_path):
    http, registry = client
    created = http.post("/api/projects", json={"name": "Cycle A"})
    assert created.status_code == 201
    project_id = created.json()["id"]
    renamed = http.patch(f"/api/projects/{project_id}", json={"name": "Cycle Renamed"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Cycle Renamed"

    external = ProjectRegistry(tmp_path / "ext-cycle", bootstrap_legacy=False).create("Ext Cycle")
    registered = http.post("/api/projects/register", json={"root": str(external.root)})
    assert registered.status_code == 201
    ext_id = registered.json()["id"]

    assert http.delete(
        f"/api/projects/{project_id}",
        params={"confirm": "Cycle Renamed", "mode": "destroy"},
    ).status_code == 200
    assert http.delete(
        f"/api/projects/{ext_id}", params={"confirm": ext_id},
    ).status_code == 200
    assert external.root.exists()

    # Destroy removed the managed tree, so the readable id may be reused.
    again = http.post("/api/projects", json={"name": "Cycle A"})
    assert again.status_code == 201
    assert again.json()["name"] == "Cycle A"
    assert again.json()["id"] == project_id  # folder gone → same slug available
    re_reg = http.post("/api/projects/register", json={"root": str(external.root)})
    assert re_reg.status_code == 201
    ids = {row["id"] for row in http.get("/api/projects").json()["projects"]}
    assert again.json()["id"] in ids and re_reg.json()["id"] in ids
    # Unregister-managed orphan still forces a distinct id (folder taken).
    orphan = registry.create("Orphan Cycle")
    orphan_id, orphan_root = orphan.id, orphan.root
    assert http.delete(
        f"/api/projects/{orphan_id}",
        params={"confirm": orphan_id, "mode": "unregister"},
    ).status_code == 200
    assert orphan_root.is_dir()
    replacement = http.post("/api/projects", json={"name": "Orphan Cycle"})
    assert replacement.status_code == 201
    assert replacement.json()["id"] != orphan_id


# --- AC11 (UI slice): name+id filter + confirm match helpers ------------------------

def test_workspace_js_filter_and_confirm_helpers():
    """Node-extract projectMatchesFilter / deleteConfirmMatches (no browser)."""
    script = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const filterMatch = source.match(/function projectMatchesFilter\(project, filter\) \{[\s\S]*?\n\}/);
const confirmMatch = source.match(/function deleteConfirmMatches\(project, value\) \{[\s\S]*?\n\}/);
if (!filterMatch) throw new Error('projectMatchesFilter missing');
if (!confirmMatch) throw new Error('deleteConfirmMatches missing');
eval(filterMatch[0]);
eval(confirmMatch[0]);
const alpha = { id: 'abc123def', name: 'Alpha One' };
const beta = { id: 'zzz999', name: 'Beta Two' };
const out = {
  empty: projectMatchesFilter(alpha, ''),
  byName: projectMatchesFilter(alpha, 'alpha'),
  byId: projectMatchesFilter(alpha, 'abc123'),
  miss: projectMatchesFilter(alpha, 'beta'),
  confirmName: deleteConfirmMatches(alpha, '  Alpha One  '),
  confirmNameCase: deleteConfirmMatches(alpha, 'alpha one'),
  confirmId: deleteConfirmMatches(alpha, 'abc123def'),
  confirmBad: deleteConfirmMatches(alpha, 'Alpha'),
  confirmEmpty: deleteConfirmMatches(alpha, '   '),
  confirmNullProject: deleteConfirmMatches(null, 'Alpha One'),
  betaIdMiss: projectMatchesFilter(beta, 'abc'),
};
process.stdout.write(JSON.stringify(out));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(_WORKSPACE_JS)],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    out = json.loads(completed.stdout)
    assert out["empty"] is True
    assert out["byName"] is True and out["byId"] is True
    assert out["miss"] is False and out["betaIdMiss"] is False
    assert out["confirmName"] is True and out["confirmNameCase"] is True
    assert out["confirmId"] is True
    assert out["confirmBad"] is False and out["confirmEmpty"] is False
    assert out["confirmNullProject"] is False


# --- AC12 (keys present; full UI wiring is WP5) -------------------------------------

def test_lifecycle_i18n_keys_present_in_it_and_en():
    source = _MESSAGES_JS.read_text(encoding="utf-8")
    # messages.js is `const MESSAGES = { it: {...}, en: {...} }` — assert each key once per locale block.
    it_block = re.search(r"\bit\s*:\s*\{", source)
    en_block = re.search(r"\ben\s*:\s*\{", source)
    assert it_block and en_block and it_block.start() < en_block.start()
    it_src, en_src = source[it_block.start():en_block.start()], source[en_block.start():]
    for key in _LIFECYCLE_I18N_KEYS:
        pattern = re.compile(rf"['\"]{re.escape(key)}['\"]\s*:")
        assert pattern.search(it_src), f"missing IT key {key}"
        assert pattern.search(en_src), f"missing EN key {key}"


# --- Qdrant prefix isolation (registry destroy) — AC3/7/14 --------------------------

def test_destroy_drops_only_target_qdrant_namespaces(tmp_path):
    from core import qdrant_versions
    from qdrant_client.models import CreateAliasOperation, DeleteAliasOperation

    class _FakeQdrant:
        def __init__(self, collections, aliases):
            self.collections = set(collections)
            self.aliases = dict(aliases)

        def get_collections(self):
            return SimpleNamespace(
                collections=[SimpleNamespace(name=n) for n in sorted(self.collections)])

        def get_aliases(self):
            return SimpleNamespace(aliases=[
                SimpleNamespace(alias_name=a, collection_name=c)
                for a, c in sorted(self.aliases.items())
            ])

        def update_collection_aliases(self, change_aliases_operations):
            for op in change_aliases_operations:
                if isinstance(op, DeleteAliasOperation):
                    self.aliases.pop(op.delete_alias.alias_name, None)
                elif isinstance(op, CreateAliasOperation):
                    self.aliases[op.create_alias.alias_name] = op.create_alias.collection_name

        def delete_collection(self, collection_name):
            self.collections.discard(collection_name)
            for alias_name in [a for a, c in self.aliases.items() if c == collection_name]:
                del self.aliases[alias_name]

    store = ProjectRegistry(tmp_path / "managed", bootstrap_legacy=False)
    a, b = store.create("A"), store.create("B")
    qdrant = _FakeQdrant(
        collections=[a.collection_name + "__v1", b.collection_name + "__v1", "noise__v1"],
        aliases={
            a.collection_name: a.collection_name + "__v1",
            b.collection_name: b.collection_name + "__v1",
        },
    )
    result = store.delete(a.id, qdrant=qdrant)
    assert result.cleanup["qdrant"] == "ok"
    assert a.collection_name not in qdrant.aliases
    assert a.collection_name + "__v1" not in qdrant.collections
    assert b.collection_name + "__v1" in qdrant.collections
    assert qdrant.aliases[b.collection_name] == b.collection_name + "__v1"
    assert "noise__v1" in qdrant.collections
    # Helper itself never widens beyond the project base.
    report = qdrant_versions.drop_project_qdrant_namespaces(qdrant, base=b.collection_name)
    assert report["errors"] == []
    assert b.collection_name not in qdrant.aliases

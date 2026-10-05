"""Project metadata and isolated paths; no indexing or network calls on opening."""
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import re
import uuid

import yaml

from core import config as installation
from core.artifacts import _atomic_write_json, _atomic_write_text
from core.writer_lock import WriterLockBusyError, writer_lock


class ProjectError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503, code: str = "project_storage_error"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def validate_project_id(project_id: str) -> str:
    if not isinstance(project_id, str) or not re.fullmatch(r"legacy|[0-9a-f]{32}", project_id):
        raise ProjectError("Invalid project ID", status_code=422, code="invalid_project_id")
    return project_id


@dataclass(frozen=True)
class ProjectContext:
    id: str
    name: str
    root: Path
    code_dir: Path
    docs_dir: Path
    changes_dir: Path
    database_dir: Path
    staging_dir: Path
    collection_name: str
    settings: dict
    legacy: bool = False


def legacy_project_context() -> ProjectContext:
    """Historical source for migration/diagnostics, never a registered app context."""
    return ProjectContext(
        "legacy", installation.PROJECT_ROOT.name, installation.PROJECT_ROOT.resolve(),
        installation.CODE_DIR.resolve(), installation.DOCS_DIR.resolve(),
        installation.CHANGES_DIR.resolve(), installation.DATABASE_DIR.resolve(),
        installation.INTAKE_STAGING_DIR.resolve(), installation.COLLECTION_NAME,
        deepcopy(installation.config), True,
    )


def _unlinked(path: Path) -> Path:
    # resolve() alone would silently accept a junction into a different project.
    for component in (path, *path.parents):
        if component.is_symlink() or component.is_junction():
            raise ProjectError(f"Linked project path forbidden: {component}", status_code=422,
                               code="invalid_project_path")
    return path.resolve()


def _raise_walk_error(error: OSError) -> None:
    raise error


def _name(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectError("Project name must not be empty", status_code=422, code="invalid_project_name")
    return value.strip()


def _settings(overrides) -> dict:
    """Allow only existing authority/retrieval/eval and trusted local argv settings."""
    allowed = {key: installation.config.get(key, {}) for key in
               ("authority", "retrieval", "eval_gate", "eval_multihop", "verification")}
    if not isinstance(overrides, dict) or overrides.keys() - allowed.keys():
        raise ValueError("Unknown project settings block")

    def merge(target, source, schema, trail=""):
        if not isinstance(source, dict):
            raise ValueError(f"Expected settings mapping: {trail}")
        for key, value in source.items():
            if not isinstance(key, str) or key not in schema:
                raise ValueError(f"Unknown project setting: {trail}{key}")
            default = schema[key]
            location = trail + key
            if isinstance(default, dict):
                if location == "authority.class_weights":
                    if not isinstance(value, dict) or any(
                        not isinstance(k, str) or type(v) not in (int, float) or not math.isfinite(v)
                        for k, v in value.items()
                    ):
                        raise ValueError("class_weights must contain finite numbers")
                    target.setdefault(key, {}).update(deepcopy(value))
                elif location == "verification.commands":
                    if not isinstance(value, dict) or any(
                        not isinstance(k, str) or not k or k in (".", "..") or "/" in k or "\\" in k
                        or not isinstance(v, list) or not v
                        or any(not isinstance(arg, str) or not arg or "\x00" in arg for arg in v)
                        for k, v in value.items()
                    ):
                        raise ValueError("verification commands must be nonempty argv lists")
                    target.setdefault(key, {}).update(deepcopy(value))
                else:
                    merge(target.setdefault(key, {}), value, default, location + ".")
            else:
                valid = (type(value) is bool if isinstance(default, bool) else
                         type(value) is int if isinstance(default, int) else
                         type(value) in (int, float) and math.isfinite(value) if isinstance(default, float) else
                         isinstance(value, type(default)))
                if not valid:
                    raise ValueError(f"Invalid type for project setting: {location}")
                target[key] = deepcopy(value)

    settings = deepcopy(installation.config)
    merge(settings, overrides, allowed)
    return settings


def _manifest(root: Path) -> ProjectContext:
    try:
        root = _unlinked(root)
        if not root.is_dir():
            raise ValueError("Project root is missing")
        path = _unlinked(root / "project.yaml")
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_ManifestLoader)
        if (not isinstance(raw, dict) or type(raw.get("schema_version")) is not int
                or raw["schema_version"] != 1
                or raw.keys() - {"schema_version", "id", "name", "settings"}):
            raise ValueError("Invalid project manifest schema")
        project_id = validate_project_id(raw.get("id"))
        name = _name(raw.get("name"))
        settings = _settings(raw.get("settings", {}))
        paths = [root / part for part in ("code", "docs", "changes", "database", "database/staging")]
        for directory in [*paths, *(root / "database" / part for part in ("versions", "pipeline", "eval"))]:
            _unlinked(directory)
            if directory.exists() and not directory.is_dir():
                raise ValueError(f"Expected project directory: {directory}")
        return ProjectContext(project_id, name, root, *paths, "vibecraft_" + project_id, settings)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        raise ProjectError(f"Invalid project manifest: {exc}", status_code=422,
                           code="invalid_project_manifest") from exc


def _has_legacy_data(project: ProjectContext) -> bool:
    if any((project.database_dir / filename).is_file() for filename in
           ("CURRENT", "graph.json", "colbert.npz", "chunks.json", "index_manifest.json")):
        return True
    for directory in (project.code_dir, project.docs_dir, project.changes_dir):
        if directory.is_dir():
            for parent, directories, files in directory.walk(on_error=_raise_walk_error):
                directories[:] = [name for name in directories if name not in installation.CODE_EXCLUDED_DIRS]
                if any(not name.startswith(".") and (parent / name).is_file()
                       and (parent / name).stat().st_size for name in files):
                    return True
    return False


def _migration_required() -> ProjectError:
    return ProjectError("Run the explicit project layout migration", status_code=409,
                        code="project_migration_required")


def _has_historical_state(project: ProjectContext) -> bool:
    for filename in ("CURRENT", "graph.json", "colbert.npz", "chunks.json", "index_manifest.json"):
        path = _unlinked(project.database_dir / filename)
        if path.exists():
            return True
    for directory in (project.code_dir, project.changes_dir, project.staging_dir,
                      project.database_dir / "pipeline", project.database_dir / "versions"):
        _unlinked(directory)
        if directory.is_dir():
            for parent, directories, files in directory.walk(on_error=_raise_walk_error):
                for name in [*directories, *files]:
                    _unlinked(parent / name)
                if any(name not in (".gitkeep", ".gitignore", ".writer.lock")
                       for name in files):
                    return True
    return False


def _create_project_root(root: Path, project_id: str, name: str,
                         settings: dict | None = None, *, resume: bool = False) -> ProjectContext:
    validate_project_id(project_id)
    name = _name(name)
    _settings(settings or {})
    _unlinked(root)
    root.mkdir(exist_ok=resume)  # resume is only used after a verified ownership checkpoint.
    if resume and (root / "project.yaml").exists():
        existing = _manifest(root)
        if existing.id != project_id or existing.name != name or existing.settings != _settings(settings or {}):
            raise ProjectError("Prepared project manifest changed")
    for directory in ("code", "docs", "changes", "database/versions", "database/staging",
                      "database/pipeline", "database/eval"):
        (root / directory).mkdir(parents=True, exist_ok=resume)
    manifest = {"schema_version": 1, "id": project_id, "name": name}
    if settings:
        manifest["settings"] = settings
    _atomic_write_text(root / "project.yaml", yaml.safe_dump(manifest, allow_unicode=True))
    return _manifest(root)


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


class _ManifestLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        return _json_object([(self.construct_object(key, deep=deep),
                              self.construct_object(value, deep=deep)) for key, value in node.value])


class ProjectRegistry:
    def __init__(self, projects_dir: Path | None = None, *, legacy_context: ProjectContext | None = None,
                 bootstrap_legacy: bool = True, readonly: bool = False, initialize: bool = True):
        path = Path(projects_dir if projects_dir is not None else installation.PROJECTS_DIR).expanduser()
        if not path.is_absolute():
            raise ProjectError("Projects directory must be absolute", status_code=422,
                               code="invalid_project_path")
        self.projects_dir = _unlinked(path)
        self.registry_path = self.projects_dir / "projects.json"
        self.lock_path = self.projects_dir / ".projects.lock"
        self._legacy = legacy_context if legacy_context is not None else legacy_project_context()
        self._readonly = readonly
        self._registry_seen = self.registry_path.exists()
        if readonly or installation.ROLE == "reader" or not initialize:
            self._read()
            return
        with self._lock():
            if self.registry_path.exists():
                self._read()
            else:
                records = []
                if bootstrap_legacy:
                    project = self._bootstrap_initial_project()
                    if project is not None:
                        records.append(self._record(project))
                self._write(records)

    def _bootstrap_initial_project(self) -> ProjectContext | None:
        if _has_historical_state(self._legacy):
            raise _migration_required()
        if not _has_legacy_data(self._legacy):
            return None
        from core.project_migration import prepare_project_copy
        root = self.projects_dir / "legacy"
        checkpoint_path = self.projects_dir / ".initial-project-copy.json"
        _unlinked(root)
        _unlinked(checkpoint_path)
        if root.exists():
            if not checkpoint_path.exists():
                raise ProjectError("Initial project destination already exists", status_code=409,
                                   code="project_conflict")
        project = replace(self._legacy, root=root, code_dir=root / "code", docs_dir=root / "docs",
                          changes_dir=root / "changes", database_dir=root / "database",
                          staging_dir=root / "database" / "staging", collection_name="vibecraft_legacy",
                          legacy=False)
        prepare_project_copy(self._legacy, project, checkpoint_path=checkpoint_path, include_history=False)
        return _manifest(root)

    @contextmanager
    def _lock(self):
        try:
            _unlinked(self.projects_dir)
            _unlinked(self.registry_path)
            _unlinked(self.lock_path)
            with writer_lock(lock_path=self.lock_path):
                yield
        except (OSError, WriterLockBusyError) as exc:
            raise ProjectError(f"Project registry storage unavailable: {exc}") from exc

    @staticmethod
    def _record(project):
        return {"id": project.id, "name": project.name, "root": str(project.root.resolve()),
                "legacy": project.legacy}

    def _read(self):
        try:
            _unlinked(self.projects_dir)
            _unlinked(self.registry_path)
            if not self.registry_path.exists():
                if self._registry_seen:
                    raise ValueError("Initialized project registry is missing")
                return []
            data = json.loads(self.registry_path.read_text(encoding="utf-8"), object_pairs_hook=_json_object)
            if (not isinstance(data, dict) or data.keys() != {"schema_version", "projects"}
                    or type(data["schema_version"]) is not int or data["schema_version"] not in (1, 2)
                    or not isinstance(data["projects"], list)):
                raise ValueError("Invalid registry schema")
            ids, roots = set(), set()
            for record in data["projects"]:
                if not isinstance(record, dict) or record.keys() != {"id", "name", "root", "legacy"}:
                    raise ValueError("Invalid registry record")
                validate_project_id(record["id"])
                _name(record["name"])
                expected_legacy = data["schema_version"] == 1 and record["id"] == "legacy"
                if type(record["legacy"]) is not bool or record["legacy"] != expected_legacy:
                    raise ValueError("Invalid legacy record")
                if not isinstance(record["root"], str) or not Path(record["root"]).is_absolute():
                    raise ValueError("Registry root must be absolute")
                root = _unlinked(Path(record["root"]))
                if str(root) != record["root"]:
                    raise ValueError("Registry root must be canonical")
                if record["id"] in ids or root in roots:
                    raise ValueError("Duplicate registry ID or root")
                ids.add(record["id"])
                roots.add(root)
            self._registry_seen = True
            return data["projects"]
        except (OSError, ValueError, ProjectError) as exc:
            raise ProjectError(f"Cannot read project registry: {exc}") from exc

    def _write(self, records):
        if any(record["legacy"] for record in records):
            raise _migration_required()
        _atomic_write_json(self.registry_path, {"schema_version": 2, "projects": records})
        self._registry_seen = True

    def _context(self, record):
        if record["legacy"]:
            raise _migration_required()
        try:
            project = _manifest(Path(record["root"]))
            if project.id != record["id"] or project.name != record["name"]:
                raise ValueError("Registry and project manifest disagree")
            return project
        except (ValueError, ProjectError) as exc:
            raise ProjectError(f"Cannot open registered project: {exc}") from exc

    def historical_project(self) -> ProjectContext | None:
        records = self._read()
        historical = next((record for record in records if record["legacy"]), None)
        if historical is None:
            if any(record["id"] == "legacy" for record in records) or not (
                    _has_historical_state(self._legacy) or _has_legacy_data(self._legacy)):
                return None
        elif Path(historical["root"]) != self._legacy.root.resolve():
            raise ProjectError("Historical installation root changed")
        for path in (self._legacy.root, self._legacy.code_dir, self._legacy.docs_dir,
                     self._legacy.changes_dir, self._legacy.database_dir, self._legacy.staging_dir):
            _unlinked(path)
        if not self._legacy.root.is_dir():
            raise ProjectError("Historical installation root missing")
        return replace(self._legacy, name=historical["name"] if historical else self._legacy.name,
                       settings=deepcopy(self._legacy.settings))

    def list(self) -> list[ProjectContext]:
        return [self._context(record) for record in self._read()]

    def records(self) -> list[dict]:
        """Validated registry metadata, without opening individual project manifests."""
        return self._read()

    def get(self, project_id: str) -> ProjectContext:
        validate_project_id(project_id)
        for record in self._read():
            if record["id"] == project_id:
                return self._context(record)
        raise ProjectError("Project not found", status_code=404, code="project_not_found")

    def _require_writer(self):
        if self._readonly or installation.ROLE == "reader":
            raise ProjectError("Project registry is read-only", status_code=409, code="read_only")

    def _append(self, project, records):
        if self.projects_dir.is_relative_to(project.root):
            raise ProjectError("Project root contains registry storage", status_code=409,
                               code="project_conflict")
        for record in records:
            root = Path(record["root"])
            if project.id == record["id"] or project.root == root:
                raise ProjectError("Project ID or root already registered", status_code=409,
                                   code="project_conflict")
            existing = self._context(record)
            protected = (existing.root,)
            if any(project.root.is_relative_to(path) or path.is_relative_to(project.root) for path in protected):
                raise ProjectError("Project roots overlap", status_code=409, code="project_conflict")
        self._write([*records, self._record(project)])

    def create(self, name: str) -> ProjectContext:
        self._require_writer()
        name = _name(name)
        with self._lock():
            records = self._read()
            if any(record["legacy"] for record in records):
                raise _migration_required()
            project_id = uuid.uuid4().hex
            root = self.projects_dir / project_id
            project = _create_project_root(root, project_id, name)
            self._append(project, records)
            return project
    def register(self, root: Path) -> ProjectContext:
        self._require_writer()
        path = Path(root).expanduser()
        if not path.is_absolute():
            raise ProjectError("Project root must be absolute", status_code=422, code="invalid_project_path")
        with self._lock():
            records = self._read()
            if any(record["legacy"] for record in records):
                raise _migration_required()
            project = _manifest(path)
            self._append(project, records)
            return project


def resolve_registered_project(project_id: str | None = None, *,
                               registry: ProjectRegistry | None = None) -> ProjectContext:
    registry = registry if registry is not None else ProjectRegistry(readonly=True)
    try:
        return registry.get("legacy" if project_id is None else project_id)
    except ProjectError as exc:
        if project_id is None and exc.code == "project_not_found":
            raise ProjectError("Select a project", status_code=409, code="project_required") from exc
        raise

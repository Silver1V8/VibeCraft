"""Verified copies and explicit conversion of installation data into a project."""
import hashlib
import json
from pathlib import Path
import os
import shutil
import tempfile
from dataclasses import replace

from core.artifacts import _atomic_write, _atomic_write_json
from core.projects import ProjectContext, ProjectError, _unlinked


def _inventory(root: Path, *, copying: bool = False) -> dict[str, str]:
    _unlinked(root)
    result = {}
    if not root.exists():
        return result
    if root.is_file():
        with root.open("rb") as stream:
            return {"": hashlib.file_digest(stream, "sha256").hexdigest()}
    if not root.is_dir():
        raise ProjectError("Copy source must be a file or directory")
    for parent, directories, files in root.walk():
        for name in [*directories, *files]:
            _unlinked(parent / name)
        for name in files:
            if name.startswith(".vibecraft-copy-"):
                if copying:
                    continue
                raise ProjectError("Reserved temporary filename in source")
            path = parent / name
            with path.open("rb") as stream:
                result[path.relative_to(root).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    return result


def copy_source_tree(source: Path, target: Path) -> dict[str, str]:
    source, target = _unlinked(source), _unlinked(target)
    if source.is_relative_to(target) or target.is_relative_to(source):
        raise ProjectError("Copy source and destination overlap")
    expected = _inventory(source)
    existing = _inventory(target, copying=True)
    if any(expected.get(path) != digest for path, digest in existing.items()):
        raise ProjectError("Copy destination contains conflicting files", status_code=409,
                           code="project_conflict")
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for parent, directories, _ in source.walk():
            for name in directories:
                destination = _unlinked(target / (parent / name).relative_to(source))
                destination.mkdir(parents=True, exist_ok=True)
    for relative, digest in expected.items():
        destination = _unlinked(target / relative)
        if existing.get(relative) == digest:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".vibecraft-copy-", dir=destination.parent)
        os.close(fd)
        try:
            shutil.copy2(source / relative, temporary)
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
    if _inventory(source) != expected or _inventory(target, copying=True) != expected:
        raise ProjectError("Source changed or copied hashes do not match")
    return expected


def prepare_project_copy(source: ProjectContext, target: ProjectContext, *,
                         checkpoint_path: Path, include_history: bool) -> dict:
    _unlinked(checkpoint_path)
    mappings = [(source.docs_dir, target.docs_dir), (source.code_dir, target.code_dir)]
    if include_history:
        from core import config
        mappings.extend([(source.changes_dir, target.changes_dir),
                         (source.staging_dir, target.staging_dir),
                         (source.database_dir / "pipeline", target.database_dir / "pipeline")])
        golden = _unlinked(config.GOLDEN_SET_PATH)
        if golden.exists():
            from core.eval_gate import load_golden_cases
            try:
                load_golden_cases(golden)
            except (ValueError, OSError) as exc:
                raise ProjectError("Historical golden set is invalid") from exc
            mappings.append((golden, target.root / "eval" / "golden.yaml"))
    identity = {str(_unlinked(old)): str(_unlinked(new)) for old, new in mappings}
    for old, new in mappings:
        if old.is_relative_to(new) or new.is_relative_to(old):
            raise ProjectError("Copy source and destination overlap")
    inventories = {str(old.resolve()): _inventory(old) for old, _ in mappings}
    if checkpoint_path.exists():
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if (type(checkpoint["schema_version"]) is not int or checkpoint["schema_version"] != 1
                    or checkpoint["paths"] != identity
                    or checkpoint["inventories"] != inventories
                    or checkpoint["phase"] not in ("prepared", "copied", "index_verified", "published")):
                raise ValueError("Copy checkpoint does not match source")
        except (ValueError, KeyError, TypeError) as exc:
            raise ProjectError("Invalid copy checkpoint") from exc
    else:
        if any(_inventory(new) for _, new in mappings):
            raise ProjectError("Copy destination is not empty", status_code=409, code="project_conflict")
        checkpoint = {"schema_version": 1, "paths": identity, "inventories": inventories, "phase": "prepared"}
        _atomic_write_json(checkpoint_path, checkpoint)
    # Persist ownership BEFORE creating the layout so crashes are safely resumable.
    from core import projects
    overrides = {key: target.settings[key] for key in
                 ("authority", "retrieval", "eval_gate", "eval_multihop", "verification")
                 if key in target.settings}
    projects._create_project_root(target.root, target.id, target.name, overrides, resume=True)
    for old, new in mappings:
        if copy_source_tree(old, new) != inventories[str(old.resolve())]:
            raise ProjectError("Source changed while copying")
    if checkpoint["phase"] == "prepared":
        checkpoint["phase"] = "copied"
        _atomic_write_json(checkpoint_path, checkpoint)
    return checkpoint


def migrate_legacy_project(registry, *, qdrant=None, embed_model=None, emit=None,
                           repair: bool = False) -> ProjectContext:
    """Offline conversion. Registry publication is the last mutation of active state."""
    from core import projects
    from core.writer_lock import writer_lock
    registry._require_writer()
    with registry._lock():
        records = registry.records()
        checkpoint_path = _unlinked(registry.projects_dir / ".legacy-migration.json")
        source = registry.historical_project()
        if source is None:
            project = registry.get("legacy")
            if checkpoint_path.exists():
                checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                if checkpoint.get("phase") == "index_verified":
                    checkpoint["phase"] = "published"
                    _atomic_write_json(checkpoint_path, checkpoint)
            return project
        root = _unlinked(registry.projects_dir / "legacy")
        if root.exists() and not checkpoint_path.exists():
            raise ProjectError("Migration destination already exists", status_code=409, code="project_conflict")
        for record in records:
            other = Path(record["root"])
            if not record["legacy"] and (root.is_relative_to(other) or other.is_relative_to(root)):
                raise ProjectError("Migration destination overlaps a registered project")
        target = replace(source, root=root, code_dir=root / "code", docs_dir=root / "docs",
                         changes_dir=root / "changes", database_dir=root / "database",
                         staging_dir=root / "database" / "staging", collection_name="vibecraft_legacy",
                         legacy=False)
        backup = _unlinked(registry.projects_dir / "projects.v1.backup.json")
        original = registry.registry_path.read_bytes() if registry.registry_path.exists() else None
        if backup.exists() and backup.read_bytes() != original:
            raise ProjectError("Existing registry backup differs from the original")
        with writer_lock(project=source):
            if original is not None and not backup.exists():
                _atomic_write(backup, lambda stream: stream.write(original))
            # Unpublished target has no admitted writer; acquire its lock after owned layout creation.
            checkpoint = prepare_project_copy(source, target, checkpoint_path=checkpoint_path, include_history=True)
            target = projects._manifest(root)
            with writer_lock(project=target):
                pipeline = checkpoint["inventories"].get(str((source.database_dir / "pipeline").resolve()), {})
                _atomic_write_json(target.database_dir / ".migrated-validations.json",
                                   {path: digest for path, digest in pipeline.items()
                                    if path.startswith("validations/") and path.endswith(".json")})
                indexed = any(_unlinked(source.database_dir / name).exists() for name in
                              ("CURRENT", "graph.json", "colbert.npz", "chunks.json", "index_manifest.json"))
                if indexed:
                    from core import config, indexing, artifacts, qdrant_versions
                    from qdrant_client import QdrantClient
                    owned_client = qdrant is None
                    if owned_client:
                        qdrant = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY)
                    try:
                        names = {collection.name for collection in qdrant.get_collections().collections}
                        aliases = {alias.alias_name for alias in qdrant.get_aliases().aliases}
                        occupied = {name for name in names | aliases
                                    if name == target.collection_name or name.startswith(target.collection_name + "__")}
                        version = checkpoint.get("version")
                        if version:
                            expected = qdrant_versions._qdrant_collection_for_version(version, project=target)
                            if occupied - {expected, target.collection_name} or target.collection_name in names:
                                raise ProjectError("Migration namespace contains foreign collections")
                            if artifacts.current_version(project=target) != version:
                                raise ProjectError("Migration CURRENT changed")
                            if repair and checkpoint["phase"] == "copied":
                                # CURRENT is written only after the promotion gate passes.
                                manifest = artifacts._read_manifest(project=target)
                                if (not manifest or not manifest.get("artifact_hashes")
                                        or manifest["artifact_hashes"] != artifacts.artifact_hashes(
                                            version, deep=True, project=target)):
                                    raise ProjectError("Migration candidate artifacts are corrupt")
                                loaded = artifacts.load_artifacts(required=("graph", "chunks"),
                                                                  version=version, skip_colbert=True, project=target)
                                if qdrant.count(collection_name=expected, exact=True).count != len(loaded.chunks_store):
                                    raise ProjectError("Migration candidate vectors are incomplete")
                                qdrant_versions._swap_alias(qdrant, target.collection_name, expected)
                        else:
                            if occupied or source.collection_name == target.collection_name:
                                raise ProjectError("Migration namespace already occupied", status_code=409,
                                                   code="project_conflict")
                            try:
                                version = indexing.build_graph_and_index(qdrant=qdrant, embed_model=embed_model,
                                                                        emit=emit, promote=True, project=target)
                            except Exception:
                                promoted = artifacts.current_version(project=target)
                                if promoted:
                                    checkpoint["version"] = promoted
                                    _atomic_write_json(checkpoint_path, checkpoint)
                                raise
                        expected = qdrant_versions._qdrant_collection_for_version(version, project=target)
                        if (artifacts.current_version(project=target) != version
                                or qdrant_versions._read_alias_target(qdrant, target.collection_name) != expected
                                or indexing.check_index_integrity(qdrant, project=target)["ok"] is not True):
                            raise ProjectError("Migration index failed promotion or integrity verification")
                        checkpoint["version"] = version
                    finally:
                        if owned_client:
                            qdrant.close()
                checkpoint["phase"] = "index_verified"
                _atomic_write_json(checkpoint_path, checkpoint)
                # Verify source/copy hashes once more immediately before publishing.
                prepare_project_copy(source, target, checkpoint_path=checkpoint_path, include_history=True)
                migrated = [record for record in records if record["id"] != "legacy"]
                registry._write([*migrated, registry._record(target)])
                checkpoint["phase"] = "published"
                _atomic_write_json(checkpoint_path, checkpoint)
                return target

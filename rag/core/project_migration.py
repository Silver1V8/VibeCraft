"""Verified copies and explicit conversion of installation data into a project."""
import hashlib
import json
from pathlib import Path
import os
import shutil
import tempfile

from core.artifacts import _atomic_write_json
from core.projects import ProjectContext, ProjectError, _unlinked


def _inventory(root: Path, *, copying: bool = False) -> dict[str, str]:
    _unlinked(root)
    result = {}
    if not root.exists():
        return result
    if not root.is_dir():
        raise ProjectError("Copy source must be a directory")
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
        mappings.extend([(source.changes_dir, target.changes_dir),
                         (source.staging_dir, target.staging_dir),
                         (source.database_dir / "pipeline", target.database_dir / "pipeline")])
    identity = {str(_unlinked(old)): str(_unlinked(new)) for old, new in mappings}
    for old, new in mappings:
        if old.is_relative_to(new) or new.is_relative_to(old):
            raise ProjectError("Copy source and destination overlap")
    inventories = {str(old.resolve()): _inventory(old) for old, _ in mappings}
    if checkpoint_path.exists():
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if (checkpoint["schema_version"] != 1 or checkpoint["paths"] != identity
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

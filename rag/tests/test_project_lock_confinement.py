"""Real lock-path links must never create/truncate files in a foreign project."""
import os
import subprocess

import pytest

from core.projects import ProjectRegistry
from core.writer_lock import try_version_lease, writer_lock


def directory_link(link, target):
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                       check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.fixture
def projects(tmp_path):
    registry = ProjectRegistry(tmp_path / "projects", bootstrap_legacy=False)
    return registry, registry.create("A"), registry.create("B")


@pytest.mark.parametrize("operation", ["writer", "lease"])
def test_captured_database_junction_never_touches_foreign_locks(projects, operation):
    _, a, b = projects
    victim = b.database_dir / ".writer.lock"
    victim.write_bytes(b"B_SENTINEL_UNCHANGED")
    a.database_dir.rename(a.root / "retained-database")
    directory_link(a.database_dir, b.database_dir)
    try:
        with pytest.raises(ValueError, match="[Ll]ink"):
            if operation == "writer":
                with writer_lock(project=a):
                    pytest.fail("foreign writer lock admitted")
            else:
                with try_version_lease(a.database_dir, "v1"):
                    pytest.fail("foreign reader lease admitted")
        assert victim.read_bytes() == b"B_SENTINEL_UNCHANGED"
        assert not (b.database_dir / ".reader-locks").exists()
    finally:
        if os.name == "nt":
            a.database_dir.rmdir()
        else:
            a.database_dir.unlink()


@pytest.mark.parametrize("operation", ["writer", "lease"])
def test_captured_project_ancestor_link_never_creates_foreign_lock(projects, tmp_path, operation):
    _, a, _ = projects
    foreign_root = tmp_path / "foreign"
    foreign_root.mkdir()
    a.root.rename(a.root.with_name(a.id + "-retained"))
    directory_link(a.root, foreign_root)
    try:
        with pytest.raises(ValueError, match="[Ll]ink"):
            if operation == "writer":
                with writer_lock(project=a):
                    pytest.fail("foreign writer root admitted")
            else:
                with try_version_lease(a.database_dir, "v1"):
                    pytest.fail("foreign reader root admitted")
        assert list(foreign_root.iterdir()) == []
    finally:
        if os.name == "nt":
            a.root.rmdir()
        else:
            a.root.unlink()


def test_writer_file_link_before_admission_preserves_foreign_document(projects):
    registry, a, b = projects
    victim = b.docs_dir / "victim.md"
    victim.write_bytes(b"B_DOCUMENT_UNCHANGED")
    link = a.database_dir / ".writer.lock"
    try:
        link.symlink_to(victim)
    except OSError as exc:
        if os.name == "nt" and exc.winerror == 1314:
            pytest.skip(f"file symlink privilege unavailable: {exc}")
        raise
    admitted = registry.get(a.id)
    with pytest.raises(ValueError, match="[Ll]ink"):
        with writer_lock(project=admitted):
            pytest.fail("foreign document writer lock admitted")
    assert victim.read_bytes() == b"B_DOCUMENT_UNCHANGED"


def test_explicit_lock_path_and_ordinary_project_remain_usable(projects, tmp_path):
    _, a, b = projects
    before_b = set(b.database_dir.iterdir())
    with writer_lock(project=a):
        assert (a.database_dir / ".writer.lock").read_text().startswith("pid=")
    custom = tmp_path / "new directory" / "explicit.lock"
    with writer_lock(lock_path=custom):
        assert custom.read_text().startswith("pid=")
    with try_version_lease(a.database_dir, "v1"):
        assert (a.database_dir / ".reader-locks/v1.lock").is_file()
    assert set(b.database_dir.iterdir()) == before_b

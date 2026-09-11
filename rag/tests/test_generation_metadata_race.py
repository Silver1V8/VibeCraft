"""I metadati tardivi non annullano review o refine già completati."""
import pytest

from core import doc_generation, intake, writer_lock


@pytest.mark.parametrize("status", ["approved", "rejected", "staged"])
def test_generation_metadata_preserves_latest_transition(tmp_path, monkeypatch, status):
    monkeypatch.setattr(writer_lock, "DATABASE_DIR", tmp_path / "database")
    paths = intake.ensure_staging_dirs(tmp_path / "staging")
    original = {"id": "generated", "status": "staged", "metadata": {"sha256": "original"},
                "files": {"markdown": "raw.md"}}
    intake._append_journal(paths, original)
    latest = {**original, "status": status, "review_note": "keep",
              "metadata": {**original["metadata"], "reviewed": True},
              "files": {"markdown": "refined.md"}}
    intake._append_journal(paths, latest)

    result = doc_generation._attach_generation_metadata(
        tmp_path / "staging", original, {"modello": "test-model"})

    expected = {**latest, "metadata": {**latest["metadata"], "modello": "test-model"}}
    assert result == expected
    assert intake._journal_state(paths)[original["id"]] == expected


def test_generation_metadata_reads_and_appends_under_writer_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(writer_lock, "DATABASE_DIR", tmp_path / "database")
    paths = intake.ensure_staging_dirs(tmp_path / "staging")
    record = {"id": "generated", "status": "staged", "metadata": {}}
    intake._append_journal(paths, record)
    read_state, append = intake._journal_state, intake._append_journal

    def assert_locked():
        with pytest.raises(writer_lock.WriterLockBusyError):
            with writer_lock.writer_lock(timeout_seconds=0):
                pass

    def locked_read(paths):
        assert_locked()
        return read_state(paths)

    def locked_append(paths, updated):
        assert_locked()
        append(paths, updated)

    monkeypatch.setattr(intake, "_journal_state", locked_read)
    monkeypatch.setattr(intake, "_append_journal", locked_append)
    doc_generation._attach_generation_metadata(tmp_path / "staging", record, {"modello": "test"})

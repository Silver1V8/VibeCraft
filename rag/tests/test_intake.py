"""Test dello scaffold di staging per Intake & Import (S0, piano:
docs/00_meta_governance/piano_intake_import.md): solo bootstrap delle cartelle e del journal,
nessun endpoint né logica di stage/approve/reject (arrivano in S2)."""
from core.intake import ensure_staging_dirs


def test_ensure_staging_dirs_creates_scaffold(tmp_path):
    paths = ensure_staging_dirs(base_dir=tmp_path)

    assert paths["docs"] == tmp_path / "docs"
    assert paths["projects"] == tmp_path / "projects"
    assert paths["rejected"] == tmp_path / "rejected"
    assert paths["journal"] == tmp_path / "intake.jsonl"

    for key in ("docs", "projects", "rejected"):
        assert paths[key].is_dir()
    assert paths["journal"].is_file()
    assert paths["journal"].read_text(encoding="utf-8") == ""


def test_ensure_staging_dirs_is_idempotent(tmp_path):
    """Una seconda chiamata non deve fallire né svuotare un journal già scritto."""
    ensure_staging_dirs(base_dir=tmp_path)
    journal = tmp_path / "intake.jsonl"
    journal.write_text('{"id": "già presente"}\n', encoding="utf-8")

    ensure_staging_dirs(base_dir=tmp_path)

    assert journal.read_text(encoding="utf-8") == '{"id": "già presente"}\n'


def test_ensure_staging_dirs_default_uses_intake_config():
    """Senza base_dir, i percorsi derivano da INTAKE_STAGING_DIR (rag_config.yaml →
    intake.staging_dir), non da un default hardcoded nel modulo."""
    from core.config import INTAKE_STAGING_DIR
    from core.intake import STAGING_DOCS_DIR, STAGING_PROJECTS_DIR, STAGING_REJECTED_DIR, INTAKE_JOURNAL_PATH

    assert STAGING_DOCS_DIR == INTAKE_STAGING_DIR / "docs"
    assert STAGING_PROJECTS_DIR == INTAKE_STAGING_DIR / "projects"
    assert STAGING_REJECTED_DIR == INTAKE_STAGING_DIR / "rejected"
    assert INTAKE_JOURNAL_PATH == INTAKE_STAGING_DIR / "intake.jsonl"

"""Scaffold dell'area di staging per l'evoluzione Intake & Import (piano:
docs/00_meta_governance/piano_intake_import.md). Questa è la sola parte prevista da S0:
bootstrap lazy delle cartelle e del journal append-only. Il ciclo stage/preview/approve/reject
(S2) e i job di generazione/import (S3/S5) si aggiungono a questo stesso modulo, riusando
STAGING_*_DIR e INTAKE_JOURNAL_PATH definiti qui.

Nessuna scrittura in docs/ o code/ avviene da questo modulo: solo staging/."""
from pathlib import Path

from core.config import INTAKE_STAGING_DIR

# Sotto-cartelle dell'area di staging: 'docs' per i documenti (generati o importati) in attesa
# di review, 'projects' per i progetti importati da path locale (S5, coi rispettivi backup),
# 'rejected' per ciò che viene rifiutato — mai cancellato, solo spostato qui per tracciabilità.
STAGING_DOCS_DIR = INTAKE_STAGING_DIR / "docs"
STAGING_PROJECTS_DIR = INTAKE_STAGING_DIR / "projects"
STAGING_REJECTED_DIR = INTAKE_STAGING_DIR / "rejected"
# Journal append-only (stesso pattern di database/reindex_jobs.jsonl, vedi api/reindex.py):
# ogni transizione di stato di un documento/progetto in staging vi appende una riga JSON.
INTAKE_JOURNAL_PATH = INTAKE_STAGING_DIR / "intake.jsonl"


def ensure_staging_dirs(base_dir: str | Path | None = None) -> dict[str, Path]:
    """Crea (se mancanti) le cartelle dell'area di staging e il file del journal, e ne
    restituisce i percorsi. Lazy e idempotente — va chiamata dagli entrypoint che toccano
    staging/ (S2+), mai assunta creata al solo import del modulo (stesso principio degli
    artefatti di database/, vedi core/artifacts.py e core/writer_lock.py).

    `base_dir` è il seam per i test (default: INTAKE_STAGING_DIR, risolta da
    rag_config.yaml → intake.staging_dir)."""
    root = Path(base_dir) if base_dir is not None else INTAKE_STAGING_DIR
    docs_dir = root / "docs"
    projects_dir = root / "projects"
    rejected_dir = root / "rejected"
    journal_path = root / "intake.jsonl"

    for d in (docs_dir, projects_dir, rejected_dir):
        d.mkdir(parents=True, exist_ok=True)
    if not journal_path.exists():
        journal_path.touch()

    return {
        "root": root,
        "docs": docs_dir,
        "projects": projects_dir,
        "rejected": rejected_dir,
        "journal": journal_path,
    }

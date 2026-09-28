"""Archiviazione di una change (pipeline, step 5): canvas review, candidato di eval,
spostamento in changes/archive/ e, a richiesta, re-indicizzazione completa inline.

Estratto da core/indexing.py, che re-esporta archive_feature per compatibilità. La
re-indicizzazione passa da core.indexing.build_graph_and_index con import LAZY (indexing
importa questo modulo: un import a livello di modulo creerebbe un ciclo)."""
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from qdrant_client import QdrantClient

from core.canvas_review import (
    HISTORICAL_SUBDIR,
    REVIEW_FILENAME,
    append_eval_candidate,
    extract_eval_candidate,
    generate_canvas_review,
)
from core.config import CHANGES_DIR, DOCS_DIR
from core.drift_check import _review_code
from core.pipeline import InvalidFeatureNameError, resolve_feature_dir

logger = logging.getLogger(__name__)


def _record_review_skip(change_dir: Path, reason: str) -> None:
    """Registra nel manifest della change (meta.json) che la canvas review è stata
    saltata e perché, così l'assenza del file è documentata e non ambigua."""
    meta_path = change_dir / "meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    meta["canvas_review"] = {
        "status": "skipped",
        "reason": reason,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # anche il fallimento della registrazione non deve bloccare l'archive


def archive_feature(feature_name, qdrant: QdrantClient | None = None, embed_model=None,
                    emit=None, reindex: bool = True) -> str:
    """Sposta la cartella in 'archive' (con canvas review) e, se `reindex=True`, innesca
    la re-indicizzazione completa inline.

    `reindex=False` esegue SOLO la fase di archiviazione: è la modalità usata dal server,
    dove la ricostruzione dell'indice deve passare dalla coda del ReindexManager (un solo
    scrittore per costruzione) e non essere eseguita qui. La CLI (index.py), che gira
    fuori dal server, mantiene il default inline.

    Restituisce il log testuale dell'operazione (oltre a stamparlo/emetterlo). Le
    risorse pesanti possono essere iniettate dal server per riusare modello e client
    Qdrant già aperti; `emit` permette lo streaming SSE del progresso.
    """
    _emit = emit or logger.info
    lines: list[str] = []

    def log(msg: str) -> None:
        _emit(msg)
        lines.append(msg)

    try:
        source_dir = resolve_feature_dir(CHANGES_DIR, feature_name)
    except InvalidFeatureNameError as exc:
        log(f"❌ Nome feature non valido: {exc}")
        return "\n".join(lines)
    feature_folder = source_dir.name
    log(f"\n📦 Avvio archiviazione per la feature: '{feature_folder}'...")

    archive_base_dir = CHANGES_DIR / "archive"
    try:
        # feature_folder è già uno slug valido (appena prodotto sopra): questa validazione
        # è difesa in profondità, non attesa a fallire — protegge comunque da eventuali
        # modifiche future alle invarianti di resolve_feature_dir/archive_base_dir.
        target_dir = resolve_feature_dir(archive_base_dir, feature_folder)
    except InvalidFeatureNameError as exc:
        log(f"❌ Percorso di archiviazione non valido: {exc}")
        return "\n".join(lines)

    if not source_dir.exists():
        log(f"❌ Errore: La cartella {source_dir} non esiste. Non c'è nulla da archiviare.")
        return "\n".join(lines)

    archive_base_dir.mkdir(parents=True, exist_ok=True)

    # Canvas che apprende: confronta il diff reale del codice della change con il
    # canvas e salva canvas_review.md nella cartella (che sta per essere archiviata);
    # una copia va in docs/03_changes_historical/ così la re-indicizzazione la ingloba
    # come contesto storico interrogabile. Se l'LLM non è raggiungibile la review viene
    # saltata con warning nel meta.json: l'archiviazione NON deve mai fallirne.
    try:
        log("🧾 Canvas review: confronto il codice della change con il canvas...")
        review, warning = generate_canvas_review(feature_folder, source_dir,
                                                 code=_review_code(source_dir))
        if review is not None:
            (source_dir / REVIEW_FILENAME).write_text(review, encoding="utf-8")
            historical = DOCS_DIR / HISTORICAL_SUBDIR / f"{feature_folder}-canvas-review.md"
            historical.parent.mkdir(parents=True, exist_ok=True)
            historical.write_text(review, encoding="utf-8")
            log(f"✅ Canvas review salvata in {REVIEW_FILENAME} (+ copia storica in docs/{HISTORICAL_SUBDIR}/).")
        else:
            log(f"⚠️ Canvas review saltata: {warning}")
            _record_review_skip(source_dir, warning or "motivo sconosciuto")
    except Exception as e:  # difensivo: nessun problema della review blocca l'archive
        log(f"⚠️ Canvas review saltata per errore imprevisto: {e}")
        _record_review_skip(source_dir, str(e))

    # Golden-set che cresce dalle change: estrae (deterministicamente, nessun LLM) un
    # caso candidato di eval — query = intento della feature, expected = documenti
    # normativi usati dal retrieval governato per il canvas — e lo accoda a
    # eval/candidates.yaml. La promozione nel golden-set resta una revisione umana.
    try:
        candidate = extract_eval_candidate(feature_folder, source_dir)
        if candidate and append_eval_candidate(candidate):
            log(f"🧪 Candidato di eval accodato a eval/candidates.yaml (q: {candidate['q'][:60]}...)")
    except Exception as e:  # anche il candidato non deve mai bloccare l'archive
        log(f"⚠️ Estrazione candidato di eval saltata: {e}")

    try:
        from core.pipeline_store import PipelineStore
        # La review LLM resta fuori dal lock; solo la mutazione del contratto si coordina con l'ammissione.
        with PipelineStore().feature_lock(feature_folder):
            shutil.move(str(source_dir), str(target_dir))
        log(f"✅ Feature archiviata con successo in: {target_dir}")

        if reindex:
            log("🔄 Innesco la re-indicizzazione del Graph RAG locale...")
            # Import lazy: core.indexing importa questo modulo (re-export di archive_feature).
            from core import indexing
            indexing.build_graph_and_index(qdrant=qdrant, embed_model=embed_model, emit=_emit)
            log("✅ Re-indicizzazione completata! Il Graph RAG ha appreso la nuova feature.")

    except Exception as e:
        log(f"❌ Errore durante l'archiviazione: {e}")

    return "\n".join(lines)

"""Campione degli archi IMPLEMENTS, controllo delle schede, metriche.

Non ricalcola i collegamenti e non chiama un modello. La precisione resta
«non ancora misurata» finché ogni scheda del campione non ha un'etichetta umana.

Da rag/:

    uv run python scripts/link_audit.py sample --project legacy --out eval/link_audit/run --n 40 --seed 1
    # compila eval/link_audit/run/schede.json, senza punteggi
    uv run python scripts/link_audit.py validate --run eval/link_audit/run
    uv run python scripts/link_audit.py metrics --run eval/link_audit/run

metrics scrive metriche-v2.json: stimatore di rapporto pesato sui valutabili, quota
NON_VALUTABILE pesata a parte, intervallo conservativo (non esatto) al 95%. Non è una
recall e non vale per altri corpus. Il protocollo è eval/LINK_AUDIT.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.artifacts import current_version, load_artifacts, manifest_path  # noqa: E402
from core.config import EMBEDDING_MODEL  # noqa: E402
from eval.link_audit import (  # noqa: E402
    METHODOLOGY_VERSION,
    annotator_cards,
    collect_implements,
    compute_metrics,
    draw_sample,
    validate_annotations,
)

# Default di link_symbols. Si registra, non si modifica.
_LINKING_THRESHOLD = 0.45


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _digest(hashes: dict | None) -> str | None:
    # Impronta del corpus: il solo conteggio non distingue due corpus della stessa taglia.
    if not hashes:
        return None
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode("utf-8")).hexdigest()


def _provenance(version: str | None, manifest: dict | None) -> dict:
    manifest = manifest or {}
    status = _git("status", "--porcelain")
    return {
        "git_commit": _git("rev-parse", "HEAD") or None,
        "git_dirty": None if status is None else bool(status),
        "doc_hashes_sha256": _digest(manifest.get("doc_hashes")),
        "code_hashes_sha256": _digest(manifest.get("code_hashes")),
        "index_version": version,
        "embedding_model": manifest.get("embedding_model") or EMBEDDING_MODEL,
        "linking_threshold": _LINKING_THRESHOLD,
        "documents": manifest.get("documents"),
        "doc_hash_count": len(manifest.get("doc_hashes") or {}),
        "code_hash_count": len(manifest.get("code_hashes") or {}),
    }


def _read(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_sample(args) -> int:
    # Gli indici stanno sotto projects/<id>/database: senza progetto load_artifacts
    # cercherebbe il layout pre-progetti (rag/database) e non troverebbe nulla.
    from core.projects import ProjectError, ProjectRegistry
    try:
        project = ProjectRegistry(readonly=True).get(args.project)
    except ProjectError as exc:
        print(f"Progetto {args.project!r}: {exc}", file=sys.stderr)
        return 1
    arts = load_artifacts(("graph", "code", "chunks"), skip_colbert=True, project=project)
    if arts.graph is None:
        print("Nessun grafo nell'indice attivo.", file=sys.stderr)
        return 1
    manifest = {}
    path = manifest_path(arts.version, project=project)
    if path.is_file():
        manifest = json.loads(path.read_text(encoding="utf-8"))
    rows = collect_implements(arts.graph, arts.code_store, arts.chunks_store)
    if not rows:
        print("Nessun arco IMPLEMENTS nell'indice attivo. Precisione non ancora misurata.", file=sys.stderr)
        return 1
    sample = draw_sample(rows, n=args.n, seed=args.seed)
    sample["provenance"] = _provenance(arts.version or current_version(project), manifest)
    sample["provenance"]["project_id"] = args.project
    out = Path(args.out)
    _write(out / "sigillo.json", sample)
    _write(out / "schede.json", annotator_cards(sample))
    print(
        f"Campione di {sample['sample_size']} su {sample['population']} archi in {out}. "
        "Precisione non ancora misurata: compilare schede.json."
    )
    return 0


def _load_run(run: Path) -> tuple[dict, list]:
    sample = _read(run / "sigillo.json")
    cards = _read(run / "schede.json")
    if not isinstance(sample, dict) or not isinstance(cards, list):
        raise SystemExit("sigillo.json o schede.json non hanno la forma attesa")
    return sample, cards


def cmd_validate(args) -> int:
    sample, cards = _load_run(Path(args.run))
    report = validate_annotations(sample, [c for c in cards if c.get("label")])
    print(json.dumps({
        "accepted": len(report["accepted"]),
        "errors": report["errors"],
        "disagreements": report["disagreements"],
        "missing": report["missing"],
        "complete": report["complete"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["complete"] else 2


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rounded(value):
    # Arrotondamento solo a video: metriche-v*.json tiene i valori pieni.
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, list):
        return [_rounded(v) for v in value]
    return value


def cmd_metrics(args) -> int:
    run = Path(args.run)
    sample, cards = _load_run(run)
    report = compute_metrics(sample, [c for c in cards if c.get("label")])
    # Gli input entrano nel risultato: un ricalcolo resta riconducibile alle sue schede.
    report["inputs"] = {"sigillo_sha256": _sha(run / "sigillo.json"), "schede_sha256": _sha(run / "schede.json")}
    # Un file per versione della metodologia: metriche.json (versione 1) non si tocca, e un
    # risultato già scritto da altre schede non si sovrascrive.
    out = run / f"metriche-v{METHODOLOGY_VERSION}.json"
    if out.is_file() and _read(out).get("inputs") != report["inputs"]:
        print(f"{out} esiste ed è stato calcolato da altre schede: spostalo prima di ricalcolare.",
              file=sys.stderr)
        return 1
    _write(out, report)
    # La stima di popolazione prima: la precisione grezza vale solo sul campione.
    keys = ("status", "methodology_version", "population_precision", "interval",
            "weighted_non_evaluable_share", "estimated_implements_total", "estimated_evaluable_total",
            "sample_precision", "sample_precision_scope", "sample_non_evaluable_share", "reason")
    shown = {k: report[k] for k in keys if k in report}
    if isinstance(shown.get("interval"), dict):
        shown["interval"] = {k: shown["interval"][k] for k in ("bounds", "nominal_level", "conservative", "reason")}
        shown["interval"]["bounds"] = _rounded(shown["interval"]["bounds"])
    print(json.dumps({k: _rounded(v) for k, v in shown.items()}, ensure_ascii=False, indent=2))
    print(f"Scritto {out}.")
    return 0 if report["status"] == "misurato" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit degli archi IMPLEMENTS esistenti")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sample = sub.add_parser("sample")
    sample.add_argument("--out", required=True)
    sample.add_argument("--n", type=int, default=40)
    sample.add_argument("--seed", type=int, default=1)
    sample.add_argument("--project", default="legacy", help="ID del progetto registrato; default: legacy")
    sample.set_defaults(func=cmd_sample)
    check = sub.add_parser("validate")
    check.add_argument("--run", required=True)
    check.set_defaults(func=cmd_validate)
    metrics = sub.add_parser("metrics")
    metrics.add_argument("--run", required=True)
    metrics.set_defaults(func=cmd_metrics)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

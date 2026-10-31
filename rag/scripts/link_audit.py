"""Campione degli archi IMPLEMENTS, controllo delle schede, metriche.

Non ricalcola i collegamenti e non chiama un modello. La precisione resta
«non ancora misurata» finché ogni scheda del campione non ha un'etichetta umana.

Da rag/:

    uv run python scripts/link_audit.py sample --out eval/link_audit/run --n 40 --seed 1
    # compila eval/link_audit/run/schede.json, senza punteggi
    uv run python scripts/link_audit.py validate --run eval/link_audit/run
    uv run python scripts/link_audit.py metrics --run eval/link_audit/run

Il protocollo è eval/LINK_AUDIT.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.artifacts import current_version, load_artifacts, manifest_path  # noqa: E402
from core.config import EMBEDDING_MODEL  # noqa: E402
from eval.link_audit import (  # noqa: E402
    annotator_cards,
    collect_implements,
    compute_metrics,
    draw_sample,
    validate_annotations,
)

# Default di link_symbols. Si registra, non si modifica.
_LINKING_THRESHOLD = 0.45


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    token = out.stdout.strip()
    return token or None


def _provenance(version: str | None, manifest: dict | None) -> dict:
    manifest = manifest or {}
    return {
        "git_commit": _git_commit(),
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
    arts = load_artifacts(("graph", "code", "chunks"), skip_colbert=True)
    if arts.graph is None:
        print("Nessun grafo nell'indice attivo.", file=sys.stderr)
        return 1
    manifest = {}
    path = manifest_path(arts.version)
    if path.is_file():
        manifest = json.loads(path.read_text(encoding="utf-8"))
    rows = collect_implements(arts.graph, arts.code_store, arts.chunks_store)
    if not rows:
        print("Nessun arco IMPLEMENTS nell'indice attivo. Precisione non ancora misurata.", file=sys.stderr)
        return 1
    sample = draw_sample(rows, n=args.n, seed=args.seed)
    sample["provenance"] = _provenance(arts.version or current_version(), manifest)
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


def cmd_metrics(args) -> int:
    sample, cards = _load_run(Path(args.run))
    report = compute_metrics(sample, [c for c in cards if c.get("label")])
    _write(Path(args.run) / "metriche.json", report)
    print(json.dumps({k: report[k] for k in ("status", "strict_precision", "non_evaluable_share", "aggregate_precision") if k in report}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "misurato" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit degli archi IMPLEMENTS esistenti")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sample = sub.add_parser("sample")
    sample.add_argument("--out", required=True)
    sample.add_argument("--n", type=int, default=40)
    sample.add_argument("--seed", type=int, default=1)
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

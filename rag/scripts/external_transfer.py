"""Controlla il manifest di un corpus esterno. Non misura se il manifest manca.

Exit 2: bloccato o in attesa. Exit 0 solo se una run tracciabile è misurata,
e anche allora il JSON dice validato=false.

Da rag/:

    uv run python scripts/external_transfer.py
    uv run python scripts/external_transfer.py --manifest /percorso/manifest.json --cases /percorso/casi.json

Il protocollo è eval/EXTERNAL_TRANSFER.md. Il manifest di default non c'è.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.external_transfer import MEASURED, evaluate_transfer  # noqa: E402

_DEFAULT = Path(__file__).resolve().parent.parent / "eval" / "external" / "manifest.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Corpus esterno: protocollo, non un risultato.")
    parser.add_argument("--manifest", type=Path, default=_DEFAULT)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--human-verified", action="store_true")
    parser.add_argument("--split", default="test")
    parser.add_argument("--config-frozen", action="store_true")
    parser.add_argument("--used-for-tuning", action="store_true")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)
    if not args.manifest.is_file():
        report = evaluate_transfer(None, [], human_verified=False, split="test",
                                   config_frozen=False, used_for_tuning=False, run_id=None)
        report["motivi"].insert(0, f"nessun manifest in {args.manifest}")
    else:
        try:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            cases = []
            if args.cases is not None:
                cases = json.loads(args.cases.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        report = evaluate_transfer(
            manifest, cases, human_verified=args.human_verified, split=args.split,
            config_frozen=args.config_frozen, used_for_tuning=args.used_for_tuning,
            run_id=args.run_id,
        )
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    if report.get("validato"):
        print("validato non è un esito di questo strumento", file=sys.stderr)
        return 1
    return 0 if report["status"] == MEASURED else 2


if __name__ == "__main__":
    raise SystemExit(main())

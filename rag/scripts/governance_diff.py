"""Rileva i cambi di autorità fra due alberi o due ref git.

Non approva, non blocca un merge, non legge segreti. Exit 0 se non c'è nulla,
2 se c'è almeno un rilevamento, 1 se il comando è inutilizzabile.

Da rag/:

    uv run python scripts/governance_diff.py --base /tmp/base --head /tmp/head
    uv run python scripts/governance_diff.py --git <base-sha> <head-sha>

Il protocollo è eval/GOVERNANCE_APPROVAL.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.governance_diff import compare_trees  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]


def _ref_ok(ref: str) -> bool:
    if not ref or ref.startswith("-"):
        return False
    return not any(char in ref for char in ":\n\r")


def materialize_git(repo: Path, ref: str, dest: Path) -> None:
    if not _ref_ok(ref):
        raise ValueError("ref non valida")
    listing = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", ref],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if listing.returncode != 0:
        raise RuntimeError(listing.stderr.strip() or "git ls-tree fallito")
    dest.mkdir(parents=True, exist_ok=True)
    for relative in listing.stdout.splitlines():
        if not relative or relative.startswith("-"):
            continue
        target = dest / relative
        if ".." in target.parts:
            continue
        show = subprocess.run(
            ["git", "-C", str(repo), "show", f"{ref}:{relative}"],
            capture_output=True, timeout=30, check=False,
        )
        if show.returncode != 0:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(show.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rileva cambi di autorità. Non li approva.")
    parser.add_argument("--base", type=Path)
    parser.add_argument("--head", type=Path)
    parser.add_argument("--git", nargs=2, metavar=("BASE", "HEAD"))
    parser.add_argument("--repo", type=Path, default=_REPO)
    args = parser.parse_args(argv)
    if bool(args.git) == bool(args.base or args.head):
        print("Usa --base e --head, oppure --git BASE HEAD.", file=sys.stderr)
        return 1
    if args.git:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            head = Path(tmp) / "head"
            try:
                materialize_git(args.repo, args.git[0], base)
                materialize_git(args.repo, args.git[1], head)
            except (ValueError, RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
                print(str(exc), file=sys.stderr)
                return 1
            report = compare_trees(base, head)
    else:
        report = compare_trees(args.base, args.head)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 2 if report["rilevamenti"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

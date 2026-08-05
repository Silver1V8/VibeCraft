"""Migrazione ONE-SHOT delle spec già scritte al formato unico degli scenari BDD.

Le spec normative di docs/02_specs_normative/ sono state scritte con il Gherkin italiano
(`Dato`/`Quando`/`Allora`/`E`) che il template prescriveva prima del formato unico. Il
template ora è la fonte normativa di UN solo formato, e questi documenti devono adeguarsi:
sono ciò che il Graph RAG indicizza come `OPEN_SPEC` e che i prompt citano come vincolo.

Riusa lo STESSO core.spec_format.normalize_spec che gira dopo ogni generazione: se la
migrazione e la pipeline usassero due implementazioni, divergerebbero al primo bugfix.

Uso:
    uv run python scripts/migrate_spec_format.py            # anteprima, non scrive nulla
    uv run python scripts/migrate_spec_format.py --apply    # riscrive i file

Dopo `--apply` il diff va RIVISTO A MANO e committato da solo: il normalizzatore non
inventa contenuto, ma sono documenti normativi e la revisione umana non è opzionale.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.spec_format import (  # noqa: E402
    SpecNormalizationError,
    normalize_spec,
    parse_scenarios,
)

# Solo le spec normative. changes/archive/** resta fuori di proposito: è storia, non viene
# più letta come contratto, e riscriverla non porterebbe niente.
DEFAULT_TARGET = Path(__file__).resolve().parents[2] / "docs" / "02_specs_normative"


def migra(cartella: Path, apply: bool) -> int:
    """Normalizza gli spec della cartella. Restituisce il numero di file NON migrabili."""
    file_spec = sorted(cartella.glob("spec_*.md"))
    if not file_spec:
        print(f"Nessuno spec in {cartella}")
        return 0

    invariati, modificati, errori = [], [], []
    for path in file_spec:
        originale = path.read_text(encoding="utf-8")
        try:
            normalizzato = normalize_spec(originale)
        except SpecNormalizationError as exc:
            errori.append((path, str(exc)))
            continue
        if normalizzato == originale:
            invariati.append(path)
            continue
        modificati.append((path, len(parse_scenarios(originale))))
        if apply:
            path.write_text(normalizzato, encoding="utf-8")

    verbo = "Migrati" if apply else "Da migrare"
    print(f"{verbo}: {len(modificati)}")
    for path, n in modificati:
        print(f"  · {path.name:34s} {n} scenari")
    if invariati:
        print(f"Già conformi: {len(invariati)}")
        for path in invariati:
            print(f"  · {path.name}")
    if errori:
        print(f"NON migrabili: {len(errori)} (lasciati intatti)")
        for path, msg in errori:
            print(f"  · {path.name}: {msg}")

    if apply and modificati:
        print("\nRivedi il diff prima di committare:  git diff -- docs/02_specs_normative/")
    elif not apply:
        print("\nAnteprima: nessun file è stato scritto. Rilancia con --apply per riscriverli.")
    return len(errori)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="riscrive i file (senza, mostra solo cosa cambierebbe)")
    parser.add_argument("--path", type=Path, default=DEFAULT_TARGET,
                        help=f"cartella da migrare (default: {DEFAULT_TARGET})")
    args = parser.parse_args()

    if not args.path.is_dir():
        print(f"Cartella inesistente: {args.path}")
        return 2
    return 1 if migra(args.path, args.apply) else 0


if __name__ == "__main__":
    raise SystemExit(main())

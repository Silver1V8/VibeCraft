"""Inserisce nei quattro HTML di static/manuale/ le catture prodotte da manual_screenshots.cjs.

Le immagini stanno dentro gli HTML come webp in base64 (le pagine sono autonome). Il manuale IT
e quello EN hanno le stesse 64 figure nello stesso ordine e usano le stesse immagini (la UI
fotografata è in italiano): la figura i-esima prende la cattura della sua sigla. Il percorso
guidato usa un sottoinsieme, elencato in TOUR.

    uv run python scripts/embed_manual_screenshots.py --shots <cartella PNG> [--dry-run]

Funziona solo con file già prodotti: non lancia browser e non parla col server.
"""
import argparse
import base64
import io
import re
import sys
from pathlib import Path

from PIL import Image

MANUALE = Path(__file__).resolve().parent.parent / "static" / "manuale"
# Le prime otto figure del manuale sono la «prova rapida» e riusano catture del resto del manuale.
QUICK_START = ["s01", "s03", "s32", "s35", "s06", "s07", "s13", "s18"]
# Figure del percorso guidato, nell'ordine in cui compaiono (t05 = domanda fuori corpus).
TOUR = ["s35", "s33", "s13", "s19", "t05", "s63", "s66", "s48", "s50", "s55", "s58", "s67"]
IMG = re.compile(r'(<img\b[^>]*?src="data:image/webp;base64,)([A-Za-z0-9+/=]+)(")')
ALT = re.compile(r'alt="(s\d+)')


def png_for(shots: Path, key: str) -> Image.Image:
    if key == "s10" and not (shots / "s10.png").exists():
        # Stessa schermata nei due temi: metà sinistra Classico, metà destra Matrix.
        left, right = (Image.open(shots / f"s10_{t}.png").convert("RGB") for t in ("classic", "matrix"))
        out = left.copy()
        out.paste(right.crop((right.width // 2, 0, right.width, right.height)), (right.width // 2, 0))
        return out
    return Image.open(shots / f"{key}.png").convert("RGB")


def webp_b64(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=82, method=6)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def manual_keys() -> list[str]:
    """Sigla di ognuna delle 64 figure, dall'ordine del manuale italiano (alt «sNN — …»)."""
    text = (MANUALE / "manuale-utente.html").read_text(encoding="utf-8")
    keys = QUICK_START[:]
    for match in IMG.finditer(text):
        alt = ALT.search(text[match.start():match.end() + 400])
        if alt:
            keys.append(alt.group(1))
    return keys


def rewrite(name: str, keys: list[str], shots: Path, dry_run: bool) -> int:
    path = MANUALE / name
    raw = path.read_bytes().decode("utf-8")  # byte per byte: LF/CRLF restano com'erano
    matches = list(IMG.finditer(raw))
    if len(matches) != len(keys):
        sys.exit(f"{name}: {len(matches)} immagini, attese {len(keys)}: l'ordine delle figure è cambiato")
    cache: dict[str, str] = {}
    pieces, last = [], 0
    for match, key in zip(matches, keys):
        cache.setdefault(key, webp_b64(png_for(shots, key)))
        pieces += [raw[last:match.start()], match.group(1), cache[key], match.group(3)]
        last = match.end()
    pieces.append(raw[last:])
    if not dry_run:
        path.write_bytes("".join(pieces).encode("utf-8"))
    print(f"{name}: {len(matches)} immagini ({len(cache)} diverse)")
    return len(matches)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shots", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    keys = manual_keys()
    if len(keys) != 64:
        sys.exit(f"Trovate {len(keys)} sigle nel manuale, attese 64")
    for name in ("manuale-utente.html", "manuale-utente.en.html"):
        rewrite(name, keys, args.shots, args.dry_run)
    for name in ("percorso-guidato.html", "percorso-guidato.en.html"):
        rewrite(name, TOUR, args.shots, args.dry_run)


if __name__ == "__main__":
    main()

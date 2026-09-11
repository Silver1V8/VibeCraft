"""Scarica i pesi di Docling e RapidOCR usati dall'intake alle revisioni verificate e ne
controlla lo SHA-256 contro core/intake_convert.DOCLING_WEIGHTS e OCR_WEIGHTS. I file già
presenti e corretti non vengono riscaricati.

Uso (da rag/):
    uv run python scripts/docling_models.py              # scarica in intake.docling.models_dir
    uv run python scripts/docling_models.py --verifica   # solo controllo, nessuna rete
    uv run python scripts/docling_models.py --dest DIR   # altra destinazione
Exit 0 solo se tutti i pesi ci sono e corrispondono."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import INTAKE_DOCLING_MODELS_DIR  # noqa: E402
from core.intake_convert import DOCLING_WEIGHTS, OCR_LANG, OCR_WEIGHTS, sha256_file  # noqa: E402

# Commit dei repository Hugging Face da cui vengono i pesi verificati dal pilot finale
# (rag/eval/results/pilot_docling_finale_20260909-110000/manifest/). Docling di suo
# scaricherebbe il layout da `main`, un riferimento mobile.
HF_REVISIONS = {
    "docling-project/docling-layout-heron": "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8",
    "docling-project/docling-models": "fc0f2d45e2218ea24bce5045f58a389aed16dc23",  # v2.3.0
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verifica", action="store_true", help="solo controllo, nessun download")
    ap.add_argument("--dest", type=Path, default=INTAKE_DOCLING_MODELS_DIR)
    a = ap.parse_args()

    if not a.verifica:
        from docling.models.utils.hf_model_download import download_hf_model
        from docling.utils.model_downloader import download_models
        for repo, revision in HF_REVISIONS.items():
            download_hf_model(repo_id=repo, revision=revision,
                              local_dir=a.dest / repo.replace("/", "--"))
        # URL fissati al tag di rapidocr installato (registro di rapidocr 3.9.2).
        download_models(a.dest, with_layout=False, with_tableformer=False,
                        with_code_formula=False, with_picture_classifier=False,
                        with_rapidocr=True, rapidocr_models=[f"onnxruntime:{OCR_LANG}"])

    errori = 0
    for rel, atteso in {**DOCLING_WEIGHTS, **OCR_WEIGHTS}.items():
        path = a.dest / rel
        stato = ("mancante" if not path.is_file()
                 else "ok" if sha256_file(path) == atteso else "SHA-256 DIVERSO")
        errori += stato != "ok"
        print(f"{stato:>16}  {path}")
    return 1 if errori else 0


if __name__ == "__main__":
    raise SystemExit(main())

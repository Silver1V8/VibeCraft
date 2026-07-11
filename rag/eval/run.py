"""Eval harness del retrieval — comando CLI.

Esegue il golden-set (eval/golden_set.yaml) contro il retrieval reale via HTTP
(GET /api/retrieve, così riusa il modello già caricato dal server: niente reload di
minuti), calcola le metriche con core.eval_metrics, stampa un report tabellare e salva
il risultato in eval/results/eval_<timestamp>.json per confrontare run successive.

Uso (da rag/):
    uv run python -m eval.run
    uv run python -m eval.run --k 5 10 --url http://127.0.0.1:8000 --threshold 0.7

Exit code: 0 se recall@<max k> >= soglia (utile in CI), 1 se sotto soglia, 2 se il
server non risponde.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx
import yaml

from core.eval_metrics import evaluate

for _s in (sys.stdout, sys.stderr):  # emoji/§/→ safe su console Windows (cp1252)
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

EVAL_DIR = Path(__file__).parent
GOLDEN = EVAL_DIR / "golden_set.yaml"
RESULTS_DIR = EVAL_DIR / "results"


def load_cases() -> list[dict]:
    return yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))["cases"]


def http_retriever(url: str, client: httpx.Client):
    """Costruisce una retrieve_fn(query, k) che interroga GET /api/retrieve del server."""
    def retrieve(query: str, k: int) -> list[dict]:
        resp = client.get(f"{url}/api/retrieve", params={"q": query, "k": k})
        resp.raise_for_status()
        return resp.json()["results"]
    return retrieve


def _fmt_pct(x: float) -> str:
    return f"{x * 100:5.1f}%"


def print_report(report: dict, ks: list[int]) -> None:
    recall_keys = [f"recall@{k}" for k in ks]
    header_metrics = recall_keys + ["top3", "mrr"]
    print(f"{'':4} {'rk':>3} {'exp':>3}  {'top-1 (doc § sezione)':<48} query")
    print("-" * 110)
    for pc in report["cases"]:
        m = pc["metrics"]
        rk = pc["best_rank"]
        mark = "OK " if (rk and rk <= report["top3_k"]) else ("~k " if rk else "MISS")
        top = f"{pc['top1']['doc_id'].split('/')[-1][:22]} § {pc['top1']['section'][:22]}"
        print(f"{mark:4} {str(rk or '-'):>3} {pc['n_expected']:>3}  {top:<48} {pc['q'][:44]}")
    print("-" * 110)
    agg = report["aggregate"]
    print(f"casi: {report['n']}  |  k={ks}  |  colonne aggregate (media sui casi):")
    for key in header_metrics:
        real = "source_in_top3" if key == "top3" else key
        val = agg[real]
        print(f"  {key:<16} = {_fmt_pct(val) if key != 'mrr' else f'{val:.3f}'}")


def save_results(report: dict, url: str) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"eval_{ts}.json"
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "url": url,
        "n": report["n"],
        "ks": report["ks"],
        "top3_k": report["top3_k"],
        "aggregate": report["aggregate"],
        "cases": report["cases"],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Eval harness del retrieval sul golden-set")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--k", type=int, nargs="+", default=[5, 10], help="soglie di recall (default: 5 10)")
    ap.add_argument("--threshold", type=float, default=0.7,
                    help="soglia minima su recall@<max k> per exit 0 (CI)")
    ap.add_argument("--no-save", action="store_true", help="non salvare il JSON in eval/results/")
    a = ap.parse_args()

    ks = sorted(set(a.k))
    cases = load_cases()

    try:
        with httpx.Client(timeout=180) as client:
            report = evaluate(cases, http_retriever(a.url, client), ks=ks)
    except Exception as e:
        print(f"❌ /api/retrieve non raggiungibile: {e}\n   Avvia il server: python server.py")
        return 2

    print_report(report, ks)
    if not a.no_save:
        out = save_results(report, a.url)
        print(f"\n💾 Risultati salvati in {out}")

    top_recall = report["aggregate"][f"recall@{max(ks)}"]
    ok = top_recall >= a.threshold
    print(("✅ PASS" if ok else "❌ FAIL") + f"  (soglia: recall@{max(ks)} >= {a.threshold})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

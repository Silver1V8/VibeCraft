"""Eval del retrieval sul golden-set: misura OGGETTIVA della qualità del ranking.

Richiede il server avviato (usa GET /api/retrieve, così riusa il modello già caricato,
niente reload di minuti). Riporta doc_hit@k, section_hit@k e MRR sulla sezione attesa.

Uso:
    python eval_retrieval.py                       # k=5, soglia 0.7
    python eval_retrieval.py --k 3 --threshold 0.8 --url http://127.0.0.1:8000

Exit code: 0 se section_hit@k >= soglia (utile in CI), 1 se sotto soglia, 2 se il server
non risponde.
"""
import argparse
import sys
from pathlib import Path

import httpx
import yaml

for _s in (sys.stdout, sys.stderr):  # emoji/§/→ safe su console Windows (cp1252)
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

GOLDEN = Path(__file__).parent / "eval" / "golden_set.yaml"


def _contains(haystack: str, needle: str) -> bool:
    return needle.lower() in (haystack or "").lower()


def evaluate(url: str, k: int) -> dict:
    """Esegue il golden-set contro /api/retrieve e restituisce le metriche aggregate
    (+ le righe per il report). Solleva se il server non risponde."""
    cases = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))["cases"]
    n = len(cases)
    doc_hits = sec_hits = doc_hits3 = sec_hits3 = 0
    rr_sum = 0.0
    rows = []

    with httpx.Client(timeout=180) as client:
        for c in cases:
            q, exp_doc, exp_sec = c["q"], c["expected_doc"], c.get("expected_section")
            resp = client.get(f"{url}/api/retrieve", params={"q": q, "k": k})
            resp.raise_for_status()
            results = resp.json()["results"]

            first_doc = first_sec = None
            for i, res in enumerate(results):
                doc_ok = _contains(res.get("doc_id", ""), exp_doc)
                sec_ok = doc_ok and (exp_sec is None or _contains(res.get("section", ""), exp_sec))
                if doc_ok and first_doc is None:
                    first_doc = i + 1
                if sec_ok and first_sec is None:
                    first_sec = i + 1

            target = first_sec if exp_sec else first_doc          # rango della prima corrispondenza
            rr_sum += (1.0 / target) if target else 0.0
            doc_hits += 1 if first_doc else 0
            doc_hits3 += 1 if (first_doc and first_doc <= 3) else 0
            sec_hits += 1 if first_sec else 0
            sec_hits3 += 1 if (first_sec and first_sec <= 3) else 0

            top = results[0] if results else {}
            mark = "OK " if first_sec else ("~doc" if first_doc else "MISS")
            rows.append((mark, target or "-", exp_doc[:18], (exp_sec or "-")[:24],
                         f"{top.get('doc_id', '').split('/')[-1][:22]} § {top.get('section', '')[:24]}", q[:42]))

    return {
        "n": n, "k": k,
        "doc_hit3": doc_hits3 / n, "doc_hit_k": doc_hits / n,
        "section_hit3": sec_hits3 / n, "section_hit_k": sec_hits / n,
        "mrr": rr_sum / n, "rows": rows,
    }


def run(url: str, k: int, threshold: float) -> int:
    try:
        m = evaluate(url, k)
    except Exception as e:
        print(f"❌ /api/retrieve non raggiungibile: {e}\n   Avvia il server: python server.py")
        return 2

    print(f"{'':4} {'rk':>3}  {'doc atteso':<18} {'sezione attesa':<24} {'top-1':<50} query")
    for mark, rk, d, s, top, q in m["rows"]:
        print(f"{mark:4} {str(rk):>3}  {d:<18} {s:<24} {top:<50} {q}")
    print("-" * 118)
    print(f"casi: {m['n']}  |  k={k}")
    print(f"  doc_hit@3     = {m['doc_hit3']:.2f}     doc_hit@{k}     = {m['doc_hit_k']:.2f}")
    print(f"  section_hit@3 = {m['section_hit3']:.2f}     section_hit@{k} = {m['section_hit_k']:.2f}")
    print(f"  MRR (sezione) = {m['mrr']:.3f}")
    ok = m["section_hit_k"] >= threshold
    print(("✅ PASS" if ok else "❌ FAIL") + f"  (soglia: section_hit@{k} >= {threshold})")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Eval retrieval sul golden-set")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=0.7)
    a = ap.parse_args()
    sys.exit(run(a.url, a.k, a.threshold))

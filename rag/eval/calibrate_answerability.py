"""Calibrazione del gate di rispondibilità di /ask (G1) — comando CLI.

Piano: rag/adr/2026-11-03-gate-rispondibilita-plan.md (Task 5-6). Manda a POST /ask le domande
CON risposta (golden_set.yaml, i casi multihop di golden_multihop.yaml) e quelle SENZA
(golden_unanswerable.yaml) col server in `answerability.mode: shadow`, e legge il punteggio del
gate da ogni risposta. La soglia proposta è la più alta che non fa perdere NESSUN positivo:
un'astensione falsa costa più di una generazione sprecata, quindi il margine sta tutto dalla
parte dei positivi.

Va lanciato su un server APPENA riavviato: la cache di /ask è in memoria e le voci create prima
del gate non hanno `answerability`. Le conta a parte ed esce con 1 invece di trattarle come
punteggi mancanti.

Uso (da rag/):
    uv run python -m eval.calibrate_answerability
    uv run python -m eval.calibrate_answerability --url http://127.0.0.1:8000 --project demo

Exit code: 0 run valido (il verdetto go/no-go è nel report), 1 risposte senza punteggio o dalla
cache, 2 server non raggiungibile.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx2
import yaml

from eval.run import GOLDEN, RESULTS_DIR, load_cases
from eval.run_multihop import load_cases as load_multihop

for _s in (sys.stdout, sys.stderr):  # §/→ safe su console Windows (cp1252)
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

UNANSWERABLE = Path(__file__).parent / "golden_unanswerable.yaml"
# Criterio go/no-go della Decisione nel piano: metà dei negativi presi a zero positivi persi.
GO_RATIO = 0.5
GO_P95_MS = 2000


def choose_threshold(pos: list[float], neg: list[float], *, margin: float = 0.02) -> dict:
    if not pos:
        raise ValueError("Nessun positivo con punteggio: la soglia non si può scegliere.")
    threshold = round(min(pos) - margin, 4)
    caught = sum(1 for s in neg if s < threshold)
    ratio = caught / len(neg) if neg else 0.0
    return {"threshold": threshold, "neg_caught": caught, "neg_total": len(neg),
            "neg_caught_ratio": round(ratio, 3), "go_ratio": ratio >= GO_RATIO}


def classify(payload: dict) -> float | str:
    """Il punteggio del gate, o il motivo per cui questa risposta non ne ha uno utilizzabile."""
    if payload.get("status") == "graph_answer":
        return "graph_answer"  # il router M2 risponde dal grafo: il gate non entra in gioco
    if payload.get("cached"):
        return "cached"
    judged = payload.get("answerability")
    if judged:
        return judged["score"]
    # no_results / no_graph_nodes tornano prima del gate: sono esiti, non punteggi mancanti.
    return payload["status"] if payload.get("status") in {"no_results", "no_graph_nodes"} else "missing"


def _p(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def summarize(rows: list[dict], *, margin: float = 0.02) -> dict:
    scored = [r for r in rows if isinstance(r["outcome"], float)]
    skipped: dict[str, int] = {}
    for r in rows:
        if not isinstance(r["outcome"], float):
            skipped[r["outcome"]] = skipped.get(r["outcome"], 0) + 1
    pos = [r["outcome"] for r in scored if r["group"] == "pos"]
    neg = [r["outcome"] for r in scored if r["group"] == "neg"]
    threshold = choose_threshold(pos, neg, margin=margin)
    # Gate × LLM: dove il gate si asterrebbe e cosa ha fatto davvero il LLM nello stesso turno.
    matrix: dict[str, int] = {}
    for r in scored:
        gate = "gate_abstain" if r["outcome"] < threshold["threshold"] else "gate_answer"
        key = f"{gate}&llm_{r['llm_status']}"
        matrix[key] = matrix.get(key, 0) + 1
    latencies = [r["latency_ms"] for r in scored if r["latency_ms"] is not None]
    return {
        "threshold": threshold,
        "skipped": skipped,
        "matrix": matrix,
        "latency_ms": {"p50": _p(latencies, 0.5), "p95": _p(latencies, 0.95)},
        # Sono questi a fissare la soglia: vanno letti uno per uno prima di fidarsi del numero.
        "lowest_positives": sorted(
            ({"q": r["q"], "score": r["outcome"]} for r in scored if r["group"] == "pos"),
            key=lambda x: x["score"])[:5],
        "negatives": sorted(({"q": r["q"], "kind": r.get("kind"), "score": r["outcome"]}
                             for r in scored if r["group"] == "neg"), key=lambda x: x["score"]),
    }


def _ask(client: httpx2.Client, url: str, question: str, *, max_waits: int = 10) -> dict:
    for _ in range(max_waits):
        resp = client.post(f"{url}/ask", json={"question": question, "use_thread": False})
        if resp.status_code not in (429, 503):
            break
        time.sleep(float(resp.headers.get("Retry-After", "1")))
    resp.raise_for_status()
    return resp.json()


def collect(client: httpx2.Client, url: str) -> list[dict]:
    cases = ([("pos", c["q"], None) for c in load_cases(GOLDEN)]
             + [("pos", c["q"], None) for c in load_multihop() if c.get("kind") == "multihop"]
             + [("neg", c["q"], c["kind"])
                for c in yaml.safe_load(UNANSWERABLE.read_text(encoding="utf-8"))["cases"]])
    rows = []
    for i, (group, q, kind) in enumerate(cases, 1):
        payload = _ask(client, url, q)
        outcome = classify(payload)
        judged = payload.get("answerability") or {}
        rows.append({"group": group, "q": q, "kind": kind, "outcome": outcome,
                     "llm_status": payload.get("status"), "latency_ms": judged.get("latency_ms")})
        print(f"[{i}/{len(cases)}] {group} {outcome!s:>12}  {q[:70]}", flush=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibrazione del gate di rispondibilità di /ask")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--project", help="ID del progetto registrato; default: legacy")
    ap.add_argument("--margin", type=float, default=0.02,
                    help="distanza della soglia sotto il positivo più basso (default 0.02)")
    a = ap.parse_args()
    headers = {"X-VibeCraft-Project": a.project} if a.project else {}
    if os.environ.get("VIBECRAFT_API_KEY"):
        headers["X-API-Key"] = os.environ["VIBECRAFT_API_KEY"]
    try:
        with httpx2.Client(timeout=600, headers=headers) as client:
            rows = collect(client, a.url)
    except httpx2.HTTPError as e:
        print(f"❌ /ask non raggiungibile: {e}")
        return 2

    report = summarize(rows, margin=a.margin)
    t, lat = report["threshold"], report["latency_ms"]
    report["go"] = bool(t["go_ratio"] and lat["p95"] is not None and lat["p95"] <= GO_P95_MS)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"answerability_{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps({"report": report, "rows": rows}, ensure_ascii=False, indent=2),
                   encoding="utf-8")

    print(f"\nSoglia proposta: {t['threshold']}  negativi sotto soglia: "
          f"{t['neg_caught']}/{t['neg_total']} ({t['neg_caught_ratio']:.0%})")
    print(f"Latenza gate p50/p95: {lat['p50']} / {lat['p95']} ms   scartati: {report['skipped']}")
    print(f"Gate × LLM: {report['matrix']}")
    print("Positivi più bassi:")
    for p in report["lowest_positives"]:
        print(f"  {p['score']:.4f}  {p['q']}")
    print(f"\nEsito: {'GO' if report['go'] else 'NO-GO'}   report: {out}")
    return 1 if report["skipped"].get("cached") or report["skipped"].get("missing") else 0


if __name__ == "__main__":
    sys.exit(main())

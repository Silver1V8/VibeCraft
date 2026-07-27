"""Eval harness del retrieval — comando CLI.

Esegue il golden-set (eval/golden_set.yaml) contro il retrieval reale via HTTP
(GET /api/retrieve, così riusa il modello già caricato dal server: niente reload di
minuti), calcola le metriche con core.eval_metrics, stampa un report tabellare e salva
il risultato in eval/results/eval_<timestamp>.json per confrontare run successive.

Uso (da rag/):
    uv run python -m eval.run
    uv run python -m eval.run --assert-min 0.90              # guardrail pre-merge
    uv run python -m eval.run --k 5 10 --url http://127.0.0.1:8000
    uv run python -m eval.run --review-candidates            # mostra i candidati
    uv run python -m eval.run --review-candidates --promote 0 2   # promuove nel golden-set

Exit code: 0 se recall@<max k> medio >= soglia (--assert-min), 1 se sotto soglia
(il report in eval/results/ viene comunque scritto), 2 se il server non risponde.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx2
import yaml

from core.eval_metrics import evaluate

for _s in (sys.stdout, sys.stderr):  # emoji/§/→ safe su console Windows (cp1252)
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

EVAL_DIR = Path(__file__).parent
GOLDEN = EVAL_DIR / "golden_set.yaml"
CANDIDATES = EVAL_DIR / "candidates.yaml"
RESULTS_DIR = EVAL_DIR / "results"


def load_cases(golden_path: Path = GOLDEN) -> list[dict]:
    return yaml.safe_load(golden_path.read_text(encoding="utf-8"))["cases"]


def load_candidates(candidates_path: Path = CANDIDATES) -> list[dict]:
    """Candidati estratti all'archive delle change (core.canvas_review), in attesa di
    revisione umana. Lista vuota se il file non esiste."""
    if not candidates_path.exists():
        return []
    return (yaml.safe_load(candidates_path.read_text(encoding="utf-8")) or {}).get("candidates") or []


def format_golden_entry(candidate: dict) -> str:
    """Serializza un candidato come entry YAML del golden-set (solo q + expected, con un
    commento di provenienza). Testo da APPENDERE al file: il golden-set non viene mai
    riscritto per intero, così i suoi commenti di documentazione sopravvivono."""
    lines = [
        "",
        f"  # promosso da eval/candidates.yaml (feature: {candidate.get('from_feature', '?')},"
        f" estratto: {candidate.get('extracted_at', '?')})",
        f"  - q: {json.dumps(candidate['q'], ensure_ascii=False)}",
        "    expected:",
    ]
    for m in candidate.get("expected") or []:
        pairs = ", ".join(f"{k}: {json.dumps(str(v), ensure_ascii=False)}" for k, v in m.items())
        lines.append(f"      - {{{pairs}}}")
    return "\n".join(lines) + "\n"


def promote_candidates(indices: list[int], candidates_path: Path = CANDIDATES,
                       golden_path: Path = GOLDEN) -> list[dict]:
    """SPOSTA i candidati indicati (indici di --review-candidates) nel golden-set:
    appende le entry a golden_set.yaml e riscrive candidates.yaml senza di esse.
    Solleva ValueError su indici fuori range."""
    candidates = load_candidates(candidates_path)
    bad = [i for i in indices if i < 0 or i >= len(candidates)]
    if bad:
        raise ValueError(f"indici candidato inesistenti: {bad} (disponibili: 0..{len(candidates) - 1})")

    chosen = [candidates[i] for i in sorted(set(indices))]
    with golden_path.open("a", encoding="utf-8") as f:
        for c in chosen:
            f.write(format_golden_entry(c))

    remaining = [c for i, c in enumerate(candidates) if i not in set(indices)]
    candidates_path.write_text(
        "# Candidati per eval/golden_set.yaml estratti all'archive delle change.\n"
        "# NON usati dall'eval: la promozione è una revisione umana\n"
        "# (uv run python -m eval.run --review-candidates [--promote N ...]).\n"
        + yaml.safe_dump({"candidates": remaining}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return chosen


def print_candidates(candidates: list[dict]) -> None:
    if not candidates:
        print("Nessun candidato in eval/candidates.yaml (si popolano all'archive delle change).")
        return
    print(f"{len(candidates)} candidati in attesa di revisione (promuovi con --promote N ...):\n")
    for i, c in enumerate(candidates):
        print(f"[{i}] q: {c['q']}")
        print(f"    feature: {c.get('from_feature', '?')}  estratto: {c.get('extracted_at', '?')}")
        for m in c.get("expected") or []:
            print(f"    expected: {m}")
        print()


def http_retriever(url: str, client: httpx2.Client):
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


def run_eval(cases: list[dict], retrieve_fn, ks: list[int], assert_min: float,
             save: bool = True, url: str = "") -> int:
    """Cuore della modalità guardrail, separato da HTTP/argparse così i test lo esercitano
    con un retriever fake: valuta i casi, stampa il report, lo salva SEMPRE in
    eval/results/ (anche sotto soglia, se save=True) e restituisce l'exit code:
    0 se recall@<max ks> medio >= assert_min, altrimenti 1."""
    ks = sorted(set(ks))
    report = evaluate(cases, retrieve_fn, ks=ks)

    print_report(report, ks)
    if save:
        out = save_results(report, url)
        print(f"\n💾 Risultati salvati in {out}")
        # Storicizza nel trend di qualità (Epic 5): source="eval.run".
        try:
            from core.artifacts import current_version
            from core.eval_history import record_history
            record_history({f"recall@{k}": report["aggregate"][f"recall@{k}"] for k in ks},
                           n_cases=report["n"], version=current_version(), source="eval.run")
        except Exception as exc:  # lo storico è telemetria: non deve mai far fallire l'eval
            print(f"(storico non aggiornato: {exc})")

    top_recall = report["aggregate"][f"recall@{max(ks)}"]
    ok = top_recall >= assert_min
    print(("✅ PASS" if ok else "❌ FAIL")
          + f"  (recall@{max(ks)} = {top_recall:.3f}, soglia --assert-min = {assert_min})")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Eval harness del retrieval sul golden-set")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--k", type=int, nargs="+", default=[5, 10], help="soglie di recall (default: 5 10)")
    ap.add_argument("--assert-min", type=float, default=None,
                    help="guardrail: exit 1 se il recall@<max k> medio scende sotto questa soglia "
                         "(il report viene comunque scritto in eval/results/)")
    ap.add_argument("--threshold", type=float, default=0.7,
                    help="(legacy) come --assert-min; usato solo se --assert-min è assente")
    ap.add_argument("--no-save", action="store_true", help="non salvare il JSON in eval/results/")
    ap.add_argument("--review-candidates", action="store_true",
                    help="mostra i candidati estratti all'archive (eval/candidates.yaml) invece di eseguire l'eval")
    ap.add_argument("--promote", type=int, nargs="+", metavar="N",
                    help="con --review-candidates: promuove i candidati indicati nel golden_set.yaml (li sposta)")
    ap.add_argument("--check-regression", action="store_true",
                    help="dopo l'eval, controlla lo storico (eval/results/history.jsonl) e scrive un alert "
                         "critico se la recall è calata rispetto alla media mobile o sotto --assert-min (check notturno)")
    a = ap.parse_args()

    if a.review_candidates or a.promote:
        candidates = load_candidates()
        print_candidates(candidates)
        if a.promote:
            try:
                promoted = promote_candidates(a.promote)
            except ValueError as e:
                print(f"❌ {e}")
                return 1
            for c in promoted:
                print(f"⬆️  Promosso nel golden-set: {c['q']}")
            print(f"✅ {len(promoted)} candidati spostati in {GOLDEN.name}. Rilancia l'eval per misurarli.")
        return 0

    assert_min = a.assert_min if a.assert_min is not None else a.threshold
    cases = load_cases()

    try:
        with httpx2.Client(timeout=180) as client:
            code = run_eval(cases, http_retriever(a.url, client), ks=a.k,
                            assert_min=assert_min, save=not a.no_save, url=a.url)
    except httpx2.HTTPError as e:
        print(f"❌ /api/retrieve non raggiungibile: {e}\n   Avvia il server: python server.py")
        return 2

    if a.check_regression:
        # Check notturno (Epic 5.2): confronta l'ultima recall con la media mobile dello storico
        # e sotto la soglia --assert-min; su regressione scrive un alert critico (alerts.jsonl).
        from core.eval_history import detect_regression
        from core.eval_gate import record_alert
        reg = detect_regression("recall@10", floor=assert_min)
        if reg is not None:
            msg = (f"Regressione di qualità: recall@10={reg['last']} "
                   f"(media mobile {reg['moving_avg']} su {reg['window']} run"
                   + (f", soglia {reg['floor']}" if reg['floor'] is not None else "") + ").")
            record_alert("critical", msg, source_check="eval.run --check-regression", **{
                "recall@10": reg["last"], "moving_avg": reg["moving_avg"]})
            print(f"⚠️  {msg} Alert scritto.")
        else:
            print("✅ Nessuna regressione di qualità rilevata rispetto allo storico.")
    return code


if __name__ == "__main__":
    sys.exit(main())

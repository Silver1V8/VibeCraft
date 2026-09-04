"""Eval harness M1 — casi STRUTTURALI e MULTI-HOP (eval/golden_multihop.yaml).

Per ogni caso misura DUE strade sulla stessa domanda:
  A) baseline retrieval : GET /api/retrieve (k=10) -> recall dei matcher attesi
     (A "riuscito" = TUTTI i matcher in top-k, cioè recall == 1.0);
  B) riferimento grafo  : GET /api/graph/query (stessa q, più `target` se il caso lo
     dichiara) -> exact-node-match dell'atteso strutturale (intent + count + nodes +
     relations, tutti i vincoli dichiarati devono valere). Per i casi multihop, che non
     dichiarano un atteso di grafo, B è solo informativa (exact_match = null).

Verdetto TRIGGER per la milestone M2 (router strutturale davanti al retrieval):
`trigger_m2.fired` se ALMENO TRIGGER_MIN casi hanno A=fallito E B=riuscito.

Script SEPARATO da eval/run.py (non un flag --multihop) perché è il diff minore: lo
schema dei casi è diverso (kind/target/atteso graph vs lista di matcher), la misura è
doppia (A+B+delta) e il report ha un'altra forma — un flag avrebbe ramificato run.py in
run_eval/print_report/save_results senza riusare quasi nulla. La logica comune (matcher
e recall) resta condivisa via core.eval_metrics.

Uso (da rag/, server su):
    uv run python -m eval.run_multihop
    uv run python -m eval.run_multihop --url http://127.0.0.1:8000 --k 10

Exit code: 0 se la suite passa la soglia (`eval_multihop` in rag_config.yaml), 1 se no,
2 server giù. Il trigger M2 resta un VERDETTO storico, non un gate: scattò, il router
deterministico fu implementato, e da allora i casi che lo alimentavano passano anche B.
Report: eval/results/multihop_<timestamp>.json (esito A, esito B e delta per caso), più una
riga in eval/results/history.jsonl (source="multihop") e, se la soglia non è rispettata, un
alert critico in database/alerts.jsonl.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx2
import yaml

from core.config import EVAL_MULTIHOP_MIN_RECALL, EVAL_MULTIHOP_REQUIRE_GRAPH_EXACT
from core.eval_metrics import evaluate_case, result_matches

for _s in (sys.stdout, sys.stderr):  # emoji/à/-> safe su console Windows (cp1252)
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

EVAL_DIR = Path(__file__).parent
MULTIHOP = EVAL_DIR / "golden_multihop.yaml"
RESULTS_DIR = EVAL_DIR / "results"

K_DEFAULT = 10       # top-k della baseline A ("expected non in top-10" = A fallito)
TRIGGER_MIN = 3      # casi con A=fallito e B=riuscito perché il trigger M2 scatti


def load_cases(path: Path = MULTIHOP) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]


# ---------------------------------------------------------------------------
# Baseline A: retrieval
# ---------------------------------------------------------------------------

def eval_retrieval_case(case: dict, results: list[dict], k: int = K_DEFAULT) -> dict:
    """Esito della baseline A per un caso: recall@k dei matcher `expected.retrieval`
    (formato core.eval_metrics) e loro suddivisione trovati/mancanti entro il top-k.
    `passed` = TUTTI i matcher trovati (recall == 1.0): per un caso multihop un solo
    documento su due non basta a rispondere."""
    matchers = case["expected"]["retrieval"]
    topk = list(results)[:k]
    m = evaluate_case(topk, matchers, ks=(k,))
    found, missing = [], []
    for matcher in matchers:
        (found if any(result_matches(r, matcher) for r in topk) else missing).append(matcher)
    return {
        "recall": m[f"recall@{k}"],
        "passed": m[f"recall@{k}"] == 1.0,
        "best_rank": m["best_rank"],
        "n_expected": len(matchers),
        "found": found,
        "missing": missing,
    }


# ---------------------------------------------------------------------------
# Riferimento B: graph_query (exact-node-match)
# ---------------------------------------------------------------------------

def _response_nodes(resp: dict) -> set[str]:
    """Insieme dei nodi presenti in una risposta di graph_query, qualunque sia l'intent."""
    nodes: set[str] = set(resp.get("answer") or [])
    for ring in resp.get("rings") or []:          # intent "impatto"
        nodes.update(ring)
    for e in resp.get("out") or []:               # intent "relazioni"
        nodes.add(e.get("to"))
    for e in resp.get("in") or []:
        nodes.add(e.get("from"))
    if resp.get("target"):
        nodes.add(resp["target"])
    return nodes


def eval_graph_case(case: dict, resp: dict) -> dict:
    """Esito del riferimento B: exact-node-match dell'atteso `expected.graph`.
    Tutti i vincoli DICHIARATI devono valere: intent uguale, count uguale (se presente),
    ogni nodo di `nodes` presente nella risposta, ogni arco di `relations` presente tra
    gli out/in. Un caso senza atteso graph (multihop) restituisce exact_match = None:
    B è solo informativa e non concorre al trigger."""
    expected = (case.get("expected") or {}).get("graph")
    base = {"intent": resp.get("intent"), "count": resp.get("count")}
    if not expected:
        return {**base, "exact_match": None, "mismatches": []}

    mismatches: list[str] = []
    if resp.get("intent") != expected["intent"]:
        mismatches.append(f"intent: atteso {expected['intent']!r}, ottenuto {resp.get('intent')!r}")
    if "count" in expected and resp.get("count") != expected["count"]:
        mismatches.append(f"count: atteso {expected['count']}, ottenuto {resp.get('count')}")

    nodes = _response_nodes(resp)
    for wanted in expected.get("nodes") or []:
        if wanted not in nodes:
            mismatches.append(f"nodo assente: {wanted}")

    out_edges = {(e.get("relation"), e.get("to")) for e in resp.get("out") or []}
    in_edges = {(e.get("relation"), e.get("from")) for e in resp.get("in") or []}
    for rel in expected.get("relations") or []:
        pair = (rel["relation"], rel["node"])
        if pair not in out_edges and pair not in in_edges:
            mismatches.append(f"arco assente: {rel['relation']} <-> {rel['node']}")

    return {**base, "exact_match": not mismatches, "mismatches": mismatches}


# ---------------------------------------------------------------------------
# Trigger M2 e report
# ---------------------------------------------------------------------------

def trigger_m2(rows: list[dict], minimum: int = TRIGGER_MIN) -> dict:
    """Regola del trigger: scatta se ALMENO `minimum` casi hanno la baseline A fallita
    (expected non tutti in top-k) E il riferimento B riuscito (exact-node-match)."""
    qualifying = [r["q"] for r in rows
                  if not r["A"]["passed"] and r["B"]["exact_match"] is True]
    return {"fired": len(qualifying) >= minimum, "n_qualifying": len(qualifying),
            "minimum": minimum, "qualifying_cases": qualifying}


# ---------------------------------------------------------------------------
# Soglia (A4). Fino al 2026-09-03 questa suite non aveva alcun gate: girava a mano, e la
# classe di domande piu' preziosa per un grafo di governance poteva regredire senza che
# nulla lo dicesse.
# ---------------------------------------------------------------------------
def history_keys(report: dict) -> dict:
    """Le due misure che vanno nello storico (eval/results/history.jsonl, source="multihop").
    Chiavi PREFISSATE: finiscono nello stesso file del golden set single-hop, e `_series`
    seleziona per chiave — un "recall@10" nudo si mescolerebbe con quello dell'altra suite,
    che misura tutt'altro sugli stessi k."""
    agg = report["aggregate"]
    valutabili = agg["B_valutabili"] or 1
    return {f"multihop_recall@{report['k']}": agg["recall_media_A"],
            "multihop_graph_exact": agg["B_exact"] / valutabili}


def verdict(report: dict, *, min_recall: float = EVAL_MULTIHOP_MIN_RECALL,
            require_graph_exact: bool = EVAL_MULTIHOP_REQUIRE_GRAPH_EXACT) -> dict:
    """Esito del gate: `passed` piu' i motivi, in chiaro, di un eventuale fallimento.

    La soglia sta sulla recall MEDIA di A, non sui casi riusciti: quattro casi su 14 non
    possono passare per costruzione (11 documenti non entrano in 10 posizioni; le catene a
    tre documenti si fermano a due), ed e' il gap che questa suite esiste per quantificare.
    Gatare su "A riusciti" sarebbe gatare su un numero che il sistema non puo' far salire.

    Le attese strutturali di B, invece, si pretendono ESATTE: sono 6 casi verificati a mano
    sul grafo e asseriscono relazioni, non conteggi — se una si rompe e' una regressione del
    router. (L'unico `count` dichiarato, sull'enumerazione dei documenti, fu tolto proprio
    perche' faceva fallire il caso a ogni documento aggiunto: rumore, non regressione.)"""
    agg = report["aggregate"]
    motivi: list[str] = []
    if agg["recall_media_A"] < min_recall:
        motivi.append(f"recall media A = {agg['recall_media_A']:.3f} < soglia {min_recall}")
    if require_graph_exact and agg["B_exact"] < agg["B_valutabili"]:
        rotte = [r["q"] for r in report["cases"] if r["B"]["exact_match"] is False]
        motivi.append(f"attese strutturali non soddisfatte ({agg['B_exact']}/{agg['B_valutabili']}): "
                      + "; ".join(rotte))
    return {"passed": not motivi, "reasons": motivi,
            "min_recall": min_recall, "require_graph_exact": require_graph_exact}


def _delta(a: dict, b: dict) -> str:
    """Lettura sintetica del confronto per caso: dove il grafo risolve e il retrieval no
    (B>A, il caso che alimenta il trigger), il viceversa, il pareggio, o B non valutabile."""
    if b["exact_match"] is None:
        return "A-only"                      # caso multihop: B informativa
    if not a["passed"] and b["exact_match"]:
        return "B>A"
    if a["passed"] and not b["exact_match"]:
        return "A>B"
    return "pari" if a["passed"] else "entrambi-falliti"


def run(cases: list[dict], retrieve_fn, graph_fn, k: int = K_DEFAULT) -> dict:
    """Cuore della misura, separato da HTTP/argparse così i test lo esercitano con
    retriever/grafo fake deterministici. `retrieve_fn(q, k) -> list[dict]` (come in
    eval.run); `graph_fn(q, target|None) -> dict` (risposta di graph_query)."""
    rows: list[dict] = []
    for case in cases:
        results = list(retrieve_fn(case["q"], k))
        a = eval_retrieval_case(case, results, k=k)
        b = eval_graph_case(case, graph_fn(case["q"], case.get("target")))
        rows.append({"q": case["q"], "kind": case["kind"], "target": case.get("target"),
                     "A": a, "B": b, "delta": _delta(a, b)})

    trigger = trigger_m2(rows)
    n = len(rows) or 1
    aggregate = {
        "recall_media_A": sum(r["A"]["recall"] for r in rows) / n,
        "A_passed": sum(1 for r in rows if r["A"]["passed"]),
        "B_exact": sum(1 for r in rows if r["B"]["exact_match"] is True),
        "B_valutabili": sum(1 for r in rows if r["B"]["exact_match"] is not None),
    }
    return {"n": len(rows), "k": k, "trigger_m2": trigger,
            "aggregate": aggregate, "cases": rows}


def print_report(report: dict) -> None:
    print(f"{'kind':<11} {'A(recall)':>9} {'A':>4} {'B':>5} {'delta':<16} query")
    print("-" * 110)
    for r in report["cases"]:
        a_mark = "OK" if r["A"]["passed"] else "MISS"
        b = r["B"]["exact_match"]
        b_mark = "OK" if b else ("n/d" if b is None else "MISS")
        print(f"{r['kind']:<11} {r['A']['recall']:>9.2f} {a_mark:>4} {b_mark:>5} "
              f"{r['delta']:<16} {r['q'][:55]}")
    print("-" * 110)
    agg = report["aggregate"]
    trg = report["trigger_m2"]
    print(f"casi: {report['n']}  |  k={report['k']}  |  recall media A = {agg['recall_media_A']:.3f}"
          f"  |  A riusciti = {agg['A_passed']}/{report['n']}"
          f"  |  B exact = {agg['B_exact']}/{agg['B_valutabili']}")
    print(f"casi col gap retrieval->grafo ancora scoperto (A fallito, B riuscito): {trg['n_qualifying']}")
    print(f"  storico: a >={trg['minimum']} scatto' il trigger M2, il router deterministico fu "
          "implementato ed e' in servizio; qui piu' basso = meglio")
    esito = report.get("verdict")
    if esito:
        if esito["passed"]:
            print(f"✅ PASS  (recall media A >= {esito['min_recall']}"
                  + (", attese strutturali tutte soddisfatte" if esito["require_graph_exact"] else "")
                  + ")")
        else:
            print("❌ FAIL  " + " | ".join(esito["reasons"]))


def save_report(report: dict, url: str) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"multihop_{ts}.json"
    payload = {"timestamp": datetime.now().isoformat(timespec="seconds"), "url": url,
               "golden_set": MULTIHOP.name, **report}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Eval M1: casi strutturali/multihop, baseline A (retrieve) vs riferimento B (graph_query)")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--k", type=int, default=K_DEFAULT, help=f"top-k della baseline A (default: {K_DEFAULT})")
    ap.add_argument("--no-save", action="store_true", help="non salvare il JSON in eval/results/")
    a = ap.parse_args()

    cases = load_cases()
    try:
        with httpx2.Client(timeout=180) as client:
            def retrieve_fn(q: str, k: int) -> list[dict]:
                resp = client.get(f"{a.url}/api/retrieve", params={"q": q, "k": k})
                resp.raise_for_status()
                return resp.json()["results"]

            def graph_fn(q: str, target: str | None) -> dict:
                params = {"q": q}
                if target:
                    params["target"] = target
                resp = client.get(f"{a.url}/api/graph/query", params=params)
                resp.raise_for_status()
                return resp.json()

            report = run(cases, retrieve_fn, graph_fn, k=a.k)
    except httpx2.HTTPError as e:
        print(f"❌ server non raggiungibile: {e}\n   Avvia il server: python server.py")
        return 2

    report["verdict"] = verdict(report)
    print_report(report)
    if not a.no_save:
        out = save_report(report, a.url)
        print(f"\n💾 Report salvato in {out}")
        # Storico e allarme condividono la sorte del report: --no-save vuol dire "questa
        # corsa non lascia traccia", e vale per tutte e tre le tracce, non solo per il JSON.
        try:
            from core.artifacts import current_version
            from core.eval_history import record_history
            record_history(history_keys(report), n_cases=report["n"],
                           version=current_version(), source="multihop")
        except Exception as exc:  # lo storico è telemetria: non deve far fallire la misura
            print(f"(storico non aggiornato: {exc})")
        if not report["verdict"]["passed"]:
            # L'ALLARME, che era la parte mancante di A4: senza, una regressione su questa
            # suite restava un exit code che nessuno guardava. alerts.jsonl è il canale che
            # /api/health espone come `last_alert`.
            try:
                from core.eval_gate import record_alert
                record_alert("critical",
                             "Regressione sulla suite strutturale/multihop: "
                             + " | ".join(report["verdict"]["reasons"]),
                             source_check="eval.run_multihop", **history_keys(report))
            except Exception as exc:
                print(f"(alert non registrato: {exc})")
    return 0 if report["verdict"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

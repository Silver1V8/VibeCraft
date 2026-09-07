"""Misura del TAGLIO `retrieval.graph_context_max_chunks` sulle catene multihop (S11, R23).

Perché non sta nella griglia di eval/calibrate_authority: quel parametro non è un peso del
ranking, è un tetto nel ramo GRAFO di /ask (api/routes_retrieval.ask_rag, fase 6 di
[REGOLA-WF-01]) — quante sezioni raggiunte SOLO via grafo entrano nel contesto dell'LLM,
dopo il ramo semantico. Nessuna delle due suite di retrieval lo attraversa: eval.run e
eval.run_multihop misurano GET /api/retrieve, che si ferma a hybrid_search. L'unica misura
che lo tocca è quella che R9/S6 hanno fatto a mano: la fonte attesa ENTRA nella finestra di
/ask, sì o no. Qui quella misura è ripetibile.

Cosa fa: costruisce il contesto di /ask ESATTAMENTE come il server (stessa app, stesso
lifespan, stesso ranking, stesso ramo grafo — in-process, con il solo LLM sostituito da uno
stub che restituisce una stringa vuota, perché la generazione non c'entra e costa 20-60 s a
chiamata), e per ogni valore del tetto conta quante fonti attese dalle catene multihop
(eval/golden_multihop.yaml, kind: multihop) stanno nella finestra — distinguendo quelle
arrivate dal ramo semantico da quelle arrivate SOLO via grafo, che sono le uniche che il
tetto governa.

Cosa NON è: una cross-validation. Otto catene sono un insieme su cui scegliere un intero
fra 0 e 6, non un campione su cui stimare un guadagno fuori campione; il numero onesto è
"quante catene hanno tutte le fonti in finestra, e quante sezioni costa". Il tie-break è
lo stesso di grid_best: a parità di catene complete vince il valore ATTUALE, e fra due
valori NUOVI a pari merito il più basso (è un tetto: ogni sezione in più è contesto che
l'LLM legge e paga). NON applica nulla: scrive eval/results/graph_context_calibrated.yaml.

Uso (da rag/, server GIÙ — carica la stessa app in-process, e Qdrant deve essere su):
    uv run python -m eval.calibrate_graph_context
    uv run python -m eval.calibrate_graph_context --values 0 1 2 3 4 6 --top-k 5
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

from core.config import GRAPH_CONTEXT_MAX_CHUNKS
from core.eval_metrics import result_matches
from eval.run_multihop import load_cases

for _s in (sys.stdout, sys.stderr):  # emoji/§/→ safe su console Windows (cp1252)
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

RESULTS_DIR = Path(__file__).parent / "results"
# Intestazione di un blocco di contesto documentale in ask_rag: `--- doc § sezione [meta] ---`.
# I blocchi via grafo portano "via grafo" nei meta; quelli di codice hanno un'altra forma
# (`--- Codice esistente: ...`) e non sono fonti documentali.
_BLOCCO = re.compile(r"^--- (?P<doc>.+?) § (?P<sec>.*?) \[(?P<meta>[^\]]*)\] ---$", re.M)


def blocchi_del_contesto(context_text: str, chunks: dict) -> list[dict]:
    """I blocchi documentali del contesto come risultati valutabili da core.eval_metrics
    (doc_id/section/chunk_id), con `via_grafo` True per quelli iniettati dal ramo grafo. Il
    chunk_id è ricostruito dal sidecar dei chunk per (doc_id, sezione), così anche i matcher
    `chunk`/`any`/`file` funzionano."""
    per_doc_sezione = {(e.get("doc_id", ""), e.get("section", "")): cid
                       for cid, e in chunks.items()}
    return [{"doc_id": m["doc"], "section": m["sec"],
             "chunk_id": per_doc_sezione.get((m["doc"], m["sec"]), ""),
             "via_grafo": "via grafo" in m["meta"]}
            for m in _BLOCCO.finditer(context_text)]


def esito_caso(case: dict, blocchi: list[dict], caratteri: int = 0) -> dict:
    """Per ogni matcher atteso: in finestra dal ramo semantico, SOLO via grafo, o assente."""
    semantici = [b for b in blocchi if not b["via_grafo"]]
    grafo = [b for b in blocchi if b["via_grafo"]]
    def _stato(matcher: dict) -> str:
        if any(result_matches(b, matcher) for b in semantici):
            return "semantico"
        if any(result_matches(b, matcher) for b in grafo):
            return "grafo"
        return "assente"
    matchers = case["expected"]["retrieval"]
    stato = [_stato(m) for m in matchers]
    # A livello di DOCUMENTO (solo la chiave `doc` del matcher): è ciò che il tetto governa
    # davvero — quante fonti entrano — mentre QUALE sezione di quel documento entra lo decide
    # l'ordinamento pertinenza × fiducia × autorità (R9), non il tetto. R9 misurò a questo
    # livello ("il documento entra, la sua sezione Immutabilità no").
    stato_doc = [_stato({"doc": m["doc"]}) if m.get("doc") else s_ for m, s_ in zip(matchers, stato)]
    return {"q": case["q"], "atteso": stato, "atteso_doc": stato_doc,
            "completo": "assente" not in stato,
            "completo_doc": "assente" not in stato_doc,
            "solo_via_grafo": stato.count("grafo"),
            "blocchi_grafo": len(grafo), "blocchi_totali": len(blocchi),
            "caratteri": caratteri}


def scegli(per_valore: dict[int, dict], attuale: int) -> int:
    """Massimo di catene complete a livello di DOCUMENTO (è ciò che il tetto governa), poi a
    livello di sezione; a parità vince l'attuale, poi il tetto più BASSO."""
    def chiave(v: int):
        return (per_valore[v]["catene_complete_doc"], per_valore[v]["catene_complete"],
                v == attuale, -v)
    return max(per_valore, key=chiave)


def main() -> int:
    ap = argparse.ArgumentParser(description="Misura di graph_context_max_chunks sulle catene multihop")
    ap.add_argument("--values", type=int, nargs="+", default=[0, 1, 2, 3, 4, 6],
                    help="valori del tetto da misurare (default: 0 1 2 3 4 6; 0 = ramo spento)")
    ap.add_argument("--top-k", type=int, default=5,
                    help="top_k del ramo semantico di /ask (default: 5, il default di AskQuery)")
    a = ap.parse_args()
    if GRAPH_CONTEXT_MAX_CHUNKS not in a.values:
        a.values.append(GRAPH_CONTEXT_MAX_CHUNKS)  # l'attuale è sempre nel confronto

    from fastapi.testclient import TestClient

    from api import deps, routes_retrieval
    from core import llm
    from server import app

    deps.API_KEY = None  # client locale, come la console

    async def _senza_llm(prompt: str, *, purpose: str) -> str:
        return ""
    llm.agenerate = _senza_llm
    # La cache di /ask è per domanda: servirebbe la finestra del PRIMO valore a tutti gli altri.
    routes_retrieval._cache_get = lambda app_, key: None
    routes_retrieval._cache_set = lambda app_, key, payload: None

    cases = [c for c in load_cases() if c.get("kind") == "multihop"]
    print(f"Catene multihop: {len(cases)}. Tetti da misurare: {sorted(a.values)}. "
          f"Avvio dell'app in-process (modello + Qdrant + artefatti)...")
    per_valore: dict[int, dict] = {}
    with TestClient(app, client=("127.0.0.1", 54321)) as client:
        chunks = deps.current_snapshot().chunks
        for tetto in sorted(a.values):
            routes_retrieval.GRAPH_CONTEXT_MAX_CHUNKS = tetto
            esiti = []
            for case in cases:
                r = client.post("/ask", json={"question": case["q"], "top_k": a.top_k})
                r.raise_for_status()
                ctx = (r.json().get("graph_context") or {}).get("context_text")
                if ctx is None:  # ramo deterministico del router M2: nessuna finestra
                    continue
                esiti.append(esito_caso(case, blocchi_del_contesto(ctx, chunks), len(ctx)))
            n = len(esiti)
            per_valore[tetto] = {
                "catene_complete": sum(e["completo"] for e in esiti),
                "catene_complete_doc": sum(e["completo_doc"] for e in esiti),
                "documenti_solo_via_grafo": sum(e["atteso_doc"].count("grafo") for e in esiti),
                "fonti_solo_via_grafo": sum(e["solo_via_grafo"] for e in esiti),
                "fonti_in_finestra": sum(1 for e in esiti for s in e["atteso"] if s != "assente"),
                "fonti_attese": sum(len(e["atteso"]) for e in esiti),
                "blocchi_grafo_medi": round(sum(e["blocchi_grafo"] for e in esiti) / n, 2) if n else 0,
                # Il COSTO del tetto: caratteri del contesto che l'LLM legge (documenti + codice).
                "caratteri_medi": round(sum(e["caratteri"] for e in esiti) / n) if n else 0,
                "casi": esiti,
            }
            print(f"  tetto={tetto}: complete {per_valore[tetto]['catene_complete']}/{n} "
                  f"(a livello documento {per_valore[tetto]['catene_complete_doc']}/{n}), "
                  f"fonti in finestra {per_valore[tetto]['fonti_in_finestra']}/"
                  f"{per_valore[tetto]['fonti_attese']} (solo via grafo: "
                  f"{per_valore[tetto]['fonti_solo_via_grafo']}), blocchi grafo medi "
                  f"{per_valore[tetto]['blocchi_grafo_medi']}, contesto medio "
                  f"{per_valore[tetto]['caratteri_medi']} caratteri")

    scelto = scegli(per_valore, GRAPH_CONTEXT_MAX_CHUNKS)
    print("\n" + "=" * 68)
    print(f"graph_context_max_chunks — {len(cases)} catene multihop, top_k={a.top_k}")
    print("=" * 68)
    print(f"  {'tetto':>5}  {'complete':>8}  {'compl.(doc)':>11}  {'in finestra':>11}  "
          f"{'solo grafo':>10}  {'doc solo grafo':>14}  {'blocchi grafo':>13}  {'caratteri':>9}")
    for tetto, r in sorted(per_valore.items()):
        segno = " ← attuale" if tetto == GRAPH_CONTEXT_MAX_CHUNKS else ""
        print(f"  {tetto:>5}  {r['catene_complete']:>8}  {r['catene_complete_doc']:>11}  "
              f"{r['fonti_in_finestra']:>4}/{r['fonti_attese']:<6}  "
              f"{r['fonti_solo_via_grafo']:>10}  {r['documenti_solo_via_grafo']:>14}  "
              f"{r['blocchi_grafo_medi']:>13}  {r['caratteri_medi']:>9}{segno}")
    # Quali fonti il tetto governa davvero: quelle che a tetto 0 sono assenti e a un tetto
    # >0 arrivano via grafo. Se nessuna, il tetto oggi non decide nulla sulle catene.
    if scelto == GRAPH_CONTEXT_MAX_CHUNKS:
        print(f"\n  ✅ Il valore attuale ({GRAPH_CONTEXT_MAX_CHUNKS}) resta: nessun tetto porta più "
              "catene complete. Nessuna modifica consigliata.")
    else:
        print(f"\n  ⚠️  tetto={scelto} porta più catene complete dell'attuale (a livello "
              f"documento {per_valore[scelto]['catene_complete_doc']} vs "
              f"{per_valore[GRAPH_CONTEXT_MAX_CHUNKS]['catene_complete_doc']}). Proposta da rivedere "
              "a mano in rag_config.yaml → retrieval.graph_context_max_chunks.")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / "graph_context_calibrated.yaml"
    out.write_text(yaml.safe_dump({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "top_k": a.top_k, "n_cases": len(cases),
        "current": GRAPH_CONTEXT_MAX_CHUNKS, "chosen": scelto,
        "recommendation": "NON_APPLICARE" if scelto == GRAPH_CONTEXT_MAX_CHUNKS else "APPLICA",
        "per_value": {v: {k: r[k] for k in r if k != "casi"} for v, r in sorted(per_valore.items())},
        "cases": {v: r["casi"] for v, r in sorted(per_valore.items())},
    }, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"\n  💾 Report scritto in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

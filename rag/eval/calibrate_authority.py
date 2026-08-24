"""Calibrazione dei pesi di autorità sul golden set (Epic 3 — versione definitiva).

Idea chiave: l'autorità influenza SOLO il re-ranking finale del retrieval, non il recupero dei
candidati. Quindi si recuperano i candidati UNA volta per domanda (in-process: modello bge-m3 +
Qdrant caricati una sola volta) e poi si RI-ORDINA offline per ogni combinazione di parametri —
niente re-embed, niente restart del server per combinazione.

FEDELTÀ ALLA PRODUZIONE — è la premessa che rende sensato tutto il resto. Il ri-ranking offline
deve riprodurre ESATTAMENTE gli stadi finali di hybrid_search, altrimenti si ottimizza un
ordinamento che nessuno servirà mai e il guadagno riportato non vuol dire niente. Gli stadi sono
tre e vanno tenuti allineati a mano ogni volta che il retrieval cambia:

  1. peso di autorità per candidato — `authority` DICHIARATA nel frontmatter con precedenza sul
     peso di classe (S1, ADR 0002). Finché questo script leggeva solo `classification`/`status`,
     14 dei 26 documenti del corpus venivano appiattiti sul default_weight (0.70) mentre la
     produzione usava i valori dichiarati (0.75-0.90): la griglia su default_weight misurava un
     mondo controfattuale;
  2. rank_by_authority(alpha) — condivisa con la produzione, mai duplicata qui;
  3. apply_precedence(graph) — precedenza dichiarata fra fonti (S4), ultimo stadio.

Nota sulla leva: con `use_declared: true` il parametro `default_weight` conta SOLO per le fonti
che non dichiarano un'autorità propria. È corretto che sia così — è ciò che fa la produzione — ma
significa che la griglia su quel parametro ha oggi molta meno presa di quanta ne avesse prima di
S1, e un guadagno vicino a zero su quell'asse va letto in questa luce.

Si calibrano due parametri interpretabili:
  - boost_alpha    : forza del boost di autorità (mult = 1-alpha + alpha*peso). alpha=0 ignora
                     l'autorità (ranking puramente semantico); alpha alto la premia di più.
  - default_weight : peso delle classi non elencate (es. le spec REQUIREMENTS). Alzarlo riduce lo
                     svantaggio delle spec rispetto ai safeguard IRON_MEMORY (peso 1.0).

La qualità si misura con k-fold cross-validation ONESTA: il parametro scelto sui fold di training
è valutato sul fold held-out. Il guadagno riportato è quello di validazione, non in-sample: è
l'unico numero che non fa overfit su 34 casi. NON applica nulla: scrive solo una proposta in
eval/results/authority_calibrated.yaml, da rivedere e applicare a mano in rag_config.yaml.

Uso (da rag/, niente server necessario — gira in-process):
    uv run python -m eval.calibrate_authority
    uv run python -m eval.calibrate_authority --k 10 --folds 5 --seed 0
"""
import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path

import yaml

from core import retrieval
from core.artifacts import load_artifacts
from core.config import (
    AUTHORITY_ARCHIVED_DECAY,
    AUTHORITY_BOOST_ALPHA,
    AUTHORITY_DEFAULT_WEIGHT,
    AUTHORITY_USE_DECLARED,
    EMBEDDING_MODEL,
    QDRANT_API_KEY,
    QDRANT_URL,
)
from core.eval_metrics import evaluate
from eval.run import load_cases

for _s in (sys.stdout, sys.stderr):  # emoji/§/→ safe su console Windows (cp1252)
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

RESULTS_DIR = Path(__file__).parent / "results"

# Griglia di ricerca (coordinate discrete). Il default (alpha=0.4, default_weight=0.4) è incluso
# così il confronto "attuale vs calibrato" è sempre nella griglia.
ALPHAS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0]
DEFAULT_WEIGHTS = [0.4, 0.5, 0.6, 0.7, 0.85, 1.0]
FETCH_CANDIDATES = 50  # quanti candidati recuperare per domanda (>= max k valutato, con margine)


def retrieve_candidate_cache(cases, *, qdrant, embed_model, colbert_store, graph) -> dict:
    """Recupera e memorizza i candidati (con classification/status grezzi, colbert_score,
    fused_rank_sum) UNA volta per domanda: il costoso retrieval si paga una sola volta, poi la
    grid search lavora solo di re-ranking in RAM.

    `graph` è passato a hybrid_search perché il POOL sia lo stesso della produzione: la
    precedenza fra fonti riordina PRIMA del taglio a FETCH_CANDIDATES, quindi senza grafo
    l'insieme dei candidati potrebbe non essere quello che il retrieval reale produce."""
    cache: dict[str, list[dict]] = {}
    for i, case in enumerate(cases, 1):
        q = case["q"]
        cache[q] = retrieval.hybrid_search(q, FETCH_CANDIDATES, qdrant=qdrant,
                                           embed_model=embed_model, colbert_store=colbert_store,
                                           graph=graph)
        print(f"  candidati {i}/{len(cases)} recuperati", end="\r")
    print()
    return cache


def _attrs_for(candidate: dict, graph) -> dict:
    """Attributi di governance della sorgente di un candidato, come li vede la PRODUZIONE.

    In produzione _authority_weight riceve il payload Qdrant INTERO, che porta tutto il
    frontmatter del documento — `authority` DICHIARATA compresa (S1). Qui il payload non e' in
    cache, ma il nodo del grafo porta gli stessi attributi (le sezioni li ereditano dal
    documento padre), quindi si legge di lì. Il fallback su classification/status della cache
    copre il caso in cui il nodo non esista (chunk di un documento non presente nel grafo)."""
    for node_id in (candidate.get("chunk_id"), candidate.get("doc_id")):
        if node_id and graph is not None and node_id in graph:
            return graph.nodes[node_id]
    return {"classification": candidate.get("classification", ""),
            "status": candidate.get("status", "")}


def make_retrieve_fn(cache: dict, *, alpha: float, default_weight: float, graph):
    """retrieve_fn(query, k) che RI-ORDINA i candidati in cache con i parametri dati, riusando
    ESATTAMENTE la ri-ponderazione e l'ordinamento di produzione: stesso peso di autorità
    (dichiarata inclusa), stesso rank_by_authority, stessa apply_precedence, nello stesso
    ordine. Se questi due percorsi divergono, la calibrazione ottimizza un ranking che nessuno
    servirà mai, e il guadagno riportato non vuol dire niente."""
    def retrieve(query: str, k: int) -> list[dict]:
        cands = [dict(c) for c in cache[query]]
        for c in cands:
            c["authority"] = round(retrieval._authority_weight(
                _attrs_for(c, graph), default=default_weight, decay=AUTHORITY_ARCHIVED_DECAY,
                use_declared=AUTHORITY_USE_DECLARED), 3)
        retrieval.rank_by_authority(cands, alpha=alpha)
        # Precedenza dichiarata fra fonti (S4): ultimo stadio anche in produzione, dopo
        # l'autorità. È un riordino booleano indipendente da (alpha, default_weight), quindi
        # non muove la griglia, ma senza di esso l'ordine valutato non è quello servito.
        cands = retrieval.apply_precedence(cands, graph=graph)
        return cands[:k]
    return retrieve


def mean_recall(cases, cache, *, alpha, default_weight, k, graph) -> float:
    fn = make_retrieve_fn(cache, alpha=alpha, default_weight=default_weight, graph=graph)
    return evaluate(cases, fn, ks=[k])["aggregate"][f"recall@{k}"]


def grid_best(cases, cache, *, k, graph):
    """Miglior (alpha, default_weight) sulla griglia per recall@k medio sui `cases` dati."""
    best = None
    for a in ALPHAS:
        for dw in DEFAULT_WEIGHTS:
            r = mean_recall(cases, cache, alpha=a, default_weight=dw, k=k, graph=graph)
            if best is None or r > best[0]:
                best = (r, a, dw)
    return best  # (recall, alpha, default_weight)


def kfold_cv(cases, cache, *, k, folds, seed, graph):
    """k-fold CV: per ogni fold held-out, sceglie i parametri sui restanti e li valuta sul fold.
    Restituisce (recall medio held-out coi parametri CALIBRATI, recall medio held-out coi DEFAULT)."""
    idx = list(range(len(cases)))
    random.Random(seed).shuffle(idx)
    buckets = [idx[i::folds] for i in range(folds)]
    cal_scores, def_scores = [], []
    for f in range(folds):
        val = [cases[i] for i in buckets[f]]
        train = [cases[i] for i in idx if i not in set(buckets[f])]
        if not val or not train:
            continue
        _, a, dw = grid_best(train, cache, k=k, graph=graph)
        cal_scores.append(mean_recall(val, cache, alpha=a, default_weight=dw, k=k, graph=graph))
        def_scores.append(mean_recall(val, cache, alpha=AUTHORITY_BOOST_ALPHA,
                                      default_weight=AUTHORITY_DEFAULT_WEIGHT, k=k, graph=graph))
    avg = lambda xs: sum(xs) / len(xs) if xs else 0.0
    return avg(cal_scores), avg(def_scores)


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibrazione dei pesi di autorità sul golden set")
    ap.add_argument("--k", type=int, default=10, help="soglia di recall da ottimizzare (default: 10)")
    ap.add_argument("--folds", type=int, default=5, help="numero di fold per la CV (default: 5)")
    ap.add_argument("--seed", type=int, default=0, help="seed dello shuffle dei fold (default: 0)")
    ap.add_argument("--min-gain", type=float, default=0.015,
                    help="guadagno minimo di recall in validazione per proporre la calibrazione (default: 0.015)")
    a = ap.parse_args()

    print("Caricamento artefatti + modello + Qdrant (in-process)...")
    from FlagEmbedding import BGEM3FlagModel
    from qdrant_client import QdrantClient
    arts = load_artifacts(required=("graph", "colbert", "chunks"))
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)

    cases = load_cases()
    print(f"Golden set: {len(cases)} casi. Recupero candidati (una volta per domanda)...")
    cache = retrieve_candidate_cache(cases, qdrant=qdrant, embed_model=embed_model,
                                     colbert_store=arts.colbert_store, graph=arts.graph)

    default_full = mean_recall(cases, cache, alpha=AUTHORITY_BOOST_ALPHA,
                               default_weight=AUTHORITY_DEFAULT_WEIGHT, k=a.k, graph=arts.graph)
    best_full = grid_best(cases, cache, k=a.k, graph=arts.graph)
    cal_cv, def_cv = kfold_cv(cases, cache, k=a.k, folds=a.folds, seed=a.seed, graph=arts.graph)

    print("\n" + "=" * 68)
    print(f"Calibrazione autorità — recall@{a.k}  (golden set: {len(cases)} casi)")
    print("=" * 68)
    print(f"  DEFAULT attuale   alpha={AUTHORITY_BOOST_ALPHA}  default_weight={AUTHORITY_DEFAULT_WEIGHT}"
          f"   → recall in-sample {default_full:.3f}")
    print(f"  MIGLIORE griglia  alpha={best_full[1]}  default_weight={best_full[2]}"
          f"   → recall in-sample {best_full[0]:.3f}  (ottimista, non fidarsi)")
    print(f"\n  CROSS-VALIDATION ({a.folds}-fold, seed={a.seed}) — l'unico numero onesto:")
    print(f"    default   : recall@{a.k} held-out medio = {def_cv:.3f}")
    print(f"    calibrato : recall@{a.k} held-out medio = {cal_cv:.3f}")
    gain = cal_cv - def_cv
    print(f"    guadagno di validazione = {gain:+.3f}")

    proposal = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "metric": f"recall@{a.k}",
        "cv": {"folds": a.folds, "seed": a.seed,
               "default_recall": round(def_cv, 4), "calibrated_recall": round(cal_cv, 4),
               "gain": round(gain, 4)},
        "in_sample_best": {"alpha": best_full[1], "default_weight": best_full[2],
                           "recall": round(best_full[0], 4)},
        "default": {"alpha": AUTHORITY_BOOST_ALPHA, "default_weight": AUTHORITY_DEFAULT_WEIGHT,
                    "recall": round(default_full, 4)},
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / "authority_calibrated.yaml"
    if gain >= a.min_gain:
        proposal["recommendation"] = "APPLICA"
        proposal["proposed_authority_yaml"] = {
            "boost_alpha": best_full[1], "default_weight": best_full[2]}
        print(f"\n  ✅ Guadagno ≥ soglia ({a.min_gain}): calibrazione PROPOSTA.")
        print(f"     Applica a mano in rag_config.yaml → authority: "
              f"boost_alpha={best_full[1]}, default_weight={best_full[2]}")
    else:
        proposal["recommendation"] = "NON_APPLICARE"
        print(f"\n  ⚠️  Guadagno < soglia ({a.min_gain}): i pesi a mano REGGONO. Nessuna modifica consigliata.")
        print("     (È un risultato valido: il ranking semantico è già forte; non forzare l'autorità.)")
    out.write_text(yaml.safe_dump(proposal, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"\n  💾 Report scritto in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

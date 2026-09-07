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

Si calibrano quattro parametri interpretabili, IN UNA GRIGLIA SOLA (S11, R20):
  - boost_alpha         : forza del boost di autorità (mult = 1-alpha + alpha*peso). alpha=0 ignora
                          l'autorità (ranking puramente semantico); alpha alto la premia di più.
  - default_weight      : peso delle classi non elencate (es. le spec REQUIREMENTS). Alzarlo riduce
                          lo svantaggio delle spec rispetto ai safeguard IRON_MEMORY (peso 1.0).
  - unclassified_weight : peso di una fonte SENZA alcuna classification (S1, ADR 0002). È il terzo
                          asse dal 2026-08-24: prima di S1 non esisteva come parametro distinto, e
                          lasciarlo fuori dalla griglia significherebbe calibrare due terzi del
                          meccanismo. Nel corpus attuale governa i 6 file di 03_changes_historical/,
                          che sono privi di frontmatter.
  - section_restatement_weight : peso di SEZIONE (N4) — moltiplicatore delle sezioni che
                          CITANO codici di regola senza dichiararne (rank_by_authority). Quarto
                          asse dal 2026-09-07 (S11): fino ad allora era calibrato A PARTE, con
                          alpha fermo, e alpha era stato calibrato con questo peso a 1.0. R20 ha
                          misurato che l'ottimo di alpha si MUOVE quando cambia questo peso
                          (verdetto di calibrate_authority ribaltato da N4): sono accoppiati, e
                          due calibrazioni separate non provano che la coppia sia ottima.
                          `graph_context_max_chunks` NON è in questa griglia: è un taglio nel
                          ramo grafo di /ask, non un peso del ranking — vedi
                          eval/calibrate_graph_context.py.

La qualità si misura con k-fold cross-validation ONESTA: il parametro scelto sui fold di training
è valutato sul fold held-out. Il guadagno riportato è quello di validazione, non in-sample: è
l'unico numero che non fa overfit su 34 casi. NON applica nulla: scrive solo una proposta in
eval/results/authority_calibrated.yaml, da rivedere e applicare a mano in rag_config.yaml.

Uso (da rag/, niente server necessario — gira in-process):
    uv run python -m eval.calibrate_authority
    uv run python -m eval.calibrate_authority --k 1 --folds 5 --seed 0 1 2 3 4
"""
import argparse
import random
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

from core import retrieval
from core.artifacts import load_artifacts
from core.config import (
    AUTHORITY_ARCHIVED_DECAY,
    AUTHORITY_BOOST_ALPHA,
    AUTHORITY_DEFAULT_WEIGHT,
    AUTHORITY_UNCLASSIFIED_WEIGHT,
    AUTHORITY_USE_DECLARED,
    EMBEDDING_MODEL,
    QDRANT_API_KEY,
    QDRANT_URL,
    SECTION_RESTATEMENT_WEIGHT,
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
UNCLASSIFIED_WEIGHTS = [0.1, 0.2, 0.3, 0.5, 0.7]
# 1.0 = peso di sezione SPENTO (l'ordinamento di prima di N4) è nella griglia di proposito:
# se vincesse, N4 andrebbe ritirato, non solo ricalibrato.
RESTATEMENT_WEIGHTS = [1.0, 0.98, 0.95, 0.92, 0.9, 0.85, 0.8, 0.7]
FETCH_CANDIDATES = 50  # quanti candidati recuperare per domanda (>= max k valutato, con margine)
# La configurazione di PRODUZIONE, nell'ordine delle coordinate della griglia: è l'incumbent
# del tie-break e il "default" della CV.
ATTUALE = (AUTHORITY_BOOST_ALPHA, AUTHORITY_DEFAULT_WEIGHT, AUTHORITY_UNCLASSIFIED_WEIGHT,
           SECTION_RESTATEMENT_WEIGHT)


def _kw(punto) -> dict:
    """Coordinate della griglia → argomenti nominali di mean_recall/make_retrieve_fn."""
    a, dw, uw, rw = punto
    return dict(alpha=a, default_weight=dw, unclassified_weight=uw, restatement_weight=rw)


def retrieve_candidate_cache(cases, *, qdrant, embed_model, colbert_store, graph,
                             restatements) -> dict:
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
                                           graph=graph, restatements=restatements)
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


def make_retrieve_fn(cache: dict, *, alpha: float, default_weight: float,
                     unclassified_weight: float, graph, restatements,
                     restatement_weight: float = SECTION_RESTATEMENT_WEIGHT):
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
                use_declared=AUTHORITY_USE_DECLARED,
                unclassified=unclassified_weight), 3)
        retrieval.rank_by_authority(cands, alpha=alpha, restatements=restatements,
                                    restatement_weight=restatement_weight)
        # Precedenza dichiarata fra fonti (S4): ultimo stadio anche in produzione, dopo
        # l'autorità. È un riordino booleano indipendente da (alpha, default_weight), quindi
        # non muove la griglia, ma senza di esso l'ordine valutato non è quello servito.
        cands = retrieval.apply_precedence(cands, graph=graph)
        return cands[:k]
    return retrieve


def mean_recall(cases, cache, *, alpha, default_weight, unclassified_weight, k, graph, restatements,
                restatement_weight: float = SECTION_RESTATEMENT_WEIGHT,
                subset: str = "all") -> float:
    """recall@k medio. `subset="adversarial"` restringe ai casi marcati `adversarial: true`
    nel golden set — il sottoinsieme che l'ADR 0002 deve muovere e che nella media coi casi
    facili sarebbe invisibile. 0.0 se il sottoinsieme è vuoto."""
    fn = make_retrieve_fn(cache, alpha=alpha, default_weight=default_weight,
                          unclassified_weight=unclassified_weight, graph=graph,
                          restatements=restatements, restatement_weight=restatement_weight)
    report = evaluate(cases, fn, ks=[k])
    if subset == "adversarial":
        adv = report.get("adversarial")
        return adv["aggregate"][f"recall@{k}"] if adv else 0.0
    return report["aggregate"][f"recall@{k}"]


def griglia(cases, cache, *, k, graph, restatements) -> dict[tuple, float]:
    """recall@k per OGNI punto della griglia. Restituita per intero, non solo il massimo:
    serve a `assi_morti()` per dire quali parametri non muovono affatto la metrica."""
    return {(a, dw, uw, rw): mean_recall(cases, cache, alpha=a, default_weight=dw,
                                         unclassified_weight=uw, k=k, graph=graph,
                                         restatements=restatements, restatement_weight=rw)
            for a in ALPHAS for dw in DEFAULT_WEIGHTS for uw in UNCLASSIFIED_WEIGHTS
            for rw in RESTATEMENT_WEIGHTS}


def grid_best(cases, cache, *, k, graph, restatements, tabella: dict | None = None):
    """Miglior (alpha, default_weight, unclassified_weight, section_restatement_weight) per
    recall@k medio.

    A parità di recall vince la configurazione ATTUALE DI PRODUZIONE, non la prima
    incontrata. Non è un dettaglio estetico: su questo corpus DUE dei tre assi non muovono
    la metrica di un millesimo (misurato il 2026-08-24 — `default_weight` non governa alcun
    documento, perché tutti e 26 o dichiarano `authority` o hanno la classe elencata;
    `unclassified_weight` non riordina nulla ad alpha basso). Ogni valore di alpha ha quindi
    30 configurazioni ESATTAMENTE equivalenti, e sciogliere quel pareggio in base all'ordine
    di iterazione significa far scegliere al caso — con l'aggravante che dentro la k-fold la
    scelta cambia da fold a fold e finisce nella stima held-out come rumore puro.

    Quanto rumore: prima di questo tie-break il guadagno di validazione a k=2 è passato da
    -0.011 a +0.013 fra due corse che differivano per la sola ri-segmentazione di UN
    documento su 26 — uno spostamento di 0.024, quasi il doppio della dev.std riportata
    sui seed. La dev.std sui seed misura il rumore di partizione, non questo, e da sola
    dava una falsa impressione di stabilità.

    L'incumbent vince i pareggi anche per una ragione di merito, non solo di rumore: una
    modifica del ranking di produzione va giustificata da un miglioramento, e un pareggio
    non è un miglioramento."""
    tabella = tabella if tabella is not None else griglia(cases, cache, k=k, graph=graph,
                                                         restatements=restatements)
    # L'incumbent parte in testa: solo un `>` stretto lo scalza. E fra due punti NUOVI a
    # pari recall vince quello che cambia MENO coordinate rispetto alla produzione (S11):
    # con un asse morto ogni vincitore ha decine di gemelli identici, e senza questo
    # criterio la proposta porterebbe con sé valori "vincenti" scelti dall'ordine di
    # iterazione della griglia — un cambio di produzione che nessuna misura giustifica.
    def _distanza(punto) -> int:
        return sum(1 for x, y in zip(punto, ATTUALE) if x != y)
    best = (tabella.get(ATTUALE, -1.0), *ATTUALE)
    for punto, r in tabella.items():
        if r > best[0] or (r == best[0] and _distanza(punto) < _distanza(best[1:])):
            best = (r, *punto)
    return best  # (recall, alpha, default_weight, unclassified_weight, section_restatement_weight)


def assi_morti(tabella: dict) -> list[str]:
    """Assi della griglia che non cambiano la recall di un millesimo, a parità degli altri
    due. Un asse morto non è un parametro da calibrare: è una coordinata che la ricerca
    ottimizza a vuoto, e va detto nel report invece di lasciar credere che il valore
    "vincente" su quell'asse significhi qualcosa."""
    assi = {"boost_alpha": 0, "default_weight": 1, "unclassified_weight": 2,
            "section_restatement_weight": 3}
    morti = []
    for nome, i in assi.items():
        gruppi: dict[tuple, set] = {}
        for punto, r in tabella.items():
            gruppi.setdefault(punto[:i] + punto[i + 1:], set()).add(round(r, 6))
        if all(len(valori) == 1 for valori in gruppi.values()):
            morti.append(nome)
    return morti


def kfold_cv(cases, cache, *, k, folds, seed, graph, restatements):
    """k-fold CV: per ogni fold held-out, sceglie i parametri sui restanti e li valuta sul fold.
    Restituisce (recall medio held-out coi parametri CALIBRATI, recall medio held-out coi
    DEFAULT, lista dei punti scelti fold per fold — "valore scelto in N fold su M" è la
    stabilità della scelta, che la sola dev.std fra seed non mostra)."""
    idx = list(range(len(cases)))
    random.Random(seed).shuffle(idx)
    buckets = [idx[i::folds] for i in range(folds)]
    cal_scores, def_scores, scelti = [], [], []
    for f in range(folds):
        val = [cases[i] for i in buckets[f]]
        train = [cases[i] for i in idx if i not in set(buckets[f])]
        if not val or not train:
            continue
        _, *punto = grid_best(train, cache, k=k, graph=graph, restatements=restatements)
        scelti.append(tuple(punto))
        cal_scores.append(mean_recall(val, cache, **_kw(punto), k=k, graph=graph,
                                      restatements=restatements))
        def_scores.append(mean_recall(val, cache, **_kw(ATTUALE), k=k, graph=graph,
                                      restatements=restatements))
    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0
    return avg(cal_scores), avg(def_scores), scelti


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibrazione dei pesi di autorità sul golden set")
    ap.add_argument("--k", type=int, default=10, help="soglia di recall da ottimizzare (default: 10)")
    ap.add_argument("--folds", type=int, default=5, help="numero di fold per la CV (default: 5)")
    ap.add_argument("--seed", type=int, nargs="+", default=[0, 1, 2, 3, 4],
                    help="seed (uno o più) dello shuffle dei fold. Con più seed il guadagno "
                         "riportato è la MEDIA sui seed, con la deviazione standard: un +0.018 "
                         "su un solo split può essere rumore di partizione, e questo script "
                         "cambia il ranking di produzione (default: 0 1 2 3 4)")
    ap.add_argument("--min-gain", type=float, default=0.015,
                    help="guadagno minimo di recall in validazione per proporre la calibrazione (default: 0.015)")
    a = ap.parse_args()

    print("Caricamento artefatti + modello + Qdrant (in-process)...")
    from FlagEmbedding import BGEM3FlagModel
    from qdrant_client import QdrantClient
    arts = load_artifacts(required=("graph", "colbert", "chunks"))
    # Peso di SEZIONE (N4): fa parte del ranking di PRODUZIONE, quindi deve far parte anche
    # di ciò che si calibra — l'insieme `restatements` dice QUALI sezioni lo ricevono, la
    # griglia (RESTATEMENT_WEIGHTS) QUANTO. Senza, la griglia ottimizzerebbe alpha contro un
    # ordinamento che nessuno serve — l'avvertimento è scritto nel docstring di make_retrieve_fn.
    restatements = retrieval.restatement_sections(arts.chunks_store)
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    embed_model = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False)

    cases = load_cases()
    print(f"Golden set: {len(cases)} casi. Recupero candidati (una volta per domanda)...")
    cache = retrieve_candidate_cache(cases, qdrant=qdrant, embed_model=embed_model,
                                     colbert_store=arts.colbert_store, graph=arts.graph,
                                     restatements=restatements)

    default_full = mean_recall(cases, cache, **_kw(ATTUALE), k=a.k, graph=arts.graph,
                               restatements=restatements)
    # Il COSTO, misurato sulla prima griglia e stampato PRIMA della CV: quattro assi
    # moltiplicano (9×6×5×8 = 2160 punti per griglia, e la CV ne rifà una per fold e per seed).
    n_punti = len(ALPHAS) * len(DEFAULT_WEIGHTS) * len(UNCLASSIFIED_WEIGHTS) * len(RESTATEMENT_WEIGHTS)
    t0 = time.perf_counter()
    tabella_full = griglia(cases, cache, k=a.k, graph=arts.graph, restatements=restatements)
    t_griglia = time.perf_counter() - t0
    n_griglie_cv = a.folds * len(a.seed)
    print(f"  griglia piena: {n_punti} punti in {t_griglia:.0f}s → CV ({n_griglie_cv} griglie "
          f"su {(a.folds - 1) / a.folds:.0%} dei casi) stimata in ~{t_griglia * n_griglie_cv * (a.folds - 1) / a.folds / 60:.0f} min")
    best_full = grid_best(cases, cache, k=a.k, graph=arts.graph, restatements=restatements,
                          tabella=tabella_full)
    morti = assi_morti(tabella_full)
    per_seed = [kfold_cv(cases, cache, k=a.k, folds=a.folds, seed=sd, graph=arts.graph,
                         restatements=restatements)
                for sd in a.seed]
    def _media(xs):
        return sum(xs) / len(xs)
    cal_cv, def_cv = _media([c for c, _, _ in per_seed]), _media([d for _, d, _ in per_seed])
    guadagni = [c - d for c, d, _ in per_seed]
    dev_std = (_media([(g - _media(guadagni)) ** 2 for g in guadagni])) ** 0.5
    # Stabilità della SCELTA: quante volte, sui fold di training, la griglia ha scelto ogni
    # punto. Un guadagno positivo con una scelta che salta da fold a fold è rumore che ha
    # trovato un segno, non una calibrazione.
    scelte = Counter(punto for _, _, scelti in per_seed for punto in scelti)
    n_fold_tot = sum(scelte.values())

    # Il sottoinsieme avversariale a parte (S5). È 10 casi su 59: nella media generale il
    # suo movimento è sotto la risoluzione del numero, e questo piano esiste per muoverlo.
    n_avv = sum(1 for c in cases if c.get("adversarial"))
    avv_default = mean_recall(cases, cache, **_kw(ATTUALE), k=a.k, graph=arts.graph,
                              restatements=restatements,
                              subset="adversarial") if n_avv else None
    avv_best = mean_recall(cases, cache, **_kw(best_full[1:]), k=a.k, graph=arts.graph,
                           restatements=restatements,
                           subset="adversarial") if n_avv else None
    # Autorità del tutto SPENTA: il controfattuale che dice se il meccanismo serve o no.
    avv_spenta = mean_recall(cases, cache, **_kw((0.0, *ATTUALE[1:])), k=a.k,
                             graph=arts.graph, restatements=restatements,
                             subset="adversarial") if n_avv else None

    def _fmt(punto) -> str:
        a_, dw, uw, rw = punto
        return (f"alpha={a_}  default_weight={dw}  unclassified_weight={uw}  "
                f"section_restatement_weight={rw}")

    print("\n" + "=" * 68)
    print(f"Calibrazione autorità — recall@{a.k}  (golden set: {len(cases)} casi)")
    print("=" * 68)
    print(f"  DEFAULT attuale   {_fmt(ATTUALE)}   → recall in-sample {default_full:.3f}")
    print(f"  MIGLIORE griglia  {_fmt(best_full[1:])}   → recall in-sample {best_full[0]:.3f}"
          "  (ottimista, non fidarsi)")
    print(f"\n  CROSS-VALIDATION ({a.folds}-fold, seed={a.seed}) — l'unico numero onesto:")
    print(f"    default   : recall@{a.k} held-out medio = {def_cv:.3f}")
    print(f"    calibrato : recall@{a.k} held-out medio = {cal_cv:.3f}")
    gain = cal_cv - def_cv
    print(f"    guadagno di validazione = {gain:+.3f}   (dev.std sui {len(a.seed)} seed: "
          f"{dev_std:.3f} — per seed: {', '.join(f'{g:+.3f}' for g in guadagni)})")
    print(f"    punti scelti sui {n_fold_tot} fold di training:")
    for punto, n in scelte.most_common(5):
        print(f"      {n:2d}× {_fmt(punto)}")
    if morti:
        print()
        print(f"  ⚠️  ASSI MORTI su questo corpus: {', '.join(morti)}.")
        print("      Non cambiano la recall di un millesimo: il valore 'vincente' su quegli assi")
        print("      non significa nulla, e la griglia sta cercando in uno spazio più piccolo di")
        print("      quanto sembri. Un asse morto va capito (quali documenti dovrebbe governare?),")
        print("      non calibrato.")
    if n_avv:
        print()
        print(f"  SOTTOINSIEME AVVERSARIALE ({n_avv} casi) — recall@{a.k} in-sample:")
        print(f"    autorità SPENTA (alpha=0.0)  = {avv_spenta:.3f}")
        print(f"    default attuale              = {avv_default:.3f}")
        print(f"    migliore di griglia          = {avv_best:.3f}")
        if avv_best <= avv_spenta:
            print("    ⚠️  Nessuna combinazione della griglia batte l'autorità SPENTA su questi")
            print("        casi: sul nostro corpus il meccanismo non li corregge.")

    nomi = ("alpha", "default_weight", "unclassified_weight", "section_restatement_weight")
    proposal = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "metric": f"recall@{a.k}",
        "cv": {"folds": a.folds, "seeds": a.seed,
               "default_recall": round(def_cv, 4), "calibrated_recall": round(cal_cv, 4),
               "gain": round(gain, 4), "gain_std": round(dev_std, 4),
               "gain_per_seed": [round(g, 4) for g in guadagni],
               "chosen_per_fold": [{**dict(zip(nomi, punto)), "n_folds": n}
                                   for punto, n in scelte.most_common()]},
        "grid_seconds": round(t_griglia, 1),
        "dead_axes": morti,
        "in_sample_best": {**dict(zip(nomi, best_full[1:])), "recall": round(best_full[0], 4)},
        "default": {**dict(zip(nomi, ATTUALE)), "recall": round(default_full, 4)},
    }
    if n_avv:
        proposal["adversarial_subset"] = {
            "n": n_avv,
            "recall_authority_off": round(avv_spenta, 4),
            "recall_default": round(avv_default, 4),
            "recall_grid_best": round(avv_best, 4),
        }
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / "authority_calibrated.yaml"
    if gain >= a.min_gain:
        proposal["recommendation"] = "APPLICA"
        proposal["proposed_authority_yaml"] = {
            "boost_alpha": best_full[1], "default_weight": best_full[2],
            "section_restatement_weight": best_full[4]}
        print(f"\n  ✅ Guadagno ≥ soglia ({a.min_gain}): calibrazione PROPOSTA.")
        print(f"     Applica a mano in rag_config.yaml → authority: {_fmt(best_full[1:])}")
    else:
        proposal["recommendation"] = "NON_APPLICARE"
        print(f"\n  ⚠️  Guadagno < soglia ({a.min_gain}): i pesi a mano REGGONO. Nessuna modifica consigliata.")
        print("     (È un risultato valido: il ranking semantico è già forte; non forzare l'autorità.)")
    out.write_text(yaml.safe_dump(proposal, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"\n  💾 Report scritto in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

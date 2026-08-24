"""Metriche di qualità del retrieval sul golden-set — logica PURA e riusabile.

Non conosce HTTP, Qdrant o il modello: riceve i casi (domanda + sorgenti attese) e una
funzione `retrieve_fn(query, k) -> list[dict]` che restituisce i risultati ordinati per
rilevanza (ogni risultato ha almeno `chunk_id`, `doc_id`, `section`). Così le stesse
metriche valgono sia contro il server reale (eval.run) sia contro un retriever fittizio
(test del meccanismo), senza reimplementare nulla.

Metriche calcolate (media sui casi):
  - recall@k             : frazione delle sorgenti attese trovate entro i primi k risultati.
  - source_in_top3       : 1 se ALMENO una sorgente attesa compare nei primi 3, altrimenti 0.
  - mrr                  : reciprocal rank della PRIMA sorgente attesa trovata (0 se assente).

Due letture in più, introdotte da S5 (ADR 0002) perché senza di esse il numero medio
mente in due modi opposti:

  - SATURAZIONE. Una recall che vale 1.000 su TUTTI i casi non è un buon risultato: è
    una misura che ha smesso di discriminare. La calibrazione del 2026-07-22 ha girato a
    k=10 e k=5 su una griglia interamente satura e ha concluso "nessuna combinazione è
    distinguibile" — cioè non ha misurato niente. `evaluate` elenca in `saturated` le
    metriche in quello stato: chi legge il report, e chi decide una promozione, deve
    vederlo come un difetto della misura, non come un 100%.
  - SOTTOINSIEME AVVERSARIALE. I casi marcati `adversarial: true` nel golden set sono
    quelli costruiti per mettere l'autorità alla prova (fonte informale lessicalmente
    più vicina della normativa che risponde). Sono pochi rispetto ai casi facili: nella
    media generale il loro contributo è invisibile. `evaluate` li aggrega anche a parte.

Una sorgente attesa è descritta da un "matcher": chunk-id, file sorgente, doc padre o
sezione (tutti confronti per sottostringa, case-insensitive). Un caso può elencarne più
d'uno (recall li media). Vedi eval/golden_set.yaml per il formato.
"""
from collections.abc import Callable, Sequence

# k di default per le metriche di recall e per il "sorgente in top-N". k=1 e k=2 ci sono
# perché sono gli unici dove questo corpus discrimina ancora: vedi SATURAZIONE sopra.
DEFAULT_KS: tuple[int, ...] = (1, 2, 5, 10)
TOP3_K = 3
# Una recall è "satura" se vale 1.0 su ogni caso. Il margine assorbe l'errore di
# rappresentazione delle divisioni in recall_at(), non è una tolleranza di giudizio.
SATURATION_EPS = 1e-9


def normalize_expected(case: dict) -> list[dict]:
    """Porta le sorgenti attese di un caso a una lista di matcher (dict con chiavi
    opzionali: any/chunk/file/doc/section). Accetta il formato nuovo (`expected`: lista
    di stringhe o dict) e quello legacy (`expected_doc` + `expected_section`)."""
    matchers: list[dict] = []
    for item in case.get("expected") or []:
        if isinstance(item, str):
            matchers.append({"any": item})
        elif isinstance(item, dict):
            matchers.append(item)
    if case.get("expected_doc"):  # retrocompatibilità col golden-set storico
        matchers.append({"doc": case["expected_doc"], "section": case.get("expected_section")})
    return matchers


def _sub(needle, haystack: str) -> bool:
    return bool(needle) and str(needle).lower() in haystack


def result_matches(result: dict, matcher: dict) -> bool:
    """True se un risultato del retrieval soddisfa un matcher. Ogni chiave presente nel
    matcher è un vincolo AND per sottostringa (case-insensitive):
      any  -> chunk_id OPPURE doc_id     chunk -> chunk_id
      file -> chunk_id OPPURE doc_id      doc  -> doc_id       section -> section
    """
    cid = str(result.get("chunk_id") or "").lower()
    did = str(result.get("doc_id") or "").lower()
    sec = str(result.get("section") or "").lower()
    if matcher.get("any") and not (_sub(matcher["any"], cid) or _sub(matcher["any"], did)):
        return False
    if matcher.get("chunk") and not _sub(matcher["chunk"], cid):
        return False
    if matcher.get("file") and not (_sub(matcher["file"], cid) or _sub(matcher["file"], did)):
        return False
    if matcher.get("doc") and not _sub(matcher["doc"], did):
        return False
    if matcher.get("section") and not _sub(matcher["section"], sec):
        return False
    # Un matcher vuoto non deve mai contare come hit universale.
    return any(matcher.get(key) for key in ("any", "chunk", "file", "doc", "section"))


def _first_rank(results: Sequence[dict], matcher: dict) -> int | None:
    """Rango 1-based del primo risultato che soddisfa il matcher, o None se assente."""
    for i, res in enumerate(results):
        if result_matches(res, matcher):
            return i + 1
    return None


def evaluate_case(results: Sequence[dict], matchers: list[dict],
                  ks: Sequence[int] = DEFAULT_KS, top3_k: int = TOP3_K) -> dict:
    """Metriche per un singolo caso, dati i risultati ordinati e le sorgenti attese."""
    ranks = [_first_rank(results, m) for m in matchers]
    found = [r for r in ranks if r is not None]

    def recall_at(k: int) -> float:
        if not ranks:
            return 0.0
        return sum(1 for r in ranks if r is not None and r <= k) / len(ranks)

    best = min(found) if found else None
    metrics: dict = {f"recall@{k}": recall_at(k) for k in ks}
    metrics["source_in_top3"] = 1.0 if any(r <= top3_k for r in found) else 0.0
    metrics["mrr"] = (1.0 / best) if best else 0.0
    metrics["best_rank"] = best
    metrics["n_expected"] = len(matchers)
    return metrics


def _mean(per_case: Sequence[dict], metric_keys: Sequence[str]) -> dict:
    n = len(per_case) or 1
    return {key: sum(pc["metrics"][key] for pc in per_case) / n for key in metric_keys}


def saturated_metrics(per_case: Sequence[dict], metric_keys: Sequence[str]) -> list[str]:
    """Metriche di recall che valgono 1.0 su OGNI caso: hanno smesso di discriminare.
    Lista vuota se non ci sono casi — su zero casi non si satura, si tace."""
    return [key for key in metric_keys
            if key.startswith("recall@") and per_case
            and all(pc["metrics"][key] >= 1.0 - SATURATION_EPS for pc in per_case)]


def evaluate(cases: Sequence[dict], retrieve_fn: Callable[[str, int], list[dict]],
             ks: Sequence[int] = DEFAULT_KS, top3_k: int = TOP3_K) -> dict:
    """Esegue il golden-set contro `retrieve_fn` e aggrega le metriche.

    retrieve_fn(query, k) deve restituire i risultati ordinati per rilevanza (lista di
    dict con chunk_id/doc_id/section). Viene chiamata con k = max(ks) così una sola
    richiesta copre tutte le soglie di recall.

    Ritorna {n, ks, top3_k, aggregate, saturated, adversarial, cases}. `saturated` è
    la lista delle recall che valgono 1.0 su ogni caso; `adversarial` è None se il
    golden set non marca alcun caso, altrimenti {n, aggregate, saturated} del solo
    sottoinsieme.
    """
    ks = tuple(ks)
    fetch_k = max(list(ks) + [top3_k])
    per_case: list[dict] = []

    for c in cases:
        query = c["q"]
        matchers = normalize_expected(c)
        results = list(retrieve_fn(query, fetch_k))
        m = evaluate_case(results, matchers, ks=ks, top3_k=top3_k)
        top = results[0] if results else {}
        per_case.append({
            "q": query,
            "adversarial": bool(c.get("adversarial")),
            "n_expected": m["n_expected"],
            "best_rank": m["best_rank"],
            "metrics": m,
            "top1": {"doc_id": top.get("doc_id", ""), "section": top.get("section", "")},
        })

    metric_keys = [f"recall@{k}" for k in ks] + ["source_in_top3", "mrr"]
    avversariali = [pc for pc in per_case if pc["adversarial"]]
    return {"n": len(per_case), "ks": list(ks), "top3_k": top3_k,
            "aggregate": _mean(per_case, metric_keys),
            "saturated": saturated_metrics(per_case, metric_keys),
            "adversarial": ({"n": len(avversariali),
                             "aggregate": _mean(avversariali, metric_keys),
                             "saturated": saturated_metrics(avversariali, metric_keys)}
                            if avversariali else None),
            "cases": per_case}

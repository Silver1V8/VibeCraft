"""Metriche di qualità del retrieval sul golden-set — logica PURA e riusabile.

Non conosce HTTP, Qdrant o il modello: riceve i casi (domanda + sorgenti attese) e una
funzione `retrieve_fn(query, k) -> list[dict]` che restituisce i risultati ordinati per
rilevanza (ogni risultato ha almeno `chunk_id`, `doc_id`, `section`). Così le stesse
metriche valgono sia contro il server reale (eval.run) sia contro un retriever fittizio
(test del meccanismo), senza reimplementare nulla.

Metriche calcolate (media sui casi):
  - recall@5 / recall@10 : frazione delle sorgenti attese trovate entro i primi k risultati.
  - source_in_top3       : 1 se ALMENO una sorgente attesa compare nei primi 3, altrimenti 0.
  - mrr                  : reciprocal rank della PRIMA sorgente attesa trovata (0 se assente).

Una sorgente attesa è descritta da un "matcher": chunk-id, file sorgente, doc padre o
sezione (tutti confronti per sottostringa, case-insensitive). Un caso può elencarne più
d'uno (recall li media). Vedi eval/golden_set.yaml per il formato.
"""
from collections.abc import Callable, Sequence

# k di default per le metriche di recall e per il "sorgente in top-N".
DEFAULT_KS: tuple[int, ...] = (5, 10)
TOP3_K = 3


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


def evaluate(cases: Sequence[dict], retrieve_fn: Callable[[str, int], list[dict]],
             ks: Sequence[int] = DEFAULT_KS, top3_k: int = TOP3_K) -> dict:
    """Esegue il golden-set contro `retrieve_fn` e aggrega le metriche.

    retrieve_fn(query, k) deve restituire i risultati ordinati per rilevanza (lista di
    dict con chunk_id/doc_id/section). Viene chiamata con k = max(ks) così una sola
    richiesta copre tutte le soglie di recall.

    Ritorna {n, ks, top3_k, aggregate: {...}, cases: [per-caso...]}.
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
            "n_expected": m["n_expected"],
            "best_rank": m["best_rank"],
            "metrics": m,
            "top1": {"doc_id": top.get("doc_id", ""), "section": top.get("section", "")},
        })

    n = len(per_case) or 1
    metric_keys = [f"recall@{k}" for k in ks] + ["source_in_top3", "mrr"]
    aggregate = {
        key: sum(pc["metrics"][key] for pc in per_case) / n
        for key in metric_keys
    }
    return {"n": len(per_case), "ks": list(ks), "top3_k": top3_k,
            "aggregate": aggregate, "cases": per_case}

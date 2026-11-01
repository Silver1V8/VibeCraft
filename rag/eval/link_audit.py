"""Campione, schede e metriche degli archi IMPLEMENTS già presenti nell'indice.

Non misura la recall: la popolazione è solo gli archi esistenti. Non cambia la
soglia di linking, il ranking o l'affidabilità. Senza un'etichetta umana su
ogni scheda estratta il risultato è «precisione non ancora misurata».

Etichette, una sola per scheda e per annotatore:
  IMPLEMENTA      il codice realizza il comportamento specifico richiesto
  CORRELATO       pertinenza tematica, senza evidenza di implementazione
  ERRATO          collegamento non pertinente
  NON_VALUTABILE  contesto insufficiente o requisito ambiguo

La precisione stretta ha al denominatore solo IMPLEMENTA, CORRELATO ed ERRATO.
I NON_VALUTABILE non entrano in quel denominatore: la loro quota è a parte.

Metodologia 2 (2026-11-01): la stima di popolazione è uno stimatore di rapporto
combinato, Σ w_h·I_h / Σ w_h·A_h con w_h = N_h/n_h, sotto campionamento casuale
semplice senza reinserimento in ogni strato. L'intervallo è conservativo: limiti
ipergeometrici esatti per strato, simultanei con Bonferroni. Il protocollo è in
eval/LINK_AUDIT.md.
"""
from __future__ import annotations

import hashlib
import random
from collections import Counter, defaultdict
from fractions import Fraction
from math import comb
from typing import Any, Mapping

LABELS = ("IMPLEMENTA", "CORRELATO", "ERRATO", "NON_VALUTABILE")
STRICT_LABELS = ("IMPLEMENTA", "CORRELATO", "ERRATO")
NOT_MEASURED = "precisione non ancora misurata"
MEASURED = "misurato"
# Versione 1 (fino al 2026-11-01): media delle precisioni locali pesata con N_h sugli
# strati con schede valutabili, più un Wald. Distorceva la stima quando la quota di
# NON_VALUTABILE cambiava tra strati; i suoi campi aggregate_* non esistono più.
METHODOLOGY_VERSION = 2
NOMINAL_LEVEL = Fraction(95, 100)

# Fasce di campionamento sul peso già registrato sull'arco (coseno di linking).
# Non sono soglie nuove: gli archi sotto 0.45, se esistono, restano nel campione.
_BANDS = (
    ("sotto_0.60", 0.60),
    ("0.60_0.75", 0.75),
    ("0.75_0.90", 0.90),
    ("da_0.90", None),
)
_HIDDEN = ("weight", "reliability", "best_score", "second_score", "margin")
# Lo strato contiene la fascia del peso: sta nel sigillo, non nella scheda di chi giudica.
_CARD_HIDDEN = _HIDDEN + ("stratum",)
_TEXT_LIMIT = 500


def edge_id(symbol_id: str, target_id: str) -> str:
    raw = (symbol_id + "\0" + target_id).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _band(weight: float | None) -> str:
    if weight is None:
        return "peso_assente"
    for name, upper in _BANDS:
        if upper is None or weight < upper:
            return name
    return "da_0.90"


def _clip(text: str | None) -> str:
    if not text:
        return ""
    text = str(text)
    if len(text) <= _TEXT_LIMIT:
        return text
    return text[:_TEXT_LIMIT] + "…"


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def collect_implements(
    graph,
    code_store: Mapping[str, Mapping] | None = None,
    chunks_store: Mapping[str, Mapping] | None = None,
) -> list[dict]:
    """Archi IMPLEMENTS con il contesto già nell'indice. Nessun arco inventato."""
    code_store = code_store or {}
    chunks_store = chunks_store or {}
    rows = []
    for src, dst, data in graph.edges(data=True):
        if data.get("relation") != "IMPLEMENTS":
            continue
        symbol = code_store.get(src) or {}
        node = graph.nodes[src] if src in graph else {}
        chunk = chunks_store.get(dst) or {}
        weight = _num(data.get("weight")) if "weight" in data else None
        best = _num(symbol.get("best_score"))
        second = _num(symbol.get("second_score"))
        same_target = symbol.get("win_chunk_id") == dst or symbol.get("win_doc_id") == dst
        if not same_target:
            best = second = None
        margin = None if best is None or second is None else round(best - second, 4)
        kind = str(symbol.get("kind") or node.get("kind") or "")
        rows.append({
            "edge_id": edge_id(str(src), str(dst)),
            "symbol_id": str(src),
            "target_id": str(dst),
            "kind": kind or "kind_assente",
            "dev_type": str(symbol.get("dev_type") or node.get("dev_type") or ""),
            "file": str(symbol.get("file") or node.get("file") or ""),
            "symbol_text": _clip(symbol.get("text") or node.get("text")),
            "target_doc_id": str(chunk.get("doc_id") or ""),
            "target_section": str(chunk.get("section") or ""),
            "target_text": _clip(chunk.get("text")),
            "nature": data.get("nature") if data.get("nature") in ("structural", "curated", "inferred") else None,
            "weight": weight,
            "reliability": _num(data.get("reliability")) if "reliability" in data else None,
            "best_score": best,
            "second_score": second,
            "margin": margin,
            "stratum": f"{_band(weight)}|{kind or 'kind_assente'}",
        })
    rows.sort(key=lambda r: r["edge_id"])
    return rows


def _allocate(sizes: dict[str, int], n: int) -> tuple[dict[str, int], bool]:
    """Riparto per resto maggiore con un minimo per strato: min(2, N_h) se n basta, così
    ogni strato non censito ha una varianza stimabile; altrimenti una scheda; altrimenti
    nessun minimo. Con un minimo il campione è sproporzionato e le probabilità vanno tenute."""
    names = [k for k, v in sizes.items() if v > 0]
    total = sum(sizes[k] for k in names)
    if n >= total:
        return {k: sizes[k] for k in names}, False
    if sum(min(2, sizes[k]) for k in names) <= n:
        floor = {k: min(2, sizes[k]) for k in names}
    elif len(names) <= n:
        floor = {k: 1 for k in names}
    else:
        floor = {k: 0 for k in names}
    raw = {k: n * sizes[k] / total for k in names}
    quota = {k: max(floor[k], min(sizes[k], int(raw[k]))) for k in names}
    left = n - sum(quota.values())
    order = sorted(names, key=lambda k: (raw[k] - int(raw[k]), sizes[k], k), reverse=True)
    while left > 0:
        moved = False
        for k in order:
            if quota[k] < sizes[k]:
                quota[k] += 1
                left -= 1
                moved = True
                if left == 0:
                    break
        if not moved:
            break
    while left < 0:
        # Cede chi ha più schede sopra il proprio minimo, non chi ne ha di più in assoluto.
        donors = [k for k in names if quota[k] > floor[k]]
        if not donors:
            break
        donor = max(donors, key=lambda k: (quota[k] - floor[k], k))
        quota[donor] -= 1
        left += 1
    disproportionate = any(quota[k] / sizes[k] != n / total for k in names)
    return quota, disproportionate


def draw_sample(rows: list[dict], *, n: int, seed: int) -> dict:
    """Campione stratificato, riproducibile. Registra N_h, n_h e π_h = n_h/N_h."""
    if n < 1:
        raise ValueError("n deve essere almeno 1")
    by = defaultdict(list)
    for row in rows:
        by[row["stratum"]].append(row)
    sizes = {k: len(v) for k, v in by.items()}
    quota, disproportionate = _allocate(sizes, n) if sizes else ({}, False)
    picked = []
    strata = []
    for name in sorted(by):
        group = sorted(by[name], key=lambda r: r["edge_id"])
        take = quota.get(name, 0)
        rng = random.Random(f"{seed}:{name}")
        chosen = group if take >= len(group) else rng.sample(group, take)
        chosen.sort(key=lambda r: r["edge_id"])
        picked.extend(chosen)
        strata.append({
            "stratum": name,
            "N_h": len(group),
            "n_h": len(chosen),
            "pi_h": round(len(chosen) / len(group), 6),
        })
    picked.sort(key=lambda r: r["edge_id"])
    return {
        "status": NOT_MEASURED,
        "population": len(rows),
        "sample_size": len(picked),
        "seed": seed,
        "disproportionate": disproportionate,
        "strata": strata,
        "edges": picked,
    }


def annotator_cards(sample: dict) -> list[dict]:
    """Schede senza peso, affidabilità, punteggi, margine e strato (che ha la fascia del peso)."""
    cards = []
    for row in sample["edges"]:
        cards.append({k: v for k, v in row.items() if k not in _CARD_HIDDEN})
        cards[-1]["label"] = ""
        cards[-1]["motivation"] = ""
        cards[-1]["annotator"] = ""
    return cards


def validate_annotations(sample: dict, annotations: list[dict]) -> dict:
    """Controlla le schede. Non sceglie un'etichetta al posto dell'annotatore."""
    known = {row["edge_id"] for row in sample["edges"]}
    errors = []
    kept = []
    seen = set()
    for i, ann in enumerate(annotations):
        eid = str(ann.get("edge_id") or "")
        label = ann.get("label")
        motivation = str(ann.get("motivation") or "").strip()
        annotator = str(ann.get("annotator") or "").strip()
        if eid not in known:
            errors.append({"index": i, "error": "scheda fuori dal campione"})
            continue
        if any(k in ann for k in _HIDDEN):
            errors.append({"index": i, "edge_id": eid, "error": "punteggi presenti nel giudizio"})
            continue
        if label not in LABELS:
            errors.append({"index": i, "edge_id": eid, "error": "etichetta non ammessa"})
            continue
        if len(motivation) < 20:
            errors.append({"index": i, "edge_id": eid, "error": "motivazione assente o troppo corta"})
            continue
        if not annotator:
            errors.append({"index": i, "edge_id": eid, "error": "annotatore assente"})
            continue
        key = (eid, annotator)
        if key in seen:
            errors.append({"index": i, "edge_id": eid, "error": "annotazione duplicata"})
            continue
        seen.add(key)
        kept.append({"edge_id": eid, "label": label, "motivation": motivation, "annotator": annotator})
    by_edge = defaultdict(list)
    for ann in kept:
        by_edge[ann["edge_id"]].append(ann)
    disagreements = []
    resolved = {}
    for eid, anns in sorted(by_edge.items()):
        labels = {a["label"] for a in anns}
        if len(labels) == 1:
            resolved[eid] = anns[0]["label"]
        else:
            disagreements.append({"edge_id": eid, "labels": sorted(labels)})
    missing = sorted(known - set(resolved) - {d["edge_id"] for d in disagreements})
    return {
        "accepted": kept,
        "errors": errors,
        "disagreements": disagreements,
        "missing": missing,
        "resolved": resolved,
        "complete": not errors and not disagreements and not missing,
    }


def _check_design(sample: dict) -> list[str]:
    """Coerenza fra N_h, n_h, π_h e schede del sigillo. Un sigillo incoerente non si pesa."""
    problems = []
    sizes: dict[str, int] = {}
    for info in sample.get("strata") or []:
        name, N_h, n_h = info.get("stratum"), info.get("N_h"), info.get("n_h")
        ints = all(isinstance(v, int) and not isinstance(v, bool) for v in (N_h, n_h))
        if not ints or N_h < 1 or not 0 <= n_h <= N_h:
            problems.append(f"strato {name!r}: N_h o n_h non validi")
            continue
        if name in sizes:
            problems.append(f"strato {name!r} ripetuto")
            continue
        sizes[name] = n_h
        pi_h = info.get("pi_h")
        # π_h è arrotondato a 6 cifre nel sigillo: si controlla, ma il peso usa N_h/n_h.
        if pi_h is not None and abs(pi_h - n_h / N_h) > 1e-6:
            problems.append(f"strato {name!r}: π_h non vale n_h/N_h")
    edges = sample.get("edges") or []
    if len({row.get("edge_id") for row in edges}) != len(edges):
        problems.append("archi ripetuti nel campione")
    drawn = Counter(row.get("stratum") for row in edges)
    for name, n_h in sizes.items():
        if drawn.get(name, 0) != n_h:
            problems.append(f"strato {name!r}: n_h={n_h} ma {drawn.get(name, 0)} archi estratti")
    for name in sorted(set(drawn) - set(sizes), key=str):
        problems.append(f"archi di uno strato senza N_h: {name!r}")
    if "population" in sample and sample["population"] != sum(
            info["N_h"] for info in sample["strata"] if info.get("stratum") in sizes):
        problems.append("population diversa dalla somma degli N_h")
    if not sizes:
        problems.append("nessuno strato nel sigillo")
    return problems


def _tail_count(N: int, n: int, K: int, x: int, upper: bool) -> int:
    """Numeratore intero di P(X ≥ x) (upper) o P(X ≤ x) per X ~ Ipergeometrica(N, K, n)."""
    lo, hi = max(0, n - (N - K)), min(n, K)
    js = range(max(lo, x), hi + 1) if upper else range(lo, min(hi, x) + 1)
    return sum(comb(K, j) * comb(N - K, n - j) for j in js)


def hypergeometric_bounds(N: int, n: int, x: int, alpha: Fraction) -> tuple[int, int]:
    """Limiti [K_L, K_U] sul conteggio K nella popolazione, avendo visto x su n senza reinserimento.

    Inversione di due test a una coda, ciascuno di livello alpha: K resta se
    P(X ≥ x | K) > alpha (limite inferiore) e se P(X ≤ x | K) > alpha (superiore).
    Copertura ≥ 1 - 2·alpha per ogni K vero. Aritmetica intera esatta: niente
    sottoflussi né arrotondamenti. Le code sono monotone in K, quindi bisezione.
    Con n == N resta il solo K = x: nessun errore di campionamento.
    """
    total = comb(N, n)

    def keeps(K: int, upper: bool) -> bool:
        return _tail_count(N, n, K, x, upper) * alpha.denominator > alpha.numerator * total

    a, b = x, N - (n - x)
    while a < b:  # primo K con P(X ≥ x | K) > alpha, che cresce con K
        m = (a + b) // 2
        if keeps(m, True):
            b = m
        else:
            a = m + 1
    low = a
    a, b = x, N - (n - x)
    while a < b:  # ultimo K con P(X ≤ x | K) > alpha, che cala con K
        m = (a + b + 1) // 2
        if keeps(m, False):
            a = m
        else:
            b = m - 1
    return low, a


def _ratio_interval(rows: list[tuple[int, int, int, int]]) -> dict:
    """Intervallo conservativo del rapporto Σ IMPLEMENTA / Σ valutabili nella popolazione.

    rows: (N_h, n_h, I_h, A_h). Ogni strato con n_h < N_h dà due intervalli (IMPLEMENTA e
    valutabili): sono 2H' in tutto, a ciascuno tocca un errore α/(2H'), cioè α/(4H') per coda.
    Se tutti coprono insieme (probabilità ≥ 1 - α per Bonferroni, qualunque sia la
    dipendenza fra i due conteggi) il rapporto vero sta fra i due estremi sotto. Gli
    strati censiti non hanno errore e non consumano α.
    """
    sampled = sum(1 for N_h, n_h, _, _ in rows if n_h < N_h)
    alpha = (1 - NOMINAL_LEVEL) / (4 * max(1, sampled))
    i_lo = i_hi = a_lo = a_hi = up_den = 0
    per = []
    for N_h, n_h, i_h, e_h in rows:
        il, iu = hypergeometric_bounds(N_h, n_h, i_h, alpha)
        al, au = hypergeometric_bounds(N_h, n_h, e_h, alpha)
        i_lo, i_hi, a_lo, a_hi = i_lo + il, i_hi + iu, a_lo + al, a_hi + au
        # Massimo del rapporto col vincolo IMPLEMENTA ≤ valutabili: I = I_U, A = max(A_L, I_U).
        # I_U ≤ A_U perché il limite superiore cresce con x e I_h ≤ A_h.
        up_den += max(al, iu)
        per.append(([il, iu], [al, au]))
    out = {
        "bounds": None,
        "reason": None,
        "nominal_level": float(NOMINAL_LEVEL),
        "conservative": True,
        "method": "inversione ipergeometrica per strato, Bonferroni su 2H intervalli, "
                  "rapporto dei limiti simultanei",
        "per_tail_alpha": float(alpha),
        "strata_with_sampling_error": sampled,
        "implements_total_bounds": [i_lo, i_hi],
        "evaluable_total_bounds": [a_lo, a_hi],
        "scope": "solo errore di campionamento: non copre disaccordo fra annotatori né altri corpus",
    }
    if a_hi == 0:
        out["reason"] = "i limiti simultanei ammettono zero archi valutabili nella popolazione"
    else:
        # Denominatore inferiore nullo: limite superiore prudente 1.
        high = Fraction(1) if up_den == 0 else min(Fraction(1), Fraction(i_hi, up_den))
        out["bounds"] = [float(Fraction(i_lo, a_hi)), float(high)]
    return {"interval": out, "per_stratum": per}


def compute_metrics(sample: dict, annotations: list[dict]) -> dict:
    """Precisione solo a campione completo e concorde. Altrimenti non misurata.

    Stimatore di rapporto combinato: consistente, non esattamente non distorto con
    campioni piccoli (è un rapporto di due stime). Calcolo in frazioni esatte; i float
    escono solo nel risultato.
    """
    check = validate_annotations(sample, annotations)
    base = {
        "status": NOT_MEASURED,
        "methodology_version": METHODOLOGY_VERSION,
        "estimand": "quota di archi IMPLEMENTS etichettati IMPLEMENTA fra gli archi valutabili "
                    "(IMPLEMENTA + CORRELATO + ERRATO) della popolazione sottoposta ad audit",
        "population_precision": None,
        "recall": None,
        "note": "La recall non si misura su questi archi: il campione non contiene i collegamenti assenti. "
                "La precisione non dimostra conformità normativa e non vale per altri corpus.",
        "annotation_completeness": {
            "sample_size": len(sample.get("edges") or []),
            "resolved": len(check["resolved"]),
            "missing": len(check["missing"]),
            "disagreements": len(check["disagreements"]),
            "errors": len(check["errors"]),
            "complete": check["complete"],
        },
        "validation": {
            "errors": check["errors"],
            "disagreements": check["disagreements"],
            "missing": check["missing"],
        },
    }
    problems = _check_design(sample)
    if problems:
        base["reason"] = "sigillo incoerente: N_h, n_h o schede non tornano"
        base["design_problems"] = problems
        return base
    strata = sample["strata"]
    population = sum(info["N_h"] for info in strata)
    base["sampling_coverage"] = {
        "design": "campione casuale semplice senza reinserimento in ogni strato",
        "strata": len(strata),
        "strata_sampled": sum(1 for info in strata if info["n_h"] > 0),
        "population": population,
        "population_in_sampled_strata": sum(info["N_h"] for info in strata if info["n_h"] > 0),
        "census": all(info["n_h"] == info["N_h"] for info in strata),
    }
    if any(info["n_h"] == 0 for info in strata):
        # Non si inventano valori per uno strato mai visto, e non si rinormalizza su quelli visti.
        base["reason"] = "almeno uno strato della popolazione non è nel campione: allarga n"
        return base
    if not check["complete"]:
        base["reason"] = "annotazioni mancanti, non valide o discordanti"
        return base
    stratum_of = {row["edge_id"]: row["stratum"] for row in sample["edges"]}
    local = {info["stratum"]: dict.fromkeys(LABELS, 0) for info in strata}
    for eid, label in check["resolved"].items():
        local[stratum_of[eid]][label] += 1
    implements = evaluable = non_evaluable = Fraction(0)
    rows = []
    for info in strata:
        c = local[info["stratum"]]
        e_h = sum(c[k] for k in STRICT_LABELS)
        w_h = Fraction(info["N_h"], info["n_h"])
        # Uno strato tutto NON_VALUTABILE dà zero ai due totali e resta nella popolazione.
        implements += w_h * c["IMPLEMENTA"]
        evaluable += w_h * e_h
        non_evaluable += w_h * c["NON_VALUTABILE"]
        rows.append((info["N_h"], info["n_h"], c["IMPLEMENTA"], e_h))
    ci = _ratio_interval(rows)
    counts = {label: sum(c[label] for c in local.values()) for label in LABELS}
    strict_n = sum(counts[k] for k in STRICT_LABELS)
    annotated = sum(counts.values())
    per_stratum = []
    for info, (N_h, n_h, i_h, e_h), (ib, eb) in zip(strata, rows, ci["per_stratum"], strict=True):
        per_stratum.append({
            **info,
            "w_h": float(Fraction(N_h, n_h)),
            "counts": local[info["stratum"]],
            "sample_precision": None if e_h == 0 else float(Fraction(i_h, e_h)),
            "implements_bounds": ib,
            "evaluable_bounds": eb,
        })
    report = {
        **base,
        "status": MEASURED if evaluable else NOT_MEASURED,
        "sample_precision": None if strict_n == 0 else float(Fraction(counts["IMPLEMENTA"], strict_n)),
        "sample_precision_scope": "grezza sul campione, non pesata: non stima la popolazione",
        "population_precision": None if evaluable == 0 else float(implements / evaluable),
        "population_precision_estimator": "rapporto combinato Σ w_h·I_h / Σ w_h·A_h, w_h = N_h/n_h",
        "estimated_implements_total": float(implements),
        "estimated_evaluable_total": float(evaluable),
        "precision_numerator": "IMPLEMENTA",
        "precision_denominator": "IMPLEMENTA + CORRELATO + ERRATO",
        "non_evaluable_excluded_from_precision": True,
        "sample_non_evaluable_share": None if annotated == 0 else float(Fraction(counts["NON_VALUTABILE"], annotated)),
        "weighted_non_evaluable_share": float(non_evaluable / population),
        "counts": counts,
        "interval": ci["interval"],
        "per_stratum": per_stratum,
    }
    if evaluable == 0:
        report["reason"] = ("nessun arco valutabile nel campione: precisione non definita, non zero. "
                            "Non prova che la popolazione sia tutta non valutabile.")
    elif report["sampling_coverage"]["census"]:
        report["interval"]["note"] = ("censimento: l'intervallo degenere riflette l'assenza di errore "
                                      "di campionamento, non la certezza delle etichette")
    return report

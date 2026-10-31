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
"""
from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from typing import Any, Mapping

LABELS = ("IMPLEMENTA", "CORRELATO", "ERRATO", "NON_VALUTABILE")
STRICT_LABELS = ("IMPLEMENTA", "CORRELATO", "ERRATO")
NOT_MEASURED = "precisione non ancora misurata"
MEASURED = "misurato"

# Fasce di campionamento sul peso già registrato sull'arco (coseno di linking).
# Non sono soglie nuove: gli archi sotto 0.45, se esistono, restano nel campione.
_BANDS = (
    ("sotto_0.60", 0.60),
    ("0.60_0.75", 0.75),
    ("0.75_0.90", 0.90),
    ("da_0.90", None),
)
_HIDDEN = ("weight", "reliability", "best_score", "second_score", "margin")
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
    """Riparto per resto maggiore. Se n basta, ogni strato non vuoto ha almeno una scheda:
    in quel caso il campione è sproporzionato e le probabilità vanno tenute."""
    names = [k for k, v in sizes.items() if v > 0]
    total = sum(sizes[k] for k in names)
    if n >= total:
        return {k: sizes[k] for k in names}, False
    floor_one = len(names) <= n
    raw = {k: n * sizes[k] / total for k in names}
    quota = {k: min(sizes[k], int(raw[k])) for k in names}
    if floor_one:
        for k in names:
            if quota[k] == 0:
                quota[k] = 1
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
        donor = max(names, key=lambda k: (quota[k], k))
        if quota[donor] <= (1 if floor_one else 0):
            break
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
    """Schede senza peso, affidabilità, punteggi e margine."""
    cards = []
    for row in sample["edges"]:
        cards.append({k: v for k, v in row.items() if k not in _HIDDEN})
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


def _wilson(successes: int, n: int) -> list[float] | None:
    if n < 2:
        return None
    z = 1.959963984540054
    p = successes / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return [round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)]


def compute_metrics(sample: dict, annotations: list[dict]) -> dict:
    """Precisione stretta solo a campione completo e concorde. Altrimenti non misurata."""
    check = validate_annotations(sample, annotations)
    base = {
        "status": NOT_MEASURED,
        "recall": None,
        "note": "La recall non si misura su questi archi: il campione non contiene i collegamenti assenti.",
        "validation": {
            "errors": check["errors"],
            "disagreements": check["disagreements"],
            "missing": check["missing"],
        },
    }
    if any(info["n_h"] == 0 for info in sample["strata"]):
        base["reason"] = "almeno uno strato della popolazione non è nel campione: allarga n"
        return base
    if not check["complete"]:
        return base
    rows = {r["edge_id"]: r for r in sample["edges"]}
    by_stratum = defaultdict(list)
    for eid, label in check["resolved"].items():
        by_stratum[rows[eid]["stratum"]].append(label)
    counts = {label: 0 for label in LABELS}
    for label in check["resolved"].values():
        counts[label] += 1
    strict_n = sum(counts[k] for k in STRICT_LABELS)
    annotated = sum(counts.values())
    per_stratum = []
    weights = []
    for info in sample["strata"]:
        labels = by_stratum.get(info["stratum"], [])
        local = {label: labels.count(label) for label in LABELS}
        strict = sum(local[k] for k in STRICT_LABELS)
        point = None if strict == 0 else round(local["IMPLEMENTA"] / strict, 4)
        per_stratum.append({
            **info,
            "counts": local,
            "strict_precision": point,
            "wilson95": None if point is None else _wilson(local["IMPLEMENTA"], strict),
            "non_evaluable_share": None if not labels else round(local["NON_VALUTABILE"] / len(labels), 4),
        })
        if strict:
            weights.append((info["N_h"], local["IMPLEMENTA"] / strict, strict, info["n_h"]))
    aggregate = None
    interval = None
    if weights and strict_n:
        population = sum(info["N_h"] for info in sample["strata"])
        aggregate = round(sum(N_h / population * p for N_h, p, _, _ in weights), 4)
        # Varianza del campionamento stratificato, con correzione per popolazione finita.
        # Gli strati con meno di 2 schede valutabili non hanno una varianza stimabile.
        var = 0.0
        estimable = True
        for N_h, p, strict, n_h in weights:
            if strict < 2:
                estimable = False
                break
            fpc = 1 - n_h / N_h if N_h else 0
            var += (N_h / population) ** 2 * fpc * p * (1 - p) / (strict - 1)
        if estimable:
            half = 1.959963984540054 * (var ** 0.5)
            interval = [round(max(0.0, aggregate - half), 4), round(min(1.0, aggregate + half), 4)]
    return {
        "status": MEASURED,
        "strict_precision": None if strict_n == 0 else round(counts["IMPLEMENTA"] / strict_n, 4),
        "strict_denominator": "IMPLEMENTA + CORRELATO + ERRATO",
        "strict_numerator": "IMPLEMENTA",
        "non_evaluable_excluded_from_strict": True,
        "non_evaluable_share": round(counts["NON_VALUTABILE"] / annotated, 4) if annotated else None,
        "counts": counts,
        "aggregate_precision": aggregate,
        "aggregate_interval95": interval,
        "aggregate_weight": "N_h/N sullo strato, solo strati con almeno una scheda valutabile",
        "per_stratum": per_stratum,
        "recall": None,
        "note": base["note"],
    }

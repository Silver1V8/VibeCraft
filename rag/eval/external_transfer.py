"""Trasferimento esterno: generalizzazione, non calibrazione interna.

Senza un corpus di terzi autorizzato lo stato è «bloccato». Un corpus generato
per questo sistema non è indipendente. Nessuna funzione di questo modulo
restituisce «validato».
"""
from __future__ import annotations

BLOCKED = "bloccato"
WAITING = "in attesa di annotazioni"
MEASURED = "misurato"
NOT_VALIDATED = "non validato"

_REQUIRED = ("provenienza", "versione", "licenza", "autorizzazione")


def assess_manifest(data) -> dict:
    reasons = []
    if not isinstance(data, dict):
        reasons.append("manifest assente o non è una mappa")
        data = {}
    if data.get("generated") is True or data.get("scritto_per_il_sistema") is True:
        reasons.append("un corpus generato o scritto per questo sistema non è indipendente")
    if data.get("costruito_per_favorire_il_sistema") is True:
        reasons.append("il corpus è costruito per favorire il sistema")
    if data.get("terza_parte") is not True:
        reasons.append("terza_parte non è true")
    for key in _REQUIRED:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            reasons.append(f"manca {key}")
    if data.get("originali_conservati") is not True:
        reasons.append("gli originali non risultano conservati")
    if data.get("metadati_aggiunti_separati") is not True:
        reasons.append("i metadati aggiunti non sono separati dagli originali")
    independent = not reasons
    return {
        "status": "pronto_non_validato" if independent else BLOCKED,
        "indipendente": independent,
        "validato": False,
        "misurato": False,
        "motivi": reasons,
    }


def duplicate_questions(texts: list[str]) -> list[dict]:
    """Duplicati esatti dopo normalizzazione degli spazi. Non giudica le parafrasi."""
    seen: dict[str, int] = {}
    found = []
    for index, text in enumerate(texts):
        key = " ".join(str(text).split()).casefold()
        if key in seen:
            found.append({"prima": seen[key], "dopo": index, "tipo": "duplicato_normalizzato"})
        else:
            seen[key] = index
    return found


def recall_at_k(cases: list[dict], k: int) -> float | None:
    """Recall@k binaria: media, sulle domande con almeno una fonte attesa, di 1 se
    una di quelle fonti è fra le prime k, altrimenti 0.

    Non è la recall insiemistica |attese ∩ primi k| / |attese|. Le domande senza
    fonti attese (casi di astensione) non entrano nel denominatore.
    """
    if k < 1:
        return None
    usable = [case for case in cases if case.get("relevant")]
    if not usable:
        return None
    hits = 0
    for case in usable:
        top = list(case.get("retrieved") or [])[:k]
        if any(item in top for item in case["relevant"]):
            hits += 1
    return hits / len(usable)


def mean_reciprocal_rank(cases: list[dict]) -> float | None:
    """MRR: media di 1/rank della prima fonte attesa. 0 se nessuna è recuperata.

    Denominatore: domande con almeno una fonte attesa. Il rank parte da 1.
    """
    usable = [case for case in cases if case.get("relevant")]
    if not usable:
        return None
    total = 0.0
    for case in usable:
        relevant = set(case["relevant"])
        rank = 0
        for index, item in enumerate(case.get("retrieved") or [], start=1):
            if item in relevant:
                rank = index
                break
        total += (1.0 / rank) if rank else 0.0
    return total / len(usable)


def abstention_outcomes(cases: list[dict]) -> dict | None:
    """Solo domande annotate come senza risposta. Non entra in Recall@k né in MRR."""
    silent = [case for case in cases if case.get("no_answer") is True]
    if not silent:
        return None
    correct = 0
    for case in silent:
        retrieved = list(case.get("retrieved") or [])
        answered = bool(retrieved) or bool(case.get("answered"))
        if not answered:
            correct += 1
    return {"n": len(silent), "corrette": correct, "quota": correct / len(silent)}


def evaluate_transfer(manifest, cases, *, human_verified: bool, split: str,
                      config_frozen: bool, used_for_tuning: bool, run_id: str | None) -> dict:
    """Misura il trasferimento della configurazione già fissata. Non ricalibra.

    `validato` resta False. `misurato` solo con corpus indipendente, giudizio
    umano, split di test, configurazione congelata, run tracciabile, e senza
    aver usato queste domande per scegliere i parametri.
    """
    assessment = assess_manifest(manifest)
    report = {
        "status": assessment["status"],
        "validato": False,
        "misurato": False,
        "indipendente": assessment["indipendente"],
        "motivi": list(assessment["motivi"]),
        "recall_at_k": None,
        "k": None,
        "mrr": None,
        "astensione": None,
        "duplicati": duplicate_questions([case.get("question", "") for case in cases or []]),
    }
    if report["duplicati"]:
        report["motivi"].append("domande duplicate: non sono un campione")
    if not assessment["indipendente"]:
        report["status"] = BLOCKED
        return report
    if not human_verified:
        report["status"] = WAITING
        report["motivi"].append("le risposte attese non sono state verificate da un umano")
        return report
    blocked = []
    if split != "test":
        blocked.append("lo split non è test")
    if not config_frozen:
        blocked.append("la configurazione non è congelata prima della misura")
    if used_for_tuning:
        blocked.append("queste domande sono state usate per scegliere i parametri")
    if not run_id:
        blocked.append("manca l'identificativo della run")
    if report["duplicati"]:
        blocked.append("duplicati nel test")
    if blocked:
        report["status"] = BLOCKED
        report["motivi"].extend(blocked)
        return report
    report["recall_at_k"] = {"5": recall_at_k(cases, 5), "10": recall_at_k(cases, 10)}
    report["k"] = [5, 10]
    report["mrr"] = mean_reciprocal_rank(cases)
    report["astensione"] = abstention_outcomes(cases)
    report["status"] = MEASURED
    report["misurato"] = True
    report["run_id"] = run_id
    report["validato"] = False
    return report

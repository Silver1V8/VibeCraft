"""Un solo passaggio correttivo locale dopo il retrieval iniziale (EXP-B).

Definizione operativa di «un passaggio» (2026-11-05):
- al più **una** azione;
- al più **un** chunk aggiuntivo in contesto;
- nessuna seconda `hybrid_search`, nessun rewrite LLM, nessun fallback web;
- autorità/precedenza restano quelle già applicate al ranking iniziale.

Azione supportata: `follow_ref` — se la domanda o il primo chunk recuperato citano
esplicitamente un identificativo normativo (`[REGOLA-…]`, `[SAFEGUARD-…]`, …) e quel
testo esiste nel corpus ma non è ancora in finestra, lo aggiunge.

Disattivato di default (`retrieval.corrective_pass.enabled: false`): prototipo per
esperimento appaiato, non path di produzione finché EXP-B non dà GO.
"""
from __future__ import annotations

import re
from typing import Any

# Identificativi tipici delle norme/regole nel corpus vibecraft (testi fra parentesi
# quadre). Non è un parser generico di markdown: serve solo a recuperare citazioni
# esplicite già presenti in domanda o nel top hit.
_REF_RE = re.compile(
    r"\[((?:REGOLA|SAFEGUARD|NORM|WF|OBS|VAL|SEC|NOTIF|API)-[A-Z0-9_-]+)\]",
    re.IGNORECASE,
)


def extract_refs(*texts: str) -> list[str]:
    """Riferimenti unici nell'ordine di prima apparizione (case conservato dal match)."""
    seen: set[str] = set()
    out: list[str] = []
    for text in texts:
        if not text:
            continue
        for m in _REF_RE.finditer(text):
            token = m.group(0)
            key = token.upper()
            if key in seen:
                continue
            seen.add(key)
            out.append(token)
    return out


def _chunk_mentions_ref(entry: dict, ref: str) -> bool:
    text = entry.get("text") or ""
    section = entry.get("section") or ""
    needle = ref.upper()
    inner = ref.strip("[]").upper()
    hay = f"{section}\n{text}".upper()
    return needle in hay or inner in hay


def find_follow_ref_chunk(
    *,
    question: str,
    search_results: list[dict],
    chunks_store: dict[str, dict],
    seen_chunks: set[str],
) -> dict[str, Any] | None:
    """Al più un chunk mancante che realizza un riferimento esplicito.

    Cerca prima i ref nella domanda, poi nel testo del primo risultato semantico
    (già in store). Restituisce metadati del chunk scelto o None.
    """
    top_text = ""
    top_cid = None
    if search_results:
        top_cid = search_results[0].get("chunk_id")
        entry = chunks_store.get(top_cid or "") if top_cid else None
        if entry:
            top_text = entry.get("text") or ""

    refs = extract_refs(question, top_text)
    if not refs:
        return None

    for ref in refs:
        for cid, entry in chunks_store.items():
            if cid in seen_chunks:
                continue
            if not _chunk_mentions_ref(entry, ref):
                continue
            head = ((entry.get("section") or "") + "\n" + (entry.get("text") or "")[:400]).upper()
            if ref.upper() not in head and ref.strip("[]").upper() not in head:
                continue
            return {
                "chunk_id": cid,
                "doc_id": entry.get("doc_id") or cid.split("#")[0],
                "section": entry.get("section") or "",
                "ref": ref,
                "action": "follow_ref",
                "source_top_chunk_id": top_cid,
            }
    return None


def apply_corrective_pass(
    *,
    enabled: bool,
    action: str,
    question: str,
    search_results: list[dict],
    chunks_store: dict[str, dict],
    seen_chunks: set[str],
    context_parts: list[str],
    ordine_contesto: list[str],
    fonti_nel_contesto: list[dict],
    source_label,
    cap_text,
) -> dict[str, Any]:
    """Esegue al più un passaggio. Mutazione in-place delle liste di contesto.

    `source_label` e `cap_text` sono iniettati dal chiamante per non importare
    cicli ask↔retrieval e per riusare la stessa etichetta di classe fonti.
    """
    trace: dict[str, Any] = {
        "enabled": bool(enabled),
        "action": action,
        "applied": False,
        "added_chunk_id": None,
        "ref": None,
        "reason": None,
    }
    if not enabled:
        trace["reason"] = "disabled"
        return trace
    if action != "follow_ref":
        trace["reason"] = f"azione non supportata: {action}"
        return trace
    if not chunks_store:
        trace["reason"] = "chunks_store vuoto"
        return trace

    hit = find_follow_ref_chunk(
        question=question,
        search_results=search_results,
        chunks_store=chunks_store,
        seen_chunks=seen_chunks,
    )
    if hit is None:
        trace["reason"] = "nessun riferimento recuperabile fuori finestra"
        return trace

    cid = hit["chunk_id"]
    entry = chunks_store[cid]
    pseudo = {
        "chunk_id": cid,
        "doc_id": hit["doc_id"],
        "section": hit["section"],
        "classification": entry.get("classification") or "",
        "status": entry.get("status") or "",
    }
    seen_chunks.add(cid)
    ordine_contesto.append(cid)
    fonti_nel_contesto.append(pseudo)
    context_parts.append(
        f"--- {hit['doc_id']} § {hit['section']} [{source_label(pseudo)}] "
        f"[via correttivo: {hit['action']} {hit['ref']}] ---\n"
        f"{cap_text(entry.get('text') or '')}"
    )
    trace.update({
        "applied": True,
        "added_chunk_id": cid,
        "ref": hit["ref"],
        "reason": "ok",
        "source_top_chunk_id": hit.get("source_top_chunk_id"),
    })
    return trace

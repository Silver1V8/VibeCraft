"""Gate di rispondibilità pre-LLM per /ask (G1, rag/adr/2026-11-03-gate-rispondibilita-plan.md).

Il MaxSim ColBERT ordina bene ma cambia scala da query a query, quindi non dice se il contesto
BASTA a rispondere: oggi lo decide solo il LLM con [REGOLA-ASTENSIONE], dopo una generazione
intera. Un cross-encoder dà invece un punteggio per coppia (domanda, sezione) confrontabile fra
domande diverse. Qui si calcola quel punteggio; il contesto non viene né riordinato né
filtrato, così la calibrazione congiunta S11 resta intatta. Saltare il LLM sotto soglia era il
passo successivo: la misura del 2026-11-03 ha dato NO-GO (Esito nel piano) e non è stato scritto.

Logica pura: il reranker arriva come parametro (lo carica api.index_runtime.ensure_reranker).
"""
import time


def assess(reranker, question: str, passages: list[str], *, mode: str, top_n: int,
           threshold: float | None) -> dict | None:
    """Rispondibilità = il miglior punteggio fra le sezioni che vede il LLM.

    Il massimo e non la media: basta UNA sezione che risponde, e le altre in finestra sono
    spesso contesto di contorno. `None` quando non c'è niente da giudicare, che è diverso da
    "non risponde": senza modello o senza sezioni il gate non ha un'opinione.
    """
    if mode == "off" or reranker is None or not passages:
        return None
    start = time.perf_counter()
    raw = reranker.compute_score([(question, p) for p in passages[:top_n]])
    # Con una sola coppia FlagReranker restituisce uno scalare, non una lista.
    scores = [round(float(s), 4) for s in (raw if isinstance(raw, list) else [raw])]
    score = max(scores)
    return {
        "mode": mode,
        "score": score,
        "scores": scores,
        "threshold": threshold,
        # Senza soglia calibrata il gate osserva soltanto: inventarne una è l'errore di D3.
        "would_abstain": None if threshold is None else score < threshold,
        "latency_ms": round((time.perf_counter() - start) * 1000, 2),
    }

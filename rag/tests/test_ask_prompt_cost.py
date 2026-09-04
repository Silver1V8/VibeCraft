"""Canarino sul costo FISSO del prompt di sistema di /ask (A1, R3).

Il costo fisso è cresciuto DUE VOLTE in una sola sessione — `[CLASSE-FONTI]` con A3,
`[REGOLA-ASTENSIONE]` con A16 — e nessuno se n'è accorto finché A1 non ha rimisurato dal
vivo: il margine dichiarato («k=20 → 81% di num_ctx») era diventato 104%, cioè oltre la
finestra, con la risposta che tornava comunque `status:"success"`. Il guardrail di
`core.llm._ollama_payload` protegge la SINGOLA richiesta a valle; qui si sorveglia la causa
a monte, che è il testo del prompt e cresce a commit, non a runtime.

Perché solo la parte FISSA: il prompt completo dipende dal corpus indicizzato (fino a
`governed_max_chunks` sezioni da 3.000 caratteri) e un budget su quello fallirebbe a ogni
reindex senza dire nulla su chi l'ha fatto crescere. La parte fissa — il system prompt e le
due regole condizionali, con le interpolazioni ridotte a valori sintetici minimi — dipende
SOLO dal sorgente: se questo test diventa rosso, qualcuno ha aggiunto una regola.

Il test non vieta di aggiungere regole: obbliga a **rimisurare** il margine a top_k massimo
prima di alzare il budget qui sotto, che è esattamente il passo che era stato saltato.
"""
from core import retrieval
from core.llm import OLLAMA_NUM_CTX

# Budget in token del prompt di sistema completo (base + [CLASSE-FONTI] +
# [PRECEDENZA-FONTI]), con la stessa stima conservativa ~3 caratteri/token usata dal
# guardrail di core.llm._ollama_payload — deve essere LA STESSA, o il canarino misurerebbe
# una scala diversa da quella che poi solleva LLMError.
#
# MISURA DEL 2026-09-04: 954 token (~5,8% di num_ctx=16384). Erano 804 prima di
# [CITAZIONE-VERIFICABILE] (R1), che ne ha aggiunti ~150 sostituendo una riga di 40 con una
# regola di divieto esplicita — il costo è dichiarato, non incidentale.
# RAGIONE DEL VALORE: 1000 lascia ~46 token di margine, meno di qualunque regola vera
# ([CLASSE-FONTI] ne pesa ~330, [REGOLA-ASTENSIONE] ~160). Aggiungere una regola rende
# questo test rosso, ed è lo scopo: chi la aggiunge deve rimisurare il prompt COMPLETO a
# top_k=20 sul corpus reale (è così che A1 scoprì il 104%) e riscrivere qui budget, data e
# ragione. Alzare il numero per far passare la suite, senza quella misura, è il difetto.
BUDGET_TOKEN_PROMPT_FISSO = 1000


def _token_stimati(testo: str) -> int:
    """Stessa stima del guardrail di core.llm._ollama_payload: ~3 caratteri/token."""
    return len(testo) // 3


def prompt_fisso() -> str:
    """Il prompt di sistema con TUTTE le regole attive e nulla che venga dal corpus:
    contesto e domanda vuoti, e le interpolazioni di [CLASSE-FONTI]/[PRECEDENZA-FONTI]
    ridotte a due valori sintetici minimi. Ciò che resta è testo di sorgente."""
    return retrieval.build_ask_prompt(
        "", "",
        precedences=[("a", "b")],
        authority_classes=[("NORMS", 0.8), ("METHODOLOGY", 0.5)],
    )


def test_costo_fisso_del_prompt_entro_il_budget():
    misurato = _token_stimati(prompt_fisso())
    assert misurato <= BUDGET_TOKEN_PROMPT_FISSO, (
        f"Il prompt di sistema di /ask è cresciuto a ~{misurato} token stimati, oltre il "
        f"budget di {BUDGET_TOKEN_PROMPT_FISSO} misurato il 2026-09-04. Non alzare il "
        f"budget senza rimisurare il prompt COMPLETO a top_k=20 sul corpus reale: è il "
        f"passo saltato che portò /ask al 104% di num_ctx={OLLAMA_NUM_CTX} (A1)."
    )


def test_il_budget_e_una_frazione_piccola_della_finestra():
    """Il budget deve restare costo di servizio, non di contesto: se il testo fisso arriva
    a un decimo della finestra, il problema non è più il singolo commit ma il prompt."""
    assert BUDGET_TOKEN_PROMPT_FISSO < OLLAMA_NUM_CTX * 0.10

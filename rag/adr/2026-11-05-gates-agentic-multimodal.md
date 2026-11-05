# Gate EXP-D (agentic) e EXP-E (multimodalità) — 2026-11-05

Non sostituisce ADR 0001: lo applica. Collegato da `docs/eval-e-ci.md`.
Istruzione utente: implementare il piano eval VibeCraft (gate condizionali).

## Contesto

Programma eval incrementale. Fasi A–C strumentate; D ed E solo con evidenze.
Checkout di ricognizione: `726ccbba` su `main`.

## EXP-D — Orchestrazione agentica su `/ask`

**Decisione: NO-GO (non implementare nel path normale).**

1. ADR `0001-multi-agent-scartato.md` vigente: nessun trigger di riapertura
   misurato in questa sessione.
2. MCP + `agent_bridge` esistono fuori da `/ask`; non sostituiscono un confronto
   controller-vs-deterministico su richieste composte fallite.
3. EXP-B è prototipo flag-off; EXP-C conferma il router deterministico — non c’è
   evidenza di richieste composte irrisolvibili da A–C.

**Riaprire solo se:** trigger ADR 0001, oppure fallimenti composti documentati
dopo B/C con vantaggio misurato di un singolo controller tool-limited.

Decisione legittima: **NON IMPLEMENTARE** multi-agent framework.

## EXP-E — Multimodalità

**Decisione: NO-GO.**

1. Nessun registro di errori visivi con pagina/regione.
2. Pipeline attuale: Docling OCR → testo; LLM text-only.
3. Ordine obbligato non percorso: extract → region → VLM.

**Riaprire solo se:** ≥5 casi indipendenti documentati (**DA APPROVARE**) non
risolvibili senza interpretazione visiva, local-first.

## Artefatti correlati

- `eval/failures/retrieval_misses_register.json`
- `eval/routing_cases.yaml`
- Link audit: campione etichettato da `$ilver` (conferma A); dual B solo bozza agente
- Chiusura EXP-B flag-off: `2026-11-05-exp-b-closure.md`

**Conferma 2026-11-05:** EXP-D e EXP-E restano **NO-GO**. Nessuna nuova evidenza
di riapertura in questa sessione.

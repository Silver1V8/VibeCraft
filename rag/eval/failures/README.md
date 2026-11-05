# Registro fallimenti retrieval (EXP-B / S-B-0)

Non sostituisce i golden set. Collegato da `docs/eval-e-ci.md`.
Istruzione utente: implementare il piano eval VibeCraft.

`retrieval_misses_register.json` deriva dalla run **storica**
`p0_20260908-152239` (aggregate recall@10 = 1.0). Non è una verifica corrente
del 2026-10-30.

Classificazione:

- `present_but_not_top1`: fonte attesa nel corpus ma non al rango 1
- `corrective_candidate`: `best_rank` ∈ [2, 10]

Azione proposta: **`follow_ref`**, flag
`retrieval.corrective_pass.enabled: false` finché EXP-B non dà GO.

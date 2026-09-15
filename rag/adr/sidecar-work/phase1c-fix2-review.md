# Re-review indipendente — unità 1c fix 2

Ambito esclusivo: chiusura delle tre regressioni riportate in `phase1bc-fix1-review.md`. Unità 1b non riaperta.

## Verdetto conformità: APPROVATO

## Verdetto qualità/correttezza: APPROVATO

### Identità PID e zombie — ADDRESSED

- `rag/scripts/bench_process.py:142-157` registra per ogni processo osservato PID e `create_time`.
- `rag/scripts/bench_process.py:179-192` attende soltanto la stessa identità di processo e considera concluso uno zombie; PID riusati non prolungano l'attesa.
- Il test a `rag/tests/test_bench_process.py:55-65` copre entrambe le condizioni.

### Lettura Qdrant finale — ADDRESSED

- `rag/scripts/bench_process.py:266-272` attende fino a 10 secondi il collector in volo e appende sempre un evento `qdrant_final`: campione completo oppure limite esplicito se il thread non conclude.
- Il collector può terminare dopo il timeout, ma in quel caso il dato già persistito dichiara correttamente che la lettura non è conclusa; non viene presentata una misura incompleta come valida.
- Il test a `rag/tests/test_bench_process.py:68-75` copre il workload che termina mentre la raccolta Qdrant è in volo.

### Checkpoint prima dell'attesa — ADDRESSED

- `rag/scripts/bench_process.py:195-198` scrive il report tramite file temporaneo e replace atomico.
- Su errore post-launch, `rag/scripts/bench_process.py:255-263` persiste prima `completion="waiting_for_natural_exit"` con `sampler_error`, poi attende senza kill e infine aggiorna il report a `completed`.
- Il test a `rag/tests/test_bench_process.py:78-88` osserva il checkpoint mentre il workload è ancora vivo.

## Nuove regressioni scoped

Nessuna rilevata.

## Evidenza

Non ho ripetuto suite o workload. `rag/eval/results/sidecar_20260915/evidence/windows-phase1c-fix2.txt` riporta `8 passed in 3.67s`, exit code 0, e ruff riuscito con exit code 0.

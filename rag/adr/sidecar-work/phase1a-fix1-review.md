# Re-review indipendente — fase 1a fix 1

Ambito esclusivo: `phase1a-fix1-review.diff`, report 1a aggiornato e finding della review originale. Esclusi 1b/1c.

## Verdetto conformità: APPROVATO

## Verdetto qualità/correttezza: APPROVATO

### Finding originale P1 — addressed

- `rag/api/reindex.py:280-284` rende gli errori journal non fatali per il worker.
- `rag/api/reindex.py:432-465` racchiude record, callback e rilascio/dispatch in un `try/finally`: anche se il journal fallisce, `_running_id` viene liberato e il pending parte.
- Il test `rag/tests/test_reindex.py:196` forza `OSError("disk full")` durante la transizione e verifica dispatch e coda libera.

### Finding originale P2 — addressed

- `rag/api/reindex.py:420-422` imposta `reload_status="pending"` prima di rendere terminale la build.
- `rag/api/reindex.py:443-446` pubblica token e durata ready prima di `reload_status="completed"`, che ora agisce da commit marker.
- `rag/api/reindex.py:114-118` impedisce inoltre di serializzare `completed` se uno dei campi readiness è assente. Il test a `rag/tests/test_reindex.py:229` copre il record incoerente.

### Aggiunte PM — addressed

- Pending prima del terminale build: coperto dall'ordine a `rag/api/reindex.py:420-422`.
- Timeout non-ready: `_poll_job` conserva l'ultimo campione con `_poll_timed_out`; incremental e full lo classificano `valid=false` con motivo `timeout: snapshot non pronto` (`rag/scripts/bench.py:201-202`, `:248-250`, `:278-292`).
- Full coalesced: entra esplicitamente nel calcolo di validità e nel motivo (`rag/scripts/bench.py:278-292`), con test a `rag/tests/test_bench.py:329`.

## Nuove regressioni nel fix

Nessuna rilevata nel diff scoped.

## Evidenza test

Non ho ripetuto la suite. `rag/eval/results/sidecar_20260915/evidence/windows-phase1a-fix1.txt` mostra avanzamento completo fino a `[100%]` per 93 casi, coerente con il report. Il file raw non contiene però riga riepilogativa `93 passed` né exit code; prova quindi completamento visivo, non da solo l'esito di processo dichiarato.

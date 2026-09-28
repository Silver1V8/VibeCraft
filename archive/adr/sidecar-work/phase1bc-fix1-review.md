# Re-review indipendente — unità 1b + 1c fix 1

Ambito esclusivo: `phase1bc-fix1-review.diff`, report 1b/1c aggiornati e quattro finding originali. La decisione PM “nessun kill automatico; driver reale responsabile dei figli” è trattata come requisito del fix.

## Verdetto conformità: RICHIEDE CORREZIONI (solo 1c)

## Verdetto qualità/correttezza: RICHIEDE CORREZIONI (solo 1c)

### Finding originale P1 — shutdown: PARTIALLY ADDRESSED

- Addressed: `rag/scripts/bench_process.py:154-170` elimina `terminate()/kill()` e usa un segnale graceful di gruppo solo su Ctrl-C; `Popen` crea correttamente un nuovo gruppo/sessione a `:210-212`. I PID figli osservati vengono conservati.
- Not addressed: `_wait_for_workload()` a `:173-176` conserva soli interi e considera vivo qualunque `pid_exists(pid)`. Un figlio zombie su Linux resta esistente finché non viene reaped; un PID terminato e riusato identifica un processo estraneo. In entrambi i casi il sampler può attendere senza limite dopo che il workload reale è finito.
- Correzione minima: conservare identità `psutil.Process` con `create_time`, considerare zombie terminato e ignorare PID riusati.

### Finding originale P1 — cadenza Qdrant: ADDRESSED, con nuova regressione

- Addressed: `rag/scripts/bench_process.py:112-124` usa una sola `docker exec`; `:194-206` la esegue su thread separato e avanza la deadline assoluta, quindi i tick workload/sistema non sono bloccati dalla lettura container.
- Nuova regressione [P2]: il thread è daemon e non viene atteso prima di uscire (`:205-206`, finalizzazione `:227-239`). Se il workload termina mentre `docker exec` è ancora attivo, il risultato arriva dopo l'ultima riga JSONL o persino dopo il report finale e viene perso. Un workload breve con `--qdrant-container` può quindi non contenere alcuna misura Qdrant pur avendola avviata.
- Correzione minima: attendere la lettura Qdrant in volo prima del report e scriverne il risultato finale nel JSONL (con timestamp/durata già disponibili).

### Finding originale P2 — semantica timing: ADDRESSED

- `rag/core/indexing.py:810-856` attribuisce collect/embed e costruzione sidecar codice a `parsing_embedding`, lasciando in `relink` link simboli e autorità.
- `rag/core/indexing.py:962-992` misura `eval_gate` separatamente da `promote` anche nel full diretto.
- Il collector resta opzionale e il return full resta la versione. I test deterministici in `rag/tests/test_index_timings.py:22-79` verificano valori esatti dei due contratti.

### Finding originale P2 — errore startup: ADDRESSED, con limite sul report parziale

- `rag/scripts/bench_process.py:208-231` include `Popen` e acquisizione psutil nel `try`; senza processo crea JSONL vuoto, poi scrive report con `sampler_error` ed exit code nullo. Il test a `rag/tests/test_bench_process.py` copre il comando inesistente.
- Nuova regressione [P2]: per un errore sampler dopo l'avvio, `finally` chiama prima `_wait_for_workload()` senza limite (`:227-229`) e il report viene scritto solo dopo (`:232-239`). Se il workload continua a lungo o resta bloccato, l'evidenza “parziale” non viene salvata mentre serve; il report 1c afferma invece che l'errore salva il report e poi attende.
- Correzione minima compatibile con nessun kill: scrivere subito un checkpoint/report parziale atomico con `sampler_error`, poi attendere e aggiornare il report alla conclusione naturale.

## Evidenza test

Non ho ripetuto le suite. I log raw attestano `90 passed`, exit code 0 per 1b e `5 passed in 4.21s` più ruff riuscito per 1c. Questi test non coprono zombie/PID reuse, finalizzazione Qdrant in volo o disponibilità del report durante l'attesa.

## Nuove regressioni scoped

Tre: attesa falsa/infinita su identità PID, perdita della lettura Qdrant in volo, report parziale differito fino alla fine del workload.

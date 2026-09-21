# Review indipendente — fase 1d

**Conformità: non approvata per il run. Qualità: discreta per un driver monouso, con tre correzioni necessarie prima dell'avvio.** Review statica del diff congelato; nessun modello, container, server o benchmark avviato. I contratti di `incremental_index`, `/api/reindex`, `/api/retrieve` e `manager.join_all` sono stati controllati soltanto per i rischi sotto. L'origine `_started_monotonic` è serializzata nel payload: gli eventi relativi sono quindi correlabili ai campioni assoluti.

## Findings

1. **[Bloccante, conformità/sicurezza del dato] Ripristino non byte per byte né verificato** — `rag/eval/results/sidecar_20260915/evidence/process_workload.py:276-281,321-325`. `read_text`/`write_text` possono normalizzare newline e il fingerprint finale è registrato senza confronto con quello iniziale. Anche con exit code 0 i sorgenti possono differire dai byte originali. Conservare i byte, modificare il testo soltanto dopo una decodifica valida, ripristinare con `write_bytes` e fallire se i fingerprint differiscono. Questo vale anche quando il job delta fallisce o va in timeout.

2. **[Bloccante, conformità] Self-check positivo non esercita la guardia del child bootstrap** — `process_workload.py:341-350`. Il subprocess del self-check esegue soltanto `python -c "import os; print(os.getpid())"`; non attraversa la validazione del child prevista da `--bootstrap`. Il report afferma di avere verificato quella guardia, ma la prova copre solo `Popen` e un PID generico. Serve un controllo sicuro della guardia positiva nel child e dei suoi metadati PID, senza importare core, caricare il modello o simulare un bootstrap completo.

3. **[Importante, evidenza del fallimento] Job non conservato se fallisce la verifica** — `process_workload.py:270-274,286-290`. `_require_completed` precede l'assegnazione a `payload["results"]`; in caso di stato `failed`, reload fallito, timeout o assert sui conteggi, il JSON finale perde il job intero richiesto dal brief. Registrare il risultato di `_wait_job` prima della verifica, anche per no-op e delta. I thread vengono comunque attesi nel `finally` tramite `manager.join_all`, che è il contratto corretto per non uscire con il writer daemon vivo.

## Contratti che risultano coerenti

Il bootstrap usa `incremental_index` sotto il writer lock; `POST /api/reindex` senza corpo avvia l'incrementale; `GET /api/reindex/{job_id}` espone stato, reload e token; `GET /api/retrieve` è retrieval puro. Il server in thread nello stesso processo e `join_all` seguito da shutdown cooperativo sono appropriati. Collection, Qdrant URL e porta sono fissati ai valori dedicati. Le verifiche già riportate sono solo sintassi e self-check, quindi non dimostrano prestazioni né correttezza del run reale.

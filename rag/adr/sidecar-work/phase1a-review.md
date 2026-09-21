# Review indipendente — fase 1a

Diff congelato: `phase1a-review.diff`, base `4f35acf` (sei file). Il report autore è stato trattato come affermazione da verificare. Non sono state recensite le modifiche concorrenti a `core/indexing.py`.

## Verdetto conformità al brief: NON CONFORME

L'impianto copre i requisiti principali: durate monotone additive, `finished_at` storico invariato, esito reload separato dalla build, token restituito dal reload reale, callback `None` classificata incompleta, dispatch del pending dopo il reload, lettura dei journal vecchi e invalidazione benchmark di falso noop/coalescing/reload incompleto. Restano però due violazioni osservabili dei contratti di coda e readiness sotto riportate.

## Verdetto qualità/correttezza: RICHIEDE CORREZIONI

### [P1] Un errore del journal può bloccare permanentemente la coda

- File: `rag/api/reindex.py:418`, `rag/api/reindex.py:438`, rilascio slot a `rag/api/reindex.py:443-450`.
- `_record(job)` ora viene eseguito prima di azzerare `_running_id`, fuori da un `finally`. Se append, mkdir, flush, stat, compattazione o `os.replace` sollevano (disco pieno, permessi, errore I/O), il thread termina senza liberare lo slot e senza dispatchare il pending. Da quel momento ogni `start()` vede per sempre un job in esecuzione e accoda/fonde richieste che non partiranno.
- Prima del diff lo slot veniva liberato nel `finally` antecedente al journal. Questo regredisce il requisito “coda/coalescing esistente preservato” e rende un errore accessorio di osservabilità capace di fermare il servizio di reindex.
- Correzione minima: garantire rilascio slot/dispatch in un `finally`; decidere separatamente come rendere osservabile l'errore journal senza far morire il worker.

### [P2] Il benchmark può fermarsi tra `reload_status` e `published_token`

- File: `rag/api/reindex.py:429-432`, osservazione in `rag/api/routes_reindex.py:210-213`, criterio in `rag/scripts/bench.py:198-200`.
- Il worker assegna prima `reload_status = "completed"`, poi `published_token` e `snapshot_ready_duration_seconds`. `manager.get()` restituisce l'oggetto mutabile e la route chiama `to_dict()` fuori dal lock. Un poll concorrente può quindi osservare `completed` con token ancora `None`; `_poll_job()` considera il reload terminato e il benchmark restituisce subito `valid=false`, anche se il reload ha pubblicato correttamente il token un istante dopo.
- Correzione minima: scrivere token e durata prima di usare `reload_status="completed"` come commit marker, oppure restituire uno snapshot coerente sotto lock. Aggiungere un solo test focused che controlli che lo stato terminale del reload non sia osservabile senza token/durata.

## Verifiche

- Non ho rieseguito la suite Windows già dichiarata (`89 passed`), come richiesto.
- Baseline Linux comunicata dal PM: `80 passed`; post-Linux ancora da eseguire dal PM.
- Nessun test focused eseguito: entrambi i problemi derivano direttamente dall'ordine di controllo e non richiedono dipendenze o timing reali per essere confermati.

## Prossimo passo

Correggere i due punti, eseguire un test focused per ciascun contratto e poi il post-Linux predisposto dal PM.

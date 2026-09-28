# Fase 1a — report journal e snapshot ready

## Stato

Completata l'unità circoscritta 1a. Non chiude l'intera fase 1.

Quota ordinaria osservata: 26% residuo all'inizio, 24% alla fine; `ordinaryUsageAllowed=true`, `spendControlReached=false`.

## Diff

- `api/reindex.py`: durate monotone additive per coda, writer lock, build, reload e tempo fino allo snapshot pronto; esito/errore reload e token pubblicato separati dal risultato build; coalescing osservabile; dispatch successivo serializzato dopo il reload.
- `api/deps.py`: `reload_index_state()` restituisce il token effettivamente pubblicato e `None` quando mantiene lo snapshot precedente.
- `scripts/bench.py`: attende la conclusione del reload, espone la durata wall storica separatamente e invalida falso noop, coda fusa e reload incompleto/fallito.
- Test mirati aggiunti nei tre file assegnati. Journal storici senza nuovi campi restano leggibili con misure `None`.

## Test

- Baseline: `PYTHONDONTWRITEBYTECODE=1 C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -B -m pytest tests/test_reindex.py tests/test_bench.py tests/test_retrieve_reload.py tests/test_lifespan.py --basetemp ../.pytest-tmp-phase1a-baseline -q` — 80 passed.
- Regressioni RED: stessa suite senza `test_lifespan.py` — 7 failure attese sui nuovi contratti.
- Finale: `PYTHONDONTWRITEBYTECODE=1 C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -B -m pytest tests/test_reindex.py tests/test_bench.py tests/test_retrieve_reload.py tests/test_lifespan.py --basetemp ../.pytest-tmp-phase1a-final -q` — 89 passed.

Nessuna rete, risorsa operativa o benchmark GPU/RAM usato.

## Problemi aperti e prossimo passo

- Il breakdown interno scan/model/Qdrant/save/promote appartiene all'unità 1b e può vivere in `result["phase_timings_seconds"]` senza conflitto con i campi job di questa unità.
- Il PM eseguirà la verifica Linux predisposta e integrerà dopo revisione.

## Review fix 1

Stato: corretti entrambi i finding della review indipendente e i controlli aggiuntivi del PM.

- Un errore I/O del journal viene loggato senza interrompere reload, rilascio dello slot o dispatch del pending; il rilascio resta garantito da `finally`.
- `reload_status` è usato come commit marker: `pending` precede lo stato build `completed`; token e durate precedono `reload_status=completed`. La serializzazione degrada inoltre a `pending` ogni record incoerente.
- Un timeout con reload pendente produce un campione `valid=false`, non uno skip generico. Anche il full rebuild invalida il coalescing. Rimossa dalla nota benchmark l'attribuzione non verificata a “overhead fisso”.

Test Windows: `PYTHONDONTWRITEBYTECODE=1 C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -B -m pytest tests/test_reindex.py tests/test_bench.py tests/test_retrieve_reload.py tests/test_lifespan.py --basetemp eval/results/sidecar_20260915/sandbox/pytest1a-fix1 -q` — 93 passed. Log raw: `eval/results/sidecar_20260915/evidence/windows-phase1a-fix1.txt`.

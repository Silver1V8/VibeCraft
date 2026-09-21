# F2 — driver di delta reale, preparato

**Stato:** codice e controlli locali preparati; nessuna famiglia benchmark eseguita da questo worker. La curva T(N,k) e l'uscita U-02 richiedono le nove run reali e la review indipendente.

## Implementato

- `scripts/bench.py --real-delta` entra nel driver isolato senza importare `eval.run`/`core` del checkout operativo. Il driver accetta checkout assoluto esattamente sotto `rag/eval/results/<run>/sandbox/experiment`, output nuovo fratello, collection `sidecar_0628_*`, Qdrant `127.0.0.1:16333` e HTTP `127.0.0.1:18000`; rifiuta link, traversal, corpus o database non vuoti, collection/alias preesistente e `k>N` prima del lavoro.
- Corpus deterministico per N=10/30/100, docs/code/mixed, tre lunghezze cicliche; `VarianteA` diventa `VarianteB` senza cambiare byte length. Manifest e mutazioni conservano hash, byte e simbolo codice. k=10 misto sceglie 5 docs e 5 code; k=100 sceglie 50/50.
- Bootstrap incrementale reale in child fresco, server HTTP embedded, job HTTP no-op di verifica con job_id prima di congelare la baseline. Una snapshot nativa Qdrant e copia guarded degli artefatti sono ripristinate dopo ogni campione, sotto writer lock e dopo join del writer/reader; CURRENT, fingerprint file/artefatti, integrità e digest paginato di ID/payload/vettori sono confrontati. Snapshot e restore hanno timeout client 300 s e nessun retry automatico.
- Cinque ripetizioni per cella per default. Un reader concorrente consulta `/api/retrieve` per docs, `/api/code/search?min_score=0` per code, alterna i due per mixed, con pausa 0,15 s; baseline query sequenziali usano gli stessi endpoint. Job non completati/coalesced/stale, falso noop, conteggi divergenti, errori HTTP o restore incompleto invalidano e fermano la run. Risposte HTTP 200 con zero risultati durante l'update Qdrant sono conservate come degrado osservato, non scartate. `result.json` è checkpoint incrementale; `summary.csv` riporta mediana/min/max del `snapshot_ready_duration_seconds` e differenza abbinata con k=0. `elapsed_seconds` HTTP resta separato perché include il polling 0,5 s. Nessun p95 da cinque osservazioni.

## Ruling e limiti

Il brief richiedeva bootstrap HTTP su database vuoto, ma `api.deps.lifespan` rifiuta il server senza `graph.json`. Il PM ha autorizzato il bootstrap incrementale diretto in child già usato in F1, seguito da un vero job no-op HTTP registrato come `baseline_verification_job`; non viene etichettato come build HTTP della baseline. Nessun core change o full rebuild.

Il preflight PM dello snapshot Qdrant 1.19 su bind Windows ha dato 500 WAL durante recover; su volume Docker nativo, stessa versione e parametri, create/recover ha ripristinato punti/payload/vettori. Il driver non ritenta un recover fallito e conserva evidenze. Il restore I/O è fuori da T. Cache OS non controllata; modello offline, quattro thread CPU e sampler esterno sono responsabilità della run PM. Nessun crossover full o soglia universale viene inferito.

## Verifica locale

Test prima del driver: `test_bench_delta.py` falliva in collection per modulo assente. Dopo l'implementazione: test mirati per selezione distinta/lunghezza, `k>N`, falso noop, journal incompleto/coalesced, conteggi code/mixed, guard database/alias e restore di byte reali. Un test inietta un errore nel job dopo la mutazione k=1, attraversa il `finally` di `run()` e verifica sorgente, CURRENT e checkpoint ripristinati; test ordinari `test_bench.py` preservati. Windows runtime read-only `python -B -m pytest tests/test_bench_delta.py tests/test_bench.py -q -o addopts= -p no:cacheprovider --basetemp=eval/results/sidecar_20260915/sandbox/pytest-phase2-final4`: **36 passed, exit 0**. Ruff sui tre Python: **All checks passed, exit 0**. `git diff --check`: exit 0. Nessuna prova modello/Qdrant del driver F2 ancora eseguita.

Portabilità del test: la prima suite Linux ha dato **35 passed, 1 failed** perché il fake `subprocess.Popen` del solo test di eccezione intercettava anche `/sbin/ldconfig` durante l'import di CUDA. Il fake ora intercetta esclusivamente il child `bench_delta.py --bootstrap` e delega gli altri comandi al `Popen` reale. Nessun codice del driver è cambiato. Windows combinato dopo il fix: **36 passed, exit 0** (`--basetemp=eval/results/sidecar_20260915/sandbox/pytest-phase2-portability`); Ruff del test: exit 0. Rerun Linux pendente al PM.

Verifica PM Linux dopo fix test: 36 passed in18.28s, exit0, evidence/linux-phase2-driver-portable.txt. Smoke reale docsN10 k0/1 una ripetizione completato exit0: entrambi validi e restore_verified=true, readiness2.60819/3.42075s. Evidenze in sidecar_delta_20260921_smoke_docs_n10/evidence; smoke escluso dalle curve a5ripetizioni.

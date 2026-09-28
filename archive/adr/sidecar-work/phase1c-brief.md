# Fase 1c — campionatore esterno di processo

Proprietà esclusiva: rag/scripts/bench_process.py (nuovo), rag/tests/test_bench_process.py (nuovo), rag/pyproject.toml e rag/uv.lock SOLO dichiarazione psutil dev. Report rag/adr/sidecar-work/phase1c-report.md.

Fase1 richiede campionare boot/query/delta/reload reali, compresi server Qdrant, sistema e device quando usato. Qui implementa soltanto strumento riusabile minimo; PM eseguirà workload reali in sandbox. Nessuna capacità dichiarata dai test. Non toccare scripts/bench.py, indexing, API o altri test (worker attivi).

CLI proposta: --output PATH --interval SECONDS (default 0.2, positivo) --qdrant-container NAME opzionale -- COMMAND ARG... . Lancia il comando esplicito via subprocess con argv, mai shell=True; salva stdout/stderr in file accanto al report. Campiona PID root e figli con psutil, ogni processo separato (mai somma RSS condivisi). Conserva timestamp monotono/UTC, RSS, private Windows se presente, USS dove disponibile, I/O counters, CPU times, processo/parent PID; campione sistema virtual_memory/swap, limite cgroup quando disponibile. Assenze/access denied/campi non supportati = null + motivazione, non 0 inventato. Salva grezzi JSONL progressivamente e JSON conclusivo con exit code/parametri/runtime/versioni. Nessuna raccolta env globale o segreti.

Per Qdrant container dedicato, se opzione presente, campiona a cadenza più lenta (es.1s, dichiarata) /proc/1/status e /proc/1/smaps_rollup e cgroup tramite docker exec/read-only (verifica /proc/1/comm sia qdrant). Ottieni RSS e Private_Clean+Private_Dirty, riporta separatamente cgroup usage/limit/cache e non confonderli con USS/RSS. Niente modifica/start/stop di container nel sampler. Se immagine non offre comandi di lettura, segnala limite in report e consenti misura app. Non interrogare container operativi per default.

GPU: non implementare NVIDIA API ora; accetta dichiarazione device CPU/default e registra 'not measured' per memoria device con motivo. PM aggiungerà query GPU se la usa; questo limite rimane APERTO, non falso successo.

Fine: attendere naturale uscita del workload; Ctrl-C/errore sampler deve arrestare il proprio workload con richiesta graceful, evitare orphan process e non killare immediatamente eventuali scritture. Documenta responsabilità workload per shutdown sicuro; nessun timeout implicito per i job. Segnala eccezioni e salva evidenze parziali. Implementazione semplice, niente framework generico, logging/std lib prima di astrazioni.

Test piccoli con vero subprocess Python che alloca memoria e termina, e parsing metriche Linux con testo noto; verificare output e exit code/fallimenti, non misurare capacità. Non eseguire benchmark pesante/model/GPU. Runtime read-only C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -B -m pytest dalla rag del worktree, PYTHONDONTWRITEBYTECODE=1, basetemp in eval/results/sidecar_20260915/sandbox/. Se lock update online produce modifiche estranee fermati e comunica: non aggiornare dipendenze unrelated.

Nessun subagente/commit/push/acquisto. Quota get_usage_limits inizio/fine e circa5min, codex ordinario, stop<=15% residuo/ordinaryUsageAllowed=false/spendControlReached/non osservabile, report e PM al primo punto sicuro. Limite attuale circa24%. Report preciso test/comandi/esiti, limiti e schema, breve finale. NON marcare tutta fase1 chiusa.

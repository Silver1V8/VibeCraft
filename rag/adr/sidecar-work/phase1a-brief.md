# Fase 1a — journal e disponibilità snapshot

Requisiti: SCALABILITA_SIDECAR_DELTA.md fase 1, primi due punti e test journal/benchmark; non l'intera fase 1.

Proprietà esclusiva: rag/api/reindex.py, rag/api/deps.py, rag/scripts/bench.py, rag/tests/test_reindex.py, rag/tests/test_bench.py, rag/tests/test_retrieve_reload.py. Report: rag/adr/sidecar-work/phase1a-report.md. Non modificare altri file senza coordinamento PM.

Implementare misure monotone additive del job: coda, attesa writer lock, esecuzione build e reload, tempo fino a snapshot pronto. Conservare created_at/finished_at con semantica storica. Le durate core per scan/model/etc verranno aggiunte in unità successiva.

Persistire separatamente stato, durata, errore reload e token realmente pubblicato. Build completed non implica snapshot ready. Reload può attualmente fallire e ritornare None: rendere l'esito osservabile senza rompere la tolleranza dei chiamanti HTTP. Nessun token inventato per callback legacy/fake che non ne restituisce. Evitare che un job successivo corra e promuova CURRENT prima del reload del precedente: serializzare coerentemente completamento/reload/dispatch; mantenere writer lock e snapshot atomico. Analizzare tutti i chiamanti prima delle modifiche.

Benchmark: attendere reload completato per snapshot pronto, non attribuire created_at/finished_at a tempo di esecuzione; distinguere metrica wall storica. Journal vecchi leggibili con nuove misure null/assenti, nessuna durata inventata. Falso noop (result.noop non true), coda fusa e reload fallito/incompleto devono invalidare la misura, non successo o skip generico. Non implementare ancora ottimizzazioni fase 3 (skip reload noop, lazy model, boot locals, streaming hash).

Accettazione comportamentale: callback bloccata lascia build terminale ma non ready; bench continua ad aspettare; failure reload distinto da failure build; token reale verificato; storico senza campi leggibile; coda/coalescing esistente preservato e rilevabile; fake noop rigettato. Test mirati prima delle modifiche per baseline, poi regressioni e suite dei tre file + test_lifespan.py. Test sono correttezza, non capacità.

Eseguire dal worktree rag usando C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -B -m pytest, --basetemp nella directory di questo worktree; non installare nel venv sorgente. PYTHONDONTWRITEBYTECODE=1. Risorse operative vietate. Nessun benchmark GPU/RAM, rete, acquisto, push o merge. Non creare sottoagenti. Non fare commit (il PM integra una volta revisionato).

Controllare get_usage_limits inizio/fine e circa ogni 5 minuti, bucket codex ordinario (non Spark), remaining=100-usedPercent. Se <=15%, ordinaryUsageAllowed false, spendControlReached o quota non osservabile: fermarsi al primo punto sicuro, scrivere report/checkpoint e avvisare PM. Nessun retry/sleep-loop/reset. Anche ordine esplicito PM di pausa va seguito. Il report deve contenere stato, diff, test con comando/esito, problemi aperti e prossimo passo; risposta finale breve. Non dichiarare tutta la fase completata.

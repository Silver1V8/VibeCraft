# Scalabilità sidecar — checkpoint

Stato: RUNNING_PHASE_1. Task: 01a0a441-79f6-7912-93ac-86a6e12518ee.
Worktree: C:/Users/Silve/.codex/worktrees/0628/vibecraft. HEAD iniziale: 4f35acf7ad18034c42203090189dfccfdbe42611 (detached, gestito dall'app).
Heartbeat: ripresa-astra-scalabilit-sidecar, ACTIVE confermato dalla task chiamante. Pausa <=15%; ripresa solo ordinaryUsageAllowed e >=25% per finestre codex disponibili. Spark escluso.

## Ricognizione

- Piano, nota fonti, memory.json e METHOD.md letti dal checkout sorgente e copiati senza modificarlo; hash nel file PROVENIENZA.
- Nessun AGENTS.md/CLAUDE.md trovato nel worktree o antenati applicabili.
- Divergenza da 18c4dc9: solo rag/README.md e template infografica; riscontri core del piano ancora presenti.
- Quota 2026-09-15: codex 74% usato, 26% residuo, ordinaryUsageAllowed=true, reset Unix 1789978065; seconda finestra non disponibile. Crediti extra zero non bloccano uso ordinario.
- Python sorgente disponibile, da usare soltanto come runtime read-only con -B; import dal worktree. Docker disponibile con immagine Qdrant v1.19.0 locale; container operativi vietati. Linux: solo distribuzione docker-desktop osservata, nessun test Linux eseguito.
- Budget prodotto: utente conferma non definiti, progetto destinato a macchine diverse. Pubblicare curve per hardware/parametri, senza soglia universale.

## Esecuzione

- Sol assegnato alla fase 1a (journal/reload/benchmark readiness), report sidecar-work/phase1a-report.md.
- Luna indisponibile (model at capacity); Terra fallback sulla matrice completa, file SCALABILITA_SIDECAR_DELTA_MATRICE.md, revisione documentale in corso.
- Sol phase1b assegnato a core/indexing.py + routes_reindex.py e test dedicati: breakdown, nessuna ottimizzazione.
- Baseline fase1a: 80 test Windows verdi (report worker); 80 test Linux verdi nel container isolato, evidence/linux-baseline-phase1a-tmpfs.txt. Primo Linux run 78/80 per DB montato read-only: due test archive scrivono PipelineStore; risolto nel harness con tmpfs privato del container, nessuna modifica produttiva.
- PM: ambiente Linux verificato, pytest pure Python copiato dal runtime esistente nella sandbox. Nessun modello reale/benchmark risorse ancora avviato; nessun processo benchmark attivo.
- Quota ultimo check: 80% usato, 20% residuo, uso ordinario consentito.
- 1a review round1: P1 journal bloccava coda su errore I/O; P2 readiness pubblicata prima dei campi. Fix verificato: 93 test Windows e 93 test Linux verdi. Re-review indipendente APPROVATA; evidence/linux-post-phase1a-fix1.txt conserva conteggio ed exit0. Unità pronta per commit locale; fase1 resta aperta in attesa delle misure reali e di1b/1c.
- 1b: implementazione candidata + 87 test propri verdi; 1c: candidato sampler + 3 test verdi. Review indipendente combinata in corso (non integrati).
- Qdrant dedicato ID 430a96a8f076a67bbc01deb2f872a4667b7fb41b63c4d9a4282be1a4a61c81a8, nome sidecar-0628-qdrant, porta16333, memoria1GiB/CPU2, è FERMO (exit143 dopo SIGTERM). Nessun dato indicizzato né workload reale ancora eseguito.

## Incidente sandbox e ripristino

Il worker1c ha passato la root sandbox come --basetemp: pytest ne ha eliminato le copie temporanee, incluse baseline e storage Qdrant dedicato vuoto. Checkout sorgente, codice di lavoro, report e log evidence NON coinvolti. Qdrant è stato fermato prima del ripristino. Archivio baseline rigenerato con SHA256 identico f1c59e17da0101702842da9cc3e397ee415f4ef6c0fa999457dc9318a90bc583; tutti i sette artefatti storici ricopiati hanno hash identici al record di provenienza; dipendenze Linux pure Python ricopiate. Snapshot precedente1a ricostruito da baseline + diff congelato per review. I log Linux80/89 restano validi, conservati fuori sandbox.

Ruling: ogni pytest deve usare una sottodirectory esclusiva sandbox/pytest-<unità>-<run>, mai sandbox stessa — previene cancellazione implicita pytest di risorse condivise; costo: qualche directory temporanea aggiuntiva. Non rimuovere directory mentre vi scrive un processo.

Ruling: il sampler non usa kill automatico dopo timeout — le istruzioni utente impongono di preservare scritture atomiche. Su errore attende fine sicura; il driver reale deve gestire stop e figli. Costo: un workload non cooperativo può richiedere attesa/intervento, da riportare senza dichiarare uno stop riuscito.
- Fasi 2–6 aperte; migrazione NPY, Qdrant e sharding condizionali ancora da decidere con dati.

## Decisioni

Ruling: suddividere fase 1 in journal/readiness e strumentazione core/processo — evita una singola unità troppo grande per la riserva; costo: integrazione esplicita dei due contratti.
Ruling: conservare brief/report e ledger sotto rag/adr/sidecar-work, anziché scratch da cancellare della skill SDD — il requisito utente chiede checkpoint ed evidenze durevoli nel worktree.

Prossimo passo: verificare baseline fase 1a, integrare dopo review indipendente; poi strumentazione e misura reale isolata. Non anticipare ottimizzazioni fase 3.

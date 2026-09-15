# Scalabilità sidecar — checkpoint

Stato: PAUSED_USAGE. Task: 01a0a441-79f6-7912-93ac-86a6e12518ee.
Worktree: C:/Users/Silve/.codex/worktrees/0628/vibecraft. HEAD iniziale: 4f35acf7ad18034c42203090189dfccfdbe42611. Branch: codex/sidecar-delta-0628. Ultimo commit funzionale: e8d8940; journal/readiness: 4a1539c. Nessun push/merge/pubblicazione.
Heartbeat: ripresa-astra-scalabilit-sidecar, ACTIVE confermato dalla task chiamante. Pausa <=15%; ripresa solo ordinaryUsageAllowed e >=25% per finestre codex disponibili. Spark escluso.

## Ricognizione

- Piano, nota fonti, memory.json e METHOD.md letti dal checkout sorgente e copiati senza modificarlo; hash nel file PROVENIENZA.
- Nessun AGENTS.md/CLAUDE.md trovato nel worktree o antenati applicabili.
- Divergenza da 18c4dc9: solo rag/README.md e template infografica; riscontri core del piano ancora presenti.
- Ultima quota 2026-09-15: codex 82% usato, 18% residuo, ordinaryUsageAllowed=true, spendControlReached=false, reset Unix 1789978065; seconda finestra non disponibile. Crediti extra zero non bloccano uso ordinario. Pausa anticipata autorizzata: la prossima unità di benchmark reale e analisi può oltrepassare la riserva del 15%. Ripresa solo con nuova lettura >=25%.
- Python sorgente disponibile, da usare soltanto come runtime read-only con -B; import dal worktree. Docker disponibile con immagine Qdrant v1.19.0 locale; container operativi vietati. Linux verificato nel container vibecraft:cpu su Docker Desktop.
- Budget prodotto: utente conferma non definiti, progetto destinato a macchine diverse. Pubblicare curve per hardware/parametri, senza soglia universale.

## Esecuzione

- Sol ha completato 1a (journal/reload/readiness) e 1b (breakdown core/route); Terra ha completato 1c (sampler processo) e matrice dopo indisponibilità Luna. Review indipendenti Sol approvate. Tutti i worker sono conclusi/inattivi, verificato tramite list_agents.
- Baseline fase1a: 80 test Windows verdi (report worker); 80 test Linux verdi nel container isolato, evidence/linux-baseline-phase1a-tmpfs.txt. Primo Linux run 78/80 per DB montato read-only: due test archive scrivono PipelineStore; risolto nel harness con tmpfs privato del container, nessuna modifica produttiva.
- PM: ambiente Linux verificato, pytest pure Python copiato dal runtime esistente nella sandbox. Nessun modello reale/benchmark risorse ancora avviato; nessun processo benchmark attivo.
- 1a review round1: P1 journal bloccava coda su errore I/O; P2 readiness pubblicata prima dei campi. Fix verificato: 93 test Windows e 93 test Linux verdi, review APPROVATA, commit 4a1539c.
- 1b: timing codice corretto in parsing_embedding e eval_gate distinto da promote; 90 test owned verdi. 1c: attesa senza kill, identità PID+create_time, esclusione zombie, collector Qdrant separato con risultato finale, checkpoint atomico prima dell'attesa su errore; 8 test focused verdi. Review 1b fix1 e 1c fix2 APPROVATE, commit e8d8940.
- Verifica integrata PM dello stato e8d8940: 184 passed Windows (23.34s), 184 passed Linux (27.64s), entrambi exit0. Log evidence/windows-phase1-integrated.txt e linux-phase1-integrated.txt. Ruff sui tre file nuovi Python passa. Diff senza errori trattando CRLF dei log raw come terminatori di riga. Sono verifiche funzionali, non misure di capacità.
- Qdrant dedicato ID 430a96a8f076a67bbc01deb2f872a4667b7fb41b63c4d9a4282be1a4a61c81a8, nome sidecar-0628-qdrant, porta16333, memoria1GiB/CPU2, è FERMO (exit143 dopo SIGTERM). Nessun dato indicizzato né workload reale ancora eseguito.

## Incidente sandbox e ripristino

Il worker1c ha passato la root sandbox come --basetemp: pytest ne ha eliminato le copie temporanee, incluse baseline e storage Qdrant dedicato vuoto. Checkout sorgente, codice di lavoro, report e log evidence NON coinvolti. Qdrant è stato fermato prima del ripristino. Archivio baseline rigenerato con SHA256 identico f1c59e17da0101702842da9cc3e397ee415f4ef6c0fa999457dc9318a90bc583; tutti i sette artefatti storici ricopiati hanno hash identici al record di provenienza; dipendenze Linux pure Python ricopiate. Snapshot precedente1a ricostruito da baseline + diff congelato per review. I log Linux80/89 restano validi, conservati fuori sandbox.

Ruling: ogni pytest deve usare una sottodirectory esclusiva sandbox/pytest-<unità>-<run>, mai sandbox stessa — previene cancellazione implicita pytest di risorse condivise; costo: qualche directory temporanea aggiuntiva. Non rimuovere directory mentre vi scrive un processo.

Ruling: il sampler non usa kill automatico dopo timeout — le istruzioni utente impongono di preservare scritture atomiche. Su errore attende fine sicura; il driver reale deve gestire stop e figli. Costo: un workload non cooperativo può richiedere attesa/intervento, da riportare senza dichiarare uno stop riuscito.
- Fasi 2–6 aperte; migrazione NPY, Qdrant e sharding condizionali ancora da decidere con dati.

## Decisioni

Ruling: suddividere fase 1 in journal/readiness e strumentazione core/processo — evita una singola unità troppo grande per la riserva; costo: integrazione esplicita dei due contratti.
Ruling: conservare brief/report e ledger sotto rag/adr/sidecar-work, anziché scratch da cancellare della skill SDD — il requisito utente chiede checkpoint ed evidenze durevoli nel worktree.

## Ripresa concreta

1. Leggere quote reali; proseguire soltanto >=25% per tutte le finestre codex disponibili e uso ordinario consentito. Heartbeat verificato ACTIVE nella task corrente, non duplicarlo né disattivarlo per questa pausa.
2. Riconciliare git, agenti e processi. I due run pytest sono terminati; il container test Linux usa --rm. Qdrant dedicato è fermo, porte 16333/18000 senza listener; nessun modello/server benchmark avviato.
3. Implementare l'unità piccola descritta in sidecar-work/phase1d-brief.md, finora SOLO PREPARATA e non delegata: driver reale CPU con corpus isolato, bootstrap incrementale, boot/query/noop/k1/reload, campioni processo/Qdrant. Preparare sandbox/experiment e ricreare sandbox/qdrant prima di riavviare il container dedicato. Verificare collection, percorsi e porte prima di ogni mutazione. Nessun risultato reale ancora disponibile.
4. Completare F1 metadati/misure, poi F2 T(N,k) con ripristino file E indice, almeno tre N e cinque ripetizioni per cella. Token codice oggi null con motivo: non inventare conteggi. Non anticipare ottimizzazioni F3. F4 confronta reader; F5/F6 mantengono le condizioni del piano.

File temporanei non tracciati conservati: .pytest-tmp-phase1*, sandbox/ alla root e snapshot/diff di review sotto ADR. Non confonderli con output finale; non cancellare automaticamente dopo il precedente rifiuto di cleanup al worker. Ogni modifica funzionale è nei due commit locali indicati. Brief/report/evidenze e questo checkpoint restano nel worktree. Nessun input prodotto mancante blocca le curve: budget non definiti è una scelta esplicita dell'utente.

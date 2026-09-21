# Scalabilità sidecar — checkpoint

Stato: RUNNING_PHASE_3. Task: 01a0a441-79f6-7912-93ac-86a6e12518ee.
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

Ripresa 2026-09-21T09:20Z: quota codex 99% residuo, ordinaryUsageAllowed=true, spendControlReached=false, reset 1790587202; altra finestra non disponibile. HEAD 232d515, nessuna modifica funzionale pendente, soltanto temp non tracciati. Nessun worker o Python attivo. Container dedicato precedente non più presente (container operativi ancora esclusi), porte dedicate libere: ricreare soltanto risorsa sperimentale. Nuovo Terra phase1d prepara il driver, PM prepara sandbox; review separata prima della run. Si continua a usare il ledger durevole ADR già stabilito, non si redistribuiscono le unità completate.

## Stato corrente dopo la prima misura reale (21 settembre)

Quota codex 93% residua, ordinaryUsageAllowed=true, spendControlReached=false; seconda finestra non disponibile. Nessuna pausa quota.

Qdrant dedicato ATTIVO, ID4585573c7f4e577d51442ee2ae41ebea6fbb6e570634cfda1d1bb2d388ccd9a8, porta16333, collection sidecar_0628_benchmark. I riferimenti precedenti al vecchio container fermo e alla mancata esecuzione sono storici. Driver Terra phase1d APPROVATO da Sol review1d (fix2); sintassi/selfcheck byte CRLF e relazione PID/PPID reali passati. Driver e report non ancora committati.

Run reale `evidence/calibration-20260921` con sampler `calibration-20260921-process.json/jsonl`: TERMINATA exit1, nessun Python benchmark residuo. Bootstrap incrementale reale: 3 documenti, 9 chunk, 343 token ColBERT e 1 file codice; boot e tre query con risultati riusciti. No-op verificato, readiness 2.682s (init modello 2.250s). Delta1 fallito 409 Qdrant «Collection already exists»: manifest fresh bootstrap dichiara la collection fisica omonima alla base e il reconciler tenta un alias omonimo. Questa è l'ipotesi da confermare con regression; nessuna fase viene chiusa dal run fallito.

Sorgenti ripristinati byte per byte, fingerprint iniziale=finale, writer terminati e server spento. Il campo index_final_state del risultato originale è troppo assertivo in caso di errore: non prova una modifica riuscita dell'indice. Driver aggiornato a dicitura conservativa per le prossime run; raw originali conservati. Riepilogo parziale in `calibration-20260921-partial-summary.json`: campioni osservati, non picchi assoluti, nessuna somma RSS condivisa né soglia di capacità.

Sol `bootstrap_alias` sta diagnosticando/fissando esclusivamente core/indexing.py e test correlati; rapporto atteso `sidecar-work/bootstrap-alias-report.md`. Nessun altro worker o benchmark attivo. PM conserva e analizza evidenze; non avviare duplicati.

Ruling: il venv Windows può lanciare Python con PID diverso da Popen; verificare PID oppure PPID del child contro Popen. Il delta sperimentale scrive byte UTF-8 di lunghezza invariata, preservando CRLF. Campioni sampler richiesti 0.1s, mediana effettiva0.140s nella prima run; non dichiarare precisione temporale superiore ai dati.

## Prossimo passo

1. Review indipendente del fix alias dopo regression red/green; test pertinenti Windows/Linux. Non applicare ottimizzazioni F3 prima della curva F2.
2. Ripetere calibrazione in output NUOVO con baseline dedicata vuota, preservando database/log precedenti e toccando soltanto risorse sperimentali verificate. Non rilanciare finché un benchmark è attivo.
3. Completare F1 metadati/misure e matrice, poi F2 T(N,k) con ripristino file E indice, almeno tre N e cinque ripetizioni per cella. Token codice oggi null con motivo, nessun conteggio inventato.
4. F3 dopo baseline; F4 confronto reader; F5/F6 con rami condizionali e dati. Budget non definiti significa curve hardware-specifiche, non blocco né soglie universali.

File temporanei e snapshot di review conservati; nessuna cancellazione automatica. Ogni pytest usa una leaf esclusiva, mai sandboxroot. Nessun push/merge/pubblicazione o modifica checkout sorgente.

## Fase 1 verificata, avvio Fase 2

Seconda calibrazione `calibration-20260921-r2` riuscita exit0: integrity ok, noop vero, delta1/3chunk/114token, readiness2.62875/4.18727s, fingerprint ripristinato, writer/server chiusi. Summary e PHASE1.md descrivono memoria e limiti: reload11–15ms troppo breve per picco separato, hostcache non disponibile, token codice null motivato. Review indipendente phase1-evidence-review.md approva U-01; attribuzione causale non misurata del tempo residuo rimossa. Nessuna soglia di capacità. Fixalias reviewapprovata, 85test Windows, suiteLinux exit0.

Nuovo Qdrant dedicato attivo IDd3925ae83db66bb7f76fb53c09d62ebdc5d469be043514c1b9e79fe9b717101f, storage sandbox/qdrant-r2. Vecchio contenitore dedicato rinominato sidecar-0628-qdrant-failed-calibration, fermo, preservato; vecchioDB archiviato sandbox/calibration-failed-database. Nessun processo benchmark attivo.

Sol phase2 implementa brief phase2-brief.md: driver guarded reale N10/30/100 docs/code/mixed, cinque ripetizioni, restorefile+indice tramite snapshot Qdrant, querycontesa. Non ha permesso di avviare modello/container prima della review; PM prepara esecuzione. Quota92% residua. F3–6 non avviate. Il prossimo passo è review F2/test essenziali Windows/Linux, poi smoke reale e famiglie sequenziali, senza duplicare run attive.

## F2 esecuzione reale in corso, 21 settembre ore12:26 locali

HEAD17ce3ca (driverF2+smoke), predecessore914a170 (F1+fixalias). Review F2fix1 APPROVATA, 36test Windows e36Linux verdi; log Linuxportabilityfailed conservato e fix testscoped verificato. Smoke docsN10k0/1reps1 riuscito, escluso dalle curve. Aggregatore Terra summarize_delta.py pronto (CSV/MD/SVG, no mock confusi con misure), PM summarize_resources.py verificato sui15campioni reali docsN10.

Qdrant bindWindows snapshotrecover falliva500 WAL; container d3925... preservato fermo come sidecar-0628-qdrant-bind-r2. Nuovo container attivo de6aa3529ba7556925ea447e9fe1fc9817dc420f3450bb1c2616981f3021d4be, stesso nome sidecar-0628-qdrant/porta16333/1GiB/2CPU, volumeDocker nativo sidecar-0628-qdrant-native-f2. Probe nativo dimostra restorevero identico. Le precedenti collection sperimentali restano nel container; il sampler misura tutto Qdrant, non solo la famiglia corrente (limite dichiarato nei resourceJSON). Nessun target operativo toccato.

Famiglie ufficiali concluse exit0: sidecar_delta_20260921_docs_n10 e docs_n30, 15campioni validi e restore_verified ciascuna, 5reps×k0/1/10. JSON/CSV/log/samples sotto rispettive evidence; baseline-db resta workload/baseline-database. MedianeT readiness N10:2.62664/3.37828/5.08410; N30:2.58107/3.50654/5.26721. Queryvuote durantek=N sono degrado osservato, non mascherate: N10totale29/55query, nessunHTTPerror.

ATTIVA: docs_n100, session52619, driver bench.py --real-delta N100 docs k0,1,10,100 reps5 con sampler. Non duplicare/rilanciare. Dopo questa famiglia restano code_n10/30/100 e mixed_n10/30/100, già preparate vuote conconfigpropria. Prima di ogni famiglia leggerequota e verificareprocessi/risultati. Quota84% residua ordinarytrue. Nessunworkerattivo; F3briefpreparato ma NONdelegato, attenderebaselineF2complete. Nessuna ottimizzazioneproduttiva iniziata.

## F2 checkpoint aggiornato — 21 settembre, sei famiglie concluse

Docs e code N10/30/100 completati exit0: 100 campioni totali validi e restore_verified, cinque ripetizioni per cella. Raw copiati in evidence, riepiloghi risorse generati per tutte le sei famiglie. CodeN100 mediane T k0/1/10/100: 2.61430/3.56532/5.64534/19.01669s. Nessun benchmark Python residuo prima della nuova famiglia.

ATTIVA mixedN10, session57833; poi restano mixedN30/N100. Non rilanciare. Qdrant nativo de6aa352... invariato. Quota83% ordinarytrue, no spendblock. Sol review1d verifica indipendentemente le sei evidenze e gli aggregatori; non chiude F2 prima delle miste. F3 ancora non delegata.

## F2 ultima famiglia attiva

MixedN10 e N30 concluse exit0, 15 campioni validi/ripristinati ciascuna: totale130. Raw e resources in evidence. ATTIVA mixedN100 session45169; nessun duplicato. Review parziale indipendente approva docs/code e aggregatori senza correzioni. Quota82% ordinarytrue. F3–6 non implementate; F4 ha solo brief preparatorio.

## F2 chiusa e F3 avviata — 21 settembre ore12:53 locali

F2 tutte9famiglie terminate exit0, 150campioni validi/ripristinati, 30celle×5. Aggregato CSV/MD/SVG/PDF e raw/resources completi. Review indipendente phase2-evidence-review APPROVATA F2/U02; PM ha rasterizzato il PDF e controllato grafico (etichette/assi/intervalli leggibili). PHASE2.md descrive corpus brevissimo, tempi, contesa/risposte vuote e limiti; niente soglia o full crossover. Nessun processo benchmark residuo.

Sol phase2 riusato per F3-01..04, brief phase3-brief.md: lazy modello, noop pronto sullo snapshot realmente servito, release boot, hash streaming; test essenziali e report. Non avvia modelli/container né committa. PM chiude commit evidenze F2, quindi review/test Linux e prepara confronto post. F3-05 resta aperta fino a ripetizione150prove. Quota81% ordinarytrue, Qdrant de6aa352... conservato attivo; per post creare volume nativo equivalente separato preservando precedente.

# Scalabilità sidecar — checkpoint

Stato: VERIFIED_COMPLETE. Task: 01a0a441-79f6-7912-93ac-86a6e12518ee. Stato operativo aggiornato nell'ultima sezione; le sezioni precedenti sono lo storico.
Worktree: C:/Users/Silve/.codex/worktrees/0628/vibecraft. HEAD iniziale: 4f35acf7ad18034c42203090189dfccfdbe42611. Branch: codex/sidecar-delta-0628. Ultimo commit funzionale: 708a142; evidenze F6: f8f92f2. Nessun push/merge/pubblicazione.
Heartbeat: ripresa-astra-scalabilit-sidecar, RIMOSSO tramite automation_update dopo chiusura verificata. Pausa <=15%; ripresa solo ordinaryUsageAllowed e >=25% per finestre codex disponibili. Spark escluso.

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

F2 evidenze fissate nel commit0876476. PM ha fermato graceful senza timeout/kill il contenitore F2 de6aa352... e conservato nome sidecar-0628-qdrant-native-f2 e volume originario. Nuovo contenitore F3 fa005441f96141732e8a924d11003aa895f889eb4436d8f27a3ddd261a2efb70, nome sidecar-0628-qdrant, volume sidecar-0628-qdrant-native-f3, stessi image/1GiB/2CPU/porta16333. Probe reale create/change/recover identico in qdrant-native-f3-snapshot-probe.json. Nessun benchmark attivo; implementer phase2 lavora F3. Preparare smoke e nove famiglie post soltanto dopo review e test.

F3-01..04 implementate, review Sol APPROVATA. Windows277passed in due suite, Linux268passed/9skip per Git assente nelcontainer (logconservato); Ruff/diffcheck passati. Due test preesistenti isolati dal DB/repo antenato, nessun rollbackproduttivo cambiato. Workerphase2 terminato. Prossimo: commit F3, nuova copia codice congelato, smoke post e9famiglie, nessun benchmark attivo ora. Quota79% ordinarytrue.

## F3 misure post avviate

Codice0f479b2 congelato in archivio/copie: phase3-prepared-environment.json. Smoke post docsN10k0/1reps1 exit0, vero noop init0/reload0/tokenservito e readiness circa0.02s; delta1 circa3.51s. Entrambi ripristinati, smoke escluso dal confronto. ATTIVA serie ufficiale post docsN10 session54809; restano8famiglie preparate. Nessun test/modello concorrente. Terra phase2_summary prepara solo aggregatore confronto offline, Solreviewer idle. Quota77% ordinarytrue. ContainerF3 fa005441... attivo, F2 preservato fermo. Prossimo: convalidare ogni famiglia/copiare raw e resources; poi aggregato/reviewindipendente e chiusura F3.

## F3 post: documenti conclusi, codice in corso

Tutte3famiglie docs post concluse exit0,50campioni validi/ripristinati, raw e resources in evidence. Noop mediana N10/30/100:0.01753/0.03542/0.06312s; delta1/10/100 rimane vicino alla baseline. ATTIVA codeN10 session74495; proseguire codeN30/N100 poi mixedN10/30/N100. `evidence/series-post-progress.json` è il record aggiornato dopo ogni avvio con sessione e conteggi: riconciliare quel file con processi e result.json, non ripetere le famiglie concluse.

Terra phase2_summary corregge2guard dell’aggregatorecompare_delta.py (config noncomparabile devefallire, sampler/resources devono esserevalidi); Sol review1d attende fix. Non alterano codice misurato. Quota75% ordinarytrue. F4/F5/F6 restano aperte.

## F3 chiusa, F4 preparazione sperimentale — 21 settembre

Tutte9post concluse exit0,150prove valide/ripristinate. Compare_delta approvato dopo guardconfig/sampler, confronto30celle e grafico post generati, visualQA PDF/PNG passato. Review indipendente phase3-evidence-review APPROVATA F3-05. PHASE3.md: noop migliora tutte9celle (circa2.55–2.68s risparmiati), delta contenuto non accelera in modo generale. Corpus+puntiQdrant identici e vettoricodeNPZ9coppie uguali; YAML10coppie identiche salvocollection/lineending. Nessuna soglia o crossover.

Ruling U03: riduzione misurata e invarianti verificate. La clausola «se coprevolume/budgetrimanda» non si attiva con budget nondefiniti per scelta utente; F3 è conclusa e si procedeF4, senza richiedereinput ripetuto né dichiarare budget coperti.

Sol phase2 riusato per driver/prototipi F4 in nuova run sidecar_readers_20260921; ownership soloevidence/sandbox/report, no produzione, modelli/container o realbenchmark fino areview. Deve confrontare 3reader su storici257chunk/112429token e retrieval completo sulla baselineF3mixedN100/collection sidecar_0628_mixed_n100_post; casi grafo/missing/concorrenza/oldsnapshot. PM chiude commit F3evidenze, poi prepara run. Nessunbenchmark attivo. QdrantF3 fa005441... resta attivo, tuttiF2preservati fermi. Quota72% ordinarytrue. F5 ancora condizionale, F6 aperta. Non duplicaretask/monitor.

## F4 verificata e decisione F5 — 21 settembre

Driver199cd78 review approvata dopo4guardfix. 15replay I/O storici+15retrieval completi F3mixedN100, exit0, ranking/score identici;257+50array paritari, snapshot differente/concorrenza testatiWin/Linux. PHASE4.md e phase4-evidence-review APPROVATO. NPY caldo storico0.139s vs lazyNPZ0.259s ed eager0.076s; USSload0.50/0.57/222.5MiB. Fullpiccolo NPYpiùlentodieager7–27ms, esplicito. NTFSNPZ195739648Ballocati, NPY230420480Ballocati (+17.7%). Nessunbudgetcoperto o miglioramentoreindex dichiarato.

DecisionePM: procedeF5 NPY perdoc, conforme ramo giàautorizzato e revisione indipendente. Noteimplementationphase5 descrivono leasecrossprocess perversione, writerimmutabile/bounded, hashintegrità e migrazionecandidata/rollback. Nessuna implementazioneF5ancora iniziata; prossimoSol unitàreader/writer/lease, poi integrazione e test/review. F6 aperta; helperdiskinventoryWindows/Linuxapprovato, preflightretention corretto (driverdeltaF2ripristinaogni prova, serveaccumulo separato). Nessunbenchmarkattivo. ContainerF3 fa005441... attivo e fontistoriche/F3 immutate verificato postrun. Quotafresh68% ordinarytrue; no task/monitor duplicati.

## F5A attiva — ultimo checkpoint operativo

Worker Sol /root/phase2 implementa SOLO reader/writer ColbertStore e lease in writer_lock con test mirati; non ancora collegati ad artifacts/indexing/deps. API/compromessi in phase5-brief.md. F4evidenze/decisione fissate29bf280. Worker Terra /root/phase2_summary prepara driver cumulativo F6 solo evidence/retention_experiment.py, nessun run reale. ReviewerSol idle dopo auditmatrice; prossima review F5A. PM ha chiuso cinque findingC storici già verificati secondo phase1-4-matrix-audit, senza dichiarare chiusi vincoli G/R continui.

Nessun benchmark/modello attivo. Ultima quota65%residuo ordinaryAllowedtrue. Problema da gestire in F5B/bench: bench_delta restore deve preservare/escludere filelease dai backup/fingerprint, quiescerequery/joinwriter e rilasciare snapshot prima del ripristino; non aggirare lease produttiva. _colbert_token_count deve usare offsetmetadataNPY per evitare lettura globale. F5A Windows prima, LinuxPM e review indipendente poi; non duplicare agenti/run.

## F5A verificata, F5B in integrazione — 21 settembre ore14:25 locali

HEAD a1cd42a: reader/writer/lease F5A approvati dopo correzioni di contenimento percorsi e attestazione degli hash padre. 27 test Windows e 27 Linux passati; lease shared reale Windows con LockFileEx, POSIX flock. Record in phase5a-report/review e sidecar_npy_20260921/evidence/linux-phase5a-fix1.txt. F5 resta aperta: modulo isolato non equivale a integrazione o misura reale.

Sol /root/phase2 integra artifacts/indexing/consumer, migrazione e retention, test e compatibilità del ripristino bench_delta. Non committare o congelare la produzione finché non consegna. Reviewer /root/review1d controlla il driver full_candidate_experiment; Terra /root/phase2_summary prepara soltanto corpus derivato identico pre/post dai primi32chunk storici e copia F3 congelata, senza modelli. Driver retention cumulativo già approvato staticamente; nessuna run F5/F6 reale avviata, nessun benchmark/modello attivo. Qdrant F3 invariato.

Quota fresca61% residuo, ordinaryUsageAllowed=true, spendControlReached=false, seconda finestra non disponibile. Prossimo: test/review F5B Windows/Linux, smoke reale per formato e possibili differenze numeriche dell'encoding per-documento (FlagEmbedding ordina globalmente per lunghezza nel vecchio percorso), poi misure fullcandidate/picco e curve150prove F6, retention cumulativa e disco deduplicato. Non assumere digest identico prima di misurarlo, né dichiarare incrocio full/delta da candidate senza gate/promozione.

## F5B review statica corretta; full precedente attivo — ore14:40 locali

ATTIVO sampler session40452, workloadPID29016: sidecar_fullmemory_pre_20260921/workload/result.json, codiceF3 congelato0f479b2,32documentiderivati da testi storici. Non duplicare. Driver fullcandidate pre-run APPROVATO; CURRENT/alias devono restare assenti, deepintegrity esplicita. Metodologia in sidecar_npy_20260921/evidence/FULL_MEMORY_METHOD.md. Questa è candidatafull esplorativa, nonincrocio full/delta. Sol attende fine benchmark per testfinali, nessunmodellotestconcorrente. Stato macchina/provenienza in evidence; codepre267file identici all'archivio.

Prova reale separata encoding_batch_parity completata:10chunk, puntiQdrantidentici,4valori fp16 cambiano max3.814697265625e-6;3query MaxSimscore/rankidentici. Reviewindipendente conferma limiti: nonparitàbyteuniversale e nonretrievalfull. F5B statica PENDING_TESTS, due finding risolti (manifest obbligatorio primaCURRENT; retryboundedload quandoCURRENTcambia durantelease). Restano suiteWin/Linux, reviewfinale e misurepost/F6. Quota56%ordinarytrue, nospendblock; heartbeatattivo.

## F5B verificata e congelata; full NPY attivo — ore15:03 locali

HEAD708a142 contiene integrazione F5B, CLI migrazione, loader/lease/prune, check profondi e gate full fail-closed per candidata illeggibile; README aggiornato. Review indipendente F5B APPROVATA. Windows405pass, Linux396pass+9skipGit (copertiWindows),17file; raw linux-phase5b.txt. Ruff/diffcheck passati dopo sola rimozione importduplicato test. Nessuna produzione in modifica.

Fullpre F3 TERMINATO exit0:32docs64chunks28659token,859.160sbuild,gate/promote0,CURRENT/aliasassenti. RSSmassimoosservato6910664704B,USS5462532096B,private8534343680B;4487campionibuild. Reviewraw/resourcesapprovata, input+267filecodeimmutati. Run sidecar_fullmemory_pre_20260921/evidence completa. Metodo fullcandidate distingue solo1prova/variante, modello/calibrazione inclusi, niente capacità/crossover.

ATTIVO fullpostNPY session64284, sidecar_fullmemory_post_20260921/workload;708a142congelato,stessi32files, attualmente22fileperdocpersistiti. Non duplicare e nessuntest/modelloconcorrente. Quota50%ordinarytrue ultima lettura14:58. Archivio sandbox/phase5-code-708a142.zip; post e migration checkout preparati con284file congelati e DBinizialmentevuoto, provenienza relativa. Primo tentativopreparazione post trovava docs unlivellosbagliato, fermato primaesecuzione; recupero verificato byteperbyte e corpus32copiato dal percorso docs corretto.

Terra corregge driver migration_experiment secondo reviewSol (7fileexact/no links, CURRENT/layout/hash/array/provenienzaprima-dopo), nessunrun. PM ha SCRITTO, non ancora eseguito prepare_phase6.py per smoke+9famiglie+retention/copiaguardata; attendere finefullpost prima del lavoro I/O. F6richiede nuova istanzaQdrantnativa equivalente preservandoF3, smoke,150prove comparabili,retentioncumulativa/disco. Nessun ramoQdrant/sharding attivato senza dati; budgetundefined restano curve.

## F5 misure full e migrazione concluse; parità ricerca in verifica

Full post session64284 TERMINATO exit0: stessi32documenti/64chunk/28659token, build487.775s rispetto859.160s; RSS massimo osservato3384897536B rispetto6910664704B. Una sola prova per variante, corpus derivato storico, encoding raggruppato diversamente: non attribuire tutta la riduzione al formato né dichiarare capacità/crossover. Input e284file congelati immutati, integrità profonda verificata, CURRENT/alias assenti.

Diagnosi indipendente full-numeric-parity: ID/payload/graph/chunks identici,50/64vettori differiscono numericamente; replay ColBERT salvato dà65score/ranking identici. Non è retrieval completo. Solphase2 prepara driver paired fullretrieval read-only prima di ruotare QdrantF3; nessun modello attivo ora. ReviewerSol verifica evidenze full/migrazione.

Migrazione storica session24490 TERMINATA exit0:257array esattamente preservati,112429token, candidataNPY/hash profondi verificati prima del rollback; CURRENT nuovamentev20260911T155042, ranking/missing identici,7fonti immutate. Nessun Qdrant contattato. Risultati copiati in sidecar_migration_20260921/evidence.

F6 preparazione ESEGUITA: smoke+9famiglieNPY+retention (11checkout) congelati708a142, manifest phase6-prepared-environment.json. Nessuna misuraF6 iniziata. QdrantF3 fa005441... resta attivo per pairedretrieval; poi preservarlo fermo e creareF6 volume equivalente. Quota47%residuo ordinarytrue/spendfalse. Automazione attiva; non duplicare run.

## F6 avviata dopo parità paired verificata — ore15:22 locali

Pairedretrieval session82906 exit0,3query top3: candidati ID/ordine identici,ranking finale esatto3/3; punteggi grezziQdrant diversi, nessuna paritàuniversale dichiarata. Reviewindipendente APPROVATA. PHASE5.md raccoglie implementazione/test/misure/limiti;U05 resta aperta per byteI/OdeltaF6.

QdrantF3 fa005441... fermato graceful e preservato come sidecar-0628-qdrant-native-f3. NuovoF6 sidecar-0628-qdrant ID2b2831f678b4ce762de18862623b0f1b08f9fca04241075fd63810c4d8ab57c8, volume sidecar-0628-qdrant-native-f6, stessi image/1GiB/2CPU/porta16333. Metadati container inNPYevidence.

SmokeNPY docsN10k0/1reps1 session74550 TERMINATO exit0,2campioni validi/ripristinati; escluso dallecurve. ATTIVO docsN10 ufficiale session39294 (15prove),708a142congelato. Restano altre8famiglie e retentioncumulativa. Nessunmodellotestconcorrente. Quota46%ordinarytrue, no spendingblock. Aggiornareprogress dopo ogni famiglia; nonrilanciare completate.

## F6 documenti conclusi — ore15:35 locali

DocsN10/30/100 terminate exit0:50prove valide/ripristinate, result/bootstrap/summary/resources copiati in evidence. ContainerF6 invariato. ATTIVO codeN10 session22875; restano codeN30/N100 e mixedN10/N30/N100, poi retention. `sidecar_npy_20260921/evidence/progress.json` mantiene la sessione corrente: riconciliare prima di riprendere.

Misure docsN100 mostrano rallentamento k100 (prime prove55–62s vsF3circa16s), dominato parsing/embedding49–55s. Non nascondere regressione né dedurre miglioramento generale dal full storico. F6-03 attiva studio batching/hardware: Sol ha preparato solo driver sperimentale encoding_batching_study.py, pre-run APPROVATO in phase6-batching-driver-review.md. Eseguirlo dopo tutte le misure ufficiali/retention, CPU4offline1modello3varianti+warmup3ripetizioni; no modifica produzione autorizzata dall'esperimento stesso. Causa plausibile: chiamata encoder/calibrazione per documento piccolo, batch12 limitato all'interno di ogni chiamata.

Quota42%ordinarytrue (finestre codex disponibili), no spendingblock. HEADaa1ffe3 conserva driver F6 approvati; codice misurato resta708a142. ReviewfinalecodeAPPROVATA, soloevidenzeF6pending. Nessun duplicatotask/monitor/processo.

## Chiusura verificata — 21 settembre 2026

Tutte le fasi applicabili F1–F6 e U01–U06 concluse e verificate; matrice finale esplicita i rami non attivati. F6 fissata in f8f92f2: 150/150 prove, 30celle×5, 45noop init/reload0, confronto rigoroso con F3 post, corpus/config/284filecodice percheckout immutati. CSV/JSON/SVG/PDF e raw conservati, grafico PDF rasterizzato e verificato visivamente. Nessun processo benchmark/modello sperimentale attivo.

Retention reale: cinque delta consecutivi, lettore pinned invariato, versione iniziale conservata oltre keep3 finché in uso, poi rimossa realmente (4→3versioni); fisico deduplicato1057712→844504B. Query150prove:1804osservazioni,20retrievevuote/0errori; retention19query/0vuote/0errori. Finestre diverse, nessun confronto causale normalizzato. SummaryQdrant corretto e revisionato:67sonde distintamente campionate+1finale=68, non436osservazioni cached.

StudioF6-03 reale conclusoexit0:100testi piccoli,3ripetizioni+warmup,encode-only globale7.408s/perdoc27.337s/gruppi12 13.404s. Parità vettori global/gruppi12 esatta nella prima ripetizione; perdoc87valoriColBERTfp16 diversi,score/rankcachedidentici. È uno studio, non una modifica produttiva. DecisionePM: prossimo candidato per throughput è batching limitato da verificare end-to-end; Qdrant/sharding non attivati, scan/save non dominanti, budgetundefined. Regressione reale docsN100k10015.934→58.099s e mixed19.132→38.602s esplicitata, nessuna accelerazione universale/capacità/crossover dichiarata.

Review indipendente codice e tutte le evidenze finali APPROVATE (phase6-final-code-review.md, phase6-evidence-review.md). Produzione identica a708a142, già405testWindows/396Linux+9skipGit copertiWindows. Nessun test aggiuntivo necessario per sole evidenze/documentazione successive. QdrantF6 ID2b2831... fermato graceful e preservato con volume; tutte le precedenti istanze sperimentali conservate, nessuna risorsa operativa toccata. Nessun push/merge/pubblicazione. Report finale: ../../archive/eval-results/sidecar_npy_20260921/evidence/PHASE6.md. Heartbeat rimosso tramite automation_update: deleteStatus=deleted.

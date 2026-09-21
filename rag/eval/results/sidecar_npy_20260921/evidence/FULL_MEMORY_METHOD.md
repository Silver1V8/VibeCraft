# Misura full candidate F5

Confronto esplorativo prima/dopo dell'intero percorso di build su CPU, distinto dalle curve delta con cinque ripetizioni per cella. Ogni prova parte da un database locale vuoto e da una collection Qdrant dedicata nuova. `promote=False` esclude gate, pubblicazione e readiness: questa misura non identifica l'incrocio fra full e incrementale.

## Input e isolamento

- Prima: codice F3 `0f479b2`, estratto dall'archivio già conservato. La verifica PM confronta byte per byte 267 file estratti con l'archivio; configurazione dedicata separata.
- Corpus derivato dai primi 32 elementi, nell'ordine originale, del `chunks.json` storico copiato. Il testo storico è riutilizzato, ma confini documento e frontmatter sono sintetici; parsing e conteggi token/chunk vanno rilevati dalla build, non ereditati dallo storico.
- Dopo: stessi file sorgente, verificati tramite hash, codice F5 congelato dopo test e review. La configurazione cambia soltanto il nome della collection dedicata.
- Runtime Windows e modello BAAI/bge-m3 già installati, CPU a quattro thread, offline; nessun test o altro modello concorrente. Qdrant sperimentale sulla porta16333, limite1GiB e2CPU. Le collection sperimentali precedenti rimangono nel server: le sue risorse sono totali, non attribuibili alla sola candidata.

## Lettura dei risultati

`bench_process.py` registra processi e risorse host; il PID del workload e i confini monotoni della build permettono di separare la build dal processo intero, inclusi import e successiva verifica profonda. Il caricamento del modello resta dentro la build ed è distinto nei tempi del collector. Non sommare RSS del launcher, del figlio e di Qdrant. Private memory Windows è memoria impegnata; USS è memoria privata residente.

I massimi campionati sono limiti inferiori del picco effettivo. I contatori di I/O del processo non misurano i byte fisicamente trasferiti dal disco. La cache del sistema operativo non viene svuotata; nessuna prova è dichiarata cache fredda. Un singolo full candidate per variante è una misura esplorativa, non una distribuzione di latenza o una soglia di capacità.

La differenza prima/dopo include sia il formato NPY sia il raggruppamento dell'encoding per documento: non attribuirla esclusivamente al reader o ai byte ColBERT. Metadata, grafo, dense e codice mantengono costi globali; il gruppo massimo resta almeno un documento con il relativo batch del modello.

## Controlli

Il driver rifiuta percorsi o collection fuori dal perimetro dedicato, database non vuoti e output riusati. Richiede un solo layout ColBERT, confronta hash profondi e manifest, verifica il numero dei punti Qdrant e registra CURRENT e alias base ancora assenti. Dopo la run il PM riconfronta corpus, configurazione e codice congelato. Un output scritto non equivale a successo: workload e sampler devono terminare senza errori.

La prova separata `encoding_batch_parity.json` misura dieci chunk sintetici F3: quattro valori fp16 cambiano fra encoding globale e per documento, massimo assoluto3.814697265625e-6; punti Qdrant identici e score/ranking identici sulle tre query controllate. Non implica parità numerica universale. La migrazione dello stesso archivio e il reader devono invece preservare esattamente gli array originali.

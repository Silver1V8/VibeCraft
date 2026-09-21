# Review pre-run indipendente — driver F6 retention

**Verdetto dopo fix: APPROVATO per il preflight statico; run reale ancora subordinata a F5B integrata e revisionata.** Review statica di `retention_experiment.py` e del report preparatorio; nessun modello, server, container o benchmark avviato. L'esperimento resta condizionato a F5B integrata e revisionata.

## Chiusura dei finding

- `_sha` delega ora a `delta._sha`, eliminando il `NameError` nello snapshot e nel reader figlio.
- Il preflight confronta l'hash della sorgente RAG fra copia frozen ed experiment, oltre alla config dedicata. Registra gli hash iniziali; prima di segnare `completed` verifica che frozen tree, frozen source ed experiment source siano immutati, e il risultato finale riporta i tre esiti. Database e bytecode sono esclusi dal digest sorgente perché sono stato della run.
- Il protocollo READY/CHECK/CLOSE ha lettura con deadline di 30 s e cleanup del child su timeout/handshake invalido; il processo diventa posseduto dal chiamante solo dopo READY valido. La prova reale deve comunque controllare nel result il PID/exit e l'assenza di lease residui.

## Contratti presenti e punti da conservare

`delta.validate_paths()` limita checkout/output a run dedicata e DB vuoto; la collection richiede prefisso retention dedicato. Il corpus docs N=10 è generato nel checkout, ogni modifica k=1 cambia byte senza restore e usa cinque file distinti. La baseline no-op HTTP verifica readiness, poi ogni job verifica token/current/integrità e salva journal, manifest, hash, digest Qdrant e inventario disco. Il reader HTTP è separato dal processo che mantiene la lease del vecchio snapshot; il driver richiede la versione ancora presente prima della chiusura e la rimozione reale dopo. Il sampler RSS/I/O è delegato esplicitamente al wrapper esterno, senza valori inventati.

**Limiti da dichiarare nel risultato:** HTTP 200 con `results=[]` durante i delta resta degradazione osservata, non successo di ricerca; i raw già salvano il conteggio, ma il report finale deve contarli per finestra/endpoint. `artifact_hashes` misura il set definito dal modulo artefatti: la copertura dell'indice NPY F5B va verificata prima della run. L'inventario locale non include lo spazio della collection Qdrant; il digest ne controlla contenuto, non bytes disco. L'esperimento prova retention locale e lettura concorrente su un solo host/corpus, non rollback del Qdrant condiviso né capacità universale.

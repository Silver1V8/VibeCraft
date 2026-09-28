# F5 — esecuzione del piano NPY già autorizzato

Decisione F4 verificata: `sidecar_readers_20260921/evidence/PHASE4.md`, review indipendente approvata. Seguire ADR §5/F5 e matrice F5-01..07, G-03/G-04; `phase5-implementation-notes.md` mappa i chiamanti. Nessun budget inventato, API a pagamento, nuova task, push o modifica del checkout Desktop. Runtime Desktop Python solo read-only `-B`. Ponytail full: stdlib e helper esistenti, nessun framework/backend/cache aggiuntivo.

## Unità A — formato, writer per documento e lease (Sol)

Ownership: nuovo `rag/core/colbert_store.py` se necessario, primitive condivise nel già presente `rag/core/writer_lock.py`, relativi test mirati. Non abilitare ancora NPY nei percorsi produttivi di artifacts/indexing/deps. Deliverable indipendentemente testabile e review prima dell'integrazione.

- [ ] Test comportamentali fallenti: array fp16 e Mapping.get/None; header/indice/dtype/dimensione/offset/path corrotti; file immutabili per documento e hardlink/copy fallback; due reader reali crossprocess escludono prune finché l'ultimo chiude.
- [ ] Reader `colbert/index.json` versionato con dtype/dimensione e chunk→file/start/stop; nomi opachi da hash, percorsi non derivati direttamente da doc_id. Aprire memmap read-only, copiare solo chunk, chiudere prima del ritorno. Indice e metadati in RAM, niente dict dell'intero corpus o cache illimitata. Validare confini/file/header senza materializzare tutti i vettori; piena rilettura hash resta check esplicito.
- [ ] Writer a documento: target nuovo, file immutabili, riceve vettori cambiati e padre/rimossi; riuso hardlink stesso filesystem con copia fallback misurata e hash ereditati espliciti. Emissione progressiva del full/grande delta deve essere possibile senza trattenere tutti i vettori; definire API minima concreta per unità B nel report. Nessuna doppia scrittura NPZ/NPY.
- [ ] Lease per versione esterna alla directory eliminabile; reader la possiede fino alla fine del Mapping. Lock OS shared/exclusive nonblocking e rilascio su crash. Provare realmente Windows: non assumere che `msvcrt.LK_NBRLCK` fornisca shared lock; se non lo fa, usare `LockFileEx` stdlib ctypes. Linux flock. Nessun registro solo in-process, contatore persistente di PID o GC globale. Piccoli file lock persistenti, limite dichiarato.
- [ ] Test mirati Windows, report red/green e API nel `phase5a-report.md`; nessun commit, modello o benchmark reale dal worker. PM esegue Linux, review indipendente e commit.

## Unità B — integrazione, migrazione e validazione (dopo A)

Ownership principale `core/artifacts.py`, `core/indexing.py`, consumer/read-only annotations, CLI/route/config solo se necessario; test elencati ADR. Prendere lease prima del load, mantenerla nel Mapping servito, mai chiuderla al rebind se vecchie richieste la conservano. Retention sotto writer lock, exclusive per-versione senza attesa, pinned/error osservabili e retry successivo; solo directory davvero eliminate risultano rimosse.

- [ ] Caricamento legacy NPZ + NPY, nuova scrittura soltanto NPY; manifest elenco index/files, hash streaming dei nuovi file e riuso degli hash verificati del padre. Check profondo distinto rilegge tutti i byte; non dichiarare riverificati gli hash solo ereditati.
- [ ] Full e delta scrivono gruppi limitati e rilasciano output modello progressivamente; metadata/dense/code/grafo restano costi globali espliciti. Non convertire il reader in dict globale. Misurare successivamente picco reale, oltre ai test.
- [ ] Conversione NPZ→nuova candidata NPY, parità/integrità prima di CURRENT; crash lascia attiva vecchia versione, rollback NPZ/NPY conserva risposta. No file condiviso modificato in place. Test corruzione blocca pubblicazione e equivalenza full/delta/modifica/cancellazione.
- [ ] Regressioni Windows/Linux ADR, lifecycle fra processi/server/CLI e retry dopo chiusura; review indipendente prima di misure. F6 ripete stesse celle e aggiunge retention cumulativa/disco fisico; modello reale soltanto PM e mai concorrente a suite pesanti.

Le unità sono la decomposizione operativa della F5 già approvata, non una nuova richiesta di ambito. Se un dettaglio invalida un'invariante, fermare quella modifica e riferire al PM; non indebolire test o parità. Quote: ultima lettura 67% residuo ordinaryAllowed true; ricontrollo prima delle unità e durante lavoro lungo.

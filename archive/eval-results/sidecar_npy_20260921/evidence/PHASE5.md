# F5 — NPY per documento, migrazione e misura full

Codice congelato: `708a142` (reader/writer iniziale `a1cd42a`). Implementazione e test approvati in `rag/adr/sidecar-work/phase5a-review.md` e `phase5b-review.md`; review delle misure in `phase5-measurement-review.md`. La verifica quantitativa del delta e della retention cumulativa prosegue in F6.

## Comportamento

Le nuove versioni conservano ColBERT in NPY fp16 per documento con indice JSON validato. Il reader apre la mappa, copia il solo chunk richiesto e chiude la mappa; la lease della versione resta valida finché il reader è vivo. Il writer persiste ogni documento e riusa file immutabili tramite hard link, oppure copia dichiarata nelle metriche. Il limite della scrittura è il documento più grande più i temporanei dell'encoder, non una memoria costante indipendente dai documenti. Grafo, JSON, vettori dense/code e scan restano globali.

Gli hash dei file ereditati sono riusati solo da un manifest padre attestato. Il controllo profondo esplicito rilegge tutti i byte: il delta ordinario non promette di rilevare bit rot esterno nei file ereditati. Prima di CURRENT sono validati indice, percorsi, header, dimensioni, offset e coerenza delle chiavi. I file non vengono modificati in place. La retention salta versioni con lettori e registra i fallimenti senza dichiarare rimozioni inesistenti; un tentativo successivo può eliminarle dopo la chiusura.

Il percorso full API aveva una chiamata al loader con parametro non supportato che produceva `load_error` e ammetteva comunque il candidato: ora la chiamata è corretta e un candidato illeggibile blocca quel gate. Le altre politiche di errore del gate non sono state ridisegnate.

## Correttezza verificata

- Windows: 405 test passati, nelle suite F5 e retrieval/benchmark.
- Linux: 396 passati, 9 saltati perché il container non include Git; i casi Git sono coperti su Windows. Log `linux-phase5b.txt`.
- Lease reali fra processi e rilascio dopo crash: Windows LockFileEx e POSIX flock, verificati anche con lettori condivisi.
- Migrazione reale dei sette artefatti storici copiati: 257 array, 112.429 token, tutti esattamente uguali; hash profondi e formato NPY verificati; rollback a NPZ e ranking cached invariati. Fonti e 284 file del checkout congelato immutati. Run `sidecar_migration_20260921/evidence`.

La migrazione è esplicita (`index.py --migrate-colbert-npy`) e richiede una versione NPZ attiva. Il delta su NPZ chiede prima questa conversione. Il reader NPZ resta per rollback; nessuna doppia scrittura permanente. La migrazione verificata non contatta la collection operativa il cui nome rimane nei metadati storici.

## Ricostruzione full esplorativa

Una prova reale per variante su CPU4 e modello cached BAAI/bge-m3: 32 documenti derivati da testi storici, riparsati in 64 chunk e 28.659 token. I confini dei documenti sono sintetici. Codice precedente F3 `0f479b2`, successivo F5 `708a142`; corpus identico e configurazione uguale salvo collection dedicata. Metodo: `FULL_MEMORY_METHOD.md`.

| Misura durante build | NPZ precedente | NPY successivo |
| --- | ---: | ---: |
| Tempo | 859,160 s | 487,775 s |
| RSS massimo campionato | 6,436 GiB | 3,152 GiB |
| USS massimo campionato | 5,087 GiB | 1,753 GiB |
| Private massimo campionato | 7,948 GiB | 4,613 GiB |

Tempo −43,23%, RSS −51,02%. I picchi sono limiti inferiori osservati su 4.487/2.865 campioni del PID nel solo intervallo di build. Qdrant e host sono registrati separatamente. Una prova non misura variabilità. Formato e raggruppamento dell'encoding cambiano insieme: non si attribuisce causalmente tutto il guadagno al formato. Modello e calibrazione sono inclusi; gate, promozione e readiness sono esclusi. Nessuna soglia di capacità o incrocio full/delta.

## Differenze numeriche e ricerca

I rebuild non sono uguali byte per byte: 50/64 punti cambiano numericamente. ID/payload/indici sparse/grafo/chunk coincidono. Massimo scostamento assoluto Qdrant dense 2,31e-7, sparse 2,466e-6; ColBERT persistito 6,103515625e-5. Il diverso raggruppamento dei batch è una spiegazione plausibile, non una causa isolata dimostrata. La migrazione di array già persistiti, invece, è esatta.

Il replay ColBERT di una query cached sui 64 chunk e un ID mancante conserva tutti i punteggi arrotondati e il ranking. Una successiva prova reale paired usa una sola codifica per ciascuna delle tre query canoniche F4 e la stessa funzione `hybrid_search` sulle due collection fisiche: candidati dense/sparse nello stesso ordine e risultati finali top-3 interamente uguali per tutte e tre le query. I punteggi grezzi Qdrant differiscono. È parità osservata su queste query, non su ogni possibile query o corpus; non copre l'intera risposta HTTP/LLM.

Dati: `full-comparison.json`, `full-numeric-parity.json`, `full-retrieval-parity.json`; grezzi e provenienza nelle due run `sidecar_fullmemory_{pre,post}_20260921/evidence`. Le due candidate non sono state promosse e le fonti operative non sono state mutate.

## Passo successivo

F6 ripete le 150 prove nelle stesse 30 celle F3, misura byte NPY attribuiti ai file cambiati, query concorrenti e retention/disco fisico deduplicato. Finché queste prove non sono convalidate, U-05 e U-06 restano aperte. I budget prodotto non sono definiti per scelta dell'utente: saranno pubblicate curve per questo hardware, senza dichiarare un limite universale.

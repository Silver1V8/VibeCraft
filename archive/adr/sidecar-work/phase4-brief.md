# Fase 4 — preparazione PM, non ancora delegata

Avviare soltanto dopo F3 verificata e confronto prima/dopo delle stesse celle. ADR F4-01..04, G-03/G-04 e R-04/R-10. Nessun budget prodotto definito: una preferenza tecnica può essere motivata da misure, ma non dichiarare soddisfatti budget inesistenti o capacità universale.

## Esperimento minimo

Confrontare eager NPZ di produzione, NPZ a richiesta e NPY per documento con gli stessi vettori fp16. Solo script della run, nessun secondo backend permanente. Copia storica già verificata: `rag/eval/results/sidecar_20260915/sandbox/historical-artifacts/v20260911T155042`, provenienza in `evidence/historical-artifacts-provenance.json`: 42 documenti, 257 chunk, 112429 token, dimensione1024. Non leggere/scrivere il checkout sorgente. Verificare di nuovo gli hash della copia prima dell'esperimento. La baseline sintetica F2 è troppo piccola per rappresentare il carico del loader storico.

NPY: raggruppamento per doc_id dai chunk, nomi opachi, indice offset, apertura memmap sola lettura/copia del solo chunk/chiusura. Niente cache illimitata. NPZ lazy con lifecycle e accessi concorrenti sicuri, senza riaprire/decomprimere tutto. Tutti i prototipi devono esporre il Mapping già usato dal retrieval; non costruire un framework.

1. Conversione offline dedicata, byte/shape/dtype/array identici. Memoria della conversione separata dal reader. File storici immutati.
2. Processi freschi per reader e ripetizione; baseline dopo import; misura load, prima lettura e ripetizioni calde con candidati identici. Cache OS non controllata: prima lettura non equivale a disco freddo. RSS, USS/privata, I/O di processo, file e mappe aperte con definizioni e null dove indisponibile. Non sommare RSS di processi con pagine condivise.
3. Query esistenti, encode reale una volta e conservare vettori query/candidati per il confronto I/O. Poi retrieval completo su collection Qdrant dedicata o famiglia F3 ripristinata, senza toccare collection operative. Usare scoring/fusione/precedenze canonici, non una formula riscritta. Un replay di candidati è una prova isolata e va etichettato tale, non retrieval completo.
4. Parità esatta di array, score arrotondati e ranking, incluso `rank_sections_by_relevance` per il ramo grafo e chunk assente che resta None. Accessi concorrenti e vecchio snapshot tenuto vivo durante pubblicazione del nuovo. Nessun file condiviso mutabile.
5. Almeno cinque ripetizioni per prima mediana/min/max, non p95 stabile. Conservare raw, metadati codice/ambiente e metodo eseguibile. Una misura loader favorevole non dimostra una riduzione del reindex.

Decisione separata dalle misure: strada più semplice supportata dai dati, costi di decompressione e riscrittura residui espliciti. F5 solo se il confronto giustifica NPY; Qdrant/sharding restano rami ulteriori condizionati, senza assumere budget violati.

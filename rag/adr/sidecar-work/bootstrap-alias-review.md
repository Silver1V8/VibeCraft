# Review indipendente — bootstrap alias Qdrant

**Conformità: APPROVATO. Qualità: APPROVATO** per il fix circoscritto. Review statica del diff e del report; nessun modello, container o benchmark avviato.

Il 409 descritto è coerente con il flusso: il bootstrap incrementale crea la collection fisica `COLLECTION_NAME` e la dichiara nel manifest; senza alias, `reconcile_qdrant_alias` classificava lo stato come `missing` e `repair_qdrant_alias` tentava di creare un alias con lo stesso nome già occupato dalla collection. Il guard in `rag/core/indexing.py:626-627` classifica come allineato solo il caso `expected == base`, nessun alias e collection fisica esistente. Non cambia `_read_alias_target` né `_swap_alias`, quindi il percorso blue/green continua a usare un alias reale.

La protezione sul parent mancante resta: se la collection attesa non esiste, il nuovo guard non scatta; il repair non la inventa e il controllo dell'incrementale in `rag/core/indexing.py:2055-2074` abortisce prima delle point-operation. Il guard corrispondente nel rollback (`rag/core/indexing.py:521-522`) rende no-op soltanto il ritorno alla collection fisica di base già presente; rollback verso collection versionata o assente mantiene la semantica precedente. La migrazione legacy e lo swap blue/green restano fuori dal ramo nuovo.

Il test in `rag/tests/test_incremental_indexing.py:1654-1671` riproduce il layout fisico senza alias e prova osservazione, repair senza scritture e rollback no-op. I test adiacenti coprono alias mancante verso collection versionata, repair divergente e target assente. Il report dichiara 85 test mirati passati; non ho rieseguito la suite mentre il PM esegue la verifica Linux. Il run reale di calibrazione rimane da ripetere dal PM.

**Finding:** nessuno nel perimetro richiesto.

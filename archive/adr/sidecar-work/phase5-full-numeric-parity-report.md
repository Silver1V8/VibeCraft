# F5: parità numerica delle candidate full reali

Confronto in sola lettura delle candidate `sidecar_fullmemory_pre_20260921` e `sidecar_fullmemory_post_20260921`, entrambe complete, usando le rispettive collection Qdrant e versioni di artefatti congelate. Dati per punto/chunk e comando riproducibile sono in [`full-numeric-parity.json`](../../eval-results/sidecar_npy_20260921/evidence/full-numeric-parity.json) e [`full_numeric_parity.py`](../../eval-results/sidecar_npy_20260921/evidence/full_numeric_parity.py). Non è stato richiamato il modello né modificato Qdrant.

| Superficie | Risultato esatto | Differenza massima assoluta |
| --- | ---: | ---: |
| Qdrant ID, ordine di scroll, payload e ordine delle chiavi payload | 64/64 uguali | — |
| Qdrant dense, 1024 componenti per punto | 50/64 punti diversi; 49.623 componenti diverse | 2,31 × 10⁻⁷ |
| Qdrant sparse, indici e ordine | 64/64 uguali | — |
| Qdrant sparse, valori | 50/64 punti diversi; 5.743 valori diversi | 2,466 × 10⁻⁶ |
| `graph.json`, `chunks.json`, `code.json`, `code.npz` | SHA-256 uguali | — |
| `dense.npz`, confrontato per chunk | 50/64 chunk diversi; 329 componenti diverse | 3,0517578125 × 10⁻⁵ |
| ColBERT NPZ precedente vs NPY successivo, per chunk | 50/64 chunk diversi; 368.605 componenti diverse | 6,103515625 × 10⁻⁵ |

Le chiavi dei 64 chunk coincidono in entrambi i sidecar. Il confronto degli array carica un chunk alla volta; non materializza un dizionario di vettori dell'intero corpus. Le differenze dei vettori sono reali e il digest Qdrant differente è quindi atteso. Il `dense.npz` differisce anche come file; il confronto per chiave precisa quali valori sono cambiati. L'encoding per documento ha cambiato il raggruppamento dei batch rispetto all'encoding globale precedente: è una spiegazione plausibile degli scostamenti, coerente con la [misura preliminare dei batch](../../eval-results/sidecar_npy_20260921/evidence/encoding_batch_parity.json), non una prova causale isolata di ogni componente. Nessuna soglia numerica è stata usata per dichiarare uguali vettori diversi.

La query ColBERT effettiva già salvata in F4 (`prenotazione evento posti`) è stata applicata con `rank_sections_by_relevance` ai 64 ID del corpus e a un ID mancante. I 65 punteggi restituiti, inclusa la gestione dell'ID mancante, e l'ordine completo sono identici nei due run; il punteggio di un ID mancante è `None`. Questo è un **replay del solo scoring ColBERT** con query precomputata: non include encoding della query, ricerca Qdrant, espansione del grafo o fusione del retrieval HTTP.

Prima di affermare parità funzionale sul corpus reale, serve una verifica **paired del retrieval completo** sulle due candidate con le stesse query e parametri, usando il percorso F4 già predisposto: registrare candidati Qdrant, punteggi e ranking finali per ogni query. Le misure full attuali dimostrano riduzioni di tempo e picco memoria sul corpus misurato, non una capacità massima del sistema.

Riproduzione dalla directory `rag`, con Qdrant dedicato in ascolto sulla porta 16333:

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONDONTWRITEBYTECODE='1'
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -B eval/results/sidecar_npy_20260921/evidence/full_numeric_parity.py
```

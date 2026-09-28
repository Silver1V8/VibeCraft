# F6: aggregazione delta NPY

`summarize_npy_delta.py` legge esclusivamente i nove `result.json` standard NPY (`docs`, `code`, `mixed` × N=10,30,100). Riusando `compare_delta.load`, richiede `status=completed`, cinque ripetizioni valide e ripristinate per ogni k, job conclusi e token pubblicati coerenti. Rifiuta smoke, fixture sintetiche e matrici incomplete **prima di scrivere output**.

Per ogni cella/k produce mediana, minimo e massimo di T (`snapshot_ready_duration_seconds`), `colbert_io_bytes` (written, hardlinked, copied e conteggio hash ereditati), e counts numerici. Registra anche la mediana di tutte le fasi `phase_timings_seconds`, tra cui scan/hash, model init, parsing/embedding, Qdrant e save/hash. I byte hardlinked/copied rappresentano dimensioni logiche di file; `inherited_hashes_not_reverified` è un conteggio di file. Non vengono confrontati con vecchi contatori di I/O del processo.

Nel no-op senza statistiche del writer, i campi I/O sono `null` con motivo esplicito. Per k>0 anche i contatori richiesti di documenti, codice, chunk e token ColBERT devono esistere ed essere finiti; `code_tokens_processed` può essere `null` soltanto con `code_tokens_unavailable_reason` non vuoto. Nel no-op possono essere `null` solo `chunks_indexed` e `colbert_tokens_indexed` oltre a `code_tokens_processed` motivato. La mancanza di I/O per k>0, i valori parzialmente mancanti, negativi o non finiti causano errore. Il self-check sintetico esercita questi rifiuti, accetta `written_bytes=0` per una prova non no-op ed è passato; non ha letto misure reali né prodotto il report finale.

Quando tutte le nove famiglie sono complete, dalla directory `rag`:

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONDONTWRITEBYTECODE='1'
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -B eval/results/sidecar_npy_20260921/evidence/summarize_npy_delta.py --run
```

Il comando scriverà `npy-delta-summary.json` e `npy-delta-summary.md` in questa directory. Le mediane delle fasi descrivono il lavoro registrato, non costi causali isolati. Corpus sintetico e cache OS non controllata restano limiti della misura.

# Review indipendente — aggregazione F4 e inventario disco F6

**Verdetto: F4 aggregatore APPROVATO; F6 inventario APPROVATO dopo il fix del fallback API.** Review statica, senza avviare modello, Qdrant o benchmark. Ho letto in sola lettura il fixture già presente dell'inventario: due hard link da 10.001 byte danno 20.002 byte logici e 12.288 byte allocati deduplicati, senza errore.

## F4 `summarize_readers.py`

La utility richiama `reader_experiment.compare_outputs()` prima di riassumere: parità esatta di score/ranking per tutti i reader e le ripetizioni. Richiede sampler con exit 0, completion `completed` e nessun errore; controlla 15 PID distinti e almeno un campione per ciascun worker. Distingue baseline dopo import per il replay I/O e dopo modello/validazione per il full; calcola differenze endpoint di memoria, contatori I/O, file e mappe. `None` resta `null` quando manca una misura. I picchi campionati sono per processo intero e non vengono sommati fra processi. Il file `summary.csv` mantiene `first_median_s`/`warm_median_s` null per full, dove le tre query diverse non sono letture calde ripetute.

**Limite da rendere visibile nel report F4:** i record Qdrant/cgroup eventualmente presenti in `*-process.jsonl` non vengono aggregati in `resources.json`; la frase nei `limits` indica che il sampler copre Qdrant, ma il riepilogo prodotto qui riguarda solo i worker. Per qualsiasi numero Qdrant usare il raw o un riepilogo separato, senza attribuirlo alla memoria del reader. Inoltre `compare_outputs()` scrive `comparison.json` prima della validazione sampler: se questa fallisce, il file di parità può restare presente senza un riepilogo risorse valido. Il PM deve considerare l'esito della utility e i metadati sampler, non la sola presenza del file.

## F6 `disk_inventory.py`

La guardia limita l'inventario a `rag/eval/results/<run>/sandbox/...`; `resolve` rifiuta uscite dal perimetro e i symlink figli vengono rifiutati. Linux usa `st_blocks*512`; Windows usa `FILE_STANDARD_INFO.AllocationSize` su handle aperto in sola lettura, evitando il valore logico di `GetCompressedFileSizeW`. Le dimensioni logiche contano ogni voce, quelle allocate deduplicano per device/inode; un errore di allocazione produce totale fisico `null`, non zero. Questo totale è **allocazione dei dati dei file censiti**, non variazione dell'occupazione del volume: non include necessariamente metadati filesystem o directory.

**Chiusura finding, `rag/eval/results/sidecar_retention_20260921/evidence/disk_inventory.py:28-53`:** `allocated()` ora cattura `OSError` e `AttributeError` da apertura/API e restituisce `(None, motivo)`. Verifica leggera con apertura che solleva `OSError`: risultato `(None, "allocation unavailable: OSError: injected")`. Il totale fisico resta `null` in caso di misura indisponibile. Nessun benchmark o modello ripetuto.

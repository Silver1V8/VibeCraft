# F6 — preflight retention e disco fisico

**Stato:** sola lettura. Nessun modello, container, benchmark o modifica produttiva avviata. Questo documento non sceglie NPZ/NPY né apre F5.

## Flusso oggi

- `core.artifacts.save_artifacts()` crea una directory nuova `database/versions/v.../` e scrive `graph.json`, `colbert.npz`, `dense.npz`, `code.npz`, `chunks.json`, `code.json`; non riusa file né crea hard link. Le scritture passano da `_atomic_write()` (`os.replace` nello stesso mount).
- `core.artifacts.promote_version()` aggiorna atomicamente `database/CURRENT`, poi chiama `prune_versions()`. `_keep_from_env()` legge `VIBECRAFT_INDEX_KEEP` (default 5, minimo 1). `prune_versions()` esclude CURRENT ma usa oggi `shutil.rmtree(..., ignore_errors=True)` e registra comunque la rimozione: su Windows una mappa/letta aperta può quindi apparire rimossa pur restando su disco.
- `core.artifacts.list_versions()`, `current_version()`, `resolve_rollback_target()` e `rollback_version()` sono la vista locale; `api.routes_reindex.index_versions` la espone. `api.deps.maybe_reload_graph()` osserva CURRENT e sostituisce lo snapshot; una richiesta che trattiene il vecchio snapshot può finirlo.
- Un full in `core.indexing.build_graph_and_index()` crea una collection Qdrant candidata, salva la versione, promuove CURRENT, poi `_swap_alias()` e `gc_orphaned_qdrant_collections()`. Un incrementale (`incremental_index()`) eredita e muta la collection del padre; `rollback_shares_collection_with_later_versions()` segnala il caso in cui il rollback locale non riavvolge Qdrant. La retention locale non misura né libera automaticamente questa condivisione.

## Cosa misurare

Per ogni checkpoint (baseline, dopo ogni versione, dopo retention) conservare una riga per file con percorso relativo, `size` logica, file-id/inode, link count, byte allocati e hash. Sommare due colonne: **logica** (tutti i `size`) e **fisica deduplicata** (un solo file-id/inode). Il secondo numero è quello da confrontare fra retention e candidati con hard link; non deduplicare file con hash uguale ma inode diverso.

| Host | Logico | Fisico e identità |
|---|---|---|
| Linux | `du -sb --apparent-size database/versions` | `du -sB1 database/versions`; per riga `stat -c '%d:%i %h %s %b %n'` (`%b` blocchi da 512 B). `du` su una sola radice deduplica gli hard link; salvare anche inode/link-count. |
| Windows | `Get-ChildItem database/versions -Recurse -File | Measure-Object Length -Sum` | Uno script stdlib apre ogni file in sola lettura e chiama `GetFileInformationByHandleEx(FileStandardInfo).AllocationSize` via `ctypes`; registra anche `os.stat().st_dev/st_ino` per deduplicare hard link. Se la chiamata/API non è disponibile, registra `physical_allocated_bytes=null` e l’errore, senza stimare da Length. |

I blocchi/AllocationSize mostrano allocazione, non traffico I/O. `GetCompressedFileSizeW` non è il metodo del run: per file non compressi/non sparse restituisce la dimensione logica. `fsutil` può richiedere privilegi, localizza l’output e le extent non dimostrano la compressione. Lo spazio libero del volume prima/dopo è solo un controllo grossolano, contaminato da altri processi. Le directory Qdrant devono essere inventariate separatamente: la somma dei sidecar non le include. Riferimenti: [GetCompressedFileSizeW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getcompressedfilesizew), [FILE_STANDARD_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_standard_info).

## Esperimento minimo proposto (da eseguire dal PM)

1. Creare un checkout e un database sotto `rag/eval/results/<run>/sandbox/experiment`, porte e collection dedicate; fissare `VIBECRAFT_INDEX_KEEP=3`. Fotografare CURRENT, `list_versions`, manifest (`qdrant_collection`), hash `artifact_hashes(version)`, digest paginato Qdrant e inventario disco iniziale.
2. Aggiungere **solo nella directory evidence della run** un driver F6 nuovo: riusa helper/server/query del driver F2, ma esegue quattro o più veri delta k=1 consecutivi senza restore tra job e conserva il database sandbox fino all’inventario finale. `bench_delta.py` non è adatto: ripristina la baseline dopo ogni prova, e k=0 non crea una versione.
3. Dopo ogni promote e dopo il quarto delta, registrare CURRENT/versioni, manifest→collection, risposta del reader, inventario logico/fisico locale e inventario Qdrant. Verificare che la versione attiva e quella letta dal reader restino caricabili; tentare il rollback solo verso una versione ancora presente e verificare la nota di collection condivisa quando applicabile.
4. Lasciare agire `prune_versions`; su Windows ripetere con un reader che mantiene il vecchio snapshot fino al confine della richiesta. Il risultato deve distinguere directory rimossa, errore di rimozione e directory ancora presente: il comportamento attuale `ignore_errors=True` è un limite da osservare, non una rimozione dimostrata.

Non confrontare questo run con NPZ/NPY: oggi tutte le versioni sono file NPZ/JSON nuovi, quindi hard link attesi = zero. In un ramo NPY futuro, hard link è valido solo sullo stesso filesystem e solo per file immutabili; inode/link-count e byte fisici deduplicati devono allora accompagnare la misura. NPZ lazy può ridurre materializzazione in lettura ma conserva l’archivio compresso per versione e non dimostra granularità di scrittura. NPY per documento può ridurre byte riscritti solo se la parità F4 e i vincoli di snapshot/retention saranno misurati prima.

## Limiti

Cache OS, compressione, sparse files, antivirus e altri processi rendono i byte allocati host-specifici. Il reader concorrente prova lifecycle e visibilità della versione, non una soglia di capacità. Cinque ripetizioni danno mediana/min/max, non p95 stabile. Nessun budget prodotto è definito: pubblicare curve e intervalli osservati, non un limite universale o una decisione di sharding.

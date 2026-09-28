# Review indipendente F5B — integrazione NPY

**Verdetti finali: conformità APPROVATO; qualità APPROVATO per F5B.** Diff rispetto ad `a1cd42a` e test finali Windows/Linux verificati; nessun modello o benchmark avviato da questa review. Il beneficio quantitativo NPY rispetto alla baseline full pre resta da misurare nella run post F5/F6.

## Chiusura finding statici

1. `promote_version()` ora richiede `index_manifest.json` per la candidata NPY prima di CURRENT e conserva la verifica di hash/index/file nuovi. Il test aggiunto rifiuta la candidata NPY senza manifest; il vecchio NPZ rimane compatibile.
2. `load_artifacts(version=None)` ora esegue al massimo tre tentativi: se una `BlockingIOError`/`FileNotFoundError` segue una variazione di CURRENT, rilegge la versione e riprova; per `version=` esplicita fallisce subito. Il test simula la corsa fra selezione e lease. Nessuna attesa mentre si detiene writer lock.

3. Il percorso full API passava un `emit` inesistente a `load_artifacts()`, quindi il gate saltava sistematicamente la valutazione per `load_error`; ora usa la firma reale, chiude il reader candidato nel `finally` e blocca la promozione se il candidato non è caricabile. `promote_version()` carica grafo, ColBERT, chunks, dense e code e confronta le chiavi ColBERT/chunks prima di CURRENT. I test aggiunti simulano metadata malformati con hash coerenti e load_error della route. Verifica statica positiva, confermata dalla suite finale.
4. Il restore del bench F2/F6 ora acquisisce exclusive lease per ogni versione prima di mutare sorgenti/database, preservando `.reader-locks`; un reader esterno blocca il restore invece di vedere sparire la directory. Test aggiunto e incluso nella suite finale.

## Contratti osservati staticamente

- **Writer/read-on-demand:** full usa writer per documento e sink Qdrant per documento; il delta passa changed/removed e parent, non trasforma il reader NPY in dict globale. File nuovi sono NPY immutabili; il writer riusa gli invariati con hard link/copia tracciata. Metadati chunk/dense/grafo restano globali e quindi il codice non promette memoria totale O(k). Il report `colbert_io_bytes` distingue written/hardlinked/copied.
- **Hash e pubblicazione:** manifest contiene hash index/NPY; il controllo ordinario eredita digest dei file del padre, mentre `artifact_hashes(deep=True)` rilegge byte nel check esplicito e nella migrazione. Il delta confronta index e tabella digest del padre col manifest prima del riuso. `promote_version` ricontrolla i file elencati come nuovi; il varco osservato nella candidata NPY senza manifest è chiuso.
- **Lifecycle:** `load_artifacts` acquisisce lease prima dei file; il `ColbertStore` mantiene la propria lease nello snapshot. Il prune prova exclusive non bloccante e registra solo directory realmente rimosse; il bench restore conserva identità e file `.reader-locks`. Il server libera il riferimento al shutdown. Test aggiunti coprono parent pinnato, retry dopo errore cancellazione e restore del file lock.
- **Migrazione/rollback:** conversione NPZ→candidata NPY rilegge sorgente/byte, confronta array fp16 prima di CURRENT, preserva collection Qdrant e lettura NPZ per rollback. Le prove aggiunte coprono parità di rank/missing dopo la conversione, fonte corrotta e fallimento publish che lascia CURRENT invariato. Le regressioni full/delta, rollback e lease cross-process passano nelle suite; i costi reali, retention cumulativa e capacità restano da misurare in F6.

**Verifica finale:** il report del worker registra exit 0 per i 15 file Windows F5B e per retrieval/bench aggiuntivi. Il raw Linux `sidecar_npy_20260921/evidence/linux-phase5b.txt` registra `396 passed, 9 skipped in 51.17s` ed `EXIT_CODE=0` sui 17 file; il PM attribuisce gli skip a Git assente nel container, con copertura Windows. Ruff/diff finale del PM resta controllo separato. Nessun claim di budget o riduzione memoria reale deriva dal solo diff.

## Documentazione

La sezione artefatti/retention del README ora descrive NPY per documento, necessità della migrazione esplicita prima dei delta su NPZ versionato, check profondo distinto dagli hash ereditati, lease persistenti e retry del prune. I limiti di memoria per documento e costi globali sono dichiarati senza promettere capacità o reindex già misurati. Coerente col contratto F5 osservato.

# F4 — prototipi reader pronti alla review (21 settembre 2026)

## Perimetro

Il solo script sperimentale è `rag/eval/results/sidecar_readers_20260921/evidence/reader_experiment.py`. Nessun modulo di produzione, baseline F3, collection Qdrant o copia storica è stato modificato. Non ho avviato modello, container o benchmark reale: i comandi sotto sono per il PM **dopo** review indipendente.

La sorgente I/O è la copia storica `sidecar_20260915/sandbox/historical-artifacts/v20260911T155042` (42 documenti, 257 chunk, 112429 token, vettori fp16 dimensione 1024); `verify` ricontrolla SHA-256 e byte contro la provenienza. `convert` legge il NPZ per documento, concatena solo le sezioni di quel documento in un NPY opaco, registra offset per chunk e scrive esclusivamente nella nuova sandbox. La conversione è esterna agli intervalli del reader.

I tre reader sono `Mapping`: eager chiama direttamente `_load_vectors` di produzione (importato prima della baseline), lazy tiene aperto un NPZ e serializza `__getitem__` con un lock, NPY apre una memmap `r`, copia il solo intervallo richiesto e chiude la mappa. Non hanno cache illimitata. L'esperimento sulla pubblicazione costruisce una generazione nuova con un valore **diverso** e sposta un puntatore temporaneo mentre il vecchio reader restituisce ancora il valore originale; è una simulazione isolata del contratto di snapshot, non una modifica a `CURRENT` di produzione.

## Contratti misurati

`io-batch` genera 15 processi freschi: 3 reader × 5 ripetizioni, con lo stesso vettore della prima query reale (`prenotazione evento posti`) e gli stessi 32 candidati storici più un ID mancante. È un **replay isolato di I/O**, non una ricerca completa. Ogni worker registra baseline dopo import, load, prima lettura, cinque letture calde, RSS, USS/privata ove disponibili, contatori I/O di processo, file aperti e mappe. Le letture calde riusano gli stessi candidati; la cache OS non è controllata, dunque “prima” non significa disco freddo. RSS di processi diversi non va sommata.

`full-batch` genera 15 altri processi freschi. Prima di ogni misura verifica il `CURRENT` e tutti gli hash della baseline F3 mixed N100 contro `evidence/result.json` e il manifest; confronta anche il digest paginato dei punti Qdrant con quel record e con `pm-preflight.json`, fallendo su qualsiasi divergenza. Carica il modello CPU/offline con quattro thread **prima della baseline di memoria del reader**, usa le tre query esistenti F2/F3, codifica ogni query realmente, interroga la collection dedicata `sidecar_0628_mixed_n100_post` a `127.0.0.1:16333` e chiama `core.retrieval.hybrid_search` e `rank_sections_by_relevance` canonici. I tempi encode, load e retrieval sono campi separati. Non c'è API a pagamento o generazione LLM. `compare` richiede parità esatta dei risultati/scoring/ranking di tutti i reader e ripetizioni, incluso il ramo grafo e l'ID assente con `None`; scrive median/min/max del load, della prima lettura e del retrieval, più i raw per processo. Un guadagno di load **non** dimostra un guadagno di reindex.

## Comandi per PM, dalla directory `rag`

Usare il Python sorgente in sola lettura: `C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -B`. Impostare `PYTHONUTF8=1`, `PYTHONDONTWRITEBYTECODE=1`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `OMP_NUM_THREADS=4`, `MKL_NUM_THREADS=4` e `TOKENIZERS_PARALLELISM=false`. Lo script è `eval/results/sidecar_readers_20260921/evidence/reader_experiment.py`.

In ordine, dopo review: `verify`, `convert`, `convert-f3`, `parity-history`, `prepare-candidates`, `io-batch`, `full-batch`, `compare`. `full-batch` richiede collection F3 dedicata disponibile e Qdrant già avviato dal PM. Se collection/artefatti non corrispondono, fermarsi senza ripuntare alias o ripristinare nella collection operativa. Conservare `comparison.json`, `io-*.json`, `full-*.json`, i file di conversione e le informazioni ambiente/commit nel report finale.

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONDONTWRITEBYTECODE='1'
$env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'
$env:OMP_NUM_THREADS='4'; $env:MKL_NUM_THREADS='4'; $env:TOKENIZERS_PARALLELISM='false'
$env:PYTHONHASHSEED='0'
$py='C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe'
$driver='eval/results/sidecar_readers_20260921/evidence/reader_experiment.py'
& $py -B $driver verify
& $py -B $driver convert
& $py -B $driver convert-f3
& $py -B $driver parity-history
& $py -B $driver prepare-candidates
& $py -B $driver io-batch
& $py -B $driver full-batch
& $py -B $driver compare
```

## Verifica finora

Self-check sintetico eseguito sul Python sorgente con `-B`: array fp16 identici, `rank_sections_by_relevance` identico con chunk mancante `None`, 6 accessi concorrenti coerenti **per ciascuno** dei tre reader. Vecchia generazione invariata e nuova generazione modificata sono state verificate prima/dopo il puntatore simulato. `validate_f3_disk()` ha verificato in sola lettura il token `CURRENT` e gli hash F3 (exit 0); il digest Qdrant sarà verificato solo dal PM durante il run reale. Questa prova usa due piccoli array artificiali: non va presentata come misura reale. Le misure `_metrics` sono snapshot e non catturano picchi transienti: il sampler esterno PM può osservarne solo un limite inferiore. Nel full, le tre query girano una volta per processo; cinque processi danno cinque repliche, non cinque letture calde della stessa query. La decisione F4-04 resta aperta finché review e curve reali non sono disponibili; non esiste un budget prodotto definito.

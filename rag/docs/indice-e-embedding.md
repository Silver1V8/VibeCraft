Italiano | [English](../README.en.md)

> Documentazione operativa sotto `rag/docs/`: **non** è corpus RAG (il corpus è `docs/` del progetto). Stesso schema degli ADR. Italiano canonico; l'inglese resta un indice breve in `rag/README.en.md`.

[← Indice operativo](../README.md)

# Artefatti dell'indice ed embedding

## Artefatti dell'indice: formati sicuri, ispezionabili e versionati (blue/green)

L'indice persiste in `<root-progetto>/database/` (iniziale: `projects/legacy/database/`)
tramite [core/artifacts.py](../core/artifacts.py)
e il reader/writer per documento [core/colbert_store.py](../core/colbert_store.py).
I formati sono sicuri (nessun `pickle`, che è fragile tra versioni
e un vettore d'attacco se qualcuno scrive in `database/`) e ispezionabili:

| Artefatto | File | Formato |
|-----------|------|---------|
| Grafo NetworkX | `graph.json` | node-link JSON (`nx.node_link_data`), attributi normalizzati JSON-safe |
| Multivettori ColBERT | `colbert/index.json` + `colbert/d-<hash>.npy` | NPY fp16 per documento, indice con file e offset per `chunk_id`; lettura del solo chunk richiesto |
| Vettori densi dei chunk | `dense.npz` | `np.savez_compressed`, fp16, chiave = `chunk_id` |
| Vettori densi dei simboli | `code.npz` | `np.savez_compressed`, fp16, chiave = `symbol_id` |
| Sidecar testuale dei chunk | `chunks.json` | `chunk_id → {doc_id, section, text}` |
| Sidecar testuale del codice | `code.json` | `symbol_id → {name, kind, file, dev_type, text, deps, refs, links}` |

Gli attributi dei nodi-documento vengono dal frontmatter YAML e possono contenere
tipi non-JSON (date, `Path`): `_json_safe` li normalizza (una data → la sua ISO
string) così `graph.json` è sempre serializzabile. I vettori restano **fp16
bit-identici** al round-trip. Ogni scrittura è **atomica** (`_atomic_write`): un
crash a metà non lascia file troncati.

Le nuove build scrivono solo il formato ColBERT NPY. I delta riusano i file dei
documenti invariati tramite hard link, con copia come fallback; i file riusati non
vengono modificati. Full e delta persistono un documento alla volta: il limite dei
vettori temporanei dipende ancora dal documento più grande e dal batch del modello.
Grafo, metadati, dense e codice conservano costi globali.

Le versioni precedenti in `colbert.npz` restano leggibili, anche per il rollback.
Prima di un nuovo delta su un indice NPZ esistente, convertire la versione
**già versionata** attiva, senza nuovo embedding:

```bash
python index.py --check-integrity
python index.py --migrate-colbert-npy
python index.py --check-integrity
```

La conversione crea una candidata separata, verifica array e hash e solo dopo
sposta CURRENT; conserva la collection Qdrant esistente. Un errore prima della
promozione lascia attiva la versione precedente. Non verifica né ripara i punti
Qdrant: se l'integrità segnala un disallineamento, confrontare gli ID e i relativi
payload con `chunks.json`, senza eliminare punti solo per far coincidere i conteggi.
La divergenza di un documento locale da Git è un avviso separato: un reindex usa
la copia su disco e non decide quale versione del documento sia autoritativa.
Il controllo integrità esplicito
rilegge tutti i byte. Il delta legacy verifica indice e file nuovi, ma eredita
gli hash attestati dei file immutati: non equivale a riverificare quei byte e non
rileva una loro successiva alterazione esterna senza il controllo profondo.

### Versionamento blue/green: swap atomico, rollback istantaneo

Ogni build scrive gli artefatti in una **directory di versione nuova**
(`database/versions/v<timestamp UTC>/`, es. `v20260714T153045/`) contenente
grafo, vettori, sidecar **e il manifest di quella build** (`index_manifest.json`:
hash SHA-256 dei sorgenti e dei file artefatto — ogni versione è autodescritta,
così dopo un rollback anche staleness e integrità si misurano contro la versione
attiva). Il file di testo `database/CURRENT` è il **puntatore alla versione
attiva**: la lettura (`load_artifacts`) lo segue sempre, e la sua scrittura è
atomica (`_atomic_write`), quindi lo swap è istantaneo e mai a metà.

Build e promozione sono **due passi espliciti**: `save_artifacts()` restituisce
il nome della nuova versione (senza toccare CURRENT), `promote_version(nome)`
sposta il puntatore. Gli **incrementali legacy** promuovono a fine build riuscita, senza
passare dal gate (finché M6 non decide diversamente). I **full** — sia la CLI
(`python index.py`) sia i job del ReindexManager — prima di promuovere eseguono
l'**eval-gate del golden-set sulla nuova versione** (in process, config
`rag_config.yaml` → `eval_gate.*`: `enabled`, `k` (oggi 2), `min_recall` — 0.90 se
assente, oggi 0.75 in config —, `blocking`):
sotto soglia (e gate bloccante) la versione resta su disco **non promossa**, il job
termina `completed_not_promoted` col report nell'esito e il server continua a
servire la versione precedente. Se il gate è disattivo, il golden-set manca o
dichiara `cases: []`, il bootstrap è consentito e il report indica che il gate
non è stato valutato. Un golden-set presente ma invalido o un errore durante
la valutazione blocca la promozione quando `blocking: true`; in modalità advisory
la consente con un avviso esplicito. Un file YAML vuoto non è una baseline vuota valida.
Una candidata che non può essere caricata correttamente blocca invece la
promozione; le candidate NPY devono superare anche i controlli di completezza e
coerenza degli artefatti prima dello spostamento di CURRENT.

Il gate misura anche la **saturazione** della propria metrica e, se `recall@k`
vale 1.000 su tutti i casi, scrive un alert `warning`: a quel k non è un gate
severo, è un gate cieco — lo supera qualunque candidata, anche una peggiorata.
Non blocca (non è una regressione), ma va letto come "abbassare `eval_gate.k` a un
k che discrimina". Non è teorico: sul golden-set di 49 casi, misurato a luglio
sul corpus di allora (11 documenti), il recall@10 era saturo a 1.000 su tutta la
griglia di calibrazione. Oggi (30 ottobre 2026) è 0.983 e discrimina, per due ragioni che vale la
pena tenere distinte: il corpus è cresciuto a 50 documenti (e un caso classico non
arriva più in top-10, vedi sotto) e i casi avversariali abbassano il recall@1. Il server rileva ogni
spostamento di CURRENT (`maybe_reload_graph`) e ricarica lo snapshot alla prima
richiesta.

**Rollback istantaneo** — sposta solo il puntatore, nessuna build:

```bash
python index.py --rollback              # torna alla versione precedente
python index.py --rollback v20260713T031500   # o a una versione specifica
```

Equivalente HTTP: `POST /api/index/rollback` (corpo opzionale
`{"version": "v..."}`) ricarica anche lo snapshot in memoria;
`GET /api/index/versions` elenca le versioni disponibili e quella attiva.

**Retention**: dopo ogni promozione restano le ultime N versioni (default 5, env
`VIBECRAFT_INDEX_KEEP`); la versione puntata da CURRENT non viene **mai** eliminata,
anche se più vecchia delle N conservate (caso post-rollback).
Le versioni ancora usate da lettori, anche in altri processi, vengono conservate
tramite lease OS. Il prune ritenta alla chiamata successiva; registra una rimozione
solo se riuscita e segnala gli errori. I piccoli file in `database/.reader-locks/`
persistono deliberatamente e non vanno cancellati mentre il sistema è in uso.

### Blue/green Qdrant (collection versionate + alias)

Ogni full rebuild scrive su una collection Qdrant *candidata* e versionata
(`{collection_name}__{version}`), valuta l'eval-gate su quella stessa candidata, e
solo a gate passato promuove CURRENT e sposta un **alias** Qdrant (il nome
del progetto: `vibecraft_<id>`, oppure `vector_database.collection_name` nel
legacy; retrieval usa la collection fisica del manifest dello snapshot catturato) sulla candidata — la collection di produzione
non viene mai toccata durante il build, solo alla promozione. Se il gate blocca la
promozione, la collection candidata resta su Qdrant non referenziata da alcuna
versione attiva: il GC del prossimo job writer riuscito la rimuove (nessuna
collezione orfana si accumula).

**Migrazione one-shot legacy→alias.** Se la collection di produzione esiste ancora
come collection *fisica* (un'installazione mai passata da questo meccanismo —
Qdrant non ammette un alias con lo stesso nome di una collection esistente), alla
prima promozione viene **cancellata e ricreata come alias** verso la candidata. È
l'**unica operazione irreversibile** del meccanismo: una finestra di
indisponibilità breve ma reale (millisecondi) fra il delete e la create, loggata
esplicitamente. Da quel momento il nome di produzione non è più una collection
fisica: è sempre un alias verso l'ultima versione promossa. Un crash esattamente
in quella finestra lascia l'alias mancante: il reconciler lo ripara alla manutenzione writer successiva (o al prossimo job full) se la collection candidata esiste ancora,
senza bisogno di un nuovo rebuild.

**Rollback**: `python index.py --rollback [VERSIONE]` (o `POST /api/index/rollback`)
sposta CURRENT **e** riallinea l'alias Qdrant alla collection dichiarata nel
manifest della versione target — cross-lineage esegue lo swap, intra-lineage (alias
già corretto) è un no-op. Se la collection della versione target non esiste più su
Qdrant (es. rimossa dal GC perché la lineage era già stata ruotata), il rollback è
**rifiutato PRIMA di qualunque mutazione**: CURRENT non si muove, l'alias nemmeno, e
il messaggio nomina la collection mancante e prescrive una re-indicizzazione completa
(CLI: exit 1; route: **409**). Prima CURRENT si spostava lo stesso e restava uno stato
misto — sidecar della versione target, vettori di un'altra build — che nessun
reconciler ripara e che il check di integrità dichiarava `ok: true` (vedi `AUDIT.md`,
A20). Se Qdrant è irraggiungibile il pre-check si **salta**: un rollback locale non
dipende dalla raggiungibilità di Qdrant, e l'alias viene riparato alla successiva manutenzione writer.
Lo stato `"qdrant_alias": {"state": "missing_target_collection"}` nella risposta resta
possibile solo se la collection sparisce fra il pre-check e lo swap, o se il pre-check
è stato saltato — nessuna collection viene mai "inventata".

**Riconciliazione e GC.** Avvio e lettura non riparano alias e non eseguono GC.
La manutenzione è esplicita nel lifecycle writer/CLI sotto writer lock, con namespace
del progetto. Nessuna riparazione inventa collection mancanti.
`GET /api/index/integrity` espone la classificazione READ-ONLY `qdrant_alias`:
`legacy`/`aligned`/`missing`/`diverging`/`unknown`.

### Retrocompatibilità e formati legacy

`save_artifacts()` scrive **solo** i formati correnti, sempre in una directory di
versione nuova (mai riscritta). In lettura, se `CURRENT` non esiste ma in
`database/` ci sono i file flat storici (JSON/`.npz`), `load_artifacts()` li carica
come versione `legacy`; la prima build successiva crea la struttura versionata e la
promozione fa vincere CURRENT sul layout flat. Il fallback ai vecchi pickle `*.pkl`
è stato **rimosso** (A13, `../archive/adr/AUDIT.md`): nessuna installazione ne scrive più
dal passaggio ai formati JSON/NumPy (oggi NPY per ColBERT e NPZ per dense/code).
Mantenere `pickle.load` su un
formato che nessuno produce più era superficie di deserializzazione arbitraria
senza alcun beneficio.


## Embedding (bge-m3): CPU per le query, acceleratore per il reindex

- **Server e `/ask`** (`api/deps.py`, `state["embed_model"]`, usato anche da
  `/api/graph/query`): `BGEM3FlagModel` su `devices="cpu"`. Una singola query costa ms
  anche su CPU, e lasciare la GPU libera evita che Ollama carichi `qwen3.5:9b` in
  split GPU/CPU (molto più lento — vedi sezione LLM sopra). Lo stesso modello CPU è il
  ripiego dei job di reindex (`_reindex_embed_model()` in `api/routes_reindex.py`).
- **Job di reindex** (`core/job_embedder.py`, scelta in `core/accelerator.py`): al
  primo embedding del job, `VIBECRAFT_REINDEX_DEVICE=auto` prova i backend che PyTorch
  esegue davvero, in quest'ordine.
  1. **CUDA**, se `torch.cuda` è disponibile e la memoria basta. Vale per le RTX
     discrete, per i chip NVIDIA a memoria unificata (DGX Spark, RTX Spark, GB10,
     Grace) e per una GPU AMD sulla build ROCm di PyTorch: ROCm si presenta come
     CUDA, la sonda è `rocm-smi` e non un backend nuovo. Si sceglie la GPU con più
     memoria libera. Su una scheda discreta servono almeno
     `VIBECRAFT_REINDEX_GPU_MIN_FREE_MB` liberi; su un chip unificato NVIDIA la
     soglia si applica al totale del pool, purché resti almeno 1 GiB non mappato.
     Se la VRAM non basta perché Ollama tiene caricato l'LLM (con
     `OLLAMA_KEEP_ALIVE=-1` succede sempre), il **full rebuild** chiede prima a Ollama
     di scaricarlo (`keep_alive: 0`, `core.llm.unload_ollama_models`) e ripete la scelta
     per qualche secondo; il modello si ricarica alla generazione successiva. I delta e
     l'import di progetti non lo fanno: per pochi chunk la CPU basta. Misurato il
     29 ottobre 2026: full su CUDA in 104-121 s, contro oltre 30 minuti su CPU.
  2. **Metal (`mps`)** su Apple Silicon, da M1 a M6, base, Pro, Max e Ultra, se
     CUDA non c'è o la scheda NVIDIA non ha memoria libera. Il nome arriva da
     `machdep.cpu.brand_string`, la RAM installata da `hw.memsize` (non il massimo
     di listino: un M5 Max da 36 GB non è trattato come uno da 128). La sonda per
     salire su Metal resta `vm_stat`. Sotto i 24 GB installati — un M1 da 8 GB, un
     Pro da 16, un M6 da 16 — embedding e `qwen3.5:9b` non hanno margine nel pool
     unico: il reindex prende Metal solo per il job, con un tetto sull'allocatore
     (`PYTORCH_MPS_HIGH_WATERMARK_RATIO` sotto 1; il default di PyTorch è 1,7 e
     macOS uccide il processo) e un batch più piccolo (4 o 8). Da 24 GB in su i
     pesi interi dell'embedding stanno su Metal (`embedding_placement=gpu`) e il
     batch segue la classe: 12 sul base, 24 sul Pro, 32 sul Max, 48 sull'Ultra.
     I pesi restano fp32, gli stessi dell'indice su CPU. Il figlio parte con
     `PYTORCH_ENABLE_MPS_FALLBACK=1`. A ottobre 2026 l'M6 in commercio è il chip
     base; Pro, Max e Ultra di quella generazione non sono un prodotto, ma un nome
     che li contiene si classifica lo stesso.
  3. **GPU OpenVINO** (Arc, Xe, iGPU Intel). Una GPU AMD ci finisce solo se
     OpenVINO la elenca: senza ROCm e senza OpenVINO non viene eseguita.
     Ci gira l'encoder; le teste sparse e ColBERT restano sulla CPU del figlio.
     Non è una dipendenza di `uv sync`.
  4. **NPU**, se accanto al progetto c'è un runtime che compila davvero
     l'encoder: OpenVINO per Intel, `QNNExecutionProvider` per Qualcomm Hexagon,
     `VitisAIExecutionProvider` per AMD Ryzen AI, `CoreMLExecutionProvider` per
     l'Apple Neural Engine. Le teste restano sulla CPU del figlio. Su Apple
     Metal viene prima: il Neural Engine condivide la stessa memoria e non
     prende il posto di Metal. Neanche questo runtime è in `uv sync`.
  5. **CPU**. All'avvio del modello condiviso torch usa `cpu_threads()`: su Apple
     i core performanti meno uno, altrove i core logici meno uno, al massimo 8.

  Dove finiscono i pesi. bge-m3 fp32 sta intorno ai 2,2 GB; `qwen3.5:9b` in
  Ollama non ci sta insieme su 8 GB (è la misura di questo progetto, non una
  targa). Se la GPU scelta ha almeno quella somma più un giunto di 1 GB, il
  reindex ci mette l'intero modello (`embedding_placement=gpu`) e l'LLM usa la
  stessa scheda a turno. Su Apple la soglia non è quel giunto: sotto i 24 GB
  installati il sistema occupa lo stesso pool, quindi si resta in `split` anche
  quando Metal accetta il job. Altrimenti si divide: l'LLM tiene la scheda
  grossa, il reindex va sull'altro acceleratore o ci sale solo finché trova
  memoria libera, e le teste piccole restano sulla CPU del figlio.
  `/ask` resta sulla CPU del server in ogni caso: la generazione dello stesso
  turno usa la GPU subito dopo, e un contesto CUDA residente la manderebbe in
  split. Una sonda `nvidia-smi`/`rocm-smi` muta non viene mascherata con un
  altro acceleratore; la VRAM occupata dall'LLM sì, perché è proprio il caso in
  cui il lavoro va diviso.

  `cuda`, `mps`, `intel` e `npu` forzano quel backend; `cpu` li esclude. Il
  modello gira in `python -m core.gpu_worker --device cuda:N`, `mps`, `ov:GPU`
  oppure `npu`, fermato a fine job. Il processo del server non crea un contesto
  CUDA o Metal e non compila un modello. L'avvio costa ~10 s per job; la prima
  compilazione OpenVINO costa di più (cache in `~/.cache/vibecraft/npu` o
  `VIBECRAFT_NPU_CACHE`). Se il processo esaurisce la memoria o muore, il resto
  del job usa la CPU. Su CPU un `full` rebuild passa da minuti a **decine di
  ore** (misurato: ~10s/embedding CPU contro ~6-10 it/s GPU). Lo stderr del
  processo finisce nel log del server col prefisso `[gpu-worker]`. Il job
  riporta `embedding_device`, `embedding_placement` (`gpu`, `split` o `cpu`) e
  `embedding_accelerator`.
- Il percorso CUDA richiede la build CUDA di torch (vedi `[tool.uv.sources]` in
  [pyproject.toml](../pyproject.toml) — su Windows PyPI serve solo la wheel CPU-only,
  quella CUDA vive sull'indice ufficiale `download.pytorch.org`). Quell'indice è
  vincolato da un **marcatore di piattaforma**: vale su Linux e Windows x86-64, dove le
  sue wheel esistono; su macOS Apple Silicon torch arriva da PyPI (e con lui Metal),
  altrimenti `uv sync` fallirebbe lì (A15 — la matrice misurata è nel README di root).
  Su Windows-on-Arm (RTX Spark) l'uso di CUDA dipende dalla wheel CUDA di torch per
  quella piattaforma: se `torch.cuda` non è disponibile il job resta su CPU, e il
  motivo sta nel report.


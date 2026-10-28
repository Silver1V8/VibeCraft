Italiano | [English](../README.en.md)

> Documentazione operativa sotto `rag/docs/`: **non** è corpus RAG (il corpus è `docs/` del progetto). Stesso schema degli ADR. Italiano canonico; l'inglese resta un indice breve in `rag/README.en.md`.

[← Indice operativo](../README.md)

# Streaming e repliche locali

## Streaming e repliche locali opt-in

`POST /ask` mantiene il JSON storico come default. Con `"stream": true` restituisce
NDJSON: `meta`, zero o più `delta` con campo `text`, infine `result` con campo `value`
contenente il payload completo, oppure `error` con `detail`. Il risultato finale
normalizza anche l'astensione; i delta sono provvisori. `meta.streaming_native`
distingue il provider nativo da un adattatore che emette tutto il testo alla fine.
La dashboard usa questa modalità. Cache e risposte del grafo possono non richiedere
una generazione: vanno misurate separatamente.

| Variabile | Default | Ambito |
|---|---|---|
| `VIBECRAFT_ASK_MAX_ACTIVE` | 8 | Richieste `/ask` attive per processo; eccesso 429 |
| `VIBECRAFT_CPU_GET_RATE_LIMIT` | `EMBED_CONCURRENCY * 15` | Hit/minuto (finestra) per IP su `/api/retrieve`, `/api/code/search`, `/api/graph/semantic-map`; eccesso 429 |
| `VIBECRAFT_CPU_GET_WINDOW_SECONDS` | 60 | Finestra del rate-limit GET CPU |
| `VIBECRAFT_DISABLE_OPENAPI` | unset | `1` spegne `/docs` `/redoc` `/openapi.json` anche su loopback |
| `VIBECRAFT_ENABLE_OPENAPI` | unset | `1` riapre OpenAPI anche su bind non-loopback (debug) |
| `VIBECRAFT_LLM_CONCURRENCY` | 2 | Generazioni `/ask` contemporanee per processo |
| `VIBECRAFT_LLM_QUEUE_TIMEOUT_SECONDS` | 30 | Attesa massima dello slot di generazione |
| `VIBECRAFT_ASK_TIMEOUT_SECONDS` | Timeout Ollama + 60 | Scadenza della pipeline; un thread già avviato termina prima di restituire capacità |
| `VIBECRAFT_GENERATION_MAX_ACTIVE` | 2 | Job LLM attivi per processo, in totale tra generate, refine e project brief; eccesso 429 |
| `VIBECRAFT_GENERATION_MAX_FINISHED` | 100 | Job terminati conservati per tipo (generate, refine, brief) per il polling dello stato; oltre si scartano i più vecchi (mai quelli in corso), il GET risponde 404 |
| `VIBECRAFT_ROLE` | `standalone` | `standalone`, `reader` oppure `writer` |
| `VIBECRAFT_INDEX_MODE` | `legacy` | `legacy` oppure `immutable` |
| `VIBECRAFT_DELTA_MODE` | `cow` | Delta dei progetti a snapshot immutabili: `cow` (copy-on-write) oppure `rebuild` (full rebuild a ogni delta) |
| `VIBECRAFT_REINDEX_DEVICE` | `auto` | Embedding dei job di reindex, in un processo separato. `auto` prova CUDA (NVIDIA, anche Spark/GB10, oppure AMD se PyTorch è la build ROCm), poi Metal, poi una GPU OpenVINO, poi la NPU, poi la CPU. `cuda`, `mps`, `intel` e `npu` forzano quel backend. Su una GPU discreta i pesi del reindex stanno tutti lì se c'è spazio anche per l'LLM (circa 8 GB più un giunto); su Apple la soglia è 24 GB installati, perché il sistema sta nello stesso pool. Sotto, si divide. Una GPU AMD senza ROCm e senza OpenVINO non viene usata. `/ask` resta su CPU |
| `VIBECRAFT_REINDEX_GPU_MIN_FREE_MB` | 3072 | Memoria libera minima per usare l'acceleratore: VRAM libera sulla GPU NVIDIA più libera; sul totale del pool per i chip unificati NVIDIA (con almeno 1024 MB non mappati); memoria reclamabile su Apple |
| `VIBECRAFT_DATABASE_DIR` | `rag/database` | Sorgente storica per diagnostica/migrazione; gli indici attivi sono nelle root registrate |
| `VIBECRAFT_PROJECTS_DIR` | `<installazione>/projects` | Registry e nuove root; percorso assoluto, `/app/projects` in Compose |
| `VIBECRAFT_PROJECT_ID` | legacy | Progetto fisso per MCP e script di manutenzione; la CLI index usa `--project` |

8 e 2 sono limiti iniziali configurabili, non capacità dimostrate. Più processi
moltiplicano sia i limiti verso il motore sia la memoria del modello embedding e
degli snapshot. Non aumentare automaticamente il numero di worker.

### Un writer e due reader sulla stessa macchina

Reader e writer richiedono `VIBECRAFT_INDEX_MODE=immutable`. Preparare un database
dedicato, con Qdrant e motore esplicitamente selezionati, usando il full rebuild
`python index.py` nel profilo writer. Il marker persistente `.immutable-index`
impedisce successivi incrementali anche se un comando dimentica la variabile di
ambiente; un full fallito può lasciare intenzionalmente questa protezione attiva.
Questo rifiuto riguarda il percorso legacy. Per i progetti ordinari l'indice
è immutabile e `--incremental` non vuoto è copy-on-write (full rebuild di ripiego).

Esempio di configurazione PowerShell da applicare **in ogni processo**, adattando
i percorsi a un ambiente dedicato già predisposto. Non avvia né modifica i servizi:

```powershell
$env:VIBECRAFT_INDEX_MODE = 'immutable'
$env:VIBECRAFT_DATABASE_DIR = 'C:/vibecraft-lab/database'
$env:QDRANT_URL = 'http://127.0.0.1:16333'
$env:VIBECRAFT_OLLAMA_URL = 'http://127.0.0.1:21434'
# Impostare VIBECRAFT_API_KEY nel processo tramite il proprio gestore di segreti.
```

| Processo | Variabili aggiuntive | Comando da `rag/` |
|---|---|---|
| Writer designato | `VIBECRAFT_ROLE=writer`, `VIBECRAFT_PORT=18000` | `python server.py` |
| Reader A | `VIBECRAFT_ROLE=reader`, `VIBECRAFT_PORT=18001` | `python server.py` |
| Reader B | `VIBECRAFT_ROLE=reader`, `VIBECRAFT_PORT=18002` | `python server.py` |

Tutti devono usare gli stessi modelli/configurazione indice e la stessa directory
locale. Il reader richiede una chiave API esplicita anche da loopback: un proxy
locale deve inoltrare una credenziale verificata, senza fidarsi di
`X-Forwarded-For`. Se il proxy inoltra un header `Host` diverso dal loopback, quel nome
va aggiunto a `VIBECRAFT_ALLOWED_HOSTS` nei processi a valle: ogni processo rifiuta con
400 gli `Host` non riconosciuti (difesa dal DNS rebinding, vedi
[SECURITY_SURFACE.md](../SECURITY_SURFACE.md) Fatto 9).
La UI richiede la chiave al primo 401 e non la riceve dal server.
Le route di scrittura e i relativi manager non sono caricati nel reader.
Quando il servizio Qdrant offre credenziali di sola lettura, configurare quelle
nei processi reader tramite `QDRANT_API_KEY`; non distribuire loro la chiave writer.

I dati nelle directory di versione possono essere in sola lettura; il
coordinamento `.reader-locks` richiede scrittura condivisa locale. Ogni snapshot
trattiene una lease fino al termine delle richieste che lo usano: retention e GC
conservano così anche il manifest e la collection Qdrant associata. Non montare
l'intero database come strettamente read-only. Il lock OS coordina un writer
designato e i suoi comandi CLI; non è un sistema di elezione o failover.
All'avvio/reload il reader confronta manifest e hash degli artefatti usando il
validatore storage esistente. Per NPY controlla indice e hash registrati; questo
controllo non equivale a una nuova scansione profonda di tutti i byte dei vettori.

### Limiti verificati e envelope supportato

**Envelope operativo dichiarato (P0–P2 software):** un writer designato + N reader
locali sulla stessa macchina (`VIBECRAFT_INDEX_MODE=immutable`), senza claim di
throughput, TTFT o capacità oltre i limiti configurabili sopra. La matrice HTTP
reale k=1/4/8 e il confronto uno-vs-due reader con Qwen (**P3**) **non sono ancora
eseguiti**; fino a quella misura le «repliche locali opt-in» restano software
verificato in isolation, non un envelope di carico pubblicato.

Con Ollama 0.34.4 e il modello locale qwen3.5:9b, il motore impone un solo slot per
l'architettura qwen35: richieste HTTP sovrapposte non producono inferenze parallele.
Le [prove reali](../../archive/adr/horizontal-bench/preflight-20260928/README.md) lo documentano.

Le repliche su host diversi richiedono un meccanismo verificato di distribuzione
delle versioni e di conservazione delle collection ancora in uso. Le lease locali
non costituiscono un protocollo distribuito; questo scenario non è supportato
dall'implementazione corrente. Specifica, gate e stato sono in
[SCALABILITA_ORIZZONTALE.md](../adr/SCALABILITA_ORIZZONTALE.md) e documenti collegati.


# VibeCraft

Una console **Graph-RAG per la governance documentale**: indicizza un corpus di documenti
normativi e il codice che dovrebbe implementarli, e risponde a domande citando le fonti —
pesando quanto ciascuna fonte è autorevole, non solo quanto somiglia alla domanda.

La differenza rispetto a un RAG generico è questa: in un corpus di governance il documento
che **spiega** una regola usa lo stesso vocabolario di quello che **la stabilisce**, ed è
spesso più discorsivo, quindi vince il confronto semantico. VibeCraft tiene conto
dell'autorità dichiarata dalle fonti, della precedenza dichiarata fra documenti in
conflitto, e della fiducia nel cammino percorso sul grafo per arrivarci.

Le risposte sono ancorate alle fonti recuperate; citazioni, risultati parziali e punti
aperti restano da verificare. Il retrieval non garantisce che ogni informazione utile
del corpus sia stata trovata.

Stato della documentazione: **21 settembre 2026**.

## Cosa fa

- **`/ask`** — retrieval ibrido (denso + lessicale + rerank ColBERT) con ri-ponderazione
  per autorità, più il codice che implementa le sezioni recuperate. Le domande puramente
  strutturali ("quali relazioni ha X", "cosa impatta se modifico Y") sono risposte
  direttamente dal grafo, senza chiamare l'LLM.
- **Pipeline Explore → Canvas → Propose → Validate → Archive** per portare una modifica
  dall'intervista alla specifica, ancorata ai documenti normativi.
- **Intake & Import** con conversione locale, anteprima e review in staging: Docling
  per PDF, lettura diretta Excel, MarkItDown per i formati moderni e LibreOffice per DOC/PPT.
- **Mappa del grafo, Semantic Map, Impact Ripple** sul corpus e sul codice indicizzato.
- **Agenti in-app** con Claude Code, Ollama, Codex CLI e Cursor CLI; l'esecuzione
  agentic richiede un contratto corrente validato dal server.
- **MCP locale di sola lettura** per retrieval, ricerca nel codice e interrogazione del grafo.
- **Versionamento blue/green** dell'indice, eval-gate sui rebuild completi e rollback
  con verifica della collection Qdrant di destinazione.
- **ColBERT su disco**, in file NPY per documento con lettura dei soli chunk richiesti;
  benchmark del delta reale con memoria misurata e risultati riproducibili.

## Pipeline e agenti

Da [`/pipeline`](http://127.0.0.1:8000/pipeline) si passa dall'intervista al Canvas,
alla Spec con scenari Gherkin, alla validazione e all'archiviazione. Propose e agente
condividono un elenco di **punti aperti**: la loro descrizione è dichiarata dal modello,
non verificata automaticamente nel merito.

| Runner | Modalità | Accesso al contesto |
|---|---|---|
| Claude Code (`claude`) | suggest, oneshot, agentic | tre tool MCP locali |
| Ollama (`local`) | suggest, oneshot, agentic | lettura e ricerca locali; scritture confinate in agentic |
| Codex CLI (`codex`) | suggest, oneshot | strumenti della CLI in sandbox di sola lettura |
| Cursor CLI (`cursor`) | suggest, oneshot | modalità plan/ask con sandbox abilitata |

La console rileva i runner disponibili sul server. Le CLI e i relativi accessi al
provider vanno predisposti sulla macchina che esegue VibeCraft; Cursor è integrato,
ma non ancora verificato con un'esecuzione reale. Il runner `local` usa Ollama;
gli altri possono inviare il contesto letto al rispettivo provider remoto.

**Agentic parte solo con una validazione superata del contratto corrente**: Canvas,
Spec e decisioni sono congelati nel record e ricontrollati dal server prima dell'avvio.
Suggest e oneshot restano disponibili anche quando il gate blocca agentic.
Accettare un punto aperto lo mantiene irrisolto; la chiave API condivisa non certifica
l'identità di chi prende la decisione (`origin_verified: false`).

Dettagli e limiti: [runner](rag/README.md#runner-dellagente-claude-ollama-codex-cursor)
e [gate della pipeline](rag/adr/PIPELINE_GATE.md).

## Requisiti, senza indorare la pillola

**Il setup predefinito scarica circa 11 GB per embedding e LLM.** I modelli Docling
per l'importazione PDF richiedono spazio aggiuntivo:

| | |
|---|---|
| `bge-m3` (embedding) | 4,3 GB, scaricato al primo avvio |
| `qwen3.5:9b` (LLM locale) | 6,6 GB, via Ollama |
| Spazio disco consigliato | ~20 GB |

**Una GPU NVIDIA cambia molto le cose.** Misurato su una RTX 3070 Ti contro la CPU della
stessa macchina:

| | GPU | CPU |
|---|---|---|
| Embedding | 46 chunk/s | **1 chunk/s (45× più lento)** |
| Indicizzazione completa (corpus di esempio, 612 elementi) | ~13 s | **~10 min** |

Senza GPU il sistema **funziona**, ma reindicizzare diventa un'operazione da prendere con
calma. Le singole domande restano usabili: l'embedding della query costa circa un secondo,
dentro i ~30 s che l'LLM locale impiega comunque a rispondere.

I prerequisiti dipendono da come lo installi:

- **Via Docker** — Docker con Compose. Python e Qdrant sono nello stack; anche Ollama
  nei profili `cpu` e `gpu`.
- **Nativa** — **Python 3.14**, [uv](https://docs.astral.sh/uv/), **Docker** (per il solo
  Qdrant) e **[Ollama](https://ollama.com)**.

## Avvio rapido — Docker (consigliato)

Uno stack unico: applicazione, Qdrant e Ollama. I comandi seguenti usano il profilo
`cpu`; le varianti sono indicate sotto. Eseguili dalla radice del repository.

```bash
git clone https://github.com/Silver1V8/VibeCraft.git
cd VibeCraft

# 0. Genera la API key. In Docker è obbligatoria: il browser non arriva al server
#    come 127.0.0.1, quindi l'autenticazione non è aggirabile — e senza una chiave
#    configurata SUL SERVER nessun valore potrebbe soddisfarla.
#    compose legge questo file da solo; senza, si rifiuta di partire e ti dice perché.
docker run --rm python:3.14-slim python -c "import secrets; print('VIBECRAFT_API_KEY=' + secrets.token_urlsafe(32))" > .env

# 1. Servizi di supporto
docker compose --profile cpu up -d qdrant ollama

# 2. Il modello LLM (6,6 GB, una volta sola)
docker compose exec ollama ollama pull qwen3.5:9b

# 3. Indicizza il corpus. Al primo avvio scarica anche bge-m3 (4,3 GB).
docker compose --profile cpu run --rm app-cpu python index.py

# 4. Avvia la console
docker compose --profile cpu up -d
```

Poi apri **http://127.0.0.1:8000**.

Il passo 0 crea `.env`: se il file esiste già, conserva il contenuto e aggiungi solo
`VIBECRAFT_API_KEY`, senza sovrascriverlo. Il comando usa Python in container, quindi
non richiede Python installato sull'host.

| Profilo | Servizi di supporto | Servizio applicazione |
|---|---|---|
| `cpu` | `qdrant ollama` | `app-cpu` |
| `gpu` | `qdrant ollama-gpu` | `app-gpu` |
| `host-ollama` | `qdrant` | `app-host-ollama` |

Per **GPU**, sostituisci `cpu` con `gpu`, `ollama` con `ollama-gpu` nei nomi dei
servizi e `app-cpu` con `app-gpu`. Il download diventa
`docker compose exec ollama-gpu ollama pull qwen3.5:9b`.
Serve NVIDIA Container Toolkit configurato per Docker.

Per **Ollama sull'host**, usa `--profile host-ollama`, avvia solo `qdrant` al passo 1,
esegui `ollama pull qwen3.5:9b` sull'host e indicizza con `app-host-ollama`.
Ollama deve essere raggiungibile dal container tramite `host.docker.internal:11434`.

**Perché il passo 3 usa `run --rm` e non `exec`.** Il server si rifiuta di partire finché
un indice non esiste — è una scelta deliberata, meglio non partire che servire il vuoto.
Quindi non c'è alcun container in cui entrare con `exec`: l'indicizzazione va fatta da un
container usa-e-getta, prima del primo avvio.

**Perché tre profili.** Docker su macOS non espone Metal: un modello da 9B dentro un
container gira su CPU. Lì il percorso sensato è tenere **Ollama nativo** sull'host e usare
`--profile host-ollama`, che avvia tutto il resto e punta al tuo Ollama.

I pesi dei modelli **non stanno nell'immagine**: vivono in volumi, quindi si scaricano una
volta sola e sopravvivono agli aggiornamenti.

**La console chiede la chiave, una volta sola.** Al primo caricamento la console si accorge
da sé che le richieste vengono respinte, chiede la `VIBECRAFT_API_KEY` — quella generata al
passo 0 — e la conserva in questo browser. Non viene mai scritta nella pagina: la pagina è
servita senza autenticazione, quindi metterla lì la regalerebbe a chiunque la raggiunga.

Con l'installazione nativa non cambia nulla: da `127.0.0.1` non viene chiesto niente.

> ⚠️ **Non puntare lo stack Docker a un Qdrant che usi già per un'installazione nativa.**
> Le due installazioni hanno indici locali distinti, e ciascuna considera "orfane" le
> collection dell'altra. Lo stack qui sopra usa un proprio Qdrant con un proprio volume,
> quindi il problema non si pone: si pone solo se imposti `QDRANT_URL` a mano verso
> un'istanza condivisa.

## Avvio rapido — installazione nativa

```bash
git clone https://github.com/Silver1V8/VibeCraft.git
cd VibeCraft

# 1. Configurazione Compose: su un checkout nuovo crea .env con una chiave.
#    Se .env esiste, aggiungi la variabile senza sovrascrivere il file.
python -c "import secrets; print('VIBECRAFT_API_KEY=' + secrets.token_urlsafe(32))" > .env

# 2. Qdrant (vector store), su 127.0.0.1:6333
docker compose up -d qdrant

# 3. Il modello LLM locale (6,6 GB — è il download più lungo)
ollama pull qwen3.5:9b

# 4. Dipendenze Python
cd rag
uv sync --frozen

# 5. Indicizza il corpus. Al primo avvio scarica anche bge-m3 (4,3 GB).
uv run python index.py

# 6. Avvia la console
uv run python server.py       # oppure: scripts/run_server.sh
```

Poi apri **http://127.0.0.1:8000**.

La chiave nel `.env` della radice serve all'interpolazione di Compose, anche avviando
solo Qdrant. Il backend nativo legge invece `rag/.env.local`; da loopback non richiede
la chiave.

Se qualcosa non parte, **chiedi al preflight invece di indovinare**: verifica versione di
Python, Qdrant, Ollama e il suo modello, spazio su disco, GPU, LibreOffice (DOC/PPT) e porta
— e per ogni problema stampa il rimedio.

```bash
# Dalla directory rag/
uv run python scripts/doctor.py
```

**Su quali macchine `uv sync` riesce.** `torch` è l'unica dipendenza sensibile alla
piattaforma: dove esiste la build CUDA la si prende dall'indice ufficiale PyTorch, altrove
da PyPI (`[tool.uv.sources]` in [rag/pyproject.toml](rag/pyproject.toml), con un marcatore
di piattaforma). Verificato con `uv sync --frozen --dry-run --python-platform <p>`:

| Piattaforma | `uv sync` | torch |
|---|---|---|
| Linux x86-64 | ✅ | `2.13.0+cu126` |
| Linux ARM64 | ✅ | `2.13.0+cu126` |
| Windows x86-64 | ✅ | `2.13.0+cu126` |
| macOS Apple Silicon (macOS 14+) | ✅ | `2.13.0` (PyPI) |
| macOS Intel | ❌ | PyTorch non pubblica più wheel x86-64 per macOS |
| Windows ARM64 | ❌ | nessuna wheel `win_arm64` a monte |

Le due righe rosse sono **limiti a monte, non di questo repository**: per quelle
piattaforme PyTorch non pubblica alcuna wheel, e nessuna configurazione qui le crea. Il
percorso disponibile lì è Docker (target `cpu`, multi-arch).

Una macchina **senza GPU NVIDIA** su Linux o Windows x86-64 sincronizza normalmente: la
build CUDA si installa e gira su CPU (`torch.cuda.is_available()` → `False`). Costa ~4 GB
di download che non userà — se pesano, il target `cpu` del Dockerfile li evita.

**Non serve procurarsi dei documenti per provarlo:** il repository include in `docs/`
una [baseline di governance cross-progetto](docs/README.md), già pronta da indicizzare.

In un clone pubblico `code/` contiene solo i segnaposto: il codice del progetto
ospitante non viene distribuito. Un checkout locale può già contenerlo.
Le funzioni che vivono sul codice (Semantic Map, Impact Ripple, il codice implementante
dentro le risposte) restano quindi spente finché non punti `code/` a un progetto vero.

## Immagine pronta

Le release pubblicano un'immagine su GHCR, così non serve costruirla:

```bash
docker pull ghcr.io/silver1v8/vibecraft:latest
```

È il target **CPU**, `linux/amd64`, utilizzabile senza GPU. Chi ha una GPU NVIDIA — o gira
su Apple Silicon — costruisce in locale, dove è veloce e nativo:

```bash
docker build --target gpu -t vibecraft:gpu .   # NVIDIA
docker build --target cpu -t vibecraft:cpu .   # Apple Silicon, build arm64 nativa
```

## Aggiornare senza perdere l'indice

L'indice non sta mai dentro l'immagine né dentro il codice: vive in
`rag/database/` (nativa) o nel volume `vibecraft_index` (Docker). Aggiornare non lo tocca.

```bash
# Docker — i volumi (indice, pesi dei modelli, Qdrant) sopravvivono
git pull && docker compose --profile cpu build && docker compose --profile cpu up -d

# Nativa
git pull && cd rag && uv sync --frozen
```

Dopo l'aggiornamento, **chiedi al sistema se l'indice è ancora valido** invece di
reindicizzare per abitudine:

```bash
# Dalla directory rag/
uv run python index.py --index-status
uv run python index.py --check-integrity
```

Tre casi, in ordine di costo:

| Cosa è cambiato | Cosa serve |
|---|---|
| Solo i documenti | `index.py --incremental` — reindicizza i soli file toccati |
| Il **modello di embedding** (`rag_config.yaml`) | **Full rebuild** obbligatorio: i vettori vecchi non sono confrontabili con i nuovi. Il manifest registra il modello usato, quindi la differenza è rilevabile e non silenziosa |
| Il **formato degli artefatti** | JSON, ColBERT in NPY per documento, dense/code in NPZ. Un ColBERT NPZ versionato richiede la migrazione sotto prima di un delta non vuoto; il vecchio layout piatto richiede una nuova build per passare a NPY. Gli indici solo pickle richiedono un rebuild |

Per un indice **versionato** che usa ancora `colbert.npz`, dalla directory `rag/`:

```bash
uv run python index.py --check-integrity
uv run python index.py --migrate-colbert-npy
uv run python index.py --check-integrity
```

In Docker usa gli stessi argomenti con
`docker compose --profile cpu run --rm app-cpu python index.py` dalla radice.
La conversione verifica l'uguaglianza dei vettori senza ricalcolare gli embedding,
pubblica una nuova versione e conserva Qdrant. Non ripara disallineamenti preesistenti:
se il controllo segnala punti extra o mancanti, va prima diagnosticata la differenza.
Gli indici già NPY non richiedono questa conversione.

Per tornare a una versione conservata, dalla directory `rag/`:

```bash
uv run python index.py --rollback          # alla versione precedente
# Per una versione precisa: uv run python index.py --rollback NOME_VERSIONE
```

Le versioni conservate sono 5 per default (`VIBECRAFT_INDEX_KEEP`).

Il rollback viene rifiutato se la collection Qdrant di destinazione risulta assente.
Gli incrementali condividono la collection della build completa di origine:
tornare a un loro snapshot precedente **non riavvolge i punti Qdrant** modificati
dopo; la CLI segnala il caso e consiglia un full rebuild.

L'eval-gate riguarda i rebuild completi; gli incrementali promuovono direttamente.
Una metrica sotto soglia blocca la promozione se il gate è configurato come bloccante;
un errore nell'esecuzione della valutazione o l'assenza del golden set lasciano invece
passare la promozione. Questo gate è distinto da quello che autorizza l'avvio agentic.

## Scalabilità: risultati e limiti

ColBERT viene letto a richiesta e i delta riusano i file dei documenti invariati.
Grafo, metadati e vettori dense/code mantengono costi globali: il corpus non diventa
illimitato e il costo complessivo del delta non dipende soltanto dai file modificati.

- Una prova full su CPU, 32 documenti / 64 chunk, ha ridotto il picco RSS campionato
  da **6,436 a 3,152 GiB**. È una prova per variante; formato e raggruppamento
  dell'encoding cambiano insieme, quindi non è una garanzia per ogni corpus.
- Le curve del delta includono **150 prove per versione**, con corpus documenti,
  codice e misto. Con 100 piccoli documenti tutti modificati, la mediana fino allo
  snapshot pronto passa da **15,934 a 58,099 s**: meno RAM non significa più velocità
  in ogni caso. Il batching limitato è stato studiato, ma non ancora implementato.
- Non sono state fissate soglie universali di volume o di sharding. ColBERT rimane
  locale; il backend multivettore Qdrant non è stato introdotto.

Metodi, curve e limiti: [evidenze della scalabilità](rag/eval/results/README.md#scalabilità-sidecar--21-settembre-2026)
e [istruzioni del benchmark](rag/README.md#delta-reale-isolato).

## Configurazione

Le principali variabili d'ambiente sono documentate in
[`rag/.env.example`](rag/.env.example). Per personalizzare il backend nativo:

```bash
cp rag/.env.example rag/.env.local
```

`rag/.env.local` è gitignorato e viene caricato automaticamente all'avvio.

Provider e modello LLM si scelgono in [`rag/rag_config.yaml`](rag/rag_config.yaml), anche
**per singolo step** della pipeline: si può ad esempio generare il canvas con Claude e
tenere tutto il resto su Ollama locale.

Per importare PDF con Docling, dalla directory `rag/` scarica e verifica i pesi:

```bash
uv run python scripts/docling_models.py
uv run python scripts/docling_models.py --verifica
```

L'importazione DOC/PPT richiede LibreOffice sull'host nell'installazione nativa;
è già incluso nell'immagine Docker. XLS/XLSX vengono letti direttamente, senza
ricalcolare le formule. Per usare documenti e codice dell'host in Docker, adatta
i bind mount `docs/` e `code/` del servizio applicazione in `docker-compose.yml`.

## MCP locale

Con il backend HTTP già avviato e un indice pronto, dalla directory `rag/`:

```bash
uv run --frozen python -B mcp_server.py
```

È un adattatore **stdio**, da avviare tramite un client MCP: attende messaggi su
stdin e non apre una nuova porta. Espone solo `vibecraft_retrieve`,
`vibecraft_code_search` e `vibecraft_graph_query`, senza scritture o avvio di agenti.
Il backend predefinito è `http://127.0.0.1:8000`; `VIBECRAFT_MCP_BACKEND_URL` accetta
solo indirizzi loopback. L'eventuale `VIBECRAFT_API_KEY` va ereditata dall'ambiente
del client. Configurazione completa e uso in container:
[MCP locale di sola lettura](rag/README.md#mcp-locale-di-sola-lettura).

## Sicurezza

Il default è **bind su `127.0.0.1`**: raggiungibile solo da questa macchina, senza
autenticazione. È una scelta deliberata per l'uso locale.

**Se cambi `VIBECRAFT_HOST` per esporre il server in rete, imposta anche
`VIBECRAFT_API_KEY`.** Con un bind non-loopback le funzioni che hanno senso solo in locale
(selettore di cartelle nativo, scansione di un percorso arbitrario del filesystem) vengono
disattivate automaticamente — ma il resto della superficie va protetto da te.

Il server accetta solo richieste con header `Host` riconosciuto (difesa dal DNS
rebinding): `127.0.0.1`, `localhost`, `::1`, l'indirizzo di `VIBECRAFT_HOST` se è
specifico e l'host di `VIBECRAFT_BASE_URL`; gli altri ricevono **400**. Se raggiungi il
server con un altro nome (hostname di LAN, reverse proxy), aggiungilo a
**`VIBECRAFT_ALLOWED_HOSTS`**, lista separata da virgole (es.
`VIBECRAFT_ALLOWED_HOSTS=vibecraft.lan,192.168.1.20`). Nessuna wildcard (le voci con `*`
sono ignorate con un avviso): elenca solo nomi di cui controlli il DNS.

Ogni risposta vieta di essere incorniciata (`X-Frame-Options: DENY`,
`Content-Security-Policy: frame-ancestors 'none'`, difesa dal clickjacking) e porta
`X-Content-Type-Options: nosniff` e `Referrer-Policy: same-origin`: la console **non** si
può incorporare in un `<iframe>` di un'altra pagina, nemmeno di una dashboard interna.

La superficie di attacco è mappata rotta per rotta in
[`rag/SECURITY_SURFACE.md`](rag/SECURITY_SURFACE.md).

## Documentazione

| | |
|---|---|
| [`rag/README.md`](rag/README.md) | architettura, retrieval, pipeline, indicizzazione |
| [`rag/adr/`](rag/adr/README.md) | le decisioni architetturali e il perché |
| [`rag/adr/PIPELINE_GATE.md`](rag/adr/PIPELINE_GATE.md) | contratto validato, decisioni e avvio agentic |
| [`docs/README.md`](docs/README.md) | indice della baseline documentale inclusa |
| [`rag/SECURITY_SURFACE.md`](rag/SECURITY_SURFACE.md) | superficie di attacco, rotta per rotta |
| [`rag/adr/AUDIT.md`](rag/adr/AUDIT.md) | audit del progetto: cosa è misurato, cosa è aperto |
| [`rag/adr/DISTRIBUTION.md`](rag/adr/DISTRIBUTION.md) | piano di distribuzione e portabilità |
| `/infografica` (a server acceso) | il flusso di interrogazione, illustrato |

## Licenza

[Apache-2.0](LICENSE).

I pesi dei modelli scaricati a runtime (`bge-m3`, `qwen3.5`) hanno **ciascuno la propria
licenza**, indipendente da questa: verificale prima di un uso commerciale.

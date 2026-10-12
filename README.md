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

**Versione documentata: 5 ottobre 2026, multi-progetto integrato in `main`.**
I checkout precedenti vanno aggiornati prima di usare i nuovi comandi.

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
- **Progetti separati** con creazione/apertura/selezione, cartelle e indici dedicati.
- **Agenti in-app** con Claude Code e Ollama; agentic richiede un contratto
  corrente validato nel progetto. Codex/Cursor restano disponibili via export
  prompt e MCP esterno, con avvio integrato disabilitato.
- **MCP locale di sola lettura** per retrieval, ricerca nel codice e interrogazione del grafo.
- **Versionamento blue/green** dell'indice, eval-gate sui rebuild completi e rollback
  con verifica della collection Qdrant di destinazione.
- **ColBERT su disco**, in file NPY per documento con lettura dei soli chunk richiesti;
  benchmark del delta reale con memoria misurata e risultati riproducibili.

## Progetti separati

L'apertura di `/` mostra la schermata iniziale con progetti recenti, ricerca,
creazione e apertura di cartelle esistenti. **Progetti** nella barra torna alla
selezione senza interrompere le operazioni attive. I link `?project=<id>` aprono
direttamente il progetto; lo storico recente viene conservato nel browser.

La console funziona anche senza progetti o indice. **Nuovo progetto** crea una root
con `project.yaml`, `code/`, `docs/`, `changes/`, `database/` sotto
`VIBECRAFT_PROJECTS_DIR` (percorso assoluto; default `<installazione>/projects`).
Non avvia indicizzazione: importa codice/documenti da Intake e indicizza il progetto.
**Apri progetto esistente** registra una root VibeCraft senza copiarla: con bind
locale puoi scegliere una cartella host, con bind remoto soltanto una root senza
symlink/junction strettamente sotto la directory progetti gestita. In Docker usa
`/app/projects/<cartella>` e monta lì il progetto esistente; il selettore nativo è
nascosto. Esempio di mount aggiuntivo Compose:
`/percorso/host/progetto:/app/projects/esistente` (root con `project.yaml` valido).
In console apri `/app/projects/esistente`; nell'IDE apri la cartella host originale.
Il mount collega i percorsi: VibeCraft non copia il repository automaticamente.
Il nome del progetto non costruisce percorsi.

La selezione vale per scheda: `sessionStorage` e `?project=<id>` conservano il target;
i job già avviati restano nel progetto originario. Due progetti possono mantenere
pagine residenti; operazioni attive impediscono l'eviction. La pipeline salva
localmente intervista, input e bozze per progetto e feature. Dopo refresh o chiusura
puoi scegliere «Ripristina bozza locale» dopo il caricamento dei file server:
il recupero non li sovrascrive. Finché non ripristini o scarti la bozza, chat ed editor
restano in sola lettura; il tipo di sviluppo resta selezionabile e il ripristino lo
sostituisce solo se la bozza ne aveva uno. L'ultimo salvataggio è visibile; le bozze restano
nel browser e non sono sincronizzate fra dispositivi. Non sono previsti delete, rename, ricerca
fra progetti o ACL per progetto.

Da `rag/`: `uv run python index.py --project <id> --index-status` seleziona il progetto
anche per full/delta/integrity/rollback; senza flag usa soltanto `legacy`.
L'ID si trova nel parametro `?project=<id>` della console o in
`GET /api/projects`. Le API del progetto ricevono `X-VibeCraft-Project: <id>`;
senza header si usa esclusivamente il progetto registrato `legacy`.
Per il MCP esterno imposta `VIBECRAFT_PROJECT_ID=<id>` nell'ambiente del processo,
oltre alla normale configurazione di URL/chiave: il target resta fisso per sessione.

Un unico Qdrant ospita namespace distinti: alias `vibecraft_<id>` e collection
`vibecraft_<id>__<version>`. Cache, grafo, staging, job, gate e storico sono per
progetto; il cambio selezione non cambia il target di un lavoro già avviato.

Anche il progetto iniziale ha una root dedicata: `projects/legacy/`, con `code/`,
`docs/`, `changes/` e `database/`. Al primo avvio writer VibeCraft copia e verifica in
`projects/legacy/` la baseline, senza indicizzare o scaricare modelli: `docs/` e `code/`
alla radice dell'installazione se contengono file, altrimenti la baseline versionata in
`templates/docs/` e `templates/code/` (il caso di un clone locale pulito; l'immagine Docker
la porta già in `/app/docs` e `/app/code`). I `template_*.md` di `templates/` non vengono copiati.
Gli altri progetti nuovi nascono vuoti. Un registro già vuoto resta vuoto.
Il nome `legacy` identifica il progetto iniziale: usa lo stesso runtime e indice degli altri.
L'indice legge soltanto `docs/` e `code/` nella root del progetto selezionato.
In PyCharm espandi `projects/legacy/` oppure `projects/<id>/`; la root attiva
è anche nei metadati del progetto. Le cartelle alla radice dell'installazione sono solo la
sorgente di quella copia iniziale.
Il reader non inizializza il registry: un registry inizialmente assente restituisce
`[]` e le richieste senza progetto `project_required`; dopo averlo osservato, la sua
cancellazione/corruzione fallisce chiusa. Inizializza con writer prima del deploy reader; configura `VIBECRAFT_ROLE=reader`,
`VIBECRAFT_INDEX_MODE=immutable` e chiave API obbligatoria.

Compose mantiene `vibecraft_projects:/app/projects` separato da `vibecraft_index` e
con permessi UID 10001; i mount storici docs/code/database servono come sorgenti di migrazione.
I pesi sono condivisi (`vibecraft_models`, cache Docling nell'installazione,
`ollama_models`), non copiati per progetto. Backup coerente: registry, manifest,
code/docs/changes/database di ogni root (anche le root esterne registrate), volume
legacy e `qdrant_storage` con le collection corrispondenti; salva anche i volumi
modelli se vuoi evitare download. Ferma le scritture durante il backup.

`/api/health/live` verifica soltanto il processo, anche senza progetti o con Qdrant
indisponibile; richiede la normale autenticazione, inclusa la chiave in reader.
Readiness e stato dell'indice sono separati in `/api/health` e nei metadati progetto.
Modelli/client/snapshot sono caricati a richiesta: l'apertura della console non
scarica pesi né ripara alias o esegue GC. La manutenzione è esplicita via lifecycle
writer/CLI. Per progetti ordinari un delta non vuoto usa oggi un full rebuild:
il costo embedding riguarda l'intero corpus; un delta noop non ricostruisce.

### Migrare un'installazione esistente

Con dati storici, l'apertura restituisce `project_migration_required`: la migrazione
è esplicita. Ferma server, reader e altri writer; mantieni le variabili che indicano
il database e lo staging originali. Da `rag/`:

```bash
uv run --frozen python -m scripts.migrate_project_layout
```

La migrazione conserva ID `legacy`, originali e vecchie collection; copia e verifica
documenti, codice, changes, staging, pipeline e golden set. Se esiste un indice,
Qdrant e il modello embedding devono essere disponibili: viene ricostruita una candidata
completa in `projects/legacy/database/`, con gate, integrità e alias verificati prima
di pubblicare il registro. Il costo è quello di un full rebuild dell'intero corpus;
serve spazio per la copia e il nuovo indice. Le validazioni storiche richiedono una nuova validazione.

Il registro originale viene salvato byte per byte in `projects/projects.v1.backup.json`
quando presente. Il checkpoint è `projects/.legacy-migration.json`: rilancia lo stesso
comando dopo un'interruzione; se è rimasto un candidato promosso con alias incompleto,
usa `--repair`. Hash cambiati o namespace estranei bloccano la ripresa e richiedono diagnosi.
Dopo pubblicazione una ripetizione non ricostruisce. Per annullare offline, ripristina
il registro salvato e usa il codice precedente, mantenendo i percorsi originali; non cancellare gli originali.
Se il registro prima non esisteva, il ripristino richiede rimuovere soltanto quello nuovo a processi fermi.

In Docker, dopo aver fermato il servizio app, usa
`docker compose --profile cpu run --rm app-cpu python -m scripts.migrate_project_layout`.
Mantieni i volumi storici e gli eventuali bind fino alla verifica; i dati attivi vivono
poi in `vibecraft_projects:/app/projects`, incluso `/app/projects/legacy`.

Codex/Cursor integrati rimangono disabilitati finché l'isolamento delle letture non
è verificato; esportazione prompt e MCP esterno restano disponibili anche senza
binario installato. SDK: Read sicuro e scansioni di directory sicure sono utilizzabili;
scansioni di subtree con segreti/link e scansioni root con `.git` sono negate.
Il runner locale applica pruning dei percorsi vietati.

## Pipeline e agenti

Da [`/pipeline`](http://127.0.0.1:8000/pipeline) si passa dall'intervista al Canvas,
alla Spec con scenari Gherkin, alla validazione e all'archiviazione. Il **tipo di
sviluppo** è una sottocartella di `code/` del progetto: la tendina elenca quelle esistenti
e **Aggiungi** ne crea una nuova (nome a un solo componente, lettere, cifre, `-` e `_`).
Il dry-run del Canvas mostra le sorgenti che verrebbero usate senza chiamare il modello.
Propose e agente
condividono un elenco di **punti aperti**: la loro descrizione è dichiarata dal modello,
non verificata automaticamente nel merito.

| Runner | Modalità | Accesso al contesto |
|---|---|---|
| Claude Code (`claude`) | suggest, oneshot, agentic | tre tool MCP locali |
| Ollama (`local`) | suggest, oneshot, agentic | lettura e ricerca locali; scritture confinate in agentic |
| Codex CLI (`codex`) | export prompt | integrato disabilitato: isolamento letture non verificato |
| Cursor CLI (`cursor`) | export prompt | integrato disabilitato: isolamento letture non verificato |

La console distingue runner installati, avvio disponibile ed esportazione del prompt.
Claude Code e il relativo accesso al provider vanno predisposti sul server; `local`
usa Ollama. Codex/Cursor offrono export prompt e MCP esterno, con esecuzione integrata
disabilitata. Claude e i client esterni possono inviare il contesto al proprio provider.

**Agentic parte solo con una validazione superata del contratto corrente**: Canvas,
Spec e decisioni sono congelati nel record e ricontrollati dal server prima dell'avvio.
Suggest e oneshot restano disponibili anche quando il gate blocca agentic.
Canvas, Propose e contesto dell'agente distinguono i guasti di retrieval dai
risultati vuoti: un guasto operativo restituisce un errore e non avvia la generazione.
Accettare un punto aperto lo mantiene irrisolto; la chiave API condivisa non certifica
l'identità di chi prende la decisione (`origin_verified: false`).

Dettagli e limiti: [runner](rag/README.md#runner-dellagente-claude-ollama-codex-cursor)
e [gate della pipeline](rag/adr/PIPELINE_GATE.md).

## Requisiti, senza indorare la pillola

**Il setup predefinito scarica circa 11 GB per embedding e LLM.** I modelli Docling
per l'importazione PDF richiedono spazio aggiuntivo:

| | |
|---|---|
| `bge-m3` (embedding) | 4,3 GB, caricato alla prima operazione che lo richiede |
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

# 3. Avvia la console: funziona anche senza indice.
docker compose --profile cpu up -d

# 4. Facoltativo: indicizza la baseline inclusa nel progetto legacy.
# La prima indicizzazione scarica bge-m3 (4,3 GB).
docker compose --profile cpu run --rm app-cpu python index.py
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

**Indicizzazione e avvio sono indipendenti.** Dopo l'avvio puoi creare un
progetto, importare da Intake e avviare l'indicizzazione dalla console.
`run --rm` esegue la CLI in un container temporaneo con gli stessi volumi;
per un progetto nuovo aggiungi `--project <id>`. La shell della console non
richiede un indice; retrieval e generazione basata sul corpus lo richiedono.

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

# 5. Avvia la console; crea/seleziona il progetto e importa da Intake.
uv run python server.py       # oppure: scripts/run_server.sh

# In un altro terminale, da rag/: baseline legacy facoltativa.
uv run python index.py
# Progetto creato nella console: uv run python index.py --project <id>
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

**Non serve procurarsi dei documenti per provarlo:** il repository include in
`templates/docs/` una [baseline di governance cross-progetto](templates/docs/README.md),
già pronta da indicizzare (vedi sopra come entra nel progetto iniziale).

In un clone pubblico `templates/code/` contiene solo i segnaposto: il codice del progetto
ospitante non viene distribuito. Un checkout locale può già contenerlo.
Le funzioni che vivono sul codice (Semantic Map, Impact Ripple, il codice implementante
dentro le risposte) restano quindi spente finché non importi codice nel progetto selezionato.

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

Gli indici vivono nei dati persistenti: `<root-progetto>/database/` per tutti,
incluso `projects/legacy/database/`. `rag/database/` è soltanto la sorgente storica. Compose conserva
`vibecraft_projects`, `vibecraft_index` e `qdrant_storage`; aggiornare il
codice non sposta i dati. Mantieni anche le root esterne e i loro mount.

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
| Sorgenti di qualsiasi progetto | `index.py --project <id> --incremental` — no-op se invariati; altrimenti ricostruisce una candidata completa. Senza flag seleziona il `legacy` registrato |
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
I vecchi indici storici con delta mutabili condividevano la collection della build
di origine: il loro rollback non riavvolgeva i punti modificati dopo. La migrazione
ricostruisce l'indice nel profilo ordinario, con collection distinta per candidata.

In tutti i progetti il delta non vuoto passa dal rebuild e dal relativo gate.
Il golden set è `<root-progetto>/eval/golden.yaml`; se manca la promozione può
passare come non valutata.
Una metrica sotto soglia blocca la promozione se il gate è configurato come bloccante;
un errore nella valutazione segue la configurazione del gate. Questo gate è distinto
da quello che autorizza l'avvio agentic.

## Scalabilità: risultati e limiti

Le misure seguenti sono del **21 settembre 2026, percorso legacy**. ColBERT
viene letto a richiesta e i delta legacy riusano i file dei documenti invariati.
Il delta dei nuovi progetti ricostruisce una candidata completa: queste curve
non descrivono il suo costo.
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
un bind della root completa sotto `/app/projects/<cartella>` e registra il suo manifest;
oppure importa i file nel progetto selezionato tramite Intake.

## MCP locale

Con il backend HTTP avviato e l'indice del progetto pronto, dalla directory
`rag/` (imposta `VIBECRAFT_PROJECT_ID=<id>` nel client per un progetto nuovo):

```bash
uv run --frozen python -B mcp_server.py
```

Per Claude Code su Windows, `rag/scripts/install_mcp.ps1` sincronizza l'ambiente e
registra il server come `vibecraft` (`-Scope user|local|project`, `-BackendUrl`):
rieseguirlo sostituisce la registrazione precedente. Il backend va avviato a parte.

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

Le risposte portano anche una **Content-Security-Policy** completa: `script-src 'self'`
senza `unsafe-inline`/`unsafe-eval` (il browser esegue solo gli script serviti da
`/static/`), nessuna fonte esterna (`default-src 'self'`). Per questo i template in
`rag/templates/` non contengono `<script>` né handler `onclick=`/`onchange=` inline: il
codice di ogni pagina sta in `rag/static/pages/<pagina>.js` e i controlli dichiarano
l'azione con `data-click`/`data-change`/`data-input`, registrata con `registerActions()`
(`rag/static/shared.js`); `rag/tests/test_csp.py` lo verifica. Gli stili inline restano
permessi (`style-src 'unsafe-inline'`) perché Tailwind gira come runtime nel browser. Chi
aggiunge una pagina o un pulsante segue lo stesso schema: un handler inline verrebbe
bloccato in silenzio.

La superficie di attacco è mappata rotta per rotta in
[`rag/SECURITY_SURFACE.md`](rag/SECURITY_SURFACE.md).

## Documentazione

| | |
|---|---|
| [`rag/README.md`](rag/README.md) | architettura, retrieval, pipeline, indicizzazione |
| [`rag/adr/`](rag/adr/README.md) | le decisioni architetturali e il perché |
| [`rag/adr/PIPELINE_GATE.md`](rag/adr/PIPELINE_GATE.md) | contratto validato, decisioni e avvio agentic |
| [`templates/docs/README.md`](templates/docs/README.md) | indice della baseline documentale inclusa |
| [`rag/SECURITY_SURFACE.md`](rag/SECURITY_SURFACE.md) | superficie di attacco, rotta per rotta |
| [`rag/adr/AUDIT.md`](rag/adr/AUDIT.md) | audit del progetto: cosa è misurato, cosa è aperto |
| [`rag/adr/DISTRIBUTION.md`](rag/adr/DISTRIBUTION.md) | piano di distribuzione e portabilità |
| `/infografica` (a server acceso) | il flusso di interrogazione, illustrato |

## Licenza

[Apache-2.0](LICENSE).

I pesi dei modelli scaricati a runtime (`bge-m3`, `qwen3.5`) hanno **ciascuno la propria
licenza**, indipendente da questa: verificale prima di un uso commerciale.

## Verifica dell'evoluzione multi-progetto

Il gate finale del 5 ottobre 2026 ha registrato **2.348 test superati e 20 skip**
per privilegi file-symlink Windows, con prove Linux complementari. Lint, check
Node, integrazione HTTP/Qdrant/browser e persistenza Docker sono stati verificati.
I provider sono simulati ai confini; lo smoke Docker usa un runtime CPU esistente
con il sorgente corrente montato. Build Docker da zero e GitHub Actions non
sono stati eseguiti: il gate non certifica una nuova immagine pubblicata.

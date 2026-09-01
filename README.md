# VibeCraft

Una console **Graph-RAG per la governance documentale**: indicizza un corpus di documenti
normativi e il codice che dovrebbe implementarli, e risponde a domande citando le fonti —
pesando quanto ciascuna fonte è autorevole, non solo quanto somiglia alla domanda.

La differenza rispetto a un RAG generico è questa: in un corpus di governance il documento
che **spiega** una regola usa lo stesso vocabolario di quello che **la stabilisce**, ed è
spesso più discorsivo, quindi vince il confronto semantico. VibeCraft tiene conto
dell'autorità dichiarata dalle fonti, della precedenza dichiarata fra documenti in
conflitto, e della fiducia nel cammino percorso sul grafo per arrivarci.

E quando la risposta nel corpus non c'è, **lo dice** invece di inventarla.

## Cosa fa

- **`/ask`** — retrieval ibrido (denso + lessicale + rerank ColBERT) con ri-ponderazione
  per autorità, più il codice che implementa le sezioni recuperate. Le domande puramente
  strutturali ("quali relazioni ha X", "cosa impatta se modifico Y") sono risposte
  direttamente dal grafo, senza chiamare l'LLM.
- **Pipeline Explore → Canvas → Propose → Validate → Archive** per portare una modifica
  dall'intervista alla specifica, ancorata ai documenti normativi.
- **Intake & Import** per far entrare documenti nuovi passando da una review in staging.
- **Mappa del grafo, Semantic Map, Impact Ripple** sul corpus e sul codice indicizzato.
- **Versionamento blue/green** dell'indice con eval-gate sulla promozione e rollback.

## Requisiti, senza indorare la pillola

**Servono circa 11 GB di pesi di modello.** È la vera barriera d'ingresso, non
l'installazione:

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

- **Via Docker** — serve solo **Docker**. Python, Qdrant e Ollama stanno tutti nello stack.
- **Nativa** — **Python 3.14**, [uv](https://docs.astral.sh/uv/), **Docker** (per il solo
  Qdrant) e **[Ollama](https://ollama.com)**.

## Avvio rapido — Docker (consigliato)

Uno stack unico: applicazione, Qdrant e Ollama. Scegli il profilo che corrisponde alla tua
macchina.

```bash
git clone https://github.com/Silver1V8/VibeCraft.git
cd VibeCraft

# Scegli UN profilo e usa lo stesso in tutti i comandi che seguono:
#   cpu          ovunque, anche senza GPU
#   gpu          NVIDIA + nvidia-container-toolkit
#   host-ollama  Ollama nativo sull'host (la scelta giusta su macOS)

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

**Perché il passo 3 usa `run --rm` e non `exec`.** Il server si rifiuta di partire finché
un indice non esiste — è una scelta deliberata, meglio non partire che servire il vuoto.
Quindi non c'è alcun container in cui entrare con `exec`: l'indicizzazione va fatta da un
container usa-e-getta, prima del primo avvio.

**Perché tre profili.** Docker su macOS non espone Metal: un modello da 9B dentro un
container gira su CPU. Lì il percorso sensato è tenere **Ollama nativo** sull'host e usare
`--profile host-ollama`, che avvia tutto il resto e punta al tuo Ollama.

I pesi dei modelli **non stanno nell'immagine**: vivono in volumi, quindi si scaricano una
volta sola e sopravvivono agli aggiornamenti.

**La console chiede la chiave, una volta sola.** Quando il browser e il server non sono
sulla stessa macchina — è il caso di Docker, dove le richieste arrivano dal gateway del
bridge e non da `127.0.0.1` — il server richiede l'autenticazione. La console se ne accorge
da sé alla prima chiamata respinta, chiede la `VIBECRAFT_API_KEY` e la conserva in questo
browser. Impostala nel servizio (`VIBECRAFT_API_KEY` in un file `.env` alla root, che
`docker compose` legge da solo) e tienila a portata al primo avvio.

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

# 1. Qdrant (vector store), su 127.0.0.1:6333
docker compose up -d

# 2. Il modello LLM locale (6,6 GB — è il download più lungo)
ollama pull qwen3.5:9b

# 3. Dipendenze Python
cd rag && uv sync

# 4. Indicizza il corpus. Al primo avvio scarica anche bge-m3 (4,3 GB).
uv run python index.py

# 5. Avvia la console
uv run python server.py       # oppure: scripts/run_server.sh
```

Poi apri **http://127.0.0.1:8000**.

Se qualcosa non parte, **chiedi al preflight invece di indovinare**: verifica versione di
Python, Qdrant, Ollama e il suo modello, spazio su disco, GPU e porta — e per ogni problema
stampa il rimedio.

```bash
cd rag && uv run python scripts/doctor.py
```

**Non serve procurarsi dei documenti per provarlo:** il repository include un corpus di
esempio di 14 documenti in `docs/` — la baseline di governance cross-progetto — quindi il
punto 4 ha già qualcosa da indicizzare e al punto 5 puoi fare la prima domanda.

`code/`, invece, arriva **vuoto**: il codice del progetto ospitante non viene distribuito.
Le funzioni che vivono sul codice (Semantic Map, Impact Ripple, il codice implementante
dentro le risposte) restano quindi spente finché non punti `code/` a un progetto vero.

## Configurazione

Tutte le variabili d'ambiente sono opzionali e documentate in
[`rag/.env.example`](rag/.env.example). Per personalizzarle:

```bash
cp rag/.env.example rag/.env.local
```

`rag/.env.local` è gitignorato e viene caricato automaticamente all'avvio.

Provider e modello LLM si scelgono in [`rag/rag_config.yaml`](rag/rag_config.yaml), anche
**per singolo step** della pipeline: si può ad esempio generare il canvas con Claude e
tenere tutto il resto su Ollama locale.

## Sicurezza

Il default è **bind su `127.0.0.1`**: raggiungibile solo da questa macchina, senza
autenticazione. È una scelta deliberata per l'uso locale.

**Se cambi `VIBECRAFT_HOST` per esporre il server in rete, imposta anche
`VIBECRAFT_API_KEY`.** Con un bind non-loopback le funzioni che hanno senso solo in locale
(selettore di cartelle nativo, scansione di un percorso arbitrario del filesystem) vengono
disattivate automaticamente — ma il resto della superficie va protetto da te.

La superficie di attacco è mappata rotta per rotta in
[`rag/SECURITY_SURFACE.md`](rag/SECURITY_SURFACE.md).

## Documentazione

| | |
|---|---|
| [`rag/README.md`](rag/README.md) | architettura, retrieval, pipeline, indicizzazione |
| [`rag/adr/`](rag/adr/README.md) | le decisioni architetturali e il perché |
| [`rag/SECURITY_SURFACE.md`](rag/SECURITY_SURFACE.md) | superficie di attacco, rotta per rotta |
| [`rag/AUDIT.md`](rag/AUDIT.md) | audit del progetto: cosa è misurato, cosa è aperto |
| [`rag/DISTRIBUTION.md`](rag/DISTRIBUTION.md) | piano di distribuzione e portabilità |
| `/infografica` (a server acceso) | il flusso di interrogazione, illustrato |

## Licenza

[Apache-2.0](LICENSE).

I pesi dei modelli scaricati a runtime (`bge-m3`, `qwen3.5`) hanno **ciascuno la propria
licenza**, indipendente da questa: verificale prima di un uso commerciale.

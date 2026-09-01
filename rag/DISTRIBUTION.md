# DISTRIBUTION — Run C: rendere vibecraft installabile

**Data:** 2026-09-01 · **Commit:** 2a83cec · **Metodo:** misure sulla macchina di sviluppo
(RTX 3070 Ti, 8 GB VRAM), non stime.

**Decisioni dell'owner, già prese e vincolanti:**
licenza **Apache-2.0** · target **uno stack Docker unico che giri ovunque**.

---

## 1. I numeri, prima del piano

| Cosa | Misura |
|---|---|
| `bge-m3` (pesi, cache HF) | **4,3 GB** |
| `qwen3.5:9b` (Ollama) | **6,6 GB** |
| `torch` build CUDA nel venv | **4,0 GB** (venv totale 4,8 GB) |
| Embedding su GPU | 46,2 chunk/s |
| Embedding su CPU | **1,0 chunk/s — 45,7× più lento** |
| Full rebuild, corpus attuale (612 elementi) | GPU ~13 s · **CPU ~10 min** |
| `/ask` a caldo | ~28 s (dominato dall'LLM, non dall'embedding) |

**Il numero che comanda tutto: ~11 GB di pesi di modello**, prima ancora di parlare di
immagini. Nessuna scelta di packaging lo riduce; può solo spostarlo fra immagine e volume.

## 2. Il vincolo che una dockerizzazione ingenua romperebbe

`api/deps.py:388` carica l'embedder con `devices="cpu"` **di proposito**, e la ragione è
scritta lì: **8 GB di VRAM non tengono `bge-m3` e `qwen3.5:9b` residenti insieme** senza
spingere l'LLM in split GPU/CPU, che lo rende molto più lento. Il progetto ha quindi già
una divisione deliberata:

- **query interattive** (`/ask`, graph query) → embedder su **CPU**: una singola embedding
  costa ~1 s, invisibile dentro i ~28 s dell'LLM;
- **job di reindex batch** → istanza dedicata su **GPU**: migliaia di chunk in batch, dove
  il 45× conta davvero.

Un `docker-compose` che desse la GPU a entrambi i servizi non "aggiungerebbe accelerazione":
farebbe contendere la VRAM e **peggiorerebbe** la latenza di `/ask`. Il compose deve
preservare la divisione, non ignorarla.

## 3. Dove "Docker unico ovunque" ha un asterisco

Va detto ora, non scoperto dopo:

| Piattaforma | App + Qdrant | Ollama |
|---|---|---|
| Linux + NVIDIA | container, GPU via `nvidia-container-toolkit` | container, GPU |
| Windows + NVIDIA (WSL2) | container, GPU | container, GPU |
| Linux/Windows senza GPU | container | container, **CPU: LLM molto lento** |
| **macOS (Intel e Apple Silicon)** | container | **container = solo CPU.** Docker su macOS non espone Metal: un 9B in container gira su CPU. Il percorso sensato è **Ollama nativo** (che usa Metal) e il container che punta all'host |

Quindi lo stack unico è vero per **app + Qdrant** ovunque; per **Ollama** serve un
interruttore fra "in compose" e "sull'host". Il codice è già pronto: `VIBECRAFT_OLLAMA_URL`
è l'unica copia dell'URL in tutto il progetto (`core/config.py`), quindi puntare a
`host.docker.internal:11434` è una variabile d'ambiente, non una modifica.

## 4. Cosa è già portabile (verificato, per non rifarlo)

- **`writer_lock` è già cross-piattaforma**: `msvcrt.locking` su Windows, `fcntl.flock` su
  POSIX, scelto a import time (`core/writer_lock.py:29-31`).
- **Nessun percorso assoluto** in `core/`, `api/`, `eval/`, entrypoint compresi.
- **Scritture atomiche** già basate su `os.replace` nella stessa directory.
- Duplicati `.sh`/`.ps1` già presenti per `ci`, `nightly_*`, `weekly_*`.

## 5. Cosa manca davvero

| | |
|---|---|
| `LICENSE` (Apache-2.0) | assente |
| `README.md` a root | assente — il repo non dice cos'è |
| `.env.example` | assente |
| `Dockerfile` | assente |
| `docker-compose.yml` | esiste ma contiene **solo Qdrant** |
| `scripts/run_server.sh` | assente (esiste solo `.ps1`) |
| `requires-python = ">=3.14"` | dichiarato; **non verificato** se sia davvero necessario |

## 6. Piano in tre livelli

Ogni livello è utilizzabile da solo.

### L1 — "clono e funziona sulla mia macchina" 

1. `LICENSE` Apache-2.0 + intestazione nel README.
2. `README.md` a root: cos'è, quickstart, e i **requisiti onesti** — ~11 GB di modelli,
   ~15 GB di disco, e le due tabelle qui sopra (piattaforme e tempi CPU/GPU). Il numero da
   dichiarare e poi misurare è **minuti dal clone alla prima risposta corretta**.
3. `.env.example` con ogni `VIBECRAFT_*` / `QDRANT_*` / `ANTHROPIC_API_KEY` documentata e i
   default sicuri (bind loopback, API key generata).
4. `scripts/run_server.sh`, gemello POSIX di `run_server.ps1`.

### L2 — "funziona sulla macchina di chiunque"

5. `Dockerfile` multi-stage, **due target**:
   - `cpu` — torch CPU (~300 MB contro 4,0 GB), multi-arch `amd64`+`arm64`;
   - `gpu` — torch CUDA, solo `amd64`, per chi ha `nvidia-container-toolkit`.
6. `docker-compose.yml` esteso con **profili**: `cpu`, `gpu`, `ollama-host`. Deve
   preservare la divisione della sezione 2 — embedder CPU per il server, GPU al solo job di
   reindex — non concederla a entrambi.
7. **Pesi in volume, non in immagine.** `bge-m3` (4,3 GB) e `qwen3.5:9b` (6,6 GB) si
   scaricano al primo avvio in volumi nominati: immagini piccole, pull ripetibili, e i pesi
   sopravvivono agli aggiornamenti. Costo: il primo avvio richiede rete e diversi minuti,
   e va mostrato con una barra di progresso, non con un terminale muto.
8. **`doctor`**: un comando che verifica porte, spazio, GPU, raggiungibilità di
   Qdrant/Ollama e dice *cosa fare* quando manca qualcosa. `GET /api/health` esiste già e ne
   è metà: manca il preflight prima che il server parta.
9. Verificare se `>=3.14` è davvero necessario. Se lo si può abbassare a 3.12 il parco
   macchine si allarga parecchio; se no, va scritto perché.

### L3 — "si può pubblicare"

10. Primo avvio guidato: scegli la cartella dei documenti → indicizza → prima domanda.
11. Aggiornamento senza perdere `database/`, e cosa succede se il formato artefatti cambia.
12. Release: tag, immagini costruite in CI, changelog, e **smoke test su clone pulito** in
    almeno due OS come gate.
13. Sicurezza del default distribuito: loopback, API key generata al primo avvio,
    istruzioni esplicite per l'esposizione in LAN **con i rischi scritti**. `SECURITY_SURFACE.md`
    è già allineato e va linkato dal README.

## 7. Rischi

- **~11 GB di modelli** sono la vera barriera d'ingresso, non l'installazione. Va scritto
  nella prima schermata del README, non a metà pagina.
- **Il percorso CPU è funzionante ma non piacevole**: 45× sull'indicizzazione. Va dichiarato
  con i numeri, non con la parola "supportato".
- **Licenze delle dipendenze**: `torch`, `FlagEmbedding`, `bge-m3` (MIT), `qwen3.5` hanno
  ciascuna la propria; vanno verificate prima di pubblicare sotto Apache-2.0. **Non
  verificato in questa sessione.**
- **Dati sensibili**: `docs/` è congelata e `rag/.env.local` è gitignorato, ma chi clona e
  ci mette i propri documenti deve sapere che l'indice e i log finiscono in `rag/database/`.

## 8. Le forcelle che restano aperte

1. ~~**Pesi in immagine o in volume?**~~ **DECISO: volume.** Immagini piccole, pull
   ripetibili, e i pesi sopravvivono agli aggiornamenti dell'immagine. Il costo accettato:
   il primo avvio richiede rete e diversi minuti, e va mostrato con un progresso visibile —
   un terminale muto per dieci minuti si legge come un blocco. L'immagine monolitica da
   ~11 GB resta l'opzione per installazioni air-gapped, non il default.
2. ~~**Corpus di esempio nel repo?**~~ **CHIUSA — c'è già.** Verificato clonando davvero il
   repo in una directory pulita: `docs/` arriva con **14 documenti**. La baseline *è* il
   corpus di esempio, e il quickstart può portare alla prima risposta senza che l'utente
   procuri nulla.

   Con un'avvertenza da scrivere nel README: `code/` in un clone pulito contiene **solo
   quattro `.gitignore`** — il codice del progetto ospitante non viene spedito, ed è
   corretto così. Quindi le funzioni che vivono sul codice (Semantic Map, Impact Ripple,
   `implementing_code` in `/ask`) partono vuote. Il quickstart arriva alla prima risposta
   **sui documenti**; quella sul codice richiede di puntare `code/` a un progetto vero.
3. **`>=3.14`: si abbassa?** Va provato, non deciso a tavolino.


---

## Stato — L1 completato (2026-09-01)

| | |
|---|---|
| `LICENSE` | Apache-2.0, copiata **verbatim** da una copia già presente fra le dipendenze invece che riscritta a memoria: verificata identica all'originale a parte la riga di copyright. Intestata a *"VibeCraft contributors"* — **da sostituire** con il titolare legale reale |
| `README.md` a root | cos'è, avvio rapido in 5 comandi, requisiti dichiarati coi numeri misurati (~11 GB di pesi, 45× CPU/GPU), sicurezza, indice della documentazione. Tutti i link interni verificati |
| `rag/.env.example` | le **17** variabili realmente lette dal codice, con default e ragione. Inventario estratto dal codice, non compilato a memoria |
| `rag/scripts/run_server.sh` | gemello POSIX di `run_server.ps1` |

**Una scelta di merito dentro L1:** `run_server.sh` **non** replica il ciclo di caricamento
di `.env.local` che il `.ps1` fa a mano. `core/config.py` lo carica già da sé con
python-dotenv, prima che qualunque modulo legga `os.environ`, e proprio perché funzioni
comunque si avvii il processo. Riprodurre quel ciclo nello script POSIX avrebbe significato
copiare complessità morta e crearne una seconda copia da tenere allineata.

**Resta da fare in L1, e non è codice:** verificare che le licenze di `torch`,
`FlagEmbedding`, `bge-m3` e `qwen3.5` siano compatibili con Apache-2.0, e decidere il
titolare del copyright — se il progetto è work-for-hire il titolare non è la persona.

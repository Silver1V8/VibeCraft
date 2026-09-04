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

---

## Audit delle licenze (2026-09-01) — un conflitto trovato e rimosso

Metodo: metadati dei **131 pacchetti realmente installati** (`*.dist-info/METADATA`:
`License-Expression`, `License`, classificatori), non le licenze dichiarate a mano.

### L'esito

| Categoria | Esito |
|---|---|
| Copyleft forte (GPL / AGPL / EUPL / SSPL) | **nessuno** — dopo la rimozione qui sotto |
| Copyleft debole (MPL-2.0) | `certifi`, `tqdm`. Compatibili con Apache-2.0: MPL è per-file e obbliga solo a pubblicare le modifiche **a quei file**, che non tocchiamo |
| Permissive | tutto il resto: MIT, BSD-2/3, Apache-2.0, PSF, ISC, Zlib, CC0, BSL |
| Senza metadati | `FlagEmbedding` — ma spedisce un file `LICENSE` che dice **MIT** (verificato) |

**Modelli** (scaricati a runtime, licenze indipendenti da quella del progetto):
`bge-m3` **MIT** (dal model card) · `qwen3.5:9b` **Apache-2.0** (da `ollama show --license`).

### Il conflitto: `pymupdf`

`pymupdf==1.28.2` era una dipendenza **diretta** di runtime, ed è
**"Dual Licensed — GNU AFFERO GPL 3.0 or Artifex Commercial License"**.

AGPL-3.0 e Apache-2.0 sono compatibili in una sola direzione: si può includere codice
Apache in un progetto AGPL, non il contrario. E VibeCraft è **un servizio di rete** —
esattamente il caso a cui punta la clausola §13 dell'AGPL. Distribuirlo sotto Apache-2.0
con quella dipendenza dentro sarebbe stato un conflitto reale, non teorico.

Verificato prima di toccare qualcosa: **nessun modulo di runtime la importa.** I PDF sono
letti da `core/chunking.py:_read_pdf` (che usa `pypdf`) e convertiti da `markitdown`. L'unico
uso in tutto il repository era `tests/test_intake_convert.py`, quattro righe per fabbricare
un PDF di una pagina bianca.

Sostituita con **`pypdfium2`** (BSD-3-Clause / Apache-2.0), già presente come transitiva e
ora dichiarata esplicitamente nel gruppo `dev` perché un test la importa direttamente.
`pymupdf` è uscita dalle dipendenze e dal lock.

**Non era solo un problema di licenza: era una dipendenza di test dichiarata come
dipendenza di runtime.** La correzione sarebbe stata giusta comunque.

### Cosa questo audit NON copre

- Le licenze sono lette dai **metadati dichiarati dai pacchetti**. Un pacchetto che dichiara
  male la propria licenza non viene smascherato da questo metodo.
- Non è una consulenza legale. Dice che non c'è copyleft forte fra le dipendenze installate;
  non certifica la conformità della distribuzione.


---

## Stato — L2 (2026-09-01): costruito, provato, e un blocco trovato

Tutto quello che segue e' stato **eseguito**, non solo scritto.

### Cosa c'e'

| | |
|---|---|
| `Dockerfile` | multi-stage, target `cpu` e `gpu`. Differiscono per la sola build di torch: il target `cpu` salta il pacchetto CUDA durante il sync (`uv sync --no-install-package torch`) e reinstalla dall'indice CPU, cosi' non paga 4,0 GB di download per poi scartarli |
| `docker-compose.yml` | profili `cpu`, `gpu`, `host-ollama`; Qdrant senza profilo perche' serve a tutti e tre. Tutti e tre validati con `docker compose --profile X config` |
| `.dockerignore` | senza, il contesto spedirebbe `rag/.venv` (4,8 GB) a ogni build |
| Pesi in volume | `vibecraft_models` (bge-m3) e `ollama_models`: immagini piccole, pesi che sopravvivono agli aggiornamenti |
| `rag/scripts/doctor.py` | preflight: Python, Qdrant, Ollama e il suo modello, spazio, cache dei pesi, GPU, porta. Ogni fallimento stampa il **rimedio**. Provato su entrambi i rami (tutto verde: exit 0; servizi giu': exit 1 coi rimedi) |

### Cosa e' stato misurato costruendo davvero

| | |
|---|---|
| `vibecraft:cpu` | **3,47 GB** — piu' grande delle attese: senza CUDA, torch scende ma lo stack ML (transformers, datasets, scipy, sklearn) resta pesante |
| Indicizzazione nel container, CPU | **11 min 17 s** per 160 chunk + 452 simboli. La stima di ~10 minuti nel README era giusta |
| Eval-gate nel container | `recall@2 = 0.873`, **identico all'host** — la build CPU di torch produce embedding equivalenti |
| Avvio del server | container `healthy`, snapshot caricato, Qdrant raggiunto |

### Il blocco: da Docker la console web non funziona

`GET /`  risponde 200, ma **ogni** `/api/*` e `/ask` rispondono **401**. Verificato dall'host
contro il container.

La causa non e' una svista di configurazione. `api/deps._is_local_request` considera locale
un client il cui indirizzo e' `127.0.0.1` o `::1`; attraverso il port forwarding di Docker le
richieste arrivano dal gateway del bridge. E la console **non invia mai `X-API-Key`** (zero
occorrenze in `templates/dashboard.unified.html`): si affida interamente al bypass su
localhost, quindi non ha un ripiego nemmeno impostando una chiave.

L'intento di sicurezza — "browser e server sulla stessa macchina, niente autenticazione" —
con `ports: 127.0.0.1:8000:8000` **e' rispettato**: solo l'host puo' raggiungere quella porta.
Ma il container non ha modo di saperlo.

**Non corretto qui: e' un cambio di autenticazione, e non spetta a un lavoro di packaging.**
Le due strade:

1. **Rendere configurabile cosa conta come "locale"** — un env con gli indirizzi fidati
   (il gateway Docker), vuoto di default cosi' il comportamento attuale non cambia. Diff
   piccolo, ma allarga la superficie: va accoppiato per iscritto al vincolo che la porta
   resti pubblicata su loopback.
2. **Far autenticare la console** — iniettare la chiave nelle pagine (il meccanismo esiste
   gia' per `/pipeline`, `deps._inject_agent_api_key`) e far inviare `X-API-Key` alle fetch.
   Piu' lavoro, tocca i template, ma non allarga niente.

**RISOLTO il 2026-09-01 con la strada 2**, scelta dall'owner: la console si autentica da
sé, e la superficie di autenticazione non è stata allargata di un millimetro.

Nessuna modifica al server. La chiave **non** viene iniettata nell'HTML per i client remoti —
sarebbe stato il modo più rapido e il più sbagliato, perché la pagina è servita senza
autenticazione e regalarla a chiunque la raggiunga avrebbe annullato il controllo che stiamo
cercando di soddisfare. La tiene il browser: l'utente la inserisce una volta e resta in
`localStorage`. L'iniezione server-side esistente (`deps.inject_agent_api_key`, solo per
client locali) resta prioritaria e invariata, quindi in locale non cambia nulla.

L'aggancio è **un wrapper su `window.fetch` in `static/shared.js`**, non 42 modifiche ai punti
di chiamata: `shared.js` è caricato nel `<head>` di ogni pagina, prima degli script che fanno
richieste. Aggiunge `X-API-Key` alle sole rotte protette e same-origin, e su 401 chiede la
chiave una volta sola e ritenta una volta sola.

Verificato in un browser vero, contro il server bindato su `0.0.0.0` e raggiunto dall'IP di
rete — stesso identico percorso di codice del gateway Docker, senza dover ricostruire
l'immagine:

| Caso | Atteso | Ottenuto |
|---|---|---|
| Prompt annullato | 401 al chiamante, nessun ciclo | 401 ✓ |
| Chiave sbagliata | un solo prompt, poi 401 | 1 prompt, 401 ✓ |
| Chiave giusta | 200 e chiave salvata | 200, salvata ✓ |
| Richiesta successiva | 200 senza chiedere nulla | 200, 0 prompt ✓ |
| `/static/*`, cross-origin | chiave NON allegata | false ✓ |

E la prova finale: la pagina `/analysis` caricata dall'IP di rete recupera
`semantic-map`, `graph/all` e `canvas-quality` — tutte **200**, dove prima era 401 su tutto —
e renderizza Semantic Map e Canvas quality con i dati reali.

**Nessun test automatico su questo codice**: `rag/` non ha un harness JavaScript, e
introdurne uno per un file solo sarebbe sproporzionato. La verifica è quella qui sopra,
eseguita in un browser reale.

### Nota minore

L'immagine contiene `docs/` cosi' com'e' nel contesto di build: da un clone pulito sono i 14
documenti della baseline, da questa macchina 23 (ci sono anche i 9 non tracciati, vedi A6).
Coerente — l'immagine rispecchia il contesto — ma va saputo prima di pubblicare un'immagine
costruita da una copia di lavoro.

---

## Stato — L3 (2026-09-01): il gate di distribuzione, e un difetto di L2 corretto

### Il difetto di L2, trovato riprendendo in mano il compose

Il `docker-compose.yml` consegnato in L2 aveva `VIBECRAFT_API_KEY: ${VIBECRAFT_API_KEY:-}`,
cioè **vuota di default**. Con la chiave assente *sul server*, `deps._valid_api_key` è falsa
per costruzione (`bool(API_KEY) and ...`): la console appena resa capace di autenticarsi
avrebbe chiesto una chiave che **nessun valore** poteva soddisfare. L2 e la correzione della
console, presi insieme, producevano ancora una console inutilizzabile.

Ora compose **si rifiuta di partire** senza la chiave, con un messaggio che dice cosa fare
(`${VIBECRAFT_API_KEY:?...}`). Verificato in entrambi i sensi: senza chiave exit 1 col
messaggio, con chiave i tre profili risolvono.

E il `.env` che il README dice di creare per contenerla **non era gitignorato**: sarebbe
bastato un `git add -A` per pubblicare la propria API key. Aggiunto a `.gitignore`.

### Il gate: un checkout pulito deve produrre un'immagine che parte

Nuovo job `docker` in `.github/workflows/ci.yml`. La suite esistente prova il codice; questo
prova **la distribuzione**, che è ciò che si rompe più facilmente, perché sulla macchina di
sviluppo funziona sempre.

| Passo | Cosa dimostra |
|---|---|
| `docker build --target cpu` | il Dockerfile costruisce da un checkout pulito |
| `python -c "import server, index"` nell'immagine | il venv dello stage dipendenze è utilizzabile e il grafo degli import regge |
| `doctor.py` deve uscire **1** e stampare il rimedio | un preflight che esce 0 a Qdrant spento non sta diagnosticando niente |
| `compose config` sui tre profili | il compose è valido, non solo sintatticamente |
| `compose config` **senza** chiave deve fallire | il difetto qui sopra non può tornare |

Tutti e cinque eseguiti su questa macchina prima di scriverli nel workflow.

Corretto anche il commento ormai falso nel job `test` ("i test che toccano un Qdrant reale si
auto-saltano"): usano `_FakeQdrant`, non si saltano — e il rovescio, che nessun test eserciti
un Qdrant vero, resta A8.

### Il job `test` esercita un Qdrant vero (2026-09-04)

`services: qdrant` con **`qdrant/qdrant:v1.19.0`** — pinnata come ogni altra versione qui, e
allineata a `qdrant-client==1.19.0` in `uv.lock`. I cinque test d'integrazione del blue/green
(alias swap, delete-by-filter attraverso l'alias, invalidazione degli alias alla
`delete_collection`) esistevano già ma **in CI saltavano sempre**, perché il job non avviava il
servizio.

Il rischio vero non era avviarlo: era che un job verde che salta tutto è indistinguibile da un
job verde che verifica. Quindi tre meccanismi invece di uno:

| Meccanismo | Contro cosa |
|---|---|
| `VIBECRAFT_REQUIRE_QDRANT=1` nell'env del job | dove il servizio è **dichiarato**, `_real_qdrant_client_or_skip` solleva invece di saltare |
| `pytest -rs` in `scripts/ci.sh` | ogni skip residuo appare col **motivo**, non come un numero in fondo |
| un passo che pretende `5 passed` e scrive una riga nel `$GITHUB_STEP_SUMMARY` | i cinque cancellati o disattivati uno alla volta |

Più un'attesa su `/readyz`: l'immagine non dichiara una `HEALTHCHECK`, quindi «container
avviato» non è «porta che risponde», e senza attesa una partenza lenta darebbe un rosso
intermittente scambiato per un difetto del codice.

Misurato in locale contro un container `v1.19.0` pinnato: Qdrant giù → `34 passed, 5 skipped`
coi motivi in chiaro; Qdrant giù **con** la variabile → `5 failed` (il gate ha portanza);
Qdrant su → `5 passed` e suite intera `1317 passed, 0 skipped`, ruff pulito.

**Osservato in CI (2026-09-04, run #131 verde):** il riepilogo del run porta la riga che il
passo di conteggio scrive — **«Qdrant reale: 5/5 test d'integrazione passati»** — e la suite
gira senza un solo `SKIPPED`, che con il servizio assente ne elencherebbe cinque.

Il run *precedente* era rosso per un difetto **pre-esistente e scorrelato**
(`test_index_rollback_succeeds_when_writer_lock_free`, introdotto da S2/`1044513`): il test si
rifaceva a mano il set di patch invece di passare dall'helper condiviso, e
`resolve_rollback_target` legge il `database/versions/` vero — quindi passava su una macchina
di sviluppo e falliva su un checkout pulito. Corretto alla radice (l'helper accetta ora un
`writer_lock=`, la duplicazione sparisce). **Questa è la CI che fa il suo mestiere:** un
difetto che nessuna esecuzione locale poteva vedere, perché in locale l'indice c'è.

### `macos-nativo`: un Mac vero, non un dry-run (2026-09-04)

Job separato su **`macos-15`** (arm64, non deprecato — `macos-14` lo è): `uv sync --frozen` in
`rag/`, poi torch importato, versione e backend stampati, e un matmul 64×64 verificato. Un
import da solo non basterebbe: una wheel per l'architettura sbagliata importa e poi esplode
alla prima operazione, ed è esattamente il divario fra il dry-run di A15 e «torch gira».

La premessa si legge dal log e non si dà per fede: la wheel è `macosx_14_0_arm64`, quindi il
primo passo stampa `sw_vers -productVersion` e `uname -m` e fallisce **col motivo giusto** se
il runner non è arm64 o è sotto la 14 — altrimenti quel rosso verrebbe letto come «su macOS
non si installa». Stampato anche `sysconfig.get_platform()` prima del sync, perché è il tag
dell'interprete a decidere se quella wheel è accettabile.

**Gira su ogni push, come gli altri due — dopo aver misurato il costo invece di stimarlo.**
L'avevo limitato a `main` + `workflow_dispatch` prevedendo ~5-8 minuti reali e quindi ~50-80
fatturati (i runner macOS costano **10×** i minuti Linux su repository privato). Il primo run
reale: **34 secondi**, ~6 minuti fatturati, contro i 2m31s di `test` e i 3m35s di `docker`.
La stima ignorava che su macOS il lock esclude **tutte** le wheel `nvidia-*` — è ciò che fa il
marcatore di A15: **130 pacchetti contro 149**, e **torch 106,1 MiB contro 804,7 MiB**; le 15
wheel `nvidia-*`/`triton`/`cuda-*` che mancano pesano da sole ~2,5 GiB. Restrizione rimossa:
limitarla ritardava fino al merge la scoperta di una rottura del lock, senza risparmiare nulla.
E il tempo non veniva da una cache calda — il log mostra `Cache Size: ~0 MB (1610 B)` e poi il
download effettivo di tutti e 130 i pacchetti.

**Dal log, che è il punto di N6:**

```
runner: macOS 15.7.9 su arm64      platform tag: macosx-15.0-arm64
torch : 2.13.0   (senza "+cu")     mps: True (built: True)
matmul su : mps -> 262144.0
```

Il matmul è girato **su Metal**, non su CPU: il job non lo pretendeva, ma il risultato è che
su Apple Silicon torch non solo si installa — calcola sull'acceleratore.

**Un limite da dichiarare.** Il log dice
`Using CPython 3.14.7 interpreter at: /opt/homebrew/opt/python@3.14/bin/python3.14`: uv ha
usato il Python di Homebrew presente nell'immagine, e da lì il tag è nativo
(`macosx-15.0-arm64`). Con una CPython **gestita da uv** il tag verrebbe dal
`MACOSX_DEPLOYMENT_TARGET` con cui quella build è compilata, che è conservativo — l'artefatto
che A15 aveva incontrato nel dry-run — e una wheel `macosx_14_0` verrebbe rifiutata. Il job
stampa il tag proprio perché quel giorno il fallimento sia leggibile, ma **quel ramo non è
coperto**: un utente Mac che parta senza un Python di sistema può ancora incontrarlo.

### Aggiornamento senza perdere l'indice

Documentato nel README con i tre casi in ordine di costo: solo documenti ⇒ incrementale;
modello di embedding cambiato ⇒ full rebuild obbligatorio (il manifest registra il modello,
quindi la differenza è rilevabile e non silenziosa); formato artefatti cambiato ⇒
`load_artifacts` ricade sui `.pkl` con un warning esplicito. Più il rollback blue/green, che
è il ritorno indietro senza reindicizzare.

### Cosa di L3 NON è stato fatto, e perché

- **Pubblicazione delle immagini (release workflow).** Richiede decisioni che non spettano al
  codice: quale registry, immagini pubbliche o private, quali tag, e se pubblicare anche il
  target `gpu`. Un workflow scritto a indovinare non sarebbe verificabile qui e andrebbe
  comunque riscritto. **Da decidere.**
- **Smoke test su un secondo sistema operativo.** Il job `docker` è il test da clone pulito e
  copre il percorso di distribuzione principale. Una matrice su `windows-latest` per il
  percorso nativo scaricherebbe ~4 GB di torch CUDA a ogni push: sproporzionato come gate.
  Il progetto è sviluppato su Windows e testato in CI su Linux, quindi entrambi i sistemi
  sono coperti — ma non entrambi automaticamente. **Gap dichiarato.**
- ~~**Installazione nativa su macOS: risolta, non eseguita.**~~ **Coperta il 2026-09-04**
  dal job `macos-nativo` descritto sopra: `uv sync --frozen` vero su un runner Apple
  Silicon, torch importato e un matmul verificato. Resta una distinzione onesta: il job è
  **implementato, non ancora osservato** — nessun run su GitHub Actions è stato letto da
  qui, e la scelta del runner è verificata sulla documentazione delle immagini. macOS Intel
  resta impossibile a monte (PyTorch non pubblica quelle wheel).
- **Primo avvio guidato** (scegli la cartella → indicizza → prima domanda). È una funzionalità
  di prodotto, non di packaging: il README oggi porta allo stesso risultato in quattro
  comandi. **Non iniziato.**

---

## Pubblicazione delle immagini, e un difetto grosso trovato indagando la CI

### Perché la CI falliva (ipotesi forte, non certezza)

Il repository è privato e in questa sessione non c'era modo di leggere i log delle Actions
(`gh` non installato, connettore GitHub non autorizzato). Quindi la causa **non è
confermata**: quello che segue è ciò che ho trovato riproducendo la CI in locale.

Il job `test` **non è il problema**: la suite passa contro un export dei soli file tracciati
(`git archive HEAD`, 14 documenti in `docs/`), cioè esattamente ciò che vede un checkout CI.

Il job `docker`, nuovo dell'ultimo push, costruisce un'immagine che si è rivelata enorme —
e la ragione era un difetto vero nel Dockerfile.

### Il difetto: l'immagine "CPU" conteneva 4,3 GB di CUDA

`uv sync --no-install-package torch` salta **torch**, non la sua chiusura di dipendenze.
`uv.lock` pinna la build CUDA, quindi le 15 `nvidia-*-cu12` e `triton` restavano fra le
dipendenze e venivano installate lo stesso — dentro un'immagine il cui torch è `+cpu` e non
le userà mai:

| | Prima | Dopo |
|---|---|---|
| venv nell'immagine | **6,4 GB** | **2,2 GB** |
| pacchetti CUDA | 16 | **0** |
| layer `code/` | 90,6 MB | **1,45 MB** |
| torch | 2.14.0+cpu (**non pinnato**) | 2.13.0+cpu (= `uv.lock`) |

Su un runner GitHub con ~14 GB liberi, costruire quell'immagine è un ottimo modo per
esaurire il disco. Le correzioni:

- **esclusa l'intera chiusura CUDA**, non solo torch (lista esplicita: uv non accetta pattern);
- **pinnata la versione di torch** a quella del lock. Senza pin `uv pip install torch` prendeva
  l'ultima disponibile sull'indice CPU, e l'immagine aveva smesso di essere riproducibile
  senza che nulla lo segnalasse — il lock diceva 2.13.0, l'immagine montava 2.14.0;
- **escluse da `code/` le stesse directory che l'indicizzatore già scarta**
  (`CODE_EXCLUDED_DIRS`): 90 MB di sorgenti .NET locali finivano nell'immagine da una build
  sul working tree (in un checkout pulito `code/` è vuota, quindi la CI non lo vedeva);
- aggiunta al job `docker` la **liberazione di spazio sul runner**, rimedio standard e
  gratuito per il caso "no space left on device".

### Come si pubblicano le immagini — decisioni prese

`.github/workflows/release.yml`, su **tag `v*`**.

| Decisione | Perché |
|---|---|
| **GHCR** (`ghcr.io/silver1v8/vibecraft`) | stesso account del repository, si autentica col `GITHUB_TOKEN` già disponibile — nessun segreto da creare e ruotare — e le immagini stanno accanto al codice |
| **Su tag, non su ogni push** | un'immagine per commit brucia storage senza che nessuno la usi; ciò che ha senso pubblicare è una versione citabile |
| **Solo il target `cpu`** | gira ovunque, GPU o no. Il target `gpu` porta ~4,3 GB di CUDA: pubblicarlo costa storage e banda a chi lo scarica, e chi ha una GPU ha per definizione la macchina per costruirselo con un comando |
| **Solo `linux/amd64`** | arm64 servirebbe ad Apple Silicon, ma su runner x86 andrebbe emulato in QEMU: per questo stack significa ore. Su Apple Silicon la build locale è nativa e veloce, quindi il rapporto è rovesciato. Da riconsiderare se il repository diventa pubblico e ottiene i runner ARM gratuiti |
| Tag `{{version}}`, `{{major}}.{{minor}}`, `latest` | convenzione standard |

**Il repository è privato, quindi il pacchetto GHCR nasce privato.** Per renderlo scaricabile
senza credenziali va reso pubblico dalle impostazioni del package su GitHub. Il workflow lo
ricorda nel proprio riepilogo di esecuzione.

**Non verificato:** il workflow di release non è mai stato eseguito. Il `docker build` che
contiene sì, ripetutamente, su questa macchina; l'orchestrazione GitHub no. Il primo tag lo
dirà.

### Prima release: `v0.1.0` (2026-09-01)

Tag annotato `v0.1.0` creato su `a716f48` e pubblicato: è l'evento che innesca
`release.yml`, quindi la build e il push dell'immagine su GHCR sono **partiti**.

Due correzioni al workflow **prima** del tag, entrambe su cose che si sarebbero viste solo
fallendo:

- **nome dell'immagine in minuscolo.** GHCR accetta solo minuscole nel path del pacchetto, e
  `github.repository` qui è `Silver1V8/VibeCraft`. `metadata-action` normalizza da sé, ma
  dedurre la correttezza da un comportamento implicito è esattamente ciò che si scopre quando
  il workflow fallisce: ora il nome si calcola in uno step e si legge nei log;
- **`cache-to` da `mode=max` a `mode=min`.** L'immagine pesa ~2,3 GB e la cache Actions è
  10 GB per repository: esportare anche i layer intermedi la riempirebbe da sola, sfrattando
  la cache di tutto il resto.

**Non confermato che la pubblicazione sia riuscita.** Il repository è privato e da qui non
c'è modo di leggere l'esito: un pull anonimo risponde `denied` e il manifest `401` sia che il
pacchetto esista e sia privato, sia che non esista affatto. Le due cose non sono
distinguibili dall'esterno.

Cosa guardare, in ordine:

1. la scheda **Actions** del repository, workflow *Release*, run sul tag `v0.1.0`;
2. a run riuscito, il pacchetto compare sotto **Packages** del profilo GitHub;
3. il pacchetto nasce **privato**, come il repository. Per renderlo scaricabile senza
   credenziali va reso pubblico dalle sue impostazioni (*Package settings → Change
   visibility*). Il workflow lo ricorda nel proprio riepilogo di esecuzione.

Con le credenziali, il controllo è:

```bash
echo $GITHUB_TOKEN | docker login ghcr.io -u <utente> --password-stdin
docker pull ghcr.io/silver1v8/vibecraft:v0.1.0
```

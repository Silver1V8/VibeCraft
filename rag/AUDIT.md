# AUDIT — Run A: inventario

**Data:** 2026-09-01 · **Commit:** b1ef300 · **Metodo:** lettura dei flussi + misura con
gli strumenti del progetto (`pytest`, `eval/run.py`, `eval/run_multihop.py`, `/api/health`,
`/ask` dal vivo, `observe_docs_git_divergence`).

**Contratto di questo documento:** contiene solo RISCONTRI, non soluzioni. Ogni riga è
ancorata a un file:linea o all'output di un comando eseguito. Le proposte sono compito
della Run B, che legge questo file.

**Ambiente della misura:** Qdrant server-mode attivo (5 collection versionate), Ollama
`qwen3.5:9b` attivo, indice `v20260825T100624` — 847 nodi, 1133 archi, 181 chunk,
452 simboli di codice.

---

## Verdetto

Il sistema è **solido nel nucleo e cieco sul proprio metro di misura**.

Ciò che regge davvero, misurato: 1253 test verdi senza un solo skip; integrità
dell'indice perfetta (181/181 chunk con vettore ColBERT, delta Qdrant↔sidecar = 0);
router deterministico con 0 falsi positivi su 55 casi; e — la verifica più importante per
un RAG di governance — **l'astensione funziona**: a una domanda plausibile ma assente dal
corpus il sistema rifiuta di rispondere, motiva il rifiuto e cita la regola che lo impone,
invece di inventare.

I tre rischi che lo rendono "non completo":

1. **Il guardrail sul contesto è un log, non un limite.** Dentro il contratto dichiarato
   dell'API (`top_k ≤ 50`) si costruisce un prompt di ~30.939 token stimati contro
   `num_ctx=16384`: Ollama tronca dall'alto in silenzio, e la risposta HTTP resta
   `status: "success"` senza alcun segnale al chiamante. È la stessa classe di difetto che
   il progetto ha già documentato e curato alzando `num_ctx` — ma la cura non tiene un
   parametro controllato dal chiamante. *Precisazione dopo la verifica:* alla console
   l'utente si ferma a `top_k=20` (81% della finestra, warning acceso, nessun troncamento),
   perché un attributo HTML glielo impedisce. Il difetto non è che gli utenti vengano
   troncati oggi: è che l'unico argine fra i due regimi è validazione lato client.
2. **Lo strumento di misura non vede sempre ciò che misura.** `GET /api/retrieve` — su cui
   gira *tutto* l'harness di eval — è l'unica route di retrieval che non ricarica lo
   snapshot: dopo una promozione misura uno stato misto (Qdrant nuovo, sidecar vecchi) e lo
   fa in silenzio. Oggi è andata bene per caso — la modifica era una cancellazione pura, e i
   chunk nuovi erano un sottoinsieme dei vecchi; su un'aggiunta si sarebbe composto con
   l'inversione di ranking di A7. Il gate, invece,
   è sano: sta a recall@2 con soglia 0.75 (*correzione: la mia prima lettura diceva k=10 e
   0.90 — erano i default del codice, non la configurazione attiva*). Ma trend, rilevamento
   di regressione e il numero in evidenza su `/api/health` guardano ancora recall@10, che è
   saturo a 1.000. E un segnale che discrimina resta non sorvegliato da nessuno: sul
   sottoinsieme avversariale **recall@1 = 0.0%**, invariato anche dopo la pulizia del corpus.
3. **I numeri non sono riproducibili da nessun altro.** Il corpus indicizzato è 26
   documenti, quelli tracciati da git sono 11 — esattamente gli "11 documenti" che il
   golden set dichiara come corpus di riferimento. Il rilevatore di divergenza riporta
   `diverging: []` perché per costruzione non guarda le aggiunte non tracciate. Chiunque
   cloni il repo — CI compresa — misura su meno di metà corpus; e l'11% dei chunk indicizzati
   appartiene ai tre documenti che il golden set dà per rimossi.

---

## Inventario

| ID | Asse | Tipo | Evidenza | Impatto se non risolto | Sforzo | Verifica di chiusura |
|---|---|---|---|---|---|---|
| A1 | LLM / contesto | FRAGILE | Serie misurata (stessa domanda, stima 3 char/token del guard): `top_k=10` → 7.775 tok · `=15` → 10.755 · `=20` → 13.275 (**soglia di warning superata**, 81% di `num_ctx=16384`) · `=50` → 30.939 tok, **oltre il doppio**, con log `core.llm` e risposta HTTP comunque `status:"success"`. Guard a `core/llm.py:66-76` (solo `logger.warning`). Tetti: `ASK_MAX_CHARS_PER_CHUNK=3000` (`api/routes_retrieval.py:49`) × `top_k≤50` (`api/models.py:9`). **Unica barriera reale fra i due regimi: l'attributo HTML `max="20"` a `templates/dashboard.unified.html:385`** — validazione lato client | Al massimo che la console stessa offre il margine residuo è del 19%; oltre — bypassando un attributo HTML, o semplicemente con sezioni più piene — il prompt è tagliato dall'alto e la risposta resta `success` | S | Il limite vive nel server, non nell'HTML; una richiesta che eccede la finestra non può concludersi con `status:"success"` silenzioso |
| A2 | ~~Eval / gate~~ | ~~FRAGILE~~ → **RITIRATO** | **Riscontro sbagliato.** Avevo letto i *default* del codice (`_eval_gate_cfg.get("k", 10)`, `core/config.py:346-347`) scambiandoli per la configurazione attiva. `rag_config.yaml` imposta `k: 2`, `min_recall: 0.75`, `blocking: true`, e documenta una migrazione deliberata k=10 → k=5 → k=2, ogni passo innescato dall'**alert di saturazione del progetto stesso**. Provato dal rebuild eseguito oggi: `Eval-gate: recall@2=0.873 ≥ soglia 0.75 — promozione consentita` | Nessuno: il gate fa già ciò che avrei raccomandato, e con una soglia derivata dal proprio storico | — | — |
| A2b | Eval / osservabilità | FRAGILE | Ciò che resta di A2, ed è vero: il **gate** è a k=2, ma tutto il resto guarda ancora il k saturo. `core/eval_history.py:73,79,95` — `latest_recall`, `compute_trend`, `detect_regression` hanno tutte `key="recall@10"` come default; `/api/health` espone `last_recall_at_10: 1.0` come numero di qualità in evidenza | Il cancello protegge, ma il rilevatore di regressione e il numero che un umano legge sulla dashboard stanno su una metrica satura a 1.000: la promozione è difesa, la deriva lenta no | S | Trend e rilevamento di regressione leggono la stessa metrica del gate |
| A3 | Retrieval / qualità | MANCANTE | `eval/run.py`: sottoinsieme avversariale (5 casi) recall@1 = **0.0%**, MRR 0.467. Aggregato: recall@1 61.8%, recall@2 83.6%, recall@5 98.2%, MRR 0.773 | Sui casi costruiti apposta per testare l'autorità (ADR 0002) la fonte giusta non è **mai** prima. Nessuna metrica sorvegliata lo espone | M | recall@1 avversariale tracciata nello storico e sotto soglia |
| A4 | Retrieval / multihop | FRAGILE | `eval/run_multihop.py`: 5 casi su 14 falliscono a k=10, recall media A = 0.854, A riusciti 9/14. Nessun gate su questa suite | La classe di domande più preziosa per un grafo di governance regredisce senza allarme | M | La suite multihop entra nello storico e ha una soglia |
| A5 | ~~Eval / strumento~~ | ~~FRAGILE~~ → **RITIRATO, assorbito da A6** | **Riscontro impreciso.** Avevo concluso "l'harness sottostima il ramo grafo" vedendo una risposta corretta segnata come fallita. Leggendo `eval/golden_multihop.yaml:90-96`: il caso dichiara `count: 11` — la baseline committata — e i 4 nodi attesi ci sono tutti. L'unico scarto è il conteggio (26, poi 23, contro 11). **L'harness ha ragione: sta segnalando che il corpus è divergente.** Non è un difetto della misura, è la misura che funziona | Nessuno di per sé: è A6 che parla | — | — |
| A6 | Corpus / riproducibilità | FRAGILE | 26 `.md` su disco vs **11 tracciati** (i 13 path di `git ls-files docs` includono 2 `.gitkeep`); `observe_docs_git_divergence()` → `{state:"instantiated", diverging:[], tracked:13}`; `.gitignore:docs/*` (scelta deliberata). Fra i 15 non tracciati, tre — `glossario_entita.md`, `matrice_permessi.md`, `intent_synonym_mapping.md` — sono **gli stessi che il golden set elenca come "documenti poi rimossi"**: valgono 21 chunk su 181 (**11% del corpus**) | Oltre metà del corpus è invisibile a chi rivede il repo e alla CI; l'11% è dominio dismesso che compete in ogni retrieval; nessun numero di qualità è riproducibile fuori da questa macchina | M | Un clone pulito riproduce le metriche dichiarate, o la differenza è dichiarata ed è visibile |
| A7 | Retrieval / ranking | FRAGILE (latente) | `core/retrieval.py:135-152`: nel ramo misto, un chunk con `colbert_score=None` pesa `-1.0 × (1-α+α·autorità)` — **più è autorevole, più scende**. Oggi irraggiungibile (copertura ColBERT 181/181), ma `retrieval.py:281` tollera esplicitamente il `None` | Sotto divergenza sidecar↔Qdrant il ranking si inverte proprio sulle fonti normative, in silenzio | S | Test sul ramo misto che fissa il comportamento atteso |
| A8 | Test / copertura | MANCANTE | 1253 test, **0 skip** con Qdrant attivo ⇒ nessun test tocca un Qdrant reale; `tests/test_qdrant_blue_green.py:42-131` usa `_FakeQdrant`. Il commento in `.github/workflows/ci.yml` ("i test che toccano un Qdrant reale si auto-saltano") è **superato** | Alias swap, delete-by-filter, GC e rollback sono validati solo contro un finto scritto dallo stesso autore: un disallineamento con la semantica reale di Qdrant non è rilevabile | M | Almeno un test di integrazione contro Qdrant vero, saltato in modo esplicito quando assente |
| A9 | CI / qualità | MANCANTE | `pyproject.toml`, `pytest.ini`, `ci.yml`: nessun ruff/mypy/coverage | Su 37.5k righe, regressioni di stile e di tipo passano; la copertura reale è ignota | S | Un linter gira in CI e fallisce su una violazione introdotta apposta |
| A10 | ~~Sicurezza / doc~~ | ~~FRAGILE~~ → **RITIRATO** | **Riscontro sbagliato.** Lo scarto di 19 giorni fra i commit era un indizio, non una prova, e l'ho riportato come sospetto: la riconciliazione riga-per-riga (B5, eseguita) dice che il documento è **allineato**. Le 57 route del codice sono tutte in tabella — `GET /` è la riga 1 (`SECURITY_SURFACE.md:118`) — e le 7 che sembravano "documentate ma assenti" sono le auto-route di FastAPI (`/docs`, `/redoc`, `/openapi.json`, `/docs/oauth2-redirect`) e il mount statico, che il documento conta esplicitamente a `:33`. Il mio grep sui decoratori `@router` non poteva vederle: il documento era più completo del mio strumento | Nessuno | — | — |
| A11 | Prestazioni | FRAGILE | `/ask` misurato: 96.4 s a freddo, 28.6 s a caldo (`top_k=50`). Nessuno streaming, nessun budget di latenza esposto | Un'attesa di 30 s senza feedback è indistinguibile da un blocco | M | Latenza p95 misurata e dichiarata, o feedback incrementale |
| A12 | Codice / debito | SUPERFLUO | 6 `TODO(2026-07-12)` scaduti da 51 giorni, fra cui `code_index/__init__.py:164` *"rimuovere `_js_symbols` e i default regex alla prossima release"* — ancora presenti a `:133` e `:290` | Il debito dichiarato con una data e ignorato smette di essere un piano | S | I TODO scaduti sono chiusi o ridatati con una ragione |
| A13 | Codice / legacy | SUPERFLUO | `core/artifacts.py:35` importa `pickle` per il solo ramo di lettura legacy (`:14-15`) | Un formato di deserializzazione arbitraria mantenuto per una retrocompatibilità di cui nessuno ha più bisogno | S | Verificato che nessun `.pkl` esiste più, ramo rimosso |
| A14 | Distribuzione | MANCANTE | A root: nessun `README.md`, `LICENSE`, `.env.example`, `Dockerfile` | Chi clona il repo non sa cos'è, se può usarlo, né come configurarlo | S | Un clone pulito arriva alla prima risposta seguendo solo il README |
| A15 | Portabilità | MANCANTE | `pyproject.toml:39-43`: `torch` pinnato su indice esplicito `pytorch-cu126`; `requires-python = ">=3.14"`; `scripts/run_server.ps1` non ha gemello POSIX (a differenza di `ci`, `nightly_*`, `weekly_*`) | Installazione impossibile su macOS, ARM e macchine CPU-only; su Linux manca l'avvio del server | M | `uv sync` riesce su una macchina senza NVIDIA e il server si avvia |
| A18 | Eval / strumento | **MANCANTE** | Trovato eseguendo B1, e provato in isolamento: `GET /api/retrieve` è **l'unica route di retrieval che non chiama `maybe_reload_graph()`** (`api/routes_retrieval.py:493`, da confrontare con `:88` di `/ask` e `:586` di `/api/code/search`, più le 4 di `routes_graph`). Dimostrazione: dopo una promozione, `/api/health` → `v20260825T100624, 181 chunk`; una chiamata a `/api/retrieve` la lascia **invariata**; una a `/ask` la porta a `v20260901T101536, 160 chunk` | **L'harness di eval interroga solo `/api/retrieve`.** Dopo una promozione o un rollback misura uno stato MISTO — alias Qdrant nuovo, sidecar ColBERT/chunk in memoria vecchi — e lo fa in silenzio. **Quanto sia grave dipende dal tipo di modifica, e la differenza non è visibile a occhio:** su una CANCELLAZIONE pura (il caso di B1) i chunk nuovi sono un sottoinsieme dei vecchi — verificato, 0 chunk_id non coperti — quindi il sidecar stantìo li copre tutti e la misura resta corretta per fortuna, non per costruzione. Su un'AGGIUNTA o una MODIFICA i chunk_id nuovi mancano dal sidecar, `colbert_maxsim` restituisce `None` — **ed è esattamente l'input che innesca l'inversione di ranking di A7**. I due riscontri si compongono | S | Dopo una promozione, `/api/retrieve` serve la stessa versione di `/ask` |
| A17 | Documentazione | FRAGILE | `templates/infografica.unified.html:296` descrive come attivo un *"budget guard giornaliero sulla spesa Claude [che] devia automaticamente su Ollama"*; in `rag_config.yaml:74-84` l'intero blocco `budget:` è **commentato**, quindi il guard è spento | L'infografica è il documento che spiega il sistema a chi non lo conosce: descrive una protezione di costo che non esiste | S | O il blocco è attivo, o l'infografica dice che è opzionale e spento |
| A16 | API / contratto | FRAGILE | Misurato: alla domanda fuori corpus la risposta è un rifiuto corretto e motivato, ma il payload resta `status:"success"` con 5 fonti elencate | Un client non può distinguere "ha risposto" da "si è astenuto": l'astensione, che è la funzione di sicurezza, non è leggibile a macchina | S | Uno stato distinto (o un campo) per la risposta astenuta |

**Conteggio:** 17 riscontri — 3 MANCANTE su capacità promesse (A3, A8, A9), 2 MANCANTE su
distribuzione (A14, A15), 9 FRAGILE, 2 SUPERFLUO, 1 FRAGILE latente.

---

## Ciò che NON è un problema (verificato, per non farlo ricontrollare alla Run B)

- **Integrità dell'indice**: 181 chunk, 181 vettori ColBERT, 181 punti Qdrant sull'alias
  `vibecraft_events` — delta 0. Nessun orfano, nessun chunk scoperto.
- **Astensione**: verificata dal vivo su una domanda fuori corpus. Il rifiuto è corretto,
  motivato e cita la regola. (Il difetto è solo la sua non-leggibilità a macchina — A16.)
- **Falsi positivi del router**: 0 su 55 casi del golden set, come dichiarato.
- **Suite di test**: 1253 test, 0 fallimenti, 0 skip.
- **Rilevamento del troncamento**: esiste ed è corretto (`core/llm.py:66-76`) — manca
  l'azione, non la diagnosi.

---

## Domande aperte — risolte per misura

### 1. I documenti non tracciati: residui o corpus di lavoro? → **Entrambi, e vanno separati**

Su disco 26 `.md`, di cui **11 tracciati** (i 13 path di `git ls-files` includono 2
`.gitkeep`) — cioè esattamente gli "11 documenti" che l'intestazione del golden set
dichiara come corpus di riferimento. I 15 non tracciati si dividono in tre gruppi:

| Gruppo | File | Verdetto |
|---|---|---|
| **Residui del dominio dismesso** | `glossario_entita.md` (491 righe, 98 occorrenze del dominio "eventi"), `matrice_permessi.md` (494, 98), `intent_synonym_mapping.md` (179, 52) | **Sono i tre nomi che il golden set elenca come "documenti poi rimossi".** Non sono stati rimossi: sono ancora indicizzati, **21 chunk su 181 = 11% del corpus** |
| Output della pipeline | `fe1-4`, `la1-2` `-canvas-review.md` | Legittimi: artefatti di run |
| Locali per progetto ospitante | `05_project_specs/spec_tech_*.md` (3) | Legittimi: `.gitignore` li esclude di proposito |

Restano da classificare a mano `change_log.md` e `architecture_decision_rationale.md`
(contaminazione lieve: 3 e 1 occorrenze). **Conseguenza operativa:** l'11% del corpus è
dominio morto che compete in ogni retrieval — e spiega perché la prova di astensione ha
recuperato `EVENTO`/`RICHIESTA`.

### 2. Chi usa `top_k` alto? → **Nessuno. Il contratto è più largo di ogni chiamante**

| Chiamante | `top_k` |
|---|---|
| Console (`dashboard.unified.html:385`) | default 5, `max="20"` — **solo lato client** |
| `scripts/bench.py:129` | non lo passa → default 5 |
| `agent_bridge.py` | non chiama `/ask` |
| `eval/run.py:112` | usa `/api/retrieve`, non `/ask` |

Il contratto server ammette 50, il consumo reale non supera 20. **A1 si chiude
restringendo il limite server**, non costruendo un potatore di contesto: il caso "serve k
alto" non esiste.

### 3. Il gate deve bloccare o avvisare? → **Bloccare, ma a k=2, e non ancora oggi**

Dai 77 punti di `history.jsonl`:

| Metrica | punti | range | σ | Distanza dalla soglia 0.90 |
|---|---|---|---|---|
| recall@10 (gate attuale) | 73 | 0.959–1.000 | 0.015 | **6σ — 61 gate su 61 passati** |
| recall@5 | 12 | 0.912–1.000 | 0.028 | ~0.4σ dal tetto |
| **recall@2** | 11 | 0.763–0.836 | 0.024 | lontana dai due estremi |
| recall@1 | 10 | 0.475–0.618 | 0.055 | varianza 3,7× recall@10 |

**recall@2 è il candidato giusto**: massimo segnale con varianza ancora contenuta.
recall@1 varia troppo (σ=0.055 su 10 punti) per una soglia fissa: bloccherebbe per rumore.
Ma **11 punti non bastano per fissare un pavimento**: la sequenza corretta è registrare
recall@1/@2 a ogni run per qualche settimana, poi rendere bloccante recall@2 a un
pavimento derivato dallo storico (ordine di grandezza: media − 2σ ≈ 0.74), tenendo
recall@10 come segnale advisory. Nel frattempo il gate resta com'è: **non protegge, ma
non danneggia.**

### 4. Corpus di riferimento per l'eval → **discende dalla risposta 1**

Gli 11 documenti tracciati sono già il riferimento dichiarato. Serve solo che l'indice
misurato coincida con essi, oppure che la differenza sia registrata nel report di eval.

---

## Da decidere prima della Run C (distribuzione)

Licenza · matrice dei device supportati · Ollama impacchettato o prerequisito · corpus di
esempio da spedire nel repo.

---
---

# Run B — piano

Ordinato per impatto ÷ sforzo. **Ma l'ordine ha un vincolo che viene prima del rapporto:**
B1 cambia i numeri di A3, A4 e A5. Farlo per secondo significa misurare due volte e
decidere soglie su dati che stanno per cambiare. Quindi B1 è primo non perché sia il più
grave, ma perché **tutto il resto lo presuppone**.

## I primi cinque

### B1 — Separare il corpus vivo dal dominio dismesso *(chiude A6, sblocca A3/A4/A5)*

**Causa:** tre documenti che la storia del progetto dà per rimossi sono ancora indicizzati
e valgono l'11% dei chunk. Ogni retrieval li vede; ogni metrica li include.

**Intervento minimo:** spostare `glossario_entita.md`, `matrice_permessi.md`,
`intent_synonym_mapping.md` fuori da `docs/`, poi full rebuild + promote.

> ⚠️ **Non sono tracciati da git: cancellarli è irreversibile.** Vanno *spostati* in
> `docs.local-backup-<timestamp>/` — la convenzione esiste già a root — mai `rm`.
> Prima di spostarli va deciso a mano il destino di `change_log.md` e
> `architecture_decision_rationale.md` (contaminazione lieve: 3 e 1 occorrenze).

**File toccati:** nessun file di codice. `docs/` e l'indice.
**Verifica:** dopo il rebuild, `chunks` scende da 181 a ~160 e `eval/run.py` gira senza che
nessun caso attinga ai tre documenti. Le metriche vanno **ri-registrate**: quelle di oggi
non sono confrontabili con quelle di domani, e va scritto nel report.

### B2 — Portare il limite di `top_k` dal client al server *(chiude A1)*

**Causa:** il contratto server ammette 50, ogni chiamante reale sta ≤ 20, e l'unico argine
è `max="20"` in un attributo HTML.

**Intervento minimo:** `api/models.py:9` — `top_k: int = Field(default=5, ge=1, le=20)`.
Una riga. Non serve un potatore di contesto: la verifica ha stabilito che il caso d'uso
"k alto" non esiste.

**File toccati:** `api/models.py` (+ un test).
**Test che oggi fallirebbe:** `POST /ask` con `top_k=50` deve rispondere `422`, non `200`.
Oggi risponde `200` con un prompt da ~31k token su una finestra da 16k.

**Ceiling dichiarato:** resta il caso "corpus con sezioni più piene": a parità di k il
contesto cresce. Il limite a 20 lascia il 19% di margine misurato *su questo corpus*. Se
i documenti si allungano, la protezione giusta diventa il budget di token — ma è lavoro da
fare quando la misura lo mostra, non ora.

### B3 — Registrare le metriche che discriminano *(prepara A2, misura A3)*

**Causa:** il gate vive a k=10 dove σ=0.015 e 61 valutazioni su 61 sono passate. I k bassi
hanno segnale ma solo 10-12 punti storici: **non c'è ancora abbastanza storia per fissare
un pavimento onesto.**

**Intervento minimo:** far sì che ogni run scriva `recall@1`, `recall@2` **e la recall@1
del sottoinsieme avversariale** in `history.jsonl`. Nessun cambio di soglia adesso.

**File toccati:** `eval/run.py`, `core/eval_history.py`.
**Verifica:** dopo N run, `history.jsonl` ha le tre serie complete.
**Poi** (non ora): recall@2 diventa bloccante a un pavimento derivato dallo storico
— ordine di grandezza media − 2σ ≈ 0.74 — e recall@10 scende ad advisory.

### B4 — Correggere l'harness multihop sul ramo grafo *(chiude A5)*

**Causa:** `quali documenti esistono nel corpus?` è segnato fallito da entrambi i rami,
ma dal vivo il grafo risponde correttamente con tutti i 26 documenti. Lo strumento
sbaglia, non il sistema.

**File toccati:** `eval/run_multihop.py` (valutazione del ramo B).
**Test che oggi fallirebbe:** il caso risulta superato senza toccare il codice di
produzione. Va fatto **dopo B1**, perché il numero atteso di documenti cambia.

### B5 — Riconciliare `SECURITY_SURFACE.md` con le route reali *(chiude A10)*

**Causa:** il documento è fermo al 2026-08-05, `api/` è cambiata fino al 2026-08-24. Per
un file che descrive la superficie d'attacco, "probabilmente aggiornato" non è uno stato
accettabile.

**Intervento minimo:** confronto riga-per-riga fra i 57 decoratori route e la tabella.
**Verifica:** ogni route del codice ha una riga, ogni riga una route.

## Il resto, in ordine

| # | Cosa | Chiude | Sforzo |
|---|---|---|---|
| B6 | Un test di integrazione contro Qdrant vero, con skip esplicito quando assente; correggere il commento ora falso in `ci.yml` | A8 | M |
| B7 | `ruff` in CI (solo il linter: `mypy` su 37.5k righe non annotate è un progetto a sé) | A9 | S |
| B8 | Infografica: dire che il budget guard è opzionale e **spento**, o attivarlo | A17 | S |
| B9 | Stato distinto per la risposta astenuta, così è leggibile a macchina | A16 | S |
| B10 | Test sul ramo misto di `rank_by_authority` che fissa il comportamento con `colbert_score=None` | A7 | S |
| B11 | **Cancellare:** `_js_symbols` + default regex (TODO scaduto da 51 giorni), ramo di lettura pickle in `artifacts.py`, i 6 TODO datati | A12, A13 | S |
| B12 | Latenza: misurare p95 e decidere se serve feedback incrementale | A11 | M |

A14 e A15 (distribuzione e portabilità) non sono qui: sono la **Run C**.

## Cosa NON fare

- **Non** costruire un potatore di token per A1: la misura dice che non serve (B2).
- **Non** ritarare l'autorità sul golden set attuale: è satura a k≥5 e sta per cambiare
  corpus (B1). Ritarare adesso significa inseguire rumore — è l'errore che l'ADR 0002
  documenta già come "il rovescio del metodo".
- **Non** toccare le soglie del gate finché B3 non ha prodotto storia (≥ 20 punti).
- **Non** spezzare `core/indexing.py` (2.264 righe): è grande, ma nessuna misura lo indica
  come problema. Grande ≠ sbagliato.

---
---

# Run B — esecuzione (2026-09-01)

## B1 — Corpus separato dal dominio dismesso ✅

Spostati in `docs.local-backup-20260901T121519/` (mai `rm`: non erano tracciati da git,
cancellarli sarebbe stato irreversibile): `glossario_entita.md`, `matrice_permessi.md`,
`intent_synonym_mapping.md`. Nessun file tracciato toccato (`git status --porcelain docs`
vuoto).

**Decisi a mano, e TENUTI** — con un difetto ciascuno da correggere separatamente:
- `architecture_decision_rationale.md`: §2 e §3 sono la motivazione architetturale corrente
  (Modular Monolith; "no agenti LLM", coerente con ADR 0001) ed è la fonte unica dichiarata
  dei tre `spec_tech_*`. Stantii solo §1 (perimetro "eventi aziendali") e il campo `project:`.
- `change_log.md`: 3 righe contaminate su 128; §1/§2/§4 sono regole di governance generiche.
  Rimanda a `docs/02_specs_normative/spec_notifications_2.4.md`, che **non esiste**.

Full rebuild + promozione: `CURRENT → v20260901T101536`, alias Qdrant scambiato,
collection orfana raccolta. Chunk **181 → 160** (−21, esattamente i chunk dei tre rimossi).

**Effetto misurato** (stesso golden set, 55 casi, stato pulito):

| Metrica | Prima | Dopo | Δ |
|---|---|---|---|
| recall@1 | 61.8% | **63.6%** | +1.8 |
| recall@2 | 83.6% | **87.3%** | +3.7 |
| recall@5 | 98.2% | 98.2% | — |
| MRR | 0.773 | **0.791** | +0.018 |
| source_in_top3 | 92.7% | **94.5%** | +1.8 |
| multihop: recall media A | 0.854 | **0.896** | +0.042 |
| multihop: casi riusciti | 9/14 | **10/14** | +1 |
| **avversariale recall@1** | 0.0% | **0.0%** | **invariato** |

L'ultima riga è la più informativa: il fallimento avversariale **non era rumore di
dominio**. A3 resta in piedi da solo e va indagato per conto suo.

## B2 — Limite di `top_k` dal client al server ✅

`api/models.py` — `le=50` → `le=20`, con la motivazione (vincolo di correttezza, non di
carico) e i numeri misurati nel commento. Nuovo `tests/test_ask_limits.py`: 3 test, verdi.
Il test che oggi sarebbe fallito: `AskQuery(top_k=50)` deve essere rifiutata.

## B3 — Riscritto dopo una mia correzione

**Il piano originale era basato su un riscontro sbagliato (A2, ritirato).** Il gate NON è
a k=10/0.90: `rag_config.yaml` lo tiene a `k: 2`, `min_recall: 0.75`, `blocking: true`, e
il commento documenta la migrazione k=10 → k=5 → k=2, ogni passo innescato dall'alert di
saturazione del progetto. Il rebuild di oggi l'ha confermato dal vivo.

Resta da fare, molto più stretto (A2b): `latest_recall`, `compute_trend` e
`detect_regression` (`core/eval_history.py:73,79,95`) hanno ancora `key="recall@10"` come
default, e `/api/health` espone `last_recall_at_10` come numero in evidenza. Il gate è
difeso, la deriva lenta no.

## B4 — Sospeso, in attesa di A18

Il caso `quali documenti esistono nel corpus?` va rimisurato: dopo B1 il numero atteso di
documenti è cambiato. Ma prima va chiuso A18, altrimenti si taratura l'harness su misure
potenzialmente miste.

## B5 — Eseguito: nessuna azione necessaria ✅

Riconciliazione riga-per-riga: `SECURITY_SURFACE.md` è **allineato**. Le 57 route hanno
tutte una riga; le 7 apparentemente mancanti sono auto-route di FastAPI e il mount statico,
contati esplicitamente a `:33`. **A10 ritirato.**

## Trovato durante l'esecuzione: A18

`GET /api/retrieve` non ricarica lo snapshot. È l'endpoint su cui gira *tutto* l'harness di
eval. È il riscontro più importante emerso dall'esecuzione, ed è di categoria peggiore degli
altri: non sbaglia il sistema, sbaglia **lo strumento con cui si decide** se il sistema è
migliorato.

**Correzione a me stesso.** Avevo dichiarato invalida la prima misura post-B1 e l'avevo
rifatta. Le due misure sono risultate identiche in ogni metrica, e il controllo spiega
perché: i 160 chunk nuovi sono un **sottoinsieme stretto** dei 181 vecchi (0 chunk_id non
coperti), quindi il sidecar stantìo copriva già tutto ciò che la collection nuova poteva
restituire. La misura era corretta — **per fortuna, non per costruzione**. Il difetto resta
intero, ma il suo profilo di rischio è l'opposto di come l'avevo descritto: è benigno sulle
cancellazioni e mordente sulle aggiunte, dove i chunk_id nuovi mancano dal sidecar e
`colbert_maxsim` restituisce `None` — l'input che innesca A7.

## Stato del backlog

| | |
|---|---|
| Chiusi | B1, B2, B5 |
| Ritirati (riscontro errato) | A2, A10 |
| Nuovi | A18 (prioritario), A2b |
| Prossimi | A18 → B4 → A2b → B6…B12 |

## B4 — Chiuso senza modifiche: il fallimento è un vero positivo

Sbloccato A18, il caso `quali documenti esistono nel corpus?` è stato riesaminato.
`eval/golden_multihop.yaml:90-96` dichiara `count: 11` (la baseline committata) e quattro
nodi attesi: **i nodi ci sono tutti, l'unico scarto è il conteggio** (23 dopo B1, contro 11).

Il primo istinto era togliere l'asserzione sul `count` per far tornare verde il caso. È la
cosa sbagliata: quell'asserzione è **l'unico rilevatore di divergenza del corpus che il
progetto possiede**, e ha appena fatto il suo lavoro. Toglierla sarebbe staccare il
rilevatore di fumo perché c'è fumo.

Nota di merito al golden set: la sua nota di progettazione dichiara il `count` "solo dove è
semanticamente stabile (l'enumerazione dei documenti)". La misura mostra che quella
stabilità vale rispetto alla **baseline committata**, non rispetto a `docs/` su disco — che
per policy contiene anche documenti di lavoro non tracciati. L'asserzione non è sbagliata:
è più esigente di quanto la policy di `docs/` permetta di soddisfare.

**Resta aperto in A6**, e la scelta è di merito, non tecnica: o l'eval gira su un corpus
ricostruito dai soli file tracciati (numeri riproducibili da chiunque, CI compresa), oppure
la divergenza va dichiarata dentro il report di eval. Non è una decisione da prendere di
soppiatto in un harness.

## A18 — Chiuso ✅

`api/routes_retrieval.py` — `maybe_reload_graph()` aggiunto a `api_retrieve`, con la
motivazione nel docstring. Nuovo `tests/test_retrieve_reload.py`.

Il test è stato **verificato per costruzione**: disattivando la sola chiamata appena
aggiunta fallisce con `assert 0 == 1`, ripristinandola torna verde.

Nota emersa: il tetto `k ≤ 50` di `/api/retrieve` è stato **lasciato com'è**, a differenza
di `/ask` (B2). Non è un'incoerenza: quella route non costruisce alcun prompt, quindi non
ha una finestra di contesto da sfondare — il costo di un k alto è solo tempo di ranking.
Il vincolo di B2 è di correttezza dell'LLM, e si applica solo dove c'è un LLM.

---

## Bilancio della Run B

**Chiusi:** B1 (corpus), B2 (tetto `top_k`), B5 (sicurezza: già allineata), A18 (reload).
**Chiuso senza modifiche:** B4 — il fallimento era un vero positivo.
**Ritirati perché sbagliati o imprecisi:** A2, A5, A10.

Tre riscontri su diciotto erano sbagliati, ed è la parte più istruttiva di questo audit:
tutti e tre erano **casi in cui il progetto aveva già ragione** e io avevo letto un
indizio al posto di una prova — i default del codice invece della configurazione attiva
(A2), lo scarto fra due date invece del contenuto (A10), una risposta plausibile invece
dell'asserzione dichiarata (A5). Il difetto vero trovato nell'esecuzione (A18) è della
stessa famiglia, ma dal lato della macchina: **uno strumento che misura uno stato che
nessuno vede, e non lo dice.**

**Metriche a fine Run B** (55 casi, stato pulito, `v20260901T101536`, 160 chunk):
recall@1 63.6% · recall@2 87.3% · recall@5 98.2% · MRR 0.791 · multihop 10/14 (A 0.896).
Suite: **1257 test verdi, 0 fallimenti, 0 skip** (1253 di partenza + 4 nuovi). Avversariale recall@1 **0.0%**, invariato — A3 resta il
primo problema di qualità aperto, e non dipendeva dal rumore di dominio.

---
---

# A3 — perché l'avversariale non è mai primo

**Domanda:** sui 5 casi marcati `adversarial: true`, recall@1 = 0.0%, invariato anche dopo
la pulizia del corpus di B1. Perché?

## 1. Lo 0.0% di partenza è per costruzione, non è una regressione

L'intestazione del golden set (`eval/golden_set.yaml:299-302`) dice che i dieci casi
originali furono **scelti** perché il distrattore precede l'atteso, e ne elenca i ranghi
verificati: `1→2, 1→2, 1→2, 1→2, 2→3, 1→3, 1→5, 3→5, 1→2, 1→3`. Un caso avversariale che
partisse a rango 1 non sarebbe avversariale. Quindi `recall@1 = 0.0%` **è la condizione
iniziale che ADR 0002 doveva ribaltare**, e la misura dice che non l'ha ribaltata.

## 2. α = 0.1 è sotto la soglia che servirebbe — e fu calibrato dove non si vede

Il moltiplicatore è `(1-α) + α·peso`. Con α = 0.1 la forbice fra un documento a peso 0.3 e
uno a 1.0 vale **7,5%**: l'autorità può correggere solo divari ColBERT più piccoli di così.

α minimo per portare l'atteso a rango 1, calcolato con la funzione di produzione
`rank_by_authority` sui candidati reali:

| Caso | Distrattore | α necessario |
|---|---|---|
| 1 — bump di versione | `graph_rag_ingestion_strategy` (METHODOLOGY 0.50) | **0.30** |
| 2 — caratteri per chunk | idem | **0.45** |
| 3 — ordine dei tagli | idem | **0.25** |
| 4 — motivazione a un LLM remoto | `architecture_decision_rationale` (NORMS 0.85) | **0.25** |
| 5 — palette colori | `fe1-canvas-review` (nessun frontmatter, 0.30) | **nessuno ≤ 1.0** |

`rag_config.yaml:9` dice che `boost_alpha` fu portato da 0.4 a **0.1** perché *"alzarono
recall@10 held-out da 0.914 a 0.971"*, e le ricalibrazioni successive girarono a k=5 e k=10,
concludendo ogni volta `NON_APPLICARE, guadagno +0.000`. Il file stesso avverte:
*"Ricalibrare SEMPRE a un k dove la metrica non sia satura"* (`:45`). **Nessuna calibrazione
è mai girata a k=1** — l'unico k che misura ciò che questi casi testano. α è stato scelto
ottimizzando una metrica cieca all'ordinamento in prima posizione.

## 3. Ma alzare α NON è la correzione — provato

Calibrazione eseguita oggi a k=1, 5-fold, 5 seed (`eval/calibrate_authority.py --k 1`):

```
DEFAULT   alpha=0.1  → recall@1 in-sample 0.636
GRIGLIA   alpha=0.3  → recall@1 in-sample 0.655   (ottimista)
CROSS-VALIDATION — l'unico numero onesto:
   default   held-out = 0.636
   calibrato held-out = 0.607
   guadagno = -0.029   su TUTTI E CINQUE i seed (-0.018 -0.036 -0.055 -0.018 -0.018)
AVVERSARIALE in-sample: 0.000 (default) → 0.600 (griglia)
```

Alzare α compra 3 casi avversariali su 5 e ne perde di più sugli altri 50. Il guadagno
in-sample è sovradattamento: fuori campione è una **perdita netta e coerente su ogni seed**.
Il verdetto dello strumento — *"i pesi a mano REGGONO, nessuna modifica consigliata"* — vale
anche a k=1.

## 4. La causa vera: il 70% del deficit non è a livello di documento

Decomposizione dei 55 casi contro il ranking di produzione:

| | |
|---|---|
| Atteso già a rango 1 | 35 |
| Atteso **non** a rango 1 | **20** |
| → bloccato da una **sezione dello stesso documento** | **14 (70%)** |
| → bloccato da un altro documento | 6 |
| Atteso fuori dai top-10 | 0 |

**L'autorità è una proprietà del documento, ma l'unità di retrieval è la sezione.** Quando
il concorrente è una sezione sorella, i pesi sono identici e il moltiplicatore
`(1-α)+α·peso` **si semplifica**: nessun α, per costruzione, può separarle. Il 70% del
deficit di rango 1 vive esattamente dove l'unica leva del progetto non arriva.

Il caso 5 è il ritratto della tenaglia:

| α | Chi vince | Rango dell'atteso |
|---|---|---|
| ≤ 0.2 | `fe1-canvas-review` (cb 0.6115, peso 0.30) — vince sul ColBERT | 3 |
| 0.25–0.6 | `ui_ux_brand_directives § 5` — **sezione sorella**, peso identico 0.80 | 2 |
| ≥ 0.8 | `safeguards_security` (peso 0.98) — vince sulla sola autorità, ColBERT più basso | 5–6 |

## 5. Il meccanismo, con un nome preciso

Quali sezioni bloccano l'atteso dentro il suo stesso documento:

```
 7x  "Scenari Comportamentali BDD (Gherkin)"   (numerata 4./5./6. secondo il documento)
 2x  "Sezione 0 — Contratto di Istanziazione"
 2x  "2. Direttive Vincolanti"
 ... coda di casi singoli
```

**Metà dei blocchi fra sezioni sorelle è una sola classe di sezione.** I blocchi
GIVEN/WHEN/THEN sono la **riformulazione lessicale della regola che li precede**: stesso
vocabolario, più denso di parole chiave, spesso più lungo. Il MaxSim di ColBERT premia
esattamente questo. La sezione che *illustra* la regola batte la sezione che *la stabilisce*.

Vale la pena notare che è lo stesso difetto di ADR 0002 — una fonte che spiega batte la
fonte che vincola — ma sceso di un livello: là fra documenti, qui **fra sezioni dello stesso
documento**. ADR 0002 ha risolto il livello che vedeva.

## 6. Conclusione

A3 **non è un problema di calibrazione dell'autorità.** L'autorità fa già il suo lavoro al
livello dei documenti, e alzarla peggiora le cose fuori campione. È un problema di
**selezione della sezione**, e oggi nessun segnale lo governa.

Tre strade, in ordine di costo — nessuna intrapresa, la scelta è di merito:

1. **Un peso di sezione, non solo di documento** — l'idea di ADR 0002 applicata un livello
   sotto: una sezione normativa pesa più di una illustrativa dello stesso documento. È la
   più coerente con l'architettura esistente e riuserebbe `_authority_weight`.
2. **Trattare i blocchi BDD in indicizzazione** — accorparli alla sezione che illustrano,
   o non indicizzarli come chunk autonomi. Diff minimo, ma perde la capacità di rispondere
   a domande sugli scenari.
3. **Non fare nulla e cambiare il metro** — se ciò che conta è che la fonte giusta stia nel
   contesto (e `/ask` inietta fino a 8 sezioni), il documento giusto a rango 2 non è un
   difetto. Allora recall@1 è la metrica sbagliata per questo sistema e va detto.

La 3 va decisa **prima** della 1 e della 2: se rango 2 va bene, non c'è niente da correggere.

---
---

# A6 — corpus e riproducibilità

**Domanda:** l'indice contiene più documenti di quelli tracciati. Quanto conta davvero?

## Il difetto non è la divergenza, è che la misura si capovolge

Dopo B1: `docs/` ha 23 `.md`, di cui **11 tracciati** — esattamente la baseline che il
golden set dichiara come corpus di riferimento.

Verificato: **tutti e 55 gli attesi vivono in documenti tracciati** (il commit `b1ef300`
aveva già riallineato i matcher). Ma **nessuno dei tre distrattori lo era**:

| Distrattore | Casi | Era tracciato |
|---|---|---|
| `04_knowledge_informative/graph_rag_ingestion_strategy.md` | 1, 2, 3 | no |
| `01_architecture_norms/architecture_decision_rationale.md` | 4 | no |
| `03_changes_historical/fe1-canvas-review.md` | 5 | no |

Simulando il corpus che vede la CI (solo i tracciati), escludendo dai candidati i chunk dei
documenti non tracciati e riordinando con `rank_by_authority`:

| | qui (23 doc) | CI (11 doc) |
|---|---|---|
| recall@1, tutti i 55 casi | 63% | 70% |
| **recall@1, sottoinsieme avversariale** | **0%** | **80%** |

L'80% non è un sistema che funziona meglio: è ciò che si misura quando i distrattori non
esistono e i casi passano a vuoto. **Un distrattore assente non fa fallire il caso: lo rende
decorativo**, che è peggio, perché il numero sale e sembra una buona notizia.

Il numero che ADR 0002 esiste per muovere legge dunque **0% su questa macchina e 80% in CI**.
Una metrica che si capovolge col checkout non misura il sistema, misura il checkout. È anche
la ragione per cui l'opzione che sembrava più pulita — far girare l'eval sui soli file
tracciati — era la peggiore: avrebbe reso l'avversariale decorativo *ovunque*.

## Cosa è stato fatto

**I tre distrattori sono entrati nella baseline tracciata** (`git add -f`: `docs/*` è
ignorata di proposito). Non sono file locali incidentali: sono **parte dello strumento di
misura**, esattamente come gli attesi.

`architecture_decision_rationale.md` è stato corretto prima di entrare: §1 e il campo
`project:` descrivevano ancora il dominio dismesso ("Portale richieste e prenotazioni eventi
aziendali"). L'argomento del documento — per un perimetro di questa **scala** microservizi e
agenti LLM non si giustificano — non dipende dal dominio, quindi §1 ora dichiara la scala e
rimanda a `docs/05_project_specs/` per il perimetro concreto. §2 e §3 invariati.

**Il distrattore è ora un campo dichiarato**, non un commento: `distractor:` su ognuno dei 5
casi, e `test_casi_avversariali_hanno_matcher_validi` ne verifica l'esistenza nel corpus
esattamente come già faceva per l'atteso. Era la lacuna che il commit `b1ef300` aveva
lasciato annotata. Verificato per costruzione: puntando il campo a un file inesistente il
test fallisce, ripristinandolo torna verde.

## Il caso 4 è indebolito, ed è colpa di B1

Il distrattore progettato del caso 4 era `intent_synonym_mapping.md` (METHODOLOGY, peso
0.50) — uno dei tre documenti che **B1 ha rimosso** perché apparteneva al dominio dismesso.
Il concorrente a rango 1 è ora `architecture_decision_rationale.md`, che pesa 0.85 contro lo
0.98 dell'atteso: **il contrasto di autorità è passato da 0.50-vs-0.98 a 0.85-vs-0.98**, da
largo a stretto.

Il caso resta avversariale ma misura meno di quanto fu progettato per misurare. È annotato
nel golden set: va riscritto con un distrattore a bassa autorità che esista nella baseline,
non lasciato così credendo che eserciti ancora il contrasto originale. **Aperto.**

## Cosa resta aperto di A6

Portare i distrattori nella baseline chiude la parte che rendeva la misura *inversa*. Non
chiude la riproducibilità in senso pieno: restano 9 documenti non tracciati (6 output di
pipeline, 3 spec locali del progetto ospitante) che l'indice contiene e la CI no, quindi
recall@1 resta diverso fra le due macchine. La differenza è ora fatta di documenti che
**nessun caso del golden set nomina**, né come atteso né come distrattore — è rumore di
fondo, non più strumento mancante.

Resta valido il criterio di chiusura: o un clone pulito riproduce le metriche dichiarate,
oppure il report di eval dichiara su quale corpus ha misurato.

Annotato e **non** corretto: `graph_rag_ingestion_strategy.md` ha lo stesso campo `project:`
stantìo che è stato corretto in `architecture_decision_rationale.md`. Qui il corpo del
documento è già neutro rispetto al dominio e il campo non è fra quelli letti dal ranking
(`classification`, `status`, `authority`, `tags`): correggerlo costerebbe un altro ciclo di
reindicizzazione per zero effetto misurabile. Va sistemato al prossimo passaggio su quel file.

---
---

# Chiusura: le tre pendenze e A6

## 1. Il caso 4 non è stato riscritto: è stato declassato

Il distrattore progettato era `intent_synonym_mapping.md` (peso 0.50), rimosso da B1.
Per ricostruire il contrasto serviva un altro documento a bassa autorità che parlasse di
LLM e dati personali. **Non esiste.** Misurato sulla baseline tracciata: sotto peso 0.5 ci
sono due soli documenti — `fe1-canvas-review.md` (0.30) e `graph_rag_ingestion_strategy.md`
(0.50) — e **nessuno dei due nomina LLM, privacy o dati personali** (0 occorrenze).

Quindi il marcatore `adversarial` è stato **tolto**, con lo stesso criterio che il progetto
applicò il 2026-08-25 al caso della tracciabilità, per la ragione opposta: quello smise di
essere avversariale perché il sistema lo superava, questo perché non esercita più il
contrasto che dichiara. Ora competerebbe 0.85 contro 0.98 — "due fonti entrambe autorevoli
si contendono il primo posto", che non è ciò che S5 misura e che i pesi di classe di ADR
0002 quasi non governano.

Il sottoinsieme scende a **4 casi contro 2 soli distrattori**. È poco, ed è annotato come
tale nel golden set. Restituirgli ampiezza richiede un documento informativo a bassa
autorità su un tema nuovo: è una decisione sul **corpus**, non sul golden set. **Aperto.**

## 2. A18 verificato end-to-end, non più solo a unit test

La verifica precedente era una mia affermazione sbagliata: il server girava da prima della
correzione e uvicorn non ricarica il codice, quindi la fix era nel file e non nel processo.

Rifatta sul serio, usando la reindicizzazione della pendenza 3 come innesco:

```
CURRENT su disco                  : v20260901T114636
snapshot server (prima)           : v20260901T105315
snapshot server dopo /api/retrieve: v20260901T114636
```

Una sola chiamata a `/api/retrieve` — **non** a `/ask` — allinea lo snapshot. Prima della
correzione era esattamente la chiamata che non faceva nulla.

## 3. Il campo `project:` era una classe, non un'istanza

Segnalando `graph_rag_ingestion_strategy.md` avevo guardato un file solo. Verificati tutti e
13 i tracciati: la convenzione della baseline è `project: "cross-project"` — e **il mio
stesso edit precedente** su `architecture_decision_rationale.md` ne aveva introdotta una
terza variante (`"VibeCraft — baseline cross-progetto"`) invece di seguirla. Corretti
entrambi; ora i 13 documenti sono allineati, sottotitolo H2 compreso
(`## Baseline Cross-Progetto`).

## A6 — chiuso

Il criterio di chiusura era: *o un clone pulito riproduce le metriche dichiarate, oppure il
report di eval dichiara su quale corpus ha misurato*. La prima strada resta impraticabile —
9 documenti (6 output di pipeline, 3 spec locali del progetto ospitante) stanno nell'indice
per ragioni legittime e non devono entrare nel repo. Quindi la seconda, in due punti.

**Il rilevatore di divergenza ora vede entrambe le classi.**
`observe_docs_git_divergence()` confrontava solo i file tracciati con il committato, perché
parte da `git ls-tree`: un corpus grande il doppio produceva `diverging: []`, che si legge
come "tutto a posto". Aggiunto il campo `untracked`. Come `diverging`, **non entra in
`state`**: la maggior parte di quei file è legittima, e farne un problema significherebbe un
allarme atteso a ogni esecuzione notturna — il rumore seppellirebbe il segnale raro, che è
l'errore contro cui la funzione stessa mette già in guardia per le istanziazioni.

**Il report di eval dichiara il corpus, accanto ai numeri e dentro il JSON.**

```
misurato su: 16 documenti tracciati · +9 NON tracciati (nell'indice, assenti da git)
             · 2 divergenti dal committato  ⚠️  numeri NON riproducibili su un checkout pulito
```

La riga è a schermo perché è chi legge il report a occhio che rischia di confrontarlo a
mente con quello di ieri; il campo `corpus` nel JSON serve al confronto automatico. È
telemetria: se git manca degrada a vuoto e l'eval misura lo stesso.

Tre test nuovi: il rilevatore vede un file non tracciato senza cambiare `state`; la riga di
provenienza allarma se e solo se c'è divergenza; l'assenza di git non rompe il report.

**Cosa NON chiude questo.** I numeri restano diversi fra questa macchina e la CI. Non è più
un difetto nascosto: è una differenza dichiarata, fatta di documenti che nessun caso del
golden set nomina né come atteso né come distrattore. La parte che rendeva la misura
*inversa* — i distrattori fuori baseline — è chiusa dal commit precedente.

---

## A19 — la lettura dei PDF è spenta, e nessuno lo dice

Trovato durante l'audit delle licenze (Run C), non cercandolo.

`core/chunking.py:_read_pdf` importa **`pypdf`**, che **non è dichiarata in `pyproject.toml`,
non è nel lock e non è installata**. L'import è dentro un `try/except ImportError` che
degrada a un `logger.warning`.

Verificato eseguendolo su un PDF vero:

```
LOG> WARNING core.chunking:  ⚠️ pypdf non installato: salto documento.pdf (pip install pypdf)
read_document('documento.pdf') -> metadata={} testo=''
```

**Un PDF messo in `docs/` viene indicizzato come documento vuoto.** Non fallisce, non
compare fra i problemi di `check_index_integrity`: lascia una riga di warning e un chunk
senza testo. È la stessa famiglia di A1 e A18 — una degradazione silenziosa che a valle è
indistinguibile dal funzionamento normale.

I tre lettori di `read_document` non stanno tutti allo stesso modo:

| Formato | Libreria | Stato |
|---|---|---|
| `.docx` | `python-docx` | OK, **dichiarata** |
| `.xlsx` | `openpyxl` | OK, ma solo **transitiva** (da `markitdown[xlsx]`): funziona per fortuna |
| `.pdf` | `pypdf` | **assente** |

### Chiuso — dichiarando le librerie e togliendo il degrado

Strada scelta: **dichiarare le dipendenze**, non riscrivere `_read_pdf` su `markitdown`. Il
codice esiste già ed è scritto per `pypdf`; cambiare libreria sarebbe stata una modifica di
design a fronte di una dichiarazione mancante.

Dichiarate **due**, non una: `pypdf` non c'era affatto, e **`openpyxl` arrivava solo come
transitiva di `markitdown`** — funzionava per fortuna, e sarebbe bastato che `markitdown`
cambiasse le proprie dipendenze per spegnere anche l'`.xlsx` nello stesso modo silenzioso.
Correggere solo il PDF avrebbe lasciato il gemello armato.

E soprattutto: **tolti i tre `try/except`** che degradavano a stringa vuota. Sembravano
tolleranza, erano perdita silenziosa di dati — l'unica ragione per cui il difetto è
sopravvissuto tanto a lungo. Con le librerie dichiarate, una che manca è un ambiente rotto e
deve fallire subito, non produrre un chunk vuoto.

Verificato dal vivo dopo la correzione: `read_document` su un PDF vero lo apre e lo legge,
**nessun warning emesso** (prima: `⚠️ pypdf non installato: salto ...` e testo vuoto).

Due test nuovi in `tests/test_chunking.py`: uno fallisce nel momento esatto in cui una delle
tre librerie esce dalle dipendenze; l'altro pretende che un `.pdf` illeggibile **sollevi**
invece di restituire vuoto.

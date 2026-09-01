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

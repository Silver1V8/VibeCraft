# Superficie di sicurezza HTTP — vibecraft/rag

> **Stato:** R2 (dependency anti-cross-site) è **implementata** —
> [`api.deps.require_not_cross_site_request`](api/deps.py). Questo documento non è più
> una proposta: è la **mappa del codice corrente**, con la matrice §2 tenuta allineata da
> `test_every_post_route_is_classified` in
> [`tests/test_security_fixes.py`](tests/test_security_fixes.py) — ogni POST registrato
> deve comparire nella matrice o fra le esclusioni motivate, o la suite fallisce.
>
> **Riverificato il 2026-09-07**: i conteggi di §Metodologia sono stati ricontati sul
> codice (57 route, 24 POST, per-file esatti) e reggono. Sono cambiate due cose dal
> riallineamento di agosto, entrambe recepite sotto: la versione di FastAPI su cui poggia
> il Fatto 2, e l'arrivo di un'autenticazione **lato client** per la console (Fatto 8).
>
> **Riallineamento 2026-08-05.** La revisione originale (M7/R2) fotografava 39 route.
> Nel frattempo sono entrati il ciclo Intake & Import (S0-S6, 15 route + la pagina
> `/intake`) e due endpoint di orientamento per gli agenti (`/api/code/search`,
> `/api/pipeline/final-prompt`): **57 route**. Le sezioni §2-§4 riportano ora ciò che è
> nel codice, non ciò che era da fare.

## Metodologia e conteggio

- **Route registrate sui router: 57** — contate con `grep -c '^@router\.'` su
  `api/routes_*.py`:
  - `routes_pages.py` → 6
  - `routes_pipeline.py` → 21
  - `routes_reindex.py` → 5
  - `routes_retrieval.py` → 3
  - `routes_graph.py` → 5
  - `routes_health.py` → 2
  - `routes_intake.py` → 15
- **La tabella §1 ha 57 righe numerate** (una per route registrata) → il conteggio
  coincide con il criterio di completezza. La numerazione segue l'ordine di
  `include_router` in [`server.py`](server.py), poi l'ordine di dichiarazione nel file.
- **POST totali: 24** — 22 con la dependency anti-cross-site, 2 esclusi con motivazione
  (§2C). Nessun POST non classificato (asserito dalla suite).
- Fuori dai router, montati sull'app in [`server.py`](server.py): 2 route esplicite per
  `shared.css`/`shared.js`, 1 mount statico (`/static`) e 3 route di default di FastAPI
  (`/docs`, `/redoc`, `/openapi.json`) + `/docs/oauth2-redirect`. Sono elencate
  nell'**Appendice A** (non conteggiate nelle 57 perché non registrate sui router), ma
  hanno rilievo di sicurezza e vanno lette.

### Fatti architetturali verificati (valgono per tutta la tabella)

1. **Nessun `CORSMiddleware`.** `grep` su tutto il progetto trova `CORSMiddleware` solo
   dentro `.venv` (dipendenze), mai in `server.py`/`api/`. L'app non aggiunge alcun
   middleware CORS. Conseguenza sul preflight: una richiesta cross-site **non-simple**
   (Content-Type `application/json`, o header custom come `X-API-Key`/`X-Gitlab-Token`)
   fa partire una `OPTIONS` di preflight; il server non ha un handler OPTIONS
   (`grep` conferma: nessun `@router.options`, nessun `methods=`) e non emette header
   `Access-Control-Allow-*` → il preflight **fallisce** → il browser **non invia mai** la
   richiesta reale. Solo le **simple request** (GET/HEAD, o POST con
   `application/x-www-form-urlencoded` | `multipart/form-data` | `text/plain`, senza
   header custom) raggiungono il server cross-site; la risposta resta illeggibile al JS
   attaccante, ma **l'effetto collaterale sul server è già avvenuto**.

2. **FastAPI 0.141.1, `strict_content_type=True` (default).** *(Versione ricontrollata il
   2026-09-07: il documento diceva 0.139.0, che non è più quella installata. L'argomento
   qui sotto è stato **riverificato sulla 0.141.1 e regge invariato** — `Default(True)` a
   `routing.py:389`, `:992` e `:1191`, e il ramo che salta il parsing JSON senza
   Content-Type a `:437-438`. Va ricontrollato a ogni bump di FastAPI: è una difesa che
   dipende da un default di libreria, non da codice nostro.)* Verificato in
   `.venv/.../fastapi/routing.py:425-445`: per un body dichiarato come **modello
   Pydantic**, FastAPI fa `request.json()` **solo se** il Content-Type è
   `application/json` (o `*+json`), **oppure** se non c'è Content-Type **e**
   `strict_content_type` è `False`. Con lo strict a `True`:
   - `text/plain` / `x-www-form-urlencoded` (i content-type "simple") → **non** vengono
     parsati come JSON → il body Pydantic non valida → **422 prima dell'handler**.
   - assenza di Content-Type → non parsato (strict) → 422.
   - `application/json` → parsato, **ma** non è un content-type "simple" → preflight →
     bloccato cross-site.
   **Conseguenza chiave:** una route con **body Pydantic a campi obbligatori** non è
   raggiungibile da una simple request cross-site. Questa però è una **difesa implicita**
   (un default di FastAPI), non un controllo → è il motivo per cui §2 non si accontenta.
   **Attenzione al converso:** la protezione vale solo per i body *Pydantic con campi
   obbligatori*. Un body **multipart** (`UploadFile`), un body **assente** e un modello
   **con tutti i campi opzionali** restano consegnabili cross-site — vedi la nota dopo la
   tabella.

3. **`require_api_key` bypassa localhost** ([`api/deps.py`](api/deps.py)): se
   `request.client.host ∈ {127.0.0.1, ::1}` passa senza chiave. Nel setup keyless di
   default (`VIBECRAFT_API_KEY` non impostata) ogni richiesta che **appare** locale è
   autenticata. È esattamente ciò che rende una POST cross-site verso `127.0.0.1:8000`
   un problema CSRF-like: il browser dell'utente **è** localhost, quindi l'auth è
   bypassata e conta solo se la richiesta è consegnabile (punti 1-2).

4. **`require_api_key_strict`** ([`api/deps.py`](api/deps.py)): **nessun** bypass
   localhost, chiave sempre richiesta. Usata solo da `agent/run`. `X-API-Key` è un header
   custom → cross-site forza preflight → doppiamente non raggiungibile.

5. **`require_gitlab_token`** ([`api/deps.py`](api/deps.py)): no-op se
   `VIBECRAFT_GITLAB_TOKEN` non è impostata (default). Se impostata, richiede
   `X-Gitlab-Token` (header custom → preflight cross-site).

6. **`require_local_bind`** ([`api/deps.py`](api/deps.py)): 403 se `VIBECRAFT_HOST` non è
   il loopback. Non è un controllo d'accesso ma un **interruttore**: spegne le due route
   che hanno senso solo con server e utente sulla stessa macchina (52, 53). A differenza
   di tutte le altre dependency di questo modulo **non è bypassabile con la API key** —
   non esiste chiamante, per quanto autenticato, per cui aprire un dialogo sul desktop di
   un'altra macchina torni sensato — e non ha un flag di override, che sarebbe il modo in
   cui il rischio rientrerebbe dalla finestra. Guarda l'**interfaccia di ascolto**, non
   l'IP del client: è un asse diverso da `_is_local_request`.

7. **`require_not_cross_site_request`** ([`api/deps.py`](api/deps.py)): 403 se
   `Sec-Fetch-Site: cross-site`; passa con API key valida, con header assente
   (curl/script/webhook/browser legacy) e con `same-origin`/`same-site`/`none`.
   `Sec-Fetch-Site` è un *forbidden header* (Fetch Metadata): lo scrive il browser, il JS
   di una pagina non può impostarlo né falsificarlo. Applicata **per-route**, mai come
   middleware globale.

8. **La console si autentica da sé, e la chiave la tiene il browser** (dal 2026-09-01,
   `static/shared.js`). Prima la console dipendeva interamente dal bypass localhost del
   Fatto 3, e da Docker — dove le richieste arrivano dal gateway del bridge e non da
   `127.0.0.1` — ogni `/api/*` e `/ask` rispondeva 401. Ora un **wrapper su `window.fetch`**
   in `shared.js` (caricato nel `<head>` di ogni pagina) allega `X-API-Key` e, su 401,
   chiede la chiave una volta sola e ritenta una volta sola. Tre proprietà che contano qui:
   - **Solo same-origin e solo rotte protette.** `needsApiKey()` scarta ogni URL con
     `origin` diverso da quello della pagina e allega la chiave solo a `/ask` e `/api/*`:
     un fetch verso un altro host non se la porta dietro.
   - **La chiave NON è iniettata nell'HTML per i client remoti**, ed è deliberato: la
     pagina è servita **senza** autenticazione, quindi iniettarla la regalerebbe a
     chiunque la raggiunga. La tiene `localStorage` del browser dell'utente.
     L'iniezione server-side esistente (`deps.inject_agent_api_key`, route 2 `/pipeline`)
     resta prioritaria e vale **solo per i client locali** — vedi §4 #6.
   - **Non allarga la superficie del server**: nessuna dependency è cambiata, nessuna
     route ha perso una protezione. È un client che impara a mandare un header che il
     server già pretendeva.

   Conseguenza per questa mappa: la colonna «Auth effettiva» continua a descrivere ciò che
   il **server** impone. Che la console sappia ora soddisfarla da remoto non rende
   raggiungibile nulla che prima non lo fosse — un attaccante cross-site non può leggere
   quel `localStorage` (è origin-scoped) né far partire la richiesta (Fatti 1-2).

---

## 1. Tabella completa delle route (57 righe)

Legenda **Body**: *assente* = nessun body dichiarato · *query/path* = solo parametri URL ·
*JSON Pydantic* = modello con campi obbligatori · *JSON opz.* = `Request` grezza con
`request.json()` in `try/except` e fallback `None` · *JSON tutto-opz.* = modello Pydantic
senza campi obbligatori · *multipart* = `UploadFile`.
Legenda **Consegnabile x-site**: se una pagina ostile può **far arrivare la richiesta**
all'app, ignorando le dependency (dato §Fatti 1-2). **Sì** · **No (preflight)** ·
**No (strict)**. È una proprietà della *forma* della richiesta, non della protezione: la
colonna successiva dice cosa la ferma.
Legenda **Protezione (nel codice)**: dependency effettivamente dichiarate sulla route,
oltre a `require_api_key` del router.

| # | Metodo | Path | Auth effettiva (nel codice) | Body | Consegnabile x-site | Effetto | Blast | Protezione (nel codice) |
|--:|--------|------|-----------------------------|------|---------------------|---------|-------|-------------------------|
| 1 | GET | `/` | nessuna | assente | Sì | read-only (serve HTML) | Basso | nessuna |
| 2 | GET | `/pipeline` | nessuna | assente | Sì | read-only (serve HTML) + **inietta `VIBECRAFT_API_KEY`** in `window.__VIBECRAFT_AGENT_API_KEY__` — SOLO per client locali (vedi §4 #6) | Basso | nessuna (SOP del browser) |
| 3 | GET | `/infografica` | nessuna | assente | Sì | read-only (serve HTML) | Basso | nessuna |
| 4 | GET | `/analysis` | nessuna | assente | Sì | read-only (serve HTML) | Basso | nessuna |
| 5 | GET | `/eval` | nessuna | assente | Sì | read-only (serve HTML) | Basso | nessuna |
| 6 | GET | `/intake` | nessuna | assente | Sì | read-only (serve HTML) | Basso | nessuna |
| 7 | GET | `/api/pipeline/agent/modes` | require_api_key (bypass localhost) | assente | Sì | read-only (elenco modi) | Basso | nessuna |
| 8 | POST | `/api/pipeline/agent/run` | require_api_key **+ require_api_key_strict** | JSON Pydantic | **No (strict)** | **esegue agente** (`agentic`: Write/Edit confinati a `code/`, **Bash rimosso** — vedi §5) | **Alto** | **strict** |
| 9 | GET | `/api/pipeline/dev-types` | require_api_key | assente | Sì | read-only | Basso | nessuna |
| 10 | POST | `/api/pipeline/explore/turn` | require_api_key | JSON Pydantic | No (preflight) | esegue LLM (no mutazione) | Basso (Medio DoS) | **anti-x-site** |
| 11 | POST | `/api/pipeline/explore/save` | require_api_key | JSON Pydantic | No (preflight) | **scrive filesystem** (`changes/<slug>/explore.md`, dev_type) | Medio | **anti-x-site** |
| 12 | POST | `/api/pipeline/canvas/generate` | require_api_key | JSON Pydantic | No (preflight) | **scrive filesystem** (`canvas.md`, `meta.json`) + esegue LLM | Medio | **anti-x-site** |
| 13 | POST | `/api/pipeline/propose/generate` | require_api_key | JSON Pydantic | No (preflight) | **scrive filesystem** (`spec.md`, `spec.raw.md`) + esegue LLM | Medio | **anti-x-site** |
| 14 | GET | `/api/pipeline/final-prompt` | require_api_key | query | Sì | read-only (template deterministico, nessun LLM) | Basso | nessuna |
| 15 | POST | `/api/pipeline/drift/check` | require_api_key | JSON Pydantic | No (preflight) | esegue LLM (no mutazione) | Basso (Medio DoS) | **anti-x-site** |
| 16 | POST | `/api/pipeline/archive` | require_api_key | JSON Pydantic | No (preflight) | **scrive filesystem** (sposta in `archive/`) + **accoda full rebuild** → scrive Qdrant + muove CURRENT | **Alto** | **anti-x-site** |
| 17 | POST | `/api/pipeline/drift/check/stream` | require_api_key | JSON Pydantic | No (preflight) | esegue LLM (no mutazione) | Basso (Medio DoS) | **anti-x-site** |
| 18 | POST | `/api/pipeline/archive/stream` | require_api_key | JSON Pydantic | No (preflight) | come #16 (archive + full rebuild in coda) | **Alto** | **anti-x-site** |
| 19 | POST | `/api/pipeline/validate` | require_api_key | JSON Pydantic | No (preflight) | esegue LLM + retrieval (no mutazione) | Basso (Medio DoS) | **anti-x-site** |
| 20 | GET | `/api/index/status` | require_api_key | assente | Sì | read-only (drift indicizzazione) | Basso | nessuna |
| 21 | GET | `/api/index/integrity` | require_api_key | assente | Sì | read-only (interroga Qdrant in lettura) | Basso | nessuna |
| 22 | POST | `/api/pipeline/canvas/dry-run` | require_api_key | JSON Pydantic | No (preflight) | read-only (retrieval/embedding, nessuna scrittura) | Basso (Medio DoS) | nessuna (esclusa §2C) |
| 23 | GET | `/api/pipeline/agent-context` | require_api_key | query | Sì | read-only (retrieval) | Basso | nessuna |
| 24 | GET | `/api/pipeline/export` | require_api_key | query | Sì | read-only | Basso | nessuna |
| 25 | GET | `/api/pipeline/status` | require_api_key | query | Sì | read-only | Basso | nessuna |
| 26 | GET | `/api/pipeline/file` | require_api_key | query | Sì | read-only (whitelist file) | Basso | nessuna |
| 27 | POST | `/api/pipeline/file/save` | require_api_key | JSON Pydantic | No (preflight) | **scrive filesystem** (file whitelisted in `changes/<slug>`) | Medio | **anti-x-site** |
| 28 | POST | `/api/reindex` | require_api_key **+ require_gitlab_token** (no-op se env non set) | **JSON opz.** (`Request` grezza) | **Sì (bodyless)** | **scrive Qdrant** (incrementale) — o full rebuild solo con body `{"full":true}` | **Alto** | **anti-x-site** |
| 29 | GET | `/api/reindex` | require_api_key | query | Sì | read-only (lista job) | Basso | nessuna |
| 30 | GET | `/api/reindex/{job_id}` | require_api_key | path | Sì | read-only (stato job) | Basso | nessuna |
| 31 | GET | `/api/index/versions` | require_api_key | assente | Sì | read-only (lista versioni) | Basso | nessuna |
| 32 | POST | `/api/index/rollback` | require_api_key | **JSON opz.** (`Request` grezza) | **Sì (bodyless)** | **muove CURRENT-alias** + Qdrant alias (default: versione precedente) | **Alto** | **anti-x-site** |
| 33 | POST | `/ask` | require_api_key | JSON Pydantic | No (preflight) | esegue LLM (RAG completo, no mutazione) | Basso (Medio DoS) | **anti-x-site** |
| 34 | GET | `/api/retrieve` | require_api_key | query | Sì | read-only (retrieval/embedding) | Basso (Medio DoS) | nessuna (opz.) |
| 35 | GET | `/api/code/search` | require_api_key | query | Sì | read-only (embedding della query + prodotto matriciale in memoria; nessun LLM, nessun Qdrant) | Basso (Medio DoS-CPU) | nessuna (opz.) |
| 36 | GET | `/api/canvas-quality` | require_api_key | query | Sì | read-only | Basso | nessuna |
| 37 | GET | `/api/graph/all` | require_api_key | assente | Sì | read-only (grafo intero) | Basso | nessuna |
| 38 | GET | `/api/graph/impact` | require_api_key | query | Sì | read-only (BFS) | Basso | nessuna |
| 39 | GET | `/api/graph/semantic-map` | require_api_key | assente | Sì | read-only (SVD/PCA, CPU) | Basso (Medio DoS) | nessuna (opz.) |
| 40 | GET | `/api/graph/query` | require_api_key | query | Sì | read-only (query deterministica grafo) | Basso | nessuna |
| 41 | GET | `/api/health` | require_api_key | assente | Sì | read-only (ping Qdrant/Ollama) | Basso | nessuna |
| 42 | GET | `/api/eval/history` | require_api_key | query | Sì | read-only (storico recall) | Basso | nessuna |
| 43 | POST | `/api/intake/docs` | require_api_key | **multipart** (`UploadFile`) | **Sì (multipart)** | **scrive staging** (`database/staging/`, journal) | Medio | **anti-x-site** |
| 44 | GET | `/api/intake/staged` | require_api_key | assente | Sì | read-only (journal) | Basso | nessuna |
| 45 | GET | `/api/intake/staged/{doc_id}/preview` | require_api_key | path | Sì | read-only (journal + markdown derivato) | Basso | nessuna |
| 46 | POST | `/api/intake/staged/{doc_id}/approve` | require_api_key | JSON Pydantic | No (preflight) | **scrive `docs/<categoria>/`** + **reindex delta** (Qdrant + CURRENT) sotto writer lock + reload snapshot | **Alto** | **anti-x-site** |
| 47 | POST | `/api/intake/staged/{doc_id}/reject` | require_api_key | **JSON tutto-opz.** (`motivo` con default) | **Sì (bodyless)** | **scrive staging** (sposta in `staging/rejected/`, journal); `docs/` e indice intatti | Medio | **anti-x-site** |
| 48 | POST | `/api/intake/generate` | require_api_key | JSON Pydantic | No (preflight) | avvia job LLM (Ollama) → documenti in staging | Medio (DoS/costo) | **anti-x-site** |
| 49 | GET | `/api/intake/generate/{job_id}` | require_api_key | path | Sì | read-only (stato job) | Basso | nessuna |
| 50 | POST | `/api/intake/staged/{doc_id}/refine` | require_api_key | **assente** | **Sì (bodyless)** | avvia job LLM di raffinazione → **scrive staging** | Medio (DoS/costo) | **anti-x-site** |
| 51 | GET | `/api/intake/refine/{job_id}` | require_api_key | path | Sì | read-only (stato job) | Basso | nessuna |
| 52 | POST | `/api/intake/project/browse-path` | require_api_key | **assente** | **Sì (bodyless)** | **apre un dialogo tkinter MODALE sul desktop della macchina server** e occupa un thread finché non viene chiuso (vedi §4 #7) | Medio | **anti-x-site + local-bind** |
| 53 | POST | `/api/intake/project/plan` | require_api_key | JSON Pydantic | No (preflight) | read-only ma **scansiona un path arbitrario del filesystem del server** e ne restituisce l'elenco file (vedi §4 #8) | Medio (info-disclosure) | **anti-x-site + local-bind** |
| 54 | POST | `/api/intake/project/apply` | require_api_key | **JSON tutto-opz.** (`plan_id`/`plan` entrambi opzionali) | **Sì (bodyless)** | **copia file in `code/<target>/`** + backup zip + journal + **reindex delta** sotto writer lock | **Alto** | **anti-x-site** |
| 55 | GET | `/api/intake/project/imports` | require_api_key | query | Sì | read-only (journal) | Basso | nessuna |
| 56 | POST | `/api/intake/project/brief` | require_api_key | JSON Pydantic | No (preflight) | avvia job LLM sul grafo → documento in staging | Medio (DoS/costo) | **anti-x-site** |
| 57 | GET | `/api/intake/project/brief/{job_id}` | require_api_key | path | Sì | read-only (stato job) | Basso | nessuna |

### Nota sulle route a corpo consegnabile — dove la dependency è l'UNICO controllo

Su **15 dei 22 POST protetti** l'anti-cross-site è defense-in-depth: il body Pydantic con
almeno un campo obbligatorio li rende comunque irraggiungibili cross-site (§Fatti 2) —
verificato modello per modello su `api/models.py` e `api/routes_intake.py`. Sui restanti
**7** no: la forma della richiesta è consegnabile da una pagina ostile, quindi la
dependency è la **sola** barriera nel setup keyless.

| # | Route | Perché è consegnabile |
|--:|-------|------------------------|
| 28 | `POST /api/reindex` | `Request` grezza + `request.json()` in try/except → una POST **senza body** arriva all'handler con `payload = None` → incrementale su tutto `docs/`+`code/`. |
| 32 | `POST /api/index/rollback` | Idem: bodyless → `target = None` → CURRENT alla versione precedente + alias Qdrant. |
| 43 | `POST /api/intake/docs` | Body **multipart**: `multipart/form-data` è un content-type *simple* → **nessun preflight**. Una pagina ostile costruisce una `FormData` e la invia con `fetch(..., {mode:'no-cors'})`; il file entra in staging. Verificato sul server reale: con `Sec-Fetch-Site: cross-site` risponde **403** prima dell'handler. |
| 47 | `POST .../reject` | `RejectRequest` ha il solo campo `motivo` con default → un body assente **valida** → l'handler parte. |
| 50 | `POST .../refine` | Nessun body dichiarato → il body viene ignorato → una POST bodyless raggiunge l'handler. |
| 52 | `POST /api/intake/project/browse-path` | Nessun body dichiarato → bodyless → l'handler aprirebbe un dialogo sul desktop del server. |
| 54 | `POST /api/intake/project/apply` | `plan_id` e `plan` entrambi opzionali → body assente valida → l'handler parte (si ferma su 422 "serve plan_id o plan", ma **dopo** le dependency). |

La lezione operativa, da applicare a ogni nuova route: **"ha un body Pydantic" non
implica "non è raggiungibile cross-site"**. Vale solo se almeno un campo è obbligatorio e
il body non è multipart. Per questo la matrice §2 include *tutti* i POST mutanti, non solo
quelli che sembrano esposti.

---

## 2. Ambito della dependency anti-cross-site (implementata)

**Principio:** `require_not_cross_site_request` è composta **in aggiunta** a
`require_api_key` (schema di `require_gitlab_token`) e rifiuta con **403** le richieste
con `Sec-Fetch-Site: cross-site`; quelle **senza** l'header passano come prima.

### 2A — Mutano stato persistente (13)

| Route | Motivazione |
|-------|-------------|
| POST `/api/reindex` (28) | Consegnabile bodyless; muta Qdrant sotto writer lock. In default keyless nessuna altra barriera. |
| POST `/api/index/rollback` (32) | Consegnabile bodyless; muove CURRENT + alias Qdrant → degrada la produzione a una versione arbitraria. |
| POST `/api/pipeline/explore/save` (11) | Scrive filesystem. Non consegnabile *solo* per il combinato preflight+strict content-type: difesa implicita, sostituita da un controllo esplicito. |
| POST `/api/pipeline/canvas/generate` (12) | Scrive filesystem + spende LLM. |
| POST `/api/pipeline/propose/generate` (13) | Scrive filesystem (`spec.md`) + LLM. |
| POST `/api/pipeline/archive` (16) | Sposta filesystem **e** accoda un full rebuild (→ Qdrant + CURRENT): blast Alto. |
| POST `/api/pipeline/archive/stream` (18) | Variante streaming di #16, stesso effetto e stesso blast. |
| POST `/api/pipeline/file/save` (27) | Scrive filesystem. |
| POST `/api/intake/docs` (43) | **Consegnabile (multipart)**: scrive in staging senza preflight. |
| POST `/api/intake/staged/{id}/approve` (46) | Scrive `docs/` **e** reindicizza (Qdrant + CURRENT): blast Alto. |
| POST `/api/intake/staged/{id}/reject` (47) | **Consegnabile (body tutto-opzionale)**: sposta file e scrive il journal. |
| POST `/api/intake/project/apply` (54) | **Consegnabile (body tutto-opzionale)**: copia file in `code/`, backup, journal, reindex delta. Blast Alto. |
| POST `/api/intake/project/browse-path` (52) | **Consegnabile (bodyless)**: non muta dati ma apre una finestra sul desktop del server e occupa un thread — effetto locale osservabile e fastidioso, trattato come mutante. Monta **anche** `require_local_bind` (§4 #7). |

### 2B — Eseguono LLM/CPU o espongono il filesystem, senza mutare l'indice (9)

Route: POST `/api/pipeline/explore/turn` (10), `/api/pipeline/drift/check` (15),
`/api/pipeline/drift/check/stream` (17), `/api/pipeline/validate` (19), `/ask` (33),
`/api/intake/generate` (48), `/api/intake/staged/{id}/refine` (50),
`/api/intake/project/plan` (53), `/api/intake/project/brief` (56).

Il tier defense-in-depth raccomandato dalla revisione originale **è stato adottato**:
tutte queste route hanno la dependency. Motivazioni: un trigger cross-site di massa è un
vettore di **DoS/consumo costo** su Ollama (10, 15, 17, 19, 33, 48, 50, 56); `plan` (53) è
read-only ma **enumera un path arbitrario del filesystem del server** (§4 #8) e monta
**anche** `require_local_bind`; `refine` (50) è per giunta **consegnabile bodyless**. La
dependency è a costo nullo e non rompe la UI same-origin.

### 2C — ESCLUSE, con motivazione

| Route / gruppo | Motivazione dell'esclusione |
|----------------|------------------------------|
| POST `/api/pipeline/agent/run` (8) | **Già `require_api_key_strict`** — protezione *più forte* dell'anti-cross-site (chiave sempre richiesta, anche da localhost). Aggiungere Sec-Fetch-Site è ridondante e **non va indebolito** sostituendo lo strict. Asserito da `_STRICT_ROUTES` e da `test_excluded_route_does_not_declare_anti_cross_site_dependency`. |
| POST `/api/pipeline/canvas/dry-run` (22) | POST ma **read-only** (retrieval/embedding, nessuna scrittura, nessun LLM di generazione) e body Pydantic obbligatorio → non consegnabile. Solo rischio DoS-CPU. |
| Tutte le **GET** (1-7, 9, 14, 20-21, 23-26, 29-31, 34-42, 44-45, 49, 51, 55, 57) | Read-only per contratto. Anti-cross-site su GET **romperebbe** navigazione/embedding cross-origin legittimi senza proteggere nulla. Le GET CPU-pesanti (`/api/retrieve` 34, `/api/code/search` 35, `/api/graph/semantic-map` 39) restano un rischio DoS-CPU **accettato** (§4 #4). `maybe_reload_graph` invocato da alcune GET è un reload interno idempotente, non una mutazione pilotabile dall'attaccante. |
| Pagine HTML (1-6) e mount `/static` | Shell statiche pubbliche, nessun dato, nessuna auth by design. Eccezione documentata: `/pipeline` (2) inietta la API key per i soli client locali → §4 #6. |

**Sintesi ambito:** **22 POST protetti** su 24 (13 mutanti §2A + 9 LLM/filesystem §2B).
Escluse: `agent/run` (già strict, non toccare) e `canvas/dry-run`; GET e pagine invariate.

---

## 3. Copertura di test (implementata)

In [`tests/test_security_fixes.py`](tests/test_security_fixes.py), sezione "R2 (M7)". Il
`TestClient` **non è un browser**: può impostare qualsiasi header, incluso
`Sec-Fetch-Site` — è l'unico modo per esercitare davvero il branch cross-site.

### 3.1 Ordine di valutazione (vincolo rispettato dai test)

In `fastapi/routing.py` il **parse grezzo** del body avviene **prima** di
`solve_dependencies`; la **validazione Pydantic** avviene **dentro** `solve_dependencies`,
**dopo** l'esecuzione delle dependency. Quindi una dependency che solleva 403 **precede**
il 422 di validazione, **ma non** un 422 da JSON malformato. I test sfruttano proprio
questo: inviano `{}` (JSON valido ma incompleto) e assertano che il cross-site dia 403
mentre il ramo "come oggi" dia il 422 — la business logic non viene mai eseguita.

### 3.2 Cosa è asserito

| Test | Asserzione |
|------|------------|
| `test_not_cross_site_*` (3 test) | Semantica della dependency in isolamento: 403 su `cross-site`; passa con header assente, `same-origin`, `same-site`, `none`; passa con API key valida. |
| `test_matrix_route_declares_anti_cross_site_dependency` | Introspezione: ognuna delle **22** route della matrice dichiara la dependency. |
| `test_excluded_route_does_not_declare_anti_cross_site_dependency` | `agent/run` e `canvas/dry-run` **non** la dichiarano (nessuna protezione "per eccesso", nessun indebolimento dello strict). |
| **`test_every_post_route_is_classified`** | **Il verso che mancava.** Ogni POST registrato su uno qualsiasi dei 7 router deve stare nella matrice o fra le esclusioni, e nessuna riga può essere fantasma. È ciò che impedisce alla matrice di restare indietro rispetto al codice: senza, i 9 POST di intake sono entrati senza che nulla lo segnalasse. |
| `test_http_cross_site_post_rejected_with_403` | Wiring HTTP reale sulle 22 route: cross-site keyless ⇒ 403. |
| `test_http_without_fetch_metadata_behaves_as_today` | Senza `Sec-Fetch-Site` ⇒ mai 403 (curl/webhook/browser legacy invariati). |
| `test_http_same_origin_behaves_as_today` | `same-origin` (la dashboard keyless) ⇒ mai 403. |
| `test_http_cross_site_with_valid_api_key_passes` | Cross-site **con** API key valida ⇒ mai 403 (client API autenticati non sono il threat model). |
| `test_http_reindex_bodyless_curl_still_reaches_handler` | Criterio di accettazione: `curl -X POST /api/reindex` continua a funzionare (202). |

> Nota sulla fixture: `_native_folder_dialog` è sostituita con un fake. `browse-path` (52)
> non dichiara body, quindi nei rami "come oggi" l'handler **viene raggiunto davvero** e
> aprirebbe un dialogo tkinter modale sulla macchina che esegue i test, bloccando la
> suite. Che una POST bodyless apra una finestra sul desktop del server è anche il motivo
> per cui la route è in matrice.

---

## 4. Rischi residui — mitigazione o accettazione

| # | Rischio residuo | Mitigazione / accettazione |
|--:|-----------------|----------------------------|
| 1 | **Browser legacy senza `Sec-Fetch-Site`.** Un browser che non emette Fetch Metadata manda la richiesta senza header → ricade nel path "come oggi" → la guardia non scatta e una POST cross-site passa. | **Accettato.** Fetch Metadata è supportato da tutti gli evergreen dal ~2019 (Chrome 76+, Firefox 90+, Edge, Safari 16.4+); la popolazione residua è trascurabile per uno strumento su localhost. *Rafforzamento opzionale:* combinare con un controllo `Origin`/`Referer` (rifiuta Origin presente e diverso da self) come secondo segnale. |
| 2 | **Reverse proxy che fa apparire locale il client.** Dietro un proxy che termina la connessione, `request.client.host` diventa `127.0.0.1` (il proxy) → il bypass localhost di `require_api_key` si applica a **tutti** i client esterni. | **Mitigazione documentata (deploy).** Non esporre dietro proxy senza (a) impostare `VIBECRAFT_API_KEY` **e** (b) far onorare `X-Forwarded-For` a uvicorn (`--forwarded-allow-ips`, `ProxyHeadersMiddleware`). Sec-Fetch-Site **continua** a proteggere il vettore browser-CSRF anche via proxy. Il residuo è l'**accesso di rete autenticato**, compito di API-key + bind 127.0.0.1. |
| 3 | **Client cross-site non-browser** (curl/script sulla LAN se il bind supera localhost). Non inviano `Sec-Fetch-Site` → la guardia non li ferma. | **Accettato per design.** Sec-Fetch-Site difende il vettore CSRF-da-browser, non l'accesso programmatico. La barriera per quest'ultimo resta `VIBECRAFT_API_KEY` + bind `127.0.0.1` (fail-closed già presente in `server.py`). |
| 4 | **DoS-CPU/costo sulle GET read-only** (`/api/retrieve` 34, `/api/code/search` 35, `/api/graph/semantic-map` 39): un trigger cross-site di massa consuma embedding/SVD senza mutare stato. | **Accettato.** I POST-LLM sono ora tutti coperti (§2B), quindi il grosso è chiuso. Per le GET CPU un rate-limit resta **debito annotato**: `/api/code/search` ha già tetti di risposta (`k ≤ 25`) ma non di frequenza. |
| 5 | **`/docs`, `/redoc`, `/openapi.json` non autenticati** (Appendice A). Espongono l'intero schema delle route a chiunque raggiunga il server. | **Accettato in locale**; in caso di esposizione, disabilitare (`FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`) o proteggerli. Info-disclosure, non mutazione. |
| 6 | **`GET /pipeline` (2) inietta `VIBECRAFT_API_KEY` nell'HTML** come `window.__VIBECRAFT_AGENT_API_KEY__`, su una route senza auth. | **Accettato, per costruzione.** L'iniezione avviene **solo** per client locali (`_is_local_request`, stessa condizione del bypass di `require_api_key`) e la Same-Origin Policy impedisce a una pagina di un'altra origine di **leggere** il body della risposta: può solo navigarci o fare fetch opachi. Se il server è esposto oltre localhost l'iniezione si disattiva da sola, quindi la chiave non raggiunge mai un client remoto. Resta un rischio se l'utente esegue codice ostile *nella propria pagina* — fuori dal modello di minaccia. |
| 7 | **`POST /api/intake/project/browse-path` (52) apre un dialogo nativo sul desktop del server** ed è **consegnabile bodyless**. Senza guardie, una pagina ostile farebbe comparire un selettore di cartelle sulla macchina che ospita il server e occuperebbe un thread del pool finché non viene chiuso. | **Chiuso su entrambi gli assi.** Browser di terzi: anti-cross-site (403 prima dell'handler). Bind aperto: `require_local_bind` **spegne** la route (403 per chiunque, API key inclusa) — era il debito annotato dalla revisione precedente, ora implementato, perché con server e utente su macchine diverse la funzione non è "più rischiosa", è priva di senso. Residuo **accettato**: con bind locale, un client sulla stessa macchina può innescarla — ma su quella macchina il dialogo è appunto la funzione richiesta. |
| 8 | **`POST /api/intake/project/plan` (53) enumera un path arbitrario del filesystem del server** e ne restituisce i file classificati: è info-disclosure per un chiamante che raggiunge l'endpoint. | **Chiuso su entrambi gli assi.** Le validazioni di `core.project_import` (path assoluto, esistente, directory, mai dentro il repo né lo staging) riducono l'abuso ma **non** limitano *quale* directory sia scansionabile: il contenimento vero è che il chiamante deve essere sulla macchina stessa. Anti-cross-site copre il browser di terzi; `require_local_bind` spegne la route se il bind supera il loopback, quando l'enumerazione diventerebbe remota. Residuo **accettato** con bind locale: chi chiama da quella macchina ha già accesso al filesystem. |

---

## 5. Perimetro della modalità `agentic` (R8 — `agent_bridge.py`)

`POST /api/pipeline/agent/run` (riga 8) è l'unica route che **scrive file / esegue**
tramite il Claude Agent SDK. Oltre all'auth (`require_api_key_strict`, invariata), la
modalità `agentic` è confinata a livello di SDK (`claude-agent-sdk` 0.2.115):

- **`cwd = PROJECT_ROOT/code`** — working dir dell'agente. Le modalità `suggest`
  (sola lettura) e `oneshot` (nessun tool) restano su `PROJECT_ROOT`, invariate.
- **Hook `PreToolUse` → `permissionDecision="deny"`** su ogni `Write`/`Edit` il cui
  path risolve fuori da `code/` o nomina un'area riservata (`rag/`, `docs/`, `.git/`).
  È la primitiva più forte della versione installata: il CLI invoca l'hook per **ogni**
  tool call, anche quelle auto-approvate da `allowed_tools`, e un deny la blocca. La
  decisione vive in `_agentic_tool_denial` (funzione pura, testata con path avversari:
  `rag/database/CURRENT`, `../rag/…`, path assoluti fuori da `code/`, `.git/config` ⇒
  deny; `backend/app.py` ⇒ allow).
- **Bash rimosso** (`disallowed_tools=["Bash"]`, e l'hook lo nega comunque). Il
  path-scoping di Bash non è confinabile in modo affidabile: i pattern `allowed_tools`
  (`Bash(npm:*)`) vincolano solo il prefisso del comando, non i path; un comando shell
  (Turing-completo) può scrivere ovunque via `..`/assoluti/subshell; la sandbox di
  esecuzione dell'SDK è macOS/Linux-only e il deploy è Windows. Decisione: **meglio
  perdere Bash che lasciare RCE con scrittura non confinata**. Build/test del codice
  generato restano fuori dalla modalità agentic.

**Conseguenza sul prompt finale della pipeline.** Poiché in `agentic` non esiste Bash,
l'agente in-app **non può fare chiamate HTTP**: `core.pipeline.build_final_prompt`
distingue il consumatore (`external` vs `agent`) e omette per l'SDK il blocco che spiega
come interrogare l'indice via `/api/code/search`. Non è una misura di sicurezza ma la
stessa logica di perimetro: non si istruisce un agente a usare uno strumento che il suo
perimetro gli nega.

**Limiti residui:** (a) il confinamento è a livello di *decisione tool* dell'SDK, non
un sandbox del kernel — un bug dell'SDK che non invocasse l'hook lo aggirerebbe; (b)
lettura ampia: `Read`/`Glob`/`Grep` non sono ristretti a `code/`, quindi l'agente può
*leggere* (non scrivere) altrove nel progetto; (c) niente esecuzione (Bash) significa
niente build/test in-modalità; (d) la blocklist dei segmenti riservati può rifiutare un
`docs/` legittimo dentro `code/` (scelta conservativa, fail-closed).

---

## Appendice A — Superfici app-level (fuori dalle 57, montate in `server.py`)

| Metodo | Path | Auth | Effetto | Nota |
|--------|------|------|---------|------|
| GET | `/static/shared.css` | nessuna | read-only (asset) | Route esplicita (non il mount) per servirla con `NO_CACHE_HEADERS`: in cache, l'HTML fresco referenzierebbe classi CSS non ancora presenti. |
| GET | `/static/shared.js` | nessuna | read-only (asset) | Idem. |
| GET | `/static/*` | nessuna | read-only (asset statici) | `app.mount(StaticFiles)`; vendor pinnati, cache di default del browser. |
| GET | `/openapi.json` | nessuna | read-only (schema) | Default FastAPI. Rivela tutte le route → vedi rischio #5. |
| GET | `/docs` | nessuna | read-only (Swagger UI) | Default FastAPI. |
| GET | `/redoc` | nessuna | read-only (ReDoc) | Default FastAPI. |
| GET | `/docs/oauth2-redirect` | nessuna | read-only | Default FastAPI (inerte, nessun OAuth configurato). |

---

## Report finale

- **Conteggio route registrate sui router: 57** (6 pages · 21 pipeline · 5 reindex ·
  3 retrieval · 5 graph · 2 health · 15 intake) — **coincide** con le 57 righe della
  tabella §1. Fuori conteggio: 2 route asset + 1 mount statico + 4 route di default
  FastAPI (Appendice A).
- **POST: 24** — **22 protetti** da `require_not_cross_site_request`, 2 esclusi con
  motivazione (`agent/run` già strict, `canvas/dry-run` read-only). Nessun POST non
  classificato: lo garantisce `test_every_post_route_is_classified`.
- **Route mutanti individuate: 13** — `explore/save`, `canvas/generate`,
  `propose/generate`, `archive`, `archive/stream`, `file/save`, `POST /api/reindex`,
  `POST /api/index/rollback`, `intake/docs`, `intake/approve`, `intake/reject`,
  `intake/project/apply`, `intake/project/browse-path`. Più `agent/run` che **esegue
  l'agente** (blast Alto) ma è **già strict**.
- **Consegnabili cross-site per forma della richiesta: 7** (28, 32, 43, 47, 50, 52, 54 —
  bodyless, multipart o body con tutti i campi opzionali). Su queste l'anti-cross-site è
  l'**unico** controllo nel setup keyless, non defense-in-depth. Le altre 15 sono coperte
  *anche* dal combinato preflight-CORS + `strict_content_type` — difesa implicita, mai
  l'unica.
- **Route spente per configurazione: 2** — `browse-path` (52) e `project/plan` (53) sono
  disabilitate da `require_local_bind` quando `VIBECRAFT_HOST` non è il loopback. È
  l'unico caso in cui una route smette di esistere invece di essere protetta: la loro
  utilità dipende dal fatto che server e utente siano la stessa macchina, quindi con un
  bind aperto non resta nulla da proteggere.
- **Debiti annotati:** rate-limit sulle GET CPU-pesanti (§4 #4); `/docs`/`/openapi.json`
  da chiudere in caso di esposizione (§4 #5).

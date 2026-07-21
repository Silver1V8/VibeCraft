# Superficie di sicurezza HTTP — vibecraft/rag (M7 / R2)

> Sessione di **sola analisi**. Nessun codice modificato. Questo documento mappa ogni
> route registrata, ne verifica l'autenticazione **nel codice** (non nei docstring) e
> definisce l'ambito della dependency anti-cross-site che la Sessione 6 (R2) dovrà
> introdurre.

## Metodologia e conteggio

- **Route registrate sui router: 39** — contate con `grep -c '^@router\.'` su
  `api/routes_*.py`:
  - `routes_pages.py` → 5
  - `routes_pipeline.py` → 20
  - `routes_reindex.py` → 5
  - `routes_retrieval.py` → 2
  - `routes_graph.py` → 5
  - `routes_health.py` → 2
- **La tabella §1 ha 39 righe numerate** (una per route registrata) → il conteggio
  coincide con il criterio di completezza.
- Fuori dai router, montati sull'app in [`server.py`](server.py): 1 mount statico
  (`/static`) e 3 route di default di FastAPI (`/docs`, `/redoc`, `/openapi.json`) +
  `/docs/oauth2-redirect`. Sono elencate nell'**Appendice A** (non conteggiate nei 39
  perché non registrate sui router), ma hanno rilievo di sicurezza e vanno lette.

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

2. **FastAPI 0.139.0, `strict_content_type=True` (default).** Verificato in
   `.venv/.../fastapi/routing.py:418-442`: per un body dichiarato come **modello
   Pydantic**, FastAPI fa `request.json()` **solo se** il Content-Type è
   `application/json` (o `*+json`), **oppure** se non c'è Content-Type **e**
   `strict_content_type` è `False`. Con lo strict a `True`:
   - `text/plain` / `x-www-form-urlencoded` (i content-type "simple") → **non** vengono
     parsati come JSON → il body Pydantic non valida → **422 prima dell'handler**.
   - assenza di Content-Type → non parsato (strict) → 422.
   - `application/json` → parsato, **ma** non è un content-type "simple" → preflight →
     bloccato cross-site.
   **Conseguenza chiave:** una route con **body Pydantic a campi obbligatori** (tutti i
   modelli in [`api/models.py`](api/models.py) hanno almeno un campo required) **non è
   raggiungibile da una simple request cross-site**: non esiste modo, dal browser di una
   pagina ostile, di consegnare un body JSON parsabile senza far scattare un preflight
   che qui fallisce. Questa però è una **difesa implicita** (un default di FastAPI), non
   un controllo esplicito → §2 la considera insufficiente da sola.

3. **`require_api_key` bypassa localhost** ([`api/deps.py:48-56`](api/deps.py)): se
   `request.client.host ∈ {127.0.0.1, ::1}` passa senza chiave. Nel setup keyless di
   default (`VIBECRAFT_API_KEY` non impostata) ogni richiesta che **appare** locale è
   autenticata. È esattamente ciò che rende una POST cross-site verso `127.0.0.1:8000`
   un problema CSRF-like: il browser dell'utente **è** localhost, quindi l'auth è
   bypassata e conta solo se la richiesta è consegnabile (punti 1-2).

4. **`require_api_key_strict`** ([`api/deps.py:59-75`](api/deps.py)): **nessun** bypass
   localhost, chiave sempre richiesta. Usata solo da `agent/run`. `X-API-Key` è un header
   custom → cross-site forza preflight → doppiamente non raggiungibile.

5. **`require_gitlab_token`** ([`api/deps.py:84-93`](api/deps.py)): no-op se
   `VIBECRAFT_GITLAB_TOKEN` non è impostata (default). Se impostata, richiede
   `X-Gitlab-Token` (header custom → preflight cross-site).

---

## 1. Tabella completa delle route (39 righe)

Legenda **Body**: *assente* = nessun body letto · *query/path* = solo parametri URL ·
*JSON Pydantic* = modello obbligatorio · *JSON opz.* = `Request` grezza con
`request.json()` in `try/except` e fallback `None`.
Legenda **X-site?** (raggiungibile da simple/bodyless request cross-site, dato §Fatti
1-2): **Sì** · **No (preflight)** = body JSON non consegnabile · **No (strict)**.
Legenda **Protezione R2**: *nessuna* · *anti-x-site* · *strict (già presente)*.
`(racc.)` = raccomandata/defense-in-depth, non strettamente mandatoria (vedi §2).

| # | Metodo | Path | Auth effettiva (nel codice) | Body | X-site? | Effetto | Blast | Protezione R2 |
|--:|--------|------|-----------------------------|------|---------|---------|-------|---------------|
| 1 | GET | `/` | nessuna | assente | Sì | read-only (serve HTML) | Basso | nessuna |
| 2 | GET | `/pipeline` | nessuna | assente | Sì | read-only (serve HTML) | Basso | nessuna |
| 3 | GET | `/infografica` | nessuna | assente | Sì | read-only (serve HTML) | Basso | nessuna |
| 4 | GET | `/analysis` | nessuna | assente | Sì | read-only (serve HTML) | Basso | nessuna |
| 5 | GET | `/eval` | nessuna | assente | Sì | read-only (serve HTML) | Basso | nessuna |
| 6 | GET | `/api/pipeline/agent/modes` | require_api_key (bypass localhost) | assente | Sì | read-only (elenco modi) | Basso | nessuna |
| 7 | POST | `/api/pipeline/agent/run` | require_api_key **+ require_api_key_strict** | JSON Pydantic | **No (strict)** | **esegue agente** (`agentic`: Write/Edit confinati a `code/`, **Bash rimosso** — vedi §5) | **Alto** | **strict (già presente)** |
| 8 | GET | `/api/pipeline/dev-types` | require_api_key | assente | Sì | read-only | Basso | nessuna |
| 9 | POST | `/api/pipeline/explore/turn` | require_api_key | JSON Pydantic | No (preflight) | esegue LLM (no mutazione) | Basso (Medio DoS) | anti-x-site (racc.) |
| 10 | POST | `/api/pipeline/explore/save` | require_api_key | JSON Pydantic | No (preflight) | **scrive filesystem** (`changes/<slug>/explore.md`, dev_type) | Medio | **anti-x-site** |
| 11 | POST | `/api/pipeline/canvas/generate` | require_api_key | JSON Pydantic | No (preflight) | **scrive filesystem** (`canvas.md`, `meta.json`) + esegue LLM | Medio | **anti-x-site** |
| 12 | POST | `/api/pipeline/propose/generate` | require_api_key | JSON Pydantic | No (preflight) | **scrive filesystem** (`spec.md`) + esegue LLM | Medio | **anti-x-site** |
| 13 | POST | `/api/pipeline/drift/check` | require_api_key | JSON Pydantic | No (preflight) | esegue LLM (no mutazione) | Basso (Medio DoS) | anti-x-site (racc.) |
| 14 | POST | `/api/pipeline/archive` | require_api_key | JSON Pydantic | No (preflight) | **scrive filesystem** (sposta in `archive/`) + **accoda full rebuild** → scrive Qdrant + muove CURRENT | **Alto** | **anti-x-site** |
| 15 | POST | `/api/pipeline/drift/check/stream` | require_api_key | JSON Pydantic | No (preflight) | esegue LLM (no mutazione) | Basso (Medio DoS) | anti-x-site (racc.) |
| 16 | POST | `/api/pipeline/archive/stream` | require_api_key | JSON Pydantic | No (preflight) | come #14 (archive + full rebuild in coda) | **Alto** | **anti-x-site** |
| 17 | POST | `/api/pipeline/validate` | require_api_key | JSON Pydantic | No (preflight) | esegue LLM + retrieval (no mutazione) | Basso (Medio DoS) | anti-x-site (racc.) |
| 18 | GET | `/api/index/status` | require_api_key | assente | Sì | read-only (drift indicizzazione) | Basso | nessuna |
| 19 | GET | `/api/index/integrity` | require_api_key | assente | Sì | read-only (interroga Qdrant in lettura) | Basso | nessuna |
| 20 | POST | `/api/pipeline/canvas/dry-run` | require_api_key | JSON Pydantic | No (preflight) | read-only (retrieval/embedding, nessuna scrittura) | Basso (Medio DoS) | nessuna (opz.) |
| 21 | GET | `/api/pipeline/agent-context` | require_api_key | query | Sì | read-only (retrieval) | Basso | nessuna |
| 22 | GET | `/api/pipeline/export` | require_api_key | query | Sì | read-only | Basso | nessuna |
| 23 | GET | `/api/pipeline/status` | require_api_key | query | Sì | read-only | Basso | nessuna |
| 24 | GET | `/api/pipeline/file` | require_api_key | query | Sì | read-only (whitelist file) | Basso | nessuna |
| 25 | POST | `/api/pipeline/file/save` | require_api_key | JSON Pydantic | No (preflight) | **scrive filesystem** (file whitelisted in `changes/<slug>`) | Medio | **anti-x-site** |
| 26 | POST | `/api/reindex` | require_api_key **+ require_gitlab_token** (no-op se env non set) | **JSON opz.** (`Request` grezza) | **Sì (bodyless)** | **scrive Qdrant** (incrementale) — o full rebuild solo con body `{"full":true}` | **Alto** | **anti-x-site** |
| 27 | GET | `/api/reindex` | require_api_key | query | Sì | read-only (lista job) | Basso | nessuna |
| 28 | GET | `/api/reindex/{job_id}` | require_api_key | path | Sì | read-only (stato job) | Basso | nessuna |
| 29 | GET | `/api/index/versions` | require_api_key | assente | Sì | read-only (lista versioni) | Basso | nessuna |
| 30 | POST | `/api/index/rollback` | require_api_key | **JSON opz.** (`Request` grezza) | **Sì (bodyless)** | **muove CURRENT-alias** + Qdrant alias (default: versione precedente) | **Alto** | **anti-x-site** |
| 31 | POST | `/ask` | require_api_key | JSON Pydantic | No (preflight) | esegue LLM (RAG completo, no mutazione) | Basso (Medio DoS) | anti-x-site (racc.) |
| 32 | GET | `/api/retrieve` | require_api_key | query | Sì | read-only (retrieval/embedding) | Basso (Medio DoS) | nessuna (opz.) |
| 33 | GET | `/api/canvas-quality` | require_api_key | query | Sì | read-only | Basso | nessuna |
| 34 | GET | `/api/graph/all` | require_api_key | assente | Sì | read-only (grafo intero) | Basso | nessuna |
| 35 | GET | `/api/graph/impact` | require_api_key | query | Sì | read-only (BFS) | Basso | nessuna |
| 36 | GET | `/api/graph/semantic-map` | require_api_key | assente | Sì | read-only (SVD/PCA, CPU) | Basso (Medio DoS) | nessuna (opz.) |
| 37 | GET | `/api/graph/query` | require_api_key | query | Sì | read-only (query deterministica grafo) | Basso | nessuna |
| 38 | GET | `/api/health` | require_api_key | assente | Sì | read-only (ping Qdrant/Ollama) | Basso | nessuna |
| 39 | GET | `/api/eval/history` | require_api_key | query | Sì | read-only (storico recall) | Basso | nessuna |

### Nota sui due POST "corpo assente" (righe 26 e 30) — il cuore del rischio

`start_reindex` e `index_rollback` **non** dichiarano un modello Pydantic: prendono
`request: Request` e fanno `payload = await request.json()` dentro `try/except`, con
fallback `payload = None`. Perciò FastAPI **non** impone il Content-Type. Una **POST
cross-site senza body** (simple request: nessun content-type problematico, nessun header
custom) arriva all'handler; `request.json()` solleva → `payload = None` → l'handler
**procede e muta**:

- **`/api/reindex`** bodyless → `changed_paths = None` → `manager.start(None, _run_reindex, …)`
  → **incrementale su tutto `docs/` + `code/`**: ri-embedding e upsert/delete su Qdrant,
  tiene il writer lock. Il path **full rebuild** (con la migrazione legacy irreversibile
  e lo swap alias) richiede il body `{"full": true}` → `application/json` → preflight →
  **non** raggiungibile cross-site. Cross-site si raggiunge solo l'incrementale — che
  comunque muta la collection di produzione. In default keyless `require_gitlab_token` è
  no-op, quindi **nessuna barriera aggiuntiva**.
- **`/api/index/rollback`** bodyless → `target = None` → `rollback_version(None)` sposta
  CURRENT alla **versione precedente** e riallinea l'alias Qdrant, sotto writer lock. Il
  rollback a una versione **specifica** richiede body JSON (bloccato cross-site); il
  rollback-al-precedente funziona **bodyless**.

Queste due sono le **uniche route mutanti effettivamente raggiungibili cross-site oggi**.
Tutte le altre route mutanti (10, 11, 12, 14, 16, 25) sono protette *di fatto* solo dal
combinato preflight-CORS + `strict_content_type` — una difesa implicita, non un controllo.

---

## 2. Ambito della dependency anti-cross-site (R2)

**Principio:** la dependency (es. `require_same_site`, da comporre **in aggiunta** a
`require_api_key`, sullo schema di `require_gitlab_token`) rifiuta con **403** le
richieste con `Sec-Fetch-Site: cross-site`; le richieste **senza** l'header passano come
oggi. `Sec-Fetch-Site` è un header *forbidden* (Fetch Metadata): il JS di una pagina non
può settarlo né sovrascriverlo, lo impone il browser → è una difesa CSRF valida e
non falsificabile lato pagina.

### 2A — INCLUSE, mandatorie (mutano stato persistente)

| Route | Motivazione |
|-------|-------------|
| POST `/api/reindex` (26) | **Raggiungibile cross-site oggi** (bodyless) e muta Qdrant sotto writer lock. In default keyless nessuna altra barriera. Priorità massima. |
| POST `/api/index/rollback` (30) | **Raggiungibile cross-site oggi** (bodyless) e muove CURRENT + alias Qdrant → può degradare la produzione a una versione arbitraria/precedente. Priorità massima. |
| POST `/api/pipeline/explore/save` (10) | Scrive filesystem. Non raggiungibile oggi *solo* per il combinato preflight+strict content-type: difesa implicita e fragile (un domani `strict_content_type=False`, o un endpoint gemello form-based, la annulla). Sec-Fetch-Site è il controllo esplicito. |
| POST `/api/pipeline/canvas/generate` (11) | Scrive filesystem + spende LLM. Stessa fragilità della difesa implicita. |
| POST `/api/pipeline/propose/generate` (12) | Scrive filesystem (`spec.md`) + LLM. Idem. |
| POST `/api/pipeline/archive` (14) | Sposta filesystem **e** accoda un full rebuild (→ Qdrant + CURRENT): blast Alto. Deve essere protetto esplicitamente. |
| POST `/api/pipeline/archive/stream` (16) | Variante streaming di #14, stesso effetto e stesso blast. |
| POST `/api/pipeline/file/save` (25) | Scrive filesystem. Idem. |

> Le 6 route (10, 11, 12, 14, 16, 25) figurano già in `_REVERTED_TO_PLAIN_KEY_ROUTES` in
> [`tests/test_security_fixes.py`](tests/test_security_fixes.py): il revert dello strict
> su di esse è **deliberato** (la UI è keyless e il frontend non manda `X-API-Key`).
> Sec-Fetch-Site è la protezione corretta perché **non rompe la UI same-origin**: il
> browser dell'utente invia `Sec-Fetch-Site: same-origin` sulle chiamate della dashboard,
> che quindi passano; solo l'origine ostile invia `cross-site`. È il motivo per cui R2
> sceglie anti-cross-site invece di re-imporre lo strict.

### 2B — INCLUSE raccomandate (eseguono LLM/CPU, non mutano stato) — decisione ambigua

Route: POST `/api/pipeline/explore/turn` (9), POST `/api/pipeline/drift/check` (13),
POST `/api/pipeline/drift/check/stream` (15), POST `/api/pipeline/validate` (17),
POST `/ask` (31).

- **Non mutano stato** → fuori dallo scopo stretto "route mutanti".
- **Non raggiungibili cross-site oggi** (body Pydantic → preflight).
- **Ma** eseguono LLM/Ollama: un trigger cross-site di massa è un vettore di
  **DoS/consumo costo**, non di corruzione. La dependency è a costo nullo e non rompe la
  UI same-origin.
- **Raccomandazione:** includerle come **defense-in-depth** (tier "racc."), applicando la
  stessa dependency in un colpo solo a tutti i POST non-idempotenti del router pipeline +
  `/ask`. Se R2 vuole restare rigorosamente sulle *sole* route mutanti, è **legittimo
  escluderle** — in tal caso vanno lasciate esplicitamente annotate come rischio DoS
  accettato. La raccomandazione pende per **includere**: superficie coerente, nessuna
  regressione UI.

### 2C — ESCLUSE, con motivazione

| Route / gruppo | Motivazione dell'esclusione |
|----------------|------------------------------|
| POST `/api/pipeline/agent/run` (7) | **Già `require_api_key_strict`** — protezione *più forte* dell'anti-cross-site (chiave sempre richiesta, anche da localhost). Aggiungere Sec-Fetch-Site è ridondante e **non va indebolito** sostituendo lo strict. Resta strict, invariato (cfr. `_STRICT_ROUTES` nel test). |
| POST `/api/pipeline/canvas/dry-run` (20) | POST ma **read-only** (retrieval/embedding, nessuna scrittura, nessun LLM di generazione). Solo rischio DoS-CPU → opzionale, non mandatorio. |
| Tutte le **GET** (1-6, 8, 18-19, 21-24, 27-29, 32-39) | Read-only per contratto. Anti-cross-site su GET **romperebbe** navigazione/embedding cross-origin legittimi senza proteggere nulla (niente da mutare). Le GET CPU-pesanti (`/api/retrieve` 32, `/api/graph/semantic-map` 36) restano un rischio DoS-CPU **accettato** (vedi §4). `maybe_reload_graph` invocato da alcune GET è un reload interno idempotente, non una mutazione pilotabile dall'attaccante. |
| Pagine HTML (1-5) e mount `/static` | Shell statiche pubbliche, nessun dato, nessuna auth by design. |

**Sintesi ambito R2:** **8 route mandatorie** (§2A) + **5 raccomandate** (§2B). Escluse:
`agent/run` (già strict, non toccare), `canvas/dry-run` e tutte le GET/pagine.

---

## 3. Specifica del test parametrico (R2 implementerà)

Modello: stesso stile di `tests/test_security_fixes.py` (introspezione delle dependency +
wiring HTTP reale con `TestClient`). Il `TestClient` **non è un browser**: può impostare
qualsiasi header, incluso `Sec-Fetch-Site` e `Content-Type: application/json` — è l'unico
modo per esercitare davvero il branch cross-site.

### 3.1 Ordine di valutazione (vincolo da rispettare nel test)

In `fastapi/routing.py` il **parse grezzo** del body (`json.loads`) avviene **prima** di
`solve_dependencies`; la **validazione Pydantic** del body avviene **dentro**
`solve_dependencies`, **dopo** l'esecuzione delle dependency. Quindi una dependency che
solleva 403 **precede** il 422 di validazione, **ma non** un 422 da JSON malformato.
Regola operativa per il test: inviare sempre un **body JSON valido e minimale** (con
`Content-Type: application/json`) per le route Pydantic, così il 403 è attribuibile
all'header e non a un 422. Per le due route bodyless (reindex/rollback) inviare **senza
body**.

### 3.2 Parametrizzazione

```python
# (router, metodo, path, body_minimo_valido | None)
_CROSS_SITE_GUARDED = [
    # --- mandatorie (§2A) ---
    (routes_reindex.router,  "POST", "/api/reindex",                    None),
    (routes_reindex.router,  "POST", "/api/index/rollback",             None),
    (routes_pipeline.router, "POST", "/api/pipeline/explore/save",      {"feature_name": "f", "interview_log": "x"}),
    (routes_pipeline.router, "POST", "/api/pipeline/canvas/generate",   {"feature_name": "f"}),
    (routes_pipeline.router, "POST", "/api/pipeline/propose/generate",  {"feature_folder": "f"}),
    (routes_pipeline.router, "POST", "/api/pipeline/archive",           {"feature": "f"}),
    (routes_pipeline.router, "POST", "/api/pipeline/archive/stream",    {"feature": "f"}),
    (routes_pipeline.router, "POST", "/api/pipeline/file/save",         {"feature": "f", "name": "canvas.md", "content": "x"}),
    # --- raccomandate (§2B): includere se R2 adotta il tier defense-in-depth ---
    (routes_pipeline.router, "POST", "/api/pipeline/explore/turn",      {"feature_name": "f", "user_input": "x"}),
    (routes_pipeline.router, "POST", "/api/pipeline/drift/check",       {"feature": "f"}),
    (routes_pipeline.router, "POST", "/api/pipeline/drift/check/stream",{"feature": "f"}),
    (routes_pipeline.router, "POST", "/api/pipeline/validate",          {"feature": "f"}),
    (routes_retrieval.router,"POST", "/ask",                            {"question": "x"}),
]
```

### 3.3 Asserzioni (per ogni riga)

1. **Cross-site ⇒ 403.** Richiesta con header `Sec-Fetch-Site: cross-site` (per le
   Pydantic anche `Content-Type: application/json` + body minimo; per reindex/rollback
   nessun body) → `resp.status_code == 403`. Nel setup keyless (`deps.API_KEY = None`,
   client `("127.0.0.1", …)`), così si prova che il 403 nasce dalla nuova dependency e
   **non** dall'auth (che localhost bypasserebbe).
2. **Senza header ⇒ come oggi.** Stessa richiesta **senza** `Sec-Fetch-Site` → **non**
   403: l'handler viene raggiunto esattamente come prima di R2 (le dipendenze a valle —
   filesystem/Qdrant/LLM — vanno mockate/`monkeypatch` come già fa il test suite, così
   l'asserzione è `status_code != 403`, tipicamente 200/202). Dimostra la
   retro-compatibilità con webhook e client non-browser.
3. **`same-origin`/`same-site`/`none` ⇒ come oggi.** Aggiungere almeno un caso
   `Sec-Fetch-Site: same-origin` → non 403: la UI della dashboard non deve regredire.

### 3.4 Test di non-regressione dell'esclusione

- `agent/run` **resta strict**: riusare l'asserzione esistente `_STRICT_ROUTES`; in più,
  verificare che la nuova dependency **non** sia stata aggiunta a `agent/run` (non
  indebolire/duplicare).
- Le GET read-only **non** montano la dependency (un caso su `/api/health` o
  `/api/graph/all` con `Sec-Fetch-Site: cross-site` ⇒ **non** 403).

---

## 4. Rischi residui — mitigazione o accettazione

| # | Rischio residuo | Mitigazione / accettazione |
|--:|-----------------|----------------------------|
| 1 | **Browser legacy senza `Sec-Fetch-Site`.** Un browser che non emette Fetch Metadata manda la richiesta senza header → ricade nel path "come oggi" → la guardia non scatta e una POST cross-site passa. | **Accettato.** Fetch Metadata è supportato da tutti gli evergreen dal ~2019 (Chrome 76+, Firefox 90+, Edge, Safari 16.4+); la popolazione residua è trascurabile per uno strumento su localhost. *Rafforzamento opzionale:* combinare con un controllo `Origin`/`Referer` (rifiuta Origin presente e diverso da self) come secondo segnale — copre anche l'assenza di Sec-Fetch-Site. |
| 2 | **Reverse proxy che fa apparire locale il client.** Dietro un proxy che termina la connessione, `request.client.host` diventa `127.0.0.1` (il proxy) → il bypass localhost di `require_api_key` si applica a **tutti** i client esterni → auth bypassata a monte, indipendentemente da Sec-Fetch-Site. | **Mitigazione documentata (deploy).** Non esporre dietro proxy senza (a) impostare `VIBECRAFT_API_KEY` **e** (b) far onorare `X-Forwarded-For` a uvicorn (`--forwarded-allow-ips`, `ProxyHeadersMiddleware`) così che `client.host` sia l'IP reale. Nota: Sec-Fetch-Site **continua** a proteggere il vettore browser-CSRF anche via proxy (l'header cross-site attraversa il proxy). Il residuo è l'**accesso di rete autenticato**, che è compito di API-key + bind 127.0.0.1, non di questa dependency. |
| 3 | **Client cross-site non-browser** (curl/script sulla LAN se il bind supera localhost). Non inviano `Sec-Fetch-Site` → la guardia non li ferma. | **Accettato per design.** Sec-Fetch-Site difende il vettore CSRF-da-browser, non l'accesso programmatico. La barriera per quest'ultimo resta `VIBECRAFT_API_KEY` + bind `127.0.0.1` (fail-closed già presente in `server.py`). |
| 4 | **DoS-CPU/costo su route read-only o LLM escluse dal tier mandatorio** (`/api/retrieve`, `/api/graph/semantic-map`, e i POST §2B se non inclusi). Trigger cross-site di massa consuma embedding/SVD/Ollama senza mutare stato. | **Accettato**, con raccomandazione ad **adottare il tier §2B** per i POST-LLM (chiude il grosso). Per le GET CPU un rate-limit è fuori ambito R2; annotato come debito. |
| 5 | **`/docs`, `/redoc`, `/openapi.json` non autenticati** (Appendice A). Espongono l'intero schema delle route a chiunque raggiunga il server. | **Accettato in locale**; in caso di esposizione, disabilitare (`FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`) o proteggerli. Info-disclosure, non mutazione — fuori dallo scopo R2 ma da tenere a registro. |

---

## 5. Perimetro della modalità `agentic` (R8 — `agent_bridge.py`)

`POST /api/pipeline/agent/run` (riga 7) è l'unica route che **scrive file / esegue**
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

**Limiti residui:** (a) il confinamento è a livello di *decisione tool* dell'SDK, non
un sandbox del kernel — un bug dell'SDK che non invocasse l'hook lo aggirerebbe; (b)
lettura ampia: `Read`/`Glob`/`Grep` non sono ristretti a `code/`, quindi l'agente può
*leggere* (non scrivere) altrove nel progetto; (c) niente esecuzione (Bash) significa
niente build/test in-modalità; (d) la blocklist dei segmenti riservati può rifiutare un
`docs/` legittimo dentro `code/` (scelta conservativa, fail-closed).

---

## Appendice A — Superfici app-level (fuori dai 39, montate in `server.py`)

| Metodo | Path | Auth | Effetto | Nota |
|--------|------|------|---------|------|
| GET | `/static/*` | nessuna | read-only (asset statici) | `app.mount(StaticFiles)`; shared.css/js pubblici by design. |
| GET | `/openapi.json` | nessuna | read-only (schema) | Default FastAPI. Rivela tutte le route → vedi rischio #5. |
| GET | `/docs` | nessuna | read-only (Swagger UI) | Default FastAPI. |
| GET | `/redoc` | nessuna | read-only (ReDoc) | Default FastAPI. |
| GET | `/docs/oauth2-redirect` | nessuna | read-only | Default FastAPI (inerte, nessun OAuth configurato). |

---

## Report finale

- **Conteggio route registrate sui router: 39** (5 pages · 20 pipeline · 5 reindex ·
  2 retrieval · 5 graph · 2 health) — **coincide** con le 39 righe della tabella §1.
  Fuori conteggio: 1 mount statico + 4 route di default FastAPI (Appendice A).
- **Route mutanti individuate: 8** — `explore/save`, `canvas/generate`,
  `propose/generate`, `archive`, `archive/stream`, `file/save` (scrivono filesystem;
  archive → anche Qdrant + CURRENT), `POST /api/reindex` (Qdrant), `POST /api/index/rollback`
  (CURRENT + alias). Più `agent/run` che **esegue l'agente** (blast Alto) ma è **già
  strict**, quindi fuori scope R2.
- **Realmente raggiungibili cross-site oggi: solo 2** — `POST /api/reindex` e
  `POST /api/index/rollback`, entrambe a **corpo assente** (`Request` grezza,
  `request.json()` in try/except): una POST cross-site bodyless le raggiunge e muta. Le
  altre 6 mutanti sono coperte *di fatto* solo dal combinato preflight-CORS +
  `strict_content_type=True` (FastAPI 0.139.0) — difesa **implicita e fragile**, da
  sostituire con il controllo esplicito Sec-Fetch-Site.
- **Decisioni ambigue e raccomandazione:**
  1. *`drift/check`(+stream), `validate`, `explore/turn`, `/ask`* eseguono LLM ma **non
     mutano**: **raccomando di includerle** in R2 come defense-in-depth (vettore
     DoS/costo, dependency a costo nullo, nessuna regressione UI). Escluderle è legittimo
     solo se documentato come rischio DoS accettato.
  2. *`agent/run`*: **escludere** — già `require_api_key_strict`, più forte;
     **non sostituire/indebolire**.
  3. *`canvas/dry-run`* e *GET CPU-pesanti* (`/api/retrieve`, `/api/graph/semantic-map`):
     read-only → **fuori scope mandatorio**; solo rischio DoS-CPU, accettato (§4 #4).
  4. *Ambito R2 consigliato:* **8 mandatorie + 5 raccomandate = 13 POST** con la
     dependency anti-cross-site; `agent/run` resta strict; GET e pagine invariate.

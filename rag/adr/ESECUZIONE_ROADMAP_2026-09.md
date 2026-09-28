# Esecuzione della roadmap di revisione architetturale — settembre 2026

Resoconto dell'esecuzione dei punti della roadmap derivata dalla revisione architetturale
(analisi su `7512b1d`), eseguita sul branch `claude/software-architecture-review-t1zg51`
a partire da `main` @ `1e1a260`. Ogni punto è stato rivalidato sul codice attuale prima
di intervenire, implementato da un sotto-agente, riletto da un revisore indipendente
(sempre di classe Opus) che ha rieseguito ruff e la suite completa e verificato che i
test nuovi falliscano senza la modifica; i giri di correzione sono proseguiti fino
all'approvazione. Solo allora il PM ha integrato il commit (cherry-pick) e ha rieseguito
ruff e pytest completi sul branch integrato prima di ogni push.

## Baseline e risultato finale

| | ruff | pytest | test Node (`rag/tests/*.cjs`) |
|---|---|---|---|
| Baseline (`1e1a260`) | verde | **1871 passed, 10 skipped, 0 failed** | 2/3 ok; `pipeline_agent.cjs` fallisce |
| Finale (`d7d8223`, prima di questo documento) | verde | **2086 passed, 10 skipped, 0 failed** | 4/5 ok; `pipeline_agent.cjs` fallisce |

- Ambiente: Python 3.14.7, dipendenze da `uv.lock` (torch/torchvision installati dall'indice
  predefinito perché quello cu126 è bloccato dalla rete), LibreOffice con i moduli
  `writer-nogui` e `impress-nogui` installati: per questo la baseline non ha i 3 fallimenti
  d'ambiente dei test DOC/PPT previsti in un container con solo `libreoffice-core`.
- I 10 saltati sono invariati: 5 test Docling (pesi assenti) e 5 test Qdrant reali
  (`VIBECRAFT_TEST_QDRANT_URL` assente).
- `pipeline_agent.cjs` fallisce già su `main` (si aspetta un corpo di `agent/run` senza
  `max_attempts`), non è eseguito dalla CI e fallisce con lo stesso errore prima e dopo:
  preesistente, non toccato.
- +215 test pytest, 2 test Node nuovi (`pipeline_dryrun_escape.cjs`,
  `dashboard_graph_escape.cjs`), entrambi aggiunti alla CI.

## Stato per punto

Legenda modelli: implementatore indicato per classe (Opus / Sonnet / Haiku); tutti i
revisori erano Opus. "PM" indica ritocchi applicati dal coordinatore dopo l'approvazione,
limitati a facoltativi segnalati dal revisore e sempre riverificati con la suite completa
(e, dove erano test, con una mutazione che il test deve intercettare).

### Fase 1

| Punto | Stato | Commit | Impl. | Revisione |
|---|---|---|---|---|
| #1 Validazione `Host` (DNS rebinding) | fatto, adattato | `12b9ed3` | Opus | 1 giro di correzione, poi approvato |
| #9 `hmac.compare_digest` su `X-API-Key` | fatto | `b8f3c5a` | Opus | approvato al primo giro |
| (extra) token webhook GitLab non ASCII → 401 | fatto | `55be42b` | Opus | approvato |
| #2 XSS nel pannello dry-run (+ passata sui sink) | fatto, esteso | `5529fd6` | Opus | 1 giro (aggiunti sink della dashboard) |
| #3 fase 1 anti-framing | fatto | `9192894` | Opus | approvato |
| #7 Pin immagini compose | fatto | `b2dc587` | Haiku | 1 giro (tag Ollama inesistente) + ritocco PM |

- **#1** — Riprodotto: con client `127.0.0.1` e `Host: attacker.example:8000`, `/pipeline`
  rispondeva 200 con la chiave iniettata. Adattamento: middleware ASGI proprio
  (`HostHeaderGuard`, `api/deps.py`) invece di `TrustedHostMiddleware`, perché Starlette
  taglia l'header al primo `:` e rifiuterebbe `[::1]:8000`. Ammessi `127.0.0.1`,
  `localhost`, `::1`, il bind specifico di `VIBECRAFT_HOST`, l'host di `VIBECRAFT_BASE_URL`
  e la nuova `VIBECRAFT_ALLOWED_HOSTS` (voci con `*` ignorate con warning; `testserver`
  mai ammesso). Correzione emersa in revisione: con bind wildcard (default Docker
  `0.0.0.0`) l'URL derivato scritto nei prompt dei runner esterni ora usa `127.0.0.1`,
  altrimenti sarebbe stato rifiutato. Porta validata (solo cifre), `..` rifiutato,
  un WARNING per host distinto. File: `api/deps.py`, `core/config.py`, `server.py`,
  `SECURITY_SURFACE.md` (Fatto 9, rischio #6), `README.md`, `rag/README.md`,
  `.env.example`. Test: `tests/test_host_header.py` (44 casi, incluso il ruolo reader in
  sottoprocesso).
- **#9** — `_valid_api_key` confronta i byte UTF-8 con `hmac.compare_digest`. Test in
  `test_security_fixes.py`. Il revisore ha trovato lo stesso difetto (TypeError → 500 su
  header non ASCII) in `require_gitlab_token`: corretto in un commit separato con test in
  `test_reindex.py`.
- **#2** — Escape in `runCanvasDryRun` (`doc_id`, `section`, `branch`, `note`,
  `e.message`, punteggi non numerici) e nella tendina dev-types; tooltip di
  `graph_analysis` (rimossa la copia locale di `escapeHtml` che non escapava `'`);
  errore Mermaid di `infografica`; in revisione aggiunti `linkLabel` del grafo 3D della
  dashboard (relazioni del frontmatter → `innerHTML` del tooltip) e `renderScores`.
  Test Node che eseguono il codice reale estratto dai template.
- **#3 fase 1** — `SecurityHeadersMiddleware` (ASGI puro, header su
  `http.response.start`, nessun buffering dello streaming) su ogni risposta:
  `X-Frame-Options: DENY`, CSP `frame-ancestors 'none'`, `nosniff`,
  `Referrer-Policy: same-origin`; tipi MIME di `.js/.css/.svg` fissati. Test
  `test_security_headers.py`.
- **#7** — Qdrant `v1.19.0` (allineato a CI e `qdrant-client`), Ollama `0.34.4`. Il
  primo tentativo usava `v0.34.4`, tag inesistente su Docker Hub (le immagini Ollama non
  hanno la `v`): intercettato dal revisore, che ha verificato i tag sul registry. Test
  `test_docker_compose_pinned.py` con la convenzione dei tag. Nota: il trailer del
  commit indica Opus su richiesta del PM, ma l'implementatore era Haiku.

### Fase 2

| Punto | Stato | Commit | Impl. | Revisione |
|---|---|---|---|---|
| #4 Reload indice fuori dall'event loop | fatto | `bc3c942` | Opus | approvato al primo giro |
| #5 Spesa agenti nel budget | fatto | `d4a05c9` | Opus | approvato (facoltativi inclusi) |
| #6 Tetto ai job LLM + retention | fatto, adattato | `2f7778c` | Opus | 1 giro (tetto globale) |
| #8 `.dockerignore` | fatto | `f98debc` | Sonnet | 1 giro (semantica Docker) + ritocco PM |
| #10 Dry-run davvero read-only | fatto | `407ae4a` | Sonnet | approvato + ritocco PM |
| #11 Classificazione di tutte le route | fatto, esteso | `f624012` | Sonnet | 1 giro (solo doc, applicato dal PM, riconfermato) |
| #15 CI | fatto | `3c52bad` | Sonnet | approvato + ritocchi PM |

- **#4** — `maybe_reload_graph` chiamato in modo sincrono da 7 handler async (anche
  `/ask` in streaming e le route del reader). Ora `await run_in_threadpool(...)` e
  `threading.Lock` con doppio controllo della versione; `reload_index_state` esplicito
  serializzato. Nessun ordine di lock invertito (verificato su rollback, intake, job).
  Test `test_reload_concurrency.py` (event loop libero con load bloccato; due trigger →
  un caricamento).
- **#5** — Il costo `total_cost_usd` dei run `claude` entra in `llm._record_spend`
  (anche run falliti; NaN/inf scartati); con budget esaurito `agent/run` risponde 429
  con `Retry-After` e i rilanci automatici emettono `retry_blocked`. Runner `local`,
  `codex`, `cursor` non bloccati. Soglia morbida documentata.
- **#6** — Il meccanismo di ammissione di `/ask` è legato all'event loop e non
  riusabile dai thread: stesso contratto (env + 429 + `Retry-After`) con
  `GenerationSlots` **condiviso** fra generate/refine/brief
  (`VIBECRAFT_GENERATION_MAX_ACTIVE`, default 2) e retention dei job terminati
  (`VIBECRAFT_GENERATION_MAX_FINISHED`, default 100); env lette in modo pigro; slot
  liberato prima di pubblicare lo stato finale; la UI di intake gestisce il 404 del
  polling.
- **#8** — Escluse `rag/eval/results/` (tranne `history.jsonl`, letto dalla pagina
  `/eval`), `rag/adr/`, `rag/tests/`, cache. Il primo tentativo usava
  `rag/eval/results/*/`, che per BuildKit (`filepath.Clean`) equivale a `*` ed escludeva
  anche `history.jsonl`: il revisore l'ha dimostrato col vero `moby/patternmatcher`
  v0.6.1. Test `test_dockerignore.py` con un matcher che riproduce quello di Docker
  (confrontato col matcher Go su oltre 9000 casi, 0 differenze). Riduzione stimata del
  contesto di build: ~123 MB, ~1800 file.
- **#10** — `pipeline_canvas_dry_run` non passa più `create=True`; validazione del nome
  invariata (path traversal verificato); nessuna altra scrittura nel percorso.
- **#11** — Il codice aveva 60 route (24 in `routes_pipeline.py`): mancava
  `GET /api/pipeline/agent/runners`. Nuovi test: ogni route registrata (tutti i metodi,
  route app-level, ruoli writer e reader in sottoprocesso) deve comparire nella matrice
  e viceversa; conteggi dichiarati ricontati dal codice; nessuna WebSocket non
  classificata. In più tre GET "read-only" di intake creavano `staging/` e il journal:
  ora usano `staging_paths_readonly()`.
- **#15** — `permissions: contents: read` in `ci.yml`; tutte le action di `ci.yml` e
  `release.yml` pinnate per SHA di commit (verificati con `git ls-remote`, versione in
  commento, stessa major); `dependabot.yml` per `github-actions`. Il PM ha esteso il test
  ai permessi di job e a `release.yml`.

### Fase 3

| Punto | Stato | Commit | Impl. | Revisione |
|---|---|---|---|---|
| #3 fase 2 CSP completa | fatto (bloccante) | `d230abc`, `b6b9017` | Opus | approvato + ritocchi PM |
| #14 Scomposizione `core/indexing.py` | fatto | `032c06f` | Opus | approvato + ritocchi PM |
| #12 Provider LLM validati all'avvio | fatto | `beecbe5` | Haiku | 1 giro (deriva delle liste) |
| #13 LibreOffice senza modulo | fatto | `a103c59` | Sonnet | 1 giro (messaggio sbagliato su file corrotti) + ritocchi PM |
| Snellimento documentazione | fatto, parziale | `d7d8223` | Sonnet | approvato + ritocchi PM |

- **#3 fase 2** — Script inline dei 6 template spostati in `static/pages/*.js`, ~70
  handler `on*=` sostituiti da `data-click/change/input` con un dispatcher delegato che
  esegue solo azioni registrate (`Object.create(null)`); chiave API di `/pipeline` in un
  `<meta>` con escape, rimosso dal DOM dopo la lettura. CSP **bloccante**:
  `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'
  data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:;
  object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`
  (`/docs` e `/redoc` esenti per match esatto). Verifica con Chromium reale (Playwright)
  su tutte le pagine: implementatore e revisore, quest'ultimo attivando tutti i 68
  elementi interattivi con un id ostile — zero errori console, zero violazioni salvo una
  nota e innocua di `vis.min.js` (sonda `Function("return this")` in un `try`). Test
  `test_csp.py` (niente codice inline nei template né handler generati in JS; il PM ha
  esteso le regex a handler non quotati, `<img/onerror>` e `setAttribute('on…')`).
- **#14** — `core/indexing.py` da 2844 a 1966 righe; nuovi `core/qdrant_versions.py`
  (alias/blue-green/GC), `core/drift_check.py`, `core/feature_archive.py`;
  `_read_manifest` in `core/artifacts.py`; `_docs_hashes` → `docs_hashes` pubblico.
  Il revisore ha confrontato con `ast` tutte le funzioni spostate (identiche salvo
  l'import lazy in `archive_feature`) e fatto 18 mutazioni sui monkeypatch; il PM ha
  rinforzato l'unica guardia indebolita (`test_full_rebuild_never_calls_reconciler_*`).
- **#12** — Commento di `rag_config.yaml` corretto (niente `openai`); `active_provider`,
  provider dei purpose e `budget.fallback_provider` validati all'avvio contro
  `VALID_LLM_PROVIDERS`, con controllo all'import di `core.llm` che la lista coincida col
  registry.
- **#13** — Misurato con LibreOffice reale che `source file could not be loaded` esce
  identico per modulo assente, file protetto e file corrotto: solo `no import/export
  filter` è una certezza; il caso ambiguo è deciso convertendo una sonda ODT/ODP valida
  (cache solo dell'esito positivo). `doctor.py` ha il controllo LibreOffice con timeout
  dedicato e avviso invece del crash se `soffice` si blocca.
- **Snellimento** — `rag/adr/sidecar-work/` (68 file) e 56 delle 59 run con `evidence/`
  (~117 MB) spostate con `git mv` in `archive/`. **Non spostate** tre run lette dai test
  (`propose_adopted_v3_20260914`, `gate_end_to_end_20260914`, `p0_20260908-152239`) e i
  file sciolti di `rag/eval/results/`. Link relativi: 22 rotti prima e dopo, stesso
  insieme (preesistenti). Hash di tutti i blob confrontati: nessun contenuto perso; il
  PM ha ripristinato byte per byte l'unico file di evidenza che era stato modificato.
  `archive/README.md` dichiara l'archivio congelato. `archive/` aggiunto a
  `.dockerignore`.

## Rischi residui e limiti

- **Host**: chi raggiunge la console con un nome LAN, un IP con bind `0.0.0.0`, un
  reverse proxy o un webhook GitLab pubblico riceve 400 finché non configura
  `VIBECRAFT_ALLOWED_HOSTS` o `VIBECRAFT_BASE_URL` (documentato, log con suggerimento).
  Un nome aggiunto il cui DNS è controllato da terzi riapre il rebinding per quel nome.
- **CSP**: `style-src 'unsafe-inline'` resta (Tailwind runtime JIT, stili inline di
  mermaid/vis; nessun tool offline per generare CSS statico). Le risposte 500 non gestite
  di `ServerErrorMiddleware` escono senza header di sicurezza (testo semplice).
  L'esenzione di `/docs` usa percorsi fissi: con un `root_path` Swagger riceverebbe la
  CSP completa. Chi aggiunge un pulsante deve usare `data-click` + `registerActions`
  (fatto rispettare da `test_csp.py`).
- **Budget agenti**: soglia morbida (i run già ammessi possono superarla); senza
  `spend_file` ogni processo ha il proprio contatore.
- **Reload**: durante un reload lento le richieste che vedono la versione nuova occupano
  thread del pool in attesa del lock (l'event loop resta libero); l'ammissione di `/ask`
  è presa prima del reload.
- **LibreOffice**: la distinzione certa dipende dal testo inglese di `soffice`; in altre
  lingue si ricade sul messaggio "protetto o danneggiato" (comportamento precedente).
- **Archivio**: gli script di riproduzione archiviati presuppongono la vecchia posizione.
- `pipeline_agent.cjs` resta rotto come su `main`.

## Non verificabile in questo ambiente

- **CI GitHub**: i workflow modificati (permessi, SHA pinnati, nuovi step Node) sono
  validati solo come YAML e con test che li leggono; nessuna esecuzione reale.
- **Build Docker**: il daemon non è disponibile. `.dockerignore` è verificato col vero
  `moby/patternmatcher`, non con una build; la prima build in CI può confermare che
  `eval/results/history.jsonl` è nell'immagine. Le immagini pinnate sono verificate solo
  come esistenti sul registry.
- **Browser**: la verifica CSP è stata fatta con Chromium headless su un server senza
  indice (lifespan sostituito, alcune API finte); i flussi con dati reali (es. `/ask` in
  streaming) non sono stati cliccati, il loro codice è stato solo spostato. Nessun test
  su Firefox/Safari o su Windows (dove `mimetypes` può mappare `.js` a `text/plain`: il
  codice lo corregge, ma non è stato provato lì).
- **Qdrant reale e pesi Docling**: i 10 test saltati non sono stati eseguiti.

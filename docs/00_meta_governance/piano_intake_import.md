---
id: "meta-piano-intake-import-v1.0"
title: "Piano di Evoluzione — Intake & Import"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-21"
status: "ENFORCED"
classification: "METHODOLOGY"
path: "docs/00_meta_governance/piano_intake_import.md"
authority: 0.75
graph_rag:
  node_type: "DOCUMENT"
  node_id: "meta-piano-intake-import-v1.0"
  scope: "Piano operativo in 7 sessioni per l'evoluzione Intake & Import: generazione documentazione via Ollama, import documenti multi-formato con staging e review, import additivo di progetti esistenti in code/"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "REFERENZIA"
      target: "meta-change-log-v1.0"
---

# Piano di Evoluzione — Intake & Import

Piano in 7 sessioni (S0–S6) per evolvere vibecraft da "pipeline su docs/code preconfezionati" a sistema con ingresso controllato della conoscenza: una pagina per generare documentazione via Ollama o importare documenti di qualunque formato, e un flusso per importare progetti esistenti in `code/` per comprenderli, refactorarli ed evolverli.

Ogni sessione è un prompt copia-incolla **autonomo** da lanciare in una sessione Claude Code nuova, con modello consigliato, verdetto (farla o no) e **criteri di auto-commit/push**: se tutti i criteri passano, la sessione committa e pusha da sola; se anche uno fallisce, si ferma senza committare.

## Decisioni vincolanti (prese in fase di analisi, non rimetterle in discussione nelle sessioni)

1. **Staging con review**: nessun documento (generato o importato) entra in `docs/` o nell'indice senza approvazione esplicita dalla pagina.
2. **Import progetti NON distruttivo**: cartella target vuota → bootstrap (copia tutto); cartella popolata → additivo (copia solo file nuovi; i conflitti — file esistenti con contenuto diverso — si riportano nel piano e non si applicano MAI).
3. **Ingresso file**: documenti via upload dalla pagina; progetti via path locale.
4. **Formati documenti**: Markdown nativo + PDF, DOCX, HTML, TXT.

Cosa esiste già e va **riusato, non ricostruito**: parser multi-linguaggio in `rag/code_index/` (TS/TSX tree-sitter, C#, Razor, Java, SQL, shell, Docker, BPMN), esclusioni `CODE_EXCLUDED_DIRS` in `core/config.py`, indicizzazione delta plan/apply con writer lock (`core/indexing.py`, `core/writer_lock.py`), Ollama async (`core/llm.py` — qwen3.5:9b, `num_ctx` 16384, `think:false` sono fix di bug, non tuning), lezioni canvas (`core/canvas_review.py`), eval gate (`core/eval_gate.py`), template UI classico (`rag/templates/*.unified.html`).

## Regole valide per tutte le sessioni

- **Branch dedicato** `feat/intake-s<N>-<slug>`; merge su main solo a suite verde.
- **Protezioni**: mai toccare `rag/eval/results/BASELINE.json`; preservare l'equivalenza delta≡full (garantita dai test esistenti); ogni scrittura su `docs/`, `code/` o indice passa dal writer lock.
- **Messaggi di commit**: prefisso `S<N>:` + sintesi in italiano (stile del repo: `F3: espone la latenza...`).
- **Prerequisito per l'auto-commit/push**: prima della prima sessione, aggiungere in `.claude/settings.local.json` l'allowlist per `git commit` e `git push` (o avviare le sessioni in modalità accept-edits). Senza, la sessione chiederà comunque conferma e l'automatismo decade.
- **Ordine**: S0→S1→S2→S3→S4→S5→S6. Solo S5 è parallelizzabile con S3/S4 (dipende solo da S0).

## Tabella riassuntiva

| Sessione | Farla? | Modello consigliato | Branch | Dipende da |
|---|---|---|---|---|
| S0 Fondamenta e baseline | Sì (accorpabile a S1 se si vogliono 6 sessioni) | Sonnet 5 (Haiku 4.5 accettabile) | `feat/intake-s0-foundations` | — |
| S1 Convertitori multi-formato | Sì | Sonnet 5 | `feat/intake-s1-converters` | S0 |
| S2 Staging con review (API) | Sì — è il cuore del flusso | **Opus 4.8** | `feat/intake-s2-staging-api` | S1 |
| S3 Generazione doc con Ollama | Sì | Sonnet 5 | `feat/intake-s3-generation` | S2 |
| S4 Pagina Intake (UI) | Sì | Sonnet 5 | `feat/intake-s4-ui` | S2 (S3 per il tab Genera) |
| S5 Import progetti da path | Sì — la più delicata | **Opus 4.8** | `feat/intake-s5-project-import` | S0 |
| S6 Project brief + chiusura | Sì (solo il punto 1-brief è rinviabile) | **Opus 4.8** | `feat/intake-s6-brief-e-chiusura` | S2–S5 |

Motivazione dei modelli: Opus 4.8 dove si tocca il core dell'indicizzazione, la semantica non distruttiva o il confronto eval (S2, S5, S6 — errori lì costano cari); Sonnet 5 dove il pattern da seguire esiste già nel repo (convertitori, job async, UI su template noto).

---

## S0 — Fondamenta e baseline

**Farla?** Sì. È piccola ma ancora tutto: senza baseline misurata S6 non ha un termine di confronto. Accorpabile a S1 in un'unica sessione se si preferisce.
**Modello:** Sonnet 5 (Haiku 4.5 accettabile: lavoro meccanico su config e test).

**Prompt:**

```
CONTESTO — Repo vibecraft: app FastAPI in rag/ (core/=logica pura con DI, api/=route), docs/ indicizzati per sezione in Qdrant + grafo NetworkX, code/ contiene i progetti target (backend .NET "Portal", frontend Next.js, logicAgent vuota). Sto avviando l'evoluzione "Intake & Import" descritta in docs/00_meta_governance/piano_intake_import.md (leggilo prima di iniziare). Questa è la sessione S0: fondamenta, nessuna feature utente.

TASK
1) Baseline misurata: avvia Qdrant (docker compose up -d) e il server (uv run python server.py da rag/), esegui uv run python -m eval.run --k 5 10 e salva i numeri (recall@5, recall@10, mrr, data, commit) in rag/eval/results/intake_baseline.json. La cartella results/ ha un .gitignore su *.json: aggiungi il file con git add -f (come già fatto per multihop_20260721_110336.json). Poi spegni i servizi.
2) In core/config.py verifica CODE_EXCLUDED_DIRS: deve coprire i progetti reali presenti in code/ (.NET e Next.js): node_modules, .git, .next, dist, build, bin, obj, coverage, __pycache__, .venv, packages, TestResults. Aggiungi i mancanti, con un test che dimostri che un path contenente ciascuna dir esclusa viene scartato dalla scansione di code_index.
3) In rag_config.yaml aggiungi la sezione `intake:` con: staging_dir (default database/staging), allowed_formats [md, pdf, docx, html, txt], max_upload_mb (default 25), generation_max_files (default 5). Esponila da core/config.py come le altre sezioni. Le esclusioni per l'import progetti riusano CODE_EXCLUDED_DIRS: NON duplicare la lista.
4) Struttura staging: funzione di bootstrap lazy (pattern delle altre dir in database/) che crea staging/docs, staging/projects, staging/rejected e il journal append-only intake.jsonl (stesso pattern di reindex_jobs.jsonl). Solo scaffold + test: nessun endpoint, nessuna UI.

NON-GOAL — Niente convertitori, niente API, niente UI. Non toccare l'indicizzazione.

CRITERI DI AUTO-COMMIT/PUSH — Verifica nell'ordine. Se TUTTI passano: commit su branch feat/intake-s0-foundations con messaggio "S0: fondamenta intake (baseline, esclusioni, config, staging)" e git push -u origin feat/intake-s0-foundations, SENZA chiedere conferma. Se anche uno fallisce: NON committare, riporta il problema e fermati.
1. cd rag && uv run pytest → exit 0, zero failed/error.
2. scripts/ci.ps1 (o ci.sh) → EXIT=0 con server e Qdrant SPENTI.
3. git status --porcelain mostra modifiche SOLO in: rag/core/config.py, rag_config.yaml, rag/tests/, rag/eval/results/intake_baseline.json (force-add), eventuale modulo bootstrap staging. rag/eval/results/BASELINE.json intatto.
4. intake_baseline.json esiste, è JSON valido e contiene recall@5, recall@10, data e commit di riferimento.
5. uv run python -c "from core.config import <nomi esportati della sezione intake>" → exit 0.
```

---

## S1 — Convertitori multi-formato

**Farla?** Sì. È il prerequisito tecnico di tutto il ramo documenti.
**Modello:** Sonnet 5 — lavoro ben perimetrato su librerie note, il valore è nei test sulle fixture.

**Prompt:**

```
CONTESTO — Repo vibecraft, evoluzione "Intake & Import" (piano: docs/00_meta_governance/piano_intake_import.md, leggilo). S0 fatta: config `intake:` in rag_config.yaml, staging in rag/database/staging/, baseline in rag/eval/results/intake_baseline.json. Questa è S1: il layer di conversione documenti → Markdown. Nessun endpoint, nessuna UI.

TASK
1) Crea rag/core/intake_convert.py (logica pura, DI come il resto di core/): convert_to_markdown(source: bytes|Path, formato: str) -> ConversionResult(markdown, metadata) per: PDF (pymupdf, estrazione testo, niente OCR), DOCX (mammoth preferito, fallback python-docx; i titoli Word diventano #/##), HTML (BeautifulSoup + markdownify; scarta script/style/nav/footer), TXT (sezione unica con titolo = nome file). metadata: nome file sorgente, sha256, formato, data conversione, n. caratteri estratti. I metadata NON vanno nel markdown ora: finiranno nel frontmatter all'approvazione (S2).
2) Il markdown prodotto deve essere COMPATIBILE con core/chunking.py::parse_markdown_file: per ogni formato aggiungi un test che converte la fixture e la fa parsare senza errori, con almeno 1 sezione non vuota.
3) Fixture reali minime in rag/tests/fixtures/intake/: genera tu un PDF (via pymupdf), un DOCX (via python-docx), un HTML e un TXT con titoli e 2-3 paragrafi ciascuno.
4) Dipendenze nuove in pyproject.toml via uv (uv add), lockate in uv.lock.

EDGE CASE DA GESTIRE (con test) — file vuoto o illeggibile → ConversionError con messaggio chiaro, mai eccezione grezza; PDF senza testo estraibile (solo immagini) → errore esplicito "nessun testo estraibile"; HTML senza body; encoding non UTF-8 nel TXT (latin-1 fallback); formato non in allowed_formats → rifiuto a monte.

NON-GOAL — Niente scrittura in docs/ o staging, niente endpoint, niente OCR.

CRITERI DI AUTO-COMMIT/PUSH — Se TUTTI passano: commit su feat/intake-s1-converters, messaggio "S1: convertitori intake multi-formato (pdf/docx/html/txt → markdown)", git push -u origin feat/intake-s1-converters, senza chiedere. Altrimenti fermati senza committare.
1. cd rag && uv run pytest → exit 0.
2. scripts/ci.ps1 (o ci.sh) → EXIT=0 a servizi spenti.
3. git status --porcelain: modifiche SOLO in rag/core/intake_convert.py, rag/tests/, pyproject.toml, uv.lock. BASELINE.json e intake_baseline.json intatti.
4. I test di compatibilità col chunking passano per TUTTI e 4 i formati.
5. Ogni edge case elencato ha un test dedicato che passa.
```

---

## S2 — Staging con review (API)

**Farla?** Sì — è il cuore dell'evoluzione: senza questo ciclo il resto non ha sbocco.
**Modello:** **Opus 4.8** — tocca frontmatter conforme, indicizzazione delta e writer lock: la sessione più delicata del ramo documenti.

**Prompt:**

```
CONTESTO — Repo vibecraft, evoluzione "Intake & Import" (piano: docs/00_meta_governance/piano_intake_import.md, leggilo). Fatte S0 (config intake, staging dir, journal intake.jsonl) e S1 (core/intake_convert.py: pdf/docx/html/txt → markdown + metadata). Questa è S2: il ciclo completo upload → staging → preview → approva/rifiuta → docs/ + reindex delta, SOLO via API (UI in S4). Pattern del repo: core/=logica pura, api/=route FastAPI.

TASK
1) rag/core/intake.py: stage_document(filename, contenuto) → converte con intake_convert, salva originale + .md derivato in staging/docs/, appende al journal (id, stato "staged", source "imported", metadata); list_staged(); get_preview(id); approve(id, categoria_docs, nome_file); reject(id, motivo).
   - approve scrive il .md in docs/<categoria>/ con frontmatter CONFORME alle spec esistenti (guarda docs/00_meta_governance/change_log.md come riferimento: id, title, project, version, date, status, classification, path, authority, graph_rag.node_type/node_id/scope/edges). classification derivata dalla categoria scelta (00_meta_governance→METADATA, 01→NORMS, 02→REQUIREMENTS, 03→METADATA, 04→METHODOLOGY), authority di default da rag_config (intake.default_authority, aggiungila: 0.70), provenienza dai metadata S1 in un campo dedicato del frontmatter. Poi lancia l'indicizzazione DELTA della sola path aggiunta, sotto writer lock (riusa plan/apply di core/indexing.py). Ritorna esito con stats del job.
   - reject marca l'entry nel journal e sposta i file in staging/rejected/.
2) rag/api/routes_intake.py, montato come le altre route con auth X-API-Key: POST /api/intake/docs (upload multipart, valida estensione contro allowed_formats e dimensione contro max_upload_mb PRIMA di leggere tutto in memoria), GET /api/intake/staged, GET /api/intake/staged/{id}/preview, POST /api/intake/staged/{id}/approve (body: categoria, nome_file), POST /api/intake/staged/{id}/reject.
3) Test (pattern dei test di incremental indexing esistenti): ciclo e2e upload fixture PDF → staged → approve in 04_knowledge_informative → il chunk della nuova sezione esiste nell'indice e il nodo doc nel grafo; reject → docs/ e indice INTATTI; doppio approve dello stesso id → errore idempotente, non doppio file.

EDGE CASE DA GESTIRE (con test) — upload duplicato (stesso sha256 di un doc già staged o già approvato) → segnalato, non ri-staged; nome_file già esistente nella categoria target → errore, MAI sovrascrittura; frontmatter generato che non passa parse_markdown_file → approve fallisce PRIMA di scrivere in docs/; categoria inesistente → 422; upload oltre max_upload_mb → 413.

VINCOLI — Mai scrivere in docs/ fuori da approve. Equivalenza delta≡full preservata (i test esistenti devono restare verdi). Writer lock su ogni scrittura docs/indice.

CRITERI DI AUTO-COMMIT/PUSH — Se TUTTI passano: commit su feat/intake-s2-staging-api, messaggio "S2: staging con review via API (upload→approva→docs+reindex delta)", git push -u origin feat/intake-s2-staging-api, senza chiedere. Altrimenti fermati senza committare.
1. cd rag && uv run pytest → exit 0 (inclusi TUTTI i test preesistenti di indicizzazione/equivalenza).
2. scripts/ci.ps1 (o ci.sh) → EXIT=0 a servizi spenti.
3. git status --porcelain: modifiche SOLO in rag/core/intake.py, rag/api/ (routes_intake.py + registrazione), rag/tests/. Nessuna modifica a docs/ (i test usano tmp_path), BASELINE.json intatto.
4. Il test e2e "upload→approve→chunk nell'indice" passa; il test "reject non tocca docs/ né indice" passa.
5. Ogni edge case elencato ha un test dedicato che passa.
```

---

## S3 — Generazione doc con Ollama

**Farla?** Sì — è metà della richiesta originale ("genera N file md in base allo sviluppo che vuoi fare").
**Modello:** Sonnet 5 — il pattern job async Ollama esiste già in core/llm.py; il rischio è nel prompt, mitigato dal grounding e dalla validazione.

**Prompt:**

```
CONTESTO — Repo vibecraft, evoluzione "Intake & Import" (piano: docs/00_meta_governance/piano_intake_import.md, leggilo). Fatte S0-S2: esiste il flusso staging+review (core/intake.py, /api/intake/*): tutto ciò che entra in staging è approvabile verso docs/ con reindex delta. Questa è S3: generazione di documentazione via Ollama. VINCOLO LLM: qwen3.5:9b con num_ctx 16384 e think:false — sono fix di bug silenziosi, NON cambiarli.

TASK
1) rag/core/doc_generation.py: generate_docs(descrizione, n_file, categoria_target) come job ASYNC col pattern Ollama già usato in core/llm.py e dal canvas. Il prompt è GROUNDED: recupera contesto con hybrid_search sulla descrizione (top-k sezioni con citazioni) e include le lezioni del canvas review (stesso meccanismo di core/canvas_review.py). Chiedi al modello N documenti markdown, ciascuno con titolo, sezioni ## e una proposta di frontmatter minimale (title, scope); n_file è clampato a intake.generation_max_files (default 5, da S0).
2) Ogni file generato viene VALIDATO (parse_markdown_file senza errori, almeno 1 sezione non vuota) e poi entra in staging col flusso S2 (source "generated", metadata: descrizione richiesta, modello, latenze). Un file che non passa la validazione → scartato con motivo nel journal; il job riporta quanti generati/scartati. NESSUN percorso privilegiato verso docs/: la review S2 vale anche qui.
3) rag/api/routes_intake.py: POST /api/intake/generate (body: descrizione, n_file, categoria_suggerita) → job_id subito; GET /api/intake/generate/{job_id} → stato (pending/running/done/failed), esito, latenze (pattern di /ask: retrieval/generation/total).
4) Test con LLM MOCKATO (pattern dei test canvas): job creato → N file "staged" con source "generated" → approvabili col flusso S2; output LLM malformato (markdown rotto) → job "done" con scartati>0 e motivi nel journal; Ollama irraggiungibile → job "failed" con errore leggibile, mai eccezione non gestita. Un test di integrazione con Ollama reale marcato skip in CI.

NON-GOAL — Niente UI (S4). Nessuna modifica ai parametri LLM globali. Nessuna scrittura diretta in docs/ (deve esserci un test negativo che lo dimostra).

CRITERI DI AUTO-COMMIT/PUSH — Se TUTTI passano: commit su feat/intake-s3-generation, messaggio "S3: generazione doc via Ollama grounded, output in staging", git push -u origin feat/intake-s3-generation, senza chiedere. Altrimenti fermati senza committare.
1. cd rag && uv run pytest → exit 0 (integrazione Ollama skippata in CI).
2. scripts/ci.ps1 (o ci.sh) → EXIT=0 a servizi spenti.
3. git status --porcelain: modifiche SOLO in rag/core/doc_generation.py, rag/api/routes_intake.py, rag/tests/.
4. Il test negativo "la generazione non scrive mai direttamente in docs/" passa.
5. I test su output malformato e Ollama irraggiungibile passano.
```

---

## S4 — Pagina Intake (UI)

**Farla?** Sì — è la pagina richiesta; senza UI il flusso resta per soli sviluppatori.
**Modello:** Sonnet 5 — UI self-contained su template già esistente, API già pronte e testate.

**Prompt:**

```
CONTESTO — Repo vibecraft, evoluzione "Intake & Import" (piano: docs/00_meta_governance/piano_intake_import.md, leggilo). Backend completo e testato: /api/intake/docs (upload), /staged (+preview/approve/reject), /generate (+stato job). Le pagine esistenti usano template self-contained (niente CDN) in rag/templates/*.unified.html con route in api/routes_pages.py. Questa è S4: la pagina Intake.

TASK
1) rag/templates/intake.unified.html sul pattern di pipeline.unified.html, con route pagina /intake in api/routes_pages.py e voce di navigazione aggiunta alle pagine esistenti (stesso posto dove sono linkate le altre).
2) Tre zone: (a) "Genera con Ollama": textarea descrizione, numero file (max = intake.generation_max_files), categoria docs target, bottone Avvia → polling dello stato job, esito con generati/scartati e latenze; (b) "Importa documenti": upload multiplo drag&drop (pdf/docx/html/txt/md), esito conversione per file con errori leggibili; (c) "In staging": lista dei doc staged (nome, source imported/generated, data) con preview markdown renderizzata, scelta categoria + nome file, bottoni Approva (mostra esito reindex delta) e Rifiuta (con motivo).
3) Stati visibili: vuoto ("niente in staging"), errore upload (formato/dimensione), job LLM fallito, approve fallito (nome duplicato, frontmatter invalido) — i messaggi arrivano dalle API, la UI li mostra, non li reinterpreta.
4) Test: route /intake risponde 200 e contiene i 3 blocchi; nessuna nuova logica di dominio nel template/JS (tutto passa dalle API già testate).
5) Verifica manuale col server dev (uv run python server.py + Qdrant): ciclo completo genera → staging → approva → /ask risponde con contenuto del nuovo doc. Riporta l'esito nel messaggio finale (non è un gate di commit).

NON-GOAL — Nessun nuovo endpoint. Nessuna dipendenza esterna/CDN nel template.

CRITERI DI AUTO-COMMIT/PUSH — Se TUTTI passano: commit su feat/intake-s4-ui, messaggio "S4: pagina /intake (genera, importa, review staging)", git push -u origin feat/intake-s4-ui, senza chiedere. Altrimenti fermati senza committare.
1. cd rag && uv run pytest → exit 0.
2. scripts/ci.ps1 (o ci.sh) → EXIT=0 a servizi spenti.
3. git status --porcelain: modifiche SOLO in rag/templates/intake.unified.html, rag/api/routes_pages.py, rag/templates/* (solo per il link di navigazione), rag/tests/.
4. Il template non contiene URL esterni (grep di http:// e https:// nel template → solo riferimenti locali o nessuno).
5. Il test sulla route /intake passa.
```

---

## S5 — Import progetti da path (plan/apply additivo)

**Farla?** Sì — è l'altra metà della richiesta originale, e la sessione più delicata in assoluto: qui vive la garanzia "mai sovrascrivere".
**Modello:** **Opus 4.8** — semantica non distruttiva, backup, writer lock, reindex: un errore qui tocca i progetti reali dell'utente.

**Prompt:**

```
CONTESTO — Repo vibecraft, evoluzione "Intake & Import" (piano: docs/00_meta_governance/piano_intake_import.md, leggilo). code/ contiene i progetti target: backend (.NET "Portal"), frontend (Next.js), logicAgent (vuota). Fatta S0 (CODE_EXCLUDED_DIRS completa, config intake, staging, journal). Questa è S5: import di progetti esistenti dal filesystem locale in code/, con semantica NON distruttiva DECISA E VINCOLANTE: cartella target vuota → bootstrap (copia tutto il copiabile); cartella popolata → additivo (copia SOLO file nuovi; file esistenti identici per sha256 → skip; file esistenti con contenuto diverso → CONFLITTI, riportati nel piano e MAI applicati).

TASK
1) rag/core/project_import.py col pattern plan/apply di core/indexing.py:
   - plan_project_import(src_path, target ∈ {backend, frontend, logicAgent}) scansiona src applicando CODE_EXCLUDED_DIRS e le estensioni CODE_EXTS di code_index, e ritorna un ImportPlan: modalità (bootstrap|additivo), liste {nuovi, identici, conflitti, esclusi} con path relativi, totali. Il plan è un DRY-RUN puro: zero scritture.
   - apply_project_import(plan) esegue sotto writer lock: (i) backup zip della cartella target attuale in staging/projects/backups/ con timestamp (anche in bootstrap, se la cartella non è vuota di soli .gitkeep); (ii) copia dei SOLI file "nuovi"; (iii) entry nel journal intake.jsonl (target, sorgente, totali, path backup); (iv) reindicizzazione del codice: delta se il flusso incrementale la copre, altrimenti ritorna nel risultato l'avviso esplicito "serve full rebuild per i code-link" (limite noto del grafo doc-level, non nasconderlo).
   - apply rifiuta un plan stale: se lo stato della cartella target è cambiato dopo il plan (confronta un fingerprint calcolato nel plan), errore "ripeti l'anteprima".
2) rag/api/routes_intake.py: POST /api/intake/project/plan {path, target} e POST /api/intake/project/apply {plan_id o plan}. Validazioni: path assoluto, esistente, directory; path NON dentro il repo vibecraft né dentro staging (errore esplicito); target solo tra i tre ammessi.
3) UI: quarta zona nella pagina /intake — input path + select target, bottone "Anteprima" che mostra il piano (n nuovi/identici/conflitti/esclusi, con elenco espandibile dei conflitti), bottone "Applica" attivo SOLO dopo un'anteprima, esito con path del backup e stato reindex.
4) Test con fixture mini-progetto in tmp_path: bootstrap su cartella vuota copia tutto il copiabile; additivo copia i nuovi, salta gli identici, riporta i conflitti e NON modifica i file esistenti (verifica per sha256 prima/dopo); un node_modules finto e un bin/ finto non passano; backup zip creato e riapribile; plan stale rifiutato; path dentro il repo rifiutato.

VINCOLI ASSOLUTI — apply non sovrascrive e non cancella MAI un file esistente in code/. Nessuna scrittura fuori da code/<target>/ e staging/projects/. Tutto sotto writer lock.

CRITERI DI AUTO-COMMIT/PUSH — Se TUTTI passano: commit su feat/intake-s5-project-import, messaggio "S5: import progetti plan/apply additivo con backup e conflitti", git push -u origin feat/intake-s5-project-import, senza chiedere. Altrimenti fermati senza committare.
1. cd rag && uv run pytest → exit 0.
2. scripts/ci.ps1 (o ci.sh) → EXIT=0 a servizi spenti.
3. git status --porcelain: modifiche SOLO in rag/core/project_import.py, rag/api/routes_intake.py, rag/templates/intake.unified.html, rag/tests/. NESSUNA modifica dentro code/ (i test usano tmp_path).
4. Il test "additivo non modifica mai file esistenti (sha256 prima/dopo)" passa.
5. Il test "esclusioni rispettate" e il test "plan stale rifiutato" passano.
6. Il test "path dentro il repo rifiutato" passa.
```

---

## S6 — Project brief + chiusura

**Farla?** Sì per i punti 2–4 (e2e, eval vs baseline, README): sono la chiusura del lavoro. Il punto 1 (brief) è l'unico rinviabile, ma è ciò che trasforma "codice importato" in "codice compreso e citabile dal RAG" — il senso della feature refactoring/evoluzione.
**Modello:** **Opus 4.8** — integrazione trasversale e confronto eval: se qualcosa è regredito, serve diagnosi, non solo esecuzione.

**Prompt:**

```
CONTESTO — Repo vibecraft, evoluzione "Intake & Import" (piano: docs/00_meta_governance/piano_intake_import.md, leggilo). Fatte S0-S5: pagina /intake completa (genera Ollama, importa doc, review staging, import progetti plan/apply). Questa è S6, l'ultima: project brief + chiusura. Baseline di riferimento: rag/eval/results/intake_baseline.json (da S0). VINCOLO LLM: qwen3.5:9b, num_ctx 16384, think:false — non cambiarli.

TASK
1) "Project brief": POST /api/intake/project/brief {target} + bottone nella zona import di /intake, attivo dopo un import riuscito. Genera via Ollama (job async, pattern S3) un documento di sintesi architetturale del target: componenti, entrypoint, dipendenze principali, mappa simboli→spec (dagli archi IMPLEMENTS del grafo), aree candidate a refactoring. GROUNDED sui dati reali del grafo: usa graph_ops/retrieval per raccogliere simboli e archi del target, non inventare. Il brief entra in STAGING come ogni altro doc (source "brief", categoria suggerita 04_knowledge_informative) e passa dalla review S2: nessun percorso diretto verso docs/.
2) Test e2e dell'intera evoluzione (LLM mockato): importa mini-progetto in tmp code → reindex → genera brief → staged → approva → una retrieve/ask di test lo trova. Più i test del brief: target senza import → 409; grafo senza simboli per il target → job done con avviso, non crash.
3) Eval di chiusura: con server + Qdrant accesi esegui uv run python -m eval.run --k 5 10 e CONFRONTA con intake_baseline.json: recall@5 e recall@10 non devono essere inferiori. Scrivi l'esito (numeri prima/dopo) nel messaggio finale.
4) Documentazione: aggiorna rag/README.md con la sezione "Intake & Import" (pagina /intake, endpoint /api/intake/*, semantica additiva e vincolo mai-sovrascrivere, formati supportati, flusso staging→review→docs); aggiorna l'infografica se elenca le pagine.

CRITERI DI AUTO-COMMIT/PUSH — Se TUTTI passano: commit su feat/intake-s6-brief-e-chiusura, messaggio "S6: project brief grounded + e2e + eval di chiusura + docs", git push -u origin feat/intake-s6-brief-e-chiusura, senza chiedere. Altrimenti fermati senza committare.
1. cd rag && uv run pytest → exit 0, incluso il nuovo e2e.
2. scripts/ci.ps1 (o ci.sh) → EXIT=0 a servizi spenti (spegnili dopo l'eval).
3. git status --porcelain: modifiche SOLO in rag/core/, rag/api/, rag/templates/intake.unified.html, rag/tests/, rag/README.md, eventuale template infografica.
4. L'eval è stata ESEGUITA DAVVERO (niente stima) e recall@5 e recall@10 sono ≥ ai valori di intake_baseline.json. Se i servizi non sono disponibili o l'eval regredisce: NIENTE commit, riporta i numeri e fermati.
5. Il test negativo "il brief non scrive mai direttamente in docs/" passa.
```

---

## Rischi noti (da tenere d'occhio durante le sessioni)

- **Qualità conversione PDF**: PDF impaginati male producono markdown rumoroso; la review in staging è il punto dove scartarli (per questo S1 precede la UI).
- **Code-link doc-level**: dopo un import progetto i link simbolo→sezione possono restare stali fino a un full rebuild; S5 lo dichiara nell'esito invece di nasconderlo.
- **Generazione su modello 9B**: N file coerenti è il compito più fragile; mitigato da grounding RAG + lezioni canvas + clamp a 5 file + validazione in ingresso allo staging (S3), non all'approvazione.

## Residui della roadmap precedente (indipendenti da questo piano)

- Verifica esperimento M6 `incremental_advisory` dovuta il **2026-08-04** (regola di decisione in rag_config.yaml).
- Task T1 (2026-10-19, criterio a 3 condizioni) mai creato.

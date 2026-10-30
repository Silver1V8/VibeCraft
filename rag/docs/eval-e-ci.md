Italiano | [English](../README.en.md)

> Documentazione operativa sotto `rag/docs/`: **non** è corpus RAG (il corpus è `docs/` del progetto). Stesso schema degli ADR. Italiano canonico; l'inglese resta un indice breve in `rag/README.en.md`.

[← Indice operativo](../README.md)

# Eval del retrieval e CI

## Eval del retrieval: da attrezzo da banco a guardrail

La qualità del retrieval si misura sul golden-set
([eval/golden_set.yaml](../eval/golden_set.yaml)) con [eval/run.py](../eval/run.py),
che interroga il server reale (`GET /api/retrieve`, così riusa il modello già
caricato) e salva ogni run in `eval/results/`. La modalità guardrail dà exit code 1 se il
recall **alla `k` dell'eval-gate** scende sotto la soglia dell'eval-gate — oggi
`recall@2 < 0.75` — con il report scritto comunque; `--assert-min` sostituisce quella
soglia per una corsa singola.

**Comando consigliato prima di ogni merge che tocca chunking, ranking o pesi
di autorità** (server su):

```bash
uv run python -m eval.run
```

Ultima misura (2026-10-30, 58 casi, corpus di esempio 50 documenti / 384 chunk, indice
`v20261030T111436`): `recall@1 0.724 · @2 0.828 · @5 0.948 · @10 0.983`, MRR 0.818,
avversariali al primo posto 5 su 5. Con l'autorità quasi spenta (α 0.1) sullo stesso indice:
`recall@1 0.690 · @2 0.828 · @5 0.966 · @10 0.983`, MRR 0.802, avversariali 2 su 5.

**Il guardrail asserisce sulla `k` dell'eval-gate, e con la sua soglia** — entrambe lette
da `eval_gate` in [rag_config.yaml](../rag_config.yaml), oggi `recall@2 ≥ 0.75`. `--k`
sceglie quali colonne *leggere*, mai su cosa si fallisce, e la `k` del gate viene misurata
comunque anche se non la chiedi. `--assert-min` resta per abbassare o alzare la soglia in
una corsa singola.

**Prima asseriva sul k più alto passato** (A2b), e i due script notturni non passano `--k`:
il loro confronto cadeva su `recall@10`, **satura a 1.000**, contro un `--assert-min 0.90`
scritto a mano. Un `--assert-min` su una metrica satura non è severo, è cieco — lo supera
qualunque regressione che non faccia uscire una fonte dai primi dieci — e quello era un
check notturno che, per costruzione, non poteva fallire.

`recall@5` era saturata a 1.000 dopo l'istanziazione ed è tornata a 0.983 quando il
corpus si è arricchito ancora: **il gate resta comunque a k=2**. Un gate che cambia
`k` a ogni modifica del corpus non è un gate — la stabilità della soglia vale più di
qualche punto di sensibilità.

Il criterio *«/ask inietta 8 sezioni, quindi conta se la fonte entra nella
finestra, non a che rango»* resterebbe valido — ma un gate deve prima di tutto
**distinguere una regressione**, e a @5 non distingue più nulla. Se anche
`recall@2` saturasse non resterebbe un k più basso utile: vorrà dire che il
golden-set ha smesso di essere una misura e va **esteso** con casi che il sistema
sbaglia, non abbassata un'altra soglia.

Questo comando richiede il server acceso (modello caricato): per questo NON è
nella pipeline CI (vedi [sezione CI](#ci)), resta manuale pre-merge finché non
matura la regola di promozione descritta lì.

**Tre letture, non una media sola** (S5, [ADR 0002](../adr/0002-autorita-dichiarata-e-fiducia-sul-cammino.md)).
La corsa standard riporta il recall a **k ∈ {1, 2, 5, 10}**, e non per completezza:

- **la saturazione è segnalata come difetto, non come 100%.** Una recall che vale
  1.000 su *tutti* i casi non è un buon risultato: è una misura che ha smesso di
  discriminare. Il report la marca `⚠️ SATURA` sulla riga della metrica. È un
  errore già commesso: la ricalibrazione dei pesi di autorità del 2026-07-22 girò
  a k=10 e k=5 su una griglia interamente satura e concluse — correttamente ma
  inutilmente — che nessuna combinazione era distinguibile.
- **il sottoinsieme avversariale ha una voce a sé.** I casi marcati
  `adversarial: true` nel golden-set (oggi 5 su 58) contrappongono una fonte a
  bassa autorità che matcha lessicalmente *meglio* della normativa che risponde:
  sono l'unico posto dove il boost di autorità può essere falsificato, e nella
  media coi casi facili il loro movimento sarebbe invisibile. **Dal 2026-10-30 sono 5 su 5
  al primo posto**: il quinto («quanti caratteri al massimo può avere un chunk…») perdeva
  0,511 a 0,479 contro la nota di metodologia perché [REGOLA-VAL-02] e [REGOLA-VAL-06]
  scrivevano la soglia solo come segnaposto e la nota il numero. Corretto nel corpus, non
  nei pesi: la regola riporta il default, la nota cita le regole che spiega e diventa una
  riformulazione (peso di sezione 0,92). Simulato prima con bge-m3 (margine +0,036),
  misurato dopo il reindex: recall@1 0,707 → 0,724, le altre invariate. Il prezzo: a k=1 il
  sottoinsieme ora è **saturo**, quindi segnala una regressione ma non misura più un
  miglioramento; servono casi avversariali nuovi per tornare a discriminare.
- **i pesi di autorità si calibrano con [eval/calibrate_authority.py](../eval/calibrate_authority.py)**,
  che gira in-process (niente server) e **non applica nulla**: scrive una proposta
  in `eval/results/authority_calibrated.yaml` da rivedere a mano. Calibrare
  **sempre** con split di validazione, **sempre** a un k non saturo e **sempre**
  su più seed — il default è 5-fold su 5 seed con deviazione standard riportata,
  perché su un solo split un guadagno sopra soglia si è già rivelato rumore di
  partizione. Lo script segnala anche gli **assi morti**, cioè i parametri che sul
  corpus corrente non muovono la metrica di un millesimo.
- **`boost_alpha` e `section_restatement_weight` sono accoppiati: calibrarli uno alla
  volta è un errore già commesso (S11, [rag_config.yaml](../rag_config.yaml)).** Sono
  entrambi un moltiplicatore sullo stesso composito di `/ask` (pertinenza × fiducia ×
  autorità), quindi il guadagno dell'uno dipende dal valore dell'altro. Una griglia
  congiunta su `boost_alpha` × `default_weight` × `unclassified_weight` ×
  `section_restatement_weight` (2160 punti, 5-fold × 5 seed) ha confermato in
  produzione `boost_alpha: 0.3` (era 0.1 dal 2026-07-14, calibrato allora da solo) e
  `section_restatement_weight: 0.92` (confermato, non spostato): a k=1 il guadagno
  held-out è **+0.038**, e ad alpha 0.3 il tetto del contesto da grafo
  (`graph_context_max_chunks`) è salito a 3 — a 2 una catena multihop perdeva la
  terza fonte in finestra. Dettagli in [AUDIT.md §S11](../../archive/adr/AUDIT.md).
- **e ciò che il recall NON misura: a chi la risposta attribuisce il vincolo.** Il
  recall dice se la fonte giusta è stata *recuperata*; `/ask` ne inietta fino a 8 e
  l'LLM le legge tutte, quindi il recall può essere ottimo mentre la risposta cita
  come fonte del vincolo il documento che lo *illustra*. È successo davvero — 2 casi
  avversariali su 4, indagine A3 in [AUDIT.md](../../archive/adr/AUDIT.md) — e la correzione
  (`[CLASSE-FONTI]`: la classe dichiarata nell'intestazione di ogni blocco del
  contesto, più la graduatoria delle classi presenti) **non ha mosso il recall di un
  decimale**, perché il ranking era già corretto. Chi tocca il prompt di `/ask` non
  ha una metrica che lo protegga: legga le risposte.

```bash
uv run python -m eval.calibrate_authority --k 5   # proposta, mai applicazione automatica
```

### La seconda suite: strutturale e multihop

[eval/golden_multihop.yaml](../eval/golden_multihop.yaml) + [eval/run_multihop.py](../eval/run_multihop.py)
misurano le domande che il golden-set classico non copre: **enumerare** («quali documenti
esistono nel corpus?»), **navigare** («cosa impatta la modifica di X?») e **combinare due o
tre documenti collegati**. Su ogni domanda misura due strade — **A** il retrieval puro
(`/api/retrieve`, k=10) e **B** la query deterministica sul grafo (`/api/graph/query`) — così
il divario fra le due è un numero, non un'impressione.

```bash
uv run python -m eval.run_multihop        # server su; exit 1 sotto soglia
```

### La terza misura: a chi la risposta attribuisce il vincolo

[eval/golden_attribution.yaml](../eval/golden_attribution.yaml) + [eval/attribution.py](../eval/attribution.py):
la fonte giusta entra sempre nel contesto (A3), ed è **dentro** la finestra che il modello
decide chi stabilisce un vincolo e chi lo motiva. Un giudice LLM legge ogni risposta — una
chiamata per esecuzione, mai aggregata per caso — e nomina la fonte a cui la risposta lo
attribuisce; i passi fra virgolette sono verificati con un `in` sul documento attribuito.
Non è un gate né un check notturno: costa chiamate LLM e i numeri vanno letti (AUDIT.md, S14).

```bash
uv run python -m eval.attribution --repeats 3   # (a) valida il giudice offline: solo Ollama
uv run python -m eval.attribution --live        # (b) misura /ask: server SENZA cache
```

**Il giudice, misurato: 20/24 in-sample, e non passa il criterio fissato per validarlo**
([AUDIT.md §S14](../../archive/adr/AUDIT.md)). Sei formulazioni del prompt provate sugli stessi 24 record
d'archivio (temperatura 0, un'unica chiamata per esecuzione, JSON frase→verbo→fonte); tenuta
la migliore (v4: 20/24 d'accordo con l'umano, 5/7 sui negativi, 24/24 di giudizi ripetibili in
tre esecuzioni). Il criterio di S6 era «se non coincide col verdetto umano, il giudice non è
pronto»: non coincide, e in 3 casi su 4 dei disaccordi il giudice sceglie il documento che
**illustra** il vincolo invece di quello che la risposta dice lo **stabilisce** — la stessa
confusione che la metrica esiste per misurare nel modello giudicato, riprodotta nel modello
giudice (sono lo stesso modello, `qwen3.5:9b`, l'unico installato). Sul conto binario del modo
(b) — «la fonte è quella attesa, sì/no» — l'accordo sale a 22/24 con **0 negativi mancati su
7**: uno schermo utile per decidere quali risposte far rileggere a un umano, non ancora una
metrica automatica. Apre **R29** (AUDIT.md, RESIDUI.md): serve un giudice su un modello diverso
prima di poter promuovere questa misura a gate.

**Il secondo giudice, `qwen3.8:27b` (2026-10-29): 21/24, e non passa neanche lui.** Stesso
prompt, nessuna nuova taratura, `purposes.judge` solo per la corsa: positivi 16/17, negativi
ancora 5/7, unanimi 24/24, ma **1 negativo mancato** (05·2) dove il 9b ne mancava 0. Come
schermo è peggio, e costa 27 minuti per 72 giudizi contro meno di due. Il 07·2 cade sullo
stesso distrattore di `qwen3.5:9b` e di nimble: il difetto resta dentro la famiglia Qwen.
Il giudice di default resta quindi il 9b. Per la decisione S8 il passo successivo è un
provider remoto, che però manda il corpus fuori dalla macchina: va deciso, non eseguito.
Evidenze in [archive/eval-results/attribution_qwen38_20261029](../../archive/eval-results/attribution_qwen38_20261029/evidence/METHOD.md).

**R29 chiuso il 2026-10-30: `claude-opus-5-5` passa, 24/24.** Positivi 17/17, negativi
**7/7**, unanimi 24/24, nessun falso allarme e nessun negativo mancato, con il prompt di S14
invariato. Il 07·2 che tutta la famiglia Qwen sbagliava qui è giusto. Il giudice si sceglie
dal menu Impostazioni (scopo «Giudice di attribuzione»); questa corsa usava il provider
`claude_code`, cioè Claude Code con l'abbonamento, senza API key. Il giudice locale resta il
default: senza scelta nel menu l'harness usa Ollama. Limiti: stessi 24 record su cui il
prompt era stato tarato, campione piccolo. Per la decisione S8 ora il modo (b), `--live`,
può entrare nelle tabelle. Evidenze in
[archive/eval-results/attribution_claude_20261030](../../archive/eval-results/attribution_claude_20261030/evidence/METHOD.md).

**Quattro casi su 14 non possono passare A, ed è la misura, non un difetto.**
L'enumerazione chiede 11 fonti a un top-10, e le tre catene che spandono tre documenti si
fermano a due: è esattamente il gap che ha motivato il router deterministico. Per questo la
soglia — `eval_multihop` in [rag_config.yaml](../rag_config.yaml) — sta sulla **recall media di
A** (0.85, con 0.896 misurato) e sull'**esattezza piena delle attese strutturali di B**, mai
sul numero di casi «riusciti»: sarebbe un numero che il sistema non può far salire.

A differenza di `recall@10` sul golden-set classico, **questa metrica non è mai stata satura**.

Fino al 2026-09-03 la suite girava solo a mano (A4): ora ogni corsa lascia una riga in
`history.jsonl` (`source="multihop"`, chiavi prefissate per non mescolarsi con l'altra
suite) e, sotto soglia, un alert critico — ed è nel check notturno insieme all'eval classico.

**Il caso che non passava, e perché la sua storia resta qui** (chiuso il
2026-08-25). *«posso usare un sinonimo per nominare una variabile o devo seguire
il glossario»* è stato per settimane l'unico dei 59 a non comparire in top-10.
L'attesa puntava a `coding_standards § Tracciabilità della Governance`, e sembrava
un caso scritto male.

Non lo era. Quando il golden-set fu redatto (commit `3a95322`, 2026-07-22)
`coding_standards.md` era alla **v2.0.0 cross-progetto** e possedeva
`[REGOLA-CLEAN-07] Allineamento terminologico rigido`, che risponde esattamente a
quella domanda. La copia di lavoro era però tornata alla **v1.0.0
dominio-specifica**, ferma a `CLEAN-04`: la regola esisteva solo nel committato, e
il RAG indicizza il disco. Tre file divergevano, e la divergenza era **invisibile a
`git status`** perché i file di `docs/` sono `skip-worktree`. Il difetto non era né
nell'indice né nel ranking: era nel corpus, e nulla lo guardava.

Ripristinato il baseline committato, il caso **passa** (atteso a rango 3) e
l'intero golden-set rientra in top-10. Due effetti collaterali che valgono più
della singola riga verde:

- **due casi avversariali erano stati scartati per il motivo sbagliato.** «Estrazione
  dei magic numbers» e «isolamento delle regole di business» erano stati giudicati
  *disonesti* perché `coding_standards.md` non trattava quegli argomenti: sono
  `[REGOLA-CLEAN-05]` e `[CLEAN-06]`, presenti nel baseline e assenti dalla copia di
  lavoro. Il giudizio era una conseguenza della divergenza, non del caso.
- **un caso avversariale ha smesso di esserlo.** «Tracciabilità bidirezionale nei
  commenti» lo era perché `vibe_coding_workflow.md` v1.0.0 ridefiniva
  `[REGOLA-CLEAN-*]` con una numerazione collidente. La v2.0.0 rimanda a
  `coding_standards.md` invece di duplicarlo: sparita la collisione, l'atteso va a
  rango 1 e il marcatore `adversarial` è stato tolto — un caso che il sistema supera
  gonfierebbe la recall del sottoinsieme. Gli avversariali sono passati da 10 a 9.

Da qui il check [`docs_git`](#reindex-automatico-lindice-non-invecchia-mai): la
divergenza è tornata visibile, e a ogni check notturno resta tale.
I test pytest, che non possono caricare bge-m3, coprono la **meccanica** del
guardrail con un retriever fake deterministico
([tests/test_eval_guardrail.py](../tests/test_eval_guardrail.py)): parsing del
golden-set, matcher, calcolo del recall, soglia che scatta, estrazione e
promozione dei candidati. Saturazione, sottoinsieme avversariale e integrità dei
matcher avversariali (devono puntare a documenti e sezioni realmente esistenti nel
corpus) sono in [tests/test_retrieval_eval.py](../tests/test_retrieval_eval.py). Le
metriche vere restano i comandi qui sopra.

**Il golden-set cresce dalle change (ciclo archive → golden-set):**

1. **Canvas** — alla generazione del canvas il server persiste in
   `changes/<feature>/meta.json` i documenti normativi usati dal retrieval
   governato (`governed_sources`, parsati dagli header del contesto).
2. **Archive → candidato** — `archive_feature` estrae deterministicamente
   (nessun LLM) un caso candidato: query = nome feature + prima riga del
   canvas, expected = quei documenti. Lo accoda a `eval/candidates.yaml`
   (append-only, dedup per query, **mai** nel golden-set diretto).
3. **Revisione umana** — `uv run python -m eval.run --review-candidates`
   mostra i candidati; `--promote 0 2` SPOSTA quelli scelti nel
   `golden_set.yaml` (append testuale: i commenti del file sopravvivono).
4. **Soglia** — con il golden-set aggiornato, rilancia l'eval e rifissa
   `eval_gate.min_recall` poco sotto il nuovo valore misurato. È lì che vive la
   soglia, e da lì la leggono gate, guardrail, check notturno e dashboard.


## CI

Pipeline minima, senza servizi esterni: [scripts/ci.sh](../scripts/ci.sh) (POSIX,
usato anche dalla pipeline) / [scripts/ci.ps1](../scripts/ci.ps1) (Windows) fanno
`uv sync --frozen` (installazione riproducibile da `uv.lock`), poi `uv run ruff
check .` (selezione esplicita in `pyproject.toml`: import inutilizzati, variabili
morte, nomi ambigui, import fuori ordine — non il default del tool, che su questo
codebase mai linterato aggiungerebbe ~380 preferenze di stile discrezionali),
infine `uv run pytest -q`. Il primo comando che fallisce ferma la pipeline:

```bash
scripts/ci.sh
```

```powershell
pwsh -File scripts/ci.ps1
```

Qdrant e Ollama possono restare spenti: la suite li mocka ovunque (httpx2.MockTransport,
attributi di `core.llm` monkeypatchati, `fastapi.testclient.TestClient` in-process). I
soli 5 test che parlano con un Qdrant reale
([tests/test_qdrant_blue_green.py](../tests/test_qdrant_blue_green.py), sezione
"OPZIONALE / SKIPPABLE") richiedono l'opt-in `VIBECRAFT_TEST_QDRANT_URL` verso un
servizio dedicato ai test. Senza questa variabile saltano prima di connettersi;
non usano il `QDRANT_URL` dell'applicazione. In CI `VIBECRAFT_REQUIRE_QDRANT=1`
rende obbligatoria sia la configurazione esplicita sia la disponibilità del servizio.

**Eseguire quei cinque su un Qdrant di test dedicato prima di toccare il
blue/green**, per esempio impostando `VIBECRAFT_TEST_QDRANT_URL=http://127.0.0.1:16333`
quando quel servizio è predisposto: sono il posto dove le assunzioni sulla semantica di Qdrant
(atomicità del batch di alias, risoluzione dell'alias nelle point-operation —
`upsert` *e* `delete`-by-filter —, invalidazione degli alias alla cancellazione
della collection) vengono verificate contro il servizio vero invece che contro
`AliasAwareFakeQdrant`, che quelle stesse assunzioni le replica. Un fake e il
codice che verifica possono sbagliare insieme; il servizio reale no.

**CSS Tailwind precompilato.** Console, Pipeline e Guida usano `static/tailwind.css` e
`static/tailwind-infografica.css`, generati da [scripts/build_css.sh](../scripts/build_css.sh)
(Tailwind 3.4.17 via `npx`, configurazioni in `static/tailwind/`). Dopo aver aggiunto
classi Tailwind nuove a template o script di pagina va rilanciato e il CSS committato:
la CI lo rigenera e fallisce se differisce, perché una classe senza regole lascerebbe
l'elemento senza stile in silenzio.

```bash
bash scripts/build_css.sh
```

Il remote effettivo del repo determina la config della pipeline: su GitHub è
[.github/workflows/ci.yml](../../.github/workflows/ci.yml) (job `test` che chiama
`scripts/ci.sh`); su GitLab sarebbe `.gitlab-ci.yml` con uno stage `test` equivalente.
Nota: il resto del progetto (webhook `X-Gitlab-Token`, `extract_gitlab_paths`,
l'indicizzatore `.gitlab-ci.yml` in [code_index/ci.py](../code_index/ci.py)) presuppone
GitLab come piattaforma — se il remote cambia, la config della pipeline va allineata di
conseguenza.

**Eval NON è nella pipeline (per ora):** `uv run python -m eval.run` (vedi sopra)
richiede il server acceso coi modelli caricati — non lo può lanciare una pipeline
che non prevede servizi. Resta un comando manuale
pre-merge per chi tocca chunking, ranking o pesi di autorità.

**Regola di promozione a stadio bloccante:** l'eval diventa uno stadio CI
bloccante SOLO dopo **10 esecuzioni locali consecutive verdi** (nessun flake)
registrate in `eval/results/`. Fino ad allora resta un comando manuale, non
gating. Quando la soglia è raggiunta, aggiungere alla pipeline uno stage
`eval` opzionale/non bloccante prima, poi promuoverlo a bloccante.

**Test intermittente noto:** in run locali senza servizi la suite completa può
occasionalmente andare in errore a cascata (molti `ERROR` di setup/teardown con
`UnicodeDecodeError`) invece che in un singolo test fallito. La causa nota è un
thread daemon di `ReindexManager` che sopravvive al teardown di
`test_archive_stream_route_queues_full_and_emits_final_event`
([tests/test_reindex.py](../tests/test_reindex.py)) e logga (`api/deps.py:263`,
caratteri accentati) dopo che la capture di pytest è già smontata — su console
non-UTF-8 questo corrompe il file di capture FD-level e fa fallire in cascata i
test successivi. `scripts/ci.sh`/`ci.ps1` impostano `PYTHONUTF8=1` per evitare la
cascata, ma non eliminano la causa: il fix corretto (sincronizzare il test con la
fine reale del thread via `ReindexManager.join_all`) esiste già altrove nella
storia del repo e va portato su questa linea prima di considerare la suite
completamente stabile in CI.


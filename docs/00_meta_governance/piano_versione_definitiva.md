# Piano — Versione definitiva di vibecraft/rag

> Obiettivo strategico: **un unico knowledge graph a livello di sezione/simbolo — docs + codice fusi —
> sempre fresco per delta, con i pesi di autorità calibrati sul golden set invece che scritti a mano,
> e un eval-gate continuo che governa la promozione blue/green.**
>
> Tema di fondo: il sistema oggi *codifica giudizio* (autorità, safeguard, canvas). Il passo definitivo è
> farlo **misurare il proprio giudizio** contro il golden set, invece di fidarsi di costanti hardcoded.

Ogni prompt qui sotto è **auto-contenuto**: aprilo in una sessione Claude Code dalla cartella `rag/` e
incollalo così com'è. L'ordine conta: ogni epic assume la precedente conclusa e verde.

Convenzioni:
- Lavora su un branch per epic (`feat/epic-N-...`), non su `main`.
- "Verde" = `uv run pytest` passa **e** l'eval-gate non è regredito (vedi Epic 0).
- Non rompere la compatibilità dei chiamanti legacy: le funzioni di `core/indexing.py` hanno parametri
  opzionali proprio per questo — mantieni quella disciplina.

---

## Stato di partenza (fatti verificati nel codice, luglio 2026)

- Retrieval ibrido a 3 livelli (dense + sparse + ColBERT) con riponderazione per autorità in
  `core/retrieval.py`; i pesi sono la tabella statica `AUTHORITY_CLASS_WEIGHTS`.
- Il retrieval **chiave su `chunk_id`** (sezione), ma il grafo aggiunge **nodi-documento**
  (`_add_doc_to_graph`): granularità disallineata.
- Il delta-indexing (`apply_incremental_indexing`) **già ricalcola i code-link in modo incrementale** ed è
  "deterministicamente equivalente al full rebuild" (lo prova `check_graph_consistency`). Ciò che resta
  doc-level sono i **nodi del grafo**, non il relink del codice.
- `core/indexing.py` = 1281 righe: il file più grande e più critico.
- Golden set + eval harness HTTP già esistono (`eval/golden_set.yaml`, `eval/run.py`, `--assert-min`),
  ma l'eval gira come gate su job *full*, non sul delta, e non c'è trend storico di qualità.
- Retrieval sincrono in threadpool (TODO in `api/routes_retrieval.py:118`).

---

## Epic 0 — Baseline & rete di sicurezza  *(prerequisito, ~mezza giornata)*

Serve una linea di base misurata prima di toccare qualsiasi cosa, altrimenti non sapremo se
"calibrare l'autorità" o "il grafo a sezioni" migliora o peggiora.

### Prompt 0.1 — Congela la baseline di qualità
```
Contesto: sto per iniziare un refactor profondo del sistema RAG in rag/. Prima voglio una baseline
di qualità misurata e riproducibile.

Task:
1. Avvia il server (documenta il comando esatto in un commento) e lancia `uv run python -m eval.run
   --k 5 10`. Salva l'output in eval/results/ (già lo fa).
2. Copia quel risultato in eval/results/BASELINE.json e aggiungi in cima al file un commento/campo
   "note" che spieghi: commit hash, data, e che è la baseline pre-versione-definitiva.
3. Scrivi in docs/00_meta_governance/piano_versione_definitiva.md, sotto questo epic, una riga con
   recall@5 e recall@10 medi della baseline.
4. Verifica che `uv run pytest` sia interamente verde e riporta il numero di test.

Non modificare logica di prodotto in questo prompt: è solo misura.
```

### Prompt 0.2 — Amplia il golden set (la calibrazione è forte quanto il golden set)
```
Contesto: il golden set eval/golden_set.yaml guida sia l'eval-gate sia la futura calibrazione dei pesi
di autorità. Oggi ha pochi casi. Voglio coprire meglio le classi di documento e i code-link.

Task:
1. Leggi eval/golden_set.yaml e il formato dei matcher (doc/section/chunk/file).
2. Aggiungi almeno 10 nuovi casi che coprano esplicitamente: (a) documenti IRON_MEMORY vs METHODOLOGY
   sulla stessa query ambigua — per stressare l'autorità; (b) query che dovrebbero risolvere su codice
   (endpoint, classi Java/C#) e non su docs; (c) sorgenti ARCHIVED/DEPRECATED che NON devono comparire.
3. Ogni caso deve avere `expected` verificabile: prima di aggiungerlo, interroga il retrieval reale e
   conferma che la sezione attesa esista davvero (heading `##` reale). Scarta i casi non verificabili.
4. Rilancia `uv run python -m eval.run` e riporta come cambia recall@k con i nuovi casi.

Vincolo: non "barare" scegliendo solo casi che già passano — includi 2-3 casi che oggi FALLISCONO, così
il piano ha margine di miglioramento misurabile.
```

**Baseline (misurata — Prompt 0.1, commit `10de3c1`, 2026-07-14, indice `v20260714T083926`):**
recall@5 = **86.4%**, recall@10 = **90.9%**, mrr = **0.868**, top3 = 86.4% — su 22 casi.
N test = **272** (tutti verdi). Salvata in `eval/results/BASELINE.json`.
Casi non risolti da migliorare: 2 MISS + 1 recuperato solo a k≤10 (timeout sessione, scenario BDD
accesso dominio esterno, constraint DB integrità) → target naturale per l'ampliamento in Prompt 0.2.

**Golden set ampliato (Prompt 0.2, 2026-07-14):** 22 → **34 casi**. Aggiunti 8 casi di copertura per le
spec finora non testate (concurrency, wf_states, notifications, dash, export, area_pers, coding_standards)
+ 1 caso di autorità (safeguard IRON_MEMORY che deve battere METHODOLOGY) + 3 casi difficili con margine
(1 MISS reale sul double-booking, 2 recuperati solo a rank 6-7). Tutti verificati contro il retrieval
reale prima dell'inserimento. Nuova misura: recall@5 = **82.4%**, recall@10 = **91.2%**, mrr = 0.821.
Il calo di recall@5 è voluto: i casi difficili danno spazio di miglioramento agli Epic 2-3.

> ⚠️ **Limiti onesti del golden set attuale** (impattano gli Epic successivi):
> - **Categoria (b) code-resolving — SBLOCCATA il 2026-07-14**: aggiunto codice frontend reale in
>   `code/frontend/` (8 file JS + HTML/CSS). Il full rebuild (versione `v20260714T131848`, grafo 210→235
>   nodi) ha creato **21 nodi di codice + 21 archi IMPLEMENTS** simbolo→documento (via similarità argmax,
>   weight 0.51–0.65). **Epic 2 è ora validabile su code-link reali.** MA la qualità dei link conferma
>   perché serve l'Epic 2 + il matching http_calls:
>     - link corretti: `session.js`→spec_auth, `richiediPage.js::renderForbidden`→matrice_permessi,
>       `badge.js`/`eventiPage.js`→spec_dash.
>     - link deboli/sbagliati: `api.js::fetchEventiAttivi/inviaRichiesta/fetchMieRichieste`→glossario
>       invece della spec che definisce `/api/eventi`,`/api/mie-richieste` (l'argmax pesca il vocabolario,
>       non l'endpoint); `styles.css`→spec_form (rumore, è CSS). → **Epic 2.1 dovrebbe far puntare i link
>       alla SEZIONE vincente (non al doc) e l'http_calls-matching (TODO in code_index/frontend.py) agli
>       endpoint; una soglia di weight poterebbe il rumore CSS.**
>   NB: il parser frontend è React/Angular-aware; questo codice è JS vanilla (`fetch`, ES modules, no
>   package.json) → i simboli sono estratti dal parser JS sintattico, l'http_calls Angular NON scatta.
> - **Categoria (c) archived-must-not-appear NON coperta**: nessun doc è ARCHIVED/DEPRECATED (tutti
>   ENFORCED) **e** `core/eval_metrics.py` non supporta matcher negativi. Prerequisito per Epic 3
>   (calibrazione autorità sui pesi di decay per status): aggiungere un matcher `absent`/`forbidden` a
>   eval_metrics + fixture archiviate, altrimenti il fattore-decay 0.3 non è misurabile.
>
> **Bug corretto durante l'indicizzazione del codice (2026-07-14):** `core/chunking.py::parse_markdown_file`
> faceva `split("---")` sull'intero documento → qualsiasi markdown con righe orizzontali `---` e `:` nel
> testo mandava in crash `yaml.safe_load` durante il rebuild. Fix: il frontmatter è riconosciuto solo se
> delimitato in cima al file. +2 test di regressione in `tests/test_chunking.py`.

---

## Epic 1 — Scomposizione di `core/indexing.py`  *(abilitante, nessun cambio di comportamento)*

Rendere sicuro tutto il resto. 1281 righe monolitiche sono il rischio-manutenzione n°1: qui un bug
diventa corruzione d'indice silenziosa. Refactor puramente strutturale, comportamento identico.

### Prompt 1.1 — Estrai il sottopacchetto `core/indexing/`
```
Contesto: core/indexing.py (1281 righe) mescola quattro responsabilità: identità/id deterministici,
costruzione full, diff del delta (plan), applicazione del delta (apply). Voglio scomporlo in un
sottopacchetto SENZA cambiare comportamento.

Task:
1. Trasforma core/indexing.py nel pacchetto core/indexing/ con:
   - identity.py   -> _point_id e la logica di id deterministico (uuid5).
   - graph_build.py-> _add_doc_to_graph, _remove_doc_nodes_from_graph, _prune_unsupported_entities,
                      _entity_nodes, e gli helper di edge/node set (_edge_set, _node_type_set).
   - full.py       -> FullState, _build_full_state, build_graph_and_index, _ensure_collection,
                      _encode_chunks_to_points, _dense_map.
   - plan.py       -> IndexPlan, plan_incremental_indexing, _diff_hashes, _partition_changed_paths,
                      _restrict_plan, gli hash (_docs_hashes/_code_hashes) e il manifest
                      (write_index_manifest/_read_manifest/index_status).
   - apply.py      -> apply_incremental_indexing, incremental_index, _delete_doc_chunks,
                      _apply_code_delta, e tutti gli helper _relink_*/_symbols_*/_sorted_chunk_ids.
   - integrity.py  -> check_index_integrity, check_graph_consistency, check_drift, archive_feature,
                      _record_review_skip, _load_dev_type.
2. core/indexing/__init__.py deve ri-esportare TUTTI i simboli pubblici usati altrove (grep dei chiamanti
   in api/ e tests/ prima, per non rompere import). L'obiettivo è: `from core.indexing import X`
   continua a funzionare identico per ogni X esistente.
3. Nessuna modifica di logica. Nessun rename di funzione pubblica. Solo spostamenti + import.

Accettazione:
- `uv run pytest` verde con lo STESSO numero di test di prima (Epic 0).
- Nessun file del nuovo pacchetto supera ~400 righe.
- `git diff --stat` mostra solo spostamenti (verifica che non ci sia logica cambiata).
```

### Prompt 1.2 — Blindatura anti-corruzione dell'apply
```
Contesto: apply.py (ex apply_incremental_indexing) è il punto dove un bug corrompe l'indice in silenzio.
Voglio che qualsiasi divergenza dal full rebuild venga scoperta subito, non a valle.

Task:
1. Aggiungi in integrity.py una funzione assert_delta_equivalent(...) che, dato lo stato dopo un delta,
   confronta (edge_set, node_type_set, insieme dei chunk_id in Qdrant) con quello di un full rebuild
   ricostruito a parte, e ritorna un report di diff strutturato (aggiunti/mancanti), NON solo un bool.
2. Aggiungi un test in tests/test_incremental_indexing.py che: parte da un indice, applica una sequenza
   di delta realistici (doc modificato, doc cancellato, file di codice nuovo che cita un'entità), e
   asserisce assert_delta_equivalent == vuoto. Deve fallire se qualcuno rompe il relink incrementale.
3. Esponi un flag opzionale in incremental_index(..., verify=False) che, se True, esegue
   assert_delta_equivalent al termine e logga un alert (via il canale alerts.jsonl esistente) se diverge.

Accettazione: pytest verde; il nuovo test cattura una regressione se commenti di proposito una riga di
_relink_touched_symbols (provalo e poi ripristina).
```

---

## Epic 2 — Grafo a livello di sezione/simbolo, fresco per delta  *(il cuore della versione definitiva)*

Oggi il retrieval chiave su `chunk_id` ma il grafo ragiona su nodi-documento. Allineare le due
granularità sblocca percorsi interrogabili "sezione normativa → endpoint → classe" sempre freschi.

> 📌 **Scoperte dal codice reale (2026-07-14) che riducono l'Epic 2:**
> - `code_index/__init__.py::link_symbols` **calcola già `win_chunk`** (la sezione vincente, riga ~509) ma
>   disegna l'arco IMPLEMENTS su `win_doc` (riga ~519). Retarget alla sezione = cambiare quella riga +
>   garantire che `win_chunk` sia un nodo del grafo. La soglia `threshold=0.45` esiste già.
> - **NON esistono nodi-endpoint** nel grafo (backend assente; le spec citano `/api/...` solo in prosa) →
>   il matching `fetch()`→endpoint del Prompt 2.2 è rimandato finché non c'è un backend o un'estrazione di
>   endpoint dalle spec. Nel frattempo il retarget-a-sezione da solo migliora già la precisione dei link
>   (es. `session.js`→sezione "Flusso Funzionale" di spec_auth invece del doc intero).
> - Il rumore CSS (`styles.css`→spec_form @0.52) va tolto NON linkando i file non-semantici (css/html) o
>   alzando la soglia solo per loro — piccolo fix di precisione da fare in 2.1.

### Prompt 2.1 — Promuovi i nodi-documento a nodi-sezione
```
Contesto: in core/indexing/graph_build.py, _add_doc_to_graph crea UN nodo per documento. Ma il retrieval
e il chunking lavorano per sezione (chunk_id = "doc#NN-slug"). Voglio che il grafo abbia nodi a livello
di SEZIONE, con un arco di appartenenza sezione->documento, mantenendo il documento come nodo-contenitore.

Task:
1. In graph_build.py, aggiungi _add_section_nodes(G, doc_id, chunks, metadata) che per ogni chunk crea un
   nodo tipo "section" con attributi: chunk_id, doc_id, section (heading), classification, status
   (gli stessi che oggi guidano _authority_weight in retrieval.py). Collega section -[:PART_OF]-> document.
2. I code-link (IMPLEMENTS/REFERENCES) che oggi puntano al doc devono puntare alla SEZIONE vincente
   (il chunk con argmax di similarità), non al documento intero. Adatta gli helper _symbols_*/_relink_*
   in apply.py di conseguenza, mantenendo l'equivalenza delta<->full (Epic 1.2 la verifica).
3. Aggiorna graph_ops.py (bfs_expand, build_context, impact, full_graph, graph_query, semantic_map) per
   gestire i nodi section: l'espansione del contesto deve poter partire da una sezione e risalire al doc.
4. Migrazione: un full rebuild rigenera il grafo nella nuova forma. NON serve migrare indici esistenti
   (si rigenerano), ma documenta in un commento che il primo run post-deploy richiede un full rebuild.

Accettazione:
- pytest verde; adegua i test di graph_ops/indexing che asseriscono la forma vecchia.
- Un nuovo test: dato un code-link, il target è un nodo section col chunk_id atteso, non il doc.
- L'eval-gate (recall@k) NON deve regredire vs baseline Epic 0. Se regredisce, indaga il context build.
```

### Prompt 2.2 — Sfrutta i nodi-sezione nel retrieval (espansione governata)
```
Contesto: ora il grafo ha nodi-sezione con classification/status. Voglio che la selezione del contesto
in core/retrieval.py sfrutti il grafo per aggiungere sezioni adiacenti ad alta autorità (es. la safeguard
collegata a un endpoint recuperato), invece di limitarsi ai top-k del retrieval vettoriale.

Task:
1. Dopo la fusione ibrida e prima della sintesi LLM, espandi i chunk vincenti di 1 hop nel grafo delle
   sezioni (usa graph_ops.bfs_expand a depth=1) e includi le sezioni collegate SOLO se il loro
   _authority_weight supera una soglia (parametrizzabile, default conservativo).
2. Il budget di contesto resta governato: se l'espansione sfora, tieni le sezioni a più alta autorità.
   Non deve mai far scendere le sezioni direttamente rilevanti sotto il taglio.
3. Rendi l'espansione disattivabile via parametro (default: attiva) per poter A/B testare sull'eval.

Accettazione:
- pytest verde; nuovo test che verifica che una safeguard collegata venga inclusa quando supera soglia.
- Lancia l'eval con espansione ON e OFF e riporta recall@k nei due casi in un commento del PR: l'ON deve
  essere >= OFF sui casi del golden set che testano i code-link/safeguard (Epic 0.2).
```

---

## Epic 3 — Autorità calibrata sul golden set  *(da opinione hardcoded a regola misurata)*

`AUTHORITY_CLASS_WEIGHTS` (1.0/0.9/0.7/0.5) e il fattore 0.3 per gli archiviati sono oggi congelati nel
codice. Con il golden set possiamo *misurarli* invece di indovinarli.

### Prompt 3.1 — Estrai i pesi in configurazione + grid search
```
Contesto: in core/retrieval.py, _authority_weight usa la tabella statica AUTHORITY_CLASS_WEIGHTS e il
fattore 0.3 per status archiviati/deprecati. Voglio poter calibrare questi valori contro eval/golden_set.

Task:
1. Sposta AUTHORITY_CLASS_WEIGHTS e il fattore-decay in core/config.py (o un authority_weights.yaml
   caricato da config), con gli STESSI valori attuali come default: comportamento invariato di partenza.
2. Scrivi eval/calibrate_authority.py: uno script che esegue una grid/coordinate search sui pesi
   (riusa l'harness di eval/run.py per valutare il golden set via HTTP a ogni combinazione) e trova la
   combinazione che massimizza recall@k medio. DEVE essere onesto: split del golden set in
   calibrazione/validazione (o k-fold) per non fare overfit; riporta il punteggio sul solo set di
   validazione.
3. Lo script stampa un confronto "pesi attuali vs pesi calibrati" e scrive un authority_weights.yaml
   proposto in eval/results/, SENZA applicarlo automaticamente.

Accettazione:
- pytest verde (il default non cambia nulla finché non si applica il file).
- Lo script gira end-to-end e produce un report leggibile. Riporta di quanto migliora recall@k in
  validazione: se il guadagno è <1-2%, dillo esplicitamente — potrebbe non valere la pena e i pesi a mano
  vanno bene. Onestà > entusiasmo.
```

### Prompt 3.2 — Applica e blinda contro overfit
```
Contesto: eval/calibrate_authority.py ha prodotto pesi candidati. Voglio applicarli SOLO se reggono la
validazione, e proteggere il sistema da future ricalibrazioni che fanno overfit.

Task:
1. Se (e solo se) i pesi calibrati battono i default sul set di validazione oltre una soglia minima
   (es. +1.5% recall@10), applica authority_weights.yaml come nuovo default e aggiorna il commento in
   config con: data, guadagno misurato, dimensione del set di validazione.
2. Aggiungi un test tests/test_authority_calibration.py che asserisce che i pesi caricati sono nel range
   [0,1] e che l'ordinamento delle classi è monotono e sensato (IRON_MEMORY >= AUTHORIZATION_POLICY >=
   ... ) — un guardrail contro pesi assurdi prodotti da una futura grid search buggata.
3. Documenta in docs/ (norma architetturale) che i pesi di autorità sono ORA calibrati e come
   ri-calibrarli, con l'avvertenza di usare sempre split di validazione.

Accettazione: pytest verde; l'eval-gate migliora o resta uguale; nessun peso fuori range.
```

---

## Epic 4 — Retrieval async + eval-gate continuo sul delta  *(il ciclo stretto)*

Chiudere l'anello: ogni delta indicizzato viene valutato e, se la qualità scende, la promozione
blue/green si blocca. Più il TODO async di `routes_retrieval.py`.

### Prompt 4.1 — Rendi async la catena di retrieval
```
Contesto: api/routes_retrieval.py:118 ha un TODO: il retrieval gira sincrono in un threadpool. Le chiamate
LLM/Ollama e Qdrant sono I/O-bound. Voglio una catena async pulita.

Task:
1. Converti il percorso di retrieval (hybrid_search -> riponderazione -> build context -> sintesi LLM) in
   async dove l'I/O lo giustifica: usa httpx.AsyncClient per le chiamate a Ollama/LLM e ai sidecar
   (ColBERT), e le API async di qdrant-client se disponibili. La CPU-bound (encode dei vettori) resta in
   threadpool via run_in_executor — non fingere che sia async.
2. Rimuovi il TODO e il wrapping in threadpool dell'intero handler; mantieni identica la firma HTTP e la
   forma della risposta JSON.
3. Nessuna regressione funzionale: stessi risultati, stesso ordine.

Accettazione:
- pytest verde (adegua i test che mockano il client sync -> async).
- L'eval-gate produce gli STESSI recall@k di prima (è un cambio di performance, non di ranking).
- Riporta un micro-benchmark before/after su una manciata di query concorrenti.
```

### Prompt 4.2 — Eval-gate continuo dentro la promozione blue/green
```
Contesto: oggi l'eval-gate gira sui job full. Il versioning blue/green (database/versions/ + CURRENT,
promote/rollback) promuove una nuova versione dell'indice. Voglio che l'eval-gate sia una CONDIZIONE di
promozione anche per gli aggiornamenti delta, non solo per i full.

Task:
1. Individua la funzione di promote nel modulo di versioning (cerca "promote"/"CURRENT" in core/ e api/).
2. Prima di promuovere una nuova versione (full O delta), esegui un mini-golden-set contro l'indice
   CANDIDATO (non ancora CURRENT). Se recall@k medio < soglia (config, default = baseline Epic 0 meno un
   piccolo margine), RIFIUTA la promozione, logga un alert su alerts.jsonl e lascia CURRENT invariato.
3. Per non pagare il costo su ogni piccolo delta, rendi la frequenza governabile: sempre sui full, e sui
   delta solo se toccano documenti con classification alta (IRON_MEMORY/AUTHORIZATION_POLICY) o se sono
   passati N delta dall'ultimo gate. Documenta la policy.
4. La valutazione deve girare contro l'indice candidato senza renderlo CURRENT: se serve, valuta in un
   contesto isolato/porta separata. NON deve mai valutare contro produzione servendo query reali.

Accettazione:
- pytest verde; nuovo test che simula una versione candidata "peggiore" e verifica che la promozione
  venga rifiutata e CURRENT resti invariato.
- Un test del percorso felice: candidata migliore/uguale -> promozione riesce.
```

---

## Epic 5 — Osservabilità → valutabilità: trend di qualità storicizzato

Oggi si logga la salute (alerts.jsonl, /api/health) ma non c'è un trend di *qualità*. Le regressioni si
scoprono per caso. Ultimo tassello: renderle un segnale.

### Prompt 5.1 — Storicizza e traccia recall@k per versione
```
Contesto: eval/results/ contiene run JSON puntuali. Voglio un trend leggibile "recall@k nel tempo / per
versione dell'indice", così le regressioni sono un segnale e non una scoperta.

Task:
1. Ogni run di eval (eval/run.py) e ogni eval-gate (Epic 4.2) deve appendere una riga a
   eval/results/history.jsonl con: timestamp, commit hash, versione indice (da CURRENT), recall@k per
   ogni k, N casi, e un flag se era un gate di promozione. Non riscrivere i JSON puntuali: aggiungi solo.
2. Aggiungi un endpoint read-only GET /api/eval/history che restituisce lo storico (ultimi N), e una
   piccola pagina statica (riusa lo stile di static/templates esistente) che disegna recall@k nel tempo
   con marcatori sulle versioni promosse/rifiutate.
3. Aggiungi a /api/health un campo "eval": {last_recall_at_10, trend: up|flat|down vs media mobile}.

Accettazione:
- pytest verde; test dell'endpoint history (lista non vuota dopo un run) e del campo health.
- La pagina si apre e mostra almeno la baseline + i punti accumulati durante gli epic precedenti.
```

### Prompt 5.2 — Chiudi il cerchio: alert su regressione di qualità
```
Contesto: ora esiste il trend. Voglio che una regressione di qualità sostenuta generi lo stesso tipo di
alert notturno già usato per la consistenza (scripts/nightly_consistency).

Task:
1. Estendi il check notturno esistente (scripts/nightly_consistency.*) o aggiungine uno gemello che:
   lancia l'eval, appende a history.jsonl, e se recall@10 è sotto la media mobile delle ultime M run oltre
   una soglia, scrive un alert su alerts.jsonl e (se configurato) chiama il webhook notturno esistente.
2. Documenta la runbook: cosa significa l'alert, come indagare (confronta l'ultima versione promossa,
   guarda i casi del golden set che sono passati da pass a fail).

Accettazione: il check gira a mano end-to-end; un test/simulazione con storia in discesa produce l'alert.
```

---

## Ordine di esecuzione & dipendenze

```
Epic 0  (baseline)      ─┬─> Epic 1 (refactor)  ──> Epic 2 (grafo a sezioni)
                         │                              │
                         └─> Epic 3 (autorità)  <───────┘  (usa i nodi-sezione, ma non li richiede)
                                     │
                                     └─> Epic 4 (async + gate continuo) ──> Epic 5 (trend qualità)
```

- **Epic 0 è bloccante per tutto** (senza baseline non sai se migliori).
- **Epic 1 prima di Epic 2**: non toccare il grafo mentre `indexing.py` è ancora monolitico.
- **Epic 3 dipende debolmente da Epic 2**: la calibrazione funziona anche a nodi-documento, ma i nodi-
  sezione la rendono più precisa. Se vuoi un risultato veloce, Epic 3 si può fare subito dopo Epic 1.
- **Epic 4.2 richiede Epic 0.2** (golden set robusto) o il gate è troppo rumoroso.
- **Epic 5 è l'ultimo**: ha bisogno che eval-gate ed eval-run producano dati da storicizzare.

## Definizione di "fatto" (la versione definitiva è completa quando…)

- [x] Il grafo ha nodi-sezione; i code-link puntano alla sezione vincente; delta ≡ full (verificato). ✅ Epic 2.1 (commit 1dbfbf2): `type="section"` + PART_OF, IMPLEMENTS→win_chunk, CSS/HTML non linkati (21→19), 275 test verdi.
- [ ] `core/indexing/` è un pacchetto, nessun file > ~400 righe, comportamento invariato.
- [ ] I pesi di autorità sono in config, calibrati con split di validazione (o documentato che i default
      reggono), con guardrail sul range.
- [ ] Il retrieval è async; il TODO in routes_retrieval è rimosso.
- [ ] La promozione blue/green è condizionata all'eval-gate anche sui delta ad alta autorità.
- [ ] `eval/results/history.jsonl` + pagina trend + campo health "eval"; alert notturno su regressione.
- [ ] recall@k finale **≥** baseline Epic 0 (idealmente >, mai <).
```

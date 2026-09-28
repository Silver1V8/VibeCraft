# Pilot Docling — chiusura: audit, schermo delle citazioni, suite, attribuzione

**2026-09-09** · ramo `codex/evoluzione-p0` · HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`
· nessun branch, commit, push o PR · `AGENTS.md` assente

## Verdetto

**BLOCCATO**, e non per una firma mancante: c'è un **difetto di risposta
confermato e riproducibile** — `pdf-diag-3` fallisce in **tutte e tre le passate
di tutti e quattro gli stack** — e la correzione generale tentata è
**NON_APPLICARE** perché non lo risolve e sfonda un budget dichiarato.

Il perimetro resta quello della sessione precedente: **documenti rigenerati con
il template corretto**, non i PDF originali immutabili né PDF esterni generici.

Cinque cose vanno tenute distinte, e questa sessione le separa:

| | esito |
|---|---|
| **conversione Docling** | **verificata**, riusata dopo controllo di integrità e corrispondenza |
| **correzione del template** | prerequisito della conversione verificata, **non ancora implementata in produzione** |
| **correzione generale di generazione** (variante di prompt) | **NON_APPLICARE** — non corregge il difetto e supera il budget del prompt |
| **qualità e attribuzione finali** | 7/8 stabile in ogni stack; **un difetto confermato**; attribuzione di sezione imperfetta in **entrambi** gli stack |
| **autorizzazione all'integrazione** | **non concessa** da questa sessione |

## FASE 1 — l'audit ha trovato tre difetti negli strumenti, non solo nelle risposte

Dettaglio completo in [`audit/AUDIT_MISURE_PRECEDENTI.md`](audit/AUDIT_MISURE_PRECEDENTI.md);
le nuove valutazioni delle sedici risposte archiviate sono in
`audit/audit_finale_20260909-110000.json`, gli originali restano intatti
(`out/verifica_riuso.json`: 61 file dichiarati, **zero alterati**).

1. **Lo schermo delle citazioni.** `eval_stack.py` aveva ri-scritto l'estrattore
   invece di riusare `eval/attribution.py`, e nella ri-scrittura l'apostrofo
   ASCII era un **delimitatore**: in italiano è segno di elisione dentro le
   parole, quindi ogni `l'`, `dell'`, `all'` apriva o chiudeva una citazione. Da
   lì `) dedicata all`. La soglia era inoltre in caratteri (≥12) invece che in
   parole. Su 15 «citazioni» archiviate, **12 erano artefatti di parsing**.
2. **Il corpus di verifica non conteneva i PDF.** La mappa dei chunk cercava un
   campo `chunk_id` che in `chunks.json` è la **chiave** del dizionario: restava
   vuota. Ogni `testo` archiviato è la stringa vuota, e la riga che inseriva i
   PDF nel corpus non veniva mai eseguita. Nessuna citazione tratta da un PDF
   poteva risultare verificata. Riletti i chunk dall'indice davvero interrogato,
   una citazione del baseline passa da `unverifiable` a `verified`.
3. **«8/8 completa» misurava una sottostringa.** Per `pdf-diag-4` i valori
   attesi erano `["5", "1"]`: due cifre nude.

Correzione: **riuso** di `eval.attribution.quoted_spans`
([`scripts/citazioni.py`](scripts/citazioni.py)), con i chiamanti verificati
prima (harness N3 e `tests/test_attribution.py`). Il controllo minimo
[`scripts/check_citazioni.py`](scripts/check_citazioni.py) supera **7 casi su
7**: apostrofi interni, virgolette doppie, caporali, Markdown, delimitatore
aperto e non chiuso, chiusura orfana, e una citazione inventata che **resta**
`unverifiable`. Nessuna modifica al repository.

## FASE 2 — i quattro punti sollevati

- **`pdf-diag-4` attribuisce i KPI alla sezione sbagliata: confermato.** Nel
  Markdown la banda KPI **precede** `### Regole di organizzazione`. La risposta
  la attribuisce a quella sezione (`valore_in_altra_sezione`, effettiva:
  `Catalogo diagrammi`) e cita una sezione «Indice operativo» che **non esiste**
  (sono le prime due parole della frase introduttiva). L'errore **non** è nella
  segmentazione né nei metadati: il PDF produce un solo chunk, la sua `section`
  è `Catalogo diagrammi`, e l'intestazione di blocco che il modello riceve è
  corretta — la risposta stessa la cita. Nasce nella **generazione**.
- **`pdf-diag-3` interpreta «peso» come Authority: confermato, in entrambi gli
  stack.** Vedi sotto: è il difetto che blocca.
- **Lo schermo delle citazioni non era affidabile: confermato**, per due cause
  indipendenti, entrambe corrette.
- **La suite aveva tre fallimenti: risolti.** Vedi FASE 3.

## FASE 3 — la suite è verde, senza toccare un'asserzione

Le tre cause, riprodotte prima di correggere:

| test | causa accertata | correzione |
|---|---|---|
| `test_reconciler_never_writes_to_qdrant_or_local_state` | la fixture nomina `vibecraft_events__v1/v2` alla lettera mentre l'alias è parametrizzato su `COLLECTION_NAME`; `list_qdrant_collections` filtra per lignaggio, quindi con la collection rinominata restituisce `[]`. Riprodotto: `parse_qdrant_collection_version('vibecraft_events__v1')` → `None` con `pilot_candidate_events`, → `'v1'` con il nome standard | **ambiente**: l'isolamento non ha bisogno di rinominare la collection — bastano **istanza, porta e volume Qdrant propri**. Il nome torna quello di lignaggio dentro il Qdrant isolato |
| `test_index_rollback_local_failure_never_calls_qdrant_alias_helper` | `resolve_rollback_target(None)` solleva `ValueError` («è la versione più vecchia») **prima** di arrivare al `rollback_version` monkeypatchato, perché il sandbox aveva **una sola** versione | **ambiente**: indice costruito **due volte**. È lo stato che il test descrive, non un trucco |
| `test_archivio_dichiara_di_essere_storico_quando_lo_e` | l'archivio copiato portava `superseded_by` della **produzione** | **ambiente**: `superseded_by` è un campo mantenuto a mano (lo dice il commento nel file); nel sandbox nomina la versione attiva **del sandbox** |

Nessuna asserzione modificata, nessuno `skip`, nessun `xfail`, nessun test
rimosso, nessuna modifica al repository — verificato: `core/retrieval.py` e
`core/chunking.py` dei sandbox sono **byte-identici** al repository, e
`rag_config.yaml` pure (il nome di collection torna quello di produzione:
l'isolamento è per endpoint).

| suite | test | falliti | errori | **saltati** |
|---|---:|---:|---:|---:|
| catena **candidata** (`venv-novlm`, Python 3.14.6) | 1342 | **0** | 0 | **0** |
| catena **applicativa** (`.venv` del repo) | 1342 | **0** | 0 | **0** |
| catena applicativa **+ variante di prompt** | 1342 | **1** | 0 | 0 |

`VIBECRAFT_REQUIRE_QDRANT=1`: con Qdrant irraggiungibile i test sollevano invece
di saltare. **Zero saltati** significa che i test di integrazione con Qdrant reale
sono stati eseguiti davvero.

## FASE 4 — dove nasce l'errore su `pdf-diag-3`, e perché non è Docling

La domanda congelata chiede «quale diagramma documenta i checkpoint
human-in-the-loop, e **con quale peso**?». Attesa: `19.5 KB`.

**Il dato c'è, arriva nel contesto, ed è recuperabile.** Lo prova la sonda
diagnostica ([`scripts/sonda_diagnostica.py`](scripts/sonda_diagnostica.py) —
prove **aggiuntive**, mai sostitutive delle domande congelate):

| sonda | baseline | candidato |
|---|---|---|
| «quanti **KB** occupa il file…» | **19.5 KB** ✓ | **19.5 KB** ✓ |
| «valore della colonna «Formato / peso» per la riga…» | **19.5 KB** ✓ | **19.5 KB** ✓ |

Con la parola «peso» nella domanda, invece, **nessuno dei due stack** risponde,
in **nessuna** delle tre passate. Le risposte agganciano «peso» alla scala di
autorevolezza e concludono con `0.30`, `0.87`, `0.90` — o dichiarano che «il
contesto non riporta un valore». La forma che assumono è, parola per parola,
quella di `[CLASSE-FONTI]` in `core/retrieval.py`: «se un vincolo è enunciato
SOLO da una fonte meno autorevole, riportalo dicendo esplicitamente che nessuna
fonte più autorevole lo stabilisce».

**Causa accertata**: collisione lessicale fra «peso» della domanda e «peso di
classe» del prompt di sistema, nella **generazione**. Non nella conversione, non
nella segmentazione, non nel retrieval — e **non** in Docling: il difetto è
identico nei due stack.

Nota collaterale sulla sonda: alla domanda diretta «come si intitola quella
sezione?» **entrambi** gli stack rispondono con la **frase introduttiva**
(«Indice operativo per classificare…»), non con l'intestazione di blocco. Il
controllo di sottostringa della sonda segnava `mancanti=[]` perché la stringa
attesa ricompare nell'eco della domanda: riletto in
[`scripts/rileggi_sonda.py`](scripts/rileggi_sonda.py) e registrato come
`titolo_dichiarato: frase introduttiva`. Uno schermo confondUTO corretto invece
che lasciato passare.

### La variante `[ATTRIBUZIONE-DICHIARATA]` — **NON_APPLICARE**

Correzione minima generale tentata
([`scripts/patch_variante_prompt.py`](scripts/patch_variante_prompt.py)):
restringere l'**ambito** di `[CLASSE-FONTI]` — la graduatoria governa i vincoli,
non i dati che una fonte riporta sui propri artefatti — e vincolare
l'indicazione del luogo all'intestazione di blocco. Nessuna regola sui nomi dei
due PDF, nessun riferimento al golden, nessun ritocco delle risposte, nessun
cambio di ranking o parametri calibrati, nessun modello remoto, nessuna
istruzione di governance rimossa. Applicata **solo** nelle copie sandbox e
rimossa a fine sessione (ripristino byte-esatto verificato).

Tre esiti, misurati:

1. **Non corregge il difetto.** `pdf-diag-3` resta 0/3 passate in entrambi gli
   stack sotto variante. Il modello cita perfino la nuova regola («i dati di una
   fonte sono fatti della fonte») e continua a rispondere `0.30`.
2. **Non sposta l'attribuzione in modo misurabile.** Sui casi N3 lo schermo dà
   4–5/8 in tutte e quattro le configurazioni, dentro la variabilità
   dell'instrumento stesso (vedi sotto).
3. **Sfonda un budget dichiarato.**
   `tests/test_ask_prompt_cost.py::test_costo_fisso_del_prompt_entro_il_budget`
   fallisce: il prompt fisso passa da ~1000 a **~1180 token stimati**, oltre il
   budget misurato il 2026-09-04. Il messaggio del test dice perché quel budget
   esiste: è «il passo saltato che portò /ask al 104% di `num_ctx=16384` (A1)».

Un miglioramento c'è ed è registrato: il documento atteso viene nominato
**21/24** contro 15/24 (candidato) e 17/24 (baseline). Non basta: la variante
fallisce un criterio dichiarato e non risolve il difetto per cui è stata
scritta. **NON_APPLICARE**, e l'esito resta anche se una variante successiva
dovesse superare i controlli.

## FASE 5 — confronto finale, tre passate per stack

Stesso corpus (42 documenti, i due PDF corretti in entrambi), stessi modelli,
stesse domande congelate (`truth/domande_pdf_locali.yaml`, sha256 identico a
quello della sessione precedente), pipeline di retrieval completa via `POST
/ask`. **Cache di `/ask` spenta** (`VIBECRAFT_ASK_CACHE_SIZE=0`): ogni passata è
una generazione vera — `cached: false` su tutte e 96 le risposte. Tutte le
passate sono conservate; nessuna selezione della migliore.

| misura | baseline | candidato | baseline+variante | candidato+variante |
|---|---|---|---|---|
| valori attesi presenti (24 = 8 × 3 passate) | 21/24 | 21/24 | 21/24 | 21/24 |
| fonte attesa **nel contesto inviato** | **24/24** | **24/24** | 24/24 | 24/24 |
| documento atteso nominato | 17/24 | 15/24 | 21/24 | 21/24 |
| dato presente dichiarato assente | `pdf-diag-3` | `pdf-diag-3` | `pdf-mock-4` | `pdf-diag-3` |
| sezione attribuita male (≥1 passata) | 4 domande | 3 domande | 4 domande | 4 domande |
| identificatori non sostenuti | `pdf-diag-4` | `pdf-diag-3`, `pdf-mock-4` | `pdf-mock-4` | `pdf-mock-4` |
| citazioni verificate / totali | 2/5 | 2/12 | 0/5 | 4/9 |
| astensioni · errori di trasporto · troncamenti | 0 · 0 · 0 | 0 · 0 · 0 | 0 · 0 · 0 | 0 · 0 · 0 |
| passate instabili (presenza o rango) | **0** | **0** | 0 | 0 |

**`pdf-diag-3` fallisce 0/3 in tutti e quattro gli stack.** Il «candidato 8/8
contro baseline 7/8» della sessione precedente era una passata singola
fortunata: rimisurato su tre passate, i due stack sono **7/8 entrambi**, con la
stessa domanda mancante.

Retrieval, misure di non regressione (interrogano `GET /api/retrieve`, non la
generazione — quindi la variante non le tocca, ed è per questo che non sono
state rieseguite su di essa):

| | baseline | candidato |
|---|---|---|
| golden `recall@2` | **0.828** PASS | **0.828** PASS |
| multihop recall A · B exact | **0.854** · **6/6** PASS | **0.854** · **6/6** PASS |

Identici fra gli stack e identici a P0. Il golden non contiene i PDF: vale come
**non regressione**, non come merito.

### Troncamenti: nessuno

Il segnale grezzo «non finisce con punteggiatura» aveva dato nove segnalazioni:
ispezionate una per una, sono tutte risposte **complete** che terminano con una
riga di tabella Markdown o con `46.4 KB`. Predicato corretto in
`scripts/score_finale.py`, che ora accetta quelle chiusure: **zero troncamenti**
in tutti gli stack.

### Lo schermo di attribuzione, e i suoi limiti dichiarati

Non è il giudice N3: nessun modello giudica, e l'archivio storico **non** è usato
come prova. Si pone al server la domanda dei casi N3 e si verifica con un `in`
se la risposta nomina il documento dichiarato normativo — **per nome di file o
per classe**, perché il repository stesso considera valido «nella specifica
[REQUIREMENTS]» (`eval.attribution.normalize_verdict`).

| configurazione | nominato | per nome | per classe | distrattore | astensioni |
|---|---|---|---|---|---|
| baseline | 5/8 | 5 | 0 | 4 | 1 |
| candidato | 5/8 | 5 | 0 | 5 | 2 |
| baseline + variante | 5/8 | 4 | 1 | 5 | 1 |
| candidato + variante | 4/8 | 4 | 2 | 4 | 2 |

**Limite dichiarato:** una passata sola per configurazione su otto casi. Sullo
stesso stack, con lo strumento **letterale** superato, il candidato ha dato
3, 3, 3 e 5 su otto in quattro esecuzioni identiche: la variabilità è di ±2/8.
Lo schermo quindi **non rileva alcuna regressione** attribuibile a Docling o alla
variante, e **non ha la risoluzione per certificare** alcunché. La prima versione
di questo schermo contava solo i nomi di file e dava 3/8 al candidato contro 7/8
al baseline: sarebbe stata una conclusione falsa — misurava lo **stile** della
risposta, non l'attribuzione.

## Isolamento, e che cosa NON è stato toccato

Due istanze Qdrant sperimentali, **porta e volume propri**:
`vibecraft-pilot-qdrant` su `127.0.0.1:6401` e `vibecraft-pilot-qdrant-2` su
`127.0.0.1:6402`. Il Qdrant di produzione (`:6333`) **non è mai stato
contattato**; i container `qdrant`, `vibecraft-qdrant-1` e `neo4j` **non sono
stati riavviati né rimossi**. Server sperimentali su 8101/8102; `database/` e
`docs/` dentro i sandbox, fuori dal repository.

Repository al termine: **stesso identico insieme** di file modificati e non
tracciati di inizio sessione, più la sola nuova directory datata. Hash di
controllo invariati per `core/retrieval.py`, `core/chunking.py`,
`rag_config.yaml`, `golden_attribution.yaml`, `golden_set.yaml`,
`pyproject.toml`, `uv.lock`. `eval/results/history.jsonl` invariato: **135
righe**, `57b1eecdd1c23983` — golden e multihop girati con `--no-save` e dentro
i sandbox. `ruff` pulito su tutti gli script.

## Che cosa manca, esattamente

1. **Una decisione del manutentore su `pdf-diag-3`.** Un dato che una fonte
   riporta sui propri artefatti (una dimensione, un formato, un conteggio) deve
   poter essere risposto anche quando la parola della domanda collide con il
   lessico di governance? Se sì, la correzione va progettata dentro il budget
   del prompt fisso, o altrove che nel prompt. Se no, va detto: l'Ispettore di
   Governance non risponde a domande di dato, e il supplemento PDF va letto in
   quella luce. **Questa sessione non può decidere al posto tuo, e la variante
   ovvia è NON_APPLICARE.**
2. **La lettura umana dell'attribuzione**, che il cancello 1c pretende e che
   nessuno strumento qui può firmare: [`review/PACCHETTO_REVISIONE.md`](review/PACCHETTO_REVISIONE.md),
   con le sei domande segnalate in cima, tutte le risposte di tutte le passate,
   la sezione **effettiva** presa dal contesto realmente inviato, e l'estratto
   pertinente.
3. **L'implementazione del template corretto** con nuova baseline, che resta il
   prerequisito dell'intero perimetro.

## Risorse sperimentali conservate

- `rag/eval/results/pilot_docling_chiusura_20260909-160000/` — 94 file, inventario SHA-256
- sandbox in scratchpad (`sandbox-baseline`, `sandbox-candidate`), con i due indici a due versioni
- venv della catena candidata (`docling-pilot/env/venv-novlm`, senza `[vlm]`)
- volumi `vibecraft_pilot_qdrant_storage` e `vibecraft_pilot2_qdrant_storage`

Arrestati soltanto i processi e i container avviati da questa sessione.

# Correzione peso/Authority e attribuzione — verifica in ambiente isolato

**2026-09-09** · ramo `codex/evoluzione-p0` · HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`
· nessun branch, commit, push o PR · `AGENTS.md` **assente** (ricerca ricorsiva nel
repository: nessun riscontro; annotato e proseguito).

## Verdetto

**BLOCCATO — REVISIONE UMANA PENDENTE**, e non per una firma mancante: **resta un
difetto confermato**. Va letto su due assi distinti, come chiede il mandato.

| perimetro | verdetto | motivo |
|---|---|---|
| **correzione generale** (variante V2 del prompt) | **BLOCCATO** — tecnicamente eleggibile, non risolutiva | Rientra nel budget (987/1000), non regredisce nulla di misurato, migliora nettamente l'attribuzione al documento (13→21 su pypdf) e il caso sintetico di collisione (0/3→2/3). **Ma non risolve `pdf-diag-3`**, che era il difetto per cui e' stata scritta. Il giudizio su una singola passata limite (C p1) e' tuo |
| **percorso Docling** sui documenti rigenerati | **BLOCCATO**, invariato | Nessun PASS nuovo. Docling non causa e non corregge nessuno dei due difetti: sono identici nei due parser. Il cancello 1c resta aperto |

Nessuno dei due autorizza l'integrazione. Nulla e' stato integrato.

## Perimetro e conservazione

Ramo corrente `codex/evoluzione-p0` (non `main`): modifiche consentite, eseguite
**solo** su copie sperimentali fuori dal repository. Preesistenti preservate —
`.gitignore`, `rag/adr/README.md`, `rag/eval/golden_attribution.yaml`,
`rag/eval/results/history.jsonl` e i non tracciati gia' presenti. L'unica
aggiunta al repository e' **questa directory datata**.

Non toccati, con hash di controllo in `inventario_sha256.json`: corpus, template
e PDF di produzione; `core/retrieval.py`, `core/chunking.py`,
`api/routes_retrieval.py`, `rag_config.yaml`, `pyproject.toml`, `uv.lock`;
indici, alias e collection di produzione; ranking, authority, precedenze e
parametri calibrati (**alpha 0.3, tetto grafo 3, peso sezione 0.92, S11**);
golden condiviso e `history.jsonl`. Modello invariato (`qwen3.5:9b` locale,
`num_ctx` 16384, `think` false, `temperature` 0.1), nessun giudice remoto,
nessuna risposta precalcolata: cache di `/ask` **spenta**
(`VIBECRAFT_ASK_CACHE_SIZE=0`), `cached: false` su tutte e 96 le risposte.

**Isolamento.** Due istanze Qdrant sperimentali con porta e volume propri
(`vibecraft-pilot-qdrant` su `127.0.0.1:6401`, `vibecraft-pilot-qdrant-2` su
`:6402`), riavviate da questa sessione e riarrestate alla fine. Il Qdrant di
produzione (`:6333`) **non e' mai stato contattato**; i container `qdrant`,
`vibecraft-qdrant-1` e `neo4j` non sono stati toccati. Server sperimentali su
8101/8102. Sandbox e venv in scratchpad, fuori dal repository.

**Riuso verificato prima dell'uso.** `core/retrieval.py`, `core/chunking.py` e
`rag_config.yaml` del sandbox baseline sono **byte-identici** al repository; nel
sandbox candidato l'unica differenza e' il ponte Docling di 14 righe, che cerca
la conversione per **SHA-256 del PDF** e fuori da quei due hash ricade su pypdf.
Corpus dei due sandbox: 60 file, **0 differenze** — la sola variabile e' il
parser. PDF rigenerati con hash **distinti** da quelli di produzione:
`e34c1366…`/`7725b280…` contro `9c0d51c5…`/`443ecfca…`.

Le otto domande congelate sono lo **stesso file** delle due sessioni precedenti,
`sha256 22eede74334b969b5f74cd3be7d69e2322fe42f3f6faae86ef6ddd23a11bcc74`.
Domande, attese, soglie e modello di risposta invariati; nessuna riformulazione.

## FASE 1 — dove vivono le istruzioni, e qual e' il budget

Percorso completo letto prima di intervenire:
`api/routes_retrieval.ask_rag` costruisce il contesto come blocchi
`--- <doc_id> § <sezione> [CLASSE] ---` (`api/routes_retrieval.py:316`, etichetta
da `retrieval.source_label`, `core/retrieval.py:154`), raccoglie le fonti
effettivamente entrate (`:297`) e ne ricava la scala con
`retrieval.authority_scale` (`:170`); `core/retrieval.build_ask_prompt`
(`:866`) concatena il system prompt fisso e, **solo se la scala discrimina**, i
blocchi condizionali `[CLASSE-FONTI]` e `[PRECEDENZA-FONTI]`.

**Budget.** `tests/test_ask_prompt_cost.py` fissa **1000 token** per il prompt
fisso, con la stima **~3 caratteri/token** di `core.llm._ollama_payload`.
E' una **stima dichiarata, non un conteggio esatto di token**: lo dico perche' il
test stesso lo dice, e non va chiamato altrimenti. Baseline misurata:
**2864 caratteri → 954 token stimati**, margine 46 token (136 caratteri).

**Difetti iniziali: riusate le prove precedenti, non ripetuti i batch validi.**
Dall'audit del 2026-09-09 (`pilot_docling_chiusura_.../audit/`): `pdf-diag-3`
risponde `0.90`/`0.30` di Authority invece di `19.5 KB`, o cita `19.5 KB` in un
inciso e conclude che il valore manca; `pdf-diag-4` attribuisce i KPI a «Regole
di organizzazione» e cita una «Indice operativo» inesistente; entrambi in
**entrambi** gli stack, quindi nella generazione e non nel parser.

## FASE 2 — la correzione, una sola variante, dentro il budget

**Ipotesi.** `[CLASSE-FONTI]` interpola numeri nudi (`NORMS (0.80) > METHODOLOGY
(0.50)`) senza **mai dire che cosa misurino**, e ordina di attribuire «un
vincolo, una soglia, una severita'» alla fonte piu' autorevole. Il modello
dispone quindi di numeri senza semantica e di un'istruzione che parla di
grandezze: alla domanda «con quale peso?» offre il coefficiente. Sulla
provenienza, l'intestazione di blocco e' l'unica dichiarata, ma nulla nel prompt
dice di **non** scendere sotto di essa.

**Scelta.** Chiarire e **riscrivere le istruzioni esistenti**, come prescritto:
nessun blocco nuovo. Diff esatto in [`diff/variante_v2.diff`](diff/variante_v2.diff)
— **7 righe sostituite da 7**, dentro il ramo `if authority_classes:`.

La variante dichiara che i numeri graduano **solo le fonti**, che valori,
quantita', dimensioni, formati e unita' **si leggono nel testo del blocco**, e
che la provenienza si indica **con l'intestazione**, senza nominare sezioni che
l'intestazione non dichiara, ripiegando sul **solo documento** quando la sezione
non e' determinabile. Preserva per costruzione: Authority = autorevolezza della
fonte; la precedenza continua ad applicarsi nei conflitti
(`[PRECEDENZA-FONTI]` **invariata alla lettera**); il testo recuperato non
acquisisce autorita' (verificato in G7).

**Non introduce** nulla di ciò che il mandato vieta: nessuna condizione sui nomi
dei cataloghi, nessun id di domanda, nessuna regola che restituisca `19.5 KB` o
altri valori del golden, nessuna associazione basata sulla parola «peso» —
`pdf-diag-2` chiede «formato e **peso**» e **gia' passava**, quindi la parola non
e' il difetto — nessun filtro post-generazione, nessuna protezione di governance
rimossa. `[CITAZIONE-VERIFICABILE]`, `[REGOLA-DIZIONARIO-RIGIDO]`,
`[FONTE-CODICE]`, `[REGOLA-ASTENSIONE]` restano invariate.

**Budget verificato subito: 2963 caratteri → 987 token stimati ≤ 1000.**
Margine 13 token. E' la differenza decisiva rispetto alla variante
`[ATTRIBUZIONE-DICHIARATA]` della sessione precedente, che **aggiungeva** un
blocco e portava il prompt a ~1180 token: quella resta **NON_APPLICARE** e non
e' stata riattivata; il suo esito e' conservato.

**Vincolo scoperto e rispettato.** `tests/test_ask_unified_llm.py::test_build_ask_prompt_snapshot_testuale`
fotografa **alla lettera** il prompt **base**. Toccare `[CITAZIONE-VERIFICABILE]`
lo farebbe fallire, e le asserzioni non si modificano: per questo la correzione
vive **interamente** dentro `[CLASSE-FONTI]`. Conseguenza dichiarata: quando
tutte le fonti stanno sullo stesso livello `authority_scale` restituisce `[]` e
la regola **non compare**. Per il difetto peso/Authority e' innocuo (senza scala
non c'e' il numero con cui collidere); per l'attribuzione di sezione e' una
**lacuna reale**. Tutte e otto le domande congelate hanno contesti a piu' classi
— verificato sui contesti archiviati — quindi la regola e' attiva su tutte.

**Controllo minimo eseguibile:** [`scripts/verifica_prompt.py`](scripts/verifica_prompt.py),
invocato **prima di ogni generazione**, prova quale prompt e' realmente in vigore
e rimisura il budget; [`scripts/check_diagnostici.py`](scripts/check_diagnostici.py),
10 casi su 10 superati, sorveglia il valutatore.

## FASE 3 — controlli di governance preregistrati, e due difetti dello strumento

Dieci casi in [`scripts/diagnostici.py`](scripts/diagnostici.py), con **nomi e
valori estranei ai cataloghi** (sensori, tarature, `sens_4_1_thermal_map.png`,
`312.7 KB`, `1.4 kg`, `250 ms`). Si **aggiungono** al golden, non lo sostituiscono
e non lo toccano. Sondano la **generazione** con contesti sintetici nel formato di
blocco reale: aggiungere documenti al corpus avrebbe cambiato l'indice e quindi
il retrieval delle otto domande, violando «ogni altra condizione identica».

**Due falsi negativi dello strumento, trovati e corretti** (v1 conservata in
`out/diagnostici_originale_v1_strumento_difettoso.json`):

1. **G7** segnato FAIL perche' la risposta **citava** «BANANA» spiegando di non
   obbedire — cioe' il comportamento corretto. Il criterio giusto e' la
   **conformita'** all'iniezione, non la presenza della parola.
2. **G6** segnato FAIL per «Banchi prova» trovato come sottostringa nel **corpo**
   del testo. Ora una sezione conta come attribuita solo se compare in
   **posizione di attribuzione** (dopo «sezione», «§», «paragrafo»).

Aggiunto contestualmente l'asse **contraddizione** (nega un dato e poi lo
riporta: la firma esatta di `pdf-diag-3`) e il caso **G10**, perche' G1/G2/G9
**non riproducevano** il difetto: con un contesto pulito il modello risponde bene
anche col prompt originale. G10 ricostruisce la pressione reale — una fonte
autorevole che parla di «peso» e «Authority» come concetti di governance accanto
a una fonte con la dimensione di un file. Dopo la correzione dello strumento,
**tutte** le configurazioni sono state rivalutate uniformemente.

Tre passate per prompt:

| caso | distinzione | originale | variante V2 |
|---|---|---|---|
| G1 | dimensione di un file in KB | 3/3 | 3/3 |
| G2 | peso fisico con unita' | 2/3 | 3/3 |
| G3 | Authority richiesta esplicitamente | 3/3 | 3/3 |
| G4 | conflitto con precedenza dichiarata | 3/3 | 3/3 |
| G5 | dato assente | 3/3 | 3/3 |
| G6 | sezione non determinabile | 3/3 | 3/3 |
| G7 | istruzioni malevole nella fonte | 3/3 | 3/3 |
| G8 | sezione determinabile (non-eccesso) | 2/3 | 2/3 |
| G9 | grandezza in fonte poco autorevole | 3/3 | 2/3 |
| **G10** | **collisione peso/Authority** | **0/3** | **2/3** |
| | **totale** | **25/30** | **27/30** |

**Letto onestamente:** l'unico segnale sopra il rumore e' **G10, 0/3 → 2/3**. Il
difetto e' **riprodotto e stabile** col prompt originale, e la correzione lo
riduce **senza eliminarlo**. G8 e G9 oscillano di una passata in entrambe le
direzioni: e' la variabilita' dello strumento (±1 caso), non un effetto.
Nessuna regressione su governance: precedenze, autorevolezza richiesta, dato
assente e istruzioni malevole restano 3/3.

La soluzione **non** si limita a convertire ogni domanda con «peso» in una
domanda sulla dimensione: **G3** (Authority richiesta esplicitamente) e **G4**
(conflitto con precedenza) restano 3/3, e **G2** — peso **fisico** in kg —
migliora invece di rompersi.

## FASE 4 — congelamento e confronto fattoriale

Congelato in [`manifest/congelamento.json`](manifest/congelamento.json): hash di
ogni file dei due corpora, versioni e manifest degli indici
(`v20260909T101204` baseline, `v20260909T102528` candidato, due versioni per
sandbox), collection interrogate, modello e impostazioni, parametri calibrati,
hash dei file applicativi che non devono cambiare.

Quattro configurazioni, **mai in parallelo**, tre passate ciascuna sulle otto
domande congelate — **96 risposte, tutte conservate, nessuna selezione**:

**A** pypdf + originali · **B** Docling + originali · **C** pypdf + V2 · **D** Docling + V2

Prova che ogni configurazione ha girato col prompt giusto
(`out/prompt_<cfg>.json`): A e B `originale` a 954 token, C e D `variante-v2` a
987, **prompt base byte-identico in tutte e quattro** (`824ff5179b631b51`).

## FASE 5 — valutazione, ogni asse separato

Strumenti corretti della sessione precedente **riusati**:
`eval.attribution.quoted_spans` via `scripts/citazioni.py`, chunk letti dalle
**chiavi** di `chunks.json`, contesti non vuoti e presi dall'indice davvero
interrogato. Ogni risposta e' associata al proprio contesto, indice e
configurazione, verificato in `out/eval_<cfg>_p<n>.json`.

| misura (su 24 = 8 domande × 3 passate) | A pypdf+orig | B docling+orig | C pypdf+V2 | D docling+V2 |
|---|---:|---:|---:|---:|
| valori attesi presenti (confini di parola) | 22/24 | 21/24 | 22/24 | 21/24 |
| fonte attesa **nel contesto inviato** | **24/24** | **24/24** | **24/24** | **24/24** |
| **documento atteso nominato** | 13/24 | 14/24 | **21/24** | **17/24** |
| dato presente dichiarato assente | diag-3, mock-4 | **diag-3** | **diag-3** | **diag-3** |
| affermazioni di sezione errate | 5 | 5 | 6 | 5 |
| identificatori non sostenuti | diag-4 | mock-4 | — | mock-4 |
| citazioni verificate / non verificabili | 0 / 7 | 3 / 9 | 0 / 13 | 3 / 12 |
| astensioni · errori di trasporto · troncamenti | 0·0·0 | 0·0·0 | 0·0·0 | 0·0·0 |

### `pdf-diag-3` — il difetto **non** e' risolto

| | A | B | C | D |
|---|---|---|---|---|
| passate con `19.5 KB` nella risposta | 1/3 (p2) | 0/3 | 1/3 (p1) | 0/3 |
| nome con doppia estensione `.svg.svg` | 3/3 | 3/3 | 3/3 | 3/3 |

In **A p2** `19.5 KB` compare ma etichettato «Peso (**Authority**)»: e' la
citazione incidentale che il criterio congelato **esclude**. In **C p1** la
risposta associa il file a «**Formato / peso:** SVG, 19.5 KB» in modo diretto e
nomina il documento — poi **aggiunge** un paragrafo che nega l'esistenza di un
valore, parlando pero' di *authority*. E' il **caso limite che spetta a te**:
sezione 1 di [`review/DA_CONTROLLARE.md`](review/DA_CONTROLLARE.md). Tutte le
altre dieci passate falliscono. Il nome a doppia estensione e' conservato **12/12**.

### `pdf-diag-4` — non riprodotto, non corretto

Valori corretti **12/12**. In **nessuna** configurazione la risposta attribuisce
i KPI a «Regole di organizzazione» o nomina «Indice operativo» — **nemmeno in A e
B, che usano le istruzioni originali**. Non e' un effetto della correzione: il
difetto **non si riproduce**. Era una passata singola nella sessione precedente;
su dodici non riappare. Va registrato come **difetto instabile**, non risolto.

### Attribuzione di sezione — la correzione non funziona

5 · 5 · 6 · 5 errori: nessun miglioramento. L'errore dominante e' identico in
tutte: la risposta dichiara «Registro dei file» dove l'intestazione dice
`§ Catalogo diagrammi`. **Sospetto di difetto dello strumento, segnalato e non
risolto**: alcune segnalazioni hanno `sezione_dichiarata == sezione_reale` e
riportano come «valore non trovato» stringhe come `[SENZA CLASSE]` o
`CODICE ESISTENTE`, cioe' l'etichetta di classe. Non l'ho corretto perche' la
correzione richiederebbe di rivalutare uniformemente tutte e quattro le
configurazioni e volevo che la revisione umana vedesse il dato grezzo: e' il
punto 3 di `review/DA_CONTROLLARE.md`.

### Retrieval — nessuna regressione, e la prova che il prompt non lo tocca

| | A | B | C |
|---|---|---|---|
| golden `recall@2` | **0.828** PASS | **0.828** PASS | **0.828** PASS |
| multihop recall A · B exact | **0.854** · **6/6** PASS | **0.854** · **6/6** PASS | **0.854** · **6/6** PASS |

Identici fra loro e identici a P0. **C** e' stato eseguito apposta per **provare**
che la variante non sposta il retrieval invece di limitarsi a dedurlo. Il golden
non contiene i PDF: vale come **non regressione**, non come merito.

## FASE 6 — suite e regressioni

| suite | catena | prompt | test | falliti | errori | **saltati** |
|---|---|---|---|---:|---:|---:|
| A | applicativa (`.venv`) | originale | 1342 | **0** | 0 | **0** |
| B | candidata (`venv-novlm`) | originale | 1342 | **0** | 0 | **0** |
| **C** | applicativa | **variante V2** | 1342 | **0** | 0 | **0** |
| **D** | candidata | **variante V2** | 1342 | **0** | 0 | **0** |

`VIBECRAFT_REQUIRE_QDRANT=1`: con Qdrant irraggiungibile i test sollevano invece
di saltare, quindi **zero saltati** significa che i test di integrazione hanno
girato davvero. Nessuna asserzione modificata, nessuno `skip`, nessun `xfail`,
nessun test omesso o deselezionato. In particolare restano verdi
`test_ask_prompt_cost.py` (987 ≤ 1000), `test_build_ask_prompt_snapshot_testuale`
(prompt base intatto) e i tre di `test_ask_authority_prompt.py` (presenza di
`[CLASSE-FONTI]`, stringa `NORMS (0.80) > METHODOLOGY (0.50)`, ordine prima di
`[PRECEDENZA-FONTI]`). Sandbox ripristinati **byte-esatti** dopo ogni corsa
(`sha256=86ebb94e21b3e427`, verificato).

`ruff check` sugli script della sessione: **All checks passed!**

Parser, parametri calibrati, modello e corpus verificati invariati a fine
sessione. I cambiamenti osservati sono attribuiti alla correzione **solo** dove
il confronto A↔C e B↔D lo sostiene: attribuzione al documento e G10. Non lo e'
`pdf-diag-4`, e lo dico sopra.

## FASE 7 — che cosa serve da te

Tutte le verifiche tecniche eseguibili sono **complete**. Resta **un difetto
confermato** (`pdf-diag-3`) e **un asse non migliorato** (sezione), piu' un
**sospetto difetto di strumento** che ho segnalato invece di correggere in corsa.

[`review/DA_CONTROLLARE.md`](review/DA_CONTROLLARE.md) dice esattamente quali
risposte e quali attribuzioni leggere, in ordine di priorita';
[`review/PACCHETTO_REVISIONE.md`](review/PACCHETTO_REVISIONE.md) contiene, per
ogni domanda: la sezione **effettiva** dal contesto inviato, l'estratto
pertinente, e **tutte** le passate di **tutte** le configurazioni — nessuna
passata problematica e' nascosta dietro un esempio rappresentativo.

Finche' la lettura manca, il verdetto resta **BLOCCATO — REVISIONE UMANA
PENDENTE**, e un'approvazione non annullerebbe comunque i difetti gia'
dimostrati.

## Risorse sperimentali conservate

- questa directory, con inventario SHA-256 in `inventario_sha256.json`
- sandbox `sandbox-baseline` e `sandbox-candidate` in scratchpad, due versioni d'indice ciascuno
- copia patchata di riferimento in `scratchpad/fixv2/rag/core/retrieval.py`
- venv della catena candidata (`docling-pilot/env/venv-novlm`)
- volumi `vibecraft_pilot_qdrant_storage` e `vibecraft_pilot2_qdrant_storage`

Arrestati soltanto i processi e i container avviati da questa sessione. Ollama
resta acceso, come lo era all'inizio.

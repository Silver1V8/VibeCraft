# Diagnosi — perché `pdf-diag-3` non si corregge dal prompt

**2026-09-09** · tutte le prove sono repliche OFFLINE dei contesti realmente
inviati il 2026-09-09 (`fix_attribuzione_20260909-183000/out/eval_<cfg>_p1.json`),
con il prompt come unica variabile. Modello, `num_ctx`, `think` e `temperature`
invariati. Le domande congelate non sono state riformulate.

## Il percorso, tracciato end-to-end

`ask_rag` (`api/routes_retrieval.py`) monta il contesto in tre parti:
chunk semantici (`:316`, intestazione `--- <doc> § <sezione> [CLASSE] ---`),
chunk raggiunti via grafo (`:459`), blocco `=== CODICE ESISTENTE ===` (`:503`).
Poi `retrieval.build_ask_prompt` (`core/retrieval.py:866`, **unico chiamante
applicativo**: `:517`) antepone il prompt fisso e, se `authority_scale` (`:170`)
discrimina, `[CLASSE-FONTI]` e `[PRECEDENZA-FONTI]`.

`source_label` (`:154`) ha due chiamanti (`:316`, `:459`); `authority_scale` uno
(`:518`). La sezione `(documento)` nasce in `core/chunking.py:172,197` quando il
documento non ha intestazioni: e' il caso di pypdf sui PDF.

## I due difetti hanno cause DIVERSE

### D2 — attribuzione di sezione

| parser | intestazione di blocco del PDF | conseguenza |
|---|---|---|
| pypdf (A, C) | `… § (documento) [SENZA CLASSE]` | **nessuna sezione e' dichiarata**: qualunque affermazione di sezione e' insostenibile, e il modello ne inventa una dal corpo del testo («Registro dei file») |
| Docling (B, D) | `… § Catalogo diagrammi [SENZA CLASSE]` | sezione corretta; il modello scende a sotto-sezioni piu' fini di quanto l'intestazione sostenga |

La regola di provenienza va quindi nel prompt **base** — dove vale sempre — non
dentro `[CLASSE-FONTI]`, che compare solo quando le classi discriminano. E' la
lacuna dichiarata della variante V2 della sessione precedente.

### D1 — «peso» letto come Authority

Il contesto **contiene il dato e la sua etichetta**. In Docling il blocco del PDF
porta la tabella con l'intestazione di colonna `| File | Area | Finalita | Formato / peso |`
e la riga
`| diag_6_2_hitl_checkpoints.svg.sv g | Governance | Checkpoint human-in-the-loop e punti di controllo. | SVG 19.5 KB |`.
Il contesto **non e' la causa** — e la prova e' sotto.

## Le prove, in ordine

### 1. Riproduzione offline (controllo)

Prompt originale, contesto Docling completo: il modello identifica il file,
glossa subito «peso (Authority)», e conclude che «il contesto non riporta il suo
peso». Riproducibile, ~12 s a esecuzione.

### 2. Otto formulazioni di prompt, tutte fallite allo stesso modo

| variante | dove | esito su `pdf-diag-3` |
|---|---|---|
| `[ATTRIBUZIONE-DICHIARATA]` (sessione precedente) | blocco nuovo | NON_APPLICARE: fuori budget (~1180 token) e non correggeva |
| V2 (sessione precedente) | solo `[CLASSE-FONTI]` | NON_APPLICARE: nel budget, 1/3 passate |
| **W1** | riga 2 del prompt base + `[CLASSE-FONTI]` | 3/6 con `19.5 KB`, 5/6 ancora con un coefficiente |
| **W2** | «prendi il dato dalla riga che nomina l'elemento» | **peggiore**: 1/6 |
| **x1** | scala senza numeri | 0/3 |
| **x2** | scala + «cerca nei campi omonimi» | 0/3 |
| **x3** | solo «cerca nei campi omonimi» | 0/3 |
| **x4/x5** | «rispondi a tutte le richieste dalla stessa voce» | 0/3 e 0/3 |

Otto formulazioni, nessuna risolutiva. Il mandato prescrive, a questo punto, di
tornare al contesto e al percorso condiviso invece di accumulare frasi: e' ciò
che segue.

### 3. Ablazione del contesto — nessun blocco singolo e' la causa

Prompt **originale**, contesto Docling, 3 esecuzioni per condizione:

| condizione | `19.5 KB` | coefficiente offerto |
|---|---|---|
| completo + scala (controllo) | 0/3 | 3/3 |
| **senza** il blocco `README.md` (che porta una tabella documento→peso) | 0/3 | 3/3 |
| completo, **senza** `[CLASSE-FONTI]` | 2/3 | 1/3 |
| senza README **e** senza scala | 1/3 | 0/3 |
| **senza** il blocco `Requisiti di Retrieval e Authority Boost` | 1/3 | 3/3 |
| senza Authority Boost **e** README | 0/3 | 1/3 |
| senza i blocchi `CODICE ESISTENTE` | 0/3 | 3/3 |
| **codice serializzato PRIMA dei documenti** (E1, cambio di sola serializzazione) | 0/3 | 2/3 |

Togliere un singolo blocco non corregge. Riordinare non corregge.

### 4. Il blocco del PDF, da solo, e' sufficiente

Stesso prompt **originale**, contesto ridotto al solo blocco del PDF:

| contesto | `19.5 KB` | risposte pulite |
|---|---|---|
| solo blocco PDF, senza scala | **3/3** | **3/3** |
| solo blocco PDF, con scala | **3/3** | 2/3 |

Il modello **sa** leggere la tabella e associare il valore al file. Con il prompt
originale, senza alcuna modifica.

### 5. L'effetto e' monotono nella dimensione del contesto

Prompt originale, blocco PDF + i primi *k* blocchi concorrenti in ordine di rango:

| contesto | prompt (token stimati) | `19.5 KB` |
|---|---:|---|
| solo PDF | 1 541 | **3/3** |
| PDF + 2 | 2 906 | 2/3 |
| PDF + 4 | 4 953 | 1/3 |
| PDF + 8 | 6 940 | 1/3 |
| PDF + 22 (reale) | 11 616 | **0/3** |

**Questa e' la causa.** Non la formulazione del prompt, non la conversione, non la
segmentazione, non il ranking: la capacita' di estrarre il dato decade al crescere
del contesto, e a 11,6 k token si azzera. Nessuna frase aggiunta al prompt la
riporta indietro — otto tentativi lo mostrano.

Concorre una collisione semantica **del corpus**: fra i blocchi recuperati c'e'
`spec_graph_rag_ingestion.md § 4. Requisiti di Retrieval e Authority Boost`, che
**definisce** «peso» come coefficiente di autorevolezza. Delle quattro occorrenze
della parola «peso» nel contesto, tre sono in quel senso e una sola e'
l'intestazione di colonna del catalogo.

## Composizione del contesto: dov'e' finito lo spazio

| parte | contesto A (pypdf) | contesto B (Docling) |
|---|---|---|
| chunk semantici (10) | 20 806 char (65,6 %) | 21 324 char (66,2 %) |
| **di cui il PDF, unica fonte che risponde** | **1 475 char (4,7 %)** | **1 993 char (6,2 %)** |
| chunk via grafo (3) | 4 453 char (14,0 %) | 4 453 char (13,8 %) |
| blocchi `CODICE ESISTENTE` (10 snippet) | 6 439 char (20,3 %) | 6 439 char (20,0 %) |
| **totale** | 31 698 char (~10 566 token) | 32 216 char (~10 738 token) |

Su una domanda che riguarda un catalogo di file, il 20 % del contesto e' codice
sorgente TypeScript raggiunto via archi `IMPLEMENTS` dai documenti recuperati
(`api/routes_retrieval.py:493`, `min_weight=CODE_CONTEXT_MIN_WEIGHT`): e'
selezionato per **prossimita' nel grafo**, non per pertinenza alla domanda.

## Proposta concreta, FUORI dal perimetro di questa sessione

La correzione richiede di ridurre cio' che `/ask` invia. Le manopole sono
**parametri configurati e calibrati**, che il mandato mi vieta di toccare:

| parametro | valore | quota del contesto |
|---|---:|---|
| `CODE_CONTEXT_TOTAL_SNIPPETS` | 12 (10 emessi) | ~20 % |
| `GRAPH_CONTEXT_MAX_CHUNKS` | 3 | ~14 % |
| `GOVERNED_MAX_CHUNKS` | 8 (10 chunk emessi) | ~66 % |

**Proposta minima e misurabile**, da decidere e da verificare con misure proprie:
subordinare l'iniezione del blocco `CODICE ESISTENTE` a una pertinenza rispetto
alla **domanda**, non alla sola prossimita' nel grafo — oppure abbassarne il
tetto quando nessun risultato semantico e' codice. Su `pdf-diag-3` toglierebbe
~20 % del contesto; l'ablazione dice che da sola **non basta** (0/3 anche senza
codice), quindi va misurata insieme al tetto dei chunk via grafo.

**Attenzione, e va detto:** `GOVERNED_MAX_CHUNKS`, `AUTHORITY_BOOST_ALPHA` (0.3),
`GRAPH_CONTEXT_MAX_CHUNKS` (3) e `SECTION_RESTATEMENT_WEIGHT` (0.92) sono stati
**calibrati in griglia congiunta** in S11: la memoria del progetto dice che alpha
e tetto sono accoppiati e vanno ricalibrati insieme. Abbassare un tetto per far
passare una domanda, senza rifare la griglia e senza rimisurare golden e
multihop, sarebbe esattamente il difetto che S11 ha chiuso.

L'alternativa e' un modello con miglior richiamo su contesto lungo: e' la
decisione R29 gia' aperta nel piano, non una scelta di questa sessione.

## Conseguenza per il verdetto

`pdf-diag-3` **non e' correggibile dal prompt**, e la prova non e' «otto tentativi
falliti» ma le misure 4 e 5: il modello risponde correttamente con lo **stesso
prompt** appena il contesto scende sotto ~3 k token, e sbaglia sistematicamente a
11,6 k. Qualunque variante di prompt che dichiarassi risolutiva sarebbe smentita
dalla prima passata successiva.

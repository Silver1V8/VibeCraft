# Difetti di generazione e attribuzione — diagnosi conclusiva e correzione degli strumenti

**2026-09-09** · ramo `codex/evoluzione-p0` · HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`
· nessun branch, commit, push o PR · `AGENTS.md` **assente** (ricerca ricorsiva:
nessun riscontro; annotato e proseguito) · nulla integrato in produzione.

## Verdetto

**BLOCCATO — manca una decisione indispensabile, e si chiama con precisione:**

> ridurre il contesto che `/ask` invia (parametri **configurati e calibrati**:
> `CODE_CONTEXT_TOTAL_SNIPPETS`, `GRAPH_CONTEXT_MAX_CHUNKS`, `GOVERNED_MAX_CHUNKS`),
> oppure adottare un modello con miglior richiamo su contesto lungo (R29).

Non e' una firma mancante e **non chiedo una revisione umana per sanarlo**: e' un
difetto confermato la cui causa e' fuori dal perimetro che questa sessione puo'
toccare. Le prove e la proposta concreta sono pronte; la scelta e' tua.

| oggetto | verdetto | prova |
|---|---|---|
| **schermo delle sezioni** (strumento) | **CORRETTO e verificato** | 4 casi minimi riproducono il difetto sullo strumento vecchio (3/7), 7/7 sul corretto, 3 controlli di non regressione inclusi |
| **`pdf-diag-3`** (peso/Authority) | **difetto confermato, NON correggibile dal prompt** | 8 formulazioni fallite; il modello risponde **3/3** con lo **stesso prompt originale** quando il contesto scende a 1,5 k token, **0/3** a 11,6 k |
| **variante W1** (prompt base + `[CLASSE-FONTI]`) | **NON_APPLICARE** | non risolutiva **e regressiva**: governance 22/30 contro 25/30 dell'originale (`G9` crolla 3/3 → 0/3) |
| varianti W2, x1–x5, E1 | **scartate** | registrate con misure e motivo in [`diagnosi/VARIANTI.md`](diagnosi/VARIANTI.md) |
| `[ATTRIBUZIONE-DICHIARATA]`, V2 (sessioni precedenti) | **NON_APPLICARE**, conservate | non riattivate |

## Perimetro e conservazione

Ramo corrente `codex/evoluzione-p0`, non `main`. Tutte le modifiche sono in copie
isolate fuori dal repository; l'unica aggiunta al repository e' **questa directory
datata**. Preesistenti preservate.

Non toccati, con hash confrontati prima/dopo in `inventario_sha256.json`: corpus,
template e PDF di produzione; `core/retrieval.py`, `core/chunking.py`,
`api/routes_retrieval.py`, `rag_config.yaml`, `pyproject.toml`, `uv.lock`; indici,
alias e collection di produzione; ranking, authority, precedenze e parametri
calibrati (**alpha 0.3, tetto grafo 3, peso sezione 0.92, S11**); golden condiviso
e `history.jsonl`. Modello invariato (`qwen3.5:9b` locale, `num_ctx` 16384,
`think` false, `temperature` 0.1); nessun giudice remoto; nessuna risposta
precalcolata. Qdrant di produzione (`:6333`) **mai contattato**; `qdrant`,
`vibecraft-qdrant-1` e `neo4j` non toccati.

Riuso verificato **prima** dell'uso: `core/retrieval.py`, `rag_config.yaml` e
`api/routes_retrieval.py` dei due sandbox byte-identici al repository; nel sandbox
candidato l'unica differenza e' il ponte Docling di 14 righe, per SHA-256 del PDF.
Corpora identici fra i sandbox (60 file, 0 differenze). Domande congelate: stesso
file delle tre sessioni precedenti, `sha256 22eede74…`, non riformulate.

## FASE 1 — lo schermo delle sezioni: difetto riprodotto, poi corretto

Prima la riproduzione, poi la correzione, come prescritto.
[`scripts/riproduci_difetti_strumento.py`](scripts/riproduci_difetti_strumento.py)
gira contro **entrambi** gli strumenti:

```text
strumento VECCHIO -> 3/7    strumento NUOVO -> 7/7
```

**Causa.** `assi.controlla_sezioni` raccoglie come «valore attribuito alla sezione
X» qualunque stringa fra virgolette o backtick nella stessa frase. Le intestazioni
di blocco portano pero' l'**etichetta di classe** (`[SENZA CLASSE]`,
`[METHODOLOGY]`, `[NORMS, ARCHIVED]`) e il contesto ha un blocco
`CODICE ESISTENTE`: citandoli, la risposta li vede finire fra i «valori», non
stanno nel corpo della sezione, e un'affermazione di sezione **corretta**
(`sezione_dichiarata == sezione_reale`) viene contata come errore.

**Correzione** ([`scripts/assi2.py`](scripts/assi2.py)): le etichette non sono mai
valori. Le classi note vengono dalla configurazione **piu'** quelle lette dalle
intestazioni del contesto realmente inviato, cosi' una classe nuova nel corpus non
richiede di aggiornare lo schermo. Aggiunta `classifica_riferimento()`, che separa
con un controllo eseguibile le cinque cose che il mandato chiede di distinguere:
**classe · documento · titolo di sezione · testo citato · descrizione**.

Non regrediscono, e sono nei 7 casi: una sezione davvero inesistente resta errore;
un valore che sta in un'altra sezione resta errore; un valore giusto nella sezione
giusta resta corretto.

Citazioni: riuso di `eval.attribution.quoted_spans` (apostrofi italiani, virgolette
doppie, caporali, Markdown, delimitatore aperto, chiusura orfana, assenza di
citazioni), gia' coperto da 7 casi in `check_citazioni.py` della sessione
precedente. `chunks.json` letto dalle **chiavi**. Contesti presi da quelli
effettivamente inviati.

**Rivalutazione uniforme** delle 96 risposte archiviate del confronto A/B/C/D
([`out/riscoring_archivio.json`](out/riscoring_archivio.json)), originali intatti:

| cfg | presenza | documento | sez. err. **vecchio** | sez. err. **corretto** | diniego |
|---|---|---|---:|---:|---:|
| A pypdf + originali | 22/24 | 13/24 | 5 | **5** | 1 |
| B Docling + originali | 21/24 | 14/24 | 5 | **2** | 0 |
| C pypdf + V2 | 22/24 | 21/24 | 6 | **6** | 1 |
| D Docling + V2 | 21/24 | 17/24 | 5 | **2** | 0 |

**21 errori di sezione → 15: sei erano artefatti dello strumento**, tutti nelle
configurazioni Docling. La conclusione della sessione precedente («5·5·6·5, la
correzione non migliora l'attribuzione di sezione») era in parte un artefatto: con
lo schermo corretto **Docling dimezza gli errori di sezione rispetto a pypdf**
(2 contro 5), il che e' coerente con la causa strutturale descritta sotto.

## FASE 2 — i due difetti hanno cause diverse

Percorso tracciato end-to-end: `ask_rag` monta chunk semantici (`routes_retrieval.py:316`),
chunk via grafo (`:459`) e blocco codice (`:503`); `build_ask_prompt`
(`core/retrieval.py:866`, **unico chiamante applicativo** `:517`) antepone il
prompt fisso e i due blocchi condizionali. `source_label` (`:154`) ha due
chiamanti, `authority_scale` (`:170`) uno.

### D2 — attribuzione di sezione: causa nel CONTESTO, diversa per parser

| parser | intestazione del blocco PDF | conseguenza |
|---|---|---|
| pypdf | `… § (documento) [SENZA CLASSE]` (`core/chunking.py:172,197`) | **nessuna sezione dichiarata**: ogni affermazione di sezione e' insostenibile, e il modello ne inventa una dal corpo («Registro dei file») |
| Docling | `… § Catalogo diagrammi [SENZA CLASSE]` | sezione corretta; il modello scende a sotto-sezioni piu' fini di quanto l'intestazione sostenga |

Ecco perche' con lo schermo corretto Docling sta a 2 errori e pypdf a 5: non e'
il modello che sbaglia di piu' con pypdf, e' che **con pypdf non c'e' una sezione
da citare**.

### D1 — peso/Authority: causa nella DILUIZIONE del contesto

Il contesto **contiene il dato e la sua etichetta**: in Docling il blocco PDF ha
l'intestazione di colonna `| File | Area | Finalita | Formato / peso |` e la riga
`| diag_6_2_hitl_checkpoints.svg.sv g | Governance | … | SVG 19.5 KB |`.

Riproduzione offline (12 s a esecuzione): il modello identifica il file, glossa
«peso (Authority)», conclude che «il contesto non riporta il suo peso».

**Ablazioni, prompt ORIGINALE invariato, 3 esecuzioni per condizione:**

| condizione | `19.5 KB` | coefficiente offerto |
|---|---|---|
| completo (controllo) | 0/3 | 3/3 |
| senza il blocco `README.md` | 0/3 | 3/3 |
| senza `Requisiti di Retrieval e Authority Boost` | 1/3 | 3/3 |
| senza i blocchi `CODICE ESISTENTE` | 0/3 | 3/3 |
| codice serializzato **prima** dei documenti (E1) | 0/3 | 2/3 |
| completo, senza `[CLASSE-FONTI]` | 2/3 | 1/3 |
| **solo il blocco del PDF** | **3/3** | **0/3** |

**Ablazione graduata — l'effetto e' monotono nella dimensione del contesto:**

| contesto | prompt (token stimati) | `19.5 KB` |
|---|---:|---|
| solo PDF | 1 541 | **3/3** |
| PDF + 2 blocchi | 2 906 | 2/3 |
| PDF + 4 | 4 953 | 1/3 |
| PDF + 8 | 6 940 | 1/3 |
| PDF + 22 (reale) | 11 616 | **0/3** |

Il modello **sa** rispondere, con lo **stesso prompt originale**, appena il
contesto scende. Concorre una collisione semantica del corpus: tre delle quattro
occorrenze di «peso» nel contesto vengono da
`spec_graph_rag_ingestion.md § 4. Requisiti di Retrieval e Authority Boost`, che
**definisce** «peso» come coefficiente di autorevolezza; una sola e'
l'intestazione di colonna del catalogo.

**Composizione del contesto** — la fonte che risponde e' una briciola:

| parte | A (pypdf) | B (Docling) |
|---|---|---|
| chunk semantici (10) | 65,6 % | 66,2 % |
| **di cui il PDF, unica fonte che risponde** | **4,7 %** | **6,2 %** |
| chunk via grafo (3) | 14,0 % | 13,8 % |
| `CODICE ESISTENTE` (10 snippet TypeScript) | 20,3 % | 20,0 % |

Su una domanda che riguarda un catalogo di file, il 20 % del contesto e' codice
sorgente scelto per **prossimita' nel grafo**, non per pertinenza alla domanda.

## FASE 3–4 — otto formulazioni, tutte non risolutive

Dettaglio e misure in [`diagnosi/VARIANTI.md`](diagnosi/VARIANTI.md). Ogni
variante e' stata provata **una alla volta**, con il controllo mirato su
`pdf-diag-3` prima di qualunque batch.

**W1** e' la piu' completa: riga 2 del prompt **base** («rispondi alla domanda
posta» invece di «estrai contratti e vincoli»), regola di provenienza legata
all'intestazione di blocco dentro `[CITAZIONE-VERIFICABILE]`, `[CLASSE-FONTI]`
riscritta piu' corta con la distinzione dato/autorevolezza. Ridondanze rimosse
**prima** di aggiungere testo (`[REGOLA-DIZIONARIO-RIGIDO]`, `[FONTE-CODICE]`,
`[CLASSE-FONTI]` liberano 113 caratteri). Budget: **954 → 994 token stimati** su
1000 — **stima** ~3 caratteri/token, la stessa del progetto, **non un conteggio
esatto**.

Sul replay di tutte e otto le domande (contesto A, 3 passate, schermo corretto)
W1 migliora: presenza 22→23/24, documento 18→20/24, errori di sezione 9→7. Ma:

| controlli di governance preregistrati (10 casi × 3 passate) | originale | V2 | **W1** |
|---|---:|---:|---:|
| totale | **25/30** | 27/30 | **22/30** |
| `G9` grandezza in fonte poco autorevole | 3/3 | 2/3 | **0/3** |
| `G10` collisione peso/Authority | 0/3 | 2/3 | **0/3** |

**W1 e' regressivo sulla governance.** Per il criterio dichiarato — «NON_APPLICARE:
variante non risolutiva, regressiva o incompatibile con un criterio di abbandono»
— il suo esito e' **NON_APPLICARE**, e non lo chiamo «tecnicamente eleggibile».

Il batch fattoriale completo **non** e' stato eseguito su W1: il mandato vieta di
ripetere grandi batch su una variante che fallisce gia' il controllo mirato. Al
suo posto e' stato **rivalutato uniformemente** il batch A/B/C/D esistente con lo
schermo corretto (tabella in FASE 1), che e' un confronto fattoriale reale a costo
di inferenza zero.

### Lo snapshot: aggiornato correttamente, e verificato a parte

Poiche' W1 tocca il prompt base, `test_build_ask_prompt_snapshot_testuale`
fallisce — ed e' il suo mestiere. Nel sandbox e' stato **aggiornato** con le
stesse quattro sostituzioni
([`scripts/patch_snapshot_w1.py`](scripts/patch_snapshot_w1.py),
diff in [`diff/snapshot_w1.diff`](diff/snapshot_w1.diff)), non indebolito:

| suite | test | falliti | saltati |
|---|---:|---:|---:|
| sandbox baseline, prompt originale | 1342 | **0** | **0** |
| sandbox candidato (venv-novlm), prompt originale | 1342 | **0** | **0** |
| baseline + **W1**, snapshot **non** aggiornato | 1342 | **1** (solo lo snapshot) | 0 |
| baseline + **W1** + snapshot aggiornato | 1342 | **0** | **0** |

Budget, comportamento e sicurezza restano verificati **separatamente**, perche' un
nuovo snapshot da solo non dimostra nulla: budget 994/1000
(`test_ask_prompt_cost`); comportamento (`test_ask_authority_prompt`: scala,
ordine, «vietato introdurre», assenza di «SQL»/«FOR UPDATE»; `test_ask_abstention`);
sicurezza (`G7`, istruzioni malevole citate ma **non** obbedite: 3/3 in tutte le
varianti, W1 inclusa).

## FASE 6 — regressioni e invarianti

`VIBECRAFT_REQUIRE_QDRANT=1` su istanze isolate (`:6401`, `:6402`): **zero
saltati** significa che i test di integrazione hanno girato davvero. Nessuna
asserzione indebolita, nessuno `skip`, nessun `xfail`, nessun test escluso.
Sandbox ripristinati **byte-esatti** dopo ogni corsa (`86ebb94e…` per
`retrieval.py`, `89ff1f1e…` per il test dello snapshot).

`ruff check` sugli script della sessione: **All checks passed!**

Golden e multihop non sono stati rieseguiti in questa sessione: nessuna variante
e' arrivata al batch finale, e le misure di retrieval della sessione precedente
(`recall@2` 0.828, multihop 0.854 · 6/6, identiche in A, B e C) restano valide —
il prompt non tocca `GET /api/retrieve`, e C lo aveva **provato**, non dedotto.

Invarianti applicativi confrontati prima/dopo: **tutti invariati**;
`history.jsonl` fermo a **135 righe**.

## Proposta concreta, FUORI perimetro — la decisione che serve

La correzione di `pdf-diag-3` richiede di ridurre cio' che `/ask` invia. Le
manopole sono parametri configurati e calibrati, che il mandato mi vieta di
toccare:

| parametro | valore | quota del contesto |
|---|---:|---|
| `CODE_CONTEXT_TOTAL_SNIPPETS` | 12 (10 emessi) | ~20 % |
| `GRAPH_CONTEXT_MAX_CHUNKS` | 3 | ~14 % |
| `GOVERNED_MAX_CHUNKS` | 8 (10 chunk emessi) | ~66 % |

**Proposta minima:** subordinare l'iniezione del blocco `CODICE ESISTENTE` alla
pertinenza rispetto alla **domanda**, non alla sola prossimita' nel grafo
(`api/routes_retrieval.py:493`) — o abbassarne il tetto quando nessun risultato
semantico e' codice. Toglierebbe ~20 % del contesto.

**Ma da sola non basta, ed e' misurato:** senza i blocchi codice `pdf-diag-3` resta
0/3. L'ablazione graduata dice che servirebbe scendere verso ~3 k token, cioe'
toccare anche `GOVERNED_MAX_CHUNKS` e `GRAPH_CONTEXT_MAX_CHUNKS`.

**Avvertenza che non va aggirata:** `GOVERNED_MAX_CHUNKS`, `AUTHORITY_BOOST_ALPHA`
(0.3), `GRAPH_CONTEXT_MAX_CHUNKS` (3) e `SECTION_RESTATEMENT_WEIGHT` (0.92) sono
stati calibrati **in griglia congiunta** in S11, dove alpha e tetto risultarono
accoppiati. Abbassare un tetto per far passare una domanda, senza rifare la
griglia e senza rimisurare golden e multihop, sarebbe esattamente il difetto che
S11 ha chiuso. L'alternativa e' un modello con miglior richiamo su contesto lungo:
e' la decisione **R29**, gia' aperta nel piano, non una scelta di questa sessione.

## Che cosa e' stato risolto, e che cosa no

**Risolto e verificato:** lo schermo delle sezioni (7/7 con 3 controlli di non
regressione), e con esso la correzione del record — 6 dei 21 errori di sezione
attribuiti a Docling erano artefatti dello strumento.

**Non risolto:** `pdf-diag-3`. La causa e' identificata, quantificata e
riproducibile, ma sta fuori dal perimetro. Non la dichiaro risolta e non chiedo
una firma per farla passare.

**Non riprodotto:** `pdf-diag-4` non ha mostrato in questa sessione l'attribuzione
a «Regole di organizzazione»; era gia' cosi' nella sessione precedente **anche con
le istruzioni originali**, quindi resta un **difetto instabile**, non risolto.

## Risorse sperimentali conservate

- questa directory (inventario SHA-256 in `inventario_sha256.json`)
- sandbox `sandbox-baseline` e `sandbox-candidate`, due versioni d'indice ciascuno
- copia patchata W1 in `scratchpad/w1/rag/core/retrieval.py`, con diff e prompt
- venv della catena candidata (`docling-pilot/env/venv-novlm`)
- volumi `vibecraft_pilot_qdrant_storage` e `vibecraft_pilot2_qdrant_storage`

Arrestati soltanto i processi e i container avviati da questa sessione.

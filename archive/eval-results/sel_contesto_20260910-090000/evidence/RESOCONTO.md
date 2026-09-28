# Selezione del contesto di `/ask` — mappa, calibrazione, e la confutazione di una causa

**2026-09-10** · ramo `codex/evoluzione-p0` · HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`
· nessun branch, commit, push o PR · `AGENTS.md` **assente** (ricerca ricorsiva: nessun
riscontro; annotato e proseguito) · nulla integrato in produzione.

## Verdetto

**BLOCCATO — manca una decisione indispensabile, e ora si chiama diversamente
da ieri**, perche' le prove di oggi hanno **confutato** la causa che la sessione
precedente aveva indicato.

> Serve decidere se autorizzare una modifica **mirata al blocco `[CLASSE-FONTI]`**
> del prompt. E' l'unica leva che le misure sostengono ancora, e sta fuori
> dall'autorizzazione di questa sessione (prompt congelato all'originale; W1 e'
> NON_APPLICARE perche' regressiva sulla governance).

| oggetto | verdetto | prova |
|---|---|---|
| **S2** — pertinenza alla domanda sul ponte IMPLEMENTS | **verificata e senza regressioni**, ma **NON_APPLICARE come soluzione di D1**: non risolve la confusione peso/Authority | contesto PDF −17 % a `top_k` 10 e −27 % a `top_k` 5, copertura golden 58/58 e multihop invariate, holdout 14/14, suite 1342/0/0 |
| **S1** — riduzione semplice dei tetti (controllo) | **scartata** | taglia **meno** (27 407 contro 25 313 caratteri) e costa un blocco via grafo |
| **S3** — pavimento di pertinenza sul ramo grafo | **scartata: e' un no-op** | a 0.3 e 0.5 produce contesti **identici** a S0 su tutti e tre gli insiemi |
| **ipotesi «diluizione del contesto»** (sessione precedente) | **CONFUTATA** | con selezione legittima a **3 440 token** `pdf-diag-3` resta **0/3**; il 3/3 di ieri veniva da una selezione privilegiata che conosceva la fonte giusta |
| **causa residua** | `[CLASSE-FONTI]` | a **parita' di contesto** (6 260 token): con la scala 0/3 e coefficiente 3/3; **senza** la scala 2/3 e coefficiente 1/3 |

## Perimetro e conservazione

Modifiche solo nelle copie isolate. Unica aggiunta al repository: **questa
directory datata**. Preesistenti preservate. Prompt, modello e impostazioni di
generazione **congelati** (prompt originale, `qwen3.5:9b`, `num_ctx` 16384,
`think` false, `temperature` 0.1): la sola variabile e' la selezione del contesto.

Invarianti confrontati inizio/fine: `core/retrieval.py`, `rag_config.yaml`,
`pyproject.toml`, `uv.lock`, golden, `history.jsonl` (135 righe) — **tutti
invariati** nel repository. Qdrant di produzione (`:6333`) **mai contattato**;
istanze isolate `:6401`/`:6402`, avviate e riarrestate da questa sessione.
Parametri calibrati S11 (`boost_alpha` 0.3, `default_weight` 0.7,
`unclassified_weight` 0.3, `section_restatement_weight` 0.92) **non toccati**.

## FASE 1 — la mappa, e due correzioni al resoconto di ieri

Dettaglio in [`manifest/MAPPA_PARAMETRI.md`](manifest/MAPPA_PARAMETRI.md).

1. **`governed_max_chunks` non tocca `/ask`.** Compare solo in
   `api/routes_pipeline.py` (canvas/propose). I blocchi semantici di `/ask` sono
   governati da `top_k` della richiesta. Ieri gli era attribuito il ~66 % del
   contesto di `/ask`: era sbagliato.
2. **I tetti di composizione non sono assi della griglia S11.** Il sorgente di
   `eval/calibrate_authority.py` lo scrive: la griglia congiunta ha **quattro
   assi, tutti pesi di ranking**, e «`graph_context_max_chunks` NON e' in questa
   griglia». Ieri avevo detto che toccare un tetto avrebbe richiesto di rifare
   quella griglia: non e' vero per i tetti di composizione, che hanno il loro
   harness (`eval/calibrate_graph_context.py`). Resta vera la dipendenza
   **documentata** in `rag_config.yaml:322` — il tetto grafo sali' a 3 quando
   alpha passo' a 0.3 — che e' di direzione nota, non una co-calibrazione.

**Terza scoperta:** `top_k` ha **default 5** (`api/models.py:19`), ma l'harness
del pilot usa **10**. Tutte le misure di contesto delle tre sessioni precedenti
sono state prese al doppio del default di produzione.

## FASE 2 — protocollo preregistrato

[`manifest/PROTOCOLLO.md`](manifest/PROTOCOLLO.md), scritto prima delle varianti:
ipotesi, ordine delle prove, criteri di selezione, metriche, condizioni di
abbandono, e le **quattro grandezze di budget** tenute distinte (prompt fisso,
documenti, codice, spazio per la risposta). Nessun obiettivo di 3 000 token: quel
valore veniva da una sonda a selezione privilegiata, ed e' una diagnosi, non un
bersaglio.

## FASE 3-4 — l'asimmetria trovata, e la correzione

`/ask` ha **due rami di codice**: quello semantico ha gia' un pavimento di
pertinenza alla domanda (`code_search_min_score` 0.45); il **ponte IMPLEMENTS**
filtra solo sul **peso dell'arco**, mai rispetto alla domanda. Misurato in-process
(LLM sostituito da uno stub, nessuna generazione), mediane:

| insieme | blocchi codice | di cui dal ramo semantico |
|---|---:|---:|
| 8 domande PDF | 10 | **0** |
| golden (58) | 12 | 8 |
| multihop (8) | 12 | 8 |

Sulle domande PDF **tutto** il codice arriva dal ponte; il ramo che valuta la
pertinenza ne fa entrare zero. Su golden e multihop il ramo semantico ne porta 8
su 12: quel codice serve, e non va tolto.

**S2** applica al ponte **lo stesso segnale** del ramo semantico — il coseno
domanda→simbolo — chiamando la **stessa funzione** (`search_code_symbols`)
ristretta con `subset_idx` ai soli simboli che il ponte propone. Nessun
classificatore nuovo, nessuna formula duplicata, nessun segnale assente in
produzione. Diff **puramente additivo: 47 righe, 0 rimosse**
([`diff/s2.diff`](diff/s2.diff)).

**Default 0.0 = disattivato**, e il contesto e' **byte-identico** a S0 in tutti e
8 i casi PDF: il codice patchato senza il parametro si comporta come la produzione.

**Invariante di copertura:** il testo **documentale** del contesto e'
byte-identico a S0 in **74 contesti su 74** (8 PDF + 58 golden + 8 multihop), a
ogni soglia provata. S2 tocca solo il ramo del codice: nessuna fonte documentale
attesa puo' uscire dalla finestra.

**Un difetto mio, trovato dalla suite e corretto.** La prima versione scartava
anche i simboli **senza vettore denso**, che non sono valutabili: due test
comportamentali sono diventati rossi. L'assenza del segnale non e' prova di
irrilevanza — il filtro ora e' **fail-open** sui non valutabili. I due test sono
tornati verdi **correggendo il filtro, non toccando le asserzioni**. Controllo
eseguibile in [`scripts/check_s2.py`](scripts/check_s2.py): **7/7**, incluso il
caso del simbolo senza vettore.

**Esclusioni con motivo e segnale**, non solo il conteggio: ogni simbolo scartato
e' loggato con `symbol_id`, file, nome, **peso dell'arco** che lo aveva fatto
entrare, motivo («coseno domanda→simbolo») e soglia.

## FASE 5 — scelta della soglia, sui criteri preregistrati

| soglia | blocchi codice PDF | golden | multihop |
|---:|---:|---:|---:|
| 0.00 | 10 | 12 | 12 |
| **0.35** | **3** | **12** | **12** |
| 0.40 | 1 | 10 | 12 |
| 0.45 | 0 | 8 | 9 |

0.45 — la soglia del ramo semantico — azzererebbe il codice sulle domande PDF ma
costerebbe 4 blocchi al golden e 3 al multihop: **codice che quelle domande
usano**. **0.35** e' il punto di massima selettivita' a copertura invariata, ed e'
scelto su golden/multihop — **non** sulle otto domande PDF, che sono casi noti di
regressione e non un insieme di scelta.

Confronto contro i criteri preregistrati (multihop → golden → riduzione → meno
parametri): dettaglio in [`calibrazione/VARIANTI.md`](calibrazione/VARIANTI.md).
**S2 batte il controllo S1 su entrambi gli assi**: taglia di piu' (25 313 contro
27 407) e non tocca un solo blocco documentale, mentre S1 ne toglie uno via grafo.
Il guadagno non e' «meno contesto», e' «contesto piu' pertinente» — ed e'
esattamente cio' che il controllo doveva distinguere.

**Calibrazione congiunta non necessaria, e verificato perche':** S2 non tocca
nessuno dei quattro assi della griglia S11, che restano ai valori calibrati.

**Insieme separato** ([`holdout/holdout.yaml`](holdout/holdout.yaml)), scritto
prima della scelta e usato **una volta sola**: 7 domande nuove su documenti
diversi dai cataloghi, con attese verificate per grep. Copre comportamento del
codice, ponte spec→codice, fattuale a classe singola e a classi diverse,
multi-documento e dato assente. **S0 14/14, S2 14/14**: S2 non danneggia le
risposte sul codice mentre ne rimuove il rumore.

## FASE 6 — la confutazione

Il punto piu' importante della sessione. La riduzione del contesto **non**
corregge `pdf-diag-3`, e non e' questione di non aver ridotto abbastanza:

| configurazione | prompt (token stimati) | `pdf-diag-3` |
|---|---:|---|
| `top_k` 10, selezione attuale | 11 443 | 0/3 |
| `top_k` 10 + S2 | 9 297 | 0/3 |
| `top_k` 5 (default di produzione) | 8 502 | 0/3 |
| `top_k` 5 + S2 | 6 260 | 0/3 |
| **diagnostico aggressivo** (`top_k` 3, ponte 0.45, grafo 1 — sacrifica la copertura) | **3 440** | **0/3** |

Ieri l'ablazione dava 3/3 a ~1 500 token e 2/3 a ~2 900. Ma quella selezione era
**privilegiata**: teneva il solo blocco del PDF, cioe' sapeva gia' quale fonte
rispondeva. Con una selezione **legittima** alla stessa taglia il difetto resta.
L'ipotesi «diluizione» era percio' un artefatto della sonda, e va ritirata.

**Che cosa resta, misurato a parita' di contesto** (6 260 token, `top_k` 5 + S2):

| | `19.5 KB` | coefficiente offerto |
|---|---|---|
| con `[CLASSE-FONTI]` | 0/3 | 3/3 |
| **senza** `[CLASSE-FONTI]` | **2/3** | 1/3 |

La scala di autorevolezza consegna al modello un numero gia' pronto per **quel
documento** (`SENZA CLASSE` → 0.30), e il modello lo offre come «peso». E' una
leva di **prompt**, fuori da questa autorizzazione.

## FASE 7 — regressioni, suite, invarianti

| controllo | esito |
|---|---|
| golden `recall@2` (percorso reale, server) | **0.828 PASS** — identico a S0 e a P0 |
| multihop recall A · B exact | **0.854 · 6/6 PASS** — identico |
| copertura golden (documenti attesi in finestra) | **58/58**, invariata |
| copertura multihop (catene complete a livello documento) | **7/8** a `top_k` 10, invariata; **8/8** a `top_k` 5 |
| holdout separato, 7 domande × 2 passate | **14/14** con S0 e con S2 |
| suite, S2 **spenta** (default 0.0) | **1342 / 0 falliti / 0 saltati** |
| suite, S2 **attiva** a 0.35 | **1342 / 0 falliti / 0 saltati** |
| controllo eseguibile della regola S2 | **7/7** |
| `ruff` sugli script della sessione | **All checks passed!** |
| budget del prompt fisso | **954 token stimati / 1000** — invariato (prompt congelato); e' una **stima** ~3 char/token, non un conteggio |

`VIBECRAFT_REQUIRE_QDRANT=1`: zero saltati significa che i test di integrazione
hanno girato davvero. Nessuna asserzione indebolita, nessuno `skip`, nessun
`xfail`, nessun test escluso.

**Budget e latenza** (mediane sulle 8 domande PDF):

| configurazione | prompt (token stimati) | latenza di generazione |
|---|---:|---:|
| `top_k` 10, S0 | 10 975 | 3,3 s |
| `top_k` 10 + S2 | 9 311 | 4,2 s |
| `top_k` 5, S0 | 8 373 | 4,3 s |
| `top_k` 5 + S2 | **6 442** | 4,0 s |

La latenza non migliora in modo leggibile su 8 domande × 3 passate: la
generazione domina, e la variabilita' fra passate e' dello stesso ordine della
differenza. **Non lo presento come un guadagno.**

## Limiti dichiarati

- Nessun batch fattoriale A/B/C/D e' stato eseguito: il protocollo vieta di
  avviare un grande batch su una variante che fallisce gia' il controllo mirato,
  e S2 fallisce `pdf-diag-3`. Al suo posto ci sono le sonde di copertura su 74
  contesti, l'holdout e le suite.
- L'assenza di regressioni e' misurata su golden (58), multihop (8), holdout (7)
  e suite (1342): e' un campione, non una garanzia generale.
- La misura «senza `[CLASSE-FONTI]`» e' un **diagnostico**, non una proposta: il
  prompt di questa sessione resta l'originale.
- `top_k` 5 migliora la copertura multihop a livello di documento (8/8) ma perde
  una attesa di sezione sul golden (57/58): non e' un cambio gratuito, e non lo
  propongo qui.

## La decisione che serve

Autorizzare — o no — una modifica **mirata** a `[CLASSE-FONTI]`, sapendo che:

1. e' l'unica leva che le misure sostengono ancora;
2. la riscrittura **ampia** del prompt (W1) e' gia' stata provata ed e'
   **NON_APPLICARE**, perche' regressiva sulla governance (22/30 contro 25/30);
3. una modifica mirata andrebbe misurata sui 10 diagnostici di governance, sul
   golden, sul multihop e sull'holdout, non solo su `pdf-diag-3`.

**S2 resta disponibile e verificata**, indipendentemente da quella decisione:
migliora la pertinenza del contesto senza regressioni, ha un default che la
disattiva, e non risolve D1. Non la chiamo «tecnicamente eleggibile» come
soluzione del difetto: non lo e'.

## Risorse sperimentali conservate

- questa directory (inventario SHA-256 in `inventario_sha256.json`)
- sandbox `sandbox-baseline` (con S2 applicata a 0.35) e `sandbox-candidate`
- venv della catena candidata (`docling-pilot/env/venv-novlm`)
- volumi `vibecraft_pilot_qdrant_storage` e `vibecraft_pilot2_qdrant_storage`

Arrestati soltanto i processi e i container avviati da questa sessione.

# Varianti di selezione del contesto — prove economiche, criteri preregistrati

Tutte le misure di questa tabella sono **senza generazione**: contesto costruito
in-process dalla stessa app, stesso ranking, LLM sostituito da uno stub
(`scripts/composizione.py`, `scripts/copertura.py`). La copertura riusa
`esito_caso`/`blocchi_del_contesto` di `eval/calibrate_graph_context.py`, non una
seconda definizione di «coperto».

Prompt e modello **congelati** all'originale verificato per tutte le varianti.

## Esito, contro i criteri preregistrati

| variante | parametri | multihop completi (doc) | golden completi (doc) | contesto mediano PDF | blocchi PDF (sem/grafo/cod) |
|---|---|---:|---:|---:|---|
| **S0** attuale | — | 7/8 | 58/58 | 30 563 | 10 / 3 / 10 |
| **S1** controllo: tetti | `code_context_total` 12→6, `graph_context_max_chunks` 3→2 | 7/8 | 58/58 | 27 407 | 10 / **2** / 6 |
| **S2** pertinenza ponte codice | `code_link_min_question_score` 0.0→**0.35** | 7/8 | 58/58 | **25 313** | 10 / 3 / **3** |
| **S3a** pavimento grafo | `graph_context_min_ratio` 0.0→0.3 | 7/8 | 58/58 | 30 563 | 10 / 3 / 10 |
| **S3b** pavimento grafo | `graph_context_min_ratio` 0.0→0.5 | 7/8 | 58/58 | 30 563 | 10 / 3 / 10 |
| **S4** S2+S3a | entrambi | — | — | 25 313 | 10 / 3 / 3 |

### S3 — **scartata: e' un no-op su questo corpus**

`graph_context_min_ratio` a 0.3 e a 0.5 produce contesti **identici** a S0:
stessi caratteri, stessi blocchi, su tutti e tre gli insiemi. Le sezioni
raggiunte via grafo stanno tutte sopra il 50 % del miglior punteggio ColBERT
della loro domanda, quindi il pavimento non taglia nulla. Un parametro che non
cambia nulla e' complessita' senza beneficio: **non entra nella variante finale**,
e S4 coincide percio' con S2.

Il pavimento resta un meccanismo corretto e gia' presente: se un domani il corpus
producesse espansioni di grafo scadenti, quella e' la leva. Oggi non serve.

### S1 — **scartata: fa meno, e costa di piu' in copertura**

Ridurre i tetti da' 27 407 caratteri contro i 25 313 di S2: **taglia di meno**. E
lo fa togliendo un blocco **via grafo** (3→2), cioe' materiale che la copertura
multihop usa, mentre S2 non tocca nemmeno un blocco documentale. Due parametri
cambiati invece di uno.

E' il controllo che il protocollo chiedeva, e serve proprio a questo: mostra che
il guadagno di S2 **non** e' «meno contesto», e' «contesto piu' pertinente». A
parita' di copertura, la selezione per pertinenza taglia di piu' e taglia meglio.

### S2 — **selezionata** dai criteri preregistrati

Ordine deciso prima delle misure: catene multihop → copertura golden →
riduzione del contesto → meno parametri cambiati.

1. multihop 7/8 — **pari** a S0 e a S1;
2. golden 58/58 — **pari**;
3. contesto PDF 30 563 → 25 313 (−17,2 %) — **migliore di S1**;
4. **un solo** parametro cambiato.

## Perche' la soglia e' 0.35, e non 0.45

Sweep completo, mediane dei blocchi di codice:

| soglia | PDF | golden | multihop |
|---:|---:|---:|---:|
| 0.00 | 10 | 12 | 12 |
| 0.30 | 7 | 12 | 12 |
| **0.35** | **3** | **12** | **12** |
| 0.40 | 1 | 10 | 12 |
| 0.45 | 0 | 8 | 9 |

0.45 — la soglia del ramo semantico — azzererebbe il codice sulle domande PDF ma
costerebbe 4 blocchi su golden e 3 su multihop: **codice che quelle domande
usano**. 0.35 toglie 7 blocchi su 10 alle domande PDF **senza togliere nulla** a
golden e multihop. E' il punto in cui la selettivita' e' massima a copertura
invariata, ed e' scelto su golden/multihop — **non** sulle otto domande PDF, che
sono casi noti di regressione e non un insieme di scelta.

## L'invariante che rende S2 sicura per la copertura

Il **testo documentale** del contesto (blocchi semantici + via grafo) e'
**byte-identico** a S0 in **74 contesti su 74** — 8 PDF, 58 golden, 8 multihop —
a ogni soglia provata. S2 tocca soltanto il ramo del codice, per costruzione:
nessuna fonte documentale attesa puo' uscire dalla finestra.

Verifica separata: con la soglia a **0.0** il contesto e' identico a S0 in tutti
e 8 i casi PDF, cioe' il codice patchato **senza** il parametro in configurazione
si comporta esattamente come la produzione. E' il default.

## Esclusioni: motivo e segnale, non solo il numero

Ogni simbolo scartato dal ponte viene registrato con
`symbol_id`, `file`, `name`, il **peso dell'arco** che lo aveva fatto entrare, il
**motivo** («coseno domanda→simbolo») e la **soglia**; il conteggio finisce in una
riga di log dedicata (`ask code_link_filter …`). Blocchi tolti in totale, a 0.35:
54 sulle 8 domande PDF, 129 sulle 58 golden, 8 sulle 8 multihop — cioe' ~6,8 per
domanda PDF contro ~1 per catena multihop, che e' la selettivita' attesa.

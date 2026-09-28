# Mappa dei parametri di composizione del contesto di `/ask`

Letta dal codice, non dalle sessioni precedenti. **Corregge due affermazioni
sbagliate** del resoconto del 2026-09-09 sera, ed e' il motivo per cui la mappa
viene rifatta qui.

## Il flusso effettivo

```
domanda
 → hybrid_search(question, top_k)                     candidati semantici
 → rank_by_authority(alpha) + apply_precedence         RANKING
 → blocchi semantici          routes_retrieval.py:316  (cap = top_k)
 → espansione BFS trust_paths                          ESPANSIONE
 → blocchi «via grafo»        routes_retrieval.py:336-444
 → codice: ramo semantico     routes_retrieval.py:209  search_code_symbols
   codice: ponte IMPLEMENTS   routes_retrieval.py:492  collect_implementing_code
   fusione + tetto            routes_retrieval.py:498  merge_code_context
 → build_ask_prompt           core/retrieval.py:866    SERIALIZZAZIONE
 → llm.agenerate(purpose="ask")                        GENERAZIONE
```

## Tabella: parametro → punto → effetto → accoppiamenti → verifica

| parametro | valore | punto di applicazione | effetto | accoppiamenti **dimostrati** | verifica appropriata |
|---|---:|---|---|---|---|
| `top_k` (richiesta) | 10 nel pilot | `routes_retrieval.py:197` | numero di blocchi semantici | — | `eval.run` (recall) |
| `boost_alpha` | 0.3 | `rank_by_authority` | forza del boost di autorita' | **griglia congiunta S11** con i tre sotto | `eval/calibrate_authority.py`, k-fold |
| `default_weight` | 0.7 | peso di classe | idem | **griglia congiunta S11** | idem |
| `unclassified_weight` | 0.3 | peso di classe | idem | **griglia congiunta S11** | idem |
| `section_restatement_weight` | 0.92 | `rank_by_authority` | peso di sezione (N4) | **griglia congiunta S11** | idem |
| `graph_context_max_chunks` | 3 | `routes_retrieval.py:444` | tetto ai blocchi via grafo | **NON** nella griglia S11 (lo dice il sorgente) | `eval/calibrate_graph_context.py` |
| `graph_context_min_ratio` | **0.0 (spento)** | `routes_retrieval.py:379` | pavimento di pertinenza RELATIVO al miglior ColBERT della domanda | nessuno dimostrato | copertura multihop + golden |
| `code_search_max_snippets` | 8 | `routes_retrieval.py:209` | tetto ramo semantico del codice | — | copertura su domande di codice |
| `code_search_min_score` | **0.45** | `search_code_symbols` | **pavimento di pertinenza alla domanda**, gia' attivo | — | idem |
| `code_search_max_per_file` | 2 | idem | anti-monopolio per file | — | idem |
| `code_context_max_snippets` | 10 | `routes_retrieval.py:494` | tetto ponte IMPLEMENTS | — | idem |
| `code_context_min_weight` | 0.5 | idem | soglia sul **peso dell'arco**, non sulla domanda | — | idem |
| `code_context_total_snippets` | 12 | `routes_retrieval.py:499` | tetto complessivo dei due rami | — | idem |
| `governed_max_chunks` | 8 | `routes_pipeline.py:116` | **canvas/propose, NON `/ask`** | — | non pertinente qui |
| `tech_max_chunks` | 3 | `routes_pipeline.py:137` | idem | — | non pertinente qui |

### Due correzioni al resoconto precedente

1. **`governed_max_chunks` non tocca `/ask`.** Compare solo in
   `api/routes_pipeline.py` (canvas/propose). Il numero di blocchi semantici di
   `/ask` e' governato da `top_k` della richiesta. Il resoconto del 2026-09-09
   sera lo attribuiva al ~66 % del contesto di `/ask`: **sbagliato**.
2. **I tetti di composizione non sono assi della griglia S11.** Il sorgente di
   `eval/calibrate_authority.py` lo dice a lettere: «`graph_context_max_chunks`
   NON e' in questa griglia: e' un taglio nel ramo grafo di /ask, non un peso del
   ranking — vedi eval/calibrate_graph_context.py». La griglia congiunta S11 ha
   **quattro assi e sono tutti pesi di ranking**: `boost_alpha`,
   `default_weight`, `unclassified_weight`, `section_restatement_weight`.
   Il resoconto precedente diceva che abbassare un tetto avrebbe richiesto di
   rifare quella griglia: **non e' vero per i tetti di composizione**, che hanno
   un controllo proprio.
   Resta vero il legame **documentato** in `rag_config.yaml:322-323`: il tetto
   grafo sali' a 3 nello stesso commit in cui alpha passo' a 0.3, perche' alpha
   riprende parte di cio' che il ramo grafo aveva guadagnato. E' una dipendenza
   **di direzione nota**, non una co-calibrazione: se alpha non cambia, il tetto
   si misura col suo harness.

## Informazioni disponibili per valutare la pertinenza (senza nuovi modelli)

| segnale | dove esiste gia' | usato oggi per |
|---|---|---|
| `colbert_score` per chunk | `search_results`, `routes_retrieval.py:378` | ordinare il ramo grafo; **il pavimento e' spento** |
| vettore denso della domanda | `query_encoding["dense"]`, `:209` | ramo semantico del codice |
| coseno domanda→simbolo | `search_code_symbols`, soglia 0.45 | **gia' filtra** il ramo semantico del codice |
| peso arco IMPLEMENTS | `collect_implementing_code` | filtra il ponte, ma **non rispetto alla domanda** |
| `trust`/`hops` del cammino | `trust_paths` | ordina ancore e blocchi grafo |
| autorita' dichiarata | `_authority_weight` | ranking e ordinamento grafo |

## L'asimmetria misurata, che orienta l'ipotesi

Sonda in-process (`scripts/composizione.py`, LLM sostituito da stub, nessuna
generazione), sandbox baseline, `top_k=10`, mediane:

| insieme | blocchi codice **totali** | di cui dal **ramo semantico** (pavimento 0.45 attivo) |
|---|---:|---:|
| 8 domande PDF | 10 | **0** |
| golden (58 casi) | 12 | **8** |
| multihop (8 catene) | 12 | **8** |

Sulle domande PDF **tutto** il codice arriva dal **ponte IMPLEMENTS**, che non ha
alcun filtro di pertinenza alla domanda; il ramo semantico, che quel filtro ce
l'ha, ne fa entrare **zero** — correttamente, perche' quelle domande non parlano
di codice. Su golden e multihop il ramo semantico contribuisce invece 8 blocchi
su 12: quel codice **serve** e non va tolto.

Quote medie del contesto (8 domande PDF, parametri attuali): totale 30 563
caratteri — semantico 18 095 (59 %), grafo 4 988 (16 %), **codice 8 635 (28 %)**.

## Fonti obbligatorie o conflittuali da preservare

- le fonti citate da `precedence_pairs` (S4): il ramo grafo gia' esclude i
  documenti *superati*, e la precedenza va continuare ad applicarsi;
- le sezioni raggiunte solo via grafo che completano una catena multihop: sono
  esattamente cio' che `calibrate_graph_context` misura;
- le fonti meno autorevoli ma pertinenti: l'autorita' regola la **precedenza**,
  non l'ammissione;
- il codice pertinente alla domanda: il ramo semantico va lasciato intatto.

# Fase 1b — osservabilità core

## Stato

Implementata la sola strumentazione di full rebuild e indicizzazione incrementale. Il contratto storico del full resta la stringa versione; il nuovo parametro opzionale `collector` espone metriche alla route. L'incrementale aggiunge le metriche al dizionario già restituito.

Quota ordinaria osservata: 24% residuo all'inizio, 23% prima della verifica finale; `ordinaryUsageAllowed=true`, `spendControlReached=false`.

## Diff

- `core/indexing.py`: tempi monotoni con `time.perf_counter`, conteggi delta/full e token ColBERT derivati dalla dimensione reale dei vettori prodotti.
- `api/routes_reindex.py`: tempo di inizializzazione modello per incremental/full, collector full e `eval_gate` separato.
- `tests/test_index_timings.py`: regressioni controllate con fake, senza modello reale, rete o benchmark.

Nessuna modifica ai file riservati alla fase 1a (`api/reindex.py`, `api/deps.py`, `scripts/bench.py`, `test_reindex.py`, `test_bench.py`, `test_retrieve_reload.py`). Nessun commit, push o merge.

## Semantica metriche

`phase_timings_seconds` usa secondi monotoni:

- `init_model`: sola costruzione di BGE-M3; nella route è misurata anche quando l'incrementale risulta no-op.
- `scan_hash`: scansione e SHA-256 di documenti e file codice, inclusa lettura manifest nel delta.
- `load`: caricamento artefatti precedenti; zero nel full e nei no-op che non caricano artefatti.
- `parsing_embedding`: lettura/parsing/chunking, mutazioni grafo accessorie ed embedding, esclusi Qdrant e relink.
- `qdrant`: apertura/verifica/lineage e operazioni sui punti/collection.
- `relink`: delta codice, selezione e ricostruzione dei link, potatura entità e risoluzione relazioni documentali.
- `save_hash`: salvataggio artefatti e manifest; nel full gli hash sono misurati separatamente in `scan_hash` e riusati dal manifest.
- `promote`: promozione locale e operazioni alias/GC collegate. Nella route full l'eval è esclusa e riportata come `eval_gate`.

`counts` riporta file doc/code aggiunti, modificati e rimossi; chunk elaborati e presenti nell'indice; token ColBERT elaborati e presenti nell'indice. I token sono la somma della prima dimensione degli array ColBERT reali, senza tokenizzazione aggiuntiva. Nel full tutto il corpus valido è rappresentato come aggiunto; modificati/rimossi sono zero.

Su un no-op, i conteggi totali dell'indice non sono letti: `chunks_indexed` e `colbert_tokens_indexed` sono `null`, mentre gli elaborati sono zero. I token del codice sono `null` con motivo esplicito perché l'output corrente di `embed_symbols` non li espone.

## Test

Rosso, prima dell'implementazione:

`python.exe -B -m pytest tests/test_index_timings.py -q --basetemp ../.pytest-tmp-phase1b-red`

Esito: 3 falliti come atteso (`phase_timings_seconds` assente, `collector` non accettato, route senza collector).

Verde mirato:

`python.exe -B -m pytest tests/test_index_timings.py -q --basetemp ../.pytest-tmp-phase1b-green1`

Esito: 3 passati.

Verifica focused core:

`python.exe -B -m pytest tests/test_incremental_indexing.py tests/test_index_timings.py -q --basetemp ../.pytest-tmp-phase1b-focused`

Esito: 87 passati.

Verifica route e compatibilità fake:

`python.exe -B -m pytest tests/test_reindex.py tests/test_index_timings.py -q --basetemp ../.pytest-tmp-phase1b-route`

Esito: 57 passati.

Verifica combinata successiva, mentre la fase 1a modificava i propri file:

`python.exe -B -m pytest tests/test_incremental_indexing.py tests/test_reindex.py tests/test_index_timings.py -q --basetemp ../.pytest-tmp-phase1b-final`

Esito: 3 falliti in `test_reindex.py` su gestione errore journal, readiness e compattazione Windows; 140 passati. Le cause ricadono in `api/reindex.py` e nei test posseduti dalla fase 1a, quindi non sono state modificate qui.

Verifica finale isolata sull'ownership 1b, sullo stesso stato corrente:

`python.exe -B -m pytest tests/test_incremental_indexing.py tests/test_index_timings.py -q --basetemp ../.pytest-tmp-phase1b-final-owned`

Esito: 87 passati.

Tutti i comandi hanno usato `PYTHONDONTWRITEBYTECODE=1` e il runtime read-only indicato nel brief.

## Limiti e prossimo passo

Byte I/O, memoria, GPU/RAM e benchmark restano fuori da questa unità. Nessuna ottimizzazione F3 è stata introdotta. Il passo successivo è far consumare questi campi alla raccolta baseline/F2 e aggiungere il campionamento fuori processo nell'unità prevista; questo report non dichiara chiusa l'intera F1.

## Fix review round 1 — semantica timing

Corretto il finding P2 di `phase1bc-review.md`:

- estrazione e embedding del codice sono attribuiti a `parsing_embedding`; `relink` misura solo selezione/ricostruzione link e risoluzione delle relazioni;
- il full diretto con `promote=True` espone `eval_gate` separato da `promote`, come già faceva la route;
- il collector resta opzionale e il return del full resta la stringa versione.

I nuovi test usano un orologio deterministico e operazioni marcate: verificano valori esatti, non soltanto non-negatività. Rosso: 5 falliti/1 passato per l'attribuzione precedente. Verde: 6 passati. Suite owned finale: 90 passati.

Log raw: `rag/adr/sidecar-work/evidence/windows-phase1b-fix1.txt`.

# S3 — Fiducia sul cammino: `trust_paths()` e la fase 6 di [REGOLA-WF-01]

> **Sessione autonoma.** Prompt self-contained.
> **Dipendenze:** richiede **S2** (gli archi devono portare `nature`/`reliability`).
> **Rischio:** MEDIO — introduce un nuovo segnale nel contesto di `/ask`, dietro parametro.

---

## Prompt

Sei un senior AI engineer su **VibeCraft**, un Graph-RAG in `rag/` (Qdrant + NetworkX +
bge-m3 + rerank ColBERT). Lavora in italiano come il resto del repository.

### Il difetto da correggere

La nostra spec normativa `docs/02_specs_normative/spec_graph_rag_ingestion.md`, regola
**[REGOLA-WF-01]**, impone al motore di recupero una sequenza rigida a sei fasi:

> 1. risoluzione sinonimi, 2. dense query, 3. sparse query (BM25), 4. reranking,
> 5. authority boost, 6. **graph expansion**. Nessuna fase può essere bypassata.

Le fasi 1–5 esistono in `core/retrieval.py::hybrid_search`. La fase 6 **è dichiarata ma non
alimenta la risposta**. Oggi, in `api/routes_retrieval.py`, `graph_ops.bfs_expand()` produce
un insieme di nodi che serve a due cose:

- disegnare la mappa del grafo nella dashboard;
- fornire le ancore a `collect_implementing_code()`, che risale gli archi `IMPLEMENTS`.

Il testo dei documenti raggiunti via grafo **non entra mai** nel contesto dell'LLM, e nessun
nodo raggiunto porta un punteggio. Guarda la firma:

```python
def bfs_expand(graph, seed_nodes, depth) -> set[str]:
```

Un **set piatto**. Un documento a un hop da un seed, raggiunto attraverso un
`EREDITA_VINCOLI` dichiarato da un umano, è indistinguibile da uno a tre hop raggiunto
attraverso una catena di `IMPLEMENTS` congetturati per coseno. Il grafo sa da dove sei
passato per arrivare lì, e noi buttiamo via l'informazione.

### Il modello da implementare

Dall'articolo che origina questo piano (Andrea Magini, HARO — stesso stack Qdrant+NetworkX):

> «Il punteggio di un nodo raggiunto attraverso il grafo è: uno diviso la lunghezza del
> cammino, moltiplicato per il prodotto delle affidabilità di ogni arco attraversato,
> calcolato sul percorso più breve tra query e nodo (una BFS). È quanto ti fidi del percorso
> che hai fatto per arrivare fin lì.»

Cioè, per un nodo `n` raggiunto da un seed:

```
trust(n) = (1 / lunghezza_cammino) × Π reliability(arco)  per ogni arco del cammino più breve
```

Il seed stesso ha `trust = 1.0` (lunghezza 0, prodotto vuoto).

**Attenzione a un punto sostanziale**: «cammino più breve» e «cammino più affidabile» possono
divergere. Un cammino di 2 hop `curated` (0.9 × 0.9 / 2 = 0.405) è più fidato di uno di 1 hop
`inferred` debole (0.5 / 1 = 0.5 → in realtà no, è meno). Costruisci esempi numerici concreti
prima di decidere. **Decisione richiesta**: implementa lo shortest-path come da articolo — è
il comportamento specificato e il più semplice da spiegare — ma se durante l'implementazione
emerge un caso reale del nostro corpus in cui produce un ordinamento chiaramente sbagliato,
**documentalo nel commit** invece di cambiare silenziosamente algoritmo. Un max-product path
(Dijkstra su `-log(reliability)`) è la variante da valutare, non da adottare di slancio.

**Nota su cosa NON stiamo facendo.** Non è PageRank e non è HITS. Non c'è centralità globale:
il punteggio è **relativo alla query**, perché misura la fiducia nel cammino percorso da
*quei* seed. L'articolo è esplicito su questo, e per il nostro grafo — una manciata di
documenti fortemente interconnessi — è la scelta giusta: la centralità globale non
discriminerebbe nulla.

### Cosa implementare

**1. `core/graph_ops.py` — la funzione**

```python
def trust_paths(graph: nx.DiGraph, seed_nodes: list[str], depth: int) -> dict[str, dict]:
    """Espansione BFS che restituisce, per ogni nodo raggiunto, quanto ci si fida del
    cammino percorso per arrivarci."""
```

Restituisce `{node_id: {"trust": float, "hops": int, "via": [nodi del cammino]}}`.

Requisiti:
- BFS **bidirezionale**, come `bfs_expand` (segue successori *e* predecessori): il nostro
  grafo è diretto, ma la fiducia si propaga in entrambi i versi — se A dichiara
  `EREDITA_VINCOLI` verso B, sapere di A informa su B e viceversa. Attraversando un arco
  all'indietro l'affidabilità è la stessa.
- Usa `edge_reliability()` introdotto da S2, **mai** un accesso diretto a `data["reliability"]`:
  il fallback per i grafi persistiti prima di S2 sta lì dentro.
- `via` serve alla spiegabilità: un punteggio di fiducia che non sai giustificare è un numero
  magico. Deve poter finire nella risposta della dashboard.
- **`bfs_expand()` resta e non cambia firma.** Ha già due chiamanti in produzione; questa è
  una funzione nuova, non una sostituzione. Se al termine risulta che `bfs_expand` è
  esprimibile come `set(trust_paths(...).keys())`, riscrivila così — ma solo se i test
  esistenti restano verdi senza modifiche.

**2. `api/routes_retrieval.py` — consumo nel contesto di `/ask`**

Due usi, entrambi dietro parametri di config (`rag_config.yaml → retrieval.*`), entrambi
disattivabili con `0`:

- **`graph_context_max_chunks`** (default `2`, `0` = disattivato) — inietta nel contesto
  dell'LLM le sezioni dei documenti raggiunti **solo via grafo** (non già presenti fra i
  risultati del retrieval semantico), ordinate per `trust × authority`, con un tetto basso.
  È la fase 6 di [REGOLA-WF-01] che finalmente arriva alla risposta. Il tetto è basso di
  proposito: il ramo semantico resta il canale principale, questo è il complemento
  strutturale. Marca questi blocchi nel contesto in modo distinguibile (es.
  `--- <doc_id> § <sezione> [via grafo: <hops> hop, fiducia <trust>] ---`), così l'LLM — e chi
  legge un dump del prompt in debug — sa che quella sezione non ha matchato la domanda: è
  arrivata da un legame dichiarato.
- **ordinamento delle ancore di `collect_implementing_code`** — oggi `code_anchor_nodes` è un
  `set`, quindi le ancore arrivano in **ordine arbitrario di hash**. Passa le ancore ordinate
  per fiducia decrescente, così a parità di `weight` dell'arco `IMPLEMENTS` vince il codice
  agganciato al documento di cui ci si fida di più.

Esponi `trust` e `hops` nei nodi di `graph_context` della risposta JSON: la dashboard può già
colorare per `classification`, questo le dà il secondo asse.

### Test di controllo (obbligatori)

In `rag/tests/test_graph_ops.py`:

1. `test_trust_seed_e_uno` — un nodo seed ha `trust == 1.0` e `hops == 0`.
2. `test_trust_decresce_con_la_distanza` — su una catena `a → b → c` di archi identici,
   `trust(a) > trust(b) > trust(c)`.
3. `test_cammino_curato_batte_cammino_inferito` — due cammini della **stessa lunghezza** da
   seed, uno di archi `curated` e uno di `inferred`: il primo ha fiducia strettamente
   maggiore. È la proprietà che giustifica l'intera sessione S2.
4. `test_prodotto_affidabilita_lungo_il_cammino` — verifica numerica esatta su un cammino
   costruito a mano di 2 hop con affidabilità note: `trust == (r1 * r2) / 2`.
5. `test_via_ricostruisce_il_cammino` — `via` contiene i nodi effettivamente attraversati, in
   ordine, e la sua lunghezza è coerente con `hops`.
6. `test_bfs_bidirezionale` — un nodo raggiungibile solo risalendo un arco all'indietro
   compare fra i risultati (stessa copertura di `bfs_expand`).
7. `test_depth_zero_restituisce_solo_i_seed` — nessuna espansione, nessun crash.
8. `test_grafo_ciclico_termina` — su un ciclo `a → b → c → a` la funzione termina e assegna a
   ogni nodo la fiducia del cammino **più breve**, non dell'ultimo visitato.
9. `test_trust_su_grafo_legacy_senza_reliability` — un grafo i cui archi non hanno gli
   attributi di S2 produce comunque punteggi sensati via il fallback di `edge_reliability`.

In `rag/tests/test_ask_observability.py` (o dove sono i test di `/ask`):

10. `test_graph_context_disattivato_non_cambia_il_contesto` — con `graph_context_max_chunks: 0`
    il contesto prodotto è **byte-identico** a quello di prima della modifica. È il test che
    rende l'intervento reversibile in produzione con una riga di config.
11. `test_sezioni_da_grafo_sono_marcate_nel_contesto` — i blocchi iniettati via grafo portano
    il marcatore e non sono confondibili con quelli del retrieval semantico.
12. `test_ancore_codice_ordinate_per_fiducia` — le ancore passate a
    `collect_implementing_code` arrivano ordinate, non in ordine di `set`.

Prima del commit:

```bash
cd rag
scripts/ci.sh
uv run python -m eval.run --k 10       # il ramo semantico non deve regredire
```

### Prerequisiti del gate di eval

`eval/run.py` interroga il retrieval **via HTTP** (`GET /api/retrieve`) per riusare il modello
già caricato dal server: senza server attivo esce con **exit code 2**, non con un fallimento
di misura. Prima di eseguirlo servono, dalla root del repository:

```bash
docker compose up -d qdrant            # Qdrant su 127.0.0.1:6333
cd rag
uv run python index.py --index-status  # indice presente e allineato? altrimenti indicizza
uv run python server.py                # in una shell separata (o scripts/run_server.ps1)
```

`eval/calibrate_authority.py` invece gira **in-process** e non richiede il server: se
l'infrastruttura non è disponibile in questa sessione, usalo come verifica offline del
ranking e **dichiara nel commit che il gate HTTP non è stato eseguito**. Non spacciare per
verde un gate che non hai potuto far girare.

### Vincoli

- **Non toccare `hybrid_search`.** Le fasi 1–5 sono calibrate e fuori perimetro.
- Il ramo del grafo **non deve** poter sostituire il ramo semantico: il tetto di default è 2
  sezioni e la config deve poterlo azzerare. Se in un test il contesto risulta dominato dalle
  sezioni da grafo, il default è sbagliato.
- Nessuna ri-indicizzazione richiesta: `trust_paths` lavora sul grafo persistito.
- Complessità: il BFS gira **per richiesta**. Con il corpus attuale (~decine di nodi
  documentali) è irrilevante, ma misura e riporta il costo nel commit — se supera ~10 ms,
  dillo, perché diventa il primo candidato a precalcolo.

### Consegna

Un commit unico, messaggio in italiano che spieghi che questa è la fase 6 di [REGOLA-WF-01]
finalmente collegata alla risposta, con la misura del costo per richiesta. Nessun push su `main`.

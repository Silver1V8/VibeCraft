# S2 — Natura e affidabilità degli archi del grafo

> **Sessione autonoma.** Prompt self-contained.
> **Dipendenze:** nessuna (indipendente da S1, può girare in parallelo).
> **Sblocca:** S3 e S4, che senza questi attributi non hanno substrato.
> **Rischio:** BASSO — puro metadato, nessun cambio di ranking.

---

## Prompt

Sei un senior AI engineer su **VibeCraft**, un Graph-RAG in `rag/` (Qdrant + NetworkX +
bge-m3 + rerank ColBERT). Lavora in italiano come il resto del repository: commenti e
docstring spiegano **perché**, non **cosa**.

### Il contesto

Il nostro grafo NetworkX contiene già archi di **tre provenienze epistemicamente diverse**, e
li tratta tutti allo stesso modo:

| Relazione | Da dove nasce | Quanto è affidabile |
|---|---|---|
| `PART_OF` (sezione → documento) | struttura del file, deterministica | certa |
| `MENTIONS` (documento → entità) | regex sul corpo del testo | certa |
| `EREDITA_VINCOLI`, `VINCOLA`, `CONNESSA_A`, `SUPERA_IN_PRIORITÀ`, `DERIVA_DA`, `CONTIENE` | `graph_rag.edges` del frontmatter, **scritti a mano** dall'autore | curata da un umano |
| `IMPLEMENTS` (simbolo di codice → sezione) | **argmax di similarità coseno** fra il vettore del simbolo e quelli dei chunk, con soglia 0.45 | euristica |
| `REFERENCES` (codice → entità) | euristica sui nomi | euristica |

Un `IMPLEMENTS` è la **congettura di un algoritmo** su quale sezione un simbolo di codice
implementi. Un `EREDITA_VINCOLI` è una **dichiarazione di un essere umano**. Un `PART_OF` è un
**fatto del filesystem**. Oggi, per il grafo, sono la stessa cosa: percorrerli costa uguale e
vale uguale.

Questo intervento etichetta la differenza. **Non cambia alcun comportamento di ranking**: è
metadato, e il consumo arriva in S3 (fiducia sul cammino) e S4 (conflitti fra fonti).

### Cosa implementare

**1. `core/config.py` — tassonomia e affidabilità, da `rag_config.yaml → graph_trust.*`**

Tre nature, con un'affidabilità di default ciascuna:

- `structural` → **1.0** — dedotta da filesystem o parsing deterministico; se è sbagliata è un
  bug, non un'incertezza.
- `curated` → **0.9** — validata da un umano. Non 1.0: un umano può sbagliare a scrivere un
  `target:`, e infatti il repository ha già dovuto introdurre `_resolve_semantic_aliases` per
  ricucire riferimenti che non combaciavano.
- `inferred` → **0.6** — congettura di un algoritmo, penalizzata per costruzione.

Esponi anche la mappa `relation → nature`, in config e non nel codice, perché il vocabolario
delle relazioni **cresce dal frontmatter dei documenti**: un autore può dichiarare un
`type:` nuovo domani, e questo non deve richiedere una modifica al sorgente. Una relazione
sconosciuta ricade su `curated` — arriva dal frontmatter, quindi da un umano.

I valori sono **empirici**, come lo sono i pesi di autorità. Dichiaralo nel commento: sono
istinto e buonsenso, ricalibrabili, non costanti universali.

**2. Etichettatura al momento della creazione dell'arco**

Ogni `G.add_edge(...)` deve portare `nature` e `reliability`. I punti sono cinque, tutti già
individuati:

- `core/indexing.py:108` — `MENTIONS` → `structural`
- `core/indexing.py:131` — `PART_OF` → `structural`
- `core/indexing.py:195` — archi doc→doc materializzati da `_resolve_semantic_aliases`:
  **ereditano la natura dell'arco-alias di origine**, non la reinventano (sono la stessa
  dichiarazione dell'autore, risolta verso il nodo giusto)
- `core/chunking.py:222` — archi tipizzati del frontmatter → `curated`
- i punti che creano `IMPLEMENTS` / `REFERENCES` in `core/indexing.py` (cerca
  `relation="IMPLEMENTS"`) → `inferred`

Per `IMPLEMENTS` **combina** l'affidabilità di base con la confidenza già disponibile: l'arco
porta un `weight` che è il coseno effettivo (soglia di linking 0.45). Un `IMPLEMENTS` a 0.92 è
una congettura molto più solida di uno a 0.46, e buttare quel segnale sarebbe uno spreco.
Definisci la combinazione in **una sola funzione**, documentata, e usala da tutti i chiamanti —
sia dal full rebuild sia dal ricalcolo incrementale (`core/indexing.py`, la funzione che
ricalcola i code-link per i simboli toccati). Le due strade **devono** produrre lo stesso
valore.

**3. Accessore unico**

Aggiungi in `core/graph_ops.py`:

```python
def edge_reliability(data: dict) -> float:
    """Affidabilità di un arco, con fallback per i grafi persistiti PRIMA di questa modifica."""
```

Deve leggere `data["reliability"]` se c'è, altrimenti derivarla da `data["relation"]` con la
mappa di config. **Questo fallback non è opzionale**: `database/graph.json` è un artefatto
persistito, i grafi già su disco non hanno i nuovi attributi, e S3 deve funzionare su un grafo
vecchio senza pretendere una ri-indicizzazione completa.

### Test di controllo (obbligatori)

In `rag/tests/test_graph_ops.py` e `rag/tests/test_incremental_indexing.py`:

1. `test_ogni_arco_ha_natura_e_affidabilita` — indicizzato un corpus fixture con documenti,
   frontmatter tipizzato e codice, **nessun** arco del grafo risultante è privo di `nature` o
   `reliability`. Iterazione su `G.edges(data=True)`, nessuna eccezione ammessa.
2. `test_natura_per_relazione` — `PART_OF`/`MENTIONS` → `structural`;
   frontmatter → `curated`; `IMPLEMENTS`/`REFERENCES` → `inferred`.
3. `test_implements_forte_piu_affidabile_di_implements_debole` — due `IMPLEMENTS` con
   `weight` 0.92 e 0.46: il primo ha `reliability` **strettamente maggiore**. Ancora una volta
   asserisci la **relazione d'ordine**, non i valori assoluti.
4. `test_alias_risolto_eredita_natura_origine` — l'arco doc→doc creato da
   `_resolve_semantic_aliases` ha la stessa natura dell'arco-alias da cui deriva.
5. `test_relazione_sconosciuta_ricade_su_curated` — un frontmatter con `type: "PIPPO"` produce
   un arco `curated`, non un crash e non un `reliability` mancante.
6. `test_edge_reliability_fallback_su_grafo_legacy` — un arco costruito **senza** i nuovi
   attributi (com'è ogni arco in `database/graph.json` oggi) restituisce comunque
   un'affidabilità sensata via `relation`.
7. **Il test che protegge l'invariante architetturale:**
   `test_natura_archi_non_altera_equivalenza_delta_full` — `check_graph_consistency()` resta
   `consistent: True` dopo la modifica. Nel commento del test spiega **perché** regge:
   `_edge_set()` confronta le triple `(u, v, relation)` e ignora per costruzione gli attributi
   non strutturali. Il test verifica che quella proprietà valga ancora, non la dà per scontata.

Prima del commit:

```bash
cd rag && scripts/ci.sh
```

### Vincoli

- **Nessun cambiamento di ranking o di retrieval.** Se un test di `test_retrieval.py` o
  `test_ask_router.py` cambia esito, hai superato il confine di questa sessione: fermati.
- Non modificare `_edge_set()` né `_node_type_set()`: sono il contratto dell'invariante
  delta ≡ full.
- La mappa `relation → nature` sta in `rag_config.yaml`, **non** hardcodata nel sorgente.
- Modifiche attese: `core/config.py`, `core/chunking.py`, `core/indexing.py`,
  `core/graph_ops.py`, `rag_config.yaml`, e i due file di test. Nessun altro.

### Consegna

Un commit unico, messaggio in italiano che spieghi perché un `IMPLEMENTS` inferito per coseno
non può valere quanto un `PART_OF` del filesystem. Nessun push su `main`.

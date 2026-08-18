# S4 — `SUPERA_IN_PRIORITÀ`: risoluzione esplicita dei conflitti fra fonti

> **Sessione autonoma.** Prompt self-contained.
> **Dipendenze:** consigliata dopo **S2** (usa la natura `curated` degli archi), ma
> implementabile anche prima.
> **Rischio:** BASSO-MEDIO — tocca il ranking solo fra coppie di documenti esplicitamente
> in relazione di precedenza.

---

## Prompt

Sei un senior AI engineer su **VibeCraft**, un Graph-RAG in `rag/` (Qdrant + NetworkX +
bge-m3 + rerank ColBERT). Lavora in italiano come il resto del repository.

### Il difetto da correggere

Il nostro corpus dichiara una relazione di **precedenza esplicita fra documenti**. In
`docs/00_meta_governance/safeguards_security.md`, frontmatter:

```yaml
graph_rag:
  edges:
    - type: "SUPERA_IN_PRIORITÀ"
      target: ...
```

È la dichiarazione più forte che un autore possa scrivere: *«quando questo documento e
quell'altro dicono cose diverse, vince questo»*. Il grafo la materializza — con
`_resolve_semantic_aliases` diventa un vero arco documento→documento — e poi:

```bash
$ grep -rn "SUPERA_IN_PRIORIT" rag/ --include=*.py
# nessun risultato
```

**Nessuna riga di codice la legge.** Un autore ha risolto in anticipo, a mano, il conflitto
più difficile che un sistema di retrieval possa incontrare, e il sistema ignora la risposta.

Il problema che questa relazione risolve è quello centrale dell'articolo che origina questo
piano: la similarità semantica *«non sa chi ha ragione, sa solo chi è lessicalmente più vicino
alla domanda»*. I pesi di autorità (S1) rispondono **per classe di documento**;
`SUPERA_IN_PRIORITÀ` risponde **per coppia specifica**, ed è quindi il segnale più preciso
che abbiamo. È anche l'unico che copre il caso duro: due documenti della **stessa classe**,
con la **stessa autorità**, che si contraddicono.

### Cosa implementare

**1. `core/retrieval.py` — precedenza nel ranking**

Una funzione pura, con il grafo iniettato dal chiamante come tutto il resto del modulo:

```python
def apply_precedence(results: list[dict], *, graph: nx.DiGraph | None,
                     relation: str = ...) -> list[dict]:
    """Riordina i risultati rispettando le precedenze dichiarate fra i documenti padre."""
```

Semantica: se fra i risultati compaiono chunk di due documenti `A` e `B` e il grafo contiene
`A -[SUPERA_IN_PRIORITÀ]-> B`, **nessun chunk di `B` può precedere il primo chunk di `A`**.

Punti da decidere e documentare:
- **Riordino stabile, non riscrittura dei punteggi.** Non moltiplicare gli score: sarebbe un
  secondo boost opaco che si somma a quello di autorità. Qui la relazione è booleana
  («precede»), e va applicata come tale — una permutazione stabile che preserva l'ordine
  relativo di tutto il resto.
- **Solo relazioni dirette.** Non calcolare la chiusura transitiva: `A > B` e `B > C` non
  implica automaticamente `A > C` in un corpus governato da esseri umani, e una catena
  inferita da noi contraddirebbe lo spirito della dichiarazione. Se serve, l'autore scrive
  l'arco.
- **Cicli.** `A > B` e `B > A` è un corpus malformato. La funzione **non deve** entrare in
  loop né sollevare dentro una richiesta: rileva il ciclo, logga un `warning` con i due
  `doc_id`, e lascia l'ordine invariato per quella coppia. Aggiungi il controllo anche a
  `check_graph_consistency()` in `core/indexing.py`, così il ciclo emerge come difetto di
  corpus e non solo come warning a runtime.
- Il nome della relazione va in `rag_config.yaml` (`authority.precedence_relation`), non
  hardcodato: il vocabolario delle relazioni nasce dal frontmatter, e un progetto istanziato
  dalla nostra baseline può usarne uno diverso.

Chiama `apply_precedence` **dopo** `rank_by_authority`, in `hybrid_search`. L'ordine conta e va
motivato nel commento: l'autorità è un segnale statistico su una classe, la precedenza è una
decisione presa da un umano su due documenti precisi. La decisione umana viene per ultima e
vince.

**2. Dichiarare il conflitto nella risposta, non nasconderlo**

Riordinare in silenzio è metà del lavoro. Se `/ask` recupera chunk di due documenti in
relazione di precedenza, la risposta deve dirlo.

In `core/retrieval.py::build_ask_prompt` esiste già il precedente esatto da seguire — la
regola `[FONTE-CODICE]`, che chiude con:

> «Quando codice e documento divergono, riporta ENTRAMBI e dichiara esplicitamente la
> divergenza.»

Aggiungi, **solo quando la precedenza si applica davvero** (niente istruzioni inerti nel
prompt quando non c'è alcun conflitto), una regola `[PRECEDENZA-FONTI]` che nomini i due
documenti e imponga: la risposta segue il documento prevalente, cita l'altro, e dichiara che
esiste una precedenza dichiarata.

Riporta la precedenza applicata anche nel JSON di risposta di `/ask`, accanto a
`qdrant_scores`: chi legge la dashboard deve poter vedere **perché** un documento è sceso.

### Test di controllo (obbligatori)

In `rag/tests/test_retrieval.py`:

1. `test_precedenza_promuove_il_documento_prevalente` — `B` primo per score, `A` terzo, con
   `A -[SUPERA_IN_PRIORITÀ]-> B` nel grafo: dopo `apply_precedence`, `A` precede `B`.
2. `test_precedenza_preserva_ordine_relativo_degli_altri` — i documenti non coinvolti nella
   relazione mantengono le loro posizioni relative. È la proprietà di stabilità: il riordino
   è chirurgico, non un rimescolamento.
3. `test_nessuna_precedenza_lascia_invariato` — senza archi di precedenza la lista è
   **identica** (stessa istanza logica, stesso ordine): il caso comune non paga nulla.
4. `test_precedenza_non_e_transitiva` — con `A > B` e `B > C` ma nessun arco `A > C`,
   la posizione relativa di `A` e `C` non viene forzata.
5. `test_ciclo_di_precedenza_non_blocca_e_logga` — `A > B` e `B > A`: la funzione ritorna,
   l'ordine di quella coppia resta invariato, e viene emesso un warning (usa `caplog`).
6. `test_grafo_assente_e_no_op` — `graph=None` restituisce la lista invariata.
7. `test_precedenza_su_chunk_multipli_dello_stesso_documento` — con tre chunk di `B` e due di
   `A`, **nessun** chunk di `B` precede il **primo** chunk di `A`. È il caso reale: il
   retrieval lavora su chunk, la precedenza è dichiarata fra documenti.
8. `test_regola_precedenza_assente_dal_prompt_senza_conflitto` — `build_ask_prompt` non
   contiene `[PRECEDENZA-FONTI]` quando nessuna precedenza si applica.
9. `test_regola_precedenza_nomina_i_documenti` — quando si applica, la regola compare e
   contiene entrambi i `doc_id`.

In `rag/tests/test_incremental_indexing.py`:

10. `test_check_consistency_segnala_ciclo_di_precedenza` — un corpus fixture con precedenza
    circolare viene segnalato da `check_graph_consistency()`.

Prima del commit:

```bash
cd rag
scripts/ci.sh
uv run python -m eval.run --k 10   # il corpus attuale ha 1 arco di precedenza: la recall non deve muoversi
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

- **Non** modificare `rank_by_authority`: è condivisa con `eval/calibrate_authority.py`, che
  deve continuare a valutare esattamente il ranking di produzione. La precedenza è uno stadio
  **successivo e separato**.
- **Non** implementare la chiusura transitiva.
- **Non** aggiungere la regola al prompt quando non c'è conflitto: un prompt che porta
  istruzioni inerti insegna al modello a ignorarle.
- Modifiche attese: `core/retrieval.py`, `core/indexing.py`, `api/routes_retrieval.py`,
  `rag_config.yaml`, `tests/test_retrieval.py`, `tests/test_incremental_indexing.py`.

### Consegna

Un commit unico, messaggio in italiano che spieghi che un autore aveva già risolto il conflitto
e il codice non lo leggeva. Nessun push su `main`.

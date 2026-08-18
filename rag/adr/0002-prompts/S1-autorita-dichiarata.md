# S1 — Onorare l'`authority` dichiarata nel frontmatter

> **Sessione autonoma.** Prompt self-contained: non presuppone contesto dalle altre sessioni.
> **Dipendenze:** nessuna. **Sblocca:** S5.
> **Rischio:** ALTO — è l'unico intervento del piano che cambia l'ordinamento di produzione
> senza passare da un parametro di config.
> **Modello:** **Opus 5** (`claude-opus-5`). Non per la mole di codice — è poca — ma per il
> punto di giudizio al gate: se la recall scende, la decisione non è "aggiusto un numero" ma
> "i coefficienti scritti a mano nel frontmatter contraddicono i pesi di classe calibrati, e
> questa è governance, non implementazione". Riconoscere quel bivio e **fermarsi** invece di
> far tornare i conti è esattamente ciò che un modello più piccolo tende a non fare.
> Sottoagenti Explore: **Sonnet 5**.

---

## Prompt

Sei un senior AI engineer su **VibeCraft**, un Graph-RAG in `rag/` (Qdrant per i vettori,
NetworkX per il grafo, bge-m3 per gli embedding, rerank ColBERT). Lavora in italiano, come il
resto del repository: commenti e docstring spiegano **perché**, non **cosa**.

### Il difetto da correggere

Il frontmatter YAML di ogni documento in `docs/` dichiara un campo `authority` (float in
[0,1]): `safeguards_security.md` → 0.98, `spec_graph_rag_ingestion.md` → 0.87,
`docs/README.md` → 0.75. Il campo è **obbligatorio** per policy
(`docs/00_meta_governance/policy_versionamento_documentale.md` §3, «Coefficiente
moltiplicativo di autorità della fonte») ed è imposto dalla regola normativa
**[REGOLA-VAL-08]** in `docs/02_specs_normative/spec_graph_rag_ingestion.md`:

> «Il posizionamento finale dei chunk nel context window è determinato moltiplicando lo score
> di rilevanza del reranker per il coefficiente di `authority` del frontmatter della sorgente.»

Il valore **arriva già** fino al retrieval: `core/indexing.py` assegna `c["metadata"] = metadata`
(il frontmatter intero) e lo riversa nel payload Qdrant (`payload={..., **c["metadata"]}`) e
negli attributi del nodo del grafo (`G.add_node(rel_path, type="document", **metadata)`).

E poi `core/retrieval.py::_authority_weight()` **non lo legge**: ricava il peso dalla sola
`classification`, consultando `AUTHORITY_CLASS_WEIGHTS`. Il coefficiente per-documento,
obbligatorio e scritto in ogni file, è un metadato morto.

**Secondo difetto, stessa funzione.** `AUTHORITY_DEFAULT_WEIGHT` (oggi `0.70`) copre due casi
che non hanno nulla in comune:
1. una classe **legittima ma non elencata** in `class_weights` — tipicamente `REQUIREMENTS`,
   cioè le spec, per cui 0.70 è un valore *calibrato* (grid search del 2026-07-14, recall
   held-out 0.914 → 0.971);
2. una fonte **senza alcuna classificazione**. `core/chunking.py::read_document()` restituisce
   frontmatter vuoto `{}` per ogni formato non-`.md` (pdf, docx, xlsx, txt): un PDF importato,
   privo di qualunque metadato di governance, entra oggi nel ranking con lo **stesso peso di
   una spec normativa calibrata**.

Il caso (2) è l'inversione di priorità che [REGOLA-VAL-08] cita come failure mode. Va separato.

Lo stesso difetto ha un secondo innesco già schedulato dal nostro design: `docs/03_changes_historical/` è oggi vuota ma è prevista dal contratto documentale per accogliere le feature archiviate. Quando si popolerà conterrà change immutabili e tracciate su Git — materiale che *sembra* autorevole proprio perché versionato, ma che descrive ciò che era vero ieri. Anche quello ricadrebbe oggi su `default_weight` = 0.70, alla pari di una spec vigente.

### Cosa implementare

**1. `core/config.py` — nuovi parametri, letti da `rag_config.yaml → authority.*`**

- `AUTHORITY_USE_DECLARED: bool` (default `True`) — se il coefficiente per-documento del
  frontmatter va onorato. È un kill-switch: deve permettere di tornare al comportamento
  storico senza toccare il codice, perché questo intervento cambia il ranking.
- `AUTHORITY_UNCLASSIFIED_WEIGHT: float` (default `0.30`) — peso di una fonte **priva di
  classificazione**. Distinto da `AUTHORITY_DEFAULT_WEIGHT`, che resta il peso della classe
  nota-ma-non-elencata e **non va toccato** (è calibrato).

Aggiungi le due chiavi a `rag/rag_config.yaml` sotto `authority:`, con commenti che spieghino
la distinzione fra i due default e perché il kill-switch esiste. Non riscrivere le note di
calibrazione già presenti: sono storia, si aggiunge in coda.

**2. `core/retrieval.py::_authority_weight()` — precedenza delle sorgenti del peso**

Nuovo ordine di risoluzione, dal più specifico al più generico:

1. `attrs["authority"]`, **se** `AUTHORITY_USE_DECLARED` è attivo **e** il valore è
   convertibile a float **e** cade in `[0.0, 1.0]`. Un valore assente, non numerico o fuori
   range **non deve** far esplodere una richiesta: si degrada al passo successivo. Logga a
   `warning` (una volta per valore anomalo, non per chunk) quando un `authority` è presente ma
   invalido — un frontmatter scritto male non deve fallire in silenzio.
2. `AUTHORITY_CLASS_WEIGHTS[classification]` se la classe è elencata.
3. `AUTHORITY_UNCLASSIFIED_WEIGHT` se `classification` è vuota o assente.
4. `AUTHORITY_DEFAULT_WEIGHT` se la classe c'è ma non è elencata.

Il decadimento per `status` archiviato (`_ARCHIVED_STATUSES` × `AUTHORITY_ARCHIVED_DECAY`) si
applica **dopo**, a qualunque ramo: è ortogonale alla provenienza del peso base. Il risultato
finale va clampato in `[0.0, 1.0]`.

**Mantieni la firma iniettabile** (`weights`, `default`, `decay` come parametri keyword): serve
a `eval/calibrate_authority.py`, che varia i parametri per la grid search senza toccare la
config. Aggiungi i nuovi parametri con lo stesso stile — il calibratore deve poter valutare
anche il ramo dichiarato.

**3. `core/indexing.py` — ereditarietà della sezione**

`_SECTION_INHERITED_ATTRS` è oggi `("classification", "status")`. Aggiungi `"authority"`: i
nodi-sezione del grafo devono portare lo stesso coefficiente del documento padre, altrimenti
un chunk letto dal grafo (non dal payload Qdrant) ricadrebbe sulla classe mentre lo stesso
chunk letto da Qdrant userebbe il coefficiente dichiarato — due pesi diversi per lo stesso
oggetto, a seconda della strada. Il commento sopra la costante va aggiornato di conseguenza.

**4. Invariante «freschezza ≠ autorità» — da blindare, non solo da rispettare**

L'articolo che origina questo lavoro individua nel confondere drift/freschezza con autorità
«uno degli errori più silenziosi che si possa fare in un sistema di retrieval». Oggi non lo
commettiamo — nessun segnale temporale entra nel ranking — ma nulla lo impedisce a chi
toccherà questa funzione domani.

Scrivi il commento che dichiara l'invariante **sopra `_authority_weight`**: il peso è funzione
**pura** di `(authority, classification, status)` e non deve leggere `date`, `last_updated`,
`version`, mtime del file o hash di drift. Motivalo con l'argomento sostanziale, non con
un'imposizione: una spec di due anni mai toccata resta la fonte primaria; una change di ieri
può essere già superata. `status` è ammesso perché è un **giudizio umano** («questo non vale
più»), non una data.

### Test di controllo (obbligatori)

In `rag/tests/test_retrieval.py`, accanto a `test_authority_weights_and_penalty` (che **non va
modificato**: è il contratto storico e deve continuare a passare per i documenti senza
`authority` dichiarata):

1. `test_authority_dichiarata_vince_sulla_classe` — `{"classification": "METHODOLOGY",
   "authority": 0.95}` → 0.95, non 0.5.
2. `test_authority_dichiarata_ignorata_se_kill_switch_spento` — con `AUTHORITY_USE_DECLARED`
   disattivato si torna esattamente al peso di classe.
3. `test_authority_invalida_degrada_alla_classe` — parametrizza su `"molto alta"`, `None`,
   `-0.5`, `1.7`, `""`: ogni caso deve restituire il peso di classe **senza sollevare**.
4. `test_fonte_non_classificata_pesa_meno_di_una_spec` — `{}` (il PDF importato) deve pesare
   **strettamente meno** di `{"classification": "REQUIREMENTS"}`. Asserisci la **relazione
   d'ordine**, non i due numeri: è la proprietà che deve reggere anche dopo una ricalibrazione.
5. `test_decadimento_archiviati_si_applica_anche_alla_dichiarata` —
   `{"authority": 0.98, "status": "ARCHIVED"}` → `0.98 × AUTHORITY_ARCHIVED_DECAY`.
6. `test_peso_autorita_e_indipendente_dai_campi_temporali` — **il test che protegge
   l'invariante**: due dict identici salvo `date`, `last_updated` e `version` (uno del 2020,
   uno di oggi) devono produrre lo **stesso identico peso**.
7. `test_sezione_eredita_authority_dal_documento` — in `rag/tests/test_incremental_indexing.py`
   (o nel file dove vivono già i test di `_add_section_nodes`): indicizzato un documento con
   `authority: 0.91`, ogni nodo-sezione porta `authority == 0.91`.

**Gate di non-regressione, prima del commit.** Questo intervento cambia il ranking di
produzione, quindi non basta che i test unitari passino:

```bash
cd rag
scripts/ci.sh                                   # suite completa, deve essere verde
uv run python -m eval.run --k 10                # golden set: recall NON deve scendere
```

Riporta nel messaggio di commit il valore di recall **prima e dopo**. Se scende, **non
committare**: apri il caso, indica quali documenti hanno cambiato posizione e perché, e
fermati — è esattamente il segnale che i coefficienti dichiarati a mano nel frontmatter
contraddicono i pesi di classe calibrati, e quella è una decisione di governance, non una
scelta di implementazione.

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

- **Non** toccare `AUTHORITY_DEFAULT_WEIGHT` (0.70) né `AUTHORITY_BOOST_ALPHA` (0.1): sono
  valori calibrati, e la loro revisione è oggetto della sessione S5.
- **Non** introdurre `date`/`last_updated`/mtime nel calcolo del peso: è l'anti-obiettivo
  esplicito di questo intervento.
- Nessuna ri-indicizzazione deve essere necessaria: il campo `authority` è **già** nel payload
  Qdrant e negli attributi del grafo. Verificalo prima di scrivere codice
  (`grep -n 'c\["metadata"\] = metadata' core/indexing.py`) e dichiaralo nel commit — se
  servisse un reindex, il piano cambia e va segnalato.
- Modifiche attese: `core/config.py`, `core/retrieval.py`, `core/indexing.py`,
  `rag_config.yaml`, `tests/test_retrieval.py`, `tests/test_incremental_indexing.py`.
  Nessun altro file.

### Consegna

Un commit unico, messaggio in italiano che spiega **perché** (metadato obbligatorio ignorato,
[REGOLA-VAL-08] violata, fonte non classificata equiparata a una spec), con i numeri di recall
prima/dopo. Nessun push su `main`.

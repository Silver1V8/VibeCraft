---
id: "spec-graph-rag-ingestion-v2.0"
title: "Specifica Normativa — Strategia di Ingestion e Indicizzazione Graph-RAG (Baseline Cross-Progetto)"
project: "cross-project"
scope: "cross-project"
version: "2.2.0"
date: "2026-08-24"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_graph_rag_ingestion.md"
authority: 0.87
changelog:
  - version: "2.2.0"
    date: "2026-08-24"
    changes:
      - "[REGOLA-VAL-08] emendata: prescrive la forma ATTENUATA `score x ((1 - alpha) + alpha x authority)` al posto della moltiplicazione piena `score x authority`, che il codice non ha mai implementato e che la misura mostra dannosa"
      - "Aggiunta l'avvertenza sulla saturazione: la forza del boost va calibrata a un k dove la recall non sia satura e su un golden set che contrapponga autorita e similarita lessicale"
  - version: "2.1.0"
    date: "2026-07-22"
    changes:
      - "Aggiunta docs/05_project_specs/ alla tabella cartella→classificazione: contenitore per le spec di progetto, senza redirect verso 00-04"
      - "Corretta la nota di istanziazione: la classification è letta dal frontmatter, non derivata dal pattern di percorso (chiarimento, nessun cambio di comportamento)"
  - version: "2.0.0"
    date: "2026-07-22"
    changes:
      - "Riscrittura cross-progetto: le entità core sono ora un parametro, non una lista hardcoded"
      - "Deduplicato: assorbito docs/04_knowledge_informative/graph_rag_ingestion_strategy.md, che aveva contenuto identico e lo STESSO node_id (collisione di grafo)"
      - "Corretta la REGOLA-VAL-01 sulla sequenza di retrieval: erano dichiarati 5 livelli su 6 fasi elencate"
      - "Aggiunta Sezione 0 — Contratto di Istanziazione"
reuse:
  parameters:
    - "<<ENTITA_CORE>>: elenco delle entità di dominio da riconoscere nel testo"
    - "<<FAMIGLIE_REGOLE>>: prefissi ammessi per gli identificatori di regola"
    - "<<SOGLIA_CHUNK>>: dimensione massima di un chunk in caratteri (default 1500)"
    - "<<SOGLIA_CHUNK_ASSOLUTA>>: limite oltre il quale l'ingestion si blocca (default 2500)"
    - "<<AUTHORITY_SPEC>>: authority di default per le nuove spec (default 0.87)"
  instantiation: "Copiare il file, compilare la Sezione 0, sostituire ogni <<PARAMETRO>>. La struttura di cartelle docs/00..05 è parte del contratto: la tabella indica la classification tipica per cartella, ma è il frontmatter di ciascun documento a determinarla effettivamente."
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-graph-rag-ingestion-v2.0"
  scope: "Requisiti e vincoli del modulo Graph-RAG Ingestion"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-baseline-v2.0"
    - type: "CONNESSA_A"
      target: "policy-versionamento-documentale-v1.0"
tags:
  - requirements
  - open-spec
  - ingestion
  - graph-rag
  - cross-project
  - baseline
---

# Specifica Normativa — Strategia di Ingestion e Indicizzazione Graph-RAG
## Baseline Cross-Progetto

---

## 1. Obiettivo e Ambito di Applicazione

Questa specifica definisce i requisiti funzionali e i vincoli obbligatori della pipeline di ingestion Graph-RAG. Lo scopo è garantire una rappresentazione coerente dei documenti Markdown nei sistemi Qdrant (vettoriale) e NetworkX (grafo), preservando integrità semantica e tracciabilità.

L'indicizzatore analizza ricorsivamente tutti i documenti sotto `docs/` applicando pattern matching su percorsi e denominazioni per assegnare i metadati corretti.

### Sezione 0 — Contratto di Istanziazione

| Parametro | Significato | Valore nel progetto |
|---|---|---|
| `<<ENTITA_CORE>>` | Entità di dominio da riconoscere nel testo | *(da compilare)* |
| `<<FAMIGLIE_REGOLE>>` | Prefissi ammessi per gli identificatori di regola | `REGOLA-*`, `SAFEGUARD-*` |
| `<<SOGLIA_CHUNK>>` | Dimensione massima di un chunk | `1500` caratteri *(default)* |
| `<<SOGLIA_CHUNK_ASSOLUTA>>` | Limite di blocco dell'ingestion | `2500` caratteri *(default)* |
| `<<AUTHORITY_SPEC>>` | Authority di default per le nuove spec | `0.87` *(default)* |

### Tassonomia delle cartelle (parte del contratto)

| Cartella | Contenuto | `classification` tipica |
|---|---|---|
| `docs/00_meta_governance/` | Contratti di ferro, policy, dizionari | `IRON_MEMORY`, `AUTHORIZATION_POLICY`, `DATA_DICTIONARY` |
| `docs/01_architecture_norms/` | Norme di codifica e scelte architetturali | `METHODOLOGY`, `NORMS` |
| `docs/02_specs_normative/` | Specifiche funzionali (`spec_*.md`) | `REQUIREMENTS` |
| `docs/03_changes_historical/` | Materiale archiviato e storicizzato | `HISTORICAL` |
| `docs/04_knowledge_informative/` | Metodologia e conoscenza di supporto | `METHODOLOGY` |
| `docs/05_project_specs/` | Specifiche di progetto (funzionali/tecnologiche, glossari, matrici permessi) che il progetto produce da sé, senza redirect verso le classificazioni 00-04 | `REQUIREMENTS` (o quella dichiarata dal singolo documento) |

Rinominare o rimuovere una di queste cartelle cambia la classificazione dei documenti che contiene, e quindi il loro peso nel ranking. È una modifica di contratto, non di layout.

> **Nota:** la tabella è una convenzione documentale, non un meccanismo dell'indicizzatore — `classification` è letta dal frontmatter di ciascun documento (`core/indexing.py`, `_SECTION_INHERITED_ATTRS`), non derivata dal percorso. La colonna "classification tipica" indica cosa ci si aspetta di trovare in ciascuna cartella, non un vincolo applicato in automatico.

### [REGOLA-VAL-01] Classificazione automatica dei documenti
- **Descrizione:** Ogni documento sul filesystem deve essere classificato in modo deterministico mediante pattern matching del percorso e del nome file sorgente.
- **Effetto in caso di violazione (Failure Mode):** Il documento viene escluso dall'indice o assegnato a una categoria errata, corrompendo i moltiplicatori di rango.
- **Entità Target:** Nessuna.

### [REGOLA-INT-01] Estensibilità automatica delle specifiche
- **Descrizione:** Ogni nuovo file inserito nella cartella delle specifiche che rispetti il pattern `spec_*.md` deve essere registrato come nodo `OPEN_SPEC` con authority di default pari a `<<AUTHORITY_SPEC>>`.
- **Effetto in caso di violazione (Failure Mode):** Il documento viene escluso dal knowledge graph, rendendo invisibili le nuove capability all'LLM.
- **Entità Target:** Nessuna.

---

## 2. Requisiti di Chunking Dinamico e Compressione

### [REGOLA-VAL-02] Limite dimensionale dei chunk
- **Descrizione:** La segmentazione deve produrre blocchi semantici sotto `<<SOGLIA_CHUNK>>` caratteri, per preservare la densità informativa.
- **Effetto in caso di violazione (Failure Mode):** Diluizione della firma semantica del vettore ed errori di accuratezza nel Dense Retrieval.
- **Entità Target:** Nessuna.

### [REGOLA-VAL-03] Blocchi atomici inviolabili
- **Descrizione:** Le definizioni di entità, le schede di salvaguardia, gli scenari BDD e le tabelle di vincoli sono strutture atomiche che non devono mai essere spezzate durante la segmentazione.
- **Effetto in caso di violazione (Failure Mode):** Perdita del contesto logico e rottura delle relazioni strutturali nel grafo.
- **Entità Target:** Nessuna.

### [REGOLA-VAL-04] Segmentazione gerarchica in cascata
- **Descrizione:** Il modulo di chunking applica la priorità di taglio in cascata: 1. blocchi atomici, 2. intestazioni H2, 3. intestazioni H3, 4. paragrafi.
- **Effetto in caso di violazione (Failure Mode):** Embedding semanticamente incompleti o frammentati.
- **Entità Target:** Nessuna.

### [REGOLA-VAL-05] Breadcrumb obbligatorio per payload
- **Descrizione:** Ogni sotto-chunk derivato da livelli H3 o inferiori deve includere un prefisso di contesto strutturato, memorizzato esclusivamente nel payload Qdrant e rimosso prima del calcolo dell'embedding.
- **Effetto in caso di violazione (Failure Mode):** Perdita dell'ancoraggio gerarchico durante la composizione del prompt.
- **Entità Target:** Nessuna.

### [REGOLA-VAL-06] Compressione controllata lossy
- **Descrizione:** Se un blocco atomico supera `<<SOGLIA_CHUNK>>`, l'indicizzatore applica una compressione conservando identificatore, invariante ed entità coinvolte; al superamento di `<<SOGLIA_CHUNK_ASSOLUTA>>` blocca l'ingestion con severity `WARNING`.
- **Effetto in caso di violazione (Failure Mode):** Rigetto del blocco normativo o crash della pipeline di pre-processing.
- **Entità Target:** Nessuna.

---

## 3. Vincoli delle Entità Core e della Tassonomia

### [REGOLA-INT-02] Formato obbligatorio delle entità core
- **Descrizione:** Ogni riferimento nel testo alle entità dichiarate in `<<ENTITA_CORE>>` deve essere scritto in maiuscolo e racchiuso tra backtick. Il riconoscimento è basato su regex: senza questa marcatura il parser non crea le relazioni.
- **Effetto in caso di violazione (Failure Mode):** Il parser fallisce il riconoscimento, impedendo la creazione automatica delle relazioni nel grafo.
- **Entità Target:** `<<ENTITA_CORE>>`

### [REGOLA-VAL-07] Tassonomia degli identificatori di regola
- **Descrizione:** Ogni norma deve aprirsi con un identificatore conforme al formato `[PREFISSO-CATEGORIA-XX]`, mappato sulle famiglie dichiarate in `<<FAMIGLIE_REGOLE>>`.
- **Effetto in caso di violazione (Failure Mode):** Il parser rigetta l'identificatore, impedendo la generazione dei nodi di governance nel grafo.
- **Entità Target:** Nessuna.

### [REGOLA-INT-03] Generazione automatica degli archi impliciti
- **Descrizione:** Durante il parsing di un chunk, la presenza di entità o regole innesca la creazione automatica degli archi `CONTIENE`, `MENZIONA` e `DIPENDE_DA` verso i rispettivi nodi.
- **Effetto in caso di violazione (Failure Mode):** Perdita della connettività topologica e fallimento delle query multi-hop.
- **Entità Target:** `<<ENTITA_CORE>>`

---

## 4. Requisiti di Retrieval e Authority Boost

### [REGOLA-WF-01] Sequenza obbligatoria della pipeline di ricerca
- **Descrizione:** Il motore di recupero deve eseguire la sequenza rigida a **6 fasi**: 1. risoluzione sinonimi, 2. dense query, 3. sparse query (BM25), 4. reranking, 5. authority boost, 6. graph expansion. Nessuna fase può essere bypassata.
- **Effetto in caso di violazione (Failure Mode):** Degradazione della qualità del ranking e potenziale inclusione di allucinazioni nel contesto.
- **Entità Target:** Nessuna.

> **Nota di correzione (v2.0):** la v1.1 dichiarava "sequenza rigida a 5 livelli" ed elencava 6 fasi. Il conteggio è ora allineato all'elenco.

### [REGOLA-VAL-08] Applicazione del coefficiente di authority (forma attenuata)
- **Descrizione:** Il posizionamento finale dei chunk nel context window è determinato modulando lo score di rilevanza del reranker per il coefficiente di `authority` della sorgente, nella forma **attenuata**:
  `score_finale = score_reranker × ((1 − α) + α × authority)`, con `α ∈ [0,1]` parametro calibrato (`authority.boost_alpha`). Il coefficiente `authority` è quello **dichiarato nel frontmatter** della sorgente; in sua assenza si applica il peso della classe, e in assenza anche di `classification` il peso della fonte non classificata (`authority.unclassified_weight`), che deve essere **distinto** e più basso di quello delle classi note ma non elencate.
- **Effetto in caso di violazione (Failure Mode):** Mancato rispetto della gerarchia delle fonti e inversione di priorità fra contratti di sicurezza e testi descrittivi. Con `α = 1` (moltiplicazione piena) il failure mode si inverte: i contratti generici ad alta autorità sovra-promuovono rispetto alle spec specifiche attese.
- **Entità Target:** Nessuna.

> **Emendamento (v2.2.0, 2026-08-24).** Fino alla v2.1.0 questa regola prescriveva la moltiplicazione **piena** `score × authority`, cioè `α = 1`. Nessuna implementazione l'ha mai applicata, e la misura spiega perché. Su un golden set esteso con 10 casi **avversariali** — costruiti perché una fonte a bassa autorità matchi lessicalmente meglio della normativa che risponde — al crescere di `α` (recall@1 sui 10 casi avversariali / recall@10 sui 59 casi complessivi):
>
> | α | 0.0 | 0.1 | 0.2 | 0.3 | 0.5 | 0.8 | 1.0 |
> |---|---|---|---|---|---|---|---|
> | avversariali recall@1 | 0.000 | 0.000 | 0.200 | 0.400 | 0.500 | **0.600** | 0.500 |
> | complessiva recall@5 | 0.949 | **0.966** | 0.949 | 0.932 | 0.898 | 0.881 | 0.814 |
> | complessiva recall@10 | **0.983** | **0.983** | 0.966 | 0.949 | 0.932 | 0.915 | 0.881 |
>
> La moltiplicazione piena costa **15.2 punti di recall@5 e 10.2 di recall@10** su tutto il golden set, e non è nemmeno il massimo sui casi avversariali (`α = 0.8` ne corregge di più). È il failure mode descritto sopra, misurato: oltre una certa forza il boost promuove i contratti generici ad alta autorità sopra le spec specifiche attese, e le fonti corrette escono dalla finestra di contesto invece di salire.
>
> La norma è quindi allineata alla forma effettivamente implementata, e la divergenza fra spec e codice — aperta e documentata dall'ADR 0002 — è chiusa qui. Il valore di `α` resta un parametro di calibrazione, non una costante di questa regola.

> **Avvertenza di calibrazione:** i pesi per classe e la forza del boost sono parametri **empirici**, non costanti universali. Vanno ricalibrati sul golden set del progetto con uno split di validazione. Due condizioni rendono la calibrazione priva di significato se disattese, ed entrambe sono state violate in passato su questo progetto:
> 1. **il `k` non deve essere saturo.** Una recall che vale 1.000 su tutti i casi non distingue una configurazione dall'altra: la ricalibrazione del 2026-07-22 girò a `k = 10` e `k = 5` su una griglia interamente satura e concluse, correttamente ma inutilmente, che nessuna combinazione era distinguibile.
> 2. **il golden set deve contrapporre autorità e similarità lessicale.** Se in ogni caso la fonte attesa è anche la più simile alla domanda, il ranking semantico basta da solo e il boost di autorità risulta inerte qualunque sia il suo valore — si misura la saturazione del set, non il meccanismo.

---

## 5. Regole di Aggiornamento Incrementale e Delta Ingestion

### [REGOLA-WF-02] Sequenza operativa di ingestion
- **Descrizione:** L'indicizzazione segue le fasi obbligatorie di Discovery, Pre-processing, Embedding, Costruzione Grafo e Validazione.
- **Effetto in caso di violazione (Failure Mode):** Pipeline instabile e non deterministica.
- **Entità Target:** Nessuna.

### [REGOLA-WF-03] Sostituzione atomica per versione documentale
- **Descrizione:** Quando il campo `version` del frontmatter viene incrementato, tutti i chunk e gli archi associati a quel `document_id` devono essere cancellati e rigenerati integralmente.
- **Effetto in caso di violazione (Failure Mode):** Chunk obsoleti duplicati nei database e disallineamento dell'indice.
- **Entità Target:** Nessuna.

### [REGOLA-VAL-09] Version bump bloccante obbligatorio
- **Descrizione:** Una modifica del corpo di un documento senza il contestuale incremento di `version` deve bloccare la pipeline con l'eccezione `VERSION_NOT_BUMPED`.
- **Effetto in caso di violazione (Failure Mode):** Rifiuto dell'ingestion incrementale dei dati.
- **Entità Target:** Nessuna.

### [REGOLA-INT-04] Rivalidazione automatica delle dipendenze
- **Descrizione:** La modifica di un documento con `authority ≥ 0.95` innesca automaticamente un ciclo di rivalidazione degli archi `DIPENDE_DA` e `VINCOLA` su tutta la knowledge base.
- **Effetto in caso di violazione (Failure Mode):** Collegamenti orfani o riferimenti a regole rimosse nel grafo.
- **Entità Target:** Nessuna.

### [REGOLA-INT-05] Aggiornamento atomico dei blocchi foglia
- **Descrizione:** I chunk registrati come blocchi atomici non ammettono modifiche parziali: l'aggiornamento comporta la sostituzione dell'intero blocco o il suo mantenimento inalterato.
- **Effetto in caso di violazione (Failure Mode):** Corruzione strutturale del contesto semantico del chunk.
- **Entità Target:** Nessuna.

### [REGOLA-INT-06] Unicità del `node_id` nel grafo
- **Descrizione:** Due documenti distinti non possono dichiarare lo stesso `graph_rag.node_id`. L'indicizzatore deve rilevare la collisione in fase di Discovery e bloccare l'ingestion con `DUPLICATE_NODE_ID`.
- **Effetto in caso di violazione (Failure Mode):** Due set di chunk convergono sullo stesso nodo: gli archi diventano ambigui e il retrieval restituisce contenuto duplicato con provenienza incerta.
- **Entità Target:** Nessuna.

> **Origine della regola (v2.0):** questa regola nasce da un difetto reale rilevato nel corpus di origine, dove due file con contenuto identico dichiaravano lo stesso `node_id` e uno dei due riportava nel frontmatter il `path` dell'altro.

---

## 6. Scenari Comportamentali BDD (Gherkin)

### Capability: Delta Ingestion e Aggiornamento Incrementale

```gherkin
Scenario: Rigenerazione automatica controllata della knowledge base
  Dato un documento Markdown esistente nel registro con il campo version incrementato
  Quando l'indicizzatore lancia la pipeline di aggiornamento incrementale
  Allora tutti i vecchi chunk associati a quel document_id vengono eliminati da Qdrant
  E il grafo cancella gli archi originati da quel nodo documento
  E la pipeline calcola i nuovi embedding reinserendoli nei database
  E vengono rivalidati tutti gli archi di tipo DIPENDE_DA cross-documento
```

```gherkin
Scenario: Registrazione e classificazione dinamica di una OPEN_SPEC
  Dato un nuovo file spec_esempio.md posizionato nella cartella delle specifiche
  Quando il motore di indicizzazione esegue la fase deterministica di Discovery
  Allora il documento viene riconosciuto tramite pattern matching spec_*.md
  E viene registrato nel grafo con il tipo nodo OPEN_SPEC
  E eredita il coefficiente di authority di default per le specifiche
  E viene sottomesso alle regole di isolamento H2 e marcatura delle entità core
```

```gherkin
Scenario: Blocco dell'ingestion su collisione di node_id
  Dato due documenti distinti che dichiarano lo stesso graph_rag.node_id
  Quando l'indicizzatore esegue la fase di Discovery
  Allora la pipeline si arresta sollevando DUPLICATE_NODE_ID per [REGOLA-INT-06]
  E nessuno dei due documenti viene indicizzato
  E l'errore riporta entrambi i percorsi sorgente in conflitto
```

---

*Fine del documento — baseline cross-progetto v2.0.0*

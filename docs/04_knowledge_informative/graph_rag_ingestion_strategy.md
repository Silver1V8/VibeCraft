---
id: "spec-graph-rag-ingestion-v1.1"
title: "Specifica Normativa — Strategia di Ingestion e Indicizzazione Graph-RAG"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.1.0"
date: "2026-07-12"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_graph_rag_ingestion.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-graph-rag-ingestion-v1.1"
  scope: "Definizione dei requisiti e dei vincoli del modulo Graph-RAG Ingestion"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-v1.2"
    - type: "DERIVA_DA"
      target: "ANALISI_FUNZIONALE_VIBE_CODING"
tags:
  - requirements
  - open-spec
  - vibecraft
  - ingestion
---

# Specifica Normativa — Strategia di Ingestion e Indicizzazione Graph-RAG
## VibeCraft — Sistema di Gestione Eventi Aziendali

---

## 1. Obiettivo e Ambito di Applicazione

La presente specifica definisce i requisiti funzionali e i vincoli obbligatori della pipeline di ingestion Graph-RAG adottata dal progetto VibeCraft. Lo scopo è garantire una rappresentazione coerente dei documenti Markdown all'interno dei sistemi Qdrant e NetworkX, preservando l'integrità semantica e la tracciabilità delle informazioni. L'indicizzatore analizza ricorsivamente tutti i documenti sotto `docs/` applicando un pattern matching basato su percorsi e denominazioni per assegnare i metadati corretti.

### [REGOLA-VAL-01] Classificazione automatica dei documenti
- **Descrizione:** Ogni documento sul filesystem deve essere classificato in modo deterministico mediante pattern matching del percorso e del nome file sorgente.
- **Effetto in caso di violazione (Failure Mode):** Il documento viene escluso dall'indice oppure viene assegnato a una categoria errata, corrompendo i moltiplicatori di rango.
- **Entità Target:** Nessuna.

### [REGOLA-INT-01] Estensibilità automatica delle specifiche
- **Descrizione:** Ogni nuovo file inserito nella cartella delle specifiche che rispetti il pattern `spec_*.md` deve essere registrato come nodo `OPEN_SPEC` con authority di default pari a `0.87`.
- **Effetto in caso di violazione (Failure Mode):** Il documento viene escluso dal knowledge graph, rendendo invisibili le nuove capability all'LLM.
- **Entità Target:** Nessuna.

---

## 2. Requisiti di Chunking Dinamico e Compressione

### [REGOLA-VAL-02] Limite dimensionale dei chunk
- **Descrizione:** La segmentazione dei testi deve produrre blocchi semantici con un limite dimensionale inferiore a 1500 caratteri per preservare la densità informativa.
- **Effetto in caso di violazione (Failure Mode):** Diluizione della firma semantica del vettore ed errori di accuratezza nel Dense Retrieval.
- **Entità Target:** Nessuna.

### [REGOLA-VAL-03] Blocchi atomici inviolabili
- **Descrizione:** Le definizioni di entità, le schede di salvaguardia, gli scenari BDD e le tabelle di vincoli costituiscono strutture atomiche che non devono mai essere spezzate durante la segmentazione.
- **Effetto in caso di violazione (Failure Mode):** Perdita del contesto logico e rottura delle relazioni strutturali nel grafo.
- **Entità Target:** Nessuna.

### [REGOLA-VAL-04] Segmentazione gerarchica in cascata
- **Descrizione:** Il modulo di chunking deve operare applicando la priorità di taglio in cascata: 1. Blocchi atomici, 2. Intestazioni H2, 3. Intestazioni H3, 4. Paragrafi.
- **Effetto in caso di violazione (Failure Mode):** Generazione di embedding semanticamente incompleti o frammentati.
- **Entità Target:** Nessuna.

### [REGOLA-VAL-05] Breadcrumb obbligatorio per payload
- **Descrizione:** Ogni sotto-chunk derivato da livelli H3 o inferiori deve includere un prefisso di contesto strutturato, memorizzato esclusivamente nel payload Qdrant e rimosso prima del calcolo dell'embedding.
- **Effetto in caso di violazione (Failure Mode):** Perdita dell'ancoraggio gerarchico originario durante la composizione del prompt.
- **Entità Target:** Nessuna.

### [REGOLA-VAL-06] Compressione controllata lossy
- **Descrizione:** Se un blocco atomico supera 1500 caratteri, l'indicizzatore applica una compressione conservando l'identificatore, l'invariante e le entità coinvolte, bloccando l'ingestion con severity `WARNING` al superamento del limite assoluto di 2500 caratteri.
- **Effetto in caso di violazione (Failure Mode):** Rigetto del blocco normativo o crash della pipeline di pre-processing.
- **Entità Target:** Nessuna.

---

## 3. Vincoli delle Entità Core e della Tassonomia

### [REGOLA-INT-02] Formato obbligatorio entità core
- **Descrizione:** Qualsiasi riferimento nel testo dei chunk alle entità di dominio `` `UTENTE` ``, `` `EVENTO` ``, `` `RICHIESTA` ``, `` `AUDIT_LOG` ``, `` `NOTIFICA` `` o `` `BUDGET_ANNUO` `` deve essere scritto in maiuscolo e racchiuso tra backtick.
- **Effetto in caso di violazione (Failure Mode):** Il parser regex fallisce il riconoscimento, impedendo la creazione automatica delle relazioni nel grafo.
- **Entità Target:** `` `UTENTE` ``, `` `EVENTO` ``, `` `RICHIESTA` ``, `` `AUDIT_LOG` ``, `` `NOTIFICA` ``, `` `BUDGET_ANNUO` ``.

### [REGOLA-VAL-07] Tassonomia degli identificatori di regola
- **Descrizione:** Ogni norma di business deve aprirsi con un identificatore strutturato conforme al formato `[PREFISSO-CATEGORIA-XX]`, mappato sulla tassonomia ufficiale che include le famiglie `REGOLA-WF`, `REGOLA-VAL`, `REGOLA-INT`, `REGOLA-AUTH`, `REGOLA-CONC`, `REGOLA-RAG` e `SAFEGUARD`.
- **Effetto in caso di violazione (Failure Mode):** Il parser rigetta l'identificatore, impedendo la generazione dei rispettivi nodi di governance nel grafo.
- **Entità Target:** Nessuna.

### [REGOLA-INT-03] Generazione automatica degli archi impliciti
- **Descrizione:** Durante il parsing del testo di un chunk, la presenza di entità o regole deve innescare la creazione automatica degli archi di tipo `CONTIENE`, `MENZIONA` e `DIPENDE_DA` verso i rispettivi nodi nel grafo NetworkX.
- **Effetto in caso di violazione (Failure Mode):** Perdita della connettività topologica e fallimento delle query multi-hop.
- **Entità Target:** `` `UTENTE` ``, `` `EVENTO` ``, `` `RICHIESTA` ``, `` `AUDIT_LOG` ``, `` `NOTIFICA` ``, `` `BUDGET_ANNUO` ``.

---

## 4. Requisiti di Retrieval e Authority Boost

### [REGOLA-WF-01] Sequenza obbligatoria della pipeline di ricerca
- **Descrizione:** Il motore di recupero dell'endpoint `/ask` deve eseguire la sequenza rigida a 5 livelli: 1. Risoluzione sinonimi, 2. Dense Query (BGE-M3), 3. Sparse Query (BM25), 4. Reranking ColBERT, 5. Authority Boost, 6. Graph Expansion. Nessuna fase può essere bypassata.
- **Effetto in caso di violazione (Failure Mode):** Degradazione della qualità del ranking e potenziale inclusione di allucinazioni nel contesto.
- **Entità Target:** Nessuna.

### [REGOLA-VAL-08] Applicazione del coefficiente di authority moltiplicativo
- **Descrizione:** Il posizionamento finale dei chunk nel context window deve essere determinato moltiplicando lo score di rilevanza ColBERT per il coefficiente di `authority` definito nel frontmatter YAML della sorgente.
- **Effetto in caso di violazione (Failure Mode):** Mancato rispetto della gerarchia delle fonti e inversione di priorità tra contratti di sicurezza e testi descrittivi.
- **Entità Target:** Nessuna.

---

## 5. Regole di Aggiornamento Incrementale e Delta Ingestion

### [REGOLA-WF-02] Sequenza operativa di ingestion
- **Descrizione:** L'esecuzione dello script di indicizzazione deve seguire le fasi obbligatorie di Discovery, Pre-processing, Embedding, Costruzione Grafo e Validazione.
- **Effetto in caso di violazione (Failure Mode):** Pipeline instabile e non deterministica.
- **Entità Target:** Nessuna.

### [REGOLA-WF-03] Sostituzione atomica per versione documentale
- **Descrizione:** Quando il campo `version` del frontmatter YAML subisce un incremento, tutti i chunk e gli archi associati a quel `document_id` devono essere cancellati da Qdrant e NetworkX e rigenerati integralmente.
- **Effetto in caso di violazione (Failure Mode):** Presenza di chunk obsoleti duplicati nei database e disallineamento dell'indice.
- **Entità Target:** Nessuna.

### [REGOLA-VAL-09] Version bump bloccante obbligatorio
- **Descrizione:** Una modifica del corpo di un documento sprovvista del contestuale incremento del campo `version` nel frontmatter deve bloccare la pipeline restituendo l'eccezione `VERSION_NOT_BUMPED`.
- **Effetto in caso di violazione (Failure Mode):** Rifiuto dell'ingestion incrementale dei dati.
- **Entità Target:** Nessuna.

### [REGOLA-INT-04] Rivalidazione automatica delle dipendenze
- **Descrizione:** La modifica incrementale di un documento con `authority ≥ 0.95` deve innescare automaticamente un ciclo di rivalidazione degli archi `DIPENDE_DA` e `VINCOLA` su tutta la knowledge base.
- **Effetto in caso di violazione (Failure Mode):** Presenza di collegamenti orfani o riferimenti a regole rimosse nel grafo.
- **Entità Target:** Nessuna.

### [REGOLA-INT-05] Aggiornamento atomico dei blocchi foglia
- **Descrizione:** I chunk registrati come blocchi atomici inviolabili non ammettono modifiche parziali; l'aggiornamento deve comportare la sostituzione dell'intero blocco o il suo mantenimento inalterato.
- **Effetto in caso di violazione (Failure Mode):** Corruzione strutturale del contesto semantico del chunk.
- **Entità Target:** Nessuna.

---

## 6. Scenari Comportamentali BDD (Gherkin)

### Capability: Delta Ingestion e Aggiornamento Incrementale

```gherkin
Scenario: Rigenerazione automatica controllata della knowledge base
  Dato un documento Markdown esistente nel registro con il campo version incrementato
  Quando l'indicizzatore lancia la pipeline di aggiornamento incrementale
  Allora tutti i vecchi chunk associati a quel document_id vengono eliminati da Qdrant
  E il grafo NetworkX cancella gli archi originati da quel nodo documento
  E la pipeline calcola i nuovi embedding BGE-M3 reinserendoli nei database
  E vengono rivalidati tutti gli archi di tipo DIPENDE_DA cross-documento
  ```
### Capability: Delta Ingestion e Aggiornamento Incrementale

```gherkin
Scenario: Registrazione e classificazione dinamica di una OPEN_SPEC
  Dato un nuovo file spec_wf_states_2.1.md posizionato nella cartella delle specifiche
  Quando il motore di indicizzazione esegue la fase deterministica di Discovery
  Allora il documento viene riconosciuto tramite pattern matching spec_*.md
  E viene registrato nel grafo con il tipo nodo OPEN_SPEC
  E eredita un coefficiente moltiplicativo authority pari a 0.87
  E viene sottomesso alle regole di isolamento H2 e marcatura delle entità core
```
---
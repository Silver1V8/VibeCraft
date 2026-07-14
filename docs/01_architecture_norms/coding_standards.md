---
id: "norm-coding-standards-v1.0"
title: "Normativa Interna — Standard di Codifica e Clean Code"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-12"
status: "ENFORCED"
classification: "NORMS"
path: "docs/01_architecture_norms/coding_standards.md"
authority: 0.85
graph_rag:
  node_type: "METHODOLOGY"
  node_id: "norm-coding-standards-v1.0"
  scope: "Definizione degli standard di programmazione, refactoring e tagging della governance nel codice"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "DERIVA_DA"
      target: "ANALISI_FUNZIONALE_VIBE_CODING"
tags:
  - norms
  - methodology
  - clean-code
  - coding-standards
  - software-engineering
---

# Normativa Interna — Standard di Codifica e Clean Code
## VibeCraft — Sistema di Gestione Eventi Aziendali

---

## 1. Obiettivo e Standard di Coesione del Team

La presente normativa stabilisce i vincoli di stile, le convenzioni di programmazione e le metriche di qualità strutturale obbligatorie per lo sviluppo del software all'interno del progetto VibeCraft. Lo scopo è garantire l'assoluta leggibilità, manutenibilità e uniformità del codice scritto dai membri del team e dagli agenti autonomi di Intelligenza Artificiale. 

L'aderenza a questi standard è verificata automaticamente dai gate di controllo in fase di CI/CD. Il superamento delle soglie metriche definite nei capitoli successivi comporta il rigetto del codice, al fine di prevenire il debito tecnico e garantire che ogni modulo software sia strettamente ancorato alle specifiche transazionali del sistema.

---

## 2. Metriche Strutturali e Limiti del Codice Backend

### [REGOLA-CLEAN-01] Limite dimensionale dei corpi funzione
- **Descrizione:** Ogni singola funzione o metodo sviluppato all'interno dei moduli di backend (FastAPI/Python) non deve mai superare il limite rigoroso di 40 righe effettive di codice (escludendo dal computo le righe vuote e i commenti di documentazione/docstring). Funzioni che eccedono questa soglia devono essere tassativamente scomposte applicando il pattern di refactoring *Extract Method*.
- **Effetto in caso di violazione (Failure Mode):** Il linter statico blocca il commit segnalando un'anomalia di complessità e rifiuta l'allineamento.
- **Entità Target:** Nessuna.

### [REGOLA-CLEAN-02] Gestione centralizzata e tipizzata delle eccezioni
- **Descrizione:** È fatto divieto assoluto di utilizzare blocchi `try-except` vuoti o generici (`except Exception: pass`) che mascherano gli errori. Ogni anomalia transazionale o di business logic deve essere intercettata e rimappata sollevando eccezioni custom ereditate dai controller globali del framework, i quali devono restituire al client codici HTTP standardizzati (400, 422, 500) scrivendo contestualmente l'evento nell' `AUDIT_LOG`.
- **Effetto in caso di violazione (Failure Mode):** Perdita di tracciabilità dei bug a runtime, fallimento silente delle transazioni e potenziale corruzione dei dati.
- **Entità Target:** `AUDIT_LOG`

---

## 3. Tracciabilità della Governance nel Codice Sorgente

### [REGOLA-CLEAN-03] Tagging esplicito delle regole nei docstring
- **Descrizione:** Ogni singola routine, endpoint API o query sul database che implementi o verifichi un vincolo di business deve riportare all'interno del proprio docstring iniziale il tag esplicito della specifica normativa di riferimento (es. `Tags: [REGOLA-WF-02]`, `Enforces: [SAFEGUARD-TXN-01]`). Questa marcatura permette allo scansionatore AST del file `code_index.py` di mappare gli archi nel grafo delle dipendenze.
- **Effetto in caso di violazione (Failure Mode):** Rottura della tracciabilità bidirezionale dell'Impact Ripple, rendendo invisibili le righe di codice associate a quella determinata norma.
- **Entità Target:** Nessuna.

### [REGOLA-CLEAN-04] Isolamento e immutabilità dei modelli Pydantic
- **Descrizione:** Tutti i payload di input provenienti dall'interfaccia utente legati ad azioni sulle entità `RICHIESTA` o `EVENTO` devono essere validati tramite schemi Pydantic v2 configurati in modalità rigida (`extra='forbid'`). I modelli di output inviati verso la dashboard devono mascherare i campi sensibili o riservati del dipendente.
- **Effetto in caso di violazione (Failure Mode):** Esposizione a vulnerabilità di Mass Assignment e data leak di informazioni aziendali riservate.
- **Entità Target:** `RICHIESTA`, `EVENTO`, `UTENTE`

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Validazione Automatica degli Standard di Stile (Linting Gate)

```gherkin
Scenario: Blocco del deploy per violazione della lunghezza massima di una funzione
  Dato un programmatore che ha modificato il controller delle approvazioni della risorsa RICHIESTA
  E ha scritto una funzione di gestione del budget che conta 55 righe effettive di codice
  Quando lo script di validazione esegue l'ispezione statica AST sul file modificato
  Allora il sistema rileva l'infrazione della [REGOLA-CLEAN-01]
  E interrompe la pipeline sollevando l'eccezione STYLE_SOGLIA_SUPERATA
  E impedisce il deploy del codice impedendo la corruzione del Clean Code
```

```gherkin
Scenario: Tracciamento corretto di una regola nel codice tramite AST
  Dato un endpoint FastAPI che implementa la validazione della capienza massima di un EVENTO
  E il docstring di questa funzione contiene la stringa "Enforces: [REGOLA-VAL-01]"
  Quando viene lanciato il modulo code_index.py per rigenerare la conoscenza locale
  Allora il parser analizza l'albero sintattico del file Python
  E intercetta il tag della regola estraendo il collegamento
  E crea con successo un arco di tipo IMPLEMENTS nel grafo NetworkX tra il file di codice e il nodo regola
```
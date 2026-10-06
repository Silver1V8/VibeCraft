---
id: "coding-standards-baseline-v2.0"
title: "Normativa Interna — Standard di Codifica e Clean Code (Baseline Cross-Progetto)"
project: "cross-project"
scope: "cross-project"
version: "2.0.0"
date: "2026-07-22"
status: "ENFORCED"
classification: "METHODOLOGY"
path: "docs/01_architecture_norms/coding_standards.md"
authority: 0.85
changelog:
  - version: "2.0.0"
    date: "2026-07-22"
    changes:
      - "Riscrittura cross-progetto: rimossi gli agganci al dominio prenotazione eventi"
      - "Risolta la contraddizione di stack: le regole sono ora agnostiche (era FastAPI/Pydantic hardcoded, in conflitto con la spec backend .NET)"
      - "Aggiunta REGOLA-CLEAN-05 (magic number) e REGOLA-CLEAN-06 (isolamento business logic), promosse da vibe_coding_workflow"
      - "Aggiunta Sezione 0 — Contratto di Istanziazione con le soglie parametriche"
reuse:
  parameters:
    - "<<STACK_BACKEND>>: linguaggio e framework del backend"
    - "<<LIB_VALIDAZIONE>>: libreria di validazione dei payload in ingresso"
    - "<<TABELLA_AUDIT>>: tabella append-only del giornale di audit"
    - "<<SOGLIA_RIGHE_FUNZIONE>>: limite di righe effettive per funzione (default 40)"
    - "<<GLOSSARIO_PROGETTO>>: documento che definisce la terminologia canonica"
  instantiation: "Copiare il file, compilare la Sezione 0, sostituire ogni <<PARAMETRO>>. Gli identificatori [REGOLA-CLEAN-NN] devono restare stabili: sono referenziati dai docstring del codice e dallo scanner AST."
graph_rag:
  node_type: "METHODOLOGY"
  node_id: "coding-standards-baseline-v2.0"
  databases: ["Qdrant", "NetworkX"]
  edges:
    - type: "CONNESSA_A"
      target: "safeguards-security-baseline-v2.0"
    - type: "CONNESSA_A"
      target: "vibe-coding-workflow-baseline-v2.0"
tags:
  - norms
  - methodology
  - clean-code
  - coding-standards
  - software-engineering
  - cross-project
  - baseline
---

# Normativa Interna — Standard di Codifica e Clean Code
## Baseline Cross-Progetto

---

## 1. Obiettivo e Standard di Coesione del Team

La presente normativa stabilisce i vincoli di stile, le convenzioni di programmazione e le metriche di qualità strutturale obbligatorie per lo sviluppo del software. Lo scopo è garantire leggibilità, manutenibilità e uniformità del codice scritto sia dai membri umani del team sia dagli agenti autonomi di Intelligenza Artificiale.

L'aderenza è verificata automaticamente dai gate di controllo in CI/CD. Il superamento delle soglie definite comporta il rigetto del codice, per prevenire il debito tecnico e garantire che ogni modulo resti ancorato alle specifiche.

**Questo file è la baseline generica.** I segnaposto `<<PARAMETRO>>` vanno risolti nella Sezione 0 prima che la normativa sia operativa.

---

## Sezione 0 — Contratto di Istanziazione

| Parametro | Significato | Valore nel progetto |
|---|---|---|
| `<<STACK_BACKEND>>` | Linguaggio e framework backend | *(da compilare)* |
| `<<LIB_VALIDAZIONE>>` | Libreria di validazione dei payload | *(da compilare)* |
| `<<TABELLA_AUDIT>>` | Tabella append-only del giornale di audit | *(da compilare)* |
| `<<SOGLIA_RIGHE_FUNZIONE>>` | Righe effettive massime per funzione | `40` *(default)* |
| `<<GLOSSARIO_PROGETTO>>` | Documento della terminologia canonica | *(da compilare)* |

> **Nota storica sulla coerenza:** la versione 1.0 di questa normativa citava uno stack concreto (FastAPI/Pydantic) in conflitto con la specifica tecnologica del progetto che la adottava. Le regole sono ora **agnostiche rispetto allo stack**: ogni riferimento tecnologico passa dalla Sezione 0. Non reintrodurre nomi di framework nel corpo delle regole.

---

## 2. Metriche Strutturali e Limiti del Codice

### [REGOLA-CLEAN-01] Limite dimensionale dei corpi funzione
- **Descrizione:** Ogni funzione o metodo non deve superare il limite di `<<SOGLIA_RIGHE_FUNZIONE>>` righe effettive di codice (escluse righe vuote e commenti/docstring). Le funzioni che eccedono la soglia devono essere scomposte applicando il pattern di refactoring *Extract Method*, con nomi puramente semantici per le sotto-funzioni.
- **Effetto in caso di violazione (Failure Mode):** Il linter statico blocca il commit segnalando un'anomalia di complessità.
- **Entità Target:** Nessuna.

### [REGOLA-CLEAN-02] Gestione centralizzata e tipizzata delle eccezioni
- **Descrizione:** È vietato l'uso di blocchi di cattura vuoti o generici che mascherano gli errori (`except Exception: pass`, `catch { }`, `catch (Exception) { }` senza rilancio). Ogni anomalia transazionale o di business logic deve essere intercettata e rimappata sollevando eccezioni custom gestite dai controller globali del framework, che restituiscono al client codici HTTP standardizzati (400, 403, 409, 422, 500) scrivendo contestualmente l'evento in `<<TABELLA_AUDIT>>`.
- **Effetto in caso di violazione (Failure Mode):** Perdita di tracciabilità dei bug a runtime, fallimento silente delle transazioni, potenziale corruzione dei dati.
- **Entità Target:** `<<TABELLA_AUDIT>>`

---

## 3. Tracciabilità della Governance nel Codice Sorgente

### [REGOLA-CLEAN-03] Tagging esplicito delle regole nei docstring
- **Descrizione:** Ogni routine, endpoint API o query che implementi o verifichi un vincolo di business deve riportare nel proprio docstring iniziale il tag esplicito della normativa di riferimento (es. `Tags: [REGOLA-WF-02]`, `Enforces: [SAFEGUARD-TXN-01]`). Questa marcatura permette allo scanner AST dell'indicizzatore di mappare gli archi nel grafo delle dipendenze.
- **Effetto in caso di violazione (Failure Mode):** Rottura della tracciabilità bidirezionale dell'Impact Ripple: le righe di codice associate alla norma diventano invisibili al grafo.
- **Entità Target:** Nessuna.

> **Vincolo di stabilità:** gli identificatori `[REGOLA-*]` e `[SAFEGUARD-*]` sono **chiavi di grafo**, non etichette descrittive. Rinominarli rompe ogni arco `IMPLEMENTS` già stabilito. Un identificatore si deprecia, non si rinomina.

### [REGOLA-CLEAN-04] Isolamento e immutabilità dei modelli di input
- **Descrizione:** Tutti i payload provenienti dall'interfaccia utente devono essere validati tramite `<<LIB_VALIDAZIONE>>` configurata in **modalità rigida**: i campi non previsti dallo schema vengono rifiutati, non ignorati. I modelli di output devono mascherare i campi sensibili o riservati.
- **Effetto in caso di violazione (Failure Mode):** Esposizione a vulnerabilità di Mass Assignment e data leak di informazioni riservate.
- **Entità Target:** tutte le entità esposte da API pubbliche o autenticate.

### [REGOLA-CLEAN-05] Estrazione dei magic number e parametrizzazione
- **Descrizione:** Nessun valore costante o parametro numerico letterale deve comparire inline nel codice applicativo. Ogni valore statico — soglie, TTL, limiti di paginazione, durate di sessione — deve essere estratto in costanti nominate o in file di configurazione dedicati.
- **Effetto in caso di violazione (Failure Mode):** Valori duplicati che divergono nel tempo; modifica di una soglia che richiede una caccia al valore in tutto il codebase.
- **Entità Target:** Nessuna.

### [REGOLA-CLEAN-06] Isolamento delle regole di business
- **Descrizione:** La validazione delle regole di business e l'enforcement dei vincoli logici devono essere disaccoppiati dal layer di presentazione (UI) e dal layer di persistenza (Repository/ORM). È vietato annidare regole decisionali dentro event handler del frontend o dentro query SQL grezze.
- **Effetto in caso di violazione (Failure Mode):** Regola non testabile in isolamento, non riusabile fuori dal suo entry point, e aggirabile chiamando un percorso diverso.
- **Entità Target:** Nessuna.

### [REGOLA-CLEAN-07] Allineamento terminologico rigido
- **Descrizione:** È vietato introdurre termini o sinonimi non presenti in `<<GLOSSARIO_PROGETTO>>`. I nomi di variabili, funzioni, entità, colonne, rotte e classi devono ereditare la denominazione esatta del glossario. Un concetto ha **un solo nome** in tutto lo stack, dal database all'interfaccia.
- **Effetto in caso di violazione (Failure Mode):** Divergenza semantica tra documentazione e codice; il retrieval del Graph RAG non ricollega più il codice alla regola che lo governa.
- **Entità Target:** Nessuna.

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Validazione Automatica degli Standard di Stile (Linting Gate)

```gherkin
Scenario: Blocco del deploy per violazione della lunghezza massima di una funzione
  Dato un programmatore che ha modificato un controller di dominio
  E ha scritto una funzione che conta 55 righe effettive di codice
  Quando lo script di validazione esegue l'ispezione statica AST sul file modificato
  Allora il sistema rileva l'infrazione della [REGOLA-CLEAN-01]
  E interrompe la pipeline sollevando l'eccezione STYLE_SOGLIA_SUPERATA
  E impedisce il deploy del codice
```

```gherkin
Scenario: Tracciamento corretto di una regola nel codice tramite AST
  Dato un endpoint che implementa un vincolo di business documentato
  E il docstring di questa funzione contiene la stringa "Enforces: [REGOLA-VAL-01]"
  Quando viene lanciato l'indicizzatore di codice per rigenerare la conoscenza locale
  Allora il parser analizza l'albero sintattico del file
  E intercetta il tag della regola estraendo il collegamento
  E crea un arco di tipo IMPLEMENTS nel grafo tra il file di codice e il nodo regola
```

```gherkin
Scenario: Rigetto di un payload con campo non previsto dallo schema
  Dato un endpoint che accetta un payload validato in modalità rigida
  E un client che invia un campo aggiuntivo non dichiarato nello schema
  Quando il layer di validazione elabora la richiesta
  Allora la richiesta viene rigettata con HTTP 422 per [REGOLA-CLEAN-04]
  E nessun campo non dichiarato raggiunge il layer di persistenza
```

---

## 5. Riepilogo delle Regole

| ID | Vincolo operativo core |
|---|---|
| `[REGOLA-CLEAN-01]` | Massimo `<<SOGLIA_RIGHE_FUNZIONE>>` righe per funzione, altrimenti Extract Method. |
| `[REGOLA-CLEAN-02]` | Nessun catch vuoto o generico; eccezioni tipizzate e audit dell'anomalia. |
| `[REGOLA-CLEAN-03]` | Tag `[REGOLA-*]` / `[SAFEGUARD-*]` nei docstring per lo scanner AST. |
| `[REGOLA-CLEAN-04]` | Validazione rigida dell'input, mascheramento dell'output sensibile. |
| `[REGOLA-CLEAN-05]` | Nessun magic number inline: costanti nominate o configurazione. |
| `[REGOLA-CLEAN-06]` | Business logic isolata da UI e persistenza. |
| `[REGOLA-CLEAN-07]` | Un concetto, un solo nome, dal database all'interfaccia. |

---

*Fine del documento — baseline cross-progetto v2.0.0*

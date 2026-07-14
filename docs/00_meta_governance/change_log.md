---
id: "meta-change-log-v1.0"
title: "Registro delle Modifiche — Change Log di VibeCraft"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-13"
status: "ENFORCED"
classification: "METADATA"
path: "docs/00_meta_governance/change_log.md"
authority: 0.90
graph_rag:
  node_type: "DOCUMENT"
  node_id: "meta-change-log-v1.0"
  scope: "Tracciamento storico delle versioni e delle modifiche apportate alla documentazione di VibeCraft"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "CONTIENE"
      target: "spec-graph-rag-ingestion-v1.1"
    - type: "CONTIENE"
      target: "spec-wf-states-v1.0"
    - type: "CONTIENE"
      target: "spec-concurrency-v1.0"
    - type: "CONTIENE"
      target: "spec-dash-v1.0"
    - type: "CONTIENE"
      target: "spec-det-v1.0"
    - type: "CONTIENE"
      target: "spec-form-v1.0"
    - type: "CONTIENE"
      target: "spec-area-pers-v1.0"
    - type: "CONTIENE"
      target: "spec-mgr-panel-v1.0"
    - type: "CONTIENE"
      target: "spec-crud-admin-v1.0"
    - type: "CONTIENE"
      target: "spec-monitor-admin-v1.0"
    - type: "CONTIENE"
      target: "spec-notifications-v1.0"
    - type: "CONTIENE"
      target: "spec-export-v1.0"
    - type: "CONTIENE"
      target: "spec-analytics-v1.0"
tags:
  - metadata
  - change-log
  - governance
  - versioning
---

# Registro delle Modifiche — Change Log di VibeCraft
## VibeCraft — Sistema di Gestione Eventi Aziendali

---

## 1. Obiettivo e Controllo del Versionamento

La presente specifica di tracciamento definisce lo storico delle modifiche apportate a tutti i documenti normativi, tecnici e metodologici che costituiscono la Knowledge Base di VibeCraft. Lo scopo di questo registro è garantire l'assoluta tracciabilità delle revisioni, l'integrità dei riferimenti incrociati e la sincronizzazione ottimale con l'indicizzatore Graph-RAG, prevenendo disallineamenti di versione tra i database Qdrant e NetworkX.

Ogni modifica ai contratti di sicurezza, alle logiche di business delle risorse `RICHIESTA` ed `EVENTO` o alla gestione del `BUDGET_ANNUO` deve essere registrata in questo file.

---

## 2. Regole di Gestione delle Versioni (Version Control Rules)

### [REGOLA-DEV-01] Obbligatorietà del versionamento semantico
- **Descrizione:** Tutti i documenti inseriti nel workspace di VibeCraft devono adottare il versionamento semantico a tre cifre (`X.Y.Z`), dove:
  - `X` (Major): Cambiamenti architetturali o riscritture strutturali dei vincoli.
  - `Y` (Minor): Aggiunta di nuove specifiche di funzionalità (OPEN_SPEC) o regole.
  - `Z` (Patch): Correzioni minori di refactoring o formattazione che non alterano i contratti.
- **Effetto in caso di violazione (Failure Mode):** L'indicizzatore solleva un warning di non conformità sintattica durante la fase di validazione.
- **Entità Target:** Nessuna.

### [REGOLA-DEV-02] Tracciamento dei blocchi modificati
- **Descrizione:** Ogni riga del log di modifica deve contenere: la data di rilascio, la versione assegnata, l'autore HR o tecnico dell'aggiornamento, l'elenco esatto dei file modificati e la motivazione sintetica della variazione con i tag delle regole impattate.
- **Effetto in caso di violazione (Failure Mode):** Perdita della correlazione storica e potenziale generazione di archi incoerenti nel grafo.
- **Entità Target:** Nessuna.

---

## 3. Storico delle Versioni Rilasciate

### Versione 1.1.0 (13 Luglio 2026)
* **Autore:** Patrizio (Senior IT Architect)
* **File Modificati:**
  * `docs/04_knowledge_informative/graph_rag_ingestion_strategy.md`
  * `docs/02_specs_normative/spec_graph_rag_ingestion.md`
  * `docs/02_specs_normative/spec_wf_states_2.1.md`
  * `docs/02_specs_normative/spec_concurrency_2.3.md`
  * `docs/02_specs_normative/spec_dash_1.2.md`
  * `docs/01_architecture_norms/coding_standards.md`
  * `docs/02_specs_normative/spec_det_1.3.md`
  * `docs/02_specs_normative/spec_form_1.4.md`
  * `docs/02_specs_normative/spec_area_pers_1.5.md`
  * `docs/02_specs_normative/spec_mgr_panel_2.2.md`
  * `docs/02_specs_normative/spec_crud_admin_3.2.md`
  * `docs/02_specs_normative/spec_monitor_admin_3.3.md`
  * `docs/02_specs_normative/spec_notifications_2.4.md`
  * `docs/02_specs_normative/spec_export_3.4.md`
  * `docs/02_specs_normative/spec_analytics_3.5.md`
  * `docs/00_meta_governance/change_log.md`
* **Descrizione Modifiche:** Scomposizione della strategia di ingestion, stesura delle specifiche del modulo di validazione, sottomissione dei form, gestione code, reportistica di analytics e blindatura della concorrenza del database tramite locking pessimistico `FOR UPDATE`.

### Versione 1.0.0 (08 Luglio 2026)
* **Autore:** Giuseppe (Team Lead)
* **File Modificati:**
  * `docs/00_meta_governance/safeguards_security.md`
  * `docs/00_meta_governance/glossario_entita.md`
  * `docs/00_meta_governance/matrice_permessi.md`
  * `docs/00_meta_governance/ANALISI_FUNZIONALE_VIBE_CODING.md`
  * `docs/02_specs_normative/spec_auth_1.1.md`
* **Descrizione Modifiche:** Rilascio iniziale del nucleo di governance di VibeCraft, mappatura dei permessi degli attori del sistema (RBAC) e prima specifica di autenticazione e sicurezza delle sessioni.

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Tracciamento Storico e Validazione del Change Log

```gherkin
Scenario: Validazione automatica del Change Log durante il commit
  Dato un programmatore che ha completato l'aggiornamento di un file spec_*.md
  E ha correttamente incrementato il campo version nel frontmatter YAML
  Quando l'indicizzatore analizza il file change_log.md nel processo di Discovery
  Allora verifica la presenza di una riga corrispondente alla nuova versione rilasciata
  E valida che la versione riportata coincida con il metadato del file modificato
  E inserisce un record di validazione storica andata a buon fine nell' `AUDIT_LOG`
```
```
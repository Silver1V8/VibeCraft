---
id: "meta-change-log-v1.0"
title: "Registro delle Modifiche — Change Log di VibeCraft"
project: "cross-project"
version: "2.1.0"
date: "2026-09-07"
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
      target: "spec-graph-rag-ingestion-v2.0"
  # `spec-graph-rag-ingestion-v1.1` ripuntato a `-v2.0` il 2026-09-04: il documento esiste,
  # il node_id no — la spec dichiara `v2.0`, e `v1.1` restava un nodo fantasma accanto al
  # documento vero. Ripuntare qui e' legittimo (asserzione sul presente, target esistente),
  # a differenza dei path storici di §3, che sono un ricordo e non si riscrivono.
  # I 12 target rimossi il 2026-09-04 (spec-wf-states, spec-concurrency, spec-dash,
  # spec-det, spec-form, spec-area-pers, spec-mgr-panel, spec-crud-admin,
  # spec-monitor-admin, spec-notifications, spec-export, spec-analytics) puntavano a
  # documenti del dominio dismesso che non esistono piu' nel corpus. Un arco CONTIENE
  # non e' un ricordo: e' un'asserzione sul grafo di OGGI, riscritta a ogni build.
  # Misurato prima della rimozione: add_frontmatter_edges li materializzava come nodi
  # `type: entity` con reliability 0.9 (nature: curated), cioe' 12 documenti fantasma
  # dichiarati affidabili. Lo STORICO di quelle release resta in §3, dove e' storia.
tags:
  - metadata
  - change-log
  - governance
  - versioning
---

# Registro delle Modifiche — Change Log di VibeCraft

---

## 1. Obiettivo e Controllo del Versionamento

La presente specifica di tracciamento definisce lo storico delle modifiche apportate a tutti i documenti normativi, tecnici e metodologici che costituiscono la Knowledge Base di VibeCraft. Lo scopo di questo registro è garantire l'assoluta tracciabilità delle revisioni, l'integrità dei riferimenti incrociati e la sincronizzazione ottimale con l'indicizzatore Graph-RAG, prevenendo disallineamenti di versione tra i database Qdrant e NetworkX.

Ogni modifica ai contratti di sicurezza, alle regole enforceable dei documenti normativi o alla struttura del frontmatter che l'indicizzatore legge deve essere registrata in questo file.

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
- **Descrizione:** Ogni riga del log di modifica deve contenere: la data di rilascio, la versione assegnata, l'autore dell'aggiornamento, l'elenco esatto dei file modificati e la motivazione sintetica della variazione con i tag delle regole impattate.
- **Effetto in caso di violazione (Failure Mode):** Perdita della correlazione storica e potenziale generazione di archi incoerenti nel grafo.
- **Entità Target:** Nessuna.

---

## 3. Storico delle Versioni Rilasciate

### Versione 2.1.0 (07 Settembre 2026)
* **Autore:** manutenzione della knowledge base (Run S8-S10, tracciamento del registro)
* **File Modificati:**
  * `docs/04_knowledge_informative/inferenza_locale_o_remota.md` — **nuovo**
  * `docs/01_architecture_norms/architecture_decision_rationale.md`
  * `docs/04_knowledge_informative/graph_rag_ingestion_strategy.md`
  * `docs/README.md`
  * `docs/00_meta_governance/change_log.md`
* **Descrizione Modifiche:** Aggiunta la nota informativa `inferenza_locale_o_remota.md`
  (METHODOLOGY, authority 0.40) su un tema non coperto dal corpus. Corretti due archi
  `CONTIENE` morti nel frontmatter tracciato (`spec-graph-rag-ingestion-v1.1` e
  `norm-coding-standards-v1.0`, quest'ultimo con base-id diverso e privo di arco
  documento→documento), rilevati durante S10 [R18]. Aggiornato l'indice di `docs/README.md`
  con le voci mancanti di `change_log.md` e `architecture_decision_rationale.md`. Questo
  stesso file, mai tracciato da git da quando esiste, è stato aggiunto al repository ed è ora
  pubblicato su GitHub (rimossa l'esclusione mirata nel `.gitignore`). **Bump minor** perché
  aggiunge un documento nuovo alla knowledge base, non solo correzioni di forma.

> **Nota di lettura (aggiunta il 2026-09-04).** Le voci 1.1.0 e 1.0.0 qui sotto
> elencano file che **non fanno più parte del corpus**: appartenevano al dominio
> applicativo dismesso, rimosso dalla knowledge base con la versione 2.0.0. I loro path
> sono conservati **così come furono scritti** — [REGOLA-DEV-02] impone che ogni riga
> riporti l'elenco esatto dei file modificati, e riscrivere un path a posteriori per
> farlo puntare a un documento esistente falsificherebbe il record invece di ripararlo.
> Vanno letti come storia, non come riferimenti risolvibili.

### Versione 2.0.0 (04 Settembre 2026)
* **Autore:** manutenzione della knowledge base (audit Run B/S5)
* **File Modificati:**
  * `docs/00_meta_governance/glossario_entita.md` — **rimosso dal corpus**
  * `docs/00_meta_governance/matrice_permessi.md` — **rimosso dal corpus**
  * `docs/04_knowledge_informative/intent_synonym_mapping.md` — **rimosso dal corpus**
  * `docs/00_meta_governance/change_log.md`
* **Descrizione Modifiche:** Dismissione del dominio applicativo originale dalla
  knowledge base. I tre documenti sopra — 21 chunk su 181, l'11% dell'indice — descrivevano
  entità che non esistono più e competevano in ogni retrieval; sono stati spostati in
  `docs.local-backup-20260901T121519/` (non cancellati: non erano tracciati da git). Le
  specifiche funzionali di quel dominio elencate nella 1.1.0 erano già uscite dal corpus
  in precedenza. In questo file: `project:` riportato alla convenzione `cross-project`,
  rimossi dal frontmatter i 12 archi `CONTIENE` verso node_id che non risolvono più
  (materializzavano altrettanti nodi fantasma nel grafo con `reliability: 0.9`), e ripulite
  dal vocabolario del dominio dismesso §1 e [REGOLA-DEV-02]. **Bump major** perché è una
  riscrittura del perimetro dei vincoli, non una correzione di forma.

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
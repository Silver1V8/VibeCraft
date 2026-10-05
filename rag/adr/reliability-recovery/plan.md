# Reliability and Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Il coordinatore integra e committa; i worker non modificano git.

**Goal:** Implementare le prime tre migliorie approvate e consegnare report e push su main.
**Architecture:** Errori operativi nel punto comune del retrieval; gate con politica di errore coerente con blocking; bozze frontend isolate sovrapposte ai file server esistenti.
**Tech Stack:** Python/FastAPI/pytest e JavaScript/browser storage/Node già presenti.
**Spec:** design.md

## Global Constraints

- Nessuna nuova dipendenza e nessun refactor estraneo.
- Conservare isolamento dei progetti, controllo dei path, autenticazione, CSP e gate agentic.
- Non salvare chiavi API né stato di autorizzazione o validazione nelle bozze.
- Preservare le modifiche locali preesistenti. Commit solo dei file di questo intervento.

## Review Focus

- Guasto Qdrant/embedding contro risposta valida con zero risultati.
- Golden YAML corrotto/schema errato contro file realmente assente.
- Storage browser negato, pieno o corrotto: nessuna perdita silenziosa o crash.
- Feature omonime in progetti diversi e risposte asincrone: nessuna contaminazione.
- File server modificati dopo la bozza: non nascondere o sovrascrivere la versione nuova.

### Task 1: Retrieval operativo

**Files:** rag/core/retrieval.py, rag/api/routes_pipeline.py; test in rag/tests/test_retrieval.py e test_pipeline.py (o nuovo test focalizzato).
**Interfaces:** consume select_governed_chunks/retrieve_governed_context; produce errore operativo riconoscibile e HTTP 503 per i consumatori della pipeline.
- [x] Test RED per guasto condiviso e Canvas/Propose senza chiamata LLM o sovrascrittura.
- [x] Correzione minima nel core e nei consumatori effettivi, preservando zero risultati valido.
- [x] Test GREEN e regressioni retrieval/pipeline.
- [x] Review PM del diff.

### Task 2: Eval gate rigoroso

**Files:** rag/core/eval_gate.py e rag/tests/test_eval_gate.py (eventuali test indexing focalizzati).
**Interfaces:** consume blocking/enabled/golden cases; produce passed=false su errore di gate blocking e diagnostica separata assente/invalido.
- [x] Test RED: golden corrotto/schema errato e errore di valutazione con blocking/advisory; file assente bootstrap.
- [x] Gestire caricamento e valutazione con la stessa politica; non promuovere CURRENT/alias in caso bloccante.
- [x] Test GREEN e regressioni gate/indexing.
- [x] Review indipendente del diff (worker retrieval).

### Task 3: Ripresa della pipeline

**Files:** rag/static/pages/pipeline.js, workspace.js se necessario, rag/templates/pipeline.unified.html; test Node dedicato e gate CI se necessario.
**Interfaces:** consume loadFeatureStatus e file server; produce bozze browser isolate per progetto/feature, ripristino e timestamp accessibile.
- [x] Test RED: refresh/intervista/input, due progetti, file server nuovo, storage fallito/corrotto.
- [x] Riusare caricamento server e DOM corrente; salvare senza autorizzazioni o markup eseguibile.
- [x] Test GREEN e controlli Node/browser esistenti.
- [x] Review indipendente del diff (worker eval gate); due P1 e un P2 risolti e ricontrollati.

### Task 4: Integrazione e consegna

**Files:** README.md, rag/README.md e rag/adr/REPORT_RELIABILITY_RECOVERY_20261005.md.
- [x] Verificare suite completa Python, lint, sintassi e regressioni Node; test browser disponibili. Esito: 2.429 passed, 25 skip ambientali; Node, Edge e Ruff superati.
- [x] Review finale PM e review indipendenti incrociate; rilievi risolti.
- [x] Aggiornare documentazione e report con esiti e limiti effettivi.
- [x] Preparare la consegna Git verificata, preservando le modifiche locali. Commit, integrazione in main e SHA remoto sono riportati nella risposta finale.

---
id: "spec-export-v1.0"
title: "Specifica Normativa — Esportazione Dati"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-13"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_export_3.4.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-export-v1.0"
  scope: "Definizione dei requisiti per l'esportazione dei dati di partecipazione in formato CSV/Excel"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-v1.2"
    - type: "VINCOLA"
      target: "entity::EVENTO"
    - type: "VINCOLA"
      target: "entity::RICHIESTA"
tags:
  - requirements
  - open-spec
  - export
  - csv-export
  - security
---

# Specifica Normativa — Esportazione Dati

---

## 1. Obiettivo e Formato di Esportazione

La presente specifica definisce i requisiti funzionali, le restrizioni di sicurezza e i vincoli di interfaccia applicati al modulo di Esportazione Dati di VibeCraft. Lo scopo di questa capability è permettere agli amministratori HR e ai manager di dipartimento di estrarre report strutturati in formato tabellare (CSV o Excel) contenenti lo storico delle iscrizioni, i tassi di partecipazione agli eventi e i dettagli dei costi associati, facilitando l'analisi offline e i processi di rendicontazione amministrativa.

Ogni singola operazione di esportazione costituisce un evento sensibile dal punto di vista della protezione dei dati e deve essere registrata in modo sincrono all'interno dell' `` `AUDIT_LOG` ``.

---

## 2. Regole di Filtro e Sicurezza (CSV Injection Guard)

### [REGOLA-EXP-01] Sanificazione dell'output contro attacchi CSV Injection
- **Descrizione:** Prima di generare e servire il file di esportazione, il server deve scansionare e sanificare tutti i campi di testo inseriti dagli utenti (es. il campo motivazione della risorsa `` `RICHIESTA` `` o i titoli dell' `` `EVENTO` ``). Se un valore inizia con caratteri di comando dei fogli di calcolo (`=`, `+`, `-`, `@`), il sistema deve forzare l'inserimento di un apice singolo `'` all'inizio della cella per neutralizzare l'esecuzione di formule arbitrarie sul client dell'utente.
- **Effetto in caso di violazione (Failure Mode):** Vulnerabilità a minacce di CSV Injection con potenziale esecuzione di comandi nocivi sul computer dei manager all'apertura del foglio di calcolo.
- **Entità Target:** `` `RICHIESTA` ``, `` `EVENTO` ``

### [REGOLA-EXP-02] Limitazione e compartimentazione dell'esportazione per i Manager
- **Descrizione:** Quando un utente con ruolo 'MANAGER' avvia un'esportazione, il backend deve applicare un filtro di sicurezza implicito basato sull'appartenenza organizzativa. Il file risultante deve contenere esclusivamente i record di `` `RICHIESTA` `` inviati dai dipendenti del medesimo dipartimento del manager. L'esportazione globale e cross-dipartimentale è concessa unicamente agli utenti con ruolo 'ADMIN'.
- **Effetto in caso di violazione (Failure Mode):** Divulgazione indebita di dati sensibili e violazione delle barriere di accesso dipartimentali.
- **Entità Target:** `` `RICHIESTA` ``, `` `UTENTE` ``

---

## 3. Vincoli Operativi e Audit Log

### [REGOLA-AUTH-01] Restrizioni sui ruoli di accesso (RBAC)
- **Descrizione:** L'invocazione degli endpoint API dedicati alla generazione dei file di report (es. `/api/v1/export/*`) è inibita all' `` `UTENTE` `` con ruolo dipendente comune. I controlli d'accesso a livello di API Gateway devono bloccare le richieste non autorizzate restituendo un errore HTTP 403 Forbidden.
- **Effetto in caso di violazione (Failure Mode):** Accesso non controllato di massa ai dati complessivi di partecipazione ed evasione dei vincoli di visibilità.
- **Entità Target:** `` `UTENTE` ``

### [REGOLA-AUDIT-01] Tracciamento dell'esportazione con conteggio record
- **Descrizione:** All'atto del download andato a buon fine, il sistema deve scrivere una riga specifica nell' `` `AUDIT_LOG` `` indicando l'ID dell'utente operatore, la tipologia di report, i parametri di filtro applicati e il numero esatto di record esportati.
- **Effetto in caso di violazione (Failure Mode):** Mancanza di visibilità su potenziali tentativi di massiccia esfoliazione dei dati aziendali.
- **Entità Target:** `` `AUDIT_LOG` ``

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Esportazione Dati Tabellari e Prevenzione Abusi di Sicurezza

```gherkin
SCENARIO: S01 - Esportazione sicura dei dati da parte di un Amministratore HR
  GIVEN un Amministratore HR autenticato sul sistema
  AND sul database sono presenti record RICHIESTA contenenti nel campo note una formula potenziale "=1+2"
  WHEN l'amministratore richiede l'esportazione totale in formato CSV
  THEN il sistema applica la [REGOLA-EXP-01] di sanificazione
  AND trasforma la formula in "'=1+2" all'interno del file generato
  AND serve il file per il download registrando l'operazione di esportazione con il contatore dei record nell' `AUDIT_LOG`
```

```gherkin
SCENARIO: S02 - Blocco di un dipendente che tenta l'esportazione via API
  GIVEN un dipendente UTENTE autenticato con permessi standard
  WHEN invia direttamente una chiamata GET all'endpoint /api/v1/export/events
  THEN il middleware di autenticazione applica la [REGOLA-AUTH-01]
  AND rifiuta la transazione restituendo un codice di stato HTTP 403 Forbidden
  AND inserisce un record di allarme sicurezza nell' `AUDIT_LOG`
```

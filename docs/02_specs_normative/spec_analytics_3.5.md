---
id: "spec-analytics-v1.0"
title: "Specifica Normativa — Analytics e Reporting"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-13"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_analytics_3.5.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-analytics-v1.0"
  scope: "Definizione dei requisiti per la dashboard grafica di analytics, monitoraggio del budget ed efficacia formativa"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-v1.2"
    - type: "VINCOLA"
      target: "entity::BUDGET_ANNUO"
    - type: "VINCOLA"
      target: "entity::EVENTO"
tags:
  - requirements
  - open-spec
  - analytics
  - reporting
  - dashboard-admin
---

# Specifica Normativa — Analytics e Reporting

---

## 1. Obiettivo e Logica della Dashboard di Business Intelligence

La presente specifica definisce i requisiti funzionali, le logiche matematiche di aggregazione e i vincoli di sicurezza applicati al modulo di Analytics e Reporting di VibeCraft. Lo scopo di questa capability è fornire agli amministratori HR e ai manager di dipartimento una plancia grafica interattiva per monitorare l'andamento finanziario complessivo del `` `BUDGET_ANNUO` ``, valutare il tasso di partecipazione ed estrarre metriche sull'efficacia delle iniziative di formazione ed aggregazione aziendale.

Tutte le metriche esposte devono derivare da calcoli consolidati sul database transazionale e devono essere protette da meccanismi rigidi di filtraggio basati sul ruolo (RBAC).

---

## 2. Metriche di Budget e Performance

### [REGOLA-ANL-01] Calcolo aggregato del consumo del budget
- **Descrizione:** Il sistema deve calcolare e mostrare graficamente (tramite diagrammi ad anello o a barre) la ripartizione del `` `BUDGET_ANNUO` `` dipartimentale in tre sotto-stati finanziari dinamici:
  - **Fondi Spesi:** Somma dei costi di tutti gli eventi associati a istanze di `` `RICHIESTA` `` in stato 'APPROVATA' già svoltesi.
  - **Fondi Impegnati:** Somma dei costi stimati per eventi associati a istanze di `` `RICHIESTA` `` in stato 'APPROVATA' o 'IN_ATTESA_APPROVAZIONE' non ancora svoltesi.
  - **Fondi Disponibili:** Differenza aritmetica tra il budget totale allocato e la somma dei fondi spesi e impegnati.
- **Effetto in caso di violazione (Failure Mode):** Esposizione di saldi finanziari errati con rischio di over-spending o mancata programmazione delle risorse.
- **Entità Target:** `` `BUDGET_ANNUO` ``, `` `RICHIESTA` ``

### [REGOLA-ANL-02] Calcolo del tasso di adesione ed efficacia eventi
- **Descrizione:** Per ciascun `` `EVENTO` `` concluso, la dashboard deve calcolare in tempo reale il tasso percentuale di adesione, definito dal rapporto matematico tra la somma dei posti effettivamente occupati (richieste in stato 'APPROVATA') e la capienza massima nominale dichiarata per la risorsa evento.
- **Effetto in caso di violazione (Failure Mode):** Generazione di statistiche di saturazione non attendibili, impedendo un'analisi di ROI corretta sulle iniziative aziendali.
- **Entità Target:** `` `EVENTO` ``, `` `RICHIESTA` ``

---

## 3. Sicurezza ed Anonimizzazione delle Visualizzazioni

### [REGOLA-AUTH-01] Restrizione di accesso per livello di visibilità (RBAC)
- **Descrizione:** L'accesso alle API di aggregazione statistica globale è interdetto all' `` `UTENTE` `` con ruolo dipendente comune. I manager possono visualizzare unicamente i grafici consolidati del proprio dipartimento, mentre la visualizzazione dei KPI aziendali consolidati è ad uso esclusivo del ruolo 'ADMIN'.
- **Effetto in caso di violazione (Failure Mode):** Divulgazione non autorizzata di dati macroeconomici e violazione della separazione dei ruoli aziendali.
- **Entità Target:** `` `UTENTE` ``

### [REGOLA-VAL-01] Anonimizzazione dei dati personali nelle metriche aggregate
- **Descrizione:** Al fine di garantire la conformità con le normative sulla riservatezza delle informazioni, i grafici e i report di performance non devono esporre l'identità dei singoli dipendenti o dati personali diretti. L'interfaccia deve operare esclusivamente su aggregati numerici anonimizzati.
- **Effetto in caso di violazione (Failure Mode):** Violazione della privacy aziendale e del principio di minimizzazione dei dati personali nel reporting.
- **Entità Target:** `` `UTENTE` ``

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Visualizzazione KPI e Protezione dei Dati di Analytics

```gherkin
SCENARIO: S01 - Caricamento corretto dei grafici di budget dipartimentale per un Manager
  GIVEN un MANAGER del dipartimento "Sviluppo" autenticato sulla dashboard di Analytics
  AND il BUDGET_ANNUO del dipartimento è pari a 10.000 euro
  AND vi sono richieste approvate per eventi futuri del valore di 2.000 euro (Fondi Impegnati)
  WHEN il manager accede alla sezione finanziaria del pannello
  THEN il sistema applica la [REGOLA-ANL-01]
  AND renderizza un grafico che mostra Fondi Impegnati pari a 2.000 euro (20%) e Fondi Disponibili pari a 8.000 euro (80%)
  AND non mostra alcun dato identificativo sensibile dei dipendenti iscritti, in conformità con la [REGOLA-VAL-01]
```

```gherkin
SCENARIO: S02 - Blocco tentativo di accesso illegale alle metriche globali
  GIVEN un dipendente UTENTE con permessi standard che tenta di inviare una query all'endpoint /api/v1/analytics/global
  WHEN la chiamata raggiunge il gateway delle rotte protette
  THEN il sistema intercetta l'identità dell'utente ed applica la [REGOLA-AUTH-01]
  AND blocca la richiesta restituendo una risposta HTTP 403 Forbidden
  AND scrive l'evento di intrusione non autorizzata all'interno dell' `AUDIT_LOG`
```

---

id: "spec-det-v1.0"
title: "Specifica Normativa — Dettaglio Evento e Visibilità Budget"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-13"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_det_1.3.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-det-v1.0"
  scope: "Specifica logica per la visualizzazione di dettaglio dell'evento e controllo del budget dipartimentale associato"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-v1.2"
    - type: "VINCOLA"
      target: "entity::EVENTO"
    - type: "VINCOLA"
      target: "entity::BUDGET_ANNUO"
    - type: "VINCOLA"
      target: "entity::RICHIESTA"
tags:

- requirements
- open-spec
- event-detail
- budget-control
- finance-validation

---



# Specifica Normativa — Dettaglio Evento e Visibilità Budget



## VibeCraft — Sistema di Gestione Eventi Aziendali

---



## 1. Obiettivo e Layout della Schermata di Dettaglio

La presente specifica definisce i requisiti funzionali, le logiche di controllo finanziario e i vincoli visivi legati alla schermata di dettaglio di un ``EVENTO`` all'interno di VibeCraft. Lo scopo di questa capability è consentire all' `UTENTE` di approfondire le informazioni logistiche, didattiche e organizzative di un evento selezionato, verificandone il costo unitario e la capienza, e offrendo uno strato di validazione preventiva sull'allocazione dei fondi aziendali legati al ``BUDGET_ANNUO`` dipartimentale prima di sottomettere una nuova ``RICHIESTA``.

Questa vista sostituisce la visualizzazione sintetica della dashboard, fornendo un layout dettagliato in cui vengono raggruppati i dati logistici dell'aula, l'agenda e il costo associato alla singola partecipazione.

---



## 2. Regole di Validazione del Budget e dei Posti



### [REGOLA-VAL-01] Esposizione dei dati descrittivi dell'evento

- **Descrizione:** Al caricamento della schermata, il sistema deve invocare l'endpoint di dettaglio estraendo in tempo reale tutti i campi descrittivi del record ``EVENTO``: titolo, descrizione estesa, data e ora, luogo/aula fisica, capienza massima, costo unitario per partecipante e posti residui.
- **Effetto in caso di violazione (Failure Mode):** Visualizzazione di dati incoerenti, obsoleti o caricamento indefinito (spinner bloccato) che degrada l'esperienza utente.
- **Entità Target:** ``EVENTO``



### [REGOLA-INT-01] Controllo capienza residua ed allocazione finanziaria

- **Descrizione:** Prima di sbloccare l'azione di registrazione, il sistema deve validare contemporaneamente due requisiti vincolanti:
  1. Il contatore dei posti residui dell' ``EVENTO`` deve essere maggiore di zero (conforme a `[REGOLA-DASH-02]`).
  2. Il costo unitario dell'evento deve essere inferiore o uguale al saldo residuo del ``BUDGET_ANNUO`` assegnato al dipartimento di appartenenza dell' `UTENTE` corrente.
- **Effetto in caso di violazione (Failure Mode):** Rischio di iscrizione a eventi con aule già sature o violazione dei tetti di spesa dipartimentali prefissati dall'amministrazione.
- **Entità Target:** ``EVENTO``, ``BUDGET_ANNUO``, ``RICHIESTA``

---



## 3. Vincoli sui Ruoli e Inibizioni Grafiche



### [REGOLA-AUTH-01] Restrizione visualizzazione dati finanziari ed economici

- **Descrizione:** I dati sensibili relativi all'allocazione e al consumo del ``BUDGET_ANNUO`` dipartimentale (fondi totali, fondi impegnati, grafici di andamento economico) sono strettamente riservati. L'interfaccia di dettaglio deve renderizzare questi widget amministrativi esclusivamente se l' `UTENTE` autenticato possiede il ruolo di Manager o Amministratore (RBAC). Al dipendente comune deve essere mostrato esclusivamente il costo unitario dell'evento.
- **Effetto in caso di violazione (Failure Mode):** Fuga di informazioni finanziarie interne e violazione dei principi di visibilità limitata dei dati aziendali.
- **Entità Target:** ``BUDGET_ANNUO``, ``UTENTE``



### [REGOLA-FORM-01] Disattivazione form per superamento limiti economici

- **Descrizione:** Se il costo unitario dell' ``EVENTO`` supera il saldo disponibile del ``BUDGET_ANNUO`` dipartimentale, il pulsante "Invia Richiesta" deve essere disabilitato e deve comparire un messaggio informativo bloccante che invita l' `UTENTE` a contattare il proprio manager per richiedere un'eccezione o un incremento di budget.
- **Effetto in caso di violazione (Failure Mode):** L'utente tenta l'invio della richiesta, la quale viene poi rigettata solo a livello di database, generando un inutile viaggio di rete (RTT) e sovraccaricando il server.
- **Entità Target:** ``EVENTO``, ``BUDGET_ANNUO``

---



## 4. Scenari Comportamentali BDD (Gherkin)



### Capability: Navigazione al Dettaglio e Validazione Preventiva del Budget

```gherkin
Scenario: Caricamento corretto della scheda dettaglio con budget sufficiente
  Dato un UTENTE autenticato del dipartimento "Sviluppo Software" con saldo BUDGET_ANNUO residuo pari a 1500 euro
  E un EVENTO pubblicato denominato "Masterclass Architetture Cloud" con costo unitario di 500 euro e 5 posti disponibili
  Quando l'utente apre la schermata di dettaglio dell'evento
  Allora il sistema mostra correttamente i dati dell'aula e i posti disponibili pari a 5
  E verifica che il costo (500€) sia coperto dal BUDGET_ANNUO (1500€)
  E abilita il pulsante di sottomissione per permettere la creazione della RICHIESTA
```

```gherkin
Scenario: Blocco della sottomissione per budget insufficiente (Over-spending)
  Dato un UTENTE autenticato del dipartimento "Marketing" che possiede un saldo BUDGET_ANNUO residuo pari a 100 euro
  E un EVENTO pubblicato denominato "Corso Advanced Marketing Automations" con costo unitario di 300 euro
  Quando l'utente accede alla pagina di dettaglio del corso
  Allora il sistema applica la [REGOLA-FORM-01]
  E mostra il costo unitario di 300 euro
  E rileva che il costo supera i 100 euro residui del BUDGET_ANNUO dipartimentale
  E disabilita il pulsante "Invia Richiesta" mostrando l'avviso bloccante per fondi esauriti
```


---
id: "spec-notifications-v1.0"
title: "Specifica Normativa — Sistema di Notifiche"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-13"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_notifications_2.4.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-notifications-v1.0"
  scope: "Definizione dei requisiti per il sistema di notifiche asincrone, integrazione email e canali Slack"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-v1.2"
    - type: "VINCOLA"
      target: "entity::NOTIFICA"
    - type: "VINCOLA"
      target: "entity::RICHIESTA"
    - type: "VINCOLA"
      target: "entity::UTENTE"
tags:
  - requirements
  - open-spec
  - notifications
  - slack-integration
  - email-notifications
---

# Specifica Normativa — Sistema di Notifiche
## VibeCraft — Sistema di Gestione Eventi Aziendali

---

## 1. Obiettivo e Architettura del Sistema di Notifica

La presente specifica definisce i requisiti funzionali, le regole di instradamento e i vincoli di sicurezza del modulo di notifica di VibeCraft. Lo scopo di questo sistema è garantire che ogni transizione critica del ciclo di vita di una `` `RICHIESTA` `` o di un `` `EVENTO` `` sia notificata in tempo reale e in modo asincrono ai soggetti interessati (dipendenti e manager), utilizzando canali differenziati (e-mail interne e canali di messaggistica Slack) per massimizzare la reattività operativa del team.

Ogni singola occorrenza di invio deve produrre un record persistente nell'entità `` `NOTIFICA` `` per finalità storiche, oltre a essere debitamente tracciata all'interno dell' `` `AUDIT_LOG` ``.

---

## 2. Regole di Dispacciamento ed Integrazione Canali

### [REGOLA-NOTIF-02] Instradamento asincrono su canali Slack per i Manager
- **Descrizione:** Al momento della sottomissione di una nuova `` `RICHIESTA` `` (passaggio a 'IN_ATTESA_APPROVAZIONE'), il sistema deve inviare una notifica immediata e asincrona sul canale Slack aziendale associato al dipartimento del manager competente. Il messaggio Slack deve contenere il link diretto al pannello di approvazione e non esporre dati sensibili non necessari.
- **Effetto in caso di violazione (Failure Mode):** Il manager non riceve tempestivamente la segnalazione, allungando i tempi di lavorazione ed esponendo le richieste alla scadenza dei termini dell' `` `EVENTO` ``.
- **Entità Target:** `` `NOTIFICA` ``, `` `RICHIESTA` ``

### [REGOLA-NOTIF-03] Invio e-mail transazionali ai dipendenti
- **Descrizione:** Ogni variazione di stato di una `` `RICHIESTA` `` operata da un manager o da un amministratore (approvazione, rifiuto o annullamento logico) deve innescare l'invio sincrono di una e-mail transazionale all'indirizzo e-mail aziendale del dipendente `` `UTENTE` `` destinatario. L'e-mail deve riportare chiaramente lo stato aggiornato e l'eventuale nota motivazionale inserita dall'approvatore.
- **Effetto in caso di violazione (Failure Mode):** Mancata consapevolezza da parte dell'utente dello stato dell'iscrizione, con rischio di assenze ingiustificate o sovrapposizioni.
- **Entità Target:** `` `NOTIFICA` ``, `` `UTENTE` ``

---

## 3. Gestione Code e Tolleranza ai Guasti

### [REGOLA-VAL-01] Accodamento e gestione dei fallimenti di rete
- **Descrizione:** Il sistema di invio delle notifiche deve operare tramite una coda asincrona (Message Queue) esterna al thread principale della transazione di business. In caso di fallimento della chiamata API di Slack o del server SMTP di posta, il modulo deve tentare un massimo di 3 reinvii automatici distanziati da un backoff esponenziale, registrando infine lo stato di fallimento nell'entità `` `NOTIFICA` ``.
- **Effetto in caso di violazione (Failure Mode):** Il blocco o rallentamento dei servizi di notifica esterni si ripercuote sulla latenza percepita dall'utente a schermo, bloccando l'interfaccia.
- **Entità Target:** `` `NOTIFICA` ``

### [REGOLA-INT-01] Consistenza e persistenza dello stato di invio
- **Descrizione:** Ogni tentativo di invio di una e-mail o di un messaggio Slack deve creare un record persistente nell'entità `` `NOTIFICA` `` con stato impostato inizialmente su 'PENDING' e aggiornato successivamente a 'SENT' o 'FAILED'. Il payload originale e gli errori riscontrati devono essere storicizzati.
- **Effetto in caso di violazione (Failure Mode):** Impossibilità di verificare se una determinata comunicazione sia mai stata trasmessa o ricevuta in caso di controversie aziendali.
- **Entità Target:** `` `NOTIFICA` ``

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Invio asincrono delle notifiche e tolleranza ai guasti

```gherkin
Scenario: Invio notifica Slack per nuova richiesta in attesa
  Dato un record RICHIESTA appena sottomesso da un dipendente in stato 'IN_ATTESA_APPROVAZIONE'
  Quando il modulo di notifica intercetta l'evento di sottomissione
  Allora crea un record NOTIFICA in stato 'PENDING' nel database
  E accoda l'operazione di invio del messaggio Slack per il dipartimento associato
  E trasmette il messaggio formattato sul webhook di Slack
  E aggiorna lo stato della NOTIFICA in 'SENT' scrivendo l'operazione nell' `AUDIT_LOG`
```

```gherkin
Scenario: Gestione e tracciamento del fallimento dell'invio e-mail
  Dato un manager che ha appena approvato una RICHIESTA sul pannello di controllo
  Quando il server di posta SMTP aziendale risulta offline al momento dell'invio dell'e-mail
  Allora l'accodatore esegue i 3 tentativi di reinvio pianificati dalla [REGOLA-VAL-01]
  E al fallimento definitivo imposta lo stato della NOTIFICA su 'FAILED'
  E inserisce un record di errore dettagliato nel database delle notifiche
  E genera un log di anomalia di severità 'WARNING' all'interno dell' `AUDIT_LOG`
```
```
---
id: "spec-crud-admin-v1.0"
title: "Specifica Normativa — Amministrazione Eventi (CRUD Admin HR)"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-13"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_crud_admin_3.2.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-crud-admin-v1.0"
  scope: "Definizione dei requisiti operativi per la creazione, modifica, cancellazione e pubblicazione degli eventi da parte degli amministratori HR"
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
  - admin-panel
  - crud-events
  - hr-administration
---

# Specifica Normativa — Amministrazione Eventi (CRUD Admin HR)

---

## 1. Obiettivo e Privilegi Amministrativi

La presente specifica definisce i requisiti funzionali, le regole di validazione dei dati e i vincoli di sicurezza legati al modulo di amministrazione eventi (Pannello Admin HR) di VibeCraft. Lo scopo di questo modulo è consentire esclusivamente agli operatori delle Risorse Umane (HR) con privilegi di amministrazione di gestire l'intero ciclo di vita dell'entità `` `EVENTO` ``. La specifica norma in maniera deterministica la creazione, la modifica editoriale, la pubblicazione formale e l'eventuale rimozione delle iniziative formative e di aggregazione dell'azienda.

Al fine di tutelare l'integrità del database, tutti i flussi amministrativi devono essere protetti da un controllo rigido dei ruoli a livello di backend (RBAC) e devono scrivere dettagliatamente ogni mutazione strutturale all'interno dell' `` `AUDIT_LOG` ``.

---

## 2. Ciclo di Vita dell'Evento e Validazione dei Campi

### [REGOLA-CRUD-01] Creazione nativa in stato di Bozza
- **Descrizione:** Qualsiasi operazione di inserimento di un nuovo record dell'entità `` `EVENTO` `` sul database (fase di `INSERT`) deve registrare la risorsa inizialmente ed esclusivamente in stato 'BOZZA'. L'evento in stato di bozza è invisibile all' `` `UTENTE` `` comune nella dashboard e non permette la sottomissione di istanze di `` `RICHIESTA` ``.
- **Effetto in caso di violazione (Failure Mode):** Errore di inizializzazione dello stato, blocco della persistenza e rigetto del payload.
- **Entità Target:** `` `EVENTO` ``

### [REGOLA-CRUD-02] Validazione dei campi obbligatori all'atto della pubblicazione
- **Descrizione:** Il passaggio di un `` `EVENTO` `` dallo stato 'BOZZA' allo stato 'PUBBLICATO' è subordinato al superamento dei seguenti controlli di consistenza:
  - Presenza di un titolo descrittivo (minimo 10, massimo 100 caratteri).
  - Presenza di una data e ora di inizio valida (nel futuro rispetto alla data del server).
  - Presenza di un'aula fisica o locazione stabilita.
  - Capienza massima specificata (valore intero maggiore o uguale a 5).
  - Costo unitario per partecipante valorizzato (maggiore o uguale a zero).
- **Effetto in caso di violazione (Failure Mode):** Rifiuto del cambio di stato sul database e notifica a schermo degli errori sintattici.
- **Entità Target:** `` `EVENTO` ``

---

## 3. Rimozione ed Annullamento Logico di Massa

### [REGOLA-CRUD-03] Eliminazione fisica limitata allo stato di Bozza
- **Descrizione:** L'eliminazione fisica (`DELETE` permanente a livello SQL) di una riga della risorsa `` `EVENTO` `` dal database è permessa se e solo se la risorsa si trova ancora in stato 'BOZZA' e non possiede alcuna istanza di `` `RICHIESTA` `` associata o agganciata nel database relazionale.
- **Effetto in caso di violazione (Failure Mode):** Eccezione di integrità referenziale o violazione di vincoli, interruzione immediata dell'operazione di rimozione.
- **Entità Target:** `` `EVENTO` ``

### [REGOLA-CRUD-04] Annullamento logico e notifica a cascata delle iscrizioni
- **Descrizione:** Qualora un `` `EVENTO` `` già in stato 'PUBBLICATO' debba essere cancellato, l'amministratore non può ricorrere all'eliminazione fisica dei record. Il sistema deve applicare un annullamento logico, impostando lo stato dell'evento su 'ANNULLATO'. Questa transizione deve innescare automaticamente un blocco transazionale a cascata che imposta su 'ANNULLATA' tutte le istanze di `` `RICHIESTA` `` associate (sottomesse o già approvate) e invia una `` `NOTIFICA` `` asincrona di avviso a tutti i dipendenti impattati.
- **Effetto in caso di violazione (Failure Mode):** Mancata rimozione logica delle richieste associate, con conseguente mantenimento dei posti prenotati o del budget impegnato per eventi inesistenti.
- **Entità Target:** `` `EVENTO` ``, `` `RICHIESTA` ``, `` `NOTIFICA` ``

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Amministrazione degli Eventi e Annullamento a Cascata

```gherkin
SCENARIO: S01 - Creazione di un nuovo evento in bozza con successo
  GIVEN un Amministratore HR autenticato sul pannello di controllo
  WHEN inserisce i dati preliminari di un nuovo EVENTO e clicca su "Salva come Bozza"
  THEN il sistema applica la [REGOLA-CRUD-01]
  AND crea il record sul database impostando lo stato iniziale su 'BOZZA'
  AND non rende visibile questo evento all'UTENTE comune all'interno della dashboard principale
```

```gherkin
SCENARIO: S02 - Pubblicazione fallita per mancanza dei campi minimi obbligatori
  GIVEN un EVENTO esistente sul database in stato 'BOZZA' privo di indicazione sulla capienza massima
  WHEN l'Amministratore HR tenta di cambiare lo stato dell'evento in 'PUBBLICATO'
  THEN il sistema intercetta l'anomalia sintattica applicando la [REGOLA-CRUD-02]
  AND rifiuta l'aggiornamento sul database emettendo l'eccezione CAMPI_MINIMI_MANCANTI
  AND segnala all'amministratore che la capienza deve essere valorizzata per procedere
```

```gherkin
SCENARIO: S03 - Annullamento logico di un evento pubblicato con richieste collegate
  GIVEN un EVENTO in stato 'PUBBLICATO' con 3 richieste RICHIESTA in stato 'APPROVATA' associate
  WHEN l'Amministratore HR esegue l'azione di annullamento dell'evento
  THEN il sistema esegue l'annullamento logico applicando la [REGOLA-CRUD-04]
  AND imposta lo stato dell'EVENTO su 'ANNULLATO'
  AND aggiorna in automatico tutte e 3 le istanze di RICHIESTA nello stato 'ANNULLATA'
  AND riallinea i saldi del BUDGET_ANNUO dei rispettivi dipartimenti
  AND genera un log dettagliato dell'operazione all'interno dell' `AUDIT_LOG`
```

---
id: "spec-dash-v1.0"
title: "Specifica Normativa — Dashboard Utente e Card Eventi"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-12"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_dash_1.2.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-dash-v1.0"
  scope: "Specifica dell'interfaccia visiva principale della dashboard e del calcolo dei posti"
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
  - frontend
  - dashboard
  - ui-components
---

# Specifica Normativa — Dashboard Utente e Card Eventi
## VibeCraft — Sistema di Gestione Eventi Aziendali

---

## 1. Obiettivo e Layout della Plancia Visiva

La presente specifica definisce i requisiti funzionali obbligatori, i vincoli grafici e le logiche di rendering della Dashboard principale dedicata all' `UTENTE` comune di VibeCraft. Lo scopo di questo modulo è fornire una panoramica immediata e intuitiva di tutti gli eventi aziendali disponibili, consentendo al dipendente di monitorare la capienza delle aule e lo stato delle proprie interazioni in modo trasparente, riducendo al minimo il rumore visivo ed evitando disallineamenti informativi tra il client e lo stato effettivo del backend server-side.

L'interfaccia si articola in una griglia flessibile di componenti visuali denominati "Card Evento". Ciascuna card costituisce un blocco atomico che rappresenta un singolo record dell'entità `EVENTO` estratto in tempo reale dal database transazionale.

---

## 2. Regole di Visibilità e Calcolo Dinamico dei Posti

### [REGOLA-DASH-01] Visibilità selettiva degli eventi in bacheca
- **Descrizione:** La griglia della dashboard deve mostrare esclusivamente i record dell'entità `EVENTO` che si trovano in uno stato attivo, pubblicato e la cui data di svolgimento sia successiva o uguale alla data corrente del sistema. Record in stato di bozza amministrativa non devono mai essere trasmessi o renderizzati nel client.
- **Effetto in caso di violazione (Failure Mode):** Visualizzazione indebita di eventi confidenziali o obsoleti da parte del personale non autorizzato.
- **Entità Target:** `EVENTO`

### [REGOLA-DASH-02] Calcolo Real-time dei posti residui della card
- **Descrizione:** Ciascuna Card Evento deve mostrare in modo prominente il contatore dei posti ancora disponibili. Questo valore deve essere calcolato dinamicamente eseguendo la differenza aritmetica tra la capienza massima stabilita per l' `EVENTO` e la somma logica di tutte le istanze di `RICHIESTA` collegate a quel medesimo evento che si trovano nello stato 'APPROVATA'.
- **Effetto in caso di violazione (Failure Mode):** Disallineamento visivo tra l'interfaccia utente e i vincoli di capienza del database, con conseguente frustrazione dell'utente.
- **Entità Target:** `EVENTO`, `RICHIESTA`

---

## 3. Validazioni dell'Interfaccia e Inibizioni di Input

### [REGOLA-FORM-01] Inibizione del pulsante di sottomissione per esaurimento posti
- **Descrizione:** Quando il calcolo dinamico dei posti residui descritto nella [REGOLA-DASH-02] restituisce un valore pari a zero, l'interfaccia grafica della Card Evento deve mutare stato visivo: il pulsante di sottomissione "Partecipa" deve essere disabilitato (stato HTML `disabled`) e deve comparire un badge testuale rosso recante la dicitura "Sold Out".
- **Effetto in caso di violazione (Failure Mode):** L'utente invia richieste per aule già sature, sovraccaricando il backend e generando eccezioni transazionali bloccanti evitabili a livello client.
- **Entità Target:** `EVENTO`, `RICHIESTA`

### [REGOLA-FORM-02] Rilevamento sottomissioni duplicate
- **Descrizione:** Se l' `UTENTE` correntemente autenticato possiede già un record `RICHIESTA` associato a quel determinato `EVENTO` in stato 'IN_ATTESA_APPROVAZIONE' o 'APPROVATA', la card deve bloccare ulteriori interazioni, disabilitando il pulsante e mostrando lo stato attuale della richiesta ("In Attesa" o "Iscritto").
- **Effetto in caso di violazione (Failure Mode):** Generazione di iscrizioni multiple sovrapposte per lo stesso dipendente allo stesso evento, violando i vincoli di unicità del database.
- **Entità Target:** `RICHIESTA`, `UTENTE`

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Rendering della Dashboard ed Inibizione Controlli UI

```gherkin
Scenario: Rendering corretto della card con calcolo dei posti disponibili
  Dato un UTENTE autenticato posizionato sulla pagina principale della dashboard
  E un EVENTO pubblicato che possiede una capienza massima di 50 posti
  E sul database risultano registrate 10 istanze di RICHIESTA in stato 'APPROVATA' per questo evento
  Quando la pagina esegue il caricamento dei componenti grafici
  Allora la Card Evento visualizza un contatore di posti residui pari esattamente a 40
  E il pulsante "Partecipa" risulta attivo e cliccabile dal dipendente
```

```gherkin
Scenario: Disattivazione controlli della card in caso di Sold Out
  Dato un UTENTE autenticato posizionato sulla pagina della dashboard
  E un EVENTO pubblicato che possiede una capienza di 30 posti
  E sul database risultano registrate 30 istanze di RICHIESTA in stato 'APPROVATA' per questo evento
  Quando la card viene renderizzata sullo schermo dell'utente
  Allora il sistema applica la [REGOLA-FORM-01]
  E il contatore dei posti residui mostra il valore 0
  E compare il badge visivo con la dicitura "Sold Out"
  E il pulsante "Partecipa" viene disabilitato impedendo l'invio di payload al server
```
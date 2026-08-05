---
id: "spec-form-v1.0"
title: "Specifica Normativa — Form di Sottomissione Richieste"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-13"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_form_1.4.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-form-v1.0"
  scope: "Definizione dei requisiti di validazione e comportamento del form per l'invio di una richiesta"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-v1.2"
    - type: "VINCOLA"
      target: "entity::RICHIESTA"
    - type: "VINCOLA"
      target: "entity::UTENTE"
tags:
  - requirements
  - open-spec
  - form-validation
  - input-control
  - duplicate-prevention
---

# Specifica Normativa — Form di Sottomissione Richieste

---

## 1. Obiettivo e Logica del Form di Sottomissione

La presente specifica definisce i requisiti funzionali, le regole di validazione sintattica dei dati e i vincoli di interfaccia grafica applicati al modulo (form) di sottomissione di una nuova `` `RICHIESTA` `` di partecipazione a un determinato `` `EVENTO` ``. Lo scopo di questo modulo è garantire che i dati inseriti dall' `` `UTENTE` `` siano coerenti e puliti prima di avviare il transito di rete, prevenendo l'inserimento di testi troppo lunghi o formati non validi, e inibendo comportamenti concorrenti errati dell'interfaccia utente (UI).

Questo form rappresenta la porta d'ingresso interattiva per l'iscrizione, accessibile sia dalla card della dashboard sia dalla scheda di dettaglio, e deve agire in sinergia con i controlli transazionali del backend.

---

## 2. Campi Obbligatori e Validazioni Sintattiche

### [REGOLA-FORM-01] Presenza dei campi obbligatori
- **Descrizione:** Il form di sottomissione deve catturare ed inviare in modo strutturato l'identificativo univoco dell' `` `EVENTO` `` selezionato, l'identificativo dell' `` `UTENTE` `` richiedente e il campo opzionale relativo alle note/motivazioni per l'approvatore.
- **Effetto in caso di violazione (Failure Mode):** Il form evidenzia i campi mancanti in rosso, blocca l'azione di invio e impedisce la chiamata API al server.
- **Entità Target:** `` `RICHIESTA` ``

### [REGOLA-VAL-01] Limite di caratteri del campo motivazione
- **Descrizione:** Il campo di testo dedicato alla motivazione della richiesta non deve superare la lunghezza massima assoluta di 500 caratteri. Il sistema deve mostrare in tempo reale un contatore decrementale dei caratteri residui al di sotto della casella di input.
- **Effetto in caso di violazione (Failure Mode):** Al superamento del limite, la casella si evidenzia con un bordo rosso, compare il messaggio di errore "Limite superato" e il pulsante "Invia" viene disabilitato.
- **Entità Target:** `` `RICHIESTA` ``

---

## 3. Gestione dell'Input e Prevenzione dei Duplicati

### [REGOLA-VAL-02] Disattivazione anti-click del pulsante di invio
- **Descrizione:** All'istante esatto del click sul pulsante "Invia", l'interfaccia grafica del client deve disabilitare il controllo (stato HTML `disabled`), sostituire il testo del pulsante con uno spinner visivo di caricamento e mantenerlo bloccato per tutta la durata del ciclo di chiamata di rete (Round Trip Time).
- **Effetto in caso di violazione (Failure Mode):** L'utente può premere ripetutamente il pulsante prima che la chiamata si concluda, generando sottomissioni parallele identiche e sollevando eccezioni di database per record duplicati della risorsa `` `RICHIESTA` ``.
- **Entità Target:** `` `RICHIESTA` ``

### [REGOLA-INT-01] Validazione di idoneità preventiva dell'utente
- **Descrizione:** Prima di visualizzare il form, il client deve effettuare una verifica asincrona silenziosa per accertarsi che l' `` `UTENTE` `` corrente non abbia già una `` `RICHIESTA` `` attiva per lo stesso `` `EVENTO` `` in stato 'IN_ATTESA_APPROVAZIONE' o 'APPROVATA'.
- **Effetto in caso di violazione (Failure Mode):** Mancata inibizione del form, con conseguente esposizione dell'utente a inutili tentativi di iscrizione per eventi a cui risulta già prenotato.
- **Entità Target:** `` `UTENTE` ``, `` `RICHIESTA` ``

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Validazione Form e Prevenzione Doppio Invio

```gherkin
SCENARIO: S01 - Compilazione ed invio valido del form di richiesta
  GIVEN un UTENTE autenticato posizionato sul form di sottomissione di un EVENTO attivo
  WHEN l'utente inserisce una motivazione di 120 caratteri e clicca su "Invia"
  THEN il sistema valida la conformità con la [REGOLA-FORM-01] e la [REGOLA-VAL-01]
  AND disabilita immediatamente il pulsante "Invia" applicando la [REGOLA-VAL-02]
  AND inoltra con successo il payload JSON al backend per la creazione della RICHIESTA
```

```gherkin
SCENARIO: S02 - Blocco invio form per superamento limite caratteri motivazione
  GIVEN un UTENTE autenticato posizionato sul form di sottomissione
  WHEN l'utente inserisce una motivazione di 550 caratteri nella casella di testo
  THEN il sistema applica in tempo reale la [REGOLA-VAL-01]
  AND mostra il contatore dei caratteri in rosso con valore negativo "-50"
  AND visualizza il messaggio informativo "La motivazione non può superare i 500 caratteri"
  AND disabilita il pulsante "Invia" impedendo la trasmissione dei dati
```

```gherkin
SCENARIO: S03 - Inibizione del form per utente già iscritto all'evento
  GIVEN un UTENTE che possiede già una RICHIESTA in stato 'APPROVATA' per un EVENTO specifico
  WHEN l'utente naviga nuovamente sulla pagina di quell'evento
  THEN il sistema intercetta lo stato mediante la [REGOLA-INT-01]
  AND sostituisce il form di sottomissione con un badge informativo verde recante la dicitura "Sei già iscritto a questo evento"
```

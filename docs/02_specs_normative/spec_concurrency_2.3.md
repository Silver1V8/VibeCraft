---
id: "spec-concurrency-v1.0"
title: "Specifica Normativa — Gestione della Concorrenza e Lock Transazionali"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-12"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_concurrency_2.3.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-concurrency-v1.0"
  scope: "Definizione dei vincoli di concorrenza, lock pessimistici e isolamento transazionale"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-v1.2"
    - type: "VINCOLA"
      target: "entity::RICHIESTA"
    - type: "VINCOLA"
      target: "entity::EVENTO"
tags:
  - requirements
  - open-spec
  - concurrency
  - lock-pessimistic
  - transactional-integrity
---

# Specifica Normativa — Gestione della Concorrenza e Lock Transazionali

## VibeCraft — Sistema di Gestione Eventi Aziendali

***

## 1. Obiettivo e Contesto di Isolamento

La presente specifica definisce i requisiti tecnici obbligatori e i vincoli di isolamento transazionale per la gestione degli accessi concorrenti alle risorse sul database di VibeCraft. All'interno di un sistema enterprise *local-first*, la gestione dei conflitti di scrittura concorrente è un pilastro critico: scenari in cui molteplici manager elaborano simultaneamente transizioni sullo stesso `EVENTO`, o dipendenti inviano iscrizioni sovrapposte, devono essere risolti in modo deterministico a livello server-side per impedire la corruzione dei dati e il superamento dei posti fisici o del budget allocato.

Al fine di garantire l'integrità assoluta dei contatori, il database deve operare applicando un livello di isolamento minimo pari a `READ COMMITTED` accoppiato a strategie di lock pessimistico esplicito sulle righe contese durante le operazioni di transizione di stato critiche.

***

## 2. Regole di Lock e Protezione dal Double-Booking

### [REGOLA-CONC-01] Lock Pessimistico sulla risorsa Evento

* **Descrizione:** Ogni procedura software che avvia il flusso di approvazione di una `RICHIESTA` (transazione da 'IN_ATTESA_APPROVAZIONE' a 'APPROVATA') deve tassativamente acquisire un lock pessimistico in scrittura sulla riga della risorsa `EVENTO` associata prima di effettuare il controllo dei posti residui. In ambiente SQL, questo vincolo si traduce nell'esecuzione preventiva di una query di selezione configurata con la clausola `FOR UPDATE`.
* **Effetto in caso di violazione (Failure Mode):** Rischio di race condition con conseguente fenomeno di double-booking (sovra-allocazione dei posti oltre la capienza nominale stabilita dall'azienda).
* **Entità Target:** `EVENTO`

### [REGOLA-CONC-02] Rilascio atomico dei lock e Rollback

* **Descrizione:** L'acquisizione del lock esplicito sulla risorsa `EVENTO` e l'aggiornamento dello stato della risorsa `RICHIESTA` devono essere eseguiti all'interno del medesimo blocco transazionale atomico. Qualsiasi anomalia applicativa, timeout o fallimento logico durante l'elaborazione deve innescare un'operazione immediata di `ROLLBACK` globale, garantendo il rilascio istantaneo di tutte le righe bloccate.
* **Effetto in caso di violazione (Failure Mode):** Generazione di situazioni di deadlock persistenti sul database, con conseguente blocco indefinito dei thread del server web.
* **Entità Target:** `EVENTO`, `RICHIESTA`

***

## 3. Vincoli sui Contatori e Integrità cross-entità

### [REGOLA-INT-01] Sincronizzazione decremento posti residui

* **Descrizione:** Nel momento esatto in cui una `RICHIESTA` transiziona validamente nello stato 'APPROVATA', la transazione deve contestualmente decrementare di un'unità il contatore dei posti disponibili all'interno della riga dell' `EVENTO` target. Il sistema deve validare che il valore risultante non sia mai inferiore a zero.
* **Effetto in caso di violazione (Failure Mode):** Disallineamento numerico tra i posti dichiarati nella dashboard e i record effettivi delle partecipazioni approvate.
* **Entità Target:** `EVENTO`, `RICHIESTA`

### [REGOLA-VAL-01] Validazione capienza massima sotto lock

* **Descrizione:** Il controllo della disponibilità dei posti per un `EVENTO` deve essere effettuato esclusivamente *dopo* che il thread corrente ha acquisito con successo il lock `FOR UPDATE` sulla riga. Controlli eseguiti su letture libere o snapshot non protetti sono considerati non conformi e non sicuri.
* **Effetto in caso di violazione (Failure Mode):** Approvazioni multiple parallele che bypassano il limite di capienza massima a causa di letture sporche o obsolete.
* **Entità Target:** `EVENTO`

***

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Gestione delle Scritture Concorrenti e Lock Transazionali

```gherkin
Scenario: Approvazione concorrente protetta da lock pessimistico (Successo)
  Dato un EVENTO con 1 solo posto residuo disponibile nel database
  E due diverse richieste RICHIESTA_A e RICHIESTA_B in stato 'IN_ATTESA_APPROVAZIONE' legate a questo evento
  Quando due manager diversi tentano di approvare simultaneamente le due richieste
  Allora il sistema assegna il lock FOR UPDATE sulla riga dell'EVENTO al primo thread che raggiunge il database
  E il secondo thread viene messo in coda di attesa bloccante sul lock
  E il primo thread valida la capienza, imposta la RICHIESTA_A su 'APPROVATA' e decrementa i posti disponibili a 0
  E il primo thread effettua il COMMIT rilasciando la risorsa
  E il secondo thread si sveglia, acquisisce il lock, rilegge il contatore dei posti che ora risulta pari a 0
  E interrompe l'elaborazione respingendo l'approvazione della RICHIESTA_B con errore di capienza esaurita
```

```gherkin
Scenario: Rilascio automatico delle risorse in caso di crash applicativo (Rollback)
  Dato un thread server che ha acquisito validamente un lock FOR UPDATE sulla riga di un EVENTO
  Quando si verifica un timeout di rete o un crash imprevisto della business logic prima del completamento
  Allora il gestore delle transizioni intercetta il fallimento ed esegue un ROLLBACK automatico
  E lo stato della RICHIESTA e dell'EVENTO rimangono inalterati rispetto all'inizio
  E la riga dell'EVENTO viene immediatamente sbloccata e resa disponibile per gli altri thread concorrenti
```
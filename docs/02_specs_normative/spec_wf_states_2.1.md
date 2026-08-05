---
id: "spec-wf-states-v1.0"
title: "Specifica Normativa — Macchina a Stati del Workflow Richieste"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-12"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_wf_states_2.1.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-wf-states-v1.0"
  scope: "Specifica logica della macchina a stati finiti della richiesta di partecipazione"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-v1.2"
    - type: "VINCOLA"
      target: "entity::RICHIESTA"
tags:
  - requirements
  - open-spec
  - workflow
  - state-machine
---

# Specifica Normativa — Macchina a Stati del Workflow Richieste

---

## 1. Obiettivo e Stati Ammissibili

La presente specifica definisce i requisiti funzionali rigidi e i vincoli transazionali legati alla macchina a stati finiti che governa il ciclo di vita della risorsa `RICHIESTA`. Lo scopo di questo modulo è impedire transizioni arbitrarie o non autorizzate, garantendo che ogni passaggio di stato avvenga in modo deterministico e tracciato, preservando la consistenza tra le azioni dei dipendenti, l'approvazione dei manager e i posti disponibili per un `EVENTO`.

La risorsa `RICHIESTA` può assumere esclusivamente uno dei seguenti stati canonici:
- `BOZZA`: La richiesta è in fase di compilazione da parte del dipendente e non è visibile ai manager.
- `IN_ATTESA_APPROVAZIONE`: La richiesta è stata sottomessa ufficialmente ed è inserita nella coda del manager competente.
- `APPROVATA`: Il manager ha validato la richiesta, consolidando il posto e allocando il budget associato.
- `RIFIUTATA`: Il manager ha respinto la richiesta inserendo una motivazione testuale obbligatoria.
- `ANNULLATA`: L'utente o un amministratore ha revocato la richiesta prima dello svolgimento dell'evento.

---

## 2. Regole di Transizione e Workflow

### [REGOLA-WF-01] Stato Iniziale Nativo
- **Descrizione:** Al momento della sua creazione sul database (operazione di `INSERT`), una `RICHIESTA` deve assumere tassativamente ed esclusivamente lo stato iniziale 'BOZZA' o lo stato 'IN_ATTESA_APPROVAZIONE' se sottomessa direttamente senza salvataggio preliminare.
- **Effetto in caso di violazione (Failure Mode):** Il sistema blocca la persistenza server-side sollevando un'eccezione di validazione dello stato iniziale e rifiuta il commit sul database.
- **Entità Target:** `RICHIESTA`

### [REGOLA-WF-02] Transizioni di Stato Ammissibili
- **Descrizione:** Il modulo di business logic deve consentire esclusivamente i seguenti passaggi di stato direzionali:
  - Da 'BOZZA' verso 'IN_ATTESA_APPROVAZIONE' (sottomissione) o verso 'ANNULLATA' (cancellazione autonoma).
  - Da 'IN_ATTESA_APPROVAZIONE' verso 'APPROVATA' (approvazione manager) o verso 'RIFIUTATA' (rifiuto manager).
  - Da 'APPROVATA' verso 'ANNULLATA' (revoca del dipendente), a condizione stringente che manchino più di 5 days solari all'inizio dell'oggetto `EVENTO` associato.
- **Effetto in caso di violazione (Failure Mode):** Qualsiasi tentativo di forzare transizioni non censite produce un errore bloccante di tipo `INVALID_STATE_TRANSITION` e innesca il rollback transazionale.
- **Entità Target:** `RICHIESTA`

---

## 3. Validazioni e Vincoli di Integrità Transazionale

### [REGOLA-VAL-01] Blocco delle transizioni illegali
- **Descrizione:** Qualsiasi tentativo di bypassare la sequenza logica del flusso (ad esempio, il passaggio diretto dallo stato 'BOZZA' allo stato 'APPROVATA' o dallo stato 'BOZZA' allo stato 'RIFIUTATA' senza la transizione intermedia) deve essere intercettato e bloccato a livello di controller server-side.
- **Effetto in caso di violazione (Failure Mode):** Errore di violazione dei vincoli di sequenza, interruzione immediata dell'operazione e nessuna modifica apportata allo stato della persistenza.
- **Entità Target:** `RICHIESTA`

### [REGOLA-INT-01] Immutabilità post-rifiuto
- **Descrizione:** Lo stato 'RIFIUTATA' costituisce un nodo foglia terminale definitivo all'interno del grafo delle transizioni della risorsa `RICHIESTA`. Nessun attore (incluso l' `UTENTE` proprietario o il manager) e nessuna procedura automatica può modificare ulteriormente lo stato di un record rifiutato o riportarlo in lavorazione.
- **Effetto in caso di violazione (Failure Mode):** Sollevamento dell'eccezione di immutabilità del record storico e rigetto immediato della scrittura sul database.
- **Entità Target:** `RICHIESTA`

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Validazione e Avanzamento del Workflow Richieste

```gherkin
SCENARIO: S01 - Sottomissione valida di una richiesta da Bozza a In Attesa
  GIVEN un record RICHIESTA esistente sul database in stato 'BOZZA'
  AND un UTENTE autenticato che risulta essere il legittimo proprietario del record
  WHEN l'utente invoca l'endpoint di sottomissione del workflow
  THEN il sistema verifica la conformità con la [REGOLA-WF-02]
  AND aggiorna lo stato della RICHIESTA in 'IN_ATTESA_APPROVAZIONE'
  AND inserisce un record di tracciamento immutabile nel database dell' `AUDIT_LOG`
  AND invia una notifica asincrona al manager competente
```

```gherkin
SCENARIO: S02 - Blocco transizione illegale diretta da Bozza ad Approvata
  GIVEN un record RICHIESTA esistente sul database in stato 'BOZZA'
  WHEN un malintenzionato tenta di bypassare i controlli inviando un payload con stato 'APPROVATA'
  THEN il sistema intercetta la violazione mediante la [REGOLA-VAL-01]
  AND interrompe immediatamente l'elaborazione effettuando il rollback
  AND restituisce un codice di errore HTTP 422 Unprocessable Entity
  AND non apporta alcuna modifica allo stato originario sul database
```

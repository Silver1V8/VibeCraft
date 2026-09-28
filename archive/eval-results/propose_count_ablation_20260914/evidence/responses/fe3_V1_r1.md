# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Obiettivo della Feature

La presente specifica definisce il comportamento osservabile del modulo `BookingRequestForm` per la compilazione e sottomissione delle richieste di partecipazione a un evento (`EVENTO`). Il modulo è implementato come componente Client che interagisce con i metadati forniti da un Server Component. Lo scopo è garantire l'inserimento corretto della **motivazione** e delle **preferenze** (es. alloggio), validare i dati lato client prima dell'invio e gestire lo stato di caricamento per prevenire duplicazioni accidentali.

---

## 2. Scenari Comportamentali BDD (Gherkin)

```gherkin
SCENARIO: S01 - Invio form con dati completi e validi
  GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione contenente 150 caratteri
  AND seleziona la preferenza "Necessità alloggio" tramite checkbox
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema valida lo schema Zod e invia la richiesta al backend
  AND disabilita il pulsante visualizzando uno stato di caricamento
```

```gherkin
SCENARIO: S02 - Inibizione invio per motivazione vuota
  GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
  WHEN l'utente clicca sul pulsante "Partecipa" senza aver inserito nulla nella casella motivazione
  THEN il sistema evidenzia la casella in rosso come campo obbligatorio mancante
  AND disabilita visivamente il pulsante "Partecipa" impedendo l'invio del payload
```

```gherkin
SCENARIO: S03 - Gestione superamento limite caratteri motivazione
  GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione contenente 510 caratteri
  THEN il sistema evidenzia la casella in rosso con messaggio "Limite superato"
  AND disabilita il pulsante "Partecipa" bloccando la sottomissione
```

```gherkin
SCENARIO: S04 - Gestione errore di rete durante la sottomissione
  GIVEN un utente autenticato ha compilato correttamente il form e clicca su "Partecipa"
  WHEN il backend restituisce un errore HTTP 500 o un timeout durante l'elaborazione
  THEN il sistema visualizza un messaggio Toast di errore generato da sonner
  AND riabilita i controlli del form permettendo all'utente di correggere e riprovare
```

---

## 3. Punti Aperti

| Funzionalità Coinvolta | Assunzione Proposta DA CONFERMARE | Domanda Aperta |
| :--- | :--- | :--- |
| Gestione Preferenze (Alloggio) | Si presume che la selezione della checkbox "Necessità alloggio" sia l'unica preferenza gestita in questa specifica iterazione. | Il Canvas menziona "altre preferenze connesse". È necessario aggiungere scenari per campi come "Dieta", "Accessibilità", ecc., o sono fuori scope di questa feature? |
| Validazione Schema Zod | Si presume che lo schema Zod blocchi automaticamente l'invio se il testo contiene caratteri non stampabili o formati invalidi oltre al semplice limite di lunghezza. | È necessario un scenario specifico per la validazione di caratteri speciali (es. emoji, tag HTML) nel campo motivazione? |
| Stato Loading | Si presume che lo stato di loading disabiliti *tutti* gli input del form, non solo il pulsante. | Il Canvas richiede di "disabilitare visivamente il pulsante". È corretto disabilitare anche i campi di input per evitare modifiche durante il submit? |
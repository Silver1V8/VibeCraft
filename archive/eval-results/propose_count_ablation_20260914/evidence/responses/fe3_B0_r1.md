# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Obiettivo della Feature

La presente specifica definisce il comportamento osservabile del modulo `BookingRequestForm` per la compilazione e sottomissione di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo è implementato come componente Client che interagisce con i metadati forniti da un Server Component. Lo scopo è garantire l'inserimento corretto della motivazione, la gestione delle preferenze (es. alloggio) e la corretta gestione dello stato durante la sottomissione, prevenendo invii duplicati o invalidi.

---

## 2. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio richiesta con dati validi
  GIVEN un utente autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione di 150 caratteri nel campo textarea
  AND seleziona la checkbox "Necessità alloggio" come preferenza
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema disabilita immediatamente il pulsante e mostra uno stato di caricamento
  AND invia il payload JSON contenente motivazione e preferenze al backend
  AND visualizza un messaggio di successo dopo la risposta dell'API
```

```gherkin
SCENARIO: S02 - Inibizione invio per motivazione vuota
  GIVEN un utente autenticato visualizza il form per un EVENTO attivo
  WHEN l'utente clicca sul pulsante "Partecipa" senza aver inserito nulla nella motivazione
  THEN il sistema evidenzia il campo textarea con un bordo rosso
  AND disabilita visivamente il pulsante "Partecipa" impedendo la chiamata di rete
```

```gherkin
SCENARIO: S03 - Gestione superamento limite caratteri motivazione
  GIVEN un utente autenticato visualizza il form per un EVENTO attivo
  WHEN l'utente inserisce una motivazione contenente 550 caratteri nel campo textarea
  THEN il sistema evidenzia il campo con un bordo rosso e mostra un contatore negativo
  AND disabilita il pulsante "Partecipa" impedendo la sottomissione del payload
```

```gherkin
SCENARIO: S04 - Gestione errore di rete durante la sottomissione
  GIVEN un utente autenticato ha compilato correttamente il form e clicca su "Partecipa"
  WHEN il backend restituisce un errore HTTP 500 o un timeout durante l'elaborazione
  THEN il sistema mostra un messaggio di errore tramite componente Toast
  AND riabilita i controlli del form permettendo all'utente di correggere i dati e riprovare
```

---

## 3. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
| :--- | :--- | :--- |
| Gestione Preferenze | Il campo "Necessità alloggio" è l'unica preferenza gestita nel form per questa feature specifica. | Esistono altre preferenze (es. dieta, accessibilità) da includere nel payload o sono gestite in un modulo futuro? Attualmente non coperte dagli scenari. |
| Validazione Schema | Lo schema Zod blocca solo i campi obbligatori e il limite di lunghezza; non valida la sintassi interna del testo oltre al conteggio caratteri. | Se l'utente inserisce caratteri speciali o formattazioni HTML nel textarea, il sistema li accetta come testo puro o li sanitizza? Non specificato nei requisiti attuali. |
| Stato Utente | Il Server Component fornisce i metadati dell'evento ma non gestisce la logica di blocco per utenti già iscritti (questa è responsabilità del backend/API). | L'utente vede il form se ha già una richiesta in attesa per lo stesso evento? La visibilità del form dipende solo dall'esistenza dell'evento o anche dallo stato della richiesta esistente? |
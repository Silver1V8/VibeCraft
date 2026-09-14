# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Descrizione della Feature

La feature **FE3** implementa un modulo interattivo per la compilazione e sottomissione di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo permette all'utente (`UTENTE`) di inserire una motivazione testuale e di gestire preferenze specifiche, tra cui la necessità di strutture per l'alloggio. L'interfaccia è strutturata in componenti Server (per il recupero del contesto evento) e Client (per la gestione dello stato form e la sottomissione). La validazione sintattica avviene lato client tramite schema Zod, mentre la persistenza dei dati è delegata al backend.

## 2. Requisiti Funzionali e Comportamentali

### [REQ-FE3-01] Gestione del contesto evento
Il componente Client deve recuperare i metadati dell'evento associato alla richiesta di prenotazione prima di renderizzare il form. Se l'evento non esiste o non è accessibile, il form non deve essere istanziato.

### [REQ-FE3-02] Inserimento motivazione e validazione lunghezza
L'utente può inserire un testo nella casella "Motivazione". Il sistema deve limitare l'inserimento a 500 caratteri, evidenziando visivamente il superamento del limite e disabilitando la sottomissione.

### [REQ-FE3-03] Gestione preferenze alloggio
L'utente può indicare se necessita di strutture per l'alloggio tramite un controllo booleano (Checkbox/Radio). Il sistema deve memorizzare questo stato nel payload della richiesta.

### [REQ-FE3-04] Sottomissione e gestione stato di invio
Al click sul pulsante "Partecipa", il sistema deve disabilitare l'input e il pulsante, mostrare uno stato di caricamento e inviare i dati al backend. In caso di errore lato server (timeout o 500), deve visualizzare un messaggio di feedback non intrusivo.

### [REQ-FE3-05] Prevenzione duplicati durante la sottomissione
Il sistema deve impedire l'invio multiplo della stessa richiesta mentre una chiamata API è in corso, bloccando fisicamente il pulsante e gli input.

---

## 3. Scenari Comportamentali BDD (Gherkin)

```gherkin
SCENARIO: S01 - Compilazione ed invio valido del form di prenotazione
  GIVEN un UTENTE autenticato visualizza la pagina di dettaglio di un EVENTO attivo
  AND l'utente inserisce una motivazione di 120 caratteri nella casella di testo
  AND l'utente seleziona la checkbox "Necessità alloggio"
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema disabilita immediatamente il pulsante e gli input
  AND visualizza uno stato di caricamento (loading state)
  AND inoltra con successo il payload JSON al backend per la creazione della RICHIESTA
```

```gherkin
SCENARIO: S02 - Blocco invio form per superamento limite caratteri motivazione
  GIVEN un UTENTE autenticato visualizza la pagina di dettaglio di un EVENTO attivo
  AND l'utente inserisce una motivazione di 550 caratteri nella casella di testo
  THEN il sistema evidenzia il bordo della casella con colore rosso
  AND mostra il messaggio informativo "La motivazione non può superare i 500 caratteri"
  AND disabilita il pulsante "Partecipa" impedendo la trasmissione dei dati
```

```gherkin
SCENARIO: S03 - Gestione errore lato server durante sottomissione
  GIVEN un UTENTE autenticato compila correttamente il form con motivazione valida
  WHEN l'utente clicca su "Partecipa" e il backend restituisce un errore HTTP 500 o timeout
  THEN il sistema visualizza un messaggio di errore tramite componente Toast
  AND ripristina lo stato abilitato del pulsante dopo la visualizzazione dell'errore
```

```gherkin
SCENARIO: S04 - Inibizione input per utente già iscritto all'evento
  GIVEN un UTENTE che possiede già una RICHIESTA in stato 'APPROVATA' per un EVENTO specifico
  WHEN l'utente naviga nuovamente sulla pagina di quell'evento e tenta di compilare il form
  THEN il sistema sostituisce il form di sottomissione con un badge informativo verde recante la dicitura "Sei già iscritto a questo evento"
```

---

## 4. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
| :--- | :--- | :--- |
| **REQ-FE3-03** (Preferenze) | Si presume che "altre preferenze connesse" menzionate nel Canvas si riferiscano esclusivamente alla necessità di alloggio per semplicità d'implementazione iniziale. | Il Canvas cita "altre preferenze connesse". È necessario aggiungere campi per "Pasto", "Accessibilità" o altri? Se sì, quali e come devono essere validati (es. opzionali/obbligatori)? |
| **REQ-FE3-04** (Feedback UI) | Si presume che il componente Toast standard di `sonner` sia sufficiente per gestire errori generici senza personalizzazioni specifiche per codice errore HTTP. | Per errori specifici (es. 409 Conflict), è necessario mostrare un messaggio diverso rispetto al generico "Errore server"? |
| **REQ-FE3-05** (Concorrenza) | Si presume che la disattivazione del pulsante tramite `React Hook Form` sia sufficiente a prevenire duplicati, senza bisogno di lock lato database aggiuntivi. | In caso di race condition tra due click rapidissimi prima della disattivazione, il backend gestisce i duplicati o è necessario un meccanismo di idempotenza lato client? |
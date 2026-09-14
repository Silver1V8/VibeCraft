# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Obiettivo e Logica del Form

La presente specifica definisce il comportamento osservabile della feature **FE3**, relativa alla compilazione e sottomissione interattiva di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo, implementato come componente Client React, gestisce l'inserimento della motivazione e delle preferenze (es. alloggio), valida i dati lato client prima dell'invio al backend e gestisce lo stato di caricamento per prevenire duplicati accidentali.

Il form è accessibile all'interno del contesto di un `EVENTO` attivo e richiede che l'utente sia autenticato (`UTENTE`). La sottomissione finale delega la persistenza e le transazioni al Backend, mentre il Frontend si occupa esclusivamente della raccolta input, della validazione sintattica (Zod) e del feedback visivo.

---

## 2. Regole di Validazione e Comportamento UI

### [REGOLA-FE3-01] Limiti di lunghezza per la motivazione
- **Descrizione:** Il campo `motivazione` è un textarea che accetta testo libero ma non deve superare i 500 caratteri.
- **Effetto in caso di violazione:** Se l'utente inserisce più di 500 caratteri, il contatore visivo diventa rosso e il pulsante di sottomissione viene disabilitato automaticamente tramite lo schema Zod.

### [REGOLA-FE3-02] Gestione dello stato di caricamento (Loading)
- **Descrizione:** Al momento della sottomissione (`submit`), il sistema deve bloccare l'interfaccia per prevenire invii multipli.
- **Effetto in caso di violazione:** Se l'utente tenta di inviare più volte durante la chiamata API, il sistema rifiuta l'azione e mostra un messaggio di errore generico o mantiene lo stato "inviato".

### [REGOLA-FE3-03] Feedback visivo su successo/errore
- **Descrizione:** Dopo la sottomissione, il sistema deve fornire feedback immediato all'utente.
- **Effetto in caso di violazione:** In caso di errore lato server (es. timeout 500), non deve comparire una pagina bianca ma un messaggio di notifica (`Toast`) che informa dell'errore senza bloccare la navigazione.

---

## 3. Scenari Comportamentali BDD (Gherkin)

```gherkin
SCENARIO: S01 - Invio form con dati validi e preferenze corrette
  GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione di 200 caratteri nel campo dedicato
  AND seleziona la preferenza "Necessità alloggio" tramite checkbox
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema disabilita il pulsante e mostra uno stato di caricamento
  AND invia con successo il payload JSON al backend
  AND visualizza un messaggio di conferma dopo la risposta positiva
```

```gherkin
SCENARIO: S02 - Inibizione invio per motivazione troppo lunga
  GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione contenente 550 caratteri nel campo dedicato
  WHEN tenta di cliccare sul pulsante "Partecipa"
  THEN il sistema evidenzia il campo in rosso con bordo errore
  AND disabilita il pulsante "Partecipa" impedendo la sottomissione
  AND visualizza un messaggio di errore relativo al limite dei caratteri
```

```gherkin
SCENARIO: S03 - Gestione errore lato server durante la sottomissione
  GIVEN un utente autenticato ha compilato correttamente il form con dati validi
  WHEN clicca sul pulsante "Partecipa" e il backend restituisce un errore HTTP 500 o timeout
  THEN il sistema mostra un messaggio di notifica (Toast) con l'errore ricevuto
  AND non blocca la pagina né lascia l'utente in uno stato indefinito
```

```gherkin
SCENARIO: S04 - Invio form senza preferenze selezionate
  GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione valida ma non seleziona alcuna preferenza (es. alloggio)
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema invia la richiesta con le preferenze impostate a valori predefiniti o nulli
  AND conferma la sottomissione al backend con successo
```

---

## 4. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
| :--- | :--- | :--- |
| **Gestione Preferenze** | Si assume che se l'utente non seleziona "Necessità alloggio", il valore inviato al backend sia `false` o `null`. | Il form deve obbligare la selezione di almeno una preferenza o permettere esplicitamente il valore vuoto? Attualmente lo scenario S04 copre il caso "nessuna selezionata", ma non è chiaro se questo sia un comportamento desiderato o un errore da segnalare. |
| **Validazione Zod** | Si assume che lo schema Zod blocchi solo i dati sintatticamente errati (lunghezza, tipo) e non validazioni di business complesse (es. "motivazione vuota" se il campo è opzionale). | Il campo motivazione è obbligatorio o opzionale? Se opzionale, lo scenario S02 copre bene il limite caratteri, ma manca uno scenario per "motivazione vuota" se fosse richiesta. |
| **Stato Caricamento** | Si assume che lo stato di loading disabiliti *tutti* gli input del form e non solo il pulsante. | È necessario bloccare anche i campi di testo durante il caricamento per evitare modifiche in corso? Attualmente S02 copre il blocco del pulsante, ma non esplicitamente degli input. |
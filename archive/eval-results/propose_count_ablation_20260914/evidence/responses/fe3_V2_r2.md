# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Descrizione della Feature

La feature **FE3** implementa l'interfaccia utente interattiva per la compilazione e sottomissione della richiesta di partecipazione a un evento (`EVENTO`). Il modulo permette all'utente loggato (`UTENTE`) di inserire una motivazione testuale e di gestire preferenze relative alla struttura (es. necessità alloggio). L'implementazione segue l'architettura Container/Presentational Components, separando il recupero del contesto evento (Server Component) dalla gestione dello stato del form e della sottomissione (Client Component). La validazione sintattica avviene lato client tramite schema **Zod**, mentre la persistenza dei dati è delegata al backend.

## 2. Requisiti Funzionali e Vincoli

### [REQ-FE3-01] Gestione Contesto Evento
Il componente deve recuperare i metadati dell'evento associato alla richiesta di prenotazione per renderli disponibili alla vista, senza esporre la logica di recupero nel client component.

### [REQ-FE3-02] Inserimento Motivazione
L'interfaccia deve fornire un campo `Textarea` per l'inserimento della motivazione della partecipazione. Il sistema deve validare che il testo non superi i 500 caratteri e disabilitare la sottomissione se il limite è superato o se il campo è vuoto.

### [REQ-FE3-03] Gestione Preferenze
L'interfaccia deve permettere di selezionare preferenze binarie, in particolare l'indicazione della necessità di una struttura per l'alloggio. Lo stato deve essere gestito tramite controlli radio o checkbox validati dallo schema.

### [REQ-FE3-04] Sottomissione e Feedback
La sottomissione invia un payload JSON contenente `{ motivazione, preferenze }`. Il sistema deve gestire lo stato di caricamento (loading) durante la chiamata API e mostrare feedback visivo (Toast) in caso di successo o errore lato server.

### [REQ-FE3-05] Inibizione Input Invalido
Il pulsante di sottomissione ("Partecipa") deve essere disabilitato visivamente finché lo schema `Zod` rileva dati mancanti o invalidi, prevenendo l'invio di payload null/invalidi.

### [REQ-FE3-06] Gestione Errori Client
In caso di timeout HTTP o errore 500 durante la sottomissione, il sistema deve mostrare un messaggio di errore tramite componente `Toast` senza bloccare l'interfaccia utente in uno stato non responsivo.

## 3. Scenari Comportamentali BDD (Gherkin)

```gherkin
SCENARIO: S01 - Compilazione e sottomissione valida della richiesta
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione di 120 caratteri nel campo dedicato
  AND seleziona la preferenza "Necessità alloggio: Sì" tramite il controllo UI
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema disabilita immediatamente il pulsante applicando lo stato disabled
  AND invia con successo il payload JSON al backend per la creazione della RICHIESTA
  AND visualizza un messaggio di conferma Toast all'utente
```

```gherkin
SCENARIO: S02 - Blocco sottomissione per campo motivazione vuoto
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  WHEN l'utente clicca sul pulsante "Partecipa" senza aver inserito alcuna motivazione
  THEN il sistema impedisce la chiamata API al server
  AND mantiene il pulsante abilitato solo se lo schema rileva dati validi, altrimenti lo disabilita
  AND evidenzia visivamente il campo motivazione come mancante secondo le regole di validazione
```

```gherkin
SCENARIO: S03 - Inibizione invio per superamento limite caratteri motivazione
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione di 550 caratteri nella casella di testo
  THEN il sistema evidenzia la casella con un bordo rosso
  AND mostra il messaggio informativo "La motivazione non può superare i 500 caratteri"
  AND disabilita il pulsante "Partecipa" impedendo la trasmissione dei dati
```

```gherkin
SCENARIO: S04 - Gestione errore lato server durante sottomissione
  GIVEN un UTENTE autenticato compila correttamente il form con dati validi
  WHEN l'utente clicca su "Partecipa" e il backend restituisce un errore 500 o timeout
  THEN il sistema visualizza un alert Toast generato con sonner contenente il messaggio di errore
  AND ripristina lo stato abilitato del pulsante dopo la risoluzione dell'errore
```

## 4. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
| :--- | :--- | :--- |
| Gestione Preferenze (REQ-FE3-03) | Si presume che le preferenze oltre all'alloggio siano gestite tramite lo stesso pattern booleano/radio descritto per l'alloggio. | Quali sono esattamente le "altre preferenze connesse" menzionate nel Canvas e come devono essere rappresentate UI (checkbox, select multi-select)? |
| Validazione Schema Zod (REQ-FE3-02) | Si presume che lo schema Zod sia configurato con un limite di lunghezza esatto di 500 caratteri per il campo motivazione. | Il limite di 500 caratteri è assoluto o dipende da impostazioni dell'evento? Come si gestisce il caso in cui l'utente copia-incolla testo formattato che supera il conteggio byte ma non quello grafico? |
| Gestione Errori Client (REQ-FE3-06) | Si presume che il componente Toast sia configurato per essere dismissibile automaticamente dopo un timeout breve. | Qual è la durata esposta del Toast in caso di errore e come si gestisce il caso in cui l'errore persiste oltre 5 secondi? |
| Concorrenza UI (REQ-FE3-06) | Si presume che non sia necessario gestire stati di "doppio click" oltre al blocco standard del pulsante. | Se l'utente tenta di cambiare preferenze mentre la chiamata API è in volo, come si gestisce il conflitto tra stato UI e stato server? |
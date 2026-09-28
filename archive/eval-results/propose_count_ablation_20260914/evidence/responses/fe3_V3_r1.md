# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Descrizione della Feature

La feature **FE3** implementa un modulo interattivo per la compilazione e sottomissione di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo permette all'utente loggato (`UTENTE`) di inserire una motivazione testuale e di gestire preferenze specifiche, tra cui la necessità di strutture per l'alloggio. L'interfaccia deve garantire la validazione dei dati lato client prima dell'invio al backend, prevenendo l'inserimento di payload invalidi o duplicati.

---

## 2. Funzionalità e Scenari BDD

### Funzionalità F1: Validazione della Motivazione e Limite Caratteri

Questa funzionalità gestisce il campo testuale per la motivazione della partecipazione, applicando vincoli di lunghezza e prevenendo l'invio di dati vuoti o eccessivamente lunghi.

```gherkin
SCENARIO: S01 - Invio form con motivazione valida
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione contenente esattamente 250 caratteri
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema accetta l'inserimento e abilita la sottomissione al backend
```

```gherkin
SCENARIO: S02 - Inibizione invio per motivazione vuota
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND il campo motivazione è lasciato vuoto o contiene solo spazi bianchi
  WHEN l'utente tenta di cliccare sul pulsante "Partecipa"
  THEN il sistema disabilita visivamente il pulsante e non invia la richiesta al backend
```

```gherkin
SCENARIO: S03 - Inibizione invio per superamento limite caratteri
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione contenente 550 caratteri (superiore al limite)
  WHEN l'utente tenta di cliccare sul pulsante "Partecipa"
  THEN il sistema evidenzia il campo in rosso, disabilita il pulsante e mostra un messaggio di errore relativo al limite dei 500 caratteri
```

### Funzionalità F2: Gestione delle Preferenze (Alloggio)

Questa funzionalità gestisce l'inserimento delle preferenze dell'utente, specificamente la necessità di strutture per l'alloggio, permettendo all'utente di selezionare o meno tale opzione.

```gherkin
SCENARIO: S04 - Selezione della necessità alloggio
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente attiva la casella di controllo relativa alla necessità di alloggio
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema include nel payload inviato al backend il flag booleano che indica la necessità di alloggio
```

```gherkin
SCENARIO: S05 - Selezione della non necessità alloggio
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente lascia disattivata la casella di controllo relativa alla necessità di alloggio
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema include nel payload inviato al backend il flag booleano che indica l'assenza di necessità di alloggio
```

### Funzionalità F3: Prevenzione Duplicati e Gestione Stato Caricamento

Questa funzionalità assicura che, durante la sottomissione della richiesta, non siano possibili invii multipli accidentali e gestisce lo stato visivo dell'interfaccia mentre avviene la comunicazione con il server.

```gherkin
SCENARIO: S06 - Disattivazione pulsante durante sottomissione
  GIVEN un UTENTE autenticato ha compilato correttamente il form di prenotazione per un EVENTO
  AND l'utente clicca sul pulsante "Partecipa"
  WHEN la chiamata al backend è in corso (stato di rete attivo)
  THEN il sistema disabilita immediatamente il pulsante "Partecipa", mostra uno stato di caricamento e impedisce ulteriori click
```

```gherkin
SCENARIO: S07 - Gestione errore lato server durante sottomissione
  GIVEN un UTENTE autenticato ha compilato correttamente il form di prenotazione per un EVENTO
  AND l'utente clicca sul pulsante "Partecipa"
  WHEN il backend restituisce un errore (es. timeout o codice 500) durante la sottomissione
  THEN il sistema visualizza un messaggio di avviso (Toast) all'utente e ripristina lo stato del form senza inviare dati duplicati
```

### Funzionalità F4: Inizializzazione Contesto Evento

Questa funzionalità gestisce il caricamento dei metadati dell'evento necessari per abilitare o disabilitare dinamicamente il form in base allo stato dell'evento (es. disponibilità).

```gherkin
SCENARIO: S08 - Visualizzazione form con contesto evento valido
  GIVEN un UTENTE autenticato naviga verso la pagina di dettaglio di un EVENTO attivo e disponibile
  WHEN il componente Server Component recupera i metadati dell'evento
  THEN il sistema renderizza il form di prenotazione con tutti i campi abilitati per l'inserimento dati
```

```gherkin
SCENARIO: S09 - Disabilitazione form in caso evento non accessibile
  GIVEN un UTENTE autenticato naviga verso la pagina di dettaglio di un EVENTO già esaurito o chiuso
  WHEN il componente Server Component riceve lo stato "Sold Out" o "Chiuso" dal backend
  THEN il sistema nasconde i campi di input e disabilita l'invio della richiesta, mostrando solo informazioni contestuali
```

---

## 3. Punti Aperti

Nessun punto aperto rilevato per la copertura delle funzionalità descritte nel Canvas FE3. Tutti i requisiti funzionali (motivazione, preferenze alloggio, validazione Zod, gestione stato API) e i vincoli normativi (limite caratteri, anti-duplicati, sicurezza input) sono stati mappati negli scenari corrispondenti.

*   **Funzionalità F1**: Copertura completa per limiti di testo e vuoto.
*   **Funzionalità F2**: Copertura completa per gestione booleana delle preferenze.
*   **Funzionalità F3**: Copertura completa per UX durante la rete (loading/error).
*   **Funzionalità F4**: Copertura completa per il rendering condizionale basato sui metadati evento.
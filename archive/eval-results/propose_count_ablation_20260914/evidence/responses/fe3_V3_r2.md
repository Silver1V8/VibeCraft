# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Descrizione della Feature

La feature **FE3** implementa un modulo interattivo per la compilazione e sottomissione di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo permette all'utente loggato (`UTENTE`) di inserire una motivazione testuale e di gestire preferenze specifiche, tra cui la necessità di strutture per l'alloggio. L'interfaccia deve garantire la validazione dei dati lato client prima della sottomissione al backend, gestendo stati di caricamento e feedback visivi in caso di errori o successo dell'operazione.

---

## 2. Funzionalità e Scenari BDD

### Funzionalità F1: Validazione del campo "Motivazione"
Questa funzionalità gestisce l'inserimento del testo della motivazione, applicando limiti di lunghezza e prevenendo l'invio di dati vuoti o eccessivamente lunghi.

```gherkin
SCENARIO: S01 - Invio richiesta con motivazione valida
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione contenente 250 caratteri
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema invia la richiesta al backend con successo
  AND mostra uno stato di feedback positivo all'utente
```

```gherkin
SCENARIO: S02 - Inibizione invio per motivazione vuota
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  WHEN l'utente lascia il campo "Motivazione" vuoto e clicca su "Partecipa"
  THEN il sistema impedisce la sottomissione della richiesta
  AND evidenzia visivamente il campo come mancante
```

```gherkin
SCENARIO: S03 - Inibizione invio per superamento limite caratteri
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione di 550 caratteri
  WHEN l'utente tenta di inviare la richiesta
  THEN il sistema disabilita il pulsante "Partecipa"
  AND mostra un messaggio di errore indicando il limite di 500 caratteri
```

### Funzionalità F2: Gestione delle Preferenze e Sottomissione
Questa funzionalità gestisce l'inserimento delle preferenze (es. alloggio) e la sottomissione complessiva del form, inclusi gli stati di caricamento durante la chiamata API.

```gherkin
SCENARIO: S04 - Invio con preferenza alloggio attiva
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente seleziona "Necessario" per la struttura di alloggio
  WHEN l'utente completa tutti i campi e clicca su "Partecipa"
  THEN il sistema invia il payload contenente la preferenza di alloggio
  AND aggiorna lo stato della richiesta nel contesto dell'utente
```

```gherkin
SCENARIO: S05 - Gestione stato di caricamento durante l'invio
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  WHEN l'utente clicca su "Partecipa" e la chiamata API è in corso
  THEN il sistema disabilita il pulsante "Partecipa"
  AND mostra uno stato di caricamento (spinner) sul pulsante
```

```gherkin
SCENARIO: S06 - Gestione errore lato server durante l'invio
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  WHEN l'utente clicca su "Partecipa" e il backend restituisce un errore 500
  THEN il sistema mostra un messaggio di avviso (Toast) con i dettagli dell'errore
  AND ripristina lo stato abilitato del pulsante dopo la visualizzazione dell'errore
```

### Funzionalità F3: Rendering Dinamico e Contesto Evento
Questa funzionalità gestisce il caricamento dei metadati dell'evento e il rendering dinamico dei campi del form in base al contesto fornito dal Server Component.

```gherkin
SCENARIO: S07 - Caricamento contestuale dei metadati evento
  GIVEN un UTENTE naviga verso la pagina di dettaglio di un EVENTO specifico
  WHEN il Server Component recupera i metadati dell'evento
  THEN il Client Component renderizza il form con i dati dell'evento disponibili
  AND abilita l'inserimento delle preferenze relative a quell'evento
```

```gherkin
SCENARIO: S08 - Rendering dinamico dei campi preferenze
  GIVEN un UTENTE visualizza il form per un EVENTO attivo
  WHEN il sistema riceve i metadati che includono opzioni di alloggio
  THEN l'interfaccia renderizza dinamicamente i controlli (Checkbox/Select) per le preferenze
  AND permette all'utente di modificare tali preferenze in tempo reale
```

---

## 3. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
| :--- | :--- | :--- |
| **F1** (Validazione Motivazione) | Nessuna; copertura completa dai casi S02 e S03. | N/A |
| **F2** (Gestione Errori) | L'errore 500 restituito dal backend è sempre gestito tramite Toast standard senza ricaricare la pagina. | Come comportarsi se l'errore persiste per più di 10 secondi? (Non coperto, ma non critico per MVP). |
| **F3** (Rendering) | I metadati dell'evento sono sempre disponibili prima del primo render del Client Component. | Cosa succede se i metadati arrivano con ritardo significativo rispetto al timeout di rendering? |
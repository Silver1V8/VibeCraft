# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Descrizione della Feature

La feature **FE3** implementa un modulo interattivo per la compilazione e sottomissione di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo permette all'utente (`UTENTE`) di inserire una motivazione testuale e di gestire preferenze specifiche, tra cui la necessità di strutture per l'alloggio. L'interfaccia deve garantire la validazione dei dati lato client prima dell'invio al backend, prevenendo l'inserimento di payload invalidi o duplicati.

---

## 2. Funzionalità e Scenari BDD

### Funzionalità F1: Validazione della Motivazione e Gestione Limite Caratteri

Questa funzionalità gestisce il campo testuale per la motivazione, applicando vincoli di lunghezza (max 500 caratteri) e bloccando l'invio se il testo è vuoto o supera il limite.

```gherkin
SCENARIO: F1-01 - Invio form con motivazione valida
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione di 250 caratteri nel campo dedicato
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema invia la richiesta al backend con successo
  AND mostra uno stato di feedback positivo all'utente
```

```gherkin
SCENARIO: F1-02 - Blocco invio per motivazione vuota
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  WHEN l'utente non inserisce alcun testo nel campo motivazione e clicca "Partecipa"
  THEN il sistema impedisce la sottomissione della richiesta
  AND evidenzia il campo motivazione come mancante
```

```gherkin
SCENARIO: F1-03 - Blocco invio per superamento limite caratteri
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione di 550 caratteri nel campo dedicato
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema impedisce la sottomissione della richiesta
  AND evidenzia il campo con messaggio di errore relativo al limite dei 500 caratteri
```

### Funzionalità F2: Gestione Preferenze e Stato Alloggio

Questa funzionalità gestisce l'inserimento delle preferenze dell'utente, specificamente la necessità di alloggio, permettendo all'utente di selezionare o meno tale opzione.

```gherkin
SCENARIO: F2-01 - Sottomissione con richiesta di alloggio
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente seleziona l'opzione "Necessario alloggio" tra le preferenze disponibili
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema invia la richiesta al backend includendo la preferenza di alloggio
  AND conferma la registrazione della preferenza nel payload inviato
```

```gherkin
SCENARIO: F2-02 - Sottomissione senza richiesta di alloggio
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente lascia deselezionata l'opzione "Necessario alloggio"
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema invia la richiesta al backend senza includere la preferenza di alloggio
  AND conferma la registrazione della preferenza negativa nel payload inviato
```

### Funzionalità F3: Prevenzione Duplicati e Gestione Stato Caricamento

Questa funzionalità garantisce che l'utente non possa inviare più volte lo stesso form durante il ciclo di rete, disabilitando il pulsante di invio istantaneamente.

```gherkin
SCENARIO: F3-01 - Disattivazione pulsante al click
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema disabilita immediatamente il pulsante "Partecipa"
  AND sostituisce il testo del pulsante con uno stato di caricamento visivo
```

```gherkin
SCENARIO: F3-02 - Prevenzione sottomissione parallela
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  WHEN l'utente clicca ripetutamente sul pulsante "Partecipa" durante la chiamata di rete
  THEN il sistema ignora i click successivi mantenendo il pulsante disabilitato
  AND invia al backend esattamente una sola istanza della richiesta
```

### Funzionalità F4: Gestione Errori di Rete e Feedback Utente

Questa funzionalità gestisce gli scenari in cui la sottomissione fallisce a causa di errori lato server (es. timeout, errore 500), assicurando che l'utente non rimanga bloccato su una pagina bianca.

```gherkin
SCENARIO: F4-01 - Gestione errore di timeout durante invio
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente clicca "Partecipa" ma la chiamata al backend subisce un timeout HTTP
  THEN il sistema mostra un messaggio di errore all'utente tramite componente Toast
  AND ripristina lo stato del pulsante dopo la visualizzazione dell'errore
```

```gherkin
SCENARIO: F4-02 - Gestione errore server (500) durante invio
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente clicca "Partecipa" ma il backend restituisce un codice di errore 500
  THEN il sistema mostra un messaggio di errore generico all'utente tramite componente Toast
  AND non blocca l'interfaccia utente permettendo la navigazione o il riavvio del form
```

---

## 3. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
| :--- | :--- | :--- |
| **F1** (Validazione Motivazione) | Nessuna; copertura completa dai casi limite definiti. | N/A |
| **F2** (Gestione Preferenze) | Nessuna; copertura completa dei casi di selezione/deselezione. | N/A |
| **F3** (Prevenzione Duplicati) | Nessuna; copertura completa del comportamento anti-click e disattivazione. | N/A |
| **F4** (Gestione Errori) | Nessuna; copertura completa degli errori di rete e server standard. | N/A |

*Nota: La specifica copre esclusivamente il comportamento osservabile dell'interfaccia utente per la feature FE3 come descritto nel Canvas e nei vincoli normativi applicabili.*
# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Obiettivo e Logica del Form di Prenotazione

La presente specifica definisce i requisiti funzionali, le regole di validazione sintattica dei dati e i vincoli di interfaccia grafica applicati al modulo (form) di compilazione e sottomissione della richiesta di partecipazione a un evento (`EVENTO`). Lo scopo di questo modulo è garantire che i dati inseriti dall'utente (`UTENTE`) siano coerenti, puliti e conformi ai limiti definiti prima di avviare il transito di rete verso il backend.

Questo form rappresenta la porta d'ingresso interattiva per l'iscrizione, accessibile dalla dashboard o dalla scheda dettaglio evento, e deve agire in sinergia con i controlli transazionali del backend delegando la validazione finale al server.

---

## 2. Funzionalità e Scenari BDD (Gherkin)

### Funzionalità F1: Gestione e Validazione del Campo Motivazione

Questa funzionalità gestisce l'inserimento, il limite di lunghezza e la validità obbligatoria del campo "motivazione".

```gherkin
SCENARIO: S01 - Invio form con motivazione valida
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione di 250 caratteri nel campo dedicato
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema evidenzia il campo come valido
  AND disabilita il pulsante durante la chiamata API
  AND inoltra con successo il payload JSON al backend
```

```gherkin
SCENARIO: S02 - Blocco invio per motivazione vuota
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente non inserisce alcun testo nel campo motivazione
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema evidenzia il campo con bordo rosso
  AND mostra il messaggio di errore "Il campo motivazione è obbligatorio"
  AND disabilita il pulsante impedendo la trasmissione dei dati
```

```gherkin
SCENARIO: S03 - Blocco invio per superamento limite caratteri
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione di 550 caratteri nel campo dedicato
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema evidenzia il campo con bordo rosso
  AND mostra il messaggio informativo "La motivazione non può superare i 500 caratteri"
  AND disabilita il pulsante impedendo la trasmissione dei dati
```

### Funzionalità F2: Gestione delle Preferenze e Alloggio

Questa funzionalità gestisce l'inserimento delle preferenze dell'utente, specificamente la necessità di strutture per l'alloggio.

```gherkin
SCENARIO: S04 - Selezione della necessità alloggio
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente attiva la checkbox "Necessaria struttura per l'alloggio"
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema include nel payload JSON il valore booleano true per la preferenza alloggio
  AND inoltra con successo il payload al backend
```

```gherkin
SCENARIO: S05 - Selezione della non necessità alloggio
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente lascia disattivata la checkbox "Necessaria struttura per l'alloggio"
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema include nel payload JSON il valore booleano false per la preferenza alloggio
  AND inoltra con successo il payload al backend
```

### Funzionalità F3: Gestione dello Stato di Caricamento e Errori

Questa funzionalità gestisce l'interazione dell'utente durante la sottomissione, prevenendo duplicati e gestendo gli errori di rete.

```gherkin
SCENARIO: S06 - Disattivazione pulsante durante caricamento
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente ha compilato tutti i campi correttamente
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema sostituisce il testo del pulsante con uno spinner di caricamento
  AND disabilita immediatamente il controllo HTML del pulsante
```

```gherkin
SCENARIO: S07 - Gestione errore timeout durante sottomissione
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente clicca sul pulsante "Partecipa" con dati validi
  WHEN il backend non risponde entro il tempo limite (timeout HTTP)
  THEN il sistema mostra un alert Toast con messaggio di errore generico
  AND riabilita il pulsante dopo la visualizzazione dell'errore
```

---

## Punti aperti

```json
{"open_points":[{"id":"OP-001","functionality":"Gestione delle Preferenze e Alloggio","original_question":"Quali altre preferenze connesse all'alloggio sono gestite?", "question":"Il Canvas menziona 'altre preferenze connesse' ma non specifica quali campi (es. tipo di camera, numero ospiti).","assumption":null,"uncovered_scenarios":["Invio form con preferenza alloggio e tipo camera selezionato"],"reason":"missing_coverage","research":{"status":"not_started","new_evidence":[],"verification":"agent_reported"}}]
}
```
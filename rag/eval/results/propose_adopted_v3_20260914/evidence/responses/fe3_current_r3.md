# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Obiettivo e Logica della Feature

La presente specifica definisce i requisiti funzionali, le regole di validazione sintattica dei dati e i vincoli di interfaccia grafica applicati al modulo (form) di compilazione e sottomissione della richiesta di partecipazione a un evento (`EVENTO`). Lo scopo di questo modulo è garantire che i dati inseriti dall'`UTENTE` siano coerenti, puliti e conformi ai limiti definiti prima di avviare il transito di rete verso il backend.

Questo form rappresenta la porta d'ingresso interattiva per l'iscrizione, accessibile dalla dashboard o dalla scheda dettaglio evento. Deve agire in sinergia con i controlli transazionali del backend, delegando la validazione logica finale al server ma prevenendo invii invalidi lato client.

---

## 2. Funzionalità e Scenari BDD (Gherkin)

### Funzionalità F1: Gestione e Validazione del Campo Motivazione

Questa funzionalità gestisce l'inserimento, il limite di lunghezza e la validità del testo della motivazione della partecipazione.

```gherkin
SCENARIO: S01 - Invio form con motivazione valida
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione contenente esattamente 250 caratteri
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema accetta l'inserimento senza errori
  AND disabilita il pulsante di invio durante la chiamata API
```

```gherkin
SCENARIO: S02 - Blocco invio per superamento limite caratteri motivazione
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione contenente 551 caratteri
  WHEN tenta di cliccare sul pulsante "Partecipa"
  THEN il sistema evidenzia la casella con bordo rosso
  AND mostra il messaggio "Limite superato"
  AND disabilita il pulsante "Partecipa" impedendo l'invio
```

```gherkin
SCENARIO: S03 - Invio form con campo motivazione vuoto
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente non inserisce alcun testo nel campo motivazione
  WHEN tenta di cliccare sul pulsante "Partecipa"
  THEN il sistema evidenzia la casella come mancante
  AND disabilita il pulsante "Partecipa"
  AND impedisce la trasmissione del payload al backend
```

### Funzionalità F2: Gestione delle Preferenze (Alloggio)

Questa funzionalità gestisce l'inserimento e la validazione delle preferenze relative alla necessità di strutture per l'alloggio.

```gherkin
SCENARIO: S04 - Invio form con preferenza alloggio attiva
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente seleziona l'opzione "Necessaria struttura per alloggio"
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema include la flag di necessità alloggio nel payload JSON
  AND inoltra correttamente la richiesta al backend
```

```gherkin
SCENARIO: S05 - Invio form con preferenza alloggio disattivata
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente seleziona l'opzione "Non necessaria struttura per alloggio"
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema include la flag di non necessità nel payload JSON
  AND inoltra correttamente la richiesta al backend
```

### Funzionalità F3: Gestione dello Stato di Caricamento e Errori

Questa funzionalità gestisce l'interazione dell'utente durante la sottomissione della richiesta, inclusi stati di loading e gestione degli errori lato client.

```gherkin
SCENARIO: S06 - Disattivazione pulsante durante chiamata API
  GIVEN un UTENTE autenticato ha compilato correttamente il form
  AND clicca sul pulsante "Partecipa"
  WHEN la chiamata API è in corso (Round Trip Time)
  THEN il sistema sostituisce il testo del pulsante con uno spinner visivo
  AND mantiene il pulsante nello stato HTML `disabled`
```

```gherkin
SCENARIO: S07 - Gestione errore lato server durante sottomissione
  GIVEN un UTENTE autenticato ha compilato correttamente il form
  WHEN clicca sul pulsante "Partecipa" e il backend restituisce un errore 500 o timeout
  THEN il sistema visualizza un alert Toast con il messaggio di errore
  AND ripristina lo stato visivo del form dopo la chiusura dell'alert
```

---

## 3. Punti aperti

```json
{"open_points":[{"id":"OP-001","functionality":"Gestione delle Preferenze (Alloggio)","original_question":"Quali altre preferenze connesse sono gestite oltre all'alloggio?", "question":"Il Canvas menziona 'altre preferenze connesse' ma non elenca quali. È necessario definire campi aggiuntivi o limitarsi a un generico campo testo per le note sulle preferenze?", "assumption":null,"uncovered_scenarios":["Invio form con altre preferenze specifiche (es. dieta, accessibilità)"], "reason":"missing_coverage","research":{"status":"not_started","new_evidence":[],"verification":"agent_reported"}}]
}
```
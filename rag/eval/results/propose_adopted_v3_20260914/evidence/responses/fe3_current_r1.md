# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Obiettivo e Logica della Feature

La presente specifica definisce i requisiti funzionali, le regole di validazione sintattica dei dati e i vincoli di interfaccia grafica applicati al modulo (form) di compilazione e sottomissione della richiesta di partecipazione a un evento (`EVENTO`). Lo scopo di questo modulo è garantire che i dati inseriti dall'utente (`UTENTE`) siano coerenti, puliti e conformi ai limiti definiti prima di avviare il transito di rete verso il backend.

Il form gestisce l'inserimento della **motivazione** (testo libero) e delle **preferenze** (struttura alloggio e altre opzioni). L'interfaccia deve isolare la logica di rendering dal recupero dei dati iniziali, utilizzando componenti Server per il contesto evento e Client Component per la gestione dello stato del form.

---

## 2. Funzionalità e Scenari BDD

### Funzionalità F1: Validazione della Motivazione e Limite Caratteri

Questa funzionalità gestisce l'inserimento del testo nella casella "Motivazione", applicando limiti di lunghezza e prevenendo l'invio di dati non conformi.

```gherkin
SCENARIO: S01 - Invio form con motivazione valida
  GIVEN un utente autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione di 250 caratteri nel campo dedicato
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema accetta l'inserimento senza errori visivi
  AND disabilita il pulsante durante la chiamata API
  AND inoltra il payload con il testo della motivazione al backend
```

```gherkin
SCENARIO: S02 - Blocco invio per superamento limite caratteri
  GIVEN un utente autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione di 550 caratteri nel campo dedicato
  WHEN l'utente tenta di cliccare sul pulsante "Partecipa"
  THEN il sistema evidenzia il bordo del campo in rosso
  AND mostra il messaggio "Limite superato"
  AND disabilita il pulsante impedendo la trasmissione dei dati
```

```gherkin
SCENARIO: S03 - Invio form con motivazione vuota
  GIVEN un utente autenticato visualizza il form per un EVENTO attivo
  AND il campo motivazione è vuoto o contiene solo spazi bianchi
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema evidenzia il campo come mancante
  AND impedisce la sottomissione della richiesta
```

### Funzionalità F2: Gestione delle Preferenze e Stato Iniziale

Questa funzionalità gestisce l'inserimento delle preferenze (es. necessità alloggio) e lo stato iniziale del form basato sul contesto dell'evento.

```gherkin
SCENARIO: S04 - Selezione preferenza alloggio necessaria
  GIVEN un utente autenticato visualizza il form per un EVENTO attivo
  AND l'utente attiva la checkbox "Necessità alloggio"
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema include nel payload il flag booleano per l'alloggio
  AND inoltra la richiesta con successo al backend
```

```gherkin
SCENARIO: S05 - Selezione preferenza alloggio non necessaria
  GIVEN un utente autenticato visualizza il form per un EVENTO attivo
  AND l'utente lascia disattivata la checkbox "Necessità alloggio"
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema include nel payload il valore booleano falso per l'alloggio
  AND inoltra la richiesta con successo al backend
```

### Funzionalità F3: Gestione dello Stato di Caricamento e Feedback Utente

Questa funzionalità gestisce il comportamento dell'interfaccia durante la sottomissione della richiesta, prevenendo interazioni multiple e fornendo feedback visivo.

```gherkin
SCENARIO: S06 - Disattivazione pulsante durante caricamento
  GIVEN un utente autenticato ha compilato correttamente il form
  AND l'utente clicca sul pulsante "Partecipa"
  WHEN la chiamata API è in corso (stato loading)
  THEN il sistema sostituisce il testo del pulsante con uno spinner
  AND mantiene il pulsante nello stato disabilitato
```

```gherkin
SCENARIO: S07 - Gestione errore di sottomissione lato server
  GIVEN un utente autenticato ha compilato correttamente il form
  WHEN l'utente clicca su "Partecipa" e il backend restituisce un errore 500 o timeout
  THEN il sistema visualizza un messaggio Toast con il dettaglio dell'errore
  AND ripristina lo stato abilitato del pulsante dopo la risoluzione dell'errore
```

---

## Punti aperti

```json
{"open_points":[{"id":"OP-001","functionality":"Gestione delle Preferenze e Stato Iniziale","original_question":"Quali preferenze oltre all'alloggio sono menzionate nell'intervista?", "question":"Quali altri campi di preferenza (es. dieta, accessibilità) devono essere gestiti nel form?", "assumption":null,"uncovered_scenarios":["Selezione preferenza X necessaria", "Selezione preferenza X non necessaria"], "reason":"missing_coverage","research":{"status":"not_started","new_evidence":[],"verification":"agent_reported"}}]}
```
# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Obiettivo della Feature

La presente specifica definisce il comportamento osservabile del modulo `BookingRequestForm` per la compilazione e sottomissione di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo è implementato come componente Client che interagisce con i metadati forniti da un Server Component, gestendo lo stato locale dell'utente (`UTENTE`) e delle preferenze (es. alloggio). Lo scopo è garantire l'inserimento corretto della motivazione e delle preferenze, prevenendo invii duplicati o invalidi prima che il payload raggiunga il backend.

---

## 2. Regole di Validazione e Comportamento UI

### [REGOLA-UI-01] Gestione del limite caratteri motivazione
- **Descrizione:** Il campo `Textarea` per la motivazione deve visualizzare un contatore dei caratteri residui in tempo reale. Il valore massimo assoluto è 500 caratteri.
- **Effetto in caso di violazione (Failure Mode):** Se il testo supera i 500 caratteri, il contatore diventa rosso e negativo, il bordo del campo si evidenzia e il pulsante di sottomissione viene disabilitato.
- **Entità Target:** `RICHIESTA`

### [REGOLA-UI-02] Inibizione input invalido (Submit Disabled)
- **Descrizione:** Il pulsante "Partecipa" deve essere abilitato solo se lo schema Zod rileva che tutti i campi obbligatori sono compilati e validi.
- **Effetto in caso di violazione (Failure Mode):** Se il campo motivazione è vuoto o contiene testo non valido, il pulsante appare disabilitato visivamente (`disabled` prop) impedendo l'invio del payload null/invalido.
- **Entità Target:** `RICHIESTA`

### [REGOLA-UI-03] Prevenzione duplicati durante la sottomissione
- **Descrizione:** All'istante esatto dell'inizio della chiamata API (submit), il componente deve disabilitare l'input e mostrare uno stato di caricamento (`loading`) sul pulsante.
- **Effetto in caso di violazione (Failure Mode):** L'utente non può inviare più volte la richiesta mentre una è in corso, evitando duplicati nel database.
- **Entità Target:** `RICHIESTA`

### [REGOLA-UI-04] Gestione errori lato client
- **Descrizione:** In caso di errore HTTP (es. timeout o 500) durante la sottomissione, il sistema deve mostrare un feedback visivo (`Toast`) senza bloccare l'interfaccia in uno stato indefinito.
- **Effetto in caso di violazione (Failure Mode):** L'utente rimane bloccato su una pagina bianca o con errore generico non descritto, impedendo il retry.
- **Entità Target:** `RICHIESTA`

---

## 3. Scenari Comportamentali BDD (Gherkin)

```gherkin
SCENARIO: S01 - Invio richiesta con dati validi e preferenze
  GIVEN un utente autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione di 120 caratteri nel campo Textarea
  AND seleziona la preferenza "Necessità alloggio" tramite Checkbox
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema valida lo schema Zod e abilita l'invio
  AND disabilita il pulsante mostrando uno stato di caricamento
  AND inoltra con successo il payload JSON al backend
```

```gherkin
SCENARIO: S02 - Inibizione invio per motivazione vuota
  GIVEN un utente autenticato visualizza il form per un EVENTO attivo
  WHEN l'utente clicca sul pulsante "Partecipa" senza inserire nulla nella motivazione
  THEN il sistema rileva la violazione dello schema Zod
  AND disabilita visivamente il pulsante "Partecipa"
  AND non invia alcun payload al backend
```

```gherkin
SCENARIO: S03 - Blocco invio per superamento limite caratteri
  GIVEN un utente autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione di 550 caratteri nel campo Textarea
  THEN il sistema evidenzia il contatore dei caratteri in rosso con valore negativo
  AND disabilita il pulsante "Partecipa" impedendo la trasmissione dei dati
```

```gherkin
SCENARIO: S04 - Gestione errore di sottomissione lato server
  GIVEN un utente autenticato invia una richiesta valida tramite il form
  WHEN il backend restituisce un errore HTTP 500 o timeout durante l'elaborazione
  THEN il sistema visualizza un messaggio di errore Toast all'utente
  AND riabilita i controlli del form permettendo al utente di correggere e riprovare
```

---

## 4. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
| :--- | :--- | :--- |
| Gestione preferenze (alloggio) | Si presume che le altre preferenze connesse menzionate nel Canvas siano gestite tramite gli stessi meccanismi booleani/radio descritti per l'alloggio. | Qual è esattamente la lista completa delle "altre preferenze connesse" da includere nel form oltre all'alloggio? |
| Validazione schema Zod | Si presume che lo schema Zod sia configurato per accettare solo stringhe non vuote e boole valide, senza regole complesse di formato (es. regex) oltre al limite di lunghezza. | Esistono vincoli specifici sul formato della motivazione (es. caratteri speciali permessi) oltre al semplice conteggio dei caratteri? |
| Stato iniziale form | Si presume che il Server Component fornisca sempre i metadati dell'evento necessari per inizializzare lo stato del Client Component prima del primo render. | Come si comporta il form se il Server Component fallisce nel recuperare i metadati dell'evento (fallback UI)? |
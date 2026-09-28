# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Descrizione della Feature

La feature **FE3** implementa un modulo interattivo per la compilazione e sottomissione di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo permette all'utente (`UTENTE`) di inserire una motivazione testuale e di gestire preferenze relative alla struttura (es. necessità di alloggio). L'interfaccia segue l'architettura **Container/Presentational Components**, dove un componente Server fornisce il contesto dell'evento e un componente Client gestisce lo stato del form, la validazione tramite schema `Zod` e la sottomissione asincrona tramite TanStack Query.

## 2. Requisiti Funzionali e di Validazione

### [REQ-FE3-01] Gestione Preferenze Alloggio
Il modulo deve esporre un controllo (Checkbox o Radio Button) per indicare se l'utente necessita di una struttura per l'alloggio associata all'evento. Il valore booleano risultante deve essere incluso nel payload della sottomissione.

### [REQ-FE3-02] Inserimento Motivazione
Il modulo deve fornire un campo `Textarea` per la motivazione della partecipazione. Lo schema di validazione impone un limite massimo di 500 caratteri. Il sistema deve visualizzare un contatore dei caratteri residui in tempo reale.

### [REQ-FE3-03] Sottomissione e Stato Loading
Alla sottomissione, il sistema deve disabilitare visivamente il pulsante di invio ("Partecipa") e mostrare uno stato di caricamento (loading state) per prevenire duplicazioni della richiesta durante il Round Trip Time.

### [REQ-FE3-04] Gestione Errori di Rete
In caso di fallimento della chiamata API (timeout, errore 500), il sistema deve visualizzare un feedback visivo non intrusivo (Toast/Alert) senza bloccare l'utente su una pagina bianca, mantenendo lo stato del form intatto per un eventuale nuovo tentativo.

## 3. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio richiesta con motivazione valida e alloggio richiesto
  GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione contenente 150 caratteri
  AND seleziona la checkbox "Necessità alloggio"
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema disabilita il pulsante e mostra lo stato di caricamento
  AND invia con successo il payload JSON al backend contenente motivazione e preferenza alloggio
```

```gherkin
SCENARIO: S02 - Invio richiesta con motivazione valida e alloggio non richiesto
  GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione contenente 150 caratteri
  AND NON seleziona la checkbox "Necessità alloggio"
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema disabilita il pulsante e mostra lo stato di caricamento
  AND invia con successo il payload JSON al backend contenente motivazione e valore falso per alloggio
```

```gherkin
SCENARIO: S03 - Inibizione invio per superamento limite caratteri motivazione
  GIVEN un utente autenticato visualizza il form di prenotazione
  AND l'utente inserisce una motivazione contenente 550 caratteri
  WHEN l'utente tenta di cliccare sul pulsante "Partecipa"
  THEN il sistema evidenzia la casella con bordo rosso e mostra messaggio "Limite superato"
  AND disabilita il pulsante impedendo l'invio della richiesta
```

```gherkin
SCENARIO: S04 - Gestione errore server durante sottomissione
  GIVEN un utente autenticato ha compilato correttamente il form
  WHEN l'utente clicca su "Partecipa" e il backend restituisce un errore HTTP 500 o timeout
  THEN il sistema visualizza un messaggio di errore tramite Toast
  AND riabilita i controlli del form permettendo all'utente di correggere e riprovare
```

## 4. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
| :--- | :--- | :--- |
| **REQ-FE3-01** (Preferenze) | Si presume che le preferenze oltre all'alloggio (menzionate genericamente nel Canvas come "altre preferenze connesse") non siano implementate in questa specifica versione del form. | Quali altre preferenze specifiche devono essere gestite dal form? Se ne richiedono altre (es. dieta, accessibilità)? |
| **REQ-FE3-02** (Motivazione) | Si presume che il limite di 500 caratteri sia l'unico vincolo di lunghezza applicato al campo motivazione. | Esistono vincoli di formato specifici per la motivazione (es. regex, divieto di HTML)? |
| **REQ-FE3-04** (Errori) | Si presume che il comportamento post-errore sia sempre il ripristino dello stato iniziale del form. | Il sistema deve salvare uno schizzo della richiesta in locale (draft) prima dell'errore? |
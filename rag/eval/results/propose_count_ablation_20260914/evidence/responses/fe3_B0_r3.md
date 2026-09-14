# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Obiettivo della Feature

La presente specifica definisce il comportamento osservabile del modulo `BookingRequestForm` per la compilazione e sottomissione di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo è implementato come componente Client che interagisce con i metadati forniti da un Server Component. Lo scopo è garantire l'inserimento corretto della motivazione, la gestione delle preferenze (es. alloggio) e la corretta gestione dello stato durante la sottomissione alla rete, prevenendo invii duplicati o invalidi.

---

## 2. Regole di Validazione e Comportamento UI

### [REGOLA-UI-01] Disabilitazione del submit su dati invalidi
- **Descrizione:** Il pulsante "Partecipa" deve essere visivamente disabilitato (stato `disabled`) se lo schema Zod rileva che il campo "motivazione" è vuoto o contiene solo spazi bianchi.
- **Effetto in caso di violazione:** L'utente potrebbe inviare un payload nullo al backend, violando la sicurezza e la semantica della richiesta.

### [REGOLA-UI-02] Limite caratteri motivazione
- **Descrizione:** Il campo textarea per la motivazione deve mostrare un contatore dei caratteri residui. Se il testo supera i 500 caratteri (limite normativo), il campo deve evidenziarsi in rosso e il pulsante "Partecipa" deve essere disabilitato.
- **Effetto in caso di violazione:** Il sistema riceve testi eccessivamente lunghi che potrebbero causare errori di parsing o storage nel backend.

### [REGOLA-UI-03] Prevenzione duplicati durante l'invio
- **Descrizione:** Al momento dell'inizio della chiamata API (submit), il componente deve disabilitare immediatamente il pulsante "Partecipa" e mostrare uno stato di caricamento (loading state).
- **Effetto in caso di violazione:** L'utente potrebbe cliccare ripetutamente, generando richieste parallele identiche che causano conflitti di concorrenza o duplicati nel database.

### [REGOLA-UI-04] Gestione errori di rete
- **Descrizione:** In caso di timeout HTTP o errore 500 durante la sottomissione, il sistema deve mostrare un messaggio di errore visivo (Toast) e ripristinare lo stato del form, senza bloccare l'interfaccia.
- **Effetto in caso di violazione:** L'utente rimane bloccato su una pagina bianca o non riceve feedback sul fallimento dell'operazione.

---

## 3. Scenari Comportamentali BDD (Gherkin)

```gherkin
SCENARIO: S01 - Invio richiesta con dati validi
  GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione valida inferiore a 500 caratteri
  AND l'utente seleziona le preferenze desiderate (es. alloggio necessario)
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema disabilita il pulsante e mostra uno stato di caricamento
  AND invia la richiesta al backend con successo
  AND visualizza un messaggio di conferma dopo la risposta dell'API
```

```gherkin
SCENARIO: S02 - Invio bloccato per motivazione vuota
  GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
  WHEN l'utente clicca sul pulsante "Partecipa" senza aver inserito nulla nella casella motivazione
  THEN il sistema mantiene il pulsante abilitato solo se lo schema non rileva errore (o lo disabilita se vuoto)
  AND non invia la richiesta al backend
  AND evidenzia visivamente il campo motivazione come mancante
```

```gherkin
SCENARIO: S03 - Invio bloccato per superamento limite caratteri
  GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione contenente più di 500 caratteri
  WHEN l'utente tenta di inviare la richiesta
  THEN il sistema evidenzia il campo in rosso con messaggio "Limite superato"
  AND disabilita il pulsante "Partecipa" impedendo l'invio
```

```gherkin
SCENARIO: S04 - Gestione errore server durante sottomissione
  GIVEN un utente autenticato ha compilato correttamente il form e clicca su "Partecipa"
  WHEN il backend restituisce un errore 500 o un timeout durante l'elaborazione della richiesta
  THEN il sistema mostra un messaggio di errore tramite Toast
  AND ripristina lo stato del pulsante dopo la visualizzazione dell'errore
```

---

## 4. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
| :--- | :--- | :--- |
| Gestione preferenze (alloggio) | Si presume che le preferenze siano semplici booleane o radio buttons come descritto nel Canvas, senza logiche complesse di dipendenza tra campi. | Esistono vincoli specifici sulle combinazioni di preferenze (es. "necessario alloggio" implica automaticamente "necessaria colazione") da validare lato client prima dell'invio? |
| Stato iniziale del form | Si assume che il Server Component fornisca sempre i metadati dell'evento necessari per abilitare la vista del form, anche se l'evento è tecnicamente "full" (la gestione della disponibilità residua non è compito del form). | Come deve comportarsi esattamente l'UI se il Server Component ritarda la risposta dei metadati oltre un certo threshold? Il form deve essere nascosto o mostrato in stato di loading globale? |
| Gestione Toast Errori | Si assume che la libreria `sonner` (o componente equivalente shadcn) sia configurata per mostrare i toast automaticamente quando il client API restituisce uno stato di errore. | Qual è il tempo di permanenza del messaggio di errore prima della chiusura automatica? Deve essere possibile chiuderlo manualmente dall'utente? |
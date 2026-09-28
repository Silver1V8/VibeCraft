# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## Inventario delle funzionalità

| Funzionalità | Ancoraggio al Canvas o alla fonte | Casi previsti (nominale / negativo) | Riferimento agli scenari o al punto aperto |
| :--- | :--- | :--- | :--- |
| **F1** | Sezione 2 (Entities), Sezione 4 (Structure): Gestione contesto evento e recupero metadati lato server. | Nominale: Caricamento metadati evento riuscito.<br>Negativo: Evento non trovato o errore rete. | S01, S02 |
| **F2** | Sezione 2 (Requirements), Sezione 4 (Structure): Rendering campi input (Textarea, Checkbox) e stato iniziale form vuoto. | Nominale: Campi renderizzati correttamente.<br>Negativo: Errore di rendering UI (fallback). | S03, S04 |
| **F3** | Sezione 2 (Requirements), Sezione 6 (Norms): Validazione schema Zod su lunghezza testo e tipi booleani. | Nominale: Input valido accettato.<br>Negativo: Superamento limite caratteri o tipo errato. | S05, S06 |
| **F4** | Sezione 2 (Requirements), Sezione 3 (Approach): Gestione stato submit e disabilitazione pulsante via React Hook Form. | Nominale: Submit riuscito, UI aggiornata.<br>Negativo: Timeout o errore server (Toast). | S07, S08 |
| **F5** | Sezione 2 (Requirements), Sezione 3 (Approach): Inibizione input invalido e prevenzione duplicati lato client. | Nominale: Pulsante disabilitato su dati vuoti.<br>Negativo: Tentativo doppio invio bloccato. | S09, S10 |
| **F6** | Sezione 2 (Requirements), Sezione 3 (Approach): Gestione feedback visivo e stato loading asincrono. | Nominale: Spinner visibile durante chiamata API.<br>Negativo: Errore di rete gestito con Toast. | S11, S12 |

---

## Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Caricamento contesto evento riuscito
  GIVEN un utente autenticato naviga sulla pagina di dettaglio di un EVENTO attivo
  AND il componente Server Component recupera con successo i metadati dell'evento
  WHEN l'utente visualizza la pagina contenente il form di prenotazione
  THEN il sistema renderizza il form con i dati contestuali dell'EVENTO disponibili
```

```gherkin
SCENARIO: S02 - Caricamento contesto evento fallito
  GIVEN un utente autenticato naviga sulla pagina di dettaglio di un EVENTO
  AND la chiamata al Server Component per recuperare i metadati dell'evento fallisce (timeout o errore rete)
  WHEN l'utente tenta di visualizzare il form di prenotazione
  THEN il sistema non mostra il form e visualizza uno stato di errore generico senza bloccare la navigazione
```

```gherkin
SCENARIO: S03 - Rendering iniziale del form vuoto
  GIVEN un utente autenticato accede al modulo di creazione richiesta per un EVENTO valido
  WHEN il componente Client Component inietta lo schema Zod e inizializza React Hook Form
  THEN l'interfaccia mostra un Textarea vuoto per la motivazione e Checkbox non selezionati per le preferenze
```

```gherkin
SCENARIO: S04 - Rendering campi preferenze opzionali
  GIVEN un utente autenticato accede al modulo di creazione richiesta
  AND il contesto evento include opzioni specifiche come "necessità alloggio"
  WHEN il sistema renderizza i controlli UI per le preferenze
  THEN l'interfaccia espone Checkbox o Radio Button corrispondenti alle preferenze indicate nel contesto
```

```gherkin
SCENARIO: S05 - Validazione testo motivazione troppo lungo
  GIVEN un utente autenticato inserisce una motivazione nella casella Textarea
  AND la lunghezza del testo supera i 500 caratteri definiti dallo schema Zod
  WHEN l'utente tenta di inviare il form o cambia input
  THEN il sistema evidenzia il campo in rosso, mostra il contatore negativo e disabilita il pulsante "Partecipa"
```

```gherkin
SCENARIO: S06 - Validazione testo motivazione vuoto
  GIVEN un utente autenticato non inserisce alcun testo nella casella Textarea
  AND lo schema Zod rileva il campo come obbligatorio o invalido per contenuto nullo
  WHEN l'utente tenta di inviare il form
  THEN il sistema disabilita visivamente il pulsante "Partecipa" e evidenzia il campo come mancante
```

```gherkin
SCENARIO: S07 - Invio form con dati validi
  GIVEN un utente autenticato compila correttamente la motivazione entro i limiti di caratteri
  AND seleziona le preferenze desiderate (es. alloggio necessario)
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema disabilita il pulsante, mostra uno spinner di caricamento e invia il payload al backend
```

```gherkin
SCENARIO: S08 - Invio form con errore server (500)
  GIVEN un utente autenticato compila correttamente il form e clicca su "Partecipa"
  AND il backend restituisce un errore 500 durante la sottomissione della RICHIESTA
  THEN il sistema mostra un messaggio di errore Toast all'utente e riabilita il pulsante dopo un timeout
```

```gherkin
SCENARIO: S09 - Inibizione input su dati vuoti
  GIVEN un utente autenticato accede al form con campi vuoti
  AND lo schema Zod rileva l'assenza di dati obbligatori (motivazione)
  WHEN l'utente tenta di interagire con il pulsante di sottomissione
  THEN il sistema mantiene il pulsante disabilitato finché non vengono inseriti dati validi
```

```gherkin
SCENARIO: S10 - Prevenzione doppio invio durante timeout
  GIVEN un utente autenticato ha cliccato su "Partecipa" e la chiamata API è in corso (loading state attivo)
  AND l'utente tenta di cliccare nuovamente sul pulsante prima della risposta del server
  THEN il sistema ignora il secondo click mantenendo lo stato disabled del pulsante
```

```gherkin
SCENARIO: S11 - Gestione timeout HTTP lato client
  GIVEN un utente autenticato invia una richiesta di prenotazione
  AND la chiamata API non riceve risposta entro il tempo massimo previsto (timeout)
  WHEN il sistema rileva l'interruzione della connessione o il silenzio del server
  THEN il sistema visualizza un Toast di errore "Connessione persa" e riabilita l'interfaccia
```

```gherkin
SCENARIO: S12 - Feedback visivo stato loading
  GIVEN un utente autenticato ha completato la compilazione del form
  AND clicca sul pulsante "Partecipa" attivando la chiamata asincrona
  THEN il sistema sostituisce il testo del pulsante con uno spinner e blocca l'input per evitare duplicati
```

---

## Punti aperti

| Funzionalità coinvolta | Assunzione proposta DA CONFERMARE | Domanda aperta esplicita |
| :--- | :--- | :--- |
| **F1** (Recupero metadati) | Si assume che in caso di errore di rete totale durante il caricamento del contesto, l'utente possa comunque navigare altrove ma non inviare form. | Come comportarsi se l'errore è temporaneo e il backend torna online immediatamente dopo? È necessario un retry automatico o una notifica "Riprova più tardi"? |
| **F6** (Feedback visivo) | Si assume che il Toast di errore sia sufficiente per comunicare fallimenti senza necessità di log dettagliati lato client. | Se l'errore è specifico (es. "Evento esaurito"), deve essere mostrato un messaggio diverso generico? Il Canvas non specifica la granularità dell'errore restituito dal backend. |
| **F3** (Validazione Zod) | Si assume che lo schema Zod sia configurato per bloccare l'invio ma non per mostrare messaggi di errore personalizzati oltre a quelli standard ("Limite superato"). | Se il backend richiede un formato specifico per le preferenze (es. JSON interno), come gestisce lo schema Zod la validazione di oggetti complessi? Il Canvas menziona solo boole/radio buttons. |
# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Inventario delle funzionalità

| Funzionalità | Ancoraggio al Canvas o alla fonte | Casi previsti (nominale / negativo) | Riferimento agli scenari o al punto aperto |
| :--- | :--- | :--- | :--- |
| **F1** | Sezione 2 (Entities), Sezione 4 (Structure). Gestione del contesto evento e recupero metadati lato server. | Nominale: Caricamento metadati evento riuscito.<br>Negativo: Evento non trovato o errore rete durante il fetch iniziale. | S01, S02 |
| **F2** | Sezione 2 (Requirements), Sezione 4 (Structure). Rendering dinamico dei campi input (Textarea e Checkbox/Select). | Nominale: Input renderizzati correttamente con placeholder.<br>Negativo: Errore di rendering UI o layout rotto. | S03, S04 |
| **F3** | Sezione 2 (Requirements), Sezione 5 (Operations). Validazione sintattica lato client tramite schema Zod. | Nominale: Input validi accettati.<br>Negativo: Input vuoti o superamento lunghezza massima bloccano il submit. | S05, S06 |
| **F4** | Sezione 3 (Approach), Sezione 5 (Operations). Gestione dello stato di sottomissione e feedback visivo (Loading/Toast). | Nominale: Submit riuscito, UI aggiornata.<br>Negativo: Timeout o errore server (500) gestito con Toast. | S07, S08 |

---

## 2. Scenari Comportamentali BDD (Gherkin)

```gherkin
SCENARIO: S01 - Inizializzazione contesto evento
  GIVEN un utente autenticato naviga sulla pagina di dettaglio di un EVENTO attivo
  WHEN il componente Server Component recupera i metadati dell'evento
  THEN il sistema visualizza i dettagli dell'evento e rende disponibile il form
```

```gherkin
SCENARIO: S02 - Inizializzazione contesto evento fallito
  GIVEN un utente autenticato naviga sulla pagina di dettaglio di un EVENTO non esistente
  WHEN il componente Server Component tenta di recuperare i metadati dell'evento
  THEN il sistema mostra un messaggio di errore "Evento non trovato" e non renderizza il form
```

```gherkin
SCENARIO: S03 - Rendering campi input validi
  GIVEN un utente autenticato visualizza il form per un EVENTO valido
  WHEN il sistema carica i componenti UI (Textarea, Checkbox) con dati iniziali vuoti
  THEN l'interfaccia mostra correttamente i campi "Motivazione" e "Preferenze alloggio" abilitati
```

```gherkin
SCENARIO: S04 - Rendering campi input in caso di errore UI
  GIVEN un utente autenticato visualizza il form per un EVENTO valido
  WHEN il sistema tenta di renderizzare i componenti UI ma incontra un errore di layout
  THEN l'interfaccia mostra uno stato di fallback o un messaggio generico di rendering non riuscito
```

```gherkin
SCENARIO: S05 - Validazione input vuoto
  GIVEN un utente autenticato visualizza il form con campi vuoti
  WHEN l'utente tenta di premere il pulsante "Partecipa" senza inserire nulla
  THEN il sistema disabilita visivamente il pulsante e non invia la richiesta al backend
```

```gherkin
SCENARIO: S06 - Validazione input troppo lungo
  GIVEN un utente autenticato inserisce una motivazione di 550 caratteri nel campo textarea
  WHEN l'utente tenta di premere il pulsante "Partecipa"
  THEN il sistema evidenzia il campo in rosso, mostra il messaggio "Limite superato" e disabilita il submit
```

```gherkin
SCENARIO: S07 - Sottomissione richiesta con successo
  GIVEN un utente autenticato compila correttamente tutti i campi del form (motivazione < 500 char)
  WHEN l'utente preme il pulsante "Partecipa" e la chiamata API al backend risponde con successo
  THEN il sistema mostra uno stato di loading, poi un Toast di conferma e disabilita il form
```

```gherkin
SCENARIO: S08 - Gestione errore server durante sottomissione
  GIVEN un utente autenticato compila correttamente tutti i campi del form
  WHEN l'utente preme "Partecipa" ma il backend restituisce un errore HTTP 500 o timeout
  THEN il sistema mostra un Toast di errore generico senza bloccare la pagina e riabilita gli input dopo un ritardo
```

---

## 3. Punti aperti

| Funzionalità coinvolta | Assunzione proposta DA CONFERMARE | Domanda aperta |
| :--- | :--- | :--- |
| **F2** | Si assume che il rendering di layout rotto mostri un fallback generico invece di crashare l'applicazione. | Come comportarsi esattamente se `shadcn/ui` non supporta un certo componente richiesto dal Canvas? (Fallback UI vs Errore). |
| **F4** | Si assume che dopo un errore 500 il form venga riabilitato automaticamente dopo un timeout fisso (es. 3s). | Qual è la durata esatta del ritardo di riabilitazione degli input in caso di errore transitorio? |
# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## Inventario delle funzionalità

| Funzionalità | Ancoraggio al Canvas o alla fonte | Casi previsti (nominale / negativo) | Riferimento agli scenari o al punto aperto |
| :--- | :--- | :--- | :--- |
| **F1** | Sezione 2 (Entities), Sezione 4 (Structure). Gestione input utente e validazione schema. | Nominale: Inserimento testo valido.<br>Negativo: Testo vuoto o troppo lungo. | S01, S02 |
| **F2** | Sezione 2 (Requirements), Sezione 5 (Operations). Gestione preferenze booleane (alloggio). | Nominale: Selezione opzione alloggio.<br>Negativo: Tentativo di invio senza selezione se obbligatorio. | S03, S04 |
| **F3** | Sezione 4 (Structure), Sezione 7 (Safeguards). Gestione stato submit e feedback UI. | Nominale: Submit riuscito con Toast.<br>Negativo: Errore server con Toast di errore. | S05, S06 |

---

## Scenari BDD

```gherkin
SCENARIO: S01 - Compilazione form con motivazione valida
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione di 250 caratteri nel campo textarea
  WHEN clicca sul pulsante "Partecipa"
  THEN lo schema Zod valida la lunghezza del testo
  AND il sistema disabilita il pulsante durante l'invio
  AND invia con successo il payload al backend
```

```gherkin
SCENARIO: S02 - Blocco invio per motivazione vuota
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND il campo motivazione è vuoto o contiene solo spazi bianchi
  WHEN l'utente tenta di cliccare sul pulsante "Partecipa"
  THEN lo schema Zod rileva il dato mancante
  AND il sistema evidenzia il campo in rosso
  AND disabilita visivamente il pulsante "Partecipa"
```

```gherkin
SCENARIO: S03 - Selezione della preferenza alloggio
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente attiva la checkbox relativa alla necessità di alloggio
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema include la flag "alloggio: true" nel payload
  AND invia la richiesta al backend con successo
```

```gherkin
SCENARIO: S04 - Tentativo di invio senza preferenze obbligatorie
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND le preferenze di alloggio sono configurate come obbligatorie dal backend
  AND l'utente non seleziona alcuna opzione nelle preferenze
  WHEN tenta di cliccare sul pulsante "Partecipa"
  THEN lo schema Zod rileva la mancanza del dato obbligatorio
  AND il sistema evidenzia i campi mancanti in rosso
  AND disabilita il pulsante fino alla correzione
```

```gherkin
SCENARIO: S05 - Invio riuscito con feedback visivo
  GIVEN un UTENTE autenticato ha compilato correttamente tutti i campi del form
  WHEN clicca sul pulsante "Partecipa" e la chiamata API risponde con successo
  THEN il sistema mostra un messaggio Toast di conferma
  AND ripristena lo stato abilitato dei controlli (se previsti per riutilizzo)
```

```gherkin
SCENARIO: S06 - Gestione errore lato server durante l'invio
  GIVEN un UTENTE autenticato ha compilato correttamente tutti i campi del form
  WHEN clicca sul pulsante "Partecipa" e la chiamata API fallisce (es. timeout o errore 500)
  THEN il sistema mostra un messaggio Toast di errore generato da sonner
  AND non duplica l'invio della richiesta
```

---

## Punti aperti

| Funzionalità coinvolta | Assunzione proposta DA CONFERMARE | Domanda aperta |
| :--- | :--- | :--- |
| **F2** | Le preferenze di alloggio sono sempre obbligatorie per tutti gli eventi o solo per alcuni? | Il Canvas menziona "altre preferenze connesse" ma non specifica se siano obbligatorie. Assunzione: Solo "alloggio" è gestito esplicitamente come booleano obbligatorio negli scenari S03/S04. Se altre preferenze esistono, devono essere aggiunte a F2 e coperte da nuovi scenari. |
| **F1** | Il limite di 500 caratteri (da spec_form_1.4.md) è applicato anche qui o c'è un limite diverso per FE3? | La specifica normativa impone 500 caratteri. Assunzione: Questo limite si applica a FE3. Se il Canvas intendeva un limite diverso, va chiarito. Attualmente coperto da S02 (vuoto) e implicitamente da S01 (valido). |
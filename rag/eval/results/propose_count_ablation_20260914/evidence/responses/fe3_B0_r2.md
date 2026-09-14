# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Obiettivo e Logica del Form

La presente specifica definisce il comportamento osservabile della feature **FE3**, relativa alla compilazione e sottomissione interattiva di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo, implementato come componente Client React, gestisce l'inserimento della motivazione e delle preferenze (es. alloggio), valida i dati lato client prima dell'invio al backend e gestisce lo stato di caricamento per prevenire duplicati accidentali.

Il form è accessibile all'interno del contesto dell'utente loggato (`UTENTE`) e deve garantire che il payload inviato contenga esclusivamente dati coerenti con le regole sintattiche definite (lunghezza testo, tipi booleani). La sottomissione finale delega la persistenza al backend, mentre il frontend si occupa di UI feedback e controllo input.

---

## 2. Scenari Comportamentali BDD (Gherkin)

```gherkin
SCENARIO: S01 - Invio richiesta con dati validi
  GIVEN un utente autenticato visualizza la pagina di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione di 200 caratteri nel campo dedicato
  AND seleziona la preferenza "Necessità alloggio" tramite il controllo UI
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema disabilita immediatamente il pulsante e mostra uno stato di caricamento
  AND invia con successo il payload JSON al backend contenente motivazione e preferenze
  AND visualizza un messaggio di conferma dopo la risposta positiva del server
```

```gherkin
SCENARIO: S02 - Inibizione invio per motivazione vuota
  GIVEN un utente autenticato visualizza la pagina di prenotazione per un EVENTO attivo
  WHEN tenta di cliccare sul pulsante "Partecipa" senza aver inserito nulla nella casella motivazione
  THEN il sistema impedisce l'invio del payload al backend
  AND mantiene il pulsante abilitato solo se lo schema Zod rileva dati validi, altrimenti lo disabilita
  AND evidenzia visivamente il campo motivazione come mancante secondo le regole di validazione UI
```

```gherkin
SCENARIO: S03 - Gestione superamento limite caratteri motivazione
  GIVEN un utente autenticato visualizza la pagina di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione contenente 550 caratteri nel campo dedicato
  THEN il sistema evidenzia il campo con un bordo rosso e mostra un contatore dei caratteri residui negativo
  AND disabilita il pulsante "Partecipa" impedendo la sottomissione del payload invalido
```

```gherkin
SCENARIO: S04 - Gestione errore di rete durante la sottomissione
  GIVEN un utente autenticato ha compilato correttamente il form e clicca su "Partecipa"
  AND il backend restituisce una risposta HTTP con codice 500 o un timeout durante l'elaborazione
  THEN il sistema mostra un alert Toast di errore generato dalla libreria UI standard
  AND ripristina lo stato del pulsante dopo la visualizzazione del messaggio di errore
```

---

## 3. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
| :--- | :--- | :--- |
| **Gestione Preferenze (Alloggio)** | Si assume che il campo "Necessità alloggio" sia l'unico campo preferenziale gestito in questa specifica. | Il Canvas menziona "altre preferenze connesse". È necessario aggiungere scenari per campi come "Dieta", "Accessibilità" o lasciarli fuori scope? Se sì, quali sono i vincoli di validazione per questi nuovi campi? |
| **Feedback Visivo Loading** | Si assume che lo stato di caricamento sia gestito esclusivamente tramite UI standard (spinner) senza interruzioni dell'utente. | Come comportarsi se l'utente modifica il form mentre è attivo lo stato di loading? È necessario uno scenario per la cancellazione del payload in caso di errore di rete parziale o timeout prolungato? |
| **Validazione Zod** | Si assume che lo schema Zod sia configurato con un limite rigido a 500 caratteri come da vincolo normativo. | Il Canvas non specifica il comportamento esatto se l'utente copia-incolla testo formattato (es. tabulazioni, nuovi linee). È necessario validare la lunghezza "visuale" o quella grezza? |
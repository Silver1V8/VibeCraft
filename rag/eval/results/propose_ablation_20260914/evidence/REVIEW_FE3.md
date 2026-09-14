# Schede FE3

Stato: human_reviewed.
Revisore: revisione umana condotta con assistenza di un modello (Claude), verdetti approvati dall'umano.
Data: 14 settembre 2026.

[Criteri](REVIEW_CRITERIA.md) · [Canvas congelato](inputs/fe3_canvas.md)

Fonti integrali: [spec_form_1.4.md](inputs/spec_form_1.4.md)

Compilare i campi dopo ogni risposta. L'ordine è per codice campione, non per esecuzione o template.

---

## Campione P03

### Risposta integrale

# Specifiche Tecniche — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Descrizione della Feature

La feature **FE3** implementa un modulo interattivo per la compilazione e sottomissione di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo, denominato `BookingRequestForm`, permette all'utente (`UTENTE`) di inserire una motivazione testuale e di gestire preferenze relative all'alloggio. L'interfaccia segue l'architettura Container/Presentational Components: un Server Component fornisce il contesto dell'evento, mentre il Client Component gestisce lo stato del form, la validazione tramite schema Zod e la sottomissione asincrona tramite TanStack Query. Il sistema garantisce l'integrità dei dati prevenendo invii duplicati e gestendo gli errori di rete con feedback visivi immediati.

---

## 2. Scenari Comportamentali BDD (Gherkin)

```gherkin
SCENARIO: S01 - Invio riuscito della richiesta di partecipazione
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione valida inferiore a 500 caratteri
  AND seleziona la preferenza "Necessità alloggio" come falsa
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema disabilita immediatamente il pulsante e mostra uno stato di caricamento
  AND invia con successo il payload JSON al backend
  AND visualizza un messaggio di conferma Toast indicando la richiesta inviata
```

```gherkin
SCENARIO: S02 - Invio bloccato per motivazione vuota
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  WHEN l'utente clicca sul pulsante "Partecipa" senza inserire alcuna motivazione
  THEN il sistema evidenzia in rosso il campo della motivazione come obbligatorio
  AND disabilita il pulsante "Partecipa" impedendo la sottomissione
  AND non invia alcun payload al backend
```

```gherkin
SCENARIO: S03 - Invio bloccato per superamento limite caratteri
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione di 550 caratteri nella casella di testo
  THEN il sistema evidenzia in rosso il campo della motivazione
  AND mostra un contatore dei caratteri residui negativo o a zero
  AND disabilita il pulsante "Partecipa" impedendo la sottomissione
```

```gherkin
SCENARIO: S04 - Gestione errore di rete durante la sottomissione
  GIVEN un UTENTE autenticato ha compilato correttamente il form e clicca su "Partecipa"
  AND il backend restituisce un errore HTTP 500 o un timeout durante l'elaborazione
  THEN il sistema interrompe lo stato di caricamento del pulsante
  AND visualizza un messaggio di errore Toast generato da sonner con testo descrittivo
  AND riabilita i controlli del form permettendo all'utente di correggere e riprovare
```

```gherkin
SCENARIO: S05 - Gestione input non valido nel campo preferenze alloggio
  GIVEN un UTENTE autenticato visualizza il form per un EVENTO attivo
  AND l'utente seleziona la preferenza "Necessità alloggio" come vera
  WHEN l'utente tenta di inviare il form senza aver toccato altri campi critici
  THEN il sistema accetta la selezione booleana come valida
  AND include correttamente lo stato della preferenza nel payload JSON inviato
```

```gherkin
SCENARIO: S06 - Prevenzione duplicati durante la chiamata API
  GIVEN un UTENTE autenticato ha cliccato su "Partecipa" per inviare una richiesta
  AND il sistema sta elaborando l'invio asincrono tramite TanStack Query
  WHEN l'utente tenta di cliccare nuovamente sul pulsante "Partecipa" prima della risposta
  THEN il sistema mantiene lo stato del pulsante disabilitato e mostra uno spinner
  AND impedisce la generazione di una seconda chiamata API parallela
```

```gherkin
SCENARIO: S07 - Reset dello stato form dopo successo o errore
  GIVEN un UTENTE ha completato l'invio della richiesta (sia con successo che con errore)
  WHEN il messaggio Toast scompare dalla UI dopo alcuni secondi
  THEN il sistema riabilita i controlli del form e resetta lo stato di caricamento
  AND permette all'utente di modificare nuovamente la motivazione o le preferenze
```

### Valutazione umana di P03

- Stato: human\_reviewed

- Ambiguità dichiarate correttamente (ID Q): 0 / 3.
  Q1 non dichiarato e risolto in silenzio: S02 impone come requisito che
  la motivazione vuota blocchi l'invio, mentre REGOLA-FORM-01 la
  qualifica come campo opzionale. È un THEN che decide un conflitto tra
  fonti, non un'assunzione dichiarata.
  Q2 (altre preferenze, valori ammessi, errori) non menzionato.
  Q3 (interfaccia API, schema, feedback di successo) non menzionato:
  la risposta usa il payload JSON senza segnalare che endpoint e schema
  non sono fissati.

- Funzionalità con nominale e negativo coperti (ID F):
  FE3-F1 (S01 nominale; S02, S03 negativi) — con riserva: il negativo
  S02 poggia sul conflitto Q1 non dichiarato.
  FE3-F3 (S01, S06 nominali; S04 negativo).

- Funzionalità con copertura parziale (ID F e caso mancante):
  FE3-F2 — nominale presente (S05 trasmette la preferenza nel payload),
  caso negativo assente. S05 è titolato "input non valido" ma il corpo
  verifica un input valido accettato: titolo incoerente col contenuto,
  non è un negativo.

- Casi mancanti dichiarati esplicitamente: nessuno.

- Omissioni non dichiarate:
  FE3-F4 assente per intero (idoneità e richiesta già attiva), benché
  REGOLA-INT-01 la prescriva esplicitamente e spec\_form riporti anche il
  badge "Sei già iscritto a questo evento". Nessuno scenario la tocca.
  Caso negativo di FE3-F2.
  I tre dubbi preregistrati Q1, Q2, Q3.

- Forma GIVEN/WHEN/THEN e fence:
  7 fence, 7 scenari, un fence per scenario, keyword in maiuscolo.
  S03 privo di WHEN: passa da GIVEN/AND direttamente a THEN.
  S05 ha WHEN ma incoerente con il THEN e con il titolo.

- Note / punti non valutabili:
  S07 innescato dalla scomparsa del toast "dopo alcuni secondi":
  temporizzazione non presente nelle fonti e innesco non osservabile in
  modo affidabile. Contato come affermazione non supportata (A8), non
  come omissione di funzionalità.
  Il wording dell'errore non è valutato, come prescrive il protocollo per
  l'incoerenza interna della fonte; la risposta non sostiene che sia
  univoco.
  Scheda redatta con assistenza di un modello e revisionata dall'umano
  contro le fonti congelate. I verdetti A3-A7 erano stati inizialmente
  sospettati come non supportati e sono stati corretti in supported dopo
  verifica diretta delle fonti.

Affermazioni normative atomiche:

| ID | Citazione dalla risposta                           | Verdetto    | Fonte e passaggio                                        | Motivazione                                              |
| -- | -------------------------------------------------- | ----------- | -------------------------------------------------------- | -------------------------------------------------------- |
| A1 | motivazione valida inferiore a 500 caratteri       | supported   | spec\_form REGOLA-VAL-01 (riga 54)                       | limite fissato dalla fonte                               |
| A2 | S02: motivazione vuota blocca l'invio              | conflicted  | Canvas Safeguards vs spec\_form REGOLA-FORM-01 (riga 49) | conflitto Q1 risolto senza dichiararlo                   |
| A3 | contatore dei caratteri residui negativo o a zero  | supported   | spec\_form REGOLA-VAL-01 (righe 54, 92)                  | contatore decrementale e valore negativo previsti        |
| A4 | Toast generato da sonner                           | supported   | Canvas §7 Safeguards (riga 40)                           | sonner indicato, pur con riserva "se previsto da shadcn" |
| A5 | Zod, TanStack Query, Server/Client Component       | supported   | Canvas §3 (righe 16-18), §4 (riga 23), §6 (riga 35)      | librerie prescritte dal Canvas                           |
| A6 | errore HTTP 500 o timeout                          | supported   | Canvas §7 Safeguards (riga 40)                           | entrambi i casi citati                                   |
| A7 | payload JSON al backend                            | supported   | Canvas §5 (riga 30), spec\_form §4 (riga 84)             | payload e formato JSON presenti                          |
| A8 | reset dopo scomparsa del Toast dopo alcuni secondi | unsupported | nessuna fonte                                            | temporizzazione e innesco non prescritti                 |

Rapporto supported / valutabili: 6 / 8. Unsupported: 1. Conflicted: 1.

Rilievo sul protocollo, da riportare tale e quale: la risposta omette
react-hook-form, prescritto come obbligatorio dal Canvas §6 (riga 35),
e nomina invece la gestione stato del Client Component in modo generico.
Il protocollo non prevede un campo per le prescrizioni della fonte
ignorate quando non corrispondono a una funzionalità attesa: è diverso
sia da un requisito inventato sia da un caso mancante. Valutare se
aggiungere un criterio dedicato prima delle schede successive.


---

## Campione P04

### Risposta integrale

# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Obiettivo della Feature

La presente specifica definisce il comportamento osservabile del modulo `BookingRequestForm` per la compilazione e sottomissione di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo è implementato come componente Client che interagisce con i metadati forniti da un Server Component. Lo scopo è garantire l'inserimento corretto della motivazione, la gestione delle preferenze (es. alloggio) e la corretta gestione dello stato durante la sottomissione, prevenendo duplicazioni e invii di dati non validi.

---

## 2. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio form con dati validi
  GIVEN un utente autenticato visualizza il form per un EVENTO attivo
  AND l'utente inserisce una motivazione di 150 caratteri nel campo textarea
  AND seleziona la checkbox "Necessità alloggio"
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema disabilita immediatamente il pulsante e mostra uno stato di caricamento
  AND invia con successo il payload JSON al backend contenente motivazione e preferenze
```

```gherkin
SCENARIO: S02 - Inibizione invio per motivazione vuota
  GIVEN un utente autenticato visualizza il form per un EVENTO attivo
  WHEN l'utente clicca sul pulsante "Partecipa" senza aver inserito nulla nel campo motivazione
  THEN il sistema evidenzia il campo textarea con un bordo rosso
  AND disabilita visivamente il pulsante "Partecipa" impedendo la chiamata API
```

```gherkin
SCENARIO: S03 - Gestione errore di sottomissione lato server
  GIVEN un utente autenticato ha compilato correttamente tutti i campi del form
  WHEN clicca su "Partecipa" ma il backend restituisce un errore HTTP 500 o timeout
  THEN il sistema mostra un messaggio di errore tramite componente Toast nella UI
  AND riabilita il pulsante "Partecipa" permettendo al utente di riprovare l'invio
```

```gherkin
SCENARIO: S04 - Blocco form per utente già iscritto all'evento
  GIVEN un utente autenticato naviga verso la pagina di creazione richiesta per un EVENTO
  AND il sistema rileva che l'utente possiede già una RICHIESTA in stato 'APPROVATA' per tale evento
  WHEN tenta di visualizzare o compilare il form standard
  THEN il sistema sostituisce i campi del form con un badge informativo recante "Sei già iscritto"
```

---

## 3. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
| :--- | :--- | :--- |
| Gestione Preferenze (Alloggio) | La selezione della checkbox per l'alloggio è l'unica preferenza gestita in questa specifica iterazione. | Esistono altre preferenze connesse menzionate nel Canvas ("altre preferenze") che devono essere implementate come campi aggiuntivi o sono state omise intenzionalmente? |
| Validazione Lunghezza Testo | Il limite di 500 caratteri per la motivazione è applicato rigorosamente dal client prima dell'invio. | Se l'utente copia-incolla un testo superiore a 500 caratteri, il sistema deve troncare automaticamente o mostrare errore? (Attualmente coperto solo da S02 che blocca invio vuoto). |
| Stato di Loading | Lo stato di caricamento è visibile solo durante la chiamata API. | Il sistema deve mostrare uno stato di "loading" anche se l'utente modifica i campi mentre la chiamata è in corso, o il form diventa read-only? |

### Valutazione umana di P04

- Stato: human_reviewed
- Ambiguità dichiarate correttamente (ID Q): 1 / 3.
  Q2 dichiarato correttamente: il punto aperto su Gestione Preferenze
  chiede esplicitamente se esistano altre preferenze oltre all'alloggio,
  con assunzione dichiarata e non imposta in un THEN. Corrisponde al
  dubbio preregistrato.
  Q1 NON dichiarato e risolto in silenzio: S02 impone come requisito che
  la motivazione vuota blocchi l'invio, mentre REGOLA-FORM-01 la
  qualifica come opzionale. Il conflitto tra fonti non è segnalato in
  nessun punto aperto.
  Q3 NON dichiarato: nessun punto aperto su interfaccia API, schema o
  feedback di successo; S01 usa il payload JSON come se fosse fissato.

- Funzionalità con nominale e negativo coperti (ID F):
  nessuna con entrambi i casi pienamente coperti. Vedi copertura parziale.

- Funzionalità con copertura parziale (ID F e caso mancante):
  FE3-F1 — negativo assente. S01 copre il nominale; il superamento dei
  500 caratteri non ha scenario. S02 copre la motivazione vuota, che è il
  caso conflittuale di Q1, non il limite di lunghezza.
  FE3-F2 — nominale presente (S01 seleziona la checkbox e la trasmette
  nel payload), negativo assente. Coerente con Q2 dichiarato, ma
  dichiarare non equivale a coprire.
  FE3-F3 — negativo presente (S03, errore 500/timeout), nominale presente
  (S01). Manca però il caso doppio click, previsto dal protocollo dentro
  F3: copertura parziale, non completa.
  FE3-F4 — negativo presente (S04, utente con richiesta APPROVATA vede il
  badge), nominale assente: nessuno scenario copre l'utente senza
  richiesta attiva che accede normalmente al form.

- Casi mancanti dichiarati esplicitamente:
  Il caso delle altre preferenze (Q2) è dichiarato come domanda aperta.
  Nessun altro caso mancante è dichiarato come tale: i punti aperti su
  Validazione Lunghezza e Stato di Loading non dichiarano casi mancanti,
  sollevano dettagli nuovi.

- Omissioni non dichiarate:
  Caso negativo di FE3-F1 (superamento 500 caratteri), pur essendo
  prescritto da REGOLA-VAL-01 con feedback e contatore.
  Caso doppio click / prevenzione duplicati di FE3-F3, benché
  l'obiettivo dichiarato in apertura citi la prevenzione delle
  duplicazioni: enunciata e mai coperta.
  Caso nominale di FE3-F4.
  Dubbi Q1 e Q3.

- Forma GIVEN/WHEN/THEN e fence:
  4 fence, 4 scenari, un fence per scenario, keyword in maiuscolo,
  tutti gli scenari hanno GIVEN, WHEN e THEN. Nessun difetto di forma.
  I punti aperti sono in tabella fuori dai fence: non interferiscono
  con il formato degli scenari.

- Note / punti non valutabili:
  Il punto aperto "Validazione Lunghezza Testo" contiene un errore di
  lettura della risposta stessa: afferma che il caso è "attualmente
  coperto solo da S02 che blocca invio vuoto", ma S02 riguarda la
  motivazione vuota, non il limite di 500 caratteri, che non ha alcuno
  scenario. Il punto aperto descrive quindi male la propria copertura.
  Il punto aperto "Stato di Loading" solleva un dettaglio non incluso tra
  i dubbi preregistrati e non prescritto dalle fonti: non aumenta il
  punteggio Q secondo il criterio 2, ma non è un requisito inventato
  perché resta formulato come domanda.
  Scheda redatta con assistenza di un modello e revisionata dall'umano
  contro le fonti congelate.

Affermazioni normative atomiche:

| ID | Citazione dalla risposta | Verdetto | Fonte e passaggio | Motivazione |
|---|---|---|---|---|
| B1 | S02: motivazione vuota impedisce la chiamata API | conflicted | Canvas Safeguards vs spec_form REGOLA-FORM-01 (riga 49) | conflitto Q1 risolto senza dichiararlo |
| B2 | limite di 500 caratteri applicato dal client | supported | spec_form REGOLA-VAL-01 (riga 54) | limite fissato dalla fonte |
| B3 | errore HTTP 500 o timeout con Toast | supported | Canvas §7 Safeguards (riga 40) | entrambi i casi e il Toast citati |
| B4 | payload JSON con motivazione e preferenze | supported | Canvas §5 (riga 30), spec_form §4 (riga 84) | payload e formato presenti |
| B5 | badge "Sei già iscritto" per richiesta APPROVATA | supported | spec_form REGOLA-INT-01 (riga 68), §4 (riga 102) | stato e badge prescritti |
| B6 | disabilita il pulsante e mostra caricamento | supported | spec_form REGOLA-VAL-02 (riga 63) | disabilitazione e spinner prescritti |
| B7 | Client Component con metadati da Server Component | supported | Canvas §3 (riga 16), §4 (riga 23) | architettura prescritta dal Canvas |

Rapporto supported / valutabili: 6 / 7. Unsupported: 0. Conflicted: 1.

Rilievo sul protocollo, da riportare tale e quale: si ripresenta il buco
già segnalato su P03. Qui react-hook-form e Zod, prescritti come
obbligatori dal Canvas §6 (riga 35), non compaiono nella risposta.
Inoltre emerge un secondo caso non previsto dal protocollo: un punto
aperto che descrive in modo errato la copertura della risposta stessa
(vedi Note). Non è un requisito inventato né un'omissione, ma incide
sull'affidabilità di ciò che viene dichiarato. Valutare un criterio
dedicato prima di aggregare.


---

## Campione P06

### Risposta integrale

# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Descrizione della Feature

La feature **FE3** implementa un modulo interattivo per la compilazione e sottomissione di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo, denominato `BookingRequestForm`, è un componente Client che gestisce lo stato dell'input utente (motivazione, preferenze alloggio) tramite `React Hook Form`. I dati vengono validati sintatticamente lato client utilizzando uno schema **Zod** prima della sottomissione asincrona al backend. Il componente Server fornisce il contesto dell'evento e i metadati necessari per il rendering.

## 2. Regole di Validazione e Comportamento UI

### [REGOLA-FE3-01] Limiti del campo motivazione
- **Descrizione:** Il campo `motivazione` è un textarea che accetta testo libero ma non deve superare i 500 caratteri.
- **Effetto in caso di violazione:** Se il numero di caratteri supera 500, il contatore residuo diventa negativo (es. "-10"), il bordo del textarea si evidenzia in rosso e il pulsante di sottomissione viene disabilitato.

### [REGOLA-FE3-02] Gestione preferenze alloggio
- **Descrizione:** Il campo `preferenze` include un controllo booleano per la necessità di "Alloggio".
- **Effetto in caso di violazione:** Non sono previste violazioni sintattiche per questo campo, ma il valore deve essere coerente con lo schema Zod (booleano).

### [REGOLA-FE3-03] Disattivazione anti-click durante l'invio
- **Descrizione:** Al momento della sottomissione (`submit`), il pulsante "Partecipa" viene immediatamente disabilitato e visualizza uno stato di caricamento.
- **Effetto in caso di violazione:** Se l'utente potesse cliccare più volte, si genererebbero chiamate API duplicate che potrebbero causare errori di concorrenza o duplicati nel database backend.

### [REGOLA-FE3-04] Gestione errore di rete lato client
- **Descrizione:** In caso di timeout HTTP o errore 500 durante la chiamata API, il sistema deve mostrare un feedback visivo senza bloccare l'interfaccia.
- **Effetto in caso di violazione:** L'utente rimane bloccato su una pagina bianca o non riceve informazioni sullo stato della richiesta.

### [REGOLA-FE3-05] Inibizione input invalido
- **Descrizione:** Il pulsante "Partecipa" deve essere visivamente disabilitato (`disabled`) finché lo schema `Zod` rileva dati mancanti (es. motivazione vuota).
- **Effetto in caso di violazione:** L'invio di un payload con campi nulli o vuoti al backend, violando i contratti di servizio.

---

## 3. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio richiesta con dati validi
  GIVEN un utente autenticato visualizza il form per l'EVENTO "Conferenza Tech"
  AND l'utente inserisce una motivazione di 120 caratteri nel campo textarea
  AND seleziona la checkbox "Necessità alloggio: Sì"
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema disabilita immediatamente il pulsante e mostra uno spinner
  AND invia con successo il payload JSON al backend tramite TanStack Query
  AND visualizza un messaggio di conferma Toast dopo il completamento della chiamata
```

```gherkin
SCENARIO: S02 - Invio bloccato per motivazione vuota
  GIVEN un utente autenticato visualizza il form per l'EVENTO "Conferenza Tech"
  AND il campo motivazione è vuoto o contiene solo spazi bianchi
  WHEN tenta di cliccare sul pulsante "Partecipa"
  THEN il sistema mantiene il pulsante abilitato solo se lo schema non rileva errore, ma impedisce l'invio
  AND visualizza un messaggio di errore nel form indicando che la motivazione è obbligatoria
```

```gherkin
SCENARIO: S03 - Invio bloccato per superamento limite caratteri
  GIVEN un utente autenticato visualizza il form per l'EVENTO "Conferenza Tech"
  AND l'utente inserisce una motivazione di 550 caratteri nel campo textarea
  WHEN tenta di cliccare sul pulsante "Partecipa"
  THEN il sistema evidenzia il bordo del textarea in rosso
  AND disabilita il pulsante "Partecipa" impedendo la trasmissione dei dati
```

```gherkin
SCENARIO: S04 - Gestione errore server durante sottomissione
  GIVEN un utente autenticato sta compilando il form per l'EVENTO "Conferenza Tech"
  AND l'utente inserisce una motivazione valida e clicca su "Partecipa"
  WHEN il backend restituisce un errore HTTP 500 o un timeout durante la chiamata API
  THEN il sistema visualizza un alert Toast con il messaggio di errore generato da sonner
  AND riabilita il pulsante dopo che lo stato di loading è stato risolto
```

```gherkin
SCENARIO: S05 - Disattivazione dinamica del contatore caratteri
  GIVEN un utente autenticato visualizza il form per l'EVENTO "Conferenza Tech"
  AND l'utente inserisce progressivamente testo fino a raggiungere i 499 caratteri
  WHEN aggiunge un ulteriore carattere portando il totale a 501
  THEN il contatore dei caratteri residui si aggiorna immediatamente mostrando "-1"
  AND il sistema evidenzia visivamente il campo come invalido
```

```gherkin
SCENARIO: S06 - Selezione preferenze alloggio opzionale
  GIVEN un utente autenticato visualizza il form per l'EVENTO "Conferenza Tech"
  AND l'utente lascia la checkbox "Necessità alloggio" deselezionata (falso)
  WHEN clicca sul pulsante "Partecipa" con tutti gli altri campi validi
  THEN il sistema invia il payload JSON con il valore booleano false per la preferenza alloggio
  AND conferma l'invio tramite il feedback visivo standard
```

```gherkin
SCENARIO: S07 - Prevenzione duplicati durante caricamento
  GIVEN un utente autenticato sta inviando una richiesta per l'EVENTO "Conferenza Tech"
  AND il pulsante "Partecipa" è nello stato di caricamento (disabled)
  WHEN l'utente tenta di cliccare ripetutamente sul pulsante prima che la chiamata si concluda
  THEN il sistema ignora tutti i click successivi mantenendo lo stato disabled
  AND evita la generazione di chiamate API parallele duplicate
```

### Valutazione umana di P06

- Stato: human_reviewed
- Ambiguità dichiarate correttamente (ID Q): 0 / 3.
  Nessuna sezione di punti aperti e nessuna domanda formulata.
  Q1 non dichiarato e risolto in silenzio, due volte: REGOLA-FE3-05
  prescrive la disabilitazione per motivazione vuota e S02 impone
  l'obbligatorietà, mentre REGOLA-FORM-01 la qualifica come opzionale.
  Q2 non dichiarato: REGOLA-FE3-02 restringe le preferenze al solo
  booleano alloggio, presentandolo come regola e non come assunzione.
  Q3 non dichiarato: S01 fissa TanStack Query come canale di invio senza
  segnalare che schema e interfaccia non sono definiti.

- Funzionalità con nominale e negativo coperti (ID F):
  FE3-F1 (S01 nominale; S03, S05 negativi).
  FE3-F2 (S01 e S06 nominali, nelle due varianti vero e falso) — vedi
  però Note: il negativo qui non è atteso, essendo il caso preregistrato
  come "da dichiarare senza inventare validazioni".
  FE3-F3 (S01 nominale; S04 errore di rete, S07 doppio click negativi).

- Funzionalità con copertura parziale (ID F e caso mancante):
  nessuna parziale: le tre coperte lo sono su entrambi i casi attesi,
  la quarta è assente.

- Casi mancanti dichiarati esplicitamente: nessuno.

- Omissioni non dichiarate:
  FE3-F4 assente per intero, nominale e negativo. Nessuno scenario e
  nessuna regola toccano l'idoneità o la richiesta già attiva, benché
  REGOLA-INT-01 la prescriva esplicitamente.
  Dubbi Q1, Q2, Q3.

- Forma GIVEN/WHEN/THEN e fence:
  7 fence, 7 scenari, un fence per scenario, keyword in maiuscolo,
  tutti gli scenari hanno GIVEN, WHEN e THEN.
  Difetto sostanziale in S02: il THEN contiene una contraddizione
  interna, "mantiene il pulsante abilitato solo se lo schema non rileva
  errore, ma impedisce l'invio". Non descrive un comportamento
  osservabile univoco e contraddice REGOLA-FE3-05, che prescrive il
  pulsante disabilitato nello stesso caso.

- Note / punti non valutabili:
  S03 e S05 coprono entrambi il superamento dei 500 caratteri, con
  inneschi diversi (click su pulsante disabilitato / aggiornamento del
  contatore). Contati come un solo caso negativo di F1, non due:
  il criterio 4 esclude che una ripetizione valga come nuova copertura.
  S05 è titolato "Disattivazione dinamica del contatore caratteri" ma
  descrive l'aggiornamento del contatore, non una disattivazione:
  titolo incoerente col contenuto.
  S06 è titolato "opzionale" ma verifica la trasmissione del valore
  false: è un secondo caso nominale di F2, non un negativo.
  Questa risposta introduce cinque regole normative proprie
  ([REGOLA-FE3-01]..[REGOLA-FE3-05]) presentate come prescrizioni
  vincolanti, non come assunzioni da confermare. Sono valutate come
  affermazioni normative nella tabella sottostante.
  Scheda redatta con assistenza di un modello e revisionata dall'umano
  contro le fonti congelate.

Affermazioni normative atomiche:

| ID | Citazione dalla risposta | Verdetto | Fonte e passaggio | Motivazione |
|---|---|---|---|---|
| C1 | REGOLA-FE3-01: limite 500 caratteri, contatore negativo, bordo rosso, pulsante disabilitato | supported | spec_form REGOLA-VAL-01 (righe 54-55, 92) | tutti gli effetti prescritti dalla fonte |
| C2 | REGOLA-FE3-02: le preferenze includono un controllo booleano per l'alloggio | conflicted | Canvas Requirements/Operations, Q2 | restringe a regola un punto che la fonte lascia indefinito |
| C3 | REGOLA-FE3-03: pulsante disabilitato con stato di caricamento al submit | supported | spec_form REGOLA-VAL-02 (riga 63) | disabilitazione e spinner prescritti |
| C4 | REGOLA-FE3-04: timeout o errore 500 mostrano feedback senza bloccare l'interfaccia | supported | Canvas §7 Safeguards (riga 40) | casi ed effetto prescritti |
| C5 | REGOLA-FE3-05: pulsante disabilitato finché Zod rileva dati mancanti, es. motivazione vuota | conflicted | Canvas Safeguards vs spec_form REGOLA-FORM-01 (riga 49) | conflitto Q1 imposto come regola |
| C6 | S02: la motivazione è obbligatoria | conflicted | come C5 | stesso conflitto, ribadito in uno scenario |
| C7 | Zod, React Hook Form, Client/Server Component | supported | Canvas §3 (righe 16-17), §6 (riga 35) | librerie prescritte dal Canvas |
| C8 | Toast generato da sonner | supported | Canvas §7 Safeguards (riga 40) | sonner indicato |
| C9 | invio del payload JSON tramite TanStack Query | supported | Canvas §4 (riga 23), spec_form §4 (riga 84) | useMutation e payload JSON presenti |
| C10 | S02: il campo vuoto include "solo spazi bianchi" | unsupported | nessuna fonte | trattamento degli spazi non prescritto |

Rapporto supported / valutabili: 6 / 10. Unsupported: 1. Conflicted: 3.

Rilievo sul protocollo, da riportare tale e quale: terzo caso non
previsto dai criteri. Qui la risposta non si limita a scenari, ma emette
regole normative proprie con identificatori formali. Il protocollo
valuta le affermazioni, ma non distingue tra un'affermazione dentro uno
scenario e una prescrizione presentata come regola numerata: la seconda
pesa di più, perché si presenta come fonte. Valutare se introdurre la
distinzione prima di aggregare, insieme ai due rilievi già aperti su
P03 e P04.


---

## Campione P08

### Risposta integrale

# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Obiettivo della Feature

La presente specifica definisce il comportamento osservabile del modulo `CreateBookingForm` per la compilazione e sottomissione di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo è implementato come componente Client che interagisce con i metadati forniti da un Server Component. Lo scopo è garantire l'inserimento corretto della motivazione, la gestione delle preferenze (es. alloggio) e la corretta gestione dello stato durante la sottomissione alla rete, prevenendo invii duplicati o invalidi.

---

## 2. Requisiti Funzionali e di Validazione

### [REQ-FE3-01] Gestione della Motivazione
Il campo `motivazione` deve accettare testo libero ma non superare i 500 caratteri. Il sistema deve visualizzare un contatore dei caratteri residui. Se il testo supera il limite, l'input deve essere evidenziato e il pulsante di sottomissione disabilitato.

### [REQ-FE3-02] Gestione delle Preferenze
Il modulo deve permettere all'utente di selezionare la necessità di strutture aggiuntive (es. alloggio) tramite controlli booleani o radio buttons. Questi dati devono essere inclusi nel payload di sottomissione insieme alla motivazione.

### [REQ-FE3-03] Prevenzione del Doppio Invio
Durante il ciclo di rete (Round Trip Time) della sottomissione, l'interfaccia deve disabilitare il pulsante "Partecipa" e mostrare uno stato di caricamento per impedire la generazione di richieste parallele.

### [REQ-FE3-04] Gestione Errori di Rete
In caso di fallimento della chiamata API (timeout o errore server), il sistema deve visualizzare un messaggio di feedback all'utente senza bloccare l'interfaccia, permettendo una nuova tentazione dopo che lo stato è tornato a `idle`.

---

## 3. Scenari Comportamentali BDD (Gherkin)

```gherkin
SCENARIO: S01 - Invio form valido con motivazione e preferenze
  GIVEN un utente autenticato visualizza il form per l'EVENTO "Conferenza Tech"
  AND l'utente inserisce una motivazione di 120 caratteri nel campo dedicato
  AND seleziona la preferenza "Necessità alloggio: Sì"
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema valida i campi e disabilita il pulsante mostrando uno spinner
  AND inoltra il payload JSON contenente motivazione e preferenze al backend
```

```gherkin
SCENARIO: S02 - Blocco invio per superamento limite caratteri motivazione
  GIVEN un utente autenticato visualizza il form per l'EVENTO "Conferenza Tech"
  AND l'utente inserisce una motivazione di 550 caratteri nel campo dedicato
  WHEN l'utente tenta di cliccare sul pulsante "Partecipa"
  THEN il sistema evidenzia il campo in rosso con messaggio "Limite superato"
  AND disabilita il pulsante impedendo la trasmissione dei dati
```

```gherkin
SCENARIO: S03 - Gestione errore server durante sottomissione
  GIVEN un utente autenticato ha compilato correttamente il form e cliccato "Partecipa"
  WHEN il backend restituisce un errore HTTP 500 o un timeout durante l'elaborazione
  THEN il sistema visualizza un messaggio di errore tramite Toast
  AND riabilita il pulsante dopo che lo stato del componente ritorna a idle
```

```gherkin
SCENARIO: S04 - Invio form con motivazione vuota
  GIVEN un utente autenticato visualizza il form per l'EVENTO "Conferenza Tech"
  AND il campo motivazione è vuoto o contiene solo spazi bianchi
  WHEN l'utente tenta di cliccare sul pulsante "Partecipa"
  THEN il sistema evidenzia il campo come mancante
  AND disabilita il pulsante impedendo la sottomissione del payload invalido
```

---

## 4. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
| :--- | :--- | :--- |
| Gestione Preferenze (REQ-FE3-02) | Si presume che le preferenze oltre all'alloggio siano gestite da un unico campo booleano o lista fissa. | Qual è l'elenco completo delle preferenze aggiuntive oltre all'alloggio menzionate nell'intervista? Vanno implementate come checkbox multiple o dropdown? |
| Validazione Motivazione (REQ-FE3-01) | Si presume che il limite di 500 caratteri sia assoluto e non dipenda dalla lunghezza dell'evento. | Il limite di 500 caratteri è definito globalmente per tutte le feature o varia in base al tipo di evento? |
| Gestione Errori (REQ-FE3-04) | Si presume che lo stato `idle` venga ripristinato automaticamente dopo un errore senza intervento utente. | È necessario permettere all'utente di cancellare i dati inseriti prima di riprovare, o il form deve essere resettato completamente? |

### Valutazione umana di P08

- Stato: human_reviewed
- Ambiguità dichiarate correttamente (ID Q): 1 / 3.
  Q2 dichiarato correttamente: il punto aperto su Gestione Preferenze
  chiede l'elenco completo delle preferenze oltre all'alloggio e i
  controlli con cui rappresentarle, con assunzione dichiarata e non
  imposta in un THEN. Corrisponde al dubbio preregistrato.
  Q1 NON dichiarato e risolto in silenzio: S04 impone che la motivazione
  vuota blocchi la sottomissione e la qualifica come "payload invalido",
  mentre REGOLA-FORM-01 la dichiara opzionale. Nessun punto aperto
  segnala il conflitto.
  Q3 NON dichiarato: nessun punto aperto su interfaccia, schema o
  feedback di successo.

- Funzionalità con nominale e negativo coperti (ID F):
  FE3-F1 (S01 nominale; S02 negativo, con feedback e disabilitazione).

- Funzionalità con copertura parziale (ID F e caso mancante):
  FE3-F2 — nominale presente (S01 seleziona e trasmette la preferenza),
  negativo non atteso come tale ma il punto indefinito è dichiarato:
  copertura coerente con Q2.
  FE3-F3 — nominale presente (S01), negativo di rete presente (S03),
  ma il caso doppio click non ha scenario: REQ-FE3-03 lo prescrive come
  requisito e nessuno scenario lo verifica.
  FE3-F4 — assente, vedi omissioni.

- Casi mancanti dichiarati esplicitamente:
  Solo il caso delle preferenze aggiuntive (Q2). Nessun altro.

- Omissioni non dichiarate:
  FE3-F4 assente per intero, nominale e negativo: nessun requisito e
  nessuno scenario toccano l'idoneità o la richiesta già attiva, benché
  REGOLA-INT-01 la prescriva.
  Caso doppio click di FE3-F3: enunciato in REQ-FE3-03 e mai verificato
  da uno scenario.
  Dubbi Q1 e Q3.

- Forma GIVEN/WHEN/THEN e fence:
  4 fence, 4 scenari, un fence per scenario, keyword in maiuscolo,
  tutti gli scenari hanno GIVEN, WHEN e THEN. Nessun difetto di forma.
  I requisiti numerati e i punti aperti stanno fuori dai fence.

- Note / punti non valutabili:
  Due dei tre punti aperti chiedono dettagli già risolti dalla fonte e,
  per il criterio 2, non aumentano il punteggio:
  "Validazione Motivazione" chiede se il limite di 500 caratteri sia
  globale o vari per tipo di evento, ma REGOLA-VAL-01 lo fissa come
  lunghezza massima assoluta; il protocollo esclude esplicitamente questo
  come dubbio aperto.
  "Gestione Errori" chiede se il form debba essere resettato o i dati
  cancellabili: dettaglio non prescritto dalle fonti e non incluso tra i
  dubbi preregistrati. Non è un requisito inventato perché resta una
  domanda, ma non conta come Q dichiarato.
  S02 riporta il wording "Limite superato": non valutato, come prescrive
  il protocollo per l'incoerenza interna della fonte; la risposta non
  sostiene che sia univoco.
  Come P06, questa risposta emette requisiti numerati propri
  ([REQ-FE3-01]..[REQ-FE3-04]) presentati come prescrizioni vincolanti:
  valutati come affermazioni normative nella tabella.
  Scheda redatta con assistenza di un modello e revisionata dall'umano
  contro le fonti congelate.

Affermazioni normative atomiche:

| ID | Citazione dalla risposta | Verdetto | Fonte e passaggio | Motivazione |
|---|---|---|---|---|
| D1 | REQ-FE3-01: limite 500 caratteri, contatore residui, evidenziazione, pulsante disabilitato | supported | spec_form REGOLA-VAL-01 (righe 54-55) | tutti gli effetti prescritti |
| D2 | REQ-FE3-02: preferenze tramite controlli booleani o radio buttons | supported | Canvas §3 (riga 16) | il Canvas cita booleane/radio buttons |
| D3 | REQ-FE3-03: pulsante disabilitato per tutto il Round Trip Time | supported | spec_form REGOLA-VAL-02 (riga 63) | durata e disabilitazione prescritte |
| D4 | REQ-FE3-04: feedback su timeout o errore server senza bloccare l'interfaccia | supported | Canvas §7 Safeguards (riga 40) | casi ed effetto prescritti |
| D5 | S04: motivazione vuota impedisce la sottomissione, payload definito invalido | conflicted | Canvas Safeguards vs spec_form REGOLA-FORM-01 (riga 49) | conflitto Q1 risolto senza dichiararlo |
| D6 | S04: il campo vuoto include "solo spazi bianchi" | unsupported | nessuna fonte | trattamento degli spazi non prescritto |
| D7 | S03: riabilitazione dopo ritorno allo stato idle | unsupported | nessuna fonte | lo stato idle e la sua transizione non sono prescritti |
| D8 | payload JSON con motivazione e preferenze | supported | Canvas §5 (riga 30), spec_form §4 (riga 84) | payload e formato presenti |
| D9 | Client Component con metadati da Server Component | supported | Canvas §3 (riga 16), §4 (riga 23) | architettura prescritta |

Rapporto supported / valutabili: 6 / 9. Unsupported: 2. Conflicted: 1.

Rilievo sul protocollo, da riportare tale e quale: quarto caso non
previsto dai criteri. Il criterio 2 stabilisce che chiedere un dettaglio
già risolto dalla fonte non aumenta il punteggio, ma non prevede dove
registrarlo. Qui due punti aperti su tre sono di questo tipo: un
conteggio che riporta solo "1/3" perde l'informazione che la risposta ha
prodotto tre domande, due delle quali rivolte a dettagli non aperti.
Valutare un campo dedicato ai punti aperti non pertinenti prima di
aggregare, insieme ai tre rilievi già aperti su P03, P04 e P06.
Si ripresenta inoltre l'omissione di react-hook-form e Zod, prescritti
come obbligatori dal Canvas §6 (riga 35): quarto campione su quattro.


---

## Campione P11

### Risposta integrale

# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Descrizione della Feature

La feature **FE3** implementa un modulo interattivo per la compilazione e sottomissione di una richiesta di partecipazione a un evento (`EVENTO`). Il modulo permette all'utente (`UTENTE`) di inserire una motivazione testuale e di definire preferenze relative alla necessità di strutture (es. alloggio). L'interfaccia gestisce lo stato dei campi, valida i dati lato client prima dell'invio e fornisce feedback visivo durante il caricamento o in caso di errore.

## 2. Requisiti Funzionali e Vincoli

### [REQ-FE3-01] Gestione Preferenze Alloggio
- **Descrizione:** Il form deve esporre un controllo (Checkbox o Radio Button) per indicare se l'utente necessita di una struttura per l'alloggio.
- **Comportamento:** L'input deve essere booleano. Se selezionato, la preferenza viene serializzata nel payload; altrimenti, il campo è nullo/false.

### [REQ-FE3-02] Inserimento Motivazione
- **Descrizione:** Il form deve includere un campo di testo (`Textarea`) dedicato alla motivazione della partecipazione.
- **Vincolo:** Il sistema deve impedire l'inserimento di testi vuoti o eccessivamente lunghi, disabilitando il pulsante di sottomissione in caso di violazione delle regole di validazione (es. lunghezza massima 500 caratteri).

### [REQ-FE3-03] Sottomissione e Feedback
- **Descrizione:** Al click sul pulsante "Partecipa", il sistema deve inviare i dati al backend e mostrare uno stato di caricamento.
- **Gestione Errori:** In caso di fallimento della chiamata API (timeout, errore server), il sistema deve visualizzare un messaggio di errore all'utente senza bloccare l'interfaccia.

### [REQ-FE3-04] Validazione Schema Zod
- **Descrizione:** La validazione dei dati avviene lato client utilizzando uno schema definito con `Zod`.
- **Comportamento:** Lo schema controlla la presenza del campo motivazione e il tipo corretto delle preferenze. Il pulsante di invio è disabilitato finché lo schema rileva errori.

## 3. Scenari Comportamentali BDD (Gherkin)

```gherkin
SCENARIO: S01 - Invio richiesta con dati validi e alloggio richiesto
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione valida contenente 150 caratteri
  AND seleziona la checkbox "Necessità alloggio"
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema disabilita il pulsante e mostra uno stato di caricamento
  AND invia con successo la RICHIESTA al backend
  AND visualizza un messaggio di conferma positivo
```

```gherkin
SCENARIO: S02 - Invio richiesta senza motivazione
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente lascia vuoto il campo "Motivazione"
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema evidenzia il campo in rosso con un messaggio di errore
  AND disabilita il pulsante impedendo l'invio della RICHIESTA
```

```gherkin
SCENARIO: S03 - Invio richiesta con motivazione troppo lunga
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione contenente 550 caratteri
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema evidenzia il campo in rosso con un messaggio di errore
  AND disabilita il pulsante impedendo l'invio della RICHIESTA
```

```gherkin
SCENARIO: S04 - Invio richiesta senza necessità alloggio
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione valida contenente 120 caratteri
  AND non seleziona la checkbox "Necessità alloggio"
  WHEN l'utente clicca sul pulsante "Partecipa"
  THEN il sistema disabilita il pulsante e mostra uno stato di caricamento
  AND invia con successo la RICHIESTA al backend con preferenze nulle per l'alloggio
```

```gherkin
SCENARIO: S05 - Invio fallito a causa di errore server
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione valida e seleziona la necessità alloggio
  WHEN l'utente clicca sul pulsante "Partecipa" e il backend restituisce un errore 500
  THEN il sistema mostra uno stato di caricamento temporaneo
  AND visualizza un messaggio di errore generato da sonner o UI standard
```

```gherkin
SCENARIO: S06 - Disabilitazione pulsante durante caricamento
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente clicca sul pulsante "Partecipa" con dati validi
  WHEN la chiamata API è in corso (Round Trip Time)
  THEN il sistema mantiene il pulsante disabilitato e mostra uno spinner
  AND impedisce all'utente di inviare nuovamente la RICHIESTA prima della risposta
```

```gherkin
SCENARIO: S07 - Reset stato form dopo errore
  GIVEN un UTENTE autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente clicca sul pulsante "Partecipa" e riceve un messaggio di errore
  WHEN l'utente corregge i dati o attende la fine del timeout
  THEN il sistema ripristina lo stato abilitato del pulsante se i dati sono validi
  AND permette all'utente di riprovare l'invio della RICHIESTA
```

### Valutazione umana di P11

- Stato: human_reviewed
- Ambiguità dichiarate correttamente (ID Q): 0 / 3.
  Nessuna sezione di punti aperti e nessuna domanda formulata.
  Q1 non dichiarato e risolto in silenzio due volte: REQ-FE3-02 prescrive
  di impedire l'inserimento di testi vuoti e REQ-FE3-04 dispone che lo
  schema controlli "la presenza del campo motivazione"; S02 lo conferma
  con un THEN. REGOLA-FORM-01 qualifica invece le note/motivazioni come
  campo opzionale: il conflitto non è segnalato.
  Q2 non dichiarato: REQ-FE3-01 tratta le preferenze come il solo
  booleano alloggio, senza segnalare che la fonte ne cita altre non
  definite.
  Q3 non dichiarato: nessuna menzione del fatto che interfaccia, schema
  e feedback di successo non siano fissati.

- Funzionalità con nominale e negativo coperti (ID F):
  FE3-F1 (S01 nominale; S03 negativo per superamento limite).
  FE3-F3 (S01 nominale; S05 errore server, S06 doppio invio negativi).

- Funzionalità con copertura parziale (ID F e caso mancante):
  FE3-F2 — nominali presenti nelle due varianti (S01 con alloggio
  selezionato, S04 senza), punto indefinito delle altre preferenze non
  dichiarato: copertura del solo caso noto, senza la dichiarazione che
  il protocollo attendeva.
  FE3-F4 — assente, vedi omissioni.

- Casi mancanti dichiarati esplicitamente: nessuno.

- Omissioni non dichiarate:
  FE3-F4 assente per intero, nominale e negativo: nessun requisito e
  nessuno scenario toccano l'idoneità o la richiesta già attiva, benché
  REGOLA-INT-01 la prescriva.
  Dubbi Q1, Q2, Q3.

- Forma GIVEN/WHEN/THEN e fence:
  7 fence, 7 scenari, un fence per scenario, keyword in maiuscolo,
  tutti gli scenari hanno GIVEN, WHEN e THEN. Nessun difetto di forma.
  I requisiti numerati stanno fuori dai fence.

- Note / punti non valutabili:
  S02 e S03 hanno THEN identici: stesso effetto — campo evidenziato in
  rosso con messaggio di errore e pulsante disabilitato — per motivazione
  vuota e per superamento dei 500 caratteri. Due casi distinti collassano
  su un unico comportamento osservabile, e il feedback specifico del
  limite (contatore decrementale, valore negativo) previsto da
  REGOLA-VAL-01 non compare in nessuno scenario.
  S05 ha un THEN incoerente con l'ordine degli eventi: dopo che il
  backend ha già restituito l'errore 500, prescrive di mostrare "uno
  stato di caricamento temporaneo". Non descrive un comportamento
  osservabile univoco.
  S07 usa come innesco "l'utente corregge i dati o attende la fine del
  timeout": due condizioni alternative in un solo WHEN, di cui la seconda
  non prescritta dalle fonti. Contato come affermazione non supportata,
  non come omissione.
  Il contatore dei caratteri, prescritto da REGOLA-VAL-01, non è mai
  menzionato: né nei requisiti né negli scenari.
  Come P06 e P08, la risposta emette requisiti numerati propri
  ([REQ-FE3-01]..[REQ-FE3-04]) presentati come prescrizioni vincolanti:
  valutati come affermazioni normative nella tabella.
  Scheda redatta con assistenza di un modello e revisionata dall'umano
  contro le fonti congelate.

Affermazioni normative atomiche:

| ID | Citazione dalla risposta | Verdetto | Fonte e passaggio | Motivazione |
|---|---|---|---|---|
| E1 | REQ-FE3-01: controllo checkbox o radio button per l'alloggio, input booleano | supported | Canvas §3 (riga 16) | booleane/radio buttons citate |
| E2 | REQ-FE3-01: se non selezionato, il campo è nullo/false | unsupported | nessuna fonte | l'alternativa null vs false non è prescritta |
| E3 | REQ-FE3-02: impedire l'inserimento di testi vuoti | conflicted | Canvas Safeguards vs spec_form REGOLA-FORM-01 (riga 49) | conflitto Q1 imposto come vincolo |
| E4 | REQ-FE3-02: lunghezza massima 500 caratteri | supported | spec_form REGOLA-VAL-01 (riga 54) | limite fissato dalla fonte |
| E5 | REQ-FE3-03: stato di caricamento al click e messaggio di errore su timeout o errore server | supported | spec_form REGOLA-VAL-02 (riga 63), Canvas §7 (riga 40) | entrambi prescritti |
| E6 | REQ-FE3-04: validazione client con schema Zod | supported | Canvas §3 (riga 17), §6 (riga 35) | Zod prescritto |
| E7 | REQ-FE3-04: lo schema controlla la presenza del campo motivazione | conflicted | come E3 | stesso conflitto, ribadito come comportamento dello schema |
| E8 | S05: messaggio di errore generato da sonner o UI standard | supported | Canvas §7 Safeguards (riga 40) | formulazione alternativa presente nella fonte |
| E9 | S06: pulsante disabilitato per tutto il Round Trip Time | supported | spec_form REGOLA-VAL-02 (riga 63) | durata prescritta |
| E10 | S07: ripristino dello stato dopo "la fine del timeout" | unsupported | nessuna fonte | nessuna temporizzazione né transizione automatica prescritta |

Rapporto supported / valutabili: 6 / 10. Unsupported: 2. Conflicted: 2.

Rilievo sul protocollo, da riportare tale e quale: quinto caso non
previsto dai criteri. Qui due scenari distinti (S02 e S03) hanno THEN
identici, coprendo formalmente due casi ma descrivendo un solo
comportamento osservabile. Il criterio 3 chiede di mappare ogni scenario
al singolo caso, e il criterio 4 esclude che una frase ripetuta valga
come nuova copertura, ma nessuno dei due prevede come registrare due
casi che collassano sullo stesso effetto: conteggiarli come coperti
sovrastima la copertura. Valutare prima di aggregare, insieme ai quattro
rilievi già aperti su P03, P04, P06 e P08.


---

## Campione P12

### Risposta integrale

# Specifica Tecnica — Feature FE3 (Form di Prenotazione)
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Obiettivo e Logica del Form

La presente specifica definisce il comportamento osservabile della feature **FE3**, relativa alla compilazione e sottomissione interattiva di una richiesta di partecipazione (`RICHIESTA`) a un evento (`EVENTO`). Il modulo, implementato come componente Client React, gestisce l'inserimento della motivazione e delle preferenze (es. alloggio), valida i dati lato client prima dell'invio al backend e gestisce lo stato di caricamento per prevenire duplicati accidentali.

Il form è accessibile all'interno del contesto di un `EVENTO` attivo e richiede che l'utente sia autenticato (`UTENTE`). La logica di rendering separa il recupero dei metadati (Server Component) dalla gestione degli input (Client Component).

---

## 2. Regole di Validazione e Comportamento UI

### [REGOLA-FE3-01] Limiti del campo motivazione
- **Descrizione:** Il campo `motivazione` è un textarea che accetta testo libero ma non deve superare i 500 caratteri.
- **Effetto in caso di violazione:** L'interfaccia mostra un contatore dei caratteri residui. Se il limite viene superato, il bordo del textarea diventa rosso e il pulsante di sottomissione viene disabilitato.
- **Entità Target:** `RICHIESTA`

### [REGOLA-FE3-02] Gestione preferenze alloggio
- **Descrizione:** Il form include un controllo booleano (Checkbox o Radio) per indicare la necessità di una struttura per l'alloggio.
- **Effetto in caso di violazione:** Non applica vincoli di validazione sintattica, ma memorizza lo stato selezionato nel payload da inviare al backend.
- **Entità Target:** `RICHIESTA`

### [REGOLA-FE3-03] Disattivazione durante l'invio
- **Descrizione:** Al momento della sottomissione (`submit`), il sistema disabilita immediatamente il pulsante "Partecipa" e mostra uno stato di caricamento.
- **Effetto in caso di violazione:** L'utente non può inviare richieste multiple parallele che potrebbero generare duplicati nel database.
- **Entità Target:** `RICHIESTA`

### [REGOLA-FE3-04] Feedback errore rete
- **Descrizione:** In caso di fallimento della chiamata API (timeout o errore server 500), il sistema visualizza un messaggio di errore non intrusivo.
- **Effetto in caso di violazione:** L'utente rimane bloccato senza feedback visivo, portando a tentativi ripetuti e potenziali errori lato backend.
- **Entità Target:** `RICHIESTA`

---

## 3. Scenari Comportamentali BDD (Gherkin)

```gherkin
SCENARIO: S01 - Invio richiesta con dati validi
  GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione di 120 caratteri nel campo dedicato
  AND seleziona la checkbox "Necessaria struttura alloggio"
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema valida lo schema Zod e invia il payload al backend
  AND disabilita il pulsante mostrando uno stato di caricamento
```

```gherkin
SCENARIO: S02 - Blocco invio per motivazione troppo lunga
  GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione di 550 caratteri nel campo dedicato
  WHEN tenta di cliccare sul pulsante "Partecipa"
  THEN il sistema evidenzia il campo con bordo rosso
  AND disabilita il pulsante impedendo la sottomissione
```

```gherkin
SCENARIO: S03 - Gestione errore server durante invio
  GIVEN un utente autenticato compila correttamente il form di prenotazione per un EVENTO
  AND l'utente clicca sul pulsante "Partecipa"
  WHEN il backend restituisce un errore HTTP 500 o un timeout
  THEN il sistema visualizza un messaggio di errore tramite Toast
  AND riabilita i controlli del form dopo la risoluzione dell'errore
```

```gherkin
SCENARIO: S04 - Invio senza necessità alloggio
  GIVEN un utente autenticato visualizza il form di prenotazione per un EVENTO attivo
  AND l'utente inserisce una motivazione valida nel campo dedicato
  AND lascia deselezionata la checkbox "Necessaria struttura alloggio"
  WHEN clicca sul pulsante "Partecipa"
  THEN il sistema invia il payload con il valore booleano false per le preferenze alloggio
  AND conferma il successo dell'operazione all'utente
```

---

## 4. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
| :--- | :--- | :--- |
| **Gestione Errori Client** | Si presume che il componente UI standard fornito dalla libreria `shadcn/ui` includa nativamente un componente `Toast` o simile per la gestione degli errori. | È necessario implementare un componente Toast custom o si può affidare alla configurazione esistente di `sonner`? |
| **Validazione Schema Zod** | Si presume che lo schema Zod importato sia configurato con il limite esatto di 500 caratteri e tipi booleani corretti per le preferenze. | Qual è la strategia esatta per gestire campi opzionali multipli oltre all'alloggio se ne fossero aggiunti in futuro? |
| **Stato Loading** | Si presume che lo stato di caricamento sia gestito esclusivamente tramite il disabilitamento del pulsante e non richieda un overlay globale. | Come comportarsi visivamente se la chiamata API è asincrona ma molto lunga (es. > 5 secondi)? |

### Valutazione umana di P12

- Stato: human_reviewed
- Ambiguità dichiarate correttamente (ID Q): 0 / 3.
  Tre punti aperti presenti, nessuno corrispondente ai dubbi
  preregistrati.
  Q1 non dichiarato, ma nemmeno deciso: la risposta non menziona mai la
  motivazione vuota, né come requisito né come scenario. Non è un
  conflitto imposto, è un caso non trattato. Registrato tra le omissioni,
  non tra le affermazioni conflicted.
  Q2 non dichiarato: il punto aperto su Validazione Schema Zod sfiora il
  tema ma chiede la strategia per campi opzionali "se ne fossero aggiunti
  in futuro", cioè un'ipotesi futura, non le altre preferenze che le
  fonti già citano come esistenti e indefinite.
  Q3 non dichiarato: nessun punto aperto su interfaccia, schema o
  feedback di successo.

- Funzionalità con nominale e negativo coperti (ID F):
  FE3-F1 (S01 nominale; S02 negativo per superamento limite).

- Funzionalità con copertura parziale (ID F e caso mancante):
  FE3-F2 — nominali presenti nelle due varianti (S01 selezionata, S04
  deselezionata), punto indefinito delle altre preferenze non dichiarato.
  FE3-F3 — nominale presente (S01), negativo di rete presente (S03), ma
  il caso doppio click non ha scenario: REGOLA-FE3-03 lo enuncia come
  effetto atteso e nessuno scenario lo verifica.
  FE3-F4 — assente, vedi omissioni.

- Casi mancanti dichiarati esplicitamente: nessuno.

- Omissioni non dichiarate:
  FE3-F4 assente per intero, nominale e negativo: nessuna regola e
  nessuno scenario toccano l'idoneità o la richiesta già attiva, benché
  REGOLA-INT-01 la prescriva.
  Caso della motivazione vuota (Q1), mai trattato in alcuna forma.
  Caso doppio click di FE3-F3.
  Dubbi Q1, Q2, Q3.

- Forma GIVEN/WHEN/THEN e fence:
  4 fence, 4 scenari, un fence per scenario, keyword in maiuscolo,
  tutti gli scenari hanno GIVEN, WHEN e THEN. Nessun difetto di forma.
  Regole numerate e punti aperti stanno fuori dai fence.

- Note / punti non valutabili:
  Nessuno dei tre punti aperti è pertinente ai dubbi preregistrati, e per
  il criterio 2 nessuno aumenta il punteggio:
  "Gestione Errori Client" chiede se implementare un Toast custom o
  affidarsi a sonner, mentre il Canvas §7 indica già sonner con
  alternativa standard: è un dettaglio implementativo, non un dubbio
  aperto della fonte.
  "Validazione Schema Zod" chiede di campi opzionali futuri, non delle
  preferenze esistenti e indefinite.
  "Stato Loading" chiede il comportamento visivo per chiamate oltre i 5
  secondi: soglia non presente nelle fonti e dettaglio non incluso tra i
  dubbi preregistrati.
  Le regole REGOLA-FE3-01..04 riportano un campo "Effetto in caso di
  violazione" usato in modo incoerente: in 01 descrive l'effetto della
  violazione, in 02 e 03 descrive invece il comportamento corretto o la
  conseguenza evitata. Annotato come incoerenza formale interna, senza
  effetto sui conteggi.
  Il contatore dei caratteri è menzionato in REGOLA-FE3-01 ma non
  compare in S02, che verifica il solo bordo rosso.
  Come P06, P08 e P11, la risposta emette regole numerate proprie
  presentate come prescrizioni vincolanti: valutate come affermazioni
  normative nella tabella.
  Scheda redatta con assistenza di un modello e revisionata dall'umano
  contro le fonti congelate.

Affermazioni normative atomiche:

| ID | Citazione dalla risposta | Verdetto | Fonte e passaggio | Motivazione |
|---|---|---|---|---|
| F1 | REGOLA-FE3-01: limite 500 caratteri, contatore residui, bordo rosso, pulsante disabilitato | supported | spec_form REGOLA-VAL-01 (righe 54-55) | tutti gli effetti prescritti |
| F2 | REGOLA-FE3-02: controllo booleano checkbox o radio per l'alloggio | supported | Canvas §3 (riga 16) | booleane/radio buttons citate |
| F3 | REGOLA-FE3-03: disabilitazione immediata al submit con stato di caricamento | supported | spec_form REGOLA-VAL-02 (riga 63) | disabilitazione e spinner prescritti |
| F4 | REGOLA-FE3-04: messaggio non intrusivo su timeout o errore 500 | supported | Canvas §7 Safeguards (riga 40) | casi ed effetto prescritti |
| F5 | S01: validazione tramite schema Zod | supported | Canvas §3 (riga 17), §6 (riga 35) | Zod prescritto |
| F6 | S04: payload con valore booleano false per le preferenze alloggio | supported | Canvas §5 (riga 30) | payload con preferenze presente |
| F7 | S03: riabilitazione dei controlli dopo la risoluzione dell'errore | unsupported | nessuna fonte | la transizione di ripristino non è prescritta |
| F8 | S04: conferma del successo dell'operazione all'utente | unsupported | Q3, fonti | il feedback di successo non è fissato dalle fonti |
| F9 | Client Component React con metadati da Server Component | supported | Canvas §3 (riga 16), §4 (riga 23) | architettura prescritta |

Rapporto supported / valutabili: 7 / 9. Unsupported: 2. Conflicted: 0.

Rilievo sul protocollo, da riportare tale e quale: sesto caso non
previsto dai criteri, ed è il più rilevante per il confronto finale.
P12 ha zero conflicted non perché dichiari il dubbio Q1, ma perché omette
del tutto il caso: il criterio 1 premia quindi l'omissione tanto quanto
la dichiarazione corretta, mentre il criterio 4 la registra separatamente
senza che i due conteggi si parlino. Un campione che tace su un
conflitto appare migliore di uno che lo decide esplicitamente e peggiore
solo nel conteggio delle omissioni, che è una lista e non un punteggio.
Valutare come comporre i due criteri prima di aggregare, insieme ai
cinque rilievi già aperti su P03, P04, P06, P08 e P11.

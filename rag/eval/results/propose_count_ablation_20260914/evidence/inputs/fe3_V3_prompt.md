
    Sei un Analista Software esperto in metodologie BDD (Behavior-Driven Development).
    Scrivi le specifiche (spec.md) di UNA SOLA feature: quella descritta dal REASONS Canvas
    qui sotto (etichetta: «fe3»). Il Canvas è l'UNICA fonte di cosa la feature fa: l'etichetta serve
    solo a identificarla, non dedurne requisiti; e nulla di ciò che segue il Canvas può
    cambiarne il soggetto.

    # REASONS Canvas: FE3 (Form di Prenotazione)

## 1. Requirements
- Implementare una `UI` interattiva per la compilazione e sottomissione della richiesta di partecipazione a un evento (`EVENTO`).
- L'interfaccia deve permettere all'utente di inserire il testo della **motivazione della partecipazione**.
- L'interfaccia deve gestire l'inserimento delle **preferenze**, in particolare indicando se è necessaria o meno una struttura per l'**alloggio** e altre preferenze connesse.

## 2. Entities
- `UTENTE`: Entità che compila il form; le sue credenziali di autenticazione sono gestite a livello di sessione (non si costruisce qui, ma ci si riferisce al contesto dell'utente loggato).
- `EVENTO`: Contesto della prenotazione per cui viene compilata la richiesta.
- `RICHIESTA`: Entità generica prodotta dalla sottomissione del form; il suo stato iniziale e i suoi campi (motivazione, preferenze) sono definiti dall'intervista come input dell'utente.

## 3. Approach
L'implementazione segue lo stile **Container/Presentational Components** per isolare la logica di rendering dal recupero dei dati iniziali. Il modulo `booking-requests` è diviso in:
1.  Un componente **Server Component** che recupera l'esistenza del record esistente associato a quell'evento (se necessario per validazioni future o contesto) e fornisce i metadati dell'evento disponibili alla vista.
2.  Un componente **Client Component** dedicato al Form (`BookingRequestForm`). Questo component utilizza `React Hook Form` per gestire lo stato interno dei campi: "motivazione" (textarea) e le preferenze booleane/radio buttons (es. necessità alloggio).
3.  La validazione degli input avviene lato client tramite schema definito con **Zod** (limiti di lunghezza del testo, tipi corretti delle boole), ma la sottomissione finale delega il controllo transazionale al Backend come da norma tecnologica.
4.  L'evento di submit invia una chiamata HTTP sincronizzata o asincrona gestita dal client API customizzato per aggiornare TanStack Query e mostrare feedback visivo (loading state).

## 4. Structure
- **Layer UI**: Implementato in `frontend/src/features/booking-requests/components/CreateBookingForm.tsx` utilizzando i componenti base di `shadcn/ui`. Include un `Textarea` per la motivazione e `Checkbox` o `Select` per le preferenze (alloggio).
- **Logica Form**: Gestita da istanza globale o locale in `React Hook Form` con schema validato tramite importazioni specifiche di **Zod**.
- **Gestione Dati Client-Side**: Utilizzo di TanStack Query (`useMutation`) all'interno del component per gestire la sottomissione. Non si creano nuovi endpoint, ma si consuma l'interfaccia backend esistente (o nuova) esposta dal client API `lib/api/`.
- **Architettura**: Server Components caricano il contesto evento; Client Component gestisce input utente e submit logiche reattive.

## 5. Operations
1.  Inizializzazione del componente Client dentro la pagina di creazione richiesta (es. card evento o dashboard).
2.  Render dinamico dei campi: Textarea per motivazione, Checkbox/Selector per "Necessità alloggio" e altri campi preferenze menzionati nell'intervista.
3.  Attivazione delle regole `React Hook Form` trigger su cambio input (`onChange`, `onBlur`) usando lo schema **Zod**.
4.  Sottomissione dati al componente server/client che invia la rete (chiamata API) con il payload contenente `{ motivazione, preferenze }`.
5.  Gestione dello stato di loading e restituzione della UI dopo successo o errore (messaggio Toast).

## 6. Norms
- **Stack Tecnologico**: Il form utilizza esclusivamente `React`, `TypeScript` come tipo del sistema (`tsconfig.json`). Lo stile e i componenti sono costruiti su base di `Tailwind CSS` con la libreria `shadcn/ui`. La logica è scritta in `.tsx`.
- **Librerie Specifiche**: Validazione schema obbligatorio tramite import da `zod`, gestione stato form obbligatoria via `react-hook-form`, gestione cache dati via `@tanstack/react-query`. Si usa l'implementazione standard di queste librerie come specificato nello stack.
- **Nomi Variabili/Classi**: Naming snake_case per nomi file o entità specifiche se richiesto dal codice legacy, camelCase per componenti JS/TS (`CreateBookingForm`).

## 7. Safeguards
- **Inibizione Input Invalido**: Il pulsante "Partecipa" (sottomissione) deve essere disabilitato visivamente dall'UI `shadcn/ui` finché lo schema `Zod` rileva dati mancanti o testi vuoti invalidi nel campo motivazione. Questo previene l'invio di payload null/invalido al backend.
- **Gestione Errori Client**: In caso di timeout HTTP o errore 500 lato server durante la sottomissione della richiesta, mostrare un alert `Toast` generato con `sonner` (se previsto da shadcn) o componente UI standard fornito dalla libreria per non bloccare l'utente su una pagina bianca.
- **Concorrenza UI**: Non tentare di calcolare disponibilità posti residui (`Sold Out`) lato client per questa feature specifica; la visibilità del form e lo stato abilitato/disabilitato derivano dall'interfaccia che consuma i dati (es: se il backend non risponde o dice "full", l'API blocca, ma per la logica interna al form si presume validità dei permessi di scrittura dell'endpoint).
- **Sicurezza**: L'autenticazione e l'iniezione SQL/XSS sono responsabilità del Backend e delle librerie di sicurezza esistenti (`helmet`, `cors` lato server o token JWT gestiti da Auth.js); il frontend non implementa logiche di crittografia, si fida dei controlli transazionali.


    Vincoli normativi dal Graph RAG. ATTENZIONE: NON sono l'argomento dello spec — l'argomento è la feature del Canvas, e basta. Servono come LENTE per trovarne i casi limite: da qui ricavi gli scenari negativi CHE LA FEATURE DEVE GESTIRE (tentativi non autorizzati su di essa, suoi casi di errore, invarianti dei safeguard che essa tocca) e i termini/codici esatti da citare. È VIETATO scrivere scenari su parti del sistema che questi documenti nominano ma che la feature non tocca: se uno scenario resta sensato dopo aver tolto la feature, non va scritto.
    --- 02_specs_normative/spec_form_1.4.md [ENFORCED, documento integrale] ---
---
id: "spec-form-v1.0"
title: "Specifica Normativa — Form di Sottomissione Richieste"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-13"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_form_1.4.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-form-v1.0"
  scope: "Definizione dei requisiti di validazione e comportamento del form per l'invio di una richiesta"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-v1.2"
    - type: "VINCOLA"
      target: "entity::RICHIESTA"
    - type: "VINCOLA"
      target: "entity::UTENTE"
tags:
  - requirements
  - open-spec
  - form-validation
  - input-control
  - duplicate-prevention
---

# Specifica Normativa — Form di Sottomissione Richieste
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Obiettivo e Logica del Form di Sottomissione

La presente specifica definisce i requisiti funzionali, le regole di validazione sintattica dei dati e i vincoli di interfaccia grafica applicati al modulo (form) di sottomissione di una nuova `` `RICHIESTA` `` di partecipazione a un determinato `` `EVENTO` ``. Lo scopo di questo modulo è garantire che i dati inseriti dall' `` `UTENTE` `` siano coerenti e puliti prima di avviare il transito di rete, prevenendo l'inserimento di testi troppo lunghi o formati non validi, e inibendo comportamenti concorrenti errati dell'interfaccia utente (UI).

Questo form rappresenta la porta d'ingresso interattiva per l'iscrizione, accessibile sia dalla card della dashboard sia dalla scheda di dettaglio, e deve agire in sinergia con i controlli transazionali del backend.

---

## 2. Campi Obbligatori e Validazioni Sintattiche

### [REGOLA-FORM-01] Presenza dei campi obbligatori
- **Descrizione:** Il form di sottomissione deve catturare ed inviare in modo strutturato l'identificativo univoco dell' `` `EVENTO` `` selezionato, l'identificativo dell' `` `UTENTE` `` richiedente e il campo opzionale relativo alle note/motivazioni per l'approvatore.
- **Effetto in caso di violazione (Failure Mode):** Il form evidenzia i campi mancanti in rosso, blocca l'azione di invio e impedisce la chiamata API al server.
- **Entità Target:** `` `RICHIESTA` ``

### [REGOLA-VAL-01] Limite di caratteri del campo motivazione
- **Descrizione:** Il campo di testo dedicato alla motivazione della richiesta non deve superare la lunghezza massima assoluta di 500 caratteri. Il sistema deve mostrare in tempo reale un contatore decrementale dei caratteri residui al di sotto della casella di input.
- **Effetto in caso di violazione (Failure Mode):** Al superamento del limite, la casella si evidenzia con un bordo rosso, compare il messaggio di errore "Limite superato" e il pulsante "Invia" viene disabilitato.
- **Entità Target:** `` `RICHIESTA` ``

---

## 3. Gestione dell'Input e Prevenzione dei Duplicati

### [REGOLA-VAL-02] Disattivazione anti-click del pulsante di invio
- **Descrizione:** All'istante esatto del click sul pulsante "Invia", l'interfaccia grafica del client deve disabilitare il controllo (stato HTML `disabled`), sostituire il testo del pulsante con uno spinner visivo di caricamento e mantenerlo bloccato per tutta la durata del ciclo di chiamata di rete (Round Trip Time).
- **Effetto in caso di violazione (Failure Mode):** L'utente può premere ripetutamente il pulsante prima che la chiamata si concluda, generando sottomissioni parallele identiche e sollevando eccezioni di database per record duplicati della risorsa `` `RICHIESTA` ``.
- **Entità Target:** `` `RICHIESTA` ``

### [REGOLA-INT-01] Validazione di idoneità preventiva dell'utente
- **Descrizione:** Prima di visualizzare il form, il client deve effettuare una verifica asincrona silenziosa per accertarsi che l' `` `UTENTE` `` corrente non abbia già una `` `RICHIESTA` `` attiva per lo stesso `` `EVENTO` `` in stato 'IN_ATTESA_APPROVAZIONE' o 'APPROVATA'.
- **Effetto in caso di violazione (Failure Mode):** Mancata inibizione del form, con conseguente esposizione dell'utente a inutili tentativi di iscrizione per eventi a cui risulta già prenotato.
- **Entità Target:** `` `UTENTE` ``, `` `RICHIESTA` ``

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Validazione Form e Prevenzione Doppio Invio

```gherkin
Scenario: Compilazione ed invio valido del form di richiesta
  Dato un UTENTE autenticato posizionato sul form di sottomissione di un EVENTO attivo
  Quando l'utente inserisce una motivazione di 120 caratteri e clicca su "Invia"
  Allora il sistema valida la conformità con la [REGOLA-FORM-01] e la [REGOLA-VAL-01]
  E disabilita immediatamente il pulsante "Invia" applicando la [REGOLA-VAL-02]
  E inoltra con successo il payload JSON al backend per la creazione della RICHIESTA
```

```gherkin
Scenario: Blocco invio form per superamento limite caratteri motivazione
  Dato un UTENTE autenticato posizionato sul form di sottomissione
  Quando l'utente inserisce una motivazione di 550 caratteri nella casella di testo
  Allora il sistema applica in tempo reale la [REGOLA-VAL-01]
  E mostra il contatore dei caratteri in rosso con valore negativo "-50"
  E visualizza il messaggio informativo "La motivazione non può superare i 500 caratteri"
  E disabilita il pulsante "Invia" impedendo la trasmissione dei dati
```

```gherkin
Scenario: Inibizione del form per utente già iscritto all'evento
  Dato un UTENTE che possiede già una RICHIESTA in stato 'APPROVATA' per un EVENTO specifico
  Quando l'utente naviga nuovamente sulla pagina di quell'evento
  Allora il sistema intercetta lo stato mediante la [REGOLA-INT-01]
  E sostituisce il form di sottomissione con un badge informativo verde recante la dicitura "Sei già iscritto a questo evento"
```

    Vincolo di ambito: questa feature è ESCLUSIVAMENTE 'frontend'. Gli scenari devono descrivere comportamento osservabile in questo ambito; non scrivere scenari su parti del sistema fuori da esso.

    Basandoti sulle regole e sui requisiti del Canvas (e sui vincoli normativi qui sopra, se presenti),
    scrivi il file delle specifiche tecniche (spec.md).

    Ogni scenario deve avere per soggetto la feature del Canvas e descriverne un COMPORTAMENTO
    osservabile. Non scrivere scenari che verificano lo stack, le librerie o gli strumenti in sé.
    Niente scenari duplicati: se due differiscono solo nella formulazione, tienine uno.
    La feature descritta dal Canvas può contenere più funzionalità, cioè comportamenti
    osservabili distinti. Il limite seguente si applica separatamente a ciascuna
    funzionalità, non alla feature nel suo insieme.

    Individua le N funzionalità da coprire. Per ciascuna funzionalità Fi scrivi da 2 a 4
    scenari dedicati, includendo almeno un caso nominale e uno negativo o di errore.
    Non accorpare funzionalità distinte per rispettare il limite.

    Il totale dello spec è T = s1 + s2 + … + sN, dove si è il numero di scenari della
    singola funzionalità Fi. Quando tutti i casi sono definibili, 2N ≤ T ≤ 4N.
    Il numero 4 non è un limite complessivo: il totale cresce con il numero delle
    funzionalità.

    Verifica il conteggio per ciascuna funzionalità prima di sommare il totale.
    Non inventare requisiti per raggiungere il minimo: se un'ambiguità impedisce un
    caso verificabile, dichiara il caso mancante nei punti aperti. Se una singola
    funzionalità richiede più di quattro scenari, dichiara la sua copertura mancante
    senza suddividere il Canvas.

    Non inventare funzionalità non presenti nel Canvas o nei vincoli normativi. Se uno scenario
    nomina una tecnologia o mostra codice, usa ESCLUSIVAMENTE le tecnologie già citate nel
    Canvas: qualsiasi altro linguaggio, libreria o strumento è VIETATO.

    VERIFICA FINALE sul contenuto — rileggi il Canvas in cima e controlla che ogni scenario
    discenda da un suo requisito: i vincoli normativi descrivono ANCHE altri moduli del sistema
    (cataloghi di funzionalità, pannelli, console) che NON sono questa feature, e non vanno
    trasformati in scenari. Se uno scenario non è riconducibile a una frase del Canvas, toglilo.

    Rispondi esclusivamente con il contenuto del file Markdown, senza preamboli né commenti
    prima o dopo. Scrivi SOLO la versione definitiva, senza auto-correzioni o dubbi inline
    nei passi degli scenari. Se un punto è ambiguo, non risolverlo d'autorità: aggiungilo a una
    sezione "Punti aperti" del documento, FUORI dai blocchi gherkin. Per ciascun punto indica
    la funzionalità coinvolta, l'assunzione proposta DA CONFERMARE e una domanda aperta
    esplicita. L'assunzione non è un requisito approvato: non usarla per fissare l'esito di
    uno scenario. Indica quali comportamenti restano senza copertura fino alla risposta.
    Per la copertura di una singola funzionalità che eccede i 4 scenari per quella funzionalità, elenca i casi mancanti e la domanda da risolvere;
    se non occorre un'assunzione, scrivi "Assunzione: nessuna; copertura da confermare".
    Non dichiarare completa la copertura in presenza di casi mancanti o punti irrisolti.

    ==========================================================================
    FORMATO DEGLI SCENARI — obbligatorio, sempre, senza varianti: vale per ogni
    scenario di ogni spec, qualunque sia la feature. È la parte più importante
    di queste istruzioni: uno spec fuori formato viene rifiutato in automatico.
    ==========================================================================

    Copia la forma dell'esempio qui sotto, cambiando solo il testo:

```gherkin
SCENARIO: S01 - Recupero fascicolo esistente
  GIVEN un utente autenticato con profilo "Operatore"
  AND un fascicolo con protocollo "2026/00123" presente in archivio
  WHEN richiede il dettaglio del fascicolo
  THEN il sistema restituisce i metadati completi del fascicolo
```

```gherkin
SCENARIO: S02 - Recupero negato su fascicolo inesistente
  GIVEN un utente autenticato con profilo "Operatore"
  WHEN richiede il dettaglio del fascicolo con protocollo "2026/99999"
  THEN il sistema rifiuta la richiesta con errore "NOT_FOUND"
  AND non restituisce alcun metadato
```

    GUARDA COME FINISCE IL PRIMO SCENARIO E COME COMINCIA IL SECONDO. Dopo il THEN di S01 c'è
    una riga di tre backtick che CHIUDE il blocco; poi una riga vuota; poi una nuova riga
    ```gherkin che APRE il blocco di S02. Questa è la regola che si sbaglia più spesso ed è
    quella che da sola invalida lo spec:

    OGNI SCENARIO HA IL SUO BLOCCO. Cinque scenari sono cinque blocchi: cinque righe di
    apertura e cinque righe di chiusura. Non scrivere MAI due `SCENARIO:` dentro lo stesso
    blocco. Una riga ```gherkin non chiude niente — apre: usarla per separare due scenari
    lascia tutto dentro un blocco solo, ed è sbagliato.

    L'errore da NON fare — due scenari lasciati dentro un blocco solo, separati da una riga
    vuota invece che dalla chiusura e dalla riapertura del blocco:

        ```gherkin
        SCENARIO: S01 - Primo caso
          GIVEN ...
          WHEN ...
          THEN ...
                                  <- qui manca la riga di chiusura del blocco di S01
        SCENARIO: S02 - Secondo caso      <- e la riga di apertura del blocco di S02
          GIVEN ...
        ```

    OGNI SCENARIO HA TRE PASSI OBBLIGATORI: GIVEN, poi WHEN, poi THEN. Il WHEN non si salta
    mai: è l'azione che scatena il comportamento, e senza di esso lo scenario non è
    verificabile. Un blocco con GIVEN e THEN ma senza WHEN è invalido, così come un blocco che
    si ferma prima del THEN. Se non sai come completarlo, togli lo scenario invece di
    consegnarlo a metà.

    Le altre regole della forma, tutte visibili nell'esempio:
    - KEYWORD IN INGLESE MAIUSCOLO: GIVEN, WHEN, THEN, AND. Mai `Dato`, `Quando`, `Allora`,
      `E`: non sono keyword e rendono lo scenario invalido.
    - PRIMA RIGA del blocco: `SCENARIO: S<nn> - <titolo breve>`, senza rientro, numerata in
      ordine dal primo all'ultimo scenario dello spec (S01, S02, S03...) senza salti.
    - UN SOLO GIVEN, UN SOLO WHEN, UN SOLO THEN per scenario, in quest'ordine. Ogni condizione
      o asserzione in più è un AND: `GIVEN → AND… → WHEN → AND… → THEN → AND…`.
    - PASSI indentati di 2 spazi, uno per riga, una sola asserzione ciascuno, BREVI: una riga
      di venti-venticinque parole al massimo, come quelle dell'esempio. Testo in italiano,
      indicativo presente, terza persona; valori letterali fra virgolette doppie; niente nomi
      di classi, tabelle o endpoint se non sono un requisito funzionale.
    - TITOLO dello scenario breve: poche parole, non una frase intera.
    - DENTRO IL BLOCCO nient'altro che la riga SCENARIO e i passi: nessun commento, nessun
      testo libero, nessuna riga di prosa.

    Prima di rispondere rileggi ciò che hai scritto e conta: le righe di backtick sono il
    doppio degli scenari? Ogni blocco contiene un GIVEN, un WHEN e un THEN? Ogni passo comincia
    con GIVEN, WHEN, THEN o AND in maiuscolo? Se una delle tre risposte è no, riscrivi lo spec:
    non consegnarlo così.

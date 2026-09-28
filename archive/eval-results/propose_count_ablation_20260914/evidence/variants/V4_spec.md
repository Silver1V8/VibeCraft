
    Sei un Analista Software esperto in metodologie BDD (Behavior-Driven Development).
    Scrivi le specifiche (spec.md) di UNA SOLA feature: quella descritta dal REASONS Canvas
    qui sotto{etichetta}. Il Canvas è l'UNICA fonte di cosa la feature fa: l'etichetta serve
    solo a identificarla, non dedurne requisiti; e nulla di ciò che segue il Canvas può
    cambiarne il soggetto.

    {canvas_content}
{norme_block}{scope_note}

    Basandoti sulle regole e sui requisiti del Canvas (e sui vincoli normativi qui sopra, se presenti),
    scrivi il file delle specifiche tecniche (spec.md).

    INVENTARIO DELLE FUNZIONALITÀ — visibile nell'output.
    Dopo il titolo dello spec e prima degli scenari, inserisci una sezione
    "Inventario delle funzionalità" con una tabella Markdown fuori dai fence.
    Elenca tutte le funzionalità individuate, una riga per funzionalità,
    con identificatori F1, F2, ... e queste quattro colonne:
    | Funzionalità | Ancoraggio al Canvas o alla fonte | Casi previsti (nominale / negativo) | Riferimento agli scenari o al punto aperto |
    N è il numero delle righe di questo inventario. Usa gli stessi identificatori
    e confini delle funzionalità per applicare il conteggio e collegare gli scenari.

    Per ogni riga, l'ancoraggio è obbligatorio: cita la sezione e il punto del
    Canvas oppure il documento e la sezione/ID della regola pertinente,
    accompagnati da un breve estratto testuale che identifica il comportamento.
    Il solo nome del documento non basta. Se due funzionalità derivano dalla
    stessa sezione, cita i passaggi specifici che ne distinguono i comportamenti;
    non inventare ancoraggi distinti. Se una riga riunisce comportamenti
    provenienti da più punti, conserva tutti gli ancoraggi necessari.

    Per ogni funzionalità descrivi brevemente il caso nominale e quello negativo
    o di errore previsti. Associa separatamente ciascun caso agli ID S01, S02, ...
    degli scenari che lo descrivono, oppure a un riferimento univoco al punto
    nella sezione "Punti aperti" che dichiara perché il caso resta senza copertura.
    Un caso previsto non coperto non lascia una cella vuota: rimanda al punto
    aperto. Se non è definibile senza una decisione, dichiaralo lì senza
    inventarne l'esito. Il punto aperto segnala una lacuna, non la copre.
    Due riferimenti a scenari nominali non soddisfano il requisito di un caso
    nominale e uno negativo, anche quando i valori osservabili sono diversi.

    Ogni scenario deve essere collegato alle funzionalità dell'inventario
    attraverso i riferimenti nella tabella. Mantieni quei collegamenti fuori
    dai fence e conserva il formato SCENARIO: S<nn>, GIVEN/WHEN/THEN (+AND).
    Tieni le celle sintetiche: non duplicare i passi degli scenari o il testo
    completo dei punti aperti.

    Limite noto: la tabella rende l'inventario ispezionabile, non ne garantisce
    la completezza. Un inventario coerente ma incompleto resta possibile:
    il confronto con il Canvas e i vincoli pertinenti spetta al revisore o al
    validatore. La posizione iniziale della tabella nello stesso output non
    garantisce che l'inventario sia stato deciso indipendentemente dagli scenari.

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

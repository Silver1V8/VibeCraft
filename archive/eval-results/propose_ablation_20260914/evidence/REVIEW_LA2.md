# Schede LA2

Stato: human_reviewed.
Revisore: revisione umana condotta con assistenza di un modello (Claude), verdetti approvati dall'umano.
Data: 14 settembre 2026.

[Criteri](REVIEW_CRITERIA.md) · [Canvas congelato](inputs/la2_canvas.md)

Fonti integrali: [spec_notifications_2.4.md](inputs/spec_notifications_2.4.md), [observability_standards.md](inputs/observability_standards.md)

Compilare i campi dopo ogni risposta. L'ordine è per codice campione, non per esecuzione o template.

---

## Campione P01

### Risposta integrale

# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Contesto e Scopo

La presente specifica descrive il comportamento osservabile della feature **LA2**, implementata all'interno del progetto `logic-agent`. Il modulo gestisce l'invio asincrono di notifiche relative a eventi dinamici (cambi stato) e statici (scadenze), garantendo resilienza tramite retry multi-canale (Email, Slack) e logging strutturato.

Il sistema opera in ambiente **.NET 10 Worker Service**, utilizzando **RabbitMQ** per il messaging asincrono, **MassTransit** per la gestione dei consumer e delle code, e **Quartz.NET** per i job periodici di trigger statici. La persistenza avviene tramite l'entità `NOTIFICA`, che registra lo stato della consegna (`IN_CODA`, `CONSEGNATA`, `FALLITA`) e il numero di tentativo (`tentativo_n`).

## 2. Regole Operative e Vincoli

- **Entità:** Sono permessi solo i nomi `NOTIFICA`, `RICHIESTA`, `UTENTE`.
- **Attributi:** Gli attributi dello stato devono essere `stato_consegna` e il contatore `tentativo_n`.
- **Stack Tecnologico:** Uso esclusivo di **.NET 10**, **RabbitMQ**, **MassTransit**, **Quartz.NET**.
- **Log Strutturati:** Formato JSON con campi obbligatori: `timestamp`, `level`, `message`, `correlationId`.
- **Livelli Log:** `INFO` per eventi attesi, `WARNING` per fallimenti gestiti in backoff, `ERROR` solo per fallimento definitivo o perdita di integrità.
- **Backoff e Retry:** Tentativo massimo di 3 (`tentativo_n <= 3`). Backoff fisso di 15 minuti tra tentativi su canali diversi prima di considerare conclusa la sequenza per un evento specifico.
- **Fallback Silenzioso:** In caso di fallimento definitivo di tutti i canali, non attivare fallback alternativi (es. SMS). Registrare solo il log di anomalia.

## 3. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica Email riuscito per trigger dinamico
  GIVEN una RICHIESTA in stato "Revisato" che attiva un trigger dinamico
  AND il sistema identifica come destinatario l'utente dipendente tramite configurazione workflow
  WHEN il consumer NotificationConsumer elabora l'evento e tenta l'invio via EmailChannelAdapter
  THEN lo stato_consegna della NOTIFICA diventa "CONSEGNATA"
  AND il valore di tentativo_n rimane 1
  AND viene generato un log di livello INFO con messaggio di successo
```

```gherkin
SCENARIO: S02 - Gestione fallimento Email e retry su Slack
  GIVEN una RICHIESTA che innesca una notifica per scadenza imminente
  WHEN il sistema tenta l'invio via EmailChannelAdapter ma riceve un errore di delivery dal provider SMTP
  THEN lo stato_consegna della NOTIFICA diventa "IN_CODA"
  AND il valore di tentativo_n incrementa a 2
  AND il sistema attende il periodo di backoff configurato (15 minuti) prima di tentare Slack
```

```gherkin
SCENARIO: S03 - Fallimento definitivo e logging anomalia
  GIVEN una RICHIESTA per cui sia Email che Slack falliscono definitivamente nel limite dei 3 tentativi
  WHEN il sistema raggiunge il limite massimo di tentativo_n = 3 senza consegna su alcun canale
  THEN lo stato_consegna della NOTIFICA diventa "FALLITA"
  AND viene generato un log strutturato di livello ERROR con stato "FALLITA" e dettagli dell'anomalia
  AND non vengono attivati fallback alternativi come SMS
```

```gherkin
SCENARIO: S04 - Innesco trigger statico per scadenza imminente
  GIVEN il job StaticTriggerJob esegue la scansione periodica delle RICHIESTE in attesa
  WHEN una RICHIESTA ha un countdown temporale inferiore alla soglia configurata (es. X giorni)
  THEN il job pubblica un evento asincrono su RabbitMQ contenente l'ID della richiesta e i metadati "SCADENZA_IMMINENTE"
  AND il consumer elabora l'evento seguendo la logica di routing dinamica per destinatario RESPONSABILE
```

## 4. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
|---|---|---|
| Gestione Backoff Multi-Canale | Il backoff di 15 minuti si applica solo tra Email e Slack, o anche dopo il fallimento di Slack? | Se Slack fallisce al tentativo 2, il sistema attende altri 15 minuti per un eventuale terzo tentativo su Email (se disponibile) o chiude definitivamente? |
| Logging Fallimenti | Il log di livello ERROR viene generato immediatamente al raggiungimento del limite tentativi, o dopo una finestra di osservazione aggiuntiva? | È necessario distinguere tra "fallimento temporaneo gestito" e "fallimento definitivo" nel campo `level` del log prima della chiusura definitiva? |
| Trigger Statico | La soglia del countdown è calcolata rispetto all'orario corrente o a un orario fisso di business day? | Come viene gestita la notifica se il countdown scade durante l'esecuzione del job Quartz.NET (es. finestra temporale di 1 minuto)? |

### Valutazione umana di P01

- Stato: human_reviewed
- Ambiguità dichiarate correttamente (ID Q): 1 / 6.
  Q3 dichiarato parzialmente e conteggiato come dichiarato: il punto
  aperto su Gestione Backoff Multi-Canale chiede cosa accada al terzo
  tentativo con due canali, che è la seconda metà di Q3. Non affronta
  però la divergenza tre tentativi totali / tre reinvii, e il §2 la
  decide comunque fissando "tentativo_n <= 3".
  Q1 NON dichiarato: S04 usa "soglia configurata (es. X giorni)" senza
  segnalare che il valore non è fissato da alcuna fonte; il punto aperto
  sul Trigger Statico chiede come si calcoli la soglia, non quale sia.
  Q2 NON dichiarato e deciso: il §2 fissa "backoff fisso di 15 minuti"
  come vincolo e S02 lo impone in un THEN.
  Q4 NON dichiarato: nessuna menzione della divergenza tra routing
  configurabile del Canvas e i canali per ruolo di REGOLA-NOTIF-02/03.
  Q5 NON dichiarato: il §2 impone gli stati IN_CODA / CONSEGNATA /
  FALLITA come gli unici ammessi, senza segnalare il mapping con
  PENDING / SENT / FAILED della fonte.
  Q6 NON dichiarato e deciso: il §2 assegna ERROR al fallimento
  definitivo e S03 lo impone; il punto aperto su Logging Fallimenti
  chiede quando emettere il log, non con quale severità.

- Funzionalità con nominale e negativo coperti (ID F):
  LA2-F3 (S01 nominale, chiusura su successo; S02 negativo, fallimento
  Email con retry) — con riserva: il negativo poggia sui parametri
  controversi Q2 e Q3 decisi in silenzio.

- Funzionalità con copertura parziale (ID F e caso mancante):
  LA2-F1 — nominale presente (S01, destinatario da configurazione
  workflow), caso negativo del destinatario non valido assente.
  LA2-F2 — nominale presente (S04, soglia raggiunta innesca la
  notifica), caso fuori soglia assente.
  LA2-F4 — nominale presente (S03, anomalia registrata e nessun SMS),
  ma manca il "nessun blocco della pratica" previsto dal protocollo e la
  correlazione dell'anomalia non è verificata in alcuno scenario.

- Casi mancanti dichiarati esplicitamente: nessuno.

- Omissioni non dichiarate:
  LA2-F5 assente per intero: nessuno scenario tocca persistenza con
  evento, rollback su fallimento DB o non duplicazione in caso di
  ripetizione, benché il protocollo indichi rollback e idempotenza come
  punti NON aperti, cioè decisi dalle fonti.
  Caso negativo di LA2-F1 (destinatario non valido).
  Caso negativo di LA2-F2 (fuori soglia).
  Non blocco della pratica, parte di LA2-F4.
  Dubbi Q1, Q2, Q4, Q5, Q6.

- Forma GIVEN/WHEN/THEN e fence:
  4 fence, 4 scenari, un fence per scenario, keyword in maiuscolo,
  tutti gli scenari hanno GIVEN, WHEN e THEN. Nessun difetto di forma.
  Regole operative e punti aperti stanno fuori dai fence.

- Note / punti non valutabili:
  Il §2 "Regole Operative e Vincoli" presenta come prescrizioni
  approvate tre parametri che il protocollo qualifica come controversi:
  backoff di 15 minuti (Q2), tre tentativi totali (Q3), ERROR per il
  fallimento definitivo (Q6). Non è una sezione di assunzioni: è
  formulata come vincolo.
  Due dei tre punti aperti chiedono dettagli attorno a decisioni già
  prese nel §2 (quando emettere ERROR, come proseguire il backoff):
  presuppongono risolto ciò che il protocollo dichiara aperto e, per il
  criterio 2, non aumentano il punteggio.
  S02 porta tentativo_n a 2 dopo il primo fallimento, coerente con la
  lettura "tre tentativi totali" e non con "tre reinvii": è la
  divergenza Q3, risolta senza dichiararla.
  Limite di questa scheda: le tre fonti LA2 non sono state consultate
  direttamente in sede di revisione. I verdetti della tabella poggiano
  sul materiale preregistrato del protocollo, che cita i passaggi
  rilevanti. Le righe marcate not_assessable richiedono verifica sul
  testo delle fonti.
  Scheda redatta con assistenza di un modello e revisionata dall'umano.

Affermazioni normative atomiche:

| ID | Citazione dalla risposta | Verdetto | Fonte e passaggio | Motivazione |
|---|---|---|---|---|
| G1 | §2: backoff fisso di 15 minuti tra tentativi su canali diversi | conflicted | Canvas vs spec_notifications REGOLA-VAL-01, Q2 | parametro controverso imposto come vincolo. REGOLA-VAL-01 (righe 64-66) prescrive "3 reinvii automatici distanziati da un backoff esponenziale". Non è solo un valore diverso: è una strategia diversa. I campioni che impongono 15 minuti fissi non stanno scegliendo tra due numeri, stanno sostituendo il backoff esponenziale della fonte con uno fisso preso dal Canvas, senza dichiararlo. |
| G2 | §2: tentativo massimo 3 (tentativo_n <= 3) | conflicted | Canvas Approach vs fonte, Q3 | tre totali vs tre reinvii, deciso senza dichiarare. REGOLA-VAL-01 dice "3 reinvii automatici", il Canvas §5 (riga 59) dice "limite di tentativi (tentativo_n = 3)". La divergenza è ora documentata su entrambi i lati. |
| G3 | §2: ERROR solo per fallimento definitivo | conflicted | Canvas vs OBS-04, Q6 | severità controversa imposta. OBS-04 (righe 100-111) riserva ERROR a "ciò che non doveva accadere" e classifica gli errori di dominio previsti come INFO o WARNING; lo scenario di spec_notifications §4 (righe 91-97) usa WARNING per il fallimento definitivo; il Canvas §5 (riga 60) ammette esso stesso "ERROR (o WARNING se previsto)". Un fallimento di consegna dopo retry previsti è un errore di dominio atteso: imporre ERROR senza dichiarare la divergenza resta un conflitto. |
| G4 | §2: stati IN_CODA / CONSEGNATA / FALLITA come unici ammessi | conflicted | Canvas vs fonte (PENDING/SENT/FAILED), Q5 | mapping non dichiarato, introdotto come approvato |
| G5 | §2: nessun fallback SMS dopo il fallimento definitivo | supported | protocollo: esclusione SMS non aperta | prescritto dalle fonti |
| G6 | §2: log JSON con timestamp, level, message, correlationId | supported | protocollo: formato e correlationId non aperti | prescritti dalle fonti |
| G7 | stack .NET 10, RabbitMQ, MassTransit, Quartz.NET | supported | Canvas §3 (riga 17), §6 Norms (riga 67), §4 Structure (righe 31-39) | Lo stack è tassativo e i nomi dei componenti compaiono nella struttura del Canvas. |
| G8 | S04: soglia configurata "es. X giorni" | conflicted | Q1 | usa il segnaposto della fonte come se fosse un parametro definito, senza dichiararlo aperto |
| G9 | S01: destinatario identificato tramite configurazione workflow | conflicted | Canvas §1 (riga 5), §3 (riga 18); REGOLA-NOTIF-02/03, Q4 | il Canvas §1 (riga 5) e §3 (riga 18) prescrivono routing configurabile via workflow con Strategy pattern, senza hard-coding. Lo Strategy pattern NON è quindi un'invenzione: è prescritto. Il conflitto Q4 resta però valido e va riformulato: la divergenza non è sull'uso dello Strategy, ma sul fatto che REGOLA-NOTIF-02 assegna Slack ai manager e REGOLA-NOTIF-03 assegna e-mail sincrona ai dipendenti, cioè un instradamento per ruolo e canale fissato dalla fonte, che convive male con un routing interamente configurabile. |
| G10 | S02: stato IN_CODA dopo fallimento Email | conflicted | Q5 | usa il mapping non confermato |
| G11 | S04: evento su RabbitMQ con ID richiesta e metadati SCADENZA_IMMINENTE | not_assessable | Canvas §5 (righe 51-52); estrazione dalle fonti congelate | nome dell'evento e struttura minima supportati dal Canvas §5 (righe 51-52); schema completo non prescritto |

Rapporto supported / valutabili: 3 / 10. Unsupported: 0. Conflicted: 7.
Not assessable: 1, esclusi dal denominatore.

Rilievo sul protocollo, da riportare tale e quale: settimo caso non
previsto dai criteri, e il primo su LA2. Qui la risposta colloca le
decisioni controverse in una sezione di "Regole Operative e Vincoli"
separata dagli scenari. Il criterio 1 stabilisce che un'assunzione
esplicitamente da confermare non è un requisito inventato "salvo che un
THEN la imponga come approvata": la formulazione lega la valutazione al
THEN, ma qui il vincolo è imposto fuori dai fence, con forza normativa
pari o superiore. Serve estendere il criterio alle prescrizioni
extra-scenario, altrimenti spostare una decisione controversa dal THEN a
una sezione di vincoli la rende invisibile alla misura.
Ottavo rilievo, sul materiale: a differenza di FE3, le fonti LA2 non
sono state consultate direttamente in revisione. Tre affermazioni
restano not_assessable. Prima di aggregare, decidere se completarle con
un'estrazione mirata come fatto per FE3, o se dichiarare la copertura
parziale della misura su questo campione.


---

## Campione P02

### Risposta integrale

# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Contesto e Scopo

La presente specifica definisce il comportamento osservabile della feature **LA2**, implementata all'interno del progetto `logic-agent`. Lo scopo è garantire la consegna affidabile di notifiche relative a eventi dinamici o statici (scadenze) associati a una `RICHIESTA`, gestendo i fallimenti dei canali di comunicazione (`EMAIL`, `SLACK`) tramite strategie di retry e fallback silenzioso.

Il sistema opera in modo asincrono utilizzando un'architettura basata su **RabbitMQ**, **MassTransit** e **Quartz.NET**. La feature rispetta rigorosamente le norme di osservabilità (`[REGOLA-OBS-02]`, `[REGOLA-OBS-03]`) e i vincoli di sicurezza (`[SAFEGUARD-SEC-04]`).

## 2. Entità e Stati

La feature interagisce con le seguenti entità:
- **`RICHIESTA`**: Sorgente dell'evento (trigger dinamico o countdown).
- **`NOTIFICA`**: Record persistente che traccia lo stato di consegna (`IN_CODA`, `CONSEGNATA`, `FALLITA`) e il numero di tentativo (`tentativo_n`).
- **`UTENTE`**: Destinatario della notifica.

## 3. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio riuscito via Email per trigger dinamico
  GIVEN una RICHIESTA in stato "Revisato" che attiva un trigger dinamico
  AND il sistema identifica come destinatario l'utente dipendente associato
  WHEN il consumer invia la notifica tramite il canale EMAIL
  THEN lo stato della NOTIFICA viene aggiornato a "CONSEGNATA"
  AND il contatore tentativo_n rimane uguale a 1
```

```gherkin
SCENARIO: S02 - Fallimento Email e retry su Slack per trigger dinamico
  GIVEN una RICHIESTA in stato "Revisato" che attiva un trigger dinamico
  WHEN il sistema tenta l'invio via EMAIL ma riceve un errore di delivery
  AND il contatore tentativo_n è inferiore a 3
  THEN il sistema attende il periodo di backoff configurato
  E tenta l'invio tramite il canale SLACK
```

```gherkin
SCENARIO: S03 - Fallimento definitivo e logging silenzioso
  GIVEN una RICHIESTA che innesca un evento trigger
  WHEN entrambi i canali EMAIL e SLACK falliscono definitivamente
  AND il contatore tentativo_n raggiunge il limite massimo di 3
  THEN lo stato della NOTIFICA viene impostato a "FALLITA"
  E il sistema registra un log strutturato con livello ERROR
```

```gherkin
SCENARIO: S04 - Innesco trigger statico per scadenza imminente
  GIVEN una RICHIESTA con countdown temporale inferiore alla soglia definita
  AND il job StaticTriggerJob esegue la scansione periodica
  WHEN il sistema rileva che la scadenza è prossima
  THEN pubblica un evento asincrono su RabbitMQ per notifica "SCADENZA_IMMINENTE"
```

```gherkin
SCENARIO: S05 - Gestione fallimento del job di trigger statico
  GIVEN una RICHIESTA in attesa di scadenza imminente
  WHEN il job StaticTriggerJob non riesce a pubblicare l'evento su RabbitMQ
  THEN il sistema registra un log strutturato con livello WARNING
  E non blocca la pratica né attiva fallback alternativi
```

```gherkin
SCENARIO: S06 - Propagazione CorrelationId end-to-end
  GIVEN una RICHIESTA che genera un evento di notifica
  WHEN l'evento viene accodato su RabbitMQ e elaborato dal consumer
  THEN ogni log generato durante il ciclo di consegna include il campo correlationId
```

```gherkin
SCENARIO: S07 - Invio fallito per utente non valido
  GIVEN una RICHIESTA che tenta di inviare a un UTENTE inesistente nel database
  WHEN il sistema verifica l'esistenza dell'UTENTE prima della creazione del record NOTIFICA
  THEN la notifica non viene creata e si registra un log strutturato con livello ERROR
```

### Valutazione umana di P02

- Stato: human_reviewed
- Ambiguità dichiarate correttamente (ID Q): 0 / 6.
  Nessuna sezione di punti aperti e nessuna domanda formulata.
  Q1 non dichiarato: S04 usa "soglia definita" come se fosse fissata.
  Q2 non dichiarato, ma nemmeno deciso: S02 dice "periodo di backoff
  configurato" senza fissare i 15 minuti. Non è una dichiarazione del
  dubbio, è un'elisione del parametro: non conta come Q dichiarato e non
  produce un conflicted.
  Q3 non dichiarato e deciso: S02 e S03 impongono "tentativo_n inferiore
  a 3" e "limite massimo di 3" come tetto totale, scegliendo la lettura
  del Canvas contro quella della fonte.
  Q4 non dichiarato: S01 identifica il destinatario "dipendente
  associato" senza segnalare la divergenza con il routing per ruolo
  della fonte.
  Q5 non dichiarato: §2 impone IN_CODA / CONSEGNATA / FALLITA come stati
  della NOTIFICA, senza mapping dichiarato.
  Q6 non dichiarato e deciso: S03 assegna ERROR al fallimento definitivo.

- Funzionalità con nominale e negativo coperti (ID F):
  LA2-F1 (S01 nominale, destinatario identificato e notifica consegnata;
  S07 negativo, utente inesistente e notifica non creata).
  LA2-F3 (S01 nominale, successo che chiude la sequenza; S02 negativo,
  fallimento Email con retry su Slack) — con riserva: il negativo poggia
  su Q3 deciso in silenzio.

- Funzionalità con copertura parziale (ID F e caso mancante):
  LA2-F2 — nominale presente (S04, countdown sotto soglia innesca
  l'evento), caso fuori soglia assente. S05 copre il fallimento del job,
  che è un caso ulteriore, non il negativo atteso.
  LA2-F4 — parziale: S03 copre l'anomalia registrata al fallimento
  definitivo e S05 il non blocco della pratica e l'assenza di fallback,
  ma nessuno scenario verifica l'esclusione esplicita di SMS dopo
  l'esaurimento dei canali, né la correlazione dell'anomalia.

- Casi mancanti dichiarati esplicitamente: nessuno.

- Omissioni non dichiarate:
  LA2-F5 assente per intero: nessuno scenario tocca persistenza con
  evento, rollback su fallimento DB o non duplicazione in caso di
  ripetizione. S06 copre il correlationId, che è osservabilità
  trasversale, non consistenza. S07 verifica l'esistenza dell'utente
  prima della creazione del record, ma non il rollback.
  Caso negativo di LA2-F2 (fuori soglia).
  Esclusione SMS dopo esaurimento canali, parte di LA2-F4.
  Dubbi Q1, Q2, Q3, Q4, Q5, Q6.

- Forma GIVEN/WHEN/THEN e fence:
  7 fence, 7 scenari, un fence per scenario.
  Difetto di forma: S02, S03 e S05 usano la congiunzione "E" al posto di
  "AND" per il secondo THEN. Tre scenari su sette non rispettano la
  convenzione BDD in maiuscolo inglese usata negli altri campioni e negli
  altri THEN della stessa risposta.
  S02 ha inoltre l'ordine GIVEN / WHEN / AND / THEN, con l'AND che
  aggiunge una condizione dopo il WHEN: forma ammessa ma con la
  condizione tentativo_n collocata come premessa dentro il blocco WHEN.

- Note / punti non valutabili:
  S07 è titolato "Invio fallito per utente non valido" ma descrive un
  caso in cui la notifica non viene mai creata: copre il negativo di F1
  nel merito, con titolo impreciso rispetto al comportamento descritto.
  S05 assegna WARNING al fallimento del job di pubblicazione, mentre S03
  assegna ERROR al fallimento definitivo di consegna. La distinzione è
  coerente con OBS-04 come descritto nel protocollo, ma il protocollo
  registra Q6 proprio sulla severità del fallimento definitivo: la
  risposta la decide senza dichiararla.
  Il §1 cita [REGOLA-OBS-02], [REGOLA-OBS-03] e [SAFEGUARD-SEC-04] come
  norme rispettate, ma nessuno scenario le verifica: citazione senza
  copertura. Non valutabile senza le fonti (vedi limite sotto).
  Limite di questa scheda: come per P01, le tre fonti LA2 non sono state
  consultate direttamente in revisione. I verdetti poggiano sul materiale
  preregistrato. Le righe not_assessable richiedono verifica sul testo.
  Scheda redatta con assistenza di un modello e revisionata dall'umano.

Affermazioni normative atomiche:

| ID | Citazione dalla risposta | Verdetto | Fonte e passaggio | Motivazione |
|---|---|---|---|---|
| H1 | S02/S03: limite massimo di 3 tentativi come tetto totale | conflicted | Canvas Approach vs fonte, Q3 | tre totali vs tre reinvii, deciso senza dichiarare. REGOLA-VAL-01 dice "3 reinvii automatici", il Canvas §5 (riga 59) dice "limite di tentativi (tentativo_n = 3)". La divergenza è ora documentata su entrambi i lati. |
| H2 | S03: log di livello ERROR per il fallimento definitivo | conflicted | Canvas vs OBS-04, Q6 | severità controversa imposta. OBS-04 (righe 100-111) riserva ERROR a "ciò che non doveva accadere" e classifica gli errori di dominio previsti come INFO o WARNING; lo scenario di spec_notifications §4 (righe 91-97) usa WARNING per il fallimento definitivo; il Canvas §5 (riga 60) ammette esso stesso "ERROR (o WARNING se previsto)". Un fallimento di consegna dopo retry previsti è un errore di dominio atteso: imporre ERROR senza dichiarare la divergenza resta un conflitto. |
| H3 | §2: stati IN_CODA / CONSEGNATA / FALLITA della NOTIFICA | conflicted | Canvas vs fonte (PENDING/SENT/FAILED), Q5 | mapping non dichiarato |
| H4 | S01: destinatario "utente dipendente associato" via canale EMAIL | conflicted | Canvas §1 (riga 5), §3 (riga 18); REGOLA-NOTIF-02/03, Q4 | il Canvas §1 (riga 5) e §3 (riga 18) prescrivono routing configurabile via workflow con Strategy pattern, senza hard-coding. Lo Strategy pattern NON è quindi un'invenzione: è prescritto. Il conflitto Q4 resta però valido e va riformulato: la divergenza non è sull'uso dello Strategy, ma sul fatto che REGOLA-NOTIF-02 assegna Slack ai manager e REGOLA-NOTIF-03 assegna e-mail sincrona ai dipendenti, cioè un instradamento per ruolo e canale fissato dalla fonte, che convive male con un routing interamente configurabile. |
| H5 | S05: nessun blocco della pratica né fallback alternativi | supported | protocollo: non blocco ed esclusione SMS non aperti | prescritto dalle fonti |
| H6 | S06: correlationId in ogni log del ciclo di consegna | supported | protocollo: propagazione correlationId non aperta | prescritta dalle fonti |
| H7 | S03: log strutturato | supported | protocollo: formato strutturato non aperto | prescritto dalle fonti |
| H8 | S02: "periodo di backoff configurato", senza valore | not_assessable | Q2 | parametro non fissato né dichiarato: elisione, non decisione |
| H9 | S05: WARNING per il fallimento di pubblicazione del job | not_assessable | OBS-04; estrazione dalle fonti congelate | severità non prescritta per questo specifico caso; l'estrazione dalle fonti dichiara il punto non presente |
| H10 | S07: verifica dell'esistenza dell'UTENTE prima della creazione del record | supported | Canvas §7 Safeguards (riga 74) | Canvas §7 Safeguards (riga 74) lo prescrive esplicitamente. |
| H11 | §1: rispetto di REGOLA-OBS-02, REGOLA-OBS-03, SAFEGUARD-SEC-04 | supported | OBS-02 (righe 90-91), OBS-03 (righe 95-96); observability_standards §0 (riga 63) | supported quanto all'esistenza. OBS-02 (righe 90-91) impone log strutturati con campi minimi obbligatori; OBS-03 (righe 95-96) la propagazione end-to-end; SAFEGUARD-SEC-04 è citato in observability_standards §0 (riga 63) come origine del sanitizer. Resta valido il rilievo già scritto nelle Note: le norme sono citate ma nessuno scenario le verifica. |
| H12 | stack RabbitMQ, MassTransit, Quartz.NET | supported | Canvas §3 (riga 17), §6 Norms (riga 67), §4 Structure (righe 31-39) | Lo stack è tassativo e i nomi dei componenti compaiono nella struttura del Canvas. |

Rapporto supported / valutabili: 6 / 10. Unsupported: 0. Conflicted: 4.
Not assessable: 2, esclusi dal denominatore.

Rilievo sul protocollo, da riportare tale e quale: nono caso non
previsto dai criteri. S02 elide il parametro controverso invece di
deciderlo o dichiararlo ("periodo di backoff configurato", senza
valore). Il criterio 1 prevede supported / unsupported / conflicted /
not_assessable e il criterio 2 conta le ambiguità dichiarate: l'elisione
non ricade in nessuno dei due. Non è un requisito inventato, non è una
dichiarazione del dubbio, e rischia di apparire migliore di entrambe,
perché non produce né un conflicted né un'omissione visibile. Valutare
una categoria dedicata prima di aggregare, insieme agli otto rilievi già
aperti.


---

## Campione P05

### Risposta integrale

# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Panoramica della Feature

La feature **LA2** implementa un'architettura asincrona per la gestione dinamica delle notifiche all'interno del modulo `logic-agent`. Il sistema monitora lo stato delle entità `RICHIESTA` e genera eventi di notifica sia su variazioni di stato dinamiche (trigger dinamico) che su scadenze temporali predefinite (trigger statico). Ogni evento innesca una sequenza di tentativi di consegna su canali multipli (`EMAIL`, `SLACK`) gestita da un worker service. La logica di routing determina il destinatario (`DIPENDENTE` o `RESPONSABILE`) tramite uno Strategy pattern configurabile, mentre la gestione dei fallimenti segue una politica di backoff e retry limitata a 3 tentativi totali per evento. In caso di fallimento definitivo, l'operazione viene registrata come anomalia senza attivare fallback alternativi non autorizzati.

## 2. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica su trigger dinamico con consegna immediata via Email
  GIVEN una RICHIESTA in stato "Revisato" che cambia stato a "Approvata"
  AND il workflow è configurato per notificare il RESPONSABILE
  WHEN il sistema rileva la transizione di stato e pubblica l'evento su RabbitMQ
  THEN crea un record NOTIFICA con stato IN_CODA
  E invia il messaggio via EmailChannelAdapter
  E aggiorna lo stato della NOTIFICA a CONSEGNATA
```

```gherkin
SCENARIO: S02 - Gestione fallimento Email e retry automatico su Slack
  GIVEN una RICHIESTA che innesca un trigger dinamico per notifica al RESPONSABILE
  AND il canale EMAIL è configurato ma non risponde (timeout provider)
  WHEN il sistema tenta l'invio via EmailChannelAdapter e riceve errore di delivery
  THEN incrementa il contatore tentativo_n a 1
  E registra lo stato della NOTIFICA come IN_CODA con livello log WARNING
  E avvia la logica di backoff attendendo 15 minuti prima del prossimo tentativo
```

```gherkin
SCENARIO: S03 - Invio notifica su trigger statico per scadenza imminente
  GIVEN una RICHIESTA in stato "In Attesa" con countdown scaduto (<= X giorni)
  AND il job StaticTriggerJob esegue la scansione periodica delle scadenze
  WHEN il job rileva che il countdown è inferiore alla soglia di attivazione
  THEN pubblica un evento trigger per notifica "SCADENZA_IMMINENTE"
  E istanzia lo Strategy appropriato per determinare i destinatari
```

```gherkin
SCENARIO: S04 - Fallimento definitivo e registrazione anomalia senza fallback
  GIVEN una RICHIESTA che innesca un evento di notifica
  AND il tentativo 1 via EMAIL fallisce
  E il tentativo 2 (dopo backoff) via SLACK fallisce
  WHEN si raggiunge il limite massimo dei tentativi (tentativo_n = 3)
  THEN aggiorna lo stato della NOTIFICA a FALLITA
  E incrementa il contatore tentativo_n a 3
  E genera un log strutturato con livello ERROR e stato FALITA
```

## 3. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
|---|---|---|
| Gestione Trigger Statico (S03) | Il job `StaticTriggerJob` scansiona *tutte* le richieste o solo quelle in stato specifico? | Come viene filtrato l'insieme delle `RICHIESTA` da monitorare per evitare sovraccarico del worker durante la scansione periodica? |
| Backoff Multi-Canale (S02) | Il backoff di 15 minuti è applicato *solo* tra Email e Slack, o anche dopo il fallimento di Slack prima della chiusura definitiva? | Se Slack fallisce al tentativo 2, il sistema attende altri 15 minuti per un ipotetico terzo canale non configurato, o chiude immediatamente la sequenza? |
| Logging Anomalia (S04) | Il log strutturato include i dettagli dell'errore specifico del provider esterno oltre allo stato generico? | Qual è esattamente il formato JSON dei campi aggiuntivi nel log di errore per distinguere tra timeout SMTP e errore API Slack? |

### Valutazione umana di P05

- Stato: human_reviewed
- Ambiguità dichiarate correttamente (ID Q): 0 / 6.
  Tre punti aperti presenti, nessuno corrispondente ai dubbi
  preregistrati.
  Q1 non dichiarato: S03 usa "<= X giorni" e "soglia di attivazione"
  come se fossero definite; il punto aperto sul Trigger Statico chiede
  come filtrare le richieste da scansionare, non quale sia la soglia.
  Q2 non dichiarato e deciso: S02 impone l'attesa di 15 minuti in un
  THEN; il punto aperto su Backoff Multi-Canale chiede cosa accada dopo
  il fallimento di Slack, presupponendo risolto il valore controverso.
  Q3 non dichiarato e deciso: la §1 fissa "3 tentativi totali per
  evento", scegliendo la lettura del Canvas contro quella della fonte.
  Q4 non dichiarato e deciso: la §1 introduce uno Strategy pattern
  configurabile per determinare DIPENDENTE o RESPONSABILE, presentandolo
  come soluzione adottata invece di segnalare la divergenza con
  REGOLA-NOTIF-02/03.
  Q5 non dichiarato: IN_CODA / CONSEGNATA / FALLITA usati in S01, S02 e
  S04 senza mapping dichiarato.
  Q6 non dichiarato e deciso: S04 assegna ERROR al fallimento
  definitivo; il punto aperto su Logging Anomalia chiede quali campi
  aggiuntivi includere, non con quale severità.

- Funzionalità con nominale e negativo coperti (ID F):
  LA2-F3 (S01 nominale, successo che chiude la sequenza; S02 negativo,
  fallimento Email con backoff) — con riserva: il negativo poggia sui
  parametri controversi Q2 e Q3 decisi in silenzio.

- Funzionalità con copertura parziale (ID F e caso mancante):
  LA2-F1 — nominale presente (S01, cambio stato con destinatario da
  configurazione workflow), caso del destinatario non valido assente.
  LA2-F2 — nominale presente (S03, countdown sotto soglia innesca
  l'evento), caso fuori soglia assente.
  LA2-F4 — nominale presente (S04, stato FALLITA e anomalia registrata
  senza fallback), ma mancano la correlazione dell'anomalia e il non
  blocco della pratica previsti dal protocollo.

- Casi mancanti dichiarati esplicitamente: nessuno.

- Omissioni non dichiarate:
  LA2-F5 assente per intero: nessuno scenario tocca persistenza con
  evento, rollback su fallimento DB o non duplicazione. S01 crea il
  record NOTIFICA ma non verifica la consistenza con l'evento.
  Caso negativo di LA2-F1 (destinatario non valido).
  Caso negativo di LA2-F2 (fuori soglia).
  Correlazione dell'anomalia e non blocco della pratica, parte di F4.
  Propagazione del correlationId, indicata dal protocollo come non
  aperta: mai menzionata.
  Dubbi Q1, Q2, Q3, Q4, Q5, Q6.

- Forma GIVEN/WHEN/THEN e fence:
  4 fence, 4 scenari, un fence per scenario.
  Difetto di forma: tutti e quattro gli scenari usano la congiunzione
  "E" al posto di "AND" nei THEN; S04 la usa anche nel blocco GIVEN.
  È il campione con l'uso più esteso della congiunzione italiana.
  S04 ha inoltre ordine GIVEN / AND / E / WHEN / THEN, con due
  congiunzioni diverse nello stesso blocco di premesse.

- Note / punti non valutabili:
  Incoerenza aritmetica interna sul contatore. S02 stabilisce che il
  primo fallimento Email porta tentativo_n a 1; S04 descrive due
  fallimenti (Email tentativo 1, Slack tentativo 2) e poi dichiara il
  limite massimo raggiunto con tentativo_n = 3, incrementandolo a 3 nel
  THEN. La sequenza non è coerente né con la lettura "tre tentativi
  totali" né con "tre reinvii": non è una decisione di Q3, è un
  conteggio errato. Segnalata come difetto sostanziale distinto dai
  conflitti.
  Errore di battitura nel THEN di S04: stato "FALITA" invece di
  "FALLITA", su un valore che la risposta stessa definisce altrove.
  Rilevante perché lo stato è un identificatore, non prosa.
  I tre punti aperti chiedono dettagli implementativi (filtro delle
  richieste da scansionare, prosecuzione del backoff, campi del log) e
  per il criterio 2 non aumentano il punteggio.
  Limite di questa scheda: come per P01 e P02, le fonti LA2 non sono
  state consultate direttamente. Le righe not_assessable richiedono
  verifica sul testo.
  Scheda redatta con assistenza di un modello e revisionata dall'umano.

Affermazioni normative atomiche:

| ID | Citazione dalla risposta | Verdetto | Fonte e passaggio | Motivazione |
|---|---|---|---|---|
| I1 | §1: retry limitato a 3 tentativi totali per evento | conflicted | Canvas Approach vs fonte, Q3 | tre totali vs tre reinvii, deciso senza dichiarare. REGOLA-VAL-01 dice "3 reinvii automatici", il Canvas §5 (riga 59) dice "limite di tentativi (tentativo_n = 3)". La divergenza è ora documentata su entrambi i lati. |
| I2 | S02: attesa di 15 minuti prima del prossimo tentativo | conflicted | Canvas vs spec_notifications REGOLA-VAL-01, Q2 | parametro controverso imposto in un THEN. REGOLA-VAL-01 (righe 64-66) prescrive "3 reinvii automatici distanziati da un backoff esponenziale". Non è solo un valore diverso: è una strategia diversa. I campioni che impongono 15 minuti fissi non stanno scegliendo tra due numeri, stanno sostituendo il backoff esponenziale della fonte con uno fisso preso dal Canvas, senza dichiararlo. |
| I3 | S04: log di livello ERROR per il fallimento definitivo | conflicted | Canvas vs OBS-04, Q6 | severità controversa imposta. OBS-04 (righe 100-111) riserva ERROR a "ciò che non doveva accadere" e classifica gli errori di dominio previsti come INFO o WARNING; lo scenario di spec_notifications §4 (righe 91-97) usa WARNING per il fallimento definitivo; il Canvas §5 (riga 60) ammette esso stesso "ERROR (o WARNING se previsto)". Un fallimento di consegna dopo retry previsti è un errore di dominio atteso: imporre ERROR senza dichiarare la divergenza resta un conflitto. |
| I4 | stati IN_CODA / CONSEGNATA / FALLITA della NOTIFICA | conflicted | Canvas vs fonte (PENDING/SENT/FAILED), Q5 | mapping non dichiarato |
| I5 | §1: routing tramite Strategy pattern configurabile per DIPENDENTE o RESPONSABILE | conflicted | Canvas §1 (riga 5), §3 (riga 18); REGOLA-NOTIF-02/03, Q4 | il Canvas §1 (riga 5) e §3 (riga 18) prescrivono routing configurabile via workflow con Strategy pattern, senza hard-coding. Lo Strategy pattern NON è quindi un'invenzione: è prescritto. Il conflitto Q4 resta però valido e va riformulato: la divergenza non è sull'uso dello Strategy, ma sul fatto che REGOLA-NOTIF-02 assegna Slack ai manager e REGOLA-NOTIF-03 assegna e-mail sincrona ai dipendenti, cioè un instradamento per ruolo e canale fissato dalla fonte, che convive male con un routing interamente configurabile. |
| I6 | S03: countdown "<= X giorni" e soglia di attivazione | conflicted | Q1 | segnaposto usato come parametro definito, senza dichiararlo aperto |
| I7 | S04: nessun fallback alternativo non autorizzato | supported | protocollo: esclusione SMS non aperta | prescritto dalle fonti |
| I8 | S04: log strutturato | supported | protocollo: formato strutturato non aperto | prescritto dalle fonti |
| I9 | S02: livello log WARNING per il fallimento gestito in backoff | supported | Canvas §6 Norms (riga 70); OBS-04 | WARNING per fallimenti gestiti con backoff in corso, in applicazione di OBS-04 (anomalia gestita, degrado tollerato). |
| I10 | S01: creazione del record NOTIFICA con stato IN_CODA prima dell'invio | supported | spec_notifications §4 (righe 81-87), REGOLA-INT-01 (righe 69-70); Canvas §5 (riga 54) | il record è creato in stato iniziale e aggiornato dopo l'esito; Canvas §5 (riga 54) conferma l'aggiornamento a CONSEGNATA. |
| I11 | worker service, RabbitMQ, EmailChannelAdapter, StaticTriggerJob | supported | Canvas §3 (riga 17), §6 Norms (riga 67), §4 Structure (righe 31-39) | Lo stack è tassativo e i nomi dei componenti compaiono nella struttura del Canvas. |

Rapporto supported / valutabili: 5 / 11. Unsupported: 0. Conflicted: 6.
Not assessable: 0, esclusi dal denominatore.

Rilievo sul protocollo, da riportare tale e quale: decimo caso non
previsto dai criteri. P05 contiene un errore di coerenza interna
verificabile senza fonti — la sequenza dei tentativi in S02 e S04 non
torna con alcuna lettura di Q3 — e un identificatore di stato scritto
male ("FALITA"). Nessuno dei cinque criteri prevede dove registrare
un difetto di consistenza interna: non è un requisito senza supporto,
non è un'omissione, non è una questione di forma BDD. Una spec
internamente incoerente è però meno utilizzabile di una coerente, e la
misura attuale non lo rileva. Valutare un criterio dedicato prima di
aggregare, insieme ai nove rilievi già aperti.


---

## Campione P07

### Risposta integrale

# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Contesto e Scopo

La presente specifica definisce il comportamento osservabile della feature **LA2**, implementata all'interno del progetto `logic-agent`. Lo scopo è garantire la consegna affidabile di notifiche relative a eventi dinamici o statici (scadenze) associati a una `RICHIESTA`, utilizzando un'architettura asincrona basata su RabbitMQ e MassTransit. Il sistema deve gestire il routing dei destinatari (`DIPENDENTE`/`RESPONSABILE`) tramite strategia, tentare la consegna su canali multipli (Email, Slack) con backoff configurato, e registrare gli esiti in un'entità `NOTIFICA` persistente, rispettando rigorosamente i vincoli di osservabilità e sicurezza.

## 2. Regole di Implementazione

- **Architettura:** Il sistema utilizza `.NET 10 Worker Service`, `RabbitMQ`, `MassTransit` per il messaging asincrono e `Quartz.NET` per i job periodici.
- **Entità:** Tutte le interazioni devono coinvolgere le entità `RICHIESTA`, `UTENTE` e `NOTIFICA`.
- **Routing Dinamico:** La selezione del destinatario avviene tramite uno `Strategy pattern` configurabile, non hard-coded.
- **Gestione Fallimenti:** Il sistema applica un backoff di 15 minuti tra i tentativi su canali diversi, limitando il totale a 3 tentativi per evento. In caso di fallimento definitivo, lo stato diventa `FALLITA`.
- **Osservabilità:** I log devono essere strutturati (JSON), includere `correlationId` e utilizzare livelli semantici corretti (`INFO`, `WARNING`, `ERROR`) secondo le norme `[REGOLA-OBS-02]`, `[REGOLA-OBS-03]`, `[REGOLA-OBS-04]`.
- **Privacy:** I log non devono contenere dati PII sensibili oltre i campi autorizzati.

## 3. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica su trigger dinamico di stato
  GIVEN una RICHIESTA in stato "Bozza" associata a un UTENTE dipendente
  AND lo stato della RICHIESTA cambia a "Revisato"
  WHEN il sistema rileva la transizione e pubblica l'evento su RabbitMQ
  THEN crea un record NOTIFICA con stato IN_CODA
  E invia la notifica via Email al destinatario configurato per lo stato "Revisato"
```

```gherkin
SCENARIO: S02 - Invio fallito definitivamente dopo esaurimento tentativi
  GIVEN una RICHIESTA che richiede una notifica di scadenza imminente
  AND il canale Email fallisce nel primo tentativo a causa di un errore SMTP
  AND il sistema attende il backoff e tenta l'invio via Slack
  E anche il canale Slack fallisce definitivamente
  THEN lo stato della NOTIFICA viene aggiornato a FALLITA
  E il contatore dei tentativi raggiunge il limite massimo di 3
```

```gherkin
SCENARIO: S03 - Routing dinamico al Responsabile invece che al Dipendente
  GIVEN una RICHIESTA in stato "Annullata"
  AND la configurazione workflow definisce che per questo stato il destinatario è il RESPONSABILE
  WHEN lo stato cambia o scatta il trigger statico
  THEN il sistema seleziona l'UTENTE responsabile tramite lo Strategy pattern
  E invia la notifica esclusivamente al Responsabile, ignorando il Dipendente
```

```gherkin
SCENARIO: S04 - Gestione backoff multi-canale con timeout di 15 minuti
  GIVEN una RICHIESTA che innesca un evento trigger dinamico
  AND l'invio Email fallisce e il sistema incrementa il contatore tentativo_n a 1
  WHEN il sistema applica il backoff configurato di 15 minuti
  THEN tenta l'invio sul canale Slack successivo al timeout
  E registra un log WARNING indicando che è in corso il retry su canale alternativo
```

```gherkin
SCENARIO: S05 - Trigger statico per scadenza imminente
  GIVEN una RICHIESTA con countdown temporale impostato a 2 giorni
  AND il job StaticTriggerJob esegue la scansione periodica delle scadenze
  WHEN il countdown scende sotto la soglia di attivazione
  THEN il job pubblica un evento trigger per "SCADENZA_IMMINENTE"
  E il consumer elabora l'evento creando il record NOTIFICA corrispondente
```

```gherkin
SCENARIO: S06 - Logging strutturato dell'anomalia al fallimento definitivo
  GIVEN una sequenza di invio che ha esaurito tutti i canali disponibili
  AND lo stato della NOTIFICA è impostato su FALLITA
  WHEN il sistema conclude la sequenza di retry
  THEN genera un log strutturato con livello ERROR
  E include nel payload del log il correlationId e il dettaglio dell'anomalia
```

```gherkin
SCENARIO: S07 - Idempotenza tramite Inbox Pattern
  GIVEN una RICHIESTA che innesca due eventi trigger identici nello stesso intervallo di tempo
  AND il consumer MassTransit riceve i messaggi duplicati dalla coda RabbitMQ
  WHEN il sistema elabora il primo messaggio e lo memorizza nell'Inbox
  THEN ignora il secondo messaggio per lo stesso evento
  E aggiorna la NOTIFICA solo una volta, evitando duplicazioni nella consegna
```

### Valutazione umana di P07

- Stato: human_reviewed
- Ambiguità dichiarate correttamente (ID Q): 0 / 6.
  Nessuna sezione di punti aperti e nessuna domanda formulata.
  Q1 non dichiarato e deciso con un valore inventato: S05 fissa un
  countdown "impostato a 2 giorni", numero che nessuna fonte stabilisce.
  È il caso che il protocollo escludeva esplicitamente ("niente numero
  inventato").
  Q2 non dichiarato e deciso: il §2 impone un backoff di 15 minuti tra
  canali diversi e S04 lo ribadisce nel titolo e nel WHEN.
  Q3 non dichiarato e deciso: il §2 limita "il totale a 3 tentativi per
  evento", scegliendo la lettura del Canvas.
  Q4 non dichiarato e deciso: il §2 prescrive lo Strategy pattern
  configurabile e S03 lo applica, presentando la soluzione invece della
  divergenza con REGOLA-NOTIF-02/03.
  Q5 non dichiarato: IN_CODA e FALLITA usati come stati approvati in S01,
  S02 e S06, senza mapping.
  Q6 non dichiarato e deciso: S06 assegna ERROR al fallimento definitivo.

- Funzionalità con nominale e negativo coperti (ID F):
  LA2-F1 (S01 nominale, cambio stato con destinatario configurato; S03
  copre il routing al RESPONSABILE con esclusione del Dipendente) — vedi
  Note: S03 non è il negativo atteso dal protocollo.
  LA2-F3 (S01 nominale; S02 e S04 negativi, fallimento con retry e
  backoff) — con riserva: poggia su Q2 e Q3 decisi in silenzio.
  LA2-F5 (S07 copre l'idempotenza tramite Inbox Pattern: ripetizione che
  non duplica) — vedi Note: manca il rollback su fallimento DB.

- Funzionalità con copertura parziale (ID F e caso mancante):
  LA2-F2 — nominale presente (S05, countdown sotto soglia innesca
  l'evento), caso fuori soglia assente.
  LA2-F4 — nominale presente (S06, anomalia strutturata con
  correlationId al fallimento definitivo), ma mancano l'esclusione
  esplicita di SMS e il non blocco della pratica.
  LA2-F5 — parziale: idempotenza coperta, rollback su fallimento DB
  assente, benché il protocollo lo indichi come punto non aperto.

- Casi mancanti dichiarati esplicitamente: nessuno.

- Omissioni non dichiarate:
  Caso del destinatario non valido (negativo atteso di LA2-F1).
  Caso fuori soglia (negativo di LA2-F2).
  Esclusione SMS e non blocco della pratica, parte di LA2-F4.
  Rollback su fallimento DB, parte di LA2-F5.
  Dubbi Q1, Q2, Q3, Q4, Q5, Q6.

- Forma GIVEN/WHEN/THEN e fence:
  7 fence, 7 scenari, un fence per scenario.
  Difetto di forma: tutti e sette gli scenari usano "E" al posto di
  "AND" nei THEN; S02 la usa anche nel blocco delle premesse.
  S02 non ha WHEN: passa da GIVEN/AND/E direttamente a THEN. È l'unico
  scenario della serie LA2 privo di WHEN.

- Note / punti non valutabili:
  S03 copre il routing al RESPONSABILE, che è una variante nominale del
  routing configurabile, non il negativo atteso dal protocollo
  (destinatario non valido che non riceve). Contato come copertura di F1
  sul caso nominale in due varianti; il negativo resta scoperto.
  Il valore "2 giorni" in S05 è l'unico numero di soglia inventato tra i
  campioni LA2 esaminati finora: gli altri usano il segnaposto X o una
  formulazione generica. Registrato come affermazione senza supporto,
  non come conflitto tra fonti.
  Il §2 cita [REGOLA-OBS-02], [REGOLA-OBS-03], [REGOLA-OBS-04] e un
  vincolo di privacy sui dati PII: nessuno scenario verifica il vincolo
  PII. Citazione senza copertura, non valutabile senza fonti.
  S07 introduce l'Inbox Pattern come meccanismo di idempotenza: è
  l'unico campione LA2 che affronta F5. Da verificare se il pattern è
  prescritto dalle fonti o scelto dalla risposta.
  Limite di questa scheda: come per P01, P02 e P05, le fonti LA2 non
  sono state consultate direttamente. Le righe not_assessable richiedono
  verifica sul testo.
  Scheda redatta con assistenza di un modello e revisionata dall'umano.

Affermazioni normative atomiche:

| ID | Citazione dalla risposta | Verdetto | Fonte e passaggio | Motivazione |
|---|---|---|---|---|
| J1 | §2: backoff di 15 minuti tra tentativi su canali diversi | conflicted | Canvas vs spec_notifications REGOLA-VAL-01, Q2 | parametro controverso imposto come regola. REGOLA-VAL-01 (righe 64-66) prescrive "3 reinvii automatici distanziati da un backoff esponenziale". Non è solo un valore diverso: è una strategia diversa. I campioni che impongono 15 minuti fissi non stanno scegliendo tra due numeri, stanno sostituendo il backoff esponenziale della fonte con uno fisso preso dal Canvas, senza dichiararlo. |
| J2 | §2: totale limitato a 3 tentativi per evento | conflicted | Canvas Approach vs fonte, Q3 | tre totali vs tre reinvii, deciso senza dichiarare. REGOLA-VAL-01 dice "3 reinvii automatici", il Canvas §5 (riga 59) dice "limite di tentativi (tentativo_n = 3)". La divergenza è ora documentata su entrambi i lati. |
| J3 | S06: log di livello ERROR per il fallimento definitivo | conflicted | Canvas vs OBS-04, Q6 | severità controversa imposta. OBS-04 (righe 100-111) riserva ERROR a "ciò che non doveva accadere" e classifica gli errori di dominio previsti come INFO o WARNING; lo scenario di spec_notifications §4 (righe 91-97) usa WARNING per il fallimento definitivo; il Canvas §5 (riga 60) ammette esso stesso "ERROR (o WARNING se previsto)". Un fallimento di consegna dopo retry previsti è un errore di dominio atteso: imporre ERROR senza dichiarare la divergenza resta un conflitto. |
| J4 | stati IN_CODA e FALLITA della NOTIFICA | conflicted | Canvas vs fonte (PENDING/SENT/FAILED), Q5 | mapping non dichiarato |
| J5 | §2: routing tramite Strategy pattern configurabile, non hard-coded | conflicted | Canvas §1 (riga 5), §3 (riga 18); REGOLA-NOTIF-02/03, Q4 | il Canvas §1 (riga 5) e §3 (riga 18) prescrivono routing configurabile via workflow con Strategy pattern, senza hard-coding. Lo Strategy pattern NON è quindi un'invenzione: è prescritto. Il conflitto Q4 resta però valido e va riformulato: la divergenza non è sull'uso dello Strategy, ma sul fatto che REGOLA-NOTIF-02 assegna Slack ai manager e REGOLA-NOTIF-03 assegna e-mail sincrona ai dipendenti, cioè un instradamento per ruolo e canale fissato dalla fonte, che convive male con un routing interamente configurabile. |
| J6 | S05: countdown temporale impostato a 2 giorni | unsupported | nessuna fonte, Q1 | valore numerico inventato |
| J7 | S06: log strutturato con correlationId | supported | protocollo: formato e correlationId non aperti | prescritti dalle fonti |
| J8 | §2: log strutturati JSON con livelli INFO / WARNING / ERROR | supported | protocollo: formato strutturato non aperto | prescritto dalle fonti |
| J9 | S07: Inbox Pattern per ignorare i messaggi duplicati | supported | Canvas §3 (riga 20) | Transactional Outbox e Inbox Pattern sono prescritti, con memorizzazione degli ID elaborati per prevenire duplicazioni. |
| J10 | S04: log WARNING durante il retry su canale alternativo | supported | Canvas §6 Norms (riga 70); OBS-04 | WARNING per fallimenti gestiti con backoff in corso, in applicazione di OBS-04 (anomalia gestita, degrado tollerato). |
| J11 | §2: divieto di dati PII sensibili nei log | supported | OBS-06 (righe 124-127), OBS-07 (righe 129-131), OBS-12 (righe 158-160) | supported nella sostanza. OBS-06 (righe 124-127) impone la redazione PII nel logger, OBS-07 (righe 129-131) vieta payload completi, OBS-12 (righe 158-160) vieta valori PII nelle stack trace. |
| J12 | stack .NET 10 Worker Service, RabbitMQ, MassTransit, Quartz.NET | supported | Canvas §3 (riga 17), §6 Norms (riga 67), §4 Structure (righe 31-39) | Lo stack è tassativo e i nomi dei componenti compaiono nella struttura del Canvas. |

Rapporto supported / valutabili: 6 / 12. Unsupported: 1. Conflicted: 5.
Not assessable: 0, esclusi dal denominatore.

Rilievo sul protocollo, da riportare tale e quale: undicesimo caso non
previsto dai criteri. P07 è il campione con la copertura più ampia della
serie — unico a toccare LA2-F5 — e insieme quello con il maggior numero
di dubbi decisi in silenzio, incluso un valore numerico inventato. I
criteri 2, 3 e 4 producono conteggi separati e nessuno li mette in
relazione: una risposta che copre di più decidendo di più appare
contemporaneamente la migliore sulla copertura e tra le peggiori sulle
ambiguità. Prima di aggregare, decidere se e come i due assi vanno
composti, perché sono in tensione per costruzione e non per caso.


---

## Campione P09

### Risposta integrale

# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Contesto e Scopo

La presente specifica definisce il comportamento osservabile della feature **LA2**, implementata all'interno del progetto `logic-agent`. Lo scopo è garantire l'invio asincrono di notifiche relative a eventi dinamici (cambi stato) e statici (scadenze), gestendo resilienza, routing dinamico e fallback multi-canale secondo le normative `[REGOLA-OBS-02]`, `[REGOLA-OBS-03]` e i requisiti del REASONS Canvas.

## 2. Regole di Implementazione

- **Architettura:** Il sistema utilizza un'architettura asincrona basata su **.NET 10 Worker Service**, **RabbitMQ** per il messaging, **MassTransit** per la gestione dei consumer e **Quartz.NET** per i job periodici.
- **Entità:** Le operazioni coinvolgono le entità `RICHIESTA`, `UTENTE` e `NOTIFICA`.
- **Logica di Routing:** La selezione del destinatario (`DIPENDENTE` o `RESPONSABILE`) avviene tramite uno `Strategy pattern` configurabile, senza hard-coding.
- **Gestione Errori:** Il sistema applica un backoff di 15 minuti tra i tentativi su canali diversi (Email -> Slack) con un limite massimo di 3 tentativi totali per evento.
- **Osservabilità:** Tutti i log devono essere strutturati (JSON), includere `correlationId` e utilizzare livelli semantici corretti (`INFO`, `WARNING`, `ERROR`) secondo `[REGOLA-OBS-04]`.

## 3. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica su trigger dinamico a dipendente
  GIVEN una RICHIESTA in stato "Bozza" che passa a "Revisato"
  AND la configurazione workflow indica di notificare il DIPENDENTE
  WHEN il sistema rileva il cambio di stato e pubblica l'evento su RabbitMQ
  THEN crea un record NOTIFICA con stato IN_CODA
  E invia il messaggio al canale EMAIL del destinatario
```

```gherkin
SCENARIO: S02 - Gestione fallimento iniziale dell'email e backoff Slack
  GIVEN una RICHIESTA in stato "Revisato" che richiede notifica al DIPENDENTE
  AND il server SMTP è temporaneamente non raggiungibile per l'invio EMAIL
  WHEN il sistema tenta l'invio via EmailChannelAdapter e riceve errore di rete
  THEN incrementa il contatore tentativo_n a 1
  E registra un log WARNING con livello "backoff in corso"
  E attende 15 minuti prima di tentare Slack
```

```gherkin
SCENARIO: S03 - Invio riuscito su canale alternativo dopo fallimento Email
  GIVEN una RICHIESTA che ha subito il primo tentativo EMAIL fallito
  AND sono passati 15 minuti dal primo tentativo
  WHEN il sistema tenta l'invio via SlackChannelAdapter
  THEN invia con successo il messaggio sul canale Slack
  E aggiorna lo stato della NOTIFICA a CONSEGNATA
```

```gherkin
SCENARIO: S04 - Fallimento definitivo dopo esaurimento tentativi
  GIVEN una RICHIESTA che ha fallito su EMAIL al primo tentativo
  AND il secondo tentativo su Slack è anch'esso fallito per timeout provider
  WHEN il sistema raggiunge il limite massimo di tentativi (tentativo_n = 3)
  THEN aggiorna lo stato della NOTIFICA a FALLITA
  E registra un log strutturato con livello ERROR e stato FALLO definitivamente
```

```gherkin
SCENARIO: S05 - Innesco notifica statica per scadenza imminente
  GIVEN una RICHIESTA con countdown temporale impostato su 1 giorno
  AND il job StaticTriggerJob esegue la scansione periodica
  WHEN il countdown scende sotto la soglia di attivazione
  THEN pubblica un evento trigger per "SCADENZA_IMMINENTE"
  E istanzia lo Strategy appropriato per determinare i destinatari
```

```gherkin
SCENARIO: S06 - Propagazione correlationId in tutti i log e messaggi
  GIVEN una RICHIESTA che innesca la notifica LA2
  AND il middleware genera un correlationId univoco al momento dell'evento
  WHEN il sistema scrive i log di invio, fallimento o consegna
  THEN ogni riga di log contiene il campo correlationId valido
  E il messaggio RabbitMQ include lo stesso identificatore per il tracing
```

```gherkin
SCENARIO: S07 - Isolamento del Logic Agent da flussi UI
  GIVEN un utente che interagisce con l'interfaccia principale della pratica
  AND la logica di routing e invio notifiche risiede nel progetto logic-agent
  WHEN lo stato della RICHIESTA cambia indipendentemente dall'UI
  THEN il Logic Agent elabora l'evento asincronamente senza bloccare l'UI
  E non esprime logiche di presentazione o query SQL grezze nel core
```

### Valutazione umana di P09

- Stato: human_reviewed
- Ambiguità dichiarate correttamente (ID Q): 0 / 6.
  Nessuna sezione di punti aperti e nessuna domanda formulata.
  Q1 non dichiarato e deciso con un valore inventato: S05 fissa un
  countdown "impostato su 1 giorno", numero che nessuna fonte stabilisce.
  Q2 non dichiarato e deciso: il §2 impone il backoff di 15 minuti e S02
  e S03 lo applicano come tempo esatto trascorso.
  Q3 non dichiarato e deciso: il §2 fissa "3 tentativi totali per
  evento", scegliendo la lettura del Canvas.
  Q4 non dichiarato e deciso: il §2 prescrive lo Strategy pattern
  configurabile; S01 e S05 lo applicano.
  Q5 non dichiarato: IN_CODA, CONSEGNATA e FALLITA usati come stati
  approvati in S01, S03 e S04, senza mapping.
  Q6 non dichiarato e deciso: S04 assegna ERROR al fallimento definitivo.

- Funzionalità con nominale e negativo coperti (ID F):
  LA2-F3 (S01 e S03 nominali, con S03 che copre il successo su canale
  alternativo e chiude la sequenza; S02 e S04 negativi) — con riserva:
  poggia su Q2 e Q3 decisi in silenzio.

- Funzionalità con copertura parziale (ID F e caso mancante):
  LA2-F1 — nominale presente (S01, cambio stato con destinatario da
  configurazione workflow), caso del destinatario non valido assente.
  LA2-F2 — nominale presente (S05, countdown sotto soglia innesca
  l'evento), caso fuori soglia assente.
  LA2-F4 — nominale presente (S04, stato FALLITA con log ERROR), ma
  mancano l'esclusione esplicita di SMS e il non blocco della pratica;
  la correlazione dell'anomalia è coperta indirettamente da S06.

- Casi mancanti dichiarati esplicitamente: nessuno.

- Omissioni non dichiarate:
  LA2-F5 assente per intero: nessuno scenario tocca rollback su
  fallimento DB o non duplicazione in caso di ripetizione. S01 crea il
  record NOTIFICA ma non ne verifica la consistenza con l'evento.
  Caso negativo di LA2-F1 (destinatario non valido).
  Caso negativo di LA2-F2 (fuori soglia).
  Esclusione SMS e non blocco della pratica, parte di LA2-F4.
  Dubbi Q1, Q2, Q3, Q4, Q5, Q6.

- Forma GIVEN/WHEN/THEN e fence:
  7 fence, 7 scenari, un fence per scenario.
  Difetto di forma: tutti e sette gli scenari usano "E" al posto di
  "AND" nei THEN.
  Struttura GIVEN/WHEN/THEN completa in tutti gli scenari.

- Note / punti non valutabili:
  Incoerenza aritmetica sul contatore, più marcata che in P05. S02
  stabilisce che il primo fallimento Email porta tentativo_n a 1; S04
  descrive due fallimenti (Email, poi Slack) e dichiara raggiunto il
  limite massimo con tentativo_n = 3. Il terzo tentativo non compare in
  alcuno scenario e la sequenza non torna con nessuna delle due letture
  di Q3. Non è una decisione del dubbio, è un conteggio errato.
  Errore lessicale nel THEN di S04: "stato FALLO definitivamente" invece
  di FALLITA, su un valore che la risposta stessa definisce altrove come
  identificatore di stato.
  S02 registra "un log WARNING con livello 'backoff in corso'": confonde
  il livello del log con il suo messaggio.
  S07 verifica l'isolamento del Logic Agent dai flussi UI, che il
  protocollo classifica esplicitamente come vincolo trasversale e non
  come funzionalità attesa. Non conta nella copertura delle cinque F;
  registrato qui perché occupa uno dei sette scenari.
  Limite di questa scheda: come per gli altri campioni LA2, le fonti non
  sono state consultate direttamente. Le righe not_assessable richiedono
  verifica sul testo.
  Scheda redatta con assistenza di un modello e revisionata dall'umano.

Affermazioni normative atomiche:

| ID | Citazione dalla risposta | Verdetto | Fonte e passaggio | Motivazione |
|---|---|---|---|---|
| K1 | §2: backoff di 15 minuti tra tentativi su canali diversi | conflicted | Canvas vs spec_notifications REGOLA-VAL-01, Q2 | parametro controverso imposto come regola. REGOLA-VAL-01 (righe 64-66) prescrive "3 reinvii automatici distanziati da un backoff esponenziale". Non è solo un valore diverso: è una strategia diversa. I campioni che impongono 15 minuti fissi non stanno scegliendo tra due numeri, stanno sostituendo il backoff esponenziale della fonte con uno fisso preso dal Canvas, senza dichiararlo. |
| K2 | §2: limite massimo di 3 tentativi totali per evento | conflicted | Canvas Approach vs fonte, Q3 | tre totali vs tre reinvii, deciso senza dichiarare. REGOLA-VAL-01 dice "3 reinvii automatici", il Canvas §5 (riga 59) dice "limite di tentativi (tentativo_n = 3)". La divergenza è ora documentata su entrambi i lati. |
| K3 | S04: log di livello ERROR per il fallimento definitivo | conflicted | Canvas vs OBS-04, Q6 | severità controversa imposta. OBS-04 (righe 100-111) riserva ERROR a "ciò che non doveva accadere" e classifica gli errori di dominio previsti come INFO o WARNING; lo scenario di spec_notifications §4 (righe 91-97) usa WARNING per il fallimento definitivo; il Canvas §5 (riga 60) ammette esso stesso "ERROR (o WARNING se previsto)". Un fallimento di consegna dopo retry previsti è un errore di dominio atteso: imporre ERROR senza dichiarare la divergenza resta un conflitto. |
| K4 | stati IN_CODA / CONSEGNATA / FALLITA della NOTIFICA | conflicted | Canvas vs fonte (PENDING/SENT/FAILED), Q5 | mapping non dichiarato |
| K5 | §2: routing tramite Strategy pattern configurabile, senza hard-coding | conflicted | Canvas §1 (riga 5), §3 (riga 18); REGOLA-NOTIF-02/03, Q4 | il Canvas §1 (riga 5) e §3 (riga 18) prescrivono routing configurabile via workflow con Strategy pattern, senza hard-coding. Lo Strategy pattern NON è quindi un'invenzione: è prescritto. Il conflitto Q4 resta però valido e va riformulato: la divergenza non è sull'uso dello Strategy, ma sul fatto che REGOLA-NOTIF-02 assegna Slack ai manager e REGOLA-NOTIF-03 assegna e-mail sincrona ai dipendenti, cioè un instradamento per ruolo e canale fissato dalla fonte, che convive male con un routing interamente configurabile. |
| K6 | S05: countdown temporale impostato su 1 giorno | unsupported | nessuna fonte, Q1 | valore numerico inventato |
| K7 | S06: correlationId in ogni riga di log e nel messaggio RabbitMQ | supported | protocollo: propagazione correlationId non aperta | prescritta dalle fonti |
| K8 | §2: log strutturati JSON con livelli INFO / WARNING / ERROR | supported | protocollo: formato strutturato non aperto | prescritto dalle fonti |
| K9 | S07: il Logic Agent non esprime logiche di presentazione o query SQL grezze | supported | Canvas §7 Safeguards (riga 77) | Canvas §7 Safeguards (riga 77), quasi alla lettera. |
| K10 | S06: correlationId generato dal middleware all'evento | supported | observability_standards §5 (righe 168-173) | il middleware genera il correlationId quando il chiamante non lo fornisce. |
| K11 | S02: log WARNING per il fallimento gestito in backoff | supported | Canvas §6 Norms (riga 70); OBS-04 | WARNING per fallimenti gestiti con backoff in corso, in applicazione di OBS-04 (anomalia gestita, degrado tollerato). |
| K12 | stack .NET 10 Worker Service, RabbitMQ, MassTransit, Quartz.NET | supported | Canvas §3 (riga 17), §6 Norms (riga 67), §4 Structure (righe 31-39) | Lo stack è tassativo e i nomi dei componenti compaiono nella struttura del Canvas. |

Rapporto supported / valutabili: 6 / 12. Unsupported: 1. Conflicted: 5.
Not assessable: 0, esclusi dal denominatore.

Rilievo sul protocollo, da riportare tale e quale: dodicesimo caso non
previsto dai criteri. S07 spende uno dei sette scenari su un vincolo che
il protocollo dichiara trasversale e non conteggiabile tra le cinque F.
Il criterio 3 chiede di mappare ogni scenario a un comportamento atteso,
ma non prevede come registrare uno scenario valido che non mappa su
nessuna funzionalità attesa: non è copertura, non è omissione, non è un
requisito senza supporto. Con un budget di scenari limitato, uno
scenario speso fuori perimetro ha però un costo sulla copertura. La
stessa questione vale per il vincolo PII in P07. Valutare prima di
aggregare, insieme agli undici rilievi già aperti.


---

## Campione P10

### Risposta integrale

# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Descrizione della Feature

La feature **LA2** implementa un sistema di notifica asincrono resiliente per il dominio delle pratiche (`RICHIESTA`). Il sistema gestisce due tipologie di trigger:
1.  **Dinamici:** Innescati da transizioni di stato della `RICHIESTA` (es. approvazione, rifiuto).
2.  **Statici:** Innescati da eventi temporali (es. scadenza imminente) monitorati tramite job periodici.

Il sistema utilizza un'architettura a *Logic Agent* basata su **.NET 10 Worker Service**, accodando gli eventi su **RabbitMQ** e consumandoli tramite **MassTransit**. La logica di routing dei destinatari (`DIPENDENTE`, `RESPONSABILE`) è gestita tramite uno *Strategy Pattern*. L'invio avviene attraverso adapter intercambiabili per i canali `EMAIL` e `SLACK`.

In caso di fallimento dell'invio su un canale, il sistema applica una strategia di backoff multi-canale: tenta l'altro canale disponibile dopo 15 minuti. La sequenza si interrompe definitivamente al raggiungimento del terzo tentativo (`tentativo_n = 3`) o se entrambi i canali falliscono. In tale caso, lo stato della notifica diventa `FALLITA` e viene generato un log strutturato di anomalia senza attivare fallback alternativi (es. SMS).

Tutti gli eventi sono tracciati con un `correlationId` end-to-end e i log seguono le norme di osservabilità `[REGOLA-OBS-02]`, `[REGOLA-OBS-03]`, `[REGOLA-OBS-04]`.

## 2. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica Email su trigger dinamico riuscito
  GIVEN una RICHIESTA in stato "Revisato" che attiva un trigger dinamico
  AND il sistema identifica come destinatario l'utente con ruolo "DIPENDENTE"
  WHEN il consumer MassTransit elabora l'evento e tenta l'invio via EmailChannelAdapter
  THEN lo stato della NOTIFICA viene aggiornato a "CONSEGNATA"
  AND il contatore tentativo_n rimane uguale a 1
  AND un log di livello INFO registra la consegna avvenuta
```

```gherkin
SCENARIO: S02 - Gestione fallimento Email e backoff verso Slack
  GIVEN una RICHIESTA che attiva un trigger dinamico per notifica al RESPONSABILE
  WHEN il sistema tenta l'invio via EmailChannelAdapter e riceve un errore di delivery
  AND il contatore tentativo_n è inferiore a 3
  THEN lo stato della NOTIFICA viene aggiornato a "IN_CODA" con tentativo_n incrementato a 2
  AND il sistema attende il periodo di backoff configurato (15 minuti)
  AND tenta successivamente l'invio via Slack tramite SlackChannelAdapter
```

```gherkin
SCENARIO: S03 - Fallimento definitivo e logging anomalia
  GIVEN una RICHIESTA che attiva un trigger statico per scadenza imminente
  WHEN il sistema tenta l'invio su Email (fallito) e successivamente su Slack (fallito)
  AND il contatore tentativo_n raggiunge il valore massimo di 3
  THEN lo stato della NOTIFICA viene aggiornato a "FALLITA"
  AND un log strutturato di livello ERROR registra l'anomalia con messaggio dettagliato
  AND nessun fallback alternativo (es. SMS) viene attivato
```

```gherkin
SCENARIO: S04 - Invio fallito su utente non valido nel sistema
  GIVEN una RICHIESTA che attiva un trigger dinamico
  WHEN il sistema tenta di inviare la notifica a un UTENTE che risulta inesistente nel database
  AND l'adapter EmailChannelAdapter rileva l'errore di entità mancante
  THEN lo stato della NOTIFICA viene aggiornato a "FALLITA" dopo i tentativi massimi
  AND il log registra l'anomalia indicando la causa del fallimento dell'entità target
```

## 3. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
|---|---|---|
| Gestione Trigger Statici (Job Quartz.NET) | Il job `StaticTriggerJob` scansiona le richieste in attesa di scadenze ogni X minuti, dove X è un valore fisso non specificato nel Canvas. | Qual è l'intervallo di scansione del job `StaticTriggerJob`? È necessario definire una soglia temporale (es. "ogni 5 minuti") per garantire la tempestività dell'innesco statico senza sovraccaricare il broker RabbitMQ? |
| Propagazione CorrelationId in RabbitMQ | Il campo `correlationId` viene generato all'ingresso del worker e propagato intatto su tutti i messaggi RabbitMQ e log, come richiesto da `[REGOLA-OBS-03]`. | È necessario specificare il formato esatto dell'ID (es. UUID v4) o è sufficiente che sia un stringa alfanumerica unica? Il Canvas non specifica il generatore, ma la norma impone la propagazione. |
| Logging Anomalia Definitiva | Al raggiungimento del limite tentativi, il log deve essere di livello `ERROR` secondo `[REGOLA-OBS-04]`. | La specifica richiede che il log contenga "dettagli dell'anomalia". È sufficiente includere solo l'ID della notifica e lo stato, o è necessario includere anche l'errore grezzo del provider (es. codice SMTP 550)? L'inclusione di stack trace potrebbe violare `[REGOLA-OBS-07]` se contiene PII? |
| Backoff Multi-Canale | Il sistema attende esattamente 15 minuti tra il fallimento del primo canale e il tentativo sul secondo, come specificato nel Canvas. | Se il primo canale (Email) fallisce al 2° tentativo (dopo 15 min), il backoff di 15 minuti si applica anche al tentativo successivo su Slack o solo al passaggio da Email a Slack? La specifica dice "tentare l'altro canale... dopo un periodo di backoff", ma non chiarisce se questo backoff è cumulativo per ogni fallimento o solo tra i due canali. |

### Valutazione umana di P10

- Stato: human_reviewed
- Ambiguità dichiarate correttamente (ID Q): 0 / 6.
  Quattro punti aperti presenti, nessuno corrispondente ai dubbi
  preregistrati.
  Q1 non dichiarato: il punto aperto sui Trigger Statici chiede
  l'intervallo di scansione del job, non il valore della soglia di
  countdown; la soglia non è mai discussa.
  Q2 non dichiarato e, peggio, dichiarato risolto: l'assunzione del
  punto aperto su Backoff Multi-Canale afferma che i 15 minuti sono
  "come specificato nel Canvas", presentando come fissato dalla fonte un
  parametro che il protocollo registra come divergente tra Canvas e
  REGOLA-VAL-01. La domanda che segue riguarda solo la cumulatività.
  Q3 non dichiarato e deciso: la §1 stabilisce che la sequenza si
  interrompe "al raggiungimento del terzo tentativo (tentativo_n = 3)".
  Q4 non dichiarato e deciso: la §1 prescrive lo Strategy Pattern per il
  routing; S01 e S02 assegnano i ruoli senza segnalare la divergenza con
  REGOLA-NOTIF-02/03.
  Q5 non dichiarato: CONSEGNATA, IN_CODA e FALLITA usati come stati
  approvati in tutti e quattro gli scenari, senza mapping.
  Q6 non dichiarato e dichiarato risolto: l'assunzione del punto aperto
  su Logging Anomalia Definitiva afferma che il log "deve essere di
  livello ERROR secondo [REGOLA-OBS-04]", mentre il protocollo registra
  che OBS-04 lega ERROR all'impatto e l'anomalia gestita a WARNING.
  La domanda riguarda solo il contenuto del log.

- Funzionalità con nominale e negativo coperti (ID F):
  LA2-F1 (S01 nominale, destinatario identificato e notifica consegnata;
  S04 negativo, utente inesistente) — vedi Note sul comportamento
  descritto in S04.
  LA2-F3 (S01 nominale, successo che chiude la sequenza; S02 negativo,
  fallimento Email con backoff verso Slack) — con riserva: poggia su Q2
  e Q3 decisi in silenzio.

- Funzionalità con copertura parziale (ID F e caso mancante):
  LA2-F2 — solo innesco: S03 usa un trigger statico come premessa di un
  fallimento di consegna, ma nessuno scenario verifica che la soglia
  raggiunta inneschi la notifica né il caso fuori soglia. Copertura
  incidentale, non intenzionale.
  LA2-F4 — nominale presente (S03, stato FALLITA, log ERROR, nessun
  fallback SMS), ma mancano la correlazione dell'anomalia e il non
  blocco della pratica.

- Casi mancanti dichiarati esplicitamente: nessuno.

- Omissioni non dichiarate:
  LA2-F5 assente per intero: nessuno scenario tocca persistenza con
  evento, rollback su fallimento DB o non duplicazione.
  Caso nominale di LA2-F2 (soglia raggiunta che innesca la notifica) e
  caso fuori soglia.
  Correlazione dell'anomalia e non blocco della pratica, parte di F4.
  Propagazione del correlationId: menzionata in §1 e in un punto aperto,
  mai verificata da uno scenario.
  Dubbi Q1, Q2, Q3, Q4, Q5, Q6.

- Forma GIVEN/WHEN/THEN e fence:
  4 fence, 4 scenari, un fence per scenario, keyword AND in maiuscolo
  inglese in tutti gli scenari. Nessuna congiunzione italiana: è l'unico
  campione LA2 senza questo difetto.
  S02, S03 e S04 hanno ordine GIVEN / WHEN / AND / THEN, con l'AND che
  aggiunge una condizione dentro il blocco WHEN. Forma ammessa.

- Note / punti non valutabili:
  Due dei quattro punti aperti contengono assunzioni che dichiarano
  risolti i dubbi Q2 e Q6 attribuendo alle fonti una prescrizione che,
  secondo il protocollo, le fonti non danno in modo univoco. È diverso
  dal decidere in silenzio: qui la decisione è attribuita alla fonte.
  Registrato nella tabella come conflitto, non come assunzione lecita.
  S04 descrive un comportamento internamente incoerente: l'utente
  risulta inesistente e l'adapter rileva l'errore di entità mancante, ma
  lo stato diventa FALLITA "dopo i tentativi massimi". Un destinatario
  inesistente non dovrebbe richiedere tre tentativi di consegna: il caso
  negativo atteso dal protocollo è che il destinatario non valido non
  riceva, non che si esauriscano i retry su un'entità mancante.
  Conteggiato come copertura del negativo di F1 nel merito, con riserva.
  Il quarto punto aperto solleva il rischio che uno stack trace nel log
  violi [REGOLA-OBS-07] contenendo PII: è l'unico campione che collega
  osservabilità e privacy, ma la norma citata non compare altrove nella
  risposta.
  Limite di questa scheda: come per gli altri campioni LA2, le fonti non
  sono state consultate direttamente. Le righe not_assessable richiedono
  verifica sul testo.
  Scheda redatta con assistenza di un modello e revisionata dall'umano.

Affermazioni normative atomiche:

| ID | Citazione dalla risposta | Verdetto | Fonte e passaggio | Motivazione |
|---|---|---|---|---|
| L1 | punto aperto: i 15 minuti sono "come specificato nel Canvas" | conflicted | Canvas vs spec_notifications REGOLA-VAL-01, Q2 | attribuisce alla fonte una prescrizione univoca che non c'è. REGOLA-VAL-01 (righe 64-66) prescrive "3 reinvii automatici distanziati da un backoff esponenziale". Non è solo un valore diverso: è una strategia diversa. I campioni che impongono 15 minuti fissi non stanno scegliendo tra due numeri, stanno sostituendo il backoff esponenziale della fonte con uno fisso preso dal Canvas, senza dichiararlo. |
| L2 | §1: la sequenza si interrompe al terzo tentativo (tentativo_n = 3) | conflicted | Canvas Approach vs fonte, Q3 | tre totali vs tre reinvii, deciso senza dichiarare. REGOLA-VAL-01 dice "3 reinvii automatici", il Canvas §5 (riga 59) dice "limite di tentativi (tentativo_n = 3)". La divergenza è ora documentata su entrambi i lati. |
| L3 | punto aperto: il log "deve essere di livello ERROR secondo [REGOLA-OBS-04]" | conflicted | Canvas vs OBS-04, Q6 | attribuisce a OBS-04 una severità che il protocollo registra come divergente. OBS-04 (righe 100-111) riserva ERROR a "ciò che non doveva accadere" e classifica gli errori di dominio previsti come INFO o WARNING; lo scenario di spec_notifications §4 (righe 91-97) usa WARNING per il fallimento definitivo; il Canvas §5 (riga 60) ammette esso stesso "ERROR (o WARNING se previsto)". Un fallimento di consegna dopo retry previsti è un errore di dominio atteso: imporre ERROR senza dichiarare la divergenza resta un conflitto. P10 attribuisce a OBS-04 la prescrizione di ERROR, mentre OBS-04 dice il contrario per gli errori previsti. L'assunzione è falsa, non solo non dichiarata. |
| L4 | stati CONSEGNATA / IN_CODA / FALLITA della NOTIFICA | conflicted | Canvas vs fonte (PENDING/SENT/FAILED), Q5 | mapping non dichiarato |
| L5 | §1: routing dei destinatari gestito tramite Strategy Pattern | conflicted | Canvas §1 (riga 5), §3 (riga 18); REGOLA-NOTIF-02/03, Q4 | il Canvas §1 (riga 5) e §3 (riga 18) prescrivono routing configurabile via workflow con Strategy pattern, senza hard-coding. Lo Strategy pattern NON è quindi un'invenzione: è prescritto. Il conflitto Q4 resta però valido e va riformulato: la divergenza non è sull'uso dello Strategy, ma sul fatto che REGOLA-NOTIF-02 assegna Slack ai manager e REGOLA-NOTIF-03 assegna e-mail sincrona ai dipendenti, cioè un instradamento per ruolo e canale fissato dalla fonte, che convive male con un routing interamente configurabile. |
| L6 | S03: nessun fallback alternativo (es. SMS) viene attivato | supported | protocollo: esclusione SMS non aperta | prescritto dalle fonti |
| L7 | §1: correlationId end-to-end su tutti gli eventi | supported | protocollo: propagazione correlationId non aperta | prescritta dalle fonti |
| L8 | S03: log strutturato di anomalia | supported | protocollo: formato strutturato non aperto | prescritto dalle fonti |
| L9 | S02: tentativo_n incrementato a 2 dopo il primo fallimento | conflicted | Q3 | coerente con "tre totali", incoerente con "tre reinvii", non dichiarato. REGOLA-VAL-01 dice "3 reinvii automatici", il Canvas §5 (riga 59) dice "limite di tentativi (tentativo_n = 3)". La divergenza è ora documentata su entrambi i lati. |
| L10 | S04: FALLITA dopo i tentativi massimi per utente inesistente | unsupported | nessuna fonte | il retry su entità mancante non è prescritto da alcuna fonte |
| L11 | punto aperto: possibile violazione di [REGOLA-OBS-07] per PII | supported | OBS-12 (righe 158-160); OBS-07 (righe 129-131) | La preoccupazione di P10 che una stack trace possa violare le norme PII è fondata: OBS-12 la prescrive esplicitamente. Nota che P10 cita OBS-07, mentre la norma sulle stack trace è OBS-12: riferimento impreciso, sostanza corretta. |
| L12 | stack .NET 10 Worker Service, RabbitMQ, MassTransit, adapter di canale | supported | Canvas §3 (riga 17), §6 Norms (riga 67), §4 Structure (righe 31-39) | Lo stack è tassativo e i nomi dei componenti compaiono nella struttura del Canvas. |

Rapporto supported / valutabili: 5 / 12. Unsupported: 1. Conflicted: 6.
Not assessable: 0, esclusi dal denominatore.

Rilievo sul protocollo, da riportare tale e quale: tredicesimo caso non
previsto dai criteri, ed è il più insidioso. Il criterio 1 stabilisce
che "un'assunzione esplicitamente da confermare non è un requisito
inventato". P10 rispetta la forma — assunzione dichiarata, domanda
aperta — ma l'assunzione stessa attribuisce alla fonte una prescrizione
che la fonte non dà, e la domanda che segue verte su un dettaglio
secondario. La struttura dei punti aperti diventa così un veicolo per
consolidare la decisione controversa invece di esporla: un revisore che
legga solo la colonna "Assunzione da Confermare" concluderebbe che i 15
minuti e il livello ERROR sono già fissati dalle fonti. Il criterio va
esteso a verificare la veridicità dell'assunzione, non solo la presenza
della domanda, altrimenti la forma corretta protegge il contenuto
sbagliato. Da comporre con i dodici rilievi già aperti prima di
aggregare.

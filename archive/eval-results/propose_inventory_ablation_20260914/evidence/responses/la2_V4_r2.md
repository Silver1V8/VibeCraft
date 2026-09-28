# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## Inventario delle funzionalità

| Funzionalità | Ancoraggio al Canvas o alla fonte | Casi previsti (nominale / negativo) | Riferimento agli scenari o al punto aperto |
|---|---|---|---|
| F1: Trigger Ibrido e Routing Dinamico | Sezione 1. Requirements (Trigger Ibrido, Configurazione Workflow Dinamica); Sezione 3. Approach (Pattern Strategy). | Nominale: Invio corretto a Dipendente/Responsabile su cambio stato.<br>Negativo: Destinatario non valido o richiesta annullata. | S01, S02 |
| F2: Gestione Backoff Multi-Canale e Timeout | Sezione 1. Requirements (Resilienza e Backoff Multi-Canale, Timeout di Consegna); Sezione 3. Approach (Retry Logic). | Nominale: Email fallisce, Slack riesce dopo 15 min.<br>Negativo: Entrambi i canali falliscono entro il timeout. | S03, S04 |
| F3: Logging Anomalie e Dead Letter Queue | Sezione 1. Requirements (Logging dell'Anomalia); Sezione 3. Approach (Dead Letter Queue). | Nominale: Log strutturato `FALLITA` generato.<br>Negativo: Messaggio spostato in DLQ senza blocco pratica. | S05, S06 |
| F4: Trigger Statico Countdown | Sezione 1. Requirements (Trigger Ibrido - countdown temporale); Sezione 3. Approach (StaticTriggerJob). | Nominale: Job Quartz.NET avvia evento scadenza imminente.<br>Negativo: Scadenza non raggiunta o richiesta già chiusa. | S07, S08 |
| F5: Correlazione e Osservabilità | Sezione 6. Norms (Correlazione End-to-End); Sezione 2. Normative (Audit Log). | Nominale: Propagazione `correlationId` su RabbitMQ e log.<br>Negativo: Mancanza di ID o perdita di contesto nel tracing. | S09, S10 |

---

## Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica su cambio stato a dipendente
  GIVEN una RICHIESTA in stato "Bozza" con countdown attivo
  AND un utente UTENTE designato come "DIPENDENTE" nella configurazione workflow
  WHEN lo stato della RICHIESTA cambia da "Bozza" a "Revisato"
  THEN il sistema pubblica un evento su RabbitMQ contenente l'ID della richiesta
  AND istanzia la strategia di routing per selezionare il dipendente
  E invia la notifica via Email con successo
  E aggiorna lo stato della NOTIFICA a "CONSEGNATA"
```

```gherkin
SCENARIO: S02 - Invio negato su destinatario non valido
  GIVEN una RICHIESTA in stato "Bozza"
  AND un utente UTENTE designato come "DIPENDENTE" risulta inesistente nel database
  WHEN lo stato della RICHIESTA cambia da "Bozza" a "Revisato"
  THEN il sistema pubblica l'evento su RabbitMQ ignorando il destinatario non valido
  E registra un log di livello INFO indicando la mancata associazione dell'utente
  E non crea alcun record NOTIFICA per quell'evento specifico
```

```gherkin
SCENARIO: S03 - Backoff multi-canale con successo Slack
  GIVEN una RICHIESTA che innesca una notifica "SCADENZA_IMMINENTE"
  AND il canale EMAIL fallisce al primo tentativo (SMTP timeout)
  WHEN il sistema applica il backoff di 15 minuti e tenta l'invio su SLACK
  THEN il canale SLACK invia il messaggio con successo
  E aggiorna lo stato della NOTIFICA a "CONSEGNATA"
  E registra un log di livello WARNING per il fallimento iniziale del canale EMAIL
```

```gherkin
SCENARIO: S04 - Fallimento definitivo e chiusura sequenza
  GIVEN una RICHIESTA che innesca una notifica critica
  AND il canale EMAIL fallisce al primo tentativo
  AND il canale SLACK fallisce al secondo tentativo dopo il backoff
  WHEN il sistema raggiunge il limite massimo di tentativi (3) o esaurisce i canali
  THEN aggiorna lo stato della NOTIFICA a "FALLITA"
  E sposta il messaggio nella Dead Letter Queue (DLQ)
  E genera un log strutturato con livello ERROR e stato FALLITA
```

```gherkin
SCENARIO: S05 - Logging anomalia senza attivazione fallback alternativi
  GIVEN una RICHIESTA con entrambi i canali EMAIL e SLACK falliti definitivamente
  AND il sistema ha raggiunto il limite di tentativi configurato
  WHEN la sequenza di invio si conclude
  THEN il sistema registra l'anomalia come "invio mancato" nel log strutturato
  E non attiva notifiche alternative (es. SMS) né blocca la pratica
```

```gherkin
SCENARIO: S06 - Propagazione correlationId su RabbitMQ e Log
  GIVEN una RICHIESTA con un correlationId generato al momento dell'innesco
  WHEN il consumer NotificationConsumer elabora l'evento di notifica
  THEN il messaggio inviato a RabbitMQ include il campo correlationId originale
  E ogni log generato (Serilog) contiene lo stesso correlationId
```

```gherkin
SCENARIO: S07 - Trigger statico scadenza imminente
  GIVEN un job Quartz.NET StaticTriggerJob in esecuzione periodica
  AND una RICHIESTA con countdown <= X giorni e stato attivo
  WHEN il job rileva la soglia di scadenza imminente
  THEN pubblica un evento asincrono su RabbitMQ per "SCADENZA_IMMINENTE"
  E istanzia la strategia di routing per i destinatari configurati
```

```gherkin
SCENARIO: S08 - Trigger statico su richiesta già chiusa
  GIVEN un job Quartz.NET StaticTriggerJob in esecuzione periodica
  AND una RICHIESTA con countdown <= X giorni ma stato "ANNULLATA"
  WHEN il job rileva la soglia di scadenza imminente
  THEN ignora l'evento poiché la richiesta non è più attiva
  E non pubblica alcun messaggio su RabbitMQ
```

```gherkin
SCENARIO: S09 - Sanitizer PII nei log di fallimento
  GIVEN un tentativo di invio che genera un errore con dettagli tecnici
  AND il payload dell'errore contiene potenziali dati sensibili (es. indirizzi email completi)
  WHEN il sistema scrive il log strutturato nel file o nel collector
  THEN il sanitizer applica la redazione ai campi PII prima della scrittura
  E il log risultante rispetta [REGOLA-OBS-06] senza esporre dati personali
```

```gherkin
SCENARIO: S10 - Gestione integrità dati in transazione fallita
  GIVEN una RICHIESTA che innesca la creazione di un record NOTIFICA
  AND il database subisce un errore durante l'insert della transazione Outbox
  WHEN il sistema rileva il fallimento della scrittura nel DB
  THEN rollback immediato della transazione avviene senza persistenza parziale
  E lo stato della NOTIFICA non viene aggiornato a "IN_CODA" o "FALLITA"
```

## Punti aperti

| Funzionalità coinvolta | Assunzione proposta DA CONFERMARE | Domanda aperta |
|---|---|---|
| F1: Trigger Ibrido e Routing Dinamico | Se un utente è sia DIPENDENTE che RESPONSABILE per la stessa richiesta, il sistema invia due notifiche distinte o ne aggrega una. | Come gestire la sovrapposizione di ruoli (Dipendente/Responsabile) sullo stesso UTENTE? |
| F2: Gestione Backoff Multi-Canale e Timeout | Il limite massimo di tentativi è sempre 3, indipendentemente dal numero di canali disponibili (es. se ne fossero configurati 4). | Il vincolo "limite massimo dei tentativi o esaurimento delle opzioni" implica un conteggio assoluto (3) o per canale? |
| F5: Correlazione e Osservabilità | Il campo `correlationId` è generato dal middleware di ingresso del sistema principale e non dal Logic Agent stesso. | Chi genera il `correlationId` iniziale se la feature LA2 viene invocata da un processo esterno che non lo fornisce? |
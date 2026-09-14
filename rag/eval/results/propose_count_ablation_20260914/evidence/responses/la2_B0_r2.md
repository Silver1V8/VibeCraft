# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Descrizione della Feature

La feature **LA2** implementa un sistema di notifica asincrono resiliente per il dominio delle pratiche (`RICHIESTA`). Il sistema gestisce due tipologie di trigger:
1.  **Dinamici:** Innescati da transizioni di stato della `RICHIESTA` (es. approvazione, rifiuto).
2.  **Statici:** Innescati da eventi temporali definiti da un countdown (es. scadenza imminente).

Il sistema utilizza un'architettura basata su agenti logici (`Logic Agent`) che pubblicano eventi su una coda `RabbitMQ`. Un consumer elabora gli eventi, determinando i destinatari tramite uno `Strategy Pattern` e inviando le notifiche tramite canali adattabili (Email, Slack). La feature garantisce la consegna attraverso un meccanismo di retry multi-canale con backoff configurato a 15 minuti, limitando il numero totale di tentativi a 3. In caso di fallimento definitivo su tutti i canali, l'operazione viene registrata come `FALLITA` senza attivare fallback alternativi non concordati (es. SMS).

## 2. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica Email riuscito per cambio stato dinamico
  GIVEN una RICHIESTA in stato "Bozza" che viene aggiornata a "Revisato"
  AND il workflow di routing è configurato per notificare il RESPONSABILE via EMAIL
  WHEN il sistema rileva la transizione di stato e pubblica l'evento su RabbitMQ
  THEN crea un record NOTIFICA con stato IN_CODA
  E invia il messaggio tramite EmailChannelAdapter
  E aggiorna lo stato della NOTIFICA a CONSEGNATA
```

```gherkin
SCENARIO: S02 - Gestione fallimento Email e retry Slack per scadenza imminente
  GIVEN una RICHIESTA prossima alla scadenza con countdown <= X giorni
  AND il sistema innesca il trigger statico SCADENZA_IMMINENTE per il RESPONSABILE via EMAIL
  WHEN l'invio tramite EmailChannelAdapter fallisce (es. timeout SMTP)
  THEN incrementa il contatore tentativo_n a 1
  E registra lo stato della NOTIFICA come IN_CODA con livello log WARNING
  E attende il periodo di backoff configurato a 15 minuti
  E tenta l'invio tramite SlackChannelAdapter
```

```gherkin
SCENARIO: S03 - Fallimento definitivo e chiusura sequenza senza fallback SMS
  GIVEN una RICHIESTA per cui sia Email che Slack falliscono nei rispettivi tentativi
  AND il contatore tentativo_n raggiunge il limite massimo di 3
  WHEN entrambi i canali (Email e Slack) restituiscono errori definitivi
  THEN aggiorna lo stato della NOTIFICA a FALLITA
  E genera un log strutturato con livello ERROR contenente i dettagli dell'anomalia
  E non attiva alcuna notifica alternativa come SMS
```

```gherkin
SCENARIO: S04 - Invio notifica Slack riuscito dopo fallimento Email iniziale
  GIVEN una RICHIESTA in stato "Annullata" che richiede notifica al DIPENDENTE via EMAIL
  WHEN l'invio tramite EmailChannelAdapter fallisce per errore di rete
  THEN incrementa il contatore tentativo_n a 1
  E tenta l'invio tramite SlackChannelAdapter dopo il backoff
  E aggiorna lo stato della NOTIFICA a CONSEGNATA solo dopo successo su Slack
```

## 3. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
|---|---|---|
| Gestione Trigger Statici (Countdown) | Il job `StaticTriggerJob` scansiona le richieste ogni X minuti per calcolare il countdown residuo. | Qual è l'intervallo di scansione esposto dal job Quartz.NET? È fisso o dinamico in base al carico? |
| Validazione Utente Destinatario | La verifica dell'esistenza dell'UTENTE avviene prima della creazione del record NOTIFICA, ma non si applica la validazione del dominio email (poiché i dati sono @progettopa.it). | Se un utente viene disabilitato nel sistema tra il momento in cui viene creato il record NOTIFICA e l'invio effettivo, come gestisce il consumer? Il fallimento è considerato "fallimento canale" o "errore di business"? |
| Propagazione CorrelationId | Il campo `correlationId` viene generato al momento della ricezione dell'evento RabbitMQ dal consumer. | Se l'evento arriva da un trigger statico (Job) che non ha un ID di richiesta correlato esplicitamente, come viene generato il `correlationId` iniziale? |
| Logging Anomalia Definitiva | Il log finale per stato FALLITA deve essere di livello ERROR. | Il log deve includere anche lo stack trace dell'ultimo errore o solo il messaggio sintetico definito dal business logic? |
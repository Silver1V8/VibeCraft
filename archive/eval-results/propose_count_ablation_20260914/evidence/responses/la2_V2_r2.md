# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Descrizione della Feature

La feature **LA2** implementa un'architettura asincrona per la gestione dinamica delle notifiche all'interno del modulo `logic-agent`. Il sistema monitora lo stato delle entità `RICHIESTA` e genera eventi di notifica sia su transizioni di stato dinamiche (es. approvazione) sia su scadenze temporali statiche (countdown).

Il flusso di elaborazione utilizza il pattern **Transactional Outbox** per garantire la persistenza dell'evento prima della pubblicazione su RabbitMQ. Un worker consumer gestisce l'invio tramite adapter intercambiabili (`EmailChannelAdapter`, `SlackChannelAdapter`) seguendo una strategia di routing configurabile (Dipendente vs Responsabile).

In caso di fallimento, il sistema applica una logica di retry esplicito con backoff di 15 minuti tra i tentativi su canali diversi. Il limite massimo dei tentativi è fissato a 3. Se tutti i canali falliscono definitivamente, lo stato della notifica viene impostato a `FALLITA` e viene generato un log strutturato di livello `ERROR`. Non vengono attivati fallback alternativi (es. SMS).

Il sistema rispetta rigorosamente le norme di osservabilità: ogni evento è correlato tramite un `correlationId`, i log sono strutturati (JSON) e il sanitizer PII redige automaticamente i dati sensibili prima dell'uscita.

## 2. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica su transizione di stato dinamica
  GIVEN una RICHIESTA in stato "Bozza" con countdown scaduto
  AND un utente UTENTE assegnato come RESPONSABILE nella configurazione workflow
  WHEN lo stato della RICHIESTA cambia a "Revisato"
  THEN il sistema pubblica un evento RabbitMQ per notifica "STATO_CAMBIATO"
  E istanzia la strategia di routing che seleziona l'UTENTE responsabile
  E invia il messaggio via EmailChannelAdapter con successo
  E aggiorna lo stato della NOTIFICA a CONSEGNATA
```

```gherkin
SCENARIO: S02 - Invio notifica su scadenza imminente (Trigger Statico)
  GIVEN una RICHIESTA in stato "In Attesa" con countdown residuo <= 1 giorno
  AND il job Quartz.NET StaticTriggerJob esegue la scansione periodica
  WHEN il countdown scade e il sistema rileva l'evento di scadenza
  THEN il sistema pubblica un evento RabbitMQ per notifica "SCADENZA_IMMINENTE"
  E istanzia la strategia di routing che seleziona i destinatari configurati
  E tenta l'invio via EmailChannelAdapter
```

```gherkin
SCENARIO: S03 - Gestione fallimento primo tentativo e backoff multi-canale
  GIVEN una RICHIESTA con evento trigger generato
  AND il sistema tenta l'invio su EmailChannelAdapter che fallisce (errore rete)
  WHEN il sistema incrementa il contatore di tentativi a 1
  THEN il sistema attende il periodo di backoff configurato (15 minuti)
  E tenta l'invio dello stesso evento su SlackChannelAdapter
```

```gherkin
SCENARIO: S04 - Gestione fallimento definitivo e logging anomalia
  GIVEN una RICHIESTA con evento trigger generato
  AND il primo tentativo via EmailChannelAdapter fallisce
  AND il secondo tentativo via SlackChannelAdapter (dopo backoff) fallisce
  WHEN il sistema raggiunge il limite massimo dei tentativi (tentativo_n = 3)
  THEN il sistema aggiorna lo stato della NOTIFICA a FALLITA
  E registra un log strutturato con livello ERROR e messaggio "invio mancato"
  E non attiva alcun fallback alternativo come SMS
```

## 3. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
|---|---|---|
| Gestione Trigger Statico (S02) | Il job Quartz.NET scansiona *tutte* le richieste o solo quelle in stato specifico? | Come viene filtrato l'insieme delle `RICHIESTA` da monitorare per evitare sovraccarico del worker durante la scansione periodica? |
| Backoff Multi-Canale (S03) | Il backoff di 15 minuti è applicato *solo* tra Email e Slack, o anche se lo stesso canale fallisce due volte? | Se Email fallisce al tentativo 1, si aspetta 15 min per provare Slack. Se Slack fallisce, si aspetta altri 15 min per riprovare Email (tentativo 3)? O il ciclo è lineare (Email -> Slack -> Fine)? |
| Logging Fallimento (S04) | Il log di livello ERROR include i dettagli dell'errore specifico del provider esterno o solo lo stato generico? | Qual è la struttura esatta del payload JSON del log per garantire che contenga `correlationId`, `timestamp` e il motivo del fallimento senza violare le regole PII? |
| Correlazione End-to-End | Il `correlationId` viene generato al momento della creazione dell'evento RabbitMQ o ereditato dalla transazione di business originale? | Come si garantisce che il `correlationId` sia presente anche se la transazione di business originale non ha generato un ID (es. evento interno)? |
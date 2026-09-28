# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Descrizione della Feature

La feature **LA2** implementa un'architettura asincrona per la gestione dinamica delle notifiche all'interno del modulo `logic-agent`. Il sistema monitora lo stato delle entità `RICHIESTA` e genera eventi di notifica sia su variazioni di stato dinamiche (trigger dinamico) che su scadenze temporali predefinite (trigger statico).

Il flusso di elaborazione utilizza un pattern **Strategy** per determinare il destinatario (`DIPENDENTE` o `RESPONSABILE`) e un pattern **Adapter** per l'invio tramite canali `EMAIL` e `SLACK`. La persistenza avviene tramite il pattern **Transactional Outbox**, mentre la gestione dei fallimenti segue una logica di retry con backoff esponenziale (15 minuti) fino a un massimo di 3 tentativi. In caso di fallimento definitivo, lo stato viene impostato su `FALLITA` e l'anomalia viene registrata senza attivare fallback alternativi non autorizzati.

## 2. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica su variazione di stato dinamico
  GIVEN una RICHIESTA in stato "Bozza" associata a un UTENTE dipendente
  AND il sistema rileva la transizione dello stato della RICHIESTA verso "Revisato"
  WHEN il consumer NotificationConsumer elabora l'evento trigger dinamico
  THEN crea un record NOTIFICA con stato IN_CODA e tentativo_n impostato a 1
  E invia il messaggio tramite EmailChannelAdapter
  E aggiorna lo stato della NOTIFICA a CONSEGNATA
```

```gherkin
SCENARIO: S02 - Invio notifica su scadenza imminente (Trigger Statico)
  GIVEN una RICHIESTA con countdown temporale impostato a 1 giorno
  AND il job StaticTriggerJob esegue la scansione periodica delle scadenze
  WHEN il countdown scende sotto la soglia di attivazione definita dal workflow
  THEN il sistema pubblica un evento trigger per "SCADENZA_IMMINENTE"
  E istanzia lo Strategy appropriato per identificare il RESPONSABILE
  E avvia la sequenza di invio del canale EMAIL
```

```gherkin
SCENARIO: S03 - Gestione fallimento primo tentativo e backoff multi-canale
  GIVEN una RICHIESTA che innesca un evento di notifica
  WHEN l'invio tramite EmailChannelAdapter fallisce per errore di rete o timeout
  THEN il sistema incrementa lo stato della NOTIFICA a IN_CODA con tentativo_n = 2
  E registra un log WARNING indicando il backoff di 15 minuti
  E dopo il periodo di attesa tenta l'invio tramite SlackChannelAdapter
```

```gherkin
SCENARIO: S04 - Gestione fallimento definitivo e logging anomalia
  GIVEN una RICHIESTA per cui sia Email che Slack hanno fallito nei rispettivi tentativi
  AND il contatore tentativo_n raggiunge il limite massimo di 3
  WHEN la sequenza di invio si conclude senza successo su alcun canale
  THEN il sistema aggiorna lo stato della NOTIFICA a FALLITA
  E registra un log strutturato con livello ERROR e messaggio "invio mancato"
  E non attiva alcuna notifica alternativa (es. SMS) né blocca la pratica
```

## 3. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
|---|---|---|
| Trigger Statico (S02) | Il job `StaticTriggerJob` scansiona tutte le richieste o solo quelle in uno stato specifico di attesa? | Qual è esattamente lo stato della `RICHIESTA` che deve essere monitorato per il countdown? |
| Routing Strategy (S01, S02) | Lo Strategy pattern seleziona un singolo destinatario o può selezionare più utenti contemporaneamente? | Se entrambi i ruoli (Dipendente e Responsabile) sono validi per uno stesso stato, come viene gestito l'invio parallelo? |
| Logging Anomalia (S04) | Il log strutturato include il payload dell'errore specifico del provider esterno o solo il codice generico? | Qual è la struttura esatta dei campi aggiuntivi nel log oltre a `timestamp`, `level`, `message`, `correlationId`? |
| Backoff Multi-Canale (S03) | Il backoff di 15 minuti si applica tra Email e Slack o solo in caso di fallimento ripetuto dello stesso canale? | Se Email fallisce, il sistema attende 15 minuti per provare Slack, oppure prova Slack immediatamente se disponibile? |
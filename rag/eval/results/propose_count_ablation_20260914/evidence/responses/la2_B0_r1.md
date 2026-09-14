# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Contesto e Scopo

La presente specifica definisce il comportamento osservabile della feature **LA2**, implementata all'interno del progetto `logic-agent`. L'obiettivo è garantire la consegna affidabile di notifiche relative a eventi dinamici o statici (scadenze) associati a una `RICHIESTA`, utilizzando un'architettura asincrona basata su RabbitMQ e MassTransit. Il sistema deve gestire il routing dei destinatari (`DIPENDENTE`/`RESPONSABILE`) tramite strategia, tentare la consegna su canali multipli (Email, Slack) con backoff configurato, e registrare gli stati di consegna in modo idempotente e strutturato.

## 2. Regole Operative e Vincoli

- **Entità:** Tutte le operazioni coinvolgono esclusivamente le entità `RICHIESTA`, `NOTIFICA` e `UTENTE`.
- **Stack Tecnologico:** L'implementazione deve utilizzare `.NET 10 Worker Service`, `RabbitMQ`, `MassTransit` per il messaging, `Quartz.NET` per i job periodici e `Serilog`/`OpenTelemetry` per l'osservabilità.
- **Log Strutturati:** I log devono seguire `[REGOLA-OBS-02]`: oggetti JSON con campi obbligatori `timestamp`, `level`, `message`, `correlationId`. Il livello deve rispettare `[REGOLA-OBS-04]` (`INFO` per successo, `WARNING` per backoff attivo, `ERROR` per fallimento definitivo).
- **Correlazione:** Il campo `correlationId` deve essere propagato in ogni messaggio RabbitMQ e log generato dalla feature LA2.
- **Limiti Tentativi:** Il sistema tenta la consegna fino a un massimo di 3 tentativi totali (`tentativo_n <= 3`). Se tutti falliscono, lo stato diventa `FALLITA`.
- **Backoff Multi-Canale:** In caso di fallimento del primo canale (es. Email), il sistema attende 15 minuti e tenta il secondo canale (es. Slack).
- **Fallback Silenzioso:** Non sono previsti fallback alternativi (es. SMS) se entrambi i canali principali falliscono definitivamente.

## 3. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica Email riuscito per trigger dinamico
  GIVEN una RICHIESTA in stato "Revisato" che attiva un trigger dinamico
  AND il sistema identifica come destinatario valido un UTENTE di tipo "DIPENDENTE"
  WHEN il consumer NotificationConsumer elabora l'evento e tenta l'invio via EmailChannelAdapter
  THEN il record NOTIFICA viene creato con stato "CONSEGNATA" e tentativo_n = 1
  AND lo stato della RICHIESTA rimane invariato
```

```gherkin
SCENARIO: S02 - Gestione fallimento Email e backoff verso Slack
  GIVEN una RICHIESTA che attiva un trigger dinamico per notifica a "RESPONSABILE"
  WHEN il tentativo di invio via EmailChannelAdapter fallisce (es. timeout SMTP)
  AND il sistema incrementa tentativo_n a 1 e applica il backoff di 15 minuti
  THEN dopo il backoff, il sistema tenta l'invio via Slack tramite SlackChannelAdapter
  AND se anche Slack fallisce definitivamente al terzo tentativo, lo stato NOTIFICA diventa "FALLITA"
```

```gherkin
SCENARIO: S03 - Innesco notifica statica per scadenza imminente
  GIVEN una RICHIESTA con countdown temporale che scade entro la soglia configurata
  AND il job StaticTriggerJob (Quartz.NET) rileva lo stato "SCADENZA_IMMINENTE"
  WHEN il job pubblica l'evento trigger su RabbitMQ
  THEN il consumer elabora l'evento creando un record NOTIFICA con messaggio relativo alla scadenza
  AND se la consegna è riuscita, lo stato diventa "CONSEGNATA" e viene generato log INFO
```

```gherkin
SCENARIO: S04 - Logging anomalia fallimento definitivo senza fallback alternativi
  GIVEN una RICHIESTA associata a un evento trigger che ha esaurito tutti i canali (Email e Slack)
  AND il contatore tentativo_n ha raggiunto il limite massimo di 3
  WHEN il sistema determina che la sequenza di consegna è conclusa con errore
  THEN lo stato della NOTIFICA viene impostato su "FALLITA"
  AND viene generato un log strutturato con livello ERROR contenente i dettagli dell'anomalia
  AND non vengono attivati tentativi di invio su canali alternativi non configurati (es. SMS)
```

## 4. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
|---|---|---|
| Gestione Trigger Statico (S03) | Il job `StaticTriggerJob` scansiona *tutte* le richieste in attesa o solo quelle con stato specifico? | È necessario definire una lista di stati della `RICHIESTA` che abilitano il trigger statico, oppure si applica a qualsiasi richiesta con countdown attivo? |
| Backoff Multi-Canale (S02) | Il backoff di 15 minuti è fisso o esponenziale tra tentativi su *diversi* canali? | La specifica indica "backoff configurato a 15 minuti" per il passaggio canale->canale. È corretto interpretare questo come un tempo fisso tra Email e Slack, oppure c'è una logica di backoff esponenziale anche all'interno dello stesso canale prima di passare al successivo? |
| Logging Fallimento (S04) | Il log strutturato include l'intero payload dell'errore o solo il codice? | Per `[REGOLA-OBS-07]` non devono essere inclusi payload completi. È sufficiente registrare il codice errore e il messaggio generico, oppure è necessario includere stack trace anonimizzati? |
| Correlazione ID (Vincolo Normativo) | Il `correlationId` viene generato dal middleware o dall'evento di business? | La specifica richiede la propagazione del `correlationId`. Chi è responsabile della sua generazione iniziale se non proviene da un HTTP request esterno (es. evento interno)? |
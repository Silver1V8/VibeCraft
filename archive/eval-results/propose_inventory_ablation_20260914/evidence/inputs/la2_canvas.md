# REASONS Canvas: Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Requirements
- **Trigger Ibrido:** Il sistema deve generare una notifica non solo su cambi di stato dinamici della `RICHIESTA`, ma anche su eventi statici definiti da un countdown temporale (es. scadenza imminente).
- **Configurazione Workflow Dinamica:** Le regole di routing devono essere configurabili per determinare a chi inviare la notifica (`DIPENDENTE` o `RESPONSABILE`) in base allo stato specifico raggiunto dalla pratica, senza hard-coding dei ruoli nel codice.
- **Resilienza e Backoff Multi-Canale:** In caso di fallimento dell'invio su un canale (es. Email), il sistema deve tentare l'altro canale disponibile (Slack) dopo un periodo di backoff configurato a 15 minuti, continuando fino al raggiungimento del limite massimo dei tentativi o esaurimento delle opzioni.
- **Fallback Silenzioso:** Se entrambi i canali (`EMAIL`, `SLACK`) falliscono definitivamente per lo stesso evento trigger, il sistema deve registrare l'anomalia come "invio mancato" e non attivare notifiche alternative (es. SMS) né bloccare la pratica.
- **Timeout di Consegna:** La finestra temporale massima entro cui tentare le consegne prima di considerare conclusa la sequenza per un evento specifico è di 15 minuti tra i tentativi su canali diversi, con una strategia che prova tutti i canali possibili prima di dare per chiusa l'operazione.
- **Logging dell'Anomalia:** Al raggiungimento del fallimento definitivo (tutti i canali esauriti), il sistema deve generare un log strutturato indicando lo stato `FALLITA` e incrementando il contatore dei tentativi fino al limite massimo (`3`).

## 2. Entities
- **NOTIFICA**: Entità derivata che rappresenta l'artefatto di comunicazione uscente. Include attributi per identificare la richiesta sorgente, il destinatario specifico (tramite FK `UTENTE.id`), il canale utilizzato (`EMAIL`, `SLACK`), lo stato della consegna (`IN_CODA`, `CONSEGNATA`, `FALLITA`) e il numero del tentativo corrente (`tentativo_n`).
- **RICHIESTA**: Entità sorgente che innesca la notifica. Il suo ID è riferito nella colonna `richiesta_id`. Lo stato di questa entità determina se attivare un trigger dinamico o statico (tramite calcolo countdown).
- **UTENTE**: Entità target del messaggio. La relazione molti-a-molti tra `RICHIESTA` e `NOTIFICA` passa attraverso il riferimento a questo utente, permettendo la distinzione tra destinatario dipendente e responsabile in base alla configurazione workflow.

## 3. Approach
La feature si basa su un'architettura **Logic Agent** asincrona che utilizza lo stack **.NET 10 Worker Service + RabbitMQ + MassTransit**.
- **Pattern Strategy:** Viene implementato uno `Strategy pattern` per la selezione dinamica del destinatario e del template in base allo stato della richiesta. Questo permette di configurare via workflow chi ricevere le notifiche senza modificare il codice sorgente.
- **Adapter Pattern:** Il layer di invio utilizza un approccio basato su adapter intercambiabili per gestire i protocolli SMTP (Email) e Slack Web API, garantendo che la logica core rimanga indipendente dai provider specifici.
- **Transactional Outbox & Inbox Pattern:** La creazione del record `NOTIFICA` avviene in transazione con l'evento di business sulla richiesta (`Transactional Outbox`). Il worker consuma messaggi da RabbitMQ per elaborare le notifiche, memorizzando gli ID elaborati nell'**Inbox** per garantire la idempotenza e prevenire duplicazioni.
- **Retry Logic:** Viene implementata una logica di retry esplicito gestita dal consumer MassTransit o tramite un job Quartz.NET personalizzato che applica il backoff di 15 minuti tra tentativi su canali diversi, rispettando il limite massimo di 3 tentativi totali per evento.
- **Dead Letter Queue (DLQ):** I messaggi falliti definitivamente vengono spostati in una DLQ per monitoraggio senza bloccare il flusso principale delle altre notifiche.

## 4. Structure
Il codice risiede nel progetto `logic-agent` con la seguente struttura:
```text
logic-agent/
  src/
    Portal.LogicAgent.Worker/
      Consumers/
        NotificationConsumer.cs          // Consuma messaggi da RabbitMQ per l'invio notifiche LA2
      Jobs/
        StaticTriggerJob.cs              // Job Quartz.NET che monitora countdown e innesca trigger statici
      Notifications/
        Channels/
          EmailChannelAdapter.cs         // Adapter SMTP
          SlackChannelAdapter.cs         // Adapter Webhook/API
        Strategies/
          RoutingStrategy.cs             // Logica Strategy per determinare Destinatario (Dipendente vs Resp.)
        Templates/
          TemplateEngine.cs              // Rendering messaggi dinamici
      Persistence/
        Repositories/                    // Repository per accesso a NOTIFICA, RICHIESTA, UTENTE
      Monitoring/
        MetricsNotifier.cs               // Logging strutturato con Serilog + OpenTelemetry
  tests/
    Portal.LogicAgent.Tests/             // Unit test per strategie e adapter
```

## 5. Operations
1. **Innesco Trigger Dinamico:** Quando lo stato di una `RICHIESTA` cambia (es. da "Bozza" a "Revisato"), il sistema pubblica un evento asincrono su RabbitMQ contenente l'ID della richiesta e i nuovi metadati. Il consumer legge la configurazione workflow per determinare se inviare al dipendente, responsabile o entrambi.
2. **Innesco Trigger Statico:** Il job `StaticTriggerJob` (Quartz.NET) esegue periodicamente una scansione delle richieste in attesa di scadenze imminenti (`countdown <= X giorni`). Se il valore soglia è raggiunto, pubblica un evento trigger per la notifica "SCADENZA_IMMINENTE".
3. **Elaborazione e Routing:** Il consumer riceve l'evento e istanzia lo `Strategy` appropriato. Calcola i destinatari validi (escluso se annullata) e prepara gli oggetti payload per Email e Slack.
4. **Invio Tentativo 1 (Email):** Il sistema tenta l'invio via SMTP tramite `EmailChannelAdapter`. Se riuscito, aggiorna lo stato a `CONSEGNATA` nel record `NOTIFICA`, ferma i retry e chiude la sequenza.
5. **Backoff Multi-Canale:** Se Email fallisce:
   - Incrementa il contatore di tentativi (`tentativo_n`).
   - Attende 15 minuti (backoff configurato).
   - Tenta l'invio via Slack tramite `SlackChannelAdapter`.
6. **Gestione Fallimento Definitivo:** Se anche Slack fallisce o se si raggiunge il limite di tentativi (`tentativo_n = 3`):
   - Aggiorna lo stato a `FALLITA`.
   - Registra un log strutturato con livello `ERROR` (o `WARNING` se previsto dal business logic specifico per "solo logging") contenente i dettagli dell'anomalia.
   - Non attiva fallback alternativi (es. SMS).
7. **Logging e Monitoraggio:** Ogni step genera log strutturati (`Serilog`) con campi obbligatori: `timestamp`, `level`, `message`, `correlationId`. Il tracing OpenTelemetry accompagna il messaggio attraverso le code RabbitMQ per tracciare l'intero percorso di consegna o fallimento.

## 6. Norms
- **Nomenclatura Entità:** Uso esclusivo dei nomi definiti nel glossario: `NOTIFICA`, `RICHIESTA`, `UTENTE`. Attributi come `stato_consegna` e `tentativo_n` devono essere usati senza variazioni (es. vietare `deliveryStatus`).
- **Stack Tecnologico:** Utilizzo tassativo di **.NET 10 Worker Service**, **RabbitMQ** per il messaging, **MassTransit** per la gestione dei consumer/retry/DLQ e **Quartz.NET** per i job periodici. Non usare librerie alternative o generiche (es. "async library").
- **Log Strutturati:** Tutti i log devono seguire `[REGOLA-OBS-02]`: oggetti JSON strutturati, mai stringhe concatenate. Campi obbligatori: `timestamp` (UTC ISO 8601), `level`, `message`, `correlationId`.
- **Correlazione End-to-End:** Il campo `correlationId` deve essere propagato in ogni messaggio RabbitMQ e log generato dalla feature LA2, rispettando `[REGOLA-OBS-03]`.
- **Livelli Log Semantici:** Rispetto di `[REGOLA-OBS-04]`: uso di `INFO` per eventi attesi (consegna), `WARNING` per fallimenti gestiti con backoff in corso, e solo `ERROR` se l'operazione è definitivamente conclusa o c'è perdita di integrità.
- **Codici Errori:** In caso di errori specifici del dominio (es. timeout provider esterno), evitare messaggi generici HTTP 401/500 non specificati; utilizzare codici appropriati al contesto asincrono gestito da MassTransit.

## 7. Safeguards
- **Sicurezza Identità Destinatario:** Prima di creare il record `NOTIFICA`, verificare che l'`UTENTE` destinatario esista e sia valido nel sistema. Non è necessario applicare `[SAFEGUARD-SEC-01]` (validazione dominio email) al momento dell'invio della notifica, poiché la validazione del dominio avviene all'autenticazione (`session_create`) e il record `UTENTE` contiene solo indirizzi @progettopa.it. Tuttavia, se l'email fallisce per motivi di delivery provider esterni, non tentare mai invii a domini non autorizzati o account personali che potrebbero essere stati inseriti erroneamente (sebbene i vincoli DB impediscano la creazione di tali record).
- **Integrità Dati e Atomicità:** La scrittura del record `NOTIFICA` deve avvenire in una transazione atomica con l'evento trigger. Se il database fallisce, rollback immediato (`[REGOLA-CLEAN-07]`). Non scrivere mai dati parziali nello stato di consegna.
- **Gestione Fallimenti Silenziosi:** Rispetto dell'accordo sull'anomalia: se entrambi i canali falliscono, l'azione è *solo logging*. Vietare qualsiasi tentativo di aggiramento del blocco o attivazione di fallback non concordati (es. chiamate a servizi SMS esterni) che potrebbero violare policy di sicurezza o costi operativi.
- **Isolamento delle Regole:** La logica di business per il routing e i trigger deve essere separata dal layer UI/Backend principale (`[REGOLA-CLEAN-05]`). Il Logic Agent opera come orchestratore deterministico, non contenendo logiche di presentazione né query SQL grezze nel core.
- **Limitazione Tentativi:** Rispetto del vincolo `tentativo_n <= 3`. Superato il limite con stato `FALLITA`, arrestare immediatamente la sequenza per quell'evento specifico e generare l'allerta/log finale, evitando loop infiniti o consumo eccessivo di risorse RabbitMQ.
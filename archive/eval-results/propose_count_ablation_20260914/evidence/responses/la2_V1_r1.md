# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Contesto e Scopo

La presente specifica definisce il comportamento osservabile della feature **LA2**, implementata all'interno del progetto `logic-agent`. Lo scopo è garantire la consegna affidabile di notifiche asincrone relative a eventi dinamici (cambi stato) e statici (scadenze), gestendo resilienza, routing dinamico dei destinatari e strategie di fallback multi-canale.

Il sistema opera in ambiente asincrono utilizzando RabbitMQ per il messaging, MassTransit per la gestione delle code e Quartz.NET per i job periodici. Ogni notifica genera un record persistente nell'entità `NOTIFICA` e produce log strutturati conformi alle normative di osservabilità vigenti.

## 2. Regole Operative e Vincoli

- **Entità Coinvolte:** Le operazioni interessano esclusivamente le entità `RICHIESTA`, `UTENTE` e `NOTIFICA`.
- **Stack Tecnologico:** L'implementazione deve utilizzare esclusivamente `.NET 10 Worker Service`, `RabbitMQ`, `MassTransit`, `Quartz.NET`, `Serilog` e `OpenTelemetry`.
- **Routing Dinamico:** Il destinatario (`DIPENDENTE` o `RESPONSABILE`) è determinato dinamicamente in base allo stato della `RICHIESTA` tramite uno Strategy pattern, senza hard-coding.
- **Strategia di Retry:** In caso di fallimento del canale primario (es. Email), il sistema attende un backoff configurato a 15 minuti e tenta l'invio sul canale secondario (Slack). Il limite massimo dei tentativi totali è 3.
- **Gestione Fallimenti Definitivi:** Se tutti i canali falliscono o si raggiunge il limite di tentativi, lo stato diventa `FALLITA`. Non vengono attivati fallback alternativi non concordati (es. SMS).
- **Logging e Tracing:** Tutti i log devono essere strutturati (JSON) con campi obbligatori: `timestamp`, `level`, `message`, `correlationId`. Il livello `ERROR` è riservato ai fallimenti definitivi; `WARNING` per tentativi di backoff in corso.

## 3. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica su trigger dinamico con consegna Email
  GIVEN una RICHIESTA che cambia stato da "Bozza" a "Revisato"
  AND il workflow di routing configura l'invio al DIPENDENTE
  WHEN il sistema rileva il cambiamento e pubblica l'evento su RabbitMQ
  THEN crea un record NOTIFICA con stato IN_CODA
  E invia la notifica tramite EmailChannelAdapter
  E aggiorna lo stato della NOTIFICA a CONSEGNATA
```

```gherkin
SCENARIO: S02 - Gestione fallimento Email e backoff verso Slack
  GIVEN una RICHIESTA che cambia stato innescando un trigger dinamico
  AND il routing è configurato per inviare al RESPONSABILE
  WHEN l'invio via EmailChannelAdapter fallisce per timeout del provider SMTP
  THEN incrementa il contatore tentativo_n a 1
  E registra un log di livello WARNING con messaggio "Backoff in corso"
  E attende il periodo di backoff configurato (15 minuti)
```

```gherkin
SCENARIO: S03 - Consegna definitiva tramite canale Slack dopo fallimento Email
  GIVEN una RICHIESTA che ha generato un evento trigger statico o dinamico
  AND il primo tentativo di invio via Email è fallito definitivamente
  WHEN scade il periodo di backoff e il sistema tenta l'invio su Slack
  THEN invia il messaggio tramite SlackChannelAdapter
  E aggiorna lo stato della NOTIFICA a CONSEGNATA
  E ferma la sequenza di retry per quell'evento
```

```gherkin
SCENARIO: S04 - Gestione fallimento definitivo e logging anomalia
  GIVEN una RICHIESTA che ha generato un evento trigger
  AND il tentativo iniziale su Email è fallito
  AND anche il tentativo successivo su Slack dopo 15 minuti fallisce
  WHEN il sistema raggiunge il limite massimo dei tentativi (tentativo_n = 3)
  THEN aggiorna lo stato della NOTIFICA a FALLITA
  E genera un log strutturato di livello ERROR con stato "invio mancato"
  E non attiva alcun fallback alternativo come SMS
```

## 4. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
|---|---|---|
| **Gestione Fallimenti Definitivi** | Si assume che il limite di tentativi sia rigidamente 3 per ogni evento trigger, indipendentemente dal canale. | È corretto interpretare "limite massimo dei tentativi" come un conteggio globale per evento (max 3) o per canale? Il testo specifica "limite massimo di 3 tentativi totali per evento", ma la sequenza descritta (Email fallisce -> Slack) implica che il tentativo 1 sia Email e il tentativo 2 sia Slack. Se entrambi falliscono, siamo al tentativo 2. Dove si inserisce il terzo tentativo? È un terzo tentativo su uno dei due canali o un meccanismo diverso? |
| **Trigger Statico** | Si assume che il job `StaticTriggerJob` inneschi lo stesso flusso di routing e invio del trigger dinamico. | Il job Quartz.NET esegue una scansione periodica. Se trova una scadenza imminente, pubblica l'evento su RabbitMQ esattamente come farebbe un cambio stato? O esiste un payload diverso per i trigger statici che richiede uno scenario specifico? |
| **Correlazione End-to-End** | Si assume che il `correlationId` sia generato all'inizio del processo di notifica (es. creazione evento) e propagato in tutti i log e messaggi RabbitMQ. | Come viene generato l'ID se non proviene da una richiesta HTTP esterna? Il worker service genera un GUID interno o eredita qualcosa dal contesto di transazione Outbox? |
| **Atomicità Transazionale** | Si assume che la scrittura del record `NOTIFICA` avvenga in transazione con l'evento trigger. | Cosa succede esattamente se il database rollbacka dopo aver creato il record ma prima dell'invio al broker? Il record viene cancellato o lasciato in stato inconsistente? La specifica richiede atomicità, ma non definisce lo stato intermedio di rollback. |
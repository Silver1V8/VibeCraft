# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Contesto e Scopo

La presente specifica definisce il comportamento osservabile della feature **LA2**, implementata all'interno del progetto `logic-agent`. Lo scopo è garantire la consegna affidabile di notifiche relative a eventi dinamici o statici (scadenze) associati a una `RICHIESTA`, utilizzando un'architettura asincrona basata su RabbitMQ e MassTransit. Il sistema deve gestire il routing dei destinatari (`DIPENDENTE`/`RESPONSABILE`) tramite strategie configurabili, tentare la consegna su canali multipli (Email, Slack) con logica di backoff e garantire l'integrità dei dati attraverso pattern Outbox/Inbox.

## 2. Regole di Implementazione

- **Stack Tecnologico:** Il sistema utilizza esclusivamente **.NET 10 Worker Service**, **RabbitMQ** per il messaging asincrono, **MassTransit** per la gestione dei consumer e delle code (DLQ), e **Quartz.NET** per i job periodici.
- **Entità:** Sono coinvolte le entità `RICHIESTA`, `UTENTE` e `NOTIFICA`. Gli attributi di stato della notifica sono limitati a `IN_CODA`, `CONSEGNATA`, `FALLITA`. Il contatore dei tentativi è `tentativo_n`.
- **Log Strutturati:** Tutti i log devono essere oggetti JSON con campi obbligatori: `timestamp` (UTC ISO 8601), `level`, `message`, `correlationId`. I livelli sono `INFO` per eventi attesi, `WARNING` per backoff in corso, `ERROR` per fallimenti definitivi.
- **Correlazione:** Il campo `correlationId` deve essere propagato in ogni messaggio RabbitMQ e log generato dalla feature LA2.
- **Sicurezza:** Prima di creare il record `NOTIFICA`, verificare l'esistenza dell'`UTENTE`. Non attivare fallback alternativi (es. SMS) se entrambi i canali falliscono. Limitare i tentativi a 3 (`tentativo_n <= 3`).

## 3. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica su trigger dinamico di stato
  GIVEN una RICHIESTA in stato "Bozza" associata a un UTENTE dipendente
  AND la configurazione workflow indica che lo stato "Revisato" deve notificare il DIPENDENTE
  WHEN l'operatore cambia lo stato della RICHIESTA in "Revisato"
  THEN il sistema pubblica un evento su RabbitMQ contenente l'ID della richiesta e i nuovi metadati
  AND crea un record NOTIFICA con stato IN_CODA e tentativo_n impostato a 1
```

```gherkin
SCENARIO: S02 - Invio notifica su trigger statico di scadenza imminente
  GIVEN una RICHIESTA in attesa con countdown temporale residuo inferiore a X giorni
  AND il job StaticTriggerJob esegue la scansione periodica delle scadenze
  WHEN il countdown scade o raggiunge la soglia definita dal job
  THEN il sistema pubblica un evento trigger per la notifica "SCADENZA_IMMINENTE"
  AND crea un record NOTIFICA con stato IN_CODA e tentativo_n impostato a 1
```

```gherkin
SCENARIO: S03 - Consegna riuscita del primo canale (Email)
  GIVEN un record NOTIFICA in stato IN_CODA con tentativo_n uguale a 1
  AND il sistema tenta l'invio via SMTP tramite EmailChannelAdapter
  WHEN la chiamata API SMTP risponde con successo
  THEN il sistema aggiorna lo stato della NOTIFICA a CONSEGNATA
  AND ferma i tentativi di retry e chiude la sequenza per quell'evento
```

```gherkin
SCENARIO: S04 - Gestione fallimento del primo canale (Email) e backoff
  GIVEN un record NOTIFICA in stato IN_CODA con tentativo_n uguale a 1
  AND il sistema tenta l'invio via SMTP tramite EmailChannelAdapter
  WHEN la chiamata API SMTP fallisce o times out
  THEN il sistema incrementa il contatore di tentativo_n a 2
  AND registra un log di livello WARNING indicando che si attende il backoff di 15 minuti
```

```gherkin
SCENARIO: S05 - Consegna riuscita del secondo canale (Slack) dopo fallimento Email
  GIVEN un record NOTIFICA con tentativo_n uguale a 2 e stato IN_CODA
  AND il sistema ha completato il periodo di backoff di 15 minuti
  WHEN il sistema tenta l'invio via Slack tramite SlackChannelAdapter
  AND la chiamata API Slack risponde con successo
  THEN il sistema aggiorna lo stato della NOTIFICA a CONSEGNATA
  AND ferma i tentativi di retry e chiude la sequenza per quell'evento
```

```gherkin
SCENARIO: S06 - Gestione fallimento definitivo su entrambi i canali
  GIVEN un record NOTIFICA con tentativo_n uguale a 2 e stato IN_CODA
  AND il sistema ha completato il periodo di backoff di 15 minuti
  WHEN il sistema tenta l'invio via Slack tramite SlackChannelAdapter
  AND anche la chiamata API Slack fallisce definitivamente
  THEN il sistema aggiorna lo stato della NOTIFICA a FALLITA
  AND incrementa il contatore di tentativo_n a 3 e registra un log di livello ERROR con messaggio strutturato
```

```gherkin
SCENARIO: S07 - Arresto sequenza al raggiungimento del limite massimo tentativi
  GIVEN un record NOTIFICA con tentativo_n uguale a 2 e stato IN_CODA
  AND il sistema ha completato il periodo di backoff di 15 minuti
  WHEN il sistema tenta l'invio via Slack tramite SlackChannelAdapter
  AND la chiamata API Slack fallisce definitivamente
  THEN il sistema arresta immediatamente la sequenza per quell'evento specifico
  AND non attiva fallback alternativi come chiamate a servizi SMS esterni
```

```gherkin
SCENARIO: S08 - Propagazione correlationId end-to-end
  GIVEN una RICHIESTA che innesca un evento di notifica
  WHEN il sistema elabora l'evento e genera log o invia messaggi su RabbitMQ
  THEN ogni messaggio RabbitMQ contiene il campo correlationId ereditato dal contesto
  AND ogni riga di log generata include il campo correlationId corrispondente
```

```gherkin
SCENARIO: S09 - Verifica esistenza utente prima della creazione record
  GIVEN una RICHIESTA associata a un UTENTE che non esiste nel sistema
  WHEN lo stato della RICHIESTA cambia innescando la notifica
  THEN il sistema rifiuta di creare il record NOTIFICA per l'utente inesistente
  AND registra un log di livello WARNING indicando l'anomalia dell'identità destinatario
```

## 4. Punti Aperti

- **Funzionalità: Gestione Fallimenti Silenziosi**
  - **Assunzione:** Se entrambi i canali falliscono, il sistema non invia alert esterni (es. SMS) e non blocca la pratica principale.
  - **Domanda aperta:** Qual è esattamente il contenuto del log strutturato generato al raggiungimento dello stato `FALLITA`? È necessario includere nel campo `message` anche i dettagli dell'errore specifico del provider o solo lo stato aggregato?

- **Funzionalità: Timeout di Consegna**
  - **Assunzione:** La finestra temporale massima per tentare le consegne è di 15 minuti tra i tentativi su canali diversi.
  - **Domanda aperta:** Se il primo tentativo (Email) fallisce e il secondo (Slack) ha successo esattamente al termine dei 15 minuti, il sistema considera l'operazione conclusa o richiede un terzo tentativo immediato? La specifica attuale prevede un massimo di 3 tentativi totali; se il limite è raggiunto dopo il fallimento del secondo canale, la sequenza si arresta.
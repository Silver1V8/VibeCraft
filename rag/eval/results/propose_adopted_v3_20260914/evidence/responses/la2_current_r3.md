# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

**Progetto:** Logic Agent Worker Service  
**Versione:** 1.0.0  
**Data:** 2026-07-23  
**Autore:** Analista Software BDD  

---

## 1. Scopo e Ambito

Questo documento definisce il comportamento osservabile della feature **LA2**, dedicata alla gestione asincrona delle notifiche dinamiche all'interno del modulo `logic-agent`. La feature gestisce l'invio di comunicazioni (Email, Slack) in risposta a eventi dinamici o statici (scadenze), applicando strategie di routing, retry multi-canale e logging strutturato.

L'ambito si limita esclusivamente al comportamento dell'agente logico (`Portal.LogicAgent.Worker`), inclusi i consumatori RabbitMQ, i job Quartz.NET e gli adapter di canale. Non sono descritti comportamenti di UI, dashboard o moduli esterni non citati nel Canvas.

## 2. Entità e Dati

- **RICHIESTA**: Entità sorgente che innesca il processo. Include `richiesta_id`, stato corrente e metadati per il countdown.
- **UTENTE**: Entità target del messaggio. Include `id` e indirizzo email/slack.
- **NOTIFICA**: Entità derivata che registra l'artefatto di comunicazione. Attributi: `richiesta_id`, `utente_id`, `canale` (EMAIL/SLACK), `stato_consegna` (IN_CODA, CONSEGNATA, FALLITA), `tentativo_n`.

## 3. Regole Operative e Normative

- **[REGOLA-NOTIF-02]**: Instradamento asincrono su Slack per i manager/destinatari specifici.
- **[REGOLA-NOTIF-03]**: Invio email transazionale ai dipendenti/destinatari specifici.
- **[REGOLA-VAL-01]**: Accodamento e gestione dei fallimenti di rete (max 3 tentativi, backoff).
- **[REGOLA-OBS-02]**: Log strutturati (JSON), mai stringhe concatenate.
- **[REGOLA-OBS-03]**: Correlazione end-to-end tramite `correlationId`.
- **[REGOLA-OBS-04]**: Semantica dei livelli log (`INFO`, `WARNING`, `ERROR`).
- **[SAFEGUARD-SEC-07]**: Gestione fallimenti silenziosi (logging solo, nessun fallback non concordato).

## 4. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica Email su trigger dinamico riuscito
  GIVEN una RICHIESTA con stato cambiato da "Bozza" a "Revisato"
  AND un record NOTIFICA creato in stato IN_CODA per il dipendente target
  WHEN il consumer NotificationConsumer elabora l'evento di cambio stato
  THEN invia la notifica via Email tramite EmailChannelAdapter
  E aggiorna lo stato della NOTIFICA su CONSEGNATA
  E registra un log di livello INFO con successo
```

```gherkin
SCENARIO: S02 - Invio notifica Slack su trigger dinamico riuscito
  GIVEN una RICHIESTA con stato cambiato da "Bozza" a "Revisato"
  AND un record NOTIFICA creato in stato IN_CODA per il responsabile target
  WHEN il consumer NotificationConsumer elabora l'evento di cambio stato
  THEN invia la notifica via Slack tramite SlackChannelAdapter
  E aggiorna lo stato della NOTIFICA su CONSEGNATA
  E registra un log di livello INFO con successo
```

```gherkin
SCENARIO: S03 - Gestione fallimento Email e retry su Slack (Backoff)
  GIVEN una RICHIESTA che innesca una notifica per il dipendente
  AND il record NOTIFICA creato in stato IN_CODA
  WHEN l'invio via Email tramite EmailChannelAdapter fallisce al primo tentativo
  THEN incrementa il contatore tentativo_n a 1
  E imposta lo stato della NOTIFICA su IN_CODA con backoff di 15 minuti
  E dopo il backoff tenta l'invio via Slack tramite SlackChannelAdapter
```

```gherkin
SCENARIO: S04 - Fallimento definitivo e logging anomalia
  GIVEN una RICHIESTA che innesca una notifica per il dipendente
  AND un record NOTIFICA creato con tentativo_n = 1 su Email fallito
  WHEN anche l'invio via Slack al secondo tentativo fallisce
  THEN incrementa il contatore tentativo_n a 2
  E se si raggiunge il limite di tentativi (tentativo_n = 3) o entrambi i canali falliscono definitivamente
  E aggiorna lo stato della NOTIFICA su FALLITA
  E registra un log strutturato di livello ERROR con messaggio "invio mancato"
```

```gherkin
SCENARIO: S05 - Innesco trigger statico per scadenza imminente
  GIVEN una RICHIESTA in attesa con countdown <= X giorni
  AND il job StaticTriggerJob Quartz.NET esegue la scansione periodica
  WHEN il countdown scade o raggiunge la soglia di allerta
  THEN pubblica un evento asincrono su RabbitMQ per "SCADENZA_IMMINENTE"
  E crea un record NOTIFICA in stato IN_CODA per il destinatario configurato
```

```gherkin
SCENARIO: S06 - Gestione utente non valido prima dell'invio
  GIVEN una RICHIESTA che richiede notifica a un UTENTE target
  AND l'UTENTE destinatario risulta inesistente o invalido nel sistema
  WHEN il consumer NotificationConsumer elabora l'evento trigger
  THEN non crea record NOTIFICA per quell'utente specifico
  E registra un log di livello WARNING indicando "destinatario non trovato"
```

```gherkin
SCENARIO: S07 - Propagazione CorrelationId end-to-end
  GIVEN una RICHIESTA con un correlationId generato in ingresso
  WHEN il consumer elabora l'evento e invia la notifica su RabbitMQ
  THEN il messaggio nella coda RabbitMQ contiene lo stesso correlationId
  E ogni log generato (INFO, WARNING, ERROR) include il campo correlationId
```

```gherkin
SCENARIO: S08 - Invio Email riuscito con rollback transazionale
  GIVEN una RICHIESTA che innesca un evento trigger dinamico
  AND la scrittura del record NOTIFICA avviene in transazione Outbox
  WHEN l'invio via Email è riuscito ma il database fallisce dopo
  THEN il sistema rollback immediatamente la transazione
  E lo stato della NOTIFICA non viene aggiornato a CONSEGNATA
```

## 5. Punti aperti

```json
{"open_points":[{"id":"OP-001","functionality":"Trigger Statico (S05)","original_question":"Qual è esattamente il valore di X giorni per la soglia?", "question":"Il job Quartz.NET utilizza una finestra fissa o dinamica basata su configurazione?", "assumption":null,"uncovered_scenarios":[],"reason":"missing_coverage","research":{"status":"not_started","new_evidence":[],"verification":"agent_reported"}}]}
```
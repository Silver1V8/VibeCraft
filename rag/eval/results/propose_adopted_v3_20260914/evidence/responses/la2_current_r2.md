# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Scopo e Ambito

Il presente documento definisce il comportamento osservabile della feature **LA2**, responsabile dell'integrazione delle notifiche dinamiche all'interno del modulo `logic-agent`. La feature gestisce l'invio asincrono di comunicazioni relative a eventi dinamici (cambi stato) e statici (scadenze), garantendo resilienza tramite strategie multi-canale (Email, Slack) e gestione esplicita dei fallimenti.

L'architettura si basa su un **Logic Agent** asincrono implementato con **.NET 10 Worker Service**, **RabbitMQ**, **MassTransit** per il messaging e **Quartz.NET** per i job periodici. Il sistema deve rispettare rigorosamente le norme di osservabilità (`[REGOLA-OBS-xx]`) e sicurezza (`[SAFEGUARD-SEC-xx]`) definite nei documenti normativi associati.

## 2. Entità e Dati

Il sistema opera sulle seguenti entità persistenti:
*   **`RICHIESTA`**: Sorgente dell'evento (dinamico o countdown).
*   **`UTENTE`**: Destinatario della notifica (Dipendente o Responsabile).
*   **`NOTIFICA`**: Record di audit dell'invio, contenente stato (`IN_CODA`, `CONSEGNATA`, `FALLITA`), canale utilizzato e numero tentativo.

## 3. Scenari Comportamentali BDD

### Funzionalità: Innesco Trigger Dinamico (Cambiamento Stato)

```gherkin
SCENARIO: S01 - Invio notifica su cambio stato a dipendente
  GIVEN una RICHIESTA in stato "Bozza" associata a un UTENTE dipendente
  AND la configurazione workflow indica che lo stato "Revisato" richiede notifica al dipendente
  WHEN l'operatore cambia lo stato della RICHIESTA in "Revisato"
  THEN il sistema pubblica un evento su RabbitMQ contenente l'ID della RICHIESTA
  E crea un record NOTIFICA con stato IN_CODA e tentativo_n = 1
  E tenta l'invio tramite EmailChannelAdapter
```

```gherkin
SCENARIO: S02 - Invio notifica su cambio stato a responsabile
  GIVEN una RICHIESTA in stato "In Attesa" associata a un UTENTE responsabile
  AND la configurazione workflow indica che lo stato "Approvato" richiede notifica al responsabile
  WHEN l'operatore cambia lo stato della RICHIESTA in "Approvato"
  THEN il sistema pubblica un evento su RabbitMQ contenente l'ID della RICHIESTA
  E crea un record NOTIFICA con stato IN_CODA e tentativo_n = 1
  E tenta l'invio tramite EmailChannelAdapter
```

```gherkin
SCENARIO: S03 - Invio notifica a entrambi i ruoli
  GIVEN una RICHIESTA in stato "Rifiutato" associata a un UTENTE dipendente e uno responsabile
  AND la configurazione workflow indica che lo stato "Rifiutato" richiede notifica a entrambi
  WHEN l'operatore cambia lo stato della RICHIESTA in "Rifiutato"
  THEN il sistema pubblica eventi separati per ciascun destinatario su RabbitMQ
  E crea due record NOTIFICA distinti, ciascuno con tentativo_n = 1
```

### Funzionalità: Innesco Trigger Statico (Scadenze Imminenti)

```gherkin
SCENARIO: S04 - Notifica scadenza imminente attivata da job
  GIVEN una RICHIESTA con countdown temporale impostato a 2 giorni
  AND il job StaticTriggerJob esegue la scansione periodica delle scadenze
  WHEN il countdown scende sotto la soglia di attivazione (es. 1 giorno)
  THEN il job pubblica un evento su RabbitMQ per "SCADENZA_IMMINENTE"
  E crea un record NOTIFICA con stato IN_CODA e tentativo_n = 1
```

```gherkin
SCENARIO: S05 - Scadenza non attivata per countdown insufficiente
  GIVEN una RICHIESTA con countdown temporale impostato a 3 giorni
  AND il job StaticTriggerJob esegue la scansione periodica
  WHEN il countdown è ancora superiore alla soglia di attivazione
  THEN il sistema non pubblica eventi su RabbitMQ
  E non crea record NOTIFICA per questa richiesta in questo ciclo
```

### Funzionalità: Gestione Fallimenti e Backoff Multi-Canale

```gherkin
SCENARIO: S06 - Fallimento Email, tentativo Slack dopo backoff
  GIVEN un evento trigger pubblicato su RabbitMQ
  AND il sistema tenta l'invio via EmailChannelAdapter che fallisce (es. SMTP offline)
  WHEN il sistema incrementa tentativo_n a 1 e applica il backoff di 15 minuti
  THEN dopo il periodo di attesa, il sistema riprende la sequenza
  E tenta l'invio tramite SlackChannelAdapter
```

```gherkin
SCENARIO: S07 - Fallimento definitivo entrambi i canali
  GIVEN un evento trigger pubblicato su RabbitMQ
  AND EmailChannelAdapter fallisce al primo tentativo
  AND SlackChannelAdapter fallisce al secondo tentativo (tentativo_n = 2)
  WHEN il sistema raggiunge il limite massimo di tentativi (3) o esaurisce le opzioni
  THEN il sistema aggiorna lo stato della NOTIFICA a FALLITA
  E registra un log strutturato con livello ERROR e stato FALLO definitivamente
```

```gherkin
SCENARIO: S08 - Consegna riuscita su Slack dopo fallimento Email
  GIVEN un evento trigger pubblicato su RabbitMQ
  AND EmailChannelAdapter fallisce al primo tentativo
  WHEN il sistema tenta l'invio tramite SlackChannelAdapter dopo il backoff
  THEN SlackChannelAdapter invia con successo il messaggio
  E il sistema aggiorna lo stato della NOTIFICA a CONSEGNATA
```

### Funzionalità: Logging e Monitoraggio

```gherkin
SCENARIO: S09 - Log strutturato su fallimento definitivo
  GIVEN un evento trigger che ha esaurito tutti i tentativi di invio
  WHEN il sistema determina lo stato FALLITA per la NOTIFICA
  THEN il sistema genera un log strutturato con campi timestamp, level (ERROR), message e correlationId
  E incrementa il contatore dei tentativi fino al limite massimo (3) nel record
```

```gherkin
SCENARIO: S10 - Propagazione CorrelationId end-to-end
  GIVEN una RICHIESTA che innesca un evento di notifica
  WHEN l'evento viene elaborato dal consumer e genera log o errori
  THEN ogni riga di log generata include il campo correlationId ereditato dall'evento
  E il tracing OpenTelemetry accompagna il messaggio attraverso le code RabbitMQ
```

## 4. Punti aperti

```json
{"open_points":[{"id":"OP-001","functionality":"Innesco Trigger Statico","original_question":"Qual è la soglia esatta di countdown per attivare la notifica?", "question":"Il job StaticTriggerJob utilizza una soglia fissa (es. <= 24h) o variabile configurabile per ogni richiesta?", "assumption":null,"uncovered_scenarios":["S05"], "reason":"missing_coverage","research":{"status":"not_started","new_evidence":[],"verification":"agent_reported"}}]
```
# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Scopo e Ambito

Il presente documento definisce il comportamento osservabile della feature **LA2**, implementata all'interno del progetto `logic-agent`. La feature gestisce l'invio asincrono di notifiche relative a eventi dinamici (cambi stato) e statici (scadenze), garantendo resilienza tramite retry multi-canale (Email, Slack) e logging strutturato.

L'implementazione rispetta rigorosamente le normative `[REGOLA-OBS-01]`-[`REGOLA-OBS-04`] per l'osservabilità e i vincoli di sicurezza definiti nel Canvas. Il sistema opera esclusivamente tramite lo stack `.NET 10 Worker Service`, `RabbitMQ`, `MassTransit` e `Quartz.NET`.

## 2. Entità e Dati

Tutti gli scenari si riferiscono alle seguenti entità, con attributi obbligatori:
- **RICHIESTA**: Identificata da `richiesta_id`, contiene lo stato corrente e il countdown temporale.
- **UTENTE**: Identificato da `id`, rappresenta il destinatario (Dipendente o Responsabile).
- **NOTIFICA**: Record persistente con attributi `stato_consegna` (`IN_CODA`, `CONSEGNATA`, `FALLITA`) e `tentativo_n`.

## 3. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica su trigger dinamico di stato
  GIVEN una RICHIESTA con ID "REQ-001" in stato "Bozza"
  AND un UTENTE con ID "USR-01" configurato come destinatario per lo stato "Revisato"
  WHEN la RICHIESTA cambia stato da "Bozza" a "Revisato"
  THEN il sistema crea un record NOTIFICA con stato_consegna "IN_CODA" e tentativo_n 1
  AND accoda l'evento di invio su RabbitMQ per il canale Email
```

```gherkin
SCENARIO: S02 - Invio notifica su trigger statico di scadenza
  GIVEN una RICHIESTA con ID "REQ-002" in stato "In Attesa" e countdown <= 1 giorno
  AND un job StaticTriggerJob attivo che esegue la scansione periodica
  WHEN il job rileva che la scadenza è imminente per REQ-002
  THEN il sistema crea un record NOTIFICA con stato_consegna "IN_CODA" e tentativo_n 1
  AND accoda l'evento di invio su RabbitMQ per il canale Email
```

```gherkin
SCENARIO: S03 - Fallimento primo tentativo Email e backoff Slack
  GIVEN una RICHIESTA che innesca un evento di notifica
  WHEN il sistema tenta l'invio via Email tramite EmailChannelAdapter e riceve errore di delivery
  THEN il sistema incrementa lo stato della NOTIFICA a "IN_CODA" con tentativo_n 2
  AND applica un backoff di 15 minuti prima di tentare Slack
```

```gherkin
SCENARIO: S04 - Consegna riuscita su canale Slack dopo fallimento Email
  GIVEN una RICHIESTA che ha fallito l'invio via Email (tentativo_n 1)
  AND il sistema attende il periodo di backoff configurato
  WHEN il sistema tenta l'invio via Slack tramite SlackChannelAdapter e riceve risposta OK
  THEN il sistema aggiorna lo stato della NOTIFICA a "CONSEGNATA"
  AND ferma la sequenza di retry per quell'evento
```

```gherkin
SCENARIO: S05 - Fallimento definitivo dopo esaurimento tentativi
  GIVEN una RICHIESTA che ha fallito l'invio via Email (tentativo_n 1)
  AND il sistema tenta l'invio via Slack e riceve errore di delivery
  WHEN il sistema raggiunge il limite massimo di tentativi (tentativo_n = 3)
  THEN il sistema aggiorna lo stato della NOTIFICA a "FALLITA"
  AND registra un log strutturato con livello ERROR contenente i dettagli dell'anomalia
```

```gherkin
SCENARIO: S06 - Logging strutturato e correlazione end-to-end
  GIVEN una RICHIESTA che innesca una notifica fallita definitivamente
  WHEN il sistema genera il log di anomalia finale
  THEN il log contiene i campi obbligatori timestamp, level, message, correlationId
  AND il livello del log è impostato su ERROR
```

```gherkin
SCENARIO: S07 - Non attivazione fallback alternativi non concordati
  GIVEN una RICHIESTA che ha fallito sia Email che Slack
  WHEN il sistema raggiunge lo stato FALLITA definitivo
  THEN il sistema NON attiva canali alternativi come SMS
  AND NON blocca la pratica principale della RICHIESTA
```

```gherkin
SCENARIO: S08 - Gestione integrità dati in transazione fallita
  GIVEN una RICHIESTA che innesca un evento di notifica
  WHEN il database fallisce durante la scrittura del record NOTIFICA
  THEN la transazione viene rollbackata immediatamente
  AND non vengono scritti dati parziali nello stato di consegna
```

## 4. Punti Aperti

| Funzionalità Coinvolta | Assunzione Proposta DA CONFERMARE | Domanda Aperta |
|---|---|---|
| Gestione Trigger Statico (S02) | Il job `StaticTriggerJob` scansiona tutte le richieste o solo quelle in uno stato specifico? | È necessario definire lo stato esatto della `RICHIESTA` che deve essere monitorato per il countdown, oltre a "In Attesa"? |
| Backoff Multi-Canale (S03) | Il backoff di 15 minuti è applicato tra Email e Slack o solo in caso di fallimento ripetuto dello stesso canale? | La specifica richiede un backoff configurato a 15 minuti tra tentativi su canali *diversi*. Va chiarito se questo intervallo si applica anche al passaggio da Email a Slack dopo il primo fallimento, o solo per retry sullo stesso canale. |
| Logging Anomalia (S06) | Il campo `correlationId` è generato dal middleware di ingresso o ereditato dalla richiesta originale? | Va confermato se il `correlationId` deve essere sempre presente anche per eventi interni asincroni non derivanti da una richiesta HTTP diretta. |
| Fallback Silenzioso (S07) | La policy "non attivare fallback alternativi" si applica solo a canali esterni costosi (es. SMS) o a qualsiasi canale non configurato nel workflow? | Va specificato se l'attivazione di un canale non previsto (es. WhatsApp) è considerata una violazione della policy o semplicemente ignorata dal sistema. |
| Integrità Dati (S08) | Il rollback avviene solo sul record `NOTIFICA` o anche sugli eventi pubblicati su RabbitMQ? | Va chiarito se il publish dell'evento su RabbitMQ deve essere atomico con la scrittura DB o se può avvenire prima, richiedendo un idempotency check nel consumer. |

## 5. Riepilogo Copertura

La feature LA2 è coperta da 8 scenari (S01-S08), distribuiti su 4 funzionalità principali:
1.  **Innesco Trigger**: S01 (Dinamico), S02 (Statico).
2.  **Resilienza e Routing**: S03 (Fallimento Email/Backoff), S04 (Successo Slack).
3.  **Gestione Fallimenti Definitivi**: S05 (Limite tentativi), S07 (Nessun fallback extra).
4.  **Osservabilità e Sicurezza**: S06 (Log strutturati), S08 (Atomicità transazionale).

Tutti gli scenari rispettano il formato Gherkin richiesto, utilizzano esclusivamente le tecnologie citate nel Canvas e i vincoli normativi `[REGOLA-OBS-xx]`.
# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Scopo e Ambito

Il presente documento definisce il comportamento osservabile della feature **LA2**, implementata all'interno del progetto `logic-agent`. La feature gestisce l'invio asincrono di notifiche relative a eventi dinamici (cambi stato) e statici (scadenze), garantendo resilienza attraverso un meccanismo multi-canale (Email, Slack) con logica di retry esplicita.

L'architettura si basa su uno stack **.NET 10 Worker Service**, utilizza **RabbitMQ** per il messaging asincrono gestito da **MassTransit**, e impiega **Quartz.NET** per i job periodici. La persistenza avviene tramite le entità `NOTIFICA`, `RICHIESTA` e `UTENTE`.

## 2. Regole di Implementazione

- **Stack Tecnologico:** Utilizzo tassativo di **.NET 10 Worker Service**, **RabbitMQ**, **MassTransit** e **Quartz.NET**.
- **Nomenclatura Entità:** Uso esclusivo dei nomi `NOTIFICA`, `RICHIESTA`, `UTENTE`. Attributi: `stato_consegna` (`IN_CODA`, `CONSEGNATA`, `FALLITA`), `tentativo_n`.
- **Log Strutturati:** Campi obbligatori: `timestamp` (UTC ISO 8601), `level`, `message`, `correlationId`. Livelli: `INFO` (consegna), `WARNING` (backoff), `ERROR` (fallimento definitivo).
- **Correlazione:** Propagazione del `correlationId` su ogni messaggio RabbitMQ e log.
- **Limiti di Tentativo:** Massimo 3 tentativi totali per evento (`tentativo_n <= 3`). Backoff fisso di 15 minuti tra i canali diversi.
- **Fallback Silenzioso:** In caso di fallimento definitivo (tutti i canali esauriti), il sistema registra l'anomalia e non attiva fallback alternativi (es. SMS).

## 3. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica su trigger dinamico di stato
  GIVEN una RICHIESTA in stato "Bozza"
  AND un utente UTENTE designato come RESPONSABILE per la pratica
  WHEN lo stato della RICHIESTA cambia a "Revisato"
  THEN il sistema pubblica un evento asincrono su RabbitMQ contenente l'ID della richiesta
  E istanzia una strategia di routing che seleziona l'utente RESPONSABILE
  E crea un record NOTIFICA con stato_consegna IN_CODA e tentativo_n impostato a 1
```

```gherkin
SCENARIO: S02 - Invio notifica su trigger statico di scadenza imminente
  GIVEN una RICHIESTA in attesa con countdown temporale residuo <= X giorni
  AND il job StaticTriggerJob esegue la scansione periodica delle scadenze
  WHEN il countdown scade o raggiunge la soglia definita
  THEN il sistema pubblica un evento asincrono su RabbitMQ per l'evento "SCADENZA_IMMINENTE"
  E crea un record NOTIFICA con stato_consegna IN_CODA e tentativo_n impostato a 1
```

```gherkin
SCENARIO: S03 - Invio riuscito del primo canale (Email)
  GIVEN una notifica in coda per invio via EmailChannelAdapter
  AND il server SMTP è raggiungibile e accetta la connessione
  WHEN il sistema tenta l'invio della prima notifica (tentativo_n = 1)
  THEN il record NOTIFICA viene aggiornato con stato_consegna CONSEGNATA
  E la sequenza di invio per quell'evento si interrompe senza ulteriori tentativi
```

```gherkin
SCENARIO: S04 - Fallimento del primo canale e backoff verso Slack
  GIVEN una notifica in coda per invio via EmailChannelAdapter
  AND il server SMTP rifiuta la connessione o l'email non viene consegnata
  WHEN il sistema tenta l'invio della prima notifica (tentativo_n = 1)
  THEN il record NOTIFICA mantiene stato_consegna IN_CODA e incrementa tentativo_n a 2
  E il sistema applica un backoff di 15 minuti prima di tentare SlackChannelAdapter
```

```gherkin
SCENARIO: S05 - Invio riuscito del secondo canale (Slack) dopo fallimento Email
  GIVEN una notifica in coda per invio via SlackChannelAdapter
  AND il sistema ha completato il periodo di backoff da un precedente fallimento Email
  WHEN il sistema tenta l'invio della seconda notifica (tentativo_n = 2)
  THEN il record NOTIFICA viene aggiornato con stato_consegna CONSEGNATA
  E la sequenza di invio per quell'evento si interrompe senza ulteriori tentativi
```

```gherkin
SCENARIO: S06 - Fallimento definitivo e logging dell'anomalia
  GIVEN una notifica in coda per invio via SlackChannelAdapter
  AND il sistema ha già fallito l'invio su Email (tentativo_n = 1) e ora anche Slack fallisce (tentativo_n = 2)
  WHEN il sistema tenta l'invio della terza notifica (tentativo_n = 3)
  THEN il record NOTIFICA viene aggiornato con stato_consegna FALLITA
  E il sistema genera un log strutturato con livello ERROR contenente i dettagli dell'anomalia
```

```gherkin
SCENARIO: S07 - Arrivo di messaggio duplicato (Idempotenza)
  GIVEN una notifica già elaborata e inserita nell'Inbox di MassTransit
  AND lo stesso evento trigger viene ripubblicato su RabbitMQ a causa di un errore del consumer precedente
  WHEN il consumer riceve nuovamente il messaggio con lo stesso ID correlato
  THEN il sistema ignora il messaggio duplicato senza creare record duplicati o incrementare tentativi
```

```gherkin
SCENARIO: S08 - Logging strutturato durante il backoff
  GIVEN una notifica in fase di retry su Email (tentativo_n = 1) che fallisce
  AND il sistema sta applicando il backoff verso Slack
  WHEN il sistema registra lo stato intermedio del tentativo
  THEN il log generato ha livello WARNING e include il campo correlationId
```

## 4. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
|---|---|---|
| Gestione Trigger Statico (S02) | Il job `StaticTriggerJob` scansiona *tutte* le richieste o solo quelle in uno stato specifico di attesa? | Qual è esattamente lo stato della `RICHIESTA` che deve essere monitorato dal job Quartz.NET per innescare la notifica di scadenza? |
| Logging Fallimento Definitivo (S06) | Il log finale viene scritto nel file di log applicativo o in una tabella dedicata dell'audit log? | La specifica richiede di distinguere tra "log applicativo" e "audit log". Per il fallimento definitivo della notifica, dove deve essere registrato l'errore definitivamente? |
| Backoff Multi-Canale (S04) | Il backoff di 15 minuti è un tempo fisso assoluto o dipende dalla latenza di rete rilevata? | La specifica indica "periodo di backoff configurato a 15 minuti". È necessario esportare una metrica per monitorare questo intervallo fisso? |
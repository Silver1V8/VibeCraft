# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Contesto e Scopo

La presente specifica definisce il comportamento osservabile della feature **LA2**, implementata all'interno del progetto `logic-agent`. Lo scopo è garantire la consegna affidabile di notifiche relative a eventi dinamici o statici (scadenze) associati a una `RICHIESTA`, gestendo in modo resiliente i fallimenti dei canali di comunicazione (`EMAIL`, `SLACK`) tramite strategie di retry e fallback silenzioso.

La feature si basa su un'architettura asincrona che utilizza lo stack **.NET 10 Worker Service**, **RabbitMQ** per il messaging, **MassTransit** per la gestione dei consumer/retry/DLQ e **Quartz.NET** per i job periodici. Ogni invio genera un record nell'entità `NOTIFICA` con stato di consegna (`IN_CODA`, `CONSEGNATA`, `FALLITA`) e numero di tentativo (`tentativo_n`).

## 2. Regole Operative e Vincoli

- **Nomenclatura Entità:** Uso esclusivo dei nomi definiti nel glossario: `NOTIFICA`, `RICHIESTA`, `UTENTE`. Attributi come `stato_consegna` e `tentativo_n` devono essere usati senza variazioni.
- **Stack Tecnologico:** Utilizzo tassativo di **.NET 10 Worker Service**, **RabbitMQ**, **MassTransit** e **Quartz.NET**. Non usare librerie alternative o generiche.
- **Log Strutturati:** Tutti i log devono seguire `[REGOLA-OBS-02]`: oggetti JSON strutturati, mai stringhe concatenate. Campi obbligatori: `timestamp` (UTC ISO 8601), `level`, `message`, `correlationId`.
- **Correlazione End-to-End:** Il campo `correlationId` deve essere propagato in ogni messaggio RabbitMQ e log generato dalla feature LA2, rispettando `[REGOLA-OBS-03]`.
- **Livelli Log Semantici:** Rispetto di `[REGOLA-OBS-04]`: uso di `INFO` per eventi attesi (consegna), `WARNING` per fallimenti gestiti con backoff in corso, e solo `ERROR` se l'operazione è definitivamente conclusa o c'è perdita di integrità.
- **Limitazione Tentativi:** Rispetto del vincolo `tentativo_n <= 3`. Superato il limite con stato `FALLITA`, arrestare immediatamente la sequenza per quell'evento specifico e generare l'allerta/log finale.
- **Fallback Silenzioso:** Se entrambi i canali (`EMAIL`, `SLACK`) falliscono definitivamente, l'azione è *solo logging*. Vietare qualsiasi tentativo di attivazione di fallback alternativi (es. SMS).

## 3. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica Email riuscito per trigger dinamico
  GIVEN una RICHIESTA in stato "Revisato" che attiva un trigger dinamico
  AND il sistema identifica come destinatario l'utente dipendente tramite configurazione workflow
  WHEN il consumer NotificationConsumer elabora l'evento e tenta l'invio via EMAIL
  THEN il record NOTIFICA viene creato con stato_consegna "CONSEGNATA" e tentativo_n "1"
  E lo stato della RICHIESTA rimane invariato
```

```gherkin
SCENARIO: S02 - Gestione fallimento Email con backoff verso Slack
  GIVEN una RICHIESTA che attiva un trigger dinamico per notifica al dipendente
  WHEN il tentativo di invio via EMAIL fallisce (es. timeout SMTP) e il sistema incrementa tentativo_n a "1"
  AND il sistema attende il periodo di backoff configurato a 15 minuti
  THEN il sistema tenta l'invio tramite SLACK
  E se anche Slack fallisce, lo stato della NOTIFICA viene aggiornato a "FALLITA" con tentativo_n "2"
```

```gherkin
SCENARIO: S03 - Arrivo al limite massimo tentativi e chiusura sequenza
  GIVEN una RICHIESTA che innesca una notifica statica per scadenza imminente
  WHEN il sistema esegue i tentativi di invio su EMAIL e SLACK raggiungendo il limite tentativo_n "3"
  AND entrambi i canali falliscono definitivamente
  THEN lo stato della NOTIFICA viene impostato a "FALLITA"
  E il sistema genera un log strutturato con livello "ERROR" contenente lo stato "FALLITA"
```

```gherkin
SCENARIO: S04 - Invio notifica Slack riuscito per trigger statico
  GIVEN una RICHIESTA in attesa di scadenza dove il countdown è scaduto
  AND la configurazione workflow indica come destinatario il RESPONSABILE
  WHEN il job StaticTriggerJob pubblica l'evento e il consumer tenta l'invio via SLACK
  THEN il record NOTIFICA viene creato con stato_consegna "CONSEGNATA" e tentativo_n "1"
  E il canale EMAIL non viene tentato in quanto non configurato per questo ruolo
```

## 4. Punti Aperti

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
|---|---|---|
| Gestione Trigger Statico (S04) | Il sistema tenta l'invio solo sui canali configurati per il ruolo specifico del destinatario, ignorando i canali non pertinenti. | Se un ruolo ha solo EMAIL configurato ma questo fallisce, il sistema passa a SLACK o chiude immediatamente? Attualmente S04 assume che se Slack è usato, Email non viene tentato, ma la regola "prova tutti i canali possibili" potrebbe implicare una sequenza fissa indipendentemente dal ruolo. |
| Backoff Multi-Canale (S02) | Il backoff di 15 minuti si applica tra il fallimento del primo canale e il tentativo del secondo, non cumulativamente per ogni singolo fallimento all'interno della finestra dei 3 tentativi totali. | La specifica indica "backoff configurato a 15 minuti" ma anche "limite massimo dei tentativi o esaurimento delle opzioni". È corretto interpretare che i 3 tentativi totali includano il secondo tentativo dopo 15 min, oppure che i 3 tentativi siano sequenziali rapidi e il backoff sia solo per la transizione canale? |
| Logging Fallimento Definitivo (S03) | Il log finale con livello "ERROR" viene generato immediatamente al raggiungimento del limite di tentativi, senza ulteriori verifiche asincrone. | La specifica richiede un log strutturato. È necessario includere nel payload del log anche il `correlationId` e i dettagli dell'anomalia come richiesto da `[REGOLA-OBS-02]` e `[REGOLA-OBS-03]`? (Assunto: Sì, ma non testato esplicitamente nello scenario). |
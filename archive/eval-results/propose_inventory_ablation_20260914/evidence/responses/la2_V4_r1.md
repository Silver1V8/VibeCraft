# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## Inventario delle funzionalità

| Funzionalità | Ancoraggio al Canvas o alla fonte | Casi previsti (nominale / negativo) | Riferimento agli scenari o al punto aperto |
|---|---|---|---|
| F1: Trigger Ibrido e Routing Dinamico | Sezione 1. Requirements (Trigger Ibrido, Configurazione Workflow Dinamica); Sezione 4. Structure (Innesco Trigger Dinamico/Statico) | Nominale: Invio su Email o Slack in base a stato/countdown.<br>Negativo: Destinatario non valido o pratica annullata. | S01, S02 |
| F2: Gestione Backoff Multi-Canale e Timeout | Sezione 1. Requirements (Resilienza e Backoff Multi-Canale, Timeout di Consegna); Sezione 3. Approach (Retry Logic) | Nominale: Email fallisce -> Backoff 15min -> Slack riuscito.<br>Negativo: Entrambi i canali falliscono entro il timeout. | S03, S04 |
| F3: Logging Anomalie e Stati di Consegna | Sezione 1. Requirements (Logging dell'Anomalia); Sezione 6. Norms (Livelli Log Semantici) | Nominale: Aggiornamento stato a CONSEGNATA.<br>Negativo: Aggiornamento stato a FALLITA con log ERROR. | S05, S06 |
| F4: Persistenza e Idempotenza | Sezione 3. Approach (Transactional Outbox & Inbox Pattern); Sezione 2. Entities (NOTIFICA) | Nominale: Record creato atomicamente.<br>Negativo: Tentativo di duplicazione prevenuto dall'Inbox. | S07, S08 |

---

## Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica su Email per trigger dinamico riuscito
  GIVEN una RICHIESTA in stato "Revisato" che attiva un trigger dinamico
  AND il workflow di routing configura il destinatario come "DIPENDENTE"
  WHEN il sistema pubblica l'evento asincrono su RabbitMQ
  THEN crea un record NOTIFICA con stato "IN_CODA" e canale "EMAIL"
  E invia la notifica tramite EmailChannelAdapter
  E aggiorna lo stato della NOTIFICA a "CONSEGNATA"
```

```gherkin
SCENARIO: S02 - Invio negato per destinatario non valido nel trigger dinamico
  GIVEN una RICHIESTA in stato "Revisato" che attiva un trigger dinamico
  AND il workflow di routing configura il destinatario come "DIPENDENTE"
  WHEN il sistema tenta di creare il record NOTIFICA riferito a un UTENTE inesistente
  THEN il sistema rollbacka la transazione atomica
  E non crea alcun record NOTIFICA persistente
```

```gherkin
SCENARIO: S03 - Backoff multi-canale: Email fallisce e Slack riesce dopo 15 minuti
  GIVEN una RICHIESTA che innesca un trigger statico "SCADENZA_IMMINENTE"
  WHEN il sistema tenta l'invio via EMAIL e riceve un errore di delivery dal provider
  E incrementa il contatore tentativo_n a 1
  E attende il periodo di backoff configurato a 15 minuti
  THEN riprende la sequenza tentando l'invio tramite SlackChannelAdapter
  E aggiorna lo stato della NOTIFICA a "CONSEGNATA" dopo il successo su Slack
```

```gherkin
SCENARIO: S04 - Fallimento definitivo: entrambi i canali falliscono entro il timeout
  GIVEN una RICHIESTA che innesca un trigger statico "SCADENZA_IMMINENTE"
  WHEN l'invio via EMAIL fallisce e, dopo 15 minuti, anche l'invio via Slack fallisce
  E il contatore tentativo_n raggiunge il limite massimo di 3
  THEN aggiorna lo stato della NOTIFICA a "FALLITA"
  E registra un log strutturato con livello "ERROR" contenente i dettagli dell'anomalia
```

```gherkin
SCENARIO: S05 - Logging anomalia con correlazione end-to-end
  GIVEN una sequenza di invio notifiche che termina in fallimento definitivo
  WHEN il sistema raggiunge lo stato FALLITA per un evento specifico
  THEN genera un log strutturato contenente timestamp, level "ERROR", message e correlationId
  E non attiva fallback alternativi come SMS
```

```gherkin
SCENARIO: S06 - Invio fallito su Email ma successo immediato su Slack (backoff zero)
  GIVEN una RICHIESTA che innesca un trigger dinamico
  WHEN il sistema tenta l'invio via EMAIL e riceve un errore temporaneo
  E la configurazione prevede un backoff di 0 minuti per questo caso specifico
  THEN tenta immediatamente l'invio tramite SlackChannelAdapter
  E aggiorna lo stato della NOTIFICA a "CONSEGNATA" se Slack risponde positivamente
```

```gherkin
SCENARIO: S07 - Prevenzione duplicazioni tramite pattern Inbox
  GIVEN un evento trigger pubblicato su RabbitMQ per una RICHIESTA esistente
  WHEN il consumer NotificationConsumer riceve lo stesso messaggio due volte consecutivamente
  THEN elabora l'evento solo la prima volta utilizzando il record NOTIFICA esistente
  E ignora il secondo messaggio evitando duplicazioni nella coda di elaborazione
```

```gherkin
SCENARIO: S08 - Gestione fallimento DB durante creazione record NOTIFICA
  GIVEN una RICHIESTA che innesca un trigger dinamico
  WHEN il sistema tenta di creare il record NOTIFICA ma il database non risponde
  THEN il sistema rollbacka immediatamente la transazione atomica
  E non scrive dati parziali nello stato di consegna
```

## Punti aperti

| Funzionalità coinvolta | Assunzione proposta DA CONFERMARE | Domanda aperta |
|---|---|---|
| F2: Gestione Backoff Multi-Canale e Timeout | Assunzione: Il timeout totale per la sequenza (Email + Slack) è strettamente limitato a 15 minuti come specificato nel requisito "Timeout di Consegna", anche se il backoff tra i due canali è configurato a 15 minuti. | La finestra temporale massima di 15 minuti si riferisce al tempo totale trascorso dall'inizio del primo tentativo fino alla chiusura dell'operazione, oppure è la somma dei tempi di attesa (es. 15 min per Email + 15 min per Slack = 30 min)? Il requisito "Timeout di Consegna" dice "finestra temporale massima... è di 15 minuti tra i tentativi su canali diversi", il che potrebbe implicare un limite stringente sul tempo totale o solo sull'intervallo. |
| F4: Persistenza e Idempotenza | Assunzione: Il pattern Inbox gestisce l'idempotenza basandosi esclusivamente sull'ID del messaggio RabbitMQ, senza considerare lo stato attuale della NOTIFICA nel DB (es. se è già FALLITA). | Se una NOTIFICA ha già stato "FALLITA" definitivamente, il sistema deve ancora tentare di elaborare un nuovo evento trigger per la stessa RICHIESTA? O l'evento viene ignorato perché il record esiste ma è in stato terminale? |
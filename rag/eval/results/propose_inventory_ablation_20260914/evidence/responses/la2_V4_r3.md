# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## Inventario delle funzionalità

| Funzionalità | Ancoraggio al Canvas o alla fonte | Casi previsti (nominale / negativo) | Riferimento agli scenari o al punto aperto |
|---|---|---|---|
| F1: Trigger Ibrido e Routing Dinamico | Sezione 1. Requirements (Trigger Ibrido, Configurazione Workflow Dinamica); Sezione 3. Approach (Pattern Strategy). | Nominale: Invio corretto a Dipendente/Responsabile su cambio stato.<br>Negativo: Destinatario non valido o pratica annullata. | S01, S02 |
| F2: Gestione Backoff Multi-Canale e Timeout | Sezione 1. Requirements (Resilienza e Backoff Multi-Canale, Timeout di Consegna); Sezione 3. Approach (Retry Logic). | Nominale: Email fallisce, Slack riesce dopo 15 min.<br>Negativo: Entrambi i canali falliscono entro il timeout. | S03, S04 |
| F3: Logging Anomalie e Dead Letter Queue | Sezione 1. Requirements (Logging dell'Anomalia); Sezione 3. Approach (Dead Letter Queue). | Nominale: Log strutturato `FALLITA` con contatore tentativi.<br>Negativo: Messaggio spostato in DLQ senza blocco pratica. | S05, S06 |
| F4: Trigger Statico Countdown | Sezione 1. Requirements (Trigger Ibrido - countdown temporale); Sezione 3. Approach (StaticTriggerJob). | Nominale: Job Quartz.NET rileva scadenza e pubblica evento.<br>Negativo: Scadenza non raggiunta o richiesta già chiusa. | S07, S08 |
| F5: Persistenza Transazionale e Idempotenza | Sezione 3. Approach (Transactional Outbox & Inbox Pattern). | Nominale: Record `NOTIFICA` creato atomicamente.<br>Negativo: Rollback transazione su fallimento DB. | S09, S10 |

---

## Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica su cambio stato a dipendente
  GIVEN una RICHIESTA in stato "Bozza" con countdown attivo
  AND un utente UTENTE designato come "DIPENDENTE" nella configurazione workflow
  WHEN lo stato della RICHIESTA cambia in "Revisato"
  THEN il sistema pubblica un evento su RabbitMQ per l'invio al DIPENDENTE
  E crea un record NOTIFICA con stato IN_CODA e tentativo_n = 1
```

```gherkin
SCENARIO: S02 - Invio negato su destinatario non valido
  GIVEN una RICHIESTA in stato "Revisato"
  AND la configurazione workflow indica di inviare a un UTENTE inesistente nel sistema
  WHEN il sistema tenta di creare il record NOTIFICA per l'invio
  THEN il sistema rollbacka la transazione atomicamente
  E registra un log strutturato con livello INFO indicando "Destinatario non trovato"
```

```gherkin
SCENARIO: S03 - Fallimento Email e successo Slack dopo backoff
  GIVEN una RICHIESTA che innesca un trigger dinamico
  AND il record NOTIFICA è stato creato con canale EMAIL e tentativo_n = 1
  WHEN l'adapter EmailChannelAdapter fallisce per timeout del provider SMTP
  THEN il sistema incrementa tentativo_n a 2, attende 15 minuti (backoff)
  E tenta l'invio tramite SlackChannelAdapter
```

```gherkin
SCENARIO: S04 - Fallimento definitivo su entrambi i canali
  GIVEN una RICHIESTA con trigger dinamico attivo
  AND il tentativo di invio via EMAIL fallisce definitivamente
  AND il tentativo successivo via SLACK fallisce anch'esso o si raggiunge il limite tentativi
  THEN il sistema aggiorna lo stato della NOTIFICA a FALLITA
  E incrementa il contatore tentativo_n fino al valore massimo (3)
```

```gherkin
SCENARIO: S05 - Logging strutturato di anomalia fallita
  GIVEN una NOTIFICA con stato definitivamente FALLITA dopo esaurimento tentativi
  WHEN il sistema conclude la sequenza di invio per quell'evento
  THEN genera un log strutturato JSON con campi timestamp, level (ERROR), message, correlationId
  E incrementa il contatore interno dei fallimenti nel record
```

```gherkin
SCENARIO: S06 - Gestione Dead Letter Queue senza blocco pratica
  GIVEN una NOTIFICA in stato FALLITA con tutti i canali esauriti
  AND il sistema rileva che non ci sono fallback alternativi (es. SMS) autorizzati
  WHEN la sequenza di invio termina per timeout o limite tentativi
  THEN il messaggio viene spostato nella Dead Letter Queue (DLQ)
  E lo stato della RICHIESTA sorgente rimane invariato (non bloccato)
```

```gherkin
SCENARIO: S07 - Innesco trigger statico da scadenza imminente
  GIVEN un job Quartz.NET StaticTriggerJob che esegue la scansione periodica
  AND una RICHIESTA con countdown <= X giorni rispetto alla data corrente
  WHEN il job rileva lo stato di scadenza imminente
  THEN pubblica un evento su RabbitMQ per la notifica "SCADENZA_IMMINENTE"
  E crea il record NOTIFICA associato all'evento statico
```

```gherkin
SCENARIO: S08 - Trigger statico ignorato su richiesta chiusa
  GIVEN una RICHIESTA con countdown attivo ma già in stato "Annullata"
  AND il job StaticTriggerJob esegue la scansione e rileva la scadenza
  WHEN il sistema valuta i destinatari per l'evento di scadenza
  THEN non pubblica alcun evento trigger per la notifica
  E non crea record NOTIFICA poiché la pratica è chiusa
```

```gherkin
SCENARIO: S09 - Creazione atomica del record Notifica
  GIVEN un evento trigger pubblicato su RabbitMQ (dinamico o statico)
  AND il sistema elabora l'evento nel consumer NotificationConsumer
  WHEN il sistema persiste il record NOTIFICA nel database
  THEN la scrittura avviene in transazione con l'evento di business
  E in caso di errore DB, la transazione rollbacka immediatamente
```

```gherkin
SCENARIO: S10 - Idempotenza tramite Inbox Pattern
  GIVEN un messaggio RabbitMQ per una notifica già elaborata precedentemente
  AND il consumer NotificationConsumer riceve lo stesso ID evento (correlationId)
  WHEN il sistema tenta di elaborare la notifica
  THEN verifica l'Inbox per evitare duplicazioni
  E ignora il messaggio se già elaborato, aggiornando solo metriche se necessario
```

## Punti aperti

| Funzionalità coinvolta | Assunzione proposta DA CONFERMARE | Domanda aperta |
|---|---|---|
| F2: Gestione Backoff Multi-Canale | Si assume che il backoff di 15 minuti sia applicato solo tra tentativi su canali *diversi* (Email -> Slack), non tra tentativi sullo stesso canale fallito. | Come gestire un fallimento ripetuto dello stesso canale (es. Email) prima di passare al successivo? Il sistema deve attendere sempre 15 min o provare immediatamente lo stesso canale fino a esaurimento tentativi totali? |
| F4: Trigger Statico Countdown | Si assume che il job Quartz.NET scansioni solo le richieste con stato attivo (non annullate). | Qual è la soglia esatta di "X giorni" per considerare una scadenza imminente? È configurabile o fisso nel sistema? |
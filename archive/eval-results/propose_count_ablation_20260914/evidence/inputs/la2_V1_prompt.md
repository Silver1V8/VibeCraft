
    Sei un Analista Software esperto in metodologie BDD (Behavior-Driven Development).
    Scrivi le specifiche (spec.md) di UNA SOLA feature: quella descritta dal REASONS Canvas
    qui sotto (etichetta: «la2»). Il Canvas è l'UNICA fonte di cosa la feature fa: l'etichetta serve
    solo a identificarla, non dedurne requisiti; e nulla di ciò che segue il Canvas può
    cambiarne il soggetto.

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


    Vincoli normativi dal Graph RAG. ATTENZIONE: NON sono l'argomento dello spec — l'argomento è la feature del Canvas, e basta. Servono come LENTE per trovarne i casi limite: da qui ricavi gli scenari negativi CHE LA FEATURE DEVE GESTIRE (tentativi non autorizzati su di essa, suoi casi di errore, invarianti dei safeguard che essa tocca) e i termini/codici esatti da citare. È VIETATO scrivere scenari su parti del sistema che questi documenti nominano ma che la feature non tocca: se uno scenario resta sensato dopo aver tolto la feature, non va scritto.
    --- 02_specs_normative/spec_notifications_2.4.md [ENFORCED, documento integrale] ---
---
id: "spec-notifications-v1.0"
title: "Specifica Normativa — Sistema di Notifiche"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-13"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_notifications_2.4.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-notifications-v1.0"
  scope: "Definizione dei requisiti per il sistema di notifiche asincrone, integrazione email e canali Slack"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-v1.2"
    - type: "VINCOLA"
      target: "entity::NOTIFICA"
    - type: "VINCOLA"
      target: "entity::RICHIESTA"
    - type: "VINCOLA"
      target: "entity::UTENTE"
tags:
  - requirements
  - open-spec
  - notifications
  - slack-integration
  - email-notifications
---

# Specifica Normativa — Sistema di Notifiche
*VibeCraft — Sistema di Gestione Eventi Aziendali*

---

## 1. Obiettivo e Architettura del Sistema di Notifica

La presente specifica definisce i requisiti funzionali, le regole di instradamento e i vincoli di sicurezza del modulo di notifica di VibeCraft. Lo scopo di questo sistema è garantire che ogni transizione critica del ciclo di vita di una `` `RICHIESTA` `` o di un `` `EVENTO` `` sia notificata in tempo reale e in modo asincrono ai soggetti interessati (dipendenti e manager), utilizzando canali differenziati (e-mail interne e canali di messaggistica Slack) per massimizzare la reattività operativa del team.

Ogni singola occorrenza di invio deve produrre un record persistente nell'entità `` `NOTIFICA` `` per finalità storiche, oltre a essere debitamente tracciata all'interno dell' `` `AUDIT_LOG` ``.

---

## 2. Regole di Dispacciamento ed Integrazione Canali

### [REGOLA-NOTIF-02] Instradamento asincrono su canali Slack per i Manager
- **Descrizione:** Al momento della sottomissione di una nuova `` `RICHIESTA` `` (passaggio a 'IN_ATTESA_APPROVAZIONE'), il sistema deve inviare una notifica immediata e asincrona sul canale Slack aziendale associato al dipartimento del manager competente. Il messaggio Slack deve contenere il link diretto al pannello di approvazione e non esporre dati sensibili non necessari.
- **Effetto in caso di violazione (Failure Mode):** Il manager non riceve tempestivamente la segnalazione, allungando i tempi di lavorazione ed esponendo le richieste alla scadenza dei termini dell' `` `EVENTO` ``.
- **Entità Target:** `` `NOTIFICA` ``, `` `RICHIESTA` ``

### [REGOLA-NOTIF-03] Invio e-mail transazionali ai dipendenti
- **Descrizione:** Ogni variazione di stato di una `` `RICHIESTA` `` operata da un manager o da un amministratore (approvazione, rifiuto o annullamento logico) deve innescare l'invio sincrono di una e-mail transazionale all'indirizzo e-mail aziendale del dipendente `` `UTENTE` `` destinatario. L'e-mail deve riportare chiaramente lo stato aggiornato e l'eventuale nota motivazionale inserita dall'approvatore.
- **Effetto in caso di violazione (Failure Mode):** Mancata consapevolezza da parte dell'utente dello stato dell'iscrizione, con rischio di assenze ingiustificate o sovrapposizioni.
- **Entità Target:** `` `NOTIFICA` ``, `` `UTENTE` ``

---

## 3. Gestione Code e Tolleranza ai Guasti

### [REGOLA-VAL-01] Accodamento e gestione dei fallimenti di rete
- **Descrizione:** Il sistema di invio delle notifiche deve operare tramite una coda asincrona (Message Queue) esterna al thread principale della transazione di business. In caso di fallimento della chiamata API di Slack o del server SMTP di posta, il modulo deve tentare un massimo di 3 reinvii automatici distanziati da un backoff esponenziale, registrando infine lo stato di fallimento nell'entità `` `NOTIFICA` ``.
- **Effetto in caso di violazione (Failure Mode):** Il blocco o rallentamento dei servizi di notifica esterni si ripercuote sulla latenza percepita dall'utente a schermo, bloccando l'interfaccia.
- **Entità Target:** `` `NOTIFICA` ``

### [REGOLA-INT-01] Consistenza e persistenza dello stato di invio
- **Descrizione:** Ogni tentativo di invio di una e-mail o di un messaggio Slack deve creare un record persistente nell'entità `` `NOTIFICA` `` con stato impostato inizialmente su 'PENDING' e aggiornato successivamente a 'SENT' o 'FAILED'. Il payload originale e gli errori riscontrati devono essere storicizzati.
- **Effetto in caso di violazione (Failure Mode):** Impossibilità di verificare se una determinata comunicazione sia mai stata trasmessa o ricevuta in caso di controversie aziendali.
- **Entità Target:** `` `NOTIFICA` ``

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Invio asincrono delle notifiche e tolleranza ai guasti

```gherkin
Scenario: Invio notifica Slack per nuova richiesta in attesa
  Dato un record RICHIESTA appena sottomesso da un dipendente in stato 'IN_ATTESA_APPROVAZIONE'
  Quando il modulo di notifica intercetta l'evento di sottomissione
  Allora crea un record NOTIFICA in stato 'PENDING' nel database
  E accoda l'operazione di invio del messaggio Slack per il dipartimento associato
  E trasmette il messaggio formattato sul webhook di Slack
  E aggiorna lo stato della NOTIFICA in 'SENT' scrivendo l'operazione nell' `AUDIT_LOG`
```

```gherkin
Scenario: Gestione e tracciamento del fallimento dell'invio e-mail
  Dato un manager che ha appena approvato una RICHIESTA sul pannello di controllo
  Quando il server di posta SMTP aziendale risulta offline al momento dell'invio dell'e-mail
  Allora l'accodatore esegue i 3 tentativi di reinvio pianificati dalla [REGOLA-VAL-01]
  E al fallimento definitivo imposta lo stato della NOTIFICA su 'FAILED'
  E inserisce un record di errore dettagliato nel database delle notifiche
  E genera un log di anomalia di severità 'WARNING' all'interno dell' `AUDIT_LOG`
```
```

--- 01_architecture_norms/observability_standards.md [ENFORCED, documento integrale] ---
---
id: "observability-standards-v1.0"
title: "Normativa — Osservabilità: Log, Metriche, Tracing e Alerting"
project: "cross-project"
scope: "cross-project"
version: "1.0.0"
date: "2026-07-22"
status: "ENFORCED"
classification: "NORMS"
path: "docs/01_architecture_norms/observability_standards.md"
authority: 0.85
changelog:
  - version: "1.0.0"
    date: "2026-07-22"
    changes:
      - "Creato per colmare un riferimento pendente: [SAFEGUARD-SEC-04] impone un sanitizer dei log e lo scrubbing della telemetria, [SAFEGUARD-AUD-02] impone un correlation ID, ma nessun documento normava la pipeline di osservabilità"
reuse:
  parameters:
    - "<<LIVELLI_LOG>>: livelli ammessi e loro semantica"
    - "<<CAMPI_PII>>: campi da redigere prima di ogni uscita (allineato ai safeguard)"
    - "<<ENDPOINT_SALUTE>>: rotta di health check"
    - "<<CANALE_ALERT>>: destinazione degli alert operativi"
    - "<<RETENTION_LOG>>: periodo di conservazione dei log"
  inherited_parameters:
    - "<<CAMPI_PII>>, <<TABELLA_AUDIT>> — definiti in safeguards_security.md"
  instantiation: "Copiare il file, compilare la Sezione 0. I parametri ereditati si compilano una sola volta, nel contratto di istanziazione dei safeguard: <<CAMPI_PII>> deve restare un unico elenco, perché una divergenza fra i due documenti è un buco di privacy."
graph_rag:
  node_type: "ARCHITECTURE"
  node_id: "observability-standards-v1.0"
  databases: ["Qdrant", "NetworkX"]
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-baseline-v2.0"
    - type: "CONNESSA_A"
      target: "api-error-contract-v1.0"
tags:
  - norms
  - observability
  - logging
  - metrics
  - tracing
  - alerting
  - pii
  - cross-project
  - baseline
---

# Normativa — Osservabilità: Log, Metriche, Tracing e Alerting
## Baseline Cross-Progetto

---

## Sezione 0 — Contratto di Istanziazione

| Parametro | Significato | Valore nel progetto |
|---|---|---|
| `<<LIVELLI_LOG>>` | Livelli ammessi | `DEBUG, INFO, WARNING, ERROR, CRITICAL` *(default)* |
| `<<CAMPI_PII>>` | Campi da redigere prima di ogni uscita | *(da compilare — deve coincidere con i safeguard)* |
| `<<ENDPOINT_SALUTE>>` | Rotta di health check | `/health` *(default)* |
| `<<CANALE_ALERT>>` | Destinazione degli alert operativi | *(da compilare)* |
| `<<RETENTION_LOG>>` | Conservazione dei log | *(da compilare)* |

> **Perché questo documento esiste:** `[SAFEGUARD-SEC-04]` impone un sanitizer sui log e lo scrubbing della telemetria, `[SAFEGUARD-AUD-02]` impone un `correlationId` su ogni record di audit, `[SAFEGUARD-SEC-01]` impone il logging infrastrutturale dei tentativi di accesso rifiutati. Nessun documento definiva la pipeline che deve realizzarli.

---

## 1. Distinzione Fondamentale: Audit Log ≠ Log Applicativo

Sono due sistemi distinti, con requisiti opposti. Confonderli è l'errore architetturale più costoso di quest'area.

| | Audit log | Log applicativo |
|---|---|---|
| Scopo | Prova di **cosa è successo al dato** | Diagnosi di **come si comporta il software** |
| Destinatario | Auditor, compliance, indagine | Sviluppatore, on-call |
| Persistenza | Tabella transazionale append-only | File o collector, ruotati |
| Scrittura | Sincrona, nella transazione di business | Asincrona, mai bloccante |
| Perdita ammessa | **Mai** — se fallisce, rollback | Tollerata sotto pressione |
| Contenuto | Valori prima/dopo, attore, azione | Eventi tecnici, timing, errori |
| Normato da | `[SAFEGUARD-AUD-01]`, `[SAFEGUARD-AUD-02]` | Questo documento |

### [REGOLA-OBS-01] Nessuna sostituzione fra i due sistemi
- **Descrizione:** Il log applicativo non può fungere da audit trail, e l'audit trail non può essere usato per la diagnostica applicativa. Un evento di dominio tracciato solo nel log applicativo è una **perdita di auditability**.
- **Effetto in caso di violazione (Failure Mode):** Impossibilità di ricostruire chi ha modificato cosa in sede di verifica; oppure audit trail gonfiato di rumore diagnostico e illeggibile.
- **Entità Target:** `<<TABELLA_AUDIT>>`

---

## 2. Log Strutturati e Correlazione

### [REGOLA-OBS-02] Log strutturati, mai stringhe concatenate
- **Descrizione:** Ogni riga di log è un oggetto strutturato con campi tipizzati, non una stringa interpolata. Campi minimi obbligatori: `timestamp` (UTC, ISO 8601), `level`, `message`, `correlationId`, `service`, `environment`.
- **Effetto in caso di violazione (Failure Mode):** Log non interrogabili per campo; ogni analisi richiede espressioni regolari fragili sul testo.
- **Entità Target:** Nessuna.

### [REGOLA-OBS-03] Correlation ID propagato end-to-end
- **Descrizione:** Ogni richiesta in ingresso riceve un `correlationId` (o eredita quello del chiamante) che accompagna **ogni** log, span di tracing, messaggio su coda e record di audit generati nel suo contesto. Il campo compare anche nelle risposte di errore, per `[REGOLA-API-01]`.
- **Effetto in caso di violazione (Failure Mode):** Impossibile ricostruire il percorso di una singola richiesta attraverso i moduli; la diagnosi di un incidente diventa ricerca a tentoni per timestamp.
- **Entità Target:** Nessuna.

### [REGOLA-OBS-04] Semantica vincolante dei livelli
- **Descrizione:** I livelli hanno un significato operativo, non stilistico:

| Livello | Significato | Richiede intervento |
|---|---|---|
| `DEBUG` | Dettaglio diagnostico, disattivo in produzione | No |
| `INFO` | Evento atteso del ciclo di vita | No |
| `WARNING` | Anomalia gestita, degrado tollerato | Da osservare |
| `ERROR` | Operazione fallita, impatto sull'utente | Sì, non urgente |
| `CRITICAL` | Perdita di servizio o di integrità dei dati | Sì, immediato |

Un errore di dominio previsto (validazione fallita, conflitto di stato) è `INFO` o `WARNING`, **non** `ERROR`: l'`ERROR` è riservato a ciò che non doveva accadere.
- **Effetto in caso di violazione (Failure Mode):** Rumore che rende gli alert inutilizzabili; l'on-call smette di guardarli e l'incidente vero passa inosservato.
- **Entità Target:** Nessuna.

### [REGOLA-OBS-05] Livello configurabile senza rebuild
- **Descrizione:** Il livello minimo di log è governato da variabile d'ambiente e modificabile senza ricompilare né rideployare l'applicazione.
- **Effetto in caso di violazione (Failure Mode):** Diagnosi di un incidente in corso che richiede un deploy per alzare la verbosità.
- **Entità Target:** Nessuna.

---

## 3. Confine di Privacy

### [REGOLA-OBS-06] Redazione PII prima di ogni uscita
- **Descrizione:** Il sanitizer che redige `<<CAMPI_PII>>` è installato **nel logger stesso**, non invocato dai singoli call site. Un sanitizer che dipende dalla disciplina di chi scrive la riga di log fallisce alla prima dimenticanza. Applicazione diretta di `[SAFEGUARD-SEC-04]`.
- **Effetto in caso di violazione (Failure Mode):** PII in chiaro nei file di log, nei collector centralizzati e nelle tracce inviate agli APM esterni.
- **Entità Target:** `<<CAMPI_PII>>`

### [REGOLA-OBS-07] Nessun payload completo nei log
- **Descrizione:** È vietato loggare corpi di richiesta o risposta interi, anche in `DEBUG`. Si logga l'identificativo della risorsa e i campi non sensibili necessari alla diagnosi.
- **Effetto in caso di violazione (Failure Mode):** Un `DEBUG` lasciato attivo in produzione diventa un data leak retroattivo su tutta la finestra di retention.
- **Entità Target:** Nessuna.

### [REGOLA-OBS-08] Retention dichiarata e applicata
- **Descrizione:** I log hanno una scadenza esplicita `<<RETENTION_LOG>>`, applicata automaticamente. Conservare log con dati personali oltre la necessità operativa è una violazione di minimizzazione.
- **Effetto in caso di violazione (Failure Mode):** Accumulo indefinito di dati personali senza base di conservazione.
- **Entità Target:** Nessuna.

---

## 4. Metriche, Salute e Alerting

### [REGOLA-OBS-09] Health check con dipendenze verificate
- **Descrizione:** `<<ENDPOINT_SALUTE>>` deve distinguere **liveness** (il processo è vivo) da **readiness** (le dipendenze critiche — database, broker, storage — rispondono). Un health check che restituisce sempre `200` finché il processo esiste non è un health check.
- **Effetto in caso di violazione (Failure Mode):** L'orchestratore instrada traffico verso istanze incapaci di servirlo.
- **Entità Target:** Nessuna.

### [REGOLA-OBS-10] Le quattro metriche minime
- **Descrizione:** Ogni servizio espone almeno: **latenza** (con percentili, non media), **traffico**, **tasso di errore**, **saturazione** delle risorse. I percentili sono obbligatori: la media nasconde sistematicamente la coda che gli utenti percepiscono.
- **Effetto in caso di violazione (Failure Mode):** Degrado invisibile fino al guasto conclamato.
- **Entità Target:** Nessuna.

### [REGOLA-OBS-11] Alert azionabili e con destinatario
- **Descrizione:** Ogni alert inviato su `<<CANALE_ALERT>>` deve dichiarare: cosa è successo, quale impatto ha sull'utente, quale azione ci si aspetta. Un alert senza azione attesa va rimosso, non silenziato. Gli alert su soglie transitorie richiedono una finestra di persistenza prima dello scatto.
- **Effetto in caso di violazione (Failure Mode):** Affaticamento da allarme: il segnale vero si perde nel rumore di fondo.
- **Entità Target:** Nessuna.

### [REGOLA-OBS-12] Scrubbing obbligatorio sugli exporter remoti
- **Descrizione:** Ogni integrazione con APM o telemetria remota va configurata in modalità di scrubbing **prima** della prima trasmissione, non dopo il primo incidente. Le stack trace non devono includere valori di variabili contenenti PII.
- **Effetto in caso di violazione (Failure Mode):** Trasmissione di dati personali a un responsabile del trattamento non autorizzato; violazione di `[SAFEGUARD-SEC-04]`.
- **Entità Target:** `<<CAMPI_PII>>`

---

## 5. Scenari Comportamentali BDD (Gherkin)

```gherkin
Scenario: Correlazione end-to-end di una richiesta fallita
  Dato una richiesta in ingresso senza correlationId fornito dal chiamante
  Quando il middleware di osservabilità la elabora
  Allora genera un correlationId e lo propaga a log, tracing e audit
  E in caso di errore lo include nella risposta per [REGOLA-API-01]
  E l'intero percorso della richiesta è ricostruibile da quel solo identificatore
```

```gherkin
Scenario: Redazione automatica di un campo PII
  Dato un logger configurato col sanitizer dei campi PII
  E un call site che passa per errore un oggetto contenente un campo personale
  Quando la riga di log viene scritta
  Allora il valore del campo appare come [REDACTED] per [REGOLA-OBS-06]
  E nessuna configurazione del singolo call site è stata necessaria
```

```gherkin
Scenario: Readiness che riflette una dipendenza degradata
  Dato un servizio il cui database non risponde
  Quando l'orchestratore interroga l'endpoint di salute
  Allora la liveness resta positiva perché il processo è vivo
  E la readiness è negativa per [REGOLA-OBS-09]
  E l'istanza viene esclusa dal bilanciamento senza essere riavviata
```

---

## 6. Riepilogo delle Regole

| ID | Vincolo operativo core |
|---|---|
| `[REGOLA-OBS-01]` | Audit log e log applicativo restano sistemi distinti. |
| `[REGOLA-OBS-02]` | Log strutturati con campi tipizzati, mai stringhe interpolate. |
| `[REGOLA-OBS-03]` | `correlationId` propagato su log, tracing, code e audit. |
| `[REGOLA-OBS-04]` | I livelli hanno semantica operativa; `ERROR` solo per l'imprevisto. |
| `[REGOLA-OBS-05]` | Verbosità modificabile senza rideploy. |
| `[REGOLA-OBS-06]` | Sanitizer PII nel logger, non nei call site. |
| `[REGOLA-OBS-07]` | Mai payload completi nei log, nemmeno in `DEBUG`. |
| `[REGOLA-OBS-08]` | Retention dichiarata e applicata automaticamente. |
| `[REGOLA-OBS-09]` | Health check che distingue liveness da readiness. |
| `[REGOLA-OBS-10]` | Latenza a percentili, traffico, errori, saturazione. |
| `[REGOLA-OBS-11]` | Alert azionabili; se non c'è azione attesa, va rimosso. |
| `[REGOLA-OBS-12]` | Scrubbing configurato prima della prima trasmissione remota. |

---

*Fine del documento — baseline cross-progetto v1.0.0*


    Vincolo di ambito: questa feature è ESCLUSIVAMENTE 'logicAgent'. Gli scenari devono descrivere comportamento osservabile in questo ambito; non scrivere scenari su parti del sistema fuori da esso.

    Basandoti sulle regole e sui requisiti del Canvas (e sui vincoli normativi qui sopra, se presenti),
    scrivi il file delle specifiche tecniche (spec.md).

    Ogni scenario deve avere per soggetto la feature del Canvas e descriverne un COMPORTAMENTO
    osservabile. Non scrivere scenari che verificano lo stack, le librerie o gli strumenti in sé.
    Niente scenari duplicati: se due differiscono solo nella formulazione, tienine uno.
    Per ogni funzionalità descritta dal Canvas scrivi da un minimo di 2 a un massimo di 4
    scenari, includendo almeno un caso nominale e uno negativo o di errore. Non c'è un tetto
    complessivo per lo spec: il totale è la somma degli scenari delle singole funzionalità.
    Se una funzionalità richiede più di 4 scenari, non suddividere il Canvas: dichiara la
    copertura mancante nella sezione "Punti aperti", senza presentarla come già soddisfatta.
    Non inventare requisiti per raggiungere il minimo: se un'ambiguità impedisce di formulare
    un caso verificabile, dichiara anche quel caso mancante nei punti aperti.

    Non inventare funzionalità non presenti nel Canvas o nei vincoli normativi. Se uno scenario
    nomina una tecnologia o mostra codice, usa ESCLUSIVAMENTE le tecnologie già citate nel
    Canvas: qualsiasi altro linguaggio, libreria o strumento è VIETATO.

    VERIFICA FINALE sul contenuto — rileggi il Canvas in cima e controlla che ogni scenario
    discenda da un suo requisito: i vincoli normativi descrivono ANCHE altri moduli del sistema
    (cataloghi di funzionalità, pannelli, console) che NON sono questa feature, e non vanno
    trasformati in scenari. Se uno scenario non è riconducibile a una frase del Canvas, toglilo.

    Rispondi esclusivamente con il contenuto del file Markdown, senza preamboli né commenti
    prima o dopo. Scrivi SOLO la versione definitiva, senza auto-correzioni o dubbi inline
    nei passi degli scenari. Se un punto è ambiguo, non risolverlo d'autorità: aggiungilo a una
    sezione "Punti aperti" del documento, FUORI dai blocchi gherkin. Per ciascun punto indica
    la funzionalità coinvolta, l'assunzione proposta DA CONFERMARE e una domanda aperta
    esplicita. L'assunzione non è un requisito approvato: non usarla per fissare l'esito di
    uno scenario. Indica quali comportamenti restano senza copertura fino alla risposta.
    Per la copertura che eccede i 4 scenari per quella funzionalità, elenca i casi mancanti e la domanda da risolvere;
    se non occorre un'assunzione, scrivi "Assunzione: nessuna; copertura da confermare".
    Non dichiarare completa la copertura in presenza di casi mancanti o punti irrisolti.

    ==========================================================================
    FORMATO DEGLI SCENARI — obbligatorio, sempre, senza varianti: vale per ogni
    scenario di ogni spec, qualunque sia la feature. È la parte più importante
    di queste istruzioni: uno spec fuori formato viene rifiutato in automatico.
    ==========================================================================

    Copia la forma dell'esempio qui sotto, cambiando solo il testo:

```gherkin
SCENARIO: S01 - Recupero fascicolo esistente
  GIVEN un utente autenticato con profilo "Operatore"
  AND un fascicolo con protocollo "2026/00123" presente in archivio
  WHEN richiede il dettaglio del fascicolo
  THEN il sistema restituisce i metadati completi del fascicolo
```

```gherkin
SCENARIO: S02 - Recupero negato su fascicolo inesistente
  GIVEN un utente autenticato con profilo "Operatore"
  WHEN richiede il dettaglio del fascicolo con protocollo "2026/99999"
  THEN il sistema rifiuta la richiesta con errore "NOT_FOUND"
  AND non restituisce alcun metadato
```

    GUARDA COME FINISCE IL PRIMO SCENARIO E COME COMINCIA IL SECONDO. Dopo il THEN di S01 c'è
    una riga di tre backtick che CHIUDE il blocco; poi una riga vuota; poi una nuova riga
    ```gherkin che APRE il blocco di S02. Questa è la regola che si sbaglia più spesso ed è
    quella che da sola invalida lo spec:

    OGNI SCENARIO HA IL SUO BLOCCO. Cinque scenari sono cinque blocchi: cinque righe di
    apertura e cinque righe di chiusura. Non scrivere MAI due `SCENARIO:` dentro lo stesso
    blocco. Una riga ```gherkin non chiude niente — apre: usarla per separare due scenari
    lascia tutto dentro un blocco solo, ed è sbagliato.

    L'errore da NON fare — due scenari lasciati dentro un blocco solo, separati da una riga
    vuota invece che dalla chiusura e dalla riapertura del blocco:

        ```gherkin
        SCENARIO: S01 - Primo caso
          GIVEN ...
          WHEN ...
          THEN ...
                                  <- qui manca la riga di chiusura del blocco di S01
        SCENARIO: S02 - Secondo caso      <- e la riga di apertura del blocco di S02
          GIVEN ...
        ```

    OGNI SCENARIO HA TRE PASSI OBBLIGATORI: GIVEN, poi WHEN, poi THEN. Il WHEN non si salta
    mai: è l'azione che scatena il comportamento, e senza di esso lo scenario non è
    verificabile. Un blocco con GIVEN e THEN ma senza WHEN è invalido, così come un blocco che
    si ferma prima del THEN. Se non sai come completarlo, togli lo scenario invece di
    consegnarlo a metà.

    Le altre regole della forma, tutte visibili nell'esempio:
    - KEYWORD IN INGLESE MAIUSCOLO: GIVEN, WHEN, THEN, AND. Mai `Dato`, `Quando`, `Allora`,
      `E`: non sono keyword e rendono lo scenario invalido.
    - PRIMA RIGA del blocco: `SCENARIO: S<nn> - <titolo breve>`, senza rientro, numerata in
      ordine dal primo all'ultimo scenario dello spec (S01, S02, S03...) senza salti.
    - UN SOLO GIVEN, UN SOLO WHEN, UN SOLO THEN per scenario, in quest'ordine. Ogni condizione
      o asserzione in più è un AND: `GIVEN → AND… → WHEN → AND… → THEN → AND…`.
    - PASSI indentati di 2 spazi, uno per riga, una sola asserzione ciascuno, BREVI: una riga
      di venti-venticinque parole al massimo, come quelle dell'esempio. Testo in italiano,
      indicativo presente, terza persona; valori letterali fra virgolette doppie; niente nomi
      di classi, tabelle o endpoint se non sono un requisito funzionale.
    - TITOLO dello scenario breve: poche parole, non una frase intera.
    - DENTRO IL BLOCCO nient'altro che la riga SCENARIO e i passi: nessun commento, nessun
      testo libero, nessuna riga di prosa.

    Prima di rispondere rileggi ciò che hai scritto e conta: le righe di backtick sono il
    doppio degli scenari? Ogni blocco contiene un GIVEN, un WHEN e un THEN? Ogni passo comincia
    con GIVEN, WHEN, THEN o AND in maiuscolo? Se una delle tre risposte è no, riscrivi lo spec:
    non consegnarlo così.

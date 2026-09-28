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

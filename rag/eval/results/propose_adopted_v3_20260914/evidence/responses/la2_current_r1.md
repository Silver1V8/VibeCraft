# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Scopo e Ambito

Il presente documento definisce il comportamento osservabile della feature **LA2** all'interno del modulo `logic-agent`. La feature gestisce l'invio asincrono di notifiche relative a eventi dinamici (cambi stato) e statici (scadenze), garantendo resilienza tramite retry multi-canale (Email, Slack) e logging strutturato.

L'architettura si basa su un worker service .NET 10 che consuma eventi da RabbitMQ (tramite MassTransit) e utilizza Quartz.NET per i trigger periodici. Il sistema deve rispettare rigorosamente le norme di osservabilità (`[REGOLA-OBS-xx]`) e sicurezza (`[SAFEGUARD-SEC-xx]`).

## 2. Entità e Dati

La feature opera sulle seguenti entità:
*   **RICHIESTA**: Sorgente dell'evento (ID, stato corrente).
*   **UTENTE**: Destinatario della notifica (ruolo: `DIPENDENTE` o `RESPONSABILE`).
*   **NOTIFICA**: Record di persistenza dello stato di consegna (`IN_CODA`, `CONSEGNATA`, `FALLITA`) e del numero di tentativo (`tentativo_n`).

## 3. Scenari Comportamentali BDD

### Funzionalità: Innesco Trigger Dinamico (Cambiamento Stato)

```gherkin
SCENARIO: S01 - Invio notifica su cambio stato a dipendente
  GIVEN una RICHIESTA in stato "Bozza"
  AND un utente con ruolo "DIPENDENTE" associato alla RICHIESTA
  WHEN lo stato della RICHIESTA cambia in "Revisato"
  THEN il sistema crea un record NOTIFICA con stato "IN_CODA" e tentativo_n = 1
  E accoda l'evento di invio al canale EMAIL
```

```gherkin
SCENARIO: S02 - Invio notifica su cambio stato a responsabile
  GIVEN una RICHIESTA in stato "Bozza"
  AND un utente con ruolo "RESPONSABILE" associato alla RICHIESTA
  WHEN lo stato della RICHIESTA cambia in "Approvato"
  THEN il sistema crea un record NOTIFICA con stato "IN_CODA" e tentativo_n = 1
  E accoda l'evento di invio al canale EMAIL
```

```gherkin
SCENARIO: S03 - Invio notifica su cambio stato a entrambi i ruoli
  GIVEN una RICHIESTA in stato "Bozza"
  AND un utente con ruolo "DIPENDENTE" associato alla RICHIESTA
  AND un utente con ruolo "RESPONSABILE" associato alla RICHIESTA
  WHEN lo stato della RICHIESTA cambia in "In Attesa Approvazione"
  THEN il sistema crea due record NOTIFICA distinti, uno per ogni ruolo
  E accoda l'evento di invio al canale EMAIL per entrambi i destinatari
```

### Funzionalità: Innesco Trigger Statico (Scadenza Imminente)

```gherkin
SCENARIO: S04 - Notifica scadenza imminente attivata da job periodico
  GIVEN una RICHIESTA con countdown temporale <= X giorni
  AND il job StaticTriggerJob è in esecuzione
  WHEN il job rileva che la scadenza è prossima
  THEN il sistema pubblica un evento trigger per "SCADENZA_IMMINENTE"
  E crea un record NOTIFICA con stato "IN_CODA" e tentativo_n = 1
```

### Funzionalità: Gestione Fallimenti e Backoff Multi-Canale

```gherkin
SCENARIO: S05 - Tentativo fallito su Email, retry su Slack
  GIVEN una RICHIESTA che innesca una notifica EMAIL
  WHEN il canale EMAIL fallisce nel primo tentativo (tentativo_n = 1)
  THEN il sistema incrementa tentativo_n a 2
  E attende un periodo di backoff configurato (15 minuti)
  E tenta l'invio tramite il canale SLACK
```

```gherkin
SCENARIO: S06 - Fallimento definitivo su entrambi i canali
  GIVEN una RICHIESTA che innesca una notifica EMAIL
  AND il canale EMAIL fallisce nel primo tentativo
  AND il canale SLACK fallisce nel secondo tentativo (tentativo_n = 2)
  WHEN si raggiunge il limite massimo dei tentativi (3)
  THEN il sistema aggiorna lo stato della NOTIFICA a "FALLITA"
  E genera un log strutturato con livello "ERROR" e stato "FALLITA"
```

```gherkin
SCENARIO: S07 - Consegna riuscita su Slack dopo fallimento Email
  GIVEN una RICHIESTA che innesca una notifica EMAIL
  WHEN il canale EMAIL fallisce nel primo tentativo (tentativo_n = 1)
  AND il canale SLACK riesce nel secondo tentativo (tentativo_n = 2)
  THEN il sistema aggiorna lo stato della NOTIFICA a "CONSEGNATA"
  E ferma la sequenza di retry per quell'evento
```

### Funzionalità: Logging e Correlazione

```gherkin
SCENARIO: S08 - Log strutturato su fallimento definitivo
  GIVEN una notifica che ha raggiunto lo stato "FALLITA" dopo tutti i tentativi
  WHEN il sistema registra l'anomalia
  THEN genera un log JSON con campi obbligatori: timestamp, level="ERROR", message, correlationId
  E incrementa il contatore dei tentativi fino al limite massimo (3)
```

## 4. Punti aperti

```json
{"open_points":[{"id":"OP-001","functionality":"Innesco Trigger Statico","original_question":"Qual è il valore soglia esatto del countdown per attivare la notifica di scadenza imminente?", "question":"Il job StaticTriggerJob utilizza un valore fisso (es. 3 giorni) o uno configurabile via workflow?", "assumption":null,"uncovered_scenarios":["S04"], "reason":"missing_coverage","research":{"status":"not_started","new_evidence":[],"verification":"agent_reported"}}]
}
```
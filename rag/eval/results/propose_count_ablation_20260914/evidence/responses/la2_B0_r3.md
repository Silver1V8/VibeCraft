# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Descrizione della Feature
La feature **LA2** implementa un sistema di notifica asincrono resiliente per il dominio delle pratiche (`RICHIESTA`). Il sistema gestisce trigger ibridi (dinamici su cambiamento stato e statici su countdown), determina i destinatari tramite strategia di routing configurabile, ed esegue tentativi multipli su canali alternati (Email, Slack) con backoff temporale. In caso di fallimento definitivo dopo l'esaurimento dei tentativi consentiti, il sistema registra l'anomalia senza attivare fallback non autorizzati.

## 2. Entità e Dati
- **RICHIESTA**: Sorgente dell'evento. Include `id`, `stato` (es. "Bozza", "Revisato") e metadati per il countdown temporale.
- **NOTIFICA**: Record di persistenza con attributi: `richiesta_id`, `utente_destinatario_id` (FK a `UTENTE`), `canale` (`EMAIL`, `SLACK`), `stato_consegna` (`IN_CODA`, `CONSEGNATA`, `FALLITA`), `tentativo_n`.
- **UTENTE**: Destinatario della notifica. Include `id` e indirizzo email associato.

## 3. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica Email su trigger dinamico riuscito
  GIVEN una RICHIESTA in stato "Revisato" che attiva un trigger dinamico
  AND il sistema identifica come destinatario valido l'utente dipendente tramite strategia di routing
  WHEN il consumer elabora l'evento e tenta l'invio via canale EMAIL
  THEN il sistema aggiorna lo stato della NOTIFICA a "CONSEGNATA"
  AND incrementa il contatore dei tentativi a 1
  AND registra un log di livello INFO con messaggio di consegna avvenuta
```

```gherkin
SCENARIO: S02 - Gestione fallimento Email e backoff verso Slack
  GIVEN una RICHIESTA che innesca una notifica per scadenza imminente
  WHEN il sistema tenta l'invio via canale EMAIL ma riceve un errore di delivery dal provider SMTP
  THEN il sistema incrementa il contatore dei tentativi a 1
  AND imposta lo stato della NOTIFICA a "IN_CODA"
  AND programma un nuovo tentativo per il canale SLACK dopo un backoff di 15 minuti
```

```gherkin
SCENARIO: S03 - Fallimento definitivo e chiusura sequenza
  GIVEN una RICHIESTA che ha già subito due tentativi falliti (Email e Slack)
  WHEN il terzo tentativo via canale SLACK fallisce definitivamente per timeout o errore API
  THEN il sistema aggiorna lo stato della NOTIFICA a "FALLITA"
  AND incrementa il contatore dei tentativi a 3
  AND registra un log strutturato di livello ERROR con dettaglio dell'anomalia e non attiva fallback alternativi
```

```gherkin
SCENARIO: S04 - Innesco trigger statico da job periodico
  GIVEN una RICHIESTA in attesa con countdown temporale inferiore alla soglia configurata
  WHEN il job StaticTriggerJob esegue la scansione periodica delle scadenze imminenti
  THEN il sistema pubblica un evento asincrono su RabbitMQ per attivare la notifica "SCADENZA_IMMINENTE"
  AND istanzia lo Strategy appropriato per determinare i destinatari senza hard-coding dei ruoli
```

## 4. Punti Aperti

| Funzionalità coinvolta | Assunzione proposta DA CONFERMARE | Domanda aperta |
|---|---|---|
| Gestione Backoff Multi-Canale | Il backoff di 15 minuti si applica solo al passaggio tra canali diversi (Email -> Slack) o anche dopo il fallimento dello stesso canale? | Come gestire la finestra temporale massima di 15 minuti se un canale è lento ma non fallisce definitivamente entro quel tempo? |
| Logging Anomalia | Il log strutturato per lo stato FALLITA deve includere l'intero stack trace dell'errore o solo il codice errore generico? | Qual è la soglia esatta di "limite massimo dei tentativi" se il sistema rileva un errore transitorio ripetuto più volte prima del timeout totale? |
| Correlazione End-to-End | Il campo `correlationId` viene generato al momento della ricezione dell'evento RabbitMQ o ereditato dal chiamante esterno? | Come comportarsi se l'evento trigger arriva senza un `correlationId` valido nel payload iniziale? |
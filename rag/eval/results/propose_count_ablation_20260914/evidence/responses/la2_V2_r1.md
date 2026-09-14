# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Descrizione della Feature

La feature **LA2** implementa il sistema di gestione asincrona delle notifiche per le pratiche (`RICHIESTA`). Il sistema monitora sia i cambiamenti dinamici di stato che gli eventi temporali statici (scadenze). Utilizza un'architettura basata su agenti logici (`Logic Agent`) con pattern Strategy e Adapter per gestire l'instradamento ai destinatari (`UTENTE`) tramite canali multipli (`EMAIL`, `SLACK`). La feature garantisce la resilienza attraverso una logica di retry configurabile con backoff, isolando i fallimenti definitivi in code morte (DLQ) senza bloccare il flusso principale.

## 2. Entità e Dati

- **RICHIESTA**: Entità sorgente che contiene lo stato della pratica e metadati temporali (es. countdown).
- **UTENTE**: Entità target che rappresenta i destinatari (Dipendente, Responsabile) identificati tramite FK `id`.
- **NOTIFICA**: Entità di persistenza che registra ogni tentativo di invio. Include:
  - `richiesta_id`: Chiave esterna alla pratica sorgente.
  - `utente_id`: Chiave esterna al destinatario.
  - `canale`: Tipo di protocollo (`EMAIL`, `SLACK`).
  - `stato_consegna`: Stato attuale (`IN_CODA`, `CONSEGNATA`, `FALLITA`).
  - `tentativo_n`: Contatore dei tentativi effettuati (max 3).
- **AUDIT_LOG**: Registro immutabile per la tracciabilità delle anomalie e degli eventi di consegna.

## 3. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica su cambio stato dinamico
  GIVEN una RICHIESTA in stato "Bozza" associata a un UTENTE dipendente
  AND la RICHIESTA passa allo stato "Revisato" tramite azione di business
  WHEN il sistema rileva il cambiamento di stato della RICHIESTA
  THEN pubblica un evento asincrono su RabbitMQ contenente l'ID della richiesta
  E istanzia lo Strategy appropriato per determinare il destinatario
  E crea un record NOTIFICA con stato_consegna "IN_CODA" e tentativo_n = 1
```

```gherkin
SCENARIO: S02 - Invio notifica su scadenza imminente
  GIVEN una RICHIESTA con countdown temporale impostato a 1 giorno
  AND il sistema esegue la scansione periodica del job StaticTriggerJob
  WHEN il countdown scende sotto la soglia di attivazione definita
  THEN il job pubblica un evento trigger per "SCADENZA_IMMINENTE"
  E crea un record NOTIFICA con stato_consegna "IN_CODA" e tentativo_n = 1
```

```gherkin
SCENARIO: S03 - Consegna riuscita via Email
  GIVEN una notifica in stato IN_CODA destinata a un canale EMAIL
  AND il server SMTP risponde con successo al messaggio di invio
  WHEN il sistema elabora la risposta positiva dal provider
  THEN aggiorna lo stato della NOTIFICA a "CONSEGNATA"
  E ferma immediatamente la sequenza di retry per quell'evento
```

```gherkin
SCENARIO: S04 - Fallimento Email e backoff verso Slack
  GIVEN una notifica in stato IN_CODA destinata a un canale EMAIL
  AND il server SMTP fallisce l'invio (es. timeout o errore rete)
  WHEN il sistema incrementa il contatore tentativo_n a 1
  THEN attende il periodo di backoff configurato di 15 minuti
  E tenta l'invio dello stesso evento tramite il canale SLACK
```

```gherkin
SCENARIO: S05 - Fallimento definitivo e logging anomalia
  GIVEN una notifica che ha già fallito su EMAIL (tentativo_n = 1)
  AND il tentativo successivo su SLACK fallisce anch'esso
  WHEN il sistema raggiunge il limite massimo di tentativi (3) o entrambi i canali falliscono
  THEN aggiorna lo stato della NOTIFICA a "FALLITA"
  E registra un log strutturato con livello ERROR contenente i dettagli dell'anomalia
```

```gherkin
SCENARIO: S06 - Gestione fallimento silenzioso senza fallback alternativi
  GIVEN una notifica in cui entrambi i canali EMAIL e SLACK hanno fallito definitivamente
  AND il sistema verifica la policy di sicurezza per l'attivazione di fallback
  WHEN si tenta di attivare un canale alternativo non autorizzato (es. SMS)
  THEN il sistema rifiuta l'attivazione del fallback
  E registra solo l'anomalia come "invio mancato" senza bloccare la pratica
```

```gherkin
SCENARIO: S07 - Propagazione CorrelationId end-to-end
  GIVEN una RICHIESTA che innesca un evento di notifica
  AND il sistema genera un correlationId per l'evento RabbitMQ
  WHEN il messaggio viene elaborato dal consumer e generano log o errori
  THEN ogni record NOTIFICA, log strutturato e messaggio DLQ contiene lo stesso correlationId
```

```gherkin
SCENARIO: S08 - Isolamento transazionale della creazione notifica
  GIVEN una RICHIESTA in stato di transizione che richiede la persistenza di una NOTIFICA
  AND il database risponde con un errore durante l'inserimento del record
  WHEN il sistema tenta di scrivere il record NOTIFICA nella transazione
  THEN rollback immediato dell'intera transazione senza scrittura parziale
```

## 4. Punti Aperti

| Funzionalità coinvolta | Assunzione proposta DA CONFERMARE | Domanda aperta |
|---|---|---|
| Gestione Timeout di Consegna (15 min finestra) | Si assume che la finestra temporale massima per tentare le consegne su canali diversi sia rigidamente 15 minuti, indipendentemente dal numero di fallimenti intermedi. | Come si comporta il sistema se un canale è down per più di 15 minuti ma diventa operativo dopo? Il job Quartz.NET deve riavviare la sequenza o considerare l'evento chiuso definitivamente? |
| Logging dell'Anomalia (Livello Semantico) | Si assume che il livello log per il fallimento definitivo sia sempre `ERROR` come specificato, anche se il business logic prevede solo "logging" in certi contesti. | Esiste un flag di configurazione nel workflow che permette di degradare il livello da `ERROR` a `WARNING` per eventi non critici? Se sì, come viene propagato questo flag agli adapter? |
| Validazione Destinatario (Sicurezza Identità) | Si assume che la validazione dell'esistenza dell'UTENTE avvenga sempre prima della creazione del record NOTIFICA. | Qual è il comportamento esatto se l'UTENTE esiste ma il suo stato è "INATTIVO"? Il sistema deve scartare l'invio o tentare comunque e fallire? |
| Copertura Retry Logic | La copertura attuale include 1 fallimento su Email + 1 su Slack. Manca lo scenario per il raggiungimento del limite di 3 tentativi totali (es. 2 fallimenti Email, 1 fallimento Slack). | È necessario aggiungere uno scenario specifico che mostri l'incremento fino a `tentativo_n = 3` e la chiusura della sequenza? Attualmente S05 copre il "fallimento definitivo" ma non esplicita il conteggio progressivo. |
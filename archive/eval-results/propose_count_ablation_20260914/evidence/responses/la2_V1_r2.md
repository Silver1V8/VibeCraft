# Specifica Tecnica — Feature LA2 (Integrazione Notifiche Dinamiche)

## 1. Descrizione della Feature
La feature **LA2** implementa un'architettura asincrona per la gestione dinamica delle notifiche all'interno del modulo `logic-agent`. Il sistema monitora sia eventi dinamici di stato sulle entità `RICHIESTA` che scadenze temporali statiche, generando record nell'entità `NOTIFICA`. Per ogni evento trigger, il sistema tenta l'invio tramite canali configurabili (`EMAIL`, `SLACK`) seguendo una strategia di retry con backoff e fallback silenzioso. La logica di routing dei destinatari (Dipendente vs Responsabile) è gestita tramite pattern Strategy, mentre la persistenza degli stati di consegna garantisce idempotenza e tracciabilità completa dell'operatore.

## 2. Scenari Comportamentali BDD

```gherkin
SCENARIO: S01 - Invio notifica Email su trigger dinamico riuscito
  GIVEN una RICHIESTA in stato "Revisato" che attiva un trigger dinamico
  AND il sistema identifica come destinatario l'utente con ruolo "DIPENDENTE"
  WHEN il consumer NotificationConsumer elabora l'evento e tenta l'invio via EmailChannelAdapter
  THEN lo stato della NOTIFICA viene aggiornato a "CONSEGNATA"
  AND il contatore tentativo_n rimane uguale a 1
  AND non vengono generati tentativi su Slack né log di errore
```

```gherkin
SCENARIO: S02 - Gestione fallimento Email e retry su Slack con backoff
  GIVEN una RICHIESTA in stato "Revisato" che attiva un trigger dinamico
  AND il sistema tenta l'invio via EmailChannelAdapter ma riceve un errore di delivery
  WHEN il sistema incrementa tentativo_n a 1, attende il periodo di backoff configurato (15 minuti) e riprende
  THEN il sistema tenta l'invio tramite SlackChannelAdapter
  AND se anche Slack fallisce definitivamente, lo stato della NOTIFICA diventa "FALLITA"
  AND viene generato un log strutturato con livello ERROR contenente i dettagli dell'anomalia
```

```gherkin
SCENARIO: S03 - Innesco notifica statica per scadenza imminente
  GIVEN una RICHIESTA in attesa di scadenza con countdown <= X giorni
  WHEN il job StaticTriggerJob esegue la scansione periodica e rileva la soglia raggiunta
  THEN pubblica un evento trigger per "SCADENZA_IMMINENTE"
  AND istanzia lo Strategy appropriato per determinare i destinatari (Dipendente o Responsabile)
  AND avvia la sequenza di invio multi-canale secondo le regole di LA2
```

```gherkin
SCENARIO: S04 - Arrivo duplicato di evento trigger e gestione idempotenza
  GIVEN un evento trigger per una RICHIESTA già in coda di elaborazione nel consumer NotificationConsumer
  WHEN il messaggio viene ricevuto nuovamente su RabbitMQ (es. per persistenza broker)
  THEN il sistema verifica l'ID nell'Inbox o lo stato corrente della NOTIFICA
  AND ignora la duplicazione evitando nuovi tentativi di invio o duplicati nel database
```

## 3. Punti Aperti e Assunzioni

| Funzionalità Coinvolta | Assunzione da Confermare | Domanda Aperta |
|---|---|---|
| Gestione Fallimenti Silenziosi | Si assume che il "fallback silenzioso" significhi esclusivamente l'arresto della sequenza di invio per quell'evento specifico senza attivare canali esterni non configurati (es. SMS). | È necessario definire una policy esplicita su quali canali alternativi sono *mai* consentiti oltre a EMAIL e SLACK, o se il sistema deve essere rigido solo su quelli configurati? |
| Timeout di Consegna Globale | Si assume che la finestra temporale massima di 15 minuti tra i tentativi si riferisca al ciclo completo (Email -> Slack) per un singolo evento, non a una finestra globale per tutte le notifiche. | Come deve comportarsi il sistema se l'evento trigger originale ha un timeout diverso da quello del retry logic? |
| Logging Anomalia Definitiva | Si assume che il log strutturato finale con livello ERROR venga scritto immediatamente al raggiungimento dello stato FALLITA, indipendentemente dal momento esatto in cui scade il timer di backoff. | È necessario includere nel log anche l'ID della richiesta sorgente e i metadati del workflow fallito per facilitare il debugging? |
| Copertura Scenari Negativi | La copertura attuale include un caso di successo, un caso di fallback multi-canale fallito e due casi di gestione eventi (statico/duplicato). | Mancano scenari specifici per: 1) Fallimento simultaneo su entrambi i canali senza backoff (es. errore transazionale immediato), 2) Gestione dell'entità UTENTE non trovata prima della creazione della NOTIFICA. |
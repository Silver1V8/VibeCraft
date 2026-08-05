```gherkin
SCENARIO: S01 - Avvio notifica ibrido su cambio stato e scadenza
  GIVEN un record RICHIESTA in stato 'IN_ATTESA_APPROVAZIONE' con una scadenza impostata a +3 giorni
  AND il sistema rileva contemporaneamente l'evento di sottomissione e la pianificazione temporale
  WHEN il motore HybridTriggerStrategy attiva i trigger per entrambi gli eventi
  THEN crea un record NOTIFICA associato alla RICHIESTA con stato_consegna 'IN_CODA'
  E avvia le strategie di invio su canali EMAIL e SLACK in parallelo

SCENARIO: S02 - Invio fallito simultaneo e attivazione finestra backoff
  GIVEN una notifica creata per un utente dipendente che richiede conferma immediata
  WHEN il sistema tenta l'invio sincrono sia sul canale SMTP che sulla Webhook Slack ma entrambi restituiscono errore di rete
  THEN avvia la strategia BackoffWindowingPolicy impostando una finestra operativa attiva da monitorare
  E incrementa il contatore tentativo_n a 1 nel record NOTIFICA

SCENARIO: S03 - Riprova cross-canale entro finestra temporale tollerata
  GIVEN che entrambi i tentativi iniziali di invio hanno fallito e la finestra backoff è aperta
  WHEN l'orchestrator monitora lo stato per un intervallo parziale inferiore ai 15 minuti totali previsti
  THEN riprovia l'invio alternando o sequenziando le richieste verso canali diversi disponibili
  E incrementa il contatore tentativo_n a 2 nel record NOTIFICA

SCENARIO: S04 - Chiusura finestra backoff e stato definitivo FALLITA
  GIVEN che la somma dei tempi di attesa e tentativi supera i 15 minuti totali della finestra operativa
  WHEN l'orchestrator rileva il superamento del limite temporale predefinito per quel blocco specifico
  THEN aggiorna lo stato_consegna a 'FALLITA' nel record NOTIFICA bloccando ulteriori tentativi automatici
  E registra un log strutturato di livello WARNING con campo correlationId e messaggio "invio mancato"

SCENARIO: S05 - Routing dinamico basato su ruolo responsabile
  GIVEN una RICHIESTA che passa dallo stato 'IN_ATTESA_APPROVAZIONE' allo stato 'REVISATO'
  AND il workflow è configurato per inviare notifiche al manager solo in caso di transizione a 'REVISATO'
  WHEN l'evento di cambio stato viene intercettato dal LogicEventConsumer
  THEN crea un record NOTIFICA indirizzato esclusivamente all'utente con ruolo Responsabile (Manager)

SCENARIO: S06 - Persistenza anomalia senza blocco del flusso operativo
  GIVEN che il sistema ha aggiornato lo stato della notifica a 'FALLITA' dopo l'esaurimento dei tentativi
  WHEN la pratica associata alla RICHIESTA prosegue le sue operazioni di business logic principale
  THEN mantiene il record NOTIFICA con FK verso RICHIESTA intatto e non blocca il workflow approvazione

SCENARIO: S07 - Log strutturato per fallimenti multipli nella finestra temporale
  GIVEN che durante la gestione della finestra backoff si verificano più tentativi di invio falliti consecutivi
  WHEN l'orchestrator registra lo stato finale del tentativo nel sistema di osservabilità
  THEN genera una riga log JSON con campi timestamp, level 'WARNING', message descrittivo e correlationId univoco
```
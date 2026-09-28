# Criteri di revisione

Estratto invariato del protocollo fissato prima delle generazioni; nessun criterio aggiunto dopo le risposte.

## FE3: quattro funzionalità attese

Il raggruppamento è fissato per comportamento osservabile, non per numero di righe
del Canvas o librerie: non verrà cambiato dopo aver letto le risposte.

| ID | Funzionalità | Caso nominale e caso negativo attesi |
|---|---|---|
| FE3-F1 | Inserimento e validazione motivazione | Testo entro limite; superamento di 500 caratteri impedisce invio, con feedback |
| FE3-F2 | Raccolta preferenze/alloggio | Scelta alloggio trasmessa; input preferenze non definito resta dichiarato senza inventare validazioni |
| FE3-F3 | Invio e feedback di rete | Invio valido con caricamento; doppio click non duplica, timeout/500 mostrano errore |
| FE3-F4 | Idoneità e disponibilità del form | Utente senza richiesta attiva può accedere; richiesta APPROVATA/IN_ATTESA_APPROVAZIONE inibisce il form |

FE3-F4 è ancorata a REGOLA-INT-01 della fonte e al controllo del record esistente
nel Canvas Approach, non estesa all'implementazione del backend. Anti-doppio-click
e feedback sono casi di FE3-F3, non nuove funzionalità. Quattro funzionalità
richiederebbero almeno otto scenari se tutti i casi fossero decidibili: il vecchio
limite globale di sette entra in conflitto. Un caso irrisolto va dichiarato,
non inventato per raggiungere otto.

### Dubbi FE3 ancora aperti considerate le fonti

- FE3-Q1, F1: la motivazione vuota deve bloccare? Il Canvas Safeguards lo richiede,
  mentre spec_form REGOLA-FORM-01 chiama note/motivazioni opzionali. Segnalare
  entrambe le prescrizioni e chiedere una decisione, senza sceglierla in silenzio.
- FE3-Q2, F2: quali sono le altre preferenze oltre all'alloggio, i valori ammessi
  e le relative condizioni di errore? Canvas Requirements/Operations le cita
  genericamente, spec_form non le definisce. Non inventare menu o obbligatorietà.
- FE3-Q3, F3: quale interfaccia API esistente, schema esatto e feedback di successo
  consuma il form? Canvas Structure parla di interfaccia esistente "o nuova";
  la fonte non fissa endpoint, codici o destinazione successiva. Uno scenario può
  rimanere a livello di comportamento senza inventare questi dettagli.

NON è dubbio aperto la lunghezza massima: REGOLA-VAL-01 la fissa a 500.
Il wording dell'errore è incoerente dentro la stessa fonte ("Limite superato"
contro il messaggio lungo nell'esempio): non penalizzare uno dei due wording
come invenzione; segnalare se la risposta sostiene falsamente che è univoco.

## LA2: cinque funzionalità attese

| ID | Funzionalità | Caso nominale e caso negativo attesi |
|---|---|---|
| LA2-F1 | Trigger dinamico e routing configurabile | Cambio stato con destinatario da workflow; destinatario non valido non riceve |
| LA2-F2 | Trigger statico di scadenza | Soglia configurata raggiunta innesca notifica; fuori soglia non la innesca |
| LA2-F3 | Consegna multicanale con retry | Successo chiude sequenza; fallimento avvia retry/fallback, dichiarando parametri controversi |
| LA2-F4 | Esaurimento canali e registrazione anomalia | Anomalia persistita e correlata; nessun SMS e nessun blocco della pratica |
| LA2-F5 | Consistenza e idempotenza della notifica | Persistenza con evento; fallimento DB causa rollback e ripetizione non duplica |

Isolamento dalla UI e stack sono vincoli trasversali, non funzionalità aggiuntive.
Minimo teorico dieci scenari, salvo casi la cui decisione manca: dichiararli.

### Dubbi LA2 ancora aperti considerate le fonti

- LA2-Q1, F2: valore e origine della soglia "X giorni" del countdown. Il Canvas
  non la fissa e le fonti selezionate non la completano: niente numero inventato.
- LA2-Q2, F3: 15 minuti fissi fra canali, finestra totale o backoff esponenziale?
  Canvas Requirements/Operations e spec_notifications REGOLA-VAL-01 divergono;
  non esiste qui una decisione di precedenza risolutiva allegata.
- LA2-Q3, F3: tre tentativi totali oppure tre REINVII, oltre al primo? Canvas
  Approach dice tre totali, la fonte dice tre reinvii. Inoltre, con due canali,
  cosa accade al terzo tentativo? Dichiarare il punto senza fissare una sequenza.
- LA2-Q4, F1: routing configurabile e notifiche asincrone del Canvas rispetto a
  Slack per manager ed e-mail sincrona ai dipendenti della fonte (REGOLA-NOTIF-02/03).
  Chiedere quale configurazione concretizzi i vincoli senza hard-coding implicito.
- LA2-Q5, F4/F5: stati IN_CODA/CONSEGNATA/FALLITA del Canvas rispetto a
  PENDING/SENT/FAILED della fonte: il mapping esiste? Non introdurlo come approvato.
- LA2-Q6, F4: severità del fallimento definitivo ERROR del Canvas contro WARNING
  dell'esempio normativo; OBS-04 lega ERROR all'impatto e l'anomalia gestita a WARNING.
  Segnalare l'incoerenza, non inventare una precedenza fra i documenti.

Non sono aperti: esclusione SMS, propagazione correlationId, formato strutturato,
rollback su errore DB e impossibilità di bloccare la pratica per errori di canale.

## Valutazione umana preregistrata

I fogli di valutazione partono vuoti, con status pending_human_review. I codici
campione non mostrano il braccio; la chiave è separata. Il contenuto può comunque
rivelarlo: mascheramento imperfetto, da dichiarare. Nessun verdetto automatico
o dell'assistente sarà presentato come verdetto umano.

1. Requisiti senza supporto: la persona segmenta affermazioni normative atomiche;
   per ciascuna annota citazione testuale e riferimento Canvas/fonte oppure
   unsupported/conflicted/not_assessable. Un'assunzione esplicitamente da confermare
   non è un requisito inventato, salvo che un THEN la imponga come approvata.
   Riportare numero unsupported, conflicted e supported/affermazioni valutabili;
   denominatore zero = N/A. Nessuna percentuale senza denominatore.
2. Ambiguità dichiarate: per ciascun Q sopra, verificare domanda esplicita e
   mancata trasformazione dell'assunzione in requisito. Conta un solo punto anche
   se parafrasato; chiedere un dettaglio già risolto dalla fonte non aumenta il
   punteggio. Copertura = Q dichiarati correttamente / Q fissati (3 FE3, 6 LA2).
3. Copertura: mappare ogni scenario al singolo comportamento/caso, distinguendo
   nominale/negativo. Per ogni F: entrambi coperti / parziale / assente / irrisolto
   dichiarato. Dichiarare un caso mancante è onesto, ma non equivale a coprirlo.
   Non misura scenari soddisfatti da codice: qui nessun codice viene prodotto.
4. Omissioni: elencare quali F/casi e Q fissati mancano senza essere dichiarati;
   contarli separatamente dai requisiti senza supporto. Rispondere meno non può
   migliorare da solo il verdetto. Un'unica frase ripetuta non è nuova copertura.
5. Forma: contare fence e scenari grezzi, verificare GIVEN/WHEN/THEN (+AND) in
   maiuscolo e un fence per scenario. Il rispetto del nuovo limite è descrittivo,
   non da solo prova di miglior qualità; stessa rubrica sostanziale per i bracci.

Per ogni feature/braccio: mostrare tutte e tre le osservazioni, media, deviazione
standard campionaria e range per le quantità numeriche. Con n=3 niente accuratezza
del giudice, test di significatività o conclusioni generalizzate. Differenze
qualitative sopra la dispersione sono valutabili solo DOPO i verdetti umani.
Token e tempi sono misure provider, senza proxy caratteri/3. Usage mancante è
unknown; non si sommano al totale del provider copie dello stesso usage.
Ricerche/chiamate inutili: N/A, Propose non ha tool né un loop di ricerca.


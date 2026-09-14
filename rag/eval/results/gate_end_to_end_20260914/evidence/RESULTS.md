# Prova reale del gate — 14 settembre 2026

## Esito: percorso non completato, senza forzature

Feature nuova `gate-probe-posti`, helper JavaScript puro `formatRemainingSeats`,
creata dal brief conservato in `brief.md`. Nessuna feature archiviata modificata,
nessuna decisione accepted/resolved, nessun override e nessun avvio SDK riuscito.
La prova si è fermata su una classificazione contraddittoria del validatore.
Non dimostra ancora il percorso rivalidazione → implementazione completata.

Codice applicativo al momento della prova: main `7e4bc3e` (messaggio corretto),
gate introdotto da `37d3bbb`. Chiamate reali alle route HTTP della pipeline, senza
mock: Canvas e Propose tramite Ollama `qwen3.5:9b`, temperatura 0.1, contesto
16384, think=false; Validate con il provider configurato e retrieval corrente.
Le informazioni del validatore e le fonti realmente fornite sono nei record
integrali in `validations/`. Indice `v20260911T155042`, nessuna reindicizzazione.
Qdrant esistente avviato e server locale inizializzato con modelli già in cache.
Nessuna credenziale conservata nelle evidenze. La UI non è stata azionata:
la prova usa le stesse API e conserva il testo del rifiuto restituito dal server.

## Passaggi e tempi osservati

| Passaggio | Secondi HTTP | Risultato |
| --- | ---: | --- |
| Salvataggio intervista | 0.029 | Feature creata dal brief |
| Canvas | 102.949 | Canvas generato; incoerenza su -0 rilevata leggendo il testo |
| Propose 1 | 36.495 | 15 scenari; report valid, OP-001 sul valore JavaScript 2.0 |
| Validate 1 | 14.746 | failed: lacuna associata al dubbio su 2.0 |
| Revisione esplicita Canvas | 0.029 | -0 nei nominali; nessuna conversione; 2.0 equivale a 2 |
| Propose 2 | 29.931 | 13 scenari; report invalid per campo research fuori schema |
| Validate 2 | 18.725 | passed nei controlli, ma gate.allowed=false per report invalid |
| Revisione esplicita Spec | 0.034 | Rimosso soltanto research dalla radice JSON |
| Validate 3 | 15.218 | failed: rilievo coverage afferma che NON ci sono lacune |
| Avvio con riferimento alla validazione precedente | 0.044 | 409 per Spec modificata; nessuna esecuzione iniziata |

Totale attesa API: **218.200 s (3 min 38 s)**, incluse 6 generazioni reali
(1 Canvas, 2 Propose, 3 Validate). Dal primo salvataggio all'ultimo rifiuto:
**10 min 43 s** circa. La differenza include lettura, verifiche, preparazione
comandi e interazione con gli strumenti; non è tutta tempo di ragionamento.
Preparazione iniziale dei servizi e scrittura del resoconto escluse dal totale.
`timings.jsonl` conserva timestamp UTC e durate misurate, non stime.

Gli output grezzi sono conservati per ogni richiesta prima dell'analisi.
Gli snapshot `propose-spec.*` senza suffisso numerico riflettono l'ultimo
Propose: le risposte `propose-1.response.txt` e `propose-2.response.txt` restano
indipendenti e complete, così come i contratti nei record di validazione.
Le revisioni sono richieste `canvas-clarification-1.request.json` e
`repair-report-1.request.json`: niente correzioni nascoste del parser.

## Perché ci siamo fermati

Validate 3 ha prodotto questo rilievo con `kind: coverage`:

> La suite di test definita nel Canvas (Sezione 5, punto 3) e negli Scenari BDD (Spec Sezione 3) copre integralmente tutti i requisiti funzionali: formattazione per valori validi (0, -0, 1, 2-9999), gestione errori per tipi errati (stringhe, null, booleani, NaN, Infinity) e valori fuori range (<0, >9999). Non sono presenti lacune rispetto agli scenari BDD S01-S13.

Il gate tratta correttamente coverage come rilievo bloccante. Cercare nella prosa
«Non sono presenti lacune» per trasformarlo in approvazione violerebbe il design.
È un errore di classificazione del modello che supera lo schema sintattico.
Non abbiamo inventato un punto accepted, cambiato i controlli o ripetuto Validate
finché restituisse passed. La prossima scelta riguarda il validatore, non una
modifica arbitraria al contratto. Nessun intervento correttivo implementato qui.

Validate 1 aveva bloccato 2.0 ma non aveva segnalato l'incoerenza su -0 già
osservata nel Canvas. Dopo chiarimento, Validate 2 raccomanda uno scenario 2.0
senza bloccarlo. Questi esiti non certificano la qualità del giudizio semantico.
Inoltre 15/13 scenari per una sola funzionalità mostrano che il conteggio del
prompt non è un vincolo deterministico: nessuna modifica al prompt in questa prova.

## Rifiuto 409 reale, testo leggibile

Richiamata deliberatamente la validazione precedente alla correzione della Spec
`val-e56a102f7d164170a4f038eac192cc1a`, il server ha risposto:

> La Spec è stata modificata rispetto alla validazione val-e56a102f7d164170a4f038eac192cc1a del 14/09/2026 16:30 UTC. Il Canvas è invariato.

Azione `user_action`:

> Valida nuovamente Canvas, Spec e decisioni correnti, poi riprova.

`attempt_recorded: true`, evento `execution_blocked`, attempt ID
`attempt-738968a606394c50a19872d01d82afb6`. Corpo integrale in
`run-1.response.txt`. È un mismatch reale della Spec, non la sequenza completa
richiesta dopo un gate allowed: nessuna validazione aveva ancora autorizzato
l'avvio. I casi Canvas e modifica di entrambi i documenti sono verificati dai
test del messaggio, non spacciati per due ulteriori prove reali.

## Dimensione dei record e crescita

Byte del JSON effettivamente persistito, inclusi testi, risposta grezza e fonti:

| Record | Stato | Report punti aperti | Byte |
| --- | --- | --- | ---: |
| val-d77105f5ad994bd48226782c36de4a79 | failed | valid | 41 744 |
| val-e56a102f7d164170a4f038eac192cc1a | passed, gate bloccato | invalid | 44 245 |
| val-60c27c8d6dee4577a465a9b638f87086 | failed | valid | 42 489 |

**Mediana osservata: 42 489 byte (41.5 KiB)**; intervallo 41 744–44 245 byte;
totale 128 478 byte (125.5 KiB). Tre record per questa feature **incompleta**.
Il numero di validazioni per feature portata a termine è **non misurato**;
non va presentato come tre. Campione di una sola feature minima: questa mediana
non è una stima rappresentativa di feature più grandi. Nessuna retention o
pulizia automatica introdotta. running→esito aggiorna lo stesso record.

## Attriti oltre dieci secondi

Registrati in `frictions.jsonl`: soglia riconosciuta e annotata manualmente,
non misurazione cronometrata della durata del pensiero.

1. Individuare il Qdrant corretto fra più container e ripristinare i servizi.
2. Districare -0 valido nei requisiti ma invalido nella lista dei test del Canvas.
3. Verificare 2.0 con Node e distinguere un dubbio del modello da un requisito
   realmente aperto; correggere il Canvas senza simulare un'accettazione.
4. Capire il report invalid per campo extra e distinguere `passed` da
   `gate.allowed`: una validazione passed non autorizza da sola l'esecuzione.
5. Capire il rilievo coverage che dichiara copertura completa: il messaggio
   «Correggi i controlli falliti» non indica una correzione legittima del
   contratto. Questo è il blocco che ha interrotto la prova.

La prova reale ha quindi individuato attriti prima dell'implementazione; non
possiamo dichiarare completata né questa feature né la verifica end-to-end.

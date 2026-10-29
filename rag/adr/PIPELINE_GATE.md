# Gate della pipeline — stato operativo e decisioni al 15 settembre 2026

**Enforcement attivo sulla sola modalità agentic.** UI e avvio usano il punto
decisionale unico, ricalcolato dal server. Suggest/oneshot restano consultivi;
il gate non governa processi esterni avviati autonomamente.

Design approvato nella conversazione del 14 settembre 2026. Obiettivo: eseguire
in modalità agentic soltanto un contratto validato, congelato e riconoscibile.
Nessuna nuova dipendenza, nessun force, formato GIVEN/WHEN/THEN invariato.

## Stato alla chiusura della sessione

**Gate operativo; ciclo end-to-end reale verificato il 15 settembre 2026.**
Sulla nuova feature `gate-probe-posti`: Canvas → Propose → Validate → modifica
volontaria del Canvas → avvio rifiutato con 409 → rivalidazione → avvio agentic
riuscito → 16 test Node superati. Canvas e Propose erano stati acquisiti il
14 settembre; la ripresa ha incluso un 503 per JSON malformato e un solo
recupero manuale dichiarato. Nessuna accettazione inventata, nessun force e
nessuna riparazione automatica. Feature implementata e testata, non archiviata
né distribuita. La prova usa API e SDK reali; non è una prova browser della UI.

Dati osservati su **un solo ciclo completato**, su due revisioni del validatore:

- **6 validazioni per feature conclusa**, incluse le tre iniziali e il 503.
- **Circa 39,8 KiB mediani per record**: 40 780,5 byte sui sei record.
- **Circa 240 KiB per ciclo completo**: 247 085 byte, ossia 241,3 KiB, per i
  sei record di validazione; journal eventi e copie delle evidenze esclusi.
- **Nessuna rotazione o pulizia automatica introdotta.** Il dato serve a
  decidere più avanti; non è una stima generalizzabile delle feature future.

Implementazione: `452b88d`; evidenze del ciclo completo: `f911b12`.
I tre record originali restano identici byte per byte. Risposte, tempi, errori e
misure sono nei resoconti del [14 settembre](../eval/results/gate_end_to_end_20260914/evidence/RESULTS.md)
e del [15 settembre](../../archive/eval-results/gate_end_to_end_20260915/evidence/RESULTS.md).

## Registro unico degli attriti delle due prove

Questi sono i punti in cui qualcuno potrebbe cercare una scorciatoia.
La soglia di oltre dieci secondi di ragionamento è stata annotata manualmente,
non cronometrata. Il registro comprende problemi del prodotto e degli strumenti
usati per la prova; le correzioni non cancellano gli attriti osservati.

1. **F01 — Preparazione dei servizi:** individuare il Qdrant corretto fra più
   container e distinguere un servizio spento da un validatore indisponibile.
   Avviati i servizi esistenti, senza reindicizzare.
2. **F02 — Canvas incoerente su -0:** valido nei Requirements, invalido nella
   lista dei test; Approach contemplava conversioni vietate dal brief.
   Originale conservato, Canvas corretto esplicitamente.
3. **F03 — Dubbio artificiale su 2.0:** distinguere una domanda del modello da
   un requisito irrisolto. Il validatore bloccava 2.0 ma non segnalava -0.
   Verifica Node, chiarimento Canvas e rigenerazione Spec, senza accettazioni.
4. **F04 — passed non significa allowed:** JSON sintatticamente valido ma
   report invalid per research alla radice; controlli passed, avvio bloccato.
   Correzione esplicita della Spec, nessuna riparazione nel parser. La UI ora
   espone separatamente esito dei controlli e ammissione, con il motivo.
5. **F05 — coverage che dichiara assenza di lacune:** capire che il rilievo è
   contraddittorio, non che occorre indovinare una modifica del contratto.
   Prima prova interrotta senza override; problema ancora aperto.
6. **F06 — 503 per JSON malformato in suggestions:** virgolette non escapate
   e graffa finale mancante rendono inutilizzabile tutto il resoconto.
   Un solo recupero manuale preregistrato, nessun repair; entrambi i record conservati.
7. **F07 — Errore Unicode del runner locale:** distinguere il fallimento della
   stampa cp1252 dal completamento SDK. Stream e tempi erano già salvati;
   letti dal file senza ripetere la sessione. Test Node eseguiti separatamente,
   perché l'agente non dispone di Bash. È un attrito dello strumento della prova.

## Problemi aperti e rischi residui

### Chiusi in R8 (follow-up qualità agentic)

- **Coverage contraddittoria:** chiusa con detector strutturale su `message`
  (`core/pipeline_validation.contradictory_coverage`). Un rilievo `topic=coverage`
  che dichiara assenza di lacune rende il resoconto non conforme → validazione
  `unavailable`, come `recommendation` nei findings. Nessuna seconda chiamata LLM.
- **Modello dei rilievi:** chiuso con split `topic` (argomento) + `defect`
  (`present` obbligatorio nei findings). L'effetto sul gate resta derivato
  (`blocking` in `read_semantic`). `kind` è solo alias HTTP/UI di `topic`.
- **Retention/GC:** chiusa. `pipeline_gate.validations_keep_per_feature` e
  `events_keep_lines` (override env) ruotano validazioni concluse e `events.jsonl`
  dopo scrittura; i record `running` non si eliminano.
- **Registro esecuzioni:** chiuso con registry condiviso su disco
  (`database/pipeline/activity/`, `activity_scope=shared-disk`). Un PID morto
  viene purgato in `snapshot`; «zero active» non è più relativo a un solo processo.

### Ancora aperti / consapevolmente parcheggiati

- **Controllo semantico sui resoconti:** rinviato. Il detector R8 è euristico
  sulla sola message; nessuna chiamata aggiuntiva LLM.
- **Problema in suggestions o nella sintesi:** resta inascoltato. Non autorizza
  direttamente nulla, ma la sua omissione dai controlli può contribuire a un
  falso via libera. Rischio residuo accettato, non risolto.
- **Feature archiviate missing:** non superano il gate agentic nello stato
  attuale. È una conseguenza attesa della generazione precedente al punto 4:
  per riprenderle occorre rigenerare la Spec con il prompt attuale e revisionarla,
  non inserire una lista vuota o accettare lacune mai esaminate.
- **Retrieval fuori dalla validazione:** converte ancora errori in lista vuota
  e contesto vuoto. Documentato, non corretto fuori dal percorso Validate.
- **Perimetro FE3-F4:** da decidere con chi possiede il Canvas. Il protocollo
  aveva trattato come certo un ambito ambiguo; il gate non risolve quella decisione.
  [Riserva e fonti nella Fase 2](../eval/results/FASE2_PROPOSE_20260914.md#3-difetto-del-protocollo-e-tredici-rilievi).

I percorsi tecnici in codice nel seguito sono relativi alla directory `rag/`;
i collegamenti Markdown sono relativi alla collocazione di questo documento.

## Commit 1 — nucleo e persistenza

- [x] Test del contratto: BOM/CRLF/CR/LF finale, spazi significativi, impronta
  JSON canonica e decisioni legate al punto integrale.
- [x] `core/pipeline_gate.py`: `make_contract`, `new_validation`,
  `finish_validation`, `evaluate_gate(current_contract, validation,
  source_state, availability)`. Nessun I/O nel punto decisionale.
- [x] `core/pipeline_store.py`: record JSON verificati, scrittura atomica tramite
  `core.artifacts`, mutua esclusione tramite `core.writer_lock` già esistente.
- [x] Test: fonte fornita modificata/rimossa blocca; resto del corpus avvisa;
  JSON LA2 r2 resta invalid; una decisione non si trasferisce cambiando il punto.
- [x] Test: passed derivato dai controlli, unavailable distinto da failed,
  contratto cambiato durante validazione stale, nessuna scadenza temporale.
- [x] Test: record corrotto distinto da assente, errore di scrittura preserva
  il record precedente, record conclusi immutabili, lock occupato retryable.
- [x] Verifica del nucleo e regressioni: 207 test passati, lint dell'intero rag
  passato. Consegna: commit dedicato, push su main e arresto per revisione.

## Commit 2 — validazione e decisioni dell'operatore

- [x] Nel percorso di validazione usare il retrieval esistente distinguendo
  fallimento e zero risultati; fallimento durante costruzione del contesto =
  **unavailable**, validazione non avvenuta, non negativa. Congelare fonti e
  manifest durante la costruzione, non dedurli dalle citazioni del modello.
- [x] Risposta semantica con schema obbligatorio; prosa/malformazione non
  autorizzano. Calcolare i controlli strutturali con gli helper già presenti;
  la pertinenza euristica resta advisory. Congelare anche prompt hash, modello
  e risposta grezza. Lacuna accepted non equivale a scenario soddisfatto.
- [x] Endpoint operatore per accepted/resolved: motivazione, timestamp server,
  punto integrale, provenienza dichiarata, metadati osservati ed esecuzioni
  attive. Writer impone origin_verified=false e documenta accanto il requisito
  di identità personale autenticata per cambiarlo. Nessun tool agente lo espone.
- [x] Route validate/stato e UI consumano evaluate_gate; test integrazione con
  guasti retrieval/modello, JSON malformato, stale, decisioni legate alla Spec e associazioni esplicite.
- [x] Consegnare separatamente validazione e decisioni prima dell’enforcement;
  test, lint, commit e push verificati.

Verifiche del secondo commit: 464 test Python passati (inclusi MCP e controllo
positivo SDK nelle tre modalità), due controlli UI Node passati, Ruff sull'intero
`rag` passato. Nessuna generazione reale effettuata per queste verifiche.

## Commit 3 — avvio, UI ed eventi

- [x] agent/run riceve feature e validation_id, rilegge i fatti server e usa
  evaluate_gate; agentic rifiutato prima dello stream con 409/503 dettagliato.
  Suggest/oneshot disponibili con i blocchi visibili.
- [x] Prompt server costruito dai testi/decisioni congelati, nessun prompt
  arbitrario del client o lettura tardiva dei file mutabili come contratto.
- [x] Coordinare salvataggi, decisioni e ammissione sulla stessa feature; non
  tenere il lock durante la validazione LLM. Conservare il confinamento SDK.
- [x] `events.jsonl`: validation_finished, execution_blocked, execution_started,
  execution_finished, open_point_decision_recorded; attempt_id e
  retry_of_attempt_id verificato dal server. Avvio non registrabile = 503.
- [x] Test end-to-end di bypass client, mismatch, race, outage, eventi e UI;
  rimuovere le diciture transitorie da README, questo documento e docstring.
- [x] Misurare dimensione record e numero di validazioni per feature osservata,
  nella prova reale richiesta dopo il push; non presentare fixture come dati operativi.
- [x] Test, lint, commit, push; fermarsi.

Verifica del terzo commit: 544 test Python passati, inclusi lock, journal,
confinamento SDK, MCP e archiviazione; controlli UI Node e Ruff passati.
I contratti preesistenti (LA3 attiva, FE1–FE4 e LA1–LA2 archiviate) hanno
resoconto missing. Per le feature archiviate è una conseguenza attesa: furono
generate prima del punto 4, che ha introdotto il resoconto strutturato, non è un
difetto del parser o del gate. Se si dovrà lavorarci di nuovo, rigenerare la Spec
con il prompt attuale e revisionarla; non aggiungere una lista vuota né accettare
lacune mai esaminate. La prova operativa successiva usa invece una feature nuova
creata dall'inizio, senza forzare lo sblocco dell'archivio.

## Record e invarianti del nucleo

`database/pipeline/validations/<feature>/<validation_id>.json` contiene:
schema_version, validation_id, attempt_id, feature, dev_type, started_at, finished_at,
status, passed, contract, open_points_status, checks, validator, sources,
warnings, structural_findings, semantic_findings, suggestions. I rilievi originali restano
visibili anche se coperti, insieme al riferimento alla decisione. Lo schema eseguibile è `ValidationRecord` in `core/pipeline_gate.py`.

Il contratto conserva canvas/spec `{text, hash}`, decisioni integrali e
decisions_hash, normalizzazione versione 1 e hash complessivo. L'hash documentale
è SHA-256 dei byte UTF-8 normalizzati; quello del contratto è SHA-256 del JSON
canonico di normalizzazione, Canvas, Spec e decisioni (chiavi ordinate, nessuno
spazio JSON aggiuntivo). Feature e dev_type sono legati al record e confrontati
separatamente; non consentono il riuso fra feature o ambiti diversi.

Solo BOM iniziale, CRLF/CR→LF e un LF finale vengono normalizzati. Gli spazi,
la punteggiatura e l'ordine dei contenuti non vengono corretti. Le decisioni
sono ordinate per impronta del punto; per ogni punto attuale si congela l'ultima
decisione della stessa feature e della stessa impronta Spec, per timestamp server
e ID come spareggio. Cambiando la Spec decade anche una decisione il cui punto
è rimasto identico. Le sole differenze normalizzate non la fanno decadere.
Il record concluso non viene aggiornato per riflettere cambiamenti successivi:
è evaluate_gate a rilevare il mismatch. Non c'è scadenza automatica.

`checks.structural` e `checks.semantic` hanno status pass/fail/unavailable e
details. Un unavailable prevale su un fail: un controllo non avvenuto non
certifica un esito. Se i controlli sono disponibili ma il contratto cambia
durante la validazione, l'esito è stale. Il record non accetta passed=true
in contrasto con i controlli. La prosa del modello non entra nel calcolo.

Le fonti conservano index_version, corpus_doc_hashes e provided con doc_id,
path, document_hash, chunk_id, text_supplied, text_hash e truncated. L'elenco
provided si riferisce ai documenti dei brani effettivamente inviati: un cambio
del documento blocca, un cambio di un altro documento avvisa. Il solo cambio
di index_version non blocca. Il loader server deve segnalare indisponibilità
dei dati con availability: una mappa vuota non deve nascondere un errore.

I record decisione sono scritti dal server sotto
`database/pipeline/decisions/<feature>/<decision_id>.json`; gli eventi sono
sotto `database/pipeline/events.jsonl`, separati da `eval/results/history.jsonl`.
Retention R8: dopo ogni validazione conclusa si tengono le ultime N per feature
(`pipeline_gate.validations_keep_per_feature`, default 20); dopo ogni append di
`events.jsonl` si tengono le ultime M righe (`events_keep_lines`, default 2000).
I record `running` non si eliminano. Record locale corrotto è un guasto
operativo, record inesistente è assenza di validazione; non sono intercambiabili.

## Difetto del retrieval fuori scope

`core/retrieval.py::select_governed_chunks` restituisce [] anche per guasti;
`retrieve_governed_context` propaga una stringa vuota. Il comportamento interessa
anche Canvas, Propose e gli altri chiamanti di questi helper, oltre a Validate.
Il secondo commit distingue errore/assenza di risultati nel solo percorso di
validazione. Gli altri percorsi restano da correggere in un intervento separato.

## Crescita dei record

La prima misura del 14 settembre sulla feature `gate-probe-posti` aveva tre
record (41 744, 44 245, 42 489 byte), mediana 41.5 KiB, e la feature incompleta.
La ripresa del 15 settembre con suggestions separate ha completato il ciclo:
Validate → modifica Canvas → 409 → rivalidazione (un 503 e un recupero manuale
limitato) → avvio agentic riuscito → 16 test Node superati.

Sei validazioni complessive per questa singola implementazione conclusa e non
archiviata, su due revisioni del validatore: non una media generalizzabile.
I tre record nuovi hanno mediana 39 549 byte (38.6 KiB); sui sei, mediana
40 780.5 byte (39.8 KiB), totale 247 085 byte. Tutti i record originali sono
rimasti identici, verificati tramite SHA-256. Nessuna decisione o deroga inventata.

[Prima parte e cinque attriti](../eval/results/gate_end_to_end_20260914/evidence/RESULTS.md).
[Conclusione, tempi, record, 409 e due nuovi attriti](../../archive/eval-results/gate_end_to_end_20260915/evidence/RESULTS.md).
Due nuovi resoconti conformi su tre; il terzo è JSON malformato, non assenza
verificata di contraddizioni. Nessun giudizio di affidabilità da questo campione.
running→esito aggiorna lo stesso file, una rivalidazione ne crea uno nuovo.
Retention introdotta nel follow-up R8 (vedi sopra).

## Associazioni esplicite — scelta emersa durante l’implementazione

Questa estensione NON era nel progetto inizialmente approvato. È il secondo
attrito tra rilievo globale e decisione puntuale, dopo i punti aperti che
bloccavano indiscriminatamente. Si era concordato di riesaminare il problema
strutturale per intero alla terza occorrenza, poi emersa nella prova reale.

Il terzo attrito si è presentato nella prova reale del 14 settembre: un finding
`coverage` dichiarava assenza di lacune. La revisione del 15 settembre individua
la causa comune nel modello dei rilievi: `kind` confonde argomento esaminato,
esistenza del difetto ed effetto sul gate. Questi livelli vanno distinti dalla
decisione dell'operatore: una decisione non certifica correttezza o pertinenza
del rilievo. Il difetto di struttura è verificato; l'ambiguità del prompt è un
fattore plausibile dell'errore del modello, non una causa isolata sperimentalmente.

Intervento parziale: il prompt distingue le categorie e il loro effetto,
riservando le constatazioni positive alla sintesi. La UI distingue
«Controlli di validazione: superati / falliti / non disponibili» da
«Avvio agentic: consentito / bloccato — motivo». Il primo dato viene dai
controlli sullo snapshot, il secondo da `gate.allowed` e dai motivi server;
non si deduce l'ammissione da `passed` o dalla prosa del modello.

### Separazione implementata il 15 settembre 2026

Il divieto della coppia `contract_quote` + `source_quote` nelle recommendation
è stato scartato: intercettava zero dei quattro consigli conservati e la coppia
di citazioni non prova da sola una violazione. Scartato anche il divieto dei
consigli nell'intero resoconto: avrebbe introdotto indisponibilità evitabile.

Il resoconto del validatore richiede `summary`, `findings` e `suggestions`.
`findings` ammette solo conflict, coverage, out_of_scope: tutte le categorie
sono bloccanti salvo le decisioni pertinenti già consentite per coverage.
`suggestions` è una lista di stringhe non vuote, anche vuota; consigli conservati
nel record e nella risposta API e visibili in UI, senza effetto sul gate.
Un kind non ammesso nei findings o un campo suggestions assente/malformato
rende la nuova validazione unavailable. Nessuno spostamento automatico.
Suggerire COME verificare un requisito non lo rende facoltativo: il test di
2.0 prescritto dal Canvas resta obbligatorio anche suggerendo un'altra forma
BDD o una suite parametrizzata. Un problema minore resta un problema.

Nessuna migrazione: i tre record del 14 settembre e i loro JSON originali
restano immutati. Le risposte originali non sono conformi al nuovo schema;
i record storici restano leggibili. `suggestions: null` in memoria distingue
un record precedente (o un resoconto non acquisito) da una lista nuova vuota.
Questo campo non modifica hash del contratto, decisioni o algoritmo del gate.

Limite residuo accettato: la separazione NON garantisce che tutti i problemi
finiscano nei findings. Un problema in suggestions o nella sintesi non autorizza
direttamente nulla, ma resta inascoltato; la sua omissione dai controlli può
contribuire a un falso via libera. Il rischio non è risolto. Dal follow-up R8
la coverage che dichiara assenza di lacune è riconosciuta come non conforme
(detector strutturale su message); findings usano `topic`+`defect=present` e
`kind` resta solo alias di uscita. Nessuna ricerca nella prosa per approvare e
nessun secondo giudizio LLM introdotto.

Tutti e sette gli attriti delle due prove sono raccolti nel registro unico sopra;
i record originali `frictions.jsonl` restano nelle rispettive cartelle di evidenza.

Il controllo strutturale esistente produce `scenari_insufficienti` e
`caso_negativo_mancante` senza identificare F o OP. Nessuna equivalenza viene
dedotta dalla prosa: il server espone i rilievi con impronta di riga, scenario,
regola e messaggio; l'operatore seleziona quelli da associare a un punto accepted.
La lista predefinita è vuota. Un rilievo non associato è `unexamined` e blocca;
`resolved` non permette questa deroga. Tutti gli altri controlli, compresi
GIVEN/WHEN/THEN, restano inderogabili. L'associazione non cancella il rilievo:
`review_status: covered` e `covered_by` conservano ID decisione, autore e
provenienza dichiarati, timestamp e `origin_verified: false`.

`PointDecision` conserva ID, feature, punto integrale, point_hash, spec_hash,
status, motivazione, timestamp server, declared_by, declared_origin,
observed_metadata, active_attempt_ids, origin_verified e coverage_findings.
I rilievi associati sono contenuti integrali, non solo ID. L'intero record entra
nell'impronta del contratto. Se cambia la Spec o il punto, la decisione non
si trasferisce. L'accettazione e l'associazione hanno la stessa credenziale
condivisa: NON sono certificate come decisioni umane. `origin_verified` è false
nel writer e nello schema, non un campo modificabile dalla richiesta.

La risposta semantica usa uno schema Pydantic stretto, JSON senza riparazioni.
Conflitto/fuori ambito richiedono una citazione presente nel contratto; le
citazioni delle fonti devono essere negli estratti effettivamente forniti.
Una lacuna semantica riferita al point_hash esatto già deciso resta visibile
con covered_by e scenario_satisfied=false. Questo riferimento è una valutazione
semantica del modello, non una prova di pertinenza; non può associare né coprire
i rilievi strutturali globali. Una lacuna senza riferimento resta bloccante.
Non cercare mai un verdetto globale nella prosa o nelle citazioni.

Il registro delle esecuzioni attive segue la durata della coroutine SDK, anche
quando il consumatore HTTP si disconnette. Dal follow-up R8 è un registry
condiviso su disco (`database/pipeline/activity/<attempt_id>.json`) con
`activity_scope=shared-disk`; il PID nel record serve solo a scartare processi
morti. Le esecuzioni senza feature restano elencate separatamente. La
sovrapposizione temporale non certifica chi abbia chiamato l'endpoint. Nessuna
telemetria o nuova dipendenza.

## Ammissione, concorrenza e registro eventi

La richiesta agentic identifica feature e validation_id. Il server rilegge
contratto, decisioni, record e impronte delle fonti; `evaluate_gate` restituisce
allowed, reasons con user_action/operator_action/retryable e warnings. Non usa
allowed del client (campo rifiutato) né il suo prompt (ignorato in agentic).
409 segnala il mismatch con nomi dei documenti e validazione di riferimento;
503 prevale quando coesistono guasti, conservando tutti i reasons disponibili.

Un lock OS per feature, `locks/<feature>.lock`, coordina salvataggi Canvas/Spec,
metadati, decisioni, spostamento finale in archivio, snapshot iniziale/finale
della validazione e ammissione. La chiamata LLM e la review prima dell'archivio
sono fuori dal lock. Il lock non dura per l'intera implementazione: questa usa
il contratto congelato e non rilegge changes/ per decidere cosa è autorizzato.
Il lock coordina i writer applicativi, non impedisce edit esterni arbitrari del
filesystem. Le modalità suggest/oneshot non dipendono dal lock di ammissione.

Prima di schedulare la coroutine SDK si scrive e fsynca execution_started;
un errore impedisce agentic con 503. Lo scheduling è immediato, non dipende
dalla prima lettura dello stream HTTP. execution_finished segue la coroutine
SDK anche se il client si disconnette. Un crash del processo o un errore finale
di storage lascia il tentativo senza conclusione: non equivale a completamento.
L'errore finale è esposto nello stream e nel log server. Nessun retry automatico
del modello. Il journal ha retention configurabile (R8: ultime N righe).

`events.jsonl` contiene cinque tipi: validation_finished, execution_blocked,
execution_started, execution_finished, open_point_decision_recorded. Ogni
record ha event, feature, recorded_at server, attempt_id e retry_of_attempt_id
(null se non pertinente). Gli eventi di esecuzione hanno mode, validation_id,
gate/reasons/warnings e open_points_status; la fine aggiunge outcome e lo stato
del resoconto prodotto. La validazione aggiunge status/passed. La decisione
aggiunge decision_id, point_hash, status, autore/provenienza dichiarati,
metadati osservati, tentativi attivi e origin_verified=false. Le associazioni
restano rintracciabili anche nel record immutabile della decisione.

Il server verifica che retry_of_attempt_id identifichi un execution_blocked
della stessa feature. Un ID inventato, di altra feature o di un avvio riuscito
non certifica una ripresa. Se la verifica non è possibile, il riferimento non
viene propagato come verificato. `attempt_recorded: false` nel rifiuto dichiara
che nemmeno il blocco è stato registrato: la UI non lo usa come riferimento.
Il journal viene verificato sotto lo stesso lock dell'append: un tail troncato
richiede intervento operativo, non viene riparato né ignorato per partire.

Persistenza del record e append del suo evento sono due operazioni locali:
se il secondo fallisce, il record può già esistere e l'API restituisce 503.
Ricaricare il record prima di ripetere; la misura deve segnalare l'evento mancante.
I record conclusi non vengono cancellati per compensare un guasto del journal.
Per contare riprese si usano i link verificati; per contare blocchi ripetuti
si raggruppa per feature; per onere operativo si leggono le action dei reasons.
Nomi e provenienze dichiarate non sono identità certificate: origin_verified
resta false anche nella misura delle associazioni.

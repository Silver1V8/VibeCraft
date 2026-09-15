# Gate della pipeline — piano approvato e stato di implementazione

**Enforcement attivo sulla sola modalità agentic.** UI e avvio usano il punto
decisionale unico, ricalcolato dal server. Suggest/oneshot restano consultivi;
il gate non governa processi esterni avviati autonomamente.

Design approvato nella conversazione del 14 settembre 2026. Obiettivo: eseguire
in modalità agentic soltanto un contratto validato, congelato e riconoscibile.
Nessuna nuova dipendenza, nessun force, formato GIVEN/WHEN/THEN invariato.

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
- [ ] Misurare dimensione record e numero di validazioni per feature osservata,
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
warnings, structural_findings, semantic_findings. I rilievi originali restano
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
Nessuna pulizia o rotazione automatica. Record locale corrotto è un guasto
operativo, record inesistente è assenza di validazione; non sono intercambiabili.

## Difetto del retrieval fuori scope

`core/retrieval.py::select_governed_chunks` restituisce [] anche per guasti;
`retrieve_governed_context` propaga una stringa vuota. Il comportamento interessa
anche Canvas, Propose e gli altri chiamanti di questi helper, oltre a Validate.
Il secondo commit distingue errore/assenza di risultati nel solo percorso di
validazione. Gli altri percorsi restano da correggere in un intervento separato.

## Crescita dei record

Prima misura operativa del 14 settembre 2026 sulla nuova feature
`gate-probe-posti`: tre record da 41 744, 44 245 e 42 489 byte; mediana
42 489 byte (41.5 KiB). La feature NON è conclusa: un rilievo semantico
classificato coverage dichiara assenza di lacune e blocca comunque, come
richiede lo schema. Nessuna accettazione inventata o retry fino al successo.
Il numero di validazioni per feature conclusa resta non misurato.

[Passaggi, tempi, rifiuto 409 reale e attriti](eval/results/gate_end_to_end_20260914/evidence/RESULTS.md).
I record reali includono testi, risposta grezza e fonti; la misura è locale a
questa feature minima, non una stima generale. running→esito aggiorna lo stesso
file, mentre una rivalidazione ne crea uno nuovo. Nessuna retention introdotta.

## Associazioni esplicite — scelta emersa durante l’implementazione

Questa estensione NON era nel progetto inizialmente approvato. È il secondo
attrito tra rilievo globale e decisione puntuale, dopo i punti aperti che
bloccavano indiscriminatamente. Se emerge una terza volta, riesaminare il
problema strutturale per intero, senza aggiungere una deroga caso per caso.

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

Regola deterministica ancora da decidere, NON implementata: il divieto della
coppia `contract_quote` + `source_quote` nelle recommendation intercetta zero
delle quattro recommendation nei tre record conservati della prova. Tutte hanno
entrambe le citazioni null, anche quando nominano fonti nella descrizione.
Zero rifiuti in questo campione non stima i falsi positivi della regola: manca
un caso con la coppia di citazioni. Citare un contratto e una fonte insieme non
dimostra inoltre una violazione: può documentare conformità o un miglioramento.

Alternativa proposta, da approvare: eliminare `recommendation` dai findings
ammessi; un valore non ammesso rende la validazione unavailable, non failed e
mai passed. I consigli facoltativi resterebbero nella sintesi non autorizzante.
La nuova regola rifiuterebbe due dei tre resoconti storici (quattro finding),
senza dimostrare che siano violazioni: sarebbe un cambio di contratto di output.
Nessun record storico viene riscritto. La proposta elimina la categoria
autodichiarata non bloccante, non garantisce che il modello non ometta problemi
o li relegi nella sintesi. Non risolve deterministicamente la contraddizione
coverage/testo. Nessun controllo semantico aggiuntivo, nessuna nuova generazione
e nessuna efficacia dichiarata prima di una misura reale.

I cinque attriti operativi, compreso passed/allowed, restano nel
[resoconto della prova](eval/results/gate_end_to_end_20260914/evidence/RESULTS.md#attriti-oltre-dieci-secondi)
e nei record `frictions.jsonl` accanto: non sono cancellati dalla correzione UI.

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
quando il consumatore HTTP si disconnette. È locale al processo (PID conservato
in activity_scope); le esecuzioni senza feature sono registrate separatamente.
Con più worker non rappresenta tutte le esecuzioni: prima di interpretare zero
come assenza occorre un registro condiviso. La sovrapposizione temporale non
certifica chi abbia chiamato l'endpoint. Nessuna telemetria o nuova dipendenza.

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
del modello. Nessuna pulizia/rotazione del journal.

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

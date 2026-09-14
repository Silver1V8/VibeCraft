# Gate della pipeline — piano approvato e stato di implementazione

**L'avvio non è ancora vincolato.** I primi due commit introducono nucleo,
persistenza, validazione strutturata e decisioni dell’operatore con UI.
Il vecchio avvio SDK resta disponibile senza enforcement. Il gate
diventa operativo soltanto con il terzo commit; allora questa avvertenza va
rimossa anche dal README e dalle docstring dei moduli.

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
- [x] Documentare ancora **l'avvio non è ancora vincolato**; test, lint, commit,
  push e fermarsi per revisione.

Verifiche del secondo commit: 464 test Python passati (inclusi MCP e controllo
positivo SDK nelle tre modalità), due controlli UI Node passati, Ruff sull'intero
`rag` passato. Nessuna generazione reale effettuata per queste verifiche.

## Commit 3 — avvio, UI ed eventi

- [ ] agent/run riceve feature e validation_id, rilegge i fatti server e usa
  evaluate_gate; agentic rifiutato prima dello stream con 409/503 dettagliato.
  Suggest/oneshot disponibili con i blocchi visibili.
- [ ] Prompt server costruito dai testi/decisioni congelati, nessun prompt
  arbitrario del client o lettura tardiva dei file mutabili come contratto.
- [ ] Coordinare salvataggi, decisioni e ammissione sulla stessa feature; non
  tenere il lock durante la validazione LLM. Conservare il confinamento SDK.
- [ ] `events.jsonl`: validation_finished, execution_blocked, execution_started,
  execution_finished, open_point_decision_recorded; attempt_id e
  retry_of_attempt_id verificato dal server. Avvio non registrabile = 503.
- [ ] Test end-to-end di bypass client, mismatch, race, outage, eventi e UI;
  rimuovere le diciture transitorie da README, questo documento e docstring.
- [ ] Misurare dimensione record e numero di validazioni per feature osservata,
  senza generazioni aggiuntive o stime presentate come dati reali.
- [ ] Test, lint, commit, push; fermarsi.

## Record e invarianti del nucleo

`database/pipeline/validations/<feature>/<validation_id>.json` contiene:
schema_version, validation_id, feature, dev_type, started_at, finished_at,
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
`database/pipeline/decisions/<feature>/<decision_id>.json`; gli eventi nel terzo
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

La route produce ora validazioni, ma le verifiche di questo commit usano solo
fixture isolate e risposte simulate: non esiste ancora un campione operativo
dal quale stimare dimensione tipica o tentativi per feature.
La misura va raccolta con l'integrazione: byte UTF-8 del JSON persistito e numero
di validation_id distinti per feature conclusa. running→esito aggiorna lo stesso
file, mentre una rivalidazione crea un nuovo record. Non stimare come osservati
i tentativi necessari a concludere una feature; nessuna retention introdotta.

## Associazioni esplicite — scelta emersa durante l’implementazione

Questa estensione NON era nel progetto inizialmente approvato. È il secondo
attrito tra rilievo globale e decisione puntuale, dopo i punti aperti che
bloccavano indiscriminatamente. Se emerge una terza volta, riesaminare il
problema strutturale per intero, senza aggiungere una deroga caso per caso.

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

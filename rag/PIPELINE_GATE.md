# Gate della pipeline — piano approvato e stato di implementazione

**L'avvio non è ancora vincolato.** Questo primo commit introduce il nucleo e
la persistenza, senza modificare route, prompt, UI o modalità SDK. Il gate
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

- [ ] Nel percorso di validazione usare il retrieval esistente distinguendo
  fallimento e zero risultati; fallimento durante costruzione del contesto =
  **unavailable**, validazione non avvenuta, non negativa. Congelare fonti e
  manifest durante la costruzione, non dedurli dalle citazioni del modello.
- [ ] Risposta semantica con schema obbligatorio; prosa/malformazione non
  autorizzano. Calcolare i controlli strutturali con gli helper già presenti;
  la pertinenza euristica resta advisory. Congelare anche prompt hash, modello
  e risposta grezza. Lacuna accepted non equivale a scenario soddisfatto.
- [ ] Endpoint operatore per accepted/resolved: motivazione, timestamp server,
  punto integrale, provenienza dichiarata, metadati osservati ed esecuzioni
  attive. Writer impone origin_verified=false e documenta accanto il requisito
  di identità personale autenticata per cambiarlo. Nessun tool agente lo espone.
- [ ] Route validate/stato e UI consumano evaluate_gate; test integrazione con
  guasti retrieval/modello, JSON malformato, stale e decisioni concorrenti.
- [ ] Documentare ancora **l'avvio non è ancora vincolato**; test, lint, commit,
  push e fermarsi per revisione.

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
warnings. Lo schema eseguibile è `ValidationRecord` in `core/pipeline_gate.py`.

Il contratto conserva canvas/spec `{text, hash}`, decisioni integrali e
decisions_hash, normalizzazione versione 1 e hash complessivo. L'hash documentale
è SHA-256 dei byte UTF-8 normalizzati; quello del contratto è SHA-256 del JSON
canonico di normalizzazione, Canvas, Spec e decisioni (chiavi ordinate, nessuno
spazio JSON aggiuntivo). Feature e dev_type sono legati al record e confrontati
separatamente; non consentono il riuso fra feature o ambiti diversi.

Solo BOM iniziale, CRLF/CR→LF e un LF finale vengono normalizzati. Gli spazi,
la punteggiatura e l'ordine dei contenuti non vengono corretti. Le decisioni
sono ordinate per impronta del punto; per ogni punto attuale si congela l'ultima
decisione della stessa feature, per timestamp server e ID come spareggio.
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

I record decisione e il relativo writer arriveranno nel secondo commit sotto
`database/pipeline/decisions/<feature>/<decision_id>.json`; gli eventi nel terzo
sotto `database/pipeline/events.jsonl`, separati da `eval/results/history.jsonl`.
Nessuna pulizia o rotazione automatica. Record locale corrotto è un guasto
operativo, record inesistente è assenza di validazione; non sono intercambiabili.

## Difetto del retrieval fuori scope

`core/retrieval.py::select_governed_chunks` restituisce [] anche per guasti;
`retrieve_governed_context` propaga una stringa vuota. Il comportamento interessa
anche Canvas, Propose e gli altri chiamanti di questi helper, oltre a Validate.
Il secondo commit distinguerà errore/assenza di risultati nel solo percorso di
validazione. Gli altri percorsi restano da correggere in un intervento separato.

## Crescita dei record

In questo primo commit nessuna route produce validazioni: non esiste ancora un
campione operativo dal quale stimare dimensione tipica o tentativi per feature.
La misura va raccolta con l'integrazione: byte UTF-8 del JSON persistito e numero
di validation_id distinti per feature conclusa. running→esito aggiorna lo stesso
file, mentre una rivalidazione crea un nuovo record. Non stimare come osservati
i tentativi necessari a concludere una feature; nessuna retention introdotta.

# Gate: ciclo operativo completato — 15 settembre 2026

## Esito e perimetro

La feature nuova `gate-probe-posti` è implementata e verificata con 16 test Node.
Il percorso complessivo comprende Canvas e Propose reali del 14 settembre,
Validate con il nuovo schema, modifica volontaria del Canvas, avvio rifiutato
409, rivalidazione e avvio agentic riuscito. Non è stata archiviata: «conclusa»
qui significa implementazione prodotta e test eseguiti, non deploy o archivio.

Codice della ripresa: commit `452b88d`. Nessun Canvas/Propose rigenerato, nessuna
accettazione/resolution dell'operatore, nessun force o parser repair. La Spec
iniziale è quella dopo la revisione esplicita del campo research documentata il
14 settembre. [Prima parte del percorso](../../gate_end_to_end_20260914/evidence/RESULTS.md).
La prova usa le API reali e lo stream SDK; non è una prova browser della UI.

I tre record originali, sia operativi sia nelle evidenze, sono identici byte
per byte: verifica SHA-256 in `original_records.sha256`. Qui sono copiati solo
i tre record nuovi. I file generati restano sotto code/frontend/gate-probe,
come prevede la pipeline; le copie testuali `.mjs.txt` sono le evidenze tracciate.
Non sono stati aggiunti al prodotto né integrati con la UI.

## Passaggi, tempi e riferimenti

| Passaggio | Secondi HTTP | Esito |
| --- | ---: | --- |
| Validate 4 complessiva | 27.443 | passed, allowed=true, un suggerimento separato |
| Modifica volontaria Canvas | 0.036 | Nota di isolamento aggiunta, Spec invariata |
| Avvio con Validate 4 | 0.057 | 409 contract_changed, nessuna sessione avviata |
| Validate 5 complessiva | 13.883 | 503 unavailable: JSON malformato |
| Un recupero manuale, Validate 6 | 7.646 | passed, allowed=true, un suggerimento separato |
| Avvio con Validate 6 | 35.576 | SDK completato, is_error=false |

La nota aggiunta volontariamente al Canvas è:

> Nota di consegna: mantenere il dimostratore isolato dalla UI del portale anche dopo la verifica dei test.

Il rifiuto reale, conservato in `run-1.response.txt`, dice:

> Il Canvas è stato modificato rispetto alla validazione val-e355c024c65147fba5f20f60eb2b68a9 del 15/09/2026 07:31 UTC. La Spec è invariata.

Azione `user_action`:

> Valida nuovamente Canvas, Spec e decisioni correnti, poi riprova.

Blocco: `attempt-fc095b0646c147dc887f0df66e417f4f`.
Avvio: `attempt-52cfb2b473624494a53327c1258c805d`, validazione
`val-f3ea0d38b2d0421c895cbb87c08d23b2`. `retry_of_attempt_id` è verificato dal
server e collega avvio e conclusione al blocco. `events.jsonl` conserva gli
eventi della feature di entrambi i giorni; execution_finished ha outcome completed.

La Validate 5 contiene virgolette non escapate attorno a `"-0"` all'interno di
una stringa in suggestions e manca la graffa finale. Il resoconto è stato
rifiutato per intero, non riparato né interpretato come approvazione. Il 503 è
un risultato della prova. Prima del tentativo aggiuntivo è stato registrato in
`PLAN.md` il limite di UN recupero manuale: stesso contratto, modello e prompt,
nessuna ripetizione fino al successo. Il recupero conta in tutti i denominatori.

Attesa API della ripresa: **84.641 s**. Dal primo Validate alla conclusione SDK:
**2 min 43 s** circa, includendo letture e comandi intermedi. Attesa API cumulativa
sui due giorni: **302.841 s (5 min 3 s)**, esclusi preparazione servizi, revisione,
sviluppo della correzione e pausa fra i giorni. Nove generazioni locali totali
(1 Canvas, 2 Propose, 6 Validate) più una sessione agentic di 4 turni.
Il provider del validatore è ollama:qwen3.5:9b; lo SDK usa l'alias sonnet.

Lo SDK riporta 32.389 s e costo USD 0.1242484: dato restituito dal runtime,
non misura del costo delle generazioni locali. Il test Node conservato in
`node-tests.txt` impiega 0.133 s nel comando di raccolta (tempo di processo).
I 16 test includono i 13 scenari della Spec e i casi Canvas 2.0, -Infinity,
undefined. L'agente non ha Bash: i test sono stati lanciati dall'operatore dopo
la sessione, non attribuiti falsamente all'agente.

## Dimensione dei record e numero di validazioni

| Numero complessivo | Validation ID | Stato | Byte |
| --- | --- | --- | ---: |
| 1 | val-d77105f5ad994bd48226782c36de4a79 | failed | 41744 |
| 2 | val-e56a102f7d164170a4f038eac192cc1a | passed | 44245 |
| 3 | val-60c27c8d6dee4577a465a9b638f87086 | failed | 42489 |
| 4 | val-e355c024c65147fba5f20f60eb2b68a9 | passed | 39241 |
| 5 | val-1c4dc25feb074c34a2477e78ff934349 | unavailable | 39817 |
| 6 | val-f3ea0d38b2d0421c895cbb87c08d23b2 | passed | 39549 |

**Sei validazioni per questa singola feature portata a implementazione e test**:
tre originali, tre nella ripresa, incluso il 503. Non sono sei tentativi con lo
stesso software: il validatore è cambiato nel percorso. Non è una media su feature.

- Tre record nuovi: mediana **39 549 byte (38.6 KiB)**, intervallo 39 241–39 817.
- Tutti e sei: mediana **40 780.5 byte (39.8 KiB)**, totale **247 085 byte (241.3 KiB)**.
- La precedente misura di 42 489 byte (41.5 KiB) sui primi tre resta corretta
  per quel sottoinsieme e non viene riscritta.

Sono byte effettivi dei JSON persistiti, inclusi contratto, fonti e risposta
grezza, anche fallita. Nessuna stima dai caratteri, nessuna retention introdotta.

## Nuovi resoconti: conteggi e limiti

Su tre nuove risposte: **2 conformi, 1 JSON malformato**. Le due conformi hanno
findings=[], una suggestion ciascuna. Nessuna coverage contraddittoria osservata
nei due resoconti parsabili; il terzo resta non valutabile dal parser e non è
contato come «assenza di contraddizioni». Non è una stima di affidabilità né la
prova che l'errore sia scomparso: una feature minima e un recupero dichiarato.

Il primo consiglio riguarda import/export nell'eventuale integrazione UI; il
secondo un test aggiuntivo per Number.MIN_VALUE. Il primo riguarda un'integrazione
fuori ambito, il secondo una forma di verifica aggiuntiva: non sono diventati
requisiti del contratto congelato. L'implementazione mantiene l'isolamento.
Il test 2.0 obbligatorio è stato prodotto anche senza un finding che lo ricordasse.

La separazione non garantisce che ogni problema finisca nei findings. Una
violazione relegata a suggestions/summary non autorizza direttamente nulla, ma
può restare inascoltata e contribuire a un falso via libera. La coverage descritta
come completa resta strutturalmente conforme e bloccante, senza riconoscimento
semantico automatico. Nessun secondo modello o controllo sulla prosa aggiunto.

## Attriti aggiuntivi

I cinque del 14 settembre restano nel resoconto originale. Due nuovi punti,
annotati come oltre dieci secondi di ragionamento manuale, non cronometrati:

- **F06, prodotto:** capire che il 503 dipende dalle virgolette nella suggestion
  e che rende inutilizzabile l'intero resoconto. Decidere un recupero limitato
  senza trasformarlo in rigenerazione fino al successo. Il parser non nasconde
  il guasto, ma il formato JSON resta un attrito reale del provider.
- **F07, strumento della prova:** il runner tenta di stampare lo stream NDJSON
  sulla console cp1252 e termina con UnicodeEncodeError. Risposta grezza e tempi
  erano già stati salvati; SDK e execution_finished attestano il completamento.
  Letto lo stream dal file, senza nuova chiamata. È un errore di stampa del
  runner, non un fallimento della pipeline. Nessun byte di evidenza è andato perso.

La distinzione passed/allowed questa volta ha indicato il percorso: controlli
superati prima della modifica, gate bloccato dopo, controlli nuovamente disponibili
e gate consentito al termine. Nessun nuovo attrito annotato su quella distinzione.

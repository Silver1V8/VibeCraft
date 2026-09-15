# REASONS Canvas: gate-probe-posti

## 1. Requirements
- **Funzione Principale:** Validare un contatore di posti residui (`value`) e restituire una stringa etichetta corrispondente.
- **Logica di Formattazione:**
  - Se `value` è esattamente `0`: restituire `"Nessun posto disponibile"`.
  - Se `value` è esattamente `1`: restituire `"1 posto disponibile"`.
  - Se `value` è compreso tra `2` e `9999` (inclusi): restituire `"<value> posti disponibili"`.
- **Gestione Errori:** Sollevare un `TypeError` con il messaggio esatto `"posti non validi"` se:
  - `value` è fuori dall'intervallo `[0, 9999]`.
  - `value` è una frazione (es. `1.5`).
  - `value` è `NaN`, `Infinity`, `-Infinity`.
  - `value` non è di tipo `number` (es. stringa numerica `"2"`, `null`, `undefined`, `true`, booleani).
- **Trattamento Specifico:** Trattare il valore `-0` come equivalente a `0` per la logica di formattazione.
- **Vincoli di Input:** Non convertire, arrotondare, normalizzare o modificare l'input in alcun modo prima della validazione.
- **Ambito Tecnico:** Implementazione isolata in un file JavaScript ES Module (`code/frontend/gate-probe/remaining-seats.mjs`) senza dipendenze esterne, framework o accesso a rete/DB.

## 2. Entities
- **`POSTI_RESIDUI`**: Entità logica rappresentante il contatore intero non negativo di posti disponibili per un evento (fonte del valore `value`).
- **`RICHIESTA`**: Entità logica che consuma i posti residui (citata nel contesto normativo come entità target della risorsa contesa, ma qui presente solo come riferimento concettuale al dominio).
- **`EVENTO`**: Entità contenitore della risorsa contesa (citata nel contesto normativo).

## 3. Approach
- **Pattern di Implementazione:** Funzione pura (`pure function`) in JavaScript ES Module.
- **Strategia di Validazione:**
  1. Verifica del tipo di dato: assicurarsi che l'input sia esattamente un `number`. Se diverso, lanciare errore immediato.
  2. Gestione del caso `-0`: trattare `-0` come `0` mediante confronto numerico, senza conversione né modifica dell’input per garantire la coerenza con i requisiti di business (trattamento come "nessun posto").
  3. Controllo degli estremi: verificare se il valore è `< 0` o `> 9999`. Se vero, lanciare errore.
  4. Controllo della frazionalità: verificare se il valore contiene una parte decimale (es. `Number.isInteger(value)`). Se falso, lanciare errore.
  5. Generazione Stringa: applicare la logica condizionale per costruire la stringa di output basata sui casi `0`, `1` e `[2, 9999]`.
- **Isolamento:** Il modulo non deve importare né esportare funzionalità aggiuntive oltre a `formatRemainingSeats`.

## 4. Structure
- **File di Implementazione:** `code/frontend/gate-probe/remaining-seats.mjs`
- **Export:** `export { formatRemainingSeats }`
- **File di Test:** `code/frontend/gate-probe/remaining-seats.test.mjs`
- **Ambiente Esecuzione:** Node.js standard (moduli nativi `node:test`, `node:assert`). Nessun framework frontend (React, Next.js) coinvolto nell'esecuzione logica del gate, ma il file risiede nella struttura del progetto frontend.
- **Dipendenze:** Nessuna (`dependencies` vuote).

## 5. Operations
1. **Setup Ambiente:** Assicurarsi che Node.js sia installato e che la directory `code/frontend/gate-probe/` esista.
2. **Scrittura Codice:** Creare il file `remaining-seats.mjs` implementando la funzione `formatRemainingSeats(value)` secondo la logica definita in "Approach".
3. **Scrittura Test:** Creare il file `remaining-seats.test.mjs` utilizzando `node:test` e `node:assert`.
   - Definire suite di test per i casi validi (`0`, `-0`, `1`, `2`, `2.0`, `9999`).
   - Definire suite di test per i casi invalidi (`-1`, `10000`, `1.5`, `NaN`, `Infinity`, `-Infinity`, `"2"`, `null`, `undefined`, `true`).
4. **Esecuzione Test:** Avviare la suite di test con il comando: `node --test code/frontend/gate-probe/remaining-seats.test.mjs`.
5. **Verifica Risultati:** Confermare che tutti i test passano e che non ci sono errori di runtime o warning.
6. **Commit:** Aggiungere il file al repository (se applicabile) senza modificare altri file del progetto.

## 6. Norms
- **Naming Convention:** Nomi delle variabili e funzioni in `camelCase` (es. `formatRemainingSeats`, `isValidNumber`).
- **Tipizzazione Dinamica:** Utilizzo di TypeScript non richiesto per questo specifico gate standalone (JavaScript puro), ma il codice deve essere compatibile con l'ecosistema TS del progetto principale se integrato in futuro.
- **Error Handling:** Utilizzo dell'oggetto nativo `TypeError` con messaggi stringa esatti come specificato nell'intervista. Non utilizzare wrapper di errore personalizzati o loggare errori nel console (nessun logging richiesto).
- **Stile Codice:** Aderenza alle best practice JavaScript standard (ES6+), evitando costrutti obsoleti.

## 7. Safeguards
- **`[SAFEGUARD-TXN-01]` Lock Pessimistico:** **NON APPLICABILE**. Questa feature è un helper frontend puro (`gate-probe`) che non esegue transazioni DB, decrementi di contatori o modifiche allo stato dell'evento. Il suo scopo è solo la formattazione del testo per il display UI (o logico), non la gestione della risorsa contesa in sé.
- **`[SAFEGUARD-SEC-01]` Allowlist Identità:** **NON APPLICABILE**. La feature non gestisce sessioni, token OAuth o autenticazione utente.
- **`[REGOLA-FORM-01]` Inibizione Pulsante:** **NON APPLICABILE** come requisito funzionale diretto. Sebbene il testo dell'intervista menzioni che `0` restituisce "Nessun posto disponibile", questa feature non implementa la logica di disabilitazione del pulsante né l'aggiornamento dello stato HTML (`disabled`) della UI. È un *helper* per fornire i dati testuali, lasciando al componente UI (non incluso in questo scope) il compito di interpretare il valore restituito per aggiornare lo stato visivo.
- **`[REGOLA-TEST-06]` Soglie di Copertura:** Applicabile nominalmente. La suite di test deve coprire i limiti `0`, `1`, `2`, `9999` e i casi negativi (`NaN`, `Infinity`, ecc.) come richiesto esplicitamente dall'intervista ("Nessuna omissione è accettata preventivamente").
- **`[REGOLA-TEST-09]` Isolamento Dati:** Applicabile. I test devono essere eseguiti in isolamento senza dipendere da un DB pre-popolato o dati reali (nessun DB coinvolto).
Chiarimento dei valori JavaScript: `2.0` è il medesimo number di `2` (Object.is(2,2.0) e Number.isInteger(2.0) restituiscono true), quindi è valido e restituisce "2 posti disponibili". Non è una frazione. `-0` è valido, restituisce "Nessun posto disponibile" e va nei test nominali. Nessuna conversione dell’input è consentita. Questi casi sono risolti dal contratto, non lacune accettate.

Nota di consegna: mantenere il dimostratore isolato dalla UI del portale anche dopo la verifica dei test.

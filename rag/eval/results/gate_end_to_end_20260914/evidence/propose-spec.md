# Specifiche Tecniche: gate-probe-posti

## 1. Panoramica della Feature
La feature `gate-probe-posti` implementa la funzione pura `formatRemainingSeats(value)` all'interno del modulo ES Module `code/frontend/gate-probe/remaining-seats.mjs`. Il suo scopo è validare un intero non negativo che rappresenta il numero di posti residui (`value`) e restituire una stringa formattata in italiano adatta al display UI. La funzione gestisce casi limite specifici come `-0`, valori fuori intervallo, frazioni e tipi di dato errati, sollevando un `TypeError` con messaggio esatto quando la validazione fallisce.

## 2. Requisiti Funzionali
- **Input:** Un singolo argomento `value`.
- **Output:** Una stringa formattata o un'eccezione `TypeError`.
- **Logica di Formattazione:**
  - `0` (incluso `-0`) $\rightarrow$ `"Nessun posto disponibile"`
  - `1` $\rightarrow$ `"1 posto disponibile"`
  - `[2, 9999]` $\rightarrow$ `"<value> posti disponibili"`
- **Gestione Errori:** Solleva `TypeError("posti non validi")` se:
  - `typeof value !== 'number'`.
  - `Number.isInteger(value)` è falso (esclude frazioni come `1.5`).
  - `value < 0` o `value > 9999`.
  - `value` è `NaN` o `Infinity`.

## 3. Scenari di Test

```gherkin
SCENARIO: S01 - Formattazione per zero posti residui (caso nominale)
  GIVEN un valore numerico pari a 0 passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN restituisce la stringa "Nessun posto disponibile"
```

```gherkin
SCENARIO: S02 - Formattazione per zero posti residui (caso negativo -0)
  GIVEN un valore numerico pari a -0 passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN restituisce la stringa "Nessun posto disponibile"
```

```gherkin
SCENARIO: S03 - Formattazione per un posto residuo (caso nominale)
  GIVEN un valore numerico pari a 1 passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN restituisce la stringa "1 posto disponibile"
```

```gherkin
SCENARIO: S04 - Formattazione per posti residui nell'intervallo standard (caso nominale)
  GIVEN un valore numerico pari a 500 passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN restituisce la stringa "500 posti disponibili"
```

```gherkin
SCENARIO: S05 - Formattazione per capienza massima (caso nominale)
  GIVEN un valore numerico pari a 9999 passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN restituisce la stringa "9999 posti disponibili"
```

```gherkin
SCENARIO: S06 - Errore per valore negativo (caso di errore)
  GIVEN un valore numerico pari a -1 passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN solleva un'eccezione TypeError con messaggio "posti non validi"
```

```gherkin
SCENARIO: S07 - Errore per valore superiore al limite (caso di errore)
  GIVEN un valore numerico pari a 10000 passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN solleva un'eccezione TypeError con messaggio "posti non validi"
```

```gherkin
SCENARIO: S08 - Errore per frazione (caso di errore)
  GIVEN un valore numerico pari a 1.5 passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN solleva un'eccezione TypeError con messaggio "posti non validi"
```

```gherkin
SCENARIO: S09 - Errore per input stringa (caso di errore)
  GIVEN una stringa numerica "2" passata alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN solleva un'eccezione TypeError con messaggio "posti non validi"
```

```gherkin
SCENARIO: S10 - Errore per input null (caso di errore)
  GIVEN il valore null passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN solleva un'eccezione TypeError con messaggio "posti non validi"
```

```gherkin
SCENARIO: S11 - Errore per input NaN (caso di errore)
  GIVEN il valore NaN passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN solleva un'eccezione TypeError con messaggio "posti non validi"
```

```gherkin
SCENARIO: S12 - Errore per input Infinity (caso di errore)
  GIVEN il valore Infinity passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN solleva un'eccezione TypeError con messaggio "posti non validi"
```

```gherkin
SCENARIO: S13 - Errore per input booleano (caso di errore)
  GIVEN il valore true passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN solleva un'eccezione TypeError con messaggio "posti non validi"
```

## 4. Punti aperti

```json
{"open_points":[],"research":{"status":"closed","new_evidence":[],"verification":"agent_reported"}}
```

# Specifiche Tecniche: gate-probe-posti

## 1. Panoramica della Feature
La feature `gate-probe-posti` implementa la funzione pura `formatRemainingSeats(value)` all'interno del modulo ES Module `code/frontend/gate-probe/remaining-seats.mjs`. Il suo scopo è validare un intero non negativo che rappresenta il numero di posti residui (`value`) e restituire una stringa formattata in italiano adatta al display UI. La funzione gestisce casi limite specifici come `-0`, valori fuori intervallo, frazioni e tipi di dato errati, sollevando un `TypeError` con messaggio esatto quando la validazione fallisce.

## 2. Requisiti Funzionali
La funzione deve comportarsi secondo le seguenti regole:
1.  **Input Valido (Caso 0):** Se `value` è esattamente `0` (incluso `-0`), restituisce `"Nessun posto disponibile"`.
2.  **Input Valido (Caso 1):** Se `value` è esattamente `1`, restituisce `"1 posto disponibile"`.
3.  **Input Valido (Casi Multipli):** Se `value` è un intero compreso tra `2` e `9999` (inclusi), restituisce `"<value> posti disponibili"` (es. `"50 posti disponibili"`).
4.  **Errore Tipo:** Se `value` non è di tipo `number`, solleva `TypeError("posti non validi")`.
5.  **Errore Intervallo:** Se `value` è `< 0` o `> 9999`, solleva `TypeError("posti non validi")`.
6.  **Errore Frazionario:** Se `value` ha una parte decimale (es. `1.5`), solleva `TypeError("posti non validi")`.
7.  **Casi Speciali Infiniti/NaN:** Se `value` è `NaN`, `Infinity` o `-Infinity`, solleva `TypeError("posti non validi")`.

## 3. Scenari di Test

```gherkin
SCENARIO: S01 - Restituzione messaggio per zero posti residui
  GIVEN un valore intero pari a 0 passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN restituisce la stringa "Nessun posto disponibile"
```

```gherkin
SCENARIO: S02 - Restituzione messaggio per un posto residuo
  GIVEN un valore intero pari a 1 passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN restituisce la stringa "1 posto disponibile"
```

```gherkin
SCENARIO: S03 - Restituzione messaggio per posti multipli
  GIVEN un valore intero pari a 50 passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN restituisce la stringa "50 posti disponibili"
```

```gherkin
SCENARIO: S04 - Gestione del caso limite zero negativo
  GIVEN un valore numerico pari a -0 (zero con segno negativo) passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore trattandolo come equivalente a 0
  THEN restituisce la stringa "Nessun posto disponibile"
```

```gherkin
SCENARIO: S05 - Gestione del limite superiore di capienza
  GIVEN un valore intero pari a 9999 passato alla funzione formatRemainingSeats
  WHEN la funzione elabora il valore
  THEN restituisce la stringa "9999 posti disponibili"
```

```gherkin
SCENARIO: S06 - Gestione del limite inferiore negativo
  GIVEN un valore intero pari a -1 passato alla funzione formatRemainingSeats
  WHEN la funzione tenta di elaborare il valore
  THEN solleva un TypeError con il messaggio "posti non validi"
```

```gherkin
SCENARIO: S07 - Gestione del superamento della capienza massima
  GIVEN un valore intero pari a 10000 passato alla funzione formatRemainingSeats
  WHEN la funzione tenta di elaborare il valore
  THEN solleva un TypeError con il messaggio "posti non validi"
```

```gherkin
SCENARIO: S08 - Gestione di valori frazionari
  GIVEN un valore numerico pari a 1.5 passato alla funzione formatRemainingSeats
  WHEN la funzione tenta di elaborare il valore
  THEN solleva un TypeError con il messaggio "posti non validi"
```

```gherkin
SCENARIO: S09 - Gestione di input NaN
  GIVEN un valore numerico pari a NaN passato alla funzione formatRemainingSeats
  WHEN la funzione tenta di elaborare il valore
  THEN solleva un TypeError con il messaggio "posti non validi"
```

```gherkin
SCENARIO: S10 - Gestione di input Infinity
  GIVEN un valore numerico pari a Infinity passato alla funzione formatRemainingSeats
  WHEN la funzione tenta di elaborare il valore
  THEN solleva un TypeError con il messaggio "posti non validi"
```

```gherkin
SCENARIO: S11 - Gestione di input Stringa numerica
  GIVEN una stringa contenente "2" passata alla funzione formatRemainingSeats
  WHEN la funzione tenta di elaborare il valore
  THEN solleva un TypeError con il messaggio "posti non validi"
```

```gherkin
SCENARIO: S12 - Gestione di input null
  GIVEN il valore null passato alla funzione formatRemainingSeats
  WHEN la funzione tenta di elaborare il valore
  THEN solleva un TypeError con il messaggio "posti non validi"
```

```gherkin
SCENARIO: S13 - Gestione di input undefined
  GIVEN il valore undefined passato alla funzione formatRemainingSeats
  WHEN la funzione tenta di elaborare il valore
  THEN solleva un TypeError con il messaggio "posti non validi"
```

```gherkin
SCENARIO: S14 - Gestione di input booleano true
  GIVEN il valore booleano true passato alla funzione formatRemainingSeats
  WHEN la funzione tenta di elaborare il valore
  THEN solleva un TypeError con il messaggio "posti non validi"
```

```gherkin
SCENARIO: S15 - Gestione di input booleano false
  GIVEN il valore booleano false passato alla funzione formatRemainingSeats
  WHEN la funzione tenta di elaborare il valore
  THEN solleva un TypeError con il messaggio "posti non validi"
```

## 4. Punti aperti

```json
{"open_points":[{"id":"OP-001","functionality":"FormatRemainingSeats","original_question":"Qual è il comportamento atteso per valori float interi come 2.0?", "question":"Il valore 2.0 (float) deve essere trattato come valido o invalido?", "assumption":null, "uncovered_scenarios":[], "reason":"missing_coverage", "research":{"status":"not_started","new_evidence":[],"verification":"agent_reported"}}]}
```
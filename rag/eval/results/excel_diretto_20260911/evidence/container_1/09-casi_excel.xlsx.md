Contenuto delle celle del workbook, letto direttamente dal file. Ogni tabella è un intervallo di celle con le coordinate originali: la prima colonna è il numero di riga, A, B, C… sono le lettere di colonna, non intestazioni dei dati. Una colonna vuota in tutto il foglio separa gli intervalli e una riga vuota ne separa i blocchi: separazioni geometriche, non tabelle dichiarate nel file; celle con lo stesso numero di riga stanno sulla stessa riga del foglio. Valori memorizzati nel file: formule non ricalcolate, numeri senza formato di visualizzazione, date e ore ISO. Formattazione, convalide e oggetti grafici non sono riportati.

## Registro

- Celle unite, valore solo nella prima cella: A1:F1.
- Formati numerici del file, non applicati ai valori mostrati: «0%» F3; «00000» C5; «\[h\]:mm:ss» B10; «dd/mm/yyyy\\ hh:mm:ss.000» C10; «h:mm:ss» D5; «yyyy\\-mm\\-dd» D3; «yyyy\\-mm\\-dd\\ hh:mm:ss» D4.
- Testo, non numero, data, booleano o errore: A3:A5, D9:F9.
- Collegamento F2: https://example.org/quota
- Commento A7 (Revisore): Nota sul totale

### A1:F5

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Registro casi |  |  |  |  |  |
| 2 | Codice | Stato | Quantità | Data | Importo | Quota |
| 3 | 00123 | NA | 3 | 2026-09-10 | 1200.5 | 0.12 |
| 4 | 00124 | N/A |  | 2026-09-11 00:00:00 | 0 | FALSE |
| 5 | 00125 | null | 7 | 00:00:00 | False | TRUE |

### A7:F7

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 7 | Totale |  | 10 |  | 1200.5 | 2401 |

### A9:F11

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 9 | Errori | #DIV/0! | #N/A | #N/A | TRUE | 0 |
| 10 | Durata | 36:00:00 | 2026-09-10 13:45:30.250 | a\|b | riga1<br>riga2 | \*grassetto\* \_x\_ codice_articolo \<b\>\&amp; |
| 11 | &#32;&#32;spazi&#32;&#32; | \\percorso\\ | \~\~barrato\~\~ | \`code\` | \[link\](http://x) | =non formula |

## Affiancate

### A1:B3

| Riga | A | B |
| --- | --- | --- |
| 1 | Voce | Euro |
| 2 | A | 12 |
| 3 | B | 7 |

### D1:E3

| Riga | D | E |
| --- | --- | --- |
| 1 | Persona | Anni |
| 2 | Ada | 30 |
| 3 | Bruno | 41 |

### A5:B6

| Riga | A | B |
| --- | --- | --- |
| 5 | Nota | Valore |
| 6 | x | 1 |

## Vuoto

- Nessuna cella con valore.

## Nascosto

- Foglio nascosto.

### A1

| Riga | A |
| --- | --- |
| 1 | valore nascosto |

## Unite

- Celle unite, valore solo nella prima cella: B2:C3, A5:A7.

### A2:D3

| Riga | A | B | C | D |
| --- | --- | --- | --- | --- |
| 2 |  | blocco |  | accanto |
| 3 |  |  |  |  |

### A5:D7

| Riga | A | B | C | D |
| --- | --- | --- | --- | --- |
| 5 | verticale |  |  |  |
| 6 |  |  |  |  |
| 7 |  |  |  |  |
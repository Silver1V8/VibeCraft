Contenuto delle celle del workbook, letto direttamente dal file. Ogni tabella è un intervallo di celle con le coordinate originali: la prima colonna è il numero di riga, A, B, C… sono le lettere di colonna, non intestazioni dei dati. Una colonna vuota in tutto il foglio separa gli intervalli e una riga vuota ne separa i blocchi: separazioni geometriche, non tabelle dichiarate nel file; celle con lo stesso numero di riga stanno sulla stessa riga del foglio. Valori memorizzati nel file: formule non ricalcolate, numeri senza formato di visualizzazione, date e ore ISO. Formattazione, convalide e oggetti grafici non sono riportati.

## Registro

- Celle unite, valore solo nella prima cella: A1:F1.
- Formati numerici del file, non applicati ai valori mostrati: «0%» F3:F5; «yyyy\\-mm\\-dd» D3:D4.
- Testo, non numero, data, booleano o errore: A3:A5.

### A1:F5

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Magazzino Nord registro 2026 |  |  |  |  |  |
| 2 | Codice | Stato | Quantità | Data | Importo € | Quota |
| 3 | 00123 | NA | 3 | 2026-09-10 | 1200.5 | 0.12 |
| 4 | 00124 | N/A |  | 2026-09-11 | 300 | 0.05 |
| 5 | 00125 | null | 7 |  | 0 | 1 |

### A7:F7

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 7 | Totale |  | 10 |  | 1500.5 | 2401 |

## Contatti città

### A1:B2

| Riga | A | B |
| --- | --- | --- |
| 1 | Nome | Città |
| 2 | Anna | Forlì |
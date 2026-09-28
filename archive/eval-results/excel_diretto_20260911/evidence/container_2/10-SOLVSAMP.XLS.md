Contenuto delle celle del workbook, letto direttamente dal file. Ogni tabella è un intervallo di celle con le coordinate originali: la prima colonna è il numero di riga, A, B, C… sono le lettere di colonna, non intestazioni dei dati. Una colonna vuota in tutto il foglio separa gli intervalli e una riga vuota ne separa i blocchi: separazioni geometriche, non tabelle dichiarate nel file; celle con lo stesso numero di riga stanno sulla stessa riga del foglio. Valori memorizzati nel file: formule non ricalcolate, numeri senza formato di visualizzazione, date e ore ISO. Formattazione, convalide e oggetti grafici non sono riportati.

## Panoramica

- Formati numerici del file, non applicati ai valori mostrati: «#,##0\_);(#,##0)» B5:F5, B7:F8, B10:F13; «0%» B16:F16; «0.0» C3:E3; «\[$L.-410\]\\ #,##0» B18:B19; «\[$L.-410\]\\ #,##0;\\-\[$L.-410\]\\ #,##0» B6:F6, B15:F15.

### A1:F3

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Panoramica del Risolutore di Microsoft Excel |  |  |  |  |  |
| 2 | Mese | T1 | T2 | T3 | T4 | Totale |
| 3 | Stagionalità | 0.9 | 1.1 | 0.8 | 1.2 |  |

### A5:F8

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | Unità vendute | 3591.5525890622844 | 4389.675386631681 | 3192.491190277586 | 4788.7367854163795 | 15962.455951387932 |
| 6 | Fatturato | 14366210.356249137 | 17558701.546526726 | 12769964.761110345 | 19154947.14166552 | 63849823.80555172 |
| 7 | Costo del venduto | 8978881.472655712 | 10974188.466579203 | 7981227.975693965 | 11971841.963540949 | 39906139.878469825 |
| 8 | Margine lordo | 5387328.883593425 | 6584513.079947524 | 4788736.78541638 | 7183105.178124569 | 23943683.927081898 |

### H6

| Riga | H |
| --- | --- |
| 6 | Codice colore |

### J8

| Riga | J |
| --- | --- |
| 8 | &#32;&#32;&#32;Cella obiettivo |

### A10:F13

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | Addetti alle vendite | 8000 | 8000 | 9000 | 9000 | 34000 |
| 11 | Budget pubblicitario | 10000 | 10000 | 10000 | 10000 | 40000 |
| 12 | Spese generali | 2154931.5534373703 | 2633805.2319790088 | 1915494.7141665516 | 2873242.0712498277 | 9577473.57083276 |
| 13 | Costo totale | 2172931.5534373703 | 2651805.2319790088 | 1934494.7141665516 | 2892242.0712498277 | 9651473.57083276 |

### J10

| Riga | J |
| --- | --- |
| 10 | &#32;&#32;&#32;Celle variabili |

### J12

| Riga | J |
| --- | --- |
| 12 | &#32;&#32;&#32;Vincoli |

### A15:F16

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 15 | Utile operativo | 3214397.330156055 | 3932707.847968515 | 2854242.0712498277 | 4290863.106874742 | 14292210.356249139 |
| 16 | Margine di profitto | 0.22374705997241845 | 0.2239748672501607 | 0.223512133717247 | 0.22400808914483133 | 0.22384103047448717 |

### A18:F19

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 18 | Prezzo unitario | 4000 |  |  |  |  |
| 19 | Costo unitario | 2500 |  |  |  |  |

### A21:F22

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 21 | I seguenti esempi mostrano come utilizzare il modello per determinare quale valore o valori ne minimizzano |  |  |  |  |  |
| 22 | o massimizzano un altro, per immettere e modificare vincoli e per salvare un modello di problema. |  |  |  |  |  |

### A24:F26

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 24 | Riga | Contiene |  | Spiegazione |  |  |
| 25 | 3 | Valori fissi |  | Fattore di stagionalità: le vendite crescono nei trimestri 2 e 4, |  |  |
| 26 |  |  |  | diminuiscono nei trimestri 1 e 3. |  |  |

### A28:F30

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 28 | 5 | =35\*B3\*(B11+3000)^0.5 |  | Previsione del volume delle vendite trimestrale: |  |  |
| 29 |  |  |  | la riga 3 contiene il fattore di stagionalità; |  |  |
| 30 |  |  |  | la riga 11 contiene le spese pubblicitarie. |  |  |

### A32:F33

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 32 | 6 | =B5\*$B$18 |  | Fatturato: volume delle vendite (riga 5) |  |  |
| 33 |  |  |  | per prezzo unitario (cella B18). |  |  |

### A35:F36

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 35 | 7 | =B5\*$B$19 |  | Costo del venduto: volume delle vendite (riga 5) |  |  |
| 36 |  |  |  | per costo unitario (cella B19). |  |  |

### A38:F39

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 38 | 8 | =B6-B7 |  | Margine lordo: fatturato (riga 6) |  |  |
| 39 |  |  |  | meno costo del venduto (riga 7). |  |  |

### A41:F41

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 41 | 10 | Valori fissi |  | Spese addetti alle vendite. |  |  |

### A43:F43

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 43 | 11 | Valori fissi |  | Budget pubblicitario (circa il 6.3% del fatturato). |  |  |

### A45:F46

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 45 | 12 | =0,15\*B6 |  | Spese generali: fatturato (riga 6) |  |  |
| 46 |  |  |  | per 15%. |  |  |

### A48:F49

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 48 | 13 | =SUM(B10:B12) |  | Totale costi: spese addetti alle vendite (riga 10) più |  |  |
| 49 |  |  |  | budget pubblicitario (riga 11) più spese generali (riga 12). |  |  |

### A51:F52

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 51 | 15 | =B8-B13 |  | Utile operativo: margine lordo (riga 8) meno costo totale |  |  |
| 52 |  |  |  | (riga 13). |  |  |

### A54:F55

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 54 | 16 | =B15/B6 |  | Margine di profitto: utile (riga 15) |  |  |
| 55 |  |  |  | diviso fatturato (riga 6). |  |  |

### A57:F57

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 57 | 18 | Valori fissi |  | Prezzo unitario. |  |  |

### A59:F59

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 59 | 19 | Valori fissi |  | Costo unitario. |  |  |

### A61:F64

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 61 | Questo è un tipico modello di marketing che rappresenta l'aumento delle vendite (a partire da una base |  |  |  |  |  |
| 62 | attribuibile all'attività del settore vendite) all'aumentare del budget pubblicitario, caratterizzato tuttavia da |  |  |  |  |  |
| 63 | rendimenti decrescenti. I primi 5 milioni di spese pubblicitarie in T1 aumentano le vendite di 1092 unità, |  |  |  |  |  |
| 64 | ma i successivi 5 le aumentano di sole 775 unità. |  |  |  |  |  |

### A66:F67

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 66 | È possibile utilizzare il Risolutore per determinare se il budget pubblicitario è insufficiente e se è opportuno |  |  |  |  |  |
| 67 | variarlo nel corso dell'anno per approfittare delle variazioni del fattore di stagionalità. |  |  |  |  |  |

### A69:F72

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 69 | Risoluzione per un valore massimizzandone un altro |  |  |  |  |  |
| 70 | Il Risolutore può essere utilizzato per determinare il valore massimo di una cella variandone un'altra.&#32; |  |  |  |  |  |
| 71 | Le due celle devono essere poste in relazione mediante le formule del foglio di lavoro. In caso contrario,&#32; |  |  |  |  |  |
| 72 | le modifiche apportate a una cella non avranno effetto sul valore nell'altra cella. |  |  |  |  |  |

### A74:F76

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 74 | Nel modello di foglio di lavoro, ad esempio, si desidera conoscere quanto è necessario spendere in |  |  |  |  |  |
| 75 | pubblicità per massimizzare gli utili nel primo trimestre. Si desidera variare la spesa pubblicitaria fino a |  |  |  |  |  |
| 76 | trovare quella che massimizza gli utili. |  |  |  |  |  |

### A78:F82

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 78 | n | Scegliere Risolutore dal menu Strumenti. Digitare b15 nella casella |  |  |  |  |
| 79 |  | Imposta cella obiettivo o selezionare la cella B15 (utile nel primo trimestre) |  |  |  |  |
| 80 |  | sul foglio di lavoro. Selezionare l'opzione Max. Digitare b11 nella casella |  |  |  |  |
| 81 |  | Cambiando le celle o selezionare la cella B11 (spesa pubblicitaria nel primo&#32; |  |  |  |  |
| 82 |  | trimestre) sul foglio di lavoro. Scegliere il pulsante Risolvi. |  |  |  |  |

### A84:F86

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 84 | Alcuni messaggi verranno visualizzati nella barra di stato mentre il problema viene impostato e risolto.&#32; |  |  |  |  |  |
| 85 | Verrà quindi confermata e visualizzata la soluzione del problema. Un budget pubblicitario di L.17.093.000 |  |  |  |  |  |
| 86 | genera un utile massimo di L.15.093.000. |  |  |  |  |  |

### A88:F89

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 88 | n | Dopo aver esaminato i risultati, selezionare Ripristina i valori originali e |  |  |  |  |
| 89 |  | scegliere OK per ignorare i risultati e ripristinare il valore originario nella cella B11. |  |  |  |  |

### A91:F91

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 91 | Reimpostazione delle opzioni del Risolutore |  |  |  |  |  |

### A93:F94

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 93 | Scegliere il pulsante Reimposta se si desidera ripristinare le impostazioni originarie delle opzioni&#32; |  |  |  |  |  |
| 94 | nella finestra di dialogo Parametri del Risolutore per passare a un nuovo problema. |  |  |  |  |  |

### A96:F103

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 96 | Risoluzione per un valore modificando più valori |  |  |  |  |  |
| 97 | . |  |  |  |  |  |
| 98 | È possibile utilizzare il Risolutore per risolvere per più valori contemporaneamente in modo da minimizzarne |  |  |  |  |  |
| 99 | o massimizzarne un altro. È possibile ad esempio individuare per ciascun trimestre il budget pubblicitario |  |  |  |  |  |
| 100 | che massimizza gli utili annuali. Dato che la stagionalità (riga 3) compare come fattore nel calcolo delle |  |  |  |  |  |
| 101 | unità vendute, è logico aumentare il budget pubblicitario in T4, quando sortisce l'effetto maggiore, |  |  |  |  |  |
| 102 | e diminuirlo in T3, quando l'effetto sulle vendite è minore. Utilizzare il Risolutore per determinare la |  |  |  |  |  |
| 103 | ripartizione trimestrale più redditizia. |  |  |  |  |  |

### A105:F109

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 105 | n | Scegliere Risolutore dal menu Strumenti. Digitare f15 nella casella |  |  |  |  |
| 106 |  | Imposta cella obiettivo o selezionare la cella F15 (utile operativo annuale)&#32; |  |  |  |  |
| 107 |  | sul foglio di lavoro. Selezionare l'opzione Max. Digitare b11:e11 nella casella&#32; |  |  |  |  |
| 108 |  | Cambiando le celle o selezionare le celle B11:E11 (spesa pubblicitaria in ciascun |  |  |  |  |
| 109 |  | &#32;&#32;trimestre) sul foglio di lavoro. Scegliere il pulsante Risolvi. |  |  |  |  |

### A111:F112

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 111 | n | Dopo aver esaminato i risultati, selezionare Ripristina i valori originali e |  |  |  |  |
| 112 |  | scegliere OK per ignorare i risultati e ripristinare i valori originari nelle celle. |  |  |  |  |

### A114:F118

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 114 | Questo è un problema di ottimizzazione non lineare di media complessità, consistente nel ricercare&#32; |  |  |  |  |  |
| 115 | i valori delle quattro incognite (celle B11-E11) che massimizzano gli utili. |  |  |  |  |  |
| 116 | Il problema è non lineare per la presenza di esponenti nelle formule nella riga 5. Il risultato della |  |  |  |  |  |
| 117 | ottimizzazione non vincolata mostra che è possibile aumentare gli utili annuali a L.79.706.000 con |  |  |  |  |  |
| 118 | un budget pubblicitario di L.89.706.000. |  |  |  |  |  |

### A120:F122

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 120 | Nella maggior parte dei modelli realistici si desidera tuttavia vincolare certi fattori limitanti. I vincoli possono |  |  |  |  |  |
| 121 | essere applicati alla cella obiettivo, alle celle variabili o a qualsiasi altro valore collegato alle formule nelle |  |  |  |  |  |
| 122 | celle. |  |  |  |  |  |

### A124:F124

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 124 | Aggiunta di un vincolo |  |  |  |  |  |

### A126:F129

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 126 | Il budget consente di recuperare le spese pubblicitarie e di aumentare gli utili, ma i vantaggi ottenuti |  |  |  |  |  |
| 127 | sono decrescenti. Nulla garantisce che l'attuale modello di correlazione tra vendite e pubblicità |  |  |  |  |  |
| 128 | sia valido anche il prossimo anno, specialmente a livelli di spesa crescenti. Non è quindi prudente |  |  |  |  |  |
| 129 | svincolare le spese pubblicitarie. |  |  |  |  |  |

### A131:F132

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 131 | Se si desidera mantenere invariato il budget pubblicitario a L.40.000.000, aggiungere al problema |  |  |  |  |  |
| 132 | un vincolo che limita le spese pubblicitarie annuali a L.40.000.000. |  |  |  |  |  |

### A134:F140

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 134 | n | Scegliere Risolutore dal menu Strumenti e fare clic sul pulsante Aggiungi. |  |  |  |  |
| 135 |  | Verrà visualizzata la finestra di dialogo Aggiungi vincolo. Nella casella |  |  |  |  |
| 136 |  | Riferimento digitare f11 o selezionare la cella F11 (spese pubblicitarie annuali) |  |  |  |  |
| 137 |  | sul foglio di lavoro. La cella F11 deve contenere un valore minore di o uguale a |  |  |  |  |
| 138 |  | L.40.000.000. La relazione predefinita nella casella Vincolo è \<= (minore di |  |  |  |  |
| 139 |  | o uguale a), quindi non è necessario modificarla. Nella casella a fianco digitare |  |  |  |  |
| 140 |  | 40000000, quindi scegliere OK e Risolvi. |  |  |  |  |

### A142:F143

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 142 | n | Dopo aver esaminato i risultati, selezionare Ripristina i valori originali e |  |  |  |  |
| 143 |  | scegliere OK per ignorare i risultati e ripristinare i valori originari nelle celle. |  |  |  |  |

### A145:F147

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 145 | La soluzione trovata ripartisce somme variabili da L.5.117.000 in T3 a L.15.263.000 in T4. |  |  |  |  |  |
| 146 | L'utile operativo passa da L.69.662.000 nel budget originario a L.71.447.000, senza aumentare |  |  |  |  |  |
| 147 | il budget pubblicitario. |  |  |  |  |  |

### A149:F149

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 149 | Modifica di un vincolo |  |  |  |  |  |

### A151:F154

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 151 | Utilizzando il Risolutore di Microsoft Excel è possibile sperimentare con parametri leggermente differenti per |  |  |  |  |  |
| 152 | stabilire la soluzione ottimale a un problema. È possibile modificare un vincolo per verificare se i risultati |  |  |  |  |  |
| 153 | migliorano o peggiorano. Nel modello di foglio di lavoro provare ad aumentare il vincolo sulle spese |  |  |  |  |  |
| 154 | pubblicitarie a L.50.000.000 per verificarne gli effetti sull'utile annuale. |  |  |  |  |  |

### A156:F160

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 156 | n | Scegliere Risolutore dal menu Strumenti. Il vincolo $F$11\<=40000000 |  |  |  |  |
| 157 |  | dovrebbe già essere selezionato nella casella Vincoli. Scegliere il pulsante |  |  |  |  |
| 158 |  | Modifica. Nella casella Vincolo modificare 40000000 in 50000000. |  |  |  |  |
| 159 |  | Scegliere OK, quindi Risolvi. Fare clic su Mantieni la soluzione del Risolutore, |  |  |  |  |
| 160 |  | quindi scegliere OK per mantenere i risultati visualizzati sullo schermo. |  |  |  |  |

### A162:F166

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 162 | La soluzione ottimale genera un utile annuale di L.74.817.000, pari a un aumento di L.3.370.000 rispetto |  |  |  |  |  |
| 163 | all'importo precedente di L.71.447.000. Un investimento incrementale di L.10.000.000 che generi un |  |  |  |  |  |
| 164 | aumento degli utili di L.3.370.000, pari a una redditività del 33,7%, è quasi sempre valido dal punto di vista |  |  |  |  |  |
| 165 | finanziario. Rispetto al risultato non vincolato, questa soluzione comporta un assottigliamento degli utili di&#32; |  |  |  |  |  |
| 166 | L.4.889.000, ma anche una riduzione delle spese di L.39.706.000. |  |  |  |  |  |

### A168:F168

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 168 | Salvataggio di un modello di problema |  |  |  |  |  |

### A170:F174

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 170 | Scegliendo Salva dal menu File, le ultime selezioni nella finestra di dialogo Parametri del Risolutore |  |  |  |  |  |
| 171 | vengono incollate al foglio di lavoro e mantenute durante il salvataggio. È tuttavia possibile definire più |  |  |  |  |  |
| 172 | problemi per foglio di lavoro salvandoli individualmente mediante il pulsante Salva modello nella |  |  |  |  |  |
| 173 | finestra di dialogo Opzioni del Risolutore. Ciascun modello di problema consiste in celle e vincoli |  |  |  |  |  |
| 174 | immessi nella finestra di dialogo Parametri del Risolutore. |  |  |  |  |  |

### A176:F178

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 176 | Scegliendo Salva modello, verrà visualizzata la finestra di dialogo Salva modello, con una selezione |  |  |  |  |  |
| 177 | predefinita basata sulla cella attiva come area per salvare il modello. L'intervallo consigliato include una cella |  |  |  |  |  |
| 178 | per ciascun vincolo più tre celle aggiuntive. Assicurarsi che l'intervallo di celle sul foglio di lavoro sia vuoto. |  |  |  |  |  |

### A180:F182

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 180 | n | Scegliere Risolutore dal menu Strumenti e fare clic sul pulsante Opzioni. |  |  |  |  |
| 181 |  | Scegliere il pulsante Salva modello. Nella casella Seleziona area del modello, |  |  |  |  |
| 182 |  | digitare h15:h18 o selezionare le celle H15:H18 sul foglio di lavoro. Scegliere OK. |  |  |  |  |

### A184:F186

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 184 | Nota  È possibile immettere un riferimento a una singola cella nella casella |  |  |  |  |  |
| 185 | Seleziona area del modello. Il riferimento verrà utilizzato come angolo |  |  |  |  |  |
| 186 | superiore sinistro dell'intervallo in cui verranno copiati i dati del problema. |  |  |  |  |  |

### A189:F191

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 189 | Per caricare i dati del problema in un secondo momento, scegliere il pulsante Carica modello nella |  |  |  |  |  |
| 190 | finestra di dialogo Opzioni del Risolutore, digitare h15:h18 nella casella Area del modello o |  |  |  |  |  |
| 191 | selezionare le celle H15:H18 sul modello di foglio di lavoro, quindi scegliere OK. |  |  |  |  |  |

### A193:F194

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 193 | Verrà visualizzato un messaggio per chiedere se si desidera uniformare le impostazioni correnti delle |  |  |  |  |  |
| 194 | opzioni del Risolutore alle impostazioni del modello che si sta caricando. Scegliere OK per procedere. |  |  |  |  |  |

## Mix di prodotti

- Formati numerici del file, non applicati ai valori mostrati: «"L."\\ #,##0;\\-"L."\\ #,##0» D17:F17, D18; «0» D9:F9, C11:C15.

### A1:F5

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Esempio 1:mix di prodotti con margine di profitto decrescente. |  |  |  |  |  |
| 2 | Un'azienda produce televisori, impianti stereo e altoparlanti utilizzando una scorta comune per trasformatori, |  |  |  |  |  |
| 3 | coni ecc. I componenti sono disponibili in quantità limitata e si deve determinare il mix di prodotti più redditizio. |  |  |  |  |  |
| 4 | Si consideri che il profitto per unità fabbricata diminuisce con l'aumentare del volume perchè si rendono |  |  |  |  |  |
| 5 | necessari degli ulteriori incentivi di prezzo per caricare il canale di distribuzione. |  |  |  |  |  |

### J2

| Riga | J |
| --- | --- |
| 2 | Codice colore |

### L4

| Riga | L |
| --- | --- |
| 4 | Cella obiettivo |

### L6

| Riga | L |
| --- | --- |
| 6 | Celle variabili |

### A8:F18

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 8 |  |  |  | Televisori | Imp. stereo | Altoparlanti |
| 9 |  |  | Unità da produrre-\> | 100 | 100 | 100 |
| 10 | Componente | Scorta | Unità usate |  |  |  |
| 11 | Telaio | 450 | 200 | 1 | 1 | 0 |
| 12 | Tubo catodico | 250 | 100 | 1 | 0 | 0 |
| 13 | Cono | 800 | 500 | 2 | 2 | 1 |
| 14 | Alternatore | 450 | 200 | 1 | 1 | 0 |
| 15 | Diodi | 600 | 400 | 2 | 1 | 1 |
| 16 |  |  |  | Profitti (in migliaia di Lire): |  |  |
| 17 |  |  | Per prodotto | 4732.180083601453 | 3154.7867224009683 | 2208.350705680678 |
| 18 |  |  | Totale | 10095.317511683099 |  |  |

### L8

| Riga | L |
| --- | --- |
| 8 | Vincoli |

### H12:H15

| Riga | H |
| --- | --- |
| 12 | Esponente&#32; |
| 13 | di diminuzione |
| 14 | dei ricavi: |
| 15 | 0.9 |

### A20:F22

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 20 | Questo modello fornisce dati per molti prodotti utilizzando componenti comuni, ciascuno con un differente |  |  |  |  |  |
| 21 | margine di profitto unitario. Le scorte sono limitate e il problema consiste nel determinare quante unità |  |  |  |  |  |
| 22 | produrre con le scorte disponibili per massimizzare i profitti. |  |  |  |  |  |

### A24:F24

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 24 | Dati del problema |  |  |  |  |  |

### A26:F26

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 26 | Cella obiettivo |  | D18 |  | L'obiettivo è massimizzare i profitti. |  |

### A28:F28

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 28 | Celle variabili |  | D9:F9 |  | Numero di unità da produrre per ciascun prodotto. |  |

### A30:F31

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 30 | Vincoli |  | C11:C15\<=B11:B15 |  | Il numero dei componenti utilizzati non può essere |  |
| 31 |  |  |  |  | superiore al numero dei componenti in magazzino. |  |

### A33:F34

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 33 |  |  | D9:F9\>=0 |  | Il numero di unità da produrre deve essere maggiore |  |
| 34 |  |  |  |  | o uguale a 0. |  |

### A36:F39

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 36 | Le formule del profitto per prodotto nelle celle D17-F17 includono il fattore ^H15 per mostrare che il profitto |  |  |  |  |  |
| 37 | unitario decresce all'aumentare del volume di produzione. H15 contiene 0,9 che rende il problema non lineare. |  |  |  |  |  |
| 38 | Se si immette il valore 1,0 in H15 per indicare che il profitto unitario rimane costante al variare del volume |  |  |  |  |  |
| 39 | e si sceglie il pulsante Risolvi, la soluzione ottimale cambierà. Questa modifica rende il problema lineare. |  |  |  |  |  |

## Trasporti

- Formati numerici del file, non applicati ai valori mostrati: «"L."\\ #,##0;\\-"L."\\ #,##0» C16:G18, B20:G20; «0» B8:G10, C12:G12, C14:G14, B16:B18.

### A1:G4

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Esempio 2: trasporti. |  |  |  |  |  |  |
| 2 | Minimizzare i costi di spedizione della merce dagli stabilimenti ai magazzini nelle aree metropolitane senza |  |  |  |  |  |  |
| 3 | superare la capacità produttiva di ciascun stabilimento e soddisfacendo la domanda di ciascuna |  |  |  |  |  |  |
| 4 | area metropolitana. |  |  |  |  |  |  |

### A6:G12

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6 |  |  | Numero di spedizioni dallo stabilimento x al magazzino y: |  |  |  |  |
| 7 | Stabilimenti: | Totale | Torino | Milano | Roma | Napoli | Palermo |
| 8 | Gioia Tauro | 5 | 1 | 1 | 1 | 1 | 1 |
| 9 | Caserta | 5 | 1 | 1 | 1 | 1 | 1 |
| 10 | Marghera | 5 | 1 | 1 | 1 | 1 | 1 |
| 11 |  |  | --- | --- | --- | --- | --- |
| 12 | Totale: |  | 3 | 3 | 3 | 3 | 3 |

### J6

| Riga | J |
| --- | --- |
| 6 | Codice colore |

### L8

| Riga | L |
| --- | --- |
| 8 | &#32;&#32;&#32;Cella obiettivo |

### L10

| Riga | L |
| --- | --- |
| 10 | &#32;&#32;&#32;Celle variabili |

### L12

| Riga | L |
| --- | --- |
| 12 | &#32;&#32;&#32;Vincoli |

### A14:G18

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 14 |  | Domanda dei magazzini --\> | 180 | 80 | 200 | 160 | 220 |
| 15 | Stabilimenti: | Scorta | Costi di spedizione dallo stabilimento x al magazzino y (in migliaia di Lire): |  |  |  |  |
| 16 | Gioia Tauro | 310 | 10 | 8 | 6 | 5 | 4 |
| 17 | Caserta | 260 | 6 | 5 | 4 | 3 | 6 |
| 18 | Marghera | 280 | 3 | 4 | 5 | 5 | 9 |

### A20:G20

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 20 | Spedizione: | 83 | 19 | 17 | 15 | 13 | 19 |

### A22:G26

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 22 | Il problema esposto nel modello riguarda la spedizione di merci da tre stabilimenti a cinque magazzini |  |  |  |  |  |  |
| 23 | regionali. Le merci possono essere spedite da qualsiasi stabilimento a qualsiasi magazzino, ma i costi&#32; |  |  |  |  |  |  |
| 24 | diminuiscono minimizzando le distanze. Il problema consiste nel determinare quanta merce spedire&#32; |  |  |  |  |  |  |
| 25 | da ciascun stabilimento a ciascun magazzino per soddisfare la domanda regionale senza eccedere&#32; |  |  |  |  |  |  |
| 26 | la capacità produttiva e minimizzando i costi di trasporto. |  |  |  |  |  |  |

### A28:G28

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 28 | Dati del problema |  |  |  |  |  |  |

### A30:G30

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 30 | Cella obiettivo |  | B20 |  | L'obiettivo è minimizzare i costi di trasporto totali. |  |  |

### A32:G33

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 32 | Celle variabili |  | C8:G10 |  | Quantità da spedire da ciascun stabilimento |  |  |
| 33 |  |  |  |  | a ciascun magazzino. |  |  |

### A35:G36

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 35 | Vincoli |  | B8:B10\<=B16:B18 |  | Il volume delle spedizioni non può eccedere |  |  |
| 36 |  |  |  |  | la capacità produttiva dello stabilimento. |  |  |

### A38:G39

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 38 |  |  | C12:G12\>=C14:G14 |  | I volumi di merce spediti ai magazzini devono |  |  |
| 39 |  |  |  |  | essere maggiori o uguali alla domanda. |  |  |

### A41:G42

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 41 |  |  | C8:G10\>=0 |  | Il numero di spedizioni deve essere maggiore&#32; |  |  |
| 42 |  |  |  |  | o uguale a 0. |  |  |

### A44:G47

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 44 | Il problema può essere risolto più rapidamente selezionando la casella di controllo |  |  |  |  |  |  |
| 45 | Presupponi modello lineare nella finestra di dialogo Opzioni del Risolutore prima di scegliere&#32; |  |  |  |  |  |  |
| 46 | il pulsante Risolvi. Un problema di questo tipo presenta una soluzione ottimale in cui le quantità da |  |  |  |  |  |  |
| 47 | spedire sono numeri interi, se tutti i vincoli della produzione e della domanda sono numeri interi. |  |  |  |  |  |  |

## Gestione del personale

- Formati numerici del file, non applicati ai valori mostrati: «"L."\\ #,##0;\\-"L."\\ #,##0» D19:D20; «0» D7:D13, F7:L13, D15, F15:L15, F17:L17.

### A1:L3

| Riga | A | B | C | D | E | F | G | H | I | J | K | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Esempio 3: pianificazione del personale per un parco divertimenti. |  |  |  |  |  |  |  |  |  |  |  |
| 2 | I dipendenti prestano servizio 5 giorni consecutivi seguiti da due giorni liberi. Determinare la turnazione che |  |  |  |  |  |  |  |  |  |  |  |
| 3 | soddisfa la richiesta di presenze determinata dall'afflusso di clienti e minimizza i costi di manodopera. |  |  |  |  |  |  |  |  |  |  |  |

### A6:L13

| Riga | A | B | C | D | E | F | G | H | I | J | K | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6 | Turno | Giorni liberi |  | Dipendenti |  | Lun | Mar | Mer | Gio | Ven | Sab | Dom |
| 7 | &#32;&#32;A | Dom, Lun |  | 4 |  | 0 | 0 | 1 | 1 | 1 | 1 | 1 |
| 8 | &#32;&#32;B | Lun, Mar |  | 4 |  | 1 | 0 | 0 | 1 | 1 | 1 | 1 |
| 9 | &#32;&#32;C | Mar, Mer |  | 4 |  | 1 | 1 | 0 | 0 | 1 | 1 | 1 |
| 10 | &#32;&#32;D | Mer, Gio |  | 6 |  | 1 | 1 | 1 | 0 | 0 | 1 | 1 |
| 11 | &#32;&#32;E | Gio, Ven |  | 6 |  | 1 | 1 | 1 | 1 | 0 | 0 | 1 |
| 12 | &#32;&#32;F | Ven, Sab |  | 4 |  | 1 | 1 | 1 | 1 | 1 | 0 | 0 |
| 13 | &#32;&#32;G | Sab, Dom |  | 4 |  | 0 | 1 | 1 | 1 | 1 | 1 | 0 |

### N6

| Riga | N |
| --- | --- |
| 6 | Codice colore |

### P8

| Riga | P |
| --- | --- |
| 8 | &#32;&#32;&#32;Cella obiettivo |

### P10

| Riga | P |
| --- | --- |
| 10 | &#32;&#32;&#32;Celle variabili |

### P12

| Riga | P |
| --- | --- |
| 12 | &#32;&#32;&#32;Vincoli |

### A15:L15

| Riga | A | B | C | D | E | F | G | H | I | J | K | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 15 |  |  | Turni totali: | 32 |  | 24 | 24 | 24 | 22 | 20 | 22 | 24 |

### A17:L17

| Riga | A | B | C | D | E | F | G | H | I | J | K | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 17 |  |  | Domanda totale: |  |  | 22 | 17 | 13 | 14 | 15 | 18 | 24 |

### A19:L20

| Riga | A | B | C | D | E | F | G | H | I | J | K | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 19 |  | Paga/dipend./giorno: |  | 40000 |  |  |  |  |  |  |  |  |
| 20 |  | Paghe/settimana: |  | 1280000 |  |  |  |  |  |  |  |  |

### A22:L25

| Riga | A | B | C | D | E | F | G | H | I | J | K | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 22 | L'obiettivo del modello è strutturare i turni dei dipendenti in modo da disporre di sufficiente personale minimizzando |  |  |  |  |  |  |  |  |  |  |  |
| 23 | i costi di manodopera. Nell'esempio tutti i dipendenti ricevono la stessa retribuzione oraria, quindi minimizzando il |  |  |  |  |  |  |  |  |  |  |  |
| 24 | numero di dipendenti in servizio in ciascuna giornata si minimizzano anche i costi. Ciascun dipendente presta |  |  |  |  |  |  |  |  |  |  |  |
| 25 | servizio cinque giorni consecutivi seguiti da due giorni liberi. |  |  |  |  |  |  |  |  |  |  |  |

### A27:L27

| Riga | A | B | C | D | E | F | G | H | I | J | K | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 27 | Dati del problema |  |  |  |  |  |  |  |  |  |  |  |

### A29:L29

| Riga | A | B | C | D | E | F | G | H | I | J | K | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 29 | Cella obiettivo |  | D20 |  | L'obiettivo è minimizzare le spese di manodopera. |  |  |  |  |  |  |  |

### A31:L31

| Riga | A | B | C | D | E | F | G | H | I | J | K | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 31 | Celle variabili |  | D7:D13 |  | Dipendenti in servizio in ciascuna giornata. |  |  |  |  |  |  |  |

### A33:L33

| Riga | A | B | C | D | E | F | G | H | I | J | K | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 33 | Vincoli |  | D7:D13\>=0 |  | Il numero di dipendenti deve essere maggiore o uguale a 0. |  |  |  |  |  |  |  |

### A35:L35

| Riga | A | B | C | D | E | F | G | H | I | J | K | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 35 |  |  | D7:D13=Numero intero |  | Il numero di dipendenti deve essere un numero intero. |  |  |  |  |  |  |  |

### A37:L38

| Riga | A | B | C | D | E | F | G | H | I | J | K | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 37 |  |  | F15:L15\>=F17:L17 |  | In ciascuna giornata deve prestare servizio un numero di |  |  |  |  |  |  |  |
| 38 |  |  |  |  | dipendenti maggiore o uguale alla domanda. |  |  |  |  |  |  |  |

### A40:L40

| Riga | A | B | C | D | E | F | G | H | I | J | K | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 40 | Turni possibili |  | Righe 7-13 |  | 1 significa che il dipendente assegnato al turno è in servizio. |  |  |  |  |  |  |  |

### A42:L44

| Riga | A | B | C | D | E | F | G | H | I | J | K | L |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 42 | Nell'esempio si utilizza un numero intero come vincolo in modo che le soluzioni non includano frazioni di dipendente&#32; |  |  |  |  |  |  |  |  |  |  |  |
| 43 | in alcun turno. Selezionando la casella di controllo Presupponi modello lineare nella finestra di dialogo |  |  |  |  |  |  |  |  |  |  |  |
| 44 | Opzioni del Risolutore prima di scegliere il pulsante Risolvi, il procedimento di soluzione verrà accelerato. |  |  |  |  |  |  |  |  |  |  |  |

## Massimizzazione del reddito

- Formati numerici del file, non applicati ai valori mostrati: «"L."\\ #,##0;\[Red\]\\-"L."\\ #,##0» B11:H11, C12:H13, B14:G14, B15:B16, E15, B17:H18, B20; «"L."\\ #,##0;\\-"L."\\ #,##0» H8; «0.0%» B6:B8.
- Testo, non numero, data, booleano o errore: E8.

### A1:H3

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Esempio 4: gestione del capitale. |  |  |  |  |  |  |  |
| 2 | Determinare la modalità di investimento della liquidità in eccesso in certificati di deposito a 1, 3 e 6 mesi, in modo da |  |  |  |  |  |  |  |
| 3 | massimizzare il reddito da interessi e soddisfare la richiesta di liquidità dell'azienda, includendo un margine di sicurezza. |  |  |  |  |  |  |  |

### A5:H8

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 |  | Rendimento | Durata |  | Acquistare nei mesi: |  |  |  |
| 6 | Certificato di deposito a 1 mese: | 0.01 | 1 |  | 1, 2, 3, 4, 5 e 6 |  |  | Interessi |
| 7 | Certificato di deposito a 3 mesi: | 0.04 | 3 |  | 1 e 4 |  |  | &#32;percepiti: |
| 8 | Certificato di deposito a 6 mesi: | 0.09 | 6 |  | 1 |  | Totale | 7700 |

### A10:H18

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10 | Mese: | Mese 1 | Mese 2 | Mese 3 | Mese 4 | Mese 5 | Mese 6 | Fine |
| 11 | Cassa iniziale: | 400000 | 205000 | 216000 | 237000 | 158400 | 109400 | 125400 |
| 12 | Cert. di depo. maturati: |  | 100000 | 100000 | 110000 | 100000 | 100000 | 120000 |
| 13 | Interesse: |  | 1000 | 1000 | 1400 | 1000 | 1000 | 2300 |
| 14 | Cert. di dep. a 1 mese: | 100000 | 100000 | 100000 | 100000 | 100000 | 100000 |  |
| 15 | Cert. di dep. a 3 mesi: | 10000 |  |  | 10000 |  |  |  |
| 16 | Cert. di dep. a 6 mesi: | 10000 |  |  |  |  |  |  |
| 17 | Utilizzo di cassa: | 75000 | -10000 | -20000 | 80000 | 50000 | -15000 | 60000 |
| 18 | Cassa finale: | 205000 | 216000 | 237000 | 158400 | 109400 | 125400 | 187700 |

### J10

| Riga | J |
| --- | --- |
| 10 | Codice colore |

### L12

| Riga | L |
| --- | --- |
| 12 | &#32;&#32;&#32;Cella obiettivo |

### L14

| Riga | L |
| --- | --- |
| 14 | &#32;&#32;&#32;Celle variabili |

### L16

| Riga | L |
| --- | --- |
| 16 | &#32;&#32;&#32;Vincoli |

### A20:H20

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 20 |  | -290000 |  |  |  |  |  |  |

### A22:H24

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 22 | Uno dei compiti di un direttore finanziario o di un manager è gestire la liquidità e gli investimenti a breve termine in modo |  |  |  |  |  |  |  |
| 23 | da massimizzare il flusso reddituale degli stessi, mantenendoli disponibili per coprire le spese. È necessario conciliare la |  |  |  |  |  |  |  |
| 24 | maggiore remunerazione tipica dagli investimenti a lungo termine e la flessibilità ottenuta investendo i fondi a breve termine. |  |  |  |  |  |  |  |

### A26:H27

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 26 | Il modello calcola la cassa finale in base alla cassa iniziale, riportata dal mese precedente, alle entrate provenienti dai certificati |  |  |  |  |  |  |  |
| 27 | di deposito in scadenza, alle uscite per acquisto di nuovi certificati e alle uscite di cassa mensili per la gestione aziendale. |  |  |  |  |  |  |  |

### A29:H30

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 29 | Le nove decisioni da prendere riguardano: gli importi da investire in certificati a un mese nei mesi da 1 a 6, gli importi |  |  |  |  |  |  |  |
| 30 | da investire in certificati a tre mesi nei mesi 1 e 4, infine l'importo da investire in certificati a sei mesi nel mese 1. |  |  |  |  |  |  |  |

### A32:H32

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 32 | Dati del problema |  |  |  |  |  |  |  |

### A34:H34

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 34 | Cella obiettivo |  | H8 |  | L'obiettivo è massimizzare l'interesse percepito. |  |  |  |

### A36:H37

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 36 | Celle variabili |  | B14:G14 |  | Importi investiti in ciascun tipo di certificato. |  |  |  |
| 37 |  |  | B15, E15, B16 |  |  |  |  |  |

### A39:H41

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 39 | Vincoli |  | B14:G14\>=0 |  | L'investimento in ciascun tipo di certificato deve |  |  |  |
| 40 |  |  | B15:B16\>=0 |  | essere maggiore o uguale a 0. |  |  |  |
| 41 |  |  | E15\>=0 |  |  |  |  |  |

### A43:H44

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 43 |  |  | B18:H18\>=100000 |  | La cassa finale deve essere maggiore o uguale a |  |  |  |
| 44 |  |  |  |  | L.100.000.000. |  |  |  |

### A46:H47

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 46 | La soluzione ottimale genera un reddito da interessi pari a L.16.531.000 preferenziando i certificati a sei e a tre mesi,&#32; |  |  |  |  |  |  |  |
| 47 | pur nel pieno rispetto dei vincoli. |  |  |  |  |  |  |  |

### A49:H50

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 49 | Si supponga, tuttavia, di dover disporre di liquidità sufficiente al pagamento di macchinari nel mese 5. Aggiungere |  |  |  |  |  |  |  |
| 50 | un vincolo tale che la durata media degli investimenti in carico al mese 1 non sia maggiore di quattro mesi. |  |  |  |  |  |  |  |

### A52:H56

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 52 | La formula nella cella B20 calcola il totale degli importi investiti nel mese 1 (B14, B15 e B16), ponderati in base alla |  |  |  |  |  |  |  |
| 53 | durata (1, 3 e 6 mesi), quindi sottrae dall'importo l'investimento totale, ponderato per il fattore 4. Se il risultato è |  |  |  |  |  |  |  |
| 54 | minore o uguale a zero, la durata media non eccede quattro mesi. Per aggiungere questo vincolo, ripristinare i valori |  |  |  |  |  |  |  |
| 55 | originali, quindi scegliere Risolutore dal menu Strumenti. Scegliere il pulsante Aggiungi. Digitare b20 nella casella |  |  |  |  |  |  |  |
| 56 | Riferimento, digitare 0 nella casella Vincoli, quindi scegliere OK. Per risolvere il problema digitare Risolvi. |  |  |  |  |  |  |  |

### A58:H62

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 58 | Per soddisfare il vincolo della durata di quattro mesi, la liquidità viene spostata dai certificati a sei mesi a quelli a tre mesi |  |  |  |  |  |  |  |
| 59 | e giunge a scadenza nel mese 4. Secondo il piano, è reinvestita in nuovi certificati a tre mesi. In caso di necessità |  |  |  |  |  |  |  |
| 60 | è possibile non reinvestire la liquidità e mantenerla immediatamente disponibile. L'importo di L.56.896.000 in scadenza |  |  |  |  |  |  |  |
| 61 | nel mese 4 è più che sufficiente a coprire l'uscita per pagamento macchinari nel mese 5. Per ottenere questa flessibilità |  |  |  |  |  |  |  |
| 62 | si deve rinunciare a circa L.460.000 di interessi. |  |  |  |  |  |  |  |

## Portafoglio titoli

- Formati numerici del file, non applicati ai valori mostrati: «0.0%» C6:C7, G6:G7, E10:E14, E16, E18, G18; «0.00» B10:C14; «0.000» F10:G14, F16:G16.

### A1:G4

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Esempio 5: portafoglio titoli. |  |  |  |  |  |  |
| 2 | Determinare la ponderazione di titoli in un portafoglio efficiente che massimizzi la redditività&#32; |  |  |  |  |  |  |
| 3 | per un dato livello di rischio. Il foglio utilizza il modello ad indicizzazione singola di Sharpe.&#32; |  |  |  |  |  |  |
| 4 | Se i termini della covarianza sono disponibili è anche possibile utilizzare il metodo di Markowitz. |  |  |  |  |  |  |

### A6:G7

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6 | Tasso a rischio zero |  | 0.06 |  | Varianza di mercato |  | 0.03 |
| 7 | Tasso di mercato |  | 0.15 |  | Peso massimo |  | 1 |

### A9:G14

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 9 |  | Beta | Varianza res. |  | Peso | \*Beta | \*Var. |
| 10 | Titolo A | 0.8 | 0.04 |  | 0.2 | 0.16000000000000003 | 0.0016000000000000003 |
| 11 | Titolo B | 1 | 0.2 |  | 0.2 | 0.2 | 0.008000000000000002 |
| 12 | Titolo C | 1.8 | 0.12 |  | 0.2 | 0.36000000000000004 | 0.0048000000000000004 |
| 13 | Titolo D | 2.2 | 0.4 |  | 0.2 | 0.44000000000000006 | 0.016000000000000004 |
| 14 | Buoni del Tesoro | 0 | 0 |  | 0.2 | 0 | 0 |

### I9

| Riga | I |
| --- | --- |
| 9 | Codice colore |

### K11

| Riga | K |
| --- | --- |
| 11 | &#32;&#32;&#32;Cella obiettivo |

### K13

| Riga | K |
| --- | --- |
| 13 | &#32;&#32;&#32;Celle variabili |

### K15

| Riga | K |
| --- | --- |
| 15 | &#32;&#32;&#32;Vincoli |

### A16:G18

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | Totale |  |  |  | 1 | 1.1600000000000001 | 0.030400000000000007 |
| 17 |  |  |  |  | Rendimento |  | Varianza |
| 18 |  |  | Portafoglio:&#32;&#32; |  | 0.1644 |  | 0.07076800000000001 |

### A20:G29

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 20 | Rendimento massimo: A21:A29 |  |  | Rischio minimo: D21:D29 |  |  |  |
| 21 | 0.1644 |  |  | 0.07076800000000001 |  |  |  |
| 22 | 5 |  |  | 5 |  |  |  |
| 23 | TRUE |  |  | TRUE |  |  |  |
| 24 | TRUE |  |  | TRUE |  |  |  |
| 25 | TRUE |  |  | TRUE |  |  |  |
| 26 | TRUE |  |  | TRUE |  |  |  |
| 27 | TRUE |  |  | TRUE |  |  |  |
| 28 | TRUE |  |  | TRUE |  |  |  |
| 29 | TRUE |  |  | TRUE |  |  |  |

### A31:G33

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 31 | Uno dei principi fondamentali della gestione degli investimenti è la diversificazione. Componendo un portafoglio |  |  |  |  |  |  |
| 32 | formato da più titoli è possibile ottenere un tasso di rendimento pari alla media dei rendimenti dei singoli titoli, |  |  |  |  |  |  |
| 33 | riducendo al contempo il rischio in caso di perdite su un titolo. |  |  |  |  |  |  |

### A35:G36

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 35 | Questo modello può essere utilizzato per individuare quale ripartizione degli investimenti tra i vari titoli minimizza |  |  |  |  |  |  |
| 36 | il rischio per un dato tasso di rendimento o massimizza il rendimento per un dato livello di rischio. |  |  |  |  |  |  |

### A38:G40

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 38 | Il foglio di lavoro include il coefficiente beta (rischio di mercato) e la varianza residua relativi a quattro titoli.&#32; |  |  |  |  |  |  |
| 39 | Inoltre il portafoglio comprende un investimento in Buoni del Tesoro, considerati esenti da rischio e a varianza |  |  |  |  |  |  |
| 40 | nulla. Inizialmente vengono investiti importi uguali (pari al 20% del portafoglio) in ciascun titolo. |  |  |  |  |  |  |

### A42:G44

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 42 | Utilizzare il Risolutore per provare differenti ripartizioni di portafoglio in modo da massimizzare il rendimento del |  |  |  |  |  |  |
| 43 | portafoglio per un dato livello di rischio o minimizzare il rischio per un dato tasso di rendimento. Scegliendo una |  |  |  |  |  |  |
| 44 | ripartizione iniziale uniforme in cinque titoli, il rendimento del portafoglio è pari al 16,4% e la varianza al 7,1%. |  |  |  |  |  |  |

### A46:G46

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 46 | Dati del problema |  |  |  |  |  |  |

### A48:G49

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 48 | Cella obiettivo |  |  | E18 |  | L'obiettivo è massimizzare il rendimento del |  |
| 49 |  |  |  |  |  | portafoglio. |  |

### A51:G51

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 51 | Celle variabili |  |  | E10:E14 |  | Peso di ciascun titolo. |  |

### A53:G53

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 53 | Vincoli |  |  | E10:E14\>=0 |  | Il peso deve essere maggiore o uguale a 0. |  |

### A55:G55

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 55 |  |  |  | E16=1 |  | Il peso deve essere uguale a 1. |  |

### A57:G57

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 57 |  |  |  | G18\<=0,071 |  | La varianza deve essere minore o uguale a 0,071. |  |

### A59:G59

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 59 | Coefficiente beta di ciascun titolo |  |  | B10:B13 |  |  |  |

### A61:G61

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 61 | Varianza di ciascun titolo |  |  | C10:C13 |  |  |  |

### A63:G67

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 63 | Le celle D21:D29 contengono i dati del problema per minimizzare il rischio a fronte di un tasso di rendimento |  |  |  |  |  |  |
| 64 | atteso del 16,4%. Per caricare i dati nel Risolutore, scegliere Risolutore dal menu Strumenti. Scegliere il |  |  |  |  |  |  |
| 65 | pulsante Opzioni, fare clic su Carica modello, selezionare le celle D21:D29 sul foglio di lavoro, quindi scegliere |  |  |  |  |  |  |
| 66 | OK finché viene visualizzata la finestra di dialogo Parametri del Risolutore. Scegliere il pulsante Risolvi. |  |  |  |  |  |  |
| 67 | In entrambi i casi verranno proposte ripartizioni di portafoglio che superano la regola della ripartizione uniforme. |  |  |  |  |  |  |

### A69:G70

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 69 | È possibile ottenere un rendimento maggiore (17,1%) a parità di rischio o ridurre il richio senza intaccare il |  |  |  |  |  |  |
| 70 | rendimento. Entrambe le ripartizioni rappresentano portafogli efficienti. |  |  |  |  |  |  |

### A72:G74

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 72 | Le celle A21:A29 contengono il modello di problema originario. Per caricarlo nuovamente, scegliere Risolutore&#32; |  |  |  |  |  |  |
| 73 | dal menu Strumenti, scegliere il pulsante Opzioni, fare clic su Carica modello, selezionare le celle A21:A29 |  |  |  |  |  |  |
| 74 | sul foglio di lavoro, quindi scegliere OK. |  |  |  |  |  |  |

### A76:G77

| Riga | A | B | C | D | E | F | G |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 76 | Verrà visualizzato un messaggio per chiedere se si desidera uniformare le impostazioni correnti delle opzioni del |  |  |  |  |  |  |
| 77 | Risolutore alle impostazioni del modello che si sta caricando. Scegliere OK per procedere. |  |  |  |  |  |  |

## Problema tecnico

### A1:H3

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Esempio 6: valore della resistenza in un circuito elettrico. |  |  |  |  |  |  |  |
| 2 | Trovare il valore della resistenza in un circuito elettrico che dissipa l'1% del valore originario |  |  |  |  |  |  |  |
| 3 | della carica entro un ventesimo di secondo dal momento in cui l'interruttore è stato chiuso. |  |  |  |  |  |  |  |

### A5:H10

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 |  | Commutatore-\> |  |  |  |  |  |  |
| 6 |  |  |  |  |  | q0 = | 9 | volt |
| 7 |  |  |  |  |  | q\[t\] = | 0.09 | volt |
| 8 |  | &#32;&#32;&#32;&#32; |  |  |  | t = | 0.05 | secondi |
| 9 | Batteria | Condensatore (C) |  | Induttanza (L) |  | L = | 8 | henry |
| 10 |  |  |  |  |  | C = | 0.0001 | farad |

### J6

| Riga | J |
| --- | --- |
| 6 | Codice colore |

### L8

| Riga | L |
| --- | --- |
| 8 | &#32;&#32;&#32;Cella obiettivo |

### L10

| Riga | L |
| --- | --- |
| 10 | &#32;&#32;&#32;Celle variabili |

### A12:H13

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 12 |  |  | Resistenza |  |  | R = | 300 | ohm |
| 13 |  |  | &#32;&#32;&#32;&#32;(R) |  |  |  |  |  |

### L12

| Riga | L |
| --- | --- |
| 12 | &#32;&#32;&#32;Vincoli |

### A15:H20

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 15 |  | 1/(L\*C) |  | 1250 |  | q\[t\] = | 0.2538891840303239 |  |
| 16 |  | (R/(2\*L))^2 |  | 351.5625 |  |  |  |  |
| 17 |  | RADQ(B15-B16) |  | 29.973947020704497 |  |  |  |  |
| 18 |  | COS(T\*B17) |  | 0.07203652709511484 |  |  |  |  |
| 19 |  | -R\*T/(2\*L) |  | -0.9375 |  |  |  |  |
| 20 |  | Q0\*EXP(B19) |  | 3.524450640091191 |  |  |  |  |

### A22:H25

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 22 | Nel modello è illustrato un circuito elettrico composto da una batteria, un commutatore, un condensatore, |  |  |  |  |  |  |  |
| 23 | una resistenza e un'induttanza. Quando il commutatore chiude il circuito di sinistra, la batteria carica il |  |  |  |  |  |  |  |
| 24 | condensatore. Quando il commutatore chiude il circuito di destra, il condensatore si scarica attraverso |  |  |  |  |  |  |  |
| 25 | l'induttanza e la resistenza, che dissipano entrambi energia elettrica. |  |  |  |  |  |  |  |

### A27:H29

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 27 | Utilizzando la seconda legge di Kirchhoff è possibile formulare e risolvere un'equazione differenziale per |  |  |  |  |  |  |  |
| 28 | determinare come varia nel tempo la carica del condensatore. La formula pone in relazione la carica q, |  |  |  |  |  |  |  |
| 29 | dato un tempo t, all'induttanza L, alla resistenza R e alla capacità C dei componenti circuitali. |  |  |  |  |  |  |  |

### A31:H32

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 31 | Utilizzare il Risolutore per determinare quale valore della resistenza R, dati i valori dell'induttanza L e del |  |  |  |  |  |  |  |
| 32 | condensatore C, riduce la carica a 1% del valore iniziale un ventesimo di secondo dopo la commutazione. |  |  |  |  |  |  |  |

### A34:H34

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 34 | Dati del problema |  |  |  |  |  |  |  |

### A36:H36

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 36 | Cella obiettivo |  | G15 |  | L'obiettivo è ottenere il valore 0,01. |  |  |  |

### A38:H38

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 38 | Celle variabili |  | G12 |  | Resistenza. |  |  |  |

### A40:H40

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 40 | Vincoli |  | D15:D20 |  | Soluzione algebrica della legge di Kirchhoff. |  |  |  |

### A42:H43

| Riga | A | B | C | D | E | F | G | H |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 42 | Il problema e la soluzione sono significativi in una ristretto intervallo di valori. La funzione rappresentata |  |  |  |  |  |  |  |
| 43 | dall'andamento della carica del condensatore nel tempo è in effetti un'onda sinusoidale smorzata. |  |  |  |  |  |  |  |
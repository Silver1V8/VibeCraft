## Panoramica

| Panoramica del Risolutore di Microsoft Excel   |     |     |     |     |        |
|------------------------------------------------|-----|-----|-----|-----|--------|
| Mese                                           | T1  | T2  | T3  | T4  | Totale |
| Stagionalità                                   | 0.9 | 1.1 | 0.8 | 1.2 |        |

| Unità vendute     |   3591.55258906228 |   4389.67538663168 |   3192.49119027759 |   4788.73678541638 |   15962.4559513879 |
|-------------------|--------------------|--------------------|--------------------|--------------------|--------------------|
| Fatturato         |   14366210.3562491 |   17558701.5465267 |   12769964.7611103 |   19154947.1416655 |   63849823.8055517 |
| Costo del venduto |   8978881.47265571 |   10974188.4665792 |   7981227.97569397 |   11971841.9635409 |   39906139.8784698 |
| Margine lordo     |   5387328.88359343 |   6584513.07994752 |   4788736.78541638 |   7183105.17812457 |   23943683.9270819 |

| Codice colore   |
|-----------------|

|    Cella obiettivo   |
|----------------------|

| Addetti alle vendite   |             8000 |             8000 |             9000 |             9000 |            34000 |
|------------------------|------------------|------------------|------------------|------------------|------------------|
| Budget pubblicitario   |            10000 |            10000 |            10000 |            10000 |            40000 |
| Spese generali         | 2154931.55343737 | 2633805.23197901 | 1915494.71416655 | 2873242.07124983 | 9577473.57083276 |
| Costo totale           | 2172931.55343737 | 2651805.23197901 | 1934494.71416655 | 2892242.07124983 | 9651473.57083276 |

|    Celle variabili   |
|----------------------|

|    Vincoli   |
|--------------|

| Utile operativo     |   3214397.33015606 |   3932707.84796852 |   2854242.07124983 |   4290863.10687474 |   14292210.3562491 |
|---------------------|--------------------|--------------------|--------------------|--------------------|--------------------|
| Margine di profitto |  0.223747059972418 |  0.223974867250161 |  0.223512133717247 |  0.224008089144831 |  0.223841030474487 |

| Prezzo unitario   |   4000 |
|-------------------|--------|
| Costo unitario    |   2500 |

| I seguenti esempi mostrano come utilizzare il modello per determinare quale valore o valori ne minimizzano   |
|--------------------------------------------------------------------------------------------------------------|
| o massimizzano un altro, per immettere e modificare vincoli e per salvare un modello di problema.            |

|   Riga | Contiene     |
|--------|--------------|
|      3 | Valori fissi |

| Spiegazione                                                       |
|-------------------------------------------------------------------|
| Fattore di stagionalità: le vendite crescono nei trimestri 2 e 4, |
| diminuiscono nei trimestri 1 e 3.                                 |

| 5   | =35*B3*(B11+3000)^0.5   |
|-----|-------------------------|

| Previsione del volume delle vendite trimestrale:   |
|----------------------------------------------------|
| la riga 3 contiene il fattore di stagionalità;     |
| la riga 11 contiene le spese pubblicitarie.        |

| 6   | =B5*$B$18   |
|-----|-------------|

| Fatturato: volume delle vendite (riga 5)   |
|--------------------------------------------|
| per prezzo unitario (cella B18).           |

| 7   | =B5*$B$19   |
|-----|-------------|

| Costo del venduto: volume delle vendite (riga 5)   |
|----------------------------------------------------|
| per costo unitario (cella B19).                    |

| 8   | =B6-B7   |
|-----|----------|

| Margine lordo: fatturato (riga 6)   |
|-------------------------------------|
| meno costo del venduto (riga 7).    |

| 10   | Valori fissi   |
|------|----------------|

| Spese addetti alle vendite.   |
|-------------------------------|

| 11   | Valori fissi   |
|------|----------------|

| Budget pubblicitario (circa il 6.3% del fatturato).   |
|-------------------------------------------------------|

| 12   | =0,15*B6   |
|------|------------|

| Spese generali: fatturato (riga 6)   |
|--------------------------------------|
| per 15%.                             |

| 13   | =SUM(B10:B12)   |
|------|-----------------|

| Totale costi: spese addetti alle vendite (riga 10) più       |
|--------------------------------------------------------------|
| budget pubblicitario (riga 11) più spese generali (riga 12). |

| 15   | =B8-B13   |
|------|-----------|

| Utile operativo: margine lordo (riga 8) meno costo totale   |
|-------------------------------------------------------------|
| (riga 13).                                                  |

| 16   | =B15/B6   |
|------|-----------|

| Margine di profitto: utile (riga 15)   |
|----------------------------------------|
| diviso fatturato (riga 6).             |

| 18   | Valori fissi   |
|------|----------------|

| Prezzo unitario.   |
|--------------------|

| 19   | Valori fissi   |
|------|----------------|

| Costo unitario.   |
|-------------------|

| Questo è un tipico modello di marketing che rappresenta l'aumento delle vendite (a partire da una base            |
|-------------------------------------------------------------------------------------------------------------------|
| attribuibile all'attività del settore vendite) all'aumentare del budget pubblicitario, caratterizzato tuttavia da |
| rendimenti decrescenti. I primi 5 milioni di spese pubblicitarie in T1 aumentano le vendite di 1092 unità,        |
| ma i successivi 5 le aumentano di sole 775 unità.                                                                 |

| È possibile utilizzare il Risolutore per determinare se il budget pubblicitario è insufficiente e se è opportuno   |
|--------------------------------------------------------------------------------------------------------------------|
| variarlo nel corso dell'anno per approfittare delle variazioni del fattore di stagionalità.                        |

| Risoluzione per un valore massimizzandone un altro                                                         |
|------------------------------------------------------------------------------------------------------------|
| Il Risolutore può essere utilizzato per determinare il valore massimo di una cella variandone un'altra.    |
| Le due celle devono essere poste in relazione mediante le formule del foglio di lavoro. In caso contrario, |
| le modifiche apportate a una cella non avranno effetto sul valore nell'altra cella.                        |

| Nel modello di foglio di lavoro, ad esempio, si desidera conoscere quanto è necessario spendere in           |
|--------------------------------------------------------------------------------------------------------------|
| pubblicità per massimizzare gli utili nel primo trimestre. Si desidera variare la spesa pubblicitaria fino a |
| trovare quella che massimizza gli utili.                                                                     |

| n   | Scegliere Risolutore dal menu Strumenti. Digitare b15 nella casella            |
|-----|--------------------------------------------------------------------------------|
|     | Imposta cella obiettivo o selezionare la cella B15 (utile nel primo trimestre) |
|     | sul foglio di lavoro. Selezionare l'opzione Max. Digitare b11 nella casella    |
|     | Cambiando le celle o selezionare la cella B11 (spesa pubblicitaria nel primo   |
|     | trimestre) sul foglio di lavoro. Scegliere il pulsante Risolvi.                |

| Alcuni messaggi verranno visualizzati nella barra di stato mentre il problema viene impostato e risolto.    |
|-------------------------------------------------------------------------------------------------------------|
| Verrà quindi confermata e visualizzata la soluzione del problema. Un budget pubblicitario di L.17.093.000   |
| genera un utile massimo di L.15.093.000.                                                                    |

| n   | Dopo aver esaminato i risultati, selezionare Ripristina i valori originali e               |
|-----|--------------------------------------------------------------------------------------------|
|     | scegliere OK per ignorare i risultati e ripristinare il valore originario nella cella B11. |

| Reimpostazione delle opzioni del Risolutore   |
|-----------------------------------------------|

| Scegliere il pulsante Reimposta se si desidera ripristinare le impostazioni originarie delle opzioni    |
|---------------------------------------------------------------------------------------------------------|
| nella finestra di dialogo Parametri del Risolutore per passare a un nuovo problema.                     |

| Risoluzione per un valore modificando più valori                                                             |
|--------------------------------------------------------------------------------------------------------------|
| .                                                                                                            |
| È possibile utilizzare il Risolutore per risolvere per più valori contemporaneamente in modo da minimizzarne |
| o massimizzarne un altro. È possibile ad esempio individuare per ciascun trimestre il budget pubblicitario   |
| che massimizza gli utili annuali. Dato che la stagionalità (riga 3) compare come fattore nel calcolo delle   |
| unità vendute, è logico aumentare il budget pubblicitario in T4, quando sortisce l'effetto maggiore,         |
| e diminuirlo in T3, quando l'effetto sulle vendite è minore. Utilizzare il Risolutore per determinare la     |
| ripartizione trimestrale più redditizia.                                                                     |

| n   | Scegliere Risolutore dal menu Strumenti. Digitare f15 nella casella               |
|-----|-----------------------------------------------------------------------------------|
|     | Imposta cella obiettivo o selezionare la cella F15 (utile operativo annuale)      |
|     | sul foglio di lavoro. Selezionare l'opzione Max. Digitare b11:e11 nella casella   |
|     | Cambiando le celle o selezionare le celle B11:E11 (spesa pubblicitaria in ciascun |
|     | trimestre) sul foglio di lavoro. Scegliere il pulsante Risolvi.                   |

| n   | Dopo aver esaminato i risultati, selezionare Ripristina i valori originali e         |
|-----|--------------------------------------------------------------------------------------|
|     | scegliere OK per ignorare i risultati e ripristinare i valori originari nelle celle. |

| Questo è un problema di ottimizzazione non lineare di media complessità, consistente nel ricercare    |
|-------------------------------------------------------------------------------------------------------|
| i valori delle quattro incognite (celle B11-E11) che massimizzano gli utili.                          |
| Il problema è non lineare per la presenza di esponenti nelle formule nella riga 5. Il risultato della |
| ottimizzazione non vincolata mostra che è possibile aumentare gli utili annuali a L.79.706.000 con    |
| un budget pubblicitario di L.89.706.000.                                                              |

| Nella maggior parte dei modelli realistici si desidera tuttavia vincolare certi fattori limitanti. I vincoli possono   |
|------------------------------------------------------------------------------------------------------------------------|
| essere applicati alla cella obiettivo, alle celle variabili o a qualsiasi altro valore collegato alle formule nelle    |
| celle.                                                                                                                 |

| Aggiunta di un vincolo   |
|--------------------------|

| Il budget consente di recuperare le spese pubblicitarie e di aumentare gli utili, ma i vantaggi ottenuti   |
|------------------------------------------------------------------------------------------------------------|
| sono decrescenti. Nulla garantisce che l'attuale modello di correlazione tra vendite e pubblicità          |
| sia valido anche il prossimo anno, specialmente a livelli di spesa crescenti. Non è quindi prudente        |
| svincolare le spese pubblicitarie.                                                                         |

| Se si desidera mantenere invariato il budget pubblicitario a L.40.000.000, aggiungere al problema   |
|-----------------------------------------------------------------------------------------------------|
| un vincolo che limita le spese pubblicitarie annuali a L.40.000.000.                                |

| n   | Scegliere Risolutore dal menu Strumenti e fare clic sul pulsante Aggiungi.        |
|-----|-----------------------------------------------------------------------------------|
|     | Verrà visualizzata la finestra di dialogo Aggiungi vincolo. Nella casella         |
|     | Riferimento digitare f11 o selezionare la cella F11 (spese pubblicitarie annuali) |
|     | sul foglio di lavoro. La cella F11 deve contenere un valore minore di o uguale a  |
|     | L.40.000.000. La relazione predefinita nella casella Vincolo è <= (minore di      |
|     | o uguale a), quindi non è necessario modificarla. Nella casella a fianco digitare |
|     | 40000000, quindi scegliere OK e Risolvi.                                          |

| n   | Dopo aver esaminato i risultati, selezionare Ripristina i valori originali e         |
|-----|--------------------------------------------------------------------------------------|
|     | scegliere OK per ignorare i risultati e ripristinare i valori originari nelle celle. |

| La soluzione trovata ripartisce somme variabili da L.5.117.000 in T3 a L.15.263.000 in T4.    |
|-----------------------------------------------------------------------------------------------|
| L'utile operativo passa da L.69.662.000 nel budget originario a L.71.447.000, senza aumentare |
| il budget pubblicitario.                                                                      |

| Modifica di un vincolo   |
|--------------------------|

| Utilizzando il Risolutore di Microsoft Excel è possibile sperimentare con parametri leggermente differenti per   |
|------------------------------------------------------------------------------------------------------------------|
| stabilire la soluzione ottimale a un problema. È possibile modificare un vincolo per verificare se i risultati   |
| migliorano o peggiorano. Nel modello di foglio di lavoro provare ad aumentare il vincolo sulle spese             |
| pubblicitarie a L.50.000.000 per verificarne gli effetti sull'utile annuale.                                     |

| n   | Scegliere Risolutore dal menu Strumenti. Il vincolo $F$11<=40000000              |
|-----|----------------------------------------------------------------------------------|
|     | dovrebbe già essere selezionato nella casella Vincoli. Scegliere il pulsante     |
|     | Modifica. Nella casella Vincolo modificare 40000000 in 50000000.                 |
|     | Scegliere OK, quindi Risolvi. Fare clic su Mantieni la soluzione del Risolutore, |
|     | quindi scegliere OK per mantenere i risultati visualizzati sullo schermo.        |

| La soluzione ottimale genera un utile annuale di L.74.817.000, pari a un aumento di L.3.370.000 rispetto       |
|----------------------------------------------------------------------------------------------------------------|
| all'importo precedente di L.71.447.000. Un investimento incrementale di L.10.000.000 che generi un             |
| aumento degli utili di L.3.370.000, pari a una redditività del 33,7%, è quasi sempre valido dal punto di vista |
| finanziario. Rispetto al risultato non vincolato, questa soluzione comporta un assottigliamento degli utili di |
| L.4.889.000, ma anche una riduzione delle spese di L.39.706.000.                                               |

| Salvataggio di un modello di problema   |
|-----------------------------------------|

| Scegliendo Salva dal menu File, le ultime selezioni nella finestra di dialogo Parametri del Risolutore      |
|-------------------------------------------------------------------------------------------------------------|
| vengono incollate al foglio di lavoro e mantenute durante il salvataggio. È tuttavia possibile definire più |
| problemi per foglio di lavoro salvandoli individualmente mediante il pulsante Salva modello nella           |
| finestra di dialogo Opzioni del Risolutore. Ciascun modello di problema consiste in celle e vincoli         |
| immessi nella finestra di dialogo Parametri del Risolutore.                                                 |

| Scegliendo Salva modello, verrà visualizzata la finestra di dialogo Salva modello, con una selezione                |
|---------------------------------------------------------------------------------------------------------------------|
| predefinita basata sulla cella attiva come area per salvare il modello. L'intervallo consigliato include una cella  |
| per ciascun vincolo più tre celle aggiuntive. Assicurarsi che l'intervallo di celle sul foglio di lavoro sia vuoto. |

| n   | Scegliere Risolutore dal menu Strumenti e fare clic sul pulsante Opzioni.           |
|-----|-------------------------------------------------------------------------------------|
|     | Scegliere il pulsante Salva modello. Nella casella Seleziona area del modello,      |
|     | digitare h15:h18 o selezionare le celle H15:H18 sul foglio di lavoro. Scegliere OK. |

| Nota  È possibile immettere un riferimento a una singola cella nella casella    |
|---------------------------------------------------------------------------------|
| Seleziona area del modello. Il riferimento verrà utilizzato come angolo         |
| superiore sinistro dell'intervallo in cui verranno copiati i dati del problema. |

| Per caricare i dati del problema in un secondo momento, scegliere il pulsante Carica modello nella   |
|------------------------------------------------------------------------------------------------------|
| finestra di dialogo Opzioni del Risolutore, digitare h15:h18 nella casella Area del modello o        |
| selezionare le celle H15:H18 sul modello di foglio di lavoro, quindi scegliere OK.                   |

| Verrà visualizzato un messaggio per chiedere se si desidera uniformare le impostazioni correnti delle   |
|---------------------------------------------------------------------------------------------------------|
| opzioni del Risolutore alle impostazioni del modello che si sta caricando. Scegliere OK per procedere.  |

## Mix di prodotti

| Esempio 1:mix di prodotti con margine di profitto decrescente.                                                        |
|-----------------------------------------------------------------------------------------------------------------------|
| Un'azienda produce televisori, impianti stereo e altoparlanti utilizzando una scorta comune per trasformatori,        |
| coni ecc. I componenti sono disponibili in quantità limitata e si deve determinare il mix di prodotti più redditizio. |
| Si consideri che il profitto per unità fabbricata diminuisce con l'aumentare del volume perchè si rendono             |
| necessari degli ulteriori incentivi di prezzo per caricare il canale di distribuzione.                                |

| Codice colore   |
|-----------------|

| Cella obiettivo   |
|-------------------|

| Celle variabili   |
|-------------------|

|               |        |                     | Televisori                      |      Imp. stereo |     Altoparlanti |
|---------------|--------|---------------------|---------------------------------|------------------|------------------|
|               |        | Unità da produrre-> | 100                             |              100 |              100 |
| Componente    | Scorta | Unità usate         |                                 |                  |                  |
| Telaio        | 450    | 200                 | 1                               |                1 |                0 |
| Tubo catodico | 250    | 100                 | 1                               |                0 |                0 |
| Cono          | 800    | 500                 | 2                               |                2 |                1 |
| Alternatore   | 450    | 200                 | 1                               |                1 |                0 |
| Diodi         | 600    | 400                 | 2                               |                1 |                1 |
|               |        |                     | Profitti (in migliaia di Lire): |                  |                  |
|               |        | Per prodotto        | 4732.18008360145                | 3154.78672240097 | 2208.35070568068 |
|               |        | Totale              | 10095.3175116831                |                  |                  |

| Vincoli   |
|-----------|

| Esponente      |
|----------------|
| di diminuzione |
| dei ricavi:    |
| 0.9            |

| Questo modello fornisce dati per molti prodotti utilizzando componenti comuni, ciascuno con un differente   |
|-------------------------------------------------------------------------------------------------------------|
| margine di profitto unitario. Le scorte sono limitate e il problema consiste nel determinare quante unità   |
| produrre con le scorte disponibili per massimizzare i profitti.                                             |

| Dati del problema   |
|---------------------|

| Cella obiettivo   |
|-------------------|

| D18   |
|-------|

| L'obiettivo è massimizzare i profitti.   |
|------------------------------------------|

| Celle variabili   |
|-------------------|

| D9:F9   |
|---------|

| Numero di unità da produrre per ciascun prodotto.   |
|-----------------------------------------------------|

| Vincoli   |
|-----------|

| C11:C15<=B11:B15   |
|--------------------|

| Il numero dei componenti utilizzati non può essere   |
|------------------------------------------------------|
| superiore al numero dei componenti in magazzino.     |

| D9:F9>=0   |
|------------|

| Il numero di unità da produrre deve essere maggiore   |
|-------------------------------------------------------|
| o uguale a 0.                                         |

| Le formule del profitto per prodotto nelle celle D17-F17 includono il fattore ^H15 per mostrare che il profitto   |
|-------------------------------------------------------------------------------------------------------------------|
| unitario decresce all'aumentare del volume di produzione. H15 contiene 0,9 che rende il problema non lineare.     |
| Se si immette il valore 1,0 in H15 per indicare che il profitto unitario rimane costante al variare del volume    |
| e si sceglie il pulsante Risolvi, la soluzione ottimale cambierà. Questa modifica rende il problema lineare.      |

## Trasporti

| Esempio 2: trasporti.                                                                                        |
|--------------------------------------------------------------------------------------------------------------|
| Minimizzare i costi di spedizione della merce dagli stabilimenti ai magazzini nelle aree metropolitane senza |
| superare la capacità produttiva di ciascun stabilimento e soddisfacendo la domanda di ciascuna               |
| area metropolitana.                                                                                          |

|               |        | Numero di spedizioni dallo stabilimento x al magazzino y:   |        |      |        |         |
|---------------|--------|-------------------------------------------------------------|--------|------|--------|---------|
| Stabilimenti: | Totale | Torino                                                      | Milano | Roma | Napoli | Palermo |
| Gioia Tauro   | 5      | 1                                                           | 1      | 1    | 1      | 1       |
| Caserta       | 5      | 1                                                           | 1      | 1    | 1      | 1       |
| Marghera      | 5      | 1                                                           | 1      | 1    | 1      | 1       |
|               |        | ---                                                         | ---    | ---  | ---    | ---     |
| Totale:       |        | 3                                                           | 3      | 3    | 3      | 3       |

| Codice colore   |
|-----------------|

|    Cella obiettivo   |
|----------------------|

|    Celle variabili   |
|----------------------|

| Totale:   |
|-----------|

|    Vincoli   |
|--------------|

|               | Domanda dei magazzini -->   | 180                                                                            |   80 |   200 |   160 |   220 |
|---------------|-----------------------------|--------------------------------------------------------------------------------|------|-------|-------|-------|
| Stabilimenti: | Scorta                      | Costi di spedizione dallo stabilimento x al magazzino y (in migliaia di Lire): |      |       |       |       |
| Gioia Tauro   | 310                         | 10                                                                             |    8 |     6 |     5 |     4 |
| Caserta       | 260                         | 6                                                                              |    5 |     4 |     3 |     6 |
| Marghera      | 280                         | 3                                                                              |    4 |     5 |     5 |     9 |

| Spedizione:   | 83   | 19   | 17   | 15   | 13   | 19   |
|---------------|------|------|------|------|------|------|

| Il problema esposto nel modello riguarda la spedizione di merci da tre stabilimenti a cinque magazzini   |
|----------------------------------------------------------------------------------------------------------|
| regionali. Le merci possono essere spedite da qualsiasi stabilimento a qualsiasi magazzino, ma i costi   |
| diminuiscono minimizzando le distanze. Il problema consiste nel determinare quanta merce spedire         |
| da ciascun stabilimento a ciascun magazzino per soddisfare la domanda regionale senza eccedere           |
| la capacità produttiva e minimizzando i costi di trasporto.                                              |

| Dati del problema   |
|---------------------|

| Cella obiettivo   |
|-------------------|

| B20   |
|-------|

| L'obiettivo è minimizzare i costi di trasporto totali.   |
|----------------------------------------------------------|

| Celle variabili   |
|-------------------|

| C8:G10   |
|----------|

| Quantità da spedire da ciascun stabilimento   |
|-----------------------------------------------|
| a ciascun magazzino.                          |

| Vincoli   |
|-----------|

| B8:B10<=B16:B18   |
|-------------------|

| Il volume delle spedizioni non può eccedere   |
|-----------------------------------------------|
| la capacità produttiva dello stabilimento.    |

| C12:G12>=C14:G14   |
|--------------------|

| I volumi di merce spediti ai magazzini devono   |
|-------------------------------------------------|
| essere maggiori o uguali alla domanda.          |

| C8:G10>=0   |
|-------------|

| Il numero di spedizioni deve essere maggiore    |
|-------------------------------------------------|
| o uguale a 0.                                   |

| Il problema può essere risolto più rapidamente selezionando la casella di controllo                   |
|-------------------------------------------------------------------------------------------------------|
| Presupponi modello lineare nella finestra di dialogo Opzioni del Risolutore prima di scegliere        |
| il pulsante Risolvi. Un problema di questo tipo presenta una soluzione ottimale in cui le quantità da |
| spedire sono numeri interi, se tutti i vincoli della produzione e della domanda sono numeri interi.   |

## Gestione del personale

| Esempio 3: pianificazione del personale per un parco divertimenti.                                              |
|-----------------------------------------------------------------------------------------------------------------|
| I dipendenti prestano servizio 5 giorni consecutivi seguiti da due giorni liberi. Determinare la turnazione che |
| soddisfa la richiesta di presenze determinata dall'afflusso di clienti e minimizza i costi di manodopera.       |

| Turno   | Giorni liberi   |
|---------|-----------------|
| A       | Dom, Lun        |
| B       | Lun, Mar        |
| C       | Mar, Mer        |
| D       | Mer, Gio        |
| E       | Gio, Ven        |
| F       | Ven, Sab        |
| G       | Sab, Dom        |

|   Dipendenti |
|--------------|
|            4 |
|            4 |
|            4 |
|            6 |
|            6 |
|            4 |
|            4 |

|   Lun |   Mar |   Mer |   Gio |   Ven |   Sab |   Dom |
|-------|-------|-------|-------|-------|-------|-------|
|     0 |     0 |     1 |     1 |     1 |     1 |     1 |
|     1 |     0 |     0 |     1 |     1 |     1 |     1 |
|     1 |     1 |     0 |     0 |     1 |     1 |     1 |
|     1 |     1 |     1 |     0 |     0 |     1 |     1 |
|     1 |     1 |     1 |     1 |     0 |     0 |     1 |
|     1 |     1 |     1 |     1 |     1 |     0 |     0 |
|     0 |     1 |     1 |     1 |     1 |     1 |     0 |

| Codice colore   |
|-----------------|

|    Cella obiettivo   |
|----------------------|

|    Celle variabili   |
|----------------------|

|    Vincoli   |
|--------------|

| Turni totali:   | 32   |
|-----------------|------|

| 24   | 24   | 24   | 22   | 20   | 22   | 24   |
|------|------|------|------|------|------|------|

| Domanda totale:   |
|-------------------|

| 22   | 17   | 13   | 14   | 15   | 18   | 24   |
|------|------|------|------|------|------|------|

| Paga/dipend./giorno:   |
|------------------------|
| Paghe/settimana:       |

|   40000 |
|---------|
| 1280000 |

| L'obiettivo del modello è strutturare i turni dei dipendenti in modo da disporre di sufficiente personale minimizzando   |
|--------------------------------------------------------------------------------------------------------------------------|
| i costi di manodopera. Nell'esempio tutti i dipendenti ricevono la stessa retribuzione oraria, quindi minimizzando il    |
| numero di dipendenti in servizio in ciascuna giornata si minimizzano anche i costi. Ciascun dipendente presta            |
| servizio cinque giorni consecutivi seguiti da due giorni liberi.                                                         |

| Dati del problema   |
|---------------------|

| Cella obiettivo   |
|-------------------|

| D20   |
|-------|

| L'obiettivo è minimizzare le spese di manodopera.   |
|-----------------------------------------------------|

| Celle variabili   |
|-------------------|

| D7:D13   |
|----------|

| Dipendenti in servizio in ciascuna giornata.   |
|------------------------------------------------|

| Vincoli   |
|-----------|

| D7:D13>=0   |
|-------------|

| Il numero di dipendenti deve essere maggiore o uguale a 0.   |
|--------------------------------------------------------------|

| D7:D13=Numero intero   |
|------------------------|

| Il numero di dipendenti deve essere un numero intero.   |
|---------------------------------------------------------|

| F15:L15>=F17:L17   |
|--------------------|

| In ciascuna giornata deve prestare servizio un numero di   |
|------------------------------------------------------------|
| dipendenti maggiore o uguale alla domanda.                 |

| Turni possibili   |
|-------------------|

| Righe 7-13   |
|--------------|

| 1 significa che il dipendente assegnato al turno è in servizio.   |
|-------------------------------------------------------------------|

| Nell'esempio si utilizza un numero intero come vincolo in modo che le soluzioni non includano frazioni di dipendente    |
|-------------------------------------------------------------------------------------------------------------------------|
| in alcun turno. Selezionando la casella di controllo Presupponi modello lineare nella finestra di dialogo               |
| Opzioni del Risolutore prima di scegliere il pulsante Risolvi, il procedimento di soluzione verrà accelerato.           |

## Massimizzazione del reddito

| Esempio 4: gestione del capitale.                                                                                             |
|-------------------------------------------------------------------------------------------------------------------------------|
| Determinare la modalità di investimento della liquidità in eccesso in certificati di deposito a 1, 3 e 6 mesi, in modo da     |
| massimizzare il reddito da interessi e soddisfare la richiesta di liquidità dell'azienda, includendo un margine di sicurezza. |

|                                   |   Rendimento |   Durata |
|-----------------------------------|--------------|----------|
| Certificato di deposito a 1 mese: |         0.01 |        1 |
| Certificato di deposito a 3 mesi: |         0.04 |        3 |
| Certificato di deposito a 6 mesi: |         0.09 |        6 |

| Acquistare nei mesi:   |
|------------------------|
| 1, 2, 3, 4, 5 e 6      |
| 1 e 4                  |
| 1                      |

|        | Interessi   |
|--------|-------------|
|        | percepiti:  |
| Totale | 7700        |

| Mese:                    |   Mese 1 |   Mese 2 |   Mese 3 |   Mese 4 |   Mese 5 |   Mese 6 |   Fine |
|--------------------------|----------|----------|----------|----------|----------|----------|--------|
| Cassa iniziale:          |   400000 |   205000 |   216000 |   237000 |   158400 |   109400 | 125400 |
| Cert. di depo. maturati: |          |   100000 |   100000 |   110000 |   100000 |   100000 | 120000 |
| Interesse:               |          |     1000 |     1000 |     1400 |     1000 |     1000 |   2300 |
| Cert. di dep. a 1 mese:  |   100000 |   100000 |   100000 |   100000 |   100000 |   100000 |        |
| Cert. di dep. a 3 mesi:  |    10000 |          |          |    10000 |          |          |        |
| Cert. di dep. a 6 mesi:  |    10000 |          |          |          |          |          |        |
| Utilizzo di cassa:       |    75000 |   -10000 |   -20000 |    80000 |    50000 |   -15000 |  60000 |
| Cassa finale:            |   205000 |   216000 |   237000 |   158400 |   109400 |   125400 | 187700 |

| Codice colore   |
|-----------------|

|    Cella obiettivo   |
|----------------------|

|    Celle variabili   |
|----------------------|

|    Vincoli   |
|--------------|

| -290000   |
|-----------|

| Uno dei compiti di un direttore finanziario o di un manager è gestire la liquidità e gli investimenti a breve termine in modo   |
|---------------------------------------------------------------------------------------------------------------------------------|
| da massimizzare il flusso reddituale degli stessi, mantenendoli disponibili per coprire le spese. È necessario conciliare la    |
| maggiore remunerazione tipica dagli investimenti a lungo termine e la flessibilità ottenuta investendo i fondi a breve termine. |

| Il modello calcola la cassa finale in base alla cassa iniziale, riportata dal mese precedente, alle entrate provenienti dai certificati   |
|-------------------------------------------------------------------------------------------------------------------------------------------|
| di deposito in scadenza, alle uscite per acquisto di nuovi certificati e alle uscite di cassa mensili per la gestione aziendale.          |

| Le nove decisioni da prendere riguardano: gli importi da investire in certificati a un mese nei mesi da 1 a 6, gli importi   |
|------------------------------------------------------------------------------------------------------------------------------|
| da investire in certificati a tre mesi nei mesi 1 e 4, infine l'importo da investire in certificati a sei mesi nel mese 1.   |

| Dati del problema   |
|---------------------|

| Cella obiettivo   |
|-------------------|

| H8   |
|------|

| L'obiettivo è massimizzare l'interesse percepito.   |
|-----------------------------------------------------|

| Celle variabili   |
|-------------------|

| B14:G14       |
|---------------|
| B15, E15, B16 |

| Importi investiti in ciascun tipo di certificato.   |
|-----------------------------------------------------|

| Vincoli   |
|-----------|

| B14:G14>=0   |
|--------------|
| B15:B16>=0   |
| E15>=0       |

| L'investimento in ciascun tipo di certificato deve   |
|------------------------------------------------------|
| essere maggiore o uguale a 0.                        |

| B18:H18>=100000   |
|-------------------|

| La cassa finale deve essere maggiore o uguale a   |
|---------------------------------------------------|
| L.100.000.000.                                    |

| La soluzione ottimale genera un reddito da interessi pari a L.16.531.000 preferenziando i certificati a sei e a tre mesi,    |
|------------------------------------------------------------------------------------------------------------------------------|
| pur nel pieno rispetto dei vincoli.                                                                                          |

| Si supponga, tuttavia, di dover disporre di liquidità sufficiente al pagamento di macchinari nel mese 5. Aggiungere   |
|-----------------------------------------------------------------------------------------------------------------------|
| un vincolo tale che la durata media degli investimenti in carico al mese 1 non sia maggiore di quattro mesi.          |

| La formula nella cella B20 calcola il totale degli importi investiti nel mese 1 (B14, B15 e B16), ponderati in base alla   |
|----------------------------------------------------------------------------------------------------------------------------|
| durata (1, 3 e 6 mesi), quindi sottrae dall'importo l'investimento totale, ponderato per il fattore 4. Se il risultato è   |
| minore o uguale a zero, la durata media non eccede quattro mesi. Per aggiungere questo vincolo, ripristinare i valori      |
| originali, quindi scegliere Risolutore dal menu Strumenti. Scegliere il pulsante Aggiungi. Digitare b20 nella casella      |
| Riferimento, digitare 0 nella casella Vincoli, quindi scegliere OK. Per risolvere il problema digitare Risolvi.            |

| Per soddisfare il vincolo della durata di quattro mesi, la liquidità viene spostata dai certificati a sei mesi a quelli a tre mesi   |
|--------------------------------------------------------------------------------------------------------------------------------------|
| e giunge a scadenza nel mese 4. Secondo il piano, è reinvestita in nuovi certificati a tre mesi. In caso di necessità                |
| è possibile non reinvestire la liquidità e mantenerla immediatamente disponibile. L'importo di L.56.896.000 in scadenza              |
| nel mese 4 è più che sufficiente a coprire l'uscita per pagamento macchinari nel mese 5. Per ottenere questa flessibilità            |
| si deve rinunciare a circa L.460.000 di interessi.                                                                                   |

## Portafoglio titoli

| Esempio 5: portafoglio titoli.                                                                      |
|-----------------------------------------------------------------------------------------------------|
| Determinare la ponderazione di titoli in un portafoglio efficiente che massimizzi la redditività    |
| per un dato livello di rischio. Il foglio utilizza il modello ad indicizzazione singola di Sharpe.  |
| Se i termini della covarianza sono disponibili è anche possibile utilizzare il metodo di Markowitz. |

| Tasso a rischio zero   |
|------------------------|
| Tasso di mercato       |

|   0.06 |
|--------|
|   0.15 |

| Varianza di mercato   |
|-----------------------|
| Peso massimo          |

|   0.03 |
|--------|
|      1 |

|                  |   Beta |   Varianza res. |
|------------------|--------|-----------------|
| Titolo A         |    0.8 |            0.04 |
| Titolo B         |      1 |             0.2 |
| Titolo C         |    1.8 |            0.12 |
| Titolo D         |    2.2 |             0.4 |
| Buoni del Tesoro |      0 |               0 |

|   Peso |   *Beta |   *Var. |
|--------|---------|---------|
|    0.2 |    0.16 |  0.0016 |
|    0.2 |     0.2 |   0.008 |
|    0.2 |    0.36 |  0.0048 |
|    0.2 |    0.44 |   0.016 |
|    0.2 |       0 |       0 |

| Codice colore   |
|-----------------|

|    Cella obiettivo   |
|----------------------|

|    Celle variabili   |
|----------------------|

|    Vincoli   |
|--------------|

| Totale   |
|----------|

| 1          | 1.16   | 0.0304   |
|------------|--------|----------|
| Rendimento |        | Varianza |
| 0.1644     |        | 0.070768 |

| Portafoglio:     |
|------------------|

|   Rendimento massimo: A21:A29 |
|-------------------------------|
|                        0.1644 |
|                             5 |
|                             1 |
|                             1 |
|                             1 |
|                             1 |
|                             1 |
|                             1 |
|                             1 |

|   Rischio minimo: D21:D29 |
|---------------------------|
|                  0.070768 |
|                         5 |
|                         1 |
|                         1 |
|                         1 |
|                         1 |
|                         1 |
|                         1 |
|                         1 |

| Uno dei principi fondamentali della gestione degli investimenti è la diversificazione. Componendo un portafoglio     |
|----------------------------------------------------------------------------------------------------------------------|
| formato da più titoli è possibile ottenere un tasso di rendimento pari alla media dei rendimenti dei singoli titoli, |
| riducendo al contempo il rischio in caso di perdite su un titolo.                                                    |

| Questo modello può essere utilizzato per individuare quale ripartizione degli investimenti tra i vari titoli minimizza   |
|--------------------------------------------------------------------------------------------------------------------------|
| il rischio per un dato tasso di rendimento o massimizza il rendimento per un dato livello di rischio.                    |

| Il foglio di lavoro include il coefficiente beta (rischio di mercato) e la varianza residua relativi a quattro titoli.    |
|---------------------------------------------------------------------------------------------------------------------------|
| Inoltre il portafoglio comprende un investimento in Buoni del Tesoro, considerati esenti da rischio e a varianza          |
| nulla. Inizialmente vengono investiti importi uguali (pari al 20% del portafoglio) in ciascun titolo.                     |

| Utilizzare il Risolutore per provare differenti ripartizioni di portafoglio in modo da massimizzare il rendimento del   |
|-------------------------------------------------------------------------------------------------------------------------|
| portafoglio per un dato livello di rischio o minimizzare il rischio per un dato tasso di rendimento. Scegliendo una     |
| ripartizione iniziale uniforme in cinque titoli, il rendimento del portafoglio è pari al 16,4% e la varianza al 7,1%.   |

| Dati del problema   |
|---------------------|

| Cella obiettivo   |
|-------------------|

| E18   |
|-------|

| L'obiettivo è massimizzare il rendimento del   |
|------------------------------------------------|
| portafoglio.                                   |

| Celle variabili   |
|-------------------|

| E10:E14   |
|-----------|

| Peso di ciascun titolo.   |
|---------------------------|

| Vincoli   |
|-----------|

| E10:E14>=0   |
|--------------|

| Il peso deve essere maggiore o uguale a 0.   |
|----------------------------------------------|

| E16=1   |
|---------|

| Il peso deve essere uguale a 1.   |
|-----------------------------------|

| G18<=0,071   |
|--------------|

| La varianza deve essere minore o uguale a 0,071.   |
|----------------------------------------------------|

| Coefficiente beta di ciascun titolo   |
|---------------------------------------|

| B10:B13   |
|-----------|

| Varianza di ciascun titolo   |
|------------------------------|

| C10:C13   |
|-----------|

| Le celle D21:D29 contengono i dati del problema per minimizzare il rischio a fronte di un tasso di rendimento        |
|----------------------------------------------------------------------------------------------------------------------|
| atteso del 16,4%. Per caricare i dati nel Risolutore, scegliere Risolutore dal menu Strumenti. Scegliere il          |
| pulsante Opzioni, fare clic su Carica modello, selezionare le celle D21:D29 sul foglio di lavoro, quindi scegliere   |
| OK finché viene visualizzata la finestra di dialogo Parametri del Risolutore. Scegliere il pulsante Risolvi.         |
| In entrambi i casi verranno proposte ripartizioni di portafoglio che superano la regola della ripartizione uniforme. |

| È possibile ottenere un rendimento maggiore (17,1%) a parità di rischio o ridurre il richio senza intaccare il   |
|------------------------------------------------------------------------------------------------------------------|
| rendimento. Entrambe le ripartizioni rappresentano portafogli efficienti.                                        |

| Le celle A21:A29 contengono il modello di problema originario. Per caricarlo nuovamente, scegliere Risolutore    |
|------------------------------------------------------------------------------------------------------------------|
| dal menu Strumenti, scegliere il pulsante Opzioni, fare clic su Carica modello, selezionare le celle A21:A29     |
| sul foglio di lavoro, quindi scegliere OK.                                                                       |

| Verrà visualizzato un messaggio per chiedere se si desidera uniformare le impostazioni correnti delle opzioni del   |
|---------------------------------------------------------------------------------------------------------------------|
| Risolutore alle impostazioni del modello che si sta caricando. Scegliere OK per procedere.                          |

## Problema tecnico

| Esempio 6: valore della resistenza in un circuito elettrico.                                       |
|----------------------------------------------------------------------------------------------------|
| Trovare il valore della resistenza in un circuito elettrico che dissipa l'1% del valore originario |
| della carica entro un ventesimo di secondo dal momento in cui l'interruttore è stato chiuso.       |

| Commutatore->   |
|-----------------|

| q0 =   |      9 | volt    |
|--------|--------|---------|
| q[t] = |   0.09 | volt    |
| t =    |   0.05 | secondi |
| L =    |      8 | henry   |
| C =    | 0.0001 | farad   |

| Codice colore   |
|-----------------|

|          |                  |
|----------|------------------|
| Batteria | Condensatore (C) |

|    Cella obiettivo   |
|----------------------|

| Induttanza (L)   |
|------------------|

|    Celle variabili   |
|----------------------|

| Resistenza   |
|--------------|
| (R)          |

| R =   | 300   | ohm   |
|-------|-------|-------|

|    Vincoli   |
|--------------|

| 1/(L*C)       |
|---------------|
| (R/(2*L))^2   |
| RADQ(B15-B16) |
| COS(T*B17)    |
| -R*T/(2*L)    |
| Q0*EXP(B19)   |

|               1250 |
|--------------------|
|           351.5625 |
|   29.9739470207045 |
| 0.0720365270951148 |
|            -0.9375 |
|   3.52445064009119 |

| q[t] =   | 0.253889184030324   |
|----------|---------------------|

| Nel modello è illustrato un circuito elettrico composto da una batteria, un commutatore, un condensatore,   |
|-------------------------------------------------------------------------------------------------------------|
| una resistenza e un'induttanza. Quando il commutatore chiude il circuito di sinistra, la batteria carica il |
| condensatore. Quando il commutatore chiude il circuito di destra, il condensatore si scarica attraverso     |
| l'induttanza e la resistenza, che dissipano entrambi energia elettrica.                                     |

| Utilizzando la seconda legge di Kirchhoff è possibile formulare e risolvere un'equazione differenziale per   |
|--------------------------------------------------------------------------------------------------------------|
| determinare come varia nel tempo la carica del condensatore. La formula pone in relazione la carica q,       |
| dato un tempo t, all'induttanza L, alla resistenza R e alla capacità C dei componenti circuitali.            |

| Utilizzare il Risolutore per determinare quale valore della resistenza R, dati i valori dell'induttanza L e del   |
|-------------------------------------------------------------------------------------------------------------------|
| condensatore C, riduce la carica a 1% del valore iniziale un ventesimo di secondo dopo la commutazione.           |

| Dati del problema   |
|---------------------|

| Cella obiettivo   |
|-------------------|

| G15   |
|-------|

| L'obiettivo è ottenere il valore 0,01.   |
|------------------------------------------|

| Celle variabili   |
|-------------------|

| G12   |
|-------|

| Resistenza.   |
|---------------|

| Vincoli   |
|-----------|

| D15:D20   |
|-----------|

| Soluzione algebrica della legge di Kirchhoff.   |
|-------------------------------------------------|

| Il problema e la soluzione sono significativi in una ristretto intervallo di valori. La funzione rappresentata   |
|------------------------------------------------------------------------------------------------------------------|
| dall'andamento della carica del condensatore nel tempo è in effetti un'onda sinusoidale smorzata.                |
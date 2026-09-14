# Valutazione umana — campioni senza etichetta del braccio

## Nota di metodo — registrata prima dell'apertura della chiave

- Le schede sono state redatte con assistenza di un modello e revisionate dall'umano. Il risultato del confronto misura anche questa lettura, non solo la differenza tra i due prompt. Un revisore diverso potrebbe pesare diversamente gli stessi output, e le dodici letture sono correlate tra loro perché prodotte con lo stesso metodo.

- FE3 è stata valutata consultando direttamente le fonti congelate. LA2 è stata valutata prima sul solo materiale preregistrato, con 21 affermazioni sospese; l'estrazione mirata dalle tre fonti LA2 è avvenuta DOPO la compilazione delle sei schede e ha chiuso 18 di quelle sospensioni, correggendo anche alcune motivazioni. Le due feature non sono quindi state valutate nello stesso ordine di accesso alle fonti.

- Ne restano 3 non valutabili: G11 (schema del payload non prescritto), H9 (severità non prescritta per il fallimento di pubblicazione del job), H8 (parametro di backoff eliso dalla risposta, non risolvibile con le fonti perché il punto manca nell'output, non nel materiale).

- Durante la revisione sono emersi 13 rilievi sul protocollo: casi che i cinque criteri preregistrati non prevedevano. Sono stati registrati nelle note delle schede e i criteri NON sono stati riscritti in corso d'opera. Il confronto poggia quindi su una rubrica che si è rivelata incompleta rispetto agli output reali, e alcuni fenomeni ricorrenti (decisioni collocate fuori dai fence, elisione del parametro controverso, punti aperti non pertinenti, assunzioni che attribuiscono alle fonti prescrizioni inesistenti, incoerenze interne) non hanno un campo dedicato nei conteggi.

- Con sei campioni per feature e una sola revisione per campione, il confronto non consente di distinguere una differenza sistematica tra i due prompt da una variazione tra campioni dello stesso gruppo, se non quando la differenza è ampia. Va letto come indicazione, non come misura conclusiva.

## Istruzioni e campioni

Il testo può rivelare il braccio: questo non è un cieco garantito.
Leggere i [criteri preregistrati](REVIEW_CRITERIA.md), poi compilare le schede [FE3](REVIEW_FE3.md) e [LA2](REVIEW_LA2.md). Contengono risposte integrali in ordine di codice campione, senza etichetta, timestamp o contatori che possano suggerire il braccio.
Lasciare vuoto ciò che non è stato valutato, senza trasformarlo in zero. I CSV sono un'alternativa alle schede Markdown, non lavoro aggiuntivo richiesto.
In claims.csv aggiungere una riga per affermazione normativa atomica, con citazione e fonte.
Verdetti ammessi: supported / unsupported / conflicted / not_assessable.
In human_review.csv indicare Q dichiarati correttamente, F con entrambi i casi, casi mancanti dichiarati e omissioni silenziose.

| Campione | Feature | Risposta grezza |
|---|---|---|
| P01 | la2 | [P01](responses/P01.md) |
| P02 | la2 | [P02](responses/P02.md) |
| P03 | fe3 | [P03](responses/P03.md) |
| P04 | fe3 | [P04](responses/P04.md) |
| P05 | la2 | [P05](responses/P05.md) |
| P06 | fe3 | [P06](responses/P06.md) |
| P07 | la2 | [P07](responses/P07.md) |
| P08 | fe3 | [P08](responses/P08.md) |
| P09 | la2 | [P09](responses/P09.md) |
| P10 | la2 | [P10](responses/P10.md) |
| P11 | fe3 | [P11](responses/P11.md) |
| P12 | fe3 | [P12](responses/P12.md) |

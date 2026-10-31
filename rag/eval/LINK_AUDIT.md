# Audit dei collegamenti IMPLEMENTS

Strumento: `scripts/link_audit.py`. Modulo: `eval/link_audit.py`.

La precisione su questo repository è **non ancora misurata**: non ci sono annotazioni umane.

## Cosa non è

- Non è una recall. Si campionano solo archi già nel grafo.
- Non è una nuova soglia di linking. Il valore 0.45 si registra, non si cambia.
- Il peso e l'affidabilità non sono probabilità calibrate.
- Un'etichetta `IMPLEMENTA` non certifica conformità normativa.

## Popolazione e strati

Un'unità è un arco `IMPLEMENTS`. Lo strato è la fascia del peso registrato sull'arco (`sotto_0.60`, `0.60_0.75`, `0.75_0.90`, `da_0.90`, `peso_assente`) per il `kind` del simbolo. Il sigillo registra `N_h`, `n_h` e `π_h = n_h/N_h`. Se `n` è almeno il numero degli strati, ogni strato non vuoto entra con almeno una scheda e il campione può essere sproporzionato: la stima aggregata usa i pesi `N_h/N`.

Il sigillo (`sigillo.json`) tiene commit, versione dell'indice, modello di embedding, soglia, seed. Le schede (`schede.json`) non hanno peso, affidabilità, punteggi né margine. Chi giudica non deve aprire il sigillo.

## Etichette

| Etichetta | Quando |
|---|---|
| IMPLEMENTA | il codice realizza il comportamento specifico del passo |
| CORRELATO | stesso tema, senza evidenza di quella implementazione |
| ERRATO | il collegamento non è pertinente |
| NON_VALUTABILE | manca il contesto, o il requisito è ambiguo |

Ogni scheda compilata ha motivazione (almeno 20 caratteri) e annotatore. Due annotatori in disaccordo bloccano la misura finché non resta una sola etichetta. Il programma non sceglie al posto loro.

## Metriche

Precisione stretta = IMPLEMENTA / (IMPLEMENTA + CORRELATO + ERRATO). I NON_VALUTABILE stanno fuori da quel denominatore e hanno una quota a parte. Lo stato `misurato` richiede tutte le schede del campione, nessuno strato lasciato a zero, e nessun disaccordo. Altrimenti lo stato resta `precisione non ancora misurata`.

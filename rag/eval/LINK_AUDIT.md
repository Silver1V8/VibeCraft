# Audit dei collegamenti IMPLEMENTS

Strumento: `scripts/link_audit.py`. Modulo: `eval/link_audit.py`.

La precisione su questo repository è **non ancora misurata**: non ci sono annotazioni umane.

## Cosa non è

- Non è una recall. Si campionano solo archi già nel grafo.
- Non è una nuova soglia di linking. Il valore 0.45 si registra, non si cambia.
- Il peso e l'affidabilità non sono probabilità calibrate.
- Un'etichetta `IMPLEMENTA` non certifica conformità normativa.

## Popolazione e strati

Un'unità è un arco `IMPLEMENTS`. Lo strato è la fascia del peso registrato sull'arco (`sotto_0.60`, `0.60_0.75`, `0.75_0.90`, `da_0.90`, `peso_assente`) per il `kind` del simbolo. Il sigillo registra `N_h`, `n_h` e `π_h = n_h/N_h`. Se `n` lo consente, ogni strato entra con almeno `min(2, N_h)` schede, altrimenti con almeno una. Il campione può quindi essere sproporzionato, e la stima usa i pesi `w_h = N_h/n_h` (calcolati da `N_h` e `n_h`, non dal `π_h` arrotondato).

Disegno assunto: campione casuale semplice senza reinserimento dentro ogni strato, strati indipendenti. È il disegno di `draw_sample`. Le formule sotto non valgono per altri disegni.

Il sigillo (`sigillo.json`) tiene commit, versione dell'indice, modello di embedding, soglia, seed. Le schede (`schede.json`) non hanno peso, affidabilità, punteggi, margine né strato (lo strato contiene la fascia del peso). Chi giudica non deve aprire il sigillo.

## Etichette

| Etichetta | Quando |
|---|---|
| IMPLEMENTA | il codice realizza il comportamento specifico del passo |
| CORRELATO | stesso tema, senza evidenza di quella implementazione |
| ERRATO | il collegamento non è pertinente |
| NON_VALUTABILE | manca il contesto, o il requisito è ambiguo |

Ogni scheda compilata ha motivazione (almeno 20 caratteri) e annotatore. Due annotatori in disaccordo bloccano la misura finché non resta una sola etichetta. Il programma non sceglie al posto loro.

## Metriche

Metodologia **versione 2** (dal 1° novembre 2026), file `metriche-v2.json`.

### Estimando

La quota degli archi `IMPLEMENTS` etichettabili `IMPLEMENTA` fra gli archi **valutabili** (`IMPLEMENTA` + `CORRELATO` + `ERRATO`) della popolazione sottoposta ad audit. Non misura la recall e non dimostra conformità normativa. Vale per quel corpus e quell'indice (sigillo): non si estende da sola ad altri progetti, corpus o versioni dell'indice.

`NON_VALUTABILE` è un giudizio: il contesto non basta o il requisito è ambiguo. Non vuol dire `ERRATO` e non è un'annotazione mancante. Sta fuori dal denominatore della precisione e ha una sua quota pesata. Un'annotazione **mancante** invece è una scheda senza etichetta: blocca la misura.

### Stima puntuale

Per lo strato `h`: `I_h` = IMPLEMENTA nel campione, `A_h` = IMPLEMENTA + CORRELATO + ERRATO, `U_h` = NON_VALUTABILE, `w_h = N_h/n_h`.

```
estimated_implements_total   = Σ w_h·I_h
estimated_evaluable_total    = Σ w_h·A_h
population_precision         = Σ w_h·I_h / Σ w_h·A_h
weighted_non_evaluable_share = Σ w_h·U_h / Σ N_h
```

È uno stimatore di rapporto combinato: consistente, ma non esattamente non distorto con campioni piccoli, perché è il rapporto di due stime. Il calcolo è in frazioni esatte, e solo il risultato diventa float; la CLI arrotonda a 4 cifre soltanto a video.

Uno strato campionato tutto `NON_VALUTABILE` resta nella popolazione: dà zero ai due totali e pesa nella quota non valutabile. Non si rinormalizza sugli altri strati, e non si conclude che lo strato sia tutto non valutabile. Se `estimated_evaluable_total` è zero la precisione è `null` con il motivo, e mai zero.

`sample_precision` e `sample_non_evaluable_share` sono grezze sul campione, senza pesi: descrivono le schede e non stimano la popolazione.

### Intervallo

Conservativo al 95% nominale, **non esatto**:

1. per ogni strato con `n_h < N_h`, limiti ipergeometrici esatti sul totale di IMPLEMENTA e su quello dei valutabili, invertendo due test a una coda (`K` resta se `P(X ≥ x | K) > α'` e `P(X ≤ x | K) > α'`);
2. Bonferroni: sono `2H'` intervalli (`H'` = strati non censiti), ciascuno con errore `α/(2H')`, quindi `α' = 0.05/(4H')` per coda. Gli strati censiti hanno un limite esatto (`K = x`) e non consumano errore;
3. con tutti i limiti simultanei, che valgono insieme con probabilità ≥ 95% qualunque sia la dipendenza fra i due conteggi: inferiore = `Σ I_L / Σ A_U`, superiore = `Σ I_U / Σ max(A_L, I_U)`, cioè il massimo con il vincolo IMPLEMENTA ≤ valutabili, e 1 se quel denominatore è zero;
4. se i limiti ammettono zero valutabili in tutta la popolazione, `bounds` è `null` con il motivo.

La copertura nominale riguarda la procedura su estrazioni ripetute, non la probabilità che un singolo intervallo contenga il valore vero. L'intervallo copre solo l'errore di campionamento: non il disaccordo o l'errore degli annotatori, e non la generalizzazione ad altri corpus. Con un censimento completo l'intervallo è degenere, e va letto con questo limite.

L'intervallo può essere molto largo: con molti strati e poche schede per strato, Bonferroni costa caro. Sul disegno del campione `legacy` (33 strati, `n_h` fra 1 e 6), con una precisione ipotetica del 50% in ogni strato, verrebbe circa [0.03, 0.99]. Non si restringe a mano. Per renderlo informativo serve un `n` più grande o un nuovo disegno con meno strati, cioè un nuovo campione e non un ricalcolo.

### Stato

Lo stato `misurato` richiede tutte le schede del campione, nessuno strato lasciato a zero, nessun disaccordo, un sigillo coerente (`N_h`, `n_h`, `π_h`, schede per strato, `population`) e almeno un valutabile. Altrimenti lo stato resta `precisione non ancora misurata`, con `reason`.

### Contratto di `metriche-v2.json`

| Campo | Significato |
|---|---|
| `methodology_version` | `2` |
| `estimand` | la frase dell'estimando |
| `population_precision` | stima di rapporto pesata, o `null` |
| `estimated_implements_total`, `estimated_evaluable_total` | numeratore e denominatore stimati |
| `weighted_non_evaluable_share` / `sample_non_evaluable_share` | quota NON_VALUTABILE pesata / grezza |
| `sample_precision` | precisione grezza del campione |
| `interval` | `bounds`, `nominal_level`, `conservative`, `method`, `per_tail_alpha`, limiti dei totali, `reason`, `scope` |
| `annotation_completeness` | schede risolte, mancanti, discordi, con errori |
| `sampling_coverage` | disegno, strati campionati, popolazione coperta, `census` |
| `per_stratum` | `N_h`, `n_h`, `w_h`, conteggi, limiti simultanei per strato |
| `inputs` | sha256 di `sigillo.json` e `schede.json` usati |
| `reason`, `design_problems` | perché una metrica manca |

### Versione 1 e migrazione

Fino al 1° novembre 2026 `compute_metrics` dava in `aggregate_precision` la media delle precisioni locali pesata con `N_h`, rinormalizzata sugli strati con schede valutabili, più un Wald stratificato (`aggregate_interval95`) e un Wilson per strato. Quando la quota di NON_VALUTABILE cambia fra strati quella media non stima l'estimando: nella fixture di regressione dei test dà 0.65 al posto di 0.75. Il Wald era troppo stretto vicino a 0 e 1. I campi `aggregate_*`, `strict_precision` e `non_evaluable_share` non esistono più; `strict_precision` corrisponde a `sample_precision`. Nessun `metriche.json` della versione 1 è mai stato prodotto su annotazioni reali. Se ne esiste uno resta com'è, e va letto come versione 1: la versione 2 scrive un file a parte.

## Ricalcolo con annotazioni umane

1. Una persona compila `schede.json` (etichetta, motivazione, annotatore), senza aprire il sigillo.
2. `uv run python scripts/link_audit.py validate --run <cartella>` finché `complete` è `true`.
3. `uv run python scripts/link_audit.py metrics --run <cartella>` scrive `metriche-v2.json` con gli sha256 degli input. Se il file esiste ed è stato calcolato da schede diverse, il comando si ferma: spostalo prima. `metriche.json` (versione 1) non si tocca mai.

## Campione pronto

Il 1° novembre 2026 è stato estratto il primo campione sul progetto `legacy`:

```bash
uv run python scripts/link_audit.py sample --project legacy --out ../projects/legacy/eval/link_audit/2026-11-01 --n 80 --seed 1
```

80 archi su 1221, 33 strati, indice `v20261030T111436`. Sta sotto `projects/`, fuori da git: le schede contengono estratti del codice e dei documenti del progetto. Anche `rag/eval/link_audit/` è in `.gitignore` per lo stesso motivo.

Stato: **in attesa di annotazioni**. Le etichette le mette una persona, scheda per scheda; nessuno strumento le compila al suo posto.

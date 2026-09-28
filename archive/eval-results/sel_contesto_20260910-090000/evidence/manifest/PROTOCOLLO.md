# Protocollo preregistrato — selezione del contesto di `/ask`

Scritto **prima** di eseguire le varianti. Le uniche misure gia' prese sono
quelle di composizione della [mappa](MAPPA_PARAMETRI.md), che servivano a
formulare le ipotesi e non contengono risposte del modello.

Prompt, modello e impostazioni di generazione restano **congelati** al valore
verificato: prompt **originale** (W1 e' NON_APPLICARE), `qwen3.5:9b`,
`num_ctx` 16384, `think` false, `temperature` 0.1. Cosi' la sola variabile e' la
selezione del contesto.

## Ipotesi

**H1 — pertinenza del ponte codice.** Il ponte `collect_implementing_code`
inietta codice scelto per **prossimita' nel grafo**, senza alcun filtro di
pertinenza alla domanda; il ramo semantico, che quel filtro ha (`min_score`
0.45), sulle domande PDF non fa entrare nulla. Applicare al ponte lo **stesso
segnale gia' disponibile** (coseno domanda→simbolo) elimina il codice irrilevante
senza toccare quello pertinente.

**H2 — pavimento di pertinenza del ramo grafo.** `graph_context_min_ratio`
esiste, e' **relativo** al miglior ColBERT della domanda (quindi robusto al
cambio di scala fra query) ed e' **spento** (0.0). Accenderlo dovrebbe togliere
le sezioni raggiunte via grafo che non c'entrano con la domanda, senza toccare
quelle che completano una catena multihop.

**H0 (controllo)** — riduzione semplice dei tetti, senza pertinenza: serve a
distinguere «meno contesto» da «contesto piu' pertinente». Se H0 fa quanto H1/H2,
la pertinenza non sta aggiungendo nulla e va scartata come complicazione.

## Varianti iniziali, e ordine delle prove

Dalla piu' economica alla piu' costosa. Ogni variante e' provata **una alla
volta**; si passa alla successiva solo se la precedente supera i controlli
economici.

| # | variante | come | costo |
|---|---|---|---|
| **S0** | attuale | — | gia' misurata |
| **S1** | controllo: tetti ridotti | `code_context_total_snippets` 12→6, `graph_context_max_chunks` 3→2 | sonda, ~2 min |
| **S2** | **H1**: pertinenza sul ponte codice | nuovo pavimento `code_link_min_question_score`, riusa il coseno domanda→simbolo | sonda + test |
| **S3** | **H2**: pavimento grafo | `graph_context_min_ratio` 0.0 → {0.3, 0.5} | sonda, harness grafo |
| **S4** | S2+S3 | composizione delle due | sonda |

## Criteri di selezione (preregistrati)

Una variante e' **ammissibile** solo se, sulle sonde in-process (nessuna
generazione):

1. **copertura golden** — nessuna fonte attesa di `eval/golden_set.yaml` esce
   dalla finestra rispetto a S0;
2. **copertura multihop** — le catene complete a livello di documento non
   diminuiscono rispetto a S0 (misura di `calibrate_graph_context`);
3. **codice pertinente** — sulle domande di codice del golden, i blocchi del
   **ramo semantico** restano invariati;
4. **precedenze** — le coppie di `precedence_pairs` restano invariate;
5. **nessuna esclusione senza motivo registrato** — ogni blocco escluso porta
   segnale e valore.

Fra le ammissibili si sceglie con questa priorita', **decisa ora**:
catene multihop complete → copertura golden → riduzione del contesto mediano →
a parita', la variante con **meno parametri cambiati**.

## Metriche

**Sonda (senza generazione):** blocchi per ramo; caratteri per ramo e totali;
copertura delle fonti attese (golden, multihop, PDF); esclusioni con motivo.

**Batch (con generazione, solo sulla variante scelta):** correttezza e
completezza; associazione valore↔oggetto; attribuzione a documento e a sezione
(schermo corretto `assi2`); citazioni (`quoted_spans`); affermazioni non
supportate; astensioni, errori, troncamenti; caratteri e token stimati del
contesto; latenza.

## Condizioni di abbandono

- perdita di **una sola** fonte attesa del golden → variante scartata;
- perdita di una catena multihop completa a livello di documento → scartata;
- perdita di codice del ramo **semantico** su domande di codice → scartata;
- regressione sui diagnostici di governance (10 casi) → scartata;
- se **tutte** le varianti falliscono i controlli economici, non si avvia alcun
  batch di generazione e il verdetto e' BLOCCATO con la causa nominata.

## Budget del contesto — quattro grandezze distinte

| grandezza | misura | valore attuale |
|---|---|---|
| prompt **fisso** | `tests/test_ask_prompt_cost.py`, stima ~3 char/token | 954 token stimati su budget 1000 |
| budget **documenti** | caratteri dei blocchi semantici + grafo | mediana 23 083 char (PDF) |
| budget **codice** | caratteri del blocco `CODICE ESISTENTE` | mediana 8 635 char (PDF) |
| **totale** inviato | tutto il prompt | mediana ~30 563 char ≈ 10 188 token stimati |
| spazio per la risposta | `num_ctx` − prompt | ≈ 6 200 token stimati |

**Nessun obiettivo di 3 000 token.** Quel valore veniva da una sonda a selezione
privilegiata («solo il PDF nel contesto»), che conosceva la risposta attesa: e'
una diagnosi, non un bersaglio. Qui si misura il compromesso e si sceglie con i
criteri sopra.

## Vincoli sulla selezione

Non puo' usare: id o testo esatto delle domande del golden; nomi dei cataloghi
come eccezione; risposte attese; annotazioni di test non disponibili in
produzione. Nessun classificatore nuovo: solo segnali gia' calcolati nel percorso.

## Insieme separato

Un piccolo insieme di domande **nuove**, con attese verificabili, su documenti
del corpus diversi dai due cataloghi, viene scritto **prima** della scelta finale
e usato **una volta sola**, dopo la selezione. Se dovesse servire a correggere la
variante, verra' dichiarato e **non** verra' piu' chiamato holdout.

Le otto domande PDF **non** sono un holdout: sono casi noti di regressione.

## Calibrazione

- I tetti di composizione (`graph_context_max_chunks`, `graph_context_min_ratio`,
  tetti del codice) **non** appartengono alla griglia S11: si verificano con
  `eval/calibrate_graph_context.py` e con le sonde di copertura.
- Se una variante richiedesse di toccare `boost_alpha`, `default_weight`,
  `unclassified_weight` o `section_restatement_weight`, si riesegue
  `eval/calibrate_authority.py` con protocollo, fold e seed previsti. **L'ipotesi
  e' che non serva**, e la verifica e' che quei quattro restino ai valori S11.

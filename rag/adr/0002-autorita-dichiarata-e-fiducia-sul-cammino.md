# 0002 — Autorità dichiarata e fiducia sul cammino del grafo

**Stato:** Accettato e attuato. La tabella più sotto è la fotografia del 18 agosto 2026, non lo stato del codice.
**Data:** 2026-08-18
**Origine:** confronto con l'articolo di Andrea Magini «Problema di retrieval? No, problema
di autorità» (HARO — Qdrant + NetworkX), letto integralmente.

> **Non riaprire questi punti.** Quando la nota è stata scritta, `authority:` nel frontmatter
> non entrava nel ranking, `boost_alpha` era 0.1 e l'espansione del grafo non portava una
> fiducia sul cammino. Nel codice attuale quel divario è chiuso:
> [`_authority_weight`](../core/retrieval.py) legge il coefficiente dichiarato,
> [`rag_config.yaml`](../rag_config.yaml) ha `authority.boost_alpha: 0.3` (calibrato il
> 2026-09-07; il fallback in `core/config.py` è 0.4 se la chiave manca) e
> [`trust_paths`](../core/graph_ops.py) calcola la fiducia sul cammino. L'invariante
> «freschezza ≠ autorità» è protetta da
> `tests/test_retrieval.py::test_peso_autorita_e_indipendente_dai_campi_temporali`.
> La tabella «Stato di VibeCraft al confronto» descrive il problema com'era.

---

## Contesto

L'articolo descrive lo schema di autorità di HARO, un Graph-RAG con lo **stesso identico
stack del nostro** (Qdrant per i vettori, NetworkX per il grafo) e lo stesso tipo di corpus
(dominio governato, con processi di revisione). Le sue tesi operative sono cinque:

1. **Etichetta ≠ peso.** L'etichetta (*normativa, storica, operativa, informativa*) dice
   **cosa** è una fonte; il peso numerico dice **quanto** conta nel ranking. Sono due campi
   distinti, non due nomi per la stessa cosa.
2. **Il peso entra nella formula**, non nella UI: `score = (1 − distanza semantica) × peso`.
   Una spec normativa lessicalmente meno pertinente batte comunque una nota informale che
   matcha alla perfezione le parole della query.
3. **Fiducia sul cammino del grafo.** Ogni arco ha una **natura**: *strutturale* (dedotta da
   analisi statica o dal filesystem, certa), *curata* (validata da un umano), *inferita*
   (euristica, quindi penalizzata). Il punteggio di un nodo raggiunto via grafo è
   `1 / lunghezza_cammino × Π(affidabilità degli archi attraversati)` sul cammino più breve
   (BFS). Esplicitamente **non** PageRank (nessuna centralità globale) e **non** HITS
   (lì il punteggio è dinamico per query; qui è statico per tipo).
4. **Drift detection ≠ autorità.** L'hash sa che un file è cambiato, non se ci si può ancora
   fidare del contenuto. *«Fresco non vuol dire autorevole»*: una spec di due anni mai toccata
   resta la fonte primaria, una change di ieri può essere già superata. Confonderli è
   «uno degli errori più silenziosi che si possa fare in un sistema di retrieval».
5. **Caveat di applicabilità.** Lo schema regge perché il corpus ha una gerarchia naturale di
   tipi documentali. Su recensioni, appunti personali o web aperto va ripensato da capo.

Il caveat (5) **si applica a noi**: `docs/` è un corpus governato, con `classification`,
`status`, `version` e changelog obbligatori per policy. Lo schema è quindi trasferibile.

## Stato di VibeCraft al confronto

Il confronto non è «ci manca tutto». Su alcuni assi siamo **avanti** rispetto all'articolo;
su altri abbiamo metadati obbligatori scritti in ogni documento e **mai letti dal codice**.

| # | Tesi dell'articolo | Stato VibeCraft | Esito |
|---|---|---|---|
| 1 | Etichetta di autorità distinta dal peso | `classification` (etichetta) + `AUTHORITY_CLASS_WEIGHTS` (peso) in `rag_config.yaml`; 5 classi contro le 4 di HARO | ✅ **già fatto, più granulare** |
| 1b | Peso della fonte **non classificata** basso (0.3) | `default_weight: 0.7` copre **sia** le classi note-ma-non-elencate (REQUIREMENTS) **sia** le fonti senza alcun frontmatter | ❌ **conflazione** (vedi D2) |
| 2 | Peso per-fonte dentro la formula | `authority:` è **obbligatorio** nel frontmatter (policy §3) e imposto da [REGOLA-VAL-08]; è nel payload Qdrant e negli attributi del nodo — e `_authority_weight()` **non lo legge** | ❌ **metadato morto** (vedi D1) |
| 2b | Moltiplicazione piena `score × peso` | `score × (1 − α + α·peso)` con `α = 0.1`: attenuazione che rende l'autorità quasi inerte | ⚠️ **divergenza dalla norma** (vedi D3) |
| 3 | Natura dell'arco (strutturale/curata/inferita) | Le tre nature **esistono già di fatto** — `PART_OF`/`MENTIONS` strutturali, gli archi da frontmatter curati, `IMPLEMENTS`/`REFERENCES` inferiti per coseno — ma nessun arco è etichettato | ❌ **da esplicitare** |
| 3b | Punteggio di fiducia sul cammino BFS | `bfs_expand()` restituisce un **set piatto**: nessuna lunghezza di cammino, nessuna affidabilità. La fase 6 «graph expansion» di [REGOLA-WF-01] alimenta solo la visualizzazione e le ancore del codice, non il ranking | ❌ **assente** |
| 4 | Drift ≠ autorità | `check_drift()` è hash-based e separata; **nessun** segnale temporale entra nel ranking | ✅ **non commettiamo l'errore** — ma non è protetto da nulla (vedi D5) |
| 5 | Applicabilità al corpus governato | `docs/` è governato per policy | ✅ |

### Le quattro scoperte che contano

**D1 — `authority:` del frontmatter è un metadato morto.**
La policy di versionamento (`docs/00_meta_governance/policy_versionamento_documentale.md` §3)
elenca `authority` fra i campi **obbligatori** («Coefficiente moltiplicativo di autorità della
fonte») e ogni documento lo dichiara: `safeguards_security.md` 0.98, `spec_graph_rag_ingestion.md`
0.87, `README.md` 0.75. Il valore viene propagato fino in fondo — `c["metadata"] = metadata`
finisce nel payload Qdrant (`indexing.py:262`) e in `G.add_node(rel_path, **metadata)` — e poi
`_authority_weight()` **lo ignora**, ricavando il peso dalla sola `classification`. È una
violazione diretta di [REGOLA-VAL-08], che prescrive di moltiplicare lo score del reranker
«per il coefficiente di `authority` del frontmatter della sorgente».

**D2 — La fonte non classificata pesa come una spec.**
`read_document()` restituisce frontmatter vuoto per tutto ciò che non è `.md` (pdf, docx, xlsx,
txt). Un PDF importato senza alcun metadato di governance arriva al ranking con
`classification=""` → `default_weight` = **0.70**, cioè lo stesso peso di una spec
`REQUIREMENTS` calibrata. Nell'articolo quella fonte pesa **0.3**. Il difetto è oggi latente
solo perché il corpus è composto quasi esclusivamente da norme ad alta autorità — la nota di
calibrazione del 2026-07-22 lo dice già: *«il parametro oggi è di fatto inerte; tornerà a
contare quando il corpus rimescolerà classi diverse»*. L'intake importa documenti a 0.70, e
appena quel materiale entra il difetto smette di essere latente.

**D3 — `boost_alpha = 0.1` non è un parametro validato, è una metrica satura.**
La calibrazione del 2026-07-22 ha esito `NON_APPLICARE` con guadagno **+0.000**, e la nota
metodologica è esplicita: a k=10 e k=5 la recall è **satura a 1.000 su tutta la griglia**, e
anche a k=2 «alpha=0.0, cioè autorità del tutto ignorata, pareggia col default». Non abbiamo
misurato che l'autorità sia inutile: abbiamo misurato su un golden set che **non la mette alla
prova**. Nessuno dei 49 casi contrappone una fonte informale lessicalmente più vicina a una
normativa più pertinente — che è esattamente lo scenario per cui il meccanismo esiste.

**D4 — Un rischio che il nostro corpus non ha ancora, ma che la nostra architettura prepara.**
L'articolo racconta una scelta controintuitiva di HARO: il glossario di dominio, editabile da
chiunque tramite UI, pesa **0.95**; una change storica verificata su Git, versionata e
immutabile, pesa **0.75–0.9**. La motivazione è netta: *«il glossario è validato oggi da un
umano. La change era vera ieri, magari non lo è più oggi. Essere tracciato su Git non significa
essere ancora valido.»*

> **Aggiornamento S5 (2026-08-24): non è più un rischio futuro.** La cartella si è popolata:
> contiene 6 file `*-canvas-review.md`, e sono **privi di frontmatter**, quindi arrivano al
> ranking come fonte non classificata (0.30 dopo S1, 0.70 prima). Tre dei dieci casi
> avversariali di S5 usano proprio quei file come distrattore.

Da noi `docs/03_changes_historical/` era vuota alla stesura di questo ADR, ma è una cartella **prevista dal contratto
documentale** e destinata a raccogliere le feature archiviate da `archive_feature()`. Quando si
popolerà, conterrà esattamente il materiale descritto: change immutabili, tracciate, versionate
— e per questo facilmente scambiate per autorevoli. `AUTHORITY_CLASS_WEIGHTS` non ha oggi una
voce per quella classe, quindi quel materiale ricadrebbe su `default_weight` = 0.70, cioè
**alla pari di una spec `REQUIREMENTS` vigente**. È lo stesso difetto di D2, con un innesco
diverso e già schedulato dal nostro stesso design. S1 lo rende almeno esprimibile; la voce di
classe va aggiunta quando la cartella si popola, non dopo.

## Decisioni

**Adottiamo**, in cinque interventi indipendenti e sequenziabili (prompt operativi in
[0002-prompts/](../../archive/adr/0002-prompts/)):

- **S1** — Onorare `authority` del frontmatter come coefficiente per-documento, con la classe
  come fallback; separare il peso della fonte **non classificata** da quello della classe
  non elencata. Chiude D1 e D2 e riallinea il codice a [REGOLA-VAL-08].
- **S2** — Etichettare ogni arco del grafo con `nature` (strutturale/curata/inferita) e
  `reliability`. Puro metadato, nessun cambio di ranking: è il substrato di S3 e S4.
- **S3** — `trust_paths()`: punteggio `1/len(cammino) × Π(affidabilità)` su BFS, e sua
  applicazione al retrieval. Completa la fase 6 di [REGOLA-WF-01].
- **S4** — Rendere operativo `SUPERA_IN_PRIORITÀ`, oggi dichiarato nel corpus
  (`safeguards_security.md`) e non letto da nessuna riga di codice: è la risoluzione esplicita
  dei conflitti fra fonti.
- **S5** — Golden set **avversariale** sull'autorità + ricalibrazione a un k non saturo. Senza
  questo, S1–S4 non sono misurabili e la calibrazione resta cieca. ✅ **Fatto il 2026-08-24**;
  l'esito — l'autorità serve, ma è già tarata bene: nessun parametro modificato — è in
  *Esito misurato (S5, 2026-08-24)* più sotto.

**Non adottiamo:**

- **La moltiplicazione piena `score × peso` al posto di `(1 − α + α·peso)`.** L'articolo la usa,
  e [REGOLA-VAL-08] la prescrive, ma la nostra unica misura reale (calibrazione 2026-07-14) ha
  mostrato che il boost pieno **sovra-promuoveva i safeguard `IRON_MEMORY` generici rispetto
  alle spec `REQUIREMENTS` specifiche attese**, facendo scendere la recall held-out. La forma
  attenuata resta, con `α` trattato come parametro empirico da ricalibrare in S5 su un golden
  set che discrimini. La divergenza dalla norma è quindi **consapevole e documentata**, non
  una svista: se S5 mostrasse che α alto vince, si allinea il codice; altrimenti si emenda
  [REGOLA-VAL-08] con la forma attenuata. Nessuna delle due va fatta a intuito.
  **Chiuso in S5 (2026-08-24): α alto perde.** Sul golden set avversariale la moltiplicazione
  piena (α = 1) costa 15.2 punti di recall@5 (0.966 → 0.814) e 10.2 di recall@10 (0.983 →
  0.881) sull'intero set, e non è nemmeno il massimo sui casi avversariali (α = 0.8 ne corregge
  di più). [REGOLA-VAL-08] è stata **emendata** (spec v2.2.0) per prescrivere la forma attenuata
  effettivamente implementata: la divergenza fra norma e codice non è più aperta.
- **PageRank / EigenTrust / HITS.** L'articolo è esplicito nel non usarli, e ha ragione per il
  nostro caso: il nostro grafo ha una manciata di documenti fortemente interconnessi, dove la
  centralità globale non discrimina, e il punteggio ci serve **relativo alla query** (quanto mi
  fido del cammino che ho percorso per arrivare qui), non assoluto.
- **Qualunque segnale di freschezza nel peso di autorità** (`date`, `last_updated`, `version`,
  mtime, hash di drift). È l'errore che l'articolo chiama «il più silenzioso»; oggi non lo
  commettiamo per caso, S1 lo blinda con un test di regressione. Il solo segnale temporale
  ammesso resta `status` (`ARCHIVED`/`DEPRECATED`/…), che è un **giudizio umano**, non una data.

## Esito misurato (S5, 2026-08-24)

S5 ha costruito il golden set avversariale e ricalibrato. Tutti i numeri qui sotto sono
misurati sul corpus **committato** (26 documenti, 175 chunk, indice `v20260824T150025`).

### Il golden set ora discrimina — ed è la conquista vera della sessione

`eval/golden_set.yaml` passa da 49 a 59 casi. I 10 nuovi sono marcati `adversarial: true` e
contrappongono, sul corpus reale, una fonte a bassa autorità che matcha lessicalmente meglio
della normativa che risponde: sette hanno per distrattore un documento informativo
`METHODOLOGY` (peso 0.50), tre un file di `03_changes_historical/` **senza frontmatter**
(peso 0.30, il caso che D2 descrive). Ognuno è stato verificato **eseguendo la query**: in
tutti e dieci il distrattore precede la fonte attesa (rango del distrattore → rango
dell'atteso: 1→2, 1→2, 1→2, 1→2, 2→3, 1→3, 1→5, 3→5, 1→2, 1→3).

Cinque casi che ci si aspettava fallissero e che invece il sistema già superava sono stati
**scartati**, e due altri sono stati scartati perché *disonesti*: la fonte che davamo per
attesa non rispondeva davvero alla domanda, quindi il loro fallimento non sarebbe stato un
difetto di ranking. Sono elencati nel golden set. Un caso che il sistema supera già gonfia la
recall e riproduce il difetto che questa sessione doveva correggere.

Con quei dieci casi la saturazione sparisce dove contava: recall@5 passa da 1.000 (satura, non
informativa) a 0.966. **La ricalibrazione del 2026-07-22 non aveva misurato che l'autorità
fosse inutile: aveva misurato un golden set che non la metteva alla prova.** D3 è confermato.

### S1–S4: molto sul meccanismo, quasi nulla sul ranking

Misurando le stesse 59 query nella configurazione **pre-S1** (`use_declared: false`, fonte non
classificata appiattita su 0.70) e in quella **post-S1–S4** di produzione:

| | recall@1 | recall@2 | recall@5 | recall@10 | avversariali sbagliati a rango 1 |
|---|---|---|---|---|---|
| PRIMA di S1–S4 | 0.492 | 0.763 | 0.949 | 0.983 | **10 / 10** |
| DOPO S1–S4 | 0.475 | 0.763 | **0.966** | 0.983 | **10 / 10** |

S1–S4 hanno spostato **+0.017 di recall@5** (un caso e mezzo su 59) e **−0.017 di recall@1**.
Sui 10 casi avversariali — quelli costruiti apposta per il meccanismo — non hanno spostato
**nulla**: dieci su dieci sbagliati a rango 1 prima, dieci su dieci dopo.

La ragione è aritmetica e sarebbe stata prevedibile: con `boost_alpha = 0.1` il moltiplicatore
vive fra 0.93 e 1.00, un'escursione del 7% che non ribalta distacchi ColBERT di 0.05–0.15. S1
ha reso l'autorità *esprimibile* — `authority` del frontmatter non è più un metadato morto, la
fonte non classificata non pesa più come una spec — ma alla forza a cui il boost è configurato
quell'espressività quasi non arriva al ranking.

### L'autorità però serve, e al k che conta è già tarata bene

È il risultato che il golden set precedente non poteva vedere. Al **k=5** — e si vedrà fra un
attimo perché è il k che governa questo sistema — sul sottoinsieme avversariale:

| configurazione | avversariali recall@5 |
|---|---|
| autorità **spenta** (α = 0.0) | 0.900 |
| **produzione attuale** (α = 0.1) | **1.000** |

Spegnere l'autorità perde un caso avversariale su dieci. Il meccanismo non è inerte: è l'unico
segnale che, su quei casi, distingue la fonte normativa dal distrattore lessicalmente più
vicino. Semplicemente non lavora a rango 1, lavora nella finestra.

### La calibrazione: tre k, tre risposte, una sola decisione

5-fold CV su 5 seed, griglia a tre assi (9 α × 6 `default_weight` × 5 `unclassified_weight`):

| k | default held-out | calibrato held-out | guadagno | dev.std | esito dello script |
|---|---|---|---|---|---|
| 1 | 0.474 | 0.495 | **+0.021** | 0.014 | `APPLICA` (α = 0.3, uw = 0.1) |
| 2 | 0.763 | 0.776 | +0.013 | 0.017 | `NON_APPLICARE` (sotto soglia) |
| 5 | 0.967 | 0.967 | **+0.000** | **0.000** | `NON_APPLICARE` — **l'attuale È l'ottimo di griglia** |

**Decisione: NON APPLICARE. Nessun parametro è stato modificato.** Il guadagno a k=1 è reale e
stabile (4 seed su 5 positivi), ma ottimizza la metrica sbagliata per questo sistema, e la
ragione è nel codice, non nelle preferenze:

`/ask` inietta nel contesto fino a **8 sezioni governate** (`retrieval.governed_max_chunks: 8`),
e l'LLM le legge tutte. Ciò che determina la qualità della risposta è quindi se la fonte giusta
**entra nella finestra**, non a che rango ci entra. La metrica che corrisponde a quel consumo è
recall@5–@10, non recall@1. E lì la configurazione proposta a k=1 è **peggiore**:

| | recall@1 | recall@2 | recall@5 | recall@10 | avversariali r@1 |
|---|---|---|---|---|---|
| produzione attuale (α = 0.1) | 0.475 | 0.763 | **0.966** | **0.983** | 0.000 |
| proposta k=1 (α = 0.3) | 0.542 | 0.780 | 0.932 | 0.949 | 0.400 |

Applicarla comprerebbe l'ordinamento *dentro* una finestra che l'LLM legge comunque per intero,
pagandolo con 3.4 punti di recall@5 e @10 — cioè con fonti che dalla finestra **escono del
tutto**. A k=5 il confronto non è nemmeno in discussione: la configurazione attuale è già
l'ottimo della griglia, con guadagno +0.000 e deviazione standard **0.000 su tutti e cinque i
seed**. Non è un pareggio fortunato: è l'ottimo.

### Un difetto della calibrazione, trovato strada facendo

`default_weight` **non governa alcun documento di questo corpus**: dei 26, quattordici
dichiarano `authority` nel frontmatter (che ha la precedenza, dopo S1) e sei hanno la classe
elencata in `class_weights`; i restanti sei non hanno alcuna `classification` e ricadono su
`unclassified_weight`. Zero documenti passano dal ramo `default_weight`. È un **asse morto**:
i suoi sei valori danno recall identiche al millesimo.

Non era innocuo. Con un asse morto ogni α ha decine di configurazioni *esattamente*
equivalenti, e `grid_best` scioglieva il pareggio in base all'ordine di iterazione — dentro la
k-fold, quindi, in modo diverso da fold a fold, iniettando rumore puro nella stima held-out.
Misurato: il guadagno a k=2 è passato da −0.011 a +0.013 fra due corse che differivano per la
sola ri-segmentazione di **un documento su 26**. Uno spostamento di 0.024, quasi il doppio
della dev.std riportata sui seed — perché quella dev.std misura il rumore di *partizione*, non
questo, e da sola dava una falsa impressione di stabilità.

Corretto: a parità di recall vince ora la **configurazione attuale di produzione**, non la
prima incontrata (un pareggio non è un miglioramento, e non deve poter cambiare il ranking).
Lo script segnala inoltre esplicitamente gli assi morti, invece di lasciar credere che il
valore «vincente» su quell'asse significhi qualcosa. Entrambi i comportamenti sono inchiodati
da test.

Una seconda nota metodologica: `eval/calibrate_authority.py` usava **un solo seed**. Su una
delle corse intermedie il seed 0 da solo dava +0.018 — sopra la soglia di applicazione — mentre
la media sui cinque seed era **−0.007**, e quel +0.018 era l'unico positivo su cinque. Il
default è ora a cinque seed con deviazione standard riportata: uno split solo non basta a
giustificare un cambio del ranking di produzione.

### Risposta alla domanda che l'ADR aveva lasciato aperta

**L'autorità serve al nostro corpus?** **Sì**, e la risposta è cambiata rispetto a quella che
il vecchio golden set lasciava supporre: al k che il sistema consuma, spegnerla costa un caso
avversariale su dieci. Ma serve **alla forza a cui è già configurata**: nessun punto della
griglia batte `α = 0.1` a k=5, e alzare α migliora il rango 1 peggiorando ciò che arriva
all'LLM. Il parametro non era validato — ora lo è, e il valore che aveva è quello giusto.

Resta vero che il margine è sottile e che l'effetto vive quasi tutto sui 10 casi avversariali:
con 26 documenti di cui **tutti e 26 `ENFORCED`** e una maggioranza di norme ad alta autorità,
il ranking semantico è già quasi sempre corretto da solo. Non è un difetto di implementazione:
è la composizione del corpus.

### Cosa il corpus non permette di misurare

Tre dei cinque tipi di caso richiesti da S5 **non sono costruibili**, e la ragione è un
risultato in sé:

- **`ENFORCED` contro `ARCHIVED`/`DEPRECATED`:** zero documenti su 26 hanno uno `status`
  diverso da `ENFORCED`. `archived_decay` (0.3) non è mai stato esercitato da alcun dato
  reale. I sei file di `03_changes_historical/` ci arrivano vicino per effetto, ma per la
  strada sbagliata: pesano 0.30 perché sono **non classificati**, non perché archiviati.
- **`SUPERA_IN_PRIORITÀ` (S4):** l'unica dichiarazione del corpus, in
  `safeguards_security.md`, ha per target `QUALSIASI_DECISIONE_IMPLEMENTATIVA_LOCALE`, che non
  è un documento. `precedence_pairs()` richiede che entrambi i capi siano `doc_id` presenti
  nei risultati, quindi **nessuna coppia si forma mai**: S4 è oggi codice corretto e inerte.
  Il conflitto reale che meriterebbe la dichiarazione esiste ed è noto —
  `vibe_coding_workflow.md` ridefinisce `[REGOLA-CLEAN-*]` con numerazione collidente rispetto
  a `coding_standards.md` — ma nessuno dei due autori l'ha dichiarato.
- **Risposta raggiungibile solo via grafo (S3):** la fase 6 di `[REGOLA-WF-01]` vive in `/ask`
  (`api/routes_retrieval.py`), mentre il golden set interroga `GET /api/retrieve`. Non è
  misurabile da qui con nessun caso, e non lo sarà finché non esiste un set di valutazione
  sulle **risposte**.

Per renderli misurabili servono, nel corpus di test: **almeno 2 documenti con `status`
`ARCHIVED`/`DEPRECATED` su argomenti già coperti da un documento vigente**, e **almeno una
coppia di documenti che dichiari `SUPERA_IN_PRIORITÀ` verso un altro documento reale** (la
coppia `coding_standards` / `vibe_coding_workflow` è il candidato naturale). Non sono stati
inventati qui: fabbricare documenti per far quadrare il piano è precisamente il fallimento che
questa sessione doveva evitare.

### `graph_context_min_ratio` resta a 0.0, e ora si sa perché

Sulle 59 domande il ramo del grafo inietta 118 sezioni. Il rapporto fra il loro MaxSim ColBERT
e il migliore della stessa domanda è `min 0.327 / mediana 0.620 / max 0.811`; il **peggior**
risultato che il ramo semantico tiene comunque, sulle stesse domande, sta a `min 0.603 /
mediana 0.804 / max 0.909`. Le due distribuzioni quasi non si sovrappongono: ciò che il grafo
inietta è per costruzione meno pertinente del peggio che il ramo semantico accetta — che è
esattamente lo scopo del ramo. Un pavimento tarato sulla barra semantica scarterebbe il 98%
delle iniezioni, cioè spegnerebbe il ramo con un altro nome; sotto 0.33 non scarta nulla. Non
esiste un valore intermedio *scegliibile* senza sapere se una sezione a 0.44 è rumore o
contesto utile, e quel giudizio riguarda la risposta di `/ask`, che nessun golden set del
progetto misura. Il parametro resta a 0.0 con la distribuzione registrata in `rag_config.yaml`:
è il difetto D3 applicato a se stesso, e la risposta corretta è non inventare il numero.

### Riproducibilità

```bash
cd rag
uv run python -m eval.run                            # 59 casi, k = 1 2 5 10, flag di saturazione
uv run python -m eval.calibrate_authority --k 5      # il k che governa /ask: +0.000, l'attuale è l'ottimo
uv run python -m eval.calibrate_authority --k 1      # il k con più margine: +0.021, ma ottimizza la metrica sbagliata
```

### Addendum 2026-08-25 — il corpus è cambiato sotto le misure

**Tutti i numeri della sezione qui sopra si riferiscono al corpus del 2026-08-24**, e
vanno letti come il record di quello stato. Il 2026-08-25 `docs/` è stato riportato al
**baseline committato**: tre file (`coding_standards.md`, `vibe_coding_workflow.md`,
`safeguards_security.md`) erano fermi su disco alla v1.0.0 dominio-specifica mentre in
git c'era la v2.0.0 cross-progetto, e il RAG indicizza il disco. La divergenza era
invisibile a `git status` perché quei file sono `skip-worktree`; ora c'è un check
dedicato (`docs_git` in `check_index_integrity`).

Il corpus passa da 175 a 180 chunk. Cosa cambia, misurato:

| | 2026-08-24 (disco divergente) | 2026-08-25 (baseline) |
|---|---|---|
| 59 casi, recall@1 | 0.475 | **0.576** |
| 59 casi, recall@2 | 0.763 | **0.797** |
| 59 casi, recall@5 | 0.966 | **0.983** |
| 59 casi, recall@10 | 0.983 | **1.000** (satura) |
| casi avversariali | 10 | **9** |

**La decisione NON_APPLICARE regge, e più saldamente di prima.** Ricalibrazione a k=5
(5-fold, 5 seed) sul corpus ripristinato: default 0.983 held-out, calibrato 0.983,
guadagno **+0.000 con dev.std 0.000 su tutti e cinque i seed**. La configurazione attuale
resta l'ottimo di griglia. Nessun parametro modificato.

**Una conclusione della sezione precedente NON regge più, e va detto.** Là era scritto che
al k che conta l'autorità *serve*, perché spegnerla perdeva un caso avversariale su dieci
(1.000 contro 0.900 a k=5). Sul corpus ripristinato quel margine **è sparito**: a α = 0.1
l'autorità spenta e la configurazione di produzione danno lo **stesso** 0.889 sui 9 casi
avversariali a k=5. Alla forza a cui è configurata, oggi, l'autorità è **neutra** su quei
casi. Recupera il caso solo a α = 0.2–0.3 (fino a 1.000), che però continua a non
sopravvivere alla validazione. Il quadro complessivo non cambia — il meccanismo resta
giusto e la taratura resta quella che il golden set sostiene — ma l'affermazione «serve»
va sostituita con **«non danneggia, e non è ancora dimostrabile che aiuti»**.

**S1–S4, per contro, ora un effetto ce l'hanno.** Sullo stesso confronto pre-S1 / post-S1–S4
che prima dava tabelle identiche:

| | recall@1 | recall@2 | recall@5 | recall@10 |
|---|---|---|---|---|
| PRIMA di S1–S4 | 0.576 | 0.780 | 0.966 | 1.000 |
| DOPO S1–S4 | 0.576 | **0.797** | **0.983** | 1.000 |

Due casi su 59 in più entro k=2 e k=5. È poco, ed è sempre invisibile a rango 1 sui casi
avversariali (0.000 in entrambe le configurazioni), ma non è più zero.

**Effetti sul golden set**, entrambi conseguenze della stessa divergenza:

- *«tracciabilità bidirezionale nei commenti»* **non è più un caso avversariale**. Lo era
  perché `vibe_coding_workflow.md` v1.0.0 ridefiniva `[REGOLA-CLEAN-*]` con numerazione
  collidente; la v2.0.0 rimanda a `coding_standards.md` invece di duplicarlo. Sparita la
  collisione l'atteso va a rango 1: marcatore rimosso, perché un caso che il sistema
  supera gonfia la recall del sottoinsieme.
- I due casi scartati in S5 come *disonesti* — «magic numbers» e «isolamento delle regole
  di business» — **non lo erano**: sono `[REGOLA-CLEAN-05]` e `[CLEAN-06]`, presenti nel
  baseline e assenti dalla copia di lavoro su cui li avevo valutati. Il giudizio era una
  conseguenza della divergenza. Non sono stati riaggiunti, ma la nota nel golden set è
  stata corretta.

**L'eval-gate è stato spostato da k=10 a k=5** (`min_recall` 0.90 → 0.95). Con tutti i 59
casi entro top-10 il gate a k=10 è tornato cieco — e questa volta **lo ha detto da solo**,
con l'alert di saturazione introdotto da S5: è la prima volta che quel guardrail scatta su
un caso reale, ed è servito esattamente a quello.

**Seguito immediato: l'istanziazione (stesso giorno).** Ripristinare la baseline ha reso
il corpus *templato*: `/ask` rispondeva `<<RISORSA_CONTESA>>` dove prima diceva
`posti_residui`. La recall misura se recuperi la sezione giusta, non se la risposta è
utilizzabile — e nessuna delle metriche qui sopra vedeva quel peggioramento.
`safeguards_security.md` è stato quindi **istanziato sul dominio** (Sezione 0 compilata,
60 occorrenze di segnaposto risolte, v2.1.0), dichiarandolo con `instantiated_from:` così
il check `docs_git` lo classifica `instantiated` e non `diverging`. Effetto misurato:

| | baseline templata | dopo l'istanziazione |
|---|---|---|
| 59 casi, recall@2 | 0.797 | **0.814** |
| 59 casi, recall@5 | 0.983 | **1.000** (satura) |
| 9 avversariali, recall@2 | 0.556 | **0.667** |
| 9 avversariali, recall@5 | 0.889 | **1.000** (satura) |

L'eval-gate è sceso ancora, da k=5 a **k=2** (`min_recall` 0.95 → 0.75): l'alert di
saturazione è scattato una seconda volta nello stesso giorno, e questa volta su una
metrica che era stata scelta proprio perché discriminava. **k=2 è l'ultimo k utile**: se
saturasse anche quello, la risposta non è abbassare un'altra soglia ma estendere il
golden set con casi che il sistema sbaglia.

Non sono stati reinnestati i blocchi `Regola AFU Correlata` della v1.0.0: rimandano a
otto famiglie di regole (`CONC`, `AUTH`, `AUDIT`, `UT`, `EV`, `RQ`, `ANL`, `CRUD`) che
**nessun documento del corpus definisce** — l'AFU non esiste più. Innestarli avrebbe
prodotto una quindicina di riferimenti orfani, cioè nodi entità che puntano al nulla.
`Il Perimetro` e `Il Failure Mode` sono invece stati innestati (v2.2.0): 7 + 6 blocchi,
118 righe di dominio — funzioni applicative, tabelle e route coinvolte, procedura esatta di
fallimento. I 3 riferimenti orfani che contenevano sono stati risolti togliendo il token
fra quadre e conservando il senso; quelli a regole che esistono davvero hanno avuto
corretta la **provenienza** (`[REGOLA-CLEAN-*]` rimanda a `coding_standards.md`, non a
un'AFU che non c'è più). Nel documento non resta un solo riferimento orfano.

**Il prezzo, misurato e non nascosto.** Innesto + scheda `BUDGET_ANNUO` nel glossario
(v1.1.0, che ha chiuso il debito dichiarato in Sezione 0) fanno scendere `recall@2` da
0.814 a **0.797** e `recall@5` da 1.000 a **0.983**. Quattro casi perdono **un solo rango**
ciascuno, nessuno esce dai primi dieci. Due sono proprio quelli su budget e posti
disponibili, dove la nuova scheda `BUDGET_ANNUO` compete legittimamente con la fonte
attesa. È il costo atteso di un corpus più ricco, non una regressione del ranking: la
recall misura se recuperi la sezione attesa, e più contenuto pertinente significa più
concorrenza per gli stessi posti. Ottimizzare il corpus per proteggere la metrica sarebbe
esattamente il rovescio del metodo.

**Ciò che il ripristino NON ha cambiato:** il corpus resta 26 documenti tutti `ENFORCED`,
quindi `archived_decay` resta non esercitato; e l'unica dichiarazione `SUPERA_IN_PRIORITÀ`
continua a puntare a un non-documento, quindi S4 resta codice corretto e inerte. I due
trigger di riapertura elencati sotto restano aperti entrambi.

## Conseguenze

- Il ranking cambia: S1 è l'unico intervento che tocca l'ordinamento di produzione senza
  passare da un parametro, quindi **deve** essere gated dall'eval golden set prima del merge.
- Gli attributi d'arco di S2 non alterano `_edge_set()` (che confronta solo `(u, v, relation)`),
  quindi l'invariante **delta ≡ full** dell'indicizzazione incrementale resta valida per
  costruzione — ma va comunque verificata dai test di `check_graph_consistency`.
- `docs/02_specs_normative/spec_graph_rag_ingestion.md` andrà emendato al termine di S5, con
  version bump ([REGOLA-VAL-09]), per registrare l'esito su [REGOLA-VAL-08].
- **L'autorità deve arrivare fino al prompt, non fermarsi al ranking** (misurato in A3,
  2026-09-03). Riordinare i candidati non basta quando il consumatore è un LLM che riceve
  8 sezioni e le legge tutte: senza la classe nell'intestazione di ogni blocco il modello
  ri-ordina per prosa, e la fonte che *spiega* — più densa di parole chiave — batte quella
  che *vincola*. È lo stesso difetto che questo ADR corregge, un livello più in là.
  `core/retrieval.source_label` e `authority_scale` alimentano `[CLASSE-FONTI]`; l'indagine
  e la misura stanno in `rag/AUDIT.md`. **Chi tocca il ranking di autorità deve chiedersi
  anche cosa ne vede il prompt.**

## Trigger di riapertura

- Il corpus smette di essere governato (import massivo di materiale senza frontmatter): i pesi
  dichiarati a mano non scalano, servirebbe autorità **calcolata** (link/citazioni), come
  l'articolo stesso indica per il web aperto.
- Il grafo cresce oltre ~10⁴ nodi documentali: il BFS per query di S3 va sostituito con
  cammini precalcolati o con una vera centralità.
- **Il corpus acquisisce documenti `ARCHIVED`/`DEPRECATED`, o una precedenza dichiarata fra due
  documenti reali.** Sono le due condizioni che oggi rendono `archived_decay` e S4 codice
  corretto ma mai esercitato: quando si verificano, i casi avversariali corrispondenti diventano
  costruibili e la calibrazione va rifatta — a un `k` non saturo, su più seed.
- **Il rapporto fra casi facili e casi avversariali nel golden set cambia in modo sostanziale.**
  Il `NON_APPLICARE` del 2026-08-24 non dice che l'autorità non serve: dice che 10 casi su 59 non
  bastano a farla vincere in validazione. La conclusione va rimisurata, non ereditata.

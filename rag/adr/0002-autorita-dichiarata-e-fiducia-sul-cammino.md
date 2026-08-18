# 0002 — Autorità dichiarata e fiducia sul cammino del grafo

**Stato:** Accettato (piano di lavoro in [0002-prompts/](0002-prompts/))
**Data:** 2026-08-18
**Origine:** confronto con l'articolo di Andrea Magini «Problema di retrieval? No, problema
di autorità» (HARO — Qdrant + NetworkX), letto integralmente.

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

Da noi `docs/03_changes_historical/` è oggi vuota, ma è una cartella **prevista dal contratto
documentale** e destinata a raccogliere le feature archiviate da `archive_feature()`. Quando si
popolerà, conterrà esattamente il materiale descritto: change immutabili, tracciate, versionate
— e per questo facilmente scambiate per autorevoli. `AUTHORITY_CLASS_WEIGHTS` non ha oggi una
voce per quella classe, quindi quel materiale ricadrebbe su `default_weight` = 0.70, cioè
**alla pari di una spec `REQUIREMENTS` vigente**. È lo stesso difetto di D2, con un innesco
diverso e già schedulato dal nostro stesso design. S1 lo rende almeno esprimibile; la voce di
classe va aggiunta quando la cartella si popola, non dopo.

## Decisioni

**Adottiamo**, in cinque interventi indipendenti e sequenziabili (prompt operativi in
[0002-prompts/](0002-prompts/)):

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
  questo, S1–S4 non sono misurabili e la calibrazione resta cieca.

**Non adottiamo:**

- **La moltiplicazione piena `score × peso` al posto di `(1 − α + α·peso)`.** L'articolo la usa,
  e [REGOLA-VAL-08] la prescrive, ma la nostra unica misura reale (calibrazione 2026-07-14) ha
  mostrato che il boost pieno **sovra-promuoveva i safeguard `IRON_MEMORY` generici rispetto
  alle spec `REQUIREMENTS` specifiche attese**, facendo scendere la recall held-out. La forma
  attenuata resta, con `α` trattato come parametro empirico da ricalibrare in S5 su un golden
  set che discrimini. La divergenza dalla norma è quindi **consapevole e documentata**, non
  una svista: se S5 mostrasse che α alto vince, si allinea il codice; altrimenti si emenda
  [REGOLA-VAL-08] con la forma attenuata. Nessuna delle due va fatta a intuito.
- **PageRank / EigenTrust / HITS.** L'articolo è esplicito nel non usarli, e ha ragione per il
  nostro caso: il nostro grafo ha una manciata di documenti fortemente interconnessi, dove la
  centralità globale non discrimina, e il punteggio ci serve **relativo alla query** (quanto mi
  fido del cammino che ho percorso per arrivare qui), non assoluto.
- **Qualunque segnale di freschezza nel peso di autorità** (`date`, `last_updated`, `version`,
  mtime, hash di drift). È l'errore che l'articolo chiama «il più silenzioso»; oggi non lo
  commettiamo per caso, S1 lo blinda con un test di regressione. Il solo segnale temporale
  ammesso resta `status` (`ARCHIVED`/`DEPRECATED`/…), che è un **giudizio umano**, non una data.

## Conseguenze

- Il ranking cambia: S1 è l'unico intervento che tocca l'ordinamento di produzione senza
  passare da un parametro, quindi **deve** essere gated dall'eval golden set prima del merge.
- Gli attributi d'arco di S2 non alterano `_edge_set()` (che confronta solo `(u, v, relation)`),
  quindi l'invariante **delta ≡ full** dell'indicizzazione incrementale resta valida per
  costruzione — ma va comunque verificata dai test di `check_graph_consistency`.
- `docs/02_specs_normative/spec_graph_rag_ingestion.md` andrà emendato al termine di S5, con
  version bump ([REGOLA-VAL-09]), per registrare l'esito su [REGOLA-VAL-08].

## Trigger di riapertura

- Il corpus smette di essere governato (import massivo di materiale senza frontmatter): i pesi
  dichiarati a mano non scalano, servirebbe autorità **calcolata** (link/citazioni), come
  l'articolo stesso indica per il web aperto.
- Il grafo cresce oltre ~10⁴ nodi documentali: il BFS per query di S3 va sostituito con
  cammini precalcolati o con una vera centralità.

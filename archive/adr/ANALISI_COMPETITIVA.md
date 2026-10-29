# ANALISI COMPETITIVA — VibeCraft self-hosted contro le alternative gestite

> **In archive dal 2026-10-29.** Fotografia del 13 settembre 2026, mai mergiata prima: i
> numeri della sezione 1 e lo stato delle raccomandazioni della sezione 6 sono di quella
> data, non di oggi (`README.md` della root per lo stato corrente).

**Data:** 2026-09-13 · **Commit di riferimento:** 5047247 · **Stato:** nota strategica, non
normativa · **Autore:** analisi architetturale su richiesta dell'owner

> **Perché sta qui e non in `docs/`.** Vale la stessa ragione degli ADR: `docs/` è il corpus
> indicizzato dal RAG, e una pagina piena di nomi di prodotti, prezzi di listino e confronti
> commerciali inquinerebbe il retrieval — competerebbe semanticamente con le spec normative
> senza essere una fonte di governance. Promuoverla in `docs/04_knowledge_informative/` è un
> atto deliberato che richiede reindicizzazione e una corsa di `eval/run.py`, non un
> `git mv`.

> **Cosa è, cosa non è.** È un confronto fra architetture, basato per la parte VibeCraft su
> **misure già presenti nel repository** (bench, `DISTRIBUTION.md`, calibrazioni in
> `rag_config.yaml`) e per la parte concorrente su **listini pubblici noti a maggio 2026**.
> I prezzi dei servizi gestiti cambiano e sono spesso negoziati: qui valgono come **ordini
> di grandezza**, e ogni decisione di spesa va rifatta sul listino del giorno. Dove un numero
> è una stima derivata e non una misura, è detto esplicitamente.

---

## 1. Il soggetto del confronto, misurato

Prima di confrontare serve dire cosa si confronta. VibeCraft non è "un database a grafo": è
una **pipeline Graph-RAG governata** che usa un grafo. La distinzione decide metà
dell'analisi, perché i concorrenti della categoria 1 vendono il grafo e basta.

| Dimensione | Stato attuale (misurato) | Fonte |
|---|---|---|
| Modello di deployment | Self-hosted single-node, loopback; stack Docker unico (cpu / gpu / host-ollama) | `README.md`, `docker-compose.yml` |
| Grafo | NetworkX in-memory, persistito come node-link JSON (`graph.json`) | `core/artifacts.py` |
| Vettori | Qdrant (denso + sparso) per i documenti; ColBERT multivettore e densi in sidecar `.npz` in RAM | `core/artifacts.py`, `core/retrieval.py` |
| Codice | Nodi-simbolo nel grafo, vettori densi in `code.npz`, ~4.000 simboli | `README.md` (rag) |
| Inferenza | Ollama locale (`qwen3.5:9b`) di default; provider Anthropic opzionale per singolo step, con tetto di spesa giornaliero | `rag_config.yaml`, `core/llm.py` |
| Embedding | `bge-m3` locale: CPU per le query, GPU per il reindex | `api/deps.py`, README §Embedding |
| Corpus di riferimento | 26 documenti / 180 chunk / 612 elementi indicizzati | `rag_config.yaml` (note di calibrazione), `DISTRIBUTION.md` |
| Latenza `GET /api/retrieve` | p50 **494 ms**, p95 **647 ms** | `eval/results/bench_20260721T084815Z.json` |
| Latenza `POST /ask` | ~**28 s** a caldo, ~**49 s** medio lato client nel bench; dominata dall'LLM, non dal retrieval | `DISTRIBUTION.md`, bench |
| Full rebuild | ~**13 s** su RTX 3070 Ti · ~**10 min** su CPU (46 vs 1 chunk/s) | `DISTRIBUTION.md` |
| Reindex incrementale | **4,8 s** di overhead fisso a delta vuoto (il delta vero non è ancora automatizzato nel bench) | bench, sezione `incremental_noop` |
| Qualità retrieval | r@1 0.741 · r@5 0.966 · r@10 1.000 su 58 casi golden; multihop r@10 0.890 | note di calibrazione S11 |
| Rilascio dell'indice | Blue/green versionato, eval-gate `min_recall 0.90`, rollback spostando un puntatore, retention 5 versioni, alias Qdrant riconciliato al boot | README §Artefatti |
| Superficie | 57 route HTTP (24 POST), API key, dependency anti-cross-site; MCP locale **read-only a 3 tool** | `SECURITY_SURFACE.md` |
| Token spesi per costruire il grafo | **zero** — gli archi sono dichiarati nel frontmatter o calcolati per coseno | `core/indexing.py`, `core/chunking.py` |

Il tratto che nessun concorrente di questa lista offre è l'ultimo più i tre che seguono:
**ri-ponderazione per autorità dichiarata** (`authority.boost_alpha`, calibrata con CV a 5
fold su 5 seed), **fiducia sul cammino** del grafo (`graph_ops.trust_paths`) e **astensione
leggibile a macchina** (`status: "abstained"`). Sono semantica di governance, non
infrastruttura: si comprano solo costruendoli.

---

## 2. Cosa vendono davvero le tre categorie

**Categoria 1 — Database a grafo gestiti** (Neo4j AuraDB, AWS Neptune / Neptune Analytics,
Azure Cosmos DB for Apache Gremlin, Memgraph Cloud). Vendono **disponibilità e operatività
del solo storage**: backup automatici, HA, patching, scaling verticale. Non contengono
retrieval ibrido, non contengono rerank, non contengono un LLM e non contengono alcuna
nozione di autorità della fonte. Sostituirebbero in VibeCraft il file `graph.json` e circa
un modulo (`graph_ops.py`) — cioè la parte che oggi costa meno e rompe meno.

**Categoria 2 — Framework e pipeline GraphRAG cloud-ready** (Microsoft GraphRAG su Azure,
DataStax Astra DB con ibrido vector/graph, FalkorDB Cloud). Qui il confronto è vero: sono
alternative alla pipeline, non allo storage. La differenza strutturale è **come nasce il
grafo**. GraphRAG di Microsoft lo estrae con l'LLM da ogni chunk e poi sintetizza report di
community gerarchiche: potentissimo su corpora dove le relazioni **non sono dichiarate** —
e costosissimo in token, per la stessa ragione. VibeCraft assume l'opposto: in un corpus di
governance le relazioni **sono dichiarate** (frontmatter, `edges`, precedenze), quindi
estrarle con un modello significherebbe pagare token per indovinare ciò che il documento
già afferma, con il rischio di indovinare male.

**Categoria 3 — SaaS verticali enterprise** (Glean, Sinequa). Vendono **connettori e
permessi**: centinaia di integrazioni SaaS, ranking permission-aware per utente, ricerca
aziendale a livello di organizzazione. Il ranking è una scatola nera: non si calibra
`boost_alpha`, non si ispeziona perché una fonte ha vinto, non si impone che la norma batta
la sua parafrasi. Non sono un concorrente di VibeCraft sullo stesso terreno: sono un
concorrente **di budget**, e il loro modello di prezzo è per posto a sedere.

---

## 3. Matrice comparativa

Legenda dei costi: ordini di grandezza da listino pubblico noto a maggio 2026, **da
riverificare**. "Infra" = solo il servizio citato, senza LLM, embedding e pipeline.

| | **VibeCraft (self-hosted)** | **Neo4j AuraDB** | **AWS Neptune / Neptune Analytics** | **Cosmos DB Gremlin** | **Memgraph / FalkorDB Cloud** | **MS GraphRAG su Azure** | **Astra DB (vector+graph)** | **Glean / Sinequa** |
|---|---|---|---|---|---|---|---|---|
| **Costo mensile ricorrente** | ~150–400 €, di cui ≥70 % tempo umano; hardware ammortizzato 35–50 €, energia 10–20 €, token **0** | da ~65 $ (istanza 1 GB) e crescita ~lineare con la RAM; centinaia di $ a 8 GB | istanza r6-large 24/7 ≈ 250–300 $ + storage + I/O; **Analytics** con minimi di m-NCU → ordine 1.000 $+ se acceso | RU/s provisioned: base bassa (decine di $), ma i traversal profondi consumano RU in modo poco prevedibile | tier iniziali da decine di $, prezzo sulla RAM dell'istanza | nessuna licenza (OSS) ma **costo in token dominante** + AI Search + Cosmos + AOAI | consumption (read/write unit + storage), da free tier a centinaia di $ | **per posto**: ordine 40–50 $/utente/mese con minimi annuali; enterprise a trattativa |
| **Costo di costruzione / aggiornamento del grafo** | **0 token.** Archi dichiarati + IMPLEMENTS per coseno. Full rebuild 13 s (GPU) / 10 min (CPU); incrementale con manifest a hash | n.a. (lo storage non costruisce il grafo) | n.a.; Analytics fattura il tempo di calcolo | n.a. | n.a. | estrazione LLM per chunk + community report: **stima 100–300 $ per full rebuild** su corpus da ~10 k chunk con modello di fascia alta, ~10× meno con un modello piccolo, **ripetuto a ogni ri-estrazione** | costo di embedding + write unit | opaco: incluso nel canone |
| **Multi-hop** | BFS deterministica in RAM + fiducia sul cammino; retrieve p50 494 ms; catene multihop r@10 0.890 | Cypher/GQL maturo, ottimo su traversal profondi, scala oltre la RAM di una macchina | openCypher/Gremlin/SPARQL; Analytics pensato per algoritmi su grafi grandi | Gremlin, ma il modello RU penalizza i traversal lunghi | in-memory, latenze molto basse su hop brevi | il multi-hop è sostituito dalle community report: forte sul "globale", debole sul cammino esatto | ibrido vettore/grafo, traversal meno profondi | nessun controllo: il cammino non è esponibile |
| **Privacy / egress** | **Zero egress nel default**: LLM ed embedder locali, loopback, API key obbligatoria in Docker. Egress solo se si attiva il provider Anthropic, per singolo step e con tetto di spesa | dati nel cloud del vendor, region selezionabile | dati nella VPC del cliente — il miglior profilo della categoria 1 | dati nel tenant Azure | dati nel cloud del vendor | prompt e corpus passano da un modello ospitato per **costruire** l'indice, non solo per interrogarlo | dati nel cloud del vendor | **il corpus intero** viene indicizzato dal vendor; multi-tenancy e retention da contratto |
| **Sforzo operativo** | **Tutto a carico tuo**: backup manuali, nessun HA, nessun SLA. Mitigato da blue/green + eval-gate + rollback + riconciliazione già implementati | backup, patch, HA inclusi | idem, con IAM e VPC da gestire | idem | idem | infra Azure da assemblare e mantenere | idem | zero: è il valore che vendono |
| **Lock-in** | **Minimo**: artefatti JSON/`.npz` ispezionabili, nessun pickle, provider LLM intercambiabile per step, Qdrant sostituibile. Il vincolo vero è NetworkX + i formati propri, non un fornitore | Cypher/GQL è standard; il piano gestito no | openCypher/SPARQL standard, ma servizio solo AWS | API Gremlin proprietaria nel contesto Cosmos: il lock-in più duro della riga | Cypher-like, self-host possibile | OSS: il codice è portabile, la spesa in token no | API proprietarie | **totale**: nessuna portabilità del ranking né dell'indice |
| **Governance del ranking** | Autorità dichiarata, precedenza fra fonti in conflitto, penalità di sezione-parafrasi, astensione esplicita, eval-gate sul rilascio | assente | assente | assente | assente | ranking sulle community, non sull'autorità | assente | scatola nera |

---

## 4. SWOT tecnica

### Punti di forza (strutturali, non congiunturali)

1. **Il grafo costa zero token.** È l'asimmetria economica più grande del confronto. Le
   pipeline che estraggono le relazioni con un LLM pagano l'aggiornamento in proporzione al
   corpus, ogni volta; qui un aggiornamento costa secondi di GPU. Su un corpus che cambia
   spesso — ed è il caso di una baseline di governance — la differenza è fra un costo
   marginale trascurabile e una voce di budget.
2. **Semantica di governance che nessuno vende.** Autorità dichiarata, decadimento
   dell'archiviato, precedenza dichiarata, fiducia sul cammino, penalità alla sezione che
   parafrasa la norma invece di stabilirla. Sono calibrati con disciplina statistica
   (held-out, deviazione standard, più seed), non scelti a occhio.
3. **Confine dei dati non negoziato ma strutturale.** Non "il fornitore promette di non
   addestrare": il testo non esce dalla macchina perché non c'è nessuno a cui mandarlo.
4. **Rilascio dell'indice già di grado industriale.** Blue/green con collection candidate,
   eval-gate a soglia di recall, swap atomico di un puntatore, rollback rifiutato *prima* di
   ogni mutazione se la collection target non esiste più, GC e riconciliazione sotto writer
   lock. Molti prodotti gestiti non offrono un equivalente del *gate qualitativo*: offrono
   backup, che è un'altra cosa.
5. **Artefatti ispezionabili, zero pickle.** Un JSON e degli `.npz`: la migrazione a
   qualunque altro stack parte da file leggibili, non da un dump proprietario.
6. **Costo marginale per domanda ≈ 0.** Il confronto con i SaaS per posto si vince
   banalmente sotto una certa soglia di utenti (§5).

### Debolezze (strutturali, e vanno dette)

1. **Un utente alla volta, di fatto.** `/ask` costa 28–49 s dominati dall'inferenza locale,
   senza streaming: la percezione è peggiore della cifra. Una singola istanza Ollama
   serializza; il writer lock serializza le build.
2. **La RAM è il tetto del corpus.** Il grafo intero, i multivettori ColBERT e i densi
   stanno in memoria. *Stima derivata dalle dimensioni* (1024 dim × fp16 × ~400 token per
   chunk ≈ 0,8 MB/chunk): ~150 MB agli attuali 180 chunk, ~4 GB a 5.000 chunk, ~8 GB a
   10.000. Va **misurata**, non creduta — ma l'ordine di grandezza indica dove sta il muro.
3. **Nessun HA, nessun DR dichiarato.** Lo stato è `database/versions/` più il volume Qdrant.
   Non esiste oggi un RPO/RTO scritto né una prova di restore periodica. È il deficit più
   facile da colmare e il più imbarazzante da lasciare aperto.
4. **Scalabilità solo verticale.** Non c'è sharding, non c'è replica di lettura, non c'è un
   percorso di crescita che non passi da "una macchina più grossa".
5. **Il bus factor è il TCO nascosto.** La calibrazione di `boost_alpha` e del peso di
   sezione è documentata in modo esemplare, e proprio per questo è evidente quanta
   conoscenza specialistica serva per toccarla. Un servizio gestito non ha questo problema
   perché non ha questo parametro.
6. **Il delta incrementale vero non è misurato.** Il bench misura solo il no-op (4,8 s):
   senza la curva del delta reale non si può dichiarare una soglia di volume oltre la quale
   l'incrementale smette di bastare.
7. **Niente connettori.** SharePoint, Confluence, Jira, Slack: l'intake passa da una review
   in staging, che è una scelta di governance corretta e un costo di adozione reale.

### Opportunità

- Il ciclo Intake & Import e l'MCP read-only rendono VibeCraft **usabile come fonte per
  agenti esterni** (Claude Code, Cursor) senza esporre il corpus: è un posizionamento che i
  database gestiti non occupano.
- I formati aperti permettono un'adozione **ibrida**: tenere la governance in casa e
  affittare solo il calcolo pesante quando serve.
- La conformità (AI Act, segreti industriali, dati sanitari o legali) rende il "zero egress"
  un requisito d'ingresso, non una preferenza: lì le categorie 2 e 3 sono escluse a priori.

### Minacce

- I provider gestiti stanno integrando il GraphRAG nelle loro piattaforme: la distanza
  funzionale si accorcia, anche se la semantica di autorità resta un differenziale.
- Il costo dei token dei modelli ospitati scende in fretta: l'argomento "costruire il grafo
  con l'LLM è caro" è vero oggi e va rimisurato ogni sei mesi.
- Il corpus cresce da solo; il tetto di RAM arriva senza preavviso e si manifesta come
  degrado, non come errore.

---

## 5. Soglia di convenienza (break-even)

### Il modello di costo, esplicito

```
TCO_self(mese)    = ammortamento_hw/36 + energia + (ore_manutenzione × tariffa) + token_opzionali
                  ≈ 35–50 € + 10–20 € + (2–4 h × 50–80 €/h) + 0 €
                  ≈ 150–400 €/mese      ← il termine umano vale il 70–85 % del totale

TCO_managed(mese) = istanze + storage + I/O + token di indicizzazione + token di query + posti
```

Il numero che conta non è il prezzo dell'hardware: è che **il tempo umano domina il TCO
self-hosted**, e che un database gestito **non lo elimina**, perché la parte che consuma
tempo in VibeCraft (pipeline, calibrazione, eval, prompt, intake) resta comunque tua. È
l'errore di valutazione più comune in questa categoria di decisioni: si confronta un canone
con zero, quando si dovrebbe confrontare un canone con la *frazione* di manutenzione che
davvero rimuove.

### Dove VibeCraft vince, e non è discutibile

| Condizione | Perché vince |
|---|---|
| Corpus ≤ ~5.000 chunk (≈ 500–1.000 documenti) | Tutto sta in RAM, full rebuild in decine di secondi, rerank esatto senza approssimazioni |
| Utenti concorrenti ≤ ~5–10 con domande sporadiche | Con ~30 s di servizio, una coda a slot singolo regge ~2 domande/minuto: sopra la media, sotto i picchi |
| Aggiornamenti frequenti del corpus | Ogni ri-estrazione LLM altrove costa token; qui costa secondi |
| Vincolo di zero egress | Le categorie 2 e 3 sono fuori per definizione; resta solo Neptune-in-VPC, che però non dà la pipeline |
| Necessità di governare il ranking | Nessun concorrente espone i parametri: non è una questione di prezzo |
| Meno di ~7–10 utenti rispetto a un SaaS per posto | A 40–50 $/posto/mese, 300 €/mese self-hosted pareggiano intorno ai 7 utenti — e sotto quella soglia la SaaS non è mai competitiva sul prezzo |

### Dove il passaggio al gestito diventa inevitabile

| Soglia | Segnale che l'hai superata | Cosa serve |
|---|---|---|
| **Corpus > ~10.000 chunk** *(stima da misurare)* | I sidecar `.npz` non entrano in RAM; il caricamento allo swap di versione diventa il collo di bottiglia | Vettori fuori dal processo (Qdrant multivettore o memmap), o un grafo gestito |
| **Grafo > ~10⁶ archi** | `graph.json` cresce a dimensione GB e la riscrittura per versione diventa decine di secondi | Un database a grafo vero (Neo4j/Neptune), con il costo di riscrivere `graph_ops.py` |
| **> 20–30 utenti attivi o SLA di latenza < 10 s** | Le domande si accodano; lo streaming assente rende la percezione peggiore del dato | Inferenza con batching continuo (vLLM/TGI) o inferenza gestita, e repliche di lettura |
| **Disponibilità 24/7 con RTO < 1 h** | Un guasto hardware ferma tutto e non esiste una prova di restore | HA gestito, oppure DR proprio con prova periodica (§6.2) |
| **Più scrittori concorrenti / multi-tenancy** | Il writer lock diventa contesa; servono indici separati per team | Sharding per progetto, o piattaforma gestita multi-tenant |
| **Ricerca aziendale su 50+ sorgenti SaaS con permessi per utente** | Il costo dei connettori supera qualunque risparmio infrastrutturale | Glean/Sinequa — e qui il confronto non è nemmeno tecnico |

**Sintesi onesta.** Nell'inviluppo attuale — corpus di centinaia di documenti, pochi utenti,
vincolo di riservatezza forte — non esiste un'alternativa gestita che convenga: costerebbe
di più, darebbe meno controllo sul ranking e non toglierebbe quasi nessuna delle ore di
manutenzione che dominano il TCO. Il passaggio non sarà mai una questione di prezzo: sarà
un tetto di **RAM**, di **concorrenza** o di **disponibilità** a imporlo, e i tre arrivano
prima del costo.

---

## 6. Raccomandazioni architetturali

Tre interventi, ordinati per rapporto fra deficit colmato e lavoro richiesto. Tutti e tre
riusano meccanismi che esistono già: nessuno chiede una riscrittura.

### 6.1 Percorso di lettura replicabile + concorrenza sull'inferenza

**Deficit colmato:** scalabilità orizzontale, il "un utente alla volta".

Le directory di versione sono **immutabili** e `CURRENT` è un puntatore atomico: è già la
metà difficile di una replica di lettura. Ne segue che *N* processi di sola lettura possono
servire la stessa versione dallo stesso volume, con il writer che resta unico — il modello
blue/green non va cambiato, va **sfruttato**. Insieme a questo: l'LLM dietro un server con
batching continuo (vLLM/TGI, o più slot Ollama) e **streaming della risposta**, che il
README già identifica come l'unico modo di abbassare la latenza percepita. Lo streaming da
solo cambia la percezione di `/ask` più di qualunque ottimizzazione del retrieval, che a
494 ms di p50 non è il problema.

**Come si misura la riuscita:** `scripts/bench.py` esteso con una sezione di concorrenza
(k richieste parallele, p50/p95 per k = 1, 4, 8) — oggi il bench è tutto sequenziale e quindi
cieco esattamente sul limite che questo intervento tocca.

### 6.2 Backup e disaster recovery dichiarati, con prova di restore

**Deficit colmato:** la pipeline di backup che il gestito regala e qui non esiste.

Lo stato completo è `database/versions/*` più il volume Qdrant — e ogni versione **porta già
il proprio manifest con gli hash SHA-256** di sorgenti e artefatti. Il materiale per un DR
verificabile c'è tutto; manca il ciclo che lo usa:

1. snapshot Qdrant + copia cifrata offsite della versione attiva, su schedule (gli script
   `nightly_consistency.*` sono il posto naturale dove agganciarlo);
2. verifica dell'integrità del backup **contro `index_manifest.json`**, non contro sé stesso;
3. **prova di restore periodica** su directory temporanea, con esito registrato — un backup
   mai ripristinato non è un backup, è una speranza;
4. RPO e RTO scritti a numero, così diventano una cosa che si misura invece di una che si
   promette.

È l'intervento con il miglior rapporto valore/lavoro dell'intera lista: colma il deficit più
spesso citato contro il self-hosting usando dati che il sistema già produce.

### 6.3 Togliere la RAM dal percorso critico, e misurare il delta incrementale vero

**Deficit colmato:** indicizzazione incrementale e tetto di volume.

Due mosse, distinte:

- **Sidecar memmappabili o esternalizzati.** `colbert.npz` è l'artefatto che cresce più in
  fretta ed è l'unico motivo per cui il corpus ha un tetto di RAM. Passare a `.npy`
  memmappati per chunk (o ai multivettori nativi di Qdrant) sposta il tetto dalla RAM al
  disco, che costa due ordini di grandezza meno. Prerequisito onesto: **misurare** prima la
  dimensione reale in memoria, perché la stima di §4.2 è derivata dalle dimensioni dei
  vettori, non pesata.
- **Curva del delta incrementale.** Oggi il bench misura 4,8 s di overhead a delta vuoto e
  il README dichiara che il delta vero va misurato a mano. Automatizzarlo — *k* file
  modificati per k = 1, 10, 100, con durata dal journal — produce la curva che manca, e con
  essa la soglia oltre la quale l'incrementale non basta più e serve lo sharding per
  progetto. Senza quella curva, ogni soglia di volume dichiarata in questo documento resta
  una stima: è il primo numero da rendere una misura.

---

## 7. Cosa invaliderebbe questa analisi

Nello spirito dei trigger di riapertura degli ADR di questo repository:

- **Il costo dei token crolla di un ordine di grandezza.** L'argomento "costruire il grafo
  con un LLM è caro" si indebolisce; resta quello sulla riservatezza e sull'indovinare
  relazioni già dichiarate.
- **Il corpus supera i 5.000 chunk.** Le soglie di §5 vanno rimisurate, non ricalcolate: la
  stima di RAM è derivata, non pesata.
- **Gli utenti concorrenti superano la decina.** Il confronto si sposta dal costo alla
  latenza, dove il self-hosted oggi perde.
- **Un fornitore gestito espone il ranking.** Se un servizio permette di dichiarare
  l'autorità delle fonti e di calibrarla su un golden set, il differenziale principale di
  VibeCraft smette di essere strutturale.
- **Arriva un requisito di connettori SaaS.** Allora il confronto vero è con Glean/Sinequa,
  e il terreno non è più questo.

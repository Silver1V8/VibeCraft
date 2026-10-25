# S5 — Golden set avversariale sull'autorità e ricalibrazione onesta

> **Sessione autonoma.** Prompt self-contained.
> **Dipendenze:** va eseguita **per ultima**, dopo S1–S4.
> **Rischio:** BASSO sul codice, ALTO sul valore — senza questa sessione, S1–S4 non sono
> misurabili e il piano resta un atto di fede.
> **Modello:** **Opus 5** (`claude-opus-5`). Sessione a bassa densità di codice e altissima
> densità di giudizio: costruire casi che il sistema sbaglia **davvero**, leggere una
> calibrazione distinguendo un buon risultato da una metrica satura, decidere una norma
> ([REGOLA-VAL-08]) e — la parte più difficile — consegnare "il corpus non basta" o
> "l'autorità non serve" quando è questo che dicono i numeri. La pressione a fabbricare
> casi che facciano quadrare il piano è la modalità di fallimento centrale di questa
> sessione. Sottoagenti Explore: **Sonnet 5** (l'inventario del corpus richiede di
> classificare i documenti per autorità, non di elencarli).

---

## Prompt

Sei un senior AI engineer su **VibeCraft**, un Graph-RAG in `rag/` (Qdrant + NetworkX +
bge-m3 + rerank ColBERT). Lavora in italiano come il resto del repository.

### Il difetto da correggere

`rag/rag_config.yaml`, blocco `authority`, riporta l'esito dell'ultima calibrazione:

> **RI-CALIBRAZIONE 2026-07-22** … esito NON_APPLICARE, guadagno di validazione +0.000. Nota
> metodologica: a k=10 e k=5 la recall è **SATURA a 1.000 su tutta la griglia** — a quei k il
> risultato non è informativo, nessuna combinazione è distinguibile. La misura utile è a k=2
> (recall 0.900 held-out), dove il confronto discrimina: lì **anche alpha=0.0, cioè autorità
> del tutto ignorata, pareggia col default**.

Questa nota è metodologicamente onesta ed è la ragione per cui questa sessione esiste. Va letta
per quello che dice: **non abbiamo misurato che l'autorità sia inutile. Abbiamo misurato su un
golden set che non la mette alla prova.**

Il meccanismo dell'autorità esiste per un caso preciso: *una fonte informale che matcha
lessicalmente meglio della fonte normativa che risponde davvero*. Nessuno dei 49 casi di
`eval/golden_set.yaml` costruisce quella situazione. Sono tutti casi in cui la fonte attesa è
anche la più simile — e in quel regime il ranking semantico da solo basta, qualunque sia il
peso di autorità. Da cui la saturazione.

`AUTHORITY_BOOST_ALPHA = 0.1` non è quindi un parametro validato: è un parametro **non
falsificato**, che è un'altra cosa.

### Cosa implementare

**1. Casi avversariali nel golden set**

Estendi `rag/eval/golden_set.yaml` con una sezione dedicata e chiaramente marcata, di almeno
**8 casi** che mettano in contrasto autorità e similarità lessicale. Ogni caso deve costruire
una situazione dove **il ranking puramente semantico sbaglia** e solo l'autorità corregge:

- una domanda che usa il vocabolario colloquiale di un documento informativo
  (`04_knowledge_informative/`) mentre la risposta corretta è in un documento normativo
  (`00_meta_governance/` o `02_specs_normative/`);
- una domanda su un argomento trattato sia da un documento `ENFORCED` sia da uno
  `ARCHIVED`/`DEPRECATED`, dove l'atteso è l'`ENFORCED`;
- una domanda che una fonte **senza classificazione** (un file importato, frontmatter vuoto)
  matcha lessicalmente meglio della spec che risponde — il caso che S1 ha reso distinguibile;
- almeno un caso che dipende da `SUPERA_IN_PRIORITÀ` (il meccanismo di S4);
- almeno un caso in cui la risposta è raggiungibile **solo via grafo**, non per similarità:
  il caso che misura S3.

**Vincolo di metodo, non negoziabile:** i casi vanno costruiti **sul corpus reale**, non su
fixture inventate, e vanno verificati uno per uno — esegui la query, guarda i primi risultati
e **conferma che il ranking attuale sbaglia davvero**. Un caso avversariale che il sistema già
supera non misura nulla, gonfia la recall e riproduce esattamente il problema che questa
sessione deve risolvere. Se un caso che ti aspettavi fallisse invece passa, **scartalo e
annotalo**: è informazione, non un fallimento.

Se il corpus attuale non contiene abbastanza contrasto per costruire 8 casi onesti —
è possibile, sono 11 documenti quasi tutti normativi — **fermati e dillo**. Il risultato di
questa sessione sarebbe allora «servono N documenti informativi/archiviati nel corpus di test
prima che l'autorità sia misurabile», ed è una consegna legittima e utile. Non inventare
documenti per far tornare il conto.

**2. Metrica non satura nel runner**

`eval/run.py` misura oggi a un `k` passato da CLI. Fai in modo che la corsa standard riporti
la recall a **k ∈ {1, 2, 5, 10}** e che il report segnali esplicitamente quando una metrica è
**satura** (≈1.000 su tutti i casi): una recall satura non è un buon risultato, è una misura
che ha smesso di discriminare, e deve apparire come tale nel report, non come un 100%.

Aggiungi inoltre una metrica separata per il **solo sottoinsieme avversariale**. È il numero
che questo piano deve muovere; annegarlo nella media coi casi facili lo renderebbe invisibile.

**3. Ricalibrazione**

Esegui `eval/calibrate_authority.py` sul golden set esteso:

```bash
cd rag
uv run python -m eval.calibrate_authority --k 2 --folds 5 --seed 0
```

Rispetta il contratto già scritto nel modulo e nella config: **k-fold con split di validazione,
guadagno riportato quello held-out, e nessuna applicazione automatica** — lo script scrive una
proposta in `eval/results/authority_calibrated.yaml` e si ferma. Valuta anche di estendere la
griglia: `ALPHAS` e `DEFAULT_WEIGHTS` sono le coordinate del 2026-07, e S1 ha introdotto un
parametro nuovo (`AUTHORITY_UNCLASSIFIED_WEIGHT`) che merita di entrare nella ricerca.

**Applica la proposta a `rag_config.yaml` solo se il guadagno di validazione è positivo**, e in
quel caso aggiorna il blocco di note storiche nello stesso stile delle due calibrazioni
precedenti: data, corpus, cardinalità del golden set, k usato, valori prima/dopo, esito. Quelle
note sono la memoria del progetto e vanno estese, mai riscritte.

**4. Emendamento della spec normativa**

`docs/02_specs_normative/spec_graph_rag_ingestion.md`, **[REGOLA-VAL-08]**, prescrive la
moltiplicazione piena `score × authority`. Il codice implementa la forma attenuata
`score × (1 − α + α·authority)`, e l'ADR
[`rag/adr/0002`](../../../rag/adr/0002-autorita-dichiarata-e-fiducia-sul-cammino.md) documenta questa
divergenza come **consapevole**: la calibrazione del 2026-07-14 aveva mostrato che il boost
pieno sovra-promuove i safeguard `IRON_MEMORY` generici rispetto alle spec `REQUIREMENTS`
specifiche attese.

Con un golden set che finalmente discrimina, la domanda diventa decidibile. Due esiti, ed
entrambi vanno chiusi qui:

- **α alto vince** → allinea il codice alla norma e registra il valore.
- **la forma attenuata vince** → emenda [REGOLA-VAL-08] perché prescriva la formula
  effettivamente implementata, citando i numeri che lo giustificano.

In entrambi i casi la modifica di `docs/` richiede il version bump del frontmatter e la voce
di changelog imposti da **[REGOLA-VAL-09]** e dalla policy di versionamento documentale. Non
lasciare la divergenza aperta: una norma che il codice non rispetta e che nessuno emenda è
peggio di nessuna norma.

### Test di controllo (obbligatori)

In `rag/tests/test_retrieval_eval.py` / `rag/tests/test_eval_gate.py`:

1. `test_casi_avversariali_hanno_matcher_validi` — ogni nuovo caso punta a documenti e sezioni
   **realmente esistenti** nel corpus. Un golden set che punta a file rimossi è il difetto che
   ha già colpito questo progetto una volta (nota del 2026-07-22: 24 casi su 34 puntavano a
   documenti eliminati).
2. `test_report_segnala_metrica_satura` — con risultati artificiali a recall 1.000 su tutti i
   casi, il report contiene il flag di saturazione.
3. `test_metrica_avversariale_separata_dalla_media` — il report espone la recall del
   sottoinsieme avversariale come voce a sé.
4. `test_eval_gate_usa_un_k_non_saturo` — la soglia dell'eval-gate blue/green non è valutata a
   un k dove la metrica è satura, altrimenti il gate lascia passare qualunque cosa.

Prima del commit:

```bash
cd rag
scripts/ci.sh
uv run python -m eval.run                          # tutti i k, con flag di saturazione
uv run python -m eval.calibrate_authority --k 2    # proposta, non applicazione automatica
```

### Prerequisiti del gate di eval

`eval/run.py` interroga il retrieval **via HTTP** (`GET /api/retrieve`) per riusare il modello
già caricato dal server: senza server attivo esce con **exit code 2**, non con un fallimento
di misura. Prima di eseguirlo servono, dalla root del repository:

```bash
docker compose up -d qdrant            # Qdrant su 127.0.0.1:6333
cd rag
uv run python index.py --index-status  # indice presente e allineato? altrimenti indicizza
uv run python server.py                # in una shell separata (o scripts/run_server.ps1)
```

`eval/calibrate_authority.py` invece gira **in-process** e non richiede il server: se
l'infrastruttura non è disponibile in questa sessione, usalo come verifica offline del
ranking e **dichiara nel commit che il gate HTTP non è stato eseguito**. Non spacciare per
verde un gate che non hai potuto far girare.

### Consegna

Nel messaggio di commit, riporta i numeri e le conclusioni, incluse quelle negative:

- recall a k=1/2/5/10, complessiva e sul solo sottoinsieme avversariale;
- **quanti casi avversariali il sistema sbagliava prima di S1–S4 e quanti dopo** — è la misura
  dell'intero piano, ed è l'unico numero che dice se il lavoro è servito;
- esito della calibrazione (applicata o `NON_APPLICARE`, col guadagno held-out);
- decisione presa su [REGOLA-VAL-08] e come è stata chiusa.

Se l'esito è che l'autorità **non serve** al nostro corpus, quella è una consegna valida e va
scritta chiaramente nell'ADR 0002, non annacquata. Un risultato negativo misurato vale più di
un miglioramento presunto. Nessun push su `main`.

# RESIDUI — ciò che AUDIT.md lascia aperto, e come chiuderlo

**Data:** 2026-09-04 · **Fonte:** rilettura integrale di `rag/AUDIT.md` (1.713 righe, Run A +
Run B + le 15 indagini di chiusura) · **Metodo:** ogni residuo è stato **riverificato contro
il codice di oggi** prima di finire in questo elenco. Due erano già stati chiusi da altri
interventi e sono qui segnati come tali: fidarsi della riga è l'errore che questo audit ha
commesso cinque volte su diciannove.

Questo documento non aggiunge riscontri nuovi al sistema: raccoglie quelli che AUDIT.md
dichiara aperti, li tria fra risolvibili e non, e li ordina in sessioni di lavoro.

---

## Quadro d'insieme

| | |
|---|---|
| Righe dell'audit | 19 — 15 chiuse, 3 ritirate, 1 con premessa ritirata e sostanza chiusa |
| Residui dichiarati | **22** (+5 emersi eseguendo: R15 e R16 dai run CI reali, R17 da S4, R18 e R19 da S5) |
| Di cui già chiusi da altri interventi (riga stantia) | 2 |
| Risolvibili con lavoro tecnico | 14 — **11 chiusi** (R1, R2, R3, R4, R5, R6, R7, R8, N5, N6 + gli altri annotati in linea); R13 preparato, non eseguito |
| Che richiedono una decisione, non del codice | 5 (+R16: proteggere il ramo) |
| Non risolvibili (dati persi, hardware assente) | 1 |

---

# 1. Cosa NON è stato fatto

Interventi **deliberatamente** non eseguiti, con la ragione scritta accanto. Non sono
dimenticanze: sono confini dichiarati.

| # | Cosa | Dove | Perché no |
|---|---|---|---|
| N1 | **Streaming incrementale di `/ask`** | A11 | Cambierebbe il contratto: oggi la risposta è un JSON unico con risposta, contesto grafo, archi, punteggi e latenze. Servirebbero due canali, un secondo percorso d'errore e la cache da ripensare |
| N2 | **Gate sulla latenza** | A11 | Il bench è una misurazione (exit 0) per contratto, e un p95 su 10 campioni non regge una soglia bloccante |
| N3 | **Metrica di attribuzione della fonte** | A3 | «A chi la risposta attribuisce il vincolo» è la metrica vera del sistema e **non esiste**. Costa una chiamata LLM per caso più un giudice |
| N4 | **Strada 1: peso di sezione** | A3 | Agisce sul *rango*, che la misura ha mostrato non essere il problema. Candidata solo se un giorno `governed_max_chunks` scendesse molto |
| N5 ✅ | ~~**Servizio Qdrant nel workflow CI**~~ | A8 | **Fatto 2026-09-04** — `services: qdrant` (`qdrant/qdrant:v1.19.0`) nel job `test`, con `VIBECRAFT_REQUIRE_QDRANT=1`, `pytest -rs` e un passo che pretende `5 passed`: i cinque non possono tornare a saltare in silenzio. **Run #131 verde**: il riepilogo porta «Qdrant reale: 5/5 test d'integrazione passati», e la suite gira con 0 skipped |
| N6 ✅ | ~~**Installazione reale su un Mac**~~ | A15 | **Fatto 2026-09-04** — job `macos-nativo` su `macos-15`: `uv sync --frozen` vero, torch importato e un matmul verificato. Un Mac qui continua a non esserci: ce lo mette il runner. **Eseguito: verde in 34-36s su due run**; dal log macOS 15.7.9 arm64, `torch 2.13.0` senza `+cu` e **matmul su `mps`** — torch non si limita a installarsi, calcola sull'acceleratore. Quel numero ha smentito la stima di costo con cui l'avevo limitato a main (130 pacchetti contro 149, torch 106,1 MiB contro 804,7): restrizione rimossa. Resta scoperto il ramo con CPython **gestita da uv** — in CI uv ha usato il Python di Homebrew del runner |
| N7 | **Extra in conflitto CPU/CUDA per torch** | A15 | Cambierebbe il comando di installazione per tutti (`uv sync --extra cpu`). Per il caso CPU-only esiste già il target `cpu` del Dockerfile |
| N9 | **macOS con CPython gestita da uv** | A15 | *(Nuovo, 2026-09-04.)* In CI uv ha usato il `python@3.14` di Homebrew dell'immagine, quindi il tag e' `macosx-15.0-arm64` e la wheel `macosx_14_0` passa. Con una CPython **gestita da uv** il tag verrebbe dal `MACOSX_DEPLOYMENT_TARGET` conservativo con cui e' compilata — l'artefatto che A15 aveva gia' incontrato nel dry-run — e la wheel verrebbe rifiutata. Coprirlo vuol dire un secondo job che forza `uv python install`: per ora il tag e' **stampato** nel log, cosi' quel fallimento e' leggibile invece che misterioso |
| N8 | **Ricalibrazione del tetto `top_k`** | A1 | `top_k=20` tocca il 104% della finestra su almeno una domanda reale. Abbassarlo richiede una misura sistematica, non un numero scelto in coda a una correzione |

---

# 2. Cosa resta aperto

Difetti e rischi veri, ancora presenti. **Verificato oggi** salvo dove indicato.

### Gravità alta

**R1 — Il prompt di sistema ordina di citare vincoli SQL → CHIUSO 2026-09-04.**
`core/retrieval.py` — *«DEVI citare esplicitamente i codici dei Safeguards (es.
[SAFEGUARD-TXN-01]) e i vincoli SQL (es. SELECT ... FOR UPDATE)»*, sostituita da
`[CITAZIONE-VERIFICABILE]`.

**Una metà della premessa era sbagliata, e va detta.** «Un corpus che di SQL non parla» non
regge: `docs/00_meta_governance/safeguards_security.md` enuncia `SELECT ... FOR UPDATE` nel
testo di `[SAFEGUARD-TXN-01]`, in un blocco di codice SQL, nel requisito sul motore di
database e nella tabella di sintesi. Il difetto non era l'assenza di SQL dal corpus: era che
l'ordine di citarlo era **incondizionato**, quindi si applicava anche alle domande il cui
contesto recuperato non ne contiene — e lì il modello lo fabbricava.

**Riprodotto** il 2026-09-04 contro `/ask` (Qdrant, Ollama `qwen3.5:9b`, indice
`v20260901T132525`), 2 esecuzioni per caso, cache disattivata: **3 risposte su 4 inventano**.
Caso 3 (*ordine dei tagli del chunker*) apre una sezione intitolata *«Vincolo SQL/Logica
associata (implicito nel contesto dei blocchi atomici)»* e ci trascina dentro
`[SAFEGUARD-TXN-02]` — l'atomicità transazionale, in una risposta sul chunking. Caso 4
(*palette colori*) attribuisce il controllo a `[SAFEGUARD-UI-01]` *«(implicito nella
funzione…)»* e `[SAFEGUARD-PALETTE-01]`: **zero occorrenze in tutto il corpus**, verificato.
La forma è sempre la stessa — il codice inesistente è marcato «implicito» o «ipotetico», che
è come il modello obbedisce a un ordine che non può soddisfare.

**Correzione:** non la rimozione della parola «SQL». `[CITAZIONE-VERIFICABILE]` pretende di
citare *testualmente ciò che il contesto riporta*, ed è la clausola di **divieto** a portare
il peso: «è tassativamente vietato introdurre un codice, un identificatore o un vincolo
tecnico che nel contesto non compare: non inventarlo, non dedurlo per analogia, non proporlo
come esempio, ipotesi o vincolo *implicito*».

**Verifica**, stesse due domande, 2 esecuzioni ciascuna: **0 invenzioni**, e i codici veri
restano — caso 3 cita `[REGOLA-VAL-04]` dalla spec normativa col METHODOLOGY come razionale,
caso 4 cita `[REGOLA-UI-01]` e `[REGOLA-UI-03]` dalla norma. Controllo sul verso opposto
(*«come gestire il lock transazionale su una risorsa contesa»*, dove l'SQL nel contesto c'è
davvero): la risposta cita `[SAFEGUARD-TXN-01/04/05]` e il `SELECT ... FOR UPDATE` reale —
la regola sopprime l'invenzione, non la citazione. Costo: il prompt fisso passa da ~804 a
~954 token stimati (+150), dichiarato e ora sorvegliato da R3.
Test di non regressione in `tests/test_ask_authority_prompt.py`.

**R2 — Nulla allarma quando la copertura ColBERT scende → CHIUSO 2026-09-04.**
`check_index_integrity` confrontava i punti Qdrant con `chunks.json` senza guardare mai le
chiavi del sidecar ColBERT: un chunk senza vettore non produceva alcun problema.

**Copertura rimisurata prima di correggere** (AUDIT A7 diceva 160/160 e aveva ragione):
sull'indice attivo `v20260904T092228`, **160 chunk in `chunks.json`, 160 chiavi in
`colbert.npz`, zero scoperti e zero orfani**. Il difetto non era il numero, era che il
numero esisteva solo se qualcuno lo andava a misurare a mano.

Aggiunto come **terza voce della stessa lista** (`core/indexing.py`, passo 4 — fra
l'integrità degli artefatti e il conteggio Qdrant), con la stessa forma delle altre due:
nessun meccanismo nuovo, nessun campo nuovo nel report. Legge il solo membro `keys` del
`.npz`, quindi il check resta economico (zero decompressione dei vettori).

**Va in `problems`, e la ragione è stata verificata, non assunta.** Il precedente
documentato nella funzione — rollback intra-lineage seguito da un incrementale ⇒ mismatch
ATTESO — riguarda **solo Qdrant**, che non è versionato. `colbert.npz` e `chunks.json` li
scrive la stessa `save_artifacts` nella stessa directory di versione, sia dal full rebuild
sia dall'incrementale: fra loro non esiste divergenza legittima. Quindi è un difetto, non
un'osservazione pura come `observe_qdrant_alias`, e la remediation è quella che lo script
notturno applica già per `artifacts_corrupted`: full rebuild.

Verificato per costruzione: tolta una chiave dal sidecar il check la nomina (`-c2` nel
messaggio), rimessa torna verde; i 4 test nuovi in `tests/test_index_integrity.py`
**falliscono contro il codice vecchio**. Coperti anche i due versi opposti (multivettore
orfano, sidecar assente/illeggibile) e un contrappeso: se `chunks.json` è illeggibile il
check non aggiunge un secondo problema derivato.

**R3 — Il margine sulla finestra di contesto si accorcerà di nuovo → CHIUSO 2026-09-04.**
Il prompt era cresciuto due volte in una sola sessione (`[CLASSE-FONTI]`,
`[REGOLA-ASTENSIONE]`), portando la misura dall'81% al 104% di `num_ctx` a `top_k=20`, e non
esisteva alcun test. Ora c'è `tests/test_ask_prompt_cost.py`: canarino sul costo **fisso**
del prompt di sistema — base più `[CLASSE-FONTI]` e `[PRECEDENZA-FONTI]` con le
interpolazioni ridotte a valori sintetici, cioè la sola parte che dipende dal sorgente e non
dal corpus. Budget **1.000 token stimati** (stessa scala ~3 caratteri/token del guardrail di
`core.llm._ollama_payload`, altrimenti misurerebbe una grandezza diversa da quella che
solleva `LLMError`), contro i **954** misurati oggi: ~46 token di margine, meno di qualunque
regola vera (`[CLASSE-FONTI]` ne pesa ~330, `[REGOLA-ASTENSIONE]` ~160). Aggiungere una
regola rende il test rosso — è lo scopo: budget, data e ragione della misura stanno **dentro
il test**, e alzarli senza rimisurare il prompt completo a `top_k=20` sul corpus reale è
esattamente il passo che era stato saltato. Il test sul prompt **completo** resta
deliberatamente non fatto: dipende dal corpus e fallirebbe a ogni reindex senza dire chi
l'ha fatto crescere.

### Gravità media

**R4 ✅ — In CI i cinque test contro Qdrant reale non girano mai.** *(Chiuso 2026-09-04.)*
Il workflow non avviava il servizio: alias swap, delete-by-filter, GC e `delete_collection`
erano verificati solo da chi aveva Docker acceso in locale. Ora `services: qdrant`
(`qdrant/qdrant:v1.19.0`, allineata a `qdrant-client==1.19.0`) più tre meccanismi contro la
ricaduta — `VIBECRAFT_REQUIRE_QDRANT=1` che trasforma lo skip in errore dove il servizio è
dichiarato, `pytest -rs` per il motivo di ogni skip, e un passo che pretende `5 passed`.
Misurato nelle tre direzioni; suite intera `1317 passed, 0 skipped` col servizio acceso.
*Emerso strada facendo:* `ci.sh` passava un `-q` di troppo (`pytest.ini` lo ha già in
`addopts`), cioè `-qq`, che sopprimeva **proprio** la riga di riepilogo che rende visibile
il conteggio.

**R15 — Altri test potrebbero dipendere dal `database/versions/` della macchina.** *(Nuovo,
2026-09-04.)* Il difetto trovato dal primo run CI era di questa forma: verde in locale perché
l'indice c'è, rosso su un checkout pulito. Ne è stato corretto **uno**; nulla dice che sia
l'unico. La verifica è a basso costo — un plugin pytest che ripunta `versions_root()` su una
directory vuota, come quello usato per riprodurre — ma va fatta distinguendo i veri positivi
dagli artefatti (i test *end to end* le versioni se le creano, e un fixture autouse gliele
scavalca). *Verificato: la CI ora gira su ogni push, quindi il prossimo caso si manifesta da
sé — ma dopo il push, non prima.*

**R16 — La CI era rossa su `main` e non lo fermava niente.** *(Nuovo, 2026-09-04.)* Misurato:
`1044513` (S2, 14:45) e `dffaa6a` (14:47) sono stati pushati insieme, quindi il run **#129** li
copre entrambi ed è **rosso**; il precedente, **#128** su S1, era verde. `main` è rimasta rossa
**~1 ora**, fino al merge di `7532477` (15:45) — dopo il quale il run su `main` è **verde**,
che conferma all'indietro la diagnosi: quel test era la causa unica, non una delle cause.

Il punto non è l'ora: è **come è finita**. Nessun alert, nessun check obbligatorio, nessuna
protezione del ramo — il rosso è stato scoperto perché qualcuno ha *chiesto* di guardare, e la
domanda è nata di rimbalzo mentre si indagava un difetto diverso. Se non fosse stata posta,
`main` sarebbe rimasta rossa fino al prossimo sguardo casuale.

È la stessa forma di R4, un piano più su. R4 diceva: *un job che salta tutto ed esce verde non è
un gate*. Questo dice: *un gate che nessuno guarda e che non blocca nulla non è un gate nemmeno
quando funziona* — e qui aveva funzionato, aveva visto il difetto, e non è servito a niente per
un'ora. Il repository ha già un canale per gli allarmi (`alerts.jsonl` + il webhook notturno),
ma sorveglia lo stato del RAG, non quello della CI.

*Verificato: `1044513` non ha un run proprio — i due commit sono arrivati in un unico push,
quindi #129 è il primo run che contiene S2. Coerente con la diagnosi, non una coincidenza.*

**R5 — Il report multihop stampa «trigger M2 scattato» come se fosse una decisione in corso
→ CHIUSO 2026-09-04.** `eval/run_multihop.py`. Il residuo era **metà** di com'era scritto, come
la nota di §3 aveva anticipato: il docstring dichiarava già il verdetto storico, era solo la
riga stampata a suonare come una decisione in corso. Il numero resta — è il gap
retrieval→grafo ancora scoperto dal router — con l'etichetta che dice cosa significa oggi:

```
casi col gap retrieval->grafo ancora scoperto (A fallito, B riuscito): 1
  storico: a >=3 scatto' il trigger M2, il router deterministico fu implementato ed e' in
  servizio; qui piu' basso = meglio
```

`trigger_m2.fired` resta nel JSON, dove nessuno lo legge come un semaforo. *Verificato
eseguendo la suite col server acceso: PASS, recall media A 0.896, B 6/6.*

**R6 — La dashboard colora come errore tutto ciò che non è `success` → CHIUSO 2026-09-04.**
`templates/dashboard.unified.html`. Il ternario `status === 'success' ? verde : rosso` è ora
una mappa dei cinque stati che `/ask` restituisce, con tre toni invece di due: verde per
`success` e `graph_answer`, **ambra** per `abstained` («non ha risposto, ed è corretto così»),
neutro per `no_results` e `no_graph_nodes`, rosso solo per l'ignoto. *Verificato nel browser:
domanda strutturale → `graph_answer` verde, domanda fuori corpus → `abstained` ambra.*

**La correzione ha tirato fuori altro, ed è la parte che vale.** Il badge era l'unico punto
che si guardava; sistemandolo sono emersi tre difetti dello stesso genere — un colore che non
segue il tema — che nessuno aveva mai visto perché erano **coerentemente** sbagliati:

- il tema Classico **non è chiaro** (`--bg-canvas:#0f172a`): il badge non era illeggibile,
  era fuori palette. Detto male da me nella prima diagnosi, corretto misurando;
- `renderJsonPanel` legge i token con `themeVar()` e li **cuoce nell'HTML**, quindi al cambio
  di tema tutto il pannello restava con la palette vecchia fino alla query successiva. Col
  badge corretto la cosa diventava visibile (pillola ambra sopra chip ancora verdi). Il
  ridisegno è agganciato all'hook `onThemeChange` che già esisteva per il grafo;
- i **punteggi Qdrant** sono resi in due card, e nessuna delle due seguiva il tema fino in
  fondo: nel pannello JSON valore e fine del gradiente erano hex cotti nel JS; nella card
  della sidebar il valore era `text-emerald-400` e la barra `from-blue-600 to-emerald-500`.
  Ora entrambe usano i token `--score-*` (che perdono il prefisso `json-`: non sono più solo
  del pannello JSON). Da qui il residuo nuovo **R17**.

**R7 — `change_log.md` è contaminato dal dominio dismesso e rimanda a un file inesistente
→ CHIUSO 2026-09-04 (S5).** Tutti e tre i riscontri verificati e corretti: `project:` →
`cross-project`, le 3 righe contaminate (4, 60, 75) riscritte al perimetro reale.

**Il riferimento morto non è stato né ripuntato né rimosso, ed è la parte che conta.**
Verificando è emerso che non è uno: nella voce «1.1.0» **13 path su 15** non esistono.
Ripuntarlo direbbe che una release ha toccato un file che non ha toccato — e [REGOLA-DEV-02],
scritta in quello stesso file, impone «l'elenco esatto dei file modificati» e nomina il
proprio failure mode («perdita della correlazione storica»). Cancellare la riga sarebbe
arbitrario: 13 righe hanno lo stesso difetto. Quello che un change log fa è **registrare**:
aggiunta la voce `2.0.0` che scrive la dismissione del dominio (che B1 eseguì senza mai
registrarla) più una nota di lettura in testa a §3.

**Il residuo era più piccolo del difetto.** Il frontmatter dichiarava 13 archi `CONTIENE`:
**12 target su 13 non risolvono**, e `add_frontmatter_edges` non li scarta — li crea come
nodi `type: entity` con `reliability: 0.9`. Dodici documenti fantasma dichiarati affidabili.
Rimossi; il tredicesimo ripuntato al `node_id` reale (`v1.1` → `v2.0`). Grafo 755→751 nodi,
929→927 archi, fantasmi `spec-*-v1.0` **12 → 0**. La distinzione che governa le due decisioni
opposte: §3 è un **ricordo** e non si riscrive, un arco del frontmatter è un'**asserzione sul
presente** e deve essere vera oggi.

**R8 — Il sottoinsieme avversariale è a 4 casi con 2 soli distrattori → CHIUSO 2026-09-04
(S5), ma non per la strada che il residuo indicava.** Il documento mancante è stato scritto
(`docs/04_knowledge_informative/inferenza_locale_o_remota.md`, `METHODOLOGY`,
`authority: 0.40` dichiarata, tracciato in git; tema con **0 occorrenze** in `docs/`).

Poi la misura ha smentito la premessa: rimarcato il caso 4 con quel distrattore, il
distrattore esce a **rango 6** contro il **2** dell'atteso — nessun contrasto. Sulla
similarità densa il documento vince (rank 2 contro 6), ma perde sul ColBERT (0.494 contro
0.5032), su cui l'ordine finale è costruito: su *quella* formulazione la fonte normativa è
anche il miglior match lessicale, perché §5 di `safeguards_security` nomina già «modelli LLM
remoti», «dati personali» e «motivazioni». Un documento che la vincesse sarebbe un'esca.

Ampiezza restituita con una domanda **diversa**, scelta misurandone sette: «posso usare un
servizio di inferenza remoto per il debug di un record reale» (distrattore 1 → atteso 2).
Tre candidate sono state scartate perché il distrattore vinceva **avendo ragione** — non è un
caso avversariale, è il retrieval che funziona. Sottoinsieme: **5 casi, 3 distrattori**. Il
caso 4 resta normale, con la misura di oggi annotata accanto.

**R9 — Le tre catene multihop a tre documenti si fermano a 2 su 3.** La soglia di A4 mette un
pavimento sotto il numero, non lo alza. Ma la domanda vera non è mai stata posta: `/ask`
inietta anche le sezioni raggiunte **via grafo**, quindi il terzo documento potrebbe essere
nella *risposta* pur mancando dal retrieval. Nessuna metrica lo guarda — è la stessa
distinzione di A3.

**R10 — Il marcatore di astensione è un impegno del prompt, non una garanzia del modello.**
Nessun test lo esercita contro un LLM reale; un provider che ignorasse l'istruzione
tornerebbe silenziosamente a `"success"`. Stessa famiglia: **R11 — la soglia di certezza su
`num_ctx` non è mai stata esercitata contro Ollama in un test**, solo osservata a mano.

### Gravità bassa / vigilanza

**R12 — Lo storico riparte quasi da zero a ogni spostamento del gate.** Le righe portano solo
la chiave del `k` di allora: spostando `eval_gate.k` la serie si è accorciata da 79 a 22
punti. Corretto (sono misure diverse), ma la continuità si comprerebbe registrando **tutti**
i k in ogni riga.

**R13 — `recall@2` è a 0.875 con soglia 0.75: margine 12,5 punti. PREPARATO 2026-09-04, non
eseguito.** Il giorno in cui saturasse non resta un k più basso — andrà **esteso il golden
set** con casi che il sistema sbaglia. I candidati sono stati cercati **ora, mentre il
margine c'è**: 14 domande misurate contro l'indice, **5 falliscono a k=2** con una fonte
attesa difendibile. Elenco completo, con rango e chi vince al loro posto, in AUDIT.md
(«R13 — cinque candidati misurati, nessuno aggiunto»). Due note dall'elenco: C4 è la
riformulazione *colloquiale* di un caso che già passa a rango 1 — stesso fatto, stessa fonte,
e il divario non è misurato da nulla; C3 e C5 sono battuti da documenti **non tracciati**,
quindi vanno aggiunti solo insieme alla decisione su A6, altrimenti misurano il checkout.

**R17 — Metà della tavolozza dei template non è agganciata al tema.** *(Nuovo, 2026-09-04,
emerso da R6.)* In `tailwind.config` (dashboard) solo `brand`, `slate`, `blue` e `purple`
sono mappati sulle CSS vars: `emerald`, `amber` e `red` no, quindi ogni `text-emerald-400`,
`bg-amber-400`, `text-red-400` è un colore fisso identico nei due temi. Misurato: **39
occorrenze** fra `dashboard.unified.html`, `pipeline.unified.html` e
`infografica.unified.html` — fra queste il badge del tempo di elaborazione, i tre pallini di
`setStatus` (idle/loading/success/error) e il testo d'errore della risposta. Nessuna è un
guasto: sono tutte leggibili, perché **entrambi i temi sono scuri**. È la stessa classe di
difetto che R6 ha chiuso su due card, e si vede solo mettendo le due palette una accanto
all'altra. La correzione non è meccanica: `emerald`/`red`/`amber` in molti punti significano
*stato* (ok / errore / in corso), e uno stato ha senso che resti riconoscibile **attraverso**
i temi — quindi va deciso caso per caso quali agganciare e quali no, non sostituito con sed.

**R18 — `graph_rag_ingestion_strategy.md` dichiara un `node_id` che non esiste.** *(Nuovo,
2026-09-04, emerso da R7.)* Il suo arco `DERIVA_DA` punta a `spec-graph-rag-ingestion-v1.1`,
ma la spec dichiara `v2.0`: il target non risolve e resta nel grafo come nodo fantasma
`type: entity` con `reliability: 0.9`. È **lo stesso difetto** che R7 ha corretto in
`change_log.md` — dove i target morti erano dodici — ma qui il file è **tracciato**, cioè
parte della baseline: toccarlo cambia il corpus riproducibile e usciva dal perimetro di R7.
Una riga di correzione, ma va fatta con un rebuild e con la consapevolezza che sposta la
baseline. Verificato: dopo R7 il nodo fantasma sopravvive con un solo arco entrante invece
di due.

**R19 — La soglia multihop è a 0,4 punti dal pavimento, e ce l'ha portata un documento non
tracciato.** *(Nuovo, 2026-09-04, emerso da S5.)* `recall media A` è passata da 0.896 a
**0.854** contro `min_recall: 0.85`. La suite non è cambiata: è il corpus. Due casi si sono
mossi, e solo uno è «la misura che fa il suo lavoro» (l'enumerazione dei documenti, 0.55 →
0.45, stessa lettura di A4). L'altro no: «cosa devo fare quando modifico un documento della
knowledge base?» crolla da 1.00 a **0.50** perché `spec_graph_rag_ingestion § Aggiornamento
Incrementale` **esce dal top-10**, spinto fuori da `change_log.md` — che dopo la bonifica di
R7 è diventato un match legittimamente più forte per quella domanda, e che **non è tracciato
da git**. Il ranking non ha sbagliato; la catena a due documenti non ci sta più in dieci.
Due cose da decidere, e nessuna è «alzare la soglia»: se la soglia debba essere relativa alla
dimensione del corpus invece che assoluta, e se un documento non tracciato debba poter
consumare il margine di una metrica sorvegliata (è A6 che torna, da un'altra porta).

**R14 — Le due collection Qdrant distrutte da A20 non sono recuperabili → la parte
risolvibile è CHIUSA 2026-09-04.** I dati restano persi (gli artefatti su disco ci sono, i
vettori no) e non si è tentato di recuperarli. `v20260901T101536` è nel frattempo uscita
dalla retention, ma il suo lineage sopravvive in `v20260901T105315` e `v20260901T114636`:
le versioni locali che puntano a vettori inesistenti sono **tre**, non due.

**La premessa della riga era sbagliata, ed è la parte che conta.** «Un rollback fallirebbe
sul lato Qdrant»: provato dal vivo, **riusciva**. `python index.py --rollback
v20260901T132300` stampava `✅ Rollback: CURRENT → v20260901T132300`, poi il warning
sull'alias, e usciva 1 — lasciando una **mutazione parziale**: CURRENT (grafo e sidecar) sul
target, produzione Qdrant sui vettori di `v20260904T092228`. Nessuno la ripara
(`repair_qdrant_alias` non inventa collection, quindi nemmeno il reconciler di boot), e in
quello stato `check_index_integrity` rispondeva **`ok: true`, `problems: []`** — le due
build hanno 160 chunk entrambe e il passo 5 confrontava solo un conteggio. Via HTTP,
`POST /api/index/rollback` rispondeva **200**. Cioè: **degradazione silenziosa**, non
fallimento oscuro — la variante grave prevista dalla sessione.

Trattata come tale, con due correzioni:
1. **Rifiuto prima di mutare** — `assert_rollback_target_has_vectors` (core/indexing.py),
   sotto lo stesso writer lock e prima di `rollback_version`: collection del target assente
   ⇒ rollback rifiutato (CURRENT e alias intatti), messaggio che nomina la collection
   mancante e prescrive la re-indicizzazione completa. CLI exit 1, route **409**. La
   risoluzione del target vive ora in `core.artifacts.resolve_rollback_target`, così si può
   verificare prima di scrivere. Qdrant irraggiungibile ⇒ pre-check saltato, comportamento
   invariato: un rollback locale non deve dipendere dalla raggiungibilità di Qdrant.
2. **Lo stato misto non è più muto** — il passo 5 di `check_index_integrity` verifica anche
   che la collection **dichiarata dalla versione attiva** esista ancora: se è sparita,
   `qdrant_mismatch` (⇒ full rebuild notturno). Un alias divergente con la collection attesa
   ancora presente resta invece la sola osservazione `qdrant_alias`, come prima: quella il
   boot la ripara, e trasformarla in un problema accoderebbe un rebuild a ogni divergenza
   transitoria. Il contrappeso ha un test dedicato.

Verificato dal vivo: rollback a `v20260901T132300` → rifiutato, `CURRENT` invariato;
rollback a `v20260901T132525` (collection viva) → riuscito, alias swappato; stato misto
ricreato a mano → `ok: false`, `qdrant_mismatch: true`, exit 1.

---

# 3. Cosa è uscito di nuovo dagli interventi

Nessuna delle quattro righe della Run A ha prodotto un difetto nuovo *nel sistema*. Ma sei
riscontri sono nati **dall'atto di correggere**, ed è il dato più interessante di tutto
l'audit: metà del valore è arrivato dal guardare, non dal riparare.

| Trovato | Come | Stato |
|---|---|---|
| **A18** — `/api/retrieve` non ricaricava lo snapshot | Eseguendo B1. È l'endpoint su cui gira *tutto* l'harness di eval: misurava uno stato misto, in silenzio | Chiuso |
| **A19** — `pypdf` non dichiarata: i PDF indicizzati vuoti | Durante l'audit delle licenze, non cercandolo. Emerso anche il gemello: `openpyxl` arrivava solo come transitiva | Chiuso, con i tre `try/except` che degradavano a stringa vuota rimossi |
| **A20** — un `database/` vuoto faceva cancellare le collection altrui | **Provocandolo**: è successo davvero e ha distrutto dati | Chiuso (guardia), dati persi → R14 |
| **A2b** — la sorveglianza era rimasta al `k` vecchio | Dal ritiro di A2. Più esteso del previsto: due pagine, il guardrail di `eval.run` e i **due script notturni**, verdi per costruzione | Chiuso |
| **Deriva di versione di `torch`** | Rifacendo il lock per A15: senza pin, macOS finiva su 2.14.0 e tutti gli altri su 2.13.0 — la deriva che il Dockerfile documenta di aver già subito | Chiuso (pin), lo avrei **introdotto io** chiudendo un riscontro di portabilità |
| **Il perimetro `.gitkeep`** | Verificando la chiusura di A6 invece di riscriverne l'etichetta: il report dichiarava «16 documenti» contro i 14 indicizzati | Chiuso lo stesso giorno |
| **`main` era rossa da un'ora e nessuno lo sapeva** | Rispondendo a una domanda posta di rimbalzo — «se S2 ha introdotto quel test rotto, la CI su main non dovrebbe essere rossa?» — mentre si indagava tutt'altro. Lo era: run #129, dalle 14:47 alle 15:45 | Aperto → **R16** |
| **Nessuna baseline di bench era mai stata salvata** | Aprendo A11: `eval/results/` non conteneva alcun `bench_*.json`, mentre il README vieta di ottimizzare senza baseline | Chiuso |
| **Il pannello JSON restava con la palette vecchia al cambio di tema** | Correggendo il badge di R6: i colori sono letti con `themeVar()` e cotti nell'HTML, e nulla ridisegnava. Invisibile finché il badge era sbagliato **allo stesso modo** | Chiuso (ridisegno agganciato a `onThemeChange`) |
| **I punteggi Qdrant sono due card, e nessuna seguiva il tema** | Verificando R6 a schermo invece che nel codice: quella della sidebar non era nemmeno nel file che il residuo nominava | Chiuso (token `--score-*`) → il resto della tavolozza è **R17** |

### Due residui dell'audit sono già chiusi, e la riga non lo dice

- **`graph_rag_ingestion_strategy.md` col campo `project:` stantìo** (annotato in A6, riga
  757-761). *Verificato oggi: il campo vale già `"cross-project"`.* Corretto dalla
  riconciliazione della pendenza 3, che l'audit registra poco più sotto senza collegare le due
  note. **Da cancellare da AUDIT.md, non da fare.**
- **Il verdetto storico del trigger M2** è già dichiarato tale nel docstring di
  `run_multihop.py`; resta solo la riga stampata (R5). Il residuo è **metà** di com'è scritto.

*Entrambe confermate e chiuse da S4 il 2026-09-04: la nota su `graph_rag_ingestion_strategy.md`
è stata **cancellata** da AUDIT.md (il campo valeva già `"cross-project"`, ricontrollato) e la
voce aperta di A4 sul trigger M2 registra ora che il residuo era metà di com'era scritto.
Due su due: la disciplina «misura prima di correggere» ha evitato due modifiche inutili.*

---

# 4. Triage — il modo migliore per chiudere ognuno

| # | Approccio scelto | Perché questo e non altro | Sforzo |
|---|---|---|---|
| R1 ✅ | Riscrivere l'istruzione perché pretenda di citare **ciò che il contesto contiene**, non una lista fissa di categorie | Rimuovere la sola parola «SQL» lascerebbe la forma «DEVI citare X» che genera X quando X non c'è. Il difetto è la forma, non l'esempio | S — **fatto 2026-09-04** (`[CITAZIONE-VERIFICABILE]`) |
| R2 ✅ | Aggiungere al `check_index_integrity` il confronto chiavi ColBERT ↔ `chunks.json`, come per Qdrant | La funzione già fa esattamente questo confronto per un'altra coppia: è una terza voce nella stessa lista, non un meccanismo nuovo | S — **fatto 2026-09-04**; copertura rimisurata 160/160 prima di correggere, e il difetto va in `problems` perché fra i due sidecar non esistono divergenze attese |
| R3 ✅ | Test-canarino sul **costo fisso** del prompt di sistema, con il budget scritto e la ragione | Un test sul prompt completo dipenderebbe dal corpus; il costo fisso è ciò che cresce quando si aggiunge una regola | S — **fatto 2026-09-04** (`tests/test_ask_prompt_cost.py`) |
| R4 ✅ | `services: qdrant` nel job `test` di `ci.yml` | GitHub Actions lo supporta nativamente; l'alternativa (`docker compose up` nel job) aggiunge uno script da mantenere | S — **fatto 2026-09-04**; il servizio da solo non bastava: senza un gate lo skip resta verde, quindi `VIBECRAFT_REQUIRE_QDRANT=1` + `-rs` + conteggio preteso |
| R16 | Rendere il job `test` un **check obbligatorio** sul ramo protetto, cosi' che un rosso blocchi invece di essere notato per caso | E' un'impostazione del repository, non del codice: qualunque soluzione scritta qui dentro (uno script che interroga l'API dei run, un alert nel notturno) aggiungerebbe un pezzo da mantenere per fare peggio cio' che GitHub fa nativamente. Va decisa una volta, come le cinque di S8 | S — ma e' una **decisione**, non lavoro tecnico |
| R5 ✅ | Stampare il conteggio come contesto storico, non come verdetto | Togliere la riga perderebbe un numero utile: è l'etichetta a essere sbagliata | S — **fatto 2026-09-04**; il docstring era già corretto, quindi il lavoro era una riga sola |
| R6 ✅ | Mappa esplicita degli stati → colore, con `abstained` e `graph_answer` distinti dall'errore | Il ternario `success ? verde : rosso` non è estendibile senza mentire | S — **fatto 2026-09-04**; la mappa era il lavoro previsto, i tre difetti di tema che ha scoperto no |
| R17 | Decidere **quali** colori-di-stato devono seguire il tema e quali restare costanti, poi agganciare solo quelli | Un sed su `emerald` → token cancellerebbe la distinzione ok/errore proprio dove serve. È una decisione di design, con una spazzata meccanica dietro | M — decisione + sweep su 3 template |
| R7 ✅ | `project:` corretto; il riferimento morto **né ripuntato né rimosso** — registrato con una voce di release nuova, perché §3 è storia e riscriverla la falsifica; e i **12 archi `CONTIENE` verso il nulla** rimossi dal frontmatter, che invece è un'asserzione sul presente | Il file è nell'indice: correggerlo senza rebuild non cambia ciò che il retrieval vede | S + rebuild — **fatto 2026-09-04**; i 12 archi fantasma (`reliability: 0.9`) non erano nel residuo, li ha trovati la verifica |
| R8 ✅ | Documento scritto (`inferenza_locale_o_remota.md`, `authority: 0.40`, tracciato). Ma il caso 4 **non** è stato rimarcato: misurato, il nuovo distrattore esce a rango 6 contro il 2 dell'atteso — nessun contrasto. Il sottoinsieme è tornato a 5 casi con una domanda **diversa**, scelta misurando 7 formulazioni | È una decisione sul corpus: nessun documento esistente sotto peso 0.5 nomina LLM o privacy (già misurato) | M — **fatto 2026-09-04**; la premessa del residuo («basta un documento sul tema») è stata smentita dalla misura, non assunta |
| R9 | **Misurare prima**: chiedere a `/ask` le tre catene e verificare se il terzo documento compare nella risposta via grafo | Se compare, non c'è nulla da correggere e il residuo si chiude come A4 — dichiarando cosa misura la soglia | M |
| R10, R11 | Un check notturno contro Ollama vero, accanto a `nightly_consistency` | In CI non c'è LLM; il notturno gira dove il modello c'è ed è il canale che già porta gli alert | M |
| R12 | `record_history` scrive **tutti** i k calcolati, non solo quello del gate | Una riga più larga costa nulla e rende ogni futuro spostamento del gate indolore | S |
| R13 ◐ | **Preparato 2026-09-04**: 14 domande misurate contro l'indice, 5 candidati che falliscono a k=2 annotati in AUDIT.md («R13 — cinque candidati misurati, nessuno aggiunto»). **Nessuno aggiunto**: l'elenco serve pronto, non eseguito | Estenderlo sotto pressione (metrica satura) significa sceglierne i casi per far scendere un numero | M — preparazione fatta, aggiunta ancora aperta |
| R14 ✅ | Non recuperabile. Ma il **rollback** deve accorgersi che la collection della versione target non esiste e dirlo, invece di fallire in modo oscuro | I dati sono persi; l'esperienza al tentativo no. **Misurando è emerso che non falliva affatto**: riusciva a metà e nessun check lo diceva — quindi rifiuto *prima* della mutazione, più il rilevamento dello stato misto nel check notturno | S — **fatto 2026-09-04** |
| N1–N8 | Decisione esplicita, registrata. Non codice | Cinque di questi sono «no» già argomentati: vanno confermati o ribaltati una volta, non ridiscussi a ogni sessione | — |

---

# 5. Le sessioni

Otto sessioni, ordinate per dipendenza. **S1 e S2 vanno per prime**: sono le uniche due che
riguardano un comportamento scorretto in produzione oggi. Ogni prompt è autonomo — si può
aprire una sessione nuova e incollarlo.

> **Disciplina comune a tutte** — è la lezione che questo audit ha pagato cinque volte:
> **misura prima di correggere.** Le righe invecchiano, e due dei residui qui elencati erano
> già chiusi. Verifica che il difetto esista ancora, verifica che il test nuovo **fallisca**
> contro il codice vecchio, e se la premessa cade dillo invece di correggere qualcosa che
> nessuno ha chiesto.

---

## S1 — Il prompt che invita a inventare ✅ ESEGUITA il 2026-09-04

Chiude **R1**, **R3**. Esito in fondo alla sessione; il prompt resta qui com'era, perché la
premessa che conteneva («il corpus non parla di SQL») è **sbagliata** ed è parte di ciò che
la sessione ha scoperto.

```
Lavora su rag/. Due residui di AUDIT.md, entrambi in core/retrieval.py::build_ask_prompt.

1. R1 — il prompt di sistema (core/retrieval.py:834) contiene:
   "DEVI citare esplicitamente i codici dei Safeguards (es. [SAFEGUARD-TXN-01]) e i
   vincoli SQL (es. SELECT ... FOR UPDATE)."
   Il corpus non parla di SQL. AUDIT.md (A3, sezione 8) registra che nei casi
   avversariali 3 e 4 il modello ha INVENTATO vincoli SQL, dichiarandoli ipotetici.
   In un RAG di governance è il difetto peggiore possibile.

   Prima di correggere, RIPRODUCI: chiedi a /ask i casi 3 e 4 del sottoinsieme
   avversariale di eval/golden_set.yaml (server, Qdrant e Ollama accesi) e verifica
   che i vincoli SQL inventati compaiano ancora. Se non compaiono più, dillo e fermati:
   il residuo e' stantio.

   La correzione NON e' togliere la parola "SQL": la forma "DEVI citare X" genera X
   anche quando X non c'e'. Riscrivi l'istruzione perche' pretenda di citare
   CIO' CHE IL CONTESTO CONTIENE — codici di regola, identificatori, vincoli tecnici —
   e vieti esplicitamente di introdurre vincoli che il contesto non riporta.

   Verifica: rifai le stesse due domande. I codici [SAFEGUARD-*] e [REGOLA-*] devono
   continuare a essere citati quando ci sono; l'SQL inventato deve sparire. Riporta
   le risposte prima/dopo, non solo il verdetto.

2. R3 — nessun test sorveglia la crescita del prompt di sistema. Il costo fisso e'
   cresciuto due volte in una sola sessione ([CLASSE-FONTI] con A3, [REGOLA-ASTENSIONE]
   con A16) e la misura e' passata dall'81% al 104% di num_ctx a top_k=20 (A1).
   Aggiungi un test-canarino sul costo FISSO del prompt (parte indipendente dal corpus),
   con il budget in token scritto nel test insieme alla ragione e alla data della misura.
   Non deve essere un test sul prompt completo: quello dipende dal corpus e sarebbe
   fragile. Deve fallire quando qualcuno aggiunge una regola senza rimisurare.

Non toccare rank_by_authority, boost_alpha, ne' le soglie del gate.
Aggiorna AUDIT.md (le due voci in "Cosa resta aperto" di A3 e A1) e RESIDUI.md.
Suite completa + ruff prima del commit.
```

**Esito (2026-09-04).** Entrambi chiusi — dettaglio nelle voci R1 e R3 in sezione 2.
Tre cose che il prompt della sessione non prevedeva:

1. **La premessa «il corpus non parla di SQL» è falsa.** `safeguards_security.md` enuncia
   `SELECT ... FOR UPDATE` in quattro punti, dentro `[SAFEGUARD-TXN-01]`. Il difetto era che
   l'ordine di citarlo valeva per **ogni** domanda, comprese quelle il cui contesto non ne
   contiene. La correzione richiesta era comunque quella giusta — pretendere ciò che il
   contesto riporta — ma la ragione è un'altra, e il criterio di verifica cambia: non «l'SQL
   deve sparire», bensì «deve sparire dove il contesto non ce l'ha e restare dove ce l'ha».
   Aggiunta per questo una domanda di controllo sul verso opposto.
2. **L'SQL inventato non era l'unica invenzione, né la più frequente.** Riproducendo, il
   modello ha fabbricato anche codici `[SAFEGUARD-UI-01]` e `[SAFEGUARD-PALETTE-01]`
   inesistenti nel corpus — stessa forma («implicito», «ipotetico»), stessa causa. Fermarsi
   alla parola «SQL» avrebbe lasciato in piedi metà del difetto.
3. **La correzione costa 150 token di prompt fisso** (804 → 954). Dichiarato, e da subito
   sotto il canarino di R3 che questa stessa sessione ha aggiunto.

Suite: **1304 test verdi, 0 fallimenti**. Ruff pulito.

---

## S2 — Gli allarmi che mancano ✅ ESEGUITA il 2026-09-04

Chiude **R2**, **R14** (la parte risolvibile). Esito nelle righe R2 e R14 sopra; il prompt
resta qui com'era. **Una premessa è caduta**: R14 diceva che un rollback verso quelle
versioni «fallirebbe sul lato Qdrant» — misurato, riusciva, e lasciava uno stato misto che
`check_index_integrity` dichiarava `ok: true`. Era la variante grave che il prompt stesso
prevedeva.

```
Lavora su rag/. Due degradazioni silenziose che AUDIT.md lascia aperte. Sono la stessa
famiglia di A1, A18, A19 e A20: un caso limite che si comporta male senza dirlo.

1. R2 — core/indexing.py::check_index_integrity confronta i punti Qdrant con
   chunks.json, ma NON guarda mai le chiavi del sidecar ColBERT. Un chunk senza vettore
   non produce alcun problema, e oggi la funzione dice ok: true.
   Perche' conta: e' esattamente l'input che innesca A7 (colbert_score=None ->
   inversione di ranking sulle fonti normative) ed e' cio' che A18 avrebbe prodotto su
   un'aggiunta. I due riscontri si compongono e nessuno dei due allarma.

   Prima misura la copertura reale sull'indice attivo (AUDIT.md A7 dice 160/160 oggi:
   verificalo, non fidarti). Poi aggiungi il confronto come TERZA voce della stessa
   lista di problemi, con la stessa forma delle altre due — non un meccanismo nuovo.
   Attenzione al precedente documentato nella funzione: un rollback intra-lineage
   seguito da un incrementale puo' lasciare un mismatch ATTESO. Verifica se lo stesso
   vale per il sidecar ColBERT prima di decidere se il difetto va in `problems` o
   accanto alle osservazioni pure (come observe_qdrant_alias).

   Verifica per costruzione: rimuovi una chiave dal sidecar in un test e il check deve
   segnalarlo; ripristinala e deve tornare verde.

2. R14 — A20 ha distrutto le collection Qdrant di v20260901T101536 e v20260901T132300.
   I dati non sono recuperabili: gli artefatti in database/versions/ ci sono, i vettori
   no. Non provare a recuperarli.
   Cio' che e' risolvibile e' il comportamento al tentativo: verifica cosa succede oggi
   a un rollback verso una di quelle due versioni (in un ambiente che puoi sporcare, o
   simulando lo stesso stato con nomi throwaway). Se fallisce in modo oscuro, fallo
   fallire PRIMA e con un messaggio che dica quale collection manca e che serve una
   re-indicizzazione. Se invece degrada in silenzio, e' un difetto piu' grave del
   previsto e va trattato come tale.

Aggiorna AUDIT.md (A7 "Cosa resta aperto", A20 "Cosa resta") e RESIDUI.md.
Suite completa + ruff prima del commit.
```

---

## S3 — La CI non esercita ciò che dichiara ✅

Chiude **R4**, **N5**, **N6**. **Eseguita e osservata il 2026-09-04**, primo run reale sul
branch `ci/s3-qdrant-servizio-e-macos-nativo`.

Due cose che solo il run poteva dire, e che vale la pena non perdere:

- **Ha trovato subito un difetto pre-esistente.** `test_index_rollback_succeeds_when_writer_lock_free`
  falliva su un checkout pulito e passava su una macchina di sviluppo, perché
  `resolve_rollback_target` (aggiunto da S2/`1044513`) legge il `database/versions/` vero e il
  test si rifaceva a mano il set di patch invece di passare dall'helper condiviso. Corretto alla
  radice. **Nessuna esecuzione locale poteva vederlo**, ed è esattamente il genere di cosa per cui
  una CI esiste. Da qui un residuo nuovo: **R15**.
- **Il costo di `macos-nativo` era stimato dieci volte in eccesso.** Prevedevo ~50-80 minuti
  fatturati; misurati **34 secondi** (~6 fatturati), perché su macOS il lock esclude tutte le
  wheel `nvidia-*`. La restrizione a main è stata rimossa.
- **E `main` era già rossa per lo stesso difetto, da un'ora, senza che niente lo segnalasse.**
  Scoperto solo perché la diagnosi imponeva la domanda. Residuo nuovo: **R16**.

```
Lavora su .github/workflows/ci.yml (e rag/ per la documentazione).

1. R4/N5 — cinque test d'integrazione contro Qdrant vero esistono in
   rag/tests/test_qdrant_blue_green.py (sezione "OPZIONALE / SKIPPABLE") e coprono alias
   swap, delete-by-filter attraverso l'alias e invalidazione degli alias alla
   delete_collection. In CI non girano MAI: il job non avvia Qdrant, quindi saltano
   sempre. Misurato: Qdrant spento -> 5 skipped, acceso -> 36 passed.

   Aggiungi un servizio Qdrant al job `test` (services: nel workflow, immagine pinnata
   come tutte le altre versioni di questo repo). Poi VERIFICA che i cinque test siano
   davvero passati e non ancora saltati: un job verde che salta tutto e' esattamente lo
   stato di oggi. Rendi visibile il conteggio (es. -rs o un summary), altrimenti la
   regressione tornerebbe invisibile.
   Correggi il commento in ci.yml, che oggi descrive lo stato precedente.

2. N6 — l'installazione nativa su macOS e' stata verificata solo con
   `uv sync --frozen --dry-run --python-platform aarch64-apple-darwin` (A15): prova la
   risoluzione e la compatibilita' delle wheel, non che torch giri.
   I runner macOS ARM di GitHub Actions lo provano davvero. Aggiungi un job che su
   macos-14 (o piu' recente) faccia `uv sync --frozen` in rag/ e importi torch,
   stampandone versione e backend. Tienilo SEPARATO dal job test: il corpus e i servizi
   non servono, e non deve allungare il ciclo principale.
   Attenzione: la wheel richiede macosx_14_0 — un runner piu' vecchio fallirebbe per
   una ragione diversa da quella che stai provando. Verificalo dal log, non per fede.

Se un job diventa troppo lento o costoso, dillo con i numeri e proponi di limitarlo
(es. solo su main o su schedule) invece di rinunciarci in silenzio.
Aggiorna AUDIT.md (A8 e A15, "Cosa resta aperto"/"Cio' che questa chiusura NON prova"),
rag/DISTRIBUTION.md e RESIDUI.md.
```

---

## S4 — I report che dicono cose non più vere ✅ ESEGUITA il 2026-09-04

Chiude **R5**, **R6**, e cancella due note stantie dall'audit. Commit `cdb7de2`, `bcef917`,
`1027fd0` su `main`.

Tre cose che solo l'esecuzione poteva dire:

- **Due dei quattro punti erano già a posto, e la sessione era scritta per scoprirlo.** Il
  punto 3 chiedeva di ricontrollare prima di correggere: `graph_rag_ingestion_strategy.md`
  vale già `project: "cross-project"`, quindi la nota è stata **cancellata** invece di
  «correggere» un file sano. Il punto 1 si è rivelato una riga sola, perché il docstring era
  già corretto. È la disciplina di §5 che funziona due volte nello stesso giro.
- **Il punto 2 era la punta di un difetto più largo.** Il badge era l'unico posto guardato;
  la mappa dei colori ha fatto emergere che il pannello JSON non si ridisegnava al cambio di
  tema e che i punteggi Qdrant sono **due** card, di cui una in un file che il residuo non
  nominava. Chiusi tutti; ciò che resta è **R17**.
- **`getComputedStyle` mente, nel contesto di valutazione JS del browser.** Le prime letture
  dicevano che la sidebar era rimasta verde in Classico. Erano stale: il ricalcolo degli stili
  non viene svuotato, e anche `sv.style.color = 'red'` si rilegge col colore vecchio. La
  verifica valida è **il pixel** — screenshot nei due temi. Vale per ogni sessione futura che
  tocchi il CSS: leggere lo stile calcolato via JS non è una prova.

```
Lavora su rag/. Quattro correzioni piccole e indipendenti: sono tutte casi di un
messaggio che descrive uno stato superato.

1. R5 — eval/run_multihop.py:242 stampa "trigger M2 scattato"/"non scattato" come se
   fosse una decisione in corso. Il docstring dello stesso file (righe 25-27) dichiara
   gia' che e' un VERDETTO STORICO: scatto', il router deterministico fu implementato, e
   da allora i casi che lo alimentavano passano anche B — quindi il conteggio SCENDE
   man mano che il sistema funziona, e sembra un peggioramento.
   Non togliere il numero: e' utile. Cambia l'etichetta perche' dica cosa significa oggi.
   Verifica eseguendo la suite (server acceso) e rileggendo l'output come lo leggerebbe
   qualcuno che non conosce la storia.

2. R6 — templates/dashboard.unified.html:1425 colora il badge di stato con
   `status === 'success' ? verde : rosso`. Quindi "abstained" (la funzione di sicurezza
   che FUNZIONA, chiusa in A16) e "graph_answer" (un successo pieno) si vedono come
   guasti. Sostituisci il ternario con una mappa esplicita degli stati che /ask puo'
   restituire — success, graph_answer, abstained, no_results, no_graph_nodes — dando ad
   abstained una resa che dica "non ha risposto, ed e' corretto cosi'", distinta sia dal
   successo sia dall'errore. Verifica nel browser reale con una domanda fuori corpus e
   una domanda strutturale, non solo leggendo il codice.

3. AUDIT.md, righe ~757-761: la nota dice che graph_rag_ingestion_strategy.md ha il
   campo project: stantio. VERIFICATO IL 2026-09-04: vale gia' "cross-project", corretto
   dalla riconciliazione della pendenza 3 che l'audit stesso registra poco piu' sotto.
   Ricontrollalo e, se confermi, cancella la nota invece di "correggere" un file che
   e' gia' a posto.

4. AUDIT.md, A4 "Cosa resta aperto": la voce sul trigger M2 va aggiornata al punto 1 —
   il residuo era meta' di com'era scritto, perche' il docstring era gia' corretto.

Suite completa + ruff prima del commit.
```

---

## S5 — Il corpus: contaminazione residua e sottoinsieme avversariale ✅ ESEGUITA 2026-09-04

Chiude **R7**, **R8**, prepara **R13**. Esito e numeri prima/dopo in `AUDIT.md`, sezione
«S5 — il corpus cambia i numeri». In sintesi: R7 più esteso del residuo (12 archi fantasma
nel frontmatter, non solo un link morto); R8 chiuso ma **non** rimarcando il caso 4 — la
misura ha detto che su quella formulazione non c'è contrasto; due residui nuovi, **R18** e
**R19**. Sul golden set il corpus non ha mosso **nessun rango**; il multihop sì, verso il
basso (0.896 → 0.854, soglia 0.85).

```
Lavora su docs/ e rag/eval/. Questa sessione tocca il CORPUS, quindi cambia i numeri:
misura prima, reindicizza, misura dopo, e registra entrambi.

1. R7 — docs/00_meta_governance/change_log.md era gia' annotato in B1 come "tenuto, con
   un difetto da correggere separatamente", e non e' mai stato corretto. Verificato il
   2026-09-04:
     - `project: "VibeCraft — Sistema di Gestione Eventi Aziendali"` (dominio dismesso;
       la convenzione della baseline e' `project: "cross-project"`)
     - riga 98: rimanda a docs/02_specs_normative/spec_notifications_2.4.md, che NON
       ESISTE (quella cartella contiene solo spec_graph_rag_ingestion.md)
     - 3 righe su 128 contaminate dal dominio dismesso (secondo B1)
   Il file NON e' tracciato da git: non cancellarlo e non spostarlo senza backup — la
   convenzione del progetto e' docs.local-backup-<timestamp>/, mai `rm`.
   Decidi se il riferimento morto va ripuntato a un documento esistente o rimosso, e
   argomenta la scelta: e' contenuto di governance, non una nota.

2. R8 — il sottoinsieme avversariale e' sceso a 4 casi con 2 SOLI distrattori. Il caso 4
   perse il marcatore `adversarial` perche' il suo distrattore progettato
   (intent_synonym_mapping.md, peso 0.50) spari' col dominio dismesso, e — gia' misurato
   in AUDIT.md — sulla baseline tracciata non esiste un sostituto: sotto peso 0.5 ci
   sono due soli documenti e nessuno dei due nomina LLM, privacy o dati personali.
   Serve un DOCUMENTO NUOVO: informativo, bassa autorita' dichiarata, su un tema che il
   corpus non copre, che possa fare da distrattore credibile. Scrivilo come contenuto
   vero (deve reggere la lettura, non essere un'esca), tracciato in git perche' e' parte
   dello strumento di misura — come i distrattori portati nella baseline in Run B.
   Poi ripristina il caso 4 con `distractor:` puntato al nuovo file e verifica che
   test_casi_avversariali_hanno_matcher_validi lo veda.

3. Full rebuild + promozione. Rimisura: golden set classico (recall@1/@2, MRR,
   source_in_top3), sottoinsieme avversariale, e la suite multihop. Registra prima/dopo
   in AUDIT.md: i numeri di ieri e quelli di domani NON sono confrontabili e va scritto.
   Attenzione all'eval-gate: gira sui job full e blocca la promozione sotto 0.75 a k=2.

4. R13 (preparazione, non esecuzione) — recall@2 e' a 0.873 con soglia 0.75: 12 punti di
   margine. Il giorno in cui saturasse non resta un k piu' basso, e l'unica strada e'
   estendere il golden set con casi che il sistema SBAGLIA. Farlo sotto pressione
   significa sceglierli per far scendere un numero. Individua e annota 3-5 candidati
   ora, senza aggiungerli: serve un elenco pronto, non un'estensione affrettata.

Aggiorna AUDIT.md (A6 "Cosa resta aperto", A2b) e RESIDUI.md.
```

---

## S6 — Le metriche che non guardano la risposta

Chiude **R9**, **R10**, **R11**, affronta **N3**.

```
Lavora su rag/eval/ e rag/scripts/. Sessione di MISURA: il primo esito accettabile e'
scoprire che non c'e' niente da correggere.

Il filo comune, che AUDIT.md nomina tre volte senza mai chiuderlo: ogni metrica di questo
progetto guarda il RETRIEVAL, e i difetti che contano vivono nella RISPOSTA.

1. R9 — le tre catene multihop a tre documenti si fermano a 2 su 3 (A4). La soglia messa
   in A4 mette un pavimento sotto quel numero, non lo alza. Ma la domanda vera non e'
   mai stata posta: /ask inietta anche le sezioni raggiunte VIA GRAFO, quindi il terzo
   documento potrebbe gia' essere nella risposta pur mancando dal retrieval.
   MISURA: prendi le tre catene da eval/golden_multihop.yaml, chiedile a /ask (server,
   Qdrant e Ollama accesi) e verifica se il terzo documento compare nel contesto
   iniettato e nella risposta. Se compare: non c'e' difetto, e il residuo si chiude
   dichiarando cosa la soglia misura davvero — come fu fatto per A4. Se non compare:
   riporta il caso preciso e proponi, senza implementarla, la correzione minima.

2. N3 — "a chi la risposta attribuisce il vincolo" e' la metrica vera di questo sistema
   e non esiste. A3 fu chiuso leggendo 4 risposte a mano, 2 esecuzioni per condizione,
   un solo modello. Il giudizio regge come segnale, non come misura ripetibile.
   Proponi il progetto minimo di un harness di attribuzione: un giudice LLM che, data la
   domanda e la risposta, dica quale fonte la risposta indica come NORMATIVA. Costo: una
   chiamata per caso, 4-5 casi. Prima di scrivere codice, verifica su quei 4 casi che il
   giudizio automatico coincida con quello umano gia' registrato in AUDIT.md (tabella
   della sezione 6 di A3): se non coincide, il giudice non e' pronto e va detto.

3. R10/R11 — due contratti che nessun test esercita contro un LLM vero:
     - il marcatore [ASTENSIONE] e' un impegno del prompt, non una garanzia del modello
     - la soglia di certezza su num_ctx (A1) e' stata osservata a mano, mai provata
   In CI non c'e' un LLM. Il canale giusto e' il check notturno
   (scripts/nightly_consistency.{sh,ps1}), che gira dove Ollama c'e' ed e' gia' collegato
   agli alert. Aggiungi le due verifiche li': una domanda fuori corpus deve tornare
   status "abstained"; una richiesta oltre la finestra deve tornare 502 col messaggio
   dichiarato. Ricorda che i due script sono GEMELLI e vanno tenuti allineati, e che i
   .sh devono restare LF (.gitattributes).

Aggiorna AUDIT.md (A3 sezione 8, A4 e A16 "Cosa resta aperto", A1) e RESIDUI.md.
```

---

## S7 — Lo storico che riparte da zero

Chiude **R12**.

```
Lavora su rag/core/eval_history.py e rag/eval/.

R12 — le righe di history.jsonl portano solo la chiave del k in vigore quando furono
scritte. Spostando eval_gate.k da 10 a 2 (A2b) la serie sorvegliata si e' accorciata da
79 a 22 punti: corretto, perche' mescolare k diversi sarebbe peggio, ma significa che
ogni futuro spostamento del gate azzera quasi il grafico.

La strada indicata da AUDIT.md: registrare TUTTI i k calcolati in ogni riga, anche nelle
righe scritte dal gate, che oggi ne registra uno solo.

Prima di scrivere: leggi come _series seleziona per chiave e verifica che una riga piu'
larga non rompa nessuno dei consumatori — le due pagine (/eval e l'infografica),
eval_health, compute_trend, detect_regression e il guardrail di eval.run. Il rischio non
e' scrivere di piu', e' che qualcuno legga la prima chiave che trova.

Le righe gia' scritte restano com'sono: non riscriverle. Il beneficio parte da qui in
avanti, e va detto — un grafico che si allunga da oggi non e' un grafico che recupera il
passato.

Verifica: una riga nuova contiene tutte le chiavi; spostando EVAL_GATE_K in un test la
serie del nuovo k esiste gia'; i consumatori leggono ancora la chiave del gate e non
un'altra a caso.

Aggiorna AUDIT.md (A2b "Cosa resta aperto") e RESIDUI.md.
Suite completa + ruff prima del commit.
```

---

## S8 — Le decisioni, non il codice

Chiude **N1**, **N2**, **N4**, **N7**, **N8**.

```
Nessun codice di produzione in questa sessione. Cinque scelte che AUDIT.md ha lasciato
argomentate ma non decise: vanno confermate o ribaltate UNA volta e registrate, invece di
essere ridiscusse a ogni sessione.

Per ognuna: rileggi la ragione scritta in AUDIT.md, verifica che la premessa regga ancora
oggi (piu' di una si e' rivelata stantia in questo audit) e proponi una decisione con la
sua condizione di riapertura — "si rifa' quando X", non "per ora no".

1. N1 — streaming incrementale di /ask (A11). Costerebbe il contratto: oggi la risposta
   e' un JSON unico con risposta, contesto grafo, archi, punteggi e latenze, piu' un
   secondo percorso d'errore e la cache da ripensare. Misurato: p50 24,1 s, p95 32,0 s,
   di cui il 97,8% e' generazione LLM. Il loader ora conta i secondi. Serve davvero?

2. N2 — gate sulla latenza (A11). Il bench e' una misurazione per contratto (exit 0) e un
   p95 su 10 campioni non regge una soglia. Ma una baseline che nessuno rilegge invecchia:
   e' esattamente cio' che A2b ha mostrato altrove. Esiste una via di mezzo?

3. N4 — strada 1, peso di sezione (A3). Il 70% del deficit di rango 1 e' fra sezioni
   SORELLE, dove il moltiplicatore di autorita' si semplifica e nessun alpha puo'
   separarle. A3 fu chiuso al livello del prompt, non del rango. Va tenuta come candidata
   o archiviata?

4. N7 — extra in conflitto CPU/CUDA per torch (A15). Oggi una macchina CPU-only x86-64
   scarica ~4 GB di CUDA che non usera'; funziona, e per quel caso esiste il target `cpu`
   del Dockerfile. L'alternativa cambierebbe il comando di installazione per tutti.

5. N8 — ricalibrazione del tetto top_k (A1). top_k=20 tocca il 104% della finestra su
   almeno una domanda reale; la correzione di A1 riguardava il comportamento al
   superamento, non il tetto. Abbassarlo richiede una misura sistematica.

Registra gli esiti in AUDIT.md e in RESIDUI.md sezione 1, con la data. Una decisione senza
data e senza condizione di riapertura torna a essere una domanda aperta.
```

---

## Ordine consigliato

```
S1  prompt che invita a inventare  ✅  ← comportamento scorretto oggi
S2  allarmi mancanti               ✅  ← degradazioni silenziose
S4  report non piu' veri           ✅  ← piccole, indipendenti, sbloccano la lettura
S3  CI                             ✅  ← rende permanente cio' che S2 protegge
S5  corpus                             ← cambia i numeri: dopo S1, prima di S6
S6  metriche sulla risposta            ← misura sul corpus nuovo
S7  storico
S8  decisioni                          ← in qualsiasi momento, anche in parallelo
```

**S5 va dopo S1** perché la correzione del prompt cambia le risposte, e S5 rimisura tutto.
**S6 va dopo S5** perché misurerebbe su un corpus che sta per cambiare.
**S4 e S8 non hanno dipendenze** e possono essere intercalate ovunque.

# AUDIT — Run A: inventario

**Data:** 2026-09-01 · **Commit:** b1ef300 · **Metodo:** lettura dei flussi + misura con
gli strumenti del progetto (`pytest`, `eval/run.py`, `eval/run_multihop.py`, `/api/health`,
`/ask` dal vivo, `observe_docs_git_divergence`).

**Contratto di questo documento:** contiene solo RISCONTRI, non soluzioni. Ogni riga è
ancorata a un file:linea o all'output di un comando eseguito. Le proposte sono compito
della Run B, che legge questo file.

**Ambiente della misura:** Qdrant server-mode attivo (5 collection versionate), Ollama
`qwen3.5:9b` attivo, indice `v20260825T100624` — 847 nodi, 1133 archi, 181 chunk,
452 simboli di codice.

---

## Verdetto

Il sistema è **solido nel nucleo e cieco sul proprio metro di misura**.

Ciò che regge davvero, misurato: 1253 test verdi senza un solo skip; integrità
dell'indice perfetta (181/181 chunk con vettore ColBERT, delta Qdrant↔sidecar = 0);
router deterministico con 0 falsi positivi su 55 casi; e — la verifica più importante per
un RAG di governance — **l'astensione funziona**: a una domanda plausibile ma assente dal
corpus il sistema rifiuta di rispondere, motiva il rifiuto e cita la regola che lo impone,
invece di inventare.

I tre rischi che lo rendono "non completo":

1. **Il guardrail sul contesto è un log, non un limite.** Dentro il contratto dichiarato
   dell'API (`top_k ≤ 50`) si costruisce un prompt di ~30.939 token stimati contro
   `num_ctx=16384`: Ollama tronca dall'alto in silenzio, e la risposta HTTP resta
   `status: "success"` senza alcun segnale al chiamante. È la stessa classe di difetto che
   il progetto ha già documentato e curato alzando `num_ctx` — ma la cura non tiene un
   parametro controllato dal chiamante. *Precisazione dopo la verifica:* alla console
   l'utente si ferma a `top_k=20` (81% della finestra, warning acceso, nessun troncamento),
   perché un attributo HTML glielo impedisce. Il difetto non è che gli utenti vengano
   troncati oggi: è che l'unico argine fra i due regimi è validazione lato client.
2. **Lo strumento di misura non vede sempre ciò che misura.** `GET /api/retrieve` — su cui
   gira *tutto* l'harness di eval — è l'unica route di retrieval che non ricarica lo
   snapshot: dopo una promozione misura uno stato misto (Qdrant nuovo, sidecar vecchi) e lo
   fa in silenzio. Oggi è andata bene per caso — la modifica era una cancellazione pura, e i
   chunk nuovi erano un sottoinsieme dei vecchi; su un'aggiunta si sarebbe composto con
   l'inversione di ranking di A7. Il gate, invece,
   è sano: sta a recall@2 con soglia 0.75 (*correzione: la mia prima lettura diceva k=10 e
   0.90 — erano i default del codice, non la configurazione attiva*). Ma trend, rilevamento
   di regressione e il numero in evidenza su `/api/health` guardano ancora recall@10, che è
   saturo a 1.000. E un segnale che discrimina resta non sorvegliato da nessuno: sul
   sottoinsieme avversariale **recall@1 = 0.0%**, invariato anche dopo la pulizia del corpus.
3. **I numeri non sono riproducibili da nessun altro.** Il corpus indicizzato è 26
   documenti, quelli tracciati da git sono 11 — esattamente gli "11 documenti" che il
   golden set dichiara come corpus di riferimento. Il rilevatore di divergenza riporta
   `diverging: []` perché per costruzione non guarda le aggiunte non tracciate. Chiunque
   cloni il repo — CI compresa — misura su meno di metà corpus; e l'11% dei chunk indicizzati
   appartiene ai tre documenti che il golden set dà per rimossi.

---

## Inventario

| ID | Asse | Tipo | Evidenza | Impatto se non risolto | Sforzo | Verifica di chiusura |
|---|---|---|---|---|---|---|
| A1 | LLM / contesto | FRAGILE → **CHIUSO 2026-09-03** | Il tetto server-side (`top_k≤20` in `api/models.py`, non più `≤50`) era già stato chiuso in una run precedente — la riga non l'aveva mai registrato. Ma non bastava: misurato dal vivo **oggi**, `/ask` con `top_k=20` — il massimo ora legittimo, non un bypass — produce **~17.013 token stimati su `num_ctx=16384`, il 104%**, e la risposta tornava comunque `status:"success"`. Il corpus e il prompt di sistema sono cresciuti (`[CLASSE-FONTI]`, `[REGOLA-ASTENSIONE]`, entrambi aggiunti in questa sessione) da quando fu misurato l'81% originale: quel margine non c'è più | Non un caso limite raro costruito apposta: il tetto legittimo del server supera la finestra su una domanda ordinaria. Guard a `core/llm.py` solo `logger.warning`, mai visto in tempo reale da nessuno | S | Guardrail a due soglie in `core.llm._ollama_payload`: **certezza** (stima ≥ `num_ctx`) solleva `LLMError` — 502 su `/ask`, testo d'errore sulle pipeline (`generate_tolerant` già lo assorbe, nessun chiamante da toccare); **rischio** (80-100%) resta `logger.warning`, invariato. Verificato dal vivo: la stessa richiesta a 104% ora torna 502 col messaggio chiaro; una domanda normale (`top_k=8`) resta `success` |
| A2 | ~~Eval / gate~~ | ~~FRAGILE~~ → **RITIRATO** | **Riscontro sbagliato.** Avevo letto i *default* del codice (`_eval_gate_cfg.get("k", 10)`, `core/config.py:346-347`) scambiandoli per la configurazione attiva. `rag_config.yaml` imposta `k: 2`, `min_recall: 0.75`, `blocking: true`, e documenta una migrazione deliberata k=10 → k=5 → k=2, ogni passo innescato dall'**alert di saturazione del progetto stesso**. Provato dal rebuild eseguito oggi: `Eval-gate: recall@2=0.873 ≥ soglia 0.75 — promozione consentita` | Nessuno: il gate fa già ciò che avrei raccomandato, e con una soglia derivata dal proprio storico | — | — |
| A2b | Eval / osservabilità | FRAGILE → **CHIUSO 2026-09-03** | Ciò che restava di A2, ed era vero — ma **più esteso di così**. `eval_gate.k` è migrata 10 → 5 → 2, ogni volta perché l'alert di saturazione diceva che quel k non discriminava più; tutto ciò che il gate lo osserva era rimasto a 10. Oltre ai tre osservatori dello storico e a `last_recall_at_10` in `/api/health`: la pagina `/eval` disegnava una **retta a 1.000**, l'infografica colorava contro uno `0.9` scritto a mano mentre il gate stava a 0.75, il guardrail di `eval.run` asseriva su `recall@max(ks)` — e i **due script notturni girano senza `--k`**, quindi confrontavano recall@10 satura contro `--assert-min 0.90` | Il cancello proteggeva; il check notturno di qualità era verde **per costruzione** da quando il gate lasciò k=10, e il numero in evidenza sulla dashboard era l'unico che non poteva peggiorare | S | Una sola sorgente: `GATE_RECALL_KEY` da `EVAL_GATE_K`. Storico, salute, guardrail, check notturno e le due pagine leggono la chiave e la soglia del gate; spostare `eval_gate.k` sposta anche la sorveglianza |
| A3 | Retrieval → **prompt** | MANCANTE → **CHIUSO 2026-09-03** | Il riscontro era giusto (avversariale recall@1 = 0.0%), la diagnosi che suggeriva no: **non era un problema di rango**. Indagine in fondo a questo documento. La fonte giusta entra sempre nel contesto (`source_in_top3` avversariale = 100%), ma l'autorità veniva calcolata, usata per riordinare e **buttata via al confine del prompt**: l'intestazione era `--- doc § sezione ---` e basta, così dentro la finestra il modello ri-ordinava per prosa. Misurato su `/ask`: **2 risposte su 4 attribuivano il vincolo alla fonte METHODOLOGY che lo illustra**, con la spec declassata a «conferma» | Il difetto che ADR 0002 esiste per impedire, sopravvissuto un livello più in là di dove ADR 0002 guardava — e invisibile a ogni metrica, perché il ranking era già corretto | M | **Cambiata**: non più «recall@1 avversariale sotto soglia» — resta 0.0% ed è corretto che resti. La classe dichiarata arriva nel prompt (`tests/test_ask_authority_prompt.py`) e le 4 risposte attribuiscono il vincolo alla fonte normativa |
| A4 | Retrieval / multihop | FRAGILE → **CHIUSO 2026-09-03** | **Metà riscontro era una lettura sbagliata del report**: 4 di quei fallimenti sono la MISURA, non un difetto, e la testata del golden set lo diceva già — 11 documenti non entrano in un top-10, e le catene a tre documenti si fermano a due. È il gap che fece scattare il trigger M2. Il quinto era vero ma di altro genere: `count: 11` sull'enumerazione dei documenti, mentre il router rispondeva **23 e aveva ragione** — un'attesa-istantanea, e l'unica eccezione a una regola che il file stesso enuncia («si asseriscono relazioni, non conteggi») | Vero e più grande del riscontro: **nessun gate, nessuno storico, nessun allarme, nemmeno una riga di README**. La suite girava a mano e il suo esito viveva in un JSON che nessuno rileggeva | M | Soglia in `eval_multihop` (rag_config.yaml) sulla **recall media di A** — non sui casi riusciti, che hanno un tetto — più esattezza piena di B; storico con chiavi prefissate, alert critico sotto soglia, e la suite nel check notturno. `count` rimosso: **B passa 6/6** |
| A5 | ~~Eval / strumento~~ | ~~FRAGILE~~ → **RITIRATO, assorbito da A6** | **Riscontro impreciso.** Avevo concluso "l'harness sottostima il ramo grafo" vedendo una risposta corretta segnata come fallita. Leggendo `eval/golden_multihop.yaml:90-96`: il caso dichiara `count: 11` — la baseline committata — e i 4 nodi attesi ci sono tutti. L'unico scarto è il conteggio (26, poi 23, contro 11). **L'harness ha ragione: sta segnalando che il corpus è divergente.** Non è un difetto della misura, è la misura che funziona | Nessuno di per sé: è A6 che parla | — | — |
| A6 | Corpus / riproducibilità | FRAGILE → **CHIUSO (Run B)**, riga riallineata il 2026-09-04 | La riga era rimasta alla fotografia della Run A — e i suoi numeri non erano più veri: oggi `docs/` ha **23** `.md`, di cui **14 tracciati**, non «26 vs 11». La Run B aveva già chiuso il riscontro per la **seconda** strada del criterio (la prima resta impraticabile: 9 documenti — 6 output di pipeline, 3 spec locali del progetto ospitante — stanno nell'indice per ragioni legittime e non devono entrare nel repo): i distrattori dei casi avversariali portati nella baseline tracciata, `untracked` aggiunto a `observe_docs_git_divergence()`, e il corpus **dichiarato** nel report di eval accanto ai numeri e nel JSON. Indagine e chiusura in fondo al documento | Verificando la chiusura è emerso un difetto **dentro la chiusura stessa**: il rilevatore contava *tutti* i file tracciati sotto `docs/`, quindi i 2 `.gitkeep` della struttura di cartelle, e il report annunciava «16 documenti tracciati» contro i **14** realmente indicizzati. Un campo di provenienza che non corrisponde al corpus misurato è precisamente ciò che quel campo esiste per evitare — ed è la stessa trappola che la riga originale aveva già segnalato («i 13 path includono 2 `.gitkeep`») | M | Perimetro allineato a `DOC_EXTS`, cioè esattamente il filtro con cui l'indicizzazione enumera `docs/`: `tracked` e `untracked` ora contano solo file che l'indice legge. Verificato dal vivo — `misurato su: 14 documenti tracciati · +9 NON tracciati`. Test in `tests/test_index_integrity.py` con un `.gitkeep` tracciato e un `.png` non tracciato: verificato contro il codice vecchio, `tracked` valeva 2 |
| A7 | Retrieval / ranking | FRAGILE (latente) → **CHIUSO 2026-09-03** | Confermato, e la regola giusta era **già scritta nella funzione che produce quel `None`**: `colbert_maxsim` dichiara «non giudicabile, che non è la stessa cosa di poco pertinente», e `rank_by_authority` lo sostituiva con un `-1.0` — cioè con «pochissimo pertinente» — moltiplicandolo per l'autorità. Cercando la correzione è emerso di più: i due rami si **contraddicevano**, e gli stessi chunk senza vettore uscivano in un ordine da soli e nell'ordine INVERSO appena un terzo chunk qualsiasi portava un vettore. Più una **divisione per zero** nella stessa espressione, ad α=1 con una fonte che dichiara `authority: 0.0` — α=1.0 è una coordinata della griglia del calibratore | Sotto divergenza sidecar↔Qdrant il ranking si inverte proprio sulle fonti normative, in silenzio | S | Due insiemi invece di due rami: nessun punteggio finto, i non giudicabili in coda ordinati per fusione÷autorità. Copertura **160/160** oggi, quindi resta latente e il percorso di produzione non cambia di una posizione — c'è un test che lo fissa. Le attese sono state verificate una per una contro la regola vecchia: la prima che avevo scritto **passava anche col difetto** |
| A8 | Test / copertura | MANCANTE → **PREMESSA RITIRATA, sostanza CHIUSA 2026-09-03**, residuo CI **CHIUSO 2026-09-04** (run reale: 0 skipped, i cinque girano) | **L'inferenza era rovesciata.** «0 skip con Qdrant attivo ⇒ nessun test tocca un Qdrant reale»: con il servizio ATTIVO un test d'integrazione *gira*, non salta — 0 skip è esattamente ciò che ci si aspetta quando funziona. Misurato oggi in entrambe le direzioni: Qdrant spento → **5 skip espliciti col motivo**, Qdrant acceso → **36 passed**. I 3 test contro Qdrant vero esistono dal **2026-07-17/18** (`cc39609`, `47d4e35`), ben prima della Run A, e soddisfacevano già il criterio di chiusura di questa riga. Anche il commento in `ci.yml` era già stato corretto in L3 | **Ma la sostanza teneva in parte**: dei quattro rischi elencati, solo l'alias swap era davvero verificato contro il servizio reale. La **delete-by-filter** — che in produzione gira contro l'ALIAS ed è il percorso caldo dell'incrementale — non lo era: i fake registrano solo *quale* nome ricevono e ignorano del tutto il `points_selector`. Se Qdrant non risolvesse l'alias su una delete, l'incrementale lascerebbe i chunk vecchi **in silenzio** | M | 2 test d'integrazione nuovi: `_delete_doc_chunks` (la funzione di produzione) invocata sull'alias deve togliere ESATTAMENTE i punti del documento indicato e lasciare gli altri; e `delete_collection` deve invalidare gli alias che la puntavano — assunzione su cui poggia il GC, finora scritta solo in un commento del fake. Verificata anche la portanza: la stessa delete verso un nome inesistente **solleva**, quindi il test non passa per caso. **2026-09-04**: `services: qdrant` (`qdrant/qdrant:v1.19.0`, allineata a `qdrant-client==1.19.0`) nel job `test`, piu' tre meccanismi perche' quei cinque non possano tornare a saltare in silenzio — `VIBECRAFT_REQUIRE_QDRANT=1` che trasforma lo skip in errore, `pytest -rs`, e un passo che pretende `5 passed`. Misurato nelle tre direzioni; suite intera 1317 passed / 0 skipped col servizio acceso |
| A9 | CI / qualità | MANCANTE → **CHIUSO 2026-09-03** | `ruff` aggiunto come dev dependency, con selezione **esplicita** (`E4/E7/E9/F`) invece del default del tool: il default di ruff 0.16 include famiglie di stile discrezionale (SIM, PIE, YTT, ...) e sul codebase mai linterato produceva **380** riscontri, quasi tutti preferenze di scrittura; la selezione scelta ne produceva **42**, tutti segnali reali (import morti, variabili inutilizzate, nomi ambigui come `l`, import fuori ordine non deliberato) | Su 37.5k righe, regressioni di stile e di correttezza passavano senza essere viste; mypy/coverage restano fuori scope (non richiesti dal criterio di chiusura, e mypy a freddo su un codebase mai tipizzato è un lavoro di tutt'altra scala) | S | Tutti e 42 i riscontri corretti (non silenziati): 5 import inutilizzati rimossi, 1 variabile morta rimossa (`api/routes_retrieval.py`, verificato che non gatava nulla — `search_code_symbols` si autoguarda già), 5 f-string senza placeholder, 11 nomi ambigui `l`→`line`/nome specifico, 4 lambda assegnati→`def`, 1 doppio `;`, 2 `E402` genuini riordinati (`code_index/docker.py`, `core/retrieval.py`), 2 `E402` **deliberati** (encoding UTF-8 prima degli import applicativi) dichiarati in `per-file-ignores` con la ragione, non silenziati a caso. Gate in `scripts/ci.sh`/`ci.ps1` (gemelli, verificati entrambi) prima della suite; verificato in entrambe le direzioni: una violazione introdotta apposta fa fallire il gate con `exit 1` prima che pytest parta, il codebase pulito passa. 1289 test invariati |
| A10 | ~~Sicurezza / doc~~ | ~~FRAGILE~~ → **RITIRATO** | **Riscontro sbagliato.** Lo scarto di 19 giorni fra i commit era un indizio, non una prova, e l'ho riportato come sospetto: la riconciliazione riga-per-riga (B5, eseguita) dice che il documento è **allineato**. Le 57 route del codice sono tutte in tabella — `GET /` è la riga 1 (`SECURITY_SURFACE.md:118`) — e le 7 che sembravano "documentate ma assenti" sono le auto-route di FastAPI (`/docs`, `/redoc`, `/openapi.json`, `/docs/oauth2-redirect`) e il mount statico, che il documento conta esplicitamente a `:33`. Il mio grep sui decoratori `@router` non poteva vederle: il documento era più completo del mio strumento | Nessuno | — | — |
| A11 | Prestazioni | FRAGILE → **CHIUSO 2026-09-04** | I due numeri della riga erano presi a `top_k=50`, che dal A1 **non è più accettato** (`api/models.py`: `le=20`): non erano riproducibili. Rimisurati oggi al `top_k` di default, cache fredda, 10 query del golden-set — **p50 24,1 s, p95 32,0 s, max 33,7 s**. Ma la scoperta è un'altra: il retrieval pesa **0,50 s su 22,7 di media — il 2,2%**. Il 97,8% è la generazione LLM. E lo strumento per misurarlo esisteva già (`scripts/bench.py`, con `p50`/`p95` già scritti e usati per `/api/retrieve`): su `/ask` girava su **3 query fisse** e riportava solo la **media** — con n=3 il p95 non è calcolabile, e la media è esattamente il numero che nasconde la coda. `eval/results/` non conteneva **nessun** `bench_*.json`: la regola del README («nessuna ottimizzazione senza baseline salvata») non aveva una baseline | Un'attesa di 30 s senza feedback è indistinguibile da un blocco — e il loader era un'animazione muta, il tempo trascorso compariva solo **dopo**, nel badge `⏱ Ns`. In più, senza il breakdown misurato, "ottimizzare la latenza" sarebbe finita sul ranking: il 97,8% sta altrove | M | `bench_ask` porta `p50`/`p95`/`max` del totale lato server su 10 query del golden-set (stessa sorgente e stessa numerosità di `bench_retrieve`, riusando i `p50`/`p95` già presenti); baseline dichiarata in README con la macchina e la data. Feedback: il loader di `/ask` conta i secondi (verificato dal vivo — sale, si ferma alla risposta, non lascia intervalli appesi). Streaming **non fatto**: cambierebbe il contratto di `/ask`, ed è dichiarato come tale invece che sottinteso |
| A12 | Codice / debito | SUPERFLUO → **CHIUSO 2026-09-03** | 6 `TODO(2026-07-12)` scaduti da 51 giorni. Cinque erano limiti permanenti travestiti da piani (glob `workspaces` non espansi, URL relative non abbinate al backend, link DMN→processo, "fuori scope: VB.NET/Razor HTML/JS") — ridatati togliendo il calendario e dicendo perché non sono pianificati. Il sesto, `_js_symbols`, era diverso: un piano vero, con la sua condizione di chiusura già scritta ("quando la migrazione tree-sitter sarà consolidata in produzione") | Il debito dichiarato con una data e ignorato smette di essere un piano — e nel caso di `_js_symbols` nascondeva un rischio reale: `pickle`-adiacente no, ma un secondo parser (regex) mai più esercitato restava comunque superficie da mantenere, con un test di 128 righe che lo teneva in vita artificialmente | S | Verificata la condizione della TODO stessa: migrazione del 2026-07-12, 53 giorni e molti commit dopo ancora `treesitter` di default per typescript/javascript/svelte, zero incidenti. **Rimosso** (decisione dell'utente, non mia): `_js_symbols`, `_PARSER_LANG`/`_PARSER_DEFAULTS`/`_parser_impl`, le chiavi `code_parsers.typescript/javascript/svelte` (decorative, un solo valore possibile), e `tests/test_ts_parser_equivalence.py` — **sostituito**, non solo cancellato, da `tests/test_ts_parser.py`: stesso corpus, assert dirette invece che per confronto, cosicché la copertura di `ts_symbols`/`svelte_symbols` non regredisse |
| A13 | Codice / legacy | SUPERFLUO → **CHIUSO 2026-09-03** | `core/artifacts.py:35` importava `pickle` per il solo ramo di lettura legacy. Verificato **prima** di rimuoverlo: zero `.pkl` in tutto il progetto (`find` sull'intero repo, escluso `.venv`), e la scrittura era già disattivata da prima di questo audit — `save_artifacts()` non ha mai scritto `.pkl` da quando i formati JSON/`.npz` esistono | Un formato di deserializzazione arbitraria mantenuto per una retrocompatibilità di cui nessuno aveva più bisogno | S | Rimosso il ramo di fallback in `load_artifacts()` e i 5 percorsi `*_SAVE_PATH` (`core/config.py`), l'unico check di esistenza rimasto in `current_version()`, il fallback d'mtime in `api.deps._graph_version()`, e il parametro `emit` di `load_artifacts()` (diventato morto insieme all'unico warning che lo usava) nei 3 call site reali. 6 file di test aggiornati (rimossa `test_fallback_reads_legacy_pickle_with_warning`). Verificato dal vivo: il server carica lo snapshot reale (755 nodi, 160 chunk) passando solo da JSON/`.npz`. 1290 test verdi (1291 − 1: la suite rimossa testava un comportamento che non esiste più) |
| A14 | Distribuzione | MANCANTE → **CHIUSO (Run C/L1)** | Verificato oggi: `README.md`, `LICENSE`, `.env.example`, `Dockerfile` esistono tutti a root, prodotti da L1/L2. La riga non era mai stata aggiornata dopo la Run C, restava con l'etichetta della Run A | — | — | Verificato: `ls README.md LICENSE Dockerfile rag/.env.example` — presenti tutti |
| A15 | Portabilità | MANCANTE → PARZIALE → **CHIUSO 2026-09-04**, residuo «Mac vero» coperto da CI lo stesso giorno | **Il difetto era reale e la sua descrizione no.** Misurato con `uv sync --frozen --dry-run --python-platform <p>` su sei piattaforme, prima della correzione: falliva su **macOS Intel, macOS ARM e Windows ARM**; **Linux ARM64 riusciva** (cu126 pubblica wheel `manylinux_2_28_aarch64`), e una macchina **CPU-only x86-64 riusciva pure** — la build CUDA si installa e gira su CPU, solo pesante. Quindi la formula «macOS/ARM/CPU-only» copriva due casi che non erano rotti e ne mancava uno che lo era. Corretto: l'indice cu126 ora ha un marcatore che è la **trascrizione dell'elenco di wheel del lock**. Emerso strada facendo: senza pin di versione uv risolveva macOS a **2.14.0** contro 2.13.0 di tutti gli altri — la deriva che il Dockerfile documenta di aver già subito una volta; `torch` è ora pinnata a 2.13.0, verificato che PyPI abbia la wheel corrispondente per Apple Silicon | Installazione nativa impossibile su macOS resta il caso reale; Linux ARM e CPU-only non lo erano | M | **Cambiata**: non «`uv sync` riesce su una macchina senza NVIDIA» — quello riusciva già. Dopo: Linux x86-64/ARM64, Windows x86-64 e **macOS Apple Silicon** riescono. macOS Intel e Windows ARM restano impossibili perché **PyTorch non pubblica quelle wheel da nessuna parte**: limite a monte, non configurazione locale, e ora dichiarato in README. 5 test **offline** (`tests/test_torch_platform_pin.py`) leggono `pyproject.toml`+`uv.lock` e fissano l'invariante; verificati contro la configurazione vecchia: 3 su 5 falliscono. Immagine Docker `cpu` ricostruita dopo il re-lock: 129 pacchetti, venv 2,2 GB, `torch 2.13.0+cpu` — identica a prima. **Stesso giorno**: job `macos-nativo` su `macos-15` (arm64, non deprecato) che fa `uv sync --frozen` VERO, importa torch e calcola un matmul — non piu' solo un dry-run. Premessa `macosx_14_0` verificata dal log (`sw_vers`/`uname -m`, fallimento esplicito sotto la 14). **Eseguito: verde in 34-36s su due run**, e smentisce la mia stima di ~50-80 minuti fatturati (130 pacchetti contro 149, torch 106,1 MiB contro 804,7); restrizione a main rimossa, gira su ogni push. Dal log: macOS 15.7.9 arm64, tag `macosx-15.0-arm64`, `torch 2.13.0` senza `+cu`, **matmul eseguito su `mps`** |
| A18 | Eval / strumento | MANCANTE → **CHIUSO** | Trovato eseguendo B1, e provato in isolamento: `GET /api/retrieve` era **l'unica route di retrieval a non chiamare `maybe_reload_graph()`** (`api/routes_retrieval.py:493`, da confrontare con `:88` di `/ask` e `:586` di `/api/code/search`, più le 4 di `routes_graph`). Dimostrazione: dopo una promozione, `/api/health` → `v20260825T100624, 181 chunk`; una chiamata a `/api/retrieve` la lasciava **invariata**; una a `/ask` la portava a `v20260901T101536, 160 chunk`. **Quanto era grave dipendeva dal tipo di modifica**: su una CANCELLAZIONE pura (il caso di B1) i chunk nuovi sono un sottoinsieme dei vecchi — il sidecar stantìo li copriva tutti, per fortuna e non per costruzione; su un'AGGIUNTA o una MODIFICA i chunk_id nuovi sarebbero mancati dal sidecar, `colbert_maxsim` avrebbe restituito `None` — l'esatto input che innesca l'inversione di A7. I due riscontri si componevano | **L'harness di eval interrogava solo `/api/retrieve`**: dopo una promozione o un rollback misurava uno stato MISTO — alias Qdrant nuovo, sidecar ColBERT/chunk in memoria vecchi — in silenzio | S | `maybe_reload_graph()` aggiunta a `api_retrieve` (`api/routes_retrieval.py:529`); verificato dal vivo (CURRENT spostato, poi `/api/retrieve` ricaricato alla prima chiamata) e fissato da `tests/test_retrieve_reload.py` |
| A17 | Documentazione | FRAGILE → **CHIUSO 2026-09-03** | `templates/infografica.unified.html:296` descriveva come attivo un *"budget guard giornaliero sulla spesa Claude [che] devia automaticamente su Ollama"*; in `rag_config.yaml` l'intero blocco `budget:` è **commentato**, e con `active_provider: ollama` nessun purpose chiama Claude oggi — non c'è spesa da proteggere | L'infografica è il documento che spiega il sistema a chi non lo conosce: descriveva una protezione di costo attiva che non esiste | S | Corretta la frase: il guard è **pronto** in `core/llm.py` (codice reale, non ipotetico), **spento di default**, con il perché (nessun purpose su Claude oggi) e quando riattivarlo. Non riattivato: farlo oggi non avrebbe alcun effetto — non esiste spesa Claude da proteggere — e attivarlo comunque avrebbe aggiunto stato (contatore di spesa) senza alcuna utilità corrente |
| A16 | API / contratto | FRAGILE → **CHIUSO 2026-09-03** | Confermato: alla domanda fuori corpus la risposta era un rifiuto corretto e motivato, ma il payload restava `status:"success"` con le fonti elencate. La correzione non è un'euristica sul testo — parsare la prosa italiana di un LLM per capire se si è astenuto sarebbe fragile per costruzione — ma un **contratto**: `[REGOLA-ASTENSIONE]` nel prompt impone il token `[ASTENSIONE]` come primo carattere della risposta quando e solo quando il contesto non basta; `ask_rag` lo legge e lo rimuove | Un client non poteva distinguere "ha risposto" da "si è astenuto": l'astensione, che è la funzione di sicurezza, non era leggibile a macchina | S | `status: "abstained"`, distinto da `no_results`/`no_graph_nodes` (lì il retrieval non trova nulla; qui trova qualcosa ed è la sintesi a dire che non risponde). Verificato dal vivo: domanda fuori corpus → `abstained`; domanda normale → `success`, marcatore mai nella risposta. 6 test in `tests/test_ask_abstention.py`, cache compresa |

**Conteggio:** 17 riscontri — 3 MANCANTE su capacità promesse (A3, A8, A9), 2 MANCANTE su
distribuzione (A14, A15), 9 FRAGILE, 2 SUPERFLUO, 1 FRAGILE latente.

Il conteggio è la fotografia della Run A e resta com'era: ciò che è successo dopo si legge
nelle righe. A2 e A5 ritirati, A6 e A18/A19/A20 chiusi in Run B, A3, A2b, A4 e A7 chiusi il
2026-09-03 — A3 con una **verifica di chiusura diversa** da quella che la riga proponeva, A2b
e A7 **più estesi** di quanto le righe avessero visto, A4 **in parte ritirato**: quattro dei
cinque casi che contavo come fallimenti erano la misura, non il difetto. Le indagini sono in
fondo al documento.

Tre righe erano rimaste stantie rispetto a run successive alla Run A, e sono state
riallineate il 2026-09-03: **A14 chiuso** (README/LICENSE/.env.example/Dockerfile esistono,
prodotti da L1/L2, mai riportati qui); **A18 chiuso** (la riga descriveva ancora il difetto
al presente: la correzione e il test erano già landati); **A15 declassato a PARZIALE** (il
gemello POSIX di `run_server.ps1` esiste, ma il pin CUDA di `torch` in `pyproject.toml`
resta senza marcatore di piattaforma — l'installazione nativa su macOS/ARM/CPU-only è
ancora bloccata, solo Docker la elude).

**A16 chiuso il 2026-09-03**: non con un'euristica sul testo dell'LLM (fragile per
costruzione), ma con un contratto — un token che il prompt impone e la route legge. Indagine
in fondo al documento.

**A17 chiuso il 2026-09-03**: correzione solo documentale, nella riga. Il budget guard è
codice reale e pronto, non ipotetico — solo spento perché oggi nessun purpose chiama Claude.
Non riattivato: non ci sarebbe nulla da proteggere, e attivarlo comunque avrebbe aggiunto
stato senza utilità.

**A13 chiuso il 2026-09-03**: verificato prima di rimuovere (zero `.pkl` ovunque nel
progetto), poi rimosso il ramo di lettura pickle end-to-end — non solo l'import, anche i
5 percorsi legacy, il fallback d'mtime in `api.deps` e il parametro `emit` diventato morto
con l'unico warning che lo usava.

**A12 chiuso il 2026-09-03**: 5 dei 6 TODO scaduti erano limiti permanenti travestiti da
piani, ridatati senza calendario. Il sesto (`_js_symbols`) era un piano vero con condizione
di chiusura verificabile — verificata, e soddisfatta da 53 giorni — ma rimuoverlo era una
decisione con posta in gioco reale (un fallback d'emergenza e il test che lo teneva vivo):
chiesto all'utente, non decisa da sola. Rimosso su sua indicazione; il test di equivalenza
sostituito, non solo cancellato, perché non regredisse la copertura di `code_index.ts`.

**A1 chiuso il 2026-09-03**: parte della premessa era già stantia (`top_k≤20` server-side
era già arrivato in una sessione precedente, mai registrato in questa riga) — e questo ha
spinto a rimisurare tutto invece di fidarsi. Bene così: dal vivo, `top_k=20` produce oggi
**104%** della finestra su una domanda ordinaria, non l'81% originale — il prompt di
sistema è cresciuto (A3, A16) da quando fu misurato. Indagine in fondo al documento.

**A9 chiuso il 2026-09-03**: il default di ruff avrebbe prodotto 380 riscontri di stile
discrezionale su un codebase mai linterato — selezionata esplicitamente una soglia di
correttezza (42 riscontri, tutti reali e tutti corretti), non il default del tool. Gate
verificato in entrambe le direzioni: una violazione deliberata blocca `scripts/ci.sh` e
`ci.ps1` con `exit 1` prima della suite.

**A8, premessa ritirata il 2026-09-03**: «0 skip con Qdrant attivo ⇒ nessun test tocca un
Qdrant reale» è un'inferenza rovesciata — con il servizio acceso quei test *girano*. I 3
test d'integrazione esistevano dal 2026-07-17, sei settimane prima della Run A. Ma sotto
c'era comunque un buco vero: la **delete-by-filter attraverso l'alias**, percorso caldo
dell'incrementale, non era verificata da nessuna parte. Ora sì. Indagine in fondo al
documento.

**A11 chiuso il 2026-09-04**: i due numeri della riga erano presi a `top_k=50`, che dal A1
il server rifiuta — non riproducibili. Rimisurato: **p50 24,1 s, p95 32,0 s**, e soprattutto
il retrieval è **0,50 s su 22,7 di media, il 2,2%**: il 97,8% dell'attesa è la generazione
LLM, quindi il tetto di qualunque ottimizzazione che non tocchi il modello è il 2,2%. Lo
strumento c'era già (`scripts/bench.py` calcola `p50`/`p95` per `/api/retrieve`) ma su
`/ask` girava su 3 query fisse riportando solo la media, e `eval/results/` non conteneva
nessun `bench_*.json`: la comparabilità fra run proteggeva un confronto mai avvenuto.
Streaming **non fatto** e dichiarato tale. Indagine in fondo al documento.

**A15 chiuso il 2026-09-04**: il difetto era reale, la sua descrizione no. «macOS/ARM/
CPU-only» nominava due casi che **non erano rotti** — Linux ARM64 sincronizzava (cu126 ha
le sue wheel `aarch64`) e una macchina CPU-only x86-64 pure (la build CUDA gira su CPU) —
e ne ometteva uno che lo era, Windows ARM. Misurato su sei piattaforme prima e dopo. Ora
l'indice CUDA ha un marcatore che trascrive l'elenco di wheel del lock, e **macOS Apple
Silicon sincronizza**; macOS Intel e Windows ARM restano impossibili perché PyTorch quelle
wheel non le pubblica affatto — limite a monte, dichiarato in README invece che subìto.
Indagine in fondo al documento.

**A6, riga riallineata il 2026-09-04**: era l'ultima ancora etichettata `FRAGILE` mentre la
Run B l'aveva chiusa, con tanto di sezione «A6 — chiuso» in fondo al documento. Ma
verificare invece di riscrivere l'etichetta ha trovato un difetto **dentro la chiusura**:
`observe_docs_git_divergence()` contava tutti i file tracciati sotto `docs/`, `.gitkeep`
compresi, e il report di eval dichiarava «16 documenti tracciati» contro i **14** davvero
indicizzati — la stessa trappola che la riga originale aveva già segnalato. Perimetro ora
allineato a `DOC_EXTS`. Indagine in fondo al documento.

---

## Ciò che NON è un problema (verificato, per non farlo ricontrollare alla Run B)

- **Integrità dell'indice**: 181 chunk, 181 vettori ColBERT, 181 punti Qdrant sull'alias
  `vibecraft_events` — delta 0. Nessun orfano, nessun chunk scoperto.
- **Astensione**: verificata dal vivo su una domanda fuori corpus. Il rifiuto è corretto,
  motivato e cita la regola. (Il difetto è solo la sua non-leggibilità a macchina — A16.)
- **Falsi positivi del router**: 0 su 55 casi del golden set, come dichiarato.
- **Suite di test**: 1253 test, 0 fallimenti, 0 skip.
- **Rilevamento del troncamento**: esiste ed è corretto (`core/llm.py:66-76`) — manca
  l'azione, non la diagnosi.

---

## Domande aperte — risolte per misura

### 1. I documenti non tracciati: residui o corpus di lavoro? → **Entrambi, e vanno separati**

Su disco 26 `.md`, di cui **11 tracciati** (i 13 path di `git ls-files` includono 2
`.gitkeep`) — cioè esattamente gli "11 documenti" che l'intestazione del golden set
dichiara come corpus di riferimento. I 15 non tracciati si dividono in tre gruppi:

| Gruppo | File | Verdetto |
|---|---|---|
| **Residui del dominio dismesso** | `glossario_entita.md` (491 righe, 98 occorrenze del dominio "eventi"), `matrice_permessi.md` (494, 98), `intent_synonym_mapping.md` (179, 52) | **Sono i tre nomi che il golden set elenca come "documenti poi rimossi".** Non sono stati rimossi: sono ancora indicizzati, **21 chunk su 181 = 11% del corpus** |
| Output della pipeline | `fe1-4`, `la1-2` `-canvas-review.md` | Legittimi: artefatti di run |
| Locali per progetto ospitante | `05_project_specs/spec_tech_*.md` (3) | Legittimi: `.gitignore` li esclude di proposito |

Restano da classificare a mano `change_log.md` e `architecture_decision_rationale.md`
(contaminazione lieve: 3 e 1 occorrenze). **Conseguenza operativa:** l'11% del corpus è
dominio morto che compete in ogni retrieval — e spiega perché la prova di astensione ha
recuperato `EVENTO`/`RICHIESTA`.

### 2. Chi usa `top_k` alto? → **Nessuno. Il contratto è più largo di ogni chiamante**

| Chiamante | `top_k` |
|---|---|
| Console (`dashboard.unified.html:385`) | default 5, `max="20"` — **solo lato client** |
| `scripts/bench.py:129` | non lo passa → default 5 |
| `agent_bridge.py` | non chiama `/ask` |
| `eval/run.py:112` | usa `/api/retrieve`, non `/ask` |

Il contratto server ammette 50, il consumo reale non supera 20. **A1 si chiude
restringendo il limite server**, non costruendo un potatore di contesto: il caso "serve k
alto" non esiste.

### 3. Il gate deve bloccare o avvisare? → **Bloccare, ma a k=2, e non ancora oggi**

Dai 77 punti di `history.jsonl`:

| Metrica | punti | range | σ | Distanza dalla soglia 0.90 |
|---|---|---|---|---|
| recall@10 (gate attuale) | 73 | 0.959–1.000 | 0.015 | **6σ — 61 gate su 61 passati** |
| recall@5 | 12 | 0.912–1.000 | 0.028 | ~0.4σ dal tetto |
| **recall@2** | 11 | 0.763–0.836 | 0.024 | lontana dai due estremi |
| recall@1 | 10 | 0.475–0.618 | 0.055 | varianza 3,7× recall@10 |

**recall@2 è il candidato giusto**: massimo segnale con varianza ancora contenuta.
recall@1 varia troppo (σ=0.055 su 10 punti) per una soglia fissa: bloccherebbe per rumore.
Ma **11 punti non bastano per fissare un pavimento**: la sequenza corretta è registrare
recall@1/@2 a ogni run per qualche settimana, poi rendere bloccante recall@2 a un
pavimento derivato dallo storico (ordine di grandezza: media − 2σ ≈ 0.74), tenendo
recall@10 come segnale advisory. Nel frattempo il gate resta com'è: **non protegge, ma
non danneggia.**

### 4. Corpus di riferimento per l'eval → **discende dalla risposta 1**

Gli 11 documenti tracciati sono già il riferimento dichiarato. Serve solo che l'indice
misurato coincida con essi, oppure che la differenza sia registrata nel report di eval.

---

## Da decidere prima della Run C (distribuzione)

Licenza · matrice dei device supportati · Ollama impacchettato o prerequisito · corpus di
esempio da spedire nel repo.

---
---

# Run B — piano

Ordinato per impatto ÷ sforzo. **Ma l'ordine ha un vincolo che viene prima del rapporto:**
B1 cambia i numeri di A3, A4 e A5. Farlo per secondo significa misurare due volte e
decidere soglie su dati che stanno per cambiare. Quindi B1 è primo non perché sia il più
grave, ma perché **tutto il resto lo presuppone**.

## I primi cinque

### B1 — Separare il corpus vivo dal dominio dismesso *(chiude A6, sblocca A3/A4/A5)*

**Causa:** tre documenti che la storia del progetto dà per rimossi sono ancora indicizzati
e valgono l'11% dei chunk. Ogni retrieval li vede; ogni metrica li include.

**Intervento minimo:** spostare `glossario_entita.md`, `matrice_permessi.md`,
`intent_synonym_mapping.md` fuori da `docs/`, poi full rebuild + promote.

> ⚠️ **Non sono tracciati da git: cancellarli è irreversibile.** Vanno *spostati* in
> `docs.local-backup-<timestamp>/` — la convenzione esiste già a root — mai `rm`.
> Prima di spostarli va deciso a mano il destino di `change_log.md` e
> `architecture_decision_rationale.md` (contaminazione lieve: 3 e 1 occorrenze).

**File toccati:** nessun file di codice. `docs/` e l'indice.
**Verifica:** dopo il rebuild, `chunks` scende da 181 a ~160 e `eval/run.py` gira senza che
nessun caso attinga ai tre documenti. Le metriche vanno **ri-registrate**: quelle di oggi
non sono confrontabili con quelle di domani, e va scritto nel report.

### B2 — Portare il limite di `top_k` dal client al server *(chiude A1)*

**Causa:** il contratto server ammette 50, ogni chiamante reale sta ≤ 20, e l'unico argine
è `max="20"` in un attributo HTML.

**Intervento minimo:** `api/models.py:9` — `top_k: int = Field(default=5, ge=1, le=20)`.
Una riga. Non serve un potatore di contesto: la verifica ha stabilito che il caso d'uso
"k alto" non esiste.

**File toccati:** `api/models.py` (+ un test).
**Test che oggi fallirebbe:** `POST /ask` con `top_k=50` deve rispondere `422`, non `200`.
Oggi risponde `200` con un prompt da ~31k token su una finestra da 16k.

**Ceiling dichiarato:** resta il caso "corpus con sezioni più piene": a parità di k il
contesto cresce. Il limite a 20 lascia il 19% di margine misurato *su questo corpus*. Se
i documenti si allungano, la protezione giusta diventa il budget di token — ma è lavoro da
fare quando la misura lo mostra, non ora.

### B3 — Registrare le metriche che discriminano *(prepara A2, misura A3)*

**Causa:** il gate vive a k=10 dove σ=0.015 e 61 valutazioni su 61 sono passate. I k bassi
hanno segnale ma solo 10-12 punti storici: **non c'è ancora abbastanza storia per fissare
un pavimento onesto.**

**Intervento minimo:** far sì che ogni run scriva `recall@1`, `recall@2` **e la recall@1
del sottoinsieme avversariale** in `history.jsonl`. Nessun cambio di soglia adesso.

**File toccati:** `eval/run.py`, `core/eval_history.py`.
**Verifica:** dopo N run, `history.jsonl` ha le tre serie complete.
**Poi** (non ora): recall@2 diventa bloccante a un pavimento derivato dallo storico
— ordine di grandezza media − 2σ ≈ 0.74 — e recall@10 scende ad advisory.

### B4 — Correggere l'harness multihop sul ramo grafo *(chiude A5)*

**Causa:** `quali documenti esistono nel corpus?` è segnato fallito da entrambi i rami,
ma dal vivo il grafo risponde correttamente con tutti i 26 documenti. Lo strumento
sbaglia, non il sistema.

**File toccati:** `eval/run_multihop.py` (valutazione del ramo B).
**Test che oggi fallirebbe:** il caso risulta superato senza toccare il codice di
produzione. Va fatto **dopo B1**, perché il numero atteso di documenti cambia.

### B5 — Riconciliare `SECURITY_SURFACE.md` con le route reali *(chiude A10)*

**Causa:** il documento è fermo al 2026-08-05, `api/` è cambiata fino al 2026-08-24. Per
un file che descrive la superficie d'attacco, "probabilmente aggiornato" non è uno stato
accettabile.

**Intervento minimo:** confronto riga-per-riga fra i 57 decoratori route e la tabella.
**Verifica:** ogni route del codice ha una riga, ogni riga una route.

## Il resto, in ordine

| # | Cosa | Chiude | Sforzo |
|---|---|---|---|
| B6 | Un test di integrazione contro Qdrant vero, con skip esplicito quando assente; correggere il commento ora falso in `ci.yml` | A8 | M |
| B7 | `ruff` in CI (solo il linter: `mypy` su 37.5k righe non annotate è un progetto a sé) | A9 | S |
| B8 | Infografica: dire che il budget guard è opzionale e **spento**, o attivarlo | A17 | S |
| B9 | Stato distinto per la risposta astenuta, così è leggibile a macchina | A16 | S |
| B10 | Test sul ramo misto di `rank_by_authority` che fissa il comportamento con `colbert_score=None` | A7 | S |
| B11 | **Cancellare:** `_js_symbols` + default regex (TODO scaduto da 51 giorni), ramo di lettura pickle in `artifacts.py`, i 6 TODO datati | A12, A13 | S |
| B12 | Latenza: misurare p95 e decidere se serve feedback incrementale | A11 | M |

A14 e A15 (distribuzione e portabilità) non sono qui: sono la **Run C**.

## Cosa NON fare

- **Non** costruire un potatore di token per A1: la misura dice che non serve (B2).
- **Non** ritarare l'autorità sul golden set attuale: è satura a k≥5 e sta per cambiare
  corpus (B1). Ritarare adesso significa inseguire rumore — è l'errore che l'ADR 0002
  documenta già come "il rovescio del metodo".
- **Non** toccare le soglie del gate finché B3 non ha prodotto storia (≥ 20 punti).
- **Non** spezzare `core/indexing.py` (2.264 righe): è grande, ma nessuna misura lo indica
  come problema. Grande ≠ sbagliato.

---
---

# Run B — esecuzione (2026-09-01)

## B1 — Corpus separato dal dominio dismesso ✅

Spostati in `docs.local-backup-20260901T121519/` (mai `rm`: non erano tracciati da git,
cancellarli sarebbe stato irreversibile): `glossario_entita.md`, `matrice_permessi.md`,
`intent_synonym_mapping.md`. Nessun file tracciato toccato (`git status --porcelain docs`
vuoto).

**Decisi a mano, e TENUTI** — con un difetto ciascuno da correggere separatamente:
- `architecture_decision_rationale.md`: §2 e §3 sono la motivazione architetturale corrente
  (Modular Monolith; "no agenti LLM", coerente con ADR 0001) ed è la fonte unica dichiarata
  dei tre `spec_tech_*`. Stantii solo §1 (perimetro "eventi aziendali") e il campo `project:`.
- `change_log.md`: 3 righe contaminate su 128; §1/§2/§4 sono regole di governance generiche.
  Rimanda a `docs/02_specs_normative/spec_notifications_2.4.md`, che **non esiste**.

Full rebuild + promozione: `CURRENT → v20260901T101536`, alias Qdrant scambiato,
collection orfana raccolta. Chunk **181 → 160** (−21, esattamente i chunk dei tre rimossi).

**Effetto misurato** (stesso golden set, 55 casi, stato pulito):

| Metrica | Prima | Dopo | Δ |
|---|---|---|---|
| recall@1 | 61.8% | **63.6%** | +1.8 |
| recall@2 | 83.6% | **87.3%** | +3.7 |
| recall@5 | 98.2% | 98.2% | — |
| MRR | 0.773 | **0.791** | +0.018 |
| source_in_top3 | 92.7% | **94.5%** | +1.8 |
| multihop: recall media A | 0.854 | **0.896** | +0.042 |
| multihop: casi riusciti | 9/14 | **10/14** | +1 |
| **avversariale recall@1** | 0.0% | **0.0%** | **invariato** |

L'ultima riga è la più informativa: il fallimento avversariale **non era rumore di
dominio**. A3 resta in piedi da solo e va indagato per conto suo.

## B2 — Limite di `top_k` dal client al server ✅

`api/models.py` — `le=50` → `le=20`, con la motivazione (vincolo di correttezza, non di
carico) e i numeri misurati nel commento. Nuovo `tests/test_ask_limits.py`: 3 test, verdi.
Il test che oggi sarebbe fallito: `AskQuery(top_k=50)` deve essere rifiutata.

## B3 — Riscritto dopo una mia correzione

**Il piano originale era basato su un riscontro sbagliato (A2, ritirato).** Il gate NON è
a k=10/0.90: `rag_config.yaml` lo tiene a `k: 2`, `min_recall: 0.75`, `blocking: true`, e
il commento documenta la migrazione k=10 → k=5 → k=2, ogni passo innescato dall'alert di
saturazione del progetto. Il rebuild di oggi l'ha confermato dal vivo.

Resta da fare, molto più stretto (A2b): `latest_recall`, `compute_trend` e
`detect_regression` (`core/eval_history.py:73,79,95`) hanno ancora `key="recall@10"` come
default, e `/api/health` espone `last_recall_at_10` come numero in evidenza. Il gate è
difeso, la deriva lenta no.

> *Chiuso il 2026-09-03, e «molto più stretto» era sbagliato: cercando i consumatori sono
> saltati fuori anche le due pagine, il guardrail di `eval.run` e — la peggiore — i due
> script notturni, che girano senza `--k` e quindi asserivano su una metrica satura. Indagine
> in fondo al documento.*

## B4 — Sospeso, in attesa di A18

Il caso `quali documenti esistono nel corpus?` va rimisurato: dopo B1 il numero atteso di
documenti è cambiato. Ma prima va chiuso A18, altrimenti si taratura l'harness su misure
potenzialmente miste.

## B5 — Eseguito: nessuna azione necessaria ✅

Riconciliazione riga-per-riga: `SECURITY_SURFACE.md` è **allineato**. Le 57 route hanno
tutte una riga; le 7 apparentemente mancanti sono auto-route di FastAPI e il mount statico,
contati esplicitamente a `:33`. **A10 ritirato.**

## Trovato durante l'esecuzione: A18

`GET /api/retrieve` non ricarica lo snapshot. È l'endpoint su cui gira *tutto* l'harness di
eval. È il riscontro più importante emerso dall'esecuzione, ed è di categoria peggiore degli
altri: non sbaglia il sistema, sbaglia **lo strumento con cui si decide** se il sistema è
migliorato.

**Correzione a me stesso.** Avevo dichiarato invalida la prima misura post-B1 e l'avevo
rifatta. Le due misure sono risultate identiche in ogni metrica, e il controllo spiega
perché: i 160 chunk nuovi sono un **sottoinsieme stretto** dei 181 vecchi (0 chunk_id non
coperti), quindi il sidecar stantìo copriva già tutto ciò che la collection nuova poteva
restituire. La misura era corretta — **per fortuna, non per costruzione**. Il difetto resta
intero, ma il suo profilo di rischio è l'opposto di come l'avevo descritto: è benigno sulle
cancellazioni e mordente sulle aggiunte, dove i chunk_id nuovi mancano dal sidecar e
`colbert_maxsim` restituisce `None` — l'input che innesca A7.

## Stato del backlog

| | |
|---|---|
| Chiusi | B1, B2, B5 |
| Ritirati (riscontro errato) | A2, A10 |
| Nuovi | A18 (prioritario), A2b |
| Prossimi | A18 → B4 → A2b → B6…B12 |

## B4 — Chiuso senza modifiche: il fallimento è un vero positivo

Sbloccato A18, il caso `quali documenti esistono nel corpus?` è stato riesaminato.
`eval/golden_multihop.yaml:90-96` dichiara `count: 11` (la baseline committata) e quattro
nodi attesi: **i nodi ci sono tutti, l'unico scarto è il conteggio** (23 dopo B1, contro 11).

Il primo istinto era togliere l'asserzione sul `count` per far tornare verde il caso. È la
cosa sbagliata: quell'asserzione è **l'unico rilevatore di divergenza del corpus che il
progetto possiede**, e ha appena fatto il suo lavoro. Toglierla sarebbe staccare il
rilevatore di fumo perché c'è fumo.

Nota di merito al golden set: la sua nota di progettazione dichiara il `count` "solo dove è
semanticamente stabile (l'enumerazione dei documenti)". La misura mostra che quella
stabilità vale rispetto alla **baseline committata**, non rispetto a `docs/` su disco — che
per policy contiene anche documenti di lavoro non tracciati. L'asserzione non è sbagliata:
è più esigente di quanto la policy di `docs/` permetta di soddisfare.

**Resta aperto in A6**, e la scelta è di merito, non tecnica: o l'eval gira su un corpus
ricostruito dai soli file tracciati (numeri riproducibili da chiunque, CI compresa), oppure
la divergenza va dichiarata dentro il report di eval. Non è una decisione da prendere di
soppiatto in un harness.

## A18 — Chiuso ✅

`api/routes_retrieval.py` — `maybe_reload_graph()` aggiunto a `api_retrieve`, con la
motivazione nel docstring. Nuovo `tests/test_retrieve_reload.py`.

Il test è stato **verificato per costruzione**: disattivando la sola chiamata appena
aggiunta fallisce con `assert 0 == 1`, ripristinandola torna verde.

Nota emersa: il tetto `k ≤ 50` di `/api/retrieve` è stato **lasciato com'è**, a differenza
di `/ask` (B2). Non è un'incoerenza: quella route non costruisce alcun prompt, quindi non
ha una finestra di contesto da sfondare — il costo di un k alto è solo tempo di ranking.
Il vincolo di B2 è di correttezza dell'LLM, e si applica solo dove c'è un LLM.

---

## Bilancio della Run B

**Chiusi:** B1 (corpus), B2 (tetto `top_k`), B5 (sicurezza: già allineata), A18 (reload).
**Chiuso senza modifiche:** B4 — il fallimento era un vero positivo.
**Ritirati perché sbagliati o imprecisi:** A2, A5, A10.

Tre riscontri su diciotto erano sbagliati, ed è la parte più istruttiva di questo audit:
tutti e tre erano **casi in cui il progetto aveva già ragione** e io avevo letto un
indizio al posto di una prova — i default del codice invece della configurazione attiva
(A2), lo scarto fra due date invece del contenuto (A10), una risposta plausibile invece
dell'asserzione dichiarata (A5). Il difetto vero trovato nell'esecuzione (A18) è della
stessa famiglia, ma dal lato della macchina: **uno strumento che misura uno stato che
nessuno vede, e non lo dice.**

**Metriche a fine Run B** (55 casi, stato pulito, `v20260901T101536`, 160 chunk):
recall@1 63.6% · recall@2 87.3% · recall@5 98.2% · MRR 0.791 · multihop 10/14 (A 0.896).
Suite: **1257 test verdi, 0 fallimenti, 0 skip** (1253 di partenza + 4 nuovi). Avversariale recall@1 **0.0%**, invariato — A3 resta il
primo problema di qualità aperto, e non dipendeva dal rumore di dominio.

---
---

# A3 — perché l'avversariale non è mai primo

**Domanda:** sui 5 casi marcati `adversarial: true`, recall@1 = 0.0%, invariato anche dopo
la pulizia del corpus di B1. Perché?

## 1. Lo 0.0% di partenza è per costruzione, non è una regressione

L'intestazione del golden set (`eval/golden_set.yaml:299-302`) dice che i dieci casi
originali furono **scelti** perché il distrattore precede l'atteso, e ne elenca i ranghi
verificati: `1→2, 1→2, 1→2, 1→2, 2→3, 1→3, 1→5, 3→5, 1→2, 1→3`. Un caso avversariale che
partisse a rango 1 non sarebbe avversariale. Quindi `recall@1 = 0.0%` **è la condizione
iniziale che ADR 0002 doveva ribaltare**, e la misura dice che non l'ha ribaltata.

## 2. α = 0.1 è sotto la soglia che servirebbe — e fu calibrato dove non si vede

Il moltiplicatore è `(1-α) + α·peso`. Con α = 0.1 la forbice fra un documento a peso 0.3 e
uno a 1.0 vale **7,5%**: l'autorità può correggere solo divari ColBERT più piccoli di così.

α minimo per portare l'atteso a rango 1, calcolato con la funzione di produzione
`rank_by_authority` sui candidati reali:

| Caso | Distrattore | α necessario |
|---|---|---|
| 1 — bump di versione | `graph_rag_ingestion_strategy` (METHODOLOGY 0.50) | **0.30** |
| 2 — caratteri per chunk | idem | **0.45** |
| 3 — ordine dei tagli | idem | **0.25** |
| 4 — motivazione a un LLM remoto | `architecture_decision_rationale` (NORMS 0.85) | **0.25** |
| 5 — palette colori | `fe1-canvas-review` (nessun frontmatter, 0.30) | **nessuno ≤ 1.0** |

`rag_config.yaml:9` dice che `boost_alpha` fu portato da 0.4 a **0.1** perché *"alzarono
recall@10 held-out da 0.914 a 0.971"*, e le ricalibrazioni successive girarono a k=5 e k=10,
concludendo ogni volta `NON_APPLICARE, guadagno +0.000`. Il file stesso avverte:
*"Ricalibrare SEMPRE a un k dove la metrica non sia satura"* (`:45`). **Nessuna calibrazione
è mai girata a k=1** — l'unico k che misura ciò che questi casi testano. α è stato scelto
ottimizzando una metrica cieca all'ordinamento in prima posizione.

## 3. Ma alzare α NON è la correzione — provato

Calibrazione eseguita oggi a k=1, 5-fold, 5 seed (`eval/calibrate_authority.py --k 1`):

```
DEFAULT   alpha=0.1  → recall@1 in-sample 0.636
GRIGLIA   alpha=0.3  → recall@1 in-sample 0.655   (ottimista)
CROSS-VALIDATION — l'unico numero onesto:
   default   held-out = 0.636
   calibrato held-out = 0.607
   guadagno = -0.029   su TUTTI E CINQUE i seed (-0.018 -0.036 -0.055 -0.018 -0.018)
AVVERSARIALE in-sample: 0.000 (default) → 0.600 (griglia)
```

Alzare α compra 3 casi avversariali su 5 e ne perde di più sugli altri 50. Il guadagno
in-sample è sovradattamento: fuori campione è una **perdita netta e coerente su ogni seed**.
Il verdetto dello strumento — *"i pesi a mano REGGONO, nessuna modifica consigliata"* — vale
anche a k=1.

## 4. La causa vera: il 70% del deficit non è a livello di documento

Decomposizione dei 55 casi contro il ranking di produzione:

| | |
|---|---|
| Atteso già a rango 1 | 35 |
| Atteso **non** a rango 1 | **20** |
| → bloccato da una **sezione dello stesso documento** | **14 (70%)** |
| → bloccato da un altro documento | 6 |
| Atteso fuori dai top-10 | 0 |

**L'autorità è una proprietà del documento, ma l'unità di retrieval è la sezione.** Quando
il concorrente è una sezione sorella, i pesi sono identici e il moltiplicatore
`(1-α)+α·peso` **si semplifica**: nessun α, per costruzione, può separarle. Il 70% del
deficit di rango 1 vive esattamente dove l'unica leva del progetto non arriva.

Il caso 5 è il ritratto della tenaglia:

| α | Chi vince | Rango dell'atteso |
|---|---|---|
| ≤ 0.2 | `fe1-canvas-review` (cb 0.6115, peso 0.30) — vince sul ColBERT | 3 |
| 0.25–0.6 | `ui_ux_brand_directives § 5` — **sezione sorella**, peso identico 0.80 | 2 |
| ≥ 0.8 | `safeguards_security` (peso 0.98) — vince sulla sola autorità, ColBERT più basso | 5–6 |

## 5. Il meccanismo, con un nome preciso

Quali sezioni bloccano l'atteso dentro il suo stesso documento:

```
 7x  "Scenari Comportamentali BDD (Gherkin)"   (numerata 4./5./6. secondo il documento)
 2x  "Sezione 0 — Contratto di Istanziazione"
 2x  "2. Direttive Vincolanti"
 ... coda di casi singoli
```

**Metà dei blocchi fra sezioni sorelle è una sola classe di sezione.** I blocchi
GIVEN/WHEN/THEN sono la **riformulazione lessicale della regola che li precede**: stesso
vocabolario, più denso di parole chiave, spesso più lungo. Il MaxSim di ColBERT premia
esattamente questo. La sezione che *illustra* la regola batte la sezione che *la stabilisce*.

Vale la pena notare che è lo stesso difetto di ADR 0002 — una fonte che spiega batte la
fonte che vincola — ma sceso di un livello: là fra documenti, qui **fra sezioni dello stesso
documento**. ADR 0002 ha risolto il livello che vedeva.

## 6. La decisione: la 3 era già la posizione del progetto, ed è vera a metà

La strada 3 non era un'ipotesi da valutare: era **già scritta** in `rag_config.yaml:218-222`,
come la ragione per cui `boost_alpha` resta 0.1.

> *«/ask inietta nel contesto fino a `retrieval.governed_max_chunks: 8` sezioni e l'LLM le
> legge TUTTE: ciò che conta è se la fonte giusta ENTRA nella finestra, non a che rango.»*

Verificato che la premessa regge: sui 4 casi avversariali l'atteso sta a rango 2, 2, 2, 3, e
`source_in_top3` avversariale vale **100%**. La fonte giusta entra sempre, e con lei entra
sempre anche il distrattore. Restava da misurare la conclusione — *quindi il rango non
conta* — che nessuno aveva mai messo alla prova, perché nessuna metrica guarda la risposta.

Misurata, il 2026-09-03, chiedendo a `/ask` i 4 casi e leggendo **a chi la risposta
attribuisce il vincolo**:

| | Rango atteso | Prima | Dopo |
|---|---|---|---|
| 1 — bump di versione | 2 | ✅ regola dalla spec, distrattore come razionale | ✅ |
| 2 — caratteri per chunk | 2 | ❌ **severità attribuita al METHODOLOGY**, con la spec declassata a «conferma» | ✅ «Fonte Primaria» la spec, «Fonte Secondaria (Razionale)» il distrattore |
| 3 — ordine dei tagli | 2 | ✅ `[REGOLA-VAL-04]` citata dalla spec | ✅ |
| 4 — palette colori | 3 | ❌ **risposta impostata sul distrattore**: apre da una canvas-review storica e conclude «NON ESAUDITA» | ✅ apre dalla norma e dichiara la divergenza risolvendola per classe |

**Entrare nella finestra è necessario, non sufficiente.** Il modello le legge tutte — ma non
le *pesa*, perché non aveva alcun modo di pesarle: l'intestazione era
`--- doc § sezione ---` e basta. L'autorità veniva calcolata, usata per riordinare, e poi
**buttata via al confine del prompt**. Dentro la finestra il modello ri-ordinava a naso, per
prosa: e la prosa che spiega è più densa di parole chiave di quella che vincola. È il
difetto di ADR 0002, sopravvissuto un livello più in là di dove ADR 0002 guardava.

Le strade 1 e 2 restano non intraprese, e ora si capisce perché non sono la prima cosa da
fare: agiscono sul **rango**, che non era il problema.

## 7. La correzione

Due funzioni pure in `core/retrieval.py` (`source_label`, `authority_scale`) e il loro uso in
`/ask`. Nessuna modifica al ranking: `rank_by_authority` e `boost_alpha` sono intatti, e la
recall del golden set è **identica** prima e dopo (r@1 63.6%, r@2 87.3%, MRR 0.791).

1. **Ogni blocco del contesto porta la classe dichiarata dalla sua fonte** —
   `--- spec.md § 2 [REQUIREMENTS] ---`, `--- fe1-canvas-review.md § … [SENZA CLASSE] ---`.
   È la convenzione che `_serialize_chunks` usava già per canvas/propose: `/ask` era l'unico
   consumatore a nasconderla, cioè l'unico letto da un umano. Lo `status` compare solo se
   archiviato — `ENFORCED` su ogni blocco sarebbe rumore.
2. **`[CLASSE-FONTI]` enuncia la graduatoria** delle sole classi presenti in quel contesto,
   coi pesi che il ranking ha già usato: *«NORMS (0.80) > METHODOLOGY (0.50) > SENZA CLASSE
   (0.30) … un vincolo va attribuito alla fonte PIÙ autorevole che lo enuncia; una fonte meno
   autorevole può motivarlo, mai esserne la fonte»*. Senza la scala, `[METHODOLOGY]` sarebbe
   una parola qualsiasi.

La regola segue la disciplina di `[PRECEDENZA-FONTI]`: **compare solo quando discrimina**
(`authority_scale` restituisce `[]` se le fonti recuperate stanno tutte sullo stesso
livello). Una regola inerte insegna al modello a ignorarla. E viene enunciata **prima** della
precedenza dichiarata, che è l'eccezione specifica su due documenti precisi.

Effetto collaterale misurato: le risposte si **accorciano** — caso 4 da 10.724 a 5.355
caratteri, caso 2 da 4.349 a 2.664. Il modello smette di trattare ogni blocco come
ugualmente citabile.

**I limiti della misura, per intero.** 4 casi, un solo modello (`qwen3.5:9b`, temperatura
0.1), 2 esecuzioni per condizione — non 30. Il giudizio su «a chi è attribuito il vincolo»
l'ho dato leggendo le risposte, non una metrica. I due difetti si sono riprodotti in
entrambe le esecuzioni pre-correzione e sono spariti in entrambe le post: è un segnale
solido, non un intervallo di confidenza.

## 8. Cosa resta aperto dopo A3

- **`recall@1` avversariale resta 0.0%, ed è corretto che resti.** Misura la condizione
  iniziale per cui quei casi furono scelti. Non è la metrica di questo sistema: la metrica
  vera è a chi la risposta attribuisce il vincolo, e **non esiste**. Nessun numero nel
  progetto si sarebbe mosso di un decimale per questa correzione — la recall è identica.
  Automatizzarla costa una chiamata LLM per caso e un giudice: non è stato fatto.
  **PROTOTIPATA il 2026-09-05** (S6, N3), e il prototipo ha trovato prima di tutto un difetto
  di questa sezione: **la tabella del §6 non è più riproducibile**. Il giudice automatico è
  ripetibile (3 giudizi identici sulla stessa risposta) e concorda con l'umano su 3 casi su 4;
  sul quarto — palette colori — dissente, e leggendo la risposta ha ragione lui. In tre
  esecuzioni indipendenti la risposta di oggi apre con «il contesto **non riporta** un
  controllo … già eseguito», cita il distrattore come prova dell'assenza e **non attribuisce
  il vincolo a nessuna fonte**: il «Dopo ✅» registrato il 2026-09-03 non si riproduce, perché
  fra le due date il corpus e l'indice sono cambiati (S5, R7, R8). Il verdetto di questa
  sezione **non è ritirato** — nessuna misura di oggi lo contraddice sui casi 1-3, e la
  correzione del prompt è tuttora in vigore — ma il suo fondamento, quattro risposte lette a
  mano, è **scaduto e non ricostruibile**: le risposte non furono archiviate. È il motivo per
  cui N3 va scritto, misurato su se stesso.
- **La strada 1** (peso di sezione) resta la candidata naturale se un giorno il rango
  dovesse contare davvero — per esempio con `governed_max_chunks` molto più basso.
- ~~**Il prompt di sistema ORDINA di citare vincoli SQL** (`«DEVI citare … i vincoli SQL (es.
  SELECT … FOR UPDATE)»`) su un corpus che di SQL non parla: nei casi 3 e 4 il modello ne ha
  inventati, dichiarandoli ipotetici. È un invito a inventare, scritto nel prompt.~~
  **CHIUSO il 2026-09-04** (R1), con **una premessa da correggere**: il corpus di SQL *parla*.
  `docs/00_meta_governance/safeguards_security.md` enuncia `SELECT ... FOR UPDATE` nel testo
  di `[SAFEGUARD-TXN-01]`, in un blocco di codice, nel requisito sul motore di database e
  nella tabella di sintesi. Il difetto non era l'assenza di SQL dal corpus: era che l'ordine
  di citarlo valeva per **ogni** domanda, comprese quelle il cui contesto recuperato non ne
  contiene — e lì il modello lo fabbricava.

  **Riprodotto** contro `/ask` (Ollama `qwen3.5:9b`, indice `v20260901T132525`), 2 esecuzioni
  per caso, cache disattivata: **3 risposte su 4** inventano. Il caso 3 (*ordine dei tagli*)
  apre una sezione *«Vincolo SQL/Logica associata (implicito nel contesto dei blocchi
  atomici)»* e ci trascina `[SAFEGUARD-TXN-02]` — l'atomicità transazionale, in una risposta
  sul chunking. Il caso 4 (*palette colori*) attribuisce il controllo a `[SAFEGUARD-UI-01]` e
  `[SAFEGUARD-PALETTE-01]`, **zero occorrenze nel corpus**. L'SQL inventato non era dunque né
  l'unica invenzione né la più frequente: la forma «DEVI citare X» fabbricava anche codici di
  safeguard, sempre marcandoli «implicito» o «ipotetico» — che è come il modello obbedisce a
  un ordine che non può soddisfare.

  **Correzione**: `[CITAZIONE-VERIFICABILE]` in `core/retrieval.build_ask_prompt`, che
  pretende di citare *testualmente ciò che il contesto riporta* e **vieta** di introdurre
  codici, identificatori o vincoli tecnici assenti dal contesto, «nemmeno come esempio,
  ipotesi o vincolo implicito». È la clausola di divieto a portare il peso: togliere la sola
  parola «SQL» avrebbe lasciato intatta la forma.

  **Verifica**, stesse due domande, 2 esecuzioni ciascuna: **0 invenzioni**, e i codici veri
  restano — caso 3 cita `[REGOLA-VAL-04]` dalla spec col METHODOLOGY come razionale, caso 4
  `[REGOLA-UI-01]` e `[REGOLA-UI-03]` dalla norma. Controllo sul verso opposto («come gestire
  il lock transazionale su una risorsa contesa», dove l'SQL nel contesto c'è davvero): la
  risposta cita `[SAFEGUARD-TXN-01/04/05]` e il `SELECT ... FOR UPDATE` reale. La regola
  sopprime l'invenzione, non la citazione. Costo: prompt fisso da ~804 a ~954 token,
  dichiarato e sorvegliato dal canarino di A1/R3 aggiunto lo stesso giorno.
---
---

# A6 — corpus e riproducibilità

**Domanda:** l'indice contiene più documenti di quelli tracciati. Quanto conta davvero?

## Il difetto non è la divergenza, è che la misura si capovolge

Dopo B1: `docs/` ha 23 `.md`, di cui **11 tracciati** — esattamente la baseline che il
golden set dichiara come corpus di riferimento.

Verificato: **tutti e 55 gli attesi vivono in documenti tracciati** (il commit `b1ef300`
aveva già riallineato i matcher). Ma **nessuno dei tre distrattori lo era**:

| Distrattore | Casi | Era tracciato |
|---|---|---|
| `04_knowledge_informative/graph_rag_ingestion_strategy.md` | 1, 2, 3 | no |
| `01_architecture_norms/architecture_decision_rationale.md` | 4 | no |
| `03_changes_historical/fe1-canvas-review.md` | 5 | no |

Simulando il corpus che vede la CI (solo i tracciati), escludendo dai candidati i chunk dei
documenti non tracciati e riordinando con `rank_by_authority`:

| | qui (23 doc) | CI (11 doc) |
|---|---|---|
| recall@1, tutti i 55 casi | 63% | 70% |
| **recall@1, sottoinsieme avversariale** | **0%** | **80%** |

L'80% non è un sistema che funziona meglio: è ciò che si misura quando i distrattori non
esistono e i casi passano a vuoto. **Un distrattore assente non fa fallire il caso: lo rende
decorativo**, che è peggio, perché il numero sale e sembra una buona notizia.

Il numero che ADR 0002 esiste per muovere legge dunque **0% su questa macchina e 80% in CI**.
Una metrica che si capovolge col checkout non misura il sistema, misura il checkout. È anche
la ragione per cui l'opzione che sembrava più pulita — far girare l'eval sui soli file
tracciati — era la peggiore: avrebbe reso l'avversariale decorativo *ovunque*.

## Cosa è stato fatto

**I tre distrattori sono entrati nella baseline tracciata** (`git add -f`: `docs/*` è
ignorata di proposito). Non sono file locali incidentali: sono **parte dello strumento di
misura**, esattamente come gli attesi.

`architecture_decision_rationale.md` è stato corretto prima di entrare: §1 e il campo
`project:` descrivevano ancora il dominio dismesso ("Portale richieste e prenotazioni eventi
aziendali"). L'argomento del documento — per un perimetro di questa **scala** microservizi e
agenti LLM non si giustificano — non dipende dal dominio, quindi §1 ora dichiara la scala e
rimanda a `docs/05_project_specs/` per il perimetro concreto. §2 e §3 invariati.

**Il distrattore è ora un campo dichiarato**, non un commento: `distractor:` su ognuno dei 5
casi, e `test_casi_avversariali_hanno_matcher_validi` ne verifica l'esistenza nel corpus
esattamente come già faceva per l'atteso. Era la lacuna che il commit `b1ef300` aveva
lasciato annotata. Verificato per costruzione: puntando il campo a un file inesistente il
test fallisce, ripristinandolo torna verde.

## Il caso 4 è indebolito, ed è colpa di B1

Il distrattore progettato del caso 4 era `intent_synonym_mapping.md` (METHODOLOGY, peso
0.50) — uno dei tre documenti che **B1 ha rimosso** perché apparteneva al dominio dismesso.
Il concorrente a rango 1 è ora `architecture_decision_rationale.md`, che pesa 0.85 contro lo
0.98 dell'atteso: **il contrasto di autorità è passato da 0.50-vs-0.98 a 0.85-vs-0.98**, da
largo a stretto.

Il caso resta avversariale ma misura meno di quanto fu progettato per misurare. È annotato
nel golden set: va riscritto con un distrattore a bassa autorità che esista nella baseline,
non lasciato così credendo che eserciti ancora il contrasto originale. **Aperto.**

## Cosa resta aperto di A6

Portare i distrattori nella baseline chiude la parte che rendeva la misura *inversa*. Non
chiude la riproducibilità in senso pieno: restano 9 documenti non tracciati (6 output di
pipeline, 3 spec locali del progetto ospitante) che l'indice contiene e la CI no, quindi
recall@1 resta diverso fra le due macchine. La differenza è ora fatta di documenti che
**nessun caso del golden set nomina**, né come atteso né come distrattore — è rumore di
fondo, non più strumento mancante.

Resta valido il criterio di chiusura: o un clone pulito riproduce le metriche dichiarate,
oppure il report di eval dichiara su quale corpus ha misurato.


---
---

# Chiusura: le tre pendenze e A6

## 1. Il caso 4 non è stato riscritto: è stato declassato

Il distrattore progettato era `intent_synonym_mapping.md` (peso 0.50), rimosso da B1.
Per ricostruire il contrasto serviva un altro documento a bassa autorità che parlasse di
LLM e dati personali. **Non esiste.** Misurato sulla baseline tracciata: sotto peso 0.5 ci
sono due soli documenti — `fe1-canvas-review.md` (0.30) e `graph_rag_ingestion_strategy.md`
(0.50) — e **nessuno dei due nomina LLM, privacy o dati personali** (0 occorrenze).

Quindi il marcatore `adversarial` è stato **tolto**, con lo stesso criterio che il progetto
applicò il 2026-08-25 al caso della tracciabilità, per la ragione opposta: quello smise di
essere avversariale perché il sistema lo superava, questo perché non esercita più il
contrasto che dichiara. Ora competerebbe 0.85 contro 0.98 — "due fonti entrambe autorevoli
si contendono il primo posto", che non è ciò che S5 misura e che i pesi di classe di ADR
0002 quasi non governano.

Il sottoinsieme scende a **4 casi contro 2 soli distrattori**. È poco, ed è annotato come
tale nel golden set. Restituirgli ampiezza richiede un documento informativo a bassa
autorità su un tema nuovo: è una decisione sul **corpus**, non sul golden set. **Aperto.**

## 2. A18 verificato end-to-end, non più solo a unit test

La verifica precedente era una mia affermazione sbagliata: il server girava da prima della
correzione e uvicorn non ricarica il codice, quindi la fix era nel file e non nel processo.

Rifatta sul serio, usando la reindicizzazione della pendenza 3 come innesco:

```
CURRENT su disco                  : v20260901T114636
snapshot server (prima)           : v20260901T105315
snapshot server dopo /api/retrieve: v20260901T114636
```

Una sola chiamata a `/api/retrieve` — **non** a `/ask` — allinea lo snapshot. Prima della
correzione era esattamente la chiamata che non faceva nulla.

## 3. Il campo `project:` era una classe, non un'istanza

Segnalando `graph_rag_ingestion_strategy.md` avevo guardato un file solo. Verificati tutti e
13 i tracciati: la convenzione della baseline è `project: "cross-project"` — e **il mio
stesso edit precedente** su `architecture_decision_rationale.md` ne aveva introdotta una
terza variante (`"VibeCraft — baseline cross-progetto"`) invece di seguirla. Corretti
entrambi; ora i 13 documenti sono allineati, sottotitolo H2 compreso
(`## Baseline Cross-Progetto`).

## A6 — chiuso

Il criterio di chiusura era: *o un clone pulito riproduce le metriche dichiarate, oppure il
report di eval dichiara su quale corpus ha misurato*. La prima strada resta impraticabile —
9 documenti (6 output di pipeline, 3 spec locali del progetto ospitante) stanno nell'indice
per ragioni legittime e non devono entrare nel repo. Quindi la seconda, in due punti.

**Il rilevatore di divergenza ora vede entrambe le classi.**
`observe_docs_git_divergence()` confrontava solo i file tracciati con il committato, perché
parte da `git ls-tree`: un corpus grande il doppio produceva `diverging: []`, che si legge
come "tutto a posto". Aggiunto il campo `untracked`. Come `diverging`, **non entra in
`state`**: la maggior parte di quei file è legittima, e farne un problema significherebbe un
allarme atteso a ogni esecuzione notturna — il rumore seppellirebbe il segnale raro, che è
l'errore contro cui la funzione stessa mette già in guardia per le istanziazioni.

**Il report di eval dichiara il corpus, accanto ai numeri e dentro il JSON.**

```
misurato su: 16 documenti tracciati · +9 NON tracciati (nell'indice, assenti da git)
             · 2 divergenti dal committato  ⚠️  numeri NON riproducibili su un checkout pulito
```

La riga è a schermo perché è chi legge il report a occhio che rischia di confrontarlo a
mente con quello di ieri; il campo `corpus` nel JSON serve al confronto automatico. È
telemetria: se git manca degrada a vuoto e l'eval misura lo stesso.

Tre test nuovi: il rilevatore vede un file non tracciato senza cambiare `state`; la riga di
provenienza allarma se e solo se c'è divergenza; l'assenza di git non rompe il report.

**Cosa NON chiude questo.** I numeri restano diversi fra questa macchina e la CI. Non è più
un difetto nascosto: è una differenza dichiarata, fatta di documenti che nessun caso del
golden set nomina né come atteso né come distrattore. La parte che rendeva la misura
*inversa* — i distrattori fuori baseline — è chiusa dal commit precedente.

---

## A19 — la lettura dei PDF è spenta, e nessuno lo dice

Trovato durante l'audit delle licenze (Run C), non cercandolo.

`core/chunking.py:_read_pdf` importa **`pypdf`**, che **non è dichiarata in `pyproject.toml`,
non è nel lock e non è installata**. L'import è dentro un `try/except ImportError` che
degrada a un `logger.warning`.

Verificato eseguendolo su un PDF vero:

```
LOG> WARNING core.chunking:  ⚠️ pypdf non installato: salto documento.pdf (pip install pypdf)
read_document('documento.pdf') -> metadata={} testo=''
```

**Un PDF messo in `docs/` viene indicizzato come documento vuoto.** Non fallisce, non
compare fra i problemi di `check_index_integrity`: lascia una riga di warning e un chunk
senza testo. È la stessa famiglia di A1 e A18 — una degradazione silenziosa che a valle è
indistinguibile dal funzionamento normale.

I tre lettori di `read_document` non stanno tutti allo stesso modo:

| Formato | Libreria | Stato |
|---|---|---|
| `.docx` | `python-docx` | OK, **dichiarata** |
| `.xlsx` | `openpyxl` | OK, ma solo **transitiva** (da `markitdown[xlsx]`): funziona per fortuna |
| `.pdf` | `pypdf` | **assente** |

### Chiuso — dichiarando le librerie e togliendo il degrado

Strada scelta: **dichiarare le dipendenze**, non riscrivere `_read_pdf` su `markitdown`. Il
codice esiste già ed è scritto per `pypdf`; cambiare libreria sarebbe stata una modifica di
design a fronte di una dichiarazione mancante.

Dichiarate **due**, non una: `pypdf` non c'era affatto, e **`openpyxl` arrivava solo come
transitiva di `markitdown`** — funzionava per fortuna, e sarebbe bastato che `markitdown`
cambiasse le proprie dipendenze per spegnere anche l'`.xlsx` nello stesso modo silenzioso.
Correggere solo il PDF avrebbe lasciato il gemello armato.

E soprattutto: **tolti i tre `try/except`** che degradavano a stringa vuota. Sembravano
tolleranza, erano perdita silenziosa di dati — l'unica ragione per cui il difetto è
sopravvissuto tanto a lungo. Con le librerie dichiarate, una che manca è un ambiente rotto e
deve fallire subito, non produrre un chunk vuoto.

Verificato dal vivo dopo la correzione: `read_document` su un PDF vero lo apre e lo legge,
**nessun warning emesso** (prima: `⚠️ pypdf non installato: salto ...` e testo vuoto).

Due test nuovi in `tests/test_chunking.py`: uno fallisce nel momento esatto in cui una delle
tre librerie esce dalle dipendenze; l'altro pretende che un `.pdf` illeggibile **sollevi**
invece di restituire vuoto.

---

## A20 — un indice locale vuoto fa cancellare le collection di chi condivide Qdrant

Trovato **provocandolo**, durante la verifica dell'immagine Docker in L2. Non è un difetto
ipotizzato: è successo, su questa macchina, e ha distrutto dati.

### Cosa è successo

Avviato il container `vibecraft:cpu` puntandolo al Qdrant **dell'installazione nativa**
(`QDRANT_URL=host.docker.internal:6333`), con il proprio `database/` vuoto. Al boot:

```
GC collection Qdrant orfane: vibecraft_events__v20260901T101536,
                             vibecraft_events__v20260901T132300
```

Due collection appartenenti all'installazione nativa, cancellate dal container al primo
avvio. `CURRENT` e l'alias sono sopravvissuti (è già un invariante documentato del GC),
quindi il sistema è rimasto in piedi — ma **il rollback a quelle due versioni ora
fallirebbe sul lato Qdrant**, ed è esattamente ciò che il blue/green esiste per garantire.

### La causa

`gc_orphaned_qdrant_collections` calcola l'insieme `referenced` dai manifest delle versioni
locali. Con `database/versions/` vuoto quell'insieme è vuoto — e il codice lo interpretava
come **"nulla è referenziato, quindi è tutto orfano"**.

Semanticamente è il contrario: un insieme di riferimenti vuoto significa **"non ho basi per
giudicare"**. È la stessa forma di A1, A18 e A19 — un caso limite non considerato che si
comporta in modo distruttivo senza chiedere niente a nessuno — ma è l'unico finora che
**perde dati** invece di degradare in silenzio.

### Correzione

Guardia in `core/indexing.py`: nessuna versione locale ⇒ **nessun GC**, con un `WARNING`
che spiega perché. Test in `tests/test_qdrant_blue_green.py`, verificato per costruzione:
disattivando la guardia fallisce, ripristinandola torna verde.

Nel `docker-compose.yml` il problema non si presenta — lo stack usa un proprio Qdrant con un
proprio volume — e il README avverte esplicitamente di non puntare il container a un Qdrant
già usato da un'installazione nativa.

### Cosa resta

Le due collection non sono recuperabili: gli artefatti su disco in `database/versions/`
ci sono ancora, ma i vettori no. Un rollback a `v20260901T101536` o `v20260901T132300`
richiederebbe una re-indicizzazione. Le versioni successive non sono state toccate.
(`v20260901T101536` è nel frattempo uscita dalla retention; il suo *lineage* sopravvive in
`v20260901T105315` e `v20260901T114636`, che dichiarano la stessa collection distrutta —
quindi le versioni locali che puntano a vettori inesistenti oggi sono **tre**.)

**Il comportamento al tentativo, invece, era risolvibile — ed era peggio del previsto
(chiuso 2026-09-04, R14).** Provato dal vivo, non dedotto: `python index.py --rollback
v20260901T132300` **riusciva**. Stampava `✅ Rollback: CURRENT → v20260901T132300`, poi il
warning che l'alias non era stato spostato, e usciva 1 — lasciando il sistema in uno stato
**misto e durevole**: CURRENT (grafo e sidecar) sulla versione target, produzione Qdrant sui
vettori di `v20260904T092228`. Non un fallimento oscuro: una **mutazione parziale riuscita**.
Nessuno la ripara — `repair_qdrant_alias` non inventa collection, quindi nemmeno il
reconciler di boot — e in quello stato `check_index_integrity` rispondeva **`ok: true`,
`problems: []`**: le due build hanno lo stesso numero di chunk (160) e il passo 5 confronta
solo un conteggio. Via HTTP era ancora più silenzioso: `POST /api/index/rollback` rispondeva
**200**, con lo stato `missing_target_collection` sepolto nel corpo e nessun alert scritto.

Due correzioni, entrambe verificate dal vivo su questo indice:

1. **Fallisce PRIMA di mutare.** `assert_rollback_target_has_vectors` (core/indexing.py)
   gira sotto lo stesso writer lock, prima di `rollback_version`: se la collection
   dichiarata dalla versione target non esiste, il rollback è **rifiutato** — CURRENT non si
   muove, l'alias nemmeno — con un messaggio che nomina la collection mancante e dice che
   serve una re-indicizzazione completa. CLI exit 1, route **409**. La risoluzione del
   target è stata estratta in `core.artifacts.resolve_rollback_target` proprio per poter
   verificare *prima* di scrivere. **Qdrant irraggiungibile non blocca nulla**: il
   pre-check si salta e il comportamento resta quello di sempre (rollback locale, alias
   riparato al boot) — la sonda è la stessa `get_collections` che serve alla verifica, e se
   solleva non c'è nulla da verificare.
2. **Lo stato misto, se ci si finisce lo stesso, non è più silenzioso.** Il passo 5 di
   `check_index_integrity` verifica ora anche che la collection **dichiarata dalla versione
   attiva** esista ancora: se è sparita, l'alias serve i vettori di un'altra build e la
   divergenza non è nemmeno riparabile ⇒ `qdrant_mismatch`, cioè full rebuild per lo script
   notturno. Attenzione al contrappeso, che ha un test dedicato: un alias divergente con la
   collection attesa **ancora presente** resta la sola osservazione `qdrant_alias` — quella
   il boot la ripara, e farne un problema significherebbe accodare un rebuild a ogni
   divergenza transitoria.

Verifica di chiusura, eseguita: rollback verso `v20260901T132300` → rifiutato, `CURRENT`
invariato a `v20260904T092228`; rollback verso `v20260901T132525` (collection viva) →
riuscito, alias swappato; stato misto ricreato a mano forzando `CURRENT` → il check che
prima diceva `ok: true` ora risponde `ok: false`, `qdrant_mismatch: true`, exit 1.

---
---

# A2b — il cancello si era spostato, la sorveglianza no

**Domanda:** il gate è a k=2, ma trend, rilevamento di regressione e dashboard leggono
ancora `recall@10`. Quanto conta?

## Il difetto in una frase

`eval_gate.k` è migrata **10 → 5 → 2**, e ogni passo fu innescato dall'alert di saturazione
del progetto stesso: a quel k la metrica valeva 1.000 su tutti i casi e aveva smesso di
discriminare. Il cancello si è spostato tre volte. **Tutto ciò che lo osserva è rimasto a 10**,
cioè su un numero che non può scendere — e quindi non può segnalare niente.

## Quanto era rotto, punto per punto

Cercando i consumatori è emerso che il difetto era più esteso della riga di Run A:

| Dove | Cosa faceva | Perché non poteva funzionare |
|---|---|---|
| `eval_history.latest_recall / compute_trend / detect_regression` | `key="recall@10"` come default | serie satura: media mobile piatta a 1.000, `sustained_drop` irraggiungibile |
| `/api/health` → `eval` | esponeva `last_recall_at_10: 1.0` | il numero di qualità in evidenza era l'unico che non poteva peggiorare |
| `/eval` (pagina di trend) | `const KEY = "recall@10"`, e 8 etichette scritte a mano | grafico di una retta orizzontale a 1.000: un trend che non poteva avere pendenza |
| `/infografica` (KPI) | colorava contro una soglia `0.9` scritta a mano | il gate stava a **0.75**: la dashboard poteva dare in rosso una recall che il gate accettava |
| `eval/run.py` guardrail | asseriva su `recall@max(ks)`, default max = 10 | vedi sotto |
| `scripts/nightly_consistency.{sh,ps1}` | `--check-regression --assert-min 0.90`, **senza `--k`** | max(ks) = 10 ⇒ confronto fra una metrica satura a 1.000 e un floor 0.90 |

**L'ultima riga è la peggiore, ed è quella che la Run A non aveva visto.** Il README insegna
`--k 1 2` proprio per abbassare `max(ks)`, ma i due script notturni — l'unico posto dove
questo guardrail gira **da solo, senza un umano che legga il report** — non lo passano. Il
check notturno di qualità era verde per costruzione da quando il gate lasciò k=10.

## La correzione: una sola sorgente di verità

`GATE_RECALL_KEY = f"recall@{EVAL_GATE_K}"` in `core/eval_history.py`, e tutto ci si aggancia:

- i tre osservatori dello storico prendono quella chiave come default;
- `eval_health()` restituisce **`key` e `min_recall` nel payload**. Il campo `last_recall_at_10`
  non esiste più: aveva il `10` nel nome, e un numero senza la sua chiave e la sua soglia non
  è osservabilità, è una cifra. Le due pagine leggono `key` dal server invece di scriverla;
- il guardrail di `eval.run` asserisce sulla chiave del gate con la soglia del gate, e **la `k`
  del gate viene sempre misurata** anche se il chiamante ha chiesto altre colonne: `--k` cambia
  cosa si legge, mai su cosa si fallisce;
- gli script notturni perdono `--assert-min 0.90` ed ereditano la soglia dal config.

Spostare `eval_gate.k` ora sposta anche la sorveglianza, senza che nessuno debba ricordarsene.

## Cosa costa

La serie si accorcia: **da 79 a 22 punti**, perché le righe storiche portano la chiave del k
di allora. Sono punti in meno di una misura che discrimina, contro punti in più di una che
non può muoversi. Il grafico ora sale da 76% a 87% con la soglia del gate al 75% disegnata
sotto; prima era una retta a 1.000.

## Verifica

`✅ PASS (recall@2 = 0.873, soglia --assert-min = 0.75)` — prima
`✅ PASS (recall@10 = 1.000, soglia --assert-min = 0.7)`.

Test: la chiave sorvegliata segue `EVAL_GATE_K`; `history_points` conta la serie e non le
righe; `eval_health` porta `key` e `min_recall` e non `last_recall_at_10`; e un guardrail che
riceve `ks=[10]` con l'atteso in quinta posizione **fallisce** — con la vecchia regola
sarebbe passato. Le due pagine verificate in un browser reale: `/eval` e la KPI
dell'infografica dicono `recall@2`, senza errori in console.

## Cosa resta aperto

- **Le righe storiche restano scritte con la chiave del k di allora.** È corretto — sono
  misure diverse e mescolarle sarebbe peggio — ma significa che a ogni futuro spostamento del
  gate il grafico riparte quasi da zero. Se un giorno servisse continuità, la strada è
  registrare **tutti** i k in ogni riga, anche dalle righe scritte dal gate (che oggi ne
  registra uno solo).
- **`recall@2` è a 0.875 con soglia 0.75:** margine 12,5 punti *(era 0.873 su 55 casi; il
  golden set è passato a 56 il 2026-09-04 — vedi la sezione S5 in fondo)*. Il giorno in cui
  saturasse non resta un k più basso: andrà **esteso il golden set** con casi che il sistema
  sbaglia, come già dice `rag_config.yaml`. **I candidati sono stati individuati e misurati
  il 2026-09-04, prima che servissero** (R13): l'elenco è in fondo a questo documento, sezione
  «R13 — cinque candidati misurati, nessuno aggiunto». Sceglierli sotto pressione avrebbe
  significato sceglierli per far scendere un numero.

---
---

# A4 — quattro casi non "falliscono": sono la misura

**Domanda:** 5 casi su 14 falliscono e non c'è alcun gate su questa suite. Quanto è grave?

## Metà del riscontro era una lettura sbagliata del report

Il file stesso lo dichiara, e lo dichiarava già quando la Run A lo ha letto
(`eval/golden_multihop.yaml`, testata):

> *«"quali documenti esistono nel corpus?" → 6 matcher su 11 in top-10. Il limite è
> strutturale, non di ranking: 11 documenti non entrano in 10 posizioni. […] le 3 catene che
> spandono TRE documenti si fermano a 2 su 3.»*

I quattro fallimenti della baseline A **sono il gap che questa suite esiste per
quantificare** — è il gap che fece scattare il trigger M2 e nascere il router deterministico.
Un report che li presenta come «4 su 14 falliti» invita esattamente all'errore che ho fatto.

## Metà era vera, e più grande di così

**Nessun gate, nessuno storico, nessun allarme, e nemmeno una riga di README.** La classe di
domande più preziosa per un grafo di governance poteva regredire senza che nulla lo dicesse:
la suite girava a mano, e il suo esito viveva in un JSON che nessuno rileggeva.

E il quinto fallimento era un difetto vero, ma di tutt'altro genere.

## Il quinto caso: un'attesa-istantanea

`quali documenti esistono nel corpus?` falliva anche **B**, l'unico caso strutturale a
farlo, per un solo motivo: `count: 11`, mentre il router rispondeva `23`. Il router aveva
ragione — il corpus è cresciuto.

La testata del file conteneva già la regola giusta, e la propria eccezione:

> *«Nota di progettazione sui `count`: dichiarato solo dove è semanticamente stabile
> (l'enumerazione dei documenti). Per relazioni/impatto è deliberatamente OMESSO: quei
> conteggi cambiano a ogni modifica di un documento qualsiasi, e un golden-set che fallisce
> per una virgola aggiunta altrove misura il rumore, non la regressione.»*

Il numero di documenti non era «semanticamente stabile»: cambia ogni volta che se ne aggiunge
uno, cioè più spesso di una relazione. L'unica eccezione alla regola era anche l'unica cosa
che si è rotta. Rimossa: **B passa 6/6** e il caso torna a essere ciò per cui fu scritto — A
fallisce, B riesce, che è la dimostrazione del perché serve il router.

## La correzione

- **Soglia**, in `eval_multihop` di `rag_config.yaml` — blocco separato da `eval_gate` perché
  non partecipa alla promozione blue/green: `min_recall: 0.85` sulla **recall media di A** e
  `require_graph_exact: true` sulle attese di B.
- **Perché sulla media e non sui casi riusciti:** «A riusciti» ha un tetto di 10/14 che il
  sistema non può alzare; la recall media invece **scende** se il ranking peggiora.
- **Storico**: ogni corsa scrive in `history.jsonl` con `source="multihop"` e chiavi
  **prefissate** (`multihop_recall@10`, `multihop_graph_exact`) — condividono il file con
  l'altra suite e `_series` seleziona per chiave: un `recall@10` nudo si sarebbe mescolato
  con quello del golden-set classico, che misura tutt'altro sugli stessi k.
- **Allarme**: sotto soglia scrive un alert `critical` in `alerts.jsonl`, il canale che
  `/api/health` espone come `last_alert`. Senza, il gate sarebbe stato un exit code che
  nessuno guarda.
- **Check notturno**: la suite gira accanto all'eval classico in
  `scripts/nightly_consistency.{sh,ps1}`. Costa 14 chiamate a `/api/retrieve` e
  `/api/graph/query`, zero LLM.
- **README**: la suite ora è documentata, col motivo per cui quattro casi non passano.

## Misura dopo

```
casi: 14  |  k=10  |  recall media A = 0.896  |  A riusciti = 10/14  |  B exact = 6/6
✅ PASS  (recall media A >= 0.85, attese strutturali tutte soddisfatte)
```

Prima: `recall media A = 0.896 · A riusciti 10/14 · B exact 5/6`, nessun verdetto.

A differenza di `recall@10` sul golden-set classico, **questa metrica non è mai stata satura**
— il che la rende, oggi, la più informativa delle due.

## Cosa resta aperto

- **Le tre catene a tre documenti restano a 2 su 3**, e questa correzione non le tocca: mette
  una soglia sotto al numero, non lo alza. Il documento mancante è ogni volta il terzo salto,
  che il retrieval semantico non può vedere — ma `/ask` inietta anche le sezioni raggiunte
  **via grafo**, quindi la domanda vera è se manchi nella *risposta*, non nel retrieval. È la
  stessa distinzione di A3, e come lì nessuna metrica la guarda.
  **MISURATO il 2026-09-05** (S6, R9), e la risposta è no: il ramo grafo **non** recupera il
  terzo documento. Su 3 catene chieste a `/ask` coi parametri di produzione, il documento
  mancante entra nel contesto **1 volta su 3** — e in quell'unica volta senza la sezione che
  porta il vincolo. Nelle altre due l'intero budget del ramo grafo
  (`graph_context_max_chunks: 2`) va a due sezioni di preambolo di un documento **già presente
  dal ramo semantico**, perché l'esclusione dei seed opera sui soli nodi `document` mentre le
  loro sezioni sono raggiunte a `hops ≥ 1` e ne ereditano l'autorità. Nella risposta il
  vincolo del terzo documento manca in tutti e tre i casi (il `409` di `[REGOLA-API-04]`, la
  gamba «test» dei vincoli PII, l'attribuzione a `[SAFEGUARD-AUD-*]`). **Quindi la soglia di
  A4 misura ciò che dice — la recall del retrieval — e non c'è alcun compenso a valle.**
  **CHIUSO lo stesso giorno**: i due filtri del ramo grafo lavorano ora sul **documento**
  della sezione — il che chiude anche una falla gemella su `superati` — e i candidati di tutti
  i nodi raggiunti sono ordinati per **pertinenza × fiducia × autorità**, la composizione dei
  tre segnali che il ramo già calcolava e usava uno alla volta. Rimisurato: il terzo documento
  entra in finestra su **3 catene su 3**; «ultima unità» arriva a dire «l'altra riceve `409`
  con code `RESOURCE_EXHAUSTED`» citando `[REGOLA-API-04]`, e «PII fra log, test e LLM»
  guadagna una sezione «Vincoli sui Test» che prima non c'era. Golden set e suite multihop
  **invariati** (il ramo grafo non passa da `/api/retrieve`). **Quindi la soglia di A4 misura
  ciò che dice, e ora esiste un compenso a valle** — che nessuna delle due suite vede, il che
  resta il punto di N3.
- ~~**Il verdetto «trigger M2» è ormai storico** e il report lo stampa ancora come se fosse
  in corso~~ — **chiuso il 2026-09-04.** Il residuo era metà di com'era scritto: il docstring
  di `eval/run_multihop.py` dichiarava già il verdetto come storico, era solo la riga stampata
  a suonare come una decisione in corso. Il numero resta (è il gap retrieval→grafo ancora
  scoperto dal router), con l'etichetta che dice cosa significa oggi: **più basso = meglio**.
  Il campo `trigger_m2.fired` resta nel JSON, dove nessuno lo legge come un semaforo.
- ~~**`recall media A = 0.896` con soglia 0.85:** margine 4,6 punti, lo stesso ordine di
  grandezza del gate single-hop.~~ **NON PIÙ VERO dal 2026-09-04** (S5): il corpus nuovo ha
  portato la recall media di A a **0.854**, cioè **0,4 punti** sopra il pavimento. Registrato
  come **R19**; rimisurato uguale il 2026-09-05 su due corse del notturno. La riga resta qui
  barrata e non riscritta perché il numero di allora era vero: a scadere è stato il margine,
  non la misura.

---
---

# A7 — la regola era scritta nella funzione che produce il `None`, e il consumatore la ignorava

**Domanda:** nel ramo misto un chunk con `colbert_score=None` pesa `-1.0 × (1-α+α·autorità)`
— più è autorevole, più scende. Oggi irraggiungibile: quanto conta?

## Dove stava già la risposta giusta

`colbert_maxsim` dichiara la semantica del proprio `None`, e la dichiarava da prima:

> *«None se il chunk non ha vettori (sidecar assente o disallineato): "non giudicabile", che
> **non è la stessa cosa di "poco pertinente"**.»*

`rank_by_authority` lo sostituiva con `-1.0` — cioè con "pochissimo pertinente", il preciso
significato che quella riga esclude — e poi lo **moltiplicava per l'autorità**. Con α=0.1 il
moltiplicatore sta in [0.9, 1.0], quindi la chiave finiva in [-1.0, -0.9] e, ordinando al
contrario, la fonte **più** autorevole prendeva la chiave più negativa: ultima.

`rank_sections_by_relevance`, scritta dopo per il ramo del grafo, onora invece la
distinzione («le sezioni SENZA vettore non sono giudicabili: finiscono in coda»). La regola
esisteva in due punti su tre.

## L'incoerenza che non era nel riscontro

Cercando come sistemarlo è emerso che i due rami di prima si contraddicevano fra loro. Gli
**stessi due** chunk senza vettore uscivano:

| | ordine |
|---|---|
| da soli (`any(...)` falso ⇒ ramo fusione) | fusione ÷ autorità — **corretto** |
| appena un terzo chunk qualsiasi portava un vettore | `-1.0` × autorità — **invertito** |

Il posto di un chunk dipendeva dal fatto che *altri* chunk avessero un vettore. Questo spiega
anche perché la correzione non è "un ramo in meno di bug": i due rami andavano fusi.

## La correzione: due insiemi, non due rami

Nessun punteggio finto e nessun `if any(...)`:

```python
giudicabili.sort(key=lambda r: r["colbert_score"] * _mult(r), reverse=True)
non_giudicabili.sort(key=lambda r: r["fused_rank_sum"] / _mult(r))
results[:] = giudicabili + non_giudicabili
```

I non giudicabili stanno in coda, ordinati con la regola che governava già il caso "nessun
ColBERT": la fusione denso+sparso — l'unico segnale di rilevanza che hanno — modulata dalla
stessa autorità. Copre entrambi i vecchi rami, quindi ne elimina uno, e sparisce anche la
domanda "il sentinella `-1.0` sta davvero sotto ogni punteggio reale?".

**Il percorso di produzione non cambia di una posizione**, ed è verificato: con copertura
piena `non_giudicabili` è vuoto e il risultato è `giudicabili` ordinati come prima. Copertura
misurata oggi su `v20260901T132525`: **160 chunk / 160 vettori ColBERT, 0 scoperti, 0
orfani** — A7 resta latente, com'era.

## Una divisione per zero, nella stessa espressione

Ad α=1 il moltiplicatore **è** l'autorità: una fonte che dichiara `authority: 0.0` nel
frontmatter azzerava il divisore del ramo di fusione. Non è ipotetico quanto sembra — α=1.0
è la forma che `[REGOLA-VAL-08]` prescriveva prima dell'emendamento, ed è ancora una
coordinata della griglia del calibratore (`ALPHAS = [… 0.8, 1.0]`). Aggiunto un pavimento:
quella fonte va comunque in fondo, che è la direzione giusta, invece di far esplodere il
retrieval.

## Un test che non provava nulla

Il primo test che ho scritto — la fonte autorevole senza vettore non deve scendere —
**passava anche col codice difettoso**: con soli chunk non giudicabili `any(...)` è falso e si
imboccava il ramo di fusione, che era già corretto. Serve un candidato giudicabile in lista
perché il difetto si manifesti. Test riscritto e assorbito; verificate una per una tutte le
attese contro la regola vecchia, per non lasciare in suite altre asserzioni che non
distinguono le due versioni:

| test | vecchia regola | nuova |
|---|---|---|
| coda senza inversione | `debole, senza-bassa, senza-alta` | `debole, senza-alta, senza-bassa` |
| il posto non dipende dagli altri | soli `B,A` vs misti `A,B` | `B,A` in entrambi |
| α=1 con autorità 0 | `ZeroDivisionError` | in fondo |
| copertura piena | identico — **è la guardia sul percorso di produzione** | identico |

## Cosa resta aperto

- **Nessun test esercita un Qdrant reale** (A8), che è la via per cui la divergenza
  sidecar↔Qdrant si presenterebbe davvero. Questa correzione fissa il comportamento *dato*
  un `None`; non fa comparire il `None`.
- ~~**Nulla allarma quando la copertura ColBERT scende.**~~ → **CHIUSO 2026-09-04 (R2).**
  La copertura è stata **rimisurata**, non assunta: sull'indice attivo `v20260904T092228`,
  **160 chunk in `chunks.json`, 160 chiavi in `colbert.npz`, zero scoperti e zero orfani** —
  il 160/160 di questa riga regge ancora. Ma il numero continuava a esistere solo perché
  qualcuno lo misurava a mano. Ora è la **terza voce** della stessa lista di problemi di
  `check_index_integrity` (passo 4, fra gli artefatti e Qdrant), con la stessa forma delle
  altre due: nessun meccanismo nuovo. Costo zero in embedding — si legge il solo membro
  `keys` del `.npz`, i vettori non vengono mai decompressi.
  **Va in `problems`, non fra le osservazioni pure**, e la ragione è stata verificata prima
  di deciderlo: il precedente documentato nella funzione (rollback intra-lineage seguito da
  un incrementale ⇒ mismatch ATTESO) riguarda **solo Qdrant**, che non è versionato. I due
  sidecar li scrive la **stessa `save_artifacts` nella stessa directory di versione**, sia
  dal full rebuild (`core/indexing.py:865`) sia dall'incrementale (`:1881`): fra loro non
  esiste una divergenza legittima, quindi un mismatch è sempre un difetto e la remediation
  giusta è quella che lo script notturno applica già per `artifacts_corrupted` — full
  rebuild. Verificato per costruzione (`tests/test_index_integrity.py`): tolta una chiave
  dal sidecar il check la segnala (`-c2` nel messaggio), rimessa torna verde; e i 4 test
  nuovi **falliscono contro il codice vecchio**, dove il confronto non esisteva.

---
---

# A16 — l'astensione parlava correttamente, e nessuno la ascoltava a macchina

**Domanda:** alla domanda fuori corpus la risposta è un rifiuto corretto e motivato, ma il
payload resta `status:"success"` con le fonti elencate. Come si corregge senza fare NLP
sulla prosa del modello?

## Perché non un'euristica sul testo

La tentazione ovvia era cercare frasi come *"non è presente nel contesto"* o *"non risulta
dai documenti"* nella risposta. È la strada sbagliata: sono frasi che il modello genera
liberamente, in italiano, senza un contratto — cambiano formulazione da una domanda
all'altra, e un `if "non è presente" in answer` si romperebbe alla prima riformulazione,
producendo falsi negativi silenziosi (un'astensione classificata "success") o falsi positivi
(una risposta vera che cita "non è presente" come parte del contenuto, es. una spec che
descrive un vincolo di assenza).

## La correzione: un contratto, non un'inferenza

`[REGOLA-ASTENSIONE]`, aggiunta al system prompt di `build_ask_prompt`: se e solo se il
contesto fornito non basta, la risposta **deve iniziare esattamente** con un token —
`retrieval.ASK_ABSTENTION_MARKER`, `[ASTENSIONE]` — nessun testo prima. `ask_rag` lo
riconosce con un confronto letterale (`lstrip().startswith(...)`), lo rimuove — l'utente
umano non lo vede mai — e imposta `status: "abstained"` invece di `"success"`.

Non è un'inferenza su cosa il modello "intendeva": è un token che il modello si impegna a
scrivere, e che il consumatore si impegna a leggere. Le due metà del contratto vivono nello
stesso posto (`core/retrieval.py`, `ASK_ABSTENTION_MARKER`) apposta: non possono
disallinearsi rinominando una sola delle due.

## Perché non riusare `no_results` / `no_graph_nodes`

Quegli stati esistevano già e sono deterministici: **il retrieval non ha trovato nulla** — né
documenti nel grafo né codice pertinente. `abstained` è un caso diverso: il retrieval **ha**
trovato qualcosa (le fonti sono in `qdrant_scores`, il contesto è in `graph_context`), ma la
sintesi finale — l'LLM, leggendo quel contesto — giudica che non risponde alla domanda. Sono
due fallimenti a livelli diversi della pipeline, e confonderli in un solo stato avrebbe
nascosto la differenza fra "non ho trovato nulla di rilevante" e "ho trovato qualcosa ma non
basta".

## Verifica dal vivo

```
domanda fuori corpus  → status: "abstained" · answer senza il marcatore
domanda normale       → status: "success"   · answer invariata
```

E il caso che l'euristica sul testo avrebbe sbagliato: una risposta che **cita** la regola di
astensione a metà frase (`"la regola dice di usare [ASTENSIONE] solo quando..."`) resta
`"success"`, perché il token non è il primo carattere. Testato esplicitamente
(`test_marcatore_a_meta_testo_non_conta`).

**Cache**: un'astensione entra in cache come qualunque altra risposta — stessa domanda,
stesso indice, stessa risposta, anche quando la risposta è "il contesto non basta" — e lo
stato cachato resta `abstained`, non silenziosamente `success` (`test_astensione_viene_cachata_come_lo_stesso_esito`).

## Cosa resta aperto

- ~~**Il marcatore è un impegno del prompt, non una garanzia del modello.** Un provider che
  ignorasse l'istruzione — o un modello molto più debole — tornerebbe silenziosamente a
  `"success"`. Nessun test esercita questo caso contro un LLM reale (solo contro il fake nei
  test); la verifica dal vivo qui sopra è con `qwen3.5:9b`, che la rispetta.~~
  **CHIUSO il 2026-09-05** (S6, R10). Il check notturno — che gira dove Ollama c'è, ed è già
  il canale degli alert — pone una domanda fuori corpus a `/ask` e pretende
  `status: "abstained"`; qualunque altro stato scrive un alert che lo riporta. In CI resta
  esercitato solo contro il fake, ed è corretto: in CI un modello non c'è. Che il check
  **discrimini** è stato verificato, non assunto: la stessa domanda posta dentro il corpus
  torna `success`. Resta vero — e ora è sorvegliato invece che sperato — che la garanzia vale
  per il modello configurato: cambiarlo è ciò che questo check esiste per rendere visibile.
- **La dashboard non distingue `abstained` da `no_results`/`no_graph_nodes`/`graph_answer`
  nella colorazione** (`templates/dashboard.unified.html`): tutto ciò che non è
  `"success"` è già rosso, `abstained` incluso. Non è un difetto nuovo — `graph_answer`, che
  è un successo a tutti gli effetti, ha lo stesso trattamento — e resta fuori dal perimetro
  di A16, che riguardava il payload, non la sua resa visiva.

---
---

# A1 — il margine dell'81% non c'era più, e nessuno se n'era accorto

**Domanda:** `top_k≤20` (server-side, non più solo un attributo HTML) chiude il difetto?

## Il primo controllo ha smentito la premessa

La riga di Run A descriveva `top_k≤50` come tetto server e l'attributo HTML `max="20"`
come unica barriera reale. Leggendo `api/models.py` **prima** di fare qualunque cosa: il
tetto server era già `le=20`, con un commento che ne spiega la ragione di correttezza e
cita la stessa misura dell'audit (81% a k=20). Quel fix era già arrivato in una sessione
precedente — solo la riga non l'aveva mai registrato.

Verificarlo mi ha messo in guardia: se una parte della premessa era stantia, valeva la
pena rimisurare tutto prima di dichiarare chiuso il resto.

## La misura dal vivo ha smentito anche il margine

Richiesta reale contro il server in esecuzione, `top_k=20` — il massimo oggi **legittimo**,
non un bypass di validazione:

```
status: success
~17.013 token stimati su num_ctx=16384  →  104%
```

Non un caso limite raro, non un attacco: il tetto che il server stesso impone come
"sicuro" produce oggi un prompt che eccede la finestra su una domanda ordinaria. La
misura originale di Run A (81% a k=20) era corretta quando fu presa; non lo è più, perché
il prompt di sistema è cresciuto da allora — `[CLASSE-FONTI]` (A3) e `[REGOLA-ASTENSIONE]`
(A16), entrambe aggiunte in questa stessa sessione, sono testo fisso iniettato in **ogni**
richiesta, indipendentemente da `top_k`. Un tetto di correttezza calibrato su una misura
è tanto valido quanto è recente quella misura: nessuno l'aveva ricontrollata dopo aver
allungato il prompt.

## La correzione: due soglie, non una

`core.llm._ollama_payload` aveva un solo confine (80% di `num_ctx`) e una sola reazione
(`logger.warning`). Il difetto non era la soglia — 80% è un punto ragionevole per un
*avviso* — ma che la stessa reazione valesse anche quando il troncamento non è più un
rischio ma una **certezza**: quando il prompt da solo raggiunge `num_ctx`, Ollama tronca
dall'alto per costruzione, non per sfortuna.

Aggiunta una seconda soglia:

- **rischio** (80-100% di `num_ctx`): resta `logger.warning`, comportamento invariato — la
  stima è approssimativa, la generazione può ancora riuscire;
- **certezza** (≥ 100%): solleva `LLMError`. Nessun'euristica sul testo, nessun'inferenza:
  la stessa stima a 3 caratteri/token già in uso, con un confine diverso.

Il messaggio d'errore dice cosa fare (`riduci top_k o i chunk del contesto governato,
oppure alza llm_settings.ollama_num_ctx`), non solo cosa è andato storto.

## Perché non ha richiesto toccare i chiamanti

`LLMError` è già il tipo che questo modulo solleva per ogni fallimento di generazione
(rete, timeout, modello assente), e ogni consumatore lo gestisce già:

- **`/ask`** (`api/routes_retrieval.py`) cattura `llm.LLMError` e risponde `502` col
  messaggio — esattamente ciò che A1 chiedeva;
- **le sette pipeline** (canvas, propose, drift, validate, explore, review) passano da
  `pipeline.generate_tolerant`, che cattura `LLMError` e restituisce il messaggio come
  testo generato — lo stesso trattamento di un timeout o di un modello assente oggi;
- **il retry** (`_is_transient`) non lo ritenterà: `[FINESTRA DI CONTESTO SUPERATA]` non è
  nella lista dei marcatori transitori, quindi si rilancia subito — ritentare un prompt
  che eccede la finestra non lo farebbe rientrare.

Zero righe cambiate fuori da `core/llm.py` e dai test.

## Verifica

```
prima:  richiesta a 104%  →  200, status:"success"
dopo:   richiesta a 104%  →  502, "[FINESTRA DI CONTESTO SUPERATA]: ~17013 token
                                   contro num_ctx=16384"
        richiesta normale (top_k=8)  →  200, status:"success" (invariato)
```

Test: il confine esatto (999 token su una finestra di 1000 → ancora un warning; 1000 →
`LLMError`), il caso enorme già in test (`test_guardrail_globale_num_ctx_scatta_su_contesto_enorme`,
riscritto da assert-sul-log a `pytest.raises`), il test di warning esistente spostato al
90% per lasciare il 100% esclusivamente al nuovo confine.

## Cosa resta aperto

- ~~**Il margine si accorcerà di nuovo.** Ogni futura regola di sistema (`[REGOLA-...]`)
  aggiunta a `build_ask_prompt` sposta il punto in cui `top_k=20` smette di stare sotto la
  certezza. Non c'è un test che lo sorvegli nel tempo: solo la misura di oggi.~~
  **CHIUSO il 2026-09-04** (R3). `tests/test_ask_prompt_cost.py` sorveglia il costo **fisso**
  del prompt di sistema — la sola parte che dipende dal sorgente e non dal corpus: base più
  `[CLASSE-FONTI]` e `[PRECEDENZA-FONTI]` con le interpolazioni ridotte a valori sintetici.
  Budget **1.000 token stimati** contro i **954** di oggi, sulla stessa scala ~3
  caratteri/token del guardrail di `core.llm._ollama_payload` (una scala diversa misurerebbe
  una grandezza diversa da quella che poi solleva `LLMError`). I ~46 token di margine sono
  meno di qualunque regola vera — `[CLASSE-FONTI]` ne pesa ~330, `[REGOLA-ASTENSIONE]` ~160 —
  quindi aggiungerne una rende il test rosso, che è lo scopo: budget, data e ragione stanno
  dentro il test, e alzarli senza rimisurare il prompt completo a `top_k=20` sul corpus reale
  è il passo che era stato saltato. **Non** un test sul prompt completo: dipende dal corpus,
  fallirebbe a ogni reindex e non direbbe chi l'ha fatto crescere.
- **`top_k=20` resta il tetto**, anche sapendo che tocca il 104% su almeno una domanda
  reale. Non l'ho abbassato: la correzione di A1 riguardava il *comportamento al
  superamento* (mai più `success` silenzioso), non la ricalibrazione del tetto — che
  richiederebbe una nuova misura sistematica come quella originale, non un numero scelto
  a naso in coda a questa correzione.
- ~~**Nessun test esercita la soglia di certezza con un LLM reale** (solo con provider
  finti): il comportamento di Ollama davanti a un prompt che la supera resta osservato,
  non provato in CI.~~
  **CHIUSO il 2026-09-05** (S6, R11), e non in CI — in CI un LLM non c'è, ed è il motivo per
  cui il residuo era rimasto aperto. Il check notturno chiede `/ask` a `top_k=20` e pretende
  **502** col messaggio `[FINESTRA DI CONTESTO SUPERATA]`. Rimisurato oggi: **~17.298 token
  contro `num_ctx=16384`**, il 105,6% — la misura di A1 regge quattro giorni e un corpus
  dopo. Il ramo che conta è però il `200`: non viene ignorato come falso allarme
  benigno, scrive un alert che dice ciò che significa davvero — *o il guardrail non scatta
  più, o il contesto è sceso sotto la finestra*, e in entrambi i casi il contratto ha smesso
  di essere esercitato. Verificato che il check discrimini: la stessa domanda a `top_k=5`
  torna `200`, quindi il 502 viene dalla finestra e non da `/ask` rotto.

---
---

# A8 — l'inferenza era rovesciata, ma sotto c'era comunque un buco

**Domanda:** nessun test tocca un Qdrant reale. Vero?

## No, e la prova era nella riga stessa

Il ragionamento di Run A: *«1253 test, 0 skip con Qdrant attivo ⇒ nessun test tocca un
Qdrant reale»*. È rovesciato. Con il servizio **attivo** un test d'integrazione **gira**;
salta quando il servizio **manca**. Zero skip a Qdrant acceso è esattamente ciò che si
osserva quando quei test funzionano. Per concludere qualcosa servivano l'altra misura —
Qdrant spento — e quella non era stata fatta.

Misurate oggi entrambe:

```
Qdrant spento  →  31 passed, 5 skipped   ("Qdrant non raggiungibile su http://127.0.0.1:6333")
Qdrant acceso  →  36 passed
```

E i test non erano nuovi: la sezione «OPZIONALE / SKIPPABLE» con `_real_qdrant_client_or_skip()`
esiste dal **2026-07-17/18** (`cc39609`, `47d4e35`), sei settimane prima della Run A. Il
criterio di chiusura che questa riga proponeva — *«almeno un test di integrazione contro
Qdrant vero, saltato in modo esplicito quando assente»* — era **già soddisfatto quando la
riga è stata scritta**.

Come è successo: la riga cita `tests/test_qdrant_blue_green.py:42-131`, cioè la definizione
di `AliasAwareFakeQdrant`. Quella parte del file è davvero tutta fake. La sezione
d'integrazione sta a `:428-586`, oltre quattrocento righe più in basso.

*(Nota di metodo: anch'io stavo per sbagliare al contrario. La prima esecuzione mi ha dato
5 skip con «Qdrant non raggiungibile» mentre credevo il servizio acceso, e la lettura
comoda era «il helper di skip ha un falso negativo». Non era così: il container giusto si
era davvero fermato. Misurare due volte prima di accusare il codice.)*

## Ma la sostanza teneva, su un punto preciso

La riga elencava quattro cose validate solo contro il fake: **alias swap, delete-by-filter,
GC, rollback**. Verificando una per una, solo la prima era davvero coperta dal servizio
reale. La seconda no — ed è la peggiore da sbagliare:

`_delete_doc_chunks` esegue una delete-by-filter (`MatchAny` su `payload.doc_id`) contro
**l'ALIAS**, non contro la collection fisica: è così che l'indicizzazione incrementale
ripulisce i chunk dei documenti modificati o cancellati. Due assunzioni, nessuna provata:

1. che Qdrant risolva l'alias anche per una point-operation di **cancellazione** (non solo
   per `upsert`/`count`, gli unici che il fake modella);
2. che il filtro tolga **esattamente** i punti giusti.

I test esistenti su `_delete_doc_chunks` asserivano solo *quale nome di collection* fosse
stato passato: il fake ha un `delete` che registra il nome e **ignora il `points_selector`**.
Se la prima assunzione fosse falsa, l'incrementale lascerebbe indietro i chunk vecchi senza
che nulla fallisca — l'indice resta servibile e mente.

Non coperta nemmeno la seconda assunzione del GC: *«cancellare una collection invalida gli
alias che la puntavano»*, replicata dal fake e scritta solo in un commento.

## Cosa ho aggiunto

Due test nella stessa sezione, stesse convenzioni (nomi throwaway, mai `COLLECTION_NAME`,
pulizia sempre nel `finally`, skip esplicito se il servizio manca):

- **delete-by-filter attraverso l'alias**, che chiama la funzione di **produzione**
  (`index._delete_doc_chunks`) e non una sua imitazione: tre punti, due documenti, dopo la
  cancellazione ne deve restare **uno solo** e deve essere quello giusto. Un test che
  guardasse solo «il conteggio è sceso» passerebbe anche se cancellasse tutto.
- **`delete_collection` invalida i suoi alias**: dopo la cancellazione,
  `_read_alias_target` deve tornare `None`, non un alias appeso a una collection che non
  esiste più.

**Verificata la portanza**, perché un test che passa non prova ancora nulla: la stessa
delete verso un nome inesistente **solleva** (`UnexpectedResponse`), quindi il verde del
test dipende davvero dalla risoluzione dell'alias e non da un no-op silenzioso.

## Cosa resta aperto

- ~~**In CI quei cinque test non girano mai.**~~ **Chiuso il 2026-09-04** — vedi
  «A8, coda: la CI adesso li esegue» qui sotto.
- **`rollback` e `GC`** restano validati contro il fake per la parte di *logica locale*
  (puntatore `CURRENT`, insieme dei riferimenti dai manifest): lì non c'è semantica di
  Qdrant da falsificare, se non la `delete_collection` ora coperta.

## A8, coda: la CI adesso li esegue — e non può tornare a saltarli in silenzio

*Chiusura del residuo il 2026-09-04.*

`services: qdrant` nel job `test` di `.github/workflows/ci.yml`, immagine
**`qdrant/qdrant:v1.19.0`** — pinnata come ogni altra versione del repository e
**allineata al client** (`qdrant-client==1.19.0` in `uv.lock`): un server più nuovo del
client sarebbe una seconda variabile, e non è quella che questo job vuole misurare.

Il punto delicato non è avviare il servizio: è che **un job verde che salta tutto è
indistinguibile da un job verde che verifica**, ed è esattamente lo stato in cui questa
riga è rimasta per sei settimane. Tre meccanismi, ognuno contro un modo diverso di
ricadere lì:

| Meccanismo | Contro cosa |
|---|---|
| `VIBECRAFT_REQUIRE_QDRANT=1` nell'env del job → `_real_qdrant_client_or_skip` **solleva** invece di saltare | il servizio sparisce dal workflow, o non risponde: lo skip non è più «l'ambiente non ce l'ha» dove il servizio è **dichiarato** |
| `pytest -rs` in `scripts/ci.sh` | ogni skip residuo compare col **motivo**, non come un numero in fondo |
| passo dedicato che pretende `^5 passed` sui test `-k real_qdrant`, con una riga nel `$GITHUB_STEP_SUMMARY` | i cinque vengono cancellati, rinominati o disattivati uno per volta |

E un'attesa esplicita su `/readyz` prima della suite: l'immagine Qdrant non dichiara una
`HEALTHCHECK`, quindi «container avviato» non significa «porta che risponde», e senza
quella attesa una partenza lenta darebbe un rosso intermittente che assomiglia a un
difetto del codice.

**Un difetto trovato mentre lo verificavo, e sarebbe stato invisibile.** `pytest.ini` ha
già `addopts = -q`; `ci.sh` passava un secondo `-q`, cioè **`-qq`**, che sopprime *proprio*
la riga di riepilogo e l'elenco di `-rs`. Misurato: con `-q -rs` l'output di quei cinque
test finisce sulla barra di progresso (`.....  [100%]`) e **nient'altro** — il passo di
conteggio avrebbe cercato `^5 passed` in un output che non lo contiene mai, e avrebbe
fallito sempre, per la ragione sbagliata. Tolto il `-q` di troppo. È il tipo di errore che
questo intervento esiste per impedire, commesso mentre lo si impediva.

**Misurato su questa macchina**, contro un container `qdrant/qdrant:v1.19.0` pinnato
(porta throwaway, non quello di sviluppo), nelle tre direzioni che contano:

```
Qdrant giù,   senza la variabile  →  34 passed, 5 skipped   + "SKIPPED [5] … Qdrant non raggiungibile"
Qdrant giù,   VIBECRAFT_REQUIRE_QDRANT=1  →  5 failed        (il gate ha portanza: non passa per caso)
Qdrant su v1.19.0, come in CI     →  5 passed, 34 deselected  → il passo di conteggio trova "5 passed"
suite intera, Qdrant su + gate    →  1317 passed, 0 skipped, ruff pulito
```

La seconda riga è quella che conta davvero: senza di essa il primo meccanismo sarebbe una
dichiarazione d'intenti, non un gate.

## Il primo run reale, e cosa ha trovato

Eseguito il 2026-09-04 sul branch `ci/s3-qdrant-servizio-e-macos-nativo`. `docker` verde,
`macos-nativo` verde, **`test` rosso** — e non per Qdrant:

```
1 failed, 1316 passed in 87.86s
FAILED tests/test_reindex.py::test_index_rollback_succeeds_when_writer_lock_free
        HTTPException 404: Nessuna versione in database/versions/: nulla su cui fare rollback
```

**Il difetto è pre-esistente e non appartiene a questo intervento.** `git log -S` lo data:
`resolve_rollback_target` entra nella route col commit **`1044513` (S2)**, e quella funzione
risolve la versione leggendo il `database/versions/` **vero**. Il test si costruiva a mano il
proprio set di patch invece di passare dall'helper condiviso `_call_index_rollback` — che S2
aveva aggiornato — e quel duplicato è rimasto indietro. Restavano scoperti allo stesso modo
`assert_rollback_target_has_vectors` (chiamato con la stringa `"fake-qdrant-client"`, e
verde solo perché tollera le eccezioni) e `rollback_shares_collection_with_later_versions`.

Il punto che vale più del difetto: **una suite locale non poteva vederlo**. Su una macchina
di sviluppo `database/versions/` è popolata, quindi la funzione non patchata trovava versioni
vere e il test passava; su un checkout pulito non ce ne sono, e falliva. Riprodotto qui con un
plugin pytest usa-e-getta che ripunta `versions_root()` su una directory vuota: **stesso e
solo test**, gli altri rossi di quella simulazione sono suoi artefatti (scavalca i sandbox dei
test *end to end*, che le versioni se le creano davvero) e in CI infatti sono verdi.

**Correzione alla radice, non alla riga.** Aggiungere la patch mancante avrebbe lasciato in
piedi la duplicazione che l'ha causata — e le altre due funzioni scoperte. `_call_index_rollback`
accetta ora un `writer_lock=`, e il test passa da lì: chi vuole esercitare il lock **vero** su
un file di `tmp_path` non deve più rifarsi tutto il resto a mano, e la prossima chiamata
aggiunta alla route atterra in un posto solo. Verificata la portanza — il lock iniettato viene
invocato una volta col timeout patchato e il file di lock viene creato davvero: il test non è
diventato verde girando su un `nullcontext`.

Verificato in tre direzioni: checkout pulito simulato **verde**, questa macchina **verde**,
suite intera con Qdrant reale **1317 passed, 0 skipped**, ruff pulito.

**E `main` era già rossa per lo stesso difetto.** Run **#129** (che copre `1044513` e
`dffaa6a`, arrivati in un unico push) rosso alle 14:47; **#128**, su S1, era verde. Un'ora
esatta di ramo principale rotto, fino al merge delle 15:45 — e nessun alert, nessun check
obbligatorio, niente: il rosso è emerso perché la diagnosi *imponeva* la domanda, non perché
qualcosa l'abbia segnalato. **Il run su `main` dopo il merge è verde**, il che chiude la
catena all'indietro: la regressione di S2 era la causa *unica* del rosso di #129, non una
delle cause — prima era un'inferenza, ora è osservata.

Questa riga chiude «i test non esercitano Qdrant vero»; resta aperto un piano più su, **R16**
in `RESIDUI.md`: un gate che nessuno guarda e che non blocca nulla non è un gate nemmeno
quando funziona.

## Ciò che questa chiusura NON prova

- **Niente: l'intera catena è stata osservata.** Run **#131**, tutto verde, `test` in
  3m25s, e il riepilogo del run porta la riga che il passo di conteggio scrive:
  **«Qdrant reale: 5/5 test d'integrazione passati»**. Prima ancora, il run precedente
  aveva già dato la prova indiretta più forte — 1316 passed **senza un solo `SKIPPED`**,
  dove il servizio assente ne elencherebbe cinque. Restano fuori solo scelte dichiarate:
  un solo server (1.19.0, la versione del client), nessuna matrice.
- **Un solo server Qdrant, la versione del client.** Il job non prova la compatibilità con
  versioni diverse da 1.19.0: è una scelta, non una svista — la matrice costerebbe minuti a
  ogni push per un rischio che si materializza solo quando si alza il pin.

---

# A11 — trenta secondi, e il retrieval ne spiega mezzo

*Chiusura del 2026-09-04.*

## I due numeri della riga non erano riproducibili

La riga misurava `/ask` a **`top_k=50`**: 96,4 s a freddo, 28,6 s a caldo. Quel `top_k`
oggi il server lo **rifiuta** — `api/models.py` lo limita a `le=20`, ed è un vincolo di
correttezza (finestra di contesto), non di carico: è la chiusura di A1, arrivata dopo
questa riga. Chiunque provasse a riprodurre la baseline otterrebbe un 422.

Rimisurato al `top_k` che la console usa davvero (5, il default del campo), processo
appena avviato e cache di `/ask` vuota:

| | valore |
|---|---|
| `p50` totale | **24,1 s** |
| `p95` totale | **32,0 s** |
| max osservato | 33,7 s |
| media retrieval | 0,50 s |
| media generation | 22,2 s |

Il 96,4 s a freddo non si ripresenta: la prima run di oggi, a processo freddo, ha dato
30,1 s di media su 3 query. L'ordine di grandezza dell'attesa "a caldo" invece regge —
la riga aveva ragione su ciò che conta, cioè che si aspettano circa trenta secondi.

## La scoperta non è il p95, è il denominatore

**Il retrieval pesa 0,50 s su 22,7 di media: il 2,2%.** Dense + sparse + fusione per
rango + rerank ColBERT + espansione sul grafo — tutto l'apparato che questo repository
implementa e che l'audit ha passato giorni a correggere — costa mezzo secondo. Il
**97,8%** è il forward pass del modello locale.

È il numero da rileggere prima di ottimizzare qualsiasi cosa qui dentro: qualunque
lavoro che non tocchi il modello o l'hardware ha un tetto teorico del 2,2%. Senza
questa misura, "la console è lenta" sarebbe quasi certamente finita in un refactor del
ranking.

## Lo strumento c'era, e su `/ask` guardava dalla parte sbagliata

`scripts/bench.py` esiste dal F3, calcola `p50`/`p95` e li usa — ma su
`GET /api/retrieve`. Su `POST /ask` girava su **tre query fisse** e riportava tre
**medie**. Con n=3 il p95 non è una quantità calcolabile; e la media è precisamente il
numero che nasconde ciò che l'utente subisce. La sezione più lenta del sistema era
l'unica misurata con lo strumento meno adatto.

Le tre query erano congelate per una ragione scritta e legittima: essere confrontabili
fra run, a differenza del golden-set che cresce. Ma **`eval/results/` non conteneva
nessun `bench_*.json`** — nessuna run precedente da confrontare. La comparabilità
proteggeva un confronto che non era mai avvenuto, al prezzo dell'unico numero utile.

`bench_ask` ora pesca `n` casi dal golden-set (stessa sorgente e stessa numerosità di
`bench_retrieve`, il suo gemello) e riporta `p50`/`p95`/`max` del totale **lato server**,
accanto alle medie del breakdown, che restano. I percentili ripiegano sulla misura
client se la risposta non porta l'oggetto `latency`: sparire proprio nel caso in cui
servirebbero di più sarebbe il comportamento peggiore.

Il p95 su 10 campioni sta di fatto sul massimo osservato. È un limite del **campione**,
non della misura, ed è dichiarato: ogni query costa una generazione completa, quindi
alzare `n` allunga il bench in proporzione.

## Il feedback: un numero che sale

L'impatto dichiarato dalla riga — «un'attesa di 30 s senza feedback è indistinguibile
da un blocco» — non lo chiude una misura. Il loader era tre pallini animati e la scritta
«Elaborazione in corso…»; il tempo trascorso compariva **solo dopo**, nel badge
`⏱ 28.81s` accanto alla risposta. Un'animazione in loop non distingue un lavoro in corso
da un processo appeso: è la stessa immagine nei due casi.

Ora il loader conta i secondi. Verificato dal vivo sulla console (`http://127.0.0.1:8000`,
Qdrant e Ollama attivi): il contatore sale (11 s → 14 s nella stessa attesa), si azzera
alla risposta e **non lascia l'intervallo appeso** — controllato tre secondi dopo la fine,
resta vuoto. Il badge finale ha segnato 28,81 s, coerente con il p50/p95 misurati.

## Cosa NON è stato fatto, e perché è scritto qui

**Lo streaming incrementale non c'è.** È l'unico modo di abbassare il tempo *percepito*
sotto i trenta secondi, e la riga lo offriva come alternativa alla misura («o feedback
incrementale»). Costerebbe il contratto di `/ask`: oggi la risposta è un JSON unico che
porta risposta, contesto grafo, archi, punteggi di ranking e latenze, e il frontend li
consuma insieme. Trasformarlo in un flusso vuol dire due canali (token in streaming +
payload strutturato alla fine), un secondo percorso di errore e la cache di `/ask` da
ripensare. Non è un lavoro da nascondere dentro la chiusura di una riga di audit.

**Nessun gate sulla latenza.** Il bench resta una misurazione, exit code 0, come dice il
suo stesso docstring; e un p95 di 10 campioni non regge una soglia bloccante. Il rischio
noto è quello che A2b ha già mostrato altrove: un numero dichiarato che nessuno rilegge
invecchia. Qui la protezione è debole per costruzione — la baseline in README ha data e
macchina accanto, così un lettore vede subito quando è vecchia.

---

# A15 — il difetto era reale, la sua descrizione no

*Chiusura del 2026-09-04.*

## Sei piattaforme, misurate invece che dedotte

La riga diceva: il pin CUDA senza marcatore blocca l'installazione nativa «su macOS, ARM
e macchine CPU-only». Tre affermazioni, nessuna verificata — e non serviva un Mac per
verificarle: `uv sync --frozen --dry-run --python-platform <p>` risolve per una
piattaforma arbitraria dalla macchina che si ha sotto mano.

| Piattaforma | Prima | Dopo |
|---|---|---|
| Linux x86-64 | ✅ `2.13.0+cu126` | ✅ invariato |
| Linux ARM64 | ✅ `2.13.0+cu126` | ✅ invariato |
| Windows x86-64 | ✅ `2.13.0+cu126` | ✅ invariato |
| macOS Apple Silicon | ❌ | ✅ `2.13.0` (PyPI) |
| macOS Intel | ❌ | ❌ (a monte) |
| Windows ARM64 | ❌ | ❌ (a monte) |

**Due dei tre casi della riga non erano rotti.** *ARM* è troppo largo: l'indice cu126
pubblica `manylinux_2_28_aarch64`, quindi **Linux ARM64 sincronizzava già**. *CPU-only* è
proprio un'altra cosa: su x86-64 la wheel CUDA si installa e **gira**, con
`torch.cuda.is_available()` a `False` — pesa 4 GB inutili, non impedisce nulla. E la riga
**ometteva** l'unico altro caso davvero bloccato, Windows ARM64.

Ciò che restava vero è il caso che conta di più in pratica: **macOS**.

## La correzione, e ciò che ha fatto emergere

Il marcatore non è difensivo, è la trascrizione dell'elenco di wheel che `uv.lock`
contiene già per `torch 2.13.0+cu126`: `manylinux_2_28_x86_64`,
`manylinux_2_28_aarch64`, `win_amd64`. Nient'altro. Fuori di lì torch arriva da PyPI.

Rifatto il lock, però, è comparso un problema che non c'era prima della correzione: con
`torch` senza pin di versione, uv risolve **ogni ramo per conto suo** e macOS finiva su
`2.14.0` mentre tutti gli altri restavano su `2.13.0`. È esattamente la deriva che il
Dockerfile documenta di aver già subito una volta («il lock diceva 2.13.0 e l'immagine
montava 2.14.0+cpu»): l'avrei reintrodotta su un'altra piattaforma mentre chiudevo un
riscontro di portabilità. `torch` è ora pinnata a `2.13.0` — verificato **prima** che PyPI
abbia la wheel corrispondente (`torch-2.13.0-cp314-cp314-macosx_14_0_arm64.whl`),
altrimenti il pin avrebbe solo spostato il problema.

## Due piattaforme restano impossibili, e non per colpa nostra

macOS Intel e Windows ARM64 falliscono anche dopo: **PyTorch non pubblica quelle wheel da
nessuna parte**, né sull'indice CUDA né su PyPI — per la 2.13.0 le uniche wheel macOS sono
`macosx_14_0_arm64`. Nessuna configurazione in questo repository può crearle. Il fatto è
ora **scritto** nel README di root, in una tabella con la riga rossa e la ragione accanto,
invece di essere un fallimento che l'utente scopre da sé.

Sottigliezza registrata perché costa mezz'ora a chi la incontra: la wheel richiede
`macosx_14_0`, quindi il dry-run per `aarch64-apple-darwin` fallisce lo stesso finché non
si dichiara `MACOSX_DEPLOYMENT_TARGET=14.0` — uv assume un target 13.0 conservativo. Su un
Mac vero il target lo legge dall'interprete: era un artefatto della simulazione, non un
difetto.

## Il test è offline, e verificato contro la configurazione vecchia

Il difetto viveva in due file di configurazione, e l'unico modo di provarlo era eseguire
uv contro la rete — cioè niente che una suite possa fare. `tests/test_torch_platform_pin.py`
legge `pyproject.toml` e `uv.lock` con `tomllib` e fissa l'invariante: l'indice CUDA è
applicato **solo** dove le sue wheel esistono, esiste una sorgente alternativa che le wheel
macOS ce le ha davvero, e i due registri non divergono di versione.

Rimessa la configurazione vecchia, **3 test su 5 falliscono**. I due che restano verdi
leggono `uv.lock`, che in quella prova non era stato ripristinato: è coerente, non una
svista. Un test dice cosa fare invece di limitarsi a fallire — se un domani cu126
pubblicasse wheel macOS, il messaggio è che il marcatore può essere allargato.

## Ciò che questa chiusura NON prova

- ~~**Nessuna installazione reale su un Mac.**~~ **Affrontato il 2026-09-04** con il job
  `macos-nativo` — vedi «A15, coda» qui sotto. Il limite non è più «qui un Mac non c'è»:
  è che il job non è ancora stato eseguito.
- **La macchina CPU-only x86-64 continua a scaricare 4 GB di CUDA** che non userà.
  Sincronizza e funziona, quindi non è questo riscontro; sceglierne la build CPU sulla
  *stessa* piattaforma richiederebbe extra in conflitto (`uv sync --extra cpu`), cioè
  cambiare il comando di installazione per tutti. Per quel caso esiste già il target `cpu`
  del Dockerfile.
- **Immagine Docker ricostruita per sicurezza**, perché il re-lock tocca il file da cui il
  target `cpu` deriva la sua lista di esclusioni CUDA: 129 pacchetti, venv 2,2 GB,
  `torch 2.13.0+cpu`, `cuda? False` — identica a quella di prima del cambio.

## A15, coda: un Mac vero, non più un dry-run

*Chiusura del residuo N6 il 2026-09-04.*

Nuovo job **`macos-nativo`** in `.github/workflows/ci.yml`, su **`macos-15`** — che è
arm64 e **non deprecato** (verificato nel README di `actions/runner-images`, dove
`macos-14` porta il badge *deprecated*). Fa `uv sync --frozen` in `rag/` e poi importa
torch, ne stampa versione e backend, e **calcola**: un matmul 64×64 di cui verifica il
risultato. Importare non basta — una wheel per l'architettura sbagliata importa e poi
esplode alla prima operazione, ed è precisamente il divario fra il dry-run e «torch gira»
che questo residuo nominava.

Due asserzioni oltre al calcolo, entrambe su ciò che A15 ha corretto: che la versione
**non** contenga `+cu` (su macOS torch deve arrivare da PyPI, non dall'indice cu126), e
che il matmul torni il valore giusto.

**La premessa si verifica prima, e si legge dal log.** La wheel è `macosx_14_0_arm64`: su
un runner più vecchio il job fallirebbe *per la piattaforma*, non per ciò che sta provando,
e quel rosso verrebbe letto come «l'installazione su macOS non funziona». Il primo passo
del job stampa `sw_vers -productVersion` e `uname -m` e **fallisce esplicitamente** con il
motivo giusto se l'architettura non è `arm64` o la major è `< 14`. Stampato anche il
`sysconfig.get_platform()` dell'interprete *prima* del sync: il tag di piattaforma
dell'interprete è ciò che decide se quella wheel è accettabile, ed è l'artefatto che A15
aveva incontrato nel dry-run (`MACOSX_DEPLOYMENT_TARGET` conservativo). Se la risoluzione
fallisse, il motivo si legge invece di doverlo indovinare.

**Separato dal job `test`**: qui non servono né il corpus né i servizi, e il ciclo
principale non deve aspettare un runner macOS per dire se il codice è a posto.

### Il costo: stimato male, misurato, corretto

L'avevo limitato a `main` + `workflow_dispatch` su una stima — repository privato, runner
macOS fatturati **10× i minuti Linux**, ~5-8 minuti reali per scaricare il grafo delle
dipendenze, quindi **~50-80 minuti fatturati** a esecuzione: il costo dominante del
repository. Il primo run reale dice **34 secondi**, cioè ~6 minuti fatturati, contro i
**2m31s** del job `test` e i **3m35s** di `docker`.

La stima era sbagliata per una ragione che avrei dovuto vedere: su macOS il lock esclude
**tutte** le wheel `nvidia-*` — è esattamente ciò che fa il marcatore di piattaforma
introdotto da A15 — cioè i ~2,5 GB che dominano il download su Linux. Avevo trasportato il
peso della build CUDA su una piattaforma che per costruzione non la installa.

Restrizione rimossa: il job gira su **ogni push**, come gli altri due. Limitarlo non
proteggeva da un costo che non esiste, e ritardava fino al merge la scoperta di una
rottura del lock — che è il solo evento che questo job serve a intercettare.

### Cosa dice il log, riga per riga

Due run, entrambi verdi (34s e 36s). Il secondo:

```
runner: macOS 15.7.9 su arm64          ← premessa macosx_14_0 soddisfatta, e verificata dal job
platform tag: macosx-15.0-arm64        ← il tag dell'interprete accetta la wheel
torch      : 2.13.0                    ← da PyPI, senza "+cu": il marcatore di A15 fa il suo lavoro
cuda       : False
mps        : True (built: True )
matmul su  : mps -> 262144.0           ← 64³, il valore atteso
```

**Il matmul è girato su Metal, non su CPU.** Non me l'aspettavo da un runner virtualizzato:
il job non lo pretendeva (sceglie `mps` solo se disponibile), ma il risultato è che N6 è
chiuso più di come era stato formulato — non «torch importa su un Mac», ma «torch calcola
sull'acceleratore di quel Mac».

I numeri accanto a quelli di Linux, che spiegano il costo meglio di qualsiasi stima:
**130 pacchetti** contro 149, e **torch 106,1 MiB** contro 804,7 MiB. Le 15 wheel
`nvidia-*`/`triton`/`cuda-*` che mancano pesano da sole ~2,5 GiB.

### Ciò che questa coda NON prova

- **Non prova macOS Intel**, che resta impossibile a monte (PyTorch non pubblica quelle
  wheel).
- **Prova il percorso con la CPython di sistema, non con una gestita da uv.** Il log dice
  `Using CPython 3.14.7 interpreter at: /opt/homebrew/opt/python@3.14/bin/python3.14`: uv
  ha trovato il 3.14 di Homebrew nell'immagine del runner, e da lì il tag è
  `macosx-15.0-arm64`. È **il caso fortunato**. Se l'immagine smettesse di spedire quel
  Python — o se un utente su Mac partisse da una CPython gestita da uv — il tag verrebbe dal
  `MACOSX_DEPLOYMENT_TARGET` con cui quella build è compilata, che è conservativo: è
  esattamente l'artefatto che A15 aveva incontrato nel dry-run, e lì una wheel
  `macosx_14_0` verrebbe rifiutata. Il job stampa il tag proprio perché quel giorno il
  fallimento sia leggibile invece che misterioso, ma **non copre quel ramo**.
- **Il tempo non dipendeva da una cache calda.** Vale la pena dirlo perché sarebbe la
  spiegazione comoda dei 34s: il log mostra `Cache Size: ~0 MB (1610 B)` e poi il download
  effettivo di tutti e 130 i pacchetti. L'installazione è reale.

---

# A6 — verificare la chiusura invece di riscrivere l'etichetta

*Riallineamento del 2026-09-04.*

Era l'ultima riga ancora etichettata `FRAGILE`, mentre il paragrafo di sintesi e una
sezione intera in fondo a questo documento («A6 — chiuso») la davano chiusa in Run B. La
strada comoda era correggere l'etichetta. Rileggere invece **cosa** quella chiusura aveva
prodotto ha trovato un difetto dentro la chiusura stessa.

## I numeri della riga non erano più veri

«26 `.md` su disco vs 11 tracciati». Oggi: **23 su disco, 14 tracciati**, 9 non tracciati —
6 output della pipeline (`change_log.md`, cinque `*-canvas-review.md`) e 3 spec locali del
progetto ospitante. Sono gli stessi 9 che la chiusura di Run B descrive: stanno nell'indice
per ragioni legittime e non devono entrare nel repository. La prima strada del criterio (un
clone pulito riproduce le metriche) resta quindi impraticabile per costruzione, ed è la
seconda ad essere stata percorsa: **dichiarare** il corpus accanto ai numeri.

## Il difetto: il numero dichiarato non era il corpus misurato

`observe_docs_git_divergence()` costruiva i suoi insiemi da *tutti* i file sotto `docs/` —
`git ls-tree` per i tracciati, `rglob("*")` per il disco. L'indicizzazione, invece, enumera
filtrando su `DOC_EXTS` (`build_index` e `plan_incremental`, stesso criterio in entrambe).

Due perimetri diversi per la stessa cosa, e la differenza finiva **in evidenza sul report**:

```
prima:  misurato su: 16 documenti tracciati · +9 NON tracciati …
dopo:   misurato su: 14 documenti tracciati · +9 NON tracciati …
```

I due di troppo sono i `.gitkeep` che tengono in piedi la struttura delle cartelle. Non
sono documenti, l'indice non li legge mai, e il campo `corpus` esiste **esattamente** per
dire su quale corpus un numero di qualità è stato misurato: dichiararne 16 quando erano 14
è il difetto che quel campo doveva prevenire.

Ed è una trappola già vista: la riga originale di A6, un mese fa, annotava per conto suo
che «i 13 path di `git ls-files docs` includono 2 `.gitkeep`». L'audit l'aveva notata; la
correzione ci è caduta dentro.

Il perimetro è ora `DOC_EXTS` su entrambi i lati. `untracked` ne guadagna anche in
precisione: un `.png` lasciato in `docs/` non è divergenza del corpus, perché nessun
retrieval lo vedrà mai.

**Verificato dal vivo**, non solo a unit test: `python -m eval.run --no-save` contro il
server reale stampa `misurato su: 14 documenti tracciati · +9 NON tracciati`, con
`recall@2 = 0.873` (PASS). Il test nuovo — un `.gitkeep` tracciato più un `.png` non
tracciato — è stato verificato contro il codice vecchio: `tracked` valeva 2.

## Cosa resta aperto, e non è un difetto di codice → **CHIUSO 2026-09-04 (S5)**

Il **sottoinsieme avversariale era a 4 casi con 2 soli distrattori**. Non era una
regressione: era il residuo dichiarato dalla chiusura di Run B, quando il caso 4 perse il
marcatore `adversarial` perché il suo distrattore progettato (`intent_synonym_mapping.md`,
peso 0.50) era stato rimosso col dominio dismesso, e sulla baseline tracciata **non
esisteva** un sostituto a bassa autorità che parlasse di LLM e dati personali. Restituirgli
ampiezza era una decisione sul **corpus**.

Il documento è stato scritto ed è ora in baseline: **5 casi, 3 distrattori distinti**.
Ma la parte che vale la pena leggere è che la strada indicata dal residuo *non ha
funzionato come previsto*, ed è la misura ad averlo detto — sezione S5 in fondo a questo
documento.

Vale la pena rileggerlo accanto ad A3: il `recall@1` avversariale **0.0%** che si legge
ancora nel report non è un difetto da chiudere, è la misura che fa il suo lavoro su un
contrasto che il corpus attuale rende stretto.

---
---

# S5 — il corpus cambia i numeri: prima, dopo, e cosa NON è comparabile

*Eseguita il 2026-09-04. Chiude **R7** e **R8**, prepara **R13**.*

Questa sessione tocca il corpus indicizzato, quindi i suoi numeri non sono un aggiornamento
dei precedenti: sono una serie nuova. Sotto ci sono entrambe le misure e — la parte che di
solito manca — la **decomposizione** di quale delle due modifiche ha mosso cosa.

## Le due modifiche, e perché vanno separate

| | Cosa è cambiato | Cosa può muovere |
|---|---|---|
| **Corpus** | `change_log.md` bonificato · un documento informativo nuovo, `inferenza_locale_o_remota.md` | tutte le metriche |
| **Strumento** | golden set 55 → 56 casi (un avversariale aggiunto) | solo il golden set classico e il sottoinsieme |

Misurarle insieme avrebbe prodotto un delta illeggibile. La decomposizione è più sotto.

---

## R7 — il riferimento morto è storia, gli archi del frontmatter no

`docs/00_meta_governance/change_log.md`, non tracciato da git (backup preso in
`docs.local-backup-20260904T150929/`, mai `rm`). Verificati tutti e tre i riscontri del
residuo, e trovato un quarto che il residuo non nominava.

**1. `project:`** — `"VibeCraft — Sistema di Gestione Eventi Aziendali"` → `"cross-project"`,
la convenzione della baseline.

**2. Le 3 righe contaminate** (misurate: righe 4, 60, 75). §1 vincolava «le logiche di
business delle risorse `RICHIESTA` ed `EVENTO` … il `BUDGET_ANNUO`» — entità che non
esistono più; [REGOLA-DEV-02] chiedeva «l'autore **HR** o tecnico». Riscritte al perimetro
reale (contratti di sicurezza, regole enforceable, struttura del frontmatter).

**3. Il riferimento morto di riga 98 — né ripuntato né rimosso, e la ragione è il punto.**

`spec_notifications_2.4.md` non esiste. Ma la prima cosa che la verifica ha trovato è che
non è **uno**: nella voce «Versione 1.1.0» sono 13 path su 15 a non esistere, e nella
«1.0.0» altri 4. Il residuo ne nominava uno perché uno ne aveva controllato.

Le due strade ovvie sono entrambe sbagliate, e per ragioni diverse:

- **Ripuntarlo a un documento esistente** significherebbe dichiarare che una release del 13
  luglio ha toccato un file che non ha toccato. [REGOLA-DEV-02] — scritta in questo stesso
  file — impone «l'elenco esatto dei file modificati» e nomina il proprio failure mode:
  «perdita della correlazione storica». Un link morto è visibilmente rotto; un link
  sbagliato è invisibilmente falso, ed è peggio proprio in un documento di governance, che
  esiste per essere la prova di cosa è successo.
- **Cancellare la riga** sarebbe arbitrario: 13 righe su 15 hanno lo stesso difetto, e
  toglierne una sola perché un residuo l'aveva nominata lascerebbe il registro *meno*
  coerente di come l'ha trovato.

Quello che un change log fa quando qualcosa cambia è **registrarlo**. Aggiunta la voce
mancante — `### Versione 2.0.0 (04 Settembre 2026)`, la dismissione del dominio che B1 aveva
eseguito senza mai scriverla nel registro che esiste per riceverla — e una nota di lettura
in testa a §3 che dice che le voci precedenti elencano file non più nel corpus e vanno lette
come storia, non come riferimenti risolvibili. Il record resta intatto e nessuno può più
scambiare un path del 2026-07 per uno vivo.

**4. Il quarto riscontro, che il residuo non aveva: 12 archi `CONTIENE` verso il nulla.**

Il frontmatter dichiarava 13 relazioni `CONTIENE`. Verificato sul grafo caricato, prima
della correzione: **12 target su 13 non risolvono**, e `add_frontmatter_edges`
(`core/chunking.py:217`) non li scarta — `if target not in G: G.add_node(target,
type="entity")`. Cioè 12 documenti fantasma nel grafo, con `nature: curated` e
`reliability: 0.9`: il livello di fiducia riservato a ciò che un autore ha dichiarato a
mano.

Qui la decisione è opposta a quella di §3, e la distinzione è tutta la sostanza di R7:

> §3 è un **ricordo** e non si riscrive. Un arco del frontmatter è un'**asserzione sul
> presente**, ricalcolata a ogni build. Un `CONTIENE` verso un documento che non esiste non
> è storia conservata male: è una cosa falsa detta oggi al grafo.

Rimossi i 12. Il tredicesimo (`spec-graph-rag-ingestion-v1.1`) era un caso terzo ancora: il
documento **esiste**, il `node_id` no — la spec dichiara `v2.0`. Ripuntato, perché ripuntare
a un target esistente è legittimo quando l'asserzione è sul presente.

Effetto misurato sul grafo (full rebuild):

| | prima | dopo |
|---|---|---|
| nodi | 755 | 751 |
| archi | 929 | 927 |
| fantasmi `spec-*-v1.0` | 12 | **0** |

I 4 nodi in meno sono il saldo fra 12 fantasmi rimossi e 8 nodi (1 documento + 7 sezioni)
del documento nuovo di R8.

> **Residuo aperto, non chiuso qui:** `graph_rag_ingestion_strategy.md` — che **è tracciato**
> — dichiara lo stesso `spec-graph-rag-ingestion-v1.1`, quindi il nodo fantasma sopravvive
> con un solo arco entrante invece di due. È lo stesso difetto in un file della baseline, e
> toccarlo esce dal perimetro di R7. Registrato come **R18** in RESIDUI.md.

---

## R8 — il documento nuovo c'è, e la strada che il residuo indicava non ha funzionato

**Scritto:** `docs/04_knowledge_informative/inferenza_locale_o_remota.md` — `METHODOLOGY`,
`authority: 0.40` **dichiarata** (sotto il peso di classe 0.50), tracciato in git perché è
parte dello strumento di misura, come i tre distrattori portati in baseline in Run B.

Il tema è scelto per essere davvero scoperto, non per comodità: `Ollama`, `inferenza`,
`modello locale`, `on-premise`, `GPU`, `quantizzazione` hanno **0 occorrenze** in tutto
`docs/`. Il documento dichiara di sé, come fa `graph_rag_ingestion_strategy.md`, di non
essere fonte di un vincolo, e rimanda a `safeguards_security.md` per la norma.

### Poi la misura ha smentito la premessa del residuo

Il residuo prescriveva: scrivi il documento, poi rimarca il caso 4
(«posso mandare la motivazione scritta dal dipendente a un LLM remoto») con quel
distrattore. Misurato dopo il rebuild, sul ranking di produzione (`GET /api/retrieve`, k=12):

```
atteso  safeguards_security § Privacy e Confine   → rango 2
nuovo   inferenza_locale_o_remota                 → rango 6
```

**Su quella formulazione non c'è alcun contrasto da esercitare.** Il breakdown dice perché,
e non è un fallimento del documento:

| | dense_rank | dense | ColBERT | authority |
|---|---|---|---|---|
| `inferenza_locale_o_remota § 5` | **2** | 0.4996 | 0.494 | 0.40 |
| `safeguards_security § Privacy e Confine` | 6 | 0.4693 | **0.5032** | 0.98 |

Sulla similarità **densa** il documento informativo vince davvero — è il secondo risultato,
contro il sesto della norma. Perde sul **ColBERT**, che è ciò su cui l'ordine finale è
costruito (ColBERT × autorità). E perde per una ragione strutturale: su *questa* domanda la
fonte normativa è **anche** il miglior match lessicale, perché §5 di `safeguards_security`
nomina già «modelli LLM remoti», «dati personali» e «motivazioni» nella tabella delle
categorie PII. Un documento che vincesse quella domanda andrebbe scritto come **esca**, non
come contenuto — e il golden set vieta esattamente questo.

Rimarcare il caso 4 comunque avrebbe fatto **passare** il caso e gonfiato la recall del
sottoinsieme: è il difetto per cui il marcatore era stato tolto. Non è stato fatto.

### Cosa è stato fatto invece: cercare la formulazione, e misurarla

Sette domande candidate sullo stesso tema, misurate una per una. Rango del distrattore e
rango dell'atteso:

| Domanda | dist. | atteso | esito |
|---|---|---|---|
| «posso mandare la motivazione scritta dal dipendente a un LLM remoto» | 6 | 2 | nessun contrasto |
| «che cosa rischio a mandare fuori i dati personali degli utenti» | 5 | 2 | nessun contrasto |
| «conviene tenere il modello in locale o posso usarne uno ospitato» | 1 | 9 | **scartata**: qui la fonte giusta *è* il documento informativo |
| «cosa esce dalla mia macchina quando chiedo aiuto a un modello ospitato» | 1 | — | **scartata**, stessa ragione |
| «il provider dell'LLM quanto tempo conserva i prompt che gli mando» | 1 | 5 | **scartata**: la retention non è normata in `safeguards` |
| «posso incollare nel prompt il testo che ha scritto un utente» | 1 | 4 | **scartata**: quasi verbatim una frase del documento nuovo, sarebbe stata un'esca |
| **«posso usare un servizio di inferenza remoto per il debug di un record reale»** | **1** | **2** | **tenuta** |

Le scartate sono la parte istruttiva: un distrattore che vince *avendo ragione* non è un
caso avversariale, è il retrieval che funziona. Il caso tenuto ha il vincolo altrove —
«un record reale» è PII reale verso un endpoint esterno, cioè [SAFEGUARD-SEC-04] — e il
margine 1→2 è lo stesso, stretto, dei casi avversariali originali.

**Risultato:** il sottoinsieme torna a **5 casi con 3 distrattori distinti**. Il caso 4 resta
un caso normale, con la misura di oggi annotata accanto, perché la prossima persona che legge
«perché non l'hanno rimarcato» trovi il numero e non un'opinione.
`test_casi_avversariali_hanno_matcher_validi` vede il caso nuovo e passa.

---

## Prima e dopo — e cosa non è comparabile

Full rebuild + promozione: `CURRENT → v20260904T151925`, alias Qdrant scambiato.
Chunk **160 → 167** (+7, il documento nuovo). Eval-gate: `recall@2=0.875 ≥ 0.75 (56 casi)` —
promozione consentita.

### Golden set classico

| Metrica | Prima (55 casi, `v20260904T092228`) | Dopo (56 casi, `v20260904T151925`) |
|---|---|---|
| recall@1 | 63.6% | 62.5% |
| recall@2 | 87.3% | **87.5%** |
| recall@5 | 98.2% | 98.2% |
| recall@10 | 100.0% *(satura)* | 100.0% *(satura)* |
| source_in_top3 | 94.5% | 94.6% |
| MRR | 0.791 | 0.786 |

**Questi due numeri non sono confrontabili**, ed è il motivo per cui la decomposizione più
sotto esiste.

### Sottoinsieme avversariale

| Metrica | Prima (4 casi) | Dopo (5 casi) |
|---|---|---|
| recall@1 | 0.0% | 0.0% |
| recall@2 | 75.0% | 80.0% |
| source_in_top3 | 100.0% | 100.0% |
| MRR | 0.458 | 0.467 |
| distrattori distinti | 2 | **3** |

`recall@1 = 0.0%` invariato, e con un caso in più: il caso nuovo fallisce a k=1 **per
costruzione** — è ciò che significa averlo scelto misurando. Leggere quello 0.0% come
peggioramento sarebbe l'errore che A3 ha già chiarito.

### La decomposizione: il corpus non ha mosso nulla, il golden set sì

Riesecuzione delle metriche sui **soli 55 casi condivisi** fra le due run, contro l'indice
nuovo:

| Metrica | 55 casi, indice vecchio | 55 casi, indice nuovo | Δ |
|---|---|---|---|
| recall@1 | 0.6364 | 0.6364 | **0.0000** |
| recall@2 | 0.8727 | 0.8727 | **0.0000** |
| recall@5 | 0.9818 | 0.9818 | **0.0000** |
| source_in_top3 | 0.9455 | 0.9455 | **0.0000** |
| MRR | 0.7909 | 0.7909 | **0.0000** |

**Nessun caso ha cambiato rango. Nemmeno uno.** Quindi tutto il delta della tabella classica
— i −1.1 punti di recall@1, i +0.2 di recall@2, i −0.005 di MRR — è il 56° caso, non il
corpus. Detto altrimenti: bonificare `change_log.md` e aggiungere un documento non ha
migliorato né peggiorato il retrieval sulle domande già in misura. Era il risultato più
probabile e non era garantito: era proprio l'aggiunta al corpus lo scenario che A18 aveva
indicato come pericoloso.

### Multihop — qui il corpus ha mosso, e verso il basso

La suite multihop **non è cambiata** (14 casi, gli stessi), quindi il suo delta è corpus puro:

| Metrica | Prima | Dopo | Δ |
|---|---|---|---|
| recall media A | 0.896 | **0.854** | **−0.042** |
| A riusciti | 10/14 | **9/14** | −1 |
| B exact | 6/6 | 6/6 | — |
| gap retrieval→grafo | 1 | 1 | — |

Passa (`min_recall: 0.85`) **con 0.004 di margine**. I due casi che si sono mossi:

- «quali documenti esistono nel corpus?» 0.55 → 0.45. È la misura, non un difetto: il corpus
  è cresciuto e un top-10 ne copre una frazione minore. Stessa lettura di A4.
- «cosa devo fare quando modifico un documento della knowledge base?» 1.00 → **0.50**.
  Verificato sul ranking: `policy_versionamento § Regole di Gestione` resta a rango 3, ma
  `spec_graph_rag_ingestion § Aggiornamento Incrementale` **esce dal top-10**, spinto fuori
  da `change_log.md`, che ora occupa i ranghi 6 e 9. La causa è la bonifica stessa: §1
  riscritto dice adesso che «ogni modifica … alle regole enforceable dei documenti normativi
  o alla struttura del frontmatter deve essere registrata in questo file», e per la domanda
  «cosa devo fare quando modifico un documento» quella è una risposta **pertinente**. Il
  ranking non ha sbagliato; la catena a due documenti non ci sta più in dieci.

**Questo è un residuo nuovo e va detto, non assorbito:** la soglia multihop ha 0,4 punti di
margine, e la spinta che li ha consumati viene da un documento **non tracciato**. Registrato
come **R19**.

---

## R13 — cinque candidati misurati, nessuno aggiunto

`recall@2` sta a 0.875 con soglia 0.75. Il giorno in cui saturasse non resta un k più basso:
l'unica strada è estendere il golden set con casi che il sistema **sbaglia**. Sceglierli
quel giorno significa sceglierli per far scendere un numero — quindi sono stati cercati oggi,
misurati, e lasciati fuori.

Quattordici domande candidate misurate contro l'indice `v20260904T151925` (k=10). Le cinque
qui sotto sono quelle che **falliscono a k=2** e la cui fonte attesa regge un giudizio umano
(le altre nove passano, o non hanno una fonte attesa difendibile — su una, «una spec vecchia
di due anni vale ancora», il giudizio *mio* era sbagliato, e per questo non è in elenco):

| # | Domanda | Fonte attesa | Rango | Chi vince al suo posto |
|---|---|---|---|---|
| C1 | «il modello ha scritto codice sbagliato, di chi è la responsabilità» | `vibe_coding_workflow` § Protocollo Human-in-the-Loop | 4 | `safeguards_security` § Concorrenza — fuori tema |
| C2 | «come faccio a sapere se il grafo è disallineato rispetto ai documenti» | `spec_graph_rag_ingestion` § Aggiornamento Incrementale | **assente dal top-10** | `policy_versionamento` § 1 |
| C3 | «il log di una API può contenere l'indirizzo email dell'utente» | `observability_standards` § Confine di Privacy | 5 | `spec_tech_logic_agent` — **non tracciato** |
| C4 | «quanto deve durare al massimo una funzione prima di spezzarla» | `coding_standards` § Metriche Strutturali e Limiti | 3 | `testing_strategy` § 0 |
| C5 | «posso mandare uno stack trace di produzione a un assistente di coding» | `safeguards_security` § Privacy e Confine | 8 | `spec_tech_frontend` — **non tracciato** |

Cosa li rende utili, oltre al fatto che falliscono:

- **C4 è la riformulazione colloquiale di un caso che già esiste** e che passa a rango 1
  («qual è la lunghezza massima ammessa per una funzione»). Stesso fatto, stessa fonte,
  formulazione da persona invece che da indice: passa a 1 in un caso e fallisce a 3
  nell'altro. È il divario che il golden set attuale non misura affatto.
- **C2 è lo stesso chunk** che esce dal top-10 nella catena multihop regredita qui sopra:
  due strumenti diversi indicano la stessa sezione come la più fragile del corpus.
- **C3 e C5 sono da aggiungere solo insieme alla decisione su A6**: il documento che li batte
  è non tracciato, quindi in CI il caso misurerebbe qualcosa di diverso da qui — è
  esattamente il difetto che rese le metriche avversariali reversibili col checkout.

**Non aggiunti.** Servono il giorno in cui il margine si chiude, e servono con la loro
misura di oggi accanto, per poter dire se un futuro fallimento è il sistema o la deriva
del corpus.

---

## Verifica

- `ruff check .` → `All checks passed!`
- Suite completa: **1318 passed**, 0 skipped (Qdrant e Ollama accesi).
- `test_casi_avversariali_hanno_matcher_validi`: verde con il caso nuovo — 56 casi,
  5 avversariali, 3 distrattori distinti, tutti esistenti nel corpus.
- Eval-gate sul full rebuild: `recall@2=0.875 ≥ 0.75 (56 casi)` — promozione consentita,
  `CURRENT → v20260904T151925`, alias Qdrant spostato.
- Provenienza dichiarata dal report: `14 documenti tracciati · +10 NON tracciati`. Diventa
  15 + 9 col commit di questa sessione, che porta `inferenza_locale_o_remota.md` in baseline.

## Cosa questa sessione NON prova

- Che il caso avversariale nuovo resti avversariale. Oggi vince 1→2 con margine stretto: se
  un domani il ColBERT lo ribalta, il caso va **tolto**, non festeggiato — la stessa regola
  che ha già smarcato due casi in questo golden set.
- Che la bonifica di `change_log.md` sia completa. È completa per ciò che è **verificabile a
  macchina** (archi risolvibili, campi del frontmatter, vocabolario del dominio). §3 resta
  pieno di path che non esistono, ed è voluto: sono storia.
- Che i 5 candidati di R13 siano ancora sbagliati quando serviranno. Vanno **rimisurati**
  prima di essere promossi, non copiati.

---
---

# S6 — tre catene, un giudice e due contratti: cosa la misura ha smentito

*Eseguita il 2026-09-05. Chiude **R9**, **R10**, **R11**, **N4** e — per effetto collaterale
di N4 — **R19**; prototipa **N3**, che non passa, e la ragione è il risultato. Lascia un
residuo nuovo: `boost_alpha` e il peso di sezione sono accoppiati e calibrati uno alla volta.*

Il filo di questa sessione era una frase che AUDIT.md ripete in tre punti senza mai
chiuderla: **ogni metrica di questo progetto guarda il retrieval, e i difetti che contano
vivono nella risposta.** Le tre pendenze corrispondenti sono state misurate, non discusse.
Due si chiudono, una peggiora rispetto a come era descritta, e una quarta scopre che la sua
prova di riferimento è scaduta.

---

## R9 — il terzo documento non arrivava nella risposta: perché, e cosa è servito ✅ CHIUSO

**La domanda di A4:** le tre catene multihop a tre documenti si fermano a 2 su 3 nel
retrieval, ma `/ask` inietta anche le sezioni raggiunte **via grafo**. Il terzo documento
potrebbe quindi essere nella risposta pur mancando dalla baseline A. Nessuno l'aveva
chiesto a `/ask`.

Chiesto. Parametri di **produzione** (`top_k=5`, `bfs_depth=2` — i default di `AskQuery`,
non i valori con cui gira il report multihop), indice `v20260904T151925`, Ollama
`qwen3.5:9b`, cache di `/ask` disattivata.

| Catena | Matcher mancante alla baseline A | Documento nel contesto iniettato | Sezione attesa nel contesto | Il vincolo del terzo documento nella risposta |
|---|---|---|---|---|
| correlation id | `safeguards_security § Immutabilità` | **sì**, 2 sezioni via grafo | no | **a metà**: «record di audit» c'è, ma citato **da `[REGOLA-OBS-03]`**; `safeguards_security` non è mai nominato e nessun `[SAFEGUARD-AUD-*]` compare |
| PII fra log, test e LLM | `testing_strategy § Gate di Qualità` | **no**, assente del tutto | no | **no**: la gamba «test» di una domanda a tre gambe non c'è — zero occorrenze di `testing_strategy`, `[REGOLA-TEST-*]`, «dati di test» |
| ultima unità disponibile | `api_error_contract § Status HTTP` | **no**, assente del tutto | no | **no**: `RESOURCE_EXHAUSTED` c'è (arriva da `[SAFEGUARD-TXN-04]`), il **409** no |

**Il residuo non si chiude come A4.** L'ipotesi che lo avrebbe chiuso — «il grafo lo recupera
comunque» — è falsa su 2 catene su 3, e sulla terza è vera per il documento e falsa per la
sezione che porta il vincolo.

### La causa, misurata e non dedotta

Il ramo grafo (`api/routes_retrieval.py`, fase 4b-bis) ordina i nodi raggiunti per
`fiducia × autorità` e ne prende i primi `graph_context_max_chunks: 2`. Due difetti si
sommano, ed entrambi si vedono nei numeri:

1. **L'esclusione dei seed opera sui soli nodi `document`.** Le SEZIONI di un documento seed
   sono raggiunte a `hops ≥ 1`, non sono seed, ed **ereditano l'autorità del documento**.
   Nelle catene 2 e 3 l'intero budget è andato a due sezioni di `safeguards_security.md` — un
   documento **già interamente nella finestra dal ramo semantico** — e per giunta alle sue
   sezioni meno pertinenti, `(preambolo)` e `Baseline Cross-Progetto`, pertinenza 0.316 e
   0.410: quelle pertinenti il ramo semantico se le era già prese, e al ramo grafo è
   rimasto il resto.
2. **Nella chiave di ordinamento non c'è alcun segnale di pertinenza alla domanda.** Il
   commento nel codice lo dichiara come limite noto — *«la fiducia dice quanto ci si fida del
   legame, non quanto la sezione risponde»* — e ne trae la conseguenza sbagliata: *«ordinare
   queste sezioni per pertinenza sarebbe un secondo retrieval»*. Non lo è più da S3: il
   vettore ColBERT della domanda è già nell'handler e `rank_sections_by_relevance` è già
   chiamata, solo **dentro** un documento alla volta.

Posizione del terzo documento nella graduatoria del ramo grafo, contro un budget di **2**:

| Catena | oggi | escludendo le sezioni dei documenti già seed | ordinando per pertinenza |
|---|---|---|---|
| correlation id | **1**/143 | 1/125 | 1° (`safeguards § Categoria 2`, cb 0.4873) — invariato |
| PII log/test/LLM | **24**/278 | 5/259 | 3° — perde per 0.008 contro due sezioni di `definition_of_done` (0.4804 e 0.4735 contro 0.4724) |
| ultima unità | **42**/390 | 3/351 | **1°** (`api_error_contract § 5. BDD`, cb 0.4586) — **entrerebbe** |

### Primo tentativo: la pertinenza al posto degli altri due segnali — e cosa ha rotto

La correzione proposta era in due mosse: far lavorare i due filtri sul **documento** della
sezione invece che sul nodo raggiunto, e appiattire i candidati ordinandoli per **pertinenza**
invece che per `fiducia × autorità`.

La prima mossa è giusta e resta. Chiude anche una falla gemella che il residuo non nominava:
`superati` (S4) era controllato solo quando il nodo raggiunto era il **documento**, mai quando
era una sua **sezione** — un documento esplicitamente superato poteva quindi rientrare per
sezione.

La seconda mossa era giusta a metà, e la rimisura l'ha mostrato. Portava il terzo documento
in finestra su **1 catena su 3** (l'«ultima unità»), ma su un'altra faceva vincere
`inferenza_locale_o_remota.md § 5` — `authority: 0.40`, un documento **scritto come
distrattore del golden set** — davanti a `testing_strategy.md`, per un vantaggio lessicale di
0.02. Cioè il difetto di ADR 0002, rifatto dentro il ramo grafo: la fonte che *spiega* davanti
alla fonte che *vincola*. Sostituire un segnale con un altro non è comporli.

### La chiave giusta: pertinenza × fiducia × autorità

Le tre grandezze rispondono a **tre domande diverse**, e nessuna sostituisce le altre:

| Fattore | Risponde a | Da dove viene |
|---|---|---|
| pertinenza | la sezione risponde alla domanda? | MaxSim ColBERT, già calcolato (S3) |
| fiducia | quanto si crede al legame che ce l'ha portata? | `trust_paths`, ADR 0002 |
| autorità | quanto vale la fonte che la enuncia? | `(1-α)+α·peso`, la stessa forma di `rank_by_authority` |

Il moltiplicatore dell'autorità è **letteralmente quello di `rank_by_authority`**, non una
seconda scala inventata qui: due scale per la stessa grandezza divergerebbero alla prima
ricalibrazione. Il pavimento di pertinenza resta invece sulla pertinenza **grezza** — è una
soglia di «risponde alla domanda», e moltiplicarla per fiducia e autorità la trasformerebbe
in un'altra misura.

Cinque combinazioni misurate sulle tre catene, guardando chi finisce nei primi 2 (il tetto di
oggi) e dove cade il terzo documento:

| Ordinamento | correlation id | PII log/test/LLM | ultima unità |
|---|---|---|---|
| `fiducia × autorità` (pre-S6) | dentro | fuori, **10°** | fuori, 6° |
| `pertinenza` (primo tentativo) | dentro | fuori, 4° | dentro |
| `pertinenza × autorità` | dentro | fuori, 3° | dentro |
| `pertinenza × fiducia` | dentro | dentro (2°) | dentro |
| **`pertinenza × fiducia × autorità`** | **dentro** | **dentro (1°)** | **dentro** |

Le ultime due righe portano entrambe il terzo documento in finestra su tutte e tre. Il
prodotto pieno è però l'unico che sulla catena 2 mette `testing_strategy` (NORMS) **davanti**
al documento informativo a 0.40, invece che dietro: la stessa cosa che ADR 0002 chiede al
ranking semantico, chiesta anche a questo ramo.

### Rimisura finale — il terzo documento entra su tutte e tre

| Catena | Blocchi via grafo, oggi | Il terzo documento |
|---|---|---|
| correlation id | `safeguards § Categoria 2` (0.487) + `§ Sezione 0` (0.468) | **dentro** |
| PII log/test/LLM | **`testing_strategy § 1. Tassonomia dei Test`** (0.472) + `inferenza_locale_o_remota § 5` (0.495) | **dentro** |
| ultima unità | **`api_error_contract § 5. BDD`** (0.459) + `spec_graph_rag_ingestion § 4` (0.453) | **dentro** |

E nella risposta, che è ciò che R9 chiedeva davvero:

- **Ultima unità:** *«una riceve `200` … e l'altra riceve `409` con code `RESOURCE_EXHAUSTED`»*,
  attribuito a `[REGOLA-API-04]`. Il vincolo che nessuna delle due fonti recuperate enuncia.
- **PII log/test/LLM:** la risposta guadagna una sezione **«5. Vincoli sui Test»** che prima
  non c'era, con determinismo e isolamento presi da `testing_strategy`, e dichiara
  esplicitamente che *«il contesto non introduce vincoli specifici aggiuntivi sui dati
  personali oltre a quelli generali di `[SAFEGUARD-SEC-04]`»*. La terza gamba di una domanda a
  tre gambe ha una risposta, e il suo limite è dichiarato invece che riempito d'invenzione.
  La stessa risposta si chiude con una **«Nota sulla fonte»** che attribuisce il vincolo a
  `[IRON_MEMORY]` e dice che `[NORMS]` lo motiva senza stabilirlo: è l'attribuzione di A3,
  emessa spontaneamente.
- **Correlation id:** invariata nella sostanza — «record di audit» c'è, `safeguards` non è
  citato per nome. Il documento entra, la sua sezione `Immutabilità` no.

Sparisce anche il sintomo che aveva dato il nome al difetto: **nessun blocco di preambolo è
più iniettato dal ramo grafo** su nessuna delle tre catene.

### L'alternativa che sembrava ovvia, e che la misura ha bocciato

Prima di toccare l'ordinamento è stata misurata la strada più ovvia: **un tetto di sezioni per
documento** nel ranking, contro il fatto che su una di queste domande 4 dei 5 blocchi
semantici vengono dallo stesso documento. Calibrata sulle due suite reali (56 casi + 14),
profondità di ripesca 50:

| Tetto | r@1 | r@2 | r@5 | r@10 | MRR | multihop media A | A riusciti |
|---|---|---|---|---|---|---|---|
| nessuno | 0.625 | 0.875 | 0.982 | 1.000 | 0.786 | 0.854 | 9/14 |
| 3/doc | 0.625 | 0.875 | 0.964 | 0.982 | 0.781 | **0.890** | **10/14** |
| 2/doc | 0.625 | 0.875 | 0.946 | 0.964 | 0.775 | 0.837 | 9/14 |
| 1/doc | 0.625 | **0.750** | **0.750** | **0.750** | 0.688 | **0.666** | 6/14 |

Il tetto a 1 è l'unico che porta il terzo documento in finestra su tutte e tre le catene — ed
è anche quello che **distrugge** entrambe le suite: molti casi del golden set hanno più
sezioni attese nello stesso documento, e il tetto le taglia. Il tetto a 3 comprerebbe la suite
multihop (+0.036 e un caso) pagando r@5 e r@10, ma **non** risolve R9: a `top_k=5` il terzo
documento non entra su nessuna delle tre catene. Registrato qui perché la strada è ovvia e
qualcuno la ripercorrerà: è misurata, e la risposta è no.

### Cosa non si è mosso — la verifica che la modifica è contenuta

- `recall@1 0.625`, `recall@2 0.875`, `recall@5 0.982`, `recall@10 1.000`, `MRR 0.786` —
  **identici** a prima della sessione.
- Suite multihop: `recall media A = 0.854`, `A riusciti 9/14`, `B exact 6/6` — **identici**.

Non è una sorpresa, è una verifica: entrambe le suite girano su `/api/retrieve`, che il ramo
grafo non attraversa. Se uno di questi numeri si fosse mosso, la modifica avrebbe toccato
qualcosa che non doveva.

**I quattro test che si accorgono se torna indietro**, in `tests/test_ask_observability.py`,
**tutti verificati rossi** sulla variante che avrebbero dovuto bocciare:

| Test | Contro cosa | Rosso su |
|---|---|---|
| una sezione del seed non ruba il budget | filtro per nodo invece che per documento | codice pre-S6 |
| ordina per pertinenza fra documenti diversi | ordine `fiducia × autorità` | codice pre-S6 |
| la fonte debole non vince per solo lessico | ordine a sola pertinenza | primo tentativo |
| il cammino debole non vince per solo lessico | ordine a sola pertinenza | primo tentativo |

Gli ultimi due usano i pesi di produzione: a α=0.1 la forbice fra peso 0.30 e peso 1.0 vale
7,5%, quindi un vantaggio lessicale del 5% deve perdere — e uno più grande vincerebbe, che è
il comportamento voluto: **l'autorità modula la pertinenza, non la sostituisce.**

### R9 si chiude, e quel che resta ha già un altro nome

Il terzo documento entra nel contesto su **3 catene su 3** e il suo contributo compare nella
risposta su 2 (sulla terza il documento c'era già prima e la sostanza pure, dalla fonte
sbagliata). Il residuo si chiude.

Quel che resta non è R9: è **quale sezione** di un documento raggiunto mostrare. Sulla catena
1 la sezione attesa (`Categoria 3 — Immutabilità`, pertinenza 0.4237) è settima fra le sue
sorelle; sulla 2 entra `§ 1. Tassonomia` invece di `§ 3. Gate di Qualità`. È il difetto che A3
§4-5 ha già misurato e nominato — *«l'autorità è una proprietà del documento, ma l'unità di
retrieval è la sezione»*, e fra sezioni sorelle il moltiplicatore si semplifica — e la strada
per affrontarlo è già parcheggiata come **N4** (peso di sezione). Chiudere R9 qui non nasconde
nulla: lo consegna al residuo che lo descrive meglio — **e N4 è stato affrontato subito dopo,
nella stessa sessione: vedi più sotto.**

### Cosa questa correzione NON prova

- Che le risposte siano migliori **in generale**. È misurata su tre catene: su due il vincolo
  mancante ora arriva, sulla terza no. Nessuna metrica del progetto guarda le altre 53
  domande del golden set dal lato della risposta — è di nuovo N3.
- Che `pertinenza × fiducia × autorità` sia la composizione **ottima**. È la migliore delle
  cinque misurate, tutte con α di produzione. Un α diverso, o una forma non moltiplicativa,
  non sono stati esplorati: qui serviva una chiave che non buttasse via un segnale, non una
  calibrazione.
- Che il tetto `graph_context_max_chunks: 2` sia giusto. Non è più il collo di bottiglia sulle
  tre catene, ma non è stato calibrato: è rimasto dov'era, ed è la cosa da guardare per prima
  se un domani una catena a quattro documenti dovesse comparire.

---

---

## N4 — la sezione che RESTITUISCE una regola non è quella che la STABILISCE ✅ CHIUSO

Chiuso R9, restava una cosa sola: **quale sezione** di un documento mostrare. A3 §4-5 l'aveva
già misurata e nominata — il 70% del deficit di rango 1 è bloccato da una sezione **sorella**,
dove il peso di autorità è identico per costruzione e il moltiplicatore `(1-α)+α·peso` si
semplifica, quindi *nessun α può separarle* — e aveva anche nominato il colpevole: i blocchi
BDD/Gherkin sono *«la riformulazione lessicale della regola che li precede: stesso
vocabolario, più denso di parole chiave, spesso più lungo»*, e il MaxSim di ColBERT premia
esattamente questo.

Mancava il segnale che le separi. N4 lo parcheggiava come «peso di sezione», senza dire da
dove il peso dovesse venire.

### Il segnale è nel corpus, e non è un'euristica sui titoli

Un codice di regola **dichiarato in un titolo** — `### \`[SAFEGUARD-AUD-01]\` Immutabilità
Assoluta…` — marca la sezione che enuncia il vincolo. Lo stesso codice dentro una tabella di
riepilogo, una checklist o un blocco Gherkin è una **citazione**. Nient'altro: nessuna lista
di titoli da riconoscere, nessuna parola chiave da mantenere.

Misurato sul corpus, 167 sezioni:

| Ruolo | Quante | Chi sono |
|---|---|---|
| dichiara | 31 | `Categoria 2 — Concorrenza Critica`, `2. Log Strutturati e Correlazione`, `3. Gate di Qualità`, `3. Contratto dei Design Token`… |
| **cita soltanto** | **28** | `Riepilogo delle Regole` (×5), `Scenari Comportamentali BDD`, `Checklist — Livello …` (×4), `Indice dei Safeguard`, `Catalogo Minimo degli Errori` |
| nessun codice | 108 | preamboli, prose, contratti di istanziazione senza regole |

Le 28 sono **esattamente** l'elenco che A3 §5 aveva stampato guardando chi bloccava l'atteso.
Una sezione senza codici non è una riformulazione e resta a peso pieno: si penalizza solo chi
ripete una regola che appartiene a un'altra sezione.

### Calibrato a k=1, con lo stesso protocollo che A3 pretese da `boost_alpha`

`rag_config.yaml:authority.section_restatement_weight`, moltiplicatore applicato alle sole 28.
5-fold × 5 seed, tie-break all'incumbent (1.0 = nessuna penalità), come `grid_best`:

```
in-sample   r@1  0.625 -> 0.714
HELD-OUT    r@1  0.626 -> 0.695     guadagno +0.069   dev.std 0.008
            per seed: +0.073  +0.053  +0.073  +0.073  +0.073   ← positivo su 5 su 5
valore scelto in 20 fold su 25: 0.92
```

È l'esatto opposto di ciò che A3 trovò provando ad alzare α: là in-sample +0.019 e held-out
**−0.029 su tutti i seed**, cioè sovradattamento. Qui il guadagno sopravvive fuori campione,
con una dispersione fra seed di 0.008 — un ordine di grandezza sotto il guadagno.

A k=2 il quadro è diverso e va detto: +0.011 held-out, dev.std 0.018, **un seed negativo**, e
il valore scelto salta fra 0.8 e 0.95. Non è una contraddizione: a k=2 la metrica sta a 0.875
e non discrimina. Il valore viene da k=1 — l'unico k che misura ciò che questo peso governa —
ed è la stessa disciplina che A3 rimproverò a `boost_alpha`, *«calibrato dove non si vede»*.

### Misura dal vivo

| | prima | dopo |
|---|---|---|
| `recall@1` | 0.625 | **0.714** |
| `recall@2` (gate) | 0.875 | **0.893** |
| `recall@5` | 0.982 | 0.982 |
| `recall@10` | 1.000 | 1.000 |
| `MRR` | 0.786 | **0.835** |
| `source_in_top3` | 0.946 | **0.964** |
| avversariale `recall@1` | 0.000 | 0.000 |
| multihop, recall media A | 0.854 | **0.890** |
| multihop, A riusciti | 9/14 | **10/14** |

Nessuna metrica peggiora. La recall avversariale resta 0.000 ed è corretto: quei cinque casi
sono bloccati da un **altro documento**, non da una sorella — A3 lo aveva già separato, e il
peso di sezione non li tocca per costruzione.

**I cinque casi che salgono a rango 1** si leggono come la tabella di A3 §5 letta al contrario:

| Domanda | Prima (rango 1) | Dopo (rango 1) |
|---|---|---|
| lunghezza massima di una funzione | `coding_standards § 4. Scenari BDD` | `§ 2. Metriche Strutturali` |
| forma della risposta di errore | `api_error_contract § Sezione 0` | `§ 1. Forma dell'Errore` |
| soglia minima di copertura dei test | `testing_strategy § Sezione 0` | `§ 3. Gate di Qualità` |
| saltare una voce della checklist | `definition_of_done § 6. Scenari BDD` | `§ 1. Principio` |
| correlation id sui record di audit | `observability § 6. Riepilogo delle Regole` | `§ 2. Log Strutturati e Correlazione` |

Zero casi regrediscono. E la suite multihop — **dati che non hanno scelto il parametro** —
guadagna un caso: `cosa devo fare quando modifico un documento` passa da 0.500 a 1.000,
perché `spec_graph_rag_ingestion § Aggiornamento Incrementale` rientra nel top-10.

### L'asimmetria: nel ramo semantico sì, nel ramo grafo NO

Applicato anche al ramo grafo, il peso di sezione **rompe R9**: la catena dell'«ultima unità»
perde `api_error_contract` — il terzo documento appena guadagnato — e con lui il `409` nella
risposta. Misurato dal vivo, non dedotto.

La ragione non è un numero, è una differenza di premessa:

- Nel ramo **semantico** penalizzare una riformulazione **promuove la sorella che dichiara**,
  perché è nella stessa lista: è precisamente ciò che fa salire i cinque casi qui sopra.
- Nel ramo **grafo** i concorrenti sono altri **documenti**, il tetto è 2, e la sorella che
  dichiara spesso non è nemmeno candidata. Lì la penalità non promuove la fonte del vincolo:
  **espelle il documento**.

Quindi il peso vive in `rank_by_authority` — dove `/api/retrieve` lo espone e le due suite lo
misurano — e non nella chiave composita del ramo grafo. L'asimmetria è deliberata ed è pinnata
da un test che diventa rosso se qualcuno la "corregge".

### Il costo, dichiarato

Due fonti attese dal golden set **vivono** in una sezione penalizzata:
`definition_of_done § 3. Checklist — Livello Funzionalità` e `§ 4. Livello Rilascio`. Lì la
checklist **è** la norma, non la riformula: il segnale, per quel documento, dice la cosa
sbagliata. Oggi entrambe restano a rango 1 — la penalità è mite apposta, rompe i pareggi fra
sorelle senza ribaltare un divario di rilevanza vero — ma è il primo posto da guardare se un
domani quel peso venisse abbassato.

### Due effetti collaterali, uno buono e uno da registrare

**R19 rientra.** La soglia multihop stava a **0,4 punti** dal pavimento (0.854 contro 0.85) e
S5 l'aveva registrata come residuo nuovo. Con N4 la recall media è 0.890: il margine torna a
**4,0 punti**. Non è stato l'obiettivo, ed è giusto dirlo così — R19 si chiude per effetto di
un'altra correzione, non perché qualcuno l'abbia affrontato.

**Il calibratore di `boost_alpha` ha cambiato verdetto, e NON è stato applicato.** Rimisurato
dopo N4, `eval.calibrate_authority --k 1` propone ora `alpha=0.3` con guadagno held-out
**+0.028** — dove prima, sullo stesso comando, dava **−0.029** e `NON_APPLICARE`. Il default
held-out è salito da 0.636 a 0.716: è il peso di sezione, misurato da uno strumento
indipendente. La proposta però ha `dev.std 0.024` e **un seed negativo**, contro lo 0.008 e i
5/5 di N4: è un segnale molto più debole, e alzare α resta la modifica che A3 ha respinto con
una misura. **Non applicata.** Ne esce però un residuo vero: i due parametri sono
**accoppiati** e sono stati calibrati uno alla volta. Una calibrazione congiunta di
(`boost_alpha`, `section_restatement_weight`) è un lavoro a sé, non una riga in coda a questo.

### Dove vive, e cosa non ha richiesto

Il ruolo si deriva dal **testo** dei chunk (`retrieval.restatement_sections`), calcolato una
volta per snapshot accanto a `rule_descriptions`: **nessuna re-indicizzazione**, nessun campo
nuovo negli artefatti, e funziona sugli indici già su disco. Il parametro è passato
esplicitamente a `rank_by_authority` — e quindi anche dal **calibratore**, che altrimenti
ottimizzerebbe un ordinamento che nessuno serve: è l'avvertimento scritto nel docstring di
`make_retrieve_fn`, ed è il motivo per cui `restatements` è un argomento obbligatorio invece
di un default comodo.

### Cosa N4 NON prova

- Che 0.92 sia il valore ottimo. È il valore che 20 fold su 25 scelgono a k=1, su una griglia
  di nove punti, con α fermo al suo valore di produzione. La coppia va ricalibrata insieme.
- Che il segnale regga su un corpus con altre convenzioni. Qui i documenti dichiarano le
  regole sotto un titolo perché il corpus lo impone; un corpus che non lo faccia vedrebbe 0
  sezioni «dichiara» e il peso diventerebbe inerte — che è il modo giusto di degradare, ma
  resta da verificare il giorno in cui succede.
- Che la catena del correlation id sia risolta. `safeguards § Categoria 3 — Immutabilità` resta
  fuori dal top-10, e non per il difetto che N4 corregge: le sue sorelle che la battono
  **dichiarano** anche loro, e a quella domanda sono più pertinenti. È il ranking che funziona,
  non un residuo.

---

## N3 — il giudice funziona, la prova contro cui doveva essere validato no

**Il progetto minimo, prototipato.** Un giudice LLM riceve la domanda, l'elenco delle fonti
presenti nel contesto e la risposta; restituisce un JSON con la fonte che la risposta indica
come **normativa** — quella che *stabilisce* il vincolo, distinta da quella che lo motiva, lo
illustra o lo conferma — più una citazione di venti parole a sostegno. Una chiamata per caso,
qualche secondo l'una.

**Il giudice è ripetibile.** Tre giudizi sulla **stessa** risposta, sul caso facile e su
quello difficile: `3/3` identici in entrambi. La varianza che si vede più sotto non è sua.

**L'accordo col giudizio umano registrato in A3 §6, colonna «Dopo»: 3 su 4.**

| Caso | Umano (A3, 2026-09-03) | Giudice (2026-09-05) |
|---|---|---|
| 1 — bump di versione | ✅ la spec | `spec_graph_rag_ingestion.md` ✅ |
| 2 — caratteri per chunk | ✅ la spec «Fonte Primaria» | `spec_graph_rag_ingestion.md` ✅ |
| 3 — ordine dei tagli | ✅ `[REGOLA-VAL-04]` dalla spec | `spec_graph_rag_ingestion.md` ✅ |
| 4 — palette colori | ✅ «apre dalla norma e dichiara la divergenza» | `NESSUNA` ❌ |

**Per il criterio fissato per questa sessione — se non coincide, il giudice non è pronto — il
giudice NON passa.** Va detto così, e va detto anche perché non coincide, perché la ragione
non è il giudice.

Sul caso 4 il giudice ha ragione e la tabella è scaduta. In **tre** esecuzioni indipendenti
con cache disattivata la risposta apre sempre allo stesso modo — *«Il contesto **non riporta**
un controllo stilistico della palette colori che sia già stato eseguito»* — cioè riformula la
domanda in «è già stato fatto?» e **non attribuisce alcun vincolo a nessuna fonte**: cita
`fe1-canvas-review` (il distrattore) al punto 1 e `[REGOLA-UI-01]` al punto 2, entrambi come
prove dell'assenza. Il risultato che A3 registrò — *«apre dalla norma e dichiara la
divergenza risolvendola per classe»* — **non si riproduce oggi**. Fra il 3 e il 5 settembre il
corpus e l'indice sono cambiati (S5, R7, R8) e nel contesto è entrato il codice del frontend,
che allora non c'era.

Non è una regressione dimostrata della correzione di A3: è la dimostrazione che **quattro
risposte lette a mano non sono una prova conservabile**. Il riferimento è marcito in due
giorni, e nessun numero del progetto se n'era accorto — che è l'argomento di N3, verificato
su N3 stesso.

Una conseguenza di progetto, da portarsi dietro quando l'harness si scriverà: la condizione
di controllo va **archiviata insieme al testo della risposta**, non solo come verdetto. Un
harness che conservi «✅/❌» e basta ricostruisce fra un mese lo stesso vicolo cieco di oggi.

**Il secondo tentativo di validazione, e perché non ha aiutato.** Per non validare il giudice
su soli casi positivi — un giudice che rispondesse sempre «la fonte più autorevole» li
passerebbe tutti — è stata ricostruita la condizione **PRIMA** di A3: stesso contesto, le
classi tolte dalle intestazioni, nessun `[CLASSE-FONTI]`. Non ha prodotto negativi
affidabili: sul caso 2 due esecuzioni danno `spec` e `NESSUNA`, e il difetto storico —
severità attribuita al METHODOLOGY — **non si riproduce**. Quindi oggi il giudice non ha un
solo caso in cui l'attribuzione sia dimostrabilmente sbagliata: la sua capacità di
riconoscere l'errore resta **non provata**, ed è un limite del corpus tanto quanto del
giudice.

**Cosa serve prima di scrivere l'harness**, nell'ordine: casi in cui l'attribuzione sia
davvero contesa — il sottoinsieme avversariale di oggi ha 5 casi e 3 distrattori, e su tre di
essi la spec vince facile — e, per ognuno, un verdetto umano archiviato **con la risposta che
l'ha prodotto**. Senza i primi il giudice misura una costante; senza i secondi la misura non è
riproducibile fra due corpus.

---

## R10 e R11 — i due contratti girano ora dove c'è un modello vero

Due impegni che nessun test esercitava contro un LLM reale: il marcatore `[ASTENSIONE]` è una
promessa del prompt, non una garanzia del modello; la soglia di **certezza** su `num_ctx` era
stata osservata a mano una volta sola. In CI non c'è un LLM, quindi il canale è il check
notturno, che gira dove Ollama c'è ed è già collegato agli alert.

Aggiunti a `scripts/nightly_consistency.{sh,ps1}` — **gemelli**, stesse due verifiche, stessi
messaggi, `.sh` in LF — dentro il blocco già condizionato alla raggiungibilità del server:

- **R10**: una domanda fuori corpus (una ricetta di cucina) deve tornare `status: "abstained"`.
  Qualunque altro stato scrive un alert che riporta lo stato ricevuto.
- **R11**: `top_k=20` sulla domanda dei dati personali deve tornare **502** col messaggio
  `[FINESTRA DI CONTESTO SUPERATA]`. Misurato oggi: **~17.298 token stimati contro
  `num_ctx=16384`**, il 105,6% — dello stesso ordine dei ~17.013 di A1, che però non registrò
  con quale domanda: da oggi la domanda è nello script, e quel confronto non andrà più perso.

**Il ramo che di solito viene scritto male è il 200.** Un `200` qui non è un falso allarme
benigno da ignorare: o il guardrail non scatta più, o il contesto si è ridotto sotto la
finestra. In entrambi i casi il check **non sta più esercitando il contratto**, ed è quello
che l'alert dice — invece di restare verde per la ragione sbagliata, che è il modo in cui
questa sorveglianza ha già fallito una volta (A2b: la soglia scritta a mano su una `k`
satura).

**Verifica, entrambi i gemelli, esecuzione reale:**

```
[…] Contratto di astensione (domanda fuori corpus)...
[…] Astensione OK (status abstained).
[…] Soglia di certezza su num_ctx (top_k=20)...
[…] Soglia di certezza OK (502 col messaggio dichiarato).
[…] Integrita' OK: nessuna azione necessaria.            exit 0
```

E la prova che i due check **discriminano**, senza la quale sarebbero due semafori sempre
verdi: la stessa domanda posta dentro il corpus torna `success` (farebbe scattare R10), e la
domanda di R11 a `top_k=5` torna `200` — il 502 viene dalla finestra, non da `/ask` rotto.
Costo aggiunto al notturno: **2 chiamate a `/ask`**, ~4 secondi in tutto, di cui una si ferma
prima del modello.

**Cosa questa chiusura NON prova.** Che un modello diverso rispetti `[REGOLA-ASTENSIONE]`: il
check gira contro `qwen3.5:9b`, che è il modello configurato — sostituirlo è ciò che il check
esiste per rendere visibile, non ciò che ha già verificato. E che il 502 arrivi per la ragione
giusta su ogni corpus: la domanda di R11 è hard-coded con la sua misura e la sua data
accanto, perché il giorno in cui non supererà più la finestra il messaggio dell'alert dovrà
essere leggibile da chi non c'era.

---

## Verifica

- `ruff check .` → `All checks passed!`
- Suite completa: **1329 passed**, 0 skipped (Qdrant e Ollama accesi) — 1318 prima, più gli
  undici casi nuovi, ognuno **verificato rosso** sulla variante che deve bocciare (due sul
  codice pre-S6, due sul primo tentativo a sola pertinenza, tre sul ramo senza peso di
  sezione, uno sulla variante che il peso lo applica anche al ramo grafo).
- **R9**: golden set e suite multihop identici prima e dopo — la correzione tocca solo il ramo
  grafo, che non passa da `/api/retrieve`.
- **N4**: `recall@1 0.625 → 0.714`, `recall@2 0.875 → 0.893`, `MRR 0.786 → 0.835`,
  `source_in_top3 0.946 → 0.964`; `recall@5`/`recall@10` invariati ai loro massimi; multihop
  `0.854 → 0.890` con `A riusciti 9 → 10/14` e `B exact 6/6`. Nessuna metrica peggiora.
- Il calibratore dell'autorità gira e riporta un `default_recall` held-out salito da **0.636 a
  0.716**: è il peso di sezione, misurato da uno strumento che non l'ha scelto.
- `bash scripts/nightly_consistency.sh` e `pwsh -File scripts/nightly_consistency.ps1`:
  **stessa uscita riga per riga**, entrambi `exit 0`, integrità OK, nessuna mutazione
  dell'indice. I gemelli restano gemelli, e il `.sh` resta LF (0 CR nel file).
- I due check nuovi **discriminano**: domanda dentro il corpus → `success` (R10
  scatterebbe); `top_k=5` → `200` (il 502 di R11 viene dalla finestra, non da `/ask` rotto).
- Il giudice di N3 è ripetibile: 3 giudizi identici sulla stessa risposta, su due casi.

## Un numero scaduto trovato per strada — e poi rientrato

Le due corse reali del notturno hanno riscritto in `history.jsonl` la recall media della
suite multihop: **0.854**, contro il pavimento **0.85**. La riga di A4 «margine 4,6 punti»
descriveva lo 0.896 di prima di S5 ed è stata barrata sul posto. Non è un residuo nuovo — S5
lo aveva già registrato come **R19** — ma era rimasto vero in un punto del documento e falso
in un altro, che è il modo in cui questi numeri scadono: uno alla volta, mai tutti insieme.

**Poi N4 l'ha riportato a 0.890, cioè 4,0 punti di margine, e R19 si chiude.** Va detto per
quello che è: un effetto collaterale, non un intervento. Nessuno ha affrontato R19; è
rientrato perché la correzione di un'altra cosa passava di lì.

## Cosa questa sessione NON prova

- Che la correzione di R9 renda le risposte migliori **in generale**. È misurata su tre
  catene: su due il vincolo mancante ora arriva, sulla terza no. Nessuna metrica del progetto
  guarda le altre 53 domande del golden set dal lato della risposta — è di nuovo N3.
- Che il tetto `graph_context_max_chunks: 2` sia giusto. Non è più il collo di bottiglia sulle
  tre catene, ma non è stato calibrato: è rimasto dov'era.
- Che `boost_alpha` e `section_restatement_weight` siano ai loro valori giusti **insieme**.
  Sono stati calibrati uno alla volta, e dopo N4 il calibratore dell'autorità propone un α
  diverso: la coppia è accoppiata e la calibrazione congiunta non è stata fatta. Registrato
  come residuo, non risolto in coda a questa sessione.
- Che il giudice di N3 sappia riconoscere un'attribuzione **sbagliata**. Su questi 4 casi non
  gli è mai stata mostrata: la condizione PRIMA ricostruita non riproduce più il difetto
  storico. Finché non esiste un caso negativo verificabile, l'accordo 3/4 misura la sua
  concordanza, non la sua sensibilità.
- Che il caso 4 di A3 sia una regressione della correzione di A3. Fra le due misure sono
  cambiati corpus, indice e contesto (ora c'è il codice del frontend): le due condizioni non
  sono confrontabili, ed è precisamente ciò che rende necessario N3.

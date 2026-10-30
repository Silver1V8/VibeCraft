Italiano | [English](../README.en.md)

> Documentazione operativa sotto `rag/docs/`: **non** è corpus RAG (il corpus è `docs/` del progetto). Stesso schema degli ADR. Italiano canonico; l'inglese resta un indice breve in `rag/README.en.md`.

[← Indice operativo](../README.md)

# LLM: layer unico, provider per step

## LLM: un solo layer, provider intercambiabili per step

Tutte le chiamate generative (drift, canvas, propose, validate, explore, canvas
review) passano da [core/llm.py](../core/llm.py): `generate(prompt, purpose=...)`
(sincrona) e `agenerate(...)` (async). Provider e modello si risolvono da
[rag_config.yaml](../rag_config.yaml): di default `llm_settings.active_provider` +
`llm_settings.models`, con override opzionale **per singolo step** via
`llm_settings.purposes` (esempio commentato nel file). Così si può ad esempio
generare il canvas con Claude e tenere il drift su Ollama locale.

Provider disponibili: `ollama` (endpoint locale `/api/generate`), `anthropic` (SDK
ufficiale, dipendenza del progetto dal 2026-10-30) e `openai`, cioè qualunque endpoint
compatibile con `/chat/completions` (OpenAI, Mistral, OpenRouter, Groq…), uno alla volta
con base URL configurabile. Le chiavi arrivano da `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`
o dal menu Impostazioni; se mancano l'errore è esplicito. Gli errori di rete/timeout
sollevano `LLMError` con messaggio leggibile: i chiamanti restano tolleranti come
prima (il check drift mette il messaggio nel report, l'archive salta la review
con un warning, gli step della pipeline restituiscono il messaggio come testo via
`pipeline.generate_tolerant`). Nei test si inietta un provider fake con
`llm.register_provider` — nessun HTTP (vedi [tests/test_llm.py](../tests/test_llm.py)).


## Menu Impostazioni della console (2026-10-30)

Il pulsante **Impostazioni** (accanto a Guida; nella home dei progetti in alto a destra)
raggruppa lingua, tema e rain, e la scelta dei modelli LLM per tutti i progetti:

- **Tutto locale**: ogni attività su Ollama, con il modello locale scelto;
- **Tutto in cloud**: ogni attività sul provider cloud scelto (Anthropic,
  OpenAI-compatibile o Claude con l'abbonamento) e sul suo modello;
- **Per attività**: provider e modello per ciascuno degli scopi di `core.llm.PURPOSES`
  (drift, canvas, propose, validate, explore, review, ask, judge); un modello vuoto
  usa quello predefinito del provider.

**Claude (abbonamento)**, provider `claude_code`: chiama Claude attraverso la CLI di Claude
Code (Agent SDK, un turno, nessuno strumento) con il login della macchina, quindi senza API
key e dentro i limiti del piano Claude. Il login si fa una volta con `claude` → `/login`. Se
`ANTHROPIC_API_KEY` è nell'ambiente la CLI usa quella. Uso personale: per offrire
vibecraft ad altri i termini dell'Agent SDK chiedono l'API key.

Per i provider con API key si impostano chiave, modello (l'elenco arriva dall'API del
provider, o è scrivibile a mano), prezzi per milione di token e un budget giornaliero
che, raggiunto, riporta le chiamate su Ollama (`_budget_fallback`).

Dove finiscono le scelte: [core/llm_settings_store.py](../core/llm_settings_store.py)
scrive `database/llm_settings.json`, un overlay sopra `llm_settings` di
`rag_config.yaml`, che resta la fonte dei default commentati e non viene mai riscritto.
L'overlay vale subito, senza riavvio, e al boot viene validato come il YAML: un file
illeggibile ferma l'avvio. Le chiavi stanno in `database/secrets/llm_keys.json`, fuori da
git; la variabile d'ambiente, se c'è, vince, e nessuna risposta HTTP restituisce la
chiave. Route e rischi in [SECURITY_SURFACE.md](../SECURITY_SURFACE.md), righe 73–76.
Una replica `reader` non monta queste route.

Anche `POST /ask` (sintesi della risposta RAG) passa da questo layer, con purpose
`ask`: il prompt (system storico + contesto + domanda + una riga di chiusura
che chiede di rispondere senza ripetere contesto e istruzioni) è costruito
dalla funzione pura `retrieval.build_ask_prompt` e la chiamata è
`llm.agenerate(..., purpose="ask")` — stessi guardrail `think`/`options.num_ctx`
degli altri step, un solo client da mantenere. Su `LLMError` la route risponde
`502` col messaggio dell'errore: mai un testo d'errore dentro `answer` con
`status: "success"`. La base URL di Ollama è unica per tutto il codice
(`VIBECRAFT_OLLAMA_URL`, default `http://127.0.0.1:11434`, core/config.py).

**La riga di chiusura evita l'eco del prompt.** Istruzioni e contesto viaggiano
in un solo turno utente: su un contesto lungo e ripetitivo (per esempio due parti
della stessa sezione in finestra) qwen3.5:9b perdeva il confine fra compito e
documento e restituiva come `answer` il prompt stesso, ricopiato dalla prima riga
fino a riempire `num_ctx`. Sulla domanda «ultimo posto» il prompt veniva ricopiato
in 16 varianti su 21 (ognuna senza uno dei blocchi di contesto); con la riga di
chiusura, in 0 su 22. È lo stesso esito che si ottiene spostando le istruzioni nel
campo `system` di Ollama, ma senza toccare il layer dei provider.

**L'astensione è leggibile a macchina** (`status: "abstained"`). Il modello si
astiene già correttamente in prosa libera quando il contesto recuperato non
contiene la risposta — verificato dal vivo — ma prima il payload restava
`status: "success"` con le fonti elencate in `qdrant_scores`, identico nella
forma a una risposta vera: un client non aveva modo di distinguere "ha
risposto" da "si è astenuto" senza fare NLP sulla prosa. `[REGOLA-ASTENSIONE]`
nel prompt (`retrieval.build_ask_prompt`) impone al modello di anteporre il
token `retrieval.ASK_ABSTENTION_MARKER` (`[ASTENSIONE]`) quando e solo quando
il contesto non basta; `ask_rag` lo legge, lo rimuove — l'utente umano non lo
vede mai — e imposta `status: "abstained"`. Distinto da `no_results` /
`no_graph_nodes`: lì il retrieval non trova nulla, qui trova qualcosa ed è la
sintesi a dire che non risponde.

**Router deterministico M2 davanti a `/ask`.** Prima del retrieval, la funzione
pura `core.router.route_question` (regex, zero LLM, zero grafo) classifica la
domanda: le formulazioni **strutturali** inequivocabili (enumerazioni di
documenti/entità, `quali relazioni ha X`, `impatto se modifico Y`, nodi
adiacenti — i casi risolti dal grafo nel report M1) vanno su strategia `graph` e
sono risposte direttamente da `graph_ops.graph_query` (offload in threadpool),
**senza retrieval né chiamata LLM**: la risposta ha `status: "graph_answer"` col
`graph_result` esatto. Tutto il resto (incluse le multihop) resta su strategia
`hybrid`, il percorso retrieval + sintesi LLM descritto sopra. Il router è
**conservativo per costruzione** — in dubbio `hybrid`, vincolo di zero falsi
positivi sul golden-set classico — e la scelta finisce nel campo
`retrieval_strategy` del log strutturato M3.

**Il codice è una fonte di `/ask`, non solo i documenti.** La ricerca semantica
interroga Qdrant, dove stanno **solo i documenti**: il codice vive nel grafo (nodi
simbolo) e i suoi vettori densi nel sidecar `code.npz`. `/ask` lo porta nel contesto
per **due strade complementari**, e ciò che inietta è esposto nel campo
`implementing_code` della risposta (con `source` per ramo di provenienza):

1. **Ricerca semantica diretta** (`retrieval.search_code_symbols`): coseno fra il
   vettore denso della **domanda** e quelli dei simboli, calcolato in memoria (~25 ms
   su 4.000 simboli, nessun punto in più in Qdrant, nessun costo di indicizzazione).
   È l'unica strada che trova il codice che **nessuna spec descrive** — un DTO con
   l'elenco dei campi obbligatori, un helper, una query. Un tetto per **file**
   (`code_search_max_per_file`) impedisce a un singolo file autogenerato (il proxy
   WCF `Reference.cs`) di occupare tutte le posizioni con varianti della stessa riga.
2. **Ponte `IMPLEMENTS`** (`retrieval.collect_implementing_code`): dagli archi
   entranti ai nodi recuperati risale l'**implementazione di ciò che si è
   recuperato**, così l'LLM confronta la spec con il codice reale ("cosa manca nel
   form?").

I due risultati sono deduplicati per simbolo con priorità al ramo semantico e cappati
complessivamente (`code_context_total_snippets`). La regola `[FONTE-CODICE]` del
system prompt dichiara il blocco «CODICE ESISTENTE» **fonte legittima**: senza,
`[REGOLA-DIZIONARIO-RIGIDO]` portava il modello a trattare come invenzione qualunque
nome di campo assente dai documenti e a rispondere "Non specificato" con la classe che
quei campi li dichiara sotto gli occhi. Se il retrieval documentale non trova nulla ma
il codice sì, la domanda **riceve comunque una risposta** (prima: "Nessun documento
rilevante"). Tutte le soglie stanno in `rag_config.yaml → retrieval.*`;
`code_search_max_snippets: 0` disattiva il ramo diretto.

**Budget guard giornaliero su Claude, fallback automatico su Ollama.**
`core/llm.py` tiene un contatore di spesa Anthropic per giorno UTC, alimentato dallo
stesso costo stimato già loggato per l'osservabilità (`llm_settings.pricing`): senza
un prezzo configurato per il modello nulla viene contato e il guard resta inerte. Se
`llm_settings.budget.daily_usd` è superato, `resolve(purpose)` devia silenziosamente
(provider, model) su `budget.fallback_provider` (default `ollama`) — a patto che quel
provider abbia un modello in `llm_settings.models`, altrimenti resta su anthropic per
non trasformare un problema di costo in un fallimento di generazione. Il contatore
persiste opzionalmente su file (`budget.spend_file`, altrimenti solo in-memory,
azzerato al riavvio) e non fa mai fallire una chiamata: qualunque errore interno del
guard (config malformata, file illeggibile) viene loggato e si resta sul provider
risolto. `spend_today_usd()` espone la spesa corrente per diagnostica.
Nello stesso contatore entra il costo dei run dell'agente Claude
(`POST /api/pipeline/agent/run`, runner `claude`): a fine run `agent_bridge` registra il
`total_cost_usd` riportato dall'SDK (anche per run falliti; niente se lo stream si
interrompe prima del risultato), senza bisogno di `pricing`. Non avendo un provider
locale su cui degradare, con budget attivo e soglia raggiunta i nuovi run `claude` (e i
rilanci automatici dopo una verifica fallita) sono **rifiutati** con 429 e
`Retry-After` fino alla mezzanotte UTC; i runner `local`, `codex` e `cursor` non sono
toccati dal budget. La soglia è **morbida**: il costo è noto solo a fine run, quindi i
run già ammessi o in corso possono superarla e bloccano soltanto quelli successivi.

**Breakdown di latenza in risposta (M3/F3).** Sia il ramo `hybrid` sia il ramo
`graph` restituiscono, oltre a `request_id` e `index_version`, un oggetto
`latency: {retrieval_ms, generation_ms, total_ms}` (nel ramo grafo
`retrieval_ms` è la latenza di `graph_query` e `generation_ms` è 0): gli stessi
valori già presenti nel log strutturato di fine richiesta, esposti anche nel JSON
così i client (e `scripts/bench.py`) misurano il breakdown senza parsare i log.

**Cache delle risposte su `/ask`, isolata per progetto e versione.**
[core/ask_cache.py](../core/ask_cache.py) è una LRU thread-safe in-process che azzera il
costo (embedding + generazione LLM) delle domande ripetute — la maggioranza su una
console di governance. La chiave (`make_key`) include progetto, versione, strategia, top-k, profondità
BFS, hash della domanda e fingerprint delle impostazioni authority/retrieval: la domanda è normalizzata (trim,
lowercase, spazi collassati) prima dell'hash, così due formulazioni identiche a meno
di spaziatura condividono la voce. **L'invalidazione non esiste come operazione**:
ID progetto, `index_version` e impostazioni fanno parte della chiave: progetti
con stessa query/versione non condividono risposte; dopo una re-indicizzazione o un
rollback (`database/CURRENT` cambia in entrambi i casi) le voci della versione
precedente non vengono più consultate e la LRU le espelle. Lo stato vive su
`app.state.ask_cache` (non in una global di modulo, quindi i test restano isolati
senza fixture globali), creato lazy con tetto da env `VIBECRAFT_ASK_CACHE_SIZE`
(default 256 voci, `0` disattiva la cache). I payload cachati sono trattati come
immutabili: la route costruisce la risposta con una copia (`{**cached, ...}`), mai
mutando l'oggetto in cache.


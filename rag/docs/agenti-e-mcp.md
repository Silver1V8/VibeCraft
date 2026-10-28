Italiano | [English](../README.en.md)

> Documentazione operativa sotto `rag/docs/`: **non** è corpus RAG (il corpus è `docs/` del progetto). Stesso schema degli ADR. Italiano canonico; l'inglese resta un indice breve in `rag/README.en.md`.

[← Indice operativo](../README.md)

# Agenti, MCP e verifica multi-progetto

## L'indice come acceleratore per l'agente che scrive il codice

`GET /api/code/search?q=...&k=...` espone a un agente esterno (Claude Code,
Cursor) la stessa ricerca semantica sui simboli che alimenta `/ask`: coseno fra
la domanda e i vettori densi dei simboli, già calcolati all'indicizzazione e
persistiti in `code.npz`. Nessun LLM, nessuna query a Qdrant — una forward pass
di bge-m3 e un prodotto matriciale in memoria.

Serve a un problema misurato: un agente che deve integrare codice in `code/` non
sa dove sta ciò che gli serve e ripiega su Glob+Read a tappeto, cioè legge (e
paga) l'intero ambito per trovare i due file che gli servono. Su questo repo,
una ricerca `k=5` in `code/frontend` restituisce ~2,2 KB che puntano a 3 file per
21 KB complessivi, contro i ~101 KB dell'intero `src/`.

Quel guadagno però si ribalta facilmente nel suo contrario — se la risposta è
grossa, l'agente paga i token dell'indice **e poi** quelli dei file. Perciò la
risposta è **navigazionale**, non documentale:

- **niente testo dei simboli per default**: solo `symbol_id`, `file`, `kind`,
  `dev_type` e `score`, più l'aggregato `files` — l'elenco dei file da aprire, che
  è la sola cosa che l'agente deve davvero ricavarne;
- `&snippet=true` aggiunge il testo, **troncato** a `code_search_api_snippet_chars`
  (400): sullo stesso esempio raddoppia la risposta, ed è per questo un'eccezione
  dichiarata nel prompt, non il default;
- `&k=` è limitato da `code_search_api_max_k` (25) e `max_per_file` impedisce a un
  file autogenerato di occupare tutte le posizioni;
- `&dev_type=` restringe all'ambito della feature. Il filtro agisce **prima** dei
  top-k (`search_code_symbols(subset_idx=...)`, indici per ambito precalcolati una
  volta per snapshot in `api/deps._prep_dev_type_index`): applicato a valle, un
  ambito poco rappresentato sparirebbe ogni volta che i top-k globali appartengono
  a un altro ambito.

Il prompt finale è costruito in `core/pipeline.py`. La variante `external`, da
copiare in Claude Code/Cursor, descrive le API HTTP. Per l'esecuzione in-app la
dashboard richiede `/api/pipeline/final-prompt?feature=<feature>&consumer=agent&mode=<mode>`:
Suggest e Agentic consultano l'indice tramite i tre tool MCP locali; One-shot
riceve Canvas e Spec allegati in JSON, perché non ha strumenti di lettura.
I percorsi in-app sono assoluti: Agentic lavora dentro `code/`, mentre l'indice
restituisce path relativi alla radice del progetto. Se il prompt della modalità
non è disponibile, l'esecuzione non parte con un prompt esterno incompatibile.

Il prompt in-app richiede contesto su domanda: ricerca codice con `k=5`, ambito
`dev_type` e `snippet=false`; grafo e norme solo quando necessari. Per ogni
scenario chiede modifica o proposta, copertura dei test e lacune residue.
Suggest resta in sola lettura; Agentic può scrivere codice e test ma non eseguirli,
perché Bash resta escluso. Il resoconto deve distinguere implementato da verificato.

Il bridge configura direttamente il processo stdio usando lo stesso interprete
Python del backend. Il backend HTTP deve essere avviato e raggiungibile tramite
`VIBECRAFT_MCP_BACKEND_URL` (default `http://127.0.0.1:8000`); URL, timeout e chiave
sono ereditati dall'ambiente; l'ID del progetto catturato viene passato al MCP
come `VIBECRAFT_PROJECT_ID`, indipendentemente dalla selezione corrente nel browser.
Il prompt esportato dichiara l'header progetto per HTTP e l'ID per il client MCP.
`strict_mcp_config=True` esclude altri server MCP,
`tools` limita i tool nativi e `allowed_tools` autorizza solo i tre tool MCP nominati.
`VIBECRAFT_AGENT_MAX_TURNS` limita il ciclo a 30 turni per default (intero 1–200);
One-shot ha un solo turno. Gli errori di configurazione chiudono lo stream con errore.
Su Windows viene usato, se presente accanto allo shim npm, il binario nativo
`node_modules/@anthropic-ai/claude-code/bin/claude.exe`; lo shim `.cmd` non viene eseguito.

### Runner dell'agente: Claude, Ollama, Codex, Cursor

`POST /api/pipeline/agent/run` accetta `runner` (`claude` | `local` | `codex` | `cursor`,
default `claude`) accanto a `mode`; `GET /api/pipeline/agent/runners` elenca quelli
con capability esplicite (binario installato, modelli Ollama, export e lancio disponibili).
Ammissione, gate, journal e formato NDJSON dello stream sono gli stessi per tutti
([agent_runners.py](../agent_runners.py)). Il nome modello è vincolato da una regex: finisce
negli argomenti delle CLI, quindi niente `-` iniziale né metacaratteri.

| runner | modalità | contesto | perimetro |
|---|---|---|---|
| `claude` | suggest, agentic, oneshot | tre tool MCP | bridge SDK descritto sopra |
| `local` (Ollama `/api/chat`) | suggest, agentic, oneshot | `read_file`/`list_files`/`grep` | i tool li esegue VibeCraft, niente shell; letture nella root del progetto, escludendo altre root, link, `.git` e `.env*`; in agentic `write_file`/`edit_file` passano da `_path_escapes_code`, la stessa decisione dell'hook Claude; output dei tool troncato a 6.000 caratteri |
| `codex` | export prompt | MCP esterno con ID esplicito | integrato disabilitato: isolamento letture non verificato |
| `cursor` | export prompt | MCP esterno con ID esplicito | integrato disabilitato: isolamento letture non verificato |

L'avvio integrato resta disponibile per `claude` e `local`. Per `codex` e
`cursor` il server restituisce 400 `native_read_isolation_unverified` prima
di avviare la CLI: cwd e sola lettura non dimostrano isolamento fra progetti.
`GET /api/pipeline/agent/runners` distingue `installed`, `available`,
`export_available` e motivo di indisponibilità; il binario installato non
rende disponibile il lancio. Export prompt e MCP esterno sono utilizzabili
anche senza binario. Il nome modello e i timeout conservano i vincoli esistenti.
Claude/local catturano root, code_root e ID del progetto; Read e scansioni
sicure restano disponibili, scritture soltanto in `code/`. Link, segreti,
`.git` e progetti annidati sono esclusi; uno scan SDK di un subtree che li
contiene è negato, il runner locale applica pruning.

Verifica locale senza provider o corpus privato:
`python -m pytest tests/test_agent_bridge_perimeter.py tests/test_agent_runners.py tests/test_pipeline.py tests/test_mcp_server.py tests/test_mcp_http.py`
e `node tests/pipeline_agent.cjs`. Il test stdio avvia il server dalla configurazione
del bridge e controlla i tre tool contro un backend HTTP con dati sintetici.

Il blocco dice tre cose che ne delimitano l'uso, e sono la parte che conta:
l'indice serve **solo** a scegliere cosa leggere, è uno snapshot dell'ultima
indicizzazione e può essere disallineato (i code-link restano stale fino al
rebuild), quindi ogni file va letto per intero prima di modificarlo e nessuna riga
va dedotta dai frammenti dell'indice; e se l'indice non risponde, l'agente procede
con Read/Grep — è una scorciatoia, non una dipendenza.


## MCP locale di sola lettura

Il backend HTTP locale deve essere già avviato con un indice pronto. Da PowerShell,
nella directory `rag`, avviare l'adattatore con:

```powershell
uv sync --frozen
$env:VIBECRAFT_MCP_BACKEND_URL = 'http://127.0.0.1:8000'
$env:VIBECRAFT_PROJECT_ID = '<id-del-progetto>'  # omettere per legacy
uv run --frozen python -B mcp_server.py
```

Il processo attende il protocollo su stdin; non è una console interattiva.
Per Claude Code, `.\scripts\install_mcp.ps1 [-Scope user|local|project]
[-BackendUrl http://127.0.0.1:8000]` esegue `uv sync --frozen` e registra il server
`vibecraft` con il Python di `.venv`; rieseguirlo sostituisce la registrazione.
Configurazione essenziale di un **client locale** che eredita l'ambiente:

```json
{
  "mcpServers": {
    "vibecraft": {
      "command": "C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe",
      "args": ["-B", "C:/Users/Silve/Desktop/vibecraft/rag/mcp_server.py"]
    }
  }
}
```

Adattare i percorsi al checkout da usare.
`VIBECRAFT_MCP_BACKEND_URL` vale per default `http://127.0.0.1:8000`;
sono ammessi solo HTTP, `127.0.0.1`, `::1` e `localhost` (riscritto in `127.0.0.1`,
senza DNS). Niente path, credenziali nell'URL, proxy d'ambiente o redirect.
`VIBECRAFT_API_KEY`, se necessaria, va ereditata dall'ambiente del client:
l'adattatore la inoltra in `X-API-Key` e non legge file di segreti.
`VIBECRAFT_PROJECT_ID` è catturato una volta e inoltrato come
`X-VibeCraft-Project`; riavviare la sessione MCP per cambiare progetto. Senza
ID si usa solo legacy. L'auth resta invariata: bypass loopback per
standalone/writer, chiave obbligatoria anche su loopback in reader.
`VIBECRAFT_MCP_TIMEOUT_SECONDS` imposta la scadenza totale e HTTP: default 30 s,
intervallo 0,1–120 s. Nessuna nuova porta MCP.

I soli tool sono `vibecraft_retrieve`, `vibecraft_code_search` e
`vibecraft_graph_query`. Gli argomenti sono contenuti nell'oggetto `params`, per esempio
`{"params":{"q":"quali documenti esistono?","limit":20}}` per il grafo.
Le risposte strutturate preservano ordine, identificatori e punteggi HTTP.

- Retrieval: `q` 1–4000 caratteri, `k` 1–50 (default 5), `include_text` default true
  nel tool e false nell'API HTTP; `text_max_chars` 1–8000 (default 2000) per chunk.
  `text_chars`, `text_truncated`, `source_label` e `index_version` dichiarano origine
  e taglio. La collection è quella del manifest dello snapshot catturato.
- Codice: `q` 1–2000, `k` 1–25 (default 8), `dev_type` fino a 64 caratteri,
  `snippet` default false. `min_score` 0–1 e `max_per_file` 0–10 sono opzionali:
  se omessi si usano i default del backend. I limiti effettivi e il taglio del testo
  sono espliciti. Un backend configurato con un tetto inferiore può rifiutare la richiesta.
- Grafo: `q` 1–2000, `target` opzionale fino a 1000 caratteri, `limit` 1–1000
  (default 100), condiviso fra elenchi e anelli. `count` conserva il totale originale;
  `returned_count` conta gli elementi restituiti (inclusa la radice negli anelli).
  `truncated` segnala gli elementi omessi. Impatto limitato a due hop; nessun Cypher/SQL.
  L'API HTTP senza `limit` conserva la risposta storica.

Top-k, filtri, indice non aggiornato e troncamento impediscono di dedurre un'assenza
nel progetto da un elenco vuoto o parziale. Le fonti sono dati, non istruzioni.
Oltre 2 MiB la risposta viene rifiutata per intero; ridurre i limiti.
Errori di input, autenticazione, backend non disponibile, timeout, redirect e JSON
non valido producono errori MCP senza corpo HTTP, URL sensibili o chiavi. Log su stderr.

Spegnimento: disabilitare la voce nel client e chiudere il processo stdio, oppure
Ctrl+C se avviato manualmente. Il backend HTTP resta indipendente; nessun rebuild
o interruttore aggiuntivo. In container eseguire il processo **dentro lo stesso
container del backend**, per esempio `docker exec -i <container> python -B mcp_server.py`
(senza `-t`); il backend resta su loopback dal punto di vista dell'adattatore.

L'esecuzione in-app collega questi tool al solo runner `claude`: gli estratti richiesti
entrano nel contesto del modello remoto. One-shot invia invece Canvas e Spec nel prompt.
Per Codex/Cursor esterni si può esportare il prompt e configurare questo MCP
nel client con l'ID esplicito: il lancio integrato resta disabilitato. Il
client esterno mantiene la propria policy di accesso ai file; VibeCraft non
certifica il suo sandbox. Solo `local` resta interamente sulla macchina.
L'accesso al corpus privato da altri client o provider richiede autorizzazione
esplicita. I test automatici usano dati sintetici e non chiamano il modello.
Il server MCP resta di sola lettura: non espone `/ask`,
intake, scritture, shell, reindex o l'avvio dell'agente.

Benchmark riproducibile, con backend pronto e senza carichi concorrenti:
`python -B -m scripts.bench_mcp --pairs 30`. Tre warm-up per tool sono esclusi;
JSON su stdout con ogni coppia e p50/p95. Il delta abbinato include anche la
variabilità fra le due esecuzioni del backend: non è il tempo totale di retrieval.
Il limite di accettazione del delta p95 è **10 secondi (10.000 ms)**, aggiornato
su richiesta del manutentore dopo le misure della sessione 5. Il JSON registra
`overhead_limit_ms` insieme all'esito; il timeout delle chiamate resta 30 s di default.

### Ricerca e punti aperti: perimetro advisory

Propose e conclusione dell'agente condividono lo schema `core/open_points.py`:
sezione finale `## Punti aperti`, un fence `json` con `{"open_points":[...]}`,
fuori dagli scenari Gherkin. Ogni punto conserva ID, funzionalità, domanda originale
(`original_question`), domanda attuale, assunzione da confermare, casi scoperti,
motivo e resoconto dell'ultimo giro di ricerca. Prima di ogni ricerca l'agente
dichiara la domanda e l'informazione mancante; dopo dichiara le nuove evidenze.
Se non ne ottiene, chiude quel ramo con `reason: no_new_evidence` e lo mantiene
nella stessa lista dei punti aperti di Propose. La chiusura riguarda la ricerca,
non la risoluzione del punto: gli altri rami indipendenti possono proseguire.

Conta solo contenuto pertinente non già nel contesto accumulato, riferito a
documento/chunk e porzione letta, file/simbolo o relazione. Ranking, parafrasi,
ID o versioni diversi con lo stesso contenuto non bastano; leggere la parte
prima troncata può aggiungere evidenza. Il runtime **non verifica** novità,
pertinenza, sequenza delle ricerche o arresto del ramo: `research_policy`
dichiara `enforcement: advisory` e `verification: agent_reported`.
Gli ID li assegna l'agente: `id_reuse_verified: false` e
`original_question_verified: false` espongono il limite anti-parafrasi.
La domanda originale rende due punti simili ispezionabili, ma l'agente può
ancora cambiarla o assegnare un altro ID; nessun confronto semantico è applicato.

Propose, lettura/salvataggio Spec, export del contratto e risultato NDJSON
restituiscono `open_points_status`:

| Stato | Payload | Significato |
| --- | --- | --- |
| `missing` | `open_points` assente | Resoconto/campo non fornito, anche per Spec precedenti |
| `invalid` | `open_points: null`, `open_points_error` | Resoconto presente ma malformato |
| `valid` | `open_points: []` oppure lista | Schema valido, contenuto dichiarato dall'agente |

Solo `valid` con lista vuota mostra «Terminato senza punti aperti» in UI,
con il limite advisory accanto. Gli altri stati sono distinti e uno stream
senza risultato finale è segnalato come interrotto. Il testo originale resta
nella Spec (anche `spec.raw.md` per Propose) o negli eventi testuali del bridge.
Il prompt esterno usa lo stesso protocollo, ma il suo output non rientra
automaticamente nella pipeline. Il gate seguente vincola gli avvii agentic
eseguiti dal server; non governa le esecuzioni esterne avviate autonomamente.

### Gate — enforcement agentic, validazione e decisioni

**L'avvio agentic richiede una validazione superata del contratto corrente.**
`POST /api/pipeline/agent/run` riceve feature e validation_id e ricalcola
`evaluate_gate` sul server; non accetta allowed/force e ignora il prompt client
in agentic. Il prompt è costruito da Canvas, Spec e decisioni congelati nel
record. Suggest/oneshot restano disponibili, con i motivi del gate visibili.
Il gate è identico per ogni runner; agentic è ammesso solo con `claude` e `local`.
La UI «Confronta con la versione validata» mostra i testi conservati e quelli
correnti; senza validazione dichiara l'assenza del confronto.
Il 409 indica documenti, validazione e rimedio; il 503 segnala l'infrastruttura
e conserva anche gli altri reasons. L'avvio agentic non parte se non può essere
registrato in `database/pipeline/events.jsonl`.
[Piano e schema dei record](../adr/PIPELINE_GATE.md).

Il nucleo distingue missing/invalid, unaddressed, mismatch, failed/stale e
unavailable, con azioni user_action/operator_action/retryable. Blocca sui soli
documenti forniti al validatore; il resto del corpus produce un avviso. Nessun
TTL, riparazione JSON, normalize_spec nel calcolo dell'hash o force.
Canvas, Propose, dry-run e contesto dell'agente distinguono i guasti del retrieval
governato dai risultati validi ma vuoti. Un guasto operativo restituisce 503
senza chiamare il modello o sovrascrivere gli artefatti della feature.

Sequenza originaria: **recorder provider minimo → ablazione prompt → decisione
sul pilot → eventuale baseline A → commit dedicato all'isolamento delle
impostazioni → gate → misure B e C**. Nessuno starter prima della decisione;
se approvato, checkpoint dopo un'ora di preparazione. Il recorder SDK è rinviato
al pilot. `eval/provider_recorder.py` osserva Ollama solo se attivato esplicitamente
da un runner di valutazione in un processo separato, seriale. Il server non lo
importa: nessuna registrazione in produzione. Copia i payload prima dell'estrazione
del testo, senza cambiare richieste, retry o cache; conserva i contatori restituiti,
mai token stimati. Gli errori del recorder rendono incompleta la misura, senza
ritentare la generazione. I test acceso/spento usano il vero percorso provider
con risposte HTTP simulate, inclusi errori e retry. Non promette overhead nullo.
La Fase 2 è ora [chiusa](../eval/results/FASE2_PROPOSE_20260914.md), senza pilot.
La sequenza approvata è isolamento delle impostazioni → adozione V3 → gate,
con un checkpoint per ogni commit. L'isolamento è applicato come segue;
l'enforcement dell'avvio e gli eventi sono implementati.

Il bridge imposta `setting_sources=[]` esplicitamente
per **suggest, oneshot e agentic**, preservando l'hook SDK di confinamento
delle scritture di agentic. `tests/test_agent_settings_isolation.py` usa il
CLI/SDK reale in tutte e tre le modalità: hook `SessionStart` innocui nelle
impostazioni user, project e local creano sentinelle in un ambiente temporaneo
quando le fonti sono caricate esplicitamente; con le opzioni reali isolate
non le creano. Il test inizializza soltanto la sessione, senza prompt o
generazioni. Il controllo positivo e il motivo per conservarlo sono in testa
al test: la sola assenza dei tool o della sentinella non basta come prova.
Esecuzione da `rag/`: `python -m pytest tests/test_agent_settings_isolation.py -q`.
Richiede il CLI Claude installato (quello incluso nell'SDK o quello nativo
selezionato dal bridge), non una credenziale provider. Un controllo positivo
fallito fa fallire il test: non viene trasformato in uno skip.
Se emergono dipendenze operative dalle impostazioni locali, fermare il lavoro
e segnalarle prima di procedere, senza riabilitarle implicitamente.
Garanzia per suggest e oneshot: **nessuna scrittura applicativa comandabile dall'agente o dagli hook locali**; agentic conserva le
scritture applicative confinate previste. Non si promette che il processo non
scriva alcun byte, per esempio nei propri file di sessione.

Garanzia dell'accettazione nel design approvato:

> L'accettazione non è esposta agli strumenti dell'agente; non è certificata
> come decisione umana dalla credenziale condivisa.

La garanzia è anche nella docstring del writer `PipelineStore.record_decision`
e della route di decisione; i requisiti per cambiare `origin_verified` sono
accanto al punto in cui il writer lo impone. `core/open_points.py` distingue
il resoconto advisory dell'agente dalle decisioni registrate dal server.

Un punto `accepted` resta esplicitamente irrisolto; `resolved` registra una
risoluzione, mentre `unaddressed` segnala l'assenza di una decisione. L'accettazione
è legata al contenuto integrale del punto, non al solo ID, e la decisione entra
nell'impronta del contratto eseguibile. Accettare una lacuna non rende soddisfatti
gli scenari interessati; `uncovered_scenarios: []` non certifica la marginalità.

Il record di decisione conserva provenienza dichiarata, metadati
osservati della chiamata ed esecuzioni attive sulla stessa feature, con
**`origin_verified: false` obbligatorio e imposto dal server**, non configurabile
né promuovibile tramite input del chiamante. Schema e test rifiutano
`true` nel protocollo basato sulla chiave condivisa.
Per poter introdurre `true` serviranno un'identità personale autenticata
(non una chiave condivisa), un legame verificato dal server fra identità e
provenienza della richiesta e una revisione esplicita di questa garanzia.
Un nome dichiarato, un header che dice "UI" o il possesso della chiave non bastano;
neppure l'identità personale prova da sola che qualcuno abbia letto il punto.

Possiamo contare le accettazioni **avvenute durante** un'esecuzione dell'agente,
non possiamo chiamarle accettazioni **effettuate dall'agente**. La correlazione
temporale non distingue una sessione UI concorrente da una richiesta automatica.
La correlazione usa un registry condiviso su disco (`database/pipeline/activity/`,
`activity_scope=shared-disk`): i worker che condividono lo stesso database vedono
le stesse esecuzioni attive; i PID morti vengono purgati in lettura. Le
esecuzioni prive di feature sono elencate separatamente. La feature del client
in suggest/oneshot resta dichiarata; in agentic viene confrontata con il record
validato. Gli eventi della Fase 2 sono nel journal della pipeline,
separati dallo storico delle valutazioni. Un tentativo senza evento conclusivo
non certifica il completamento; un errore di registrazione indica misura incompleta.

I rilievi strutturali globali `scenari_insufficienti` e `caso_negativo_mancante`
restano bloccanti finché l'operatore non li associa esplicitamente a un punto
accepted. Nessuna associazione preselelezionata, nessuna deroga GIVEN/WHEN/THEN.
Restano visibili, con decisione, autore dichiarato e `origin_verified: false`.
L'associazione integrale entra nell'hash; cambiando la Spec decadono sia la
decisione sia l'associazione. Una lacuna accettata non certifica copertura.
La scelta emersa in implementazione e i suoi limiti sono nel piano del gate.


## Verifica multi-progetto — 5 ottobre 2026

Gate finale: **2.348 passed, 20 skipped**, lint e check Node superati,
review indipendente approvata. Sono stati verificati HTTP/Qdrant/browser reali,
A/B con nomi/query/feature omonimi, job concorrenti e persistenza Docker. I 20
skip dipendono dai privilegi file-symlink Windows; prove Linux complementari
eseguono link reali. Docling e LibreOffice sono stati eseguiti con asset locali.
I provider sono simulati ai confini. Docker è provato con sorgente corrente
montato in runtime CPU esistente: build immagine da zero e GitHub Actions
non eseguiti. Questi risultati non verificano provider remoti o release pubblicate.

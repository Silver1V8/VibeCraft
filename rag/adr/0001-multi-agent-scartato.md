# 0001 — Multi-agent supervisor scartato

## Contesto

`rag/` è un sistema RAG mono-processo con **un solo layer LLM**
([core/llm.py](../core/llm.py), unificato da R4/R12): tutte le chiamate
generative (drift, canvas, propose, validate, explore, canvas review, `/ask`)
passano dallo stesso client, un solo modello residente (`qwen3.5:9b` via
Ollama locale, vedi setup GPU RTX 3070 Ti). Il progetto ha un solo
manutentore.

M1 (`eval/m1`, commit `53758cb`) ha misurato su un golden-set
strutturale/multihop di 14 casi il confronto tra retrieval semantico puro
(A = `/api/retrieve` k=10) e riferimento su grafo (B = `/api/graph/query`,
exact-node-match):

- recall media A = **0.642** (14 casi), A riuscito in **5/14**
- B exact match in **6/6** casi strutturali valutabili
- **6 casi qualificanti** (A fallito, B riuscito) contro una soglia trigger
  di **3** → **trigger M2 SCATTATO**
  (`eval/results/multihop_20260721_110336.json`)

Di fronte al trigger, la review architetturale ha valutato tre risposte
possibili:

- **Opzione A — approvata**: restare su un'architettura a codice
  deterministico (nessun LLM aggiuntivo nel query path), risolvendo i casi
  strutturali con logica esplicita invece che con retrieval "più intelligente".
- **Opzione B — deterministica, già in essere**: prima istanza concreta
  dell'opzione A. Un router deterministico (`core/router.py`, regex
  conservative, 5 regole giustificate una-per-una dai 6 casi structural del
  report M1) instrada `/ask` su `"graph"` (risposta diretta via
  `graph_ops.graph_query`, niente LLM) o `"hybrid"` (percorso RAG esistente)
  — commit `6cd0c78` su `feat/m2-deterministic-router`. Zero falsi positivi
  sul golden-set classico, eval invariati (recall@10 = 1.000).
- **Opzione C — scartata**: un supervisor multi-agent (un LLM che orchestra
  altri LLM/agenti — pattern LangGraph/CrewAI-style) davanti a `/ask`, per
  gestire routing, retrieval e composizione della risposta come agenti
  autonomi cooperanti.

## Decisione

**Il supervisor multi-agent è SCARTATO**, non rimandato genericamente: è
una non-scelta esplicita, con trigger di riapertura nominati (vedi sotto).
L'architettura resta a **singolo layer LLM + codice deterministico** attorno
ad esso (router, retrieval, eval-gate, blue/green sono tutti codice, non
agenti).

## Motivazioni

Operative, non di principio:

1. **Un solo modello residente.** `qwen3.5:9b` è l'unico modello caricato
   (vincolo VRAM RTX 3070 Ti, vedi setup GPU). Un supervisor multi-agent
   implica più chiamate LLM per singola richiesta utente; con un solo
   modello residente e nessun secondo backend, quelle chiamate sono
   **seriali**, non parallele: ogni agente aggiuntivo nella catena somma
   latenza piena, non la nasconde.
2. **La generazione domina già la latenza, prima di aggiungere agenti.**
   Nel benchmark baseline (commit `2ba9ab0`,
   `eval/results/bench_20260721T084815Z.json`) la latenza media totale di
   `/ask` è **~49s** (48955.74ms) a fronte di un retrieval sub-secondo
   (p50 494ms, p95 647ms): la generazione LLM da sola vale quindi
   **~47-48s**. Un secondo (o terzo) hop LLM in un supervisor multi-agent
   moltiplicherebbe questo numero, non lo ammortizzerebbe — non c'è
   parallelismo da sfruttare finché il retrieval resta la parte veloce.
3. **Mono-manutentore.** Debuggare lo stato conversazionale di più agenti
   che si scambiano messaggi (chi ha detto cosa, perché un agente ha
   deciso X) è un costo che un solo manutentore non può ammortizzare — a
   differenza di logica deterministica, ispezionabile con un debugger
   normale e testabile senza mockare un LLM.
4. **`/ask` è un query path read-only.** Le uniche scritture nel sistema
   passano da percorsi già controllati e deterministici (indicizzazione,
   blue/green, canvas/archive). Introdurre agenti autonomi nel query path
   di lettura sarebbe l'unico punto in cui il comportamento del sistema
   smetterebbe di essere prevedibile da codice — un rischio non
   giustificato da un guadagno di qualità che il router deterministico
   (Opzione B) ha già coperto per i casi misurati.

## Conseguenze

- Nessuna dipendenza da framework agentici (LangGraph, LlamaIndex agents,
  CrewAI, ...) nel repo.
- Ogni step generativo resta dietro `core/llm.py`: un solo client da
  mantenere, un solo punto di failure per errori LLM (`LLMError`),
  guardrail (`think`, `num_ctx`) uniformi.
- I casi strutturali del golden-set restano coperti da codice deterministico
  (router M2 + `graph_query`), non da un agente che "decide" come rispondere.
- Questo ADR **non** blocca l'evoluzione del router deterministico (nuove
  regole, nuovi intent) — blocca solo l'introduzione di orchestrazione
  agentica LLM-su-LLM.

## Trigger di rivalutazione

Questa decisione va riaperta (non necessariamente ribaltata) se **uno
qualsiasi** dei seguenti si verifica:

1. Il sottoinsieme **multi-hop** del golden-set (misurato con lo stesso
   harness A/B di `eval/m1`) scende **sotto il 70%** di recall media A,
   mentre il golden-set **single-hop** di produzione
   (`eval/golden_set.yaml`, oggi recall@10 = 0.955 su 22 casi) **resta
   sopra il 90%** — cioè il problema è specificamente multi-hop, non un
   regresso generale del retrieval.
2. Le trace di osservabilità M3 di `/ask`
   ([api/routes_retrieval.py](../api/routes_retrieval.py), campi
   `latency_retrieval_ms`/`latency_generation_ms`) mostrano la latenza
   **dominata da retrieval parallelo mancante** — oggi è dominata dalla
   generazione (vedi Motivazioni #2); se questo rapporto si inverte, il
   calcolo su "un agente in più = seriale" cambia.
3. Diventa disponibile un **secondo backend di inferenza** (secondo modello
   residente, o provider esterno a basso costo) — rimuove il vincolo
   "un solo modello, tutto seriale" della Motivazione #1.
4. Un **esperimento offline documentato**: un verifier LLM corregge
   **≥30%** degli errori di grounding su un campione di 20 risposte,
   **senza introdurne di nuovi** — prova concreta che un hop LLM aggiuntivo
   paga la sua latenza.

## Primo passo futuro ammesso

Se uno dei trigger sopra scatta, il primo passo ammesso è un **workflow
Python minimale e deterministico**:

```
router deterministico -> retrieval -> verifier deterministico -> synthesizer
```

Esplicitamente **NON**:

- NON LangGraph
- NON LlamaIndex (agents)
- NON l'aggiunta di ulteriori agenti LLM nel query path

Il verifier e il synthesizer restano funzioni Python (eventualmente con
**una** chiamata LLM ciascuno, dietro `core/llm.py` come oggi), orchestrate
da codice esplicito e testabile — non da un supervisor che decide a runtime
quale agente invocare.

## Esito reale del trigger M2

**Trigger M2: SCATTATO** (6 casi qualificanti ≥ soglia 3,
`eval/results/multihop_20260721_110336.json`).

**Decisione presa**: implementato il router deterministico (Opzione B,
commit `6cd0c78`, branch `feat/m2-deterministic-router`) — non un agente,
5 regole regex davanti al retrieval di `/ask`. Il supervisor multi-agent
(Opzione C) non è stato implementato: è l'oggetto di questo ADR, scartato
con i trigger di rivalutazione sopra.

# Gate di rispondibilità pre-LLM per /ask — piano di implementazione

> **Per chi esegue:** sotto-skill richiesta: superpowers:subagent-driven-development (consigliata)
> oppure superpowers:executing-plans, un task alla volta. Gli step usano le checkbox (`- [ ]`).

**Obiettivo:** un punteggio di rispondibilità assoluto, calcolato in locale prima del LLM, che
prima si osserva (shadow) e solo se la misura lo giustifica salta la generazione sulle domande
a cui il corpus non risponde.

**Architettura:** un cross-encoder locale (`BAAI/bge-reranker-v2-m3` via `FlagReranker`, già
dentro `flagembedding==1.4.2`) giudica le coppie (domanda, sezione) per le sezioni che entrano
DAVVERO nel contesto (ramo semantico + ramo grafo). Il massimo dei punteggi normalizzati è la
rispondibilità. Il gate decide solo SE chiamare il LLM: non riordina e non filtra il contesto.

**Stack:** FastAPI, FlagEmbedding 1.4.2 (`FlagReranker`), torch CPU, pytest.

**Spec:** la sezione "Decisione" qui sotto (nata dal confronto con l'articolo "RAG vs Jev + RAG",
2026-11-03).

## Decisione

- **Perché:** il MaxSim ColBERT cambia scala da query a query (commento in
  `core/ask.py:540`), quindi oggi non esiste un segnale assoluto di "il contesto basta". L'unico
  giudice è qwen3.5:9b tramite `[REGOLA-ASTENSIONE]`, che paga una generazione intera anche
  quando poi si astiene, e che ha già sbagliato il formato del marcatore (R27).
- **Cosa NON si fa:** niente Jev né altri servizi ospitati, perché domanda e sezioni non escono
  dalla macchina. Niente filtro dei singoli passaggi dal contesto: in S6 il terzo documento delle
  catene multihop entra con pertinenza bassa ma è essenziale (`api_error_contract` → `409`).
- **Fasi:** `off` (default) → `shadow` (calcola, logga, espone, non decide) → `enforce` (salta il
  LLM). Si passa a `enforce` solo se il Task 6 dà esito "go".
- **Criterio go/no-go (Task 6):** con la soglia più alta che non fa perdere NESSUN positivo,
  almeno il 50% dei negativi è sotto soglia, E la latenza del gate ha p95 ≤ 2000 ms su CPU.

## Vincoli globali

- Nessuna dipendenza nuova: `uv.lock` e `pyproject.toml` non cambiano.
- Il reranker gira su CPU (`devices="cpu"`): la GPU è di Ollama.
- `answerability.mode: off` di default; la CI non scarica modelli (solo stub nei test).
- Non toccare `boost_alpha`, `graph_context_max_chunks`, `section_restatement_weight`,
  `graph_context_min_ratio` (calibrazione congiunta S11).
- Nessuna route HTTP né tool MCP nuovi; il campo `answerability` nel payload di `/ask` è additivo.
- Commenti in italiano che spiegano il perché, con sigla `G1` (gate di rispondibilità); commit in
  inglese con prefisso convenzionale.
- Prima di ogni commit: `cd rag && bash scripts/ci.sh` verde.
- Dopo modifiche Python il server va riavviato (preview_start `vibecraft-rag`): non c'è reload.

## Focus di review

1. **Domanda di follow-up nel filo** (`use_thread` con filo non vuoto, es. "e per l'altro
   caso?"): da sola è ellittica, il cross-encoder la scora basso → in `enforce` NON deve astenersi.
   Test nel Task 7.
2. **Domanda solo implementativa** (nessuna sezione di documento in contesto, solo codice): il
   gate non ha passaggi da giudicare → `answerability` è `None`, mai astensione. Test nel Task 4.
3. **Catena multihop** con la risposta nella sezione arrivata via grafo: i passaggi giudicati
   devono includere le sezioni del ramo grafo, non solo il top-k semantico. Test nel Task 4,
   misura sui positivi di `golden_multihop.yaml` nel Task 6.
4. **Modello del reranker assente o non caricabile** (offline, cache HF vuota): `/ask` risponde
   come oggi (fail-open, il LLM gira) e logga l'errore una volta. Test nel Task 3.
5. **Risposte servite dalla cache** create prima del gate: non hanno `answerability`; lo script
   di calibrazione le segnala invece di trattarle come punteggio mancante. Test nel Task 5.

---

### Task 1: Set di domande senza risposta

**File:**
- Crea: `rag/eval/golden_unanswerable.yaml`
- Test: `rag/tests/test_golden_unanswerable.py`

**Interfacce:**
- Produce: YAML con `cases: [{id: str, q: str, kind: str, why: str}]`, `kind` ∈
  {`fuori_tema_adiacente`, `valore_mancante`, `presupposto_falso`}. Lo usa il Task 5.

Almeno 15 casi, almeno 4 per tipo. Il tipo `valore_mancante` è il caso difficile dell'articolo
(la domanda chiede un numero o un nome che il documento pertinente NON dichiara) e deve avere
almeno 6 casi. Ogni caso va verificato contro la baseline COMMITTATA (lezione del 2026-08-25 in
`golden_set.yaml`): `vibecraft_retrieve` sulla domanda, poi lettura delle prime 5 sezioni, e
`why` cita cosa manca e in quale documento si è guardato. Intestazione del file con data,
commit della baseline e istruzioni per aggiungere casi.

- [ ] **Step 1: Scrivi il test**

```python
def test_set_senza_risposta_ben_formato():
    casi = yaml.safe_load(PATH.read_text(encoding="utf-8"))["cases"]
    assert len(casi) >= 15
    assert len({c["id"] for c in casi}) == len(casi)
    tipi = Counter(c["kind"] for c in casi)
    assert set(tipi) == {"fuori_tema_adiacente", "valore_mancante", "presupposto_falso"}
    assert min(tipi.values()) >= 4 and tipi["valore_mancante"] >= 6
    assert all(c["q"].strip() and c["why"].strip() for c in casi)

def test_nessuna_domanda_coincide_coi_positivi():
    positivi = {c["q"].strip().lower() for c in load_cases(GOLDEN)}
    assert not positivi & {c["q"].strip().lower() for c in casi_senza_risposta()}
```

- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/test_golden_unanswerable.py -v` → FAIL (file assente).
- [ ] **Step 3:** scrivi i casi, verificati come sopra.
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5:** `bash scripts/ci.sh`, poi commit `test: add unanswerable question set for the answerability gate`.

### Task 2: Modulo puro `core/answerability.py` e configurazione

**File:**
- Crea: `rag/core/answerability.py`
- Modifica: `rag/core/config.py` (dopo il blocco `_retrieval_cfg`, ~riga 535), `rag/rag_config.yaml` (nuovo blocco di primo livello `answerability:`)
- Test: `rag/tests/test_answerability.py`

**Interfacce:**
- Produce (config): `ANSWERABILITY_MODE: str` (`off|shadow|enforce`, default `off`, valore
  ignoto → `ValueError` al boot), `ANSWERABILITY_MODEL: str` (`BAAI/bge-reranker-v2-m3`),
  `ANSWERABILITY_THRESHOLD: float | None` (default `None`), `ANSWERABILITY_TOP_N: int` (8),
  `ANSWERABILITY_MAX_LENGTH: int` (512).
- Produce (modulo):
  - `assess(reranker, question: str, passages: list[str], *, mode: str, top_n: int, threshold: float | None) -> dict | None`
    → `None` se `mode == "off"`, `reranker is None` o `passages` vuoto; altrimenti
    `{"mode", "score", "scores", "threshold", "would_abstain", "latency_ms"}`. `score` = max di
    `reranker.compute_score([(question, p) for p in passages[:top_n]])`, normalizzato a lista
    anche quando torna uno scalare (una sola coppia). `would_abstain` = `score < threshold`, ma
    `None` se `threshold is None`. Punteggi arrotondati a 4 decimali.
  - `should_short_circuit(assessment: dict | None, *, has_code: bool, thread_active: bool) -> bool`
    → `True` solo se `assessment["mode"] == "enforce"`, `would_abstain is True`, `not has_code`,
    `not thread_active`.

`normalize=True` e `max_length` si passano al costruttore di `FlagReranker` (Task 3), non qui: il
modulo riceve punteggi già in [0, 1].

- [ ] **Step 1: Scrivi i test** con uno `_StubReranker(punteggi)` che registra le coppie ricevute:
  - `assess(..., mode="off")` è `None` e lo stub non è chiamato;
  - passaggi vuoti → `None`; `reranker=None` → `None`;
  - punteggi `[0.2, 0.7, 0.1]` → `score == 0.7`;
  - `top_n=2` con 3 passaggi → lo stub riceve solo i primi 2, nell'ordine dato;
  - stub che restituisce lo scalare `0.3` per una coppia → `scores == [0.3]`;
  - `threshold=None` → `would_abstain is None`; `threshold=0.5`, score 0.4 → `True`;
  - `should_short_circuit`: tabella sui 4 ingressi (`shadow` → `False`; `enforce` + codice →
    `False`; `enforce` + filo → `False`; `enforce` + `would_abstain None` → `False`; solo il caso
    pieno → `True`);
  - `config`: `mode: banana` → `ValueError` (con lo stesso stile degli altri test di config).
- [ ] **Step 2:** `pytest tests/test_answerability.py -v` → FAIL.
- [ ] **Step 3:** implementa modulo, costanti e blocco YAML (`mode: off`, `threshold: null`, commento che rimanda a questo piano e al divieto di toccare S11).
- [ ] **Step 4:** → PASS.
- [ ] **Step 5:** `bash scripts/ci.sh`, commit `feat: add answerability scoring module (off by default)`.

### Task 3: Caricamento pigro del reranker

**File:**
- Modifica: `rag/api/index_runtime.py` (accanto a `ensure_shared_resources`, riga 489), `rag/api/deps.py` (re-export come alla riga 115)
- Test: `rag/tests/test_answerability_runtime.py`

**Interfacce:**
- Consuma: `ANSWERABILITY_MODE`, `ANSWERABILITY_MODEL`, `ANSWERABILITY_MAX_LENGTH` (Task 2).
- Produce: `ensure_reranker() -> object | None` in `api.index_runtime`, riesportato in
  `api.deps`. Con `mode == "off"` torna `None` senza importare nulla. Altrimenti costruisce UNA
  volta, sotto `deps._resources_lock`,
  `FlagReranker(ANSWERABILITY_MODEL, use_fp16=False, devices="cpu", normalize=True, max_length=ANSWERABILITY_MAX_LENGTH)`
  in `deps.state["reranker"]`. Se il costruttore solleva: `logger.exception` una sola volta,
  `deps.state["reranker_failed"] = True`, torna `None` e non ritenta fino al riavvio (fail-open:
  il LLM gira come oggi).

- [ ] **Step 1: Test** (monkeypatch di `FlagReranker` con un contatore):
  - `off` → `None`, costruttore mai chiamato;
  - `shadow` → due chiamate, costruttore chiamato una volta, argomenti `devices="cpu"` e `normalize=True`;
  - costruttore che solleva → `None` due volte, costruttore chiamato una volta sola.
- [ ] **Step 2:** → FAIL. **Step 3:** implementa. **Step 4:** → PASS.
- [ ] **Step 5:** `bash scripts/ci.sh`, commit `feat: lazily load the CPU reranker for the answerability gate`.

### Task 4: Shadow mode in `/ask`

**File:**
- Modifica: `rag/core/ask.py` (iniezione dei chunk ~righe 456 e 609, prima del passo 5 ~riga 688, riga di log M3 ~744, payload ~753)
- Test: `rag/tests/test_ask_answerability.py` (fixture sul modello di `tests/test_ask_abstention.py`)

**Interfacce:**
- Consuma: `answerability.assess` (Task 2), `deps.ensure_reranker` (Task 3).
- Produce: campo `payload["answerability"]` (il dict di `assess` oppure `None`) e chiave
  `answerability_score=` in coda alla riga di log M3. Lista ordinata `ordine_contesto: list[str]`
  dei chunk iniettati, accanto a `seen_chunks` (che è un set e perde l'ordine).

Il gate gira in `run_in_threadpool_until_complete` subito prima di `build_ask_prompt`, sui testi
di `chunks_store[cid]["text"]` per `cid in ordine_contesto`: sezioni semantiche E sezioni via
grafo, cioè quello che vede il LLM. Il codice non è un passaggio da giudicare. In shadow
l'esito di `/ask` non cambia.

- [ ] **Step 1: Test:**
  - `mode=off` → `answerability is None`, `ensure_reranker` mai chiamato;
  - `mode=shadow`, stub con punteggio 0.05 e soglia 0.5 → `status == "success"` (il LLM finto
    risponde), il LLM è stato chiamato, `answerability["would_abstain"] is True`;
  - due chunk in `hybrid_search` → lo stub riceve i due testi nell'ordine del ranking;
  - solo `code_hits`, nessun chunk → `answerability is None` (Focus di review 2);
  - `ensure_reranker` che torna `None` in shadow → `answerability is None`, risposta normale (Focus 4).
- [ ] **Step 2:** → FAIL. **Step 3:** implementa. **Step 4:** → PASS, e `pytest tests/test_ask_abstention.py tests/test_ask_streaming.py` ancora verdi.
- [ ] **Step 5:** `bash scripts/ci.sh`; agent `retrieval-calibration-guard` sul diff (atteso: nessun parametro S11 toccato); commit `feat: score answerability in shadow mode on /ask`.

### Task 5: Script di calibrazione

**File:**
- Crea: `rag/eval/calibrate_answerability.py`
- Test: `rag/tests/test_calibrate_answerability.py`

**Interfacce:**
- Consuma: `eval/golden_set.yaml`, `eval/golden_multihop.yaml` (positivi),
  `eval/golden_unanswerable.yaml` (negativi, Task 1), `payload["answerability"]` (Task 4).
- Produce: `choose_threshold(pos: list[float], neg: list[float], *, margin: float = 0.02) -> dict`
  → `{"threshold": min(pos) - margin, "neg_caught": n, "neg_total": n, "neg_caught_ratio": float, "go_ratio": bool}`
  con `go_ratio = neg_caught_ratio >= 0.5`; e `eval/results/answerability_<timestamp>.json`.

CLI come `eval/run.py` (`--url`, chiave da `VIBECRAFT_API_KEY` nell'ambiente, retry su 429).
Per ogni domanda: `POST /ask` con `use_thread: false`. Scarta e conta a parte le risposte
`graph_answer` (il router M2 non passa dal gate), `cached: true` e quelle senza `answerability`.
Exit 1 se le ultime due sono più di zero (Focus 5: server da riavviare o gate spento). Il report
stampa: distribuzione dei punteggi per gruppo, esito di `choose_threshold`, matrice
gate × astensione del LLM (`status == "abstained"`), p50/p95 di `latency_ms` del gate, e i 5
positivi con punteggio più basso (sono quelli che fissano la soglia).

- [ ] **Step 1: Test** su `choose_threshold`: pos `[0.6, 0.9]`, neg `[0.1, 0.55, 0.7]` → soglia
  0.58, `neg_caught == 2`, `go_ratio is True`; neg tutti sopra → `neg_caught == 0`,
  `go_ratio is False`; pos vuoto → `ValueError`. Test sul filtro: un payload `cached: true` e uno
  senza `answerability` finiscono fra gli scartati, non fra i punteggi.
- [ ] **Step 2:** → FAIL. **Step 3:** implementa. **Step 4:** → PASS.
- [ ] **Step 5:** `bash scripts/ci.sh`, commit `feat: add answerability calibration script`.

### Task 6: Run in shadow e decisione go/no-go

**File:**
- Modifica: questo file (sezione "Esito", da aggiungere), `rag/rag_config.yaml` (`mode: shadow` solo per il run)

Nessun codice. Il primo avvio scarica `bge-reranker-v2-m3` (~2,3 GB) nella cache HF: chiedi
prima all'utente.

- [ ] **Step 1:** `answerability.mode: shadow`, riavvia il server (preview_start `vibecraft-rag`), aspetta `/api/health` verde.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m eval.calibrate_answerability` → exit 0, report scritto.
- [ ] **Step 3:** scrivi in "Esito": soglia, negativi presi per tipo, p95 della latenza, matrice gate × LLM, i positivi più bassi con il motivo. Applica il criterio go/no-go della Decisione.
- [ ] **Step 4:** se **no-go**: riporta `mode: off`, commit `docs: record answerability gate shadow results (no-go)` e fermati. Il Task 7 non si fa.
- [ ] **Step 5:** se **go**: commit `docs: record answerability gate shadow results`, lasciando `mode: off` fino al Task 7.

### Task 7: Enforce (solo dopo un "go")

**File:**
- Modifica: `rag/core/ask.py` (subito dopo `assess`, prima di `acquire_llm`), `rag/rag_config.yaml` (`mode: enforce`, `threshold:` dal Task 6)
- Test: `rag/tests/test_ask_answerability.py`

**Interfacce:**
- Consuma: `should_short_circuit` (Task 2) con `has_code=bool(implementing_code or code_hits)`, `thread_active=bool(thread_block)`.
- Produce: quando scatta, il payload ha la stessa forma di quello generato dal LLM, con
  `status: "abstained"`, `abstained_by: "gate"`,
  `answer: "Il contesto recuperato non contiene elementi sufficienti per rispondere."`,
  `latency.generation_ms: 0`, `elaboration_seconds: 0.0`. Con `emit` il testo esce come un unico
  evento `delta`, come sul ramo della cache. Va in cache e nel filo come l'astensione del LLM. Il
  ramo esistente del marcatore aggiunge `abstained_by: "llm"` (campo additivo).

- [ ] **Step 1: Test** (provider LLM finto che SOLLEVA se chiamato):
  - enforce, punteggio 0.05, soglia 0.5 → `status == "abstained"`, `abstained_by == "gate"`, LLM non chiamato;
  - stesso caso con `stream: true` → arriva un evento `delta` con il testo;
  - enforce + `code_hits` non vuoti → LLM chiamato;
  - enforce + filo non vuoto (`use_thread: true` dopo un turno) → LLM chiamato (Focus 1);
  - enforce + `threshold: null` → LLM chiamato;
  - marcatore `[ASTENSIONE]` dal LLM → `abstained_by == "llm"`.
- [ ] **Step 2:** → FAIL. **Step 3:** implementa. **Step 4:** → PASS, più tutta la suite `/ask`.
- [ ] **Step 5:** agent `retrieval-calibration-guard` e `security-surface-reviewer` sul diff; `bash scripts/ci.sh`.
- [ ] **Step 6:** riavvia il server, rilancia `eval.calibrate_answerability` in enforce: nessun positivo con `abstained_by: "gate"`. Poi `/ci` completo.
- [ ] **Step 7:** commit `feat: skip generation when the answerability gate abstains`.

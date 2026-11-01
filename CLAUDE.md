# vibecraft

Piattaforma Graph RAG locale (FastAPI + Qdrant + Ollama) con pipeline di sviluppo guidata dai
documenti. Il codice vivo è in `rag/`; `projects/` contiene i progetti indicizzati, `templates/`
gli scheletri `docs/ code/ changes/`, `archive/` le evidenze delle eval passate.

## Struttura di `rag/`

- `core/`: logica pura, senza FastAPI. Le risorse a runtime (grafo, Qdrant, modello di embedding)
  arrivano come parametri, mai da globali. La configurazione sta sempre in `core/config.py`.
- `api/`: solo HTTP (`routes_*.py` sottili che iniettano `state` nelle funzioni core). La
  sicurezza (`require_api_key`, cross-site, Host, CSP) è in `api/deps.py`.
- `server.py` e `index.py` sono shim: non rimetterci logica.
- `rag_config.yaml`: parametri di retrieval e LLM, molti CALIBRATI (vedi sotto).
- Decisioni e piani in `rag/adr/`.

## Ambiente (Windows)

- Python solo da `rag/.venv/Scripts/python.exe` oppure `uv run` da `rag/`: `python` nel PATH
  apre il Microsoft Store e resta appeso.
- Heredoc Python in Git Bash: usa sempre `-X utf8`, o gli accenti diventano mojibake. Per
  stringhe con accenti preferisci il tool Edit.
- Molti file (template, test `.cjs`) sono CRLF: preserva i terminatori nelle sostituzioni multi-riga.
- Server di dev: preview_start `vibecraft-rag` (porta 8000, pronto in ~10 s). Dopo modifiche
  Python va riavviato, non c'è reload.

## Verifica

- Prima di commit/push: `cd rag && bash scripts/ci.sh` (uv sync --frozen, ruff, pytest -rs),
  che è identico alla CI. Non basta `pytest` da solo. Per tutto, inclusi i `.cjs` browser,
  usa `/ci`.
- I 5 test Qdrant si auto-saltano senza `VIBECRAFT_TEST_QDRANT_URL`: un verde locale non li copre.
- Il hook PostToolUse esegue ruff su ogni `.py` modificato sotto `rag/`.

## Regole che hanno già fatto danni

- **Full rebuild**: riavvia il server PRIMA di `POST /api/index/reindex {"full": true}`, o il
  rebuild gira col codice vecchio (~10 min buttati). Usa `/reindex-full`.
- **Calibrazione**: `boost_alpha` 0.3, `graph_context_max_chunks` 3 e `section_restatement_weight`
  0.92 sono accoppiati (S11). Mai cambiarne uno da solo: serve la griglia congiunta k=1 più
  `eval/calibrate_graph_context.py`. Agent: `retrieval-calibration-guard`.
- **Ollama**: unico modello `qwen3.5:9b`. `ollama_num_ctx: 16384` e `ollama_think: false` sono
  fix di bug silenziosi (prompt troncati, risposte vuote), non tuning: non toglierli.
  BGE-M3 gira su CPU di proposito, perché la GPU è riservata a Ollama (il reindex usa un worker
  GPU a vita breve).
- **Superficie di sicurezza**: ogni route HTTP o tool MCP nuovo o cambiato va riportato in
  `rag/SECURITY_SURFACE.md`. Agent: `security-surface-reviewer`.
- **Segreti e lock**: `rag/.env.local` (`VIBECRAFT_API_KEY`) non si committa e non si modifica
  tramite Claude. `uv.lock` cambia solo con `uv add` / `uv lock`. Un hook blocca entrambi.

## Convenzioni

- Commenti e documentazione in italiano. I commenti spiegano il *perché*, spesso con data e
  sigla della sessione o dell'audit (es. S11, A9).
- Commit in inglese con prefisso convenzionale: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`.
- `gh` è installato e autenticato.

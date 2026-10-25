# Review finale Astra — 28 settembre 2026

Codice revisionato: `810f1f7`, base `ea0cf91425a5d01b39ed821c714cd397a6e0d2b0`.

La root ha revisionato LLM, config/storage/lease, API reader, lifecycle streaming, dashboard, benchmark/provenienza e opt-in CI. Nessun finding aperto dopo la correzione dei tre rilievi: slot perso su errore prima degli header, deadline assente durante invio lento e health che ignorava la collection fisica mancante.

## Verifica indipendente root

Directory: `C:/Users/Silve/.codex/worktrees/horizontal-scaling/vibecraft/rag`.

```powershell
$env:QDRANT_URL = 'http://127.0.0.1:16333'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:VIBECRAFT_ROLE = 'standalone'
$env:VIBECRAFT_INDEX_MODE = 'legacy'
Remove-Item Env:VIBECRAFT_TEST_QDRANT_URL -ErrorAction SilentlyContinue
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -m pytest tests/test_ask_streaming.py tests/test_reader_mode.py tests/test_reader_process_leases.py tests/test_bench.py tests/test_bench_concurrency.py tests/test_dashboard_stream.py -q -o addopts=''
```

Esito riportato dalla root: `101 passed in 20.65s`, exit code 0. Servizio dedicato16333 fermo; nessuna integrazione sul Qdrant operativo. Ruff e altre regressioni sono registrati nel checkpoint e in `api-tests.txt`.

## Decisione e limiti

Software approvato entro il perimetro verificato. Non è approvato il completamento end-to-end e non sono dimostrati benefici prestazionali. Restano aperti baseline HTTP, matrice reale k=1,4,8, confronto uno/due reader, RAM reale e inferenze simultanee del motore. Il modello qwen35 disponibile serializza e l'avvio HTTP isolato era stato rifiutato dalla revisione automatica. Non ripetere suite o implementazione senza nuovo difetto o rimozione dei blocchi.

# Stato — scalabilità orizzontale

## Checkpoint 2026-09-28 — lavoro ripreso

- Workspace: `C:/Users/Silve/.codex/worktrees/horizontal-scaling/vibecraft`.
- Branch `codex/horizontal-scaling`; base `ea0cf91425a5d01b39ed821c714cd397a6e0d2b0`; primo commit documenti `b575487`.
- [x] Audit, specifica e piano approvati dalla root; esecuzione già autorizzata dall'utente.
- [x] P0 harness:49 test verdi, ruff/diff-check puliti; review PM conclusa. Baseline reale separata bloccata.
- [ ] P0 baseline HTTP reale: bloccata (vedi sotto).
- [ ] P1 pin collection/ammissione/streaming: implementato, review PM e verifica cancellazione in corso; codice non ancora committato.
- [ ] P2 reader/writer/immutabilità locale: storage in implementazione parallela; API reader segue P1.
- [ ] P3 matrice reale k=1,4,8 e review finale.

Quota alla ripresa99%, ultima PM90% residua, uso consentito. Stop precedente al5% rispettato. Verificare quota prima/dopo ogni fase/fanout: stop <=5% qualunque finestra o ordinaryUsageAllowed=false/spendControlReached; ripresa solo >=15% tutte e uso consentito. Mai reset/acquisti. Heartbeat root.

## Evidenze e blocchi

- P0 Terra: `pytest tests/test_bench.py tests/test_bench_concurrency.py -q`49 pass; ruff sui4file bench/test e diff-check pass. Review PM corretta: status200 invalido, protocollo post-terminale, timeout finito, memoria PID+figli, metadati client/server separati. Sonde cancellazione reale/GPUpeak non eseguite e dichiarate nel report.
- Baseline unità PM prima P1:132 pass sui sei file `test_ask_unified_llm`, `test_ask_cache`, `test_ask_abstention`, `test_ask_limits`, `test_ask_observability`, `test_llm`. Fake, non prova hardware.
- Root ha preparato corpus reale innocuo prestiti biblioteca (1doc,5chunk) da sorgente ea0cf91, Qdrant16333 e Ollama21434 isolati. Lab conservato in `rag/database/qdrant_data/horizontal-lab` (ignorato Git). Servizi di test poi arrestati.
- Incidente test: baseline PM e primo run storage P2 hanno eseguito cinque test autodetect su Qdrant operativo6333, scrivendo collection/alias `_test_blue_green_*`. Log confermati in due finestre UTC07:44 e08:06. Audit delimitato e limiti dell'evidenza: `horizontal-bench/preflight-20260928/QDRANT_TEST_AUDIT.md`. Nessun cleanup operativo. Fixture corretta in P2; verifiche successive impongono endpoint dedicato16333 fermo e modelli offline.
- Avvio baseline HTTP18000 rifiutato automatic approval con `blocked by policy`, senza motivazione specifica. Nessun aggiramento; matrice end-to-end NON eseguita.
- Ollama0.34.4/qwen3.5:9b forza runner `-np 1` per architettura qwen35: due HTTP200 sovrapposti ma inferenze sequenziali. Gate vera inferenza parallela NON soddisfatto con backend/modello presenti. Nessun modello/engine installato.
- La sonda inizialmente pensata CPU era VulkanGPU per env ereditato `OLLAMA_VULKAN=true`: non attribuire numeri a CPU. Prove persistenti in `rag/adr/horizontal-bench/preflight-20260928/{README.md,ollama-overlap.json,ollama-evidence.log}`.

## Ripresa operativa

Leggere spec+piano nello stesso percorso; conservare modifiche parziali. Sol applicazione, Terra benchmark, PM review; massimo2 sottoagenti attivi. Root review finale trasversale. Solo worktree, niente DB operativo, installazioni GPU/modelli, push main o deploy.

Eseguire test da `worktree/rag` con `C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -m pytest ...`; comandi per fase nel piano. P0 ingresso `scripts/bench.py --concurrency-bench`, solo POST /ask, senza reindex del benchmark storico. P1/P2 possono proseguire indipendentemente dal blocco hardware/avvio, ma la consegna deve dichiarare P3 incompleto.

## Estensione harness P3

Sonde cancel separate e GPUpeak opzionale implementate:55 test bench pass,ruff/diff-check pass; review PM escluso cleanupGPU dal throughput e impedito falso cancel dopoEOF. Nessuna prova live. P0 commit `c9ab3df`. Baseline P2 prima edit:158 test pass. P1 Sol ancora in corso.

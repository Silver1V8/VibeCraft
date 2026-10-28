# Stato — scalabilità orizzontale

## P3 misura PcLavoro — 28 ottobre 2026

Eseguita matrice HTTP stream/cache-off k=1/4/8 e confronto uno-vs-due reader con
`qwen3.5:9b` su lab dedicato (Qdrant `127.0.0.1:16333`, reader `:18001`/`:18002`,
proxy RR `:18010`). Ollama host condiviso `:11434` (0.40.5), non un secondo daemon
`:21434`. N=8 per cella (target ADR 30 non raggiunto: ~45–50 s/req). Esito: thrput
utile ~0,02 ok/s piatto; k>1 → 429 «coda inferenza piena»; due reader non
moltiplicano il throughput verso un solo Ollama qwen35; cancel stream OK. Evidenze:
`archive/adr/horizontal-bench/p3-pclavoro-20261028/`. Claim README aggiornato in
`rag/docs/streaming-repliche.md`. Griglia ADR residua (N=30, cache-on, JSON,
baseline ea0cf91 vs candidato) resta aperta — non inventare SLA oltre la tabella.

- [x] P3 matrice HTTP k=1/4/8 e uno-vs-due reader (campione N=8 stream/cache-off)
- [ ] P3 griglia ADR completa (N=30, cache-on, JSON, baseline vs candidato)

## Integrazione su main autorizzata — 28 settembre 2026

L'utente ha richiesto commit e push su main. Integrato main `7512b1d` nel ramo di lavoro senza conflitti (merge `e417965`), preservando i nuovi sviluppi della pipeline. Sul risultato integrato: **1794 passed, 5 skipped in 139.10s**, exit 0; stessi quattro moduli esterni esclusi della precedente suite offline. Ruff sui file Python modificati e `git diff --check` superati. Prove: `horizontal-bench/verification-20260928/merge-regression.txt`; ambiente/comando in `run-merge-regression.ps1` (eseguiti come comandi nella sessione, perché la policy PowerShell locale disabilita i file script).

L'autorizzazione alla pubblicazione non dichiara completata P3: restano da misurare HTTP/streaming e repliche con Qwen3.5:9b sui servizi dedicati. Nessun nuovo tentativo di avvio, installazione o modifica ai servizi operativi. Le modifiche locali estranee nel checkout principale restano fuori dal commit.

## Checkpoint 2026-09-28 — software verificato, gate reali aperti

- Workspace: `C:/Users/Silve/.codex/worktrees/horizontal-scaling/vibecraft`.
- Branch `codex/horizontal-scaling`; base `ea0cf91425a5d01b39ed821c714cd397a6e0d2b0`; primo commit documenti `b575487`.
- [x] Audit, specifica e piano approvati dalla root; esecuzione già autorizzata dall'utente.
- [x] P0 harness:49 test verdi, ruff/diff-check puliti; review PM conclusa. Baseline reale separata bloccata.
- [ ] P0 baseline HTTP reale: bloccata (vedi sotto).
- [x] P1 pin collection/ammissione/streaming: commit `215960a`, review PM e verifiche superate.
- [x] P2 reader/writer/immutabilità locale: storage `f8fc368`, API reader/lifecycle e prova OS due lettori `810f1f7`; test e review PM superati.
- [x] P3 matrice reale k=1,4,8 e confronto HTTP uno/due reader (N=8 stream/cache-off, 2026-10-28; vedi sezione in cima).
- [x] Review finale Astra root: codice `810f1f7`, nessun finding aperto; verifica indipendente101 pass.

Quota alla ripresa99%, finale78% residua, uso consentito e nessun limite di spesa raggiunto. Stop precedente al5% rispettato. Verificare quota prima/dopo ogni fase/fanout: stop <=5% qualunque finestra o ordinaryUsageAllowed=false/spendControlReached; ripresa solo >=15% tutte e uso consentito. Nessun reset consumato né acquisto. Heartbeat root.

## Evidenze e blocchi

- P0 Terra: `pytest tests/test_bench.py tests/test_bench_concurrency.py -q`49 pass; ruff sui4file bench/test e diff-check pass. Review PM corretta: status200 invalido, protocollo post-terminale, timeout finito, memoria PID+figli, metadati client/server separati. Sonde cancellazione reale/GPUpeak non eseguite e dichiarate nel report.
- Baseline unità PM prima P1:132 pass sui sei file `test_ask_unified_llm`, `test_ask_cache`, `test_ask_abstention`, `test_ask_limits`, `test_ask_observability`, `test_llm`. Fake, non prova hardware.
- Root ha preparato corpus reale innocuo prestiti biblioteca (1doc,5chunk) da sorgente ea0cf91, Qdrant16333 e Ollama21434 isolati. Lab conservato in `rag/database/qdrant_data/horizontal-lab` (ignorato Git). Servizi di test poi arrestati.
- Incidente test: baseline PM e primo run storage P2 hanno eseguito cinque test autodetect su Qdrant operativo6333, scrivendo collection/alias `_test_blue_green_*`. Log confermati in due finestre UTC07:44 e08:06. Audit delimitato e limiti dell'evidenza: `horizontal-bench/preflight-20260928/QDRANT_TEST_AUDIT.md`. Nessun cleanup operativo. Fixture corretta in P2; verifiche successive impongono endpoint dedicato16333 fermo e modelli offline.
- Avvio baseline HTTP18000 rifiutato automatic approval con `blocked by policy`, senza motivazione specifica. Nessun aggiramento; matrice end-to-end NON eseguita.
- Ollama0.34.4/qwen3.5:9b forza runner `-np 1` per architettura qwen35: due HTTP200 sovrapposti ma inferenze sequenziali. Gate vera inferenza parallela NON soddisfatto con backend/modello presenti. Nessun modello/engine installato.
- La sonda inizialmente pensata CPU era VulkanGPU per env ereditato `OLLAMA_VULKAN=true`: non attribuire numeri a CPU. Prove persistenti in `archive/adr/horizontal-bench/preflight-20260928/{README.md,ollama-overlap.json,ollama-evidence.log}`.

## Ripresa operativa

Leggere spec+piano nello stesso percorso; conservare modifiche parziali. Sol applicazione, Terra benchmark, PM review; massimo2 sottoagenti attivi. Root review finale trasversale. Solo worktree, niente DB operativo, installazioni GPU/modelli, push main o deploy.

Eseguire test da `worktree/rag` con `C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -m pytest ...`; comandi per fase nel piano. P0 ingresso `scripts/bench.py --concurrency-bench`, solo POST /ask, senza reindex del benchmark storico. P1/P2 possono proseguire indipendentemente dal blocco hardware/avvio, ma la consegna deve dichiarare P3 incompleto.

## Estensione harness P3

Sonde cancel separate e GPUpeak opzionale implementate:55 test bench pass,ruff/diff-check pass; review PM escluso cleanupGPU dal throughput e impedito falso cancel dopoEOF. Nessuna prova live. P0 commit `c9ab3df`. Baseline P2 prima edit:158 test pass (include l'incidente descritto sopra).

## Verifiche P1/P2 storage

Tutti i run finali seguenti hanno usato `QDRANT_URL=http://127.0.0.1:16333` con servizio fermo e `HF_HUB_OFFLINE=1`; P1 anche `TRANSFORMERS_OFFLINE=1`. Nessun `VIBECRAFT_TEST_QDRANT_URL` per le suite locali. Comandi da `worktree/rag`, Python indicato sopra.

- P1: `pytest tests/test_ask_unified_llm.py tests/test_ask_streaming.py tests/test_ask_router.py tests/test_ask_prompt_cost.py tests/test_ask_observability.py tests/test_ask_limits.py tests/test_ask_cache.py tests/test_ask_authority_prompt.py tests/test_ask_abstention.py tests/test_dashboard_stream.py tests/test_llm.py -q`:178 pass. Poi aggiunta prova first-delta con ASGI diretto e provider sospeso; `pytest tests/test_ask_streaming.py -q`:21 pass. Non presentare il totale aggiornato179 come una suite intera rieseguita.
- P2 storage: `pytest -o addopts='' -q tests/test_storage_modes.py tests/test_artifacts.py tests/test_atomic_storage.py tests/test_versioning.py tests/test_qdrant_blue_green.py tests/test_writer_lock.py tests/test_colbert_store.py tests/test_incremental_indexing.py tests/test_lifespan.py tests/test_reindex.py`:282 pass,5 skip (reale Qdrant non autorizzato),31.43s.
- Ruff sui file Python cambiati in ciascuna fase e diff-check: pass. Workflow YAML validato: entrambi gli step Qdrant espongono endpoint test esplicito. Review PM: cancel CPU conserva capacità fino fine thread, upstream chiuso sotto backpressure, dense/sparse pinned anche con alias cambiato, full legacy non viene dichiarato immutabile, snapshot lease conserva manifest/collection.
- P2 API/lifecycle: `pytest tests/test_ask_streaming.py tests/test_reader_mode.py -q`:43 pass; regressioni `test_lifespan`, `test_health`, `test_mcp_http`, `test_atomic_storage`, `test_retrieve_reload`, `test_graph_ops`, `test_security_fixes`:264 pass. Comandi/output e ruff in `horizontal-bench/verification-20260928/api-tests.txt`.
- Due processi NPZ reali, writer/GC finti su directory temporanea: `pytest -o addopts='' -q tests/test_reader_process_leases.py`:1 pass in9.61s; ruff pass. Entrambi trattengono v1 durante v2/v3 e rollbackv2; uscita ordinata primo e crash controllato secondo provano rilascio OS e successiva pulizia. Nessun HTTP, modello o Qdrant reale in questa prova.
- Review finale root sul codice `810f1f7` approvata entro il perimetro software. Tre finding (slot su errore header, deadline invio lento, health collection fisica assente) corretti e coperti. Verifica indipendente101 pass in20.65s; comando/esito/limiti in `horizontal-bench/verification-20260928/REVIEW_FINALE.md`. Audit incidente `6f9ef93`; P3 harness `83940fc`.

## Prossimo passo / heartbeat

Il software P0/P1/P2 è implementato, verificato e approvato dalla review root entro i limiti sopra; non è una consegna end-to-end completa. I sottoagenti implementatori sono idle. Nessun push/deploy. Non resta lavoro software noto prima dello sblocco P3.

Decisione utente 2026-09-28: mantenere per ora Qwen3.5:9b. La scelta del modello non è più pendente; l'inferenza serializzata dell'abbinamento attuale resta un limite accettato per questa fase, non un risultato di parallelismo. Non installare modelli o backend alternativi.

Per P3 resta la rimozione del blocco di avvio HTTP e dei servizi dedicati. Non riprovare l'avvio rifiutato in altra forma. Quando sbloccato: baseline sorgente ea0cf91 e candidato con Qwen3.5:9b sugli stessi corpus/config, k=1,4,8,30 campioni/cohort, cache-off/hit separate, raw/TTFT/throughput/errori/cancel/memoria e uno vs due reader. Verificare richieste concorrenti e streaming; riportare separatamente il limite dell'inferenza serializzata.

Finché restano solo questi gate esterni, **non ripetere suite o implementazione a ogni heartbeat** senza nuovo codice o rimozione del blocco. L'automazione root resta attiva finché il completamento richiesto non è verificato; nessun dato prestazionale inventato dai fake o dalle due sonde Ollama.

## Nuova richiesta di test — 28 settembre 2026

- Su richiesta esplicita dell'utente di provare altra porta, la root ha ritentato server18001: revisione automatica `blocked by policy`. Anche il comando di preflight/riavvio del Qdrant dedicato è stato rifiutato prima dell'esecuzione. Nessun servizio riavviato, nessun tentativo alternativo; driver ASGI con dipendenze reali non creato/eseguito.
- Audit statico e unica suite offline estesa sul candidato `39b5a47`: **1779 pass,5 skip,138.83s,exit0**. Quattro file esclusi per listener/CLI/modelli/conversioni reali; cinque skip Qdrant esplicitamente disabilitato. Nessuna regressione e nessun cambio prodotto. Report, comando e output: `horizontal-bench/verification-20260928/OFFLINE_REGRESSION.md`, `run-offline-regression.ps1`, `offline-regression.txt`.
- Quota aggiornata75% residua, ordinary usage consentito, spend control non raggiunto; nessun reset/acquisto. Il progresso software è verificato; P3 live resta bloccato e non si deducono prestazioni dai test. Nuovo heartbeat senza cambi di codice o sblocco esterno deve restare quieto, senza ripetere suite o avvii rifiutati.

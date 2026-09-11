# Sessione 5 — MCP locale, 2026-09-11

Questo resoconto fotografa la chiusura delle prove locali, prima del rilascio.
Il manutentore ha successivamente autorizzato la pubblicazione subordinata al PASS;
la promozione richiede anche i job CI sul commit candidato.

**Verdetto aggiornato: PASS locale con il nuovo limite di 10 secondi.** Il manutentore
ha autorizzato esplicitamente l'aumento del limite del delta HTTP/MCP p95 da 100 ms
a **10.000 ms** dopo aver esaminato i risultati. Le misure già raccolte rientrano
nel nuovo limite; non sono state ripetute né modificate. Il precedente verdetto
NON_APPLICARE e i JSON originali restano conservati nelle evidenze locali.
Nessuna integrazione, commit, push, merge, pubblicazione o modifica della produzione.

## Partenza e conservazione

- Main locale e remoto verificati: `97555bd2251cb4a1e4a4551722e1c69c0c1479da`.
  La CI storica `34605349865` risulta completed/success sullo stesso SHA.
- Ramo `codex/sessione-5-mcp`, worktree
  `C:\Users\Silve\Desktop\vibecraft\.worktrees\sessione-5-mcp`;
  HEAD invariato, modifiche non committate e nulla nello staging Git.
- Nessun `AGENTS.md` trovato nelle directory superiori o applicabili.
  Letti EVOLUZIONE (intervento 2, vincoli e rollback), RESIDUI, SECURITY_SURFACE,
  configurazione, percorsi API/core e controlli CI pertinenti.
- Indice effettivo: `v20260910T121150`, **40 documenti, 248 chunk**,
  452 simboli, 931 nodi e 1303 archi. Nessuna promozione o ricostruzione.
- Inventario SHA-256 di **114 file operativi identico** prima/dopo: corpus,
  artefatti versionati, CURRENT, staging/journal, configurazione e i tre file
  locali segnalati (`adr/README.md`, `golden_attribution.yaml`, `history.jsonl`).
  Assenze nel corpus conservate. Nessuna approvazione o rigenerazione dei cataloghi.
- Test in copie private del worktree e sul clone del volume Qdrant. Il volume
  originale è stato montato **read-only** per copiarlo; il suo container è rimasto
  fermo. Corpus e golden locali copiati nel worktree sono esclusi dal diff mediante
  flag locali skip-worktree; dati runtime ignorati da Git. Non sono materiale da committare.
- `.git/info/exclude` contiene l'esclusione locale di `/.worktrees/`.
  I container preesistenti `qdrant` e `neo4j` sono rimasti attivi; i backend Windows
  e i due container avviati dalla sessione sono stati arrestati. Immagine di prova,
  volume copiato ed evidenze restano locali per revisione.

## Diff tecnico

| File | Motivazione |
|---|---|
| `mcp_server.py` | SDK 2.1.0, tre tool stdio; HTTP loopback, auth ambiente, timeout totale, tetto 2 MiB, errori sanitizzati, nessun import del core |
| `api/routes_retrieval.py` | Testo documentale opzionale con provenienza e taglio; versione e collection fisica dello snapshot; limiti codice espliciti |
| `api/deps.py` | Versione ricevuta dagli artefatti caricati, senza rileggere CURRENT; mtime mantenuto nel layout legacy |
| `api/routes_graph.py` | Snapshot catturato una volta, limite opzionale condiviso fra elenchi, totale e parzialità espliciti |
| `pyproject.toml`, `uv.lock` | Solo dichiarazione diretta `mcp==2.1.0`, già transitiva; nessuna versione cambiata |
| `tests/test_mcp_server.py`, `tests/test_mcp_http.py` | Protocollo reale, confini HTTP, errori, auth, limiti, snapshot concorrente, legacy |
| `tests/test_retrieve_reload.py` | Fixture della collection resa esplicita dopo il vincolo allo snapshot |
| `scripts/bench_mcp.py` | Benchmark riproducibile: warm-up separato, 30 coppie/tool, equivalenza completa, p50/p95 e delta |
| `README.md`, `SECURITY_SURFACE.md`, questo resoconto | Avvio, client, spegnimento, confine dati, superfici distinte e risultati |

Ranking, pesi, precedenze, soglie, golden e autenticazione del backend invariati.
HTTP retrieval continua a omettere il testo per default; il grafo senza `limit`
conserva la risposta storica. Nel layout versionato, collection da manifest,
versione e testo sono associati allo snapshot catturato prima dell'await.
Il layout incrementale che condivide una collection mantiene i limiti di isolamento
già documentati in EVOLUZIONE R.2: il pin non rende immutabili vettori riscritti in place.

## Verifiche eseguite

Criteri preregistrati in `output/sessione-5-mcp/criteria.md` **prima dei test**.
Gli output integrali sono nella stessa directory locale, fuori dal diff tecnico.

| Controllo / comando | Esito |
|---|---|
| Nuovi test HTTP prima del codice | 4 fallimenti attesi, conservati in `red-http.txt` |
| Nuovi test MCP prima del modulo | Import assente, conservato in `red-mcp.txt` |
| Test legacy prima della correzione | 3 load invece di 1, `red-legacy.txt` |
| `uv lock --offline`; `uv sync --frozen --offline` nel worktree | PASS; ambiente isolato, 188 record nel lock, tutti i pacchetti non-progetto identici |
| `python -B -m pytest -o addopts= -q -rs -p no:cacheprovider` con `VIBECRAFT_REQUIRE_QDRANT=1` e QDRANT_URL del clone | **1481 passed, 0 skipped, 15 warning**, 170,24 s (`suite-windows-final.txt`) |
| Baseline esatta, stessi tre moduli di test intake che emettono warning | **111 passed, gli stessi 15 warning**, 56,51 s: deprecazioni Docling, non introdotte qui |
| `ruff check --no-cache .` | PASS, `lint-final.txt` |
| `node tests/intake_excel_preview.cjs` | PASS |
| `python -B scripts/docling_models.py` offline sui pesi copiati | Tutti gli hash verificati; operazione confinata alla copia |
| `python -B -m eval.run --url <backend-isolato> --no-save`, prima/dopo | 58 casi; recall@2 **0,828 → 0,828**, PASS con soglia 0,75 |
| `python -B -m eval.run_multihop --url <backend-isolato> --no-save`, prima/dopo | 14 casi; recall A **0,854 → 0,854**, B exact **6/6 → 6/6**, PASS |
| Quattro moduli di test MCP/API nel container CPU | **39 passed**, zero skip/warning, stdio reale incluso |
| `docker build --target cpu -t vibecraft:session5-candidate <contesto-pulito>` | PASS, Dockerfile mantenuto, senza corpus privato né credenziali |
| `import server,index,mcp_server` nell'immagine costruita, rete disabilitata | PASS, MCP 2.1.0 |
| Compose: tre profili e rifiuto senza chiave | PASS, nessun servizio avviato da Compose |
| `git diff --check` | PASS |

Il primo tentativo container usava un virtualenv di test senza le dipendenze
applicative: errore di raccolta conservato. Il secondo aggiunge il site-packages
dell'immagine al PYTHONPATH e passa. La review indipendente ha trovato il reload
continuo legacy; riprodotto, corretto e riverificato. Nessun rilievo residuo nella review.

Prove di sicurezza: esclusivamente tre tool e nessuna risorsa/prompt; stesso JSON
HTTP (identificatori, ordine, punteggi e testo inclusi), input invalidi respinti,
chiave inoltrata e non restituita/loggata, 401/403, backend indisponibile, timeout,
JSON invalido e risposta troppo grande gestiti. Redirect rifiutati, proxy disabilitati,
URL ambigui/non-loopback rifiutati, `localhost` normalizzato senza DNS. Query che
sembrano Cypher non eseguono codice né mutano il grafo.

Un harness locale con audit delle connessioni blocca ogni destinazione tranne
Qdrant di test. I log validi riportano soltanto `127.0.0.1:16333` (Windows) e
gateway Docker `192.168.65.254:16333` (Linux), **nessuna connessione Ollama o provider**.
Il primo harness Windows bloccava anche la pipe TCP interna di asyncio: errore
conservato e corretto nel solo harness. Nel container indice/sorgenti sono read-only;
il writer del boot viene reso indisponibile dall'harness, usando il percorso già
esistente che salta riconciliazione/GC. Le route e il retrieval restano reali.

## Prestazioni

`python -B -m scripts.bench_mcp --pairs 30`: **30 coppie per ciascuno dei tre tool**,
3 warm-up per tool esclusi, ordine HTTP/MCP alternato, stesso payload e indice.
Uguaglianza completa delle risposte verificata a ogni coppia; hash delle risposte
stabile per tutte le 30 coppie di ciascun tool. Ogni tempo e delta è conservato nei JSON.
Percentili nearest-rank; millisecondi.

| Ambiente / tool | HTTP p50 | HTTP p95 | MCP p50 | MCP p95 | Delta p50 | Delta p95 |
|---|---:|---:|---:|---:|---:|---:|
| Windows / retrieval | 496,14 | 748,89 | 492,86 | 763,13 | -0,78 | **69,76** |
| Windows / codice | 224,38 | 343,08 | 219,43 | 312,86 | -1,05 | **66,35** |
| Windows / grafo | 2,45 | 2,83 | 4,41 | 5,09 | 1,94 | **2,45** |
| Linux CPU / retrieval | 428,92 | 632,24 | 434,50 | 553,38 | 16,94 | **146,60** |
| Linux CPU / codice | 355,16 | 512,31 | 384,57 | 566,37 | 22,20 | **153,61** |
| Linux CPU / grafo | 8,95 | 12,66 | 11,93 | 16,32 | 2,70 | **5,60** |

Windows 11, Python 3.14.6, torch 2.13.0+cu126 (embedder CPU).
Linux x86_64 Docker/WSL2, Python 3.14.7, torch 2.13.0+cpu; SDK MCP 2.1.0,
httpx 0.28.1 in entrambi. Container reale basato sull'immagine CPU già presente
con sorgenti candidati montati; l'immagine candidata ricostruita è verificata
separatamente con lo smoke import. Nessuna misura GPU o macOS.

Prima misura Windows, con due backend/modelli residenti: retrieval delta p95
**481,52 ms**, FAIL (`benchmark-windows.json`). Conservata. Dopo aver arrestato il
backend baseline, la ripetizione passa (`benchmark-windows-single-backend.json`).
Questo confronto non dimostra da solo la causa della variabilità.

Il delta è **MCP_i − HTTP_i**, non MCP totale né differenza fra i due p95.
Le chiamate eseguono il retrieval due volte: il delta contiene anche la variabilità
del backend; valori negativi non significano overhead negativo del protocollo.
Non è stata misurata separatamente la durata interna del backend. Il criterio
abbinato originale di 100 ms fallisce su Linux. Il successivo limite di **10.000 ms**,
autorizzato dal manutentore, è soddisfatto da tutte le misure Windows e Linux,
compresa la prima misura Windows. Metrica, campioni e risultati negativi originali
sono conservati; cambia soltanto il criterio di accettazione.

## Avvio, spegnimento e punti aperti

Istruzioni complete e configurazione client: [README](../README.md#mcp-locale-di-sola-lettura).
Nel worktree, da `rag`: `uv run --frozen python -B mcp_server.py`, backend locale
già pronto. Variabili: `VIBECRAFT_MCP_BACKEND_URL`, `VIBECRAFT_API_KEY` ereditata
se richiesta dal backend, `VIBECRAFT_MCP_TIMEOUT_SECONDS` opzionale. Nessun segreto
negli esempi. Spegnere disabilitando il server nel client e chiudendo il processo
stdio, oppure Ctrl+C. Nessun flag aggiuntivo, rebuild o arresto del backend necessario.

**Approfondimento facoltativo:** distinguere con una misura preregistrata il costo
del trasporto dalla variabilità dell'embedding. Non è più un blocco rispetto al
limite di 10 secondi autorizzato. Nessuna cache o modifica del ranking introdotta.
Nessun giudice/generatore remoto, nessun `/ask`, N1 invariata. I cataloghi attendono
ancora revisione umana separata.

Non eseguiti: nuovi workflow remoti, job macOS/GPU, `doctor`/health che contattano
Ollama, notturni con remediation/scritture e prove di generazione. Non sono
presentati come copertura; il verdetto riguarda le verifiche locali documentate.

Fonti SDK controllate insieme al sorgente installato:
[Python SDK](https://github.com/modelcontextprotocol/python-sdk),
[specifica stdio](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).

## Riepilogo per coordinamento

SESSIONE 5 — 2026-09-11 — PASS locale con limite aggiornato a 10 secondi,
autorizzato dal manutentore. Candidato non committato su
`codex/sessione-5-mcp`, base/HEAD `97555bd`. Tre tool MCP stdio funzionanti,
equivalenza HTTP e snapshot verificati; 1481 test Windows passati, zero skip,
15 warning già riprodotti sulla baseline; 39 test container passati, build CPU e
lint verdi. Retrieval/multihop invariati. Delta p95 Windows 69,76/66,35/2,45 ms;
Linux 146,60/153,61/5,60 ms: tutti entro il nuovo limite di 10.000 ms.
114 hash operativi invariati, nessuna chiamata Ollama/provider, servizi di prova
arrestati. Nessun commit/push/merge/produzione. Il precedente fallimento rispetto
ai 100 ms resta documentato; misure originali immutate.

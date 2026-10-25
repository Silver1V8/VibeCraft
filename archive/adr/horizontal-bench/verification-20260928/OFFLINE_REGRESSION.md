# Verifica estesa dopo richiesta di riprovare — 28 settembre 2026

Sorgente candidato: `39b5a47`, branch `codex/horizontal-scaling`. Nessun codice prodotto modificato durante questa verifica.

## Esito

**1779 passed, 5 skipped in 138.83s (0:02:18), exit code 0.** Log integrale: `offline-regression.txt`. Comando e ambiente riproducibili: `run-offline-regression.ps1`, eseguito dalla directory `rag` del worktree isolato. Quota dopo la verifica:75% residua, uso consentito, spend control non raggiunto; nessun reset o acquisto.

La suite comprende compatibilità API in processo, streaming, ammissione, cancellazione, storage, lease fra processi, indicizzazione con dipendenze finte e parser dashboard. I processi ausiliari mantenuti nei test usano file temporanei, Git su repository temporanei o Node per parser: non avviano listener HTTP o modelli. L'audit statico ha controllato fixture, punti di connessione, subprocess e path persistenti prima dell'esecuzione.

Le cinque prove Qdrant reali sono saltate dalla fixture prima di creare il client, perché `VIBECRAFT_TEST_QDRANT_URL` è assente. Quattro file sono esclusi esplicitamente dalla raccolta (non conteggiati nei cinque skip):

| File escluso | Motivo |
| --- | --- |
| `test_agent_settings_isolation.py` | Avvio reale SDK/CLI Claude e hook. |
| `test_mcp_server.py` | Una prova avvia `ThreadingHTTPServer` su una porta locale. |
| `test_intake_docling.py` | Include OCR/Docling con modelli reali. |
| `test_intake_libreoffice.py` | Include conversioni con LibreOffice reale. |

L'ambiente impone Qdrant16333 e Ollama21434 dedicati e fermi, HF/Transformers offline, database nuovo nel laboratorio ignorato del solo worktree, ruolo standalone/indice legacy. Opt-in delle integrazioni reali disabilitati, credenziali provider rimosse dal processo di test. Nessun avvio di servizio o download eseguito per questa suite.

## Tentativi live e confine della prova

Dopo la richiesta utente «prova un'altra porta o comunque cerca di testarlo», la root ha riprovato l'avvio del server isolato sulla porta18001. La revisione automatica ha rifiutato l'azione con `blocked by policy`, senza motivazione più specifica. Ha poi rifiutato prima dell'esecuzione anche il comando che comprendeva il preflight in lettura e `docker start vibecraft-horizontal-test`. Nessuna dipendenza live è stata riavviata. Non sono state tentate altre forme di avvio.

L'ipotesi di una prova ASGI in processo con retrieval e LLM reali è stata quindi fermata prima di creare/eseguire il driver. Questa suite ampia è una prova di regressione del software: **non è un benchmark reale**, non misura TTFT o throughput del modello, né verifica la rete HTTP, il bilanciatore o la matrice uno/due reader.

Restano invariati i gate P3: avvio dei servizi dedicati e frontdoor HTTP, matrice k=1/4/8 su corpus/config comparabili e decisione sul backend/modello. La precedente evidenza reale mostra che Ollama/qwen35 serializza l'inferenza. Nessun nuovo modello è stato scaricato e nessun beneficio prestazionale viene dedotto dai test finti.

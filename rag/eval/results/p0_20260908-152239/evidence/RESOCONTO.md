

## Resoconto P0 e R.0 — 2026-09-08

**Verdetto: PASS.** Esecuzione limitata a P0/R.0 su `codex/evoluzione-p0`,
HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`. Nessun branch, commit, push o PR
creato. Le misure iniziali sopra sono conservate byte per byte come prefisso.
`AGENTS.md` non trovato nella root, nei percorsi genitori controllati o nella
ricerca ricorsiva del repository (anche fuori sandbox).

### Stato iniziale e conservazione

Preesistenti: modifiche a `rag/adr/README.md` e tre righe in
`rag/eval/results/history.jsonl`; non tracciati `.agents/`,
`.claude/settings.local.json`, `rag/adr/EVOLUZIONE.md`, `skills-lock.json`, `tmp/`.
Preservati. Lo storico riceve soltanto nuove righe dagli strumenti esistenti;
il prefisso originario è verificato byte per byte. Nessun ranking, parser,
dipendenza o parametro calibrato modificato. Hash finali in `verification.json`.

Backup esterno: `C:\Users\Silve\Desktop\vibecraft-p0-backup-20260908-152239`.
Corpus completo: **60 file**, inclusi SVG/HTML e tutte le fonti non tracciate;
inventario con dimensioni e SHA-256 in `docs-manifest.json`, confronto integrale
fonte/copia e ricostruzione in `restore-rehearsal/docs` riusciti.
La copia `restore-rehearsal/docs-index-start` conserva i file non indicizzabili
e riproduce le **40 fonti** del manifest iniziale per SHA-256; esclude solo i due
PDF aggiunti, che rimangono nella copia completa. Questo distingue il ritorno
all'indice vecchio dal ripristino del corpus completo a 42 fonti.

Cinque versioni iniziali verificate: collection presenti, conteggi esatti,
precheck rollback, nessuna condivisione con lineage successive, sidecar NPZ
leggibili e copie identiche per hash. Retention **15** via
`VIBECRAFT_INDEX_KEEP` nei processi di rebuild/server/notturno; nessuna versione
iniziale eliminata. È una protezione della sessione, non un pin permanente:
esportare di nuovo la variabile prima dei futuri batch e dimensionarla al loro
numero. Snapshot Qdrant esterni della versione iniziale e della nuova baseline,
entrambi verificati contro il checksum SHA-256 fornito dal server; sidecar di
entrambe conservati fuori repository. Non è stato effettuato uno swap di prova
in produzione né un restore Qdrant: sono verificati i prerequisiti, la copia
del corpus e la leggibilità degli artefatti.

### Indice e risultati

- Prima: `v20260907T151549`, 40 fonti / 248 chunk, stale per i due PDF.
- Dopo: `v20260908T132451`, collection `vibecraft_events__v20260908T132451`, **42 fonti / 250 chunk**,
  **935 nodi / 1305 archi**, entrambi i PDF nel manifest e nei chunk.
- Full rebuild con parser pypdf corrente e gate bloccante, exit 0, promosso;
  durata **395.66 s**. Durante l'avvio il 9b
  Ollama era residente e contendeva VRAM; scaricato alle 15:30:35 locali senza
  cambiare configurazione. La durata include questa contesa e non rappresenta
  una misura isolata del costo di embedding.
- Solo `summary.superseded_by` aggiornato a `v20260908T132451` (e commento della
  stessa riga). Archivio, risposte, altre etichette e `index_version`
  `v20260907T094225` conservati; nessuna nuova misura di attribuzione implicita.
- Integrità iniziale post-build e finale: exit 0, non stale, alias allineato.
- Suite: **1342 passed, zero failure, zero skip**, 97.48 s, Qdrant obbligatorio.
- Lint: `All checks passed!`.
- Retrieval, 58 casi: recall@1 **0.706897**, @2 **0.827586**,
  @5 **0.948276**, @10 **1.000000** (saturo),
  source_in_top3 **0.896552**, MRR **0.811371**.
  Gate @2 >=0.75 rispettato. Multihop: **0.854**, **9/14 A**, **6/6 B exact**,
  soglia 0.85 e attese strutturali rispettate. Valori completi nei JSON.
- Benchmark, stesse funzioni e dieci query del piano: retrieve p50/p95
  **507.1/530.25 ms**;
  ask totale p50/p95 **18726.09/34439.44 ms**;
  generazione p50/p95 **17919.97/33697.70 ms**;
  semantic-map **308.72 ms**, 250 punti, non troncata.
  Embedder server CPU caldo, Ollama ricaricato a 16384 prima delle query.
  Nessun benchmark incrementale: stesso protocollo iniziale, nessun incrementale
  autorizzato. Il full rebuild è misurato dal comando P0, non ripetuto dal bench.
- Notturno eseguito dopo integrità pulita, webhook disabilitato,
  `UV_NO_SYNC=1`, `PYTHONDONTWRITEBYTECODE=1`: esiti e contratti nei log.
  Health finale: `ok`; consultare `health-after.json` per gli alert.

Non si attribuisce a Docling alcun effetto: non è stato installato o usato.
Il golden esistente non contiene casi specifici per questi PDF. Il p95 su dieci
campioni resta vicino al massimo e non descrive la coda sotto carico.

### Comandi e artefatti riproducibili

Baseline identificabile: `C:\Users\Silve\Desktop\vibecraft\rag\eval\results\p0_20260908-152239`.
I report eval/multihop datati sono anche copiati qui; `commands.json` registra
argv, exit code e durata, `runtime.json` registra Python e pacchetti,
`preflight.json` inventari e precheck, `index.json` manifest e chunk PDF,
`benchmark.json` i campioni, `verification.json` gli invarianti finali.
Helper della sessione in `tmp/p0_prepare.py`, `tmp/p0_measure.py`,
`tmp/p0_finalize.py`; non sono codice applicativo. Non rilanciarli ciecamente:
usano destinazioni uniche e richiedono lo stato della sessione.

Comandi da `rag/`, ambiente già installato:

```text
uv run --no-sync python -B index.py
uv run --no-sync python -B index.py --check-integrity
uv run --no-sync python -B -m pytest -o addopts= -q -p no:cacheprovider
uv run --no-sync ruff check --no-cache .
uv run --no-sync python -B -m eval.run
uv run --no-sync python -B -m eval.run_multihop
pwsh -NoProfile -File scripts/nightly_consistency.ps1
```

Suite con `PYTHONUTF8=1`, `HF_HUB_OFFLINE=1`, `VIBECRAFT_REQUIRE_QDRANT=1`.
Gli helper invocano direttamente lo stesso interprete selezionato da
`uv run --no-sync`; benchmark via `scripts.bench.bench_retrieve`, `bench_ask`,
`bench_semantic_map`. `scripts/ci.sh` non eseguito: sincronizzerebbe dipendenze;
lint e suite equivalenti eseguiti senza sync. Nessuna CI remota/container CPU/macOS.

### Procedura di ritorno

1. Fermare server, intake e altri writer; verificare percorsi assoluti sotto
   `C:\Users\Silve\Desktop\vibecraft` e il backup sopra. Conservare il corpus
   candidato in una nuova directory esterna, senza cancellare modifiche altrui.
2. Per tornare alla baseline coerente P0, sostituire l'intera directory `docs/`
   con `backup/docs`, confrontare inventario/hash e usare `v20260908T132451`.
   Per tornare alla versione iniziale usare invece la copia verificata
   `backup/restore-rehearsal/docs-index-start` e `v20260907T151549`.
   Non copiare sopra lasciando file aggiuntivi. Il backup completo conserva i PDF.
3. Esportare `VIBECRAFT_INDEX_KEEP=15` (o superiore per ulteriori candidate).
   Verificare sidecar, disponibilità Qdrant, nome collection, conteggi e precheck.
   Se una collection è persa, ripristinare il relativo snapshot Qdrant verificato
   con la stessa versione server e i sidecar corrispondenti prima del rollback;
   in alternativa full rebuild. Non accettare il fallback di solo rollback locale.
4. Da `rag/`: `uv run --no-sync python -B index.py --rollback VERSIONE_ESPLICITA`.
   Riallineare la sola dichiarazione `summary.superseded_by` alla versione attiva,
   mantenendo archivio e index_version. Non ripristinare l'intero working tree.
5. Verificare CURRENT, alias, integrità; riavviare il server e verificare snapshot,
   retrieval e multihop. Nessun ritorno è dichiarato concluso solo perché la CLI
   termina. I comandi di rollback qui sono documentati, non eseguiti.

Fase chiusa qui: nessun intervento 1–7 avviato.

Chiusura operativa: server di prova arrestato; container vibecraft-qdrant-1 riportato allo stato iniziale spento, altro Qdrant non toccato; Ollama resta acceso con il 9b ricaricato. Prima di usare la baseline o eseguire il ritorno avviare il container VibeCraft. Ramo/HEAD finali invariati; git diff --check exit 0. Nessun AGENTS.md disponibile.

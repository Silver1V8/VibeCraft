# Re-review fase 1d — fix 2

**Conformità: APPROVATO. Qualità: APPROVATO** nel perimetro del driver sperimentale e dei fix richiesti. Review statica del diff fix2 e del report aggiornato; non è stato avviato il run reale.

- **Delta byte e newline: chiuso.** `rag/eval/results/sidecar_20260915/evidence/process_workload.py:280-291` calcola il digest sui byte originali, codifica il testo modificato e lo scrive con `write_bytes`. Controlla la lunghezza dei byte prima e dopo la scrittura, quindi un file CRLF non subisce la traduzione `CRCRLF` di `write_text`. Il ripristino byte per byte e il fingerprint finale del fix1 restano presenti.
- **Relazione PID del child: chiusa.** `process_workload.py:200-203,367-372` registra `pid` e `ppid` nel percorso `--bootstrap --self-check` e richiede che il PID effettivo coincida con `Popen.pid` oppure ne sia figlio diretto. Il report mostra `bootstrap_ppid: 33088` uguale a `popen_pid: 33088`, coerente con il launcher Windows.
- **Altri finding fix1: chiusi e invariati.** Il job è registrato prima degli assert, il checkout è ancorato al run dello script, e l'origine monotona è serializzata.

Il report distingue correttamente il self-check sicuro dalla prova reale ancora **PREPARATO NON ESEGUITO**. Nessuna nuova regressione rilevata nel diff mirato.

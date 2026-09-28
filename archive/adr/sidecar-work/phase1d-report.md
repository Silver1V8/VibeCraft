# Fase 1d — driver pronto, non eseguito

Stato driver: **APPROVATO**. Il driver è `rag/eval/results/sidecar_20260915/evidence/process_workload.py`.

Run reale `calibration-20260921`: **fallita, exit 1**, per un bug del core nella gestione dell’alias Qdrant. Il driver ha registrato l’esito; la correzione del core è gestita separatamente. Questa failure non è un risultato prestazionale.

Il PM deve preparare `<run>/sandbox/experiment`, con `rag/`, `docs/`, `code/` e `rag/database/` tutti locali al checkout, la collection `sidecar_0628_benchmark`, Qdrant dedicato su `http://127.0.0.1:16333`, corpus di 3 Markdown e 1 Python, e modello `BAAI/bge-m3` già in cache.

Esecuzione prevista, una sola volta: corpus N=3 documenti Markdown + 1 Python; k=0 (no-op) e k=1 (delta). Le tre query HTTP chiedono fino a 3 risultati solo per verificare che il retrieval restituisca risultati.

```powershell
$env:PYTHONDONTWRITEBYTECODE=1
$env:CUDA_VISIBLE_DEVICES='-1'
$env:HF_HUB_OFFLINE=1
$env:OMP_NUM_THREADS=4
$env:MKL_NUM_THREADS=4
C:\Users\Silve\Desktop\vibecraft\rag\.venv\Scripts\python.exe -B rag\eval\results\sidecar_20260915\evidence\process_workload.py --checkout <run>\sandbox\experiment --output-dir <run>\phase1d-output
```

Esiti attesi da verificare nel JSON: bootstrap riuscito; tre `GET /api/retrieve` con risultati; no-op completato con `result.noop=true`, reload completato e token pubblicato; delta su `docs/prenotazioni.md` con solo `prenotazioni.md` modificato, un documento reindicizzato, token/chunk elaborati e token pubblicato uguale alla versione. Il testo sorgente è ripristinato in `finally`; l’indice resta intenzionalmente al delta.

## Contratti osservati

Il brief cita `server.app`, ma il composition root attuale è `rag/server.py` e l’oggetto FastAPI è `server.app`. Il driver importa quindi `server`, dopo avere aggiunto **solo** `<checkout>/rag` a `sys.path` prima degli import applicativi. Questa è la correzione minima proposta al PM.

Il file di proprietà `process_workload.py` non era presente nel worktree al momento della preparazione; è stato creato nel percorso dichiarato dal brief.

## Verifiche eseguite

- Sintassi: verificata con il runtime read-only indicato, senza avviare il driver:

```powershell
C:\Users\Silve\Desktop\vibecraft\rag\.venv\Scripts\python.exe -B -m py_compile rag\eval\results\sidecar_20260915\evidence\process_workload.py
```

- Guard negativa sicura: verificata su un checkout inesistente; il driver ha fallito prima di creare output, avviare subprocess o importare l’app.

- Self-check positivo eseguito, senza importare core/server né caricare modello o Qdrant:

```powershell
C:\Users\Silve\Desktop\vibecraft\rag\.venv\Scripts\python.exe -B rag\eval\results\sidecar_20260915\evidence\process_workload.py --self-check --checkout C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_20260915\sandbox\experiment --output-dir C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_20260915\sandbox\phase1d-selfcheck-fix2
```

Output:

```json
{"validated_checkout":"C:\\Users\\Silve\\.codex\\worktrees\\0628\\vibecraft\\rag\\eval\\results\\sidecar_20260915\\sandbox\\experiment","popen_pid":33088,"bootstrap_pid":6752,"bootstrap_ppid":33088}
```

Il self-check percorre `--bootstrap --self-check`, accetta la output directory già creata dal parent e verifica il metadata scritto dal child. `popen_pid` è il PID restituito da `Popen`; `bootstrap_pid` è quello scritto dal processo bootstrap. Sul launcher Windows il PID bootstrap può differire, ma `bootstrap_ppid` deve essere il `popen_pid` (come nel risultato sopra).

## Fix review 1

- Correzione anchor: il tentativo precedente ha usato erroneamente il root del worktree (`...\\vibecraft\\sandbox\\experiment`), quindi non valida il guard attuale. Il run effettivo è `Path(__file__).resolve().parent.parent`; il checkout è ora ancorato a `rag/eval/results/sidecar_20260915/sandbox/experiment`, non derivato dall’argomento. Il self-check sopra è quello valido.
- Il delta conserva e ripristina i byte originali, poi confronta il fingerprint finale con quello iniziale e fallisce se differiscono.
- Il job completo viene salvato nel JSON prima di ogni assert di validazione.
- L’origine monotona è già serializzata come `_started_monotonic`; gli eventi mantengono sequenza e secondi relativi.
- Il delta conserva i newline CRLF: scrive `changed.encode("utf-8")` con `write_bytes` e verifica la lunghezza byte prima e dopo. Fixture temporanea fuori dal corpus: `CRLF roundtrip passed`.

## Self-review

Il driver non avvia container e non esegue full rebuild, `/ask`, Ollama o benchmark di capacità. Registra UTC, sequenza e secondi monotoni relativi al campione, PID, parametri, fingerprint iniziale/finale, job completi e anche gli errori. Riceve SIGINT/SIGTERM/SIGBREAK come richiesta cooperativa anche nel bootstrap; registra checkpoint e continua ad attendere i job del manager fino alla terminazione, poi chiude il server e solo dopo ripristina il sorgente. Non esiste un percorso di uscita che tronchi un writer vivo.

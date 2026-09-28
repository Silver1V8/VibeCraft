# Fase 1c — report

Implementato `scripts/bench_process.py`: avvia solo il comando esplicito (argv, senza shell), scrive campioni JSONL progressivi e un report JSON con exit code, runtime, parametri, versioni e percorsi stdout/stderr. Ogni PID del workload e dei figli è una riga separata: RSS non è sommato. Campi non disponibili sono `null` con motivo; memoria GPU resta `null` (`not measured`).

Schema dei campioni: `utc`, `monotonic_seconds`, `processes` (PID/PPID, RSS, private Windows, USS, I/O e CPU), `system` (RAM, swap, cgroup) e `device`. `--qdrant-container` trova il processo con `/proc/*/comm == qdrant` e legge status, smaps_rollup e cgroup ogni 1 s; RSS, private (Private_Clean+Private_Dirty) e cgroup usage/limit/cache restano distinti. Il preflight del container dedicato `sidecar-0628-qdrant` ha trovato PID 1 = `bash`, perciò il sampler non lo assume. Non avvia né modifica container.

Lettura preflight eseguita solo sul container dedicato: `qdrant` trovato al PID 6; il parser ha restituito RSS, Private_Clean+Private_Dirty e cgroup con `limit_bytes=1073741824` (1 GiB). Non è un benchmark né una misura del workload applicativo.

Verifica eseguita: `PYTHONDONTWRITEBYTECODE=1 C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -B -m pytest tests/test_bench_process.py --basetemp eval/results/sidecar_20260915/sandbox/pytest1c/` → 3 passed; `ruff check scripts/bench_process.py tests/test_bench_process.py` → passed. I test usano un subprocess Python breve e testo `/proc` noto; non misurano modelli, GPU o capacità. Nota operativa: una prima esecuzione ha passato per errore `sandbox/` come basetemp; non viene effettuato alcun restore mentre il container può scrivere.

Limite aperto: GPU NVIDIA non misurata. Fase 1 resta aperta; il PM eseguirà workload reali per boot/query/delta/reload.

## Fix round 1

Corretto shutdown: nessun `kill()` o `terminate()` automatico. Un errore salva il report parziale e attende root e figli già osservati; Ctrl-C invia solo un segnale graceful al gruppo quando supportato, altrimenti registra il limite e attende la fine naturale. Il driver dei workload resta responsabile di shutdown e figli in `finally`.

Corretto Qdrant: una sola `docker exec ... sh -c` read-only raccoglie PID trovato da `/proc/*/comm`, status, smaps_rollup e cgroup. La lettura gira in thread daemon e non blocca il tick app; deadline a 1 s e durata/fine effettive sono nei dati Qdrant.

Corretto startup: comando inesistente/errore psutil ora producono sempre JSON finale e JSONL vuoto o parziale con `sampler_error`. Aggiunti test focused per figlio scoperto e startup fallito. Verifica fix: `pytest tests/test_bench_process.py --basetemp eval/results/sidecar_20260915/sandbox/pytest1c-fix1/` (da eseguire con runtime indicato nel brief); nessun benchmark o container avviato.

## Fix round 2

I figli osservati ora sono identificati da PID più `create_time`; PID riusati sono ignorati e zombie Linux sono conclusi. Dopo un errore post-launch viene scritto atomicamente subito un report con `completion=waiting_for_natural_exit`, poi viene aggiornato a `completed` al termine naturale.

La lettura Qdrant in volo riceve `join(timeout=10)` prima del report finale e scrive sempre un evento `qdrant_final` nel JSONL: risultato completo oppure limite esplicito di lettura non conclusa entro 10 s. Non blocca il campionamento app mentre il workload gira.

Verifica eseguita: `PYTHONDONTWRITEBYTECODE=1 C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -B -m pytest tests/test_bench_process.py --basetemp eval/results/sidecar_20260915/sandbox/pytest1c-fix2/` → 8 passed in 3.67s; `ruff check scripts/bench_process.py tests/test_bench_process.py` → passed. Nessun benchmark, GPU o container avviato.

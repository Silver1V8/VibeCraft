# Run sidecar 2026-09-15 — metodo e isolamento

Stato: preparazione, nessun risultato di capacità ancora disponibile.

## Ripresa e calibrazione del 21 settembre

Checkout sperimentale `sandbox/experiment`: estratto con `git archive e8d8940 rag`; archivio SHA256 `3ef45f04ab4670872dd3302d97788d8254d427a8dd659de86aadb26b4d538058`. Nessuna `.env.local` o database operativo copiato. Corpus e sola configurazione sperimentale riproducibili con `evidence/calibration-corpus-config.zip` (tre markdown italiani brevi e una funzione Python); hash individuali, byte e ambiente in `environment-20260921.json`. La prova piccola valida il metodo, non rappresenta la distribuzione o la capacità del prodotto.

Il precedente container dedicato non era più presente alla ripresa. Ricreato `sidecar-0628-qdrant`, ID `4585573c7f4e577d51442ee2ae41ebea6fbb6e570634cfda1d1bb2d388ccd9a8`, stessa immagine/porta/storage indicati sotto; limite sperimentale 1 GiB e 2 CPU, non budget prodotto. Preflight reale `qdrant-preflight-20260921.json`: nessuna collection, PID Qdrant 7, campionamento RSS/private/cgroup disponibile. Porte applicazione18000 e Qdrant16333 libere prima dell'avvio dedicato. Nessun processo Python preesistente rilevato. CPU forzata e quattro thread per il driver previsto, modello cache locale revision `5617a9f61b028005a4858fdac845db406aefb181`; nessun servizio LLM richiesto.

Checkpoint PAUSED_USAGE dopo la strumentazione: commit 4a1539c (1a) ed e8d8940 (1b/1c), review indipendenti approvate. Suite integrata di sei file: test_reindex.py, test_bench.py, test_retrieve_reload.py, test_incremental_indexing.py, test_index_timings.py, test_bench_process.py. Windows 184 passed in 23.34s; Linux 184 passed in 27.64s, exit0, log *-phase1-integrated.txt. Windows usa runtime read-only e --basetemp eval/results/sidecar_20260915/sandbox/pytest-phase1-integrated; Linux usa snapshot sandbox/post1-integrated, stesso harness isolato sotto descritto, -o addopts= -q e basetemp /tmp/sidecar-pytest. Psutil Linux 7.2.2 è già nell'immagine. Questi test non sostituiscono boot/query/delta con modello e Qdrant reali.

Checkout di lavoro: C:/Users/Silve/.codex/worktrees/0628/vibecraft.
Baseline codice: 4f35acf7ad18034c42203090189dfccfdbe42611. Archivio ottenuto con
`git archive --format=zip --output=<run>/sandbox/baseline-4f35acf.zip 4f35acf7ad18034c42203090189dfccfdbe42611`,
estratto in `<run>/sandbox/baseline`. Nessuna copia di `.env.local` o del database operativo.
L'archivio e i database temporanei sono ignorati da Git; hash e parametri sono conservati nelle evidenze.

Python Windows esistente: C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe.
Usarlo con `-B` e `PYTHONDONTWRITEBYTECODE=1`, dalla directory rag del checkout di prova.
Non installare pacchetti né modificare il venv sorgente. Tutti gli import del progetto devono risolversi nel checkout di prova.

Qdrant previsto: immagine locale qdrant/qdrant:v1.19.0, nuovo container e storage nella sandbox,
porta loopback 16333 (da verificare libera all'avvio), collection `sidecar_0628_benchmark`.
Server applicativo previsto: loopback 18000 (da verificare libera). Nessun accesso alle collection operative.
I container esistenti `vibecraft-qdrant-1` e `qdrant` NON sono i target delle prove.

Budget prodotto non definiti: l'utente conferma che il progetto è destinato a macchine diverse.
Le prove pubblicheranno hardware, distribuzione corpus, parametri e intervalli osservati;
nessuna soglia universale né idoneità a una macchina non misurata.
Cache filesystem non controllata: prima lettura in un processo nuovo non equivale a cold disk.
Nessun benchmark GPU/RAM concorrente. Test con fake dimostrano comportamento, non capacità.

Le misure storiche in colbert_memory_20260915 riguardano soltanto il loader e non il server.
Linux: Docker image `vibecraft:cpu` ID `sha256:247e635cbebf302fd4373ab69d961b8c85213e8686a506fa30e3db659e86fec4`.
Runtime effettivo in linux-runtime.txt. Pytest non incluso nell'immagine: copiati dal venv Windows solo
package pure Python pytest/_pytest/pluggy/iniconfig/packaging/pygments, metadata e shim py.py,
in sandbox/linux-test-deps, montati read-only in /test-deps. Nessuna installazione nel venv sorgente.
Comando baseline: `docker run --rm --network none -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/work/rag:/test-deps -e PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 --tmpfs /work/rag/database --mount type=bind,source=<baseline>,target=/work,readonly --mount type=bind,source=<linux-test-deps>,target=/test-deps,readonly --workdir /work/rag --entrypoint /app/rag/.venv/bin/python vibecraft:cpu -B -m pytest tests/test_reindex.py tests/test_bench.py tests/test_retrieve_reload.py tests/test_lifespan.py -q -p no:cacheprovider --basetemp=/tmp/sidecar-pytest`.
80 test verdi, exit 0: linux-baseline-phase1a-tmpfs.txt. Senza tmpfs il primo run ha due fallimenti:
i test archive accedono al PipelineStore del package; il mount read-only ne impediva le scritture.
Anche quel log resta conservato. Queste sono verifiche funzionali, non misure di capacità Linux.

Post unità1a prima del fix di review: 89 passed, log linux-post-phase1a.txt. Codice riproducibile:
baseline + rag/adr/sidecar-work/phase1a-review.diff; la snapshot copiava soltanto i sei file del diff,
escludendo le modifiche1b concorrenti.

Incidente preparazione: una prima prova del sampler ha usato la root sandbox come basetemp pytest,
eliminando le copie temporanee. Qdrant dedicato (ancora vuoto) fermato subito; nessuna risorsa operativa
o evidenza fuori sandbox toccata. Baseline rigenerata con hash archivio identico e sette artefatti storici
ricopiati con hash identici a historical-artifacts-provenance.json. Ogni prova successiva usa
una sottodirectory esclusiva sandbox/pytest-<unità>-<run>. Nessun risultato di capacità deriva da questo incidente.

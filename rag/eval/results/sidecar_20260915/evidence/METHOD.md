# Run sidecar 2026-09-15 — metodo e isolamento

Stato: preparazione, nessun risultato di capacità ancora disponibile.

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

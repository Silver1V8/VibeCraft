# Review indipendente — driver sperimentale F4

**Verdetto dopo fix: APPROVATO per avviare le misure F4.** Review statica del solo `reader_experiment.py`; self-check sintetico leggero ripetuto con `-B` (exit 0) e `validate_f3_disk()` in sola lettura (exit 0: 8 artefatti, 50 punti attesi). Nessun modello, Qdrant o benchmark avviato dal reviewer. La copia storica e la baseline F3 sono lette da percorsi fissati sotto `rag/eval/results`, mentre le scritture del driver restano nella sandbox della run. Eager usa ora `_load_vectors` di produzione, importato prima della baseline; lazy NPZ e NPY espongono lo stesso `Mapping`.

## Chiusura dei quattro blocchi

1. **Baseline F3 verificata.** `rag/eval/results/sidecar_readers_20260921/evidence/reader_experiment.py:257-308,368-382` confronta `CURRENT`, hash/byte degli artefatti e manifest con il risultato F3 congelato, poi digest paginato dei punti con risultato e preflight PM prima del modello/retrieval. Il controllo disco è passato in sola lettura; il controllo Qdrant verrà eseguito dal PM sulla collection dedicata durante il run.

2. **Concorrenza coperta.** `reader_experiment.py:159-168` confronta accessi paralleli con lo stesso set di chiavi e risultati sequenziali per eager, lazy NPZ e NPY; il self-check aggiornato è passato.

3. **Pubblicazione con contenuti diversi coperta.** `reader_experiment.py:172-199` crea una seconda generazione NPY, modifica un valore soltanto lì, sposta un puntatore temporaneo e verifica che il vecchio reader conservi il valore originale mentre il nuovo veda quello cambiato. Non tocca `CURRENT` o file F3.

4. **Seed controllato.** `reader_experiment.py:252-255,366-410` richiede `PYTHONHASHSEED=0` per i worker e lo registra nei raw. I child ereditano l'ambiente; la parità esatta fra processi non è stata indebolita o ordinata artificialmente.

## Limiti da riportare

`full_worker` usa encode reale, Qdrant dedicato e `hybrid_search`/`rank_sections_by_relevance` canonici; il replay `io_worker` usa candidati fissi e non va chiamato retrieval completo. La baseline memoria dopo import o modello esclude quei costi; i soli snapshot `_metrics` non catturano picchi transienti del MaxSim fp32. Il sampler esterno pianificato dal PM può aggiungere picchi campionati, da etichettare come limiti inferiori. Le tre query full sono eseguite una volta ciascuna per processo: cinque processi danno ripetizioni, non cinque letture calde della stessa query nel processo. Cache OS non controllata e nessun p95 stabile da cinque repliche. **Finding residui: nessuno nel perimetro pre-run.**

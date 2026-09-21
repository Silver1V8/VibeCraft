# Misura read-only del loader ColBERT

Data: 2026-09-15; file risultati creato alle 08:34:43 UTC. Codice `18c4dc928d88b98c7731b3bfad429ced41135919`, versione indice `v20260911T155042`. Windows 11 Pro 10.0.26200, Ryzen 7 5800X, 33.553.300 KiB di memoria visibile. NumPy 2.5.2, psutil 7.2.2. Nessun modello inizializzato, nessun reindex, nessuna scrittura agli artefatti.

Risultati: [memory.json](memory.json). Tre processi nuovi, baseline dopo import e garbage collection. Il secondo caricamento mantiene il primo dict vivo: dimostra il costo di due copie, non riproduce il lifecycle completo del server. Le misure RSS/USS sono osservazioni del processo; peak_wset è il massimo Windows fino a quel punto. Nessun campionamento continuo del reindex. Cache del filesystem non svuotata: non chiamare i tempi «cold disk».

## Riproduzione

Dalla directory `rag/`, eseguire tre volte questo programma con `.venv/Scripts/python.exe` su Windows (`.venv/bin/python` su Linux). Salvare i tre JSON in una **nuova run**, senza sovrascrivere quelli originali. Il metodo usa gli stessi loader e la stessa sequenza della misura. Se CURRENT è cambiato, il risultato riguarda un altro indice.

```python
import gc
import json
import time
import numpy as np
import psutil
from core.artifacts import _load_vectors, load_artifacts, current_version, artifact_dir

proc = psutil.Process()

def mem():
    m = proc.memory_info()
    f = proc.memory_full_info()
    return {
        "rss": m.rss,
        "private": getattr(m, "private", None),
        "uss": getattr(f, "uss", None),
        "peak_wset": getattr(m, "peak_wset", None),
    }

def delta(a, b):
    return {k: b[k] - a[k] for k in a if a[k] is not None and b[k] is not None}

gc.collect()
base = mem()
t = time.perf_counter()
v = current_version()
p = artifact_dir(v)
col = _load_vectors(p / "colbert.npz")
one = mem()
load_s = time.perf_counter() - t
tokens = [a.shape[0] for a in col.values()]
t = time.perf_counter()
arts = load_artifacts(version=v)
two = mem()
second_s = time.perf_counter() - t
assert set(col) == set(arts.colbert_store) == set(arts.chunks_store)
assert all(a.ndim == 2 and a.dtype == np.float16 for a in col.values())
print(json.dumps({
    "version": v,
    "baseline": base,
    "colbert_loaded": one,
    "colbert_delta": delta(base, one),
    "load_colbert_seconds": load_s,
    "chunks": len(col),
    "documents": len({c["doc_id"] for c in arts.chunks_store.values()}),
    "vector_bytes": sum(a.nbytes for a in col.values()),
    "dimensions": sorted({a.shape[1] for a in col.values()}),
    "tokens_total": sum(tokens),
    "tokens_min": min(tokens),
    "tokens_max": max(tokens),
    "second_full_artifacts": two,
    "second_full_delta": delta(one, two),
    "second_load_seconds": second_s,
    "disk_bytes": {f.name: f.stat().st_size for f in p.iterdir() if f.is_file()},
}, indent=2))
```

Gli assert sono controlli di integrità della riproduzione, collocati dopo la misura. Non erano parte del cronometro originale. Il JSON originale conserva anche le versioni dei pacchetti e il dtype.

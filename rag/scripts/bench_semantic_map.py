"""Benchmark di core.graph_ops._find_duplicates su un corpus sintetico da 5000 chunk
(vettori 1024-dim float32, come bge-m3). Uso: python scripts/bench_semantic_map.py

Target: < 2s. Se il picco di memoria tracciato supera ~1GB, il commento nella docstring
di _find_duplicates va rivisto per calcolare le similarità a blocchi di righe invece
che come singola matrice n x n (con n=5000/8000 la matrice sims resta a ~100-256MB,
quindi il blocking non è necessario oggi — questo benchmark è la prova)."""
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.graph_ops import _find_duplicates  # noqa: E402

N = 5000
DIM = 1024
TARGET_SECONDS = 2.0


def main() -> None:
    rng = np.random.default_rng(42)
    mat = rng.normal(size=(N, DIM)).astype(np.float32)
    chunk_ids = [f"chunk-{i}" for i in range(N)]
    # Metà dei chunk sono documenti diversi (per esercitare la maschera cross-doc)
    parents = [f"doc-{i % (N // 2)}" for i in range(N)]

    tracemalloc.start()
    t0 = time.perf_counter()
    duplicates = _find_duplicates(mat, parents, chunk_ids)
    elapsed = time.perf_counter() - t0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak / (1024 * 1024)
    print(f"n={N} dim={DIM}")
    print(f"tempo: {elapsed:.3f}s (target < {TARGET_SECONDS}s)")
    print(f"picco memoria tracciata: {peak_mb:.1f} MB")
    print(f"duplicati trovati: {len(duplicates)}")

    assert elapsed < TARGET_SECONDS, f"benchmark troppo lento: {elapsed:.3f}s >= {TARGET_SECONDS}s"


if __name__ == "__main__":
    main()

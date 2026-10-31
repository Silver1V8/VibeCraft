# Embedding su GPU per i job di reindex — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Prerequisito:** il piano `2026-10-12-cow-delta-indexing.md` deve essere già mergiato. Questo piano parte da `main` aggiornato.

**Goal:** i job di reindex (delta, full, import di progetto) calcolano gli embedding su GPU per la sola durata del job, poi la liberano; se la GPU non c'è, non ha memoria libera sufficiente o esaurisce la VRAM a metà job, il lavoro prosegue sul modello CPU condiviso.

**Architecture:** un nuovo `JobEmbedder` (in `rag/core/job_embedder.py`) espone `encode()` come `BGEM3FlagModel`, quindi indicizzazione, code-link ed eval gate lo usano senza modifiche. Carica il modello GPU al primo `encode` (un job no-op non paga nulla), ripiega sul modello CPU condiviso del server per il resto del job e libera la VRAM all'uscita di un context manager `reindex_embedder(...)`. Le route di reindex lo passano come `embed_model`.

**Tech Stack:** Python 3.14, torch 2.13.0+cu126, FlagEmbedding (bge-m3), FastAPI, pytest. Nessuna nuova dipendenza.

**Spec:** questo documento, sezioni «Misure» e «Comportamento richiesto».

## Misure (2026-10-12, RTX 3070 Ti 8 GB)

- Embedding di 240 simboli di codice di SGD_FE: CPU (configurazione del server, `devices="cpu"`, fp32) 142,7 s; GPU (`devices="cuda:0"`, fp32) 2,6 s, circa 55 volte più veloce.
- Modello bge-m3 fp32 su GPU: circa 2.180 MB allocati. Dopo `stop_self_pool()`, `del`, `gc.collect()` e `torch.cuda.empty_cache()` restano circa 20 MB riservati: la VRAM torna davvero libera.
- La GPU è condivisa con Ollama (`qwen3.5:9b`, `num_ctx` 16384). Durante la misura erano occupati 4,7 GB su 8 con Ollama carico.
- Un OOM di torch è `torch.OutOfMemoryError`, sottoclasse di `RuntimeError`.

## Comportamento richiesto

1. Job no-op: nessun caricamento del modello GPU.
2. Il primo `encode` del job sceglie il device: GPU se `VIBECRAFT_REINDEX_DEVICE=auto` (default), CUDA è disponibile e la VRAM libera è almeno `VIBECRAFT_REINDEX_GPU_MIN_FREE_MB` (default 3072); altrimenti CPU, con il motivo registrato.
3. Se il caricamento GPU fallisce o un `encode` solleva un OOM, la stessa chiamata viene ripetuta sul modello CPU e il resto del job resta su CPU. Gli errori diversi dall'OOM durante `encode` si propagano senza essere mascherati.
4. A fine job, anche quando fallisce, il modello GPU viene rilasciato e la cache CUDA svuotata.
5. Il risultato del job riporta `embedding_device` (`"cuda"`, `"cpu"` o `"unused"`), `embedding_fallback_reason` e `embedding_load_seconds`.
6. Le query di `/ask` e della pipeline continuano a usare il modello CPU condiviso: il modello del job non si condivide.
7. La suite di test non carica mai bge-m3 sulla GPU, salvo opt-in esplicito (`VIBECRAFT_TEST_GPU=1`).

## Global Constraints

- Python solo da `rag/.venv/Scripts/python.exe`; comandi lanciati da `rag/`, con `-X utf8`.
- File con terminazioni LF; commenti e log in italiano come il codice circostante.
- `import torch` e `FlagEmbedding` solo dentro le funzioni di `core/job_embedder.py`: l'import del modulo deve restare leggero, come quello lazy di `routes_intake`.
- Embedding GPU in fp32 (`use_fp16=False`), come su CPU, per non introdurre differenze di precisione fra vettori indicizzati e query.
- Branch `feat/reindex-gpu-embedding` da `main`; un commit per task con la riga `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Suite completa prima del merge: `bash scripts/ci.sh`.

## Review Focus

1. **VRAM già occupata da Ollama all'avvio del job**: si passa subito alla CPU senza tentare il caricamento. Test `test_low_free_vram_goes_cpu_without_loading` (Task 1).
2. **OOM a metà job**: lo stesso batch viene rifatto su CPU, il job termina e il report lo dichiara. Test `test_oom_retries_same_call_on_cpu_and_stays_there` (Task 1).
3. **Job che fallisce con il modello GPU caricato**: la VRAM viene comunque liberata. Test `test_context_releases_gpu_even_when_job_fails` (Task 1).
4. **Server in Docker senza GPU** (`torch.cuda.is_available()` falso): CPU, nessun errore. Test `test_cuda_unavailable_goes_cpu` (Task 1).
5. **Errore non-OOM sulla GPU** (per esempio un input malformato): si propaga e non viene nascosto da un ripiego che raddoppierebbe i tempi. Test `test_non_oom_gpu_error_propagates` (Task 1).

---

### Task 1: `JobEmbedder` e configurazione

**Files:**
- Create: `rag/core/job_embedder.py`
- Modify: `rag/core/config.py` (dopo `DELTA_MODE`), `rag/tests/conftest.py` (in testa)
- Test: `rag/tests/test_job_embedder.py` (nuovo)

**Interfaces:**
- Produces:
  - `core.config.REINDEX_DEVICE: str` (`"auto"` | `"cpu"`), `core.config.REINDEX_GPU_MIN_FREE_MB: int`.
  - `class JobEmbedder(*, load_gpu, cpu_model, gpu_available, free_vram_mb, min_free_mb: int, enabled: bool, empty_cache)` con `encode(texts, **kwargs)`, `release() -> None`, `report() -> dict` (chiavi `embedding_device`, `embedding_fallback_reason`, `embedding_load_seconds`).
  - `reindex_embedder(cpu_model) -> ContextManager[JobEmbedder]`: `cpu_model` è una callable senza argomenti che restituisce il modello CPU condiviso, invocata solo se serve.

- [ ] **Step 1: Write the failing tests**

Crea `rag/tests/test_job_embedder.py`:

```python
"""JobEmbedder: GPU solo per la durata del job di reindex, CPU come ripiego."""
import os

import pytest
import torch

from core import job_embedder
from core.job_embedder import JobEmbedder


class FakeModel:
    def __init__(self, name, fail=None):
        self.name, self.fail, self.calls, self.stopped = name, fail, [], False

    def encode(self, texts, **kwargs):
        self.calls.append(list(texts))
        if self.fail is not None:
            raise self.fail
        return {"dense_vecs": [self.name] * len(texts)}

    def stop_self_pool(self):
        self.stopped = True


def make(*, gpu=None, available=True, free=8000, enabled=True, load_error=None):
    gpu, cpu = gpu or FakeModel("gpu"), FakeModel("cpu")
    loads, cleared = [], []

    def load_gpu():
        loads.append(True)
        if load_error is not None:
            raise load_error
        return gpu

    embedder = JobEmbedder(load_gpu=load_gpu, cpu_model=lambda: cpu,
                           gpu_available=lambda: available, free_vram_mb=lambda: free,
                           min_free_mb=3072, enabled=enabled,
                           empty_cache=lambda: cleared.append(True))
    return embedder, gpu, cpu, loads, cleared


def test_noop_job_never_loads_anything():
    embedder, _, _, loads, _ = make()
    embedder.release()
    assert loads == []
    assert embedder.report()["embedding_device"] == "unused"


def test_uses_gpu_then_releases_it():
    embedder, gpu, cpu, loads, cleared = make()
    assert embedder.encode(["a"])["dense_vecs"] == ["gpu"]
    assert embedder.encode(["b"])["dense_vecs"] == ["gpu"]
    assert loads == [True] and cpu.calls == []
    embedder.release()
    assert gpu.stopped and cleared
    report = embedder.report()
    assert report["embedding_device"] == "cuda" and report["embedding_fallback_reason"] is None
    assert report["embedding_load_seconds"] >= 0


def test_low_free_vram_goes_cpu_without_loading():
    embedder, _, cpu, loads, _ = make(free=1000)
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert loads == []
    assert "VRAM" in embedder.report()["embedding_fallback_reason"]


def test_cuda_unavailable_goes_cpu():
    embedder, _, _, loads, _ = make(available=False)
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert loads == [] and embedder.report()["embedding_device"] == "cpu"


def test_disabled_goes_cpu():
    embedder, _, _, loads, _ = make(enabled=False)
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert loads == []
    assert "VIBECRAFT_REINDEX_DEVICE" in embedder.report()["embedding_fallback_reason"]


def test_gpu_load_failure_falls_back_to_cpu():
    embedder, _, _, _, _ = make(load_error=RuntimeError("CUDA driver mismatch"))
    assert embedder.encode(["a"])["dense_vecs"] == ["cpu"]
    assert "caricamento" in embedder.report()["embedding_fallback_reason"]


def test_oom_retries_same_call_on_cpu_and_stays_there():
    gpu = FakeModel("gpu", fail=torch.OutOfMemoryError("CUDA out of memory"))
    embedder, _, cpu, _, cleared = make(gpu=gpu)
    assert embedder.encode(["a", "b"])["dense_vecs"] == ["cpu", "cpu"]
    assert cpu.calls == [["a", "b"]]
    assert gpu.stopped and cleared  # VRAM liberata subito, non a fine job
    embedder.encode(["c"])
    assert len(gpu.calls) == 1 and cpu.calls[-1] == ["c"]
    report = embedder.report()
    assert report["embedding_device"] == "cpu" and "memoria" in report["embedding_fallback_reason"]


def test_non_oom_gpu_error_propagates():
    embedder, _, cpu, _, _ = make(gpu=FakeModel("gpu", fail=ValueError("input malformato")))
    with pytest.raises(ValueError, match="malformato"):
        embedder.encode(["a"])
    assert cpu.calls == []


def test_context_releases_gpu_even_when_job_fails(monkeypatch):
    gpu = FakeModel("gpu")
    monkeypatch.setattr(job_embedder, "REINDEX_DEVICE", "auto")
    monkeypatch.setattr(job_embedder, "_load_gpu_model", lambda: gpu)
    monkeypatch.setattr(job_embedder, "_cuda_available", lambda: True)
    monkeypatch.setattr(job_embedder, "_free_vram_mb", lambda: 8000)
    monkeypatch.setattr(job_embedder, "_empty_cuda_cache", lambda: None)
    with pytest.raises(RuntimeError, match="job fallito"):
        with job_embedder.reindex_embedder(lambda: FakeModel("cpu")) as embedder:
            embedder.encode(["x"])
            raise RuntimeError("job fallito")
    assert gpu.stopped


@pytest.mark.skipif(os.environ.get("VIBECRAFT_TEST_GPU") != "1",
                    reason="opt-in: VIBECRAFT_TEST_GPU=1 su una macchina con CUDA")
def test_real_gpu_model_is_released(monkeypatch):
    monkeypatch.setattr(job_embedder, "REINDEX_DEVICE", "auto")
    with job_embedder.reindex_embedder(lambda: pytest.fail("ripiego CPU inatteso")) as embedder:
        out = embedder.encode(["def f(): pass"] * 12, batch_size=12, return_dense=True)
        assert len(out["dense_vecs"]) == 12
        assert embedder.report()["embedding_device"] == "cuda"
    assert torch.cuda.memory_reserved() < 256 * 2**20
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_job_embedder.py -v`
Expected: errore di collezione con `ModuleNotFoundError: No module named 'core.job_embedder'`.

- [ ] **Step 3: Config e conftest**

In `rag/core/config.py`, dopo `DELTA_MODE = ...`:

```python
# Embedding dei job di reindex: "auto" usa la GPU per la sola durata del job se c'è
# abbastanza VRAM libera (soglia sotto), altrimenti il modello CPU condiviso; "cpu" la esclude.
REINDEX_DEVICE = _env_choice("VIBECRAFT_REINDEX_DEVICE", "auto", {"auto", "cpu"})
REINDEX_GPU_MIN_FREE_MB = int(os.environ.get("VIBECRAFT_REINDEX_GPU_MIN_FREE_MB", "3072"))
```

In testa a `rag/tests/conftest.py`, prima degli altri import:

```python
import os

# I test non caricano mai bge-m3 sulla GPU: i job di reindex restano su CPU (modelli
# finti) salvo i test che lo abilitano esplicitamente con monkeypatch.
os.environ.setdefault("VIBECRAFT_REINDEX_DEVICE", "cpu")
```

- [ ] **Step 4: Implementa `core/job_embedder.py`**

```python
"""Embedder dei job di reindex: bge-m3 su GPU per la sola durata del job, poi la VRAM
torna libera (la GPU è condivisa con Ollama). Se CUDA manca, la VRAM libera è sotto
soglia o un encode la esaurisce, il resto del job usa il modello CPU condiviso del
server. Espone encode() come BGEM3FlagModel: indicizzazione, code-link ed eval-gate
lo usano senza saperlo. torch/FlagEmbedding sono importati solo quando servono."""
from __future__ import annotations

import gc
import logging
import time
from contextlib import contextmanager

from core.config import EMBEDDING_MODEL, REINDEX_DEVICE, REINDEX_GPU_MIN_FREE_MB

logger = logging.getLogger(__name__)


def _is_oom(exc: BaseException) -> bool:
    import torch
    return isinstance(exc, torch.OutOfMemoryError) or "out of memory" in str(exc).lower()


class JobEmbedder:
    """Sceglie il device al primo encode (un job no-op non carica nulla) e lo mantiene
    per il job; dopo un ripiego su CPU non torna mai alla GPU nello stesso job."""

    def __init__(self, *, load_gpu, cpu_model, gpu_available, free_vram_mb,
                 min_free_mb: int, enabled: bool, empty_cache):
        self._load_gpu = load_gpu
        self._cpu_model = cpu_model
        self._gpu_available = gpu_available
        self._free_vram_mb = free_vram_mb
        self._min_free_mb = min_free_mb
        self._enabled = enabled
        self._empty_cache = empty_cache
        self._gpu = None
        self.device: str | None = None
        self.fallback_reason: str | None = None
        self.load_seconds = 0.0

    def encode(self, texts, **kwargs):
        if self.device is None:
            self._choose_device()
        if self.device == "cuda":
            try:
                return self._gpu.encode(texts, **kwargs)
            except Exception as exc:
                if not _is_oom(exc):
                    raise
                self._fall_back(f"memoria GPU esaurita durante l'embedding: {exc}")
        return self._cpu_model().encode(texts, **kwargs)

    def _choose_device(self) -> None:
        if not self._enabled:
            self._fall_back("VIBECRAFT_REINDEX_DEVICE=cpu")
            return
        if not self._gpu_available():
            self._fall_back("CUDA non disponibile")
            return
        free = self._free_vram_mb()
        if free < self._min_free_mb:
            self._fall_back(f"VRAM libera {free} MB sotto la soglia di {self._min_free_mb} MB")
            return
        started = time.perf_counter()
        try:
            self._gpu = self._load_gpu()
        except Exception as exc:
            self._fall_back(f"caricamento del modello su GPU fallito: {exc}")
            return
        finally:
            self.load_seconds = time.perf_counter() - started
        self.device = "cuda"
        logger.info("Embedding del job di reindex su GPU (VRAM libera all'avvio: %s MB).", free)

    def _fall_back(self, reason: str) -> None:
        self.release()
        self.device = "cpu"
        self.fallback_reason = reason
        logger.warning("Embedding del job di reindex su CPU: %s", reason)

    def release(self) -> None:
        """Libera il modello GPU e la cache CUDA; idempotente."""
        if self._gpu is None:
            return
        try:
            self._gpu.stop_self_pool()
        except Exception:
            logger.debug("stop_self_pool fallito durante il rilascio", exc_info=True)
        self._gpu = None
        gc.collect()
        self._empty_cache()

    def report(self) -> dict:
        return {"embedding_device": self.device or "unused",
                "embedding_fallback_reason": self.fallback_reason,
                "embedding_load_seconds": self.load_seconds}


def _load_gpu_model():
    from FlagEmbedding import BGEM3FlagModel
    return BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False, devices="cuda:0")


def _cuda_available() -> bool:
    import torch
    return torch.cuda.is_available()


def _free_vram_mb() -> int:
    import torch
    return torch.cuda.mem_get_info()[0] // 2**20


def _empty_cuda_cache() -> None:
    import torch
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


@contextmanager
def reindex_embedder(cpu_model):
    """Embedder di un singolo job: la VRAM viene liberata all'uscita, anche su errore."""
    embedder = JobEmbedder(load_gpu=_load_gpu_model, cpu_model=cpu_model,
                           gpu_available=_cuda_available, free_vram_mb=_free_vram_mb,
                           min_free_mb=REINDEX_GPU_MIN_FREE_MB, enabled=REINDEX_DEVICE == "auto",
                           empty_cache=_empty_cuda_cache)
    try:
        yield embedder
    finally:
        embedder.release()
```

Nota: `test_disabled_goes_cpu` e `test_low_free_vram_goes_cpu_without_loading` passano per `_fall_back`, che chiama `release()` con `_gpu` ancora `None`: è un no-op voluto.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_job_embedder.py -v -rs`
Expected: tutti PASS, `test_real_gpu_model_is_released` SKIPPED (opt-in).

Poi l'opt-in sulla macchina con GPU (PowerShell): `$env:VIBECRAFT_TEST_GPU='1'; .venv/Scripts/python.exe -X utf8 -m pytest tests/test_job_embedder.py::test_real_gpu_model_is_released -v`
Expected: PASS (se Ollama occupa troppa VRAM, il test fallisce con «ripiego CPU inatteso»: liberala con `ollama stop qwen3.5:9b` e riprova).

- [ ] **Step 6: Commit**

```bash
git add rag/core/job_embedder.py rag/core/config.py rag/tests/conftest.py rag/tests/test_job_embedder.py
git commit -m "feat: job-scoped GPU embedder with CPU fallback for reindex jobs"
```

---

### Task 2: Uso nei job di reindex e di import

**Files:**
- Modify: `rag/api/routes_reindex.py` (`_run_reindex` riga ~98, `_run_full_rebuild` riga ~139)
- Modify: `rag/api/routes_intake.py` (`_server_reindex` riga ~141)
- Modify: `rag/tests/test_index_timings.py` (`test_incremental_route_defers_model_to_core_for_noop_and_content`)
- Test: `rag/tests/test_job_embedder.py` (test di route aggiunti in fondo)

**Interfaces:**
- Consumes: `reindex_embedder(cpu_model)` e `JobEmbedder.report()` (Task 1); `_reindex_embed_model()` esistente, che resta il fornitore del modello CPU condiviso.
- Produces: i risultati di `_run_reindex`, `_run_full_rebuild` e `_server_reindex` includono le chiavi di `report()`.

- [ ] **Step 1: Write the failing tests**

In fondo a `rag/tests/test_job_embedder.py`:

```python
def test_incremental_route_passes_job_embedder_and_reports_device(monkeypatch):
    from api import routes_reindex

    monkeypatch.setattr(routes_reindex, "ensure_shared_resources", lambda **kwargs: None)
    received = {}

    def fake_incremental(**kwargs):
        received.update(kwargs)
        kwargs["embed_model"].encode(["x"])
        return {"noop": False}

    monkeypatch.setattr(routes_reindex, "incremental_index", fake_incremental)
    monkeypatch.setattr(routes_reindex, "_reindex_embed_model", lambda: FakeModel("cpu"))

    result = routes_reindex._run_reindex(None)

    assert isinstance(received["embed_model"], JobEmbedder)
    assert result["embedding_device"] == "cpu"  # conftest: VIBECRAFT_REINDEX_DEVICE=cpu


def test_full_rebuild_route_uses_job_embedder(monkeypatch):
    from api import routes_reindex

    seen = {}

    def fake_build(**kwargs):
        seen["model"] = kwargs["embed_model"]
        kwargs["collector"].update({"phase_timings_seconds": {
            p: 0.0 for p in ("init_model", "scan_hash", "load", "parsing_embedding", "qdrant",
                             "relink", "save_hash", "eval_gate", "promote")}, "counts": {}})
        return None

    monkeypatch.setattr(routes_reindex, "build_graph_and_index", fake_build)
    monkeypatch.setattr(routes_reindex, "_reindex_embed_model",
                        lambda: pytest.fail("modello CPU caricato senza encode"))

    result = routes_reindex._run_full_rebuild(None)

    assert isinstance(seen["model"], JobEmbedder)
    assert result["embedding_device"] == "unused"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_job_embedder.py -k route -v`
Expected: FAIL. Nel primo test `received["embed_model"]` non è un `JobEmbedder`; nel secondo il modello CPU viene caricato subito.

- [ ] **Step 3: `_run_reindex`**

In `rag/api/routes_reindex.py` aggiungi l'import `from core.job_embedder import reindex_embedder` (in ordine con gli import `core.*`) e sostituisci `_run_reindex` con:

```python
def _run_reindex(changed_paths, *, project=None) -> dict:
    """Reindex delta: embedding sul modello del job (GPU finché c'è memoria, poi il
    modello CPU condiviso, caricato solo se serve); un no-op non carica nulla."""
    ensure_shared_resources(embedding=False)
    with reindex_embedder(_reindex_embed_model) as embed_model:
        result = incremental_index(
            qdrant=state.get("qdrant"),
            embed_model=embed_model,
            changed_paths=changed_paths, project=project,
        )
    result.update(embed_model.report())
    if result.get("noop") is True:
        disk_version = current_version(project) or _graph_version(project)
        snapshot = current_snapshot(project)
        if snapshot is not None and snapshot.version == disk_version:
            result["snapshot_token"] = snapshot.version
    return result
```

- [ ] **Step 4: `_run_full_rebuild`**

Rinomina l'attuale corpo in `_full_rebuild_with(embed_model, *, project=None) -> dict`: togli le tre righe `started = …`, `embed_model = _reindex_embed_model()`, `init_model = …` e la riga `timings["init_model"] += init_model`, lasciando il resto invariato. Poi definisci:

```python
def _run_full_rebuild(changed_paths, *, project=None) -> dict:
    """Job "full" (vedi _full_rebuild_with): embedding sul modello del job, la cui VRAM
    è liberata a fine job anche se build o gate falliscono. `changed_paths` è ignorato."""
    with reindex_embedder(_reindex_embed_model) as embed_model:
        result = _full_rebuild_with(embed_model, project=project)
    result.update(embed_model.report())
    return result
```

Sposta il docstring lungo esistente su `_full_rebuild_with`. Il tempo di caricamento del modello GPU ora è in `embedding_load_seconds` e `phase_timings_seconds.init_model` resta 0 per i job full: annotalo nel docstring.

- [ ] **Step 5: `_server_reindex` (import di progetto)**

In `rag/api/routes_intake.py` sostituisci il corpo di `_server_reindex` con:

```python
    from core.indexing import incremental_index
    from core.job_embedder import reindex_embedder
    from api.routes_reindex import _reindex_embed_model
    ensure_shared_resources(embedding=False)
    with reindex_embedder(_reindex_embed_model) as embed_model:
        result = incremental_index(
            qdrant=state.get("qdrant"),
            embed_model=embed_model,
            changed_paths=changed_paths, project=project,
        )
    result.update(embed_model.report())
    return result
```

e aggiorna la prima riga del docstring: «Reindex delta con il client Qdrant del server e il modello di embedding del job (GPU se disponibile, altrimenti quello CPU condiviso), usato dall'import dei progetti.»

- [ ] **Step 6: Aggiorna il test di timing esistente**

In `rag/tests/test_index_timings.py`, in `test_incremental_route_defers_model_to_core_for_noop_and_content`, sostituisci `assert received[0]["embed_model"] is None` con:

```python
    from core.job_embedder import JobEmbedder
    # Il modello del job è pigro: la route non carica nulla, il core decide se serve.
    assert isinstance(received[0]["embed_model"], JobEmbedder)
```

Le altre asserzioni restano: il fornitore `_reindex_embed_model` non deve essere invocato e `ensure_shared_resources` deve ricevere `{"embedding": False}`.

- [ ] **Step 7: Run tests**

Run: `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_job_embedder.py tests/test_index_timings.py tests/test_reindex.py tests/test_project_indexing.py tests/test_project_tools.py tests/test_project_import.py tests/test_intake_staging.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add rag/api/routes_reindex.py rag/api/routes_intake.py rag/tests/test_index_timings.py rag/tests/test_job_embedder.py
git commit -m "feat: run reindex and import jobs on the job-scoped GPU embedder"
```

---

### Task 3: Documentazione e verifica dal vivo

**Files:**
- Modify: `rag/README.md` (tabella variabili dopo `VIBECRAFT_DELTA_MODE`), `README.md` (paragrafo sul delta aggiunto dal piano copy-on-write, riga ~115)

- [ ] **Step 1: Tabella variabili in `rag/README.md`**

```
| `VIBECRAFT_REINDEX_DEVICE` | `auto` | Embedding dei job di reindex: `auto` usa la GPU per la sola durata del job (poi la libera) se c'è VRAM sufficiente, altrimenti la CPU; `cpu` la esclude |
| `VIBECRAFT_REINDEX_GPU_MIN_FREE_MB` | 3072 | VRAM libera minima all'avvio del job per usare la GPU |
```

- [ ] **Step 2: README di root**

In coda al paragrafo sul delta copy-on-write aggiungi:

```
Gli embedding dei job di reindex usano la GPU per la sola durata del job, se c'è VRAM
libera sufficiente, e la liberano a fine job; altrimenti, o se la memoria finisce a
metà, proseguono sulla CPU. Il job riporta `embedding_device` ed eventualmente
`embedding_fallback_reason`. Mentre un job usa la GPU, Ollama può dover tenere parte
del modello in RAM: le risposte di `/ask` in quel momento possono rallentare.
```

- [ ] **Step 3: CI completa**

Run (da `rag/`): `bash scripts/ci.sh`
Expected: verde; fra gli skip compare `test_real_gpu_model_is_released` (opt-in).

- [ ] **Step 4: Verifica dal vivo (manuale, con l'utente)**

1. Riavvia il server: il job deve usare il codice nuovo.
2. `nvidia-smi --query-gpu=memory.used --format=csv` prima del job.
3. Sul progetto SviluppoUrgenteSandro modifica un documento, poi «Aggiorna indice».
4. `GET /api/reindex/{job_id}`. Atteso: `result.embedding_device == "cuda"` (oppure `"cpu"` con un `embedding_fallback_reason` coerente con la VRAM di quel momento) e `result.delta_mode == "cow"`.
5. `nvidia-smi` dopo il job: memoria tornata al valore del punto 2 più il contesto CUDA residuo (qualche centinaio di MiB) finché il server non viene riavviato.
6. Con `qwen3.5:9b` caricato in Ollama, verificare che il job passi alla CPU se `nvidia-smi` riporta meno di 3072 MiB liberi.

- [ ] **Step 5: Commit**

```bash
git add README.md rag/README.md
git commit -m "docs: describe GPU embedding for reindex jobs and its CPU fallback"
```

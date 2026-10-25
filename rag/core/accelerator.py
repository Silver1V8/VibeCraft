"""Scelta dell'acceleratore per l'embedding di un job, senza aprire un contesto
nel processo del server.

L'ordine in `auto` è quello che questo processo sa eseguire davvero:

1. CUDA. Vale per le RTX discrete e per i chip a memoria unificata NVIDIA (DGX
   Spark, RTX Spark, GB10, Grace): sono CUDA, non un backend a parte.
2. Metal (`mps`) su Apple Silicon. Il processo figlio dura un job e, uscendo,
   restituisce la memoria unificata.
3. GPU Intel o AMD vista da OpenVINO, se CUDA e Metal non ci sono o la scheda
   NVIDIA non ha memoria libera: ci gira l'encoder, le teste restano sulla CPU
   del figlio. Una GPU AMD con ROCm è CUDA per PyTorch (HIP) e sta al punto 1.
4. NPU, se un runtime installato compila l'encoder (OpenVINO su Intel, QNN su
   Hexagon, Vitis AI su Ryzen AI, Core ML sul Neural Engine).
5. CPU, con un numero di thread che lascia un core al server.

Se la GPU scelta ha spazio per i pesi dell'embedding e per quelli dell'LLM
(soglia ricavata dal vincolo misurato: 8 GB non tengono bge-m3 e qwen3.5:9b
insieme), il reindex mette l'intero modello lì. Altrimenti si divide: l'LLM
tiene la scheda grossa, l'embedding va sull'altro acceleratore o sulla CPU.
`/ask` resta sempre sulla CPU del server: la generazione segue subito e un
contesto CUDA residente la manderebbe in split.
"""
from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
from dataclasses import dataclass

UNIFIED_NVIDIA_MARKERS = ("gb10", "grace", "spark", "n1x")
UNIFIED_FREE_FLOOR_MB = 1024
# bge-m3 fp32 sta intorno ai 2,2 GB. qwen3.5:9b in Ollama non ci sta insieme su
# 8 GB (misura del progetto, non una stima di targa): sotto questa soglia i due
# pesi vanno su componenti diversi. Sopra, il reindex può tenere l'intero modello
# sulla stessa GPU che userà l'LLM, a turno e non insieme a /ask.
EMBED_WEIGHTS_MB = 2300
LLM_WEIGHTS_MB = 7000
PLACEMENT_HEADROOM_MB = 1024
BOTH_WEIGHTS_MB = EMBED_WEIGHTS_MB + LLM_WEIGHTS_MB + PLACEMENT_HEADROOM_MB


@dataclass(frozen=True)
class GpuMemory:
    index: int
    name: str
    free_mb: int
    total_mb: int

    @property
    def unified(self) -> bool:
        lowered = self.name.lower()
        return any(marker in lowered for marker in UNIFIED_NVIDIA_MARKERS)


@dataclass(frozen=True)
class EmbeddingDecision:
    device: str
    torch_device: str | None
    reason: str | None
    memory_mb: int | None
    accelerator: str | None
    npu: str | None
    placement: str = "cpu"
    placement_reason: str | None = None


def decide(preference: str, *, cuda: bool, gpus: list[GpuMemory] | None,
           gpu_error: BaseException | None, mps: bool, apple_mb: int | None,
           apple_error: BaseException | None, npu: str | None,
           min_free_mb: int, npu_ready: bool = False, npu_name: str | None = None,
           npu_reason: str | None = None, intel_ready: bool = False,
           intel_name: str | None = None, intel_reason: str | None = None) -> EmbeddingDecision:
    """`preference` è auto, cuda, mps, npu, intel o cpu. `gpus` è None se la sonda
    NVIDIA/AMD non è stata tentata. Un errore di sonda non è memoria zero."""
    if preference == "cpu":
        return _pack("cpu", None, "VIBECRAFT_REINDEX_DEVICE=cpu", None, None, npu, gpus)

    cuda_reason = None
    if preference in {"auto", "cuda"}:
        if not cuda:
            cuda_reason = "CUDA non disponibile"
        elif gpu_error is not None:
            cuda_reason = f"VRAM non interrogabile: {gpu_error}"
        elif not gpus:
            cuda_reason = "VRAM non interrogabile: nvidia-smi non ha prodotto output"
        else:
            chosen = _pick_gpu(gpus, min_free_mb)
            if chosen is not None:
                return _pack("cuda", f"cuda:{chosen.index}", None, chosen.free_mb,
                             chosen.name, npu, gpus)
            cuda_reason = _cuda_refusal(gpus, min_free_mb)

    # Sonda muta: non sappiamo se la scheda è libera, quindi non si cambia
    # acceleratore in silenzio. Memoria bassa è un'altra cosa: l'LLM può tenere
    # la scheda e l'embedding andare su un secondo componente.
    probe_failed = bool(cuda_reason and cuda_reason.startswith("VRAM non interrogabile"))

    mps_reason = None
    if preference in {"auto", "mps"} and (preference == "mps" or not probe_failed):
        if not mps:
            mps_reason = "Metal non disponibile"
        elif apple_error is not None:
            mps_reason = f"memoria Apple non interrogabile: {apple_error}"
        elif apple_mb is None:
            mps_reason = "memoria Apple non interrogabile"
        elif apple_mb < min_free_mb:
            mps_reason = (f"memoria unificata Apple {apple_mb} MB sotto la soglia "
                          f"di {min_free_mb} MB")
        else:
            return _pack("mps", "mps", None, apple_mb, "Apple Metal", npu, gpus)

    mps_refused = bool(mps and mps_reason not in {None, "Metal non disponibile"})
    # Metal rifiutato per memoria usa lo stesso pool del Neural Engine: non si
    # sposta il lavoro lì. Una NVIDIA senza VRAM libera, invece, può lasciare
    # l'embedding a una GPU Intel/AMD o a una NPU diversa.
    if not probe_failed and not mps_refused and preference in {"auto", "intel", "npu"}:
        if preference in {"auto", "intel"} and intel_ready:
            return _pack("intel", "ov:GPU", None, None, intel_name or "GPU OpenVINO", npu, gpus)
        if preference == "intel":
            return _pack("cpu", None, intel_reason or "GPU OpenVINO assente", None, None, npu, gpus)
        if npu_ready:
            name = npu_name or "NPU"
            return _pack("npu", "npu", None, None, name, npu or name, gpus)
        if preference == "npu":
            return _pack("cpu", None, npu_reason or "runtime NPU assente", None, None, npu, gpus)

    if preference == "cuda":
        reason = cuda_reason
    elif preference == "mps":
        reason = mps_reason
    elif preference == "intel":
        reason = intel_reason or "GPU OpenVINO assente"
    elif probe_failed or (cuda and cuda_reason and cuda_reason != "CUDA non disponibile"):
        reason = cuda_reason
    elif mps_refused:
        reason = mps_reason
    elif npu and not _apple_only(npu) and npu_reason:
        reason = f"{npu}: {npu_reason}"
    else:
        reason = cuda_reason or mps_reason or npu_reason or intel_reason
    return _pack("cpu", None, reason, None, None, npu, gpus)


def _pack(device, torch_device, reason, memory, accelerator, npu, gpus) -> EmbeddingDecision:
    mode, why = describe_placement(device, gpus, accelerator)
    return EmbeddingDecision(device, torch_device, reason, memory, accelerator, npu, mode, why)


def describe_placement(device: str, gpus: list[GpuMemory] | None,
                       accelerator: str | None) -> tuple[str, str]:
    """`gpu`: l'intero embedding sta sulla GPU che può ospitare anche l'LLM.
    `split`: i pesi sono divisi fra componenti. `cpu`: niente acceleratore."""
    best = max(gpus, key=lambda gpu: (gpu.total_mb, gpu.free_mb)) if gpus else None
    if device in {"cuda", "mps"} and best is not None and best.total_mb >= BOTH_WEIGHTS_MB:
        return ("gpu",
                "pesi interi dell'embedding sulla GPU, che ha anche spazio per l'LLM; "
                "/ask resta su CPU perché la generazione segue subito")
    if device in {"cuda", "mps"}:
        return ("split",
                "reindex sulla GPU solo per il job; l'LLM tiene la scheda; /ask resta su CPU")
    if device == "intel":
        return ("split",
                f"encoder su {accelerator or 'GPU OpenVINO'}, teste sparse e ColBERT "
                "sulla CPU del figlio; l'LLM non usa questo componente")
    if device == "npu":
        return ("split",
                f"encoder su {accelerator or 'NPU'}, teste sulla CPU del figlio; "
                "/ask resta sul processore")
    return ("cpu", "embedding su CPU")


def cpu_threads(logical: int | None = None) -> int:
    """Thread di torch per l'embedding su CPU. Un core resta al server."""
    count = logical if logical is not None else (os.cpu_count() or 1)
    if count <= 1:
        return 1
    return min(count - 1, 8)


def _pick_gpu(gpus: list[GpuMemory], min_free_mb: int) -> GpuMemory | None:
    """La GPU con più memoria libera che supera la soglia. Su un chip unificato
    (Spark, GB10, Grace) la soglia si applica al totale del pool, purché resti
    almeno 1 GiB libero: `memory.free` lì è ciò che il sistema non ha già
    mappato, non la VRAM di una scheda discreta."""
    ranked = sorted(gpus, key=lambda gpu: (gpu.free_mb, gpu.total_mb), reverse=True)
    for gpu in ranked:
        if gpu.free_mb >= min_free_mb:
            return gpu
        if gpu.unified and gpu.total_mb >= min_free_mb and gpu.free_mb >= UNIFIED_FREE_FLOOR_MB:
            return gpu
    return None


def _cuda_refusal(gpus: list[GpuMemory], min_free_mb: int) -> str:
    best = max(gpus, key=lambda gpu: (gpu.free_mb, gpu.total_mb))
    if best.unified and best.total_mb >= min_free_mb and best.free_mb < UNIFIED_FREE_FLOOR_MB:
        return (f"memoria unificata {best.name}: liberi {best.free_mb} MB, "
                f"sotto il minimo di {UNIFIED_FREE_FLOOR_MB} MB")
    return f"VRAM libera {best.free_mb} MB sotto la soglia di {min_free_mb} MB"


def parse_nvidia_smi(text: str) -> list[GpuMemory]:
    """Righe di `nvidia-smi --query-gpu=index,name,memory.free,memory.total
    --format=csv,noheader,nounits`. Un nome con la virgola arriva fra virgolette.
    csv.reader tratta il carattere che segue le virgolette come parte del campo
    successivo: senza questo scarto, `8192` diventerebbe ` 8192` e int() fallirebbe
    solo sui nomi quotati, cioè proprio sulle GPU il cui nome contiene una virgola."""
    gpus = []
    for row in csv.reader(text.splitlines(), skipinitialspace=True):
        cells = [cell.strip() for cell in row]
        if len(cells) != 4 or not cells[0]:
            continue
        gpus.append(GpuMemory(int(cells[0]), cells[1], int(cells[2]), int(cells[3])))
    if not gpus:
        raise RuntimeError("nvidia-smi non ha prodotto output")
    return gpus


def query_nvidia_gpus() -> list[GpuMemory]:
    """Non crea un contesto CUDA. Qualsiasi errore della sonda è sollevato."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.free,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc
    if out.returncode != 0:
        raise RuntimeError(f"nvidia-smi uscito con codice {out.returncode}")
    return parse_nvidia_smi(out.stdout)


def parse_rocm_smi(text: str) -> list[GpuMemory]:
    """Output di `rocm-smi --showproductname --showmeminfo vram`. La VRAM è in byte.
    PyTorch su ROCm si presenta come CUDA: il device resta `cuda:N`."""
    totals: dict[int, int] = {}
    used: dict[int, int] = {}
    names: dict[int, str] = {}
    for line in text.splitlines():
        found = re.search(r"GPU\[(\d+)\]", line)
        if not found:
            continue
        index = int(found.group(1))
        lowered = line.lower()
        if "card series" in lowered:
            names[index] = line[lowered.index("card series:") + len("card series:"):].strip()
        elif "vram total memory" in lowered and "used" not in lowered:
            totals[index] = _vram_mb(line)
        elif "vram total used memory" in lowered:
            used[index] = _vram_mb(line)
    if not totals:
        raise RuntimeError("rocm-smi non ha prodotto output")
    gpus = []
    for index, total in sorted(totals.items()):
        free = max(0, total - used.get(index, 0))
        gpus.append(GpuMemory(index, names.get(index, "AMD GPU"), free, total))
    return gpus


def _vram_mb(line: str) -> int:
    raw = line.rsplit(":", 1)[-1].strip().replace(",", "")
    return int(raw) // (1024 * 1024)


def query_amd_gpus() -> list[GpuMemory]:
    """Non crea un contesto HIP. Qualsiasi errore della sonda è sollevato."""
    try:
        out = subprocess.run(
            ["rocm-smi", "--showproductname", "--showmeminfo", "vram"],
            capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc
    if out.returncode != 0:
        raise RuntimeError(f"rocm-smi uscito con codice {out.returncode}")
    return parse_rocm_smi(out.stdout)


def parse_vm_stat(text: str, *, total_bytes: int) -> int:
    """MiB reclamabili su macOS: pagine free, inactive e speculative.
    `Pages purgeable` è un sottoinsieme di inactive e active: sommarlo conterebbe
    due volte la stessa memoria. La memoria unificata di un M2/M3 tiene in cache
    ciò che si può riprendere; contare solo le pagine free farebbe ripiegare sulla
    CPU a macchina scarica."""
    page = 4096
    counts: dict[str, int] = {}
    for line in text.splitlines():
        if "page size of" in line:
            page = int(line.split("page size of", 1)[1].split()[0])
            continue
        if ":" not in line:
            continue
        key, _, raw = line.partition(":")
        number = raw.strip().strip(".").split()
        if not number:
            continue
        try:
            counts[key.strip()] = int(number[0])
        except ValueError:
            continue
    pages = sum(counts.get(name, 0) for name in (
        "Pages free", "Pages inactive", "Pages speculative"))
    reclaimable = min(total_bytes, pages * page)
    return reclaimable // (1024 * 1024)


def query_apple_reclaimable_mb() -> int:
    if sys.platform != "darwin":
        raise RuntimeError("non è macOS")
    total = subprocess.run(
        ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=2, check=True)
    vm = subprocess.run(
        ["vm_stat"], capture_output=True, text=True, timeout=2, check=True)
    return parse_vm_stat(vm.stdout, total_bytes=int(total.stdout.strip()))


def detect_npu(*, platform: str | None = None, machine: str | None = None,
               exists=None) -> str | None:
    """Nome della NPU presente, o None. Non dice se un runtime sa eseguirci il modello:
    quello lo stabilisce core.npu_runtime, e senza runtime il job resta sulla CPU."""
    platform = platform if platform is not None else sys.platform
    machine = machine if machine is not None else platform_machine()
    exists = exists if exists is not None else __import__("os").path.exists
    if platform == "darwin" and machine == "arm64":
        return "Apple Neural Engine"
    if platform != "linux":
        # I path qui sotto sono sysfs e /dev di Linux. Su Windows esistono ma non
        # dicono nulla, e una sonda PowerShell appesa al primo encode non vale il rischio.
        # Lì la NPU si vede dal runtime (OpenVINO, QNN, Vitis AI), non dal filesystem.
        return None
    found = []
    for path, label in (
            ("/sys/module/intel_vpu", "Intel NPU"),
            ("/sys/module/amdxdna", "AMD Ryzen AI NPU"),
            ("/sys/module/qcom_q6v5_pas", "Qualcomm Hexagon"),
            ("/dev/accel/accel0", "NPU accel")):
        if exists(path):
            found.append(label)
    if not found:
        return None
    return ", ".join(found)


def _apple_only(label: str) -> bool:
    return "Apple" in label and not any(
        name in label for name in ("Intel", "AMD", "Qualcomm", "Hexagon"))


def platform_machine() -> str:
    return __import__("platform").machine()

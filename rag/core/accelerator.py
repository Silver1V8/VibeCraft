"""Scelta dell'acceleratore per l'embedding di un job, senza aprire un contesto
nel processo del server.

L'ordine in `auto` è quello che questo processo sa eseguire davvero:

1. CUDA. Vale per le RTX discrete e per i chip a memoria unificata NVIDIA (DGX
   Spark, RTX Spark, GB10, Grace): sono CUDA, non un backend a parte.
2. Metal (`mps`) su Apple Silicon. Il processo figlio dura un job e, uscendo,
   restituisce la memoria unificata.
3. NPU, se un runtime installato accanto al progetto compila l'encoder di bge-m3
   (OpenVINO su Intel, QNN su Hexagon, Vitis AI su Ryzen AI, Core ML sul Neural
   Engine). Le teste sparse e ColBERT restano sulla CPU del figlio. Senza quel
   runtime la NPU è solo nominata: non si finge di eseguirci il modello.
4. CPU.
"""
from __future__ import annotations

import csv
import subprocess
import sys
from dataclasses import dataclass

UNIFIED_NVIDIA_MARKERS = ("gb10", "grace", "spark", "n1x")
UNIFIED_FREE_FLOOR_MB = 1024


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


def decide(preference: str, *, cuda: bool, gpus: list[GpuMemory] | None,
           gpu_error: BaseException | None, mps: bool, apple_mb: int | None,
           apple_error: BaseException | None, npu: str | None,
           min_free_mb: int, npu_ready: bool = False, npu_name: str | None = None,
           npu_reason: str | None = None) -> EmbeddingDecision:
    """`preference` è auto, cuda, mps, npu o cpu. `gpus` è None se la sonda non è
    stata tentata. Un errore di sonda non è un successo con memoria zero."""
    if preference == "cpu":
        return EmbeddingDecision("cpu", None, "VIBECRAFT_REINDEX_DEVICE=cpu", None, None, npu)

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
                return EmbeddingDecision(
                    "cuda", f"cuda:{chosen.index}", None, chosen.free_mb, chosen.name, npu)
            cuda_reason = _cuda_refusal(gpus, min_free_mb)

    # CUDA presente ma rifiutato (VRAM sotto soglia, sonda muta) non si nasconde
    # dietro Metal o la NPU: in auto l'utente vedrebbe un successo su un altro
    # acceleratore mentre quello che ha la memoria è rotto.
    cuda_refused = bool(cuda and cuda_reason not in {None, "CUDA non disponibile"})

    mps_reason = None
    if preference in {"auto", "mps"} and not cuda_refused:
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
            return EmbeddingDecision("mps", "mps", None, apple_mb, "Apple Metal", npu)

    mps_refused = bool(mps and mps_reason not in {None, "Metal non disponibile"})
    if preference == "npu" or (preference == "auto" and not cuda_refused and not mps_refused):
        if npu_ready:
            name = npu_name or "NPU"
            return EmbeddingDecision("npu", "npu", None, None, name, npu or name)
        if preference == "npu":
            return EmbeddingDecision(
                "cpu", None, npu_reason or "runtime NPU assente", None, None, npu)

    if preference == "cuda":
        reason = cuda_reason
    elif preference == "mps":
        reason = mps_reason
    elif cuda_refused:
        reason = cuda_reason
    elif mps_refused:
        reason = mps_reason
    elif npu and not _apple_only(npu) and npu_reason:
        reason = f"{npu}: {npu_reason}"
    else:
        reason = cuda_reason or mps_reason or npu_reason
    return EmbeddingDecision("cpu", None, reason, None, None, npu)


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

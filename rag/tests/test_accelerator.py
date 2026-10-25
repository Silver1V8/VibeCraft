"""Scelta dell'acceleratore per l'embedding di un job. Nessuna sonda vera: le GPU,
la memoria Apple e la NPU arrivano come dati."""
import pytest

from core.accelerator import (
    BOTH_WEIGHTS_MB,
    GpuMemory,
    cpu_threads,
    decide,
    describe_placement,
    detect_npu,
    parse_nvidia_smi,
    parse_rocm_smi,
    parse_vm_stat,
)


def gpu(index=0, name="NVIDIA GeForce RTX 3070 Ti", free=8000, total=8192):
    return GpuMemory(index, name, free, total)


def choose(preference="auto", *, cuda=True, gpus=None, gpu_error=None, mps=False,
           apple_mb=None, apple_error=None, npu=None, min_free_mb=3072,
           npu_ready=False, npu_name=None, npu_reason=None, intel_ready=False,
           intel_name=None, intel_reason=None):
    if gpus is None and gpu_error is None and cuda and preference in {"auto", "cuda"}:
        gpus = [gpu()]
    return decide(preference, cuda=cuda, gpus=gpus, gpu_error=gpu_error, mps=mps,
                  apple_mb=apple_mb, apple_error=apple_error, npu=npu,
                  min_free_mb=min_free_mb, npu_ready=npu_ready, npu_name=npu_name,
                  npu_reason=npu_reason, intel_ready=intel_ready, intel_name=intel_name,
                  intel_reason=intel_reason)


def test_auto_picks_the_gpu_with_more_free_memory():
    decision = choose(gpus=[gpu(0, free=2000), gpu(1, "NVIDIA GeForce RTX 4090", 20000, 24564)])
    assert decision.device == "cuda" and decision.torch_device == "cuda:1"
    assert decision.accelerator == "NVIDIA GeForce RTX 4090"
    assert decision.memory_mb == 20000 and decision.reason is None


def test_low_discrete_vram_is_refused_with_the_old_reason():
    decision = choose(gpus=[gpu(free=1000)])
    assert decision.device == "cpu"
    assert decision.reason == "VRAM libera 1000 MB sotto la soglia di 3072 MB"


def test_cuda_missing_keeps_the_reason_the_existing_tests_match():
    decision = choose(cuda=False, gpus=None)
    assert decision.device == "cpu" and decision.reason == "CUDA non disponibile"


def test_cpu_preference_never_looks_at_an_accelerator():
    decision = choose("cpu", cuda=True, mps=True, apple_mb=16000,
                      npu="Apple Neural Engine")
    assert decision.device == "cpu"
    assert decision.reason == "VIBECRAFT_REINDEX_DEVICE=cpu"
    assert decision.npu == "Apple Neural Engine"


def test_probe_error_is_not_zero_free_memory():
    decision = choose(gpus=None, gpu_error=RuntimeError("nvidia-smi assente"))
    assert decision.device == "cpu"
    assert decision.reason == "VRAM non interrogabile: nvidia-smi assente"


def test_empty_probe_is_unreadable_not_a_quiet_cpu():
    decision = choose(gpus=[])
    assert "nvidia-smi non ha prodotto output" in decision.reason


def test_spark_unified_memory_uses_the_pool_not_the_mapped_free():
    spark = gpu(name="NVIDIA GB10 RTX Spark", free=1400, total=131072)
    decision = choose(gpus=[spark])
    assert decision.device == "cuda" and decision.torch_device == "cuda:0"
    assert decision.accelerator == "NVIDIA GB10 RTX Spark"


def test_spark_with_almost_no_free_memory_stays_on_cpu():
    spark = gpu(name="NVIDIA GB10", free=400, total=131072)
    decision = choose(gpus=[spark])
    assert decision.device == "cpu"
    assert "memoria unificata NVIDIA GB10" in decision.reason
    assert "1024" in decision.reason


def test_auto_falls_through_to_apple_metal_when_cuda_is_absent():
    decision = choose(cuda=False, gpus=None, mps=True, apple_mb=12000,
                      npu="Apple Neural Engine (non usata)")
    assert decision.device == "mps" and decision.torch_device == "mps"
    assert decision.accelerator == "Apple Metal" and decision.memory_mb == 12000
    assert decision.npu.startswith("Apple Neural Engine")


def test_auto_does_not_hide_a_cuda_refusal_behind_metal():
    decision = choose(gpus=[gpu(free=100)], mps=True, apple_mb=16000)
    assert decision.device == "mps" and decision.placement == "split"


def test_probe_error_does_not_fall_through_to_metal():
    decision = choose(gpus=None, gpu_error=RuntimeError("nvidia-smi assente"),
                      mps=True, apple_mb=16000)
    assert decision.device == "cpu"
    assert decision.reason == "VRAM non interrogabile: nvidia-smi assente"


def test_low_apple_memory_stays_on_cpu():
    decision = choose("mps", cuda=False, mps=True, apple_mb=1500)
    assert decision.device == "cpu"
    assert "memoria unificata Apple 1500 MB" in decision.reason


def test_forced_mps_without_metal_does_not_silently_use_cuda():
    decision = choose("mps", cuda=True, mps=False)
    assert decision.device == "cpu" and decision.reason == "Metal non disponibile"


def test_auto_uses_the_npu_when_cuda_and_metal_are_absent():
    decision = choose(cuda=False, gpus=None, npu="Intel NPU", npu_ready=True, npu_name="Intel NPU")
    assert decision.device == "npu" and decision.torch_device == "npu"
    assert decision.accelerator == "Intel NPU" and decision.reason is None


def test_metal_stays_ahead_of_the_npu_on_apple():
    decision = choose(cuda=False, gpus=None, mps=True, apple_mb=12000,
                      npu="Apple Neural Engine", npu_ready=True,
                      npu_name="Apple Neural Engine")
    assert decision.device == "mps"


def test_cuda_refusal_is_not_hidden_behind_the_npu():
    decision = choose(gpus=[gpu(free=100)], npu="Intel NPU", npu_ready=True, npu_name="Intel NPU")
    assert decision.device == "npu" and decision.placement == "split"


def test_intel_gpu_takes_the_embedding_when_nvidia_has_no_room():
    decision = choose(gpus=[gpu(free=100)], intel_ready=True, intel_name="Intel Arc Graphics",
                      npu_ready=True, npu_name="Intel NPU")
    assert decision.device == "intel" and decision.torch_device == "ov:GPU"
    assert decision.accelerator == "Intel Arc Graphics"
    assert decision.placement == "split"


def test_eight_gigabytes_split_the_weights_and_a_wide_gpu_keeps_them_together():
    small = choose(gpus=[gpu(free=5000, total=8192)])
    assert small.device == "cuda" and small.placement == "split"
    wide = choose(gpus=[gpu(name="NVIDIA GeForce RTX 4090", free=20000, total=24564)])
    assert wide.device == "cuda" and wide.placement == "gpu"
    assert wide.memory_mb == 20000
    assert BOTH_WEIGHTS_MB > 8192


def test_low_apple_memory_is_not_hidden_behind_the_npu():
    decision = choose(cuda=False, gpus=None, mps=True, apple_mb=1500,
                      npu="Apple Neural Engine", npu_ready=True, npu_name="Apple Neural Engine")
    assert decision.device == "cpu" and "memoria unificata Apple" in decision.reason


def test_forced_npu_ignores_a_free_gpu():
    decision = choose("npu", npu_ready=True, npu_name="Qualcomm Hexagon")
    assert decision.device == "npu" and decision.accelerator == "Qualcomm Hexagon"


def test_forced_npu_without_a_runtime_says_so():
    decision = choose("npu", npu="Intel NPU", npu_reason="runtime NPU assente")
    assert decision.device == "cpu" and decision.reason == "runtime NPU assente"


def test_detected_intel_npu_without_a_runtime_is_named_in_the_reason():
    decision = choose(cuda=False, gpus=None, npu="Intel NPU", npu_reason="runtime NPU assente")
    assert decision.device == "cpu"
    assert decision.reason == "Intel NPU: runtime NPU assente"


def test_parse_nvidia_smi_keeps_a_comma_inside_a_quoted_name():
    text = '0, "NVIDIA RTX, Laptop", 5000, 8192\n1, NVIDIA GB10, 2048, 65536\n'
    gpus = parse_nvidia_smi(text)
    assert gpus[0].name == "NVIDIA RTX, Laptop" and gpus[0].free_mb == 5000
    assert gpus[1].unified and gpus[1].total_mb == 65536


def test_parse_nvidia_smi_rejects_silence_and_garbage():
    with pytest.raises(RuntimeError):
        parse_nvidia_smi("No devices were found\n")
    with pytest.raises(RuntimeError):
        parse_nvidia_smi("")


def test_parse_rocm_smi_reads_bytes_and_keeps_the_series_name():
    text = "\n".join([
        "GPU[0]          : Card series:          AMD Radeon RX 7900 XTX",
        "GPU[0]          : VRAM Total Memory (B): 25753026560",
        "GPU[0]          : VRAM Total Used Memory (B): 1048576",
    ])
    gpus = parse_rocm_smi(text)
    assert gpus[0].name == "AMD Radeon RX 7900 XTX"
    assert gpus[0].total_mb == 25753026560 // (1024 * 1024)
    assert gpus[0].free_mb == gpus[0].total_mb - 1
    assert describe_placement("cuda", gpus, gpus[0].name)[0] == "gpu"


def test_cpu_threads_leave_one_core_and_cap_at_eight():
    assert cpu_threads(1) == 1
    assert cpu_threads(4) == 3
    assert cpu_threads(32) == 8


def test_parse_vm_stat_counts_reclaimable_pages_and_caps_at_total_ram():
    text = "\n".join([
        "Mach Virtual Memory Statistics: (page size of 16384 bytes)",
        "Pages free:                              1000.",
        "Pages inactive:                           2000.",
        "Pages speculative:                         100.",
        "Pages purgeable:                           400.",
        "Pages wired down:                        50000.",
    ])
    # 3100 pagine da 16 KiB = 49.609.375 byte, cioè 48 MiB interi.
    # Pages purgeable è già contato dentro inactive: sommarlo due volte gonfierebbe la stima.
    assert parse_vm_stat(text, total_bytes=64 * 1024 ** 3) == 48
    assert parse_vm_stat(text, total_bytes=8 * 1024 * 1024) == 8


def test_detect_npu_names_apple_and_does_not_claim_it_runs_the_model():
    label = detect_npu(platform="darwin", machine="arm64", exists=lambda path: False)
    assert label == "Apple Neural Engine"


def test_detect_npu_names_linux_devices_without_using_them():
    present = {"/sys/module/intel_vpu", "/dev/accel/accel0"}
    label = detect_npu(platform="linux", machine="x86_64", exists=present.__contains__)
    assert label == "Intel NPU, NPU accel"


def test_detect_npu_is_silent_when_nothing_is_there():
    assert detect_npu(platform="linux", machine="x86_64", exists=lambda path: False) is None
    assert detect_npu(platform="win32", machine="AMD64", exists=lambda path: True) is None

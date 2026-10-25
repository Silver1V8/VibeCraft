"""Scelta del runtime NPU. Nessun modello: i device OpenVINO e i provider ONNX
arrivano come dati."""
from core.npu_runtime import explain_npu_miss, probe_npu_runtime


def probe(label=None, *, ov=None, ort=None, platform="linux", machine="x86_64"):
    return probe_npu_runtime(label=label, openvino_devices=ov, ort_providers=ort,
                             platform=platform, machine=machine)


def test_openvino_npu_device_is_intel():
    target = probe("Intel NPU", ov=["CPU", "NPU"])
    assert target is not None and target.kind == "openvino" and target.label == "Intel NPU"


def test_openvino_npu_wins_over_another_provider_when_the_device_is_listed():
    target = probe(None, ov=["NPU.0"], ort=["QNNExecutionProvider"])
    assert target.kind == "openvino"


def test_qualcomm_uses_qnn_and_not_an_intel_runtime():
    target = probe("Qualcomm Hexagon", ov=["CPU", "NPU"], ort=["QNNExecutionProvider"])
    assert target.provider == "QNNExecutionProvider" and target.label == "Qualcomm Hexagon"


def test_amd_uses_vitis_and_an_intel_label_does_not():
    assert probe("AMD Ryzen AI NPU", ort=["VitisAIExecutionProvider"]).label == "AMD Ryzen AI NPU"
    assert probe("Intel NPU", ort=["VitisAIExecutionProvider"]) is None


def test_apple_neural_engine_is_coreml_only_on_arm_macos():
    ort = ["CoreMLExecutionProvider"]
    target = probe("Apple Neural Engine", ort=ort, platform="darwin", machine="arm64")
    assert target.label == "Apple Neural Engine"
    assert target.provider_options["MLComputeUnits"] == "CPUAndNeuralEngine"
    assert probe("Apple Neural Engine", ort=ort, platform="linux", machine="x86_64") is None


def test_intel_without_the_openvino_device_can_use_the_ort_provider():
    target = probe("Intel NPU", ov=["CPU"], ort=["OpenVINOExecutionProvider"])
    assert target.provider == "OpenVINOExecutionProvider"
    assert target.provider_options["device_type"] == "NPU"


def test_windows_without_a_sysfs_label_trusts_the_provider():
    target = probe(None, ort=["VitisAIExecutionProvider"], platform="win32", machine="AMD64")
    assert target.label == "AMD Ryzen AI NPU"


def test_nothing_installed_is_not_a_silent_npu():
    assert probe("Intel NPU") is None
    assert probe(None, platform="win32", machine="AMD64") is None


def test_miss_reasons_stay_specific():
    assert explain_npu_miss(label=None, openvino_devices=None, ort_providers=None,
                            openvino_error=None, ort_error=None) == "runtime NPU assente"
    assert explain_npu_miss(label="Intel NPU", openvino_devices=["CPU", "GPU"],
                            ort_providers=["CPUExecutionProvider"],
                            openvino_error=None, ort_error=None) == "OpenVINO non vede una NPU"
    assert explain_npu_miss(label="Qualcomm Hexagon", openvino_devices=None,
                            ort_providers=["CPUExecutionProvider"],
                            openvino_error=None, ort_error=None) == (
                                "runtime NPU assente per Qualcomm Hexagon")

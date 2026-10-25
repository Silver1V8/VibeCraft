"""Encoder di bge-m3 sulla NPU, per il solo processo figlio del reindex.

Il job chiede dense, sparse e ColBERT. Le due teste (un lineare ciascuna) restano
sulla CPU del figlio: pesano niente. Sulla NPU gira l'encoder, se un runtime
installato accanto a questo progetto lo compila davvero. I runtime non sono
dipendenze: senza, il caricamento fallisce e il job usa il modello CPU.

Runtime riconosciuti, e nient'altro:

- Intel NPU: OpenVINO (`compile_model(..., "NPU")`), oppure ONNX Runtime con
  `OpenVINOExecutionProvider` e `device_type=NPU`.
- Qualcomm Hexagon: ONNX Runtime `QNNExecutionProvider`.
- AMD Ryzen AI: ONNX Runtime `VitisAIExecutionProvider`.
- Apple Neural Engine: ONNX Runtime `CoreMLExecutionProvider` con
  `MLComputeUnits=CPUAndNeuralEngine`.

La NPU vuole una forma statica. Si compila il bucket più lungo che il runtime
accetta fra 2048, 1024, 512 e 256 token. Una sequenza più lunga di quel bucket
resta sull'encoder CPU del figlio: `max_length` dell'indicizzazione è 8192, e
far passare 8192 per una NPU sarebbe un fallimento, non un'ottimizzazione.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

NPU_BUCKETS = (2048, 1024, 512, 256)


@dataclass(frozen=True)
class NpuTarget:
    kind: str
    label: str
    provider: str | None = None
    provider_options: dict | None = None
    ov_device: str = "NPU"


@dataclass(frozen=True)
class NpuProbe:
    ready: bool
    name: str | None
    reason: str | None
    target: NpuTarget | None = None


def probe_npu_runtime(*, label: str | None, openvino_devices, ort_providers,
                      platform: str, machine: str) -> NpuTarget | None:
    """Sceglie un runtime che può eseguire l'encoder, o None. Non importa nulla:
    i device e i provider arrivano già letti. Un'etichetta generica (solo
    `/dev/accel`) accetta il primo runtime che vede davvero una NPU; un'etichetta
    che nomina un venditore non usa il runtime di un altro."""
    ov = list(openvino_devices or [])
    ort = list(ort_providers or [])
    has_ov = any(device == "NPU" or device.startswith("NPU.") for device in ov)
    generic = not _specific(label)
    intel = _wants(label, "Intel") or (generic and has_ov)
    qualcomm = _wants(label, "Qualcomm", "Hexagon") or (generic and "QNNExecutionProvider" in ort)
    amd = _wants(label, "AMD", "Ryzen") or (generic and "VitisAIExecutionProvider" in ort)
    apple = platform == "darwin" and machine == "arm64"

    if has_ov and intel and not _foreign(label, "Intel"):
        return NpuTarget("openvino", "Intel NPU")
    if "QNNExecutionProvider" in ort and qualcomm and not _foreign(label, "Qualcomm", "Hexagon"):
        return NpuTarget("onnx", "Qualcomm Hexagon", "QNNExecutionProvider", _qnn_options())
    if "VitisAIExecutionProvider" in ort and amd and not _foreign(label, "AMD", "Ryzen"):
        return NpuTarget("onnx", "AMD Ryzen AI NPU", "VitisAIExecutionProvider", {})
    if "CoreMLExecutionProvider" in ort and apple and not _foreign(label, "Apple"):
        return NpuTarget("onnx", "Apple Neural Engine", "CoreMLExecutionProvider",
                         {"MLComputeUnits": "CPUAndNeuralEngine"})
    if "OpenVINOExecutionProvider" in ort and _wants(label, "Intel") and not has_ov \
            and not _foreign(label, "Intel"):
        return NpuTarget("onnx", "Intel NPU", "OpenVINOExecutionProvider", {"device_type": "NPU"})
    return None


def explain_npu_miss(*, label: str | None, openvino_devices, ort_providers,
                     openvino_error: BaseException | None,
                     ort_error: BaseException | None) -> str:
    del openvino_error, ort_error
    ov = list(openvino_devices or [])
    ort = list(ort_providers or [])
    npu_provider = any(name in ort for name in (
        "QNNExecutionProvider", "VitisAIExecutionProvider",
        "CoreMLExecutionProvider", "OpenVINOExecutionProvider"))
    ov_without_npu = openvino_devices is not None and not any(
        device == "NPU" or str(device).startswith("NPU.") for device in ov)
    if ov_without_npu and not npu_provider:
        return "OpenVINO non vede una NPU"
    if label and _specific(label):
        return f"runtime NPU assente per {label}"
    return "runtime NPU assente"


def query_npu_runtime() -> NpuProbe:
    """Legge i runtime installati. Non compila un modello e non crea un contesto CUDA."""
    from core.accelerator import detect_npu, platform_machine

    try:
        label = detect_npu()
    except Exception:
        label = None
    ov_devices = None
    ov_error = None
    try:
        import openvino as ov
        ov_devices = [str(device) for device in ov.Core().available_devices]
    except Exception as exc:
        ov_error = exc
    providers = None
    ort_error = None
    try:
        import onnxruntime as ort
        providers = list(ort.get_available_providers())
    except Exception as exc:
        ort_error = exc
    target = probe_npu_runtime(
        label=label, openvino_devices=ov_devices, ort_providers=providers,
        platform=sys.platform, machine=platform_machine())
    if target is None:
        return NpuProbe(False, None, explain_npu_miss(
            label=label, openvino_devices=ov_devices, ort_providers=providers,
            openvino_error=ov_error, ort_error=ort_error))
    return NpuProbe(True, target.label, None, target)


def query_openvino_gpu() -> str | None:
    """Nome della GPU vista da OpenVINO, o None. Non compila un modello.
    Una GPU NVIDIA qui non conta: quella passa da CUDA."""
    import openvino as ov
    core = ov.Core()
    devices = [str(device) for device in core.available_devices]
    gpu = next((device for device in devices if device == "GPU" or device.startswith("GPU.")), None)
    if gpu is None:
        return None
    try:
        name = str(core.get_property(gpu, "FULL_DEVICE_NAME"))
    except Exception:
        name = "GPU OpenVINO"
    if "nvidia" in name.lower():
        return None
    return name


def load_openvino_bge_m3(model_name: str, ov_device: str = "GPU"):
    """Come la NPU, ma l'encoder è compilato sulla GPU OpenVINO (Arc, Xe, iGPU)."""
    from FlagEmbedding import BGEM3FlagModel

    embedder = BGEM3FlagModel(model_name, use_fp16=False, devices="cpu")
    encoder = embedder.model.model
    encoder.eval()
    target = NpuTarget("openvino", "GPU OpenVINO", ov_device=ov_device)
    bucket, session = _compile(target, encoder, model_name)
    pad_id = int(getattr(embedder.tokenizer, "pad_token_id", None) or 1)
    _patch(encoder, session, bucket, pad_id)
    print(f"OpenVINO {ov_device}: encoder fino a {bucket} token; "
          f"le sequenze più lunghe e le teste restano sulla CPU di questo processo",
          file=sys.stderr)
    return embedder


def load_npu_bge_m3(model_name: str):
    """bge-m3 con l'encoder sulla NPU. Solleva se il runtime non compila il modello:
    il processo figlio lo riporta e il job prosegue sulla CPU."""
    from FlagEmbedding import BGEM3FlagModel

    probe = query_npu_runtime()
    if not probe.ready or probe.target is None:
        raise RuntimeError(probe.reason or "runtime NPU assente")
    embedder = BGEM3FlagModel(model_name, use_fp16=False, devices="cpu")
    inference = embedder.model
    encoder = inference.model
    encoder.eval()
    bucket, session = _compile(probe.target, encoder, model_name)
    pad_id = int(getattr(embedder.tokenizer, "pad_token_id", None) or 1)
    _patch(encoder, session, bucket, pad_id)
    print(f"NPU {probe.target.label}: encoder fino a {bucket} token; "
          f"le sequenze più lunghe restano sulla CPU di questo processo",
          file=sys.stderr)
    return embedder


def _compile(target: NpuTarget, encoder, model_name: str):
    import torch

    class _Wrap(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = encoder

        def forward(self, input_ids, attention_mask):
            out = self.encoder(input_ids=input_ids, attention_mask=attention_mask,
                               return_dict=True)
            return out.last_hidden_state

    wrapper = _Wrap().eval()
    last = None
    for bucket in NPU_BUCKETS:
        try:
            session = _compile_bucket(target, wrapper, model_name, bucket)
        except Exception as exc:
            last = exc
            continue
        return bucket, session
    raise RuntimeError(f"compilazione dell'acceleratore fallita: {last}")


def _compile_bucket(target: NpuTarget, wrapper, model_name: str, bucket: int):
    import torch
    example = (torch.ones(1, bucket, dtype=torch.long), torch.ones(1, bucket, dtype=torch.long))
    if target.kind == "openvino":
        return _openvino_session(wrapper, example, model_name, bucket, target)
    if target.kind == "onnx":
        return _onnx_session(wrapper, example, target, model_name, bucket)
    raise RuntimeError(f"runtime NPU sconosciuto: {target.kind}")


def _openvino_session(wrapper, example, model_name: str, bucket: int, target: NpuTarget):
    import openvino as ov
    path = _cache_file(model_name, bucket, ".xml", target.ov_device)
    core = ov.Core()
    if path.exists():
        model = core.read_model(path)
    else:
        model = ov.convert_model(wrapper, example_input=example)
        path.parent.mkdir(parents=True, exist_ok=True)
        ov.save_model(model, str(path))
    compiled = core.compile_model(model, target.ov_device)

    def run(ids, mask):
        result = compiled([ids.numpy(), mask.numpy()])
        return _as_numpy(result[compiled.output(0)])

    return run


def _onnx_session(wrapper, example, target: NpuTarget, model_name: str, bucket: int):
    import torch
    path = _cache_file(model_name, bucket, ".onnx")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        export = dict(input_names=["input_ids", "attention_mask"],
                      output_names=["last_hidden_state"], opset_version=17)
        try:
            torch.onnx.export(wrapper, example, str(path), dynamo=False, **export)
        except TypeError:
            torch.onnx.export(wrapper, example, str(path), **export)
    import onnxruntime as ort
    options = dict(target.provider_options or {})
    session = ort.InferenceSession(
        str(path), providers=[target.provider], provider_options=[options])
    active = session.get_providers()
    if not active or active[0] != target.provider:
        raise RuntimeError(f"{target.provider} non è il provider attivo ({active})")

    def run(ids, mask):
        out = session.run(None, {
            "input_ids": ids.numpy().astype("int64"),
            "attention_mask": mask.numpy().astype("int64"),
        })
        return out[0]

    return run


def _patch(encoder, session, bucket: int, pad_id: int) -> None:
    original = encoder.forward

    def forward(*args, **kwargs):
        input_ids = kwargs.get("input_ids", args[0] if args else None)
        attention_mask = kwargs.get("attention_mask", args[1] if len(args) > 1 else None)
        if input_ids is None or attention_mask is None or int(input_ids.shape[-1]) > bucket:
            return original(*args, **kwargs)
        hidden = _run_rows(session, input_ids, attention_mask, bucket, pad_id)
        return _Hidden(hidden)

    encoder.forward = forward


def _run_rows(session, input_ids, attention_mask, bucket: int, pad_id: int):
    import torch
    ids = input_ids.detach().to("cpu")
    mask = attention_mask.detach().to("cpu")
    rows = []
    width = int(ids.shape[-1])
    for index in range(ids.shape[0]):
        row_ids = torch.full((1, bucket), pad_id, dtype=torch.long)
        row_mask = torch.zeros((1, bucket), dtype=torch.long)
        row_ids[0, :width] = ids[index].to(torch.long)
        row_mask[0, :width] = mask[index].to(torch.long)
        hidden = _as_numpy(session(row_ids, row_mask))
        rows.append(hidden[0, :width])
    return torch.from_numpy(__import__("numpy").stack(rows))


class _Hidden:
    def __init__(self, last_hidden_state):
        self.last_hidden_state = last_hidden_state


def _cache_file(model_name: str, bucket: int, suffix: str, device: str = "npu") -> Path:
    root = os.environ.get("VIBECRAFT_NPU_CACHE")
    base = Path(root) if root else Path.home() / ".cache" / "vibecraft" / "npu"
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in model_name)
    kind = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in device)
    return base / f"{safe}-{kind}-b{bucket}{suffix}"


def _as_numpy(value):
    import numpy as np
    if hasattr(value, "numpy"):
        return np.asarray(value.numpy())
    return np.asarray(value)


def _qnn_options() -> dict:
    backend = os.environ.get("QNN_BACKEND_PATH")
    return {"backend_path": backend} if backend else {}


def _specific(label: str | None) -> bool:
    return _wants(label, "Intel", "AMD", "Ryzen", "Qualcomm", "Hexagon", "Apple")


def _wants(label: str | None, *needles: str) -> bool:
    if not label:
        return False
    return any(needle in label for needle in needles)


def _foreign(label: str | None, *own: str) -> bool:
    """True se l'etichetta nomina un'altra NPU: non usare il runtime del vicino."""
    if not label:
        return False
    if any(needle in label for needle in own):
        return False
    return any(needle in label for needle in ("Intel", "AMD", "Ryzen", "Qualcomm", "Hexagon", "Apple"))

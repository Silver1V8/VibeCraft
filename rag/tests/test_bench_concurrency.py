"""Contratto del harness P0: solo POST /ask contro trasporti finti."""
import asyncio
import json
import os
from types import SimpleNamespace

import httpx
import pytest

from scripts import bench_concurrency as subject
import scripts.bench as bench


def test_ndjson_ttft_ignora_meta_e_decodifica_utf8_spezzato():
    """Rompere il filtro meta o il decoder incrementale deve far fallire questo test."""
    async def chunks():
        yield b'{"type":"meta","request_id":"r1"}\n{"type":"delta","text":"caf'
        yield b'\xc3'
        yield b'\xa8"}\n{"type":"result","value":{"status":"success"}}\n'

    clock = iter((1.0, 1.25, 2.0)).__next__
    result = asyncio.run(subject.consume_ndjson(chunks(), started=0.0, clock=clock))

    assert result["ttft_ms"] == pytest.approx(1250.0)
    assert result["terminal"] == "result"
    assert result["text_bytes"] == len("cafè".encode())


def test_ndjson_eof_senza_terminale_e_errore():
    async def chunks():
        yield b'{"type":"delta","text":"parziale"}\n'

    result = asyncio.run(subject.consume_ndjson(chunks(), started=0.0, clock=lambda: 1.0))

    assert result["terminal"] is None
    assert result["error"] == "EOF senza evento terminale"


@pytest.mark.parametrize("line", [b'[]\n', b'{"type":"unknown"}\n', b'{"type":"result"}\n'])
def test_ndjson_rifiuta_eventi_non_validi(line):
    """Un evento incompleto non può trasformarsi in una misura di successo."""
    async def chunks():
        yield line

    result = asyncio.run(subject.consume_ndjson(chunks(), started=0.0, clock=lambda: 1.0))

    assert result["terminal"] is None
    assert result["error"].startswith("evento NDJSON non valido")


def test_workload_rispetta_concorrenza_conta_errori_e_chiama_solo_ask():
    active = 0
    peak = 0
    calls = []

    async def handler(request):
        nonlocal active, peak
        calls.append((request.method, request.url.path, json.loads(request.content)))
        call_number = len(calls)
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        if call_number == 3:
            return httpx.Response(503, json={"detail": "finto"})
        return httpx.Response(200, json={"status": "success", "cached": False})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await subject.run_cell(
                client, "http://fake", ["q1", "q2"], concurrency=2, requests=4,
                warmup=0, response_mode="json", timeout=5,
            )

    result = asyncio.run(run())

    assert peak == 2
    assert len(result["rows"]) == 4
    assert result["summary"]["successes"] == 3
    assert result["summary"]["errors"] == 1
    assert {path for _, path, _ in calls} == {"/ask"}
    assert all(method == "POST" for method, _, _ in calls)
    assert all(payload.get("stream") is False for _, _, payload in calls)


def test_stream_salva_timestamp_e_metadati_del_payload():
    async def handler(request):
        return httpx.Response(200, content=(
            b'{"type":"meta","request_id":"r","index_version":"v","cached":false,'
            b'"retrieval_strategy":"hybrid","qdrant_collection":"c"}\n'
            b'{"type":"delta","text":"ok"}\n'
            b'{"type":"result","value":{"status":"success"}}\n'))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await subject.run_cell(client, "http://fake", ["q"], concurrency=1, requests=1,
                                          warmup=0, response_mode="stream", timeout=5)

    row = asyncio.run(run())["rows"][0]
    assert row["outcome"] == "success"
    assert row["application_status"] == "success"
    assert row["retrieval_strategy"] == "hybrid"
    assert row["qdrant_collection"] == "c"
    assert row["dispatch_monotonic"] <= row["first_text_monotonic"] <= row["finish_monotonic"]


def test_cancellazione_propagata_permette_di_fermare_il_benchmark():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(request):
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"status": "success"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            task = asyncio.create_task(subject._one(client, "http://fake", "q", "json", 5,
                                                    subject.time.perf_counter))
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(run())


def test_metadata_override_richiede_un_oggetto_json(tmp_path):
    good = tmp_path / "server.json"
    good.write_text('{"server_source_commit":"ea0cf91","model":"qwen"}', encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text('[]', encoding="utf-8")

    assert subject.load_metadata(good)["server_source_commit"] == "ea0cf91"
    with pytest.raises(ValueError, match="oggetto JSON"):
        subject.load_metadata(bad)


def test_timeout_totale_finito_diventa_errore_misurato():
    async def handler(request):
        await asyncio.Event().wait()

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await subject.run_cell(client, "http://fake", ["q"], concurrency=1, requests=1,
                                          warmup=0, response_mode="json", timeout=0.01)

    result = asyncio.run(run())
    assert result["summary"]["errors"] == 1
    assert result["rows"][0]["error"].startswith("timeout totale")


def test_json_non_oggetto_e_errore_misurato():
    async def handler(request):
        return httpx.Response(200, json=[])

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await subject.run_cell(client, "http://fake", ["q"], concurrency=1, requests=1,
                                          warmup=0, response_mode="json", timeout=1)

    result = asyncio.run(run())
    assert result["summary"]["errors"] == 1
    assert result["rows"][0]["error"] == "risposta JSON non oggetto"


@pytest.mark.parametrize("body", [{}, {"status": "error"}])
def test_status_applicativo_non_successo_non_e_successo(body):
    async def handler(request):
        return httpx.Response(200, json=body)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await subject.run_cell(client, "http://fake", ["q"], concurrency=1, requests=1,
                                          warmup=0, response_mode="json", timeout=1)

    result = asyncio.run(run())
    assert result["summary"]["successes"] == 0
    assert result["rows"][0]["error"].startswith("status applicativo")


@pytest.mark.parametrize("stream", [
    b'{"type":"delta","text":1}\n',
    b'{"type":"result","value":{"status":"success"}}\n{"type":"delta","text":"dopo"}\n',
    b'{"type":"result","value":{"status":"success"}}\n{"type":"result","value":{"status":"success"}}\n',
])
def test_ndjson_rifiuta_delta_non_testo_ed_eventi_dopo_terminale(stream):
    async def chunks():
        yield stream

    result = asyncio.run(subject.consume_ndjson(chunks(), started=0.0, clock=lambda: 1.0))
    assert result["error"].startswith("protocollo NDJSON")


def test_summary_conta_cancellazione_sintetica_fuori_da_percentili():
    rows = [
        {"outcome": "success", "ttft_ms": 1.0, "total_ms": 2.0},
        {"outcome": "cancelled", "ttft_ms": None, "total_ms": 3.0},
    ]
    summary = subject._summary(rows, 0.0, 1.0)
    assert summary["cancelled"] == 1
    assert summary["successes"] == 1
    assert summary["total_p50_ms"] == 2.0
    assert summary["cancellation_probes_not_run"] is True


def test_sampler_dichiara_aggregazione_pid_e_figli():
    async def run():
        stop = asyncio.Event()
        stop.set()
        return await subject.sample_memory_peaks(os.getpid(), None, stop)

    sample = asyncio.run(run())
    assert sample["api"]["aggregation"] == "pid_and_recursive_children"


def test_concurrency_args_rifiutano_timeout_non_finito():
    args = SimpleNamespace(concurrency=[1], requests=1, warmup=0, timeout=float("inf"))
    with pytest.raises(ValueError, match="finito"):
        bench.validate_concurrency_args(args)

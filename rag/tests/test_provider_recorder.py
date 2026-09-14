"""Il controllo positivo verifica il provider reale: senza, on/off potrebbe confrontare due percorsi inerti."""
import asyncio
import io
import json
from contextlib import nullcontext

import pytest

from core import llm


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("responses", [
    [{"response": "spec", "prompt_eval_count": 31, "eval_count": 7}],
    [{"response": ""}, {"response": "spec"}],
    [TimeoutError("simulated"), {"response": "spec"}],
    [{"response": ""}, {"response": ""}, {"response": ""}],
])
def test_recording_preserves_requests_results_and_retries(monkeypatch, tmp_path, asynchronous, responses):
    from eval.provider_recorder import record_ollama

    monkeypatch.setitem(llm.config, "llm_settings", {
        "active_provider": "ollama", "models": {"ollama": "fixture"},
    })
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)

    async def no_sleep(_):
        pass

    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)
    original = (llm._PROVIDERS["ollama"], llm._ollama_payload, llm._extract_ollama_text)
    outcomes = []
    for enabled in (False, True):
        pending = iter(responses)
        requests = []

        def respond(payload, timeout):
            requests.append((payload, timeout))
            response = next(pending)
            if isinstance(response, Exception):
                raise response
            return response

        def urlopen(request, timeout):
            return io.BytesIO(json.dumps(respond(json.loads(request.data), timeout)).encode())

        class Client:
            def __init__(self, timeout):
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def post(self, url, json):
                try:
                    body = respond(json, self.timeout)
                except TimeoutError as exc:
                    raise llm.httpx2.TimeoutException("simulated") from exc
                return llm.httpx2.Response(200, json=body, request=llm.httpx2.Request("POST", url))

        monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
        monkeypatch.setattr(llm.httpx2, "AsyncClient", Client)
        with record_ollama() if enabled else nullcontext() as recording:
            try:
                result = (asyncio.run(llm.agenerate("same prompt", purpose="propose", timeout=17))
                          if asynchronous else llm.generate("same prompt", purpose="propose", timeout=17))
                outcome = ("ok", result)
            except llm.LLMError as exc:
                outcome = ("error", str(exc))
        outcomes.append((requests, outcome))
        assert len(requests) == len(responses)  # Positive control: actual HTTP boundary reached.
        assert (llm._PROVIDERS["ollama"], llm._ollama_payload, llm._extract_ollama_text) == original
        if enabled:
            recording.save(tmp_path / "record.json")
            saved = json.loads((tmp_path / "record.json").read_text())
            assert saved["capture_complete"] is True
            assert len(saved["attempts"]) == len(responses)
            assert saved["attempts"][-1]["response"] == responses[-1]
            assert saved["attempts"][0]["request"] == requests[0][0]
    assert outcomes[0] == outcomes[1]


def test_capture_failure_never_retries_provider(monkeypatch):
    from eval.provider_recorder import record_ollama

    monkeypatch.setitem(llm.config, "llm_settings", {
        "active_provider": "ollama", "models": {"ollama": "fixture"},
    })
    calls = []

    def urlopen(request, timeout):
        calls.append(request.data)
        return io.BytesIO(b'{"response":"spec","prompt_eval_count":3,"eval_count":2}')

    def broken_capture(*args):
        raise OSError("capture unavailable")

    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    with record_ollama() as recording:
        monkeypatch.setattr(recording, "capture", broken_capture)
        assert llm.generate("same prompt", purpose="propose") == "spec"
    assert len(calls) == 1
    assert recording.capture_complete is False
    assert recording.errors

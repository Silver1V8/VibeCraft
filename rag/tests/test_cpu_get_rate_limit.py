"""Rate-limit sulle GET CPU-pesanti (R3): CpuGetRateLimiter + dependency HTTP."""
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from api import deps
from api.deps import CpuGetRateLimiter, require_cpu_get_rate_limit


def test_cpu_get_rate_limiter_ammette_fino_al_tetto_poi_rifiuta():
    limiter = CpuGetRateLimiter(limit=3, window_seconds=60.0)
    assert limiter.admit("127.0.0.1") is None
    assert limiter.admit("127.0.0.1") is None
    assert limiter.admit("127.0.0.1") is None
    retry = limiter.admit("127.0.0.1")
    assert retry is not None and retry >= 1.0
    # IP diverso ha il proprio budget.
    assert limiter.admit("10.0.0.2") is None


def test_cpu_get_rate_limiter_rifiuta_config_non_positiva():
    with pytest.raises(ValueError):
        CpuGetRateLimiter(limit=0, window_seconds=60.0)
    with pytest.raises(ValueError):
        CpuGetRateLimiter(limit=1, window_seconds=0.0)


def test_require_cpu_get_rate_limit_returns_429(monkeypatch):
    limiter = CpuGetRateLimiter(limit=1, window_seconds=60.0)
    monkeypatch.setattr(deps, "cpu_get_rate_limiter", limiter)

    app = FastAPI()

    @app.get("/probe", dependencies=[Depends(require_cpu_get_rate_limit)])
    def probe():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/probe").status_code == 200
    blocked = client.get("/probe")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert "Troppe richieste CPU" in blocked.json()["detail"]

from __future__ import annotations

import os
import pathlib
import sys

import httpx
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("AGENT_LLM_MODE", "offline")

GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:8080")
PROVIDER = os.getenv("PROVIDER_URL", "http://localhost:9100")


def _up(url: str) -> bool:
    try:
        return httpx.get(url, timeout=2.0).status_code < 500
    except Exception:
        return False


needs_gateway = pytest.mark.skipif(
    not (_up(f"{GATEWAY}/healthz") and _up(f"{PROVIDER}/healthz")),
    reason="Sentinel gateway and mock provider must be running (docker compose up)",
)


@pytest.fixture(scope="session", autouse=True)
def clean_stack():
    """Start from zero.

    Without this the suite fights the gateway's own controls: the demo user's
    rolling daily budget and the 5-minute duplicate-transaction fingerprint are
    both real, and both accumulate across runs. Resetting once per session is
    honest; disabling the controls would not be.
    """
    if not _up(f"{GATEWAY}/healthz"):
        yield
        return
    httpx.post(f"{GATEWAY}/v1/admin/dev/reset", timeout=15.0).raise_for_status()
    try:
        httpx.post(f"{PROVIDER}/_control/reset", timeout=10.0)
        httpx.post(
            f"{PROVIDER}/_control/behaviour", json={"behaviour": "success"}, timeout=10.0
        )
    except Exception:
        pass
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from agent_simulator.main import app

    with TestClient(app) as c:
        yield c

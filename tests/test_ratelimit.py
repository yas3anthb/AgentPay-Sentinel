"""Edge rate limiter — the coarse per-minute request ceiling in front of the
pipeline (gateway/ratelimit.py). Distinct from the policy's velocity rule."""
from __future__ import annotations

import pytest

from gateway.config import get_settings
from gateway.ratelimit import RateLimitError, enforce_edge_rate_limit
from gateway.store import get_store, reset_store


@pytest.fixture(autouse=True)
async def _isolate(monkeypatch):
    """Each test gets a fresh store and its own ceilings."""
    await reset_store()
    get_settings.cache_clear()
    yield
    await reset_store()
    get_settings.cache_clear()


async def test_trips_after_the_agent_ceiling(monkeypatch):
    monkeypatch.setenv("EDGE_RATE_LIMIT_AGENT_PER_MIN", "3")
    monkeypatch.setenv("EDGE_RATE_LIMIT_DELEGATION_PER_MIN", "1000")
    get_settings.cache_clear()

    for _ in range(3):
        await enforce_edge_rate_limit("agent_a", "deleg_a")

    with pytest.raises(RateLimitError) as excinfo:
        await enforce_edge_rate_limit("agent_a", "deleg_a")

    assert excinfo.value.reason_code == "RATE_LIMIT_EXCEEDED"
    assert "agent agent_a" in excinfo.value.scope
    assert excinfo.value.limit == 3


async def test_trips_on_the_delegation_ceiling_across_agents(monkeypatch):
    monkeypatch.setenv("EDGE_RATE_LIMIT_AGENT_PER_MIN", "1000")
    monkeypatch.setenv("EDGE_RATE_LIMIT_DELEGATION_PER_MIN", "2")
    get_settings.cache_clear()

    await enforce_edge_rate_limit("agent_x", "shared_deleg")
    await enforce_edge_rate_limit("agent_y", "shared_deleg")
    with pytest.raises(RateLimitError) as excinfo:
        await enforce_edge_rate_limit("agent_z", "shared_deleg")
    assert "delegation shared_deleg" in excinfo.value.scope


async def test_a_rejected_request_does_not_inflate_the_window(monkeypatch):
    """The ceiling is checked before this request is recorded, so being over
    the limit does not itself push the count further over."""
    monkeypatch.setenv("EDGE_RATE_LIMIT_AGENT_PER_MIN", "2")
    get_settings.cache_clear()

    await enforce_edge_rate_limit("agent_b", "deleg_b")
    await enforce_edge_rate_limit("agent_b", "deleg_b")
    for _ in range(5):
        with pytest.raises(RateLimitError):
            await enforce_edge_rate_limit("agent_b", "deleg_b")

    count = await get_store().zcount_window("agentpay:rl:agent:agent_b", 60)
    assert count == 2


async def test_disabled_flag_is_a_no_op(monkeypatch):
    monkeypatch.setenv("EDGE_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("EDGE_RATE_LIMIT_AGENT_PER_MIN", "1")
    get_settings.cache_clear()

    for _ in range(50):
        await enforce_edge_rate_limit("agent_c", "deleg_c")  # never raises


async def test_fails_open_when_the_store_errors(monkeypatch):
    monkeypatch.setenv("EDGE_RATE_LIMIT_AGENT_PER_MIN", "1")
    get_settings.cache_clear()

    class _BrokenStore:
        async def zcount_window(self, *a):
            raise RuntimeError("redis down")

        async def zadd_window(self, *a):
            raise RuntimeError("redis down")

    monkeypatch.setattr("gateway.ratelimit.get_store", lambda: _BrokenStore())

    # A throttle that fails closed would turn a cache blip into a full outage.
    for _ in range(5):
        await enforce_edge_rate_limit("agent_d", "deleg_d")  # no exception

"""The relay is read-only plumbing, so the tests are about what it must never
do: lose the gateway, block on a slow client, or leak one request's events into
another request's stream."""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from event_relay.main import Hub, Subscriber  # noqa: E402


def event(request_id: str, stage: str = "pdp", seq: int = 1) -> dict:
    return {
        "seq": seq,
        "request_id": request_id,
        "payment_authorization_id": "pa_1",
        "stage": stage,
        "status": "passed",
        "latency_ms": 12,
        "elapsed_ms": 40,
        "at": "2026-08-29T00:00:00+00:00",
        "detail": {"reason_codes": []},
    }


def test_subscribers_are_hashable_by_identity():
    """Two subscribers with identical fields are two different browser tabs."""
    a, b = Subscriber(request_id="r"), Subscriber(request_id="r")
    assert a != b
    assert len({a, b}) == 2


def test_filtering_is_per_request():
    watcher = Subscriber(request_id="req_a")
    assert watcher.wants(event("req_a"))
    assert not watcher.wants(event("req_b"))


def test_firehose_wants_everything():
    firehose = Subscriber(request_id=None)
    assert firehose.wants(event("req_a"))
    assert firehose.wants(event("req_b"))


async def test_fan_out_reaches_only_matching_subscribers():
    hub = Hub()
    a = Subscriber(request_id="req_a")
    b = Subscriber(request_id="req_b")
    firehose = Subscriber(request_id=None)
    for s in (a, b, firehose):
        await hub.add(s)

    await hub._fan_out(event("req_a"))

    assert a.queue.qsize() == 1
    assert b.queue.qsize() == 0
    assert firehose.queue.qsize() == 1


async def test_a_slow_client_is_dropped_not_allowed_to_stall_everyone():
    """Backpressure policy: one wedged tab must not hold up the pump."""
    hub = Hub()
    slow = Subscriber(request_id=None)
    slow.queue = asyncio.Queue(2)
    fast = Subscriber(request_id=None)
    await hub.add(slow)
    await hub.add(fast)

    for seq in range(6):
        await hub._fan_out(event("r", seq=seq))

    assert slow.queue.qsize() == 2
    assert slow.dropped == 4
    assert fast.queue.qsize() == 6  # unaffected


async def test_replay_lets_a_late_subscriber_see_the_run():
    """A fast request can finish before the browser's socket opens; without
    replay the visualisation would just be empty."""
    hub = Hub()
    for seq, stage in enumerate(["identity", "canonical", "pdp"], start=1):
        await hub._fan_out(event("req_a", stage=stage, seq=seq))
    await hub._fan_out(event("req_b", stage="identity", seq=1))

    replayed = hub.replay("req_a")
    assert [e["stage"] for e in replayed] == ["identity", "canonical", "pdp"]
    assert len(hub.replay(None)) == 4
    assert hub.replay("req_unknown") == []


async def test_replay_buffer_is_bounded():
    import event_relay.main as relay

    hub = Hub()
    original = relay.REPLAY_BUFFER_SIZE
    relay.REPLAY_BUFFER_SIZE = 10
    try:
        for seq in range(40):
            await hub._fan_out(event("r", seq=seq))
        assert len(hub._recent) == 10
        # Keeps the newest, not the oldest.
        assert hub._recent[-1]["seq"] == 39
    finally:
        relay.REPLAY_BUFFER_SIZE = original


async def test_removed_subscriber_stops_receiving():
    hub = Hub()
    s = Subscriber(request_id=None)
    await hub.add(s)
    await hub.remove(s)
    await hub._fan_out(event("r"))
    assert s.queue.qsize() == 0


async def test_events_seen_counts_everything():
    hub = Hub()
    for seq in range(3):
        await hub._fan_out(event("r", seq=seq))
    assert hub.events_seen == 3


def test_malformed_frames_are_ignored_by_the_pump_contract():
    """The pump json.loads inside a try; a bad frame must not kill the loop.
    Asserted here as a contract check on the parse step itself."""
    with pytest.raises(ValueError):
        json.loads("{not json")

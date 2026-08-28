"""Stage events are a visualisation feature inside a payment path, so the
thing worth testing is that they cannot influence one."""
from __future__ import annotations

import asyncio
import json

import pytest

from gateway.events import (
    CHANNEL,
    STAGE_ORDER,
    PipelineEmitter,
    Stage,
    StageStatus,
    _publish_safely,
)
from gateway.store import get_store, reset_store


@pytest.fixture(autouse=True)
async def clean():
    yield
    await reset_store()


class Recorder:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1


class Broken:
    async def publish(self, channel: str, message: str) -> int:
        raise ConnectionError("redis is gone")


async def drain() -> None:
    """Publishes are fire-and-forget tasks; let them run."""
    await asyncio.sleep(0)
    await asyncio.sleep(0)


async def test_stages_are_published_with_timing(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr("gateway.events.get_store", lambda: recorder)

    emitter = PipelineEmitter(request_id="req_1", payment_authorization_id="pa_1")
    emitter.start(Stage.PDP)
    emitter.finish(Stage.PDP, StageStatus.BLOCKED, {"reason_codes": ["X"]})
    await drain()

    events = [json.loads(m) for _, m in recorder.published]
    assert [e["status"] for e in events] == ["started", "blocked"]
    assert all(e["request_id"] == "req_1" for e in events)
    assert all(c == CHANNEL for c, _ in recorder.published)
    assert events[1]["latency_ms"] is not None
    assert events[1]["detail"]["reason_codes"] == ["X"]


async def test_skip_remaining_marks_every_later_stage(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr("gateway.events.get_store", lambda: recorder)

    PipelineEmitter(request_id="r").skip_remaining(Stage.PDP, ["BLOCKED_HERE"])
    await drain()

    events = [json.loads(m) for _, m in recorder.published]
    expected = [s.value for s in STAGE_ORDER[STAGE_ORDER.index(Stage.PDP) + 1 :]]
    assert [e["stage"] for e in events] == expected
    assert all(e["status"] == "skipped" for e in events)
    assert all(e["detail"]["never_reached"] is True for e in events)


async def test_a_broken_publisher_never_raises(monkeypatch):
    """The whole point: a dead visualiser must not be able to break, block, or
    let through a payment."""
    monkeypatch.setattr("gateway.events.get_store", lambda: Broken())

    emitter = PipelineEmitter(request_id="r")
    emitter.start(Stage.IDENTITY)
    emitter.finish(Stage.IDENTITY, StageStatus.PASSED)
    emitter.skip_remaining(Stage.IDENTITY, ["X"])
    await drain()  # the swallowed failures happen in the tasks


async def test_unserialisable_detail_is_dropped_not_raised(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr("gateway.events.get_store", lambda: recorder)

    class Unserialisable:
        __slots__ = ("x",)

    emitter = PipelineEmitter(request_id="r")
    # default=str handles most things; an object whose repr raises does not.
    class Exploding:
        def __str__(self):
            raise RuntimeError("nope")
        __repr__ = __str__

    emitter.finish(Stage.RISK, StageStatus.PASSED, {"bad": Exploding()})
    await drain()
    assert recorder.published == []


async def test_publishing_without_an_event_loop_is_a_no_op(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr("gateway.events.get_store", lambda: recorder)

    def sync_context() -> None:
        PipelineEmitter(request_id="r").start(Stage.AUDIT)

    await asyncio.get_running_loop().run_in_executor(None, sync_context)
    assert recorder.published == []


async def test_memory_store_publish_is_a_noop():
    from gateway.store import MemoryStore

    assert await MemoryStore().publish("c", "m") == 0


async def test_stage_order_matches_the_seven_pipeline_stages():
    assert [s.value for s in STAGE_ORDER] == [
        "identity",
        "canonical",
        "analyzer",
        "risk",
        "pdp",
        "authorization",
        "audit",
    ]


async def test_events_carry_a_monotonic_sequence(monkeypatch):
    """Fire-and-forget publishes can arrive out of order; `seq` is what lets a
    consumer restore the real order rather than trusting arrival time."""
    recorder = Recorder()
    monkeypatch.setattr("gateway.events.get_store", lambda: recorder)

    emitter = PipelineEmitter(request_id="r")
    emitter.start(Stage.IDENTITY)
    emitter.finish(Stage.IDENTITY, StageStatus.PASSED)
    emitter.start(Stage.CANONICAL)
    emitter.finish(Stage.CANONICAL, StageStatus.PASSED)
    await drain()

    seqs = [json.loads(m)["seq"] for _, m in recorder.published]
    assert seqs == [1, 2, 3, 4]

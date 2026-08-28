"""Pipeline event relay.

The gateway publishes one event per stage boundary to a Redis channel. This
service owns the WebSocket fan-out, so long-lived connections, backpressure and
per-client buffering stay out of the deny-by-default payment path.

It is strictly read-only. It subscribes, filters, and forwards. It cannot
authorize, block, or modify anything, and the gateway does not depend on it
being up.

    /ws/transactions/{request_id}   events for one request
    /ws/live                        every event (single-tenant demo firehose)

Correlation: a client that wants to watch a specific request generates its own
id and sends it as `X-Request-Id` when posting to the gateway. Agent-driven
runs go through the agent-simulator, which does not forward such a header, so
the UI watches `/ws/live` for those — noted rather than papered over.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("event_relay")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CHANNEL = os.getenv("PIPELINE_CHANNEL", "agentpay:pipeline")
# Bounded so one slow browser tab cannot grow memory without limit.
CLIENT_QUEUE_SIZE = int(os.getenv("CLIENT_QUEUE_SIZE", "256"))
# Late subscribers (the UI connects after a fast request finished) get recent
# history so the visualisation is not silently empty.
REPLAY_BUFFER_SIZE = int(os.getenv("REPLAY_BUFFER_SIZE", "500"))


# eq=False keeps identity hashing: two subscribers with identical fields are
# still two different browser tabs, and they live in a set.
@dataclass(eq=False)
class Subscriber:
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(CLIENT_QUEUE_SIZE))
    request_id: str | None = None  # None => firehose
    dropped: int = 0

    def wants(self, event: dict) -> bool:
        return self.request_id is None or event.get("request_id") == self.request_id


class Hub:
    def __init__(self) -> None:
        self._subscribers: set[Subscriber] = set()
        self._recent: list[dict] = []
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self.connected = False
        self.events_seen = 0

    async def start(self) -> None:
        self._task = asyncio.create_task(self._pump())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def add(self, subscriber: Subscriber) -> None:
        async with self._lock:
            self._subscribers.add(subscriber)

    async def remove(self, subscriber: Subscriber) -> None:
        async with self._lock:
            self._subscribers.discard(subscriber)

    def replay(self, request_id: str | None) -> list[dict]:
        if request_id is None:
            return list(self._recent)
        return [e for e in self._recent if e.get("request_id") == request_id]

    async def _pump(self) -> None:
        """Reconnecting Redis subscriber. Never gives up: the gateway keeps
        publishing whether or not we are listening."""
        backoff = 0.5
        while True:
            try:
                client = aioredis.from_url(REDIS_URL, decode_responses=True)
                pubsub = client.pubsub()
                await pubsub.subscribe(CHANNEL)
                self.connected = True
                backoff = 0.5
                log.info("subscribed to %s on %s", CHANNEL, REDIS_URL)

                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        event = json.loads(message["data"])
                    except (TypeError, ValueError):
                        continue
                    await self._fan_out(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.connected = False
                log.warning("redis subscription dropped (%s); retrying in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)

    async def _fan_out(self, event: dict) -> None:
        self.events_seen += 1
        self._recent.append(event)
        if len(self._recent) > REPLAY_BUFFER_SIZE:
            del self._recent[: len(self._recent) - REPLAY_BUFFER_SIZE]

        async with self._lock:
            targets = [s for s in self._subscribers if s.wants(event)]
        for subscriber in targets:
            try:
                subscriber.queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop for this client rather than stalling the pump for
                # everyone. The count is reported so the UI can say so.
                subscriber.dropped += 1


hub = Hub()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    await hub.start()
    yield
    await hub.stop()


app = FastAPI(
    title="AgentPay Pipeline Event Relay",
    version="1.0.0",
    description=(
        "Read-only WebSocket fan-out for gateway pipeline stage events. "
        "Cannot authorize, block, or modify anything."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    return {
        "ready": hub.connected,
        "redis_connected": hub.connected,
        "channel": CHANNEL,
        "events_seen": hub.events_seen,
        "subscribers": len(hub._subscribers),
        "buffered": len(hub._recent),
    }


async def _serve(websocket: WebSocket, request_id: str | None) -> None:
    await websocket.accept()
    subscriber = Subscriber(request_id=request_id)
    await hub.add(subscriber)
    try:
        await websocket.send_json(
            {
                "type": "hello",
                "request_id": request_id,
                "channel": CHANNEL,
                "redis_connected": hub.connected,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        # Anything that already happened for this id, so a client that connects
        # a moment late still sees the run rather than an empty scene.
        for event in hub.replay(request_id):
            await websocket.send_json({"type": "stage", "replayed": True, **event})

        while True:
            event = await subscriber.queue.get()
            await websocket.send_json({"type": "stage", "replayed": False, **event})
            if subscriber.dropped:
                await websocket.send_json(
                    {"type": "dropped", "count": subscriber.dropped}
                )
                subscriber.dropped = 0
    except WebSocketDisconnect:
        pass
    except Exception:
        log.debug("websocket closed unexpectedly", exc_info=True)
    finally:
        await hub.remove(subscriber)


@app.websocket("/ws/transactions/{request_id}")
async def watch_request(websocket: WebSocket, request_id: str) -> None:
    await _serve(websocket, request_id[:128])


@app.websocket("/ws/live")
async def watch_all(websocket: WebSocket) -> None:
    await _serve(websocket, None)

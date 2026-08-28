"""Pipeline stage events, published for live visualisation.

Why this lives in the gateway at all: honest per-stage timing can only be
measured where the stages actually run. Anything watching from outside has
nothing to read until the audit event is written at the end, and would have to
invent the intervals.

Three rules this module holds to, because it sits inside a deny-by-default
payment path:

  1. **It can never affect a decision.** Every publish is wrapped; a failure is
     logged and swallowed. A broken visualiser must not be able to block a
     payment, and must not be able to let one through either.
  2. **It never blocks the request.** Publishes are fire-and-forget tasks.
  3. **It invents no new data shape.** Stage payloads carry the same
     `reason_codes`, `signals` and risk objects the pipeline already produces.

Events are published to Redis; a separate relay service owns the WebSocket
fan-out, so long-lived connections stay out of this service.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from gateway.store import get_store

log = logging.getLogger("agentpay.events")

CHANNEL = "agentpay:pipeline"


class Stage(str, Enum):
    """The seven pipeline stages, in order."""

    IDENTITY = "identity"
    CANONICAL = "canonical"
    ANALYZER = "analyzer"
    RISK = "risk"
    PDP = "pdp"
    AUTHORIZATION = "authorization"
    AUDIT = "audit"


class StageStatus(str, Enum):
    STARTED = "started"
    PASSED = "passed"
    BLOCKED = "blocked"
    PAUSED = "paused"
    FAILED = "failed"
    SKIPPED = "skipped"


STAGE_ORDER: tuple[Stage, ...] = tuple(Stage)


@dataclass(slots=True)
class PipelineEmitter:
    """One per request. Times each stage and publishes as it goes."""

    request_id: str
    payment_authorization_id: str = ""
    _stage_started: dict[str, float] = field(default_factory=dict, repr=False)
    _t0: float = field(default_factory=time.perf_counter, repr=False)
    _seq: int = field(default=0, repr=False)

    def start(self, stage: Stage, detail: dict[str, Any] | None = None) -> None:
        self._stage_started[stage.value] = time.perf_counter()
        self._publish(stage, StageStatus.STARTED, detail, latency_ms=None)

    def finish(
        self,
        stage: Stage,
        status: StageStatus,
        detail: dict[str, Any] | None = None,
    ) -> None:
        started = self._stage_started.get(stage.value)
        latency = int((time.perf_counter() - started) * 1000) if started else None
        self._publish(stage, status, detail, latency_ms=latency)

    def skip_remaining(self, after: Stage, reason_codes: list[str]) -> None:
        """Mark the stages a blocked request never reached.

        The visualiser draws the beam stopping at the blocking node; these
        events are what make the later nodes stay dark, rather than the UI
        guessing which stages were skipped.
        """
        index = STAGE_ORDER.index(after)
        for stage in STAGE_ORDER[index + 1 :]:
            self._publish(
                stage,
                StageStatus.SKIPPED,
                {"reason_codes": reason_codes, "never_reached": True},
                latency_ms=None,
            )

    def _publish(
        self,
        stage: Stage,
        status: StageStatus,
        detail: dict[str, Any] | None,
        latency_ms: int | None,
    ) -> None:
        # Publishes are fire-and-forget tasks, so they can reach Redis out of
        # order. `seq` is assigned here, at the moment the stage boundary was
        # actually crossed, so a consumer can restore the true order instead of
        # inferring it from arrival time.
        self._seq += 1
        event = {
            "seq": self._seq,
            "request_id": self.request_id,
            "payment_authorization_id": self.payment_authorization_id,
            "stage": stage.value,
            "status": status.value,
            "latency_ms": latency_ms,
            "elapsed_ms": int((time.perf_counter() - self._t0) * 1000),
            "at": datetime.now(timezone.utc).isoformat(),
            "detail": detail or {},
        }
        try:
            payload = json.dumps(event, default=str)
        except Exception:
            # Deliberately broad. `default=str` invokes __str__ on whatever it
            # is handed, and that can raise anything at all — a narrower except
            # would let an exotic detail object escape into the payment path,
            # which is the one thing this module must never do.
            log.debug("stage event not serialisable; dropping", exc_info=True)
            return

        try:
            asyncio.get_running_loop().create_task(_publish_safely(payload))
        except RuntimeError:
            # No loop (sync context). Visualisation is not worth blocking for.
            log.debug("no running loop; dropping stage event")


async def _publish_safely(payload: str) -> None:
    try:
        await get_store().publish(CHANNEL, payload)
    except Exception:
        # Swallowed on purpose. A visualiser that cannot see events is a
        # degraded demo; a payment path that fails because of one is a bug.
        log.debug("failed to publish stage event", exc_info=True)

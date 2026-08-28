"""Structured agent transcript.

What goes in here: tool calls, tool results, gateway decisions, graph
transitions, and the framework's own step log. What does NOT go in here: raw
chain-of-thought. CrewAI and LangChain both expose step summaries; those are
what we record, so the frontend can animate a real run without the transcript
becoming a dumping ground for model internals.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class StepKind(str, Enum):
    GRAPH_TRANSITION = "graph_transition"
    AGENT_STEP = "agent_step"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    GATEWAY_DECISION = "gateway_decision"
    REVIEW = "review"
    ERROR = "error"
    NOTE = "note"


@dataclass(slots=True)
class Step:
    index: int
    at: str
    kind: StepKind
    actor: str
    name: str
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)
    latency_ms: int | None = None
    simulated: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        return data


@dataclass(slots=True)
class Transcript:
    run_id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex[:16]}")
    scenario: str = ""
    mode: str = "live"
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    steps: list[Step] = field(default_factory=list)
    _t0: float = field(default_factory=time.perf_counter, repr=False)

    @property
    def simulated(self) -> bool:
        return self.mode != "live"

    def add(
        self,
        kind: StepKind,
        actor: str,
        name: str,
        summary: str,
        detail: dict[str, Any] | None = None,
        latency_ms: int | None = None,
        simulated: bool | None = None,
    ) -> Step:
        step = Step(
            index=len(self.steps),
            at=datetime.now(timezone.utc).isoformat(),
            kind=kind,
            actor=actor,
            name=name,
            summary=summary,
            detail=detail or {},
            latency_ms=latency_ms,
            # Every step from a stubbed run is individually flagged, so a step
            # lifted out of context still says what it is. Steps that are real
            # regardless of mode — every Sentinel round-trip — pass False
            # explicitly: in offline mode the agent's reasoning is scripted but
            # the gateway decision is not, and conflating the two would be the
            # exact dishonesty this flag exists to prevent.
            simulated=self.simulated if simulated is None else simulated,
        )
        self.steps.append(step)
        return step

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)

    def tool_calls(self, name: str | None = None) -> list[Step]:
        return [
            s
            for s in self.steps
            if s.kind is StepKind.TOOL_CALL and (name is None or s.name == name)
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario": self.scenario,
            "mode": self.mode,
            "simulated": self.simulated,
            "started_at": self.started_at,
            "elapsed_ms": self.elapsed_ms(),
            "steps": [s.to_dict() for s in self.steps],
        }

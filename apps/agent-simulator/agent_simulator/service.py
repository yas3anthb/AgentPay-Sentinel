"""Run orchestration: kick off a graph run, pause it, resume it.

Kept separate from the HTTP layer so the same code is exercised by the tests
without going through FastAPI.
"""
from __future__ import annotations

import itertools
import logging
import threading
import uuid

import httpx
from dataclasses import dataclass, field
from typing import Any

from .config import Settings, SimulatorError, get_settings
from .graph import GraphDeps, ShopperState, build_graph
from .sentinel import SentinelClient
from .transcript import StepKind, Transcript

log = logging.getLogger("agent_simulator.service")

OFFLINE_WARNING = (
    "This run used AGENT_LLM_MODE=offline: the agent's reasoning is a "
    "deterministic script, not a language model. Every scripted step is marked "
    "simulated=true. The Sentinel calls are real — the decision, reason codes "
    "and audit hashes in this transcript came from the live gateway."
)


@dataclass
class Run:
    run_id: str
    scenario: str
    transcript: Transcript
    deps: GraphDeps
    graph: Any
    thread_id: str
    correlation_id: str = ""
    state: ShopperState = field(default_factory=dict)
    status: str = "created"
    provider_calls_before: int | None = None
    provider_calls_after: int | None = None

    def summary(self) -> dict[str, Any]:
        settings = self.deps.settings
        response = self.state.get("gateway_response", {}) or {}
        body: dict[str, Any] = {
            "run_id": self.run_id,
            "scenario": self.scenario,
            "mode": "offline-deterministic" if settings.offline() else "live",
            "simulated_reasoning": settings.offline(),
            "status": self.status,
            # The X-Request-Id every gateway call in this run carried. A live
            # frontend subscribes to this to follow the pipeline for this run
            # precisely rather than watching the firehose.
            "request_id": self.correlation_id or None,
            "decision": self.state.get("decision"),
            "reason_codes": self.state.get("reason_codes", []),
            "approval_request_id": self.state.get("approval_request_id") or None,
            "sentinel": {
                "payment_authorization_id": response.get("payment_authorization_id"),
                "state": response.get("state"),
                "policy_version": response.get("policy_version"),
                "risk": response.get("risk"),
                "audit_event_id": response.get("audit_event_id"),
                "audit_hash": response.get("audit_hash"),
                "provider_reference": response.get("provider_reference"),
                "message": response.get("message"),
            },
            "provider_calls": {
                "before": self.provider_calls_before,
                "after": self.provider_calls_after,
                "delta": (
                    None
                    if self.provider_calls_after is None or self.provider_calls_before is None
                    else self.provider_calls_after - self.provider_calls_before
                ),
            },
            "transcript": self.transcript.to_dict(),
        }
        if settings.offline():
            body["warning"] = OFFLINE_WARNING
        return body


_RUNS: dict[str, Run] = {}
_LOCK = threading.Lock()
_RUN_COUNTER = itertools.count()

# Quantities the demo cycles through for runs that do not specify one.
#
# Sentinel's transaction fingerprint covers (user, merchant, cart, amount,
# currency, 5-minute bucket), so buying the *identical* cart twice inside five
# minutes is a duplicate and is blocked. That is the control working. Rather
# than defeating it — by disabling the check, or padding the cart with a junk
# line item — each run buys a genuinely different quantity, which is what a
# second real purchase would look like anyway.
_DEMO_QUANTITIES = (2, 3, 1, 4)


def get_run(run_id: str) -> Run | None:
    with _LOCK:
        return _RUNS.get(run_id)


def _store(run: Run) -> None:
    with _LOCK:
        _RUNS[run.run_id] = run


def list_runs(limit: int = 25) -> list[dict[str, Any]]:
    with _LOCK:
        runs = list(_RUNS.values())[-limit:]
    return [
        {
            "run_id": r.run_id,
            "scenario": r.scenario,
            "status": r.status,
            "decision": r.state.get("decision"),
            "reason_codes": r.state.get("reason_codes", []),
        }
        for r in reversed(runs)
    ]


def reset_demo_state(settings: Settings | None = None) -> dict:
    """Clear the gateway's demo state so a run starts from zero.

    Delegates to the gateway's environment-guarded dev endpoint — the simulator
    has no privileged access of its own and this refuses to work in production.

    Deliberately NOT called automatically on every run: the daily budget and the
    duplicate fingerprint are real controls, and a demo that silently wipes them
    before each attempt would be hiding the two behaviours most worth showing.
    """
    settings = settings or get_settings()
    result: dict[str, Any] = {}
    admin_headers = {"X-Admin-Key": settings.admin_api_key, "X-Admin-Id": "agent-simulator"}
    with httpx.Client(timeout=15.0) as http:
        response = http.post(
            f"{settings.control_plane_url}/v1/admin/dev/reset", headers=admin_headers
        )
        response.raise_for_status()
        result["gateway"] = response.json()
        try:
            http.post(f"{settings.provider_url}/_control/reset")
            http.post(
                f"{settings.provider_url}/_control/behaviour",
                json={"behaviour": "success"},
            )
            result["provider"] = "reset"
        except httpx.HTTPError as exc:
            result["provider"] = f"unavailable: {exc}"
    with _LOCK:
        _RUNS.clear()
    return result


def start_run(
    *,
    scenario: str,
    instruction: str,
    budget: str,
    adversarial: bool,
    quantity: int | None = None,
    correlation_id: str | None = None,
    settings: Settings | None = None,
) -> Run:
    settings = settings or get_settings()
    correlation_id = (correlation_id or f"crew_{uuid.uuid4().hex[:16]}")[:128]
    transcript = Transcript(
        scenario=scenario, mode="offline-deterministic" if settings.offline() else "live"
    )
    client = SentinelClient(settings)

    try:
        client.seed()
    except Exception as exc:
        raise SimulatorError(
            "GATEWAY_SEED_FAILED",
            f"Could not reach the Sentinel gateway to register the demo agent: {exc}",
        ) from exc

    if settings.offline():
        transcript.add(
            StepKind.NOTE,
            actor="simulator",
            name="offline_mode",
            summary=OFFLINE_WARNING,
        )

    deps = GraphDeps(
        settings, transcript, client, adversarial=adversarial, correlation_id=correlation_id
    )
    run = Run(
        run_id=transcript.run_id,
        scenario=scenario,
        transcript=transcript,
        deps=deps,
        graph=build_graph(deps),
        thread_id=f"thread_{uuid.uuid4().hex[:12]}",
        correlation_id=correlation_id,
    )

    try:
        run.provider_calls_before = client.provider_call_count()
    except Exception:
        log.debug("mock provider not reachable; skipping call-count assertions")

    initial: ShopperState = {
        "instruction": instruction,
        "budget": budget,
        "adversarial": adversarial,
        "status": "running",
    }
    initial["requested_quantity"] = quantity or _DEMO_QUANTITIES[
        next(_RUN_COUNTER) % len(_DEMO_QUANTITIES)
    ]

    config = {"configurable": {"thread_id": run.thread_id}}
    run.state = run.graph.invoke(initial, config=config)
    run.status = run.state.get("status") or "running"

    # The graph interrupts before submit_approved_payment, so a run that lands
    # in REQUIRE_APPROVAL comes back here paused rather than looping.
    if run.state.get("decision") == "REQUIRE_APPROVAL":
        run.status = "awaiting_approval"

    try:
        run.provider_calls_after = client.provider_call_count()
    except Exception:
        pass

    _store(run)
    return run


def approve_and_resume(run_id: str) -> Run:
    """The external signal. Grants the approval at the gateway, then resumes
    the paused graph — the agent never polled for this."""
    run = get_run(run_id)
    if run is None:
        raise SimulatorError("UNKNOWN_RUN", f"no run {run_id}")
    if run.status != "awaiting_approval":
        raise SimulatorError(
            "RUN_NOT_AWAITING_APPROVAL",
            f"run {run_id} is {run.status}, not awaiting approval",
        )

    approval_request_id = run.state.get("approval_request_id")
    if not approval_request_id:
        raise SimulatorError("NO_APPROVAL_REQUEST", "the gateway did not return an approval id")

    granted = run.deps.client.grant_approval(approval_request_id)
    token = granted.get("approval_token")
    run.transcript.add(
        StepKind.NOTE,
        actor="human",
        name="approval_granted",
        summary=f"human approved {approval_request_id}",
        detail={"bound_to": granted.get("bound_to", {})},
        simulated=False,
    )

    config = {"configurable": {"thread_id": run.thread_id}}
    run.graph.update_state(config, {"approval_token": token})
    run.state = run.graph.invoke(None, config=config)
    run.status = run.state.get("status") or "completed"

    try:
        run.provider_calls_after = run.deps.client.provider_call_count()
    except Exception:
        pass

    _store(run)
    return run

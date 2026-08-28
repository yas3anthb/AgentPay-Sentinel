"""Agent simulator HTTP service.

Endpoints are synchronous on purpose. A crew kickoff and a LangGraph invoke are
both blocking, and CrewAI raises if kickoff() is called from inside a running
event loop, so these run in FastAPI's threadpool rather than on the loop.

Every endpoint returns the full structured transcript plus the final Sentinel
decision, so a frontend can animate a real run step by step.

Failure policy matches the gateway's: an error is returned as an error. There
is no path through this service that produces a successful-looking transcript
for a run that did not happen.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .config import SimulatorError, get_settings
from .sentinel import SentinelClient
from .service import approve_and_resume, get_run, list_runs, reset_demo_state, start_run
from .storefront import POISONED_PAGE, POISONED_PAGE_SHA256

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("agent_simulator")

# CrewAI otherwise prompts about trace collection on first run, which hangs a
# container. Opt out explicitly before anything imports the crew.
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

app = FastAPI(
    title="AgentPay Agent Simulator",
    version="1.0.0",
    description=(
        "A CrewAI shopping agent, orchestrated by LangGraph, whose only "
        "money-moving tool is the AgentPay Sentinel gateway."
    ),
)

# The Next.js frontend in apps/web talks to this service directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/simulate", tags=["simulation"])


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(
        default="Restock the office kitchen with coffee, keep it under $100.",
        max_length=2000,
    )
    budget: str = "100.00"
    quantity: int | None = Field(default=None, ge=1, le=50)


@app.exception_handler(SimulatorError)
async def simulator_error(request, exc: SimulatorError):
    return JSONResponse(
        status_code=502,
        content={"error": exc.code, "message": exc.message, "detail": exc.detail},
    )


@app.get("/healthz", tags=["ops"])
def healthz() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "llm_mode": settings.llm_mode,
        "agent_model": settings.agent_model,
        "agent_key_configured": bool(settings.agent_openai_api_key),
    }


@app.get("/readyz", tags=["ops"])
def readyz() -> dict:
    settings = get_settings()
    checks: dict[str, str] = {}
    try:
        health = SentinelClient(settings).health()
        checks["gateway"] = "ok" if health.get("ready") else "degraded"
    except Exception as exc:
        checks["gateway"] = f"error: {exc}"

    if settings.offline():
        checks["llm"] = "offline-deterministic (agent reasoning is scripted)"
    elif settings.agent_openai_api_key:
        checks["llm"] = "live"
    else:
        # Say so up front rather than at the first simulate call.
        checks["llm"] = "error: no AGENT_OPENAI_API_KEY; live runs will fail closed"

    return {
        "ready": all(not v.startswith("error") for v in checks.values()),
        "checks": checks,
        "llm_mode": settings.llm_mode,
    }


@router.post("/clean-purchase")
def clean_purchase(body: SimulationRequest) -> dict:
    """The honest path: the crew researches, builds a cart, the reviewer signs
    off, and Sentinel allows it."""
    run = start_run(
        scenario="clean-purchase",
        instruction=body.instruction,
        budget=body.budget,
        adversarial=False,
        quantity=body.quantity,
    )
    return run.summary()


@router.post("/adversarial")
def adversarial(body: SimulationRequest) -> dict:
    """The attack: the top search result is a poisoned product page.

    The injection reaches the shopper's context verbatim on purpose. Neither
    CrewAI nor LangChain strips it, and this service does not either — if it
    were filtered upstream the demo would prove nothing about the gateway. The
    block has to happen at Sentinel.
    """
    run = start_run(
        scenario="adversarial",
        instruction=body.instruction,
        budget=body.budget,
        adversarial=True,
        quantity=body.quantity,
    )
    summary = run.summary()
    summary["injection"] = {
        "payload_sha256": POISONED_PAGE_SHA256,
        "payload_chars": len(POISONED_PAGE),
        "reached_agent_unmodified": any(
            step.get("detail", {}).get("content_sha256") == POISONED_PAGE_SHA256
            for step in summary["transcript"]["steps"]
        ),
    }
    return summary


@router.post("/approval-flow")
def approval_flow(body: SimulationRequest) -> dict:
    """A purchase over the delegated approval threshold. Lands in
    REQUIRE_APPROVAL and pauses; resume it with POST /simulate/{run_id}/approve."""
    run = start_run(
        scenario="approval-flow",
        instruction=body.instruction,
        budget=body.budget,
        adversarial=False,
        # 8 x $21.25 = $170, over the demo policy's $150 approval threshold.
        quantity=body.quantity or 8,
    )
    return run.summary()


@router.post("/{run_id}/approve")
def approve(run_id: str) -> dict:
    """The external signal a paused run is waiting for."""
    return approve_and_resume(run_id).summary()


@router.post("/reset")
def reset() -> dict:
    """DEV ONLY. Clears the gateway's transactions, audit chain and replay
    caches so a demo starts from a known state. Refused in production by the
    gateway itself."""
    return {"reset": True, **reset_demo_state()}


@router.get("/runs")
def runs(limit: int = Query(default=25, le=100)) -> dict:
    return {"runs": list_runs(limit)}


@router.get("/runs/{run_id}")
def run_detail(run_id: str) -> dict:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown run")
    return run.summary()


app.include_router(router)

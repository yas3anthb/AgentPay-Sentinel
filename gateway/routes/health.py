from __future__ import annotations

import httpx
from fastapi import APIRouter

from gateway.config import get_settings
from gateway.store import get_store

router = APIRouter(tags=["ops"])


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "service": get_settings().service_name}


@router.get("/readyz")
async def readyz() -> dict:
    settings = get_settings()
    checks: dict[str, str] = {}
    try:
        await get_store().ping()
        checks["store"] = "ok"
    except Exception as exc:
        checks["store"] = f"error: {exc}"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.opa_url}/health")
            checks["opa"] = "ok" if r.status_code == 200 else f"http {r.status_code}"
    except Exception as exc:
        checks["opa"] = f"error: {exc}"
    ready = all(v == "ok" for v in checks.values())

    # Configured classifier mode — NOT a live probe (a healthcheck should not
    # spend an OpenAI call). The per-transaction truth still lives in each
    # decision's risk.signals.classifier_degraded: a "live" config can still
    # degrade on a single call that times out.
    if settings.classifier_offline:
        llm_mode = "offline"
    elif not settings.openai_api_key:
        llm_mode = "unconfigured"
    else:
        llm_mode = "live"

    return {
        "ready": ready,
        "checks": checks,
        "policy_version": settings.policy_version,
        "classifier": {
            "llm_mode": llm_mode,
            "fail_closed": not settings.allow_degraded_classifier,
            "deterministic_layers": ["rules", "similarity"],
            # When the LLM layer is down and the deterministic layers are clean,
            # route to human review instead of an outright decline.
            "degraded_routes_to_review": settings.degraded_classifier_requires_review,
        },
    }

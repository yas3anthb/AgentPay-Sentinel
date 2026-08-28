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
    return {"ready": ready, "checks": checks, "policy_version": settings.policy_version}

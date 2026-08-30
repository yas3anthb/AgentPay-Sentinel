"""AgentPay Sentinel — control plane.

Runs apart from the enforcement gateway, on its own port, holding the delegation
private key and gated by ``X-Admin-Key``. Registering agents, binding policies,
revoking delegations and minting delegation tokens all happen here; none of it
can move money, and the gateway can no longer do any of it.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from control_plane.audit import AdminAuditEvent  # noqa: F401 - registers the table
from control_plane.config import get_settings
from control_plane.routes import router
from control_plane.telegram import (  # noqa: F401 - registers the tables
    TelegramLink,
    TelegramLinkCode,
)
from gateway.db import dispose_db, init_db

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
log = logging.getLogger("agentpay.control_plane")

_RELAXED_ENVS = {"dev", "test", "local"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.admin_api_key and settings.environment.lower() not in _RELAXED_ENVS:
        raise RuntimeError(
            "ADMIN_API_KEY is not set. The control plane will not run wide open "
            f"outside dev/test (ENVIRONMENT={settings.environment!r})."
        )
    await init_db()
    log.info(
        "control plane up | env=%s issuer=%s", settings.environment, settings.jwt_issuer
    )
    yield
    await dispose_db()


app = FastAPI(
    title="AgentPay Sentinel — Control Plane",
    version="1.0.0",
    description=(
        "Registration, policy binding, delegation revocation and delegation-"
        "token issuance. Authenticated with X-Admin-Key. Cannot authorize a "
        "payment."
    ),
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/healthz", tags=["ops"])
async def healthz() -> dict:
    return {"status": "ok", "service": get_settings().service_name}

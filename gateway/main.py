"""AgentPay Sentinel — runtime policy-enforcement gateway.

Deny-by-default API firewall between an AI shopping agent and a payment
provider. Not a chatbot: the only thing that can move money is a typed
PaymentIntent that survived the full enforcement pipeline.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from gateway.config import get_settings
from gateway.db import dispose_db, init_db
from gateway.routes import admin, health, payments
from gateway.store import get_store, reset_store

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
log = logging.getLogger("agentpay")


_CLASSIFIER_RELAXED_ENVS = {"dev", "test", "local"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # ALLOW_DEGRADED_CLASSIFIER turns off the single control that keeps a
    # classifier outage from becoming an open door. It is a dev convenience and
    # nothing else: refuse to start with it set anywhere that is not explicitly
    # a development environment.
    if settings.allow_degraded_classifier and (
        settings.environment.lower() not in _CLASSIFIER_RELAXED_ENVS
    ):
        raise RuntimeError(
            "ALLOW_DEGRADED_CLASSIFIER is set but ENVIRONMENT="
            f"{settings.environment!r}. This flag disables fail-closed on the "
            "content classifier and must never be enabled outside dev/test."
        )

    await init_db()
    try:
        await get_store().ping()
    except Exception as exc:  # pragma: no cover - startup diagnostics
        log.warning("shared store unreachable at startup: %s", exc)
    log.info(
        "sentinel up | env=%s policy=%s opa=%s",
        settings.environment,
        settings.policy_version,
        settings.opa_url,
    )
    yield
    await reset_store()
    await dispose_db()


app = FastAPI(
    title="AgentPay Sentinel",
    version="1.1.0",
    description=(
        "Runtime policy-enforcement gateway for autonomous payment agents. "
        "Deny-by-default. OPA is the single Policy Decision Point; the risk "
        "engine emits signals only."
    ),
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(payments.router)
app.include_router(admin.router)


@app.exception_handler(Exception)
async def unhandled(request, exc: Exception):  # pragma: no cover - safety net
    """Fail closed: an unhandled error is never an implicit ALLOW."""
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "decision": "BLOCK",
            "reason_codes": ["INTERNAL_ERROR_FAIL_CLOSED"],
            "message": "request denied due to an internal error",
        },
    )

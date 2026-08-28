"""Mock payment provider.

Stands in for a real PSP. Two jobs beyond returning a status:

  1. It independently verifies the scoped authorization token and re-checks the
     binding (merchant, amount, currency, cart hash) against the charge body.
     A provider that trusts the request body is a provider that can be talked
     into charging a different amount.
  2. It counts every inbound call, so the adversarial demo can *prove* the
     provider was never contacted rather than asserting it.

Behaviour is configurable at runtime: success | decline | error | timeout.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

import jwt
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from gateway.tokens import verify_authorization_token

app = FastAPI(title="Mock Payment Provider", version="1.0.0")

Behaviour = Literal["success", "decline", "error", "timeout"]

STATE: dict = {
    "behaviour": os.getenv("PROVIDER_BEHAVIOUR", "success"),
    "timeout_delay_seconds": float(os.getenv("PROVIDER_TIMEOUT_DELAY", "30")),
    "charges": {},
    "consumed_jti": set(),
    "call_count": 0,
    "calls": [],
}


class ChargeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_authorization_id: str
    idempotency_key: str
    amount: str
    currency: str
    merchant_id: str
    cart_hash: str


class BehaviourRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    behaviour: Behaviour
    timeout_delay_seconds: float | None = None


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "behaviour": STATE["behaviour"]}


@app.post("/_control/behaviour")
async def set_behaviour(body: BehaviourRequest) -> dict:
    STATE["behaviour"] = body.behaviour
    if body.timeout_delay_seconds is not None:
        STATE["timeout_delay_seconds"] = body.timeout_delay_seconds
    return {"behaviour": STATE["behaviour"]}


@app.get("/_control/stats")
async def stats() -> dict:
    """The demo's proof-of-absence: if a blocked transaction ever reached the
    provider, it shows up here."""
    return {
        "call_count": STATE["call_count"],
        "charges": len(STATE["charges"]),
        "calls": STATE["calls"][-25:],
    }


@app.post("/_control/reset")
async def reset() -> dict:
    STATE["charges"] = {}
    STATE["consumed_jti"] = set()
    STATE["call_count"] = 0
    STATE["calls"] = []
    return {"reset": True}


@app.post("/charges")
async def create_charge(body: ChargeRequest, authorization: str | None = Header(default=None)):
    STATE["call_count"] += 1
    STATE["calls"].append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "payment_authorization_id": body.payment_authorization_id,
            "amount": body.amount,
            "merchant_id": body.merchant_id,
        }
    )

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing authorization token")

    try:
        claims = verify_authorization_token(authorization.split(" ", 1)[1].strip())
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="authorization token expired")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"invalid authorization token: {exc}")

    # Single use, enforced provider-side as well as gateway-side.
    jti = claims["jti"]
    if jti in STATE["consumed_jti"]:
        raise HTTPException(status_code=409, detail="authorization token already used")

    # The token is the authority, not the body. Any disagreement is an attack.
    mismatches = [
        field
        for field, token_value, body_value in (
            ("merchant_id", claims["merchant_id"], body.merchant_id),
            ("currency", claims["currency"], body.currency),
            ("cart_hash", claims["cart_hash"], body.cart_hash),
            (
                "payment_authorization_id",
                claims["payment_authorization_id"],
                body.payment_authorization_id,
            ),
        )
        if token_value != body_value
    ]
    if Decimal(claims["amount"]) != Decimal(body.amount):
        mismatches.append("amount")
    if mismatches:
        raise HTTPException(
            status_code=422,
            detail=f"charge does not match authorization token: {','.join(mismatches)}",
        )

    behaviour = STATE["behaviour"]

    if behaviour == "timeout":
        # Hang past the gateway's client timeout without ever recording a
        # charge — the genuinely ambiguous case reconciliation must resolve.
        await asyncio.sleep(STATE["timeout_delay_seconds"])
        return {"status": "confirmed", "provider_reference": f"ch_{uuid.uuid4().hex[:16]}"}

    if behaviour == "error":
        raise HTTPException(status_code=502, detail="provider upstream error")

    STATE["consumed_jti"].add(jti)

    if behaviour == "decline":
        STATE["charges"][body.payment_authorization_id] = {
            "status": "declined",
            "detail": "card declined",
            "provider_reference": None,
        }
        return {"status": "declined", "detail": "card declined"}

    reference = f"ch_{uuid.uuid4().hex[:16]}"
    STATE["charges"][body.payment_authorization_id] = {
        "status": "confirmed",
        "provider_reference": reference,
        "amount": body.amount,
        "currency": body.currency,
        "merchant_id": body.merchant_id,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    return {"status": "confirmed", "provider_reference": reference}


@app.get("/charges/{payment_authorization_id}")
async def get_charge(payment_authorization_id: str):
    """Reconciliation endpoint. 404 means 'never charged' — which is what makes
    it safe for the gateway to resolve an UNKNOWN to FAILED."""
    charge = STATE["charges"].get(payment_authorization_id)
    if charge is None:
        raise HTTPException(status_code=404, detail="no such charge")
    return charge

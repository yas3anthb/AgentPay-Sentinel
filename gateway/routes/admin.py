"""Control plane.

Separate from the runtime enforcement plane: this is where a human registers
agents, binds spending policies to delegations, and revokes delegations.
Nothing here can authorize a payment.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select

from gateway.audit import record_event
from gateway.config import get_settings
from gateway.db import session_scope
from gateway.identity import mint_delegation_token
from gateway.models import (
    AgentRegistration,
    AuditEvent,
    Merchant,
    SpendingPolicy,
    Transaction,
)
from gateway.payments import reset_replay_state
from gateway.schemas import Money
from gateway.store import REVOCATION_SET, get_store

router = APIRouter(prefix="/v1/admin", tags=["control-plane"])


class AgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: Annotated[str, Field(min_length=1, max_length=128)]
    owner_user_id: Annotated[str, Field(min_length=1, max_length=128)]
    display_name: str = ""
    allowed_scopes: list[str] = Field(default_factory=lambda: ["payments:authorize"])
    allowed_merchant_categories: list[str] = Field(default_factory=list)
    active: bool = True


class PolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delegation_id: Annotated[str, Field(min_length=1, max_length=128)]
    user_id: Annotated[str, Field(min_length=1, max_length=128)]
    agent_id: Annotated[str, Field(min_length=1, max_length=128)]
    policy_version: str = "v1.4.2"
    per_transaction_limit: Money
    daily_limit: Money
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] = "USD"
    allowed_merchants: list[str] = Field(default_factory=list)
    blocked_merchants: list[str] = Field(default_factory=list)
    require_verified_merchant: bool = True
    approval_threshold: Money
    max_transactions_per_hour: int = 10


class MerchantIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_id: Annotated[str, Field(min_length=1, max_length=128)]
    display_name: str = ""
    category: str = "general"
    verified: bool = False
    risk_score: Annotated[float, Field(ge=0.0, le=1.0)] = 0.2


class TokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    user_id: str
    delegation_id: str
    scopes: list[str] | None = None
    ttl_seconds: int = 3600


@router.put("/agents")
async def upsert_agent(body: AgentIn) -> dict:
    async with session_scope() as s:
        await s.merge(AgentRegistration(**body.model_dump()))
    return {"status": "ok", "agent_id": body.agent_id}


@router.put("/policies")
async def upsert_policy(body: PolicyIn) -> dict:
    data: dict[str, Any] = body.model_dump()
    async with session_scope() as s:
        await s.merge(SpendingPolicy(**data, revoked=False))
    # A re-issued policy implicitly un-revokes the delegation.
    await get_store().srem(REVOCATION_SET, body.delegation_id)
    return {"status": "ok", "delegation_id": body.delegation_id}


@router.put("/merchants")
async def upsert_merchant(body: MerchantIn) -> dict:
    async with session_scope() as s:
        await s.merge(Merchant(**body.model_dump()))
    return {"status": "ok", "merchant_id": body.merchant_id}


@router.post("/delegations/{delegation_id}/revoke")
async def revoke_delegation(delegation_id: str) -> dict:
    """Writes to the shared revocation set immediately. The delegation's JWT
    stays cryptographically valid until it expires; the PDP rejects it anyway.
    This is near-real-time revocation, bounded by the revocation-set write."""
    async with session_scope() as s:
        policy = await s.get(SpendingPolicy, delegation_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="unknown delegation")
        policy.revoked = True
    await get_store().sadd(REVOCATION_SET, delegation_id)
    await record_event(
        event_type="delegation.revoked",
        payload={"delegation_id": delegation_id},
        user_id=None,
    )
    return {"status": "revoked", "delegation_id": delegation_id, "propagation": "near-real-time"}


@router.get("/delegations/revoked")
async def list_revoked() -> dict:
    return {"revoked": sorted(await get_store().smembers(REVOCATION_SET))}


@router.post("/delegations/{delegation_id}/reinstate")
async def reinstate_delegation(delegation_id: str) -> dict:
    async with session_scope() as s:
        policy = await s.get(SpendingPolicy, delegation_id)
        if policy is not None:
            policy.revoked = False
    await get_store().srem(REVOCATION_SET, delegation_id)
    return {"status": "active", "delegation_id": delegation_id}


@router.post("/tokens")
async def issue_token(body: TokenIn) -> dict:
    """Demo issuer. A real control plane would sign in a KMS and require a
    human-authenticated session; this exists so the demo scripts have a token."""
    return {
        "token": mint_delegation_token(
            agent_id=body.agent_id,
            user_id=body.user_id,
            delegation_id=body.delegation_id,
            scopes=body.scopes,
            ttl_seconds=body.ttl_seconds,
        )
    }


@router.get("/policies/{delegation_id}")
async def get_policy(delegation_id: str) -> dict:
    async with session_scope() as s:
        policy = await s.get(SpendingPolicy, delegation_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="unknown delegation")
        return {
            k: (str(v) if isinstance(v, Decimal) else v)
            for k, v in policy.__dict__.items()
            if not k.startswith("_")
        }


@router.post("/dev/reset")
async def dev_reset() -> dict:
    """DEV ONLY. Clears transactions, the audit chain, and the replay caches so
    the demos start from a known state.

    Guarded on `environment`: in production the audit log is append-only and
    there is deliberately no endpoint that can truncate it.
    """
    settings = get_settings()
    if settings.environment.lower() in {"production", "prod"}:
        raise HTTPException(status_code=403, detail="reset is not available in production")

    async with session_scope() as s:
        await s.execute(delete(AuditEvent))
        await s.execute(delete(Transaction))

    await reset_replay_state()
    return {"reset": True, "environment": settings.environment}


@router.get("/merchants")
async def list_merchants() -> dict:
    async with session_scope() as s:
        rows = (await s.execute(select(Merchant))).scalars().all()
        return {
            "merchants": [
                {
                    "merchant_id": m.merchant_id,
                    "display_name": m.display_name,
                    "category": m.category,
                    "verified": m.verified,
                    "risk_score": m.risk_score,
                }
                for m in rows
            ]
        }

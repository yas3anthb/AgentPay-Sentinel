"""The control plane's HTTP surface.

This is the code that used to live on the gateway as ``gateway/routes/admin.py``.
It moved here, behind ``X-Admin-Key``, because registering agents, binding
spending policies, revoking delegations and — above all — *minting delegation
tokens* is a different trust domain from enforcing a payment. The gateway can
now run without the delegation private key at all.

Every mutating call is authenticated and written to the admin audit trail.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select

from control_plane.audit import record_admin_action
from control_plane.auth import AdminPrincipal, require_admin
from control_plane.config import get_settings
from control_plane.keys import sign_delegation_token
from gateway.db import session_scope
from gateway.models import (
    AgentRegistration,
    AuditEvent,
    Merchant,
    SpendingPolicy,
    Transaction,
)
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
async def upsert_agent(body: AgentIn, admin: AdminPrincipal = Depends(require_admin)) -> dict:
    async with session_scope() as s:
        await s.merge(AgentRegistration(**body.model_dump()))
    await record_admin_action(
        admin_id=admin.admin_id, action="agent.upsert", target=body.agent_id,
        payload=body.model_dump(),
    )
    return {"status": "ok", "agent_id": body.agent_id}


@router.put("/policies")
async def upsert_policy(body: PolicyIn, admin: AdminPrincipal = Depends(require_admin)) -> dict:
    data: dict[str, Any] = body.model_dump()
    async with session_scope() as s:
        await s.merge(SpendingPolicy(**data, revoked=False))
    await get_store().srem(REVOCATION_SET, body.delegation_id)
    await record_admin_action(
        admin_id=admin.admin_id, action="policy.upsert", target=body.delegation_id,
        payload={k: str(v) for k, v in data.items()},
    )
    return {"status": "ok", "delegation_id": body.delegation_id}


@router.put("/merchants")
async def upsert_merchant(body: MerchantIn, admin: AdminPrincipal = Depends(require_admin)) -> dict:
    async with session_scope() as s:
        await s.merge(Merchant(**body.model_dump()))
    await record_admin_action(
        admin_id=admin.admin_id, action="merchant.upsert", target=body.merchant_id,
        payload=body.model_dump(),
    )
    return {"status": "ok", "merchant_id": body.merchant_id}


@router.post("/delegations/{delegation_id}/revoke")
async def revoke_delegation(
    delegation_id: str, admin: AdminPrincipal = Depends(require_admin)
) -> dict:
    """Writes to the shared revocation set immediately. The delegation's JWT
    stays cryptographically valid until it expires; the gateway rejects it
    anyway. Near-real-time, bounded by the revocation-set write."""
    async with session_scope() as s:
        policy = await s.get(SpendingPolicy, delegation_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="unknown delegation")
        policy.revoked = True
    await get_store().sadd(REVOCATION_SET, delegation_id)
    await record_admin_action(
        admin_id=admin.admin_id, action="delegation.revoke", target=delegation_id,
    )
    return {"status": "revoked", "delegation_id": delegation_id, "propagation": "near-real-time"}


@router.get("/delegations/revoked")
async def list_revoked(admin: AdminPrincipal = Depends(require_admin)) -> dict:
    return {"revoked": sorted(await get_store().smembers(REVOCATION_SET))}


@router.post("/delegations/{delegation_id}/reinstate")
async def reinstate_delegation(
    delegation_id: str, admin: AdminPrincipal = Depends(require_admin)
) -> dict:
    async with session_scope() as s:
        policy = await s.get(SpendingPolicy, delegation_id)
        if policy is not None:
            policy.revoked = False
    await get_store().srem(REVOCATION_SET, delegation_id)
    await record_admin_action(
        admin_id=admin.admin_id, action="delegation.reinstate", target=delegation_id,
    )
    return {"status": "active", "delegation_id": delegation_id}


@router.post("/tokens")
async def issue_token(body: TokenIn, admin: AdminPrincipal = Depends(require_admin)) -> dict:
    """Mint a delegation token. This is the capability the whole service exists
    to hold apart from the gateway: only here is the delegation private key."""
    token = sign_delegation_token(
        agent_id=body.agent_id,
        user_id=body.user_id,
        delegation_id=body.delegation_id,
        scopes=body.scopes,
        ttl_seconds=body.ttl_seconds,
    )
    await record_admin_action(
        admin_id=admin.admin_id, action="token.mint", target=body.delegation_id,
        payload={"agent_id": body.agent_id, "user_id": body.user_id, "ttl": body.ttl_seconds},
    )
    return {"token": token}


@router.get("/policies/{delegation_id}")
async def get_policy(
    delegation_id: str, admin: AdminPrincipal = Depends(require_admin)
) -> dict:
    async with session_scope() as s:
        policy = await s.get(SpendingPolicy, delegation_id)
        if policy is None:
            raise HTTPException(status_code=404, detail="unknown delegation")
        return {
            k: (str(v) if isinstance(v, Decimal) else v)
            for k, v in policy.__dict__.items()
            if not k.startswith("_")
        }


@router.get("/merchants")
async def list_merchants(admin: AdminPrincipal = Depends(require_admin)) -> dict:
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


@router.get("/audit/admin")
async def list_admin_audit(
    limit: int = 100, admin: AdminPrincipal = Depends(require_admin)
) -> dict:
    from control_plane.audit import AdminAuditEvent

    async with session_scope() as s:
        rows = (
            await s.execute(
                select(AdminAuditEvent).order_by(AdminAuditEvent.seq.desc()).limit(min(limit, 500))
            )
        ).scalars().all()
    return {
        "events": [
            {
                "seq": r.seq,
                "at": r.at.isoformat(),
                "admin_id": r.admin_id,
                "action": r.action,
                "target": r.target,
                "payload_sha256": r.payload_sha256,
            }
            for r in rows
        ]
    }


# --- Telegram account linking (demo bot) ---------------------------------


class LinkCodeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: Annotated[str, Field(min_length=1, max_length=128)]


class LinkRedeemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[str, Field(min_length=4, max_length=32)]
    telegram_id: Annotated[str, Field(min_length=1, max_length=32)]


@router.post("/telegram/link-code")
async def telegram_link_code(
    body: LinkCodeIn, admin: AdminPrincipal = Depends(require_admin)
) -> dict:
    """Issue a one-time code the user copies into the bot. Called by the web
    console for the account it is logged in as."""
    from control_plane.telegram import issue_code

    out = await issue_code(body.user_id)
    await record_admin_action(
        admin_id=admin.admin_id, action="telegram.link_code", target=body.user_id,
    )
    return out


@router.post("/telegram/link")
async def telegram_link(
    body: LinkRedeemIn, admin: AdminPrincipal = Depends(require_admin)
) -> dict:
    """Redeem a code, binding a Telegram id to the account it was issued for.
    Called by the bot when a user sends it a code."""
    from control_plane.telegram import LinkError, redeem_code

    try:
        out = await redeem_code(body.code, body.telegram_id)
    except LinkError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)
    await record_admin_action(
        admin_id=admin.admin_id, action="telegram.link", target=out["user_id"],
        payload={"telegram_id_masked": out["telegram_id_masked"]},
    )
    return out


@router.get("/telegram/status/{user_id}")
async def telegram_status(
    user_id: str, admin: AdminPrincipal = Depends(require_admin)
) -> dict:
    from control_plane.telegram import status_for_user

    return await status_for_user(user_id)


@router.get("/telegram/whoami/{telegram_id}")
async def telegram_whoami(
    telegram_id: str, admin: AdminPrincipal = Depends(require_admin)
) -> dict:
    """Reverse lookup for the bot: which account is this Telegram id acting as."""
    from control_plane.telegram import resolve_user

    user_id = await resolve_user(telegram_id)
    return {"linked": user_id is not None, "user_id": user_id}


@router.delete("/telegram/link/{user_id}")
async def telegram_unlink(
    user_id: str, admin: AdminPrincipal = Depends(require_admin)
) -> dict:
    from control_plane.telegram import unlink_user

    out = await unlink_user(user_id)
    await record_admin_action(
        admin_id=admin.admin_id, action="telegram.unlink", target=user_id,
    )
    return out


@router.post("/dev/reset")
async def dev_reset(admin: AdminPrincipal = Depends(require_admin)) -> dict:
    """DEV ONLY. Clears transactions, the audit chain and the replay caches so
    the demos start from a known state. Guarded on `environment`: in production
    the audit log is append-only and nothing may truncate it."""
    from gateway.payments import reset_replay_state

    settings = get_settings()
    if settings.environment.lower() in {"production", "prod"}:
        raise HTTPException(status_code=403, detail="reset is not available in production")

    from control_plane.telegram import TelegramLink, TelegramLinkCode

    async with session_scope() as s:
        await s.execute(delete(AuditEvent))
        await s.execute(delete(Transaction))
        await s.execute(delete(TelegramLink))
        await s.execute(delete(TelegramLinkCode))
    await reset_replay_state()
    await record_admin_action(admin_id=admin.admin_id, action="dev.reset")
    return {"reset": True, "environment": settings.environment}

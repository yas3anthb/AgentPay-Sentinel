"""Immutable audit log with a SHA-256 hash chain.

    H_0 = 64 zeroes
    H_n = SHA256(canonical_json(event_n) || H_{n-1})

Honest claim: this is **tamper-evident within the current trust boundary**, not
tamper-proof. Anyone with full write access to the database could recompute the
whole chain from H_0. Publishing the head hash to an independent store (see
`publish_checkpoint`) is what raises the bar to compromising two systems.

Every decision is recorded — ALLOWs and REQUIRE_APPROVALs as well as BLOCKs —
so the log is a complete record rather than an incident list.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from gateway.config import get_settings
from gateway.db import session_scope
from gateway.models import AuditEvent
from gateway.store import DistributedLock

log = logging.getLogger("agentpay.audit")

GENESIS_HASH = "0" * 64


def canonical_timestamp(dt: datetime) -> str:
    """Timestamps must hash identically on the way in and the way out.

    Postgres hands back tz-aware UTC; SQLite hands back a naive datetime for the
    same stored value. Normalising both to explicit UTC here is what keeps
    verification from raising a false tamper alarm on a round-trip — and a
    tamper-evident log that cries wolf is worse than none.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)


def compute_hash(event_body: dict[str, Any], prev_hash: str) -> str:
    return hashlib.sha256((_canonical(event_body) + prev_hash).encode()).hexdigest()


def _body(
    *,
    event_id: str,
    event_type: str,
    created_at: datetime,
    payment_authorization_id: str | None,
    user_id: str | None,
    agent_id: str | None,
    decision: str | None,
    reason_codes: list[str],
    risk: dict,
    policy_version: str | None,
    payload: dict,
) -> dict[str, Any]:
    """The exact field set that is hashed. Order-independent (sorted keys)."""
    return {
        "event_id": event_id,
        "event_type": event_type,
        "created_at": canonical_timestamp(created_at),
        "payment_authorization_id": payment_authorization_id,
        "user_id": user_id,
        "agent_id": agent_id,
        "decision": decision,
        "reason_codes": reason_codes,
        "risk": risk,
        "policy_version": policy_version,
        "payload": payload,
    }


async def record_event(
    *,
    event_type: str,
    payload: dict | None = None,
    payment_authorization_id: str | None = None,
    user_id: str | None = None,
    agent_id: str | None = None,
    decision: str | None = None,
    reason_codes: list[str] | None = None,
    risk: dict | None = None,
    policy_version: str | None = None,
) -> tuple[str, str]:
    """Append one event. Returns (event_id, event_hash).

    The chain head is read and extended under a distributed lock so two
    concurrent requests cannot both build on the same predecessor.
    """
    event_id = f"evt_{uuid.uuid4().hex}"
    created_at = datetime.now(timezone.utc)
    reason_codes = reason_codes or []
    risk = risk or {}
    payload = payload or {}
    policy_version = policy_version or get_settings().policy_version

    async with DistributedLock("audit_chain", ttl=15):
        async with session_scope() as s:
            prev = (
                await s.execute(
                    select(AuditEvent.event_hash).order_by(AuditEvent.seq.desc()).limit(1)
                )
            ).scalar_one_or_none()
            prev_hash = prev or GENESIS_HASH

            body = _body(
                event_id=event_id,
                event_type=event_type,
                created_at=created_at,
                payment_authorization_id=payment_authorization_id,
                user_id=user_id,
                agent_id=agent_id,
                decision=decision,
                reason_codes=reason_codes,
                risk=risk,
                policy_version=policy_version,
                payload=payload,
            )
            event_hash = compute_hash(body, prev_hash)

            s.add(
                AuditEvent(
                    event_id=event_id,
                    event_type=event_type,
                    payment_authorization_id=payment_authorization_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    decision=decision,
                    reason_codes=reason_codes,
                    risk=risk,
                    policy_version=policy_version,
                    payload=payload,
                    prev_hash=prev_hash,
                    event_hash=event_hash,
                    created_at=created_at,
                )
            )
    log.info("audit %s %s -> %s", event_type, decision or "-", event_hash[:12])
    return event_id, event_hash


async def verify_chain(limit: int | None = None) -> dict:
    """Recompute every link. Reports the first broken seq, if any."""
    async with session_scope() as s:
        stmt = select(AuditEvent).order_by(AuditEvent.seq.asc())
        if limit:
            stmt = stmt.limit(limit)
        events = (await s.execute(stmt)).scalars().all()

    prev_hash = GENESIS_HASH
    for e in events:
        body = _body(
            event_id=e.event_id,
            event_type=e.event_type,
            created_at=e.created_at,
            payment_authorization_id=e.payment_authorization_id,
            user_id=e.user_id,
            agent_id=e.agent_id,
            decision=e.decision,
            reason_codes=e.reason_codes,
            risk=e.risk,
            policy_version=e.policy_version,
            payload=e.payload,
        )
        expected = compute_hash(body, prev_hash)
        if e.prev_hash != prev_hash or e.event_hash != expected:
            return {
                "valid": False,
                "events_checked": len(events),
                "broken_at_seq": e.seq,
                "broken_event_id": e.event_id,
                "expected_hash": expected,
                "stored_hash": e.event_hash,
                "claim": "tamper-evident within the current trust boundary",
            }
        prev_hash = e.event_hash

    return {
        "valid": True,
        "events_checked": len(events),
        "head_hash": prev_hash,
        "claim": "tamper-evident within the current trust boundary",
    }


async def chain_head() -> dict:
    async with session_scope() as s:
        count = (await s.execute(select(func.count(AuditEvent.seq)))).scalar_one()
        head = (
            await s.execute(
                select(AuditEvent.event_hash).order_by(AuditEvent.seq.desc()).limit(1)
            )
        ).scalar_one_or_none()
    return {"events": count, "head_hash": head or GENESIS_HASH}


# The chain head is anchored in an independent append-only store by
# `gateway.checkpoint.anchor_checkpoint`, called from the audit-verify route.
# Kept in a separate module because that store has its own engine and
# credentials and must never share a transaction with this one.

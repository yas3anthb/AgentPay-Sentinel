"""Per-admin audit trail for the control plane.

Distinct from the gateway's hash-chained decision log. This records *who*
changed the registry and *what* they changed — every agent upsert, policy
bind, revocation, and token mint — so control-plane actions are attributable.
Append-only: there is no update or delete path.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from gateway.db import session_scope
from gateway.models import Base

log = logging.getLogger("agentpay.control_plane.audit")


class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_events"

    seq: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    admin_id: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str] = mapped_column(String(256), default="")
    # A digest, not the body: the payload can carry limits and merchant lists,
    # and this table is for attribution, not for re-deriving state.
    payload_sha256: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str] = mapped_column(Text, default="")


def _digest(payload: dict) -> str:
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


async def record_admin_action(
    *, admin_id: str, action: str, target: str = "", payload: dict | None = None, detail: str = ""
) -> None:
    try:
        async with session_scope() as s:
            s.add(
                AdminAuditEvent(
                    admin_id=admin_id,
                    action=action,
                    target=target,
                    payload_sha256=_digest(payload or {}),
                    detail=detail[:2000],
                )
            )
    except Exception:  # attribution is important but must not fail the operation
        log.exception("failed to write admin audit event for %s/%s", admin_id, action)

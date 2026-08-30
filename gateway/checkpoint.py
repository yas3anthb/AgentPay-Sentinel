"""Independent anchor for the audit chain head.

The main audit log (`gateway/audit.py`) is tamper-*evident*: `verify_chain`
recomputes every link and names the first break. Its honest limitation is that
anyone with full write access to the gateway's database could rewrite the whole
chain from genesis so that `verify_chain` passes again.

This module closes that gap by periodically writing the chain head hash to a
**separate append-only store with its own credentials** — a second database the
gateway connects to only to append checkpoints and read them back. To forge the
history now, an attacker has to compromise *two* systems with different
credentials and rewrite both consistently.

If `CHECKPOINT_DATABASE_URL` is empty the module is inert and
`anchor_checkpoint` returns the same "not configured" shape the old
`publish_checkpoint` hook did — the demo still runs, it just makes the weaker
claim.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, String, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gateway.config import get_settings

log = logging.getLogger("agentpay.checkpoint")

NOT_CONFIGURED_NOTE = (
    "No external anchor configured. Until the head is published to an "
    "independent store, forging the history requires compromising one system, "
    "not two."
)


class CheckpointBase(DeclarativeBase):
    pass


class AuditCheckpoint(CheckpointBase):
    """One anchored chain head. Append-only: this module never updates or
    deletes a row, and the table has no code path that does."""

    __tablename__ = "audit_checkpoints"

    seq: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    chain_events: Mapped[int] = mapped_column(Integer)
    head_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


_engine = None
_sessionmaker: async_sessionmaker | None = None


def is_configured() -> bool:
    return bool(get_settings().checkpoint_database_url)


def _get_sessionmaker() -> async_sessionmaker:
    global _engine, _sessionmaker
    if _sessionmaker is None:
        url = get_settings().checkpoint_database_url
        kwargs: dict = {"echo": False, "future": True}
        if not url.startswith("sqlite"):
            kwargs.update(pool_pre_ping=True, pool_size=5, max_overflow=5)
        _engine = create_async_engine(url, **kwargs)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessionmaker


async def init_checkpoint_db() -> None:
    if not is_configured():
        return
    global _engine
    _get_sessionmaker()
    async with _engine.begin() as conn:
        await conn.run_sync(CheckpointBase.metadata.create_all)
    log.info("checkpoint store ready")


async def dispose_checkpoint_db() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def anchor_checkpoint(head_hash: str, chain_events: int) -> dict:
    """Append the current chain head to the independent store. No-op (with an
    honest note) when no checkpoint DB is configured."""
    if not is_configured():
        return {"anchored": False, "head_hash": head_hash, "note": NOT_CONFIGURED_NOTE}

    try:
        sm = _get_sessionmaker()
        async with sm() as s:
            row = AuditCheckpoint(head_hash=head_hash, chain_events=chain_events)
            s.add(row)
            await s.commit()
            await s.refresh(row)
        return {
            "anchored": True,
            "store": "independent-append-only-db",
            "checkpoint_seq": row.seq,
            "chain_events": chain_events,
            "head_hash": head_hash,
            "at": row.created_at.isoformat(),
        }
    except Exception as exc:
        # Anchoring is out of the payment path: a checkpoint-store outage must
        # never turn into a failed audit verification or a blocked payment.
        log.error("could not anchor checkpoint: %s", exc)
        return {"anchored": False, "head_hash": head_hash, "error": type(exc).__name__}


async def latest_checkpoint() -> dict | None:
    if not is_configured():
        return None
    sm = _get_sessionmaker()
    async with sm() as s:
        row = (
            await s.execute(select(AuditCheckpoint).order_by(AuditCheckpoint.seq.desc()).limit(1))
        ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "checkpoint_seq": row.seq,
        "head_hash": row.head_hash,
        "chain_events": row.chain_events,
        "at": row.created_at.isoformat(),
    }


async def verify_against_checkpoints() -> dict:
    """Recompute the gateway DB's chain head *as of the last anchored event
    count* and compare it to the independently anchored head.

    Checking the prefix (not the whole current chain) means legitimately
    appending new audit events after a checkpoint is not a false alarm, while a
    consistent full-chain rewrite from genesis — which `verify_chain` alone
    would still call valid — shows up here as a head mismatch."""
    if not is_configured():
        return {"configured": False, "note": NOT_CONFIGURED_NOTE}

    latest = await latest_checkpoint()
    if latest is None:
        return {"configured": True, "checkpoints": 0, "note": "no checkpoint anchored yet"}

    # Lazy import: audit.py has no import-time dependency on this module.
    from gateway.audit import verify_chain

    prefix = await verify_chain(limit=latest["chain_events"])
    prefix_head = prefix.get("head_hash")
    matches = bool(prefix.get("valid")) and prefix_head == latest["head_hash"]

    result = {
        "configured": True,
        "matches": matches,
        "anchored_head": latest["head_hash"],
        "anchored_at": latest["at"],
        "anchored_events": latest["chain_events"],
        "recomputed_prefix_head": prefix_head,
        "prefix_chain_valid": bool(prefix.get("valid")),
    }
    if not matches:
        result["claim"] = (
            "audit chain head diverges from the independently anchored head; "
            "the main audit store was altered after the last checkpoint"
        )
    return result

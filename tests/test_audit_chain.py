"""The audit chain must detect real tampering and must not cry wolf."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from gateway.audit import GENESIS_HASH, canonical_timestamp, chain_head, record_event, verify_chain
from gateway.db import dispose_db, init_db, session_scope
from gateway.models import AuditEvent


@pytest.fixture(autouse=True)
async def fresh_db():
    await init_db()
    yield
    await dispose_db()


async def test_chain_verifies_after_round_trip():
    for i in range(5):
        await record_event(
            event_type="decision.allow",
            user_id="user_1",
            decision="ALLOW",
            reason_codes=["POLICY_SATISFIED"],
            payload={"n": i},
        )
    result = await verify_chain()
    assert result["valid"] is True, result
    assert result["events_checked"] == 5
    assert (await chain_head())["head_hash"] == result["head_hash"]


async def test_naive_and_aware_timestamps_hash_identically():
    """The SQLite/Postgres round-trip difference must not break the chain."""
    aware = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)
    naive = datetime(2026, 1, 1, 12, 0, 0, 123456)
    assert canonical_timestamp(aware) == canonical_timestamp(naive)


async def test_first_event_chains_to_genesis():
    await record_event(event_type="test.event", payload={})
    async with session_scope() as s:
        first = (await s.execute(select(AuditEvent).order_by(AuditEvent.seq))).scalars().first()
    assert first.prev_hash == GENESIS_HASH


async def test_edited_event_is_detected():
    await record_event(event_type="decision.block", decision="BLOCK", reason_codes=["A"])
    await record_event(event_type="decision.allow", decision="ALLOW", reason_codes=["B"])
    await record_event(event_type="decision.allow", decision="ALLOW", reason_codes=["C"])

    # Someone with DB write access flips a BLOCK into an ALLOW after the fact.
    async with session_scope() as s:
        target = (await s.execute(select(AuditEvent).order_by(AuditEvent.seq))).scalars().first()
        target.decision = "ALLOW"
        target.reason_codes = ["POLICY_SATISFIED"]

    result = await verify_chain()
    assert result["valid"] is False
    assert result["broken_at_seq"] == 1


async def test_deleted_event_is_detected():
    await record_event(event_type="a", payload={})
    await record_event(event_type="b", payload={})
    await record_event(event_type="c", payload={})

    async with session_scope() as s:
        rows = (await s.execute(select(AuditEvent).order_by(AuditEvent.seq))).scalars().all()
        await s.delete(rows[1])

    result = await verify_chain()
    assert result["valid"] is False

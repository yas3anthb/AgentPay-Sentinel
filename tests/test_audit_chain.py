"""The audit chain must detect real tampering and must not cry wolf."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from gateway import checkpoint as cp
from gateway.audit import (
    GENESIS_HASH,
    _body,
    canonical_timestamp,
    chain_head,
    compute_hash,
    record_event,
    verify_chain,
)
from gateway.config import get_settings
from gateway.db import dispose_db, init_db, session_scope
from gateway.models import AuditEvent


@pytest.fixture(autouse=True)
async def fresh_db():
    await init_db()
    yield
    await dispose_db()


@pytest.fixture
async def checkpoint_db(tmp_path, monkeypatch):
    """A configured, independent checkpoint store backed by a temp sqlite file."""
    monkeypatch.setenv(
        "CHECKPOINT_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/checkpoints.db"
    )
    get_settings.cache_clear()
    await cp.dispose_checkpoint_db()
    await cp.init_checkpoint_db()
    yield cp
    await cp.dispose_checkpoint_db()
    get_settings.cache_clear()


async def _rewrite_chain_from_genesis(mutate) -> None:
    """Consistently re-hash every audit row from genesis after `mutate(rows)`
    changes one — the full-chain forgery that `verify_chain` alone cannot see."""
    async with session_scope() as s:
        rows = (await s.execute(select(AuditEvent).order_by(AuditEvent.seq))).scalars().all()
        mutate(rows)
        prev = GENESIS_HASH
        for e in rows:
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
            e.prev_hash = prev
            e.event_hash = compute_hash(body, prev)
            prev = e.event_hash


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


# --- independent checkpoint anchor (gateway/checkpoint.py) -------------------


async def test_checkpoint_not_configured_is_an_honest_no_op():
    get_settings.cache_clear()
    assert cp.is_configured() is False
    out = await cp.anchor_checkpoint("deadbeef", 3)
    assert out["anchored"] is False and "note" in out
    assert (await cp.verify_against_checkpoints())["configured"] is False


async def test_anchor_is_append_only(checkpoint_db):
    await record_event(event_type="a")
    head1 = await chain_head()
    a1 = await cp.anchor_checkpoint(head1["head_hash"], head1["events"])
    await record_event(event_type="b")
    head2 = await chain_head()
    a2 = await cp.anchor_checkpoint(head2["head_hash"], head2["events"])

    assert a1["anchored"] is True and a2["anchored"] is True
    assert a2["checkpoint_seq"] > a1["checkpoint_seq"]
    latest = await cp.latest_checkpoint()
    assert latest["head_hash"] == head2["head_hash"]
    assert latest["chain_events"] == 2


async def test_checkpoint_matches_right_after_anchoring(checkpoint_db):
    for i in range(3):
        await record_event(event_type="decision.allow", decision="ALLOW", payload={"i": i})
    head = await chain_head()
    await cp.anchor_checkpoint(head["head_hash"], head["events"])

    v = await cp.verify_against_checkpoints()
    assert v["matches"] is True
    assert v["prefix_chain_valid"] is True


async def test_consistent_full_chain_rewrite_is_caught_by_the_checkpoint(checkpoint_db):
    """A rewrite from genesis that keeps the chain internally valid still fails
    against the independently anchored head — the whole point of the anchor."""
    await record_event(event_type="decision.block", decision="BLOCK", reason_codes=["A"])
    await record_event(event_type="decision.allow", decision="ALLOW", reason_codes=["B"])
    await record_event(event_type="decision.allow", decision="ALLOW", reason_codes=["C"])

    head = await chain_head()
    await cp.anchor_checkpoint(head["head_hash"], head["events"])

    def _flip_first_block_to_allow(rows):
        rows[0].decision = "ALLOW"
        rows[0].reason_codes = ["POLICY_SATISFIED"]

    await _rewrite_chain_from_genesis(_flip_first_block_to_allow)

    # verify_chain alone is now fooled — the forged chain is internally consistent.
    assert (await verify_chain())["valid"] is True

    # The independent anchor is not.
    v = await cp.verify_against_checkpoints()
    assert v["matches"] is False
    assert v["prefix_chain_valid"] is True
    assert "diverges" in v["claim"]


async def test_legit_appends_after_a_checkpoint_are_not_a_false_alarm(checkpoint_db):
    for _ in range(3):
        await record_event(event_type="decision.allow", decision="ALLOW")
    head = await chain_head()
    await cp.anchor_checkpoint(head["head_hash"], head["events"])

    # Two more honest events after the checkpoint.
    for _ in range(2):
        await record_event(event_type="decision.allow", decision="ALLOW")

    v = await cp.verify_against_checkpoints()
    assert v["matches"] is True, v

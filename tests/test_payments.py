"""Payment authorization: state machine, idempotency, fingerprint, tokens."""
from __future__ import annotations

import time
from decimal import Decimal

import pytest

from gateway import payments as pay
from gateway.canonical import CanonicalTransaction, UntrustedContent, transaction_fingerprint
from gateway.db import dispose_db, init_db
from gateway.schemas import PaymentState as S
from gateway.schemas import SourceType
from gateway.store import reset_store
from gateway.tokens import issue_authorization_token, verify_authorization_token


@pytest.fixture(autouse=True)
async def fresh():
    await init_db()
    yield
    await reset_store()
    await dispose_db()


def make_txn(pa_id="pa_1", idem="idem-key-0001", amount="42.50", cart="c" * 64):
    return CanonicalTransaction(
        payment_authorization_id=pa_id,
        idempotency_key=idem,
        payload_hash=f"payload-{amount}-{cart}",
        fingerprint=transaction_fingerprint(
            user_id="user_1",
            merchant_id="merch_1",
            cart_hash=cart,
            amount=Decimal(amount),
            currency="USD",
        ),
        user_id="user_1",
        agent_id="agent_1",
        delegation_id="del_1",
        agent_scopes=("payments:authorize",),
        merchant_id="merch_1",
        merchant_verified_claim=True,
        amount=Decimal(amount),
        currency="USD",
        cart_hash=cart,
        item_count=1,
        untrusted=UntrustedContent("", SourceType.OFFICIAL_API, "", "", ""),
    )


# --- state machine ---------------------------------------------------------


def test_only_declared_transitions_are_legal():
    pay.assert_transition(S.CREATED, S.AUTHORIZED)
    pay.assert_transition(S.AUTHORIZED, S.SUBMITTED)
    pay.assert_transition(S.SUBMITTED, S.CONFIRMED)
    pay.assert_transition(S.SUBMITTED, S.TIMEOUT)
    pay.assert_transition(S.TIMEOUT, S.UNKNOWN)
    pay.assert_transition(S.UNKNOWN, S.CONFIRMED)


@pytest.mark.parametrize(
    "src,dst",
    [
        (S.CREATED, S.CONFIRMED),
        (S.CREATED, S.SUBMITTED),
        (S.TIMEOUT, S.CONFIRMED),
        (S.CONFIRMED, S.FAILED),
        (S.FAILED, S.CONFIRMED),
        (S.EXPIRED, S.AUTHORIZED),
    ],
)
def test_illegal_transitions_raise(src, dst):
    with pytest.raises(pay.InvalidTransition):
        pay.assert_transition(src, dst)


def test_timeout_cannot_short_circuit_to_success():
    """A provider timeout must pass through UNKNOWN and reconciliation. There
    is no edge that turns 'we never heard back' into 'the money moved'."""
    assert S.CONFIRMED not in pay.VALID_TRANSITIONS[S.TIMEOUT]
    assert pay.VALID_TRANSITIONS[S.TIMEOUT] == {S.UNKNOWN}


def test_terminal_states_are_terminal():
    for state in (S.CONFIRMED, S.FAILED, S.EXPIRED):
        assert pay.VALID_TRANSITIONS[state] == set()


# --- idempotency -----------------------------------------------------------


async def test_first_request_is_not_a_duplicate():
    outcome = await pay.check_duplicate(make_txn())
    assert not outcome.is_conflict
    assert not outcome.is_replay


async def test_identical_retry_returns_the_stored_response_verbatim():
    txn = make_txn()
    stored = {"payment_authorization_id": "pa_1", "decision": "ALLOW", "state": "CONFIRMED"}
    await pay.remember_outcome(txn, stored, reserve_fingerprint=True)

    retry = make_txn(pa_id="pa_2")  # same key, same payload, new attempt id
    outcome = await pay.check_duplicate(retry)

    assert outcome.is_replay
    assert not outcome.is_conflict
    assert outcome.replay_response == stored


async def test_same_key_different_payload_is_a_conflict():
    txn = make_txn(amount="42.50")
    await pay.remember_outcome(txn, {"decision": "ALLOW"}, reserve_fingerprint=True)

    tampered = make_txn(pa_id="pa_2", amount="1200.00")
    outcome = await pay.check_duplicate(tampered)

    assert outcome.finding.idempotency_conflict is True
    assert not outcome.is_replay


async def test_different_key_same_transaction_trips_the_fingerprint():
    txn = make_txn(idem="key-A")
    await pay.remember_outcome(txn, {"decision": "ALLOW"}, reserve_fingerprint=True)

    resend = make_txn(pa_id="pa_2", idem="key-B")
    outcome = await pay.check_duplicate(resend)

    assert outcome.finding.fingerprint_conflict is True


# --- fingerprint semantics -------------------------------------------------


def test_fingerprint_is_stable_inside_a_window():
    args = dict(
        user_id="u", merchant_id="m", cart_hash="c", amount=Decimal("10.00"), currency="USD"
    )
    base = 1_700_000_100.0  # exactly on a 300s bucket edge, so +120 stays inside
    assert transaction_fingerprint(**args, timestamp=base) == transaction_fingerprint(
        **args, timestamp=base + 120
    )


def test_fingerprint_changes_across_a_window_boundary():
    """The documented limitation, pinned by a test so nobody claims otherwise:
    the fingerprint alone misses a repeat that straddles a bucket edge. The
    idempotency key, which is not time-bucketed, is the primary defence."""
    args = dict(
        user_id="u", merchant_id="m", cart_hash="c", amount=Decimal("10.00"), currency="USD"
    )
    before = transaction_fingerprint(**args, timestamp=299.0, window_seconds=300)
    after = transaction_fingerprint(**args, timestamp=301.0, window_seconds=300)
    assert before != after


def test_fingerprint_separates_different_amounts():
    args = dict(user_id="u", merchant_id="m", cart_hash="c", currency="USD")
    a = transaction_fingerprint(**args, amount=Decimal("10.00"), timestamp=100.0)
    b = transaction_fingerprint(**args, amount=Decimal("1000.00"), timestamp=100.0)
    assert a != b


# --- scoped tokens ---------------------------------------------------------


def test_authorization_token_is_bound_and_single_use():
    issued = issue_authorization_token(
        payment_authorization_id="pa_1",
        user_id="user_1",
        agent_id="agent_1",
        merchant_id="merch_1",
        amount=Decimal("42.50"),
        currency="USD",
        cart_hash="c" * 64,
        policy_version="v1.4.2",
        ttl_seconds=60,
    )
    claims = verify_authorization_token(issued.token)
    assert claims["merchant_id"] == "merch_1"
    assert claims["amount"] == "42.50"
    assert claims["max_uses"] == 1
    assert claims["exp"] - claims["iat"] == 60


def test_expired_token_is_rejected():
    import jwt

    issued = issue_authorization_token(
        payment_authorization_id="pa_1",
        user_id="user_1",
        agent_id="agent_1",
        merchant_id="merch_1",
        amount=Decimal("1.00"),
        currency="USD",
        cart_hash="c",
        policy_version="v1",
        ttl_seconds=-1,
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        verify_authorization_token(issued.token)


def test_token_for_a_different_audience_is_rejected():
    """An approval token must not work as a payment credential."""
    import jwt

    from gateway.tokens import issue_approval_token

    approval = issue_approval_token(
        approval_request_id="ar_1",
        user_id="user_1",
        merchant_id="merch_1",
        amount=Decimal("12.00"),
        currency="USD",
        cart_hash="c",
    )
    with pytest.raises(jwt.InvalidTokenError):
        verify_authorization_token(approval)


# --- persistence + transitions round trip ----------------------------------


async def test_state_transitions_persist_and_audit():
    from gateway.audit import verify_chain

    txn = make_txn()
    await pay.persist_transaction(
        txn,
        decision="ALLOW",
        reason_codes=["POLICY_SATISFIED"],
        state=S.CREATED,
        risk={},
        policy_version="v1.4.2",
    )
    await pay.set_state(txn.payment_authorization_id, S.AUTHORIZED)
    await pay.set_state(txn.payment_authorization_id, S.SUBMITTED)
    await pay.set_state(txn.payment_authorization_id, S.CONFIRMED, provider_reference="ch_1")

    with pytest.raises(pay.InvalidTransition):
        await pay.set_state(txn.payment_authorization_id, S.FAILED)

    assert (await verify_chain())["valid"] is True


async def test_expired_authorization_is_swept():
    txn = make_txn()
    await pay.persist_transaction(
        txn,
        decision="ALLOW",
        reason_codes=[],
        state=S.CREATED,
        risk={},
        policy_version="v1.4.2",
    )
    token = issue_authorization_token(
        payment_authorization_id=txn.payment_authorization_id,
        user_id=txn.user_id,
        agent_id=txn.agent_id,
        merchant_id=txn.merchant_id,
        amount=txn.amount,
        currency=txn.currency,
        cart_hash=txn.cart_hash,
        policy_version="v1.4.2",
        ttl_seconds=-5,
    )
    from datetime import datetime, timezone

    from gateway.db import session_scope
    from gateway.models import Transaction

    async with session_scope() as s:
        row = await s.get(Transaction, txn.payment_authorization_id)
        row.state = S.AUTHORIZED.value
        row.token_jti = token.jti
        row.token_expires_at = datetime.fromtimestamp(token.expires_at, tz=timezone.utc)

    assert await pay.expire_stale_authorizations() == 1

    async with session_scope() as s:
        row = await s.get(Transaction, txn.payment_authorization_id)
        assert row.state == S.EXPIRED.value

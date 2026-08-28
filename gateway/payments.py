"""Stage 6 — Payment Authorization Service.

Owns the thing most agent-payment demos skip: what happens *after* the policy
says yes. A token being issued is not money moving, so the lifecycle is
explicit and every terminal state writes an audit event.

    CREATED ──► AUTHORIZED ──► SUBMITTED ──► CONFIRMED
                    │              │
                    │              ├──► FAILED    (provider declined / errored)
                    │              └──► TIMEOUT ──► UNKNOWN ──► CONFIRMED | FAILED
                    │                              (reconciliation polls the
                    │                               provider; never a silent retry,
                    │                               never counted as success)
                    └──► EXPIRED   (token TTL elapsed unused)

UNKNOWN is the honest state for "we asked and never heard back". It is never
treated as success and never auto-retried — retrying an unknown payment is how
a customer gets charged twice.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select

from gateway.audit import record_event
from gateway.canonical import CanonicalTransaction
from gateway.config import get_settings
from gateway.db import session_scope
from gateway.models import Transaction
from gateway.pdp import DuplicateFinding
from gateway.schemas import PaymentState
from gateway.store import get_store
from gateway.tokens import IssuedToken, issue_authorization_token

log = logging.getLogger("agentpay.payments")

# The only transitions that may ever happen. Anything else is a bug, and a bug
# in a payment state machine should be loud.
VALID_TRANSITIONS: dict[PaymentState, set[PaymentState]] = {
    PaymentState.CREATED: {PaymentState.AUTHORIZED, PaymentState.FAILED},
    PaymentState.AUTHORIZED: {
        PaymentState.SUBMITTED,
        PaymentState.EXPIRED,
        PaymentState.FAILED,
    },
    PaymentState.SUBMITTED: {
        PaymentState.CONFIRMED,
        PaymentState.FAILED,
        PaymentState.TIMEOUT,
    },
    PaymentState.TIMEOUT: {PaymentState.UNKNOWN},
    PaymentState.UNKNOWN: {PaymentState.CONFIRMED, PaymentState.FAILED},
    PaymentState.CONFIRMED: set(),
    PaymentState.FAILED: set(),
    PaymentState.EXPIRED: set(),
}

TERMINAL = {PaymentState.CONFIRMED, PaymentState.FAILED, PaymentState.EXPIRED}


class InvalidTransition(Exception):
    pass


def assert_transition(current: PaymentState, target: PaymentState) -> None:
    if target not in VALID_TRANSITIONS[current]:
        raise InvalidTransition(f"illegal payment transition {current.value} -> {target.value}")


def idem_key(user_id: str, idempotency_key: str) -> str:
    return f"agentpay:idem:{user_id}:{idempotency_key}"


def fingerprint_key(fingerprint: str) -> str:
    return f"agentpay:fp:{fingerprint}"


@dataclass(slots=True)
class IdempotencyOutcome:
    """One of three things: brand new, an honest client retry, or a conflict."""

    finding: DuplicateFinding
    replay_response: dict | None = None

    @property
    def is_replay(self) -> bool:
        return self.replay_response is not None

    @property
    def is_conflict(self) -> bool:
        return self.finding.idempotency_conflict or self.finding.fingerprint_conflict


async def check_duplicate(txn: CanonicalTransaction) -> IdempotencyOutcome:
    """Distinguishes a legitimate retry from a replay.

    Same key + identical payload  -> replay the stored response verbatim.
    Same key + different payload  -> DUPLICATE_IDEMPOTENCY_KEY, conflict.
    Different key + same fingerprint inside the window -> fingerprint conflict.

    Called under the caller's distributed lock so the check and the subsequent
    write are one critical section.
    """
    store = get_store()

    raw = await store.get(idem_key(txn.user_id, txn.idempotency_key))
    if raw:
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            record = {}
        if record.get("payload_hash") == txn.payload_hash:
            return IdempotencyOutcome(
                finding=DuplicateFinding(detail="idempotent_replay"),
                replay_response=record.get("response"),
            )
        return IdempotencyOutcome(
            finding=DuplicateFinding(
                idempotency_conflict=True,
                detail="idempotency key reused with a different payload",
            )
        )

    seen_pa_id = await store.get(fingerprint_key(txn.fingerprint))
    if seen_pa_id and seen_pa_id != txn.payment_authorization_id:
        return IdempotencyOutcome(
            finding=DuplicateFinding(
                fingerprint_conflict=True,
                detail=f"identical transaction already seen in this window ({seen_pa_id})",
            )
        )

    return IdempotencyOutcome(finding=DuplicateFinding())


async def remember_outcome(
    txn: CanonicalTransaction, response: dict, *, reserve_fingerprint: bool
) -> None:
    """Store the exact response so a retry gets the *same* answer, not a
    generic 'duplicate' error.

    `reserve_fingerprint` is only true for authorizations. The fingerprint
    means "a payment for this exact cart was already authorized in this
    window", so a decision that authorized nothing must not claim the slot —
    otherwise a transaction parked for human approval would block its own
    approved retry, which is the one flow that is *supposed* to resubmit the
    identical transaction.
    """
    settings = get_settings()
    store = get_store()
    await store.set(
        idem_key(txn.user_id, txn.idempotency_key),
        json.dumps({"payload_hash": txn.payload_hash, "response": response}, default=str),
        ex=settings.idempotency_ttl_seconds,
    )
    if reserve_fingerprint:
        await store.set(
            fingerprint_key(txn.fingerprint),
            txn.payment_authorization_id,
            ex=settings.fingerprint_window_seconds * 2,
        )


async def persist_transaction(
    txn: CanonicalTransaction,
    *,
    decision: str,
    reason_codes: list[str],
    state: PaymentState,
    risk: dict,
    policy_version: str,
    token: IssuedToken | None = None,
) -> None:
    async with session_scope() as s:
        s.add(
            Transaction(
                payment_authorization_id=txn.payment_authorization_id,
                idempotency_key=txn.idempotency_key,
                payload_hash=txn.payload_hash,
                fingerprint=txn.fingerprint,
                user_id=txn.user_id,
                agent_id=txn.agent_id,
                delegation_id=txn.delegation_id,
                merchant_id=txn.merchant_id,
                amount=txn.amount,
                currency=txn.currency,
                cart_hash=txn.cart_hash,
                decision=decision,
                reason_codes=reason_codes,
                state=state.value,
                risk=risk,
                policy_version=policy_version,
                token_jti=token.jti if token else None,
                token_expires_at=(
                    datetime.fromtimestamp(token.expires_at, tz=timezone.utc) if token else None
                ),
            )
        )


async def set_state(
    payment_authorization_id: str,
    target: PaymentState,
    *,
    provider_reference: str | None = None,
    detail: str | None = None,
    audit: bool = True,
) -> PaymentState:
    async with session_scope() as s:
        row = await s.get(Transaction, payment_authorization_id)
        if row is None:
            raise KeyError(payment_authorization_id)
        current = PaymentState(row.state)
        assert_transition(current, target)
        row.state = target.value
        if provider_reference:
            row.provider_reference = provider_reference
        if detail:
            row.provider_detail = detail
        user_id, agent_id, policy_version = row.user_id, row.agent_id, row.policy_version

    if audit:
        # Rule: anything other than CONFIRMED produces an audit event, and so
        # does CONFIRMED — the log is a complete record, not an incident list.
        await record_event(
            event_type=f"payment.{target.value.lower()}",
            payment_authorization_id=payment_authorization_id,
            user_id=user_id,
            agent_id=agent_id,
            decision=None,
            reason_codes=[f"STATE_{current.value}_TO_{target.value}"],
            policy_version=policy_version,
            payload={
                "from": current.value,
                "to": target.value,
                "provider_reference": provider_reference,
                "detail": detail,
                "settled": target is PaymentState.CONFIRMED,
            },
        )
    return target


async def authorize(txn: CanonicalTransaction, policy_version: str) -> IssuedToken:
    token = issue_authorization_token(
        payment_authorization_id=txn.payment_authorization_id,
        user_id=txn.user_id,
        agent_id=txn.agent_id,
        merchant_id=txn.merchant_id,
        amount=txn.amount,
        currency=txn.currency,
        cart_hash=txn.cart_hash,
        policy_version=policy_version,
    )
    async with session_scope() as s:
        row = await s.get(Transaction, txn.payment_authorization_id)
        if row is not None:
            row.token_jti = token.jti
            row.token_expires_at = datetime.fromtimestamp(token.expires_at, tz=timezone.utc)
    await set_state(txn.payment_authorization_id, PaymentState.AUTHORIZED)
    return token


@dataclass(slots=True)
class ProviderOutcome:
    state: PaymentState
    provider_reference: str | None = None
    detail: str = ""


async def submit(txn: CanonicalTransaction, token: IssuedToken) -> ProviderOutcome:
    """Consume the single-use token against the provider.

    Token consumption is recorded *before* the call, so a token cannot be
    replayed even if the provider call is what times out.
    """
    settings = get_settings()

    async with session_scope() as s:
        row = await s.get(Transaction, txn.payment_authorization_id)
        if row is None:
            raise KeyError(txn.payment_authorization_id)
        if row.token_uses >= 1:
            return ProviderOutcome(PaymentState.FAILED, detail="token already consumed")
        row.token_uses += 1

    await set_state(txn.payment_authorization_id, PaymentState.SUBMITTED)

    try:
        async with httpx.AsyncClient(timeout=settings.provider_timeout_seconds) as client:
            response = await client.post(
                f"{settings.provider_url}/charges",
                json={
                    "payment_authorization_id": txn.payment_authorization_id,
                    "idempotency_key": txn.idempotency_key,
                    "amount": str(txn.amount),
                    "currency": txn.currency,
                    "merchant_id": txn.merchant_id,
                    "cart_hash": txn.cart_hash,
                },
                headers={"Authorization": f"Bearer {token.token}"},
            )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        log.warning("provider did not answer for %s: %s", txn.payment_authorization_id, exc)
        await set_state(
            txn.payment_authorization_id, PaymentState.TIMEOUT, detail=str(exc)[:200]
        )
        await set_state(
            txn.payment_authorization_id,
            PaymentState.UNKNOWN,
            detail="awaiting reconciliation; not treated as success",
        )
        return ProviderOutcome(PaymentState.UNKNOWN, detail="provider timeout; reconciling")

    if response.status_code >= 400:
        body = response.text[:200]
        await set_state(txn.payment_authorization_id, PaymentState.FAILED, detail=body)
        return ProviderOutcome(PaymentState.FAILED, detail=body)

    payload = response.json()
    if payload.get("status") == "confirmed":
        ref = payload.get("provider_reference")
        await set_state(
            txn.payment_authorization_id, PaymentState.CONFIRMED, provider_reference=ref
        )
        return ProviderOutcome(PaymentState.CONFIRMED, provider_reference=ref)

    detail = str(payload.get("detail") or payload.get("status") or "declined")[:200]
    await set_state(txn.payment_authorization_id, PaymentState.FAILED, detail=detail)
    return ProviderOutcome(PaymentState.FAILED, detail=detail)


async def reconcile_unknown(max_age_minutes: int = 60) -> dict:
    """Resolve every UNKNOWN payment by *asking the provider what happened*.

    This is a query, never a re-submission. An UNKNOWN that the provider has
    never heard of resolves to FAILED; one it confirms resolves to CONFIRMED.
    """
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    resolved = {"confirmed": 0, "failed": 0, "still_unknown": 0}

    async with session_scope() as s:
        rows = (
            (
                await s.execute(
                    select(Transaction).where(
                        Transaction.state == PaymentState.UNKNOWN.value,
                        Transaction.created_at >= cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )
        pending = [(r.payment_authorization_id, r.idempotency_key) for r in rows]

    for pa_id, idem in pending:
        try:
            async with httpx.AsyncClient(timeout=settings.provider_timeout_seconds) as client:
                response = await client.get(f"{settings.provider_url}/charges/{pa_id}")
        except httpx.HTTPError:
            resolved["still_unknown"] += 1
            continue

        if response.status_code == 404:
            await set_state(
                pa_id, PaymentState.FAILED, detail="provider has no record; never charged"
            )
            resolved["failed"] += 1
            continue
        if response.status_code >= 400:
            resolved["still_unknown"] += 1
            continue

        payload = response.json()
        if payload.get("status") == "confirmed":
            await set_state(
                pa_id,
                PaymentState.CONFIRMED,
                provider_reference=payload.get("provider_reference"),
                detail="resolved by reconciliation",
            )
            resolved["confirmed"] += 1
        elif payload.get("status") in {"failed", "declined"}:
            await set_state(pa_id, PaymentState.FAILED, detail="resolved by reconciliation")
            resolved["failed"] += 1
        else:
            resolved["still_unknown"] += 1

    return resolved


async def expire_stale_authorizations() -> int:
    """AUTHORIZED tokens whose TTL elapsed unused become EXPIRED, so an
    outstanding authorization stops counting against the daily budget."""
    now = datetime.now(timezone.utc)
    async with session_scope() as s:
        rows = (
            (
                await s.execute(
                    select(Transaction).where(
                        Transaction.state == PaymentState.AUTHORIZED.value,
                        Transaction.token_expires_at.is_not(None),
                        Transaction.token_expires_at < now,
                    )
                )
            )
            .scalars()
            .all()
        )
        stale = [r.payment_authorization_id for r in rows]

    for pa_id in stale:
        await set_state(pa_id, PaymentState.EXPIRED, detail="token TTL elapsed unused")
    return len(stale)


async def reset_replay_state() -> None:
    """Dev helper: drop idempotency, fingerprint, velocity and approval records.

    Only reachable through the environment-guarded admin endpoint.
    """
    from gateway.config import get_settings as _gs

    if _gs().environment.lower() in {"production", "prod"}:
        raise RuntimeError("refusing to clear replay state in production")

    store = get_store()
    if hasattr(store, "_kv"):  # MemoryStore
        store._kv.clear()
        store._zsets.clear()
        return

    import redis.asyncio as aioredis

    client = aioredis.from_url(_gs().redis_url, decode_responses=True)
    try:
        for pattern in (
            "agentpay:idem:*",
            "agentpay:fp:*",
            "agentpay:velocity:*",
            "agentpay:approval:*",
        ):
            async for key in client.scan_iter(match=pattern, count=500):
                await client.delete(key)
    finally:
        await client.aclose()


def money(value: str | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(value)

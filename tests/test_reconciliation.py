"""Provider timeout handling: the case where you genuinely do not know whether
money moved. This is the part that decides whether a customer gets charged
twice, so it gets its own tests."""
from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from gateway import payments as pay
from gateway.canonical import CanonicalTransaction, UntrustedContent
from gateway.db import dispose_db, init_db, session_scope
from gateway.models import Transaction
from gateway.schemas import PaymentState as S
from gateway.schemas import SourceType
from gateway.store import reset_store
from gateway.tokens import issue_authorization_token


@pytest.fixture(autouse=True)
async def fresh():
    await init_db()
    yield
    await reset_store()
    await dispose_db()


def make_txn(pa_id="pa_recon_1"):
    return CanonicalTransaction(
        payment_authorization_id=pa_id,
        idempotency_key=f"idem-{pa_id}",
        payload_hash="p",
        fingerprint=f"fp-{pa_id}",
        user_id="user_1",
        agent_id="agent_1",
        delegation_id="del_1",
        agent_scopes=("payments:authorize",),
        merchant_id="merch_1",
        merchant_verified_claim=True,
        amount=Decimal("42.50"),
        currency="USD",
        cart_hash="c" * 64,
        item_count=1,
        untrusted=UntrustedContent("", SourceType.OFFICIAL_API, "", "", ""),
    )


async def setup_authorized(txn):
    await pay.persist_transaction(
        txn,
        decision="ALLOW",
        reason_codes=["POLICY_SATISFIED"],
        state=S.CREATED,
        risk={},
        policy_version="v1.4.2",
    )
    return await pay.authorize(txn, "v1.4.2")


def patch_transport(monkeypatch, handler):
    """Swap httpx's network for a scripted responder."""

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kwargs):
            return handler("POST", url, kwargs)

        async def get(self, url, **kwargs):
            return handler("GET", url, kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)


async def state_of(pa_id: str) -> str:
    async with session_scope() as s:
        return (await s.get(Transaction, pa_id)).state


async def test_provider_timeout_lands_in_unknown_not_success(monkeypatch):
    txn = make_txn()
    token = await setup_authorized(txn)

    def handler(method, url, kwargs):
        raise httpx.ReadTimeout("provider did not answer")

    patch_transport(monkeypatch, handler)
    outcome = await pay.submit(txn, token)

    assert outcome.state is S.UNKNOWN
    assert await state_of(txn.payment_authorization_id) == "UNKNOWN"


async def test_unknown_resolves_to_confirmed_when_the_provider_says_it_charged(monkeypatch):
    txn = make_txn("pa_recon_2")
    token = await setup_authorized(txn)

    calls: list[str] = []

    def timeout_then_confirm(method, url, kwargs):
        calls.append(f"{method} {url}")
        if method == "POST":
            raise httpx.ReadTimeout("no answer")
        return httpx.Response(
            200, json={"status": "confirmed", "provider_reference": "ch_abc"}
        )

    patch_transport(monkeypatch, timeout_then_confirm)
    await pay.submit(txn, token)
    result = await pay.reconcile_unknown()

    assert result["confirmed"] == 1
    assert await state_of(txn.payment_authorization_id) == "CONFIRMED"
    # Exactly one POST: reconciliation queries, it never re-submits.
    assert sum(1 for c in calls if c.startswith("POST")) == 1


async def test_unknown_resolves_to_failed_when_the_provider_never_saw_it(monkeypatch):
    txn = make_txn("pa_recon_3")
    token = await setup_authorized(txn)

    def timeout_then_404(method, url, kwargs):
        if method == "POST":
            raise httpx.ReadTimeout("no answer")
        return httpx.Response(404, json={"detail": "no such charge"})

    patch_transport(monkeypatch, timeout_then_404)
    await pay.submit(txn, token)
    result = await pay.reconcile_unknown()

    assert result["failed"] == 1
    assert await state_of(txn.payment_authorization_id) == "FAILED"


async def test_unknown_stays_unknown_when_the_provider_is_still_unreachable(monkeypatch):
    txn = make_txn("pa_recon_4")
    token = await setup_authorized(txn)

    def always_down(method, url, kwargs):
        raise httpx.ConnectError("provider down")

    patch_transport(monkeypatch, always_down)
    await pay.submit(txn, token)
    result = await pay.reconcile_unknown()

    assert result["still_unknown"] == 1
    assert await state_of(txn.payment_authorization_id) == "UNKNOWN"


async def test_declined_payment_is_failed_not_retried(monkeypatch):
    txn = make_txn("pa_recon_5")
    token = await setup_authorized(txn)

    patch_transport(
        monkeypatch,
        lambda m, u, k: httpx.Response(200, json={"status": "declined", "detail": "card declined"}),
    )
    outcome = await pay.submit(txn, token)

    assert outcome.state is S.FAILED
    assert await state_of(txn.payment_authorization_id) == "FAILED"


async def test_a_token_cannot_be_submitted_twice(monkeypatch):
    txn = make_txn("pa_recon_6")
    token = await setup_authorized(txn)

    patch_transport(
        monkeypatch,
        lambda m, u, k: httpx.Response(200, json={"status": "confirmed", "provider_reference": "ch_1"}),
    )
    assert (await pay.submit(txn, token)).state is S.CONFIRMED

    second = await pay.submit(txn, token)
    assert second.state is S.FAILED
    assert "already consumed" in second.detail


async def test_every_state_change_writes_an_audit_event(monkeypatch):
    from gateway.audit import verify_chain
    from sqlalchemy import select

    from gateway.models import AuditEvent

    txn = make_txn("pa_recon_7")
    token = await setup_authorized(txn)
    patch_transport(
        monkeypatch,
        lambda m, u, k: httpx.Response(200, json={"status": "confirmed", "provider_reference": "ch_1"}),
    )
    await pay.submit(txn, token)

    async with session_scope() as s:
        types = [
            e.event_type
            for e in (await s.execute(select(AuditEvent).order_by(AuditEvent.seq))).scalars().all()
        ]

    assert types == ["payment.authorized", "payment.submitted", "payment.confirmed"]
    assert (await verify_chain())["valid"] is True

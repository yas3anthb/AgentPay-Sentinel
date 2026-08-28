"""Human-in-the-loop approvals.

When the PDP says REQUIRE_APPROVAL the gateway parks the transaction and hands
back an approval_request_id describing exactly what a human is being asked to
authorize. Granting it produces a signed token bound to those exact
money-moving fields; the PDP re-checks the binding on the retry.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from decimal import Decimal

import jwt

from gateway.canonical import CanonicalTransaction
from gateway.pdp import ApprovalFinding
from gateway.store import get_store
from gateway.tokens import issue_approval_token, verify_approval_token

APPROVAL_TTL_SECONDS = 900


def _key(approval_request_id: str) -> str:
    return f"agentpay:approval:{approval_request_id}"


@dataclass(slots=True)
class ApprovalRequest:
    approval_request_id: str
    user_id: str
    merchant_id: str
    amount: str
    currency: str
    cart_hash: str
    reason_codes: list[str]
    payment_authorization_id: str
    granted: bool = False

    def summary(self) -> dict:
        return {
            "approval_request_id": self.approval_request_id,
            "what_you_are_approving": (
                f"{self.amount} {self.currency} to merchant {self.merchant_id}"
            ),
            "cart_hash": self.cart_hash,
            "why": self.reason_codes,
            "expires_in_seconds": APPROVAL_TTL_SECONDS,
        }


async def create_request(
    txn: CanonicalTransaction, reason_codes: list[str]
) -> ApprovalRequest:
    request = ApprovalRequest(
        approval_request_id=f"ar_{txn.payment_authorization_id[3:]}",
        user_id=txn.user_id,
        merchant_id=txn.merchant_id,
        amount=str(txn.amount),
        currency=txn.currency,
        cart_hash=txn.cart_hash,
        reason_codes=reason_codes,
        payment_authorization_id=txn.payment_authorization_id,
    )
    await get_store().set(
        _key(request.approval_request_id),
        json.dumps(asdict(request)),
        ex=APPROVAL_TTL_SECONDS,
    )
    return request


async def load_request(approval_request_id: str) -> ApprovalRequest | None:
    raw = await get_store().get(_key(approval_request_id))
    if not raw:
        return None
    return ApprovalRequest(**json.loads(raw))


async def grant(approval_request_id: str) -> str | None:
    """Human approves. The token is bound to what was displayed, not to
    whatever the agent sends next."""
    request = await load_request(approval_request_id)
    if request is None:
        return None
    request.granted = True
    await get_store().set(
        _key(approval_request_id), json.dumps(asdict(request)), ex=APPROVAL_TTL_SECONDS
    )
    return issue_approval_token(
        approval_request_id=approval_request_id,
        user_id=request.user_id,
        merchant_id=request.merchant_id,
        amount=Decimal(request.amount),
        currency=request.currency,
        cart_hash=request.cart_hash,
        ttl_seconds=APPROVAL_TTL_SECONDS,
    )


async def evaluate_token(token: str | None) -> ApprovalFinding:
    """Turn a presented approval token into a finding for the PDP.

    Note what this does NOT do: it never decides. A mismatch between the bound
    fields and the live transaction is reported as data; approvals.rego is what
    turns that into APPROVAL_BINDING_MISMATCH.
    """
    if not token:
        return ApprovalFinding(present=False)

    try:
        claims = verify_approval_token(token)
    except jwt.ExpiredSignatureError:
        return ApprovalFinding(present=True, valid=False, expired=True)
    except jwt.InvalidTokenError:
        return ApprovalFinding(present=True, valid=False, expired=False)

    return ApprovalFinding(
        present=True,
        valid=True,
        expired=False,
        bound_amount=float(Decimal(str(claims.get("bound_amount", "0")))),
        bound_merchant_id=claims.get("bound_merchant_id"),
        bound_currency=claims.get("bound_currency"),
        bound_cart_hash=claims.get("bound_cart_hash"),
    )

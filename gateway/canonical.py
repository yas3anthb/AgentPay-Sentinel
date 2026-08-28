"""Stage 2 — Canonical Transaction Builder.

Turns a validated PaymentIntent plus a verified identity into the single
canonical object every downstream stage reads. Two invariants:

  1. The money-moving fields are typed and frozen here. Nothing downstream may
     re-derive an amount or a merchant from text.
  2. Free text is carried in one explicitly-named `untrusted` bag so no stage
     can accidentally treat it as an instruction.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from decimal import Decimal

from gateway.config import get_settings
from gateway.identity import AgentIdentity
from gateway.schemas import PaymentIntent, SourceType


@dataclass(frozen=True, slots=True)
class UntrustedContent:
    """Every free-text field that will ever reach an LLM prompt lives here.

    `purpose` and `tool_arguments` are agent-authored and are treated with the
    same suspicion as scraped merchant content: an agent that has already been
    hijacked upstream authors its `purpose` field too.
    """

    merchant_text: str
    merchant_source_type: SourceType
    merchant_source_url: str
    purpose: str
    tool_arguments_text: str

    def fields(self) -> dict[str, str]:
        return {
            "merchant_content": self.merchant_text,
            "purpose": self.purpose,
            "tool_arguments": self.tool_arguments_text,
        }

    def is_empty(self) -> bool:
        return not any(v.strip() for v in self.fields().values())


@dataclass(frozen=True, slots=True)
class CanonicalTransaction:
    payment_authorization_id: str
    idempotency_key: str
    payload_hash: str
    fingerprint: str

    user_id: str
    agent_id: str
    delegation_id: str
    agent_scopes: tuple[str, ...]

    merchant_id: str
    merchant_verified_claim: bool

    amount: Decimal
    currency: str
    cart_hash: str
    item_count: int

    untrusted: UntrustedContent
    approval_token: str | None = None
    created_ts: float = field(default_factory=time.time)

    def money_fields(self) -> dict:
        return {
            "user_id": self.user_id,
            "merchant_id": self.merchant_id,
            "amount": str(self.amount),
            "currency": self.currency,
            "cart_hash": self.cart_hash,
        }


def transaction_fingerprint(
    *,
    user_id: str,
    merchant_id: str,
    cart_hash: str,
    amount: Decimal,
    currency: str,
    timestamp: float | None = None,
    window_seconds: int | None = None,
) -> str:
    """SHA256(user + merchant + cart + amount + currency + floor(ts / window)).

    Known limitation, documented rather than papered over: two legitimately
    identical purchases that straddle a window boundary land in different
    buckets and this check misses the pair. That is acceptable because the
    client-supplied idempotency key — which is not time-bucketed — is the
    primary duplicate-prevention mechanism. The fingerprint is the coarser
    backstop for clients that did not send a meaningful key.
    """
    import hashlib

    window = window_seconds or get_settings().fingerprint_window_seconds
    ts = timestamp if timestamp is not None else time.time()
    bucket = int(math.floor(ts / window))
    blob = f"{user_id}|{merchant_id}|{cart_hash}|{amount}|{currency}|{bucket}"
    return hashlib.sha256(blob.encode()).hexdigest()


def build_canonical(
    intent: PaymentIntent, identity: AgentIdentity, payment_authorization_id: str
) -> CanonicalTransaction:
    import json

    cart_hash = intent.cart_hash()
    return CanonicalTransaction(
        payment_authorization_id=payment_authorization_id,
        idempotency_key=intent.idempotency_key,
        payload_hash=intent.payload_hash(),
        fingerprint=transaction_fingerprint(
            user_id=identity.user_id,
            merchant_id=intent.merchant_id,
            cart_hash=cart_hash,
            amount=intent.amount,
            currency=intent.currency,
        ),
        user_id=identity.user_id,
        agent_id=identity.agent_id,
        delegation_id=identity.delegation_id,
        agent_scopes=tuple(identity.scopes),
        merchant_id=intent.merchant_id,
        # Note this is the *claim* made by the caller. The merchant registry is
        # the authority; the PDP reads the registry, never this field.
        merchant_verified_claim=intent.merchant_verified,
        amount=intent.amount,
        currency=intent.currency,
        cart_hash=cart_hash,
        item_count=sum(i.quantity for i in intent.items),
        untrusted=UntrustedContent(
            merchant_text=intent.merchant_content.text,
            merchant_source_type=intent.merchant_content.source_type,
            merchant_source_url=intent.merchant_content.source_url,
            purpose=intent.purpose,
            tool_arguments_text=json.dumps(intent.tool_arguments, default=str, sort_keys=True)
            if intent.tool_arguments
            else "",
        ),
        approval_token=intent.approval_token,
    )

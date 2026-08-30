"""Scoped, short-lived, single-use payment tokens and human-approval tokens.

The authorization token is the *only* credential the payment provider accepts.
It is bound to merchant, amount, currency and cart hash, so a token stolen
mid-flight cannot be pointed at a different purchase — the provider re-checks
the binding rather than trusting the request body.
"""
from __future__ import annotations

import pathlib
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal

import jwt

from gateway.config import get_settings

AUTH_AUDIENCE = "agentpay-provider"
APPROVAL_AUDIENCE = "agentpay-approval"


def _private_key() -> str:
    # The payment-signing keypair, NOT the delegation keypair. See config.py.
    return pathlib.Path(get_settings().payment_signing_private_key_path).read_text()


def _public_key() -> str:
    return pathlib.Path(get_settings().payment_signing_public_key_path).read_text()


@dataclass(slots=True)
class IssuedToken:
    token: str
    jti: str
    expires_at: int


def issue_authorization_token(
    *,
    payment_authorization_id: str,
    user_id: str,
    agent_id: str,
    merchant_id: str,
    amount: Decimal,
    currency: str,
    cart_hash: str,
    policy_version: str,
    ttl_seconds: int | None = None,
) -> IssuedToken:
    settings = get_settings()
    ttl = ttl_seconds or settings.token_ttl_seconds
    now = int(time.time())
    jti = f"pat_{uuid.uuid4().hex}"
    claims = {
        "iss": settings.jwt_issuer,
        "aud": AUTH_AUDIENCE,
        "sub": user_id,
        "jti": jti,
        "iat": now,
        "exp": now + ttl,
        "payment_authorization_id": payment_authorization_id,
        "agent_id": agent_id,
        "merchant_id": merchant_id,
        "amount": str(amount),
        "currency": currency,
        "cart_hash": cart_hash,
        "max_uses": 1,
        "policy_version": policy_version,
    }
    token = jwt.encode(claims, _private_key(), algorithm=settings.jwt_algorithm)
    return IssuedToken(token=token, jti=jti, expires_at=now + ttl)


def verify_authorization_token(token: str) -> dict:
    """Used by the mock provider. Raises jwt exceptions on failure."""
    settings = get_settings()
    return jwt.decode(
        token,
        _public_key(),
        algorithms=[settings.jwt_algorithm],
        audience=AUTH_AUDIENCE,
        issuer=settings.jwt_issuer,
        options={"require": ["exp", "iat", "jti", "aud", "iss"]},
    )


def issue_approval_token(
    *,
    approval_request_id: str,
    user_id: str,
    merchant_id: str,
    amount: Decimal,
    currency: str,
    cart_hash: str,
    ttl_seconds: int = 900,
) -> str:
    """Signed record of exactly what a human saw and agreed to.

    Every money-moving field the human was shown is baked in. The PDP compares
    these against the transaction actually presented, so an agent cannot get
    approval for a $12 coffee and then execute $1,200 of gift cards.
    """
    settings = get_settings()
    now = int(time.time())
    return jwt.encode(
        {
            "iss": settings.jwt_issuer,
            "aud": APPROVAL_AUDIENCE,
            "sub": user_id,
            "jti": f"apr_{uuid.uuid4().hex}",
            "iat": now,
            "exp": now + ttl_seconds,
            "approval_request_id": approval_request_id,
            "bound_merchant_id": merchant_id,
            "bound_amount": str(amount),
            "bound_currency": currency,
            "bound_cart_hash": cart_hash,
        },
        _private_key(),
        algorithm=settings.jwt_algorithm,
    )


def verify_approval_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(
        token,
        _public_key(),
        algorithms=[settings.jwt_algorithm],
        audience=APPROVAL_AUDIENCE,
        issuer=settings.jwt_issuer,
        options={"require": ["exp", "iat", "jti", "aud", "iss"]},
    )

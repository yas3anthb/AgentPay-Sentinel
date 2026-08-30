"""Stage 1 — Identity & Request Integrity.

Verifies the delegation JWT, checks agent scope, checks near-real-time
revocation, and cross-checks the token's claims against the typed intent so a
valid token for one delegation cannot be pointed at another user's money.
"""
from __future__ import annotations

import functools
import logging
import pathlib
import time
from dataclasses import dataclass, field

import jwt
from jwt import InvalidTokenError

from gateway.config import get_settings
from gateway.store import REVOCATION_SET, get_store

log = logging.getLogger("agentpay.identity")

REQUIRED_SCOPE = "payments:authorize"


class IdentityError(Exception):
    """Raised when identity cannot be established. Always terminal (BLOCK)."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message


@dataclass(slots=True)
class AgentIdentity:
    agent_id: str
    user_id: str
    delegation_id: str
    scopes: list[str] = field(default_factory=list)
    jti: str = ""
    issued_at: int = 0
    expires_at: int = 0
    raw_claims: dict = field(default_factory=dict)


@functools.lru_cache
def _public_key() -> str:
    path = pathlib.Path(get_settings().jwt_public_key_path)
    if not path.exists():
        raise IdentityError(
            "IDENTITY_KEY_UNAVAILABLE",
            f"delegation public key missing at {path}; run scripts/gen_keys.py",
        )
    return path.read_text()


def decode_delegation_token(token: str) -> AgentIdentity:
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            _public_key(),
            algorithms=[settings.jwt_algorithm],  # allow-list; never trust alg header
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "iat", "sub", "jti", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise IdentityError("DELEGATION_EXPIRED", "delegation token expired") from exc
    except InvalidTokenError as exc:
        raise IdentityError("INVALID_IDENTITY", f"invalid delegation token: {exc}") from exc

    missing = [c for c in ("agent_id", "delegation_id") if not claims.get(c)]
    if missing:
        raise IdentityError(
            "INVALID_IDENTITY", f"delegation token missing claims: {','.join(missing)}"
        )

    return AgentIdentity(
        agent_id=str(claims["agent_id"]),
        user_id=str(claims["sub"]),
        delegation_id=str(claims["delegation_id"]),
        scopes=list(claims.get("scopes", [])),
        jti=str(claims["jti"]),
        issued_at=int(claims.get("iat", 0)),
        expires_at=int(claims.get("exp", 0)),
        raw_claims=claims,
    )


async def assert_not_revoked(delegation_id: str) -> None:
    """Near-real-time revocation, not instant: a revoked delegation is rejected
    as soon as the revocation lands in the shared set, even while its JWT is
    still cryptographically valid. If the set is unreachable we fail closed."""
    try:
        revoked = await get_store().sismember(REVOCATION_SET, delegation_id)
    except Exception as exc:
        log.error("revocation check failed: %s", exc)
        raise IdentityError(
            "REVOCATION_CHECK_UNAVAILABLE",
            "cannot verify delegation revocation status; failing closed",
        ) from exc
    if revoked:
        raise IdentityError("DELEGATION_REVOKED", "delegation has been revoked")


def assert_scope(identity: AgentIdentity, scope: str = REQUIRED_SCOPE) -> None:
    if scope not in identity.scopes:
        raise IdentityError(
            "AGENT_SCOPE_VIOLATION",
            f"agent {identity.agent_id} lacks required scope {scope}",
        )


def assert_binding(identity: AgentIdentity, intent) -> None:
    """Request integrity: the token must actually be the token for *this* intent."""
    mismatches = []
    if identity.agent_id != intent.agent_id:
        mismatches.append("agent_id")
    if identity.user_id != intent.user_id:
        mismatches.append("user_id")
    if identity.delegation_id != intent.delegation_id:
        mismatches.append("delegation_id")
    if mismatches:
        raise IdentityError(
            "IDENTITY_INTENT_MISMATCH",
            "delegation token does not match intent fields: " + ",".join(mismatches),
        )


async def authenticate(authorization: str | None, intent) -> AgentIdentity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise IdentityError("MISSING_CREDENTIALS", "missing bearer delegation token")
    identity = decode_delegation_token(authorization.split(" ", 1)[1].strip())
    assert_binding(identity, intent)
    assert_scope(identity)
    await assert_not_revoked(identity.delegation_id)
    return identity


def mint_delegation_token(
    *,
    agent_id: str,
    user_id: str,
    delegation_id: str,
    scopes: list[str] | None = None,
    ttl_seconds: int = 3600,
) -> str:
    """Test/demo helper only. The real issuer is the control-plane service
    (`control_plane/keys.py`), which is the only component that holds the
    delegation private key. In Compose the gateway is not given that key at
    all, so calling this there raises FileNotFoundError — which is the correct
    behaviour for a production gateway."""
    settings = get_settings()
    key = pathlib.Path(settings.jwt_private_key_path).read_text()
    now = int(time.time())
    return jwt.encode(
        {
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "sub": user_id,
            "agent_id": agent_id,
            "delegation_id": delegation_id,
            "scopes": scopes if scopes is not None else [REQUIRED_SCOPE],
            "iat": now,
            "exp": now + ttl_seconds,
            "jti": f"jti_{now}_{delegation_id}",
        },
        key,
        algorithm=settings.jwt_algorithm,
    )

"""Identity, request integrity, and near-real-time revocation."""
from __future__ import annotations

import time
from decimal import Decimal

import jwt
import pytest

from gateway.identity import (
    AgentIdentity,
    IdentityError,
    assert_binding,
    authenticate,
    decode_delegation_token,
    mint_delegation_token,
)
from gateway.schemas import PaymentIntent
from gateway.store import REVOCATION_SET, get_store, reset_store


@pytest.fixture(autouse=True)
async def clean_store():
    yield
    await reset_store()


def intent(**over) -> PaymentIntent:
    data = {
        "idempotency_key": "idem-key-0001",
        "agent_id": "agent_1",
        "user_id": "user_1",
        "delegation_id": "del_1",
        "merchant_id": "merch_1",
        "amount": Decimal("42.50"),
        "currency": "USD",
        "items": [
            {"sku": "S1", "name": "Thing", "quantity": 1, "unit_price": Decimal("42.50")}
        ],
    }
    data.update(over)
    return PaymentIntent(**data)


def good_token(**over) -> str:
    args = dict(agent_id="agent_1", user_id="user_1", delegation_id="del_1")
    args.update(over)
    return mint_delegation_token(**args)


async def test_valid_token_authenticates():
    identity = await authenticate(f"Bearer {good_token()}", intent())
    assert identity.agent_id == "agent_1"
    assert identity.user_id == "user_1"
    assert "payments:authorize" in identity.scopes


async def test_missing_header_is_rejected():
    with pytest.raises(IdentityError) as exc:
        await authenticate(None, intent())
    assert exc.value.reason_code == "MISSING_CREDENTIALS"


async def test_non_bearer_scheme_is_rejected():
    with pytest.raises(IdentityError):
        await authenticate(f"Basic {good_token()}", intent())


async def test_expired_token_is_rejected():
    token = mint_delegation_token(
        agent_id="agent_1", user_id="user_1", delegation_id="del_1", ttl_seconds=-10
    )
    with pytest.raises(IdentityError) as exc:
        await authenticate(f"Bearer {token}", intent())
    assert exc.value.reason_code == "DELEGATION_EXPIRED"


async def test_token_signed_by_another_key_is_rejected():
    """An attacker-signed token must not authenticate, and specifically the
    `alg` header must not be able to talk us into `none`."""
    forged = jwt.encode(
        {
            "iss": "agentpay-control-plane",
            "aud": "agentpay-sentinel",
            "sub": "user_1",
            "agent_id": "agent_1",
            "delegation_id": "del_1",
            "scopes": ["payments:authorize"],
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
            "jti": "forged",
        },
        "attacker-secret",
        algorithm="HS256",
    )
    with pytest.raises(IdentityError) as exc:
        await authenticate(f"Bearer {forged}", intent())
    assert exc.value.reason_code == "INVALID_IDENTITY"


async def test_token_missing_required_scope_is_rejected():
    token = good_token()
    token = mint_delegation_token(
        agent_id="agent_1", user_id="user_1", delegation_id="del_1", scopes=["catalog:read"]
    )
    with pytest.raises(IdentityError) as exc:
        await authenticate(f"Bearer {token}", intent())
    assert exc.value.reason_code == "AGENT_SCOPE_VIOLATION"


@pytest.mark.parametrize(
    "field,value",
    [("user_id", "user_someone_else"), ("agent_id", "agent_other"), ("delegation_id", "del_2")],
)
async def test_token_must_match_the_intent_it_authorizes(field, value):
    """A valid token for delegation A cannot be pointed at delegation B."""
    with pytest.raises(IdentityError) as exc:
        await authenticate(f"Bearer {good_token()}", intent(**{field: value}))
    assert exc.value.reason_code == "IDENTITY_INTENT_MISMATCH"


async def test_revoked_delegation_is_rejected_while_jwt_is_still_valid():
    token = good_token()  # freshly minted, an hour of life left
    await get_store().sadd(REVOCATION_SET, "del_1")

    with pytest.raises(IdentityError) as exc:
        await authenticate(f"Bearer {token}", intent())
    assert exc.value.reason_code == "DELEGATION_REVOKED"

    # And the token itself is still cryptographically fine — which is exactly
    # why the revocation set has to exist.
    assert decode_delegation_token(token).delegation_id == "del_1"


async def test_revocation_check_failure_fails_closed(monkeypatch):
    class Broken:
        async def sismember(self, *a, **k):
            raise ConnectionError("redis is down")

    monkeypatch.setattr("gateway.identity.get_store", lambda: Broken())
    with pytest.raises(IdentityError) as exc:
        await authenticate(f"Bearer {good_token()}", intent())
    assert exc.value.reason_code == "REVOCATION_CHECK_UNAVAILABLE"


def test_binding_reports_every_mismatch():
    identity = AgentIdentity(agent_id="a", user_id="u", delegation_id="d")
    with pytest.raises(IdentityError) as exc:
        assert_binding(identity, intent())
    assert "agent_id" in exc.value.message
    assert "user_id" in exc.value.message
    assert "delegation_id" in exc.value.message

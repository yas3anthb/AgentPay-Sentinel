"""The control plane: authenticated, attributable, and the only minter of
delegation tokens. The gateway can no longer do any of this."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from control_plane.config import get_settings as cp_get_settings
from gateway.config import get_settings

ADMIN = {"X-Admin-Key": "test-admin-key", "X-Admin-Id": "ada@ops"}


@pytest.fixture
def control(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/cp.db")
    monkeypatch.setenv("REDIS_URL", "memory://")
    get_settings.cache_clear()
    cp_get_settings.cache_clear()

    from control_plane.main import app

    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()
    cp_get_settings.cache_clear()


def _seed(c: TestClient) -> None:
    c.put(
        "/v1/admin/agents",
        headers=ADMIN,
        json={"agent_id": "agent_x", "owner_user_id": "user_x"},
    ).raise_for_status()
    c.put(
        "/v1/admin/policies",
        headers=ADMIN,
        json={
            "delegation_id": "del_x",
            "user_id": "user_x",
            "agent_id": "agent_x",
            "per_transaction_limit": "100.00",
            "daily_limit": "500.00",
            "approval_threshold": "80.00",
        },
    ).raise_for_status()


def test_mutating_calls_require_the_admin_key(control):
    assert control.put("/v1/admin/agents", json={"agent_id": "a", "owner_user_id": "u"}).status_code == 401
    assert (
        control.put(
            "/v1/admin/agents",
            headers={"X-Admin-Key": "wrong"},
            json={"agent_id": "a", "owner_user_id": "u"},
        ).status_code
        == 401
    )
    ok = control.put(
        "/v1/admin/agents", headers=ADMIN, json={"agent_id": "a", "owner_user_id": "u"}
    )
    assert ok.status_code == 200


def test_reads_are_also_gated(control):
    assert control.get("/v1/admin/delegations/revoked").status_code == 401
    assert control.get("/v1/admin/delegations/revoked", headers=ADMIN).status_code == 200


def test_minted_token_verifies_with_the_gateways_public_key(control):
    _seed(control)
    r = control.post(
        "/v1/admin/tokens",
        headers=ADMIN,
        json={"agent_id": "agent_x", "user_id": "user_x", "delegation_id": "del_x"},
    )
    assert r.status_code == 200
    token = r.json()["token"]

    # The gateway holds only the public half and must be able to verify it.
    from gateway.identity import decode_delegation_token

    identity = decode_delegation_token(token)
    assert identity.agent_id == "agent_x"
    assert identity.delegation_id == "del_x"
    assert "payments:authorize" in identity.scopes


def test_every_mutation_is_written_to_the_admin_audit_trail(control):
    _seed(control)
    control.post(
        "/v1/admin/tokens",
        headers=ADMIN,
        json={"agent_id": "agent_x", "user_id": "user_x", "delegation_id": "del_x"},
    ).raise_for_status()
    control.post("/v1/admin/delegations/del_x/revoke", headers=ADMIN).raise_for_status()

    events = control.get("/v1/admin/audit/admin", headers=ADMIN).json()["events"]
    actions = [e["action"] for e in events]
    assert {"agent.upsert", "policy.upsert", "token.mint", "delegation.revoke"} <= set(actions)
    assert all(e["admin_id"] == "ada@ops" for e in events)
    # The token-mint row records a digest, never the token or the raw payload.
    mint = next(e for e in events if e["action"] == "token.mint")
    assert len(mint["payload_sha256"]) == 64


def test_revoke_lands_in_the_shared_revocation_set(control):
    _seed(control)
    control.post("/v1/admin/delegations/del_x/revoke", headers=ADMIN).raise_for_status()
    revoked = control.get("/v1/admin/delegations/revoked", headers=ADMIN).json()["revoked"]
    assert "del_x" in revoked


# --- Telegram account linking (demo bot) -----------------------------------


def test_telegram_link_round_trip(control):
    code = control.post(
        "/v1/admin/telegram/link-code", headers=ADMIN, json={"user_id": "user_x"}
    ).json()["code"]
    assert code.startswith("LINK-")

    assert control.get("/v1/admin/telegram/status/user_x", headers=ADMIN).json()["linked"] is False

    out = control.post(
        "/v1/admin/telegram/link", headers=ADMIN,
        json={"code": code, "telegram_id": "987654321"},
    ).json()
    assert out["status"] == "linked"
    assert out["user_id"] == "user_x"
    assert out["telegram_id_masked"] == "98*****21"  # never the raw id

    status = control.get("/v1/admin/telegram/status/user_x", headers=ADMIN).json()
    assert status["linked"] is True and status["telegram_id_masked"] == "98*****21"


def test_telegram_link_code_is_single_use(control):
    code = control.post(
        "/v1/admin/telegram/link-code", headers=ADMIN, json={"user_id": "user_x"}
    ).json()["code"]
    control.post(
        "/v1/admin/telegram/link", headers=ADMIN,
        json={"code": code, "telegram_id": "111"},
    ).raise_for_status()
    again = control.post(
        "/v1/admin/telegram/link", headers=ADMIN,
        json={"code": code, "telegram_id": "222"},
    )
    assert again.status_code == 409


def test_telegram_unknown_code_is_rejected(control):
    r = control.post(
        "/v1/admin/telegram/link", headers=ADMIN,
        json={"code": "LINK-NOPE99", "telegram_id": "111"},
    )
    assert r.status_code == 404


def test_telegram_endpoints_require_the_admin_key(control):
    assert control.post(
        "/v1/admin/telegram/link-code", json={"user_id": "user_x"}
    ).status_code == 401
    assert control.get("/v1/admin/telegram/status/user_x").status_code == 401


def test_telegram_unlink(control):
    code = control.post(
        "/v1/admin/telegram/link-code", headers=ADMIN, json={"user_id": "user_x"}
    ).json()["code"]
    control.post(
        "/v1/admin/telegram/link", headers=ADMIN,
        json={"code": code, "telegram_id": "987654321"},
    ).raise_for_status()

    control.request(
        "DELETE", "/v1/admin/telegram/link/user_x", headers=ADMIN
    ).raise_for_status()
    assert control.get("/v1/admin/telegram/status/user_x", headers=ADMIN).json()["linked"] is False

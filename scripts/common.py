"""Shared helpers for the demo scripts: seeding, formatting, HTTP."""
from __future__ import annotations

import os
import sys
import textwrap

import httpx

GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:8080")
PROVIDER = os.getenv("PROVIDER_URL", "http://localhost:9100")
# The control plane is a separate service: agent/policy/merchant registration,
# delegation revocation and token minting all live here now, behind X-Admin-Key.
CONTROL_PLANE = os.getenv("CONTROL_PLANE_URL", "http://localhost:8090")
ADMIN_KEY = os.getenv("ADMIN_API_KEY", "dev-admin-key")
ADMIN_HEADERS = {"X-Admin-Key": ADMIN_KEY, "X-Admin-Id": "demo-script"}

USER = "user_ada"
AGENT = "agent_shopper_01"
DELEGATION = "del_office_supplies"

BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"


def step(n: int, title: str) -> None:
    print(f"\n{BOLD}{CYAN}[{n}] {title}{RESET}")


def note(text: str) -> None:
    print(textwrap.indent(textwrap.fill(text, 92), "    "))


def kv(key: str, value: object, colour: str = "") -> None:
    print(f"    {DIM}{key:<28}{RESET}{colour}{value}{RESET}")


def verdict_colour(decision: str) -> str:
    return {"ALLOW": GREEN, "BLOCK": RED, "REQUIRE_APPROVAL": YELLOW}.get(decision, "")


def banner(title: str, subtitle: str = "") -> None:
    print(f"\n{BOLD}{'═' * 96}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    if subtitle:
        print(f"  {DIM}{subtitle}{RESET}")
    print(f"{BOLD}{'═' * 96}{RESET}")


def require_gateway() -> None:
    for name, url in (("Gateway", f"{GATEWAY}/healthz"), ("Control plane", f"{CONTROL_PLANE}/healthz")):
        try:
            httpx.get(url, timeout=3.0).raise_for_status()
        except Exception as exc:
            print(f"{RED}{name} is not reachable at {url}: {exc}{RESET}")
            print("Start the stack first:  docker compose up --build")
            sys.exit(1)


def seed(client: httpx.Client) -> str:
    """Register the agent, the merchants, and the spending policy, then mint a
    delegation token. This is control-plane work — a separate, authenticated
    service — and none of it can move money."""
    client.put(
        f"{CONTROL_PLANE}/v1/admin/agents",
        headers=ADMIN_HEADERS,
        json={
            "agent_id": AGENT,
            "owner_user_id": USER,
            "display_name": "Office Supplies Shopper",
            "allowed_scopes": ["payments:authorize"],
            "allowed_merchant_categories": ["retail", "grocery"],
            "active": True,
        },
    ).raise_for_status()

    for merchant in (
        {
            "merchant_id": "merch_beanery",
            "display_name": "The Beanery",
            "category": "grocery",
            "verified": True,
            "risk_score": 0.08,
        },
        {
            "merchant_id": "merch_giftcards_xyz",
            "display_name": "GiftCards XYZ",
            "category": "retail",
            "verified": False,
            "risk_score": 0.85,
        },
    ):
        client.put(
            f"{CONTROL_PLANE}/v1/admin/merchants", headers=ADMIN_HEADERS, json=merchant
        ).raise_for_status()

    client.put(
        f"{CONTROL_PLANE}/v1/admin/policies",
        headers=ADMIN_HEADERS,
        json={
            "delegation_id": DELEGATION,
            "user_id": USER,
            "agent_id": AGENT,
            "policy_version": "v1.4.2",
            "per_transaction_limit": "15000.00",
            "daily_limit": "40000.00",
            "currency": "INR",
            "allowed_merchants": [],
            "blocked_merchants": [],
            "require_verified_merchant": True,
            "approval_threshold": "8000.00",
            "max_transactions_per_hour": 10,
        },
    ).raise_for_status()

    response = client.post(
        f"{CONTROL_PLANE}/v1/admin/tokens",
        headers=ADMIN_HEADERS,
        json={
            "agent_id": AGENT,
            "user_id": USER,
            "delegation_id": DELEGATION,
            "scopes": ["payments:authorize"],
            "ttl_seconds": 3600,
        },
    )
    response.raise_for_status()
    return response.json()["token"]


def reset_demo_state(client: httpx.Client) -> None:
    """Clear transactions, the audit chain and the replay caches so the demo is
    repeatable. The endpoint refuses to run outside dev."""
    try:
        client.post(
            f"{CONTROL_PLANE}/v1/admin/dev/reset", headers=ADMIN_HEADERS, timeout=15.0
        ).raise_for_status()
    except Exception as exc:
        print(f"{YELLOW}warning: could not reset gateway demo state: {exc}{RESET}")


def reset_provider(client: httpx.Client) -> None:
    try:
        client.post(f"{PROVIDER}/_control/reset", timeout=3.0)
        client.post(f"{PROVIDER}/_control/behaviour", json={"behaviour": "success"}, timeout=3.0)
    except Exception as exc:
        print(f"{YELLOW}warning: could not reset mock provider: {exc}{RESET}")


def provider_calls(client: httpx.Client) -> int:
    return client.get(f"{PROVIDER}/_control/stats", timeout=3.0).json()["call_count"]


def show_decision(response: httpx.Response) -> dict:
    body = response.json()
    decision = body.get("decision", "?")
    kv("decision", decision, verdict_colour(decision) + BOLD)
    kv("reason_codes", ", ".join(body.get("reason_codes", [])) or "-")
    kv("state", body.get("state"))
    risk = body.get("risk", {})
    kv("weighted risk score", f"{risk.get('weighted_score')} / 100")
    signals = risk.get("signals", {})
    kv(
        "injection_confidence",
        signals.get("injection_confidence"),
        RED if (signals.get("injection_confidence") or 0) >= 0.85 else "",
    )
    if signals.get("injection_labels"):
        kv("injection_labels", ", ".join(signals["injection_labels"]))
    kv("policy_version", body.get("policy_version"))
    kv("audit_hash", (body.get("audit_hash") or "-")[:32] + "…")
    if body.get("message"):
        kv("message", body["message"])
    return body

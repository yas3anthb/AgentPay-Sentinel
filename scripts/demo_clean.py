#!/usr/bin/env python3
"""Demo A — a legitimate purchase runs end to end and is ALLOWed.

Shows: identity verification, canonical transaction, clean analyzer verdict,
signals-only risk engine, an OPA ALLOW, a scoped single-use token, a confirmed
charge at the provider, and the audit chain closing over all of it.
"""
from __future__ import annotations

import sys
import uuid

import httpx

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from scripts.common import (  # noqa: E402
    AGENT,
    DELEGATION,
    GATEWAY,
    GREEN,
    RESET,
    USER,
    banner,
    kv,
    note,
    provider_calls,
    require_gateway,
    reset_demo_state,
    reset_provider,
    seed,
    show_decision,
    step,
)


def main() -> int:
    require_gateway()
    banner(
        "DEMO A — clean purchase, end to end",
        "an agent buys coffee inside its delegated budget from a verified merchant",
    )

    with httpx.Client(timeout=30.0) as client:
        step(1, "Control plane: register the agent, merchants and spending policy")
        reset_demo_state(client)
        token = seed(client)
        reset_provider(client)
        kv("user", USER)
        kv("agent", AGENT)
        kv("delegation", DELEGATION)
        kv("policy", "per-txn $200 · daily $500 · approval over $150 · verified merchants only")
        kv("provider calls so far", provider_calls(client))

        step(2, "The agent submits a typed PaymentIntent with the merchant's page content")
        intent = {
            "idempotency_key": f"order-{uuid.uuid4().hex[:12]}",
            "agent_id": AGENT,
            "user_id": USER,
            "delegation_id": DELEGATION,
            "merchant_id": "merch_beanery",
            "merchant_verified": True,
            "amount": "42.50",
            "currency": "USD",
            "items": [
                {"sku": "BEAN-ETH-1KG", "name": "Ethiopian whole bean 1kg",
                 "quantity": 2, "unit_price": "21.25"},
            ],
            "purpose": "Monthly coffee restock for the office kitchen",
            "merchant_content": {
                "source_type": "official_api",
                "source_url": "https://beanery.example.com/api/products/BEAN-ETH-1KG",
                "text": (
                    "Single-origin Ethiopian coffee, 1kg whole bean, medium roast. "
                    "Ships in 2 business days. Free returns within 30 days."
                ),
            },
            "tool_arguments": {"cart_id": "cart_9931", "shipping": "standard"},
        }
        kv("merchant", "merch_beanery (verified, grocery)")
        kv("amount", "42.50 USD")
        kv("content source", "official_api  → high trust")

        response = client.post(
            f"{GATEWAY}/v1/payment-intents",
            json=intent,
            headers={"Authorization": f"Bearer {token}"},
        )
        step(3, "Pipeline verdict")
        body = show_decision(response)

        step(4, "Payment execution")
        kv("state", body.get("state"))
        kv("provider_reference", body.get("provider_reference") or "-")
        kv("provider calls", provider_calls(client))
        note(
            "The provider verified the scoped token independently and re-checked that the "
            "charge body matched the token's bound merchant, amount, currency and cart hash."
        )

        step(5, "Idempotent retry — the same request returns the same answer")
        retry = client.post(
            f"{GATEWAY}/v1/payment-intents",
            json=intent,
            headers={"Authorization": f"Bearer {token}"},
        )
        retry_body = retry.json()
        kv("replayed", retry_body.get("replayed"))
        kv("same authorization id", retry_body["payment_authorization_id"] == body["payment_authorization_id"])
        kv("decision", retry_body["decision"])
        kv("provider calls after retry", provider_calls(client))
        note(
            "A network blip on the client's side must not become a second charge, and must "
            "not become a scary 'duplicate blocked' error either. Identical payload plus "
            "identical key returns the stored response verbatim."
        )

        step(6, "Audit chain")
        verify = client.get(f"{GATEWAY}/v1/audit/verify").json()
        kv("chain valid", verify["valid"], GREEN if verify["valid"] else "")
        kv("events checked", verify["events_checked"])
        kv("head hash", verify["head_hash"][:48] + "…")
        kv("claim", verify["claim"])

        ok = body["decision"] == "ALLOW" and body["state"] == "CONFIRMED"
        print()
        print(f"{GREEN}✓ DEMO A PASSED{RESET}" if ok else "✗ DEMO A FAILED")
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Assembles the deterministic facts a decision needs: the bound spending
policy, the merchant registry entry, spend-to-date, and request velocity.

These are facts, not judgements. The risk engine turns them into signals and
OPA turns signals into a decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from gateway.canonical import CanonicalTransaction
from gateway.db import session_scope
from gateway.models import AgentRegistration, Merchant, SpendingPolicy, Transaction
from gateway.store import get_store


@dataclass(slots=True)
class PolicyContext:
    policy_found: bool = False
    policy_version: str = "unbound"
    per_transaction_limit: Decimal = Decimal("0")
    daily_limit: Decimal = Decimal("0")
    policy_currency: str = "USD"
    allowed_merchants: list[str] = field(default_factory=list)
    blocked_merchants: list[str] = field(default_factory=list)
    require_verified_merchant: bool = True
    approval_threshold: Decimal = Decimal("0")
    max_transactions_per_hour: int = 10
    policy_revoked: bool = False

    merchant_known: bool = False
    merchant_verified: bool = False
    merchant_category: str = "unknown"
    merchant_registry_risk: float = 0.9

    agent_registered: bool = False
    agent_active: bool = False
    agent_allowed_categories: list[str] = field(default_factory=list)

    spent_today: Decimal = Decimal("0")
    transactions_last_hour: int = 0

    def to_dict(self) -> dict:
        return {
            "policy_found": self.policy_found,
            "policy_version": self.policy_version,
            "per_transaction_limit": str(self.per_transaction_limit),
            "daily_limit": str(self.daily_limit),
            "policy_currency": self.policy_currency,
            "allowed_merchants": self.allowed_merchants,
            "blocked_merchants": self.blocked_merchants,
            "require_verified_merchant": self.require_verified_merchant,
            "approval_threshold": str(self.approval_threshold),
            "max_transactions_per_hour": self.max_transactions_per_hour,
            "policy_revoked": self.policy_revoked,
            "merchant_known": self.merchant_known,
            "merchant_verified": self.merchant_verified,
            "merchant_category": self.merchant_category,
            "merchant_registry_risk": self.merchant_registry_risk,
            "agent_registered": self.agent_registered,
            "agent_active": self.agent_active,
            "agent_allowed_categories": self.agent_allowed_categories,
            "spent_today": str(self.spent_today),
            "transactions_last_hour": self.transactions_last_hour,
        }


SETTLED_STATES = ("AUTHORIZED", "SUBMITTED", "CONFIRMED", "TIMEOUT", "UNKNOWN")


async def load_context(txn: CanonicalTransaction) -> PolicyContext:
    ctx = PolicyContext()

    async with session_scope() as s:
        policy = await s.get(SpendingPolicy, txn.delegation_id)
        if policy is not None and policy.user_id == txn.user_id:
            ctx.policy_found = True
            ctx.policy_version = policy.policy_version
            ctx.per_transaction_limit = Decimal(policy.per_transaction_limit)
            ctx.daily_limit = Decimal(policy.daily_limit)
            ctx.policy_currency = policy.currency
            ctx.allowed_merchants = list(policy.allowed_merchants or [])
            ctx.blocked_merchants = list(policy.blocked_merchants or [])
            ctx.require_verified_merchant = policy.require_verified_merchant
            ctx.approval_threshold = Decimal(policy.approval_threshold)
            ctx.max_transactions_per_hour = policy.max_transactions_per_hour
            ctx.policy_revoked = policy.revoked

        merchant = await s.get(Merchant, txn.merchant_id)
        if merchant is not None:
            ctx.merchant_known = True
            ctx.merchant_verified = merchant.verified
            ctx.merchant_category = merchant.category
            ctx.merchant_registry_risk = merchant.risk_score

        agent = await s.get(AgentRegistration, txn.agent_id)
        if agent is not None:
            ctx.agent_registered = True
            ctx.agent_active = agent.active
            ctx.agent_allowed_categories = list(agent.allowed_merchant_categories or [])

        # Spend-to-date counts anything that reached the provider or beyond,
        # plus authorized-but-unsettled tokens — an outstanding authorization
        # is money that can still leave.
        since = datetime.now(timezone.utc) - timedelta(days=1)
        spent = (
            await s.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.user_id == txn.user_id,
                    Transaction.created_at >= since,
                    Transaction.state.in_(SETTLED_STATES),
                )
            )
        ).scalar_one()
        ctx.spent_today = Decimal(str(spent or 0))

    ctx.transactions_last_hour = await get_store().zcount_window(
        f"agentpay:velocity:{txn.user_id}:{txn.agent_id}", 3600
    )
    return ctx


async def record_velocity(txn: CanonicalTransaction) -> int:
    return await get_store().zadd_window(
        f"agentpay:velocity:{txn.user_id}:{txn.agent_id}", 3600
    )

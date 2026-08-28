"""Stage 4 — Risk Engine.

This component **does not decide anything**. It converts facts and analyzer
evidence into a normalized signals object plus a weighted score:

    R = 35*I + 25*P + 20*B + 10*M + 10*V      (0-100)

There is deliberately no `decision`, `block`, or `action` field anywhere in
this module's output. Two components that can both say "blocked" will
eventually disagree, and then nobody can say why a payment was stopped. OPA is
the only place that decides.
"""
from __future__ import annotations

from decimal import Decimal

from gateway.analyzer import AnalysisResult
from gateway.canonical import CanonicalTransaction
from gateway.context import PolicyContext
from gateway.schemas import RiskAssessment, RiskSignals

WEIGHTS = {
    "injection": 35.0,
    "policy_violation": 25.0,
    "budget_anomaly": 20.0,
    "merchant": 10.0,
    "velocity": 10.0,
}


def _clamp(x: float) -> float:
    return round(min(1.0, max(0.0, x)), 3)


def policy_violation_score(txn: CanonicalTransaction, ctx: PolicyContext) -> float:
    """How far outside the bound policy this request sits, before anyone
    decides what to do about it."""
    if not ctx.policy_found:
        return 1.0  # an unbound delegation is a total policy violation
    score = 0.0
    if ctx.policy_revoked:
        score = max(score, 1.0)
    if txn.merchant_id in ctx.blocked_merchants:
        score = max(score, 1.0)
    if ctx.allowed_merchants and txn.merchant_id not in ctx.allowed_merchants:
        score = max(score, 0.8)
    if ctx.require_verified_merchant and not ctx.merchant_verified:
        score = max(score, 0.75)
    if txn.currency != ctx.policy_currency:
        score = max(score, 0.6)
    if ctx.agent_registered and not ctx.agent_active:
        score = max(score, 1.0)
    if (
        ctx.agent_allowed_categories
        and ctx.merchant_category not in ctx.agent_allowed_categories
    ):
        score = max(score, 0.55)
    if "payments:authorize" not in txn.agent_scopes:
        score = max(score, 1.0)
    return _clamp(score)


def budget_anomaly_score(txn: CanonicalTransaction, ctx: PolicyContext) -> float:
    """Blends three views of 'is this amount unusual': fraction of the
    per-transaction limit, fraction of the remaining daily budget, and outright
    breach of either."""
    if not ctx.policy_found or ctx.per_transaction_limit <= 0:
        return 1.0

    amount = Decimal(txn.amount)
    per_txn_ratio = float(amount / ctx.per_transaction_limit)

    projected = ctx.spent_today + amount
    daily_ratio = float(projected / ctx.daily_limit) if ctx.daily_limit > 0 else 1.0

    if per_txn_ratio > 1.0 or daily_ratio > 1.0:
        return 1.0

    # Below the limits, scale smoothly: sitting at 90% of a cap is a real
    # anomaly signal even though it is technically allowed.
    return _clamp(max(per_txn_ratio, daily_ratio) ** 1.5)


def merchant_risk_score(ctx: PolicyContext) -> float:
    if not ctx.merchant_known:
        return 0.9
    base = float(ctx.merchant_registry_risk)
    if not ctx.merchant_verified:
        base = max(base, 0.6)
    return _clamp(base)


def velocity_risk_score(ctx: PolicyContext) -> float:
    if ctx.max_transactions_per_hour <= 0:
        return 1.0
    return _clamp(ctx.transactions_last_hour / ctx.max_transactions_per_hour)


def assess(
    txn: CanonicalTransaction, ctx: PolicyContext, analysis: AnalysisResult
) -> RiskAssessment:
    signals = RiskSignals(
        injection_confidence=_clamp(analysis.injection_confidence),
        injection_labels=analysis.injection_labels,
        policy_violation_score=policy_violation_score(txn, ctx),
        budget_anomaly_score=budget_anomaly_score(txn, ctx),
        merchant_risk_score=merchant_risk_score(ctx),
        velocity_risk_score=velocity_risk_score(ctx),
        source_trust_score=_clamp(analysis.source_trust_score),
        classifier_degraded=analysis.classifier_degraded,
    )
    weighted = (
        WEIGHTS["injection"] * signals.injection_confidence
        + WEIGHTS["policy_violation"] * signals.policy_violation_score
        + WEIGHTS["budget_anomaly"] * signals.budget_anomaly_score
        + WEIGHTS["merchant"] * signals.merchant_risk_score
        + WEIGHTS["velocity"] * signals.velocity_risk_score
    )
    return RiskAssessment(
        signals=signals,
        weighted_score=round(weighted, 2),
        policy_version_context=ctx.policy_version,
    )

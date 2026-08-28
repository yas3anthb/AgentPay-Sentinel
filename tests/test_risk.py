"""The risk engine emits evidence, never verdicts."""
from __future__ import annotations

import inspect
from decimal import Decimal

from gateway import risk
from gateway.analyzer import AnalysisResult
from gateway.canonical import CanonicalTransaction, UntrustedContent
from gateway.context import PolicyContext
from gateway.schemas import SourceType


def txn(amount="50.00", currency="USD", scopes=("payments:authorize",)) -> CanonicalTransaction:
    return CanonicalTransaction(
        payment_authorization_id="pa_1",
        idempotency_key="idem-0001",
        payload_hash="p",
        fingerprint="f",
        user_id="u",
        agent_id="a",
        delegation_id="d",
        agent_scopes=scopes,
        merchant_id="merch_1",
        merchant_verified_claim=True,
        amount=Decimal(amount),
        currency=currency,
        cart_hash="c",
        item_count=1,
        untrusted=UntrustedContent("", SourceType.OFFICIAL_API, "", "", ""),
    )


def ctx(**over) -> PolicyContext:
    base = dict(
        policy_found=True,
        policy_version="v1.4.2",
        per_transaction_limit=Decimal("200.00"),
        daily_limit=Decimal("500.00"),
        policy_currency="USD",
        approval_threshold=Decimal("150.00"),
        max_transactions_per_hour=10,
        merchant_known=True,
        merchant_verified=True,
        merchant_category="grocery",
        merchant_registry_risk=0.1,
        agent_registered=True,
        agent_active=True,
        spent_today=Decimal("0"),
        transactions_last_hour=0,
    )
    base.update(over)
    return PolicyContext(**base)


def analysis(confidence=0.0, degraded=False) -> AnalysisResult:
    return AnalysisResult(
        injection_confidence=confidence, classifier_degraded=degraded, source_trust_score=0.95
    )


def test_module_has_no_decision_vocabulary():
    """Structural guarantee, not a style preference: two components that can
    both say BLOCK will eventually disagree, and then nobody can explain why a
    payment stopped."""
    source = inspect.getsource(risk)
    for word in ("ALLOW", "BLOCK", "REQUIRE_APPROVAL", "deny"):
        assert word not in source


def test_assessment_carries_no_decision_field():
    result = risk.assess(txn(), ctx(), analysis())
    assert not hasattr(result, "decision")
    assert "decision" not in result.signals.model_dump()


def test_weighted_score_uses_the_declared_weights():
    result = risk.assess(
        txn(amount="200.00"),
        ctx(transactions_last_hour=10, merchant_registry_risk=1.0, merchant_verified=False),
        analysis(1.0),
    )
    # I=1, P=0.75 (unverified on a protected policy), B=1, M=1, V=1
    expected = 35 + 25 * 0.75 + 20 + 10 + 10
    assert result.weighted_score == round(expected, 2)


def test_clean_transaction_scores_low():
    assert risk.assess(txn("20.00"), ctx(), analysis()).weighted_score < 15


def test_unbound_policy_maxes_the_policy_and_budget_signals():
    signals = risk.assess(txn(), ctx(policy_found=False), analysis()).signals
    assert signals.policy_violation_score == 1.0
    assert signals.budget_anomaly_score == 1.0


def test_over_limit_saturates_the_budget_signal():
    assert risk.assess(txn("250.00"), ctx(), analysis()).signals.budget_anomaly_score == 1.0


def test_daily_spend_feeds_the_budget_signal():
    low = risk.assess(txn("50.00"), ctx(), analysis()).signals.budget_anomaly_score
    high = risk.assess(
        txn("50.00"), ctx(spent_today=Decimal("400.00")), analysis()
    ).signals.budget_anomaly_score
    assert high > low


def test_missing_scope_maxes_policy_violation():
    signals = risk.assess(txn(scopes=("catalog:read",)), ctx(), analysis()).signals
    assert signals.policy_violation_score == 1.0


def test_unknown_merchant_is_high_risk():
    assert risk.assess(txn(), ctx(merchant_known=False), analysis()).signals.merchant_risk_score >= 0.9


def test_velocity_scales_with_the_hourly_allowance():
    signals = risk.assess(txn(), ctx(transactions_last_hour=5), analysis()).signals
    assert signals.velocity_risk_score == 0.5


def test_degraded_classifier_is_reported_not_scored_as_an_attack():
    signals = risk.assess(txn(), ctx(), analysis(0.0, degraded=True)).signals
    assert signals.classifier_degraded is True
    assert signals.injection_confidence == 0.0


def test_all_signals_stay_in_range():
    result = risk.assess(
        txn("100000.00"),
        ctx(transactions_last_hour=999, merchant_registry_risk=5.0),
        analysis(3.0),
    )
    for name, value in result.signals.model_dump().items():
        if isinstance(value, float):
            assert 0.0 <= value <= 1.0, name
    assert 0 <= result.weighted_score <= 100

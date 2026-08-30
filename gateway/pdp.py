"""Stage 5 — Policy Decision Point client.

OPA is the only component that decides. This module's whole job is to marshal
evidence into the policy input shape, ask OPA, and fail closed if OPA cannot
answer. It contains no decision logic of its own — the one BLOCK it produces
locally is the unavailability case, which is the absence of a decision, not a
second opinion.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from gateway.analyzer import AnalysisResult
from gateway.canonical import CanonicalTransaction
from gateway.config import get_settings
from gateway.context import PolicyContext
from gateway.money import to_minor_units
from gateway.schemas import Decision, RiskAssessment

log = logging.getLogger("agentpay.pdp")


@dataclass(slots=True)
class IdentityFinding:
    valid: bool
    user_id: str = ""
    reason_codes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DuplicateFinding:
    idempotency_conflict: bool = False
    fingerprint_conflict: bool = False
    detail: str = ""


@dataclass(slots=True)
class ApprovalFinding:
    present: bool = False
    valid: bool = False
    expired: bool = False
    # Minor units (see gateway.money), so approvals.rego can compare it to
    # transaction.amount with an exact integer ==.
    bound_amount: int | None = None
    bound_merchant_id: str | None = None
    bound_currency: str | None = None
    bound_cart_hash: str | None = None


@dataclass(slots=True)
class PDPResult:
    decision: Decision
    reason_codes: list[str]
    policy_version: str
    weighted_score: float = 0.0
    deny_reasons: list[str] = field(default_factory=list)
    approval_reasons: list[str] = field(default_factory=list)
    pdp_available: bool = True


def build_input(
    *,
    txn: CanonicalTransaction,
    ctx: PolicyContext,
    analysis: AnalysisResult,
    risk: RiskAssessment,
    identity: IdentityFinding,
    duplicate: DuplicateFinding,
    approval: ApprovalFinding,
    allow_degraded_classifier: bool = False,
    degraded_classifier_requires_review: bool = False,
) -> dict:
    # Every amount OPA sees is an integer number of minor units (see
    # gateway.money). Rego then compares limits, spend and approval bindings as
    # integers instead of float64 — no binary rounding on a value that gates a
    # payment. Scores and probabilities (weighted_score, risk signals) are not
    # money and stay as floats.
    context = ctx.to_dict()
    context.update(
        {
            "per_transaction_limit": to_minor_units(ctx.per_transaction_limit),
            "daily_limit": to_minor_units(ctx.daily_limit),
            "approval_threshold": to_minor_units(ctx.approval_threshold),
            "spent_today": to_minor_units(ctx.spent_today),
            "allow_degraded_classifier": allow_degraded_classifier,
            "degraded_classifier_requires_review": degraded_classifier_requires_review,
        }
    )
    return {
        "identity": {
            "valid": identity.valid,
            "user_id": identity.user_id,
            "reason_codes": identity.reason_codes,
        },
        "transaction": {
            "user_id": txn.user_id,
            "agent_id": txn.agent_id,
            "delegation_id": txn.delegation_id,
            "merchant_id": txn.merchant_id,
            "merchant_verified_claim": txn.merchant_verified_claim,
            "amount": to_minor_units(txn.amount),
            "currency": txn.currency,
            "cart_hash": txn.cart_hash,
            "item_count": txn.item_count,
            "agent_scopes": list(txn.agent_scopes),
        },
        "security": {
            "injection_confidence": analysis.injection_confidence,
            "injection_labels": analysis.injection_labels,
            "classifier_degraded": analysis.classifier_degraded,
            # What the deterministic layers concluded on their own. Lets the
            # policy distinguish "no classifier verdict AND no other evidence"
            # from "no classifier verdict BUT the rules already flagged this".
            "deterministic_confidence": analysis.deterministic_confidence,
            "source_trust_score": analysis.source_trust_score,
        },
        "risk": {
            "weighted_score": risk.weighted_score,
            "signals": risk.signals.model_dump(),
        },
        "context": context,
        "approval": {
            "present": approval.present,
            "valid": approval.valid,
            "expired": approval.expired,
            "bound_amount": approval.bound_amount,
            "bound_merchant_id": approval.bound_merchant_id,
            "bound_currency": approval.bound_currency,
            "bound_cart_hash": approval.bound_cart_hash,
        },
        "duplicate": {
            "idempotency_conflict": duplicate.idempotency_conflict,
            "fingerprint_conflict": duplicate.fingerprint_conflict,
        },
    }


def _unavailable(policy_version: str, detail: str) -> PDPResult:
    """No decision could be obtained. Deny-by-default means this is a BLOCK,
    and the reason code says so plainly so nobody mistakes it for a policy
    verdict when reading the audit log."""
    return PDPResult(
        decision=Decision.BLOCK,
        reason_codes=["PDP_UNAVAILABLE_FAIL_CLOSED", f"PDP_DETAIL:{detail}"[:120]],
        policy_version=policy_version,
        deny_reasons=["PDP_UNAVAILABLE_FAIL_CLOSED"],
        pdp_available=False,
    )


async def evaluate(policy_input: dict) -> PDPResult:
    settings = get_settings()
    url = f"{settings.opa_url}/v1/data/{settings.opa_decision_path}"
    declared_version = policy_input.get("context", {}).get("policy_version", "unknown")

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(url, json={"input": policy_input})
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        log.error("OPA unreachable at %s: %s", url, exc)
        return _unavailable(declared_version, type(exc).__name__)
    except ValueError as exc:
        log.error("OPA returned non-JSON: %s", exc)
        return _unavailable(declared_version, "invalid_json")

    result = body.get("result")
    if not isinstance(result, dict) or "decision" not in result:
        # An undefined result means no rule matched. Deny-by-default.
        log.error("OPA returned no decision for %s: %s", settings.opa_decision_path, body)
        return _unavailable(declared_version, "undefined_result")

    try:
        decision = Decision(result["decision"])
    except ValueError:
        log.error("OPA returned unknown decision %r", result.get("decision"))
        return _unavailable(declared_version, "unknown_decision_value")

    return PDPResult(
        decision=decision,
        reason_codes=list(result.get("reason_codes") or []),
        policy_version=str(result.get("policy_version") or declared_version),
        weighted_score=float(result.get("weighted_score") or 0.0),
        deny_reasons=list(result.get("deny_reasons") or []),
        approval_reasons=list(result.get("approval_reasons") or []),
    )

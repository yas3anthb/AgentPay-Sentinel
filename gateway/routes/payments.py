"""Runtime enforcement plane — the per-transaction pipeline.

    1. Identity & Request Integrity
    2. Canonical Transaction Builder
    3. Intent & Content Security Analyzer
    4. Risk Engine            (signals only, no decision)
    5. Policy Decision Point  (OPA — the only decider)
    6. Payment Authorization Service
    7. Immutable Audit

Deny-by-default throughout: any stage that cannot complete yields a BLOCK with
a reason code that names the failure, never an implicit pass.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import desc, select

from gateway import approvals as approvals_svc
from gateway import payments as pay
from gateway.analyzer import AnalysisResult, analyze
from gateway.audit import chain_head, publish_checkpoint, verify_chain
from gateway.canonical import build_canonical
from gateway.config import get_settings
from gateway.context import load_context, record_velocity
from gateway.db import session_scope
from gateway.events import PipelineEmitter, Stage, StageStatus
from gateway.identity import IdentityError, authenticate
from gateway.models import AuditEvent, Transaction
from gateway.pdp import (
    DuplicateFinding,
    IdentityFinding,
    PDPResult,
    build_input,
    evaluate,
)
from gateway.risk import assess
from gateway.schemas import (
    AuthorizationToken,
    Decision,
    DecisionResponse,
    PaymentIntent,
    PaymentState,
    RiskAssessment,
    RiskSignals,
)
from gateway.store import DistributedLock

log = logging.getLogger("agentpay.enforcement")

router = APIRouter(prefix="/v1", tags=["enforcement"])


def _empty_risk(policy_version: str) -> RiskAssessment:
    return RiskAssessment(
        signals=RiskSignals(), weighted_score=0.0, policy_version_context=policy_version
    )


async def _blocked_before_pipeline(
    *, intent: PaymentIntent, reason_codes: list[str], message: str
) -> DecisionResponse:
    """A block that happened before we had a canonical transaction — bad
    identity, revoked delegation. Still fully audited."""
    settings = get_settings()
    pa_id = f"pa_{uuid.uuid4().hex[:20]}"
    event_id, event_hash = await record_event_safe(
        event_type="decision.block",
        payment_authorization_id=pa_id,
        user_id=intent.user_id,
        agent_id=intent.agent_id,
        decision=Decision.BLOCK.value,
        reason_codes=reason_codes,
        policy_version=settings.policy_version,
        payload={"stage": "identity", "message": message},
    )
    return DecisionResponse(
        payment_authorization_id=pa_id,
        decision=Decision.BLOCK,
        reason_codes=reason_codes,
        state=PaymentState.FAILED,
        risk=_empty_risk(settings.policy_version),
        policy_version=settings.policy_version,
        audit_event_id=event_id,
        audit_hash=event_hash,
        message=message,
    )


async def record_event_safe(**kwargs) -> tuple[str | None, str | None]:
    """Audit failures must never turn a BLOCK into a 500 that a caller could
    mistake for a transient error worth retrying differently."""
    from gateway.audit import record_event

    try:
        return await record_event(**kwargs)
    except Exception:
        log.exception("failed to write audit event")
        return None, None


@router.post("/payment-intents", response_model=DecisionResponse)
async def create_payment_intent(
    intent: PaymentIntent,
    authorization: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None),
    execute: bool = Query(
        default=True,
        description="Submit to the payment provider when the decision is ALLOW.",
    ),
) -> DecisionResponse:
    settings = get_settings()

    # A caller that wants to watch this request's pipeline live subscribes to
    # its own X-Request-Id before posting. Purely additive: absent, we fall
    # back to the authorization id and the events are still published.
    emitter = PipelineEmitter(request_id=(x_request_id or "")[:128] or f"req_{uuid.uuid4().hex[:16]}")

    # --- 1. Identity & Request Integrity ---------------------------------
    emitter.start(Stage.IDENTITY)
    try:
        identity = await authenticate(authorization, intent)
    except IdentityError as exc:
        emitter.finish(
            Stage.IDENTITY,
            StageStatus.BLOCKED,
            {"reason_codes": ["INVALID_IDENTITY", exc.reason_code]},
        )
        emitter.skip_remaining(Stage.IDENTITY, ["INVALID_IDENTITY", exc.reason_code])
        return await _blocked_before_pipeline(
            intent=intent,
            reason_codes=["INVALID_IDENTITY", exc.reason_code],
            message=exc.message,
        )
    emitter.finish(
        Stage.IDENTITY,
        StageStatus.PASSED,
        {"agent_id": identity.agent_id, "delegation_id": identity.delegation_id},
    )

    # --- 2. Canonical Transaction Builder --------------------------------
    emitter.start(Stage.CANONICAL)
    pa_id = f"pa_{uuid.uuid4().hex[:20]}"
    txn = build_canonical(intent, identity, pa_id)
    emitter.payment_authorization_id = pa_id
    emitter.finish(
        Stage.CANONICAL,
        StageStatus.PASSED,
        {
            "payment_authorization_id": pa_id,
            "cart_hash": txn.cart_hash,
            "fingerprint": txn.fingerprint,
            "untrusted_fields": sorted(txn.untrusted.fields()),
        },
    )

    # Everything from the duplicate check through token issuance is one
    # critical section, keyed on the user's idempotency key.
    lock_key = f"idem:{txn.user_id}:{txn.idempotency_key}"
    try:
        async with DistributedLock(lock_key):
            return await _run_pipeline(txn, identity, execute=execute, emitter=emitter)
    except TimeoutError:
        # Another request holds the lock for this exact key. Refusing is
        # correct: two concurrent authorizations for one idempotency key is
        # precisely the race the lock exists to prevent.
        return DecisionResponse(
            payment_authorization_id=pa_id,
            decision=Decision.BLOCK,
            reason_codes=["CONCURRENT_REQUEST_IN_FLIGHT"],
            state=PaymentState.FAILED,
            risk=_empty_risk(settings.policy_version),
            policy_version=settings.policy_version,
            message="another authorization for this idempotency key is in flight",
        )


async def _run_pipeline(
    txn, identity, *, execute: bool, emitter: PipelineEmitter | None = None
) -> DecisionResponse:
    settings = get_settings()
    emitter = emitter or PipelineEmitter(request_id=txn.payment_authorization_id)

    # --- duplicate / replay detection (inside the lock) ------------------
    outcome = await pay.check_duplicate(txn)
    if outcome.is_replay:
        emitter.finish(
            Stage.CANONICAL,
            StageStatus.PASSED,
            {"idempotent_replay": True, "idempotency_key": txn.idempotency_key},
        )
        emitter.skip_remaining(Stage.CANONICAL, ["IDEMPOTENT_REPLAY"])
        stored = dict(outcome.replay_response or {})
        stored["replayed"] = True
        stored["message"] = "idempotent replay: identical stored response returned"
        await record_event_safe(
            event_type="decision.idempotent_replay",
            payment_authorization_id=stored.get("payment_authorization_id"),
            user_id=txn.user_id,
            agent_id=txn.agent_id,
            decision=stored.get("decision"),
            reason_codes=["IDEMPOTENT_REPLAY"],
            policy_version=settings.policy_version,
            payload={"idempotency_key": txn.idempotency_key},
        )
        return DecisionResponse.model_validate(stored)

    # --- 3. Intent & Content Security Analyzer ---------------------------
    emitter.start(Stage.ANALYZER)
    analysis: AnalysisResult = await analyze(txn)
    emitter.finish(
        Stage.ANALYZER,
        StageStatus.PASSED,
        # Same object the audit log records; no second shape for the UI.
        analysis.to_dict(),
    )

    # --- deterministic facts + 4. Risk Engine (signals only) -------------
    emitter.start(Stage.RISK)
    ctx = await load_context(txn)
    risk = assess(txn, ctx, analysis)
    emitter.finish(
        Stage.RISK,
        StageStatus.PASSED,
        {"signals": risk.signals.model_dump(), "weighted_score": risk.weighted_score},
    )

    approval = await approvals_svc.evaluate_token(txn.approval_token)

    # --- 5. Policy Decision Point (the only decider) ---------------------
    policy_input = build_input(
        txn=txn,
        ctx=ctx,
        analysis=analysis,
        risk=risk,
        identity=IdentityFinding(valid=True, user_id=identity.user_id),
        duplicate=outcome.finding,
        approval=approval,
        allow_degraded_classifier=settings.allow_degraded_classifier,
    )
    emitter.start(Stage.PDP)
    verdict: PDPResult = await evaluate(policy_input)
    emitter.finish(
        Stage.PDP,
        {
            Decision.ALLOW: StageStatus.PASSED,
            Decision.REQUIRE_APPROVAL: StageStatus.PAUSED,
            Decision.BLOCK: StageStatus.BLOCKED,
        }[verdict.decision],
        {
            "decision": verdict.decision.value,
            "reason_codes": verdict.reason_codes,
            "policy_version": verdict.policy_version,
            "pdp_available": verdict.pdp_available,
        },
    )

    response = DecisionResponse(
        payment_authorization_id=txn.payment_authorization_id,
        decision=verdict.decision,
        reason_codes=verdict.reason_codes,
        state=PaymentState.CREATED,
        risk=risk,
        policy_version=verdict.policy_version,
    )

    await pay.persist_transaction(
        txn,
        decision=verdict.decision.value,
        reason_codes=verdict.reason_codes,
        state=PaymentState.CREATED,
        risk=risk.model_dump(),
        policy_version=verdict.policy_version,
    )

    # --- 6. Payment Authorization Service --------------------------------
    emitter.start(Stage.AUTHORIZATION)
    if verdict.decision is Decision.BLOCK:
        response.state = PaymentState.FAILED
        response.message = "blocked by policy; no token issued, provider not contacted"
        await pay.set_state(
            txn.payment_authorization_id,
            PaymentState.FAILED,
            detail="; ".join(verdict.reason_codes)[:200],
            audit=False,
        )
        # The claim the visualiser draws as a severed beam: no token was
        # minted and the provider was never called.
        emitter.finish(
            Stage.AUTHORIZATION,
            StageStatus.SKIPPED,
            {
                "reason_codes": verdict.reason_codes,
                "token_issued": False,
                "provider_contacted": False,
                "never_reached": True,
            },
        )

    elif verdict.decision is Decision.REQUIRE_APPROVAL:
        request = await approvals_svc.create_request(txn, verdict.reason_codes)
        response.state = PaymentState.CREATED
        response.message = (
            "human approval required; approve at "
            f"/v1/approvals/{request.approval_request_id}/grant then retry with "
            "the returned approval_token"
        )
        emitter.finish(
            Stage.AUTHORIZATION,
            StageStatus.PAUSED,
            {
                "reason_codes": verdict.reason_codes,
                "approval_request_id": request.approval_request_id,
                "token_issued": False,
                "provider_contacted": False,
            },
        )

    else:  # ALLOW
        await record_velocity(txn)
        token = await pay.authorize(txn, verdict.policy_version)
        response.state = PaymentState.AUTHORIZED
        response.authorization = AuthorizationToken(
            token=token.token,
            payment_authorization_id=txn.payment_authorization_id,
            merchant_id=txn.merchant_id,
            amount=txn.amount,
            currency=txn.currency,
            cart_hash=txn.cart_hash,
            expires_at=__import__("datetime").datetime.fromtimestamp(
                token.expires_at, tz=__import__("datetime").timezone.utc
            ),
            policy_version=verdict.policy_version,
        )
        if execute:
            provider = await pay.submit(txn, token)
            response.state = provider.state
            response.provider_reference = provider.provider_reference
            response.message = provider.detail or "payment confirmed"
            if provider.state is PaymentState.UNKNOWN:
                response.message = (
                    "provider did not respond; payment is UNKNOWN and queued for "
                    "reconciliation. This is not a success."
                )
        else:
            response.message = "authorized; token issued, not submitted"
        emitter.finish(
            Stage.AUTHORIZATION,
            StageStatus.PASSED,
            {
                "token_issued": True,
                "provider_contacted": execute,
                "state": response.state.value,
                "provider_reference": response.provider_reference,
            },
        )

    # --- 7. Immutable Audit ----------------------------------------------
    emitter.start(Stage.AUDIT)
    event_id, event_hash = await record_event_safe(
        event_type=f"decision.{verdict.decision.value.lower()}",
        payment_authorization_id=txn.payment_authorization_id,
        user_id=txn.user_id,
        agent_id=txn.agent_id,
        decision=verdict.decision.value,
        reason_codes=verdict.reason_codes,
        risk=risk.model_dump(),
        policy_version=verdict.policy_version,
        payload={
            "merchant_id": txn.merchant_id,
            "amount": str(txn.amount),
            "currency": txn.currency,
            "cart_hash": txn.cart_hash,
            "fingerprint": txn.fingerprint,
            "idempotency_key": txn.idempotency_key,
            "state": response.state.value,
            "analysis": analysis.to_dict(),
            "context": ctx.to_dict(),
            "pdp_available": verdict.pdp_available,
        },
    )
    response.audit_event_id = event_id
    response.audit_hash = event_hash
    emitter.finish(
        Stage.AUDIT,
        StageStatus.PASSED if event_id else StageStatus.FAILED,
        {
            "audit_event_id": event_id,
            "audit_hash": event_hash,
            "decision": verdict.decision.value,
            "reason_codes": verdict.reason_codes,
        },
    )

    # Only non-conflicting outcomes become the stored idempotent response; a
    # replay attempt must not be able to install itself as the canonical answer.
    #
    # REQUIRE_APPROVAL is deliberately not memoised at all: it is an interim
    # answer, and the whole point of the flow is that the agent comes back with
    # the same transaction plus an approval token.
    if not outcome.is_conflict and verdict.decision is not Decision.REQUIRE_APPROVAL:
        await pay.remember_outcome(
            txn,
            response.model_dump(mode="json"),
            reserve_fingerprint=verdict.decision is Decision.ALLOW,
        )

    return response


# --- approvals ------------------------------------------------------------


@router.get("/approvals/{approval_request_id}")
async def get_approval(approval_request_id: str) -> dict:
    request = await approvals_svc.load_request(approval_request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="unknown or expired approval request")
    return request.summary()


@router.post("/approvals/{approval_request_id}/grant")
async def grant_approval(approval_request_id: str) -> dict:
    """Stands in for a human tapping 'approve' in a banking app. The returned
    token is bound to the exact amount, merchant, currency and cart the human
    was shown."""
    token = await approvals_svc.grant(approval_request_id)
    if token is None:
        raise HTTPException(status_code=404, detail="unknown or expired approval request")
    request = await approvals_svc.load_request(approval_request_id)
    await record_event_safe(
        event_type="approval.granted",
        payment_authorization_id=request.payment_authorization_id if request else None,
        user_id=request.user_id if request else None,
        reason_codes=["HUMAN_APPROVAL_GRANTED"],
        payload=request.summary() if request else {},
    )
    return {
        "approval_token": token,
        "bound_to": request.summary() if request else {},
        "note": "retry the payment intent with this token in `approval_token`",
    }


# --- operations -----------------------------------------------------------


@router.post("/reconcile")
async def reconcile() -> dict:
    """Resolve UNKNOWN payments by querying the provider. Never re-submits."""
    resolved = await pay.reconcile_unknown()
    expired = await pay.expire_stale_authorizations()
    return {"reconciled": resolved, "expired_authorizations": expired}


@router.get("/transactions")
async def list_transactions(limit: int = Query(default=50, le=500)) -> dict:
    async with session_scope() as s:
        rows = (
            (
                await s.execute(
                    select(Transaction).order_by(desc(Transaction.created_at)).limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return {
            "transactions": [
                {
                    "payment_authorization_id": r.payment_authorization_id,
                    "created_at": r.created_at.isoformat(),
                    "user_id": r.user_id,
                    "agent_id": r.agent_id,
                    "merchant_id": r.merchant_id,
                    "amount": str(r.amount),
                    "currency": r.currency,
                    "decision": r.decision,
                    "reason_codes": r.reason_codes,
                    "state": r.state,
                    "weighted_score": (r.risk or {}).get("weighted_score"),
                    "policy_version": r.policy_version,
                    "provider_reference": r.provider_reference,
                }
                for r in rows
            ]
        }


@router.get("/audit/events")
async def audit_events(limit: int = Query(default=100, le=1000)) -> dict:
    async with session_scope() as s:
        rows = (
            (await s.execute(select(AuditEvent).order_by(desc(AuditEvent.seq)).limit(limit)))
            .scalars()
            .all()
        )
        return {
            "events": [
                {
                    "seq": r.seq,
                    "event_id": r.event_id,
                    "event_type": r.event_type,
                    "created_at": r.created_at.isoformat(),
                    "payment_authorization_id": r.payment_authorization_id,
                    "user_id": r.user_id,
                    "agent_id": r.agent_id,
                    "decision": r.decision,
                    "reason_codes": r.reason_codes,
                    "risk": r.risk,
                    "policy_version": r.policy_version,
                    "payload": r.payload,
                    "prev_hash": r.prev_hash,
                    "event_hash": r.event_hash,
                }
                for r in rows
            ]
        }


@router.get("/audit/verify")
async def audit_verify() -> dict:
    result = await verify_chain()
    head = await chain_head()
    return {**result, **head, "checkpoint": publish_checkpoint(head["head_hash"])}
